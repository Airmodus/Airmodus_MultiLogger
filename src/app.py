from datetime import datetime as dt
from time import time, sleep
import os
import locale
import platform
import logging
import traceback
import json
import warnings
import sys

from numpy import full, nan, array, polyval, array_equal, roll, nanmean, isnan, linspace
from serial import Serial
from serial.serialutil import SerialException
from PyQt5.QtGui import QPalette, QColor, QIntValidator, QDoubleValidator, QFont, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QLocale
from PyQt5.QtWidgets import (QMainWindow, QSplitter, QApplication, QTabWidget, QGridLayout, QLabel, QWidget,
    QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox, QTextEdit, QSizePolicy,
    QFileDialog, QComboBox, QGraphicsRectItem, QMessageBox)
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, PlotCurveItem, LegendItem, PlotItem, mkPen, mkBrush
from pyqtgraph.parametertree import Parameter, ParameterTree, parameterTypes

from config import *
from utils import (
    compile_cpc_data,
    compile_cpc_settings,
    compile_psm_data,
    compile_psm_settings,
    _manage_plot_array,
    _roll_pulse_array,
    psm_update,
    psm_flow_send,
    cpc_flow_send,
    ten_hz_clicked,
    command_entered
)
from widgets import (
    SetWidget,
    SpinBox,
    DoubleSpinBox,
    ToggleButton,
    StartButton,
    IndicatorWidget,
    CommandWidget,
    StepsWidget,
    FloatTextEdit,
    StatusLights,
)
from plots import (
    MainPlot,
    SinglePlot, 
    TriplePlot, 
    AFMPlot, 
    ElectrometerPlot
)

from devices import (
    CPCWidget, 
    PSMWidget, 
    CO2Widget, 
    ElectrometerWidget, 
    RHTPWidget,
    eDiluterWidget, 
    AFMWidget, 
    TSIWidget, 
    ExampleDeviceWidget
)

from managers import (
    DataHolder,
    TimerService,
    DeviceManager,
    PlotManager
)

from serial_connection import SerialDeviceConnection
from params import ScalableGroup, params, p


