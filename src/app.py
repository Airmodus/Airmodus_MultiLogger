from datetime import datetime as dt
from time import time
import os
import traceback
import json

from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (QMainWindow, QSplitter, QApplication, QTabWidget, QLabel,
    QFileDialog)
from pyqtgraph.parametertree import ParameterTree

from config import *
from utils import (
    psm_update,
    psm_flow_send,
    cpc_flow_send,
    ten_hz_clicked,
    command_entered
)
from plots import (
    MainPlot,
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
    PlotManager,
    DataLogger,
    ErrorStatus
)

from serial_connection import SerialDeviceConnection
from params import p


# main program
class MainWindow(QMainWindow):

    def __init__(self, params=p, parent=None):
        super().__init__() # super init function must be called when subclassing a Qt class
        self.setWindowTitle("Airmodus MultiLogger v. " + version_number) # set window title

        self.params = params # predefined parameter tree
        self.config_file_path = "" # path to the configuration file

        # Extracted inits
        self.data_holder = DataHolder()
        self.data_holder.error_icon = QIcon(resource_path + "/icons/error.png")
        self.data_holder.disconnected_icon = QIcon(resource_path + "/icons/disconnected.png")

        self._setup_parameter_tree()
        for child in self.params.child('Device settings').children():
            self.device_added(self.params.child('Device settings'), child) 

        self.device_manager = DeviceManager(self.params, self.data_holder, self.data_holder.device_widgets)
        self.device_manager.list_com_ports()
        self._setup_gui()
        self.plot_manager = PlotManager(self, self.data_holder, self.main_plot)
        self.data_logger = DataLogger(self.data_holder, self.params)
        self._connect_signals()
        self.error_status = ErrorStatus(self.data_holder, self.params, self.device_tabs)

        self.timer_service = TimerService(self, self.data_holder, self.device_manager, self.plot_manager, self.data_logger, self.error_status)
        self.timer_service.start()

        # load ini file if available
        self.load_ini()

    def _setup_parameter_tree(self):
        """Create and configure the ParameterTree."""
        # create parameter tree
        self.t = ParameterTree()
        self.t.setParameters(self.params, showTop=False)
        self.t.setHeaderHidden(True)

        # load CSS style and apply it to the main window
        with open(script_path + "/style.css", "r") as f:
            self.style = f.read()
        self.setStyleSheet(self.style)


    def _setup_gui(self):
        """Build main layout, splitters, tabs, etc."""
        # create and set central widget (requirement of QMainWindow)
        self.main_splitter = QSplitter()
        self.setCentralWidget(self.main_splitter)
        # create logo pixmap label
        self.logo = QLabel(alignment=Qt.AlignCenter, objectName="logo")
        pixmap = QPixmap(resource_path + "/images/airmodus-envea-logo.png")
        self.logo.setPixmap(pixmap.scaled(400, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        # create left side vertical splitter
        # contains parameter tree and status widget
        left_splitter = QSplitter(Qt.Vertical) # split vertically
        left_splitter.addWidget(self.logo) # add logo
        left_splitter.addWidget(self.t) # add parameter tree widget
        left_splitter.addWidget(self.data_holder.status_lights) # add status lights widget
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
        self.params.child('Data settings').child('Save data').sigValueChanged.connect(self.data_logger.save_changed)
        # connect file path parameter to filepath_changed function
        self.params.child('Data settings').child('File path').sigValueChanged.connect(self.data_logger.filepath_changed)
        # connect file tag parameter to reset_all_filenames function
        self.params.child('Data settings').child('File tag').sigValueChanged.connect(self.data_logger.reset_all_filenames)
        # connect com port update button
        self.params.child('Serial ports').child('Update serial ports').sigActivated.connect(self.set_inquiry_flag)

        # connect parameter tree's sigChildAdded signal to device_added function
        self.params.child("Device settings").sigChildAdded.connect(self.device_added)
        # connect parameter tree's sigChildRemoved signal to device_removed function
        self.params.child("Device settings").sigChildRemoved.connect(self.device_removed)
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

    # set COM port inquiry flag
    def set_inquiry_flag(self):
        self.data_holder.inquiry_flag = True
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
    def device_added(self, param, child):
        if param.name() == "Device settings": # check if detected parameter is a device
            device_param = child # store device parameter
            device_type = child.child("Device type").value() # store device type
            device_id = child.child("DevID").value() # store device ID
            device_port = child.child("COM port") # store COM port parameter
            connection = device_param.child('Connection').value() # store connection class

            # connect serial number change to reset_device_filenames function
            device_param.child("Serial number").sigValueChanged.connect(lambda: self.data_logger.reset_device_filenames(device_id))
            # connect device nickname change to reset_device_filenames function
            device_param.child("Device nickname").sigValueChanged.connect(lambda: self.data_logger.reset_device_filenames(device_id))
            # connect device nickname change to rename_tab function
            device_param.child("Device nickname").sigValueChanged.connect(lambda: self.rename_tab(device_param))
            # connect device serial number change to rename_device function
            device_param.child("Serial number").sigValueChanged.connect(lambda: self.rename_device(device_param))
            # connect device serial number change to reset_device_filenames function
            device_param.child("Serial number").sigValueChanged.connect(lambda: self.data_logger.reset_device_filenames(device_id))
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
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: command_entered(device_id, device_param, self.data_holder.device_widgets, self.data_holder.latest_command))
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
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: command_entered(device_id, device_param, self.data_holder.device_widgets, self.data_holder.latest_command))
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
            self.data_holder.init_plot_data_for_device(device_id, device_type)
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
