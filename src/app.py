from datetime import datetime as dt
from time import time, sleep
import os
import locale
import platform
import logging
import random
import traceback
import json
import warnings
import sys

from numpy import full, nan, array, polyval, array_equal, roll, nanmean, isnan, linspace
from serial import Serial
from serial.tools import list_ports
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

from serial_connection import SerialDeviceConnection
from params import ScalableGroup, params, p


# main program
class MainWindow(QMainWindow):

    def __init__(self, params=p, parent=None):
        super().__init__() # super init function must be called when subclassing a Qt class
        self.setWindowTitle("Airmodus MultiLogger v. " + version_number) # set window title
        self.timer = QTimer(timerType=Qt.PreciseTimer) # create timer object
        self.params = params # predefined parameter tree
        self.config_file_path = "" # path to the configuration file

        # Extracted inits
        self._init_data_structs()
        self._setup_parameter_tree()
        self._setup_gui()
        self._connect_signals()

        self.list_com_ports()
        self.startTimer()
        # load ini file if available
        self.load_ini()


    def _init_data_structs(self):
        """Initialize all dicts/lists (data, plots, devices, etc.)."""
        # data related
        self.latest_data = {} # contains latest values
        self.latest_settings = {} # contains latest CPC and PSM settings
        self.latest_psm_prnt = {} # contains latest PSM prnt values
        self.latest_poly_correction = {} # contains latest polynomial correction values from PSM
        self.latest_command = {} # contains latest user entered command message
        self.latest_ten_hz = {} # contains latest 10 hz OPC concentration log values
        self.extra_data = {} # contains extra data, used when multiple data prints are received at once
        self.extra_data_counter = {} # contains extra data counter, used to determine when extra data buffer is safe to clear
        self.partial_data = {} # contains partial data, used when incomplete messages are received
        self.pulse_analysis_index = {} # contains CPC pulse analysis index, used for pulse analysis progress tracking
        self.psm_dilution = {} # contains PSM dilution parameters
        # plot related
        self.plot_data = {} # contains plotted values
        self.curve_dict = {} # contains curve objects for main plot
        self.start_times = {} # contains start times of measurements
        # device related
        self.current_ports = [] # contains current available ports as serial objects
        self.com_descriptions = {} # contains com port descriptions
        self.device_widgets = {} # contains device widgets, appended in device_added function
        # filenames
        self.dat_filenames = {} # contains filenames of .dat files
        self.par_filenames = {} # contains filenames of .par files (CPC and PSM)
        self.ten_hz_filenames = {} # contains filenames of 10 hz OPC concentration log files (CPC)
        self.pulse_analysis_filenames = {} # contains filenames of pulse analysis files (CPC)
        # flags
        self.par_updates = {} # contains .par update flags: 1 = update, 0 = no update
        self.psm_settings_updates = {} # contains PSM settings update flags: 1 = update, 0 = no update
        self.device_errors = {} # contains device error flags: 0 = ok, 1 = errors
        self.idn_inquiry_devices = [] # contains IDs of devices that need IDN inquiry
        # dictionary of device names matching device type
        self.device_names = {CPC: 'CPC', PSM: 'PSM Retrofit', ELECTROMETER: 'Electrometer', CO2_SENSOR: 'CO2 sensor', RHTP: 'RHTP', AFM: 'AFM', EDILUTER: 'eDiluter', PSM2: 'PSM 2.0', TSI_CPC: 'TSI CPC', EXAMPLE_DEVICE: 'Example device'}

    def _setup_parameter_tree(self):
        """Create and configure the ParameterTree."""
        # create parameter tree
        self.t = ParameterTree()
        self.t.setParameters(p, showTop=False)
        self.t.setHeaderHidden(True)
        # x axis time attributes
        self.time_counter = 0 # used as index value, incremented every second
        self.x_time_list = full(10, nan) # 60 # list for saving x-axis time values
        self.max_reached = False # flag for checking if MAX_TIME_SEC has been reached
        self.first_connection = 0 # once first connection has been made, set to 1
        self.inquiry_flag = False # when COM ports change, this is set to True to inquire device IDNs

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

        # connect signals to functions
        # connect timer timeout to timer_functions
        self.timer.timeout.connect(self.timer_functions)
        # connect parameter tree's save data parameter
        self.params.child('Data settings').child('Save data').sigValueChanged.connect(self.save_changed)
        # connect file path parameter to filepath_changed function
        self.params.child('Data settings').child('File path').sigValueChanged.connect(self.filepath_changed)
        # connect file tag parameter to reset_filenames function
        self.params.child('Data settings').child('File tag').sigValueChanged.connect(self.reset_filenames)
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

    # timer timeout launches this chain of functions
    def timer_functions(self):
        # TODO rename functions to something more descriptive, explain phases with comments
        self.current_time = int(time()) # get current time as integer
        # initialize error status light flag
        self.error_status = 0 # 0 = ok, 1 = errors
        # initialize saving status flag, set to 0 in write_data function if saving not on or fails
        self.saving_status = 1 # 0 = not saving, 1 = saving
        # set all device errors to False, individually set to True when errors encountered
        self.device_errors = {key: False for key in self.device_errors}
        self.connection_test() # check if devices are connected
        if self.first_connection: # if first connection has been made
            self.get_dev_data() # send read commands to connected serial devices
            # launch delayed_functions after specified ms
            QTimer.singleShot(TIMER_DELAY_MS, self.delayed_functions) # changed from 500 to 600

    # delayed functions are launched after a short delay
    def delayed_functions(self):
        self.readIndata() # read and compile data from connected serial devices
        self.ten_hz_check() # check and update 10 hz settings
        self.update_plot_data() # update plot data lists with latest data
        self.update_figures_and_menus() # update figures and menus
        self.compare_day() # check if day has changed and create new files if necessary
        self.write_data() # write data to files
        self.update_error_icons() # set error icons according to device_errors dict
        self.status_lights.set_error_light(self.error_status) # update error status light according to error_status flag
        self.status_lights.set_saving_light(self.saving_status) # update saving status light according to saving_status flag
        if self.time_counter < MAX_TIME_SEC - 1: # if time counter has not reached MAX_TIME_SEC - 1
            self.time_counter += 1 # increment time counter
        else: # if time counter has reached MAX_TIME_SEC - 1 (max index)
            self.max_reached = True # set max_reached flag to True
        # convert current_time to datetime object
        current_datetime = dt.fromtimestamp(self.current_time)
        # restart timer every 12 hours (at 11:59:59 and 23:59:59) to prevent drifting over time
        if current_datetime.hour in [11, 23] and current_datetime.minute == 59 and current_datetime.second == 59:
            self.restartTimer()

    # Check if serial connection is established
    def connection_test(self):
        # list COM ports
        com_port_list = self.list_com_ports()
        # go through each of the devices set in the parameter tree
        for dev in self.params.child('Device settings').children():

            # if device type is Example device, set first connection to True
            if dev.child('Device type').value() == -1:
                if self.first_connection == 0:
                    self.first_connection = True

            # get current connected (Connected value) from parameter tree
            connected = dev.child('Connected').value() # "Connected" parameter
            # get current port from parameter tree
            if osx_mode:
                port = str(dev.child('COM port').value())
            else:
                port = "COM"+str(dev.child('COM port').value()) # "COM port" parameter
            # check if port is listed in the available ports
            if connected and port not in com_port_list: # if connected but port address does not exists (physically disconnected)
                try: # try to close the port
                    dev.child('Connection').value().close() # "Connection" parameter
                except Exception as e:
                    print(traceback.format_exc())

            connected = False # set value to not connected
            try: # try to check if the port is open
                # If a connection exists and port is open
                if dev.child('Connection').value().connection.is_open == True: # "Connection" parameter
                    connected = True # is connected
                else: # if port is closed, try to connect
                    dev.child('Connection').value().connect()
                    if dev.child('Connection').value().connection.is_open == True:
                        connected = True # is connected

            except AttributeError: # if device has no connection attribute
                try: # try to connect
                    dev.child('Connection').value().set_port(port)
                    dev.child('Connection').value().connect()
                    # check if connection is open
                    if dev.child('Connection').value().connection.is_open == True:
                        connected = True # is connected
                except Exception as e:
                    #print("connection_test - error:", e)
                    pass
            
            except Exception as e:
                #print("connection_test - error:", e)
                pass
            
            # add device to IDN inquiry list whenever connection is made ('Connected' changes from False to True)
            # this ensures serial number is up to date if device changes
            if dev.child('Device type').value() in [CPC, PSM, PSM2, CO2_SENSOR, RHTP, AFM]:
                if connected and dev.child('Connected').value() == False:
                    if dev.child('DevID').value() not in self.idn_inquiry_devices:
                        self.idn_inquiry_devices.append(dev.child('DevID').value())
                    # if device is PSM, reset firmware version and dilution parameters to ensure they are updated
                    if dev.child('Device type').value() in [PSM, PSM2]:
                        dev.child('Firmware version').setValue("") # reset firmware version
                        if dev.child('DevID').value() in self.psm_dilution:
                            del self.psm_dilution[dev.child('DevID').value()] # reset dilution parameters
                        # set settings update flag
                        self.psm_settings_updates[dev.child('DevID').value()] = True
                    if dev.child('Device type').value() in [CPC, PSM, PSM2, EDILUTER]:
                        # set text to normal using CSS ID
                        self.device_widgets[dev.child('DevID').value()].setObjectName("connected")
                        self.device_widgets[dev.child('DevID').value()].setStyleSheet("")

            # print disconnected message when device is disconnected
            if dev.child('Device type').value() in [CPC, PSM, PSM2, EDILUTER]:
                if connected == False and dev.child('Connected').value() == True:
                    self.device_widgets[dev.child('DevID').value()].set_tab.command_widget.update_text_box("Device disconnected.")
                    # set text to grey using CSS ID
                    self.device_widgets[dev.child('DevID').value()].setObjectName("disconnected")
                    self.device_widgets[dev.child('DevID').value()].setStyleSheet("")
            
            # set the connection state according to connected value
            dev.child('Connected').setValue(connected)
            if self.first_connection == 0:
                self.first_connection = connected
    
    # send read commands to connected serial devices
    def get_dev_data(self):
        # Loop through devices
        for dev in self.params.child('Device settings').children():
            # if device is connected
            if dev.child('Connected').value():
                device_type = dev.child('Device type').value() # get device type

                try: # try to send message(s) to device

                    if device_type in [CPC, TSI_CPC]: # CPC
                        # send multiple messages to device according to type
                        if device_type == CPC and dev.child('DevID').value() in self.pulse_analysis_index:
                            # if pulse analysis is in progress, send pulse analysis messages
                            if self.pulse_analysis_index[dev.child('DevID').value()] is not None: # when index is None, analysis has reached its end
                                threshold = PULSE_ANALYSIS_THRESHOLDS[self.pulse_analysis_index[dev.child('DevID').value()]]
                                dev.child('Connection').value().send_pulse_analysis_messages(threshold)
                        elif device_type == CPC and dev.child('10 hz').value() == True:
                            dev.child('Connection').value().send_multiple_messages(device_type, ten_hz=True)
                        else:
                            dev.child('Connection').value().send_multiple_messages(device_type)

                    elif device_type in [PSM, PSM2]: # PSM
                        # if settings update flag is True, fetch set points from PSM and update GUI
                        if self.psm_settings_updates[dev.child('DevID').value()] == True:
                            # send message to device to get settings
                            dev.child('Connection').value().send_message(":SYST:PRNT")
                        # if dilution parameters have not been fetched, send message
                        if dev.child('DevID').value() not in self.psm_dilution:
                            dev.child('Connection').value().send_delayed_message(":SYST:VCMP", 150)

                    elif device_type == ELECTROMETER: # ELECTROMETER
                        dev.child('Connection').value().connection.reset_input_buffer()
                        dev.child('Connection').value().connection.reset_output_buffer()
                        dev.child('Connection').value().connection.read_all()
                        dev.child('Connection').value().send_message(":MEAS:V")

                    elif device_type == CO2_SENSOR: # CO2 sensor
                        dev.child('Connection').value().connection.reset_input_buffer()
                        dev.child('Connection').value().connection.reset_output_buffer()
                        dev.child('Connection').value().connection.read_all()
                        # send measure command to device
                        dev.child('Connection').value().send_message(":MEAS:CO2")
                    
                    # RHTP, eDiluter and AFM push data automatically

                    if device_type in [CPC, PSM, PSM2, CO2_SENSOR, RHTP, AFM]: # CPC, PSM, CO2, RHTP, AFM
                        # if device is in IDN inquiry list, send IDN inquiry with delay
                        if dev.child('DevID').value() in self.idn_inquiry_devices:
                            self.idn_inquiry(dev.child('Connection').value().connection)
                        # if Serial number has been acquired, check if Firmware version is empty
                        elif device_type in [PSM, PSM2]:
                            # if Firmware version is empty, send firmware version inquiry with delay
                            if dev.child('Firmware version').value() == "":
                                self.firmware_inquiry(dev.child('Connection').value().connection)
                        
                except Exception as e:
                    print(traceback.format_exc())
                    logging.exception(e)

    # independent functions for delayed sends prevent serial connections getting mixed up in iteration
    # send IDN inquiry with delay
    def idn_inquiry(self, connection):
        QTimer.singleShot(IDN_INQUIRY_DELAY_MS, lambda: connection.write(b'*IDN?\n'))
    # send firmware inquiry with delay
    def firmware_inquiry(self, connection):
        QTimer.singleShot(FIRMWARE_INQUIRY_DELAY_MS, lambda: connection.write(b':SYST:VER\n'))
    
    # read and compile data
    def readIndata(self):
        for dev in self.params.child('Device settings').children():
            # if device is connected
            if dev.child('Connected').value():
                # store device ID for convenience
                dev_id = dev.child('DevID').value()

                if dev.child('Device type').value() == CPC: # CPC

                    # check if there's data from last round in extra_data dictionary
                    # if no extra data, start with nan lists
                    if dev_id in self.extra_data:
                        self.latest_data[dev_id] = self.extra_data.pop(dev_id)
                    else:
                        self.latest_data[dev_id] = full(15, nan)
                    if str(dev_id)+":prnt" in self.extra_data:
                        prnt_list = self.extra_data.pop(str(dev_id)+":prnt")
                    else:
                        prnt_list = full(13, nan)
                    if str(dev_id)+":pall" in self.extra_data:
                        pall_list = self.extra_data.pop(str(dev_id)+":pall")
                    else:
                        pall_list = full(28, nan)
                    # if 10 hz is True, initialize 10 hz data with extra data or nan list
                    if dev.child('10 hz').value() == True:
                        if str(dev_id)+":10hz" in self.extra_data:
                            self.latest_ten_hz[dev_id] = self.extra_data.pop(str(dev_id)+":10hz")
                        else:
                            self.latest_ten_hz[dev_id] = full(10, nan)

                    try:
                        readings = dev.child('Connection').value().connection.read_all()
                        readings = readings.decode().split("\r")[:-1] # decode, separate messages and remove last empty message
                        for message in readings: # loop through messages
                            message_string = message # store message as string
                            message = message.split(" ", 1) # separate command name and data readings
                            command = message[0] # get command name
                            data = message[1] # get data readings
                            data = data.split(",") # split data readings to list

                            if command == ":MEAS:ALL":
                                status_hex = data[-1] # store status hex value

                                # check if cabin pressure value is within valid range (0-200 kPa)
                                if float(data[12]) < 0 or float(data[12]) > 200:
                                    cabin_p_error = True
                                else:
                                    cabin_p_error = False
                                # update widget error colors and store total errors
                                total_errors = self.device_widgets[dev_id].update_errors(status_hex, cabin_p_error)
                                
                                # set error_status flag if total errors is not 0
                                if total_errors != 0:
                                    self.error_status = 1
                                    # set device error flag
                                    self.set_device_error(dev_id, True)

                                meas_list = list(map(float,data[:-1])) # convert to float without status hex
                                # compile data list
                                # if latest_data is nan, store data normally
                                if isnan(self.latest_data[dev_id][0]):
                                    self.latest_data[dev_id] = compile_cpc_data(meas_list, status_hex, total_errors)
                                else: # if not nan, store data to extra_data dictionary
                                    self.extra_data[dev_id] = compile_cpc_data(meas_list, status_hex, total_errors)

                            elif command == ":SYST:PRNT":
                                # if prnt_list is nan, store data normally
                                if isnan(prnt_list[0]):
                                    prnt_list = list(map(float,data)) # convert to float
                                else: # if not nan, store data to extra_data dictionary
                                    self.extra_data[str(dev_id)+":prnt"] = list(map(float,data))

                            elif command == ":SYST:PALL":
                                data[22] = "NaN" # set device id and firmware variant letter to NaN before float conversion
                                data[23] = "NaN" # TODO store device id and firmware variant letter somewhere
                                # if pall_list is nan, store data normally
                                if isnan(pall_list[0]): # TODO make sure this value (inlet press lower limit) is never nan in valid data
                                    pall_list = list(map(float,data))
                                else: # if not nan, store data to extra_data dictionary
                                    self.extra_data[str(dev_id)+":pall"] = list(map(float,data))
                            
                            elif command == ":MEAS:OPC_CONC_LOG":
                                del data[0] # remove first item (timestamp)
                                # if latest_ten_hz is nan, store data normally
                                if isnan(float(self.latest_ten_hz[dev_id][0])):
                                    self.latest_ten_hz[dev_id] = data
                                else: # if not nan, store data to extra_data dictionary
                                    self.extra_data[str(dev_id)+":10hz"] = data
                            
                            elif command == ":STAT:SELF:LOG":
                                error_length = len(CPC_ERRORS) # get amount of CPC errors
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                status_bin = bin(int(data[0], 16)) # convert hex to int and int to binary
                                status_bin = status_bin[2:].zfill(error_length) # remove 0b from string and fill with 0s
                                # print self test error binary
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error binary: " + status_bin)
                                inverted_status_bin = status_bin[::-1] # invert status_bin for error parsing
                                # print error indices
                                for i in range(error_length): # loop through errors
                                    if inverted_status_bin[i] == "1":
                                        self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error bit index: " + str(i))
                                        self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error: " + CPC_ERRORS[i])

                            elif command == ":SELF:ERR":
                                try:
                                    self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                    error_code = int(data[0])
                                    print("self test error: " + CPC_ERRORS[error_code])
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                            
                            elif command == "*IDN":
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                serial_number = data[0]
                                serial_number = serial_number.strip("\n")
                                serial_number = serial_number.strip("\r")
                                # check if serial number has changed
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)
                                    # update PSM 'Connected CPC' list
                                    self.params.child('Device settings').update_cpc_dict()
                                # remove device from IDN inquiry list
                                if dev_id in self.idn_inquiry_devices:
                                    self.idn_inquiry_devices.remove(dev_id)

                            else: # print these to command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                #logging.warning("readIndata - unknown command: %s", command)

                    except Exception as e: # if reading fails, print error message
                        print(traceback.format_exc())
                        logging.exception(e)
                    
                    # update CPC widget data values
                    self.device_widgets[dev_id].update_values(self.latest_data[dev_id])
                    # update CPC widget set values
                    self.device_widgets[dev_id].update_settings(prnt_list)

                    # set settings update flag if both lists are successfully read
                    if str(prnt_list[0]) != "nan" and str(pall_list[0]) != "nan": # if both lists are not nan (checks first item only)
                        settings_update = True
                    else:
                        settings_update = False
                    
                    # if pulse analysis is in progress, skip settings update
                    # this keeps the original threshold value intact in latest_settings dictionary
                    if dev_id in self.pulse_analysis_index:
                        settings_update = False
                    
                    # update settings if settings are valid
                    if settings_update == True: # if settings are valid, not nan
                        
                        # if device doesn't yet exist in latest_settings dictionary, add as nan list
                        if dev_id not in self.latest_settings:
                            self.latest_settings[dev_id] = full(13, nan)
                        
                        # get previous settings form latest_settings dictionary
                        previous_settings = self.latest_settings[dev_id]
                        # compile settings list
                        settings = compile_cpc_settings(prnt_list, pall_list)

                        if not array_equal(settings, previous_settings, equal_nan=True): # if values have changed
                            # update latest settings
                            self.latest_settings[dev_id] = settings
                            # set .par update flag
                            self.par_updates[dev_id] = 1
                        else:
                            # clear .par update flag
                            self.par_updates[dev_id] = 0
                    
                    else: # if settings are not valid, clear .par update flag
                        self.par_updates[dev_id] = 0
                
                if dev.child('Device type').value() in [PSM, PSM2]: # PSM

                    # clear extra data buffer after 60 seconds of consecutive buffering
                    # this ensures data is real time and not delayed by 1 second
                    if dev_id in self.extra_data and self.extra_data_counter[dev_id] >= 60:
                        del self.extra_data[dev_id]
                        logging.info("PSM %s extra data buffer cleared", dev.child('Serial number').value())
                    
                    # check if there is extra data from last round
                    if dev_id in self.extra_data:
                        # if there is extra data, store it to latest_data dictionary
                        self.latest_data[dev_id] = self.extra_data.pop(dev_id)
                        # increment extra data counter
                        self.extra_data_counter[dev_id] += 1
                    else:
                        # if no extra data, initialize latest_data with nan list
                        # convert from array to list to allow string insertion (CPC status hex)
                        if dev.child('Device type').value() == PSM:
                            self.latest_data[dev_id] = full(33, nan).tolist()
                        elif dev.child('Device type').value() == PSM2:
                            self.latest_data[dev_id] = full(34, nan).tolist()
                        # reset extra data counter
                        self.extra_data_counter[dev_id] = 0

                    # clear par update flag
                    self.par_updates[dev_id] = 0

                    # set settings_fetched flag to False
                    # flag is set to True when settings are successfully fetched
                    settings_fetched = False

                    try: # try to read data, decode and split
                        #print("inWaiting():", dev.child('Connection').value().connection.inWaiting())
                        readings = dev.child('Connection').value().connection.read_all()
                        # decode and separate messages
                        readings = readings.decode().split("\r")

                        # check if first message is expected as second half of partial message
                        if dev_id in self.partial_data:
                            # add stored partial message to the front of first message
                            readings[0] = self.partial_data[dev_id] + readings[0]
                            # remove partial message from dictionary
                            del self.partial_data[dev_id]
                            #logging.info("PSM %s combined message: %s", dev.child('Serial number').value(), readings[0])

                        # check if last message is empty or partial
                        if readings[-1] == "": # if empty, remove it from readings
                            readings = readings[:-1]
                        else: # if not empty, store partial message and remove it from readings
                            self.partial_data[dev_id] = readings[-1]
                            readings = readings[:-1]
                            #logging.info("PSM %s partial message: %s", dev.child('Serial number').value(), self.partial_data[dev_id])
                        
                        # loop through messages
                        for message in readings:
                            message_string = message # store message as string
                            message = message.split(" ", 1) # separate command name and data readings
                            command = message[0] # get command name
                            data = message[1] # get data readings
                            data = data.split(",") # split data readings to list

                            # if measurement command
                            if command == ":MEAS:SCAN" or command == ":MEAS:STEP" or command == ":MEAS:FIXD":
                                
                                # update PSM widget data values in GUI
                                self.device_widgets[dev_id].update_values(data)
                                # update active measure mode color
                                self.device_widgets[dev_id].measure_tab.change_mode_color(command)
                                # status hex handling
                                status_hex = data[-2]
                                try:
                                    # update widget errors colors
                                    total_errors = self.device_widgets[dev_id].update_errors(status_hex)
                                    # set error_status flag if total errors is not 0
                                    if total_errors != 0:
                                        self.error_status = 1
                                        # set device error flag
                                        self.set_device_error(dev_id, True)
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                # note hex handling
                                note_hex = data[-1]
                                # update widget liquid states with note hex
                                liquid_errors = self.device_widgets[dev_id].update_notes(note_hex)
                                # set error flags if liquid errors is not 0
                                if liquid_errors != 0:
                                    self.error_status = 1
                                    # set device error flag
                                    self.set_device_error(dev_id, True)
                                # store polynomial correction value as float to dictionary
                                self.latest_poly_correction[dev_id] = float(data[14])

                                scan_status = "9" # set scan status to 9 (undefined) as default
                                # check firmware number to determine if scan status is included in data
                                try:
                                    if dev.child('Firmware version').value() != "":
                                        firmware_version = dev.child('Firmware version').value().split(".")
                                        # Retrofit: version >= 0.5.5
                                        if dev.child('Device type').value() == PSM:
                                            if int(firmware_version[1]) > 5:
                                                scan_status = data[15]
                                            elif int(firmware_version[1]) == 5 and int(firmware_version[2]) >= 5:
                                                scan_status = data[15]
                                        # PSM 2.0: version >= 0.6.8
                                        elif dev.child('Device type').value() == PSM2:
                                            if int(firmware_version[1]) > 6:
                                                scan_status = data[15]
                                            elif int(firmware_version[1]) == 6 and int(firmware_version[2]) >= 8:
                                                scan_status = data[15]
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                
                                # compile psm data
                                compiled_data = compile_psm_data(data, status_hex, note_hex, scan_status, psm_version=dev.child('Device type').value())
                                # if latest_data is nan, store data normally
                                if isnan(float(self.latest_data[dev_id][2])): # check saturator flow rate value (index 2)
                                    self.latest_data[dev_id] = compiled_data
                                else: # if not nan, store data to extra_data dictionary
                                    self.extra_data[dev_id] = compiled_data
                                    #logging.info("PSM %s extra data: %s", dev.child('Serial number').value(), str(compiled_data))
                            
                            elif command == ":SYST:PRNT":
                                # update GUI set points
                                self.device_widgets[dev_id].update_settings(data)
                                # store settings to latest PSM prnt dictionary with device id as key
                                self.latest_psm_prnt[dev_id] = data
                                # print settings to command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                # set settings_fetched flag to True
                                settings_fetched = True
                            
                            elif command == ":STAT:SELF:LOG":
                                error_length = len(PSM_ERRORS) # get amount of PSM errors
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                status_bin = bin(int(data[0], 16)) # convert hex to int and int to binary
                                status_bin = status_bin[2:].zfill(error_length) # remove 0b from string and fill with 0s
                                # print self test error binary
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error binary: " + status_bin)
                                inverted_status_bin = status_bin[::-1] # invert status_bin for error parsing
                                # print error indices
                                for i in range(error_length): # loop through binary digits
                                    if inverted_status_bin[i] == "1":
                                        self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error bit index: " + str(i))
                                        # if error is MFC_HEATER / MFC_EXCESS, check device type
                                        if i == 27 and dev.child('Device type').value() == PSM: # Retrofit has different error at index 27
                                            self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error: " + "ERROR_SELFTEST_MFC_EXCESS")
                                        else:
                                            self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error: " + PSM_ERRORS[i])
                            
                            elif command == ":SELF:ERR":
                                try:
                                    self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                    error_code = int(data[0])
                                    # if error is MFC_HEATER / MFC_EXCESS, check device type
                                    if error_code == 27 and dev.child('Device type').value() == PSM:
                                        print("self test error: " + "ERROR_SELFTEST_MFC_EXCESS")
                                    else:
                                        print("self test error: " + PSM_ERRORS[int(error_code)])
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                            
                            elif command == "*IDN":
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                serial_number = data[0]
                                serial_number = serial_number.strip("\n")
                                serial_number = serial_number.strip("\r")
                                # check if serial number has changed
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)
                                # remove device from IDN inquiry list
                                if dev_id in self.idn_inquiry_devices:
                                    self.idn_inquiry_devices.remove(dev_id)
                            
                            elif command == "Firmware":
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                if "version: " in data[0]:
                                    firmware_version = data[0].split(": ")[1]
                                    if dev.child('Firmware version').value() != firmware_version:
                                        dev.child('Firmware version').setValue(firmware_version)
                            
                            elif command == ":SYST:VCMP":
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                if len(data) == 6: # make sure data is valid
                                    # store dilution parameters to dictionary
                                    self.psm_dilution[dev_id] = data
                                else:
                                    print("PSM dilution parameters invalid:", data)
                            
                            else: # print other messages to command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)

                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        # update widget error colors
                        self.device_widgets[dev_id].measure_tab.scan.change_color(0)
                        self.device_widgets[dev_id].measure_tab.step.change_color(0)
                        self.device_widgets[dev_id].measure_tab.fixed.change_color(0)
                        try:
                            # print message_string to log
                            logging.info("PSM message_string: %s", message_string)
                        except Exception:
                            print(traceback.format_exc())
                    
                    # compile settings list if update flag is True, settings_fetched is True and dilution parameters have been fetched
                    if self.psm_settings_updates[dev_id] == True and settings_fetched == True and dev_id in self.psm_dilution:
                        try:
                            psm_version = dev.child('Device type').value()
                            if psm_version == PSM:
                                # get CO flow rate from PSM widget
                                co_flow = round(self.device_widgets[dev_id].set_tab.set_co_flow.value_spinbox.value(), 3)
                            elif psm_version == PSM2:
                                # set nan as placeholder
                                co_flow = "nan"
                            dilution_parameters = self.psm_dilution[dev_id]
                            # compile settings with latest PSM prnt settings and CO flow rate
                            settings = compile_psm_settings(self.latest_psm_prnt[dev_id], co_flow, dilution_parameters, psm_version)
                            # store settings to latest settings dictionary with device id as key
                            self.latest_settings[dev_id] = settings
                            # add par update flag
                            self.par_updates[dev_id] = 1
                            # remove update settings flag once settings have been updated and compiled
                            self.psm_settings_updates[dev_id] = False
                        except Exception as e:
                            print(traceback.format_exc())
                            logging.exception(e)
                
                if dev.child('Device type').value() == ELECTROMETER: # ELECTROMETER
                    try: # try to read data, decode, split and convert to float
                        readings = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                        readings = list(map(float,readings.split(";")))
                        # store to latest_data dictionary with device id as key
                        self.latest_data[dev_id] = readings
                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.latest_data[dev_id] = full(3, nan)
                        logging.exception(e)

                if dev.child('Device type').value() == CO2_SENSOR: # CO2 sensor TODO make CO2 process similar to RHTP?
                    try:
                        # if device is in IDN inquiry list, look for *IDN
                        if dev_id in self.idn_inquiry_devices:
                            # read all data from buffer
                            messages = dev.child('Connection').value().connection.read_all().decode().split("\r\n")
                            # go through messages
                            for message in messages:
                                # if message length is above 5 ("*IDN " + device IDN)
                                if len(message) > 5:
                                    # if "*IDN " is part of message
                                    if "*IDN " in message:
                                        serial_number = message.split(" ", 1)[1] # separate serial number from message
                                        serial_number = serial_number.strip("\n")
                                        serial_number = serial_number.strip("\r")
                                        # check if serial number has changed
                                        if dev.child('Serial number').value() != serial_number:
                                            dev.child('Serial number').setValue(serial_number) # set serial number to parameter tree
                                        # remove device from IDN inquiry list
                                        if dev_id in self.idn_inquiry_devices:
                                            self.idn_inquiry_devices.remove(dev_id)
                            # store nan values to latest_data
                            self.latest_data[dev_id] = full(3, nan)

                        # if Serial number has been acquired, read data normally
                        else:
                            # read data, decode, split and convert to float
                            readings = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                            readings = list(map(float,readings.split(";")))
                            if readings[0] != 0: # if data is something else than 0
                                # store to latest_data dictionary with device id as key
                                self.latest_data[dev_id] = readings
                            else: # if data is 0, not valid
                                self.latest_data[dev_id] = full(3, nan)

                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.latest_data[dev_id] = full(3, nan)
                        logging.exception(e)
                
                if dev.child('Device type').value() == RHTP: # RHTP
                    try:
                        # start with nan list
                        self.latest_data[dev_id] = full(3, nan)

                        # if device is in IDN inquiry list, look for *IDN
                        if dev_id in self.idn_inquiry_devices:
                            # read all data from buffer
                            messages = dev.child('Connection').value().connection.read_all().decode().split("\r\n")
                            # go through messages
                            for message in messages:
                                # if message length is above 5 ("*IDN " + device IDN)
                                if len(message) > 5:
                                    # if "*IDN " is part of message
                                    if "*IDN " in message:
                                        serial_number = message.split(" ", 1)[1] # separate serial number from message
                                        serial_number = serial_number.strip("\n")
                                        serial_number = serial_number.strip("\r")
                                        # check if serial number has changed
                                        if dev.child('Serial number').value() != serial_number:
                                            dev.child('Serial number').setValue(serial_number) # set serial number to parameter tree
                                        # remove device from IDN inquiry list
                                        if dev_id in self.idn_inquiry_devices:
                                            self.idn_inquiry_devices.remove(dev_id)
                        
                        # if Serial number has been acquired, read data normally
                        else:
                            # read and decode a line of data
                            readings = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                            # remove '\r\n' from end
                            readings = readings.strip('\r\n')
                            # split data to list
                            readings = readings.split(", ")

                            # check if data is valid and store to latest_data
                            # readings length should be 3 (RH, T, P)
                            if len(readings) == 3:
                                self.latest_data[dev_id] = readings

                            # check if there's extra data in buffer
                            # max message length is 23 (normal 20 + 2 \r\n + 1 if negative T)
                            buffer_length = dev.child('Connection').value().connection.inWaiting()
                            if buffer_length >= 24:
                                # create log entry
                                # serial_number = dev.child('Serial number').value()
                                # logging.warning("RHTP %s buffer: %i", serial_number, buffer_length)

                                # read next line
                                extra_data = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                                # remove '\r\n' and split data to list
                                extra_data = extra_data.strip('\r\n').split(", ")
                                # use extra data as latest_data if valid
                                if len(extra_data) == 3:
                                    self.latest_data[dev_id] = extra_data

                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                
                if dev.child('Device type').value() == AFM: # AFM
                    try:
                        # start with nan list
                        self.latest_data[dev_id] = full(5, nan)

                        # if device is in IDN inquiry list, look for *IDN
                        if dev_id in self.idn_inquiry_devices:
                            # read all data from buffer
                            messages = dev.child('Connection').value().connection.read_all().decode().split("\r\n")
                            # go through messages
                            for message in messages:
                                # if message length is above 5 ("*IDN " + device IDN)
                                if len(message) > 5:
                                    # if "*IDN " is part of message
                                    if "*IDN " in message:
                                        serial_number = message.split(" ", 1)[1]
                                        serial_number = serial_number.strip("\n")
                                        serial_number = serial_number.strip("\r")
                                        # check if serial number has changed
                                        if dev.child('Serial number').value() != serial_number:
                                            dev.child('Serial number').setValue(serial_number)
                                        # remove device from IDN inquiry list
                                        if dev_id in self.idn_inquiry_devices:
                                            self.idn_inquiry_devices.remove(dev_id)
                        
                        # if Serial number has been acquired, read data normally
                        else:
                            # read and decode a line of data
                            readings = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                            # remove '\r\n' from end
                            readings = readings.strip('\r\n')
                            # split data to list
                            readings = readings.split(", ")

                            # check if data is valid and store to latest_data
                            # readings length should be 5 (volumetric flow, standard flow, RH, T, P)
                            if len(readings) == 5:
                                self.latest_data[dev_id] = readings

                            # check if there's extra data in buffer
                            # max message length is 39 (normal 34 + 2 \r\n + 1 if negative T + 2 if flow values >= 10)
                            buffer_length = dev.child('Connection').value().connection.inWaiting()
                            if buffer_length >= 40:
                                # create log entry
                                # serial_number = dev.child('Serial number').value()
                                # logging.warning("AFM %s buffer: %i", serial_number, buffer_length)

                                # read next line
                                extra_data = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                                # remove '\r\n' and split data to list
                                extra_data = extra_data.strip('\r\n').split(", ")
                                # use extra data as latest_data if valid
                                if len(extra_data) == 5:
                                    self.latest_data[dev_id] = extra_data
                    
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                
                if dev.child('Device type').value() == EDILUTER: # eDiluter
                    try:
                        # store nan values to latest_data in case reading fails
                        self.latest_data[dev_id] = full(12, nan)
                        # flag indicating if data has already been received, used for handling extra data
                        data_received = False
                        # check if there's extra data from last round
                        if dev_id in self.extra_data:
                            # store extra data to latest_data
                            self.latest_data[dev_id] = self.extra_data[dev_id]
                            # remove extra data from dictionary
                            del self.extra_data[dev_id]
                        # read all data from buffer
                        readings = dev.child('Connection').value().connection.read_all()
                        # decode, separate messages and remove last empty message
                        readings = readings.decode().split("\r\n")[:-1]
                        
                        # loop through messages
                        for message in readings:

                            # if message starts with "time" - data push message
                            if message.split(" ")[0] == "time":
                                # check if message is full (147 characters) # TODO make sure this message is always 147 characters
                                if len(message) == 147:
                                    # remove time and id from message
                                    data = message.split("Status ")[1]
                                    # replace value labels with ""
                                    data = data.replace("pres", "").replace("temp", "").replace("DF", "")
                                    # split data to list
                                    data = data.split(",")
                                    # strip whitespace from values
                                    data = [i.strip() for i in data]
                                    # if data has already been received
                                    if data_received == True:
                                        # store extra data to extra_data dictionary for next round
                                        self.extra_data[dev_id] = data
                                    # if data has not been received yet
                                    else:
                                        # store data to latest_data dictionary with device id as key
                                        self.latest_data[dev_id] = data
                                        # set data received flag to True
                                        data_received = True
                                else: # if message is not full
                                    # TODO store partial message and expect the rest on next round
                                    print("readIndata - eDiluter message not full:", message)
                                    logging.error("readIndata - eDiluter message not full: %s", message)

                            # if message starts with "SUCCESS:" - command message response
                            elif message.split(" ")[0] == "SUCCESS:":
                                # append device's command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message)
                            
                            # if message starts with "ERROR:" - command message response
                            elif message.split(" ")[0] == "ERROR:":
                                # append device's command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message)
                            
                            else: # if message is not recognized
                                logging.error("readIndata - eDiluter unknown message: %s", message)
                                # append device's command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message)
                        
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                    
                    # update eDiluter status tab values
                    self.device_widgets[dev_id].update_values(self.latest_data[dev_id])
                
                if dev.child('Device type').value() == TSI_CPC:
                    try: # try to read data, decode and split
                        readings = dev.child('Connection').value().connection.read_all()
                        readings = readings.decode().split("\r")[:-1]
                        readings[0] = float(readings[0]) # convert concentration to float

                        # store to latest data dictionary
                        self.latest_data[dev_id] = readings

                        # set error_status flag if instrument errors is not equal to 0
                        if int(readings[1], 16) != 0:
                            self.error_status = 1
                            # set device error flag
                            self.set_device_error(dev_id, True)
                    
                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        logging.exception(e)
                        self.latest_data[dev_id] = full(2, nan)

    # check and update 10 hz settings
    def ten_hz_check(self):
        # go through devices
        for dev in self.params.child('Device settings').children():

            try:
                # if device is Airmodus CPC, set TAVG according to 10 hz parameter and check connection to PSM
                if dev.child('Device type').value() == CPC:
                    # if 10 hz is on
                    if dev.child('10 hz').value() == True:
                        # if device is connected
                        if dev.child('Connected').value() == True:
                            # if TAVG is not 0.1, set it to 0.1
                            if self.latest_settings[dev.child('DevID').value()][0] != 0.1:
                                dev.child('Connection').value().send_message(":SET:TAVG 0.1")
                        # check if CPC is still connected to PSM with 10 hz on
                        ten_hz_connected = False
                        for psm in self.params.child('Device settings').children():
                            if psm.child('Device type').value() in [PSM, PSM2]:
                                if psm.child('Connected CPC').value() == dev.child('DevID').value():
                                    if psm.child('10 hz').value() == True:
                                        ten_hz_connected = True
                                        break
                        # if CPC is not connected to PSM with 10 hz on, set 10 hz off
                        if ten_hz_connected == False:
                            dev.child('10 hz').setValue(False)
                    # if 10 hz is off
                    else:
                        # if device is connected
                        if dev.child('Connected').value() == True:
                            # if TAVG is smaller than 1, set it to 1
                            if self.latest_settings[dev.child('DevID').value()][0] < 1:
                                dev.child('Connection').value().send_message(":SET:TAVG 1")
                
                # if device is PSM and 10 hz is on, check if connected CPC has 10 hz on
                elif dev.child('Device type').value() in [PSM, PSM2]:
                    if dev.child('10 hz').value() == True:
                        # if a connected CPC exists
                        if dev.child('Connected CPC').value() != 'None':
                            for cpc in self.params.child('Device settings').children():
                                if cpc.child('DevID').value() == dev.child('Connected CPC').value():
                                    # check if connected CPC is Airmodus CPC
                                    if cpc.child('Device type').value() == CPC:
                                        # if connected CPC has 10 hz off, set it on
                                        if cpc.child('10 hz').value() == False:
                                            cpc.child('10 hz').setValue(True)
                                    break
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)
    
    # update plot data lists
    def update_plot_data(self):

        # ----- PSM connected CPC calculations -----
        
        # before setting plot data, go through each PSM and perform connected CPC calculations
        for dev in self.params.child('Device settings').children():

            try:
                # if device is PSM and it is connected, calculate and compile connected CPC values
                if dev.child('Device type').value() in [PSM, PSM2] and dev.child('Connected').value(): # PSM
                    # get PSM ID
                    psm_id = dev.child('DevID').value()
                    # get connected CPC ID
                    cpc_id = dev.child('Connected CPC').value()

                    # if connected CPC is not 'None' and CPC is not in pulse analysis mode
                    if cpc_id != 'None' and cpc_id not in self.pulse_analysis_index:
                        
                        # get connected CPC device parameter
                        for cpc in self.params.child('Device settings').children():
                            if cpc.child('DevID').value() == cpc_id:
                                cpc_device = cpc
                                break

                        # if CPC is connected, calculate missing values
                        if cpc_device.child('Connected').value() == True:
                            cpc_data = self.latest_data[cpc_id]

                            # Inlet flow = (CPC flow + CO flow) - Saturator flow - Excess flow

                            # get cpc flow rate from PSM latest_settings
                            cpc_flow = float(self.latest_settings[psm_id][5])

                            if dev.child('Device type').value() == PSM:
                                # get co flow rate from PSM widget
                                co_flow = round(self.device_widgets[psm_id].set_tab.set_co_flow.value_spinbox.value(), 3)
                                if co_flow == 0: # if co flow is 0, not set by user
                                    self.device_widgets[psm_id].set_tab.set_co_flow.set_red_color() # set CO flow rate widget to red
                                    self.error_status = 1 # set error_status flag to 1
                                else:
                                    self.device_widgets[psm_id].set_tab.set_co_flow.set_default_color()
                                inlet_flow = cpc_flow + co_flow - float(self.latest_data[psm_id][2]) - float(self.latest_data[psm_id][3])
                            
                            elif dev.child('Device type').value() == PSM2:
                                # get vacuum mfc flow rate from latest data
                                vacuum_flow = float(self.latest_data[psm_id][15])
                                # TODO vacuum flow GUI value is updated in PSMWidget's update_values, check if it works and remove line below
                                #self.device_widgets[psm_id].status_tab.flow_vacuum.change_value(str(round(vacuum_flow, 3)))
                                inlet_flow = cpc_flow + vacuum_flow - float(self.latest_data[psm_id][2]) - float(self.latest_data[psm_id][3])
                                inlet_flow0 = cpc_flow + vacuum_flow - 4 + float(self.latest_data[psm_id][2]) + float(self.latest_data[psm_id][3])
                            
                            # store inlet flow into PSM latest_settings, rounded to 3 decimals
                            self.latest_settings[psm_id][6] = round(inlet_flow, 3)
                            # show inlet flow in PSM widget
                            self.device_widgets[psm_id].status_tab.flow_inlet.change_value(str(round(inlet_flow, 3)))

                            # if received polynomial correction is 0 (placeholder)
                            if self.latest_poly_correction[psm_id] == 0:
                                # calculate polynomial correction factor
                                if dev.child('Device type').value() == PSM:
                                    pcor = array([-0.0272052, 0.11394213, -0.08959011, -0.20675596, 0.24343024, 1.10531145])
                                elif dev.child('Device type').value() == PSM2:
                                    pcor = array([0.12949491, -0.50587616, 0.57214191, 0.76108161])
                                poly_correction  = polyval(pcor, float(self.latest_data[psm_id][2]))
                            else: # if received polynomial correction is other than 0, use received value
                                poly_correction = self.latest_poly_correction[psm_id]

                            # calculate dilution correction factor
                            # Dilution ratio = (inlet flow + Excess flow + Saturator flow) / Inlet flow
                            dilution_correction_factor = (inlet_flow + float(self.latest_data[psm_id][3]) + float(self.latest_data[psm_id][2])) / inlet_flow
                            if dev.child('Device type').value() == PSM2:
                                dilution_correction_factor = (inlet_flow + 4 - float(self.latest_data[psm_id][3]) - float(self.latest_data[psm_id][2])) / inlet_flow0
                            
                            # calculate concentration from PSM
                            # Concentration from PSM = CPC concentration * Dilution ratio / Polynomial correction
                            concentration_from_psm = float(self.latest_data[cpc_id][0]) * dilution_correction_factor / poly_correction
                            # add to PSM latest_data
                            self.latest_data[psm_id][0] = round(concentration_from_psm, 2)

                            # if Connected CPC is Airmodus CPC, add CPC data to PSM latest_data
                            if cpc_device.child('Device type').value() == CPC:
                                # compile connected CPC data
                                connected_cpc_data = [
                                    cpc_data[0], round(dilution_correction_factor, 3), # concentration,  dilution correction factor
                                    cpc_data[3], cpc_data[4], cpc_data[5], cpc_data[6],# T: saturator, condenser, optics, cabin
                                    cpc_data[8], cpc_data[9], cpc_data[7],# P: critical orifice, nozzle, absolute (inlet)
                                    cpc_data[11], cpc_data[2], cpc_data[1],# liquid level, pulses, pulse duration
                                    cpc_data[13], cpc_data[14] # number of errors, system status (hex)
                                ]
                                # replace PSM's latest_data CPC placeholders with connected CPC data
                                self.latest_data[psm_id][-16:-2] = connected_cpc_data # 14 values before status hex and note hex
                            # if Connected device is TSI CPC, add concentration and dilution correction factor to PSM latest_data
                            elif cpc_device.child('Device type').value() == TSI_CPC:
                                self.latest_data[psm_id][-16] = cpc_data[0] # concentration
                                self.latest_data[psm_id][-15] = round(dilution_correction_factor, 3) # dilution correction factor

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

        # ----- update plot data -----

        self.x_time_list = _manage_plot_array(self.x_time_list, self.time_counter, max_reached=self.max_reached)
        self.x_time_list[self.time_counter] = self.current_time
        
        # go through each device
        for dev in self.params.child('Device settings').children():
            # store device id to variable for clarity
            dev_id = dev.child('DevID').value()

            try: # if one device fails, continue with the next one
                dev_type = dev.child('Device type').value()

                # Devices with multiple values - create lists for each value
                if dev_type in [CPC, TSI_CPC, ELECTROMETER, RHTP, AFM]:
                    # determine value types based on device type
                    if dev_type in [CPC, TSI_CPC]:
                        types = ['', ':raw'] # concentration, raw concentration
                    elif dev_type == ELECTROMETER:
                        types = [':1', ':2', ':3'] # voltage 1, voltage 2, voltage 3
                    elif dev_type == RHTP:
                        types = [':rh', ':t', ':p'] # RH, T, P
                    elif dev_type == AFM:
                        types = [':f', ':sf', ':rh', ':t', ':p'] # flow, standard flow, RH, T, P
                    
                    # if device is not yet in plot_data dict, add it
                    if str(dev_id)+types[0] not in self.plot_data:
                        # make the new lists the same size as x_time_list
                        for i in types:
                            self.plot_data[str(dev_id)+i] = full(len(self.x_time_list), nan)

                    # Manage all arrays for this device type in one go
                    for i in types:
                        self.plot_data[str(dev_id)+i] = _manage_plot_array(self.plot_data[str(dev_id)+i], self.time_counter, max_reached=self.max_reached)
                
                # other devices
                else:
                    # if device is not yet in plot_data dict, add it
                    if dev_id not in self.plot_data:
                        # make the new list the same size as x_time_list
                        self.plot_data[dev_id] = full(len(self.x_time_list), nan)
                    self.plot_data[dev_id] = _manage_plot_array(self.plot_data[dev_id], self.time_counter, max_reached=self.max_reached)
                
                # create lists for pulse duration and pulse ratio if they don't exist yet
                if dev_type == CPC:
                    key_pd = str(dev_id)+':pd'
                    if key_pd not in self.plot_data:
                        self.plot_data[key_pd] = full(86400, nan) # 24 hours in seconds
                    self.plot_data[key_pd] = _roll_pulse_array(self.plot_data[key_pd])
                    key_pr = str(dev_id)+':pr'
                    if key_pr not in self.plot_data:
                        self.plot_data[key_pr] = full(86400, nan)
                    self.plot_data[key_pr] = _roll_pulse_array(self.plot_data[key_pr])
                
                # if device is connected, add latest_values data to plot_data according to device
                if dev.child('Connected').value():
                    if dev_type in [CPC, TSI_CPC]: # CPC
                        
                        # if CPC is in pulse analysis mode, update pulse analysis plot data instead of normal plot data
                        if dev_id in self.pulse_analysis_index:
                            if self.pulse_analysis_index[dev_id] is not None: # when index is None, analysis has reached its end
                                try:
                                    # calculate current pulse duration
                                    dead_time = self.latest_data[dev_id][1]
                                    number_of_pulses = self.latest_data[dev_id][2]
                                    if number_of_pulses == 0:
                                        pulse_duration = nan # if number of pulses is 0, set pulse duration to nan
                                    else:
                                        # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                                        pulse_duration = round(dead_time * 1000 / number_of_pulses, 2)
                                    # get current threshold value with pulse_analysis_index
                                    threshold_value = PULSE_ANALYSIS_THRESHOLDS[self.pulse_analysis_index[dev_id]]
                                    #print(f"threshold: {threshold_value} pulse duration: {pulse_duration} dead time: {dead_time} number of pulses: {number_of_pulses}")
                                    # add analysis point to pulse quality widget
                                    self.device_widgets[dev_id].pulse_quality.add_analysis_point(pulse_duration, threshold_value)
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                    # stop pulse analysis if exception occurs
                                    self.pulse_analysis_stop(dev_id, dev)

                        else:
                            psm_connection = False
                            # check if this CPC is connected to any PSM
                            for psm in self.params.child('Device settings').children():
                                if psm.child('Device type').value() in [PSM, PSM2] and psm.child('Connected').value():
                                    if psm.child('Connected CPC').value() == dev_id:
                                        # if PSM connection exists, add latest PSM concentration value to plot_data
                                        self.plot_data[str(dev_id)][self.time_counter] = self.latest_data[psm.child('DevID').value()][0]
                                        psm_connection = True
                                        break
                            # if not connected to PSM, add CPC concentration value to plot_data
                            if psm_connection == False:
                                self.plot_data[str(dev_id)][self.time_counter] = self.latest_data[dev_id][0]
                            # add raw concentration value to plot_data
                            self.plot_data[str(dev_id)+':raw'][self.time_counter] = self.latest_data[dev_id][0]
                            
                            # update pulse duration and pulse ratio lists
                            if dev.child('Device type').value() == CPC:
                                try:
                                    #print("concentration", self.latest_data[dev_id][0], "* sample flow", self.latest_settings[dev_id][2], "=", self.latest_data[dev_id][0] * self.latest_settings[dev_id][2])
                                    # check if (concentration * sample flow) is above 50 and below 5000 (valid)
                                    check_value = self.latest_data[dev_id][0] * self.latest_settings[dev_id][2]
                                    if check_value > 50 and check_value < 5000:
                                        # calculate pulse duration
                                        if self.latest_data[dev_id][2] == 0:
                                            pulse_duration = nan # if number of pulses is 0, set pulse duration to nan
                                        else:
                                            # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                                            pulse_duration = round(self.latest_data[dev_id][1] * 1000 / self.latest_data[dev_id][2], 2)
                                        # store pulse duration and pulse ratio values to plot_data
                                        self.plot_data[str(dev_id)+':pd'][-1] = pulse_duration
                                        self.plot_data[str(dev_id)+':pr'][-1] = self.latest_data[dev_id][12]
                                    else: # if concentration is outside range (invalid)
                                        # store nan values to plot_data
                                        self.plot_data[str(dev_id)+':pd'][-1] = nan
                                        self.plot_data[str(dev_id)+':pr'][-1] = nan
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                    # store nan values to plot_data
                                    self.plot_data[str(dev_id)+':pd'][-1] = nan
                                    self.plot_data[str(dev_id)+':pr'][-1] = nan

                    elif dev_type in [PSM, PSM2]: # PSM
                        # add latest saturator flow rate value to time_counter index of plot_data
                        self.plot_data[dev_id][self.time_counter] = self.latest_data[dev_id][2]
                    elif dev_type == ELECTROMETER: # ELECTROMETER
                        # add latest voltage values to time_counter index of plot_data
                        self.plot_data[str(dev_id)+':1'][self.time_counter] = self.latest_data[dev_id][0]
                        self.plot_data[str(dev_id)+':2'][self.time_counter] = self.latest_data[dev_id][1]
                        self.plot_data[str(dev_id)+':3'][self.time_counter] = self.latest_data[dev_id][2]
                    elif dev_type == CO2_SENSOR: # CO2 sensor
                        # add latest CO2 value to time_counter index of plot_data
                        self.plot_data[dev_id][self.time_counter] = self.latest_data[dev_id][0]
                    elif dev_type == RHTP: # RHTP
                        # add latest values (RH, T, P) to time_counter index of plot_data
                        self.plot_data[str(dev_id)+':rh'][self.time_counter] = self.latest_data[dev_id][0]
                        self.plot_data[str(dev_id)+':t'][self.time_counter] = self.latest_data[dev_id][1]
                        self.plot_data[str(dev_id)+':p'][self.time_counter] = self.latest_data[dev_id][2]
                    elif dev_type == AFM: # AFM
                        # add latest values (flow, RH, T, P) to time_counter index of plot_data
                        self.plot_data[str(dev_id)+':f'][self.time_counter] = self.latest_data[dev_id][0]
                        self.plot_data[str(dev_id)+':sf'][self.time_counter] = self.latest_data[dev_id][1]
                        self.plot_data[str(dev_id)+':rh'][self.time_counter] = self.latest_data[dev_id][2]
                        self.plot_data[str(dev_id)+':t'][self.time_counter] = self.latest_data[dev_id][3]
                        self.plot_data[str(dev_id)+':p'][self.time_counter] = self.latest_data[dev_id][4]
                    elif dev_type == EDILUTER: # eDiluter
                        # add latest T1 value to time_counter index of plot_data
                        self.plot_data[dev_id][self.time_counter] = self.latest_data[dev_id][3]
                if dev_type == -1: # Example device
                    # generate random value for plotting and logging
                    random_value = round(random.random() * 100, 2) # 0-100
                    # add random value to time_counter index of plot_data
                    self.plot_data[dev_id][self.time_counter] = random_value
                    # add random value to latest_data as list object
                    self.latest_data[dev_id] = [random_value]

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

    
    # update plots with plot data lists
    def update_figures_and_menus(self):
        # go through each device
        for dev in self.params.child('Device settings').children():
            
            # store device id and device type to variables for readability
            dev_id = dev.child('DevID').value()
            dev_type = dev.child('Device type').value()

            try: # if one device fails, continue with the next one

                # MAIN PLOT

                # if device is not yet in curve_dict, add it
                # used when plotting to main plot
                if dev.child('DevID').value() not in self.curve_dict:
                    # create curve
                    self.curve_dict[dev_id] = PlotCurveItem(pen=dev_id, connect="finite")
                    #self.curve_dict[dev_id] = PlotCurveItem(pen={'color':dev_id, 'width':2}, connect="finite")
                    # add curve to viewbox according to device type
                    if dev_type == PSM2: # if PSM2, add to PSM viewbox
                        self.main_plot.viewboxes[PSM].addItem(self.curve_dict[dev_id])
                    elif dev_type == TSI_CPC: # if TSI CPC, add to CPC viewbox
                        self.main_plot.viewboxes[CPC].addItem(self.curve_dict[dev_id])
                    else: # other devices
                        self.main_plot.viewboxes[dev_type].addItem(self.curve_dict[dev_id])
                
                # if device type is RHTP or AFM, update main plot according to selected value
                if dev_type in [RHTP, AFM]: # RHTP or AFM
                    if dev.child("Plot to main").value() == None:
                        self.curve_dict[dev_id].setData(x=[], y=[])
                    elif dev.child("Plot to main").value() == 'RH':
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':rh'][:self.time_counter+1])
                    elif dev.child("Plot to main").value() == 'T':
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':t'][:self.time_counter+1])
                    elif dev.child("Plot to main").value() == 'P':
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':p'][:self.time_counter+1])
                    elif dev_type == AFM and dev.child("Plot to main").value() == 'Flow':
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':f'][:self.time_counter+1])
                    elif dev_type == AFM and dev.child("Plot to main").value() == 'Standard flow':
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':sf'][:self.time_counter+1])

                # other devices: update main plot if 'Plot to main' is enabled
                elif dev.child("Plot to main").value():
                    # if device is CPC, get plot data with str(dev_id) key
                    if dev_type in [CPC, TSI_CPC]: # CPC
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)][:self.time_counter+1])
                    # if device is Electrometer, plot Voltage 2
                    elif dev_type == ELECTROMETER: # ELECTROMETER
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':2'][:self.time_counter+1])
                    else: # other devices
                        self.curve_dict[dev_id].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[dev_id][:self.time_counter+1])
                else: # if 'Plot to main' is off, hide curve from main plot (set empty data)
                    self.curve_dict[dev_id].setData(x=[], y=[])
                
                # scale x-axis range if Follow is on
                if self.params.child('Plot settings').child('Follow').value():
                    self.main_plot.plot.setXRange(self.current_time - (p.child('Plot settings').child('Time window (s)').value()), self.current_time, padding=0)

                # INDIVIDUAL PLOTS

                # if device is connected OR Example device
                if dev.child('Connected').value() or dev_type == EXAMPLE_DEVICE:
                    
                    # store current time counter value as start time in dictionary if not yet stored
                    # start time is stored when first non-nan value is received
                    # start time is used to crop plot data to only show non-nan values
                    if dev_id not in self.start_times:
                        # CPC
                        if dev_type in [CPC, TSI_CPC]:
                            if str(self.plot_data[str(dev_id)+':raw'][self.time_counter]) != "nan":
                                self.start_times[dev_id] = self.time_counter
                        # ELECTROMETER
                        elif dev_type == ELECTROMETER:
                            if str(self.plot_data[str(dev_id)+':1'][self.time_counter]) != "nan":
                                self.start_times[dev_id] = self.time_counter
                        # RHTP or AFM
                        elif dev_type in [RHTP, AFM]:
                            if str(self.plot_data[str(dev_id)+':rh'][self.time_counter]) != "nan":
                                self.start_times[dev_id] = self.time_counter
                        # other devices
                        elif str(self.plot_data[dev_id][self.time_counter]) != "nan":
                            self.start_times[dev_id] = self.time_counter

                    # if device is in start times dictionary, update plot
                    if dev_id in self.start_times:
                        # get start time from dictionary to determine plot start index
                        start_time = self.start_times[dev_id]
                        # update plot in device widget
                        # TODO start times removed from curve setData, problems with array shift index - add back later if compatible
                        #self.device_widgets[dev_id].plot_tab.curve.setData(x=self.x_time_list[start_time:self.time_counter+1], y=self.plot_data[dev_id][start_time:self.time_counter+1])
                        if dev_type in [CPC, TSI_CPC]: # CPC
                            # update plot with raw CPC concentration
                            self.device_widgets[dev_id].plot_tab.curve.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':raw'][:self.time_counter+1])
                            # update CPC pulse quality tab view (scatter plot and labels)
                            if dev_type == CPC:
                                self.pulse_quality_update(dev_id)

                        elif dev_type == ELECTROMETER: # ELECTROMETER
                            # update Electrometer plot with all 3 values
                            self.device_widgets[dev_id].plot_tab.curve1.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':1'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curve2.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':2'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curve3.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':3'][:self.time_counter+1])
                        elif dev_type == RHTP: # RHTP
                            # update RHTP plot with all 3 values
                            self.device_widgets[dev_id].plot_tab.curve1.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':rh'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curve2.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':t'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curve3.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':p'][:self.time_counter+1])
                        elif dev_type == AFM: # AFM
                            # update AFM plot with all 5 values
                            self.device_widgets[dev_id].plot_tab.curves[0].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':f'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curves[1].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':sf'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curves[2].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':rh'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curves[3].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':t'][:self.time_counter+1])
                            self.device_widgets[dev_id].plot_tab.curves[4].setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[str(dev_id)+':p'][:self.time_counter+1])
                        else: # other devices
                            self.device_widgets[dev_id].plot_tab.curve.setData(x=self.x_time_list[:self.time_counter+1], y=self.plot_data[dev_id][:self.time_counter+1])
                        
                        # scale x-axis range if Follow is on
                        if self.params.child('Plot settings').child('Follow').value():
                            if dev_type == ELECTROMETER: # if ELECTROMETER, update all 3 plots
                                for plot in self.device_widgets[dev_id].plot_tab.plots:
                                    plot.setXRange(self.current_time - (p.child('Plot settings').child('Time window (s)').value()), self.current_time, padding=0)
                            else: # other devices
                                self.device_widgets[dev_id].plot_tab.plot.setXRange(self.current_time - (p.child('Plot settings').child('Time window (s)').value()), self.current_time, padding=0)

                # PSM CPC FLOW CHECK
                # warn if no CPC is connected or update Set tab's CPC sample flow value

                # if device type is PSM and it is connected
                if dev_type in [PSM ,PSM2] and dev.child('Connected').value():
                    # if no CPC is connected
                    if dev.child('Connected CPC').value() == 'None':
                        # update status_tab flow_cpc widget value and color
                        if self.device_widgets[dev_id].status_tab.flow_cpc.value_label.text() != "Not connected":
                            # set status_tab flow_cpc color to red and change text
                            self.device_widgets[dev_id].status_tab.flow_cpc.change_color(1) # change color to red
                            self.device_widgets[dev_id].status_tab.flow_cpc.change_value("Not connected") # update value on status_tab as well
                        # set error_status flag to 1
                        self.error_status = 1
                        # set device error flag
                        self.set_device_error(dev.child('DevID').value(), True)
                    # if CPC is connected
                    else:
                        # get connected CPC id
                        cpc_id = dev.child('Connected CPC').value()
                        # get connected CPC device parameter
                        for cpc in self.params.child('Device settings').children():
                            if cpc.child('DevID').value() == cpc_id:
                                cpc_device = cpc
                                break
                        # if connected CPC is Airmodus CPC, check if connected CPC sample flow has changed
                        if cpc_device.child('Device type').value() == CPC:
                            cpc_sample_flow = float(self.latest_settings[cpc_id][2])
                            # if CPC sample flow is different from value displayed in Set tab, update displayed value
                            if self.device_widgets[dev_id].set_tab.set_cpc_sample_flow.value_spinbox.value() != cpc_sample_flow:
                                self.device_widgets[dev_id].set_tab.set_cpc_sample_flow.value_spinbox.setValue(cpc_sample_flow)
                        
                        # if CPC inlet flow is different from value displayed in Status tab, update displayed value
                        if self.device_widgets[dev_id].status_tab.flow_cpc.value_label.text() != str(self.latest_settings[dev_id][5]) + " lpm":
                            # set status_tab flow_cpc color to normal and change text
                            self.device_widgets[dev_id].status_tab.flow_cpc.change_color(0)
                            self.device_widgets[dev_id].status_tab.flow_cpc.change_value(str(self.latest_settings[dev_id][5]) + " lpm")

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

        # update axes # TODO add flag for updating axes, activate flag when any 'Plot to main' option is changed
        self.axis_check()
        # update legend with current values
        self.legend_check()
    
    # write data to file(s)
    def write_data(self):
        # if saving is on
        if self.params.child('Data settings').child('Save data').value():

            # create timestamp from current_time
            timestamp = dt.fromtimestamp(self.current_time)
            timeStampStr = str(timestamp.strftime("%Y.%m.%d %H:%M:%S"))

            # go through each device
            for dev in self.params.child('Device settings').children():

                # if device is TSI CPC, do nothing
                if dev.child('Device type').value() == TSI_CPC:
                    pass
                # if device is in pulse analysis mode, do nothing
                elif dev.child('DevID').value() in self.pulse_analysis_index:
                    pass

                # if device is connected OR example device
                elif dev.child('Connected').value() or dev.child('Device type').value() == EXAMPLE_DEVICE:

                    try:
                        # store device id to variable for clarity
                        dev_id = dev.child('DevID').value()

                        # if device is not yet in dat_filenames dict, create .dat file and add filename to dict
                        if dev_id not in self.dat_filenames:
                            # format timestamp for filename
                            timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
                            # get serial number from device settings
                            serial_number = dev.child('Serial number').value()
                            # if serial number is not empty, add underscore to beginning
                            if serial_number != "":
                                serial_number = '_' + serial_number
                            # get device type from device settings
                            device_type = dev.child('Device type').value() # device type number
                            device_type_name = self.device_names[device_type] # device type name
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
                            # compile filename and add to dat_filenames
                            if osx_mode:
                                filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.dat'
                            else:
                                filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.dat'
                            self.dat_filenames[dev_id] = filename
                            with open(self.filePath + filename ,"w",encoding='UTF-8'):
                                pass
                            
                            # if CPC or PSM, create .par file and add filename to par_filenames
                            if dev.child('Device type').value() in [CPC, PSM, PSM2]:
                                if osx_mode:
                                    filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.par'
                                else:
                                    filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.par'
                                self.par_filenames[dev_id] = filename
                                with open(self.filePath + filename ,"w",encoding='UTF-8'):
                                    pass
                                self.par_updates[dev.child('DevID').value()] = 1 # set .par update flag, ensuring new .par file is updated at start
                        
                        # check if device is Airmodus CPC and 10hz parameter is on
                        if dev.child('Device type').value() == CPC and dev.child('10 hz').value():
                            # if device is not in ten_hz_filenames dict, create .csv file and add filename to ten_hz_filenames
                            if dev_id not in self.ten_hz_filenames:
                                # format timestamp for filename
                                timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
                                # get serial number from device settings
                                serial_number = dev.child('Serial number').value()
                                # if serial number is not empty, add underscore to beginning
                                if serial_number != "":
                                    serial_number = '_' + serial_number
                                # get device type from device settings
                                device_type = dev.child('Device type').value() # device type number
                                device_type_name = self.device_names[device_type] # device type name
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
                                # compile filename and add to ten_hz_filenames
                                if osx_mode:
                                    filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + '_10hz' + file_tag + '.csv'
                                else:
                                    filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + '_10hz' + file_tag + '.csv'
                                self.ten_hz_filenames[dev_id] = filename
                                # create file and write header
                                with open(self.filePath + filename ,"w",encoding='UTF-8') as file:
                                    # write header
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration 1 (#/cc),Concentration 2 (#/cc),Concentration 3 (#/cc),Concentration 4 (#/cc),Concentration 5 (#/cc),Concentration 6 (#/cc),Concentration 7 (#/cc),Concentration 8 (#/cc),Concentration 9 (#/cc),Concentration 10 (#/cc)')
                            
                        # get filename from dictionary and add path to front
                        filename = self.filePath + self.dat_filenames[dev_id]
                        
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
                            write_data = ','.join(str(vals) for vals in self.latest_data[dev_id])
                            # write data
                            file.write(write_data)
                        
                        # if CPC or PSM, append .par file with new settings
                        if dev.child('Device type').value() in [CPC, PSM, PSM2]:
                            # get filename from dictionary and add path to front
                            filename = self.filePath + self.par_filenames[dev_id]

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
                                if self.par_updates[dev_id] == 1:
                                    update_par = 1
                                
                                # else if a command has been entered, write data
                                elif dev_id in self.latest_command:
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
                                        if dev.child('Connected CPC').value() in self.par_updates and self.par_updates[dev.child('Connected CPC').value()] == 1:
                                            update_par = 1
                                
                                # if update_par flag is set
                                if update_par == 1:
                                    file.write("\n")
                                    # Add timestamp
                                    file.write(timeStampStr+',')
                                    # Convert data to string                            
                                    write_data = ','.join(str(vals) for vals in self.latest_settings[dev_id])
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
                                                cpc_settings = self.latest_settings[cpc_id]
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
                                    if dev_id in self.latest_command:
                                        # write latest command to file and remove from dictionary
                                        file.write(',' + self.latest_command.pop(dev_id))
                        
                        # check if device is Airmodus CPC and 10hz parameter is on
                        if dev.child('Device type').value() == CPC and dev.child('10 hz').value():
                            # check if device is in latest_ten_hz dictionary
                            if dev_id in self.latest_ten_hz:
                                # get filename from dictionary and add path to front
                                filename = self.filePath + self.ten_hz_filenames[dev_id]
                                # append file with new data
                                with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                                    file.write("\n")
                                    # Add timestamp
                                    file.write(timeStampStr+',')
                                    # Convert data to string
                                    write_data = ','.join(str(vals) for vals in self.latest_ten_hz[dev_id])
                                    file.write(write_data)

                    # if saving fails, set saving status to 0
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        self.saving_status = 0 # set saving status to 0
                
                # if device is not connected
                else:
                    pass
                # TODO change saving status if device is not connected?

        else: # if saving is toggled off
            self.saving_status = 0 # set saving status to 0
        
        # write data to pulse analysis file if pulse analysis is on
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            if dev_id in self.pulse_analysis_index:
                if self.pulse_analysis_index[dev_id] is not None: # when index is None, analysis has reached its end
                    try:
                        # calculate current pulse duration
                        dead_time = self.latest_data[dev_id][1]
                        number_of_pulses = self.latest_data[dev_id][2]
                        if number_of_pulses == 0:
                            pulse_duration = nan # if number of pulses is 0, set pulse duration to nan
                        else:
                            # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                            pulse_duration = round(dead_time * 1000 / number_of_pulses, 2)
                        # get current threshold value with pulse_analysis_index
                        threshold_value = PULSE_ANALYSIS_THRESHOLDS[self.pulse_analysis_index[dev_id]]
                        # get filename from dictionary (includes file path)
                        filename = self.pulse_analysis_filenames[dev_id]
                        # append file with new data
                        with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                            file.write('\n') # create new line
                            file.write(str(threshold_value) + ',' + str(number_of_pulses) + ',' + str(dead_time) + ',' + str(pulse_duration))
                        # increase pulse_analysis_index by 1
                        self.pulse_analysis_index[dev_id] += 1
                        # if all thresholds have been gone through, end pulse analysis
                        if self.pulse_analysis_index[dev_id] >= len(PULSE_ANALYSIS_THRESHOLDS):
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
            self.reset_filenames()
            # disable read only file path
            self.params.child('Data settings').child('File path').setReadonly(False)

    def filepath_changed(self):
        # set file path
        self.filePath = self.params.child('Data settings').child('File path').value()
        # reset filename dictionaries
        self.reset_filenames()
    
    # reset filename dictionaries, results in new files being created
    def reset_filenames(self):
        self.dat_filenames = {}
        self.par_filenames = {}
        self.ten_hz_filenames = {}
        self.par_updates = {}
    
    # remove specific device from filename dictionaries, results in new files being created
    def reset_device_filenames(self, dev_id):
        if dev_id in self.dat_filenames:
            self.dat_filenames.pop(dev_id)
        if dev_id in self.par_filenames:
            self.par_filenames.pop(dev_id)
        if dev_id in self.par_updates:
            self.par_updates.pop(dev_id)
        if dev_id in self.ten_hz_filenames:
            self.ten_hz_filenames.pop(dev_id)

    

    
    # compare current day to file start day (self.start_day defined in save_changed)
    def compare_day(self):
        # check if saving is on
        if self.params.child('Data settings').child('Save data').value():
            # check if new file should be started at midnight
            if self.params.child("Data settings").child('Generate daily files').value():
                current_day = dt.fromtimestamp(self.current_time).strftime("%m%d")
                if current_day != self.start_day:
                    self.reset_filenames() # start new file if day has changed
                    # update start day
                    self.start_day = current_day
    
    # set COM port inquiry flag
    def set_inquiry_flag(self):
        self.inquiry_flag = True
        self.inquiry_time = time()
        self.com_descriptions = {} # reset com descriptions
    
    def list_com_ports(self):
        # get list of available ports as serial objects
        ports = list_ports.comports()
        # check if ports list has changed from stored ports
        # if ports != self.current_ports: # if ports have changed, set flag for a specific time
        #     self.set_inquiry_flag()
        # self.current_ports = ports # store current ports for comparison
        com_port_list = [] # list of port addresses
        new_ports = {} # dictionary for new ports, ports are added after *IDN? send
        # go through current ports
        for port in sorted(ports):
            # add comport to list of com port addresses
            com_port_list.append(port[0])
            # if port is not in com_descriptions
            if port[0] not in self.com_descriptions:
                # add port to com_descriptions with default descripion
                self.com_descriptions[port[0]] = port[1]
            # if inquiry flag is True, inquire IDN from ports that haven't been inquired yet
            if self.inquiry_flag == True:
                # inquire IDN from ports with default description
                # if port has default description, port *IDN? hasn't been acquired
                if self.com_descriptions[port[0]] == port[1]:
                    try:
                        # open port
                        serial_connection = Serial(str(port[0]), 115200, timeout=0.2)
                        # inquire device type - delay makes sure ESP32 init is done
                        self.idn_inquiry(serial_connection)
                        # add serial_connection to new_ports dictionary, port address : serial object
                        # new_ports dictionary is sent to update_com_ports after delay
                        new_ports[port[0]] = serial_connection
                    # if port cannot be opened, look for serial number in device parameters
                    except SerialException:
                        for dev in self.params.child('Device settings').children():
                            if osx_mode:
                                if port[0] == dev.child('COM port').value():
                                    # set description according to device's serial number parameter
                                    self.com_descriptions[port[0]] = dev.child('Serial number').value()
                            else:
                                if port[0] == 'COM' + str(dev.child('COM port').value()):
                                    # set description according to device's serial number parameter
                                    self.com_descriptions[port[0]] = dev.child('Serial number').value()
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
        # remove port descriptions for physically disconnected devices
        remove_ports = []
        for port in self.com_descriptions.keys():
            if port not in com_port_list:
                remove_ports.append(port)
        for port in remove_ports:
            self.com_descriptions.pop(port)
        # if inquiry flag is True, check timeout
        if self.inquiry_flag == True:
            # if inquiry has timed out - if current time is bigger than inquiry_time + timeout (seconds)
            if time() > self.inquiry_time + 3:
                self.inquiry_flag = False # set inquiry flag to False

        # trigger update_com_ports with delay
        # reads responses from opened ports and prints devices to GUI
        QTimer.singleShot(800, lambda: self.update_com_ports(new_ports, com_port_list)) # delay increased from 600 to 800
        # return list of port addresses
        return com_port_list
    
    def update_com_ports(self, new_ports, com_port_list):
        # read messages from new_ports and update descriptions
        for port in new_ports:
            try:
                # read received messages
                messages = new_ports[port].read_all().decode().split("\r")
                print("update_com_ports -", port, "messages:", messages)
                # go through messages and find *IDN
                for message in messages:
                    # if message length is above 5 ("*IDN " + device IDN)
                    if len(message) > 5:
                        # if "*IDN " is part of message
                        if "*IDN " in message:
                            # read after "*IDN " and store to com_descriptions
                            serial_number = message[message.index("*IDN ")+5:]
                            serial_number = serial_number.strip("\n")
                            serial_number = serial_number.strip("\r")
                            self.com_descriptions[port] = serial_number
                            new_ports[port].close() # close port after *IDN response
                        # eDiluter ID
                        elif " ID " in message:
                            # read device ID between " ID " and ", Status" and store to com_descriptions
                            self.com_descriptions[port] = message[message.index(" ID ")+4:message.index(", Status")]
                            new_ports[port].close() # close port after *IDN response
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)
            try: # if inquiry has ended and port is still open, close port
                if self.inquiry_flag == False and new_ports[port].is_open:
                    new_ports[port].close()
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)
        # compile com_ports_text using com_descriptions
        # add only devices that are connected - in com_port_list
        com_ports_text = ""
        for key in self.com_descriptions:
            # if port is currently physically connected - in com_port_list
            if key in com_port_list:
                com_ports_text += key + " - " + self.com_descriptions[key] + "\n"
        # update GUI 'Available serial ports' text box if com port list has changed
        if com_ports_text != self.params.child('Serial ports').child('Available serial ports').value():
            self.params.child('Serial ports').child('Available serial ports').setValue(com_ports_text)

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
                self.params.child('Device settings').addNew(self.device_names[dev_type], device_name=dev_name)
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
                        self.device_widgets[param.parent().child("DevID").value()].set_tab.set_co_flow.value_spinbox.setValue(round(float(param.value()), 3))
                    except ValueError:
                        pass # if value has not been saved, skip
                # Check if parameter name is 10 hz
                elif param.name() == '10 hz':
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
                    # if device type is PSM or PSM2
                    if param.parent().child('Device type').value() in [PSM, PSM2]:
                        # Set 10 hz status (True/False) to ten_hz button
                        self.device_widgets[param.parent().child("DevID").value()].measure_tab.ten_hz.change_color(int(values.get(param.name(), param.value())))
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
                for plot in self.device_widgets[dev_id].plot_tab.plots:
                    plot.enableAutoRange()
            else:
                self.device_widgets[dev_id].plot_tab.plot.enableAutoRange()
            
    
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
    
    # updates main_plot axes according to Plot to main settings
    def axis_check(self):
        # hide all axes
        for key in self.main_plot.axes:
            self.main_plot.show_hide_axis(key, False)
        # show axes for devices that are set to plot to main
        for dev in self.params.child('Device settings').children():
            # RHTP
            if dev.child('Device type').value() == RHTP:
                self.main_plot.change_rhtp_axis(dev.child('Plot to main').value())
            # AFM
            elif dev.child('Device type').value() == AFM:
                self.main_plot.change_afm_axis(dev.child('Plot to main').value())
            # other devices
            elif dev.child('Plot to main').value():
                self.main_plot.show_hide_axis(dev.child('Device type').value(), True)
    
    # updates main_plot legend with current values according to 'Plot to main' settings
    def legend_check(self):
        # clear legend
        self.main_plot.legend.clear()
        # check each device and add to legend if exists in curve_dict and Plot to main is enabled
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            # if device is in curve_dict
            if dev_id in self.curve_dict:
                # check if device has a nickname
                if dev.child('Device nickname').value() != "":
                    device_name = dev.child('Device nickname').value()
                else: # if no nickname, use device parameter name (device type and serial number)
                    device_name = dev.name()
                # RHTP or AFM
                if dev.child('Device type').value() in [RHTP, AFM]:
                    # if Plot to main is enabled
                    if dev.child('Plot to main').value() != None:
                        # add curve to legend with device name and current value of chosen parameter
                        if dev.child('Plot to main').value() == "RH":
                            legend_string = device_name + ": " + str(self.plot_data[str(dev_id)+':rh'][self.time_counter])
                        elif dev.child('Plot to main').value() == "T":
                            legend_string = device_name + ": " + str(self.plot_data[str(dev_id)+':t'][self.time_counter])
                        elif dev.child('Plot to main').value() == "P":
                            legend_string = device_name + ": " + str(self.plot_data[str(dev_id)+':p'][self.time_counter])
                        elif dev.child('Device type').value() == AFM and dev.child('Plot to main').value() == "Flow":
                            legend_string = device_name + ": " + str(self.plot_data[str(dev_id) + ':f'][self.time_counter])
                        elif dev.child('Device type').value() == AFM and dev.child('Plot to main').value() == "Standard flow":
                            legend_string = device_name + ": " + str(self.plot_data[str(dev_id) + ':sf'][self.time_counter])
                        self.main_plot.legend.addItem(self.curve_dict[dev_id], legend_string)
                    else: # if disabled
                        # remove curve from legend
                        self.main_plot.legend.removeItem(self.curve_dict[dev_id])
                # other devices
                # if Plot to main is True
                elif dev.child('Plot to main').value():
                    # compile legend string - device name and current value
                    # if CPC, round value to 2 decimals
                    if dev.child('Device type').value() in [CPC, TSI_CPC]:
                        legend_string = device_name + ": " + str(round(self.plot_data[str(dev_id)][self.time_counter], 2))
                    # if ELECTROMETER, get Voltage 2 value
                    elif dev.child('Device type').value() == ELECTROMETER:
                        legend_string = device_name + ": " + str(self.plot_data[str(dev_id)+':2'][self.time_counter])
                    # other devices
                    else:
                        legend_string = device_name + ": " + str(self.plot_data[dev_id][self.time_counter])
                    # add curve to legend with legend string
                    self.main_plot.legend.addItem(self.curve_dict[dev_id], legend_string)
                else: # if False
                    # remove curve from legend
                    self.main_plot.legend.removeItem(self.curve_dict[dev_id])
    
    # update CPC pulse quality tab view (scatter plot and labels)
    # called in update_figures_and_menus and when pulse quality options ae changed
    def pulse_quality_update(self, device_id):
        try:
            # check selected average time and history draw limit
            draw_limit_h = self.device_widgets[device_id].pulse_quality.history_time # hours
            draw_limit_s = draw_limit_h * 3600 # seconds
            avg_time = self.device_widgets[device_id].pulse_quality.average_time * 3600 # seconds
            # calculate average values (ignore nan values)
            avg_pulse_duration = nanmean(self.plot_data[str(device_id)+':pd'][-avg_time:])
            avg_pulse_ratio = nanmean(self.plot_data[str(device_id)+':pr'][-avg_time:])
            # slice pulse duration and pulse ratio data to selected history time
            # number of points is always 3600, longer times are drawn with lower resolution
            # start at end of list, stop at negative draw limit in seconds, step size negative draw limit in hours
            sliced_pd = self.plot_data[str(device_id)+':pd'][-1:-1*(draw_limit_s+1):-1*draw_limit_h]
            sliced_pr = self.plot_data[str(device_id)+':pr'][-1:-1*(draw_limit_s+1):-1*draw_limit_h]

            # update pulse quality scatter plot and value labels
            # draw history with sliced data
            self.device_widgets[device_id].pulse_quality.data_points.setData(sliced_pd, sliced_pr)
            # update current point and labels
            # check if (concentration * sample flow) is above 50 and below 5000 (valid)
            check_value = self.latest_data[device_id][0] * self.latest_settings[device_id][2]
            if check_value > 50 and check_value < 5000:
                self.device_widgets[device_id].pulse_quality.current_point.setData(x=[self.plot_data[str(device_id)+':pd'][-1]], y=[self.plot_data[str(device_id)+':pr'][-1]])
                self.device_widgets[device_id].pulse_quality.current_duration.setText(str(round(self.plot_data[str(device_id)+':pd'][-1], 3)))
                self.device_widgets[device_id].pulse_quality.current_ratio.setText(str(round(self.plot_data[str(device_id)+':pr'][-1], 3)))
            else: # if concentration is outside range (invalid)
                self.device_widgets[device_id].pulse_quality.current_point.setData(x=[], y=[]) # set current point to empty if invalid data
                self.device_widgets[device_id].pulse_quality.current_duration.setText("Concentration out of range")
                self.device_widgets[device_id].pulse_quality.current_ratio.setText("Concentration out of range")
            # update average point and labels
            self.device_widgets[device_id].pulse_quality.average_point.setData(x=[avg_pulse_duration], y=[avg_pulse_ratio])
            self.device_widgets[device_id].pulse_quality.average_duration.setText(str(round(avg_pulse_duration, 2)))
            self.device_widgets[device_id].pulse_quality.average_ratio.setText(str(round(avg_pulse_ratio, 2)))
        except Exception as e:
            print(traceback.format_exc())
            #logging.exception(e)
    
    # start CPC pulse analysis, stop normal operation
    def pulse_analysis_start(self, device_id, device_param):
        # ask for user confirmation before starting
        start = QMessageBox.question(self, 'Start pulse analysis?', 'Regular measurement for this device will pause for one minute.\nStart pulse analysis?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if start == QMessageBox.No:
            return
        try:
            # add device to pulse_analysis_index dictionary with index value 0
            self.pulse_analysis_index[device_id] = 0
            # update pulse analysis status
            self.device_widgets[device_id].pulse_quality.update_pa_status(True)
            # disable command input
            self.device_widgets[device_id].set_tab.command_widget.disable_command_input()

            # get original threshold value from latest_settings
            # value should stay intact during pulse analysis, settings are not updated
            original_threshold = self.latest_settings[device_id][7]
            # if threshold value is nan, stop pulse analysis
            if isnan(original_threshold):
                self.pulse_analysis_stop(device_id, device_param)
                return

            # clear previous pulse analysis points
            self.device_widgets[device_id].pulse_quality.clear_analysis_points()

            # create file and store threshold value
            filepath = self.params.child('Data settings').child('File path').value()
            # timestamp
            timestamp = dt.fromtimestamp(self.current_time)
            timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
            # serial number
            serial_number = device_param.child('Serial number').value()
            # compile filename and add to pulse_analysis_filenames dictionary
            if osx_mode:
                filename = filepath + '/' + timestamp_file + '_pulse_analysis_' + serial_number + '.csv'
            else:
                filename = filepath + '\\' + timestamp_file + '_pulse_analysis_' + serial_number + '.csv'
            self.pulse_analysis_filenames[device_id] = filename
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
            device_param.child('Connection').value().send_message(":SET:OPC:THRS " + str(self.latest_settings[device_id][7]))
        except Exception as e:
            print(traceback.format_exc())
            logging.exception(e)
        # clear current threshold value
        self.device_widgets[device_id].pulse_quality.current_threshold.setText("")
        # set pulse_analysis_index to None (signaling end of pulse analysis)
        self.pulse_analysis_index[device_id] = None
        # remove device id from pulse_analysis_index dictionary with delay
        # delay ensures CPC has time to set original threshold before measurement continues
        QTimer.singleShot(1000, lambda: self.pulse_analysis_index.pop(device_id))
        # remove device id from pulse_analysis_filenames dictionary
        if device_id in self.pulse_analysis_filenames:
            self.pulse_analysis_filenames.pop(device_id)

        # TODO plot gaussian fit and calculate nRMSE
        # analysis values are stored as listed tuples (pulse duration, threshold value)
        # analysis_values = self.device_widgets[device_id].pulse_quality.analysis_values
        # pulse_durations = [x[0] for x in analysis_values]
        # thresholds = [x[1] for x in analysis_values]

        # enable command input
        self.device_widgets[device_id].set_tab.command_widget.enable_command_input()
        # update pulse analysis status
        self.device_widgets[device_id].pulse_quality.update_pa_status(False)
    
    # set device error status in dictionary
    def set_device_error(self, device_id, error):
        self.device_errors[device_id] = error
    
    # updates tab error icons according to device_errors dictionary
    # TODO add comparison list of previous values to avoid unnecessary icon updates
    def update_error_icons(self):
        # go through each device
        for dev in self.params.child('Device settings').children():
            try:
                # device id
                device_id = dev.child('DevID').value()
                # error status from device_errors
                error = self.device_errors[device_id]
                # device type
                device_type = dev.child('Device type').value()
                # device widget
                device_widget = self.device_widgets[device_id]
                # device widget tab index
                tab_index = self.device_tabs.indexOf(device_widget)
                # connected status
                connected = dev.child('Connected').value() # True or False

                # if connected is False
                if not connected and device_type != EXAMPLE_DEVICE: # exclude Example device
                    # set disconnected icon
                    self.device_tabs.setTabIcon(tab_index, self.disconnected_icon)
                    # set general error status flag
                    self.error_status = 1

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
        device_type_name = self.device_names[device_type] # device type name
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
        device_widget = self.device_widgets[device_id]
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
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: command_entered(device_id, device_param, self.device_widgets))
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
                widget.pulse_quality.history_time_select.currentIndexChanged.connect(lambda: self.pulse_quality_update(device_id))
                widget.pulse_quality.average_time_select.currentIndexChanged.connect(lambda: self.pulse_quality_update(device_id))
                # connect pulse analysis start button to pulse_analysis_start function
                widget.pulse_quality.start_analysis.clicked.connect(lambda: self.pulse_analysis_start(device_id, device_param))
                # connect device nickname change to ScalableGroup's update_cpc_dict function
                device_param.child("Device nickname").sigValueChanged.connect(param.update_cpc_dict)

            if device_type in [PSM, PSM2]: # if PSM TODO optimize structure, remove repetition
                # create PSM widget instance
                widget = PSMWidget(device_param, device_type)
                # add to psm_settings_updates dictionary, set to True
                self.psm_settings_updates[device_id] = True
                # add to extra_data_counter dictionary, set to 0
                self.extra_data_counter[device_id] = 0
                # connect Measure tab buttons to send_set function
                widget.measure_tab.scan.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_scan()))
                widget.measure_tab.step.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_step()))
                widget.measure_tab.fixed.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_fixed()))
                # connect ten_hz button to ten_hz_clicked function
                widget.measure_tab.ten_hz.clicked.connect(lambda: ten_hz_clicked(device_param, widget))
                # connect SetTab SetWidgets to send_set_val function and set settings update flag to True
                # growth tube temperature set
                widget.set_tab.set_growth_tube_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:GT "))
                widget.set_tab.set_growth_tube_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                widget.set_tab.set_growth_tube_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_growth_tube_temp.value_input.text()), ":SET:TEMP:GT "))
                widget.set_tab.set_growth_tube_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                # saturator temperature set
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_saturator_temp.value_input.text()), ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                # inlet temperature set
                widget.set_tab.set_inlet_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:INL "))
                widget.set_tab.set_inlet_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                widget.set_tab.set_inlet_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_inlet_temp.value_input.text()), ":SET:TEMP:INL "))
                widget.set_tab.set_inlet_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                # heater temperature set
                widget.set_tab.set_heater_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:PRE "))
                widget.set_tab.set_heater_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                widget.set_tab.set_heater_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_heater_temp.value_input.text()), ":SET:TEMP:PRE "))
                widget.set_tab.set_heater_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                # drainage temperature set
                widget.set_tab.set_drainage_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:DRN "))
                widget.set_tab.set_drainage_temp.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                widget.set_tab.set_drainage_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_drainage_temp.value_input.text()), ":SET:TEMP:DRN "))
                widget.set_tab.set_drainage_temp.value_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                # cpc inlet flow set (send value to PSM)
                #widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:FLOW:CPC "))
                widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda value: psm_flow_send(device_param, value))
                widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                #widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_cpc_inlet_flow.value_input.text()), ":SET:FLOW:CPC "))
                widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: psm_flow_send(device_param, float(widget.set_tab.set_cpc_inlet_flow.value_input.text())))
                widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                # cpc sample flow set (send value to connected CPC if it exists)
                # TODO is psm_update required when setting cpc sample flow?
                widget.set_tab.set_cpc_sample_flow.value_spinbox.stepChanged.connect(lambda value: cpc_flow_send(device_param, value))
                widget.set_tab.set_cpc_sample_flow.value_input.returnPressed.connect(lambda: cpc_flow_send(device_param, float(widget.set_tab.set_cpc_sample_flow.value_input.text())))
                # if device type is PSM, connect co flow set
                if device_type == PSM:
                    widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                    widget.set_tab.set_co_flow.value_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                    # set value to hidden 'CO flow' parameter in parameter tree
                    widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(lambda value: device_param.child('CO flow').setValue(str(round(value, 3))))
                    widget.set_tab.set_co_flow.value_input.returnPressed.connect(lambda: device_param.child('CO flow').setValue(widget.set_tab.set_co_flow.value_input.text()))
                # connect command_input to command_entered and psm_update functions
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: command_entered(device_id, device_param, self.device_widgets))
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: psm_update(device_id, self.psm_settings_updates))
                # connect liquid operations
                widget.set_tab.autofill.clicked.connect(lambda: connection.send_set(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
                #widget.set_tab.autofill.clicked.connect(lambda: self.psm_update(device_id, self.psm_settings_updates))
                widget.set_tab.drain.clicked.connect(lambda: connection.send_set(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
                #widget.set_tab.drain.clicked.connect(lambda: self.psm_update(device_id, self.psm_settings_updates))
                widget.set_tab.drying.clicked.connect(lambda: connection.send_set(widget.set_tab.drying.messages[int(widget.set_tab.drying.isChecked())]))
                #widget.set_tab.drying.clicked.connect(lambda: self.psm_update(device_id, self.psm_settings_updates))

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
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: self.command_entered(device_id, device_param, self.device_widgets, self.latest_command))
            
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

            # add widget instance to device_widgets dictionary with device ID as key
            self.device_widgets[device_id] = widget
            # add widget instance to tab widget
            self.device_tabs.addTab(widget, widget.name)
            # add device id to device_errors dictionary
            self.device_errors[device_id] = False
    
    # triggered when a device is removed from the parameter tree
    # sigChildRemoved(self, parent, child, index) - Emitted when a child (device) is removed
    def device_removed(self, param, child):
        if param == self.params.child("Device settings"):
            device_id = child.child("DevID").value()
            device_type = child.child("Device type").value()
            # remove device widget from main tab widget
            self.device_tabs.removeTab(self.device_tabs.indexOf(self.device_widgets[device_id]))
            # close serial connection if open
            try:
                child.child('Connection').value().close()
            except AttributeError:
                pass
            # set empty data to curve_dict (remove curve from Main plot)
            try:
                self.curve_dict[device_id].setData(x=[], y=[])
            except KeyError:
                pass
            # remove device from all device related dictionaries
            for dictionary in [self.latest_data, self.latest_settings, self.latest_psm_prnt, # data
                self.latest_poly_correction, self.latest_ten_hz, self.extra_data, self.psm_dilution, # data
                self.plot_data, self.curve_dict, self.start_times, self.device_widgets, # plots and widgets
                self.dat_filenames, self.par_filenames, self.ten_hz_filenames, # filenames
                self.par_updates, self.psm_settings_updates, self.device_errors]: # flags
                try:
                    del dictionary[device_id]
                except KeyError:
                    pass
                # plot data string keys cleaning
                if dictionary == self.plot_data:
                    # check if device has multiple data types
                    if device_type in [CPC, TSI_CPC, ELECTROMETER, RHTP, AFM]:
                        # determine value types based on device type
                        if device_type in [CPC, TSI_CPC]:
                            types = ['', ':raw'] # concentration, raw concentration
                        elif device_type == ELECTROMETER:
                            types = [':1', ':2', ':3'] # voltage 1, voltage 2, voltage 3
                        elif device_type == RHTP:
                            types = [':rh', ':t', ':p'] # RH, T, P
                        elif device_type == AFM:
                            types = [':f', ':sf', ':rh', ':t', ':p'] # flow, standard flow, RH, T, P
                        # remove all keys with device_id and value types
                        for t in types:
                            try:
                                del dictionary[str(device_id)+t]
                            except KeyError:
                                pass

    def startTimer(self):
        # check start time and sync with next second
        start_time = time()
        sync_time = start_time - int(start_time)
        sleep(1 - sync_time)
        # start timer
        self.timer.start(1000)
        print("Timer start time:", time())

    def endTimer(self):
        self.timer.stop()
    
    # restart timer to sync to seconds
    def restartTimer(self):
        self.endTimer() # stop timer
        print("Restarting timer...")
        self.startTimer() # start timer
        self.timer_functions() # call timer functions at start time


# application format
if __name__ == '__main__': # protects from accidentally invoking the script when not intended
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