# main program
class MainWindow(QMainWindow):

    def __init__(self, params=p, parent=None):
        super().__init__() # super init function must be called when subclassing a Qt class
        self.setWindowTitle("Airmodus MultiLogger v. " + version_number) # set window title

        self.params = params # predefined parameter tree
        self.config_file_path = "" # path to the configuration file

        # Extracted inits
        self.data_holder = DataHolder()
        self._setup_parameter_tree()
        self._setup_gui()
        self._connect_signals()

        self.device_manager = DeviceManager(self.params, self.data_holder, self.data_holder.device_widgets)
        self.device_manager.list_com_ports()
        self.plot_manager = PlotManager(self, self.data_holder, self.main_plot)

        self.timer_service = TimerService(self, self.data_holder, self.device_manager, self.plot_manager)
        self.timer_service.start()

        # load ini file if available
        self.load_ini()

    def _setup_parameter_tree(self):
        """Create and configure the ParameterTree."""
        # create parameter tree
        self.t = ParameterTree()
        self.t.setParameters(p, showTop=False)
        self.t.setHeaderHidden(True)

        # load CSS style and apply it to the main window
        with open(script_path + "/style.css", "r") as f:
            self.style = f.read()
        self.setStyleSheet(self.style)

        # create error and disconnected icon objects
        self.error_icon = QIcon(resource_path + "/icons/error.png")
        self.disconnected_icon = QIcon(resource_path + "/icons/disconnected.png")

    def _setup_gui(self):
        """Build main layout, splitters, tabs, etc."""
        # create and set central widget (requirement of QMainWindow)
        self.main_splitter = QSplitter()
        self.setCentralWidget(self.main_splitter)
        # create status lights widget instance showing measurement and saving status
        self.status_lights = StatusLights()
        # create logo pixmap label
        self.logo = QLabel(alignment=Qt.AlignCenter, objectName="logo")
        pixmap = QPixmap(resource_path + "/images/airmodus-envea-logo.png")
        self.logo.setPixmap(pixmap.scaled(400, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        # create left side vertical splitter
        # contains parameter tree and status widget
        left_splitter = QSplitter(Qt.Vertical) # split vertically
        left_splitter.addWidget(self.logo) # add logo
        left_splitter.addWidget(self.t) # add parameter tree widget
        left_splitter.addWidget(self.status_lights) # add status lights widget
        left_splitter.setSizes([100, 800, 100]) # set relative sizes of widgets
        # create right side tab widget containing device widgets as tabs
        # new devices are added to this as tabs in device_added function
        self.device_tabs = QTabWidget()
        self.main_plot = MainPlot() # create main plot widget instance
        self.device_tabs.addTab(self.main_plot, "Main plot") # add main plot widget to tab widget
        # add widgets to main_splitter (MainWindow's central widget)
        self.main_splitter.addWidget(left_splitter) # contains parameter tree and status lights
        self.main_splitter.addWidget(self.device_tabs) # contains devices as tabs
        self.main_splitter.setSizes([2000, 8000]) # set relative sizes of widgets
        # resize window (int x, int y)
        self.resize(1400, 800)

    def _connect_signals(self):
        """Wire up all signals/slots."""

        # connect parameter tree's save data parameter
        self.params.child('Data settings').child('Save data').sigValueChanged.connect(self.save_changed)
        # connect file path parameter to filepath_changed function
        self.params.child('Data settings').child('File path').sigValueChanged.connect(self.filepath_changed)
        # connect file tag parameter to reset_all_filenames function
        self.params.child('Data settings').child('File tag').sigValueChanged.connect(self.data_holder.reset_all_filenames)
        # connect com port update button
        self.params.child('Serial ports').child('Update serial ports').sigActivated.connect(self.set_inquiry_flag)

        # connect parameter tree's sigChildAdded signal to device_added function
        p.child("Device settings").sigChildAdded.connect(self.device_added)
        # connect parameter tree's sigChildRemoved signal to device_removed function
        p.child("Device settings").sigChildRemoved.connect(self.device_removed)
        # connect main_plot's viewboxes' sigXRangeChanged signals to x_range_changed function
        for viewbox in self.main_plot.viewboxes.values():
            viewbox.sigXRangeChanged.connect(self.x_range_changed)
        # connect main_plot's auto range button click to auto_range_clicked function
        self.main_plot.plot.autoBtn.clicked.connect(self.auto_range_clicked)


        # connect parameter tree's sigTreeStateChanged signal to save_ini function
        self.params.sigTreeStateChanged.connect(self.save_ini)
        # connect 'Save settings' and 'Load settings' buttons
        self.params.child('Data settings').child('Save settings').sigActivated.connect(self.manual_save_configuration)
        self.params.child('Data settings').child('Load settings').sigActivated.connect(self.manual_load_configuration)

    
    # write data to file(s)
    def write_data(self):
        # if saving is on
        if self.params.child('Data settings').child('Save data').value():

            # create timestamp from data_holder.current_time
            timestamp = dt.fromtimestamp(self.data_holder.current_time)
            timeStampStr = str(timestamp.strftime("%Y.%m.%d %H:%M:%S"))

            # go through each device
            for dev in self.params.child('Device settings').children():

                # if device is TSI CPC, do nothing
                if dev.child('Device type').value() == TSI_CPC:
                    pass
                # if device is in pulse analysis mode, do nothing
                elif dev.child('DevID').value() in self.data_holder.pulse_analysis_index:
                    pass

                # if device is connected OR example device
                elif dev.child('Connected').value() or dev.child('Device type').value() == EXAMPLE_DEVICE:

                    try:
                        # store device id to variable for clarity
                        dev_id = dev.child('DevID').value()

                        # if device is not yet in data_holder.dat_filenames dict, create .dat file and add filename to dict
                        if dev_id not in self.data_holder.dat_filenames:
                            # format timestamp for filename
                            timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
                            # get serial number from device settings
                            serial_number = dev.child('Serial number').value()
                            # if serial number is not empty, add underscore to beginning
                            if serial_number != "":
                                serial_number = '_' + serial_number
                            # get device type from device settings
                            device_type = dev.child('Device type').value() # device type number
                            device_type_name = self.data_holder.device_names[device_type] # device type name
                            # get device nickname from device settings
                            device_nickname = dev.child('Device nickname').value()
                            # if nickname is not empty, add underscore to beginning
                            if device_nickname != "":
                                device_nickname = '_' + device_nickname
                            # get file tag from data settings
                            file_tag = self.params.child('Data settings').child('File tag').value()
                            # if file tag is not empty, add underscore to beginning
                            if file_tag != "":
                                file_tag = '_' + file_tag
                            # compile filename and add to data_holder.dat_filenames
                            if osx_mode:
                                filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.dat'
                            else:
                                filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.dat'
                            self.data_holder.dat_filenames[dev_id] = filename
                            with open(self.filePath + filename ,"w",encoding='UTF-8'):
                                pass
                            
                            # if CPC or PSM, create .par file and add filename to data_holder.par_filenames
                            if dev.child('Device type').value() in [CPC, PSM, PSM2]:
                                if osx_mode:
                                    filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.par'
                                else:
                                    filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.par'
                                self.data_holder.par_filenames[dev_id] = filename
                                with open(self.filePath + filename ,"w",encoding='UTF-8'):
                                    pass
                                self.data_holder.par_updates[dev.child('DevID').value()] = 1 # set .par update flag, ensuring new .par file is updated at start
                        
                        # check if device is Airmodus CPC and 10hz parameter is on
                        if dev.child('Device type').value() == CPC and dev.child('10 hz').value():
                            # if device is not in data_holder.ten_hz_filenames dict, create .csv file and add filename to data_holder.ten_hz_filenames
                            if dev_id not in self.data_holder.ten_hz_filenames:
                                # format timestamp for filename
                                timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
                                # get serial number from device settings
                                serial_number = dev.child('Serial number').value()
                                # if serial number is not empty, add underscore to beginning
                                if serial_number != "":
                                    serial_number = '_' + serial_number
                                # get device type from device settings
                                device_type = dev.child('Device type').value() # device type number
                                device_type_name = self.data_holder.device_names[device_type] # device type name
                                # get device nickname from device settings
                                device_nickname = dev.child('Device nickname').value()
                                # if nickname is not empty, add underscore to beginning
                                if device_nickname != "":
                                    device_nickname = '_' + device_nickname
                                # get file tag from data settings
                                file_tag = self.params.child('Data settings').child('File tag').value()
                                # if file tag is not empty, add underscore to beginning
                                if file_tag != "":
                                    file_tag = '_' + file_tag
                                # compile filename and add to data_holder.ten_hz_filenames
                                if osx_mode:
                                    filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + '_10hz' + file_tag + '.csv'
                                else:
                                    filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + '_10hz' + file_tag + '.csv'
                                self.data_holder.ten_hz_filenames[dev_id] = filename
                                # create file and write header
                                with open(self.filePath + filename ,"w",encoding='UTF-8') as file:
                                    # write header
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration 1 (#/cc),Concentration 2 (#/cc),Concentration 3 (#/cc),Concentration 4 (#/cc),Concentration 5 (#/cc),Concentration 6 (#/cc),Concentration 7 (#/cc),Concentration 8 (#/cc),Concentration 9 (#/cc),Concentration 10 (#/cc)')
                            
                        # get filename from dictionary and add path to front
                        filename = self.filePath + self.data_holder.dat_filenames[dev_id]
                        
                        # Check the type and length of header
                        with open(filename, 'r', encoding='UTF-8') as file:
                            file.seek(0)
                            header_row1 = file.readline()
                            header_len = len(header_row1)
                            # At the moment only check is a header exists
                            if header_len == 0:
                                write_headers = 1
                            else:
                                write_headers = 0

                        # append file with new data
                        with open(filename, 'a', newline='\n', encoding='UTF-8') as file:

                            # write headers if they don't exist
                            if write_headers == 1:
                            #if len(file.readline()) == 0:
                                if dev.child('Device type').value() == CPC: # CPC
                                    # TODO complete CPC headers, check if ok
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration (#/cc),Dead time (µs),Number of pulses,Saturator T (C),Condenser T (C),Optics T (C),Cabin T (C),Inlet P (kPa),Critical orifice P (kPa),Nozzle P (kPa),Cabin P (kPa),Liquid level,Pulse ratio,Total CPC errors,System status error')
                                elif dev.child('Device type').value() == PSM: # PSM
                                    # TODO check if PSM headers are ok
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),Scan status,PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)')
                                elif dev.child('Device type').value() == PSM2: # PSM 2.0
                                    # TODO check if correct
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),Scan status,Vacuum flow (lpm),PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)')
                                elif dev.child('Device type').value() == ELECTROMETER: # ELECTROMETER
                                    file.write('YYYY.MM.DD hh:mm:ss,Voltage 1 (V),Voltage 2 (V),Voltage 3 (V)')
                                elif dev.child('Device type').value() == CO2_SENSOR: # CO2
                                    file.write('YYYY.MM.DD hh:mm:ss,CO2 (ppm),T (C),RH (%)')
                                elif dev.child('Device type').value() == RHTP: # RHTP
                                    file.write('YYYY.MM.DD hh:mm:ss,RH (%),T (C),P (Pa)')
                                elif dev.child('Device type').value() == AFM: # AFM
                                    file.write('YYYY.MM.DD hh:mm:ss,Flow (lpm),Standard flow (slpm),RH (%),T (C),P (Pa)')
                                elif dev.child('Device type').value() == EDILUTER: # eDiluter
                                    file.write('YYYY.MM.DD hh:mm:ss,Status,P1,P2,T1,T2,T3,T4,T5,T6,DF1,DF2,DFTot')
                                elif dev.child('Device type').value() == EXAMPLE_DEVICE:
                                    file.write('YYYY.MM.DD hh:mm:ss,Random value (0-100)')
                                else:
                                    file.write('YYYY.MM.DD hh:mm:ss,value1,value2,value3')
                            
                            # Write the actual data
                            file.write("\n") # create new line
                            file.write(timeStampStr+',') # add timestamp
                            # convert data to string
                            write_data = ','.join(str(vals) for vals in self.data_holder.latest_data[dev_id])
                            # write data
                            file.write(write_data)
                        
                        # if CPC or PSM, append .par file with new settings
                        if dev.child('Device type').value() in [CPC, PSM, PSM2]:
                            # get filename from dictionary and add path to front
                            filename = self.filePath + self.data_holder.par_filenames[dev_id]

                            # Check the type and length of header
                            with open(filename, 'r', encoding='UTF-8') as file:
                                file.seek(0)
                                header_row1 = file.readline()
                                header_len = len(header_row1)
                                # At the moment only check is a header exists
                                if header_len == 0:
                                    write_headers = 1
                                else:
                                    write_headers = 0
                        
                            # append file with new data
                            with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                                # write headers if they don't exist
                                if write_headers == 1:
                                    if dev.child('Device type').value() == CPC: # CPC
                                        file.write('YYYY.MM.DD hh:mm:ss,Averaging time (s),Nominal flow rate (lpm),Flow rate (lpm),Saturator T setpoint (C),Condenser T setpoint (C),Optics T setpoint (C),Autofill,OPC counter threshold voltage (mV),OPC counter threshold 2 voltage (mV),Water removal,Dead time correction,Drain,K-factor,Tau,Command input')
                                    elif dev.child('Device type').value() == PSM: # PSM
                                        file.write('YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),CO flow rate (lpm),amp,cen,sig,slope,intercept,modeInUse,CPC IDN,CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input')
                                    elif dev.child('Device type').value() == PSM2: # PSM2
                                        file.write('YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),amp,cen,sig,slope,intercept,modeInUse,CPC IDN,CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input')
                                
                                # reset local update_par flag
                                update_par = 0

                                # if device's .par update flag is set, write data
                                if self.data_holder.par_updates[dev_id] == 1:
                                    update_par = 1
                                
                                # else if a command has been entered, write data
                                elif dev_id in self.data_holder.latest_command:
                                    update_par = 1
                                
                                # else check if device is PSM and if there are changes in connected CPC
                                elif dev.child('Device type').value() in [PSM, PSM2]:
                                    # check if Connected CPC parameter has been changed
                                    if dev.cpc_changed == True: # check device's cpc_changed flag
                                        update_par = 1
                                        dev.cpc_changed = False # reset cpc_changed flag
                                    # else check if connected CPC is not 'None'
                                    elif dev.child('Connected CPC').value() != 'None':
                                        # check if connected CPC is in par_updates dictionary and its .par update flag is set
                                        if dev.child('Connected CPC').value() in self.data_holder.par_updates and self.data_holder.par_updates[dev.child('Connected CPC').value()] == 1:
                                            update_par = 1
                                
                                # if update_par flag is set
                                if update_par == 1:
                                    file.write("\n")
                                    # Add timestamp
                                    file.write(timeStampStr+',')
                                    # Convert data to string                            
                                    write_data = ','.join(str(vals) for vals in self.data_holder.latest_settings[dev_id])
                                    file.write(write_data)

                                    # if device type is PSM
                                    if dev.child('Device type').value() in [PSM, PSM2]: # if PSM
                                        # get connected CPC ID
                                        cpc_id = dev.child('Connected CPC').value()

                                        # if connected CPC is not 'None'
                                        if cpc_id != 'None':
                                            # get connected CPC device parameter
                                            for cpc in self.params.child('Device settings').children():
                                                if cpc.child('DevID').value() == cpc_id:
                                                    cpc_device = cpc
                                                    break
                                            # if CPC is connected Airmodus CPC, write connected CPC settings
                                            if cpc_device.child('Connected').value() and cpc_device.child('Device type').value() == CPC:
                                                cpc_idn = cpc_device.child('Serial number').value()
                                                cpc_settings = self.data_holder.latest_settings[cpc_id]
                                                file.write(',') # separate PSM and CPC settings with comma
                                                # compile connected CPC settings
                                                connected_cpc_settings = [
                                                    cpc_idn, # connected CPC serial number (IDN)
                                                    cpc_settings[6], cpc_settings[11], cpc_settings[9], # autofill, drain, water removal
                                                    cpc_settings[3], cpc_settings[4], cpc_settings[5], # T set: saturator, condenser, optics
                                                    cpc_settings[2], cpc_settings[0] # inlet flow rate (measured), aveaging time
                                                ]
                                                # write connected CPC settings
                                                write_data = ','.join(str(vals) for vals in connected_cpc_settings)
                                                file.write(write_data)
                                            
                                            else: # if CPC is not connected or not Airmodus CPC, write nan values
                                                file.write(',nan,nan,nan,nan,nan,nan,nan,nan,nan')
                                        
                                        else: # if no connected CPC selected, write nan values
                                            file.write(',nan,nan,nan,nan,nan,nan,nan,nan,nan')
                                        
                                    # check if device is in latest_command dictionary
                                    if dev_id in self.data_holder.latest_command:
                                        # write latest command to file and remove from dictionary
                                        file.write(',' + self.data_holder.latest_command.pop(dev_id))
                        
                        # check if device is Airmodus CPC and 10hz parameter is on
                        if dev.child('Device type').value() == CPC and dev.child('10 hz').value():
                            # check if device is in latest_ten_hz dictionary
                            if dev_id in self.data_holder.latest_ten_hz:
                                # get filename from dictionary and add path to front
                                filename = self.filePath + self.data_holder.ten_hz_filenames[dev_id]
                                # append file with new data
                                with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                                    file.write("\n")
                                    # Add timestamp
                                    file.write(timeStampStr+',')
                                    # Convert data to string
                                    write_data = ','.join(str(vals) for vals in self.data_holder.latest_ten_hz[dev_id])
                                    file.write(write_data)

                    # if saving fails, set saving status to 0
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        self.data_holder.saving_status = 0 # set saving status to 0
                
                # if device is not connected
                else:
                    pass
                # TODO change saving status if device is not connected?

        else: # if saving is toggled off
            self.data_holder.saving_status = 0 # set saving status to 0
        
        # write data to pulse analysis file if pulse analysis is on
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            if dev_id in self.data_holder.pulse_analysis_index:
                if self.data_holder.pulse_analysis_index[dev_id] is not None: # when index is None, analysis has reached its end
                    try:
                        # calculate current pulse duration
                        dead_time = self.data_holder.latest_data[dev_id][1]
                        number_of_pulses = self.data_holder.latest_data[dev_id][2]
                        if number_of_pulses == 0:
                            pulse_duration = nan # if number of pulses is 0, set pulse duration to nan
                        else:
                            # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                            pulse_duration = round(dead_time * 1000 / number_of_pulses, 2)
                        # get current threshold value with data_holder.pulse_analysis_index
                        threshold_value = PULSE_ANALYSIS_THRESHOLDS[self.data_holder.pulse_analysis_index[dev_id]]
                        # get filename from dictionary (includes file path)
                        filename = self.data_holder.pulse_analysis_filenames[dev_id]
                        # append file with new data
                        with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                            file.write('\n') # create new line
                            file.write(str(threshold_value) + ',' + str(number_of_pulses) + ',' + str(dead_time) + ',' + str(pulse_duration))
                        # increase data_holder.pulse_analysis_index by 1
                        self.data_holder.pulse_analysis_index[dev_id] += 1
                        # if all thresholds have been gone through, end pulse analysis
                        if self.data_holder.pulse_analysis_index[dev_id] >= len(PULSE_ANALYSIS_THRESHOLDS):
                            self.pulse_analysis_stop(dev_id, dev)
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        # stop pulse analysis if exception occurs
                        self.pulse_analysis_stop(dev_id, dev)
    
    # triggered when saving is toggled on/off
    def save_changed(self):
        # if saving is toggled on
        if self.params.child('Data settings').child('Save data').value():
            # store start day
            self.start_day = dt.now().strftime("%m%d")
            # get file path
            self.filePath = self.params.child('Data settings').child('File path').value()
            # set file path as read only
            self.params.child('Data settings').child('File path').setReadonly(True)
        # if saving is toggled off, reset filename dictionaries
        else:
            self.data_holder.reset_all_filenames()
            # disable read only file path
            self.params.child('Data settings').child('File path').setReadonly(False)

    def filepath_changed(self):
        # set file path
        self.filePath = self.params.child('Data settings').child('File path').value()
        # reset filename dictionaries
        self.data_holder.data_holder.reset_all_filenames()
    
    
    # remove specific device from filename dictionaries, results in new files being created
    def reset_device_filenames(self, dev_id):
        if dev_id in self.data_holder.dat_filenames:
            self.data_holder.dat_filenames.pop(dev_id)
        if dev_id in self.data_holder.par_filenames:
            self.data_holder.par_filenames.pop(dev_id)
        if dev_id in self.data_holder.par_updates:
            self.data_holder.par_updates.pop(dev_id)
        if dev_id in self.data_holder.ten_hz_filenames:
            self.data_holder.ten_hz_filenames.pop(dev_id)

    
    # compare current day to file start day (self.start_day defined in save_changed)
    def compare_day(self):
        # check if saving is on
        if self.params.child('Data settings').child('Save data').value():
            # check if new file should be started at midnight
            if self.params.child("Data settings").child('Generate daily files').value():
                current_day = dt.fromtimestamp(self.data_holder.current_time).strftime("%m%d")
                if current_day != self.start_day:
                    self.data_holder.reset_all_filenames() # start new file if day has changed
                    # update start day
                    self.start_day = current_day
    
    # set COM port inquiry flag
    def set_inquiry_flag(self):
        self.dataholder.inquiry_flag = True
        self.data_holder.inquiry_time = time()
        self.data_holder.com_descriptions = {} # reset com descriptions
    

    def save_ini(self):
        # check if resume on startup is on
        resume_measurements = 0
        if self.params.child('Data settings').child('Resume on startup').value():
            resume_measurements = 1
        # store resume config path
        self.config_file_path = os.path.join(save_path, 'resume_config.json')
        with open(os.path.join(save_path, 'config.ini'),'w') as f:
            f.write(self.config_file_path)
            f.write(';')
            f.write(str(resume_measurements))
        # save the configuration to the JSON file
        self.save_configuration(self.config_file_path)
    
    def load_ini(self):
        try:
            # load the configuration file "config.ini" from the save_path
            with open(os.path.join(save_path, 'config.ini'),'r') as f:
                config = f.read()
                json_path = config.split(';')[0]
                resume_measurements = config.split(';')[1]
                # If json path is empty
                if not json_path:
                    json_path = os.path.join(save_path, 'resume_config.json')
                self.config_file_path = json_path
                resume_measurements = int(resume_measurements)
                # if resume on startup is on, load the stored configuration
                if resume_measurements:
                    self.load_configuration(json_path)
        except Exception as e:
            # If the file does not exist, raise an exception saying that the file does not exist
            #print("No ini file found")
            print(traceback.format_exc())
        
    def save_configuration(self, json_path):
        # Get the parameter tree values
        parameter_values = self.save_parameters_recursive(self.params)
        # Save the configuration to the JSON file
        with open(json_path, 'w') as file:
            json.dump(parameter_values, file)
    
    def save_parameters_recursive(self, parameters):
        result = {}
        for param in parameters:
            if param.hasChildren():
                result[param.name()] = self.save_parameters_recursive(param.children())
            else:
                # Check if the parameter value is an instance of SerialDeviceConnection
                if isinstance(param.value(), SerialDeviceConnection):
                    # store parameter value as None
                    result[param.name()] = None
                else:
                    result[param.name()] = param.value()
        return result

    def load_configuration(self, json_path=None):
        if json_path:
            # Load the configuration from the JSON file
            with open(json_path, 'r') as file:
                parameter_values = json.load(file)
            # Add devices in configuration file to the parameter tree
            self.load_devices(parameter_values.get('Device settings', {}))
            # Set the loaded parameter values to the parameter tree
            self.load_parameters_recursive(self.params, parameter_values)
    
    def load_devices(self, device_settings):
        # remove all devices from the parameter tree
        self.params.child('Device settings').clearChildren()
        try:
            # go through each device in the device settings
            for dev_name, dev_values in device_settings.items():
                # get 'DevID' and 'Device type' values
                dev_id = dev_values.get('DevID', None)
                dev_type = dev_values.get('Device type', None)
                # set n_devices to current dev_id
                self.params.child('Device settings').n_devices = dev_id
                # add device to the parameter tree
                self.params.child('Device settings').addNew(self.data_holder.device_names[dev_type], device_name=dev_name)
        except AttributeError:
            pass
            
    def load_parameters_recursive(self, parameters, values):
        for param in parameters:
            if param.hasChildren():
                self.load_parameters_recursive(param.children(), values.get(param.name(), {}))
            else:
                if param.name() == 'Connection':
                    # skip 'Connection' parameter (SerialDeviceConnection)
                    # SerialDeviceConnection was created when the device was added (load_devices)
                    pass
                elif param.name() == 'Connected':
                    # skip 'Connected' parameter, this is checked in connection_test()
                    pass
                # Check if parameter name is CO flow
                elif param.name() == 'CO flow':
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
                    # Set CO flow value to related PSM widget
                    try:
                        self.data_holder.device_widgets[param.parent().child("DevID").value()].set_tab.set_co_flow.value_spinbox.setValue(round(float(param.value()), 3))
                    except ValueError:
                        pass # if value has not been saved, skip
                # Check if parameter name is 10 hz
                elif param.name() == '10 hz':
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
                    # if device type is PSM or PSM2
                    if param.parent().child('Device type').value() in [PSM, PSM2]:
                        # Set 10 hz status (True/False) to ten_hz button
                        self.data_holder.device_widgets[param.parent().child("DevID").value()].measure_tab.ten_hz.change_color(int(values.get(param.name(), param.value())))
                else:
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
    
    def manual_save_configuration(self):
        # Ask the user for the file path to save the configuration
        file_dialog = QFileDialog(self)
        json_path, _ = file_dialog.getSaveFileName(self, 'Save Configuration', '', 'JSON Files (*.json)')
        self.save_configuration(json_path)
    
    def manual_load_configuration(self):
        # Ask the user for the file path to load the configuration
        file_dialog = QFileDialog(self)
        json_path, _ = file_dialog.getOpenFileName(self, 'Load Configuration', '', 'JSON Files (*.json)')
        self.load_configuration(json_path)
        
    def x_range_changed(self, viewbox):
        # if autoscale y is on
        if self.params.child("Plot settings").child('Autoscale Y').value():
            viewbox.enableAutoRange(axis='y')
            viewbox.setAutoVisible(y=True)
    
    # called when main plot's auto range button is clicked
    def auto_range_clicked(self):
        # disable follow
        self.params.child("Plot settings").child('Follow').setValue(False)
        # set autorange on for individual plots
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            dev_type = dev.child('Device type').value()
            if dev_type == ELECTROMETER:
                for plot in self.data_holder.device_widgets[dev_id].plot_tab.plots:
                    plot.enableAutoRange()
            else:
                self.data_holder.device_widgets[dev_id].plot_tab.plot.enableAutoRange()
            
    
    # set the 'Plot to main' selection of all RHTP devices to the same value
    # called when 'Plot to main' selection of any RHTP device is changed
    def rhtp_axis_changed(self, value):
        for dev in self.params.child('Device settings').children():
            if dev.child('Device type').value() == RHTP and dev.child('Plot to main').value() != value:
                dev.child('Plot to main').setValue(value)
    # same as above but for AFM devices
    def afm_axis_changed(self, value):
        for dev in self.params.child('Device settings').children():
            if dev.child('Device type').value() == AFM and dev.child('Plot to main').value() != value:
                dev.child('Plot to main').setValue(value)
    
    
    # start CPC pulse analysis, stop normal operation
    def pulse_analysis_start(self, device_id, device_param):
        # ask for user confirmation before starting
        start = QMessageBox.question(self, 'Start pulse analysis?', 'Regular measurement for this device will pause for one minute.\nStart pulse analysis?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if start == QMessageBox.No:
            return
        try:
            # add device to data_holder.pulse_analysis_index dictionary with index value 0
            self.data_holder.pulse_analysis_index[device_id] = 0
            # update pulse analysis status
            self.data_holder.device_widgets[device_id].pulse_quality.update_pa_status(True)
            # disable command input
            self.data_holder.device_widgets[device_id].set_tab.command_widget.disable_command_input()

            # get original threshold value from latest_settings
            # value should stay intact during pulse analysis, settings are not updated
            original_threshold = self.data_holder.latest_settings[device_id][7]
            # if threshold value is nan, stop pulse analysis
            if isnan(original_threshold):
                self.pulse_analysis_stop(device_id, device_param)
                return

            # clear previous pulse analysis points
            self.data_holder.device_widgets[device_id].pulse_quality.clear_analysis_points()

            # create file and store threshold value
            filepath = self.params.child('Data settings').child('File path').value()
            # timestamp
            timestamp = dt.fromtimestamp(self.data_holder.current_time)
            timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
            # serial number
            serial_number = device_param.child('Serial number').value()
            # compile filename and add to data_holder.pulse_analysis_filenames dictionary
            if osx_mode:
                filename = filepath + '/' + timestamp_file + '_pulse_analysis_' + serial_number + '.csv'
            else:
                filename = filepath + '\\' + timestamp_file + '_pulse_analysis_' + serial_number + '.csv'
            self.data_holder.pulse_analysis_filenames[device_id] = filename
            with open(filename, 'w', newline='\n', encoding='UTF-8') as file:
                # write info row (serial number and original threshold)
                file.write(serial_number + ' original threshold: ' + str(original_threshold) + ' mV')
                file.write('\n') # create new line
                # write header
                file.write('Threshold (mV),Number of pulses,Dead time (µs),Pulse duration (ns)')
        
        except Exception as e:
            print(traceback.format_exc())
            logging.exception(e)
            # if pulse analysis cannot be started, stop it (resume normal operation)
            self.pulse_analysis_stop(device_id, device_param)
    
    # stop CPC pulse analysis, resume normal operation
    def pulse_analysis_stop(self, device_id, device_param):
        # restore original threshold value to device
        try:
            device_param.child('Connection').value().send_message(":SET:OPC:THRS " + str(self.data_holder.latest_settings[device_id][7]))
        except Exception as e:
            print(traceback.format_exc())
            logging.exception(e)
        # clear current threshold value
        self.data_holder.device_widgets[device_id].pulse_quality.current_threshold.setText("")
        # set data_holder.pulse_analysis_index to None (signaling end of pulse analysis)
        self.data_holder.pulse_analysis_index[device_id] = None
        # remove device id from data_holder.pulse_analysis_index dictionary with delay
        # delay ensures CPC has time to set original threshold before measurement continues
        QTimer.singleShot(1000, lambda: self.data_holder.pulse_analysis_index.pop(device_id))
        # remove device id from data_holder.pulse_analysis_filenames dictionary
        if device_id in self.data_holder.pulse_analysis_filenames:
            self.data_holder.pulse_analysis_filenames.pop(device_id)

        # TODO plot gaussian fit and calculate nRMSE
        # analysis values are stored as listed tuples (pulse duration, threshold value)
        # analysis_values = self.data_holder.device_widgets[device_id].pulse_quality.analysis_values
        # pulse_durations = [x[0] for x in analysis_values]
        # thresholds = [x[1] for x in analysis_values]

        # enable command input
        self.data_holder.device_widgets[device_id].set_tab.command_widget.enable_command_input()
        # update pulse analysis status
        self.data_holder.device_widgets[device_id].pulse_quality.update_pa_status(False)
    
    # set device error status in dictionary
    def set_device_error(self, device_id, error):
        self.data_holder.device_errors[device_id] = error
    
    # updates tab error icons according to data_holder.device_errors dictionary
    # TODO add comparison list of previous values to avoid unnecessary icon updates
    def update_error_icons(self):
        # go through each device
        for dev in self.params.child('Device settings').children():
            try:
                # device id
                device_id = dev.child('DevID').value()
                # error status from data_holder.device_errors
                error = self.data_holder.device_errors[device_id]
                # device type
                device_type = dev.child('Device type').value()
                # device widget
                device_widget = self.data_holder.device_widgets[device_id]
                # device widget tab index
                tab_index = self.device_tabs.indexOf(device_widget)
                # connected status
                connected = dev.child('Connected').value() # True or False

                # if connected is False
                if not connected and device_type != EXAMPLE_DEVICE: # exclude Example device
                    # set disconnected icon
                    self.device_tabs.setTabIcon(tab_index, self.disconnected_icon)
                    # set general error status flag
                    self.data_holder.error_status = 1

                # if error is True
                elif error:
                    # change tab icon to error icon
                    self.device_tabs.setTabIcon(tab_index, self.error_icon)
                    # change status tab icon to error icon if device is CPC or PSM
                    if device_type in [CPC, PSM, PSM2]:
                        status_tab_index = device_widget.indexOf(device_widget.status_tab)
                        device_widget.setTabIcon(status_tab_index, self.error_icon)

                # if connected and no error
                else:
                    # remove error icon with empty QIcon object
                    self.device_tabs.setTabIcon(tab_index, QIcon())
                    # remove status tab error icon if device is CPC or PSM
                    if device_type in [CPC, PSM, PSM2]:
                        status_tab_index = device_widget.indexOf(device_widget.status_tab)
                        device_widget.setTabIcon(status_tab_index, QIcon())
                
                # if device is PSM, check co flow status
                if device_type == PSM:
                    # if co flow is red (error)
                    if device_widget.set_tab.set_co_flow.error == True:
                        # change tab icon to error icon
                        self.device_tabs.setTabIcon(tab_index, self.error_icon)
                        # change set tab icon to error icon
                        set_tab_index = device_widget.indexOf(device_widget.set_tab)
                        device_widget.setTabIcon(set_tab_index, self.error_icon)
                    else:
                        # remove error icon with empty QIcon object
                        set_tab_index = device_widget.indexOf(device_widget.set_tab)
                        device_widget.setTabIcon(set_tab_index, QIcon())

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)
    
    # rename device parameter according to device type and serial number
    def rename_device(self, device):
        # combine device type name and serial number into device name
        device_type = device.child('Device type').value() # device type number
        device_type_name = self.data_holder.device_names[device_type] # device type name
        serial_number = device.child('Serial number').value() # serial number
        device_name = device_type_name + " " + serial_number
        # set device name
        device.setName(device_name)
        # update tab name
        self.rename_tab(device)

    # update device tab name according to device parameter name or nickname
    def rename_tab(self, device):
        # get tab index of device widget
        device_id = device.child('DevID').value()
        device_widget = self.data_holder.device_widgets[device_id]
        tab_index = self.device_tabs.indexOf(device_widget)
        # check if device has a nickname
        if device.child('Device nickname').value() != "":
            device_name = device.child('Device nickname').value()
        else: # if no nickname, use device parameter name (device type and serial number)
            device_name = device.name()
        # update tab name
        self.device_tabs.setTabText(tab_index, device_name)

    # triggered when a new device is added to the parameter tree
    # sigChildAdded(self, param, child, index) - Emitted when a child (device) is added
    def device_added(self, param, child, index):
        if param.name() == "Device settings": # check if detected parameter is a device
            device_param = child # store device parameter
            device_type = child.child("Device type").value() # store device type
            device_id = child.child("DevID").value() # store device ID
            device_port = child.child("COM port") # store COM port parameter
            connection = device_param.child('Connection').value() # store connection class

            # connect serial number change to reset_device_filenames function
            device_param.child("Serial number").sigValueChanged.connect(lambda: self.reset_device_filenames(device_id))
            # connect device nickname change to reset_device_filenames function
            device_param.child("Device nickname").sigValueChanged.connect(lambda: self.reset_device_filenames(device_id))
            # connect device nickname change to rename_tab function
            device_param.child("Device nickname").sigValueChanged.connect(lambda: self.rename_tab(device_param))
            # connect device serial number change to rename_device function
            device_param.child("Serial number").sigValueChanged.connect(lambda: self.rename_device(device_param))
            # connect device serial number change to reset_device_filenames function
            device_param.child("Serial number").sigValueChanged.connect(lambda: self.reset_device_filenames(device_id))
            # connect COM port change to SerialDeviceConnection's change_port function
            if osx_mode:
                device_port.sigValueChanged.connect(lambda: connection.change_port(str(device_port.value())))
            else:
                device_port.sigValueChanged.connect(lambda: connection.change_port('COM'+str(device_port.value())))

            # create new widget according to device type
            if device_type == CPC: # if CPC
                # create CPC widget instance
                widget = CPCWidget(device_param)
                # connect Set tab buttons to send_set function
                widget.set_tab.drain.clicked.connect(lambda: connection.send_set(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
                widget.set_tab.autofill.clicked.connect(lambda: connection.send_set(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
                widget.set_tab.water_removal.clicked.connect(lambda: connection.send_set(":SET:WREM " + str(int(widget.set_tab.water_removal.isChecked()))))
                # connect command_input to comand_entered function
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: command_entered(device_id, device_param, self.data_holder.device_widgets))
                # connect Set tab set points to send_set_val function
                # send set value and message using lambda once value has been changed
                # stepChanged signal is defined in SpinBox and DoubleSpinBox classes
                # https://stackoverflow.com/questions/47874952/qspinbox-signal-for-arrow-buttons
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_saturator_temp.value_input.text()), ":SET:TEMP:SAT "))
                widget.set_tab.set_condenser_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:CON "))
                widget.set_tab.set_condenser_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_condenser_temp.value_input.text()), ":SET:TEMP:CON "))
                # averaging time: use integer formatting with times > 1 to preserve compatibility with older firmware
                def send_averaging_time(value: float):
                    output: float | int = value
                    if value >= 1.0:
                        output = round(value)
                    connection.send_set_val(output, ":SET:TAVG ")
                widget.set_tab.set_averaging_time.value_spinbox.stepChanged.connect(lambda value: send_averaging_time(value))
                widget.set_tab.set_averaging_time.value_input.returnPressed.connect(lambda: send_averaging_time(float(widget.set_tab.set_averaging_time.value_input.text())))
                # connect Pulse quality tab options to pulse_quality_update function
                widget.pulse_quality.history_time_select.currentIndexChanged.connect(lambda: self.plot_manager.pulse_quality_update(device_id))
                widget.pulse_quality.average_time_select.currentIndexChanged.connect(lambda: self.plot_manager.pulse_quality_update(device_id))
                # connect pulse analysis start button to pulse_analysis_start function
                widget.pulse_quality.start_analysis.clicked.connect(lambda: self.pulse_analysis_start(device_id, device_param))
                # connect device nickname change to ScalableGroup's update_cpc_dict function
                device_param.child("Device nickname").sigValueChanged.connect(param.update_cpc_dict)

            if device_type in [PSM, PSM2]: # if PSM TODO optimize structure, remove repetition
                # create PSM widget instance
                widget = PSMWidget(device_param, device_type)
                # connect Measure tab buttons to send_set function
                widget.measure_tab.scan.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_scan()))
                widget.measure_tab.step.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_step()))
                widget.measure_tab.fixed.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_fixed()))
                # connect ten_hz button to ten_hz_clicked function
                widget.measure_tab.ten_hz.clicked.connect(lambda: ten_hz_clicked(device_param, widget))
                # connect SetTab SetWidgets to send_set_val function and set settings update flag to True
                # growth tube temperature set
                widget.set_tab.set_growth_tube_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:GT "))
                widget.set_tab.set_growth_tube_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                widget.set_tab.set_growth_tube_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_growth_tube_temp.value_input.text()), ":SET:TEMP:GT "))
                widget.set_tab.set_growth_tube_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                # saturator temperature set
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_saturator_temp.value_input.text()), ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                # inlet temperature set
                widget.set_tab.set_inlet_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:INL "))
                widget.set_tab.set_inlet_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                widget.set_tab.set_inlet_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_inlet_temp.value_input.text()), ":SET:TEMP:INL "))
                widget.set_tab.set_inlet_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                # heater temperature set
                widget.set_tab.set_heater_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:PRE "))
                widget.set_tab.set_heater_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                widget.set_tab.set_heater_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_heater_temp.value_input.text()), ":SET:TEMP:PRE "))
                widget.set_tab.set_heater_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                # drainage temperature set
                widget.set_tab.set_drainage_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:DRN "))
                widget.set_tab.set_drainage_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                widget.set_tab.set_drainage_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_drainage_temp.value_input.text()), ":SET:TEMP:DRN "))
                widget.set_tab.set_drainage_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                # cpc inlet flow set (send value to PSM)
                #widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:FLOW:CPC "))
                widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda value: psm_flow_send(device_param, value))
                widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                #widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_cpc_inlet_flow.value_input.text()), ":SET:FLOW:CPC "))
                widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: psm_flow_send(device_param, float(widget.set_tab.set_cpc_inlet_flow.value_input.text())))
                widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                # cpc sample flow set (send value to connected CPC if it exists)
                # TODO is psm_update required when setting cpc sample flow?
                widget.set_tab.set_cpc_sample_flow.value_spinbox.stepChanged.connect(lambda value: cpc_flow_send(device_param, value))
                widget.set_tab.set_cpc_sample_flow.value_input.returnPressed.connect(lambda: cpc_flow_send(device_param, float(widget.set_tab.set_cpc_sample_flow.value_input.text())))
                # if device type is PSM, connect co flow set
                if device_type == PSM:
                    widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                    widget.set_tab.set_co_flow.value_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                    # set value to hidden 'CO flow' parameter in parameter tree
                    widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(lambda value: device_param.child('CO flow').setValue(str(round(value, 3))))
                    widget.set_tab.set_co_flow.value_input.returnPressed.connect(lambda: device_param.child('CO flow').setValue(widget.set_tab.set_co_flow.value_input.text()))
                # connect command_input to command_entered and psm_update functions
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: command_entered(device_id, device_param, self.data_holder.device_widgets))
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: psm_update(device_id, self.data_holder.psm_settings_updates))
                # connect liquid operations
                widget.set_tab.autofill.clicked.connect(lambda: connection.send_set(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
                #widget.set_tab.autofill.clicked.connect(lambda: self.psm_update(device_id, self.data_holder.psm_settings_updates))
                widget.set_tab.drain.clicked.connect(lambda: connection.send_set(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
                #widget.set_tab.drain.clicked.connect(lambda: self.psm_update(device_id, self.data_holder.psm_settings_updates))
                widget.set_tab.drying.clicked.connect(lambda: connection.send_set(widget.set_tab.drying.messages[int(widget.set_tab.drying.isChecked())]))
                #widget.set_tab.drying.clicked.connect(lambda: self.psm_update(device_id, self.data_holder.psm_settings_updates))

            if device_type == ELECTROMETER: # if ELECTROMETER
                widget = ElectrometerWidget(device_param) # create ELECTROMETER widget instance

            if device_type == CO2_SENSOR: # if CO2
                widget = CO2Widget(device_param) # create CO2 widget instance
            
            if device_type == RHTP: # if RHTP
                widget = RHTPWidget(device_param) # create RHTP widget instance
                # check if there are other RHTP devices and if so, set 'Plot to main' according to them
                for dev in self.params.child('Device settings').children():
                    if dev.child('Device type').value() == RHTP and dev.child('DevID').value() != device_id:
                        # call rhtp_axis_changed() to change 'Plot to main' selection of new device
                        # delay ensures change is made to updated "Plot to main" RHTP menu
                        QTimer.singleShot(50, lambda: self.rhtp_axis_changed(dev.child('Plot to main').value()))
                        break # break loop after first RHTP device is found
                # connect device parameter's 'Plot to main' value change to rhtp_axis_changed()
                # delay ensures connection is made from updated "Plot to main" RHTP menu
                QTimer.singleShot(60, lambda: device_param.child("Plot to main").sigValueChanged.connect(lambda parameter: self.rhtp_axis_changed(parameter.value())))
            
            if device_type == AFM: # if AFM
                widget = AFMWidget(device_param) # create AFM widget instance
                # check if there are other AFM devices and if so, set 'Plot to main' according to them
                for dev in self.params.child('Device settings').children():
                    if dev.child('Device type').value() == AFM and dev.child('DevID').value() != device_id:
                        # call afm_axis_changed() to change 'Plot to main' selection of new device
                        # delay ensures change is made to updated "Plot to main" AFM menu
                        QTimer.singleShot(50, lambda: self.afm_axis_changed(dev.child('Plot to main').value()))
                        break
                # connect device parameter's 'Plot to main' value change to afm_axis_changed()
                # delay ensures connection is made from updated "Plot to main" AFM menu
                QTimer.singleShot(60, lambda: device_param.child("Plot to main").sigValueChanged.connect(lambda parameter: self.afm_axis_changed(parameter.value())))
            
            if device_type == EDILUTER: # if eDiluter
                widget = eDiluterWidget(device_param) # create eDiluter widget instance
                # connect set_tab's mode buttons to send_set function
                widget.set_tab.init.clicked.connect(lambda: connection.send_set("do set app.measurement.state INIT"))
                widget.set_tab.warmup.clicked.connect(lambda: connection.send_set("do set app.measurement.state WARMUP"))
                widget.set_tab.standby.clicked.connect(lambda: connection.send_set("do set app.measurement.state STANDBY"))
                widget.set_tab.measurement.clicked.connect(lambda: connection.send_set("do set app.measurement.state MEASUREMENT"))
                # connect dilution factor 1 buttons to send_set function
                widget.set_tab.df_1.prev_button.clicked.connect(lambda: connection.send_set("do set dilution.1st.prev true"))
                widget.set_tab.df_1.next_button.clicked.connect(lambda: connection.send_set("do set dilution.1st.next true"))
                # connect dilution factor 2 buttons to send_set function
                widget.set_tab.df_2.prev_button.clicked.connect(lambda: connection.send_set("do set dilution.2nd.prev true"))
                widget.set_tab.df_2.next_button.clicked.connect(lambda: connection.send_set("do set dilution.2nd.next true"))
                # connect command_input to command_entered function
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: self.command_entered(device_id, device_param, self.data_holder.device_widgets, self.data_holder.latest_command))
            
            if device_type == TSI_CPC: # if TSI CPC
                # create TSI widget instance
                widget = TSIWidget(device_param)
                # add baud rate parameter
                device_param.addChild({'name': 'Baud rate', 'type': 'int', 'value': 115200})
                # connect baud rate parameter to connection's set_baud_rate function
                device_param.child('Baud rate').sigValueChanged.connect(lambda: connection.set_baud_rate(device_param.child('Baud rate').value()))
                # connect device nickname change to ScalableGroup's update_cpc_dict function
                device_param.child("Device nickname").sigValueChanged.connect(param.update_cpc_dict)
            
            if device_type == EXAMPLE_DEVICE: # if Example device
                widget = ExampleDeviceWidget(device_param) # create Example device widget instance
            
            # connect x range change of plot_tab's viewbox(es) to x_range_changed function (autoscale y)
            if device_type == ELECTROMETER:
                for plot in widget.plot_tab.plots:
                    plot.getViewBox().sigXRangeChanged.connect(self.x_range_changed)
            elif device_type in [RHTP, AFM]:
                for viewbox in widget.plot_tab.viewboxes:
                    viewbox.sigXRangeChanged.connect(self.x_range_changed)
            else:
                widget.plot_tab.viewbox.sigXRangeChanged.connect(self.x_range_changed)

            # add widget instance to data_holder.device_widgets dictionary with device ID as key
            self.data_holder.device_widgets[device_id] = widget
            # init data for this device with nan values
            self.data_holder.reset_for_device(device_id, device_type)
            # add widget instance to tab widget
            self.device_tabs.addTab(widget, widget.name)
            # add device id to data_holder.device_errors dictionary
            self.data_holder.device_errors[device_id] = False
    
    # triggered when a device is removed from the parameter tree
    # sigChildRemoved(self, parent, child, index) - Emitted when a child (device) is removed
    def device_removed(self, param, child):
        if param == self.params.child("Device settings"):
            device_id = child.child("DevID").value()
            device_type = child.child("Device type").value()
            # remove device widget from main tab widget
            self.device_tabs.removeTab(self.device_tabs.indexOf(self.data_holder.device_widgets[device_id]))
            # close serial connection if open
            try:
                child.child('Connection').value().close()
            except AttributeError:
                pass
            # set empty data to data_holder.curve_dict (remove curve from Main plot)
            try:
                self.data_holder.curve_dict[device_id].setData(x=[], y=[])
            except KeyError:
                pass

            self.data_holder.clear_for_device(device_id)


# application format
if __name__ == '__main__': # protects from accidentally invoking the script when not intended
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
