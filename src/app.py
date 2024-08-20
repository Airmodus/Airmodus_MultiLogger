from datetime import datetime as dt
from time import time, sleep
import os
import locale
import platform
import logging
import random
import traceback
import json

from numpy import full, nan, array, polyval, array_equal, isnan
from serial import Serial
from serial.tools import list_ports
from PyQt5.QtGui import QPalette, QColor, QIntValidator, QDoubleValidator, QFont, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QLocale
from PyQt5.QtWidgets import (QMainWindow, QSplitter, QApplication, QTabWidget, QGridLayout, QLabel, QWidget,
    QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox, QTextEdit, QSizePolicy,
    QFileDialog)
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, PlotCurveItem, LegendItem, PlotItem
from pyqtgraph.parametertree import Parameter, ParameterTree, parameterTypes

# current version number displayed in the GUI (Major.Minor.Patch or Breaking.Feature.Fix)
version_number = "0.6.0"

# Define instrument types
CPC = 1
PSM = 2
Electrometer = 3
CO2_sensor = 4
RHTP = 5
eDiluter = 6
PSM2 = 7
TSI_CPC = 8
AFM = 9
Example_device = -1

# Set the LC_ALL environment variable to US English (en_US)
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# set up logging
logging.basicConfig(filename='debug.log', encoding='UTF-8', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

# assign file path to a variable
file_path = os.path.dirname(__file__)
main_path = os.path.dirname(file_path)

# check if platform is OSX
if platform.system() == "Darwin":
    # OSX mode makes code compatible with OSX
    osx_mode = 1
else:
    osx_mode = 0

class SerialDeviceConnection():
    def __init__(self):
        self.serial_port = "NaN"
        self.timeout = 0.2
        self.baud_rate = 115200
        # store comport name currently in use
        self.port_in_use = "NaN"
        
    def set_port(self, serial_port):
        self.serial_port = serial_port
    
    def set_baud_rate(self, baud_rate):
        self.baud_rate = baud_rate
    
    # open serial connection
    def connect(self):
        try: # Try to close with the port that was last used (needed if the port has been changed)
            self.connection.close()
        except: # if fails (i.e. port has not been open) continue normally
            pass
        self.connection = Serial(self.serial_port, self.baud_rate, timeout=self.timeout) #, rtscts=True)
        self.port_in_use = self.serial_port
        print("Connected to %s" % self.serial_port)
    
    # close serial connection
    def close(self):
        # if connection exist, it is closed
        try:
            # Try to close with the port that was last used (needed if the port has been changed)
            self.connection.close()
            #print("Connection closed")
        except:
            pass
    
    def send_message(self, message):
        # add line termination and convert to bytes
        message = bytes((str(message)+'\r\n'), 'utf-8')
        try:
            # send message if connection exists
            self.connection.write(message)
        except AttributeError:
            # print message if connection does not exist
            print("send_message - no connection, message -", message)
    
    def send_multiple_messages(self, device_type, ten_hz=False):

        if device_type == 1: # CPC
            self.send_message(":MEAS:ALL")
            QTimer.singleShot(100, lambda: self.send_message(":SYST:PRNT"))
            QTimer.singleShot(200, lambda: self.send_message(":SYST:PALL"))
            if ten_hz:
                QTimer.singleShot(300, lambda: self.send_message(":MEAS:OPC_CONC_LOG"))
        
        elif device_type == TSI_CPC: # TSI CPC
            self.send_message("RD") # read concentration
            QTimer.singleShot(100, lambda: self.send_message("RIE")) # read instrument errors
    
    # --- CPC & PSM set/command functions ---

    # # send set message
    def send_set(self, message):
        if message == None:
            # if message is None, do nothing
            return
        else:
            # send message
            self.send_message(message)
    
    # add value to set message
    def send_set_val(self, value, message, **kwargs):
        if isinstance(value, float): # if value is float, round to 2 or x decimals
            if kwargs: # if kwargs is not empty
                value = round(value, kwargs['decimals']) # round value to kwargs['decimals'] decimals
            else: # otherwise, round to 2 decimals
                value = round(value, 2)
        message = message + str(value) # add value to message
        #print("send_set_val -", message) # print message for debugging
        self.send_set(message) # send message using send_message()
    
    # --- parameter saving ---

    def to_dict(self):
        return {
            'serial_port': self.serial_port,
            'timeout': self.timeout,
            'port_in_use': self.port_in_use,
            #'port_list': self.port_list
        }
    
    def from_dict(self, data):
        self.serial_port = data.get('serial_port', "NaN")
        self.timeout = data.get('timeout', 1)
        self.port_in_use = data.get('port_in_use', "NaN")
        #self.port_list = data.get('port_list', [])

# ScalableGroup for creating a menu where to set up new COM devices
class ScalableGroup(parameterTypes.GroupParameter):
    def __init__(self, **opts):
        #opts['type'] = 'action'
        opts['addText'] = "Add new device"
        # opts for choosing device type when adding new device
        opts["addList"] = ["CPC", "PSM Retrofit", "PSM 2.0", "Electrometer", "CO2 sensor", "RHTP", "AFM", "TSI CPC", "Example device"] #  "eDiluter",
        parameterTypes.GroupParameter.__init__(self, **opts)
        self.n_devices = 0
        self.cpc_dict = {'None': 'None'}
        # update cpc_dict when device is removed
        self.sigChildRemoved.connect(self.update_cpc_dict)

    def addNew(self, device_name): # device_name is the name of the added device type
        # device_value is used to set the default value for the Device type parameter below
        device_value = {"CPC": CPC, "PSM Retrofit": PSM, "PSM 2.0": PSM2, "Electrometer": Electrometer, "CO2 sensor": CO2_sensor, "RHTP": RHTP, "AFM": AFM, "eDiluter": eDiluter, "TSI CPC": TSI_CPC, "Example device": -1}[device_name]
        # if OSX mode is on, set COM port type as string to allow complex port addresses
        if osx_mode:
            port_type = 'str'
        else:
            port_type = 'int'
        # New types of devices should be added in the "Device type" list and given unique id number
        self.addChild({'name': device_name + " (ID %d)" % (self.n_devices), 'removable': True, 'type': 'group', 'children': [
                dict(name="Device name", type='str', value=device_name+" (ID %d)" % (self.n_devices), renamable=True),
                dict(name="COM port", type=port_type),
                dict(name="Serial number", type='str', value="", readonly=True),
                #dict(name="Baud rate", type='int', value=115200, visible=False),
                dict(name = "Connection", value = SerialDeviceConnection(), visible=False),
                {'name': 'Device type', 'type': 'list', 'values': {"CPC": CPC, "PSM Retrofit": PSM, "PSM 2.0": PSM2, "Electrometer": Electrometer, "CO2 sensor": CO2_sensor, "RHTP": RHTP, "AFM": AFM, "eDiluter": eDiluter, "TSI CPC": TSI_CPC, "Example device": -1}, 'value': device_value, 'readonly': True, 'visible': False},
                dict(name = "Connected", type='bool', value=False, readonly = True),
                dict(name = "DevID", type='int', value=self.n_devices,readonly = True, visible = False),
                dict(name = "Plot to main", type='bool', value=True),
                ]})
        
        self.n_devices += 1 # increase device counter

        # if added device is CPC, update cpc_dict
        if device_value in [CPC, TSI_CPC]:
            self.update_cpc_dict()
            # if Airmodus CPC, add hidden 10 hz parameter
            # when 10 hz is True, OPC concentration is polled
            if device_value == CPC:
                self.children()[-1].addChild({'name': '10 hz', 'type': 'bool', 'value': False, 'readonly': True, 'visible': True}) # TODO set visible to False after testing

        # if added device is PSM, add hidden parameters and option for 'Connected CPC'
        if device_value in [PSM, PSM2]:
            # if device is PSM Retrofit, add hidden CO flow parameter
            if device_value == PSM:
                self.children()[-1].addChild({'name': 'CO flow', 'type': 'str', 'visible': False})
            # add hidden 10 hz parameter for storing 10 hz status for startup
            self.children()[-1].addChild({'name': '10 hz', 'type': 'bool', 'value': False, 'readonly': True, 'visible': True}) # TODO set visible to False after testing
            # add options for connected CPC
            self.children()[-1].addChild({'name': 'Connected CPC', 'type': 'list', 'values': self.cpc_dict, 'value': 'None'})
            # add cpc_changed flag to device
            self.children()[-1].cpc_changed = False
            # connect value change signal of Connected CPC to update_cpc_changed slot
            self.children()[-1].child('Connected CPC').sigValueChanged.connect(self.update_cpc_changed)
        
        # if added device is RHTP, add options for plotted value
        if device_value == RHTP:
            # remove default Plot to main parameter
            self.children()[-1].removeChild(self.children()[-1].child('Plot to main'))
            # create new Plot to main parameter with options for plotted value
            self.children()[-1].addChild({'name': 'Plot to main', 'type': 'list', 'values': [None, 'RH', 'T', 'P'], 'value': 'RH'})
        
        # if added device is AFM, add options for plotted value
        if device_value == AFM:
            # remove default Plot to main parameter
            self.children()[-1].removeChild(self.children()[-1].child('Plot to main'))
            # create new Plot to main parameter with options for plotted value
            self.children()[-1].addChild({'name': 'Plot to main', 'type': 'list', 'values': [None, 'Flow', 'Standard flow', 'RH', 'T', 'P'], 'value': 'Flow'})

    def update_cpc_dict(self):
        self.cpc_dict = {'None': 'None'} # reset cpc_dict
        # add device name to cpc_dict if device is CPC
        for device in self.children():
            if device.child('Device type').value() in [CPC, TSI_CPC]:
                self.cpc_dict[device.name()] = device.child('DevID').value()
        # update Connected CPC parameter for all PSM devices
        for device in self.children():
            if device.child('Device type').value() in [PSM, PSM2]:
                # store current value (ID) of Connected CPC parameter
                current_cpc = device.child('Connected CPC').value()
                # remove Connected CPC parameter
                device.removeChild(device.child('Connected CPC'))
                # add updated Connected CPC parameter
                device.addChild({'name': 'Connected CPC', 'type': 'list', 'values': self.cpc_dict})
                # set Connected CPC parameter to previous value if it is still in the list
                if current_cpc in self.cpc_dict.values():
                    device.child('Connected CPC').setValue(current_cpc)
                else: # else set cpc_changed to True
                    device.cpc_changed = True
                # connect value change signal of Connected CPC to update_cpc_changed slot
                device.child('Connected CPC').sigValueChanged.connect(self.update_cpc_changed)

    # slot for setting cpc_changed flag to True when Connected CPC parameter is changed
    def update_cpc_changed(self, value):
        device = value.parent() # get device parameter
        device.cpc_changed = True # set cpc_changed flag to True

# Create a dictionary, in which the names, types and default values are set
params = [
    {'name': 'Measurement status', 'type': 'group', 'children': [
        {'name': 'Data settings', 'type': 'group', 'children': [
            {'name': 'File path', 'type': 'str', 'value': main_path},
            {'name': 'File tag', 'type': 'str', 'value': "", 'tip': "Datafile format: YYYYMMDD_HHMMSS_(Serial number)_(Device name)_(File tag).dat"},
            {'name': 'Save data', 'type': 'bool', 'value': False},
            {'name': 'Generate daily files', 'type': 'bool', 'value': True, 'tip': "If on, new files are started at midnight."},
            {'name': 'Resume on startup', 'type': 'bool', 'value': False, 'tip': "Option to resume the last settings on startup."},
            {'name': 'Save settings', 'type': 'action'},
            {'name': 'Load settings', 'type': 'action'},
        ]},
        {'name': 'COM settings', 'type': 'group', 'children': [
            {'name': 'Available ports', 'type': 'text', 'value': '', 'readonly': True},
            {'name': 'Update port list', 'type': 'action'},
        ]}
    ]},
    {'name': 'Plot settings', 'type': 'group', 'children': [
        {'name': 'Follow', 'type': 'bool', 'value': True},
        {'name': 'Time window (s)', 'type': 'int', 'value': 60},
        {'name': 'Autoscale Y', 'type': 'bool', 'value': True}
    ]},
    ScalableGroup(name="Device settings", children=[
        # devices will be added here
    ]),
]

# Create tree of Parameter objects
p = Parameter.create(name='params', type='group', children=params)

## COM PORT CHANGING - This structure detects any changes in the parameter tree
# and should close the old serial port and open a new one if com port addresses have changed
# TODO move to SerialDeviceConnection class, connect COM port change in device_added
def COMchange(param, changes):
    for param, change, data in changes:
        path = p.childPath(param) # get path of the changed parameter
        if path is not None: # if path exists, join it to a string
            childName = '.'.join(path)
        else: # if path does not exist, use the name of the parameter
            childName = param.name()
        if 'COM port' in childName:
            names = childName.split('.') # split the name into a list
            try: # Close the old connection if open
                if p.child(names[0]).child(names[1]).child('Connection').value().connection.is_open == True:
                    p.child(names[0]).child(names[1]).child('Connection').value().close()
            except:
                pass
            finally: # try to set connection settings and connect
                try:
                    if osx_mode:
                        p.child(names[0]).child(names[1]).child('Connection').value().set_port(str(data))
                    else:
                        p.child(names[0]).child(names[1]).child('Connection').value().set_port('COM'+str(data))
                    p.child(names[0]).child(names[1]).child('Connection').value().connect()
                except Exception as e: # print exception if opening fails
                    #print("COMchange - error:", e)
                    pass

# connect changes in the parameter tree to the COM change function
p.sigTreeStateChanged.connect(COMchange)

# main program
class MainWindow(QMainWindow):

    def __init__(self, params=p, parent=None):
        super().__init__() # super init function must be called when subclassing a Qt class
        self.setWindowTitle("Airmodus MultiLogger v. " + version_number) # set window title
        self.timer = QTimer(timerType=Qt.PreciseTimer) # create timer object
        self.params = params # predefined parameter tree
        self.config_file_path = "" # path to the configuration file
        # create parameter tree
        t = ParameterTree()
        t.setParameters(p, showTop=False)
        t.setHeaderHidden(True)
        # x axis time attributes
        self.time_counter = 0 # used as index value, incremented every second
        self.x_time_list = full(10, nan) # 60 # list for saving x-axis time values
        self.max_time = 604800 # maximum time value in seconds
        self.max_reached = False # flag for checking if max_time has been reached
        self.first_connection = 0 # once first connection has been made, set to 1
        self.inquiry_flag = False # when COM ports change, this is set to True to inquire device IDNs

        # load CSS style and apply it to the main window
        with open(file_path + "/style.css", "r") as f:
            self.style = f.read()
        self.setStyleSheet(self.style)

        # create error icon object
        self.error_icon = QIcon(main_path + "/res/icons/error.png")

        # initialize dictionaries and lists
        # data related
        self.latest_data = {} # contains latest values
        self.latest_settings = {} # contains latest CPC and PSM settings
        self.latest_psm_prnt = {} # contains latest PSM prnt values
        self.latest_poly_correction = {} # contains latest polynomial correction values from PSM
        self.latest_command = {} # contains latest user entered command message
        self.latest_ten_hz = {} # contains latest 10 hz OPC concentration log values
        self.extra_data = {} # contains extra data, used when multiple data prints are received at once
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
        # flags
        self.par_updates = {} # contains .par update flags: 1 = update, 0 = no update
        self.psm_settings_updates = {} # contains PSM settings update flags: 1 = update, 0 = no update
        self.device_errors = {} # contains device error flags: 0 = ok, 1 = errors

        # initialize GUI
        # create and set central widget (requirement of QMainWindow)
        self.main_splitter = QSplitter()
        self.setCentralWidget(self.main_splitter)
        # create status lights widget instance showing measurement and saving status
        self.status_lights = StatusLights()
        # create logo pixmap label
        self.logo = QLabel(alignment=Qt.AlignCenter)
        pixmap = QPixmap(main_path + "/res/images/logo.png")
        self.logo.setPixmap(pixmap.scaled(400, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        # create left side vertical splitter
        # contains parameter tree and status widget
        left_splitter = QSplitter(Qt.Vertical) # split vertically
        left_splitter.addWidget(self.logo) # add logo
        left_splitter.addWidget(t) # add parameter tree widget
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

        # connect signals to functions
        # connect timer timeout to timer_functions
        self.timer.timeout.connect(self.timer_functions)
        # connect parameter tree's save data parameter
        self.params.child('Measurement status').child('Data settings').child('Save data').sigValueChanged.connect(self.save_changed)
        # connect file path parameter to filepath_changed function
        self.params.child('Measurement status').child('Data settings').child('File path').sigValueChanged.connect(self.filepath_changed)
        # connect file tag parameter to reset_filenames function
        self.params.child('Measurement status').child('Data settings').child('File tag').sigValueChanged.connect(self.reset_filenames)
        # connect com port update button
        self.params.child('Measurement status').child('COM settings').child('Update port list').sigActivated.connect(self.set_inquiry_flag)

        # connect parameter tree's sigChildAdded signal to device_added function
        p.child("Device settings").sigChildAdded.connect(self.device_added)
        # connect parameter tree's sigChildRemoved signal to device_removed function
        p.child("Device settings").sigChildRemoved.connect(self.device_removed)
        # connect main_plot's viewboxes' sigXRangeChanged signals to x_range_changed function
        for viewbox in self.main_plot.viewboxes.values():
            viewbox.sigXRangeChanged.connect(self.x_range_changed)

        # list com ports at startup
        self.list_com_ports()

        # start timer
        self.startTimer()

        # connect parameter tree's sigTreeStateChanged signal to save_ini function
        self.params.sigTreeStateChanged.connect(self.save_ini)
        # connect 'Save settings' and 'Load settings' buttons
        self.params.child('Measurement status').child('Data settings').child('Save settings').sigActivated.connect(self.manual_save_configuration)
        self.params.child('Measurement status').child('Data settings').child('Load settings').sigActivated.connect(self.manual_load_configuration)
        # load ini file if available
        self.load_ini()

        # end of __init__ function

    # timer timeout launches this chain of functions
    def timer_functions(self):
        # TODO rename functions to something more descriptive, explain phases with comments
        self.current_time = round(time()) # get current time and round it to nearest second
        # initialize error status light flag
        self.error_status = 0 # 0 = ok, 1 = errors
        # initialize saving status flag, set to 0 in write_data function if saving not on or fails
        self.saving_status = 1 # 0 = not saving, 1 = saving
        # set all device errors to False, individually set to True when errors encountered
        self.device_errors = {key: False for key in self.device_errors}
        self.connection_test() # check if devices are connected
        if self.first_connection: # if first connection has been made
            self.get_dev_data() # send read commands to connected serial devices
            # launch delayed_functions after specified ms (orig. 350 ms)
            QTimer.singleShot(500, self.delayed_functions) # changed from 400 to 500

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
        if self.time_counter < self.max_time - 1: # if time counter has not reached max_time - 1
            self.time_counter += 1 # increment time counter
        else: # if time counter has reached max_time - 1 (max index)
            self.max_reached = True # set max_reached flag to True
        # convert current_time to datetime object
        current_datetime = dt.fromtimestamp(self.current_time)
        # restart timer daily (at 23:59:59) to prevent drifting over time
        if current_datetime.hour == 23 and current_datetime.minute == 59 and current_datetime.second == 59:
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
            
            finally: # set the connection state according to connected value
                dev.child('Connected').setValue(connected) # "Connected" parameter
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
                        if device_type == CPC and dev.child('10 hz').value() == True:
                            dev.child('Connection').value().send_multiple_messages(device_type, ten_hz=True)
                        else:
                            dev.child('Connection').value().send_multiple_messages(device_type)

                    elif device_type in [PSM, PSM2]: # PSM
                        # if settings update flag is True, fetch set points from PSM and update GUI
                        if self.psm_settings_updates[dev.child('DevID').value()] == True:
                            # send message to device to get settings
                            dev.child('Connection').value().send_message(":SYST:PRNT")

                    elif device_type == Electrometer: # Electrometer
                        dev.child('Connection').value().connection.reset_input_buffer()
                        dev.child('Connection').value().connection.reset_output_buffer()
                        dev.child('Connection').value().connection.read_all()
                        dev.child('Connection').value().send_message(":MEAS:V")

                    elif device_type == CO2_sensor: # CO2 sensor
                        dev.child('Connection').value().connection.reset_input_buffer()
                        dev.child('Connection').value().connection.reset_output_buffer()
                        dev.child('Connection').value().connection.read_all()
                        # send measure command to device
                        dev.child('Connection').value().send_message(":MEAS:CO2")
                    
                    # RHTP, eDiluter and AFM push data automatically

                    if device_type in [CPC, PSM, PSM2, CO2_sensor, RHTP, AFM]: # CPC, PSM, CO2, RHTP, AFM
                        # if Serial number is empty, send IDN inquiry with delay
                        if dev.child('Serial number').value() == "":
                            QTimer.singleShot(300, lambda: dev.child('Connection').value().connection.write(b'*IDN?\n'))
                        
                except Exception as e:
                    print(traceback.format_exc())
                    logging.exception(e)
    
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
                        self.latest_data[dev_id] = full(14, nan)
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

                                # update widget error colors and store total errors
                                total_errors = self.device_widgets[dev_id].update_errors(status_hex)
                                
                                # set error_status flag if total errors is not 0
                                if total_errors != 0:
                                    self.error_status = 1
                                    # set device error flag
                                    self.set_device_error(dev_id, True)

                                meas_list = list(map(float,data[:-1])) # convert to float without status hex
                                # compile data list
                                # if latest_data is nan, store data normally
                                if isnan(self.latest_data[dev_id][0]):
                                    self.latest_data[dev_id] = self.compile_cpc_data(meas_list, status_hex, total_errors)
                                else: # if not nan, store data to extra_data dictionary
                                    self.extra_data[dev_id] = self.compile_cpc_data(meas_list, status_hex, total_errors)

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
                                print("OPC_CONC_LOG", data) # TODO remove after testing
                                del data[0] # remove first item (timestamp)
                                # if latest_ten_hz is nan, store data normally
                                if isnan(self.latest_ten_hz[dev_id][0]):
                                    self.latest_ten_hz[dev_id] = data
                                else: # if not nan, store data to extra_data dictionary
                                    self.extra_data[str(dev_id)+":10hz"] = data
                            
                            elif command == ":STAT:SELF:LOG":
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                # TODO make sure largest error index in firmware is 28
                                status_bin = bin(int(data[0], 16)) # convert hex to int and int to binary
                                status_bin = status_bin[2:].zfill(28) # remove 0b from string and fill with 0s to make 28 digits
                                # print self test error binary
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error binary: " + status_bin)
                                # print error indices
                                for i in range(28): # loop through binary digits
                                    bit_index = 27 - i # this should match the indices or errors in manual
                                    if status_bin[i] == "1":
                                        self.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error bit index: " + str(bit_index))
                            
                            elif command == "*IDN":
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                serial_number = data[0]
                                serial_number = serial_number.strip("\n")
                                serial_number = serial_number.strip("\r")
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)

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
                    
                    # update settings if settings are valid
                    if settings_update == True: # if settings are valid, not nan
                        
                        # if device doesn't yet exist in latest_settings dictionary, add as nan list
                        if dev_id not in self.latest_settings:
                            self.latest_settings[dev_id] = full(13, nan)
                        
                        # get previous settings form latest_settings dictionary
                        previous_settings = self.latest_settings[dev_id]
                        # compile settings list
                        settings = self.compile_cpc_settings(prnt_list, pall_list)

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
                    
                    # if device doesn't yet exist in latest_data dictionary, add as nan list
                    if dev_id not in self.latest_data:
                        self.latest_data[dev_id] = full(31, nan)

                    # clear par update flag
                    self.par_updates[dev_id] = 0

                    # set settings_fetched flag to False
                    # flag is set to True when settings are successfully fetched
                    settings_fetched = False

                    try: # try to read data, decode and split
                        #print("inWaiting():", dev.child('Connection').value().connection.inWaiting())
                        readings = dev.child('Connection').value().connection.read_all()
                        # decode, separate messages and remove last empty message
                        readings = readings.decode().split("\r")[:-1]
                        #print("PSM messages:", readings)
                        
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
                                # update widget liquid states with note hex, get liquid sets in return
                                liquid_sets = self.device_widgets[dev_id].update_notes(note_hex)
                                # store polynomial correction value as float to dictionary
                                self.latest_poly_correction[dev_id] = float(data[14])
                                
                                # compile and store psm data to latest data dictionary with device id as key
                                if dev.child('Device type').value() == PSM: # PSM
                                    self.latest_data[dev_id] = self.compile_psm_data(data, status_hex, note_hex, psm_version=1)
                                elif dev.child('Device type').value() == PSM2: # PSM2
                                    self.latest_data[dev_id] = self.compile_psm_data(data, status_hex, note_hex, psm_version=2)
                            
                            elif command == ":SYST:PRNT":
                                # update GUI set points
                                self.device_widgets[dev_id].update_settings(data)
                                # store settings to latest PSM prnt dictionary with device id as key
                                self.latest_psm_prnt[dev_id] = data
                                # print settings to command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                # set settings_fetched flag to True
                                settings_fetched = True
                            
                            elif command == "*IDN":
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                serial_number = data[0]
                                serial_number = serial_number.strip("\n")
                                serial_number = serial_number.strip("\r")
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)
                            
                            else: # print other messages to command widget text box
                                self.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)

                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.latest_data[dev_id] = full(31, nan) # TODO determine amount of data items
                        logging.exception(e)
                        # update widget error colors
                        self.device_widgets[dev_id].measure_tab.scan.change_color(0)
                        self.device_widgets[dev_id].measure_tab.step.change_color(0)
                        self.device_widgets[dev_id].measure_tab.fixed.change_color(0)
                    
                    # compile settings list if update flag is True and settings_fetched is True
                    if self.psm_settings_updates[dev_id] == True and settings_fetched == True:
                        try:
                            if dev.child('Device type').value() == PSM:
                                # get CO flow rate from PSM widget
                                co_flow = round(self.device_widgets[dev_id].set_tab.set_co_flow.value_spinbox.value(), 3)
                                psm_version = 1
                            elif dev.child('Device type').value() == PSM2:
                                # set nan as placeholder
                                co_flow = "nan"
                                psm_version = 2
                            # compile settings with latest PSM prnt settings and CO flow rate
                            settings = self.compile_psm_settings(self.latest_psm_prnt[dev_id], co_flow, psm_version)
                            # store settings to latest settings dictionary with device id as key
                            self.latest_settings[dev_id] = settings
                            # add par update flag
                            self.par_updates[dev_id] = 1
                            # remove update settings flag once settings have been updated and compiled
                            self.psm_settings_updates[dev_id] = False
                        except Exception as e:
                            print(traceback.format_exc())
                            logging.exception(e)
                
                if dev.child('Device type').value() == Electrometer: # Electrometer
                    try: # try to read data, decode, split and convert to float
                        readings = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                        readings = list(map(float,readings.split(";")))
                        # store to latest_data dictionary with device id as key
                        self.latest_data[dev_id] = readings
                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.latest_data[dev_id] = full(3, nan)
                        logging.exception(e)

                if dev.child('Device type').value() == CO2_sensor: # CO2 sensor TODO make CO2 process similar to RHTP?
                    try:
                        # if Serial number is empty, look for *IDN
                        if dev.child('Serial number').value() == "":
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
                                        dev.child('Serial number').setValue(serial_number) # set serial number to parameter tree
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
                        # if Serial number is empty, look for *IDN
                        if dev.child('Serial number').value() == "":
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
                                        dev.child('Serial number').setValue(serial_number) # set serial number to parameter tree
                            # store nan values to latest_data
                            self.latest_data[dev_id] = full(3, nan)
                        
                        # if Serial number has been acquired, read data normally
                        else:
                            # read and decode a line of data
                            readings = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                            # remove '\r\n' from end
                            readings = readings[:-2]
                            # split data to list
                            readings = readings.split(", ")

                            # check if there's an extra line's worth of data in buffer
                            # TODO when extra lines occur, store them for next round using a dictionary, e.g. self.extra_data[dev.child('DevID').value()] = extra_line
                            # - create check before first reading above: is there extra data stored in dictionary? if yes, use it and remove from dictionary
                            # - consider valid data length in various scenarios: is it always the same (22)?
                            # - create similar system for PSM data reading?
                            if dev.child('Connection').value().connection.inWaiting() >= 22:
                                buffer_length = dev.child('Connection').value().connection.inWaiting()
                                try: # try to read next line
                                    extra_line = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                                    # create log entry
                                    logging.warning("readIndata - RHTP buffer: %i - RHTP extra line: %s", buffer_length, extra_line)
                                    #print("readIndata - RHTP buffer:", buffer_length, "- RHTP extra line:", extra_line)
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)

                            # check if data is valid and store to latest_data dictionary
                            if float(readings[0]) != 0: # if data is valid, not 0
                                # store data to latest_data
                                self.latest_data[dev_id] = readings
                            else: # if data is not valid, 0
                                # store nan values to latest_data
                                self.latest_data[dev_id] = full(3, nan)

                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.latest_data[dev_id] = full(3, nan)
                        logging.exception(e)
                
                if dev.child('Device type').value() == AFM: # AFM
                    try:
                        # if Serial number is empty, look for *IDN
                        if dev.child('Serial number').value() == "":
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
                                        dev.child('Serial number').setValue(serial_number)
                            # store nan values to latest_data
                            self.latest_data[dev_id] = full(5, nan)
                        
                        # if Serial number has been acquired, read data normally
                        else:
                            # read and decode a line of data
                            readings = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                            # remove '\r\n' from end
                            readings = readings[:-2]
                            # split data to list
                            readings = readings.split(", ")

                            # check if there's an extra line's worth of data in buffer
                            # this is done in case data cumulates slowly over time in buffer
                            if dev.child('Connection').value().connection.inWaiting() >= 38: # 34 + 2 (\r\n) + 2 (if flow >= 10)
                                buffer_length = dev.child('Connection').value().connection.inWaiting()
                                # create log entry
                                logging.warning("readIndata - AFM buffer: %i", buffer_length)
                                print("readIndata - AFM extra data buffer:", buffer_length)
                                try: # try to read next line
                                    extra_line = dev.child('Connection').value().connection.read_until(b'\r\n').decode()
                                    # use extra line as readings
                                    readings = extra_line[:-2].split(", ") # remove '\r\n' and split data to list
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                            
                            #print("AFM readings:", readings)

                            # check if data is valid and store to latest_data dictionary
                            if float(readings[2]) != 0: # if RH data is valid, not 0
                                self.latest_data[dev_id] = readings
                            else:
                                self.latest_data[dev_id] = full(5, nan)
                    
                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.latest_data[dev_id] = full(5, nan)
                        logging.exception(e)
                
                if dev.child('Device type').value() == eDiluter: # eDiluter
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

                    # if connected CPC is not 'None'
                    if cpc_id != 'None':
                        
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
                                vacuum_flow = float(self.latest_data[psm_id][14])
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
                                    cpc_data[10], cpc_data[3], cpc_data[2],# liquid level, pulses, pulse duration
                                    cpc_data[12], cpc_data[13] # number of errors, system status (hex)
                                ]
                                # replace PSM's latest_data CPC placeholders with connected CPC data
                                if dev.child('Device type').value() == PSM:
                                    # PSM: index 16-29 (no vacuum flow)
                                    self.latest_data[psm_id][16:30] = connected_cpc_data
                                elif dev.child('Device type').value() == PSM2:
                                    # PSM: index 17-30 (with vacuum flow)
                                    self.latest_data[psm_id][17:31] = connected_cpc_data
            
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

        # ----- update plot data -----

        # TODO create function for array doubling/shifting to avoid repetition
        # if time_counter has reached max_time - 1 (max index), start shifting data
        if self.time_counter >= self.max_time - 1:
            # if max has been reached, shift all items one index to left
            if self.max_reached == True:
                self.x_time_list = self.x_time_list[:self.max_time] # shorten list to max time length
                self.x_time_list[:-1] = self.x_time_list[1:] # shift all items one index to left
                self.x_time_list[-1] = nan # change nan to end
        # if max_time hasn't been reached, double time array size when full (when time_counter reaches array length)
        elif self.time_counter >= self.x_time_list.shape[0]:
            tmp_time = self.x_time_list
            self.x_time_list = full(self.x_time_list.shape[0] * 2, nan)
            self.x_time_list[:tmp_time.shape[0]] = tmp_time
        # add current time to x time list
        self.x_time_list[self.time_counter] = self.current_time
        
        # go through each device
        for dev in self.params.child('Device settings').children():
            # store device id to variable for clarity
            dev_id = dev.child('DevID').value()

            try: # if one device fails, continue with the next one

                # Devices with multiple values - create lists for each value
                if dev.child('Device type').value() in [CPC, TSI_CPC, Electrometer, RHTP, AFM]:
                    # determine value types based on device type
                    if dev.child('Device type').value() in [CPC, TSI_CPC]:
                        types = ['', ':raw'] # concentration, raw concentration
                    elif dev.child('Device type').value() == Electrometer:
                        types = [':1', ':2', ':3'] # voltage 1, voltage 2, voltage 3
                    elif dev.child('Device type').value() == RHTP:
                        types = [':rh', ':t', ':p'] # RH, T, P
                    elif dev.child('Device type').value() == AFM:
                        types = [':f', ':sf', ':rh', ':t', ':p'] # flow, standard flow, RH, T, P
                    
                    # if device is not yet in plot_data dict, add it
                    if str(dev_id)+types[0] not in self.plot_data:
                        # make the new lists the same size as x_time_list
                        for i in types:
                            self.plot_data[str(dev_id)+i] = full(len(self.x_time_list), nan)
                    # if time_counter has reached max_time - 1, start shifting data
                    if self.time_counter >= self.max_time - 1:
                        for i in types:
                            if self.max_reached == True:
                                self.plot_data[str(dev_id)+i] = self.plot_data[str(dev_id)+i][:self.max_time] # shorten list to max time length
                                self.plot_data[str(dev_id)+i][:-1] = self.plot_data[str(dev_id)+i][1:] # shift all items one index to left
                                self.plot_data[str(dev_id)+i][-1] = nan # change nan to end
                    # if max_time hasn't been reached, double device plot array sizes when full
                    elif self.time_counter >= self.plot_data[str(dev_id)+types[0]].shape[0]:
                        for i in types:
                            tmp_data = self.plot_data[str(dev_id)+i]
                            self.plot_data[str(dev_id)+i] = full(self.plot_data[str(dev_id)+i].shape[0] * 2, nan)
                            self.plot_data[str(dev_id)+i][:tmp_data.shape[0]] = tmp_data
                
                # other devices
                else:
                    # if device is not yet in plot_data dict, add it
                    if dev_id not in self.plot_data:
                        # make the new list the same size as x_time_list
                        self.plot_data[dev_id] = full(len(self.x_time_list), nan)
                    # if time_counter has reached max_time - 1, start shifting data
                    if self.time_counter >= self.max_time - 1:
                        if self.max_reached == True:
                            self.plot_data[dev_id] = self.plot_data[dev_id][:self.max_time] # shorten list to max time length
                            self.plot_data[dev_id][:-1] = self.plot_data[dev_id][1:] # # shift all items one index to left
                            self.plot_data[dev_id][-1] = nan # change nan to end
                    # if max_time hasn't been reached, double device plot array size when full
                    elif self.time_counter >= self.plot_data[dev_id].shape[0]:
                        tmp_data = self.plot_data[dev_id]
                        self.plot_data[dev_id] = full(self.plot_data[dev_id].shape[0] * 2, nan)
                        self.plot_data[dev_id][:tmp_data.shape[0]] = tmp_data
                
                # if device is connected, add latest_values data to plot_data according to device
                if dev.child('Connected').value():
                    if dev.child('Device type').value() in [CPC, TSI_CPC]: # CPC
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
                    elif dev.child('Device type').value() in [PSM, PSM2]: # PSM
                        # add latest saturator flow rate value to time_counter index of plot_data
                        self.plot_data[dev_id][self.time_counter] = self.latest_data[dev_id][2]
                    elif dev.child('Device type').value() == Electrometer: # Electrometer
                        # add latest voltage values to time_counter index of plot_data
                        self.plot_data[str(dev_id)+':1'][self.time_counter] = self.latest_data[dev_id][0]
                        self.plot_data[str(dev_id)+':2'][self.time_counter] = self.latest_data[dev_id][1]
                        self.plot_data[str(dev_id)+':3'][self.time_counter] = self.latest_data[dev_id][2]
                    elif dev.child('Device type').value() == CO2_sensor: # CO2 sensor
                        # add latest CO2 value to time_counter index of plot_data
                        self.plot_data[dev_id][self.time_counter] = self.latest_data[dev_id][0]
                    elif dev.child('Device type').value() == RHTP: # RHTP
                        # add latest values (RH, T, P) to time_counter index of plot_data
                        self.plot_data[str(dev_id)+':rh'][self.time_counter] = self.latest_data[dev_id][0]
                        self.plot_data[str(dev_id)+':t'][self.time_counter] = self.latest_data[dev_id][1]
                        self.plot_data[str(dev_id)+':p'][self.time_counter] = self.latest_data[dev_id][2]
                    elif dev.child('Device type').value() == AFM: # AFM
                        # add latest values (flow, RH, T, P) to time_counter index of plot_data
                        self.plot_data[str(dev_id)+':f'][self.time_counter] = self.latest_data[dev_id][0]
                        self.plot_data[str(dev_id)+':sf'][self.time_counter] = self.latest_data[dev_id][1]
                        self.plot_data[str(dev_id)+':rh'][self.time_counter] = self.latest_data[dev_id][2]
                        self.plot_data[str(dev_id)+':t'][self.time_counter] = self.latest_data[dev_id][3]
                        self.plot_data[str(dev_id)+':p'][self.time_counter] = self.latest_data[dev_id][4]
                    elif dev.child('Device type').value() == eDiluter: # eDiluter
                        # add latest T1 value to time_counter index of plot_data
                        self.plot_data[dev_id][self.time_counter] = self.latest_data[dev_id][3]
                if dev.child('Device type').value() == -1: # Example device
                    # add latest value to time_counter index of plot_data
                    self.plot_data[dev_id][self.time_counter] = round(random.random() * 100 + 150, 2)

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
                    elif dev_type == Electrometer: # Electrometer
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
                if dev.child('Connected').value() or dev_type == Example_device:
                    
                    # store current time counter value as start time in dictionary if not yet stored
                    # start time is stored when first non-nan value is received
                    # start time is used to crop plot data to only show non-nan values
                    if dev_id not in self.start_times:
                        # CPC
                        if dev_type in [CPC, TSI_CPC]:
                            if str(self.plot_data[str(dev_id)+':raw'][self.time_counter]) != "nan":
                                self.start_times[dev_id] = self.time_counter
                        # Electrometer
                        elif dev_type == Electrometer:
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
                        elif dev_type == Electrometer: # Electrometer
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
                            if dev_type == Electrometer: # if Electrometer, update all 3 plots
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
                        # if stored CPC flow is not 1, set it to 1
                        if float(self.latest_settings[dev_id][5]) != 1:
                            # send value to PSM
                            dev.child('Connection').value().send_set_val(1, ":SET:FLOW:CPC ")
                            # set PSM update flag
                            self.psm_settings_updates[dev_id] = True
                            # GUI is updated when PSM settings are fetched
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
        if self.params.child('Measurement status').child('Data settings').child('Save data').value():

            # create timestamp from current_time
            timestamp = dt.fromtimestamp(self.current_time)
            timeStampStr = str(timestamp.strftime("%Y.%m.%d %H:%M:%S"))

            # go through each device
            for dev in self.params.child('Device settings').children():

                # if device is TSI CPC, do nothing
                if dev.child('Device type').value() == TSI_CPC:
                    pass

                # if device is connected OR example device
                elif dev.child('Connected').value() or dev.child('Device type').value() == Example_device:

                    try:
                        # store device id to variable for clarity
                        dev_id = dev.child('DevID').value()

                        # if device is not yet in dat_filenames dict, create .dat file and add filename to dict
                        if dev_id not in self.dat_filenames:
                            # format timestamp for filename
                            timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
                            # get device name from device settings
                            device_name = dev.child('Device name').value()
                            # TODO format device name to remove spaces and special characters
                            # get serial number from device settings
                            serial_number = dev.child('Serial number').value()
                            # if serial number is not empty, add underscore to beginning
                            if serial_number != "":
                                serial_number = '_' + serial_number
                            # get file tag from data settings
                            file_tag = self.params.child('Measurement status').child('Data settings').child('File tag').value()
                            # if file tag is not empty, add underscore to beginning
                            if file_tag != "":
                                file_tag = '_' + file_tag
                            # compile filename and add to dat_filenames
                            if osx_mode:
                                filename = '/' + timestamp_file + serial_number + '_' + device_name + file_tag + '.dat'
                            else:
                                filename = '\\' + timestamp_file + serial_number + '_' + device_name + file_tag + '.dat'
                            self.dat_filenames[dev_id] = filename
                            with open(self.filePath + filename ,"w",encoding='UTF-8'):
                                pass
                            
                            # if CPC or PSM, create .par file and add filename to par_filenames
                            if dev.child('Device type').value() in [CPC, PSM, PSM2]:
                                if osx_mode:
                                    filename = '/' + timestamp_file + serial_number + '_' + device_name + file_tag + '.par'
                                else:
                                    filename = '\\' + timestamp_file + serial_number + '_' + device_name + file_tag + '.par'
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
                                # get device name from device settings
                                device_name = dev.child('Device name').value()
                                # get serial number from device settings
                                serial_number = dev.child('Serial number').value()
                                # if serial number is not empty, add underscore to beginning
                                if serial_number != "":
                                    serial_number = '_' + serial_number
                                # get file tag from data settings
                                file_tag = self.params.child('Measurement status').child('Data settings').child('File tag').value()
                                # if file tag is not empty, add underscore to beginning
                                if file_tag != "":
                                    file_tag = '_' + file_tag
                                # compile filename and add to ten_hz_filenames
                                if osx_mode:
                                    filename = '/' + timestamp_file + serial_number + '_' + device_name + '_10hz' + file_tag + '.csv'
                                else:
                                    filename = '\\' + timestamp_file + serial_number + '_' + device_name + '_10hz' + file_tag + '.csv'
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
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration (#/cc),Dead time (µs),Number of pulses,Saturator T (C),Condenser T (C),Optics T (C),Cabin T (C),Inlet P (kPa),Critical orifice P (kPa),Nozzle P (kPa),Liquid level,Pulse ratio,Total CPC errors,System status error')
                                elif dev.child('Device type').value() == PSM: # PSM
                                    # TODO check if PSM headers are ok
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)')
                                elif dev.child('Device type').value() == PSM2: # PSM 2.0
                                    # TODO check if correct
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),Vacuum flow (lpm),PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)')
                                elif dev.child('Device type').value() == Electrometer: # Electrometer
                                    file.write('YYYY.MM.DD hh:mm:ss,Voltage 1 (V),Voltage 2 (V),Voltage 3 (V)')
                                elif dev.child('Device type').value() == CO2_sensor: # CO2
                                    file.write('YYYY.MM.DD hh:mm:ss,CO2 (ppm),T (C),RH (%)')
                                elif dev.child('Device type').value() == RHTP: # RHTP
                                    file.write('YYYY.MM.DD hh:mm:ss,RH (%),T (C),P (Pa)')
                                elif dev.child('Device type').value() == AFM: # AFM
                                    file.write('YYYY.MM.DD hh:mm:ss,Flow (lpm),Standard flow (slpm),RH (%),T (C),P (Pa)')
                                elif dev.child('Device type').value() == eDiluter: # eDiluter
                                    file.write('YYYY.MM.DD hh:mm:ss,Status,P1,P2,T1,T2,T3,T4,T5,T6,DF1,DF2,DFTot')
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
                                        file.write('YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),CO flow rate (lpm),CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input')
                                    elif dev.child('Device type').value() == PSM2: # PSM2
                                        # TODO: check if correct
                                        file.write('YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input')
                                
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
                                                cpc_settings = self.latest_settings[cpc_id]
                                                file.write(',') # separate PSM and CPC settings with comma
                                                # compile connected CPC settings
                                                connected_cpc_settings = [
                                                    cpc_settings[6], cpc_settings[11], cpc_settings[9], # autofill, drain, water removal
                                                    cpc_settings[3], cpc_settings[4], cpc_settings[5], # T set: saturator, condenser, optics
                                                    cpc_settings[2], cpc_settings[0] # inlet flow rate (measured), aveaging time
                                                ]
                                                # write connected CPC settings
                                                write_data = ','.join(str(vals) for vals in connected_cpc_settings)
                                                file.write(write_data)
                                            
                                            else: # if CPC is not connected or not Airmodus CPC, write nan values
                                                file.write(',nan,nan,nan,nan,nan,nan,nan,nan')
                                        
                                        else: # if no connected CPC selected, write nan values
                                            file.write(',nan,nan,nan,nan,nan,nan,nan,nan')
                                        
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
    
    # triggered when saving is toggled on/off
    def save_changed(self):
        # if saving is toggled on
        if self.params.child('Measurement status').child('Data settings').child('Save data').value():
            # store start day
            self.start_day = dt.now().strftime("%m%d")
            #self.start_day = dt.now().strftime("%M") # testing with minutes
            # get file path
            self.filePath = self.params.child('Measurement status').child('Data settings').child('File path').value()
            # set file path as read only
            self.params.child('Measurement status').child('Data settings').child('File path').setReadonly(True)
        # if saving is toggled off, reset filename dictionaries
        else:
            self.reset_filenames()
            # disable read only file path
            self.params.child('Measurement status').child('Data settings').child('File path').setReadonly(False)

    def filepath_changed(self):
        # set file path
        self.filePath = self.params.child('Measurement status').child('Data settings').child('File path').value()
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

    # compile data list for CPC .dat file
    def compile_cpc_data(self, meas, status_hex, total_errors):

        # determine pulse ratio
        if str(meas[3]) == "nan":
            pulse_ratio = "nan"
        elif meas[1] == 0:
            pulse_ratio = 0
        else:
            pulse_ratio = round(meas[3]/meas[1], 2) # calculate and round to 2 decimals

        cpc_data = [ # TODO nominal flow concentration
            meas[0], meas[2], meas[1], # concentration, dead time, number of pulses during average
            meas[5], meas[7], meas[6], meas[8], # T: saturator, condenser, optics, cabin
            meas[9], meas[10], meas[11], # P: inlet, critical orifice, nozzle
            int(meas[14]), pulse_ratio, # liquid level, pulse ratio
            total_errors, status_hex # total number of errors, hexadecimal system status
            # TODO add OPC voltage level when added to firmware
        ]
        return cpc_data
    
    # compile settings list for CPC .par file
    def compile_cpc_settings(self, prnt, pall):
        cpc_settings = [
            prnt[5], pall[24], prnt[10], # averaging time, nominal inlet flow rate, measured cpc flow rate
            prnt[8], prnt[6], prnt[7], # temperature set points: saturator, condenser, optics
            int(prnt[1]), pall[26], pall[27], int(prnt[4]), # autofill, OPC counter threshold voltage, OPC counter threshold voltage 2, water removal
            prnt[12], int(prnt[2]), pall[20], pall[25] # dead time correction, drain, k-factor, tau
            # TODO add Firmware version
        ]
        return cpc_settings

    # compile data list for PSM .dat file
    def compile_psm_data(self, meas, status_hex, note_hex, psm_version):
        # psm_version: 1 = PSM, 2 = PSM 2.0

        # determine PSM status
        if int(status_hex, 16) == 0:
            psm_status = 1
        else:
            psm_status = 0
        # determine PSM note
        if int(note_hex, 16) == 0:
            psm_note = 1
        else:
            psm_note = 0

        # concentration form PSM is calculated and stored later in write_data
        # cut-off diameter is left with a "nan" placeholder for now
        psm_data = [
            "nan", "nan", meas[0], meas[1], # concentration from PSM, cut-off diameter, saturator flow rate, excess flow rate
            meas[3], meas[2], meas[4], meas[6], meas[5], meas[7], # psm saturator t, growth tube t, inlet t, drainage t, heater t, psm cabin t
            meas[9], meas[10], meas[11], meas[12], # inlet p, inlet-sat p, sat-excess p, critical orifice p,
            psm_status, psm_note, # PSM status (1 ok / 0 nok), PSM notes (1 ok / 0 notes)
            # CPC nan placeholders, replaced later if CPC is connected
            "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan",
            status_hex, note_hex # PSM status (hex), PSM notes (hex)
        ]
        # if PSM 2.0, insert vacuum flow rate
        if psm_version == 2:
            psm_data.insert(14, meas[13]) # vacuum flow rate

        return psm_data
    
    # compile settings list for PSM .par file
    def compile_psm_settings(self, prnt, co_flow, psm_version):
        # psm_version: 1 = PSM, 2 = PSM 2.0
        
        # inlet flow is calculated and stored in update_plot_data
        psm_settings = [
            prnt[1], prnt[2], prnt[3], prnt[4], prnt[5], # T setpoints: growth tube, PSM saturator, inlet, heater, drainage
            prnt[6], "nan" # PSM stored CPC flow rate, inlet flow rate (added when calculated),
        ]

        # if PSM, add CO flow rate
        if psm_version == 1:
            psm_settings.append(co_flow)

        # add CPC values later in write_data if CPC connected
        return psm_settings
    
    # sets psm_settings_updates flag for specified PSM device
    # when flag is True, PSM settings are requested from device in get_dev_data
    def psm_update(self, device_id):
        self.psm_settings_updates[device_id] = True
    
    # sends set CPC flow rate to PSM and CPC if connected
    # TODO unused, remove?
    def psm_cpc_flow_send(self, device, value):
        self.psm_flow_send(device, value) # send flow rate to PSM
        self.cpc_flow_send(device, value) # send flow rate to connected CPC if it exists  
    
    # sends set flow rate to PSM
    def psm_flow_send(self, device, value):
        device.child("Connection").value().send_set_val(value, ":SET:FLOW:CPC ", decimals=3)
    
    # sends set flow rate to CPC
    def cpc_flow_send(self, device, value):
        # get connected CPC ID
        cpc_id = device.child("Connected CPC").value()
        # if PSM is connected to CPC, send value to CPC
        if cpc_id != 'None':
            # get connected CPC device parameter
            for cpc in self.params.child('Device settings').children():
                if cpc.child('DevID').value() == cpc_id:
                    cpc_device = cpc
                    break
            # if device is Airmodus CPC
            if cpc_device.child('Device type').value() == CPC:
                # send flow rate set value to CPC
                cpc_device.child("Connection").value().send_set_val(value, ":SET:FLOW ", decimals=3)

    # when command is entered, send message to device and update .par file
    def command_entered(self, dev_id, dev_param):
        try:
            # get message from command input and clear input
            command_widget = self.device_widgets[dev_id].set_tab.command_widget
            message = command_widget.command_input.text()
            command_widget.command_input.clear()
            # update command_widget's text box
            command_widget.update_text_box(message)

            # send message to device
            dev_param.child('Connection').value().send_message(message)

            # if saving is on, store command to latest_command dictionary
            if self.params.child('Measurement status').child('Data settings').child('Save data').value():
                self.latest_command[dev_id] = message
        
        except Exception as e:
            self.device_widgets[dev_id].set_tab.command_widget.update_text_box(str(e))
    
    # change PSM's 10 Hz parameter and button status
    def ten_hz_clicked(self, psm_param, psm_widget):
        # get current status of PSM 10 hz parameter
        status = psm_param.child('10 hz').value()
        # if 10 hz is off, turn it on
        if status == False:
            # set 10 hz flag to True
            psm_param.child('10 hz').setValue(True)
            psm_widget.measure_tab.ten_hz.change_color(1)       
        # if 10 hz is on, turn it off
        elif status == True:
            # set 10 hz flag to False
            psm_param.child('10 hz').setValue(False)
            psm_widget.measure_tab.ten_hz.change_color(0)
    
    # compare current day to file start day (self.start_day defined in save_changed)
    def compare_day(self):
        # check if saving is on
        if self.params.child('Measurement status').child("Data settings").child('Save data').value():
            # check if new file should be started at midnight
            if self.params.child('Measurement status').child("Data settings").child('Generate daily files').value():
                current_day = dt.now().strftime("%m%d")
                if current_day != self.start_day:
                    self.reset_filenames() # start new file if day has changed
                    # update start day
                    self.start_day = current_day
    
    # set COM port inquiry flag
    def set_inquiry_flag(self):
        self.inquiry_flag = True
        self.inquiry_time = time()
    
    def list_com_ports(self):
        # get list of available ports as serial objects
        ports = list_ports.comports()
        # check if ports list has changed from stored ports
        # if ports != self.current_ports: # if ports have changed, set flag for a specific time
        #     self.inquiry_flag = True # set inquiry flag to True
        #     self.inquiry_time = time() # store inquiry start timestamp for calculating timeout
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
                        QTimer.singleShot(300, lambda: serial_connection.write(b'*IDN?\n'))
                        # add serial_connection to new_ports dictionary, port address : serial object
                        # new_ports dictionary is sent to update_com_ports after delay
                        new_ports[port[0]] = serial_connection
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
        # if inquiry flag is True, check timeout
        if self.inquiry_flag == True:
            # if inquiry has timed out - if current time is bigger than inquiry_time + timeout (seconds)
            if time() > self.inquiry_time + 3:
                self.inquiry_flag = False # set inquiry flag to False

        # trigger update_com_ports with delay
        # reads responses from opened ports and prints devices to GUI
        QTimer.singleShot(600, lambda: self.update_com_ports(new_ports, com_port_list))
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
        # update GUI 'Available ports' text box if com port list has changed
        if com_ports_text != self.params.child('Measurement status').child('COM settings').child('Available ports').value():
            self.params.child('Measurement status').child('COM settings').child('Available ports').setValue(com_ports_text)
    
    def save_ini(self):
        # check if resume on startup is on
        resume_measurements = 0
        if self.params.child('Measurement status').child('Data settings').child('Resume on startup').value():
            resume_measurements = 1
        # store resume config path
        self.config_file_path = os.path.join(file_path, 'resume_config.json')
        with open(os.path.join(file_path, 'config.ini'),'w') as f:
            f.write(self.config_file_path)
            f.write(';')
            f.write(str(resume_measurements))
        # save the configuration to the JSON file
        self.save_configuration(self.config_file_path)
    
    def load_ini(self):
        try:
            # load the configuration file "config.ini" from the file_path
            with open(os.path.join(file_path, 'config.ini'),'r') as f:
                config = f.read()
                json_path = config.split(';')[0]
                resume_measurements = config.split(';')[1]
                # If json path is empty
                if not json_path:
                    json_path = os.path.join(file_path, 'resume_config.json')
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
                    # Use the to_dict method for serialization
                    result[param.name()] = param.value().to_dict()
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
        # dictionary of device names matching device type
        device_names = {CPC: 'CPC', PSM: 'PSM Retrofit', Electrometer: 'Electrometer', CO2_sensor: 'CO2 sensor', RHTP: 'RHTP', AFM: 'AFM', eDiluter: 'eDiluter', PSM2: 'PSM 2.0', TSI_CPC: 'TSI CPC', Example_device: 'Example device'}
        try:
            # go through each device in the device settings
            for dev_name, dev_values in device_settings.items():
                # get 'DevID' and 'Device type' values
                dev_id = dev_values.get('DevID', None)
                dev_type = dev_values.get('Device type', None)
                # set n_devices to current dev_id
                self.params.child('Device settings').n_devices = dev_id
                # add device to the parameter tree
                self.params.child('Device settings').addNew(device_names[dev_type])
        except AttributeError:
            pass
            
    def load_parameters_recursive(self, parameters, values):
        for param in parameters:
            if param.hasChildren():
                self.load_parameters_recursive(param.children(), values.get(param.name(), {}))
            else:
                # Check if the parameter value is a dictionary (indicating a complex object)
                if isinstance(values.get(param.name()), dict):
                    # skip the parameter
                    # 'Connection' parameter (SerialDeviceConnection) was created when the device was added
                    pass
                # Check if parameter name is CO flow
                elif param.name() == 'CO flow':
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
                    # Set CO flow value to related PSM widget
                    self.device_widgets[param.parent().child("DevID").value()].set_tab.set_co_flow.value_spinbox.setValue(round(float(param.value()), 3))
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
        """ # if Follow is on
        if self.params.child('Plot settings').child('Follow').value():
            # detect if view is dragged and turn Follow off if it is
            viewbox_range = viewbox.viewRange()
            # if x axis range differs from follow window size OR x axis max value differs from self.current_time
            if viewbox_range[0][1]-viewbox_range[0][0] != self.params.child('Plot settings').child('Time window (s)').value() or viewbox_range[0][1] != self.current_time:
                # if active widget is main plot
                if QApplication.focusWidget() == self.main_plot:
                    self.params.child('Plot settings').child('Follow').setValue(False) # turn follow parameter off """
    
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
                # RHTP or AFM
                if dev.child('Device type').value() in [RHTP, AFM]:
                    # if Plot to main is enabled
                    if dev.child('Plot to main').value() != None:
                        # add curve to legend with device name and current value of chosen parameter
                        if dev.child('Plot to main').value() == "RH":
                            legend_string = dev.child('Device name').value() + ": " + str(self.plot_data[str(dev_id)+':rh'][self.time_counter])
                        elif dev.child('Plot to main').value() == "T":
                            legend_string = dev.child('Device name').value() + ": " + str(self.plot_data[str(dev_id)+':t'][self.time_counter])
                        elif dev.child('Plot to main').value() == "P":
                            legend_string = dev.child('Device name').value() + ": " + str(self.plot_data[str(dev_id)+':p'][self.time_counter])
                        elif dev.child('Device type').value() == AFM and dev.child('Plot to main').value() == "Flow":
                            legend_string = dev.child('Device name').value() + ": " + str(self.plot_data[str(dev_id) + ':f'][self.time_counter])
                        elif dev.child('Device type').value() == AFM and dev.child('Plot to main').value() == "Standard flow":
                            legend_string = dev.child('Device name').value() + ": " + str(self.plot_data[str(dev_id) + ':sf'][self.time_counter])
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
                        legend_string = dev.child('Device name').value() + ": " + str(round(self.plot_data[str(dev_id)][self.time_counter], 2))
                    # if Electrometer, get Voltage 2 value
                    elif dev.child('Device type').value() == Electrometer:
                        legend_string = dev.child('Device name').value() + ": " + str(self.plot_data[str(dev_id)+':2'][self.time_counter])
                    # other devices
                    else:
                        legend_string = dev.child('Device name').value() + ": " + str(self.plot_data[dev_id][self.time_counter])
                    # add curve to legend with legend string
                    self.main_plot.legend.addItem(self.curve_dict[dev_id], legend_string)
                else: # if False
                    # remove curve from legend
                    self.main_plot.legend.removeItem(self.curve_dict[dev_id])
    
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

                # if error is True
                if error:
                    # change tab icon to error icon
                    self.device_tabs.setTabIcon(tab_index, self.error_icon)
                    # change status tab icon to error icon if device is CPC or PSM
                    if device_type in [CPC, PSM, PSM2]:
                        status_tab_index = device_widget.indexOf(device_widget.status_tab)
                        device_widget.setTabIcon(status_tab_index, self.error_icon)

                # if error is False
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
    
    # update device tab name according to device name
    def update_tab_name(self, device_id, device_name):
        device_widget = self.device_widgets[device_id]
        tab_index = self.device_tabs.indexOf(device_widget)
        self.device_tabs.setTabText(tab_index, device_name)

    # triggered when a new device is added to the parameter tree
    # sigChildAdded(self, param, child, index) - Emitted when a child (device) is added
    def device_added(self, param, child, index):
        if param.name() == "Device settings": # check if detected parameter is a device
            device_param = child # store device parameter
            device_type = child.child("Device type").value() # store device type
            device_id = child.child("DevID").value() # store device ID

            # connect serial number change to reset_device_filenames function
            device_param.child("Serial number").sigValueChanged.connect(lambda: self.reset_device_filenames(device_id))
            # connect device name change to reset_device_filenames function
            device_param.child("Device name").sigValueChanged.connect(lambda: self.reset_device_filenames(device_id))
            # connect device name change to update_tab_name function
            device_param.child("Device name").sigValueChanged.connect(lambda: self.update_tab_name(device_id, device_param.child("Device name").value()))

            # create new widget according to device type
            if device_type == CPC: # if CPC
                # create CPC widget instance
                widget = CPCWidget(device_param)
                # store connection for readability
                connection = device_param.child('Connection').value()
                # connect Set tab buttons to send_set function
                widget.set_tab.drain.clicked.connect(lambda: connection.send_set(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
                widget.set_tab.autofill.clicked.connect(lambda: connection.send_set(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
                widget.set_tab.water_removal.clicked.connect(lambda: connection.send_set(":SET:WREM " + str(int(widget.set_tab.water_removal.isChecked()))))
                # connect command_input to comand_entered function
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: self.command_entered(device_id, device_param))
                # connect Set tab set points to send_set_val function
                # send set value and message using lambda once value has been changed
                # stepChanged signal is defined in SpinBox and DoubleSpinBox classes
                # https://stackoverflow.com/questions/47874952/qspinbox-signal-for-arrow-buttons
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_saturator_temp.value_input.text()), ":SET:TEMP:SAT "))
                widget.set_tab.set_condenser_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:CON "))
                widget.set_tab.set_condenser_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_condenser_temp.value_input.text()), ":SET:TEMP:CON "))
                #widget.set_tab.set_averaging_time.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TAVG "))
                #widget.set_tab.set_averaging_time.value_input.returnPressed.connect(lambda: connection.send_set_val(int(widget.set_tab.set_averaging_time.value_input.text()), ":SET:TAVG "))

                # Use integer formatting with times > 1 to preserve compatibility with older firmware
                def send_averaging_time(value: float):
                    output: float | int = value
                    if value >= 1.0:
                        output = round(value)
                    connection.send_set_val(output, ":SET:TAVG ")

                widget.set_tab.set_averaging_time.value_spinbox.stepChanged.connect(lambda value: send_averaging_time(value))
                widget.set_tab.set_averaging_time.value_input.returnPressed.connect(lambda: send_averaging_time(float(widget.set_tab.set_averaging_time.value_input.text())))

            if device_type in [PSM, PSM2]: # if PSM TODO optimize structure, remove repetition
                # create PSM widget instance
                widget = PSMWidget(device_param, device_type)
                # add to psm_settings_updates dictionary, set to True
                self.psm_settings_updates[device_id] = True
                # store connection for readability
                connection = device_param.child('Connection').value()
                # connect Measure tab buttons to send_set function
                widget.measure_tab.scan.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_scan()))
                widget.measure_tab.step.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_step()))
                widget.measure_tab.fixed.clicked.connect(lambda: connection.send_set(widget.measure_tab.compile_fixed()))
                # connect ten_hz button to ten_hz_clicked function
                widget.measure_tab.ten_hz.clicked.connect(lambda: self.ten_hz_clicked(device_param, widget))
                # connect SetTab SetWidgets to send_set_val function and set settings update flag to True
                # growth tube temperature set
                widget.set_tab.set_growth_tube_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:GT "))
                widget.set_tab.set_growth_tube_temp.value_spinbox.stepChanged.connect(lambda: self.psm_update(device_id))
                widget.set_tab.set_growth_tube_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_growth_tube_temp.value_input.text()), ":SET:TEMP:GT "))
                widget.set_tab.set_growth_tube_temp.value_input.returnPressed.connect(lambda: self.psm_update(device_id))
                # saturator temperature set
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(lambda: self.psm_update(device_id))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_saturator_temp.value_input.text()), ":SET:TEMP:SAT "))
                widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(lambda: self.psm_update(device_id))
                # inlet temperature set
                widget.set_tab.set_inlet_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:INL "))
                widget.set_tab.set_inlet_temp.value_spinbox.stepChanged.connect(lambda: self.psm_update(device_id))
                widget.set_tab.set_inlet_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_inlet_temp.value_input.text()), ":SET:TEMP:INL "))
                widget.set_tab.set_inlet_temp.value_input.returnPressed.connect(lambda: self.psm_update(device_id))
                # heater temperature set
                widget.set_tab.set_heater_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:PRE "))
                widget.set_tab.set_heater_temp.value_spinbox.stepChanged.connect(lambda: self.psm_update(device_id))
                widget.set_tab.set_heater_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_heater_temp.value_input.text()), ":SET:TEMP:PRE "))
                widget.set_tab.set_heater_temp.value_input.returnPressed.connect(lambda: self.psm_update(device_id))
                # drainage temperature set
                widget.set_tab.set_drainage_temp.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:TEMP:DRN "))
                widget.set_tab.set_drainage_temp.value_spinbox.stepChanged.connect(lambda: self.psm_update(device_id))
                widget.set_tab.set_drainage_temp.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_drainage_temp.value_input.text()), ":SET:TEMP:DRN "))
                widget.set_tab.set_drainage_temp.value_input.returnPressed.connect(lambda: self.psm_update(device_id))
                # cpc inlet flow set (send value to PSM)
                #widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda value: connection.send_set_val(value, ":SET:FLOW:CPC "))
                widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda value: self.psm_flow_send(device_param, value))
                widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(lambda: self.psm_update(device_id))
                #widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: connection.send_set_val(float(widget.set_tab.set_cpc_inlet_flow.value_input.text()), ":SET:FLOW:CPC "))
                widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: self.psm_flow_send(device_param, float(widget.set_tab.set_cpc_inlet_flow.value_input.text())))
                widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(lambda: self.psm_update(device_id))
                # cpc sample flow set (send value to connected CPC if it exists)
                # TODO is psm_update required when setting cpc sample flow?
                widget.set_tab.set_cpc_sample_flow.value_spinbox.stepChanged.connect(lambda value: self.cpc_flow_send(device_param, value))
                widget.set_tab.set_cpc_sample_flow.value_input.returnPressed.connect(lambda: self.cpc_flow_send(device_param, float(widget.set_tab.set_cpc_sample_flow.value_input.text())))
                # if device type is PSM, connect co flow set
                if device_type == PSM:
                    widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(lambda: self.psm_update(device_id))
                    widget.set_tab.set_co_flow.value_input.returnPressed.connect(lambda: self.psm_update(device_id))
                    # set value to hidden 'CO flow' parameter in parameter tree
                    widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(lambda value: device_param.child('CO flow').setValue(str(round(value, 3))))
                    widget.set_tab.set_co_flow.value_input.returnPressed.connect(lambda: device_param.child('CO flow').setValue(widget.set_tab.set_co_flow.value_input.text()))
                # connect command_input to command_entered and psm_update functions
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: self.command_entered(device_id, device_param))
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: self.psm_update(device_id))
                # connect liquid operations
                widget.set_tab.autofill.clicked.connect(lambda: connection.send_set(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
                #widget.set_tab.autofill.clicked.connect(lambda: self.psm_update(device_id))
                widget.set_tab.drain.clicked.connect(lambda: connection.send_set(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
                #widget.set_tab.drain.clicked.connect(lambda: self.psm_update(device_id))
                widget.set_tab.drying.clicked.connect(lambda: connection.send_set(widget.set_tab.drying.messages[int(widget.set_tab.drying.isChecked())]))
                #widget.set_tab.drying.clicked.connect(lambda: self.psm_update(device_id))

            if device_type == Electrometer: # if Electrometer
                widget = ElectrometerWidget(device_param) # create Electrometer widget instance

            if device_type == CO2_sensor: # if CO2
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
            
            if device_type == eDiluter: # if eDiluter
                widget = eDiluterWidget(device_param) # create eDiluter widget instance
                # store connection for readability
                connection = device_param.child('Connection').value()
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
                widget.set_tab.command_widget.command_input.returnPressed.connect(lambda: self.command_entered(device_id, device_param))
            
            if device_type == TSI_CPC: # if TSI CPC
                # create TSI widget instance
                widget = TSIWidget(device_param)
                # store connection for readability
                connection = device_param.child('Connection').value()
                # add baud rate parameter
                device_param.addChild({'name': 'Baud rate', 'type': 'int', 'value': 115200})
                # connect baud rate parameter to connection's set_baud_rate function
                device_param.child('Baud rate').sigValueChanged.connect(lambda: connection.set_baud_rate(device_param.child('Baud rate').value()))
            
            if device_type == Example_device: # if Example device
                widget = ExampleDeviceWidget(device_param) # create Example device widget instance
            
            # connect x range change of plot_tab's viewbox(es) to x_range_changed function (autoscale y)
            if device_type == Electrometer:
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
                self.latest_poly_correction, self.latest_ten_hz, self.extra_data, # data
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
                    if device_type in [CPC, TSI_CPC, Electrometer, RHTP, AFM]:
                        # determine value types based on device type
                        if device_type in [CPC, TSI_CPC]:
                            types = ['', ':raw'] # concentration, raw concentration
                        elif device_type == Electrometer:
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
        print("Timer stopped.")
    
    # restart timer to sync to seconds
    def restartTimer(self):
        self.endTimer() # stop timer
        print("Restarting timer...")
        self.startTimer() # start timer
        self.timer_functions() # call timer functions at start time

# main plot widget
class MainPlot(GraphicsLayoutWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        
        # create plot by adding it to widget
        self.plot = self.addPlot()
        # create legend
        self.legend = LegendItem(offset=(70,20), labelTextColor='w', labelTextSize='11pt')
        self.legend.setParentItem(self.plot.graphicsItem())
        # create dictionaries for viewboxes and axes, use device type as key
        self.viewboxes = {}
        self.axes = {}

        # time axis
        self.plot.setAxisItems({'bottom':DateAxisItem()}) # set time axis to bottom
        self.plot.setLabel('bottom', "Time") # set time axis label
        self.axis_time = self.plot.getAxis('bottom') # store time axis to variable
        self.set_axis_style(self.axis_time, 'w') # set axis style
        self.axis_time.enableAutoSIPrefix(enable=False) # disable auto SI prefix

        # CPC viewbox
        self.viewboxes[CPC] = self.plot.getViewBox() # store default viewbox to dictionary
        # CPC axis
        self.axes[CPC] = self.plot.getAxis('left') # store left axis to dictionary
        self.axes[CPC].setLabel('CPC concentration', units='#/cc', color='w') # set label
        self.set_axis_style(self.axes[CPC], 'w') # set axis style

        # PSM viewbox # TODO create function for viewbox and axis creation
        self.viewboxes[PSM] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[PSM]) # add viewbox to scene
        self.viewboxes[PSM].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # PSM axis
        self.axes[PSM] = AxisItem('right') # create second axis
        self.plot.layout.addItem(self.axes[PSM], 2, 3) # add axis to plot
        self.axes[PSM].setLabel('PSM saturator flow rate', units='lpm', color='w') # set label
        self.set_axis_style(self.axes[PSM], 'w') # set axis style
        self.axes[PSM].linkToView(self.viewboxes[PSM]) # link axis to viewbox

        # Electrometer viewbox
        self.viewboxes[Electrometer] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[Electrometer]) # add viewbox to scene
        self.viewboxes[Electrometer].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # Electrometer axis
        self.axes[Electrometer] = AxisItem('right') # create third axis
        self.plot.layout.addItem(self.axes[Electrometer], 2, 4) # add axis to plot
        self.axes[Electrometer].setLabel('Electrometer voltage 2', units='V', color='w') # set label
        self.set_axis_style(self.axes[Electrometer], 'w') # set axis style
        self.axes[Electrometer].linkToView(self.viewboxes[Electrometer]) # link axis to viewbox

        # CO2 viewbox
        self.viewboxes[CO2_sensor] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[CO2_sensor]) # add viewbox to scene
        self.viewboxes[CO2_sensor].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # CO2 axis
        self.axes[CO2_sensor] = AxisItem('right') # create fourth axis
        self.plot.layout.addItem(self.axes[CO2_sensor], 2, 5) # add axis to plot
        self.axes[CO2_sensor].setLabel('CO2 concentration', units='ppm', color='w') # set label
        self.set_axis_style(self.axes[CO2_sensor], 'w') # set axis style
        self.axes[CO2_sensor].linkToView(self.viewboxes[CO2_sensor]) # link axis to viewbox

        # RHTP viewbox
        self.viewboxes[RHTP] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[RHTP]) # add viewbox to scene
        self.viewboxes[RHTP].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # RHTP axis
        self.axes[RHTP] = AxisItem('right') # create fifth axis
        self.plot.layout.addItem(self.axes[RHTP], 2, 6) # add axis to plot
        self.axes[RHTP].setLabel('RHTP', color='w') # set label
        self.set_axis_style(self.axes[RHTP], 'w') # set axis style
        self.axes[RHTP].linkToView(self.viewboxes[RHTP]) # link axis to viewbox

        # AFM viewbox
        self.viewboxes[AFM] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[AFM]) # add viewbox to scene
        self.viewboxes[AFM].setXLink(self.plot)
        # AFM axis
        self.axes[AFM] = AxisItem('right') # create sixth axis
        self.plot.layout.addItem(self.axes[AFM], 2, 7) # add axis to plot
        self.axes[AFM].setLabel('AFM', color='w')
        self.set_axis_style(self.axes[AFM], 'w')
        self.axes[AFM].linkToView(self.viewboxes[AFM])

        # eDiluter viewbox
        self.viewboxes[eDiluter] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[eDiluter]) # add viewbox to scene
        self.viewboxes[eDiluter].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # eDiluter axis
        self.axes[eDiluter] = AxisItem('right') # create axis
        self.plot.layout.addItem(self.axes[eDiluter], 2, 8) # add axis to plot
        self.axes[eDiluter].setLabel('eDiluter temperature', units='°C', color='w') # set label
        self.set_axis_style(self.axes[eDiluter], 'w') # set axis style
        self.axes[eDiluter].linkToView(self.viewboxes[eDiluter]) # link axis to viewbox

        # Example device viewbox
        self.viewboxes[Example_device] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[Example_device]) # add viewbox to scene
        self.viewboxes[Example_device].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # Example device axis
        self.axes[Example_device] = AxisItem('right') # create axis
        self.plot.layout.addItem(self.axes[Example_device], 2, 9) # add axis to plot
        self.axes[Example_device].setLabel('Example device', units='units', color='w') # set label
        self.set_axis_style(self.axes[Example_device], 'w') # set axis style
        self.axes[Example_device].linkToView(self.viewboxes[Example_device]) # link axis to viewbox
        
        # connect viewbox resize event to updateViews function
        self.plot.vb.sigResized.connect(self.updateViews)
        # call updateViews function to set viewboxes to same size
        self.updateViews()

        # hide axes and disable SI scaling by default
        for key in self.axes:
            self.axes[key].hide()
            self.axes[key].enableAutoSIPrefix(enable=False) # disable auto SI prefix
        
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)
        # TODO does this affect all viewboxes?
    
    # handle view resizing
    # called when plot widget (or window) is resized
    # source: https://stackoverflow.com/questions/42931474/how-can-i-have-multiple-left-axisitems-with-the-same-alignment-position-using-py
    def updateViews(self):
        # set viewbox geometry to plot geometry
        for viewbox in self.viewboxes.values():
            # exclude CPC viewbox
            if viewbox != self.viewboxes[CPC]:
                viewbox.setGeometry(self.plot.vb.sceneBoundingRect())
                # update linked axes
                viewbox.linkedViewChanged(self.plot.vb, viewbox.XAxis)
    
    def set_axis_style(self, axis, color):
        axis.setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
        axis.setPen(color)
        axis.setTextPen(color)
        axis.label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font

    def show_hide_axis(self, device_type, show):
        if device_type == PSM2:
            axis = self.axes[PSM]
        elif device_type == TSI_CPC:
            axis = self.axes[CPC]
        else:
            axis = self.axes[device_type]
        if show:
            axis.show() # show axis
        else:
            axis.hide() # hide axis
    
    # change rhtp axis label according to value type
    # None, "RH", "T", "P"
    def change_rhtp_axis(self, value):
        # TODO: only change axis if value differs from current axis
        if value == None:
            self.axes[RHTP].setLabel('RHTP', units=None, color='w')
            self.axes[RHTP].hide() # hide axis
        else:
            if value == "RH":
                self.axes[RHTP].setLabel('RHTP RH', units='%', color='w')
            elif value == "T":
                self.axes[RHTP].setLabel('RHTP T', units='°C', color='w')
            elif value == "P":
                self.axes[RHTP].setLabel('RHTP P', units='Pa', color='w')
            self.axes[RHTP].show() # show axis
        # set axis style
        self.set_axis_style(self.axes[RHTP], 'w')
    
    def change_afm_axis(self, value):
        if value == None:
            self.axes[AFM].setLabel('AFM', units=None, color='w')
            self.axes[AFM].hide() # hide axis
        else:
            if value == "Flow":
                self.axes[AFM].setLabel('AFM flow', units='lpm', color='w')
            elif value == "Standard flow":
                self.axes[AFM].setLabel('AFM standard flow', units='slpm', color='w')
            elif value == "RH":
                self.axes[AFM].setLabel('AFM RH', units='%', color='w')
            elif value == "T":
                self.axes[AFM].setLabel('AFM T', units='°C', color='w')
            elif value == "P":
                self.axes[AFM].setLabel('AFM P', units='Pa', color='w')
            self.axes[AFM].show() # show axis
        # set axis style
        self.set_axis_style(self.axes[AFM], 'w')
        
# triple plot widget containing three plots
class TriplePlot(GraphicsLayoutWidget):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()

        if device_type == 5: # RHTP
            value_names = ["RH", "T", "P"]
            unit_names = ["%", "°C", "Pa"]
            colors = [(100,188,255), (255,100,100), (255, 255, 100)]
        else: # other devices
            value_names = ["val1", "val2", "val3"]
            unit_names = ["unit1", "unit2", "unit3"]
            colors = [(255,255,255), (255,100,100), (100,188,255)]
        
        # create plot by adding it to widget
        self.plot = self.addPlot()

        # time axis
        self.plot.setAxisItems({'bottom':DateAxisItem()}) # set time axis to bottom
        self.plot.setLabel('bottom', "Time") # set time axis label
        self.axis_time = self.plot.getAxis('bottom') # store time axis to variable
        self.set_axis_style(self.axis_time, 'w') # set axis style

        # viewbox 1
        self.viewbox1 = self.plot.getViewBox() # store default viewbox to variable
        # axis 1
        self.axis1 = self.plot.getAxis('left') # store left axis to variable
        self.axis1.setLabel(value_names[0], units=unit_names[0], color=colors[0]) # set label
        self.set_axis_style(self.axis1, colors[0]) # set axis style
        # curve 1
        self.curve1 = PlotCurveItem(pen=colors[0], connect="finite") # create curve 1
        self.viewbox1.addItem(self.curve1) # add curve 1 to viewbox 1

        # viewbox 2
        self.viewbox2 = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewbox2) # add viewbox to scene
        self.viewbox2.setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # axis 2
        self.axis2 = AxisItem('right') # create second axis
        self.plot.layout.addItem(self.axis2, 2, 3) # add axis to plot
        self.axis2.setLabel(value_names[1], units=unit_names[1], color=colors[1]) # set label
        self.set_axis_style(self.axis2, colors[1]) # set axis style
        self.axis2.linkToView(self.viewbox2) # link axis to viewbox
        # curve 2
        self.curve2 = PlotCurveItem(pen=colors[1], connect="finite") # create curve 2
        self.viewbox2.addItem(self.curve2) # add curve 2 to viewbox 2

        # viewbox 3
        self.viewbox3 = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewbox3) # add viewbox to scene
        self.viewbox3.setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # axis 3
        self.axis3 = AxisItem('right') # create third axis
        self.plot.layout.addItem(self.axis3, 2, 4) # add axis to plot
        self.axis3.setLabel(value_names[2], units=unit_names[2], color=colors[2]) # set label
        self.set_axis_style(self.axis3, colors[2]) # set axis style
        self.axis3.linkToView(self.viewbox3) # link axis to viewbox
        # curve 3
        self.curve3 = PlotCurveItem(pen=colors[2], connect="finite") # create curve 3
        self.viewbox3.addItem(self.curve3) # add curve 3 to viewbox 3

        # create list of viewboxes
        self.viewboxes = [self.viewbox1, self.viewbox2, self.viewbox3]

        # connect viewbox resize event to updateViews function
        self.plot.vb.sigResized.connect(self.updateViews)
        # call updateViews function to set viewboxes to same size
        self.updateViews()
        
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)
    
    # handle view resizing
    # called when plot widget (or window) is resized
    # source: https://stackoverflow.com/questions/42931474/how-can-i-have-multiple-left-axisitems-with-the-same-alignment-position-using-py
    def updateViews(self):
        # set viewbox geometry to plot geometry
        for viewbox in self.viewboxes[1:]: # exclude viewbox 1
            viewbox.setGeometry(self.plot.vb.sceneBoundingRect())
            # update linked axes
            viewbox.linkedViewChanged(self.plot.vb, viewbox.XAxis)

    def set_axis_style(self, axis, color):
        axis.setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
        axis.setPen(color)
        axis.setTextPen(color)
        axis.label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font
        axis.enableAutoSIPrefix(enable=False) # disable auto SI prefix

class AFMPlot(GraphicsLayoutWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        # define value names, units and colors
        value_names = ["Flow", "Standard flow", "RH", "T", "P"]
        unit_names = ["lpm", "slpm", "%", "°C", "Pa"]
        colors = [(255,255,255), (255,100,255), (100,188,255), (255, 100, 100), (255, 255, 100)]

        # create plot item and hide its default axes
        self.plot = PlotItem()
        self.plot.hideAxis('left')
        self.plot.hideAxis('bottom')
        # add plot to widget column 2, leave space for left axes
        self.addItem(self.plot, row=0, col=2)

        # create viewboxes for each axis
        self.viewboxes = []
        # store default viewbox
        self.viewboxes.append(self.plot.getViewBox())
        # create 4 additional viewboxes
        for i in range(4):
            viewbox = ViewBox() # create viewbox
            self.plot.scene().addItem(viewbox) # add viewbox to scene
            viewbox.setXLink(self.plot) # link x axis of viewbox to x axis of plot
            self.viewboxes.append(viewbox) # store viewbox to list
        
        # create axes for each viewbox
        self.axes = []
        for i in range(2):
            axis = AxisItem('left') # create left axis
            self.axes.append(axis) # store axis to list
            self.addItem(axis, row=0, col=i) # add axis to widget
        for i in range(3):
            axis = AxisItem('right') # create right axis
            self.axes.append(axis) # store axis to list
            self.addItem(axis, row=0, col=i+3) # add axis to widget, skip left axes and plot
        
        # link axes to viewboxes
        for i in range(5):
            self.axes[i].linkToView(self.viewboxes[i])
        
        # set axis labels and styles
        for i in range(5):
            # set label
            self.axes[i].setLabel(value_names[i], units=unit_names[i], color=colors[i])
            # set style
            self.axes[i].setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
            self.axes[i].setPen(colors[i])
            self.axes[i].setTextPen(colors[i])
            self.axes[i].label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font
            self.axes[i].enableAutoSIPrefix(enable=False) # disable auto SI prefix
        
        # create bottom time axis
        self.axis_time = DateAxisItem('bottom')
        # link time axis to viewbox
        self.axis_time.linkToView(self.viewboxes[0])
        # set botton axis label and style
        self.axis_time.setLabel("Time")
        self.axis_time.setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
        self.axis_time.setPen('w')
        self.axis_time.setTextPen('w')
        self.axis_time.label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font
        self.axis_time.enableAutoSIPrefix(enable=False) # disable auto SI prefix

        # add bottom time axis to widget, same column as plot but on next row
        self.addItem(self.axis_time, row=1, col=2)

        # create curves for each viewbox
        self.curves = []
        for i in range(5):
            curve = PlotCurveItem(pen=colors[i], connect="finite") # create curve
            self.curves.append(curve) # store curve to list
            self.viewboxes[i].addItem(curve) # add curve to viewbox
        
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)
        
        # connect viewbox resize event to updateViews function
        self.plot.vb.sigResized.connect(self.updateViews)
        # call updateViews function to set viewboxes to same size
        self.updateViews()
    
    def updateViews(self):
        # set viewbox geometry to plot geometry
        for viewbox in self.viewboxes[1:]: # exclude first viewbox
            viewbox.setGeometry(self.plot.vb.sceneBoundingRect())
            # update linked axes
            viewbox.linkedViewChanged(self.plot.vb, viewbox.XAxis)

class ElectrometerPlot(GraphicsLayoutWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        # list for storing references to plots
        self.plots = []
        # create plots and curves
        # Voltage 1
        self.plot1 = self.addPlot()
        self.curve1 = self.plot1.plot(pen="g", connect="finite")
        self.plots.append(self.plot1)
        self.nextRow()
        # Voltage 2
        self.plot2 = self.addPlot()
        self.curve2 = self.plot2.plot(pen="r", connect="finite")
        self.plots.append(self.plot2)
        self.nextRow()
        # Voltage 3
        self.plot3 = self.addPlot()
        self.curve3 = self.plot3.plot(pen="b", connect="finite")
        self.plots.append(self.plot3)
        # set up plots
        for i in range(3):
            label = "Voltage " + str(i+1)
            self.plots[i].setLabel('left', label, units='V') # set y-axis label
            self.plots[i].setLabel('bottom', "Time") # set time axis label
            self.plots[i].setAxisItems({'bottom':DateAxisItem()})
            #self.plots[i].getAxis('left').enableAutoSIPrefix(enable=False) # disable auto SI prefix
            self.plots[i].getAxis('bottom').enableAutoSIPrefix(enable=False) # disable auto SI prefix
            self.plots[i].showGrid(x=True, y=True) # show grid by default
            self.plots[i].setDownsampling(mode='peak')
            self.plots[i].setClipToView(True)

# single plot widget containing plot
class SinglePlot(GraphicsLayoutWidget):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()

        # create plot and curve
        self.plot = self.addPlot() # create plot by adding it to widget
        self.curve = self.plot.plot(pen="w", connect="finite") # create plot curve

        # plot settings
        self.plot.setAxisItems({'bottom':DateAxisItem()}) # set time axis to bottom
        self.plot.getAxis('bottom').enableAutoSIPrefix(enable=False) # disable auto SI prefix 
        self.plot.setLabel('bottom', "Time") # set time axis label
        self.plot.showGrid(x=True, y=True) # show grid by default
        self.plot.getAxis('left').enableAutoSIPrefix(enable=False) # disable auto SI prefix
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)

        # set y-axis label and units based on device type
        if device_type == CPC:
            self.plot.setLabel('left', "Concentration", units='#/cc')
        elif device_type == PSM:
            self.plot.setLabel('left', "Saturator flow", units='lpm')
        elif device_type == CO2_sensor:
            self.plot.setLabel('left', "CO2", units='ppm')
        elif device_type == eDiluter:
            self.plot.setLabel('left', "eDiluter temperature", units='°C')
        elif device_type == AFM:
            self.plot.setLabel('left', "Flow", units='lpm')
        elif device_type == Example_device:
            self.plot.setLabel('left', "Example device", units='units')
        
        self.viewbox = self.plot.getViewBox() # store viewbox to variable

# CPC widget containing CPC related GUI elements as tabs
class CPCWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create set tab widget for cpc settings
        self.set_tab = CPCSetTab()
        self.addTab(self.set_tab, "Set")
        # create status tab widget showing CPC values
        self.status_tab = CPCStatusTab()
        self.addTab(self.status_tab, "Status")
        # create plot widget for Concentration
        self.plot_tab = SinglePlot(device_type=CPC)
        self.addTab(self.plot_tab, "Concentration")

        # create list of widget references for updating gui with cpc system status
        self.cpc_status_widgets = [
            self.status_tab.pres_critical_orifice, self.status_tab.temp_cabin,
            self.status_tab.liquid_level, self.status_tab.laser_power,
            self.status_tab.pres_nozzle, self.status_tab.pres_inlet,
            self.status_tab.temp_condenser, self.status_tab.temp_saturator,
            self.status_tab.temp_optics
        ]

    # convert CPC status hex to binary and update error label colors
    def update_errors(self, status_hex):
        status_bin = bin(int(status_hex, 16)) # convert hex to int and int to binary
        status_bin = status_bin[2:].zfill(9) # remove 0b from string and fill with 0s to make 9 digits
        total_errors = status_bin.count("1") # count number of 1s in status_bin
        for i in range(9): # iterate through all 9 digits, index 0-8
            self.cpc_status_widgets[i].change_color(status_bin[i]) # change color of error label according to status_bin digit
        
        return total_errors # return total number of errors
    
    def update_settings(self, settings):
        # update GUI set values if they differ from CPC set values
        # TODO remove repetition

        # saturator temperature
        if self.set_tab.set_saturator_temp.value_spinbox.value() != settings[8]:
            # update value
            self.set_tab.set_saturator_temp.value_spinbox.setValue(settings[8])
            # if saturator temperature is nan, clear visible value
            if str(settings[8]) == 'nan':
                self.set_tab.set_saturator_temp.value_spinbox.clear()
            # if text is empty (without suffix), set text with value
            # TODO ? change this to text().split(" ")[0] == ""
            elif self.set_tab.set_saturator_temp.value_spinbox.text()[:-3] == "":
                self.set_tab.set_saturator_temp.value_spinbox.lineEdit().setText(str(settings[8]))

        # condenser temperature
        if self.set_tab.set_condenser_temp.value_spinbox.value() != settings[6]:
            # update value
            self.set_tab.set_condenser_temp.value_spinbox.setValue(settings[6])
            # if condenser temperature is nan, clear visible value
            if str(settings[6]) == 'nan':
                self.set_tab.set_condenser_temp.value_spinbox.clear()
            # if text is empty (without suffix), set text with value
            elif self.set_tab.set_condenser_temp.value_spinbox.text()[:-3] == "":
                self.set_tab.set_condenser_temp.value_spinbox.lineEdit().setText(str(settings[6]))

        # averaging time
        if self.set_tab.set_averaging_time.value_spinbox.value() != settings[5]:
            # update value
            if str(settings[5]) == 'nan': # if nan, set to 0
                self.set_tab.set_averaging_time.value_spinbox.setValue(0)
            else: # else update value
                self.set_tab.set_averaging_time.value_spinbox.setValue(settings[5])
            # if averaging time is nan, clear visible value
            if str(settings[5]) == 'nan':
                self.set_tab.set_averaging_time.value_spinbox.clear()
            # if text is empty (without suffix), update value set text with value
            elif self.set_tab.set_averaging_time.value_spinbox.text()[:-2] == "":
                self.set_tab.set_averaging_time.value_spinbox.lineEdit().setText(str(settings[5]))
        
        # update mode settings
        self.set_tab.autofill.update_state(settings[1]) # autofill
        self.set_tab.water_removal.update_state(settings[4]) # water removal
        self.set_tab.drain.update_state(settings[2]) # drain
    
    # update all data values in status tab
    def update_values(self, current_list):
        # update temperature values
        self.status_tab.temp_optics.change_value(str(current_list[5]) + " °C")
        self.status_tab.temp_saturator.change_value(str(current_list[3]) + " °C")
        self.status_tab.temp_condenser.change_value(str(current_list[4]) + " °C")
        # update pressure values
        self.status_tab.pres_inlet.change_value(str(current_list[7]) + " kPa")
        self.status_tab.pres_nozzle.change_value(str(current_list[9]) + " kPa")
        self.status_tab.pres_critical_orifice.change_value(str(current_list[8]) + " kPa")
        # update misc values
        if current_list[10] == 0:
            self.status_tab.liquid_level.change_value("LOW")
        elif current_list[10] == 1:
            self.status_tab.liquid_level.change_value("OK")
        elif current_list[10] == 2:
            self.status_tab.liquid_level.change_value("OVERFILL")
        self.status_tab.temp_cabin.change_value(str(current_list[6]) + " °C")

# PSM widget
class PSMWidget(QTabWidget):
    def __init__(self, device_parameter, device_type, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        self.device_type = device_type # store device type (PSM or PSM 2.0)
        # create set tab for PSM
        self.set_tab = PSMSetTab(device_type)
        self.addTab(self.set_tab, "Set")
        # create status tab for PSM
        self.status_tab = PSMStatusTab(device_type)
        self.addTab(self.status_tab, "Status")
        # create mode tab for PSM
        self.measure_tab = PSMMeasureTab()
        self.addTab(self.measure_tab, "Measure")
        # create plot widget for PSM
        self.plot_tab = SinglePlot(device_type=PSM)
        self.addTab(self.plot_tab, "PSM plot")

        # TODO check PSM 2.0 compatibility
        # create list of PSM status widgets, used in update_errors
        # TODO reverse to correct order, change update_errors
        self.psm_status_widgets = [ # reverse order for binary
            "mfc_temp", self.status_tab.pressure_critical_orifice,
            self.status_tab.temp_drainage, self.status_tab.temp_cabin, "drain_level",
            self.status_tab.flow_excess, self.status_tab.pressure_inlet, "mix2_press", "mix1_press",
            self.status_tab.temp_inlet, self.status_tab.temp_heater, self.status_tab.flow_saturator,
            self.status_tab.temp_saturator, self.status_tab.temp_growth_tube
        ]
        # if PSM 2.0, add vacuum flow widget to list
        if device_type == PSM2:
            self.psm_status_widgets.insert(0, self.status_tab.flow_vacuum)

    # convert PSM status hex to binary and update error label colors
    def update_errors(self, status_hex):
        widget_amount = len(self.psm_status_widgets) # get amount of widgets in list
        status_bin = bin(int(status_hex, 16)) # convert hex to int and int to binary
        status_bin = status_bin[2:].zfill(widget_amount) # remove 0b from string and fill with 0s to length of widget_amount
        total_errors = status_bin.count("1") # count number of 1s in status_bin
        for i in range(widget_amount): # iterate through all digits
            if type(self.psm_status_widgets[i]) != str: # filter placeholder strings
                self.psm_status_widgets[i].change_color(status_bin[i]) # change color of error label according to status_bin digit
        
        return total_errors # return total number of errors
    
    # if hex changes, make sure zero fill and indices match new hex
    def update_notes(self, note_hex):
        # TODO PSM 2.0 should have same note_hex as PSM after its firmware is updated
        note_bin = bin(int(note_hex, 16)) # convert hex to int and int to binary
        note_bin = note_bin[2:].zfill(7) # remove 0b from string and fill with 0s
        total_notes = note_bin.count("1") # count number of 1s in note_bin
        liquid_sets = note_bin[:3] # autofill, drying, drainage

        # update liquid mode settings in GUI
        # 0 = autofill on, 1 = autofill off
        if note_bin[1] == "0":
            self.set_tab.autofill.update_state(1)
        elif note_bin[1] == "1":
            self.set_tab.autofill.update_state(0)
        # 0 = drying off, 1 = drying on
        self.set_tab.drying.update_state(int(note_bin[2]))
        # 0 = drain on, 1 = drain off
        if note_bin[3] == "0":
            self.set_tab.drain.update_state(1)
        elif note_bin[3] == "1":
            self.set_tab.drain.update_state(0)
        # 0 = saturator liquid level OK, 1 = saturator liquid level LOW
        self.status_tab.liquid_saturator.change_color(note_bin[0])
        # 0 = drain liquid level OK, 1 = drain liquid level HIGH
        self.status_tab.liquid_drain.change_color(note_bin[6])

        return liquid_sets # return liquid settings string

    def update_settings(self, settings):
        self.set_tab.set_growth_tube_temp.value_spinbox.setValue(float(settings[1]))
        self.set_tab.set_saturator_temp.value_spinbox.setValue(float(settings[2]))
        self.set_tab.set_inlet_temp.value_spinbox.setValue(float(settings[3]))
        self.set_tab.set_heater_temp.value_spinbox.setValue(float(settings[4]))
        self.set_tab.set_drainage_temp.value_spinbox.setValue(float(settings[5]))
        self.set_tab.set_cpc_inlet_flow.value_spinbox.setValue(float(settings[6]))
    
    # update all data values in status tab
    def update_values(self, current_list):
        # update temperature values
        self.status_tab.temp_growth_tube.change_value(str(current_list[2]) + " °C")
        self.status_tab.temp_saturator.change_value(str(current_list[3]) + " °C")
        self.status_tab.temp_inlet.change_value(str(current_list[4]) + " °C")
        self.status_tab.temp_heater.change_value(str(current_list[5]) + " °C")
        self.status_tab.temp_drainage.change_value(str(current_list[6]) + " °C")
        self.status_tab.temp_cabin.change_value(str(current_list[7]) + " °C")
        # update flow values
        # self.status.flow_cpc is updated in PSMWidget's update_settings()
        self.status_tab.flow_saturator.change_value(str(current_list[0]) + " lpm")
        self.status_tab.flow_excess.change_value(str(current_list[1]) + " lpm")
        # self.status_tab.flow_inlet is updated in update_plot_data()
        # update pressure values
        self.status_tab.pressure_inlet.change_value(str(current_list[9]) + " kPa")
        self.status_tab.pressure_critical_orifice.change_value(str(current_list[12]) + " kPa")
        # update vacuum flow if PSM 2.0
        if self.device_type == PSM2:
            self.status_tab.flow_vacuum.change_value(str(current_list[13]) + " lpm")
        # liquid level values are updated in PSMWidget's update_notes()

class PSMSetTab(QSplitter):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()
        # split tab vertically
        self.setOrientation(Qt.Vertical)

        # TODO check device type and create widgets accordingly

        # horizontal splitter containing upper half of tab - set widgets
        upper_splitter = QSplitter(Qt.Horizontal)
        self.set_growth_tube_temp = SetWidget("Growth tube T", " °C")
        upper_splitter.addWidget(self.set_growth_tube_temp)
        self.set_saturator_temp = SetWidget("Saturator T", " °C")
        upper_splitter.addWidget(self.set_saturator_temp)
        self.set_inlet_temp = SetWidget("Inlet T", " °C")
        upper_splitter.addWidget(self.set_inlet_temp)
        self.set_heater_temp = SetWidget("Heater T", " °C")
        upper_splitter.addWidget(self.set_heater_temp)
        self.set_drainage_temp = SetWidget("Drainage T", " °C")
        upper_splitter.addWidget(self.set_drainage_temp)
        # horizontal splitter containing middle half of tab - set widgets
        middle_splitter = QSplitter(Qt.Horizontal)
        self.set_cpc_inlet_flow = SetWidget("CPC inlet flow rate\n(used in dilution correction)", " lpm", decimals=3)
        middle_splitter.addWidget(self.set_cpc_inlet_flow)
        self.set_cpc_sample_flow = SetWidget("CPC sample flow rate\n(used in concentration calculation)", " lpm", decimals=3)
        middle_splitter.addWidget(self.set_cpc_sample_flow)
        if device_type == PSM: # if PSM, add CO flow rate set widget
            self.set_co_flow = SetWidget("CO flow rate", " lpm", decimals=3)
            middle_splitter.addWidget(self.set_co_flow)
        # horizontal splitter containing lower half of tab - mode widgets
        lower_splitter = QSplitter(Qt.Horizontal)
        self.autofill = ToggleButton("Autofill")
        lower_splitter.addWidget(self.autofill)
        self.drain = ToggleButton("Drain")
        lower_splitter.addWidget(self.drain)
        self.drying = ToggleButton("Drying")
        lower_splitter.addWidget(self.drying)
        # set splitter's relative widget sizes and add to tab
        upper_splitter.setSizes([1000, 1000, 1000, 1000, 1000])
        self.addWidget(upper_splitter)
        middle_splitter.setSizes([1000, 1000, 1000])
        self.addWidget(middle_splitter)
        lower_splitter.setSizes([1000, 1000, 1000])
        self.addWidget(lower_splitter)
        # add line edit for command input
        if device_type == PSM: # if PSM
            self.command_widget = CommandWidget("PSM Retrofit")
        elif device_type == PSM2: # if PSM 2.0
            self.command_widget = CommandWidget("PSM 2.0")
        self.addWidget(self.command_widget)
        # set relative sizes in tab splitter
        self.setSizes([1000, 1000, 1000, 1000])
    
class PSMStatusTab(QWidget):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create layout

        # TODO check device type and create widgets accordingly

        # temperature indicators
        self.temp_growth_tube = IndicatorWidget("Growth tube temperature")
        layout.addWidget(self.temp_growth_tube, 0, 0)
        self.temp_saturator = IndicatorWidget("Saturator temperature")
        layout.addWidget(self.temp_saturator, 1, 0)
        self.temp_inlet = IndicatorWidget("Inlet temperature")
        layout.addWidget(self.temp_inlet, 2, 0)
        self.temp_heater = IndicatorWidget("Heater temperature")
        layout.addWidget(self.temp_heater, 3, 0)
        self.temp_drainage = IndicatorWidget("Drainage temperature")
        layout.addWidget(self.temp_drainage, 4, 0)
        self.temp_cabin = IndicatorWidget("Cabin temperature")
        layout.addWidget(self.temp_cabin, 0, 1)

        # flow indicators
        self.flow_cpc = IndicatorWidget("CPC inlet flow")
        layout.addWidget(self.flow_cpc, 1, 1)
        self.flow_saturator = IndicatorWidget("Saturator flow")
        layout.addWidget(self.flow_saturator, 2, 1)
        self.flow_excess = IndicatorWidget("Excess flow") # TODO change name to heater flow?
        layout.addWidget(self.flow_excess, 3, 1)
        self.flow_inlet = IndicatorWidget("Inlet flow")
        layout.addWidget(self.flow_inlet, 4, 1)
        if device_type == PSM2: # if PSM 2.0, add vacuum flow indicator
            self.flow_vacuum = IndicatorWidget("Vacuum flow")
            layout.addWidget(self.flow_vacuum, 4, 2)

        # pressure indicators
        self.pressure_inlet = IndicatorWidget("Inlet pressure")
        layout.addWidget(self.pressure_inlet, 0, 2)
        if device_type == PSM: # if PSM, add critical orifice pressure indicator
            self.pressure_critical_orifice = IndicatorWidget("Critical orifice pressure")
            layout.addWidget(self.pressure_critical_orifice, 1, 2)
        elif device_type == PSM2: # if PSM 2.0, add vacuum line pressure indicator
            # TODO name variable accordingly?
            self.pressure_critical_orifice = IndicatorWidget("Vacuum line pressure")
            layout.addWidget(self.pressure_critical_orifice, 1, 2)

        # liquid level indicators
        self.liquid_saturator = IndicatorWidget("Saturator liquid level")
        layout.addWidget(self.liquid_saturator, 2, 2)
        self.liquid_drain = IndicatorWidget("Drain liquid level")
        layout.addWidget(self.liquid_drain, 3, 2)

        self.setLayout(layout)

class PSMMeasureTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create layout

        # scan mode widgets
        self.scan = StartButton("Scan")
        layout.addWidget(self.scan, 0, 0)
        self.set_minimum_flow = SetWidget("Minimum flow", " lpm")
        self.set_minimum_flow.value_spinbox.setValue(0.05)
        layout.addWidget(self.set_minimum_flow, 1, 0)
        self.set_max_flow = SetWidget("Maximum flow", " lpm")
        self.set_max_flow.value_spinbox.setValue(1.9)
        layout.addWidget(self.set_max_flow, 2, 0)
        self.set_scan_time = SetWidget("Scan time", " s", integer=True)
        self.set_scan_time.value_spinbox.setValue(240)
        layout.addWidget(self.set_scan_time, 3, 0)

        # step mode widgets
        self.step = StartButton("Step")
        layout.addWidget(self.step, 0, 1)
        self.step_time = SetWidget("Step time", " s", integer=True)
        self.step_time.value_spinbox.setValue(30)
        layout.addWidget(self.step_time, 1, 1)
        self.steps = StepsWidget()
        self.steps.text_box.setText("0.1\n0.7\n1.3\n1.9")
        layout.addWidget(self.steps, 2, 1, 2, 1)

        # fixed mode widgets
        self.fixed = StartButton("Fixed")
        layout.addWidget(self.fixed, 0, 2)
        self.set_flow = SetWidget("Saturator flow", " lpm")
        self.set_flow.value_spinbox.setValue(1.9)
        layout.addWidget(self.set_flow, 1, 2)

        # 10 hz logging button
        self.ten_hz = StartButton("10 Hz logging")
        layout.addWidget(self.ten_hz, 4, 0, 1, 3)
        # set button size policy to minimum
        self.ten_hz.setSizePolicy(QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum))

        self.setLayout(layout)
    
    def compile_scan(self): # compile scan command
        scan_time = self.set_scan_time.value_spinbox.value()
        if scan_time % 2 == 0: # if scan time is even
            time = int((scan_time - 20) / 2)
            parameters = [10, time, 10, time]
        else: # if scan time is odd
            time = int((scan_time - 21) / 2)
            parameters = [11, time, 10, time]
        # add minimum flow to parameters
        parameters.append(round(self.set_minimum_flow.value_spinbox.value(), 3))
        # add maximum flow to parameters
        parameters.append(round(self.set_max_flow.value_spinbox.value(), 3))
        scan_string = ":SET:FLOW:SCAN " + ",".join(map(str, parameters))
        print(scan_string)
        return scan_string
    
    def compile_step(self): # compile step command
        step_list = self.steps.text_box.toPlainText().split("\n") # get list of steps
        while "" in step_list:
            step_list.remove("") # remove empty rows
        error_flag = False
        self.steps.text_box.clear()
        self.steps.text_box.setTextColor(self.steps.default_color)
        for step in step_list: # remove non-float values from list
            try:
                float(step) # check if float
                self.steps.text_box.append(step)
            except ValueError:
                # write rows containing errors with red text
                self.steps.text_box.setTextColor(QColor(255, 0, 0))
                self.steps.text_box.append(step)
                self.steps.text_box.setTextColor(self.steps.default_color)
                error_flag = True # set error flag
        if error_flag: # if there are errors
            return None
        else:
            step_amount = len(step_list)
            step_times = [self.step_time.value_spinbox.value()] * step_amount
            step_string = ":SET:FLOW:STEP " + str(step_amount) + "," + ",".join(map(str, step_times)) + "," + ",".join(map(str, step_list))
            return step_string

    def compile_fixed(self): # compile fixed command
        # append saturator flow value to command
        fixed_string = ":SET:FLOW:FXD " + str(round(self.set_flow.value_spinbox.value(), 3))
        return fixed_string
    
    # change color of active mode
    def change_mode_color(self, command):
        # TODO only update if command is different from current
        if command == ":MEAS:SCAN":
            self.scan.change_color(1)
            self.step.change_color(0)
            self.fixed.change_color(0)
        if command == ":MEAS:STEP":
            self.scan.change_color(0)
            self.step.change_color(1)
            self.fixed.change_color(0)
        if command == ":MEAS:FIXD":
            self.scan.change_color(0)
            self.step.change_color(0)
            self.fixed.change_color(1)

# used in PSMMeasureTab
class StepsWidget(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        layout = QVBoxLayout()
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        label = QLabel("Steps (lpm)", objectName="label")
        label.setFont(font)
        label.setAlignment(Qt.AlignCenter) # center label
        self.text_box = FloatTextEdit(objectName="text_edit")
        self.default_color = self.text_box.palette().color(QPalette.Text) # get default text color
        self.text_box.setFont(font)
        # add widgets to layout
        layout.addWidget(label)
        layout.addWidget(self.text_box)
        self.setLayout(layout)

# used in StepsWidget
class FloatTextEdit(QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # override keyPressEvent to only allow certain keys
        self.allowed_keys = [Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, 
                        Qt.Key_Home, Qt.Key_End, Qt.Key_Period, Qt.Key_Return, Qt.Key_Enter,
                        Qt.Key_0, Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5, Qt.Key_6,
                        Qt.Key_7, Qt.Key_8, Qt.Key_9]
    def keyPressEvent(self, event):
        if event.key() in self.allowed_keys:
            super().keyPressEvent(event)

# Electrometer widget
class ElectrometerWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for Electrometer
        self.plot_tab = ElectrometerPlot()
        self.addTab(self.plot_tab, "Electrometer plot")

# CO2 widget
class CO2Widget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for CO2
        self.plot_tab = SinglePlot(device_type=CO2_sensor)
        self.addTab(self.plot_tab, "CO2 plot")

# RHTP widget
class RHTPWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for RHTP
        self.plot_tab = TriplePlot(device_type=RHTP)
        self.addTab(self.plot_tab, "RHTP plot")

# AFM widget
class AFMWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for AFM
        self.plot_tab = AFMPlot()
        self.addTab(self.plot_tab, "AFM plot")

# eDiluter widget
class eDiluterWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        self.current_mode = None # used for storing current mode
        # create set tab for eDiluter
        self.set_tab = eDiluterSetTab()
        self.addTab(self.set_tab, "Set")
        # create status tab for eDiluter
        self.status_tab = eDiluterStatusTab()
        self.addTab(self.status_tab, "Status")
        # create plot widget for eDiluter
        self.plot_tab = SinglePlot(device_type=eDiluter)
        self.addTab(self.plot_tab, "eDiluter plot")
        # create dictionary with mode names and corresponding widgets
        self.mode_dict = {"INIT": self.set_tab.init, "WARMUP": self.set_tab.warmup,
                          "STANDBY": self.set_tab.standby, "MEASUREMENT": self.set_tab.measurement}
    
    # update all data values in status tab and set tab
    # current list: Status, P1, P2, T1, T2, T3, T4, T5, T6, DF1, DF2, DFTot
    def update_values(self, current_list):
        # update temperature values
        self.status_tab.t1.change_value(str(current_list[3]) + " °C")
        self.status_tab.t2.change_value(str(current_list[4]) + " °C")
        self.status_tab.t3.change_value(str(current_list[5]) + " °C")
        self.status_tab.t4.change_value(str(current_list[6]) + " °C")
        self.status_tab.t5.change_value(str(current_list[7]) + " °C")
        self.status_tab.t6.change_value(str(current_list[8]) + " °C")
        # update pressure values
        self.status_tab.p1.change_value(str(current_list[1]) + " mbar")
        self.status_tab.p2.change_value(str(current_list[2]) + " mbar")
        # update dilution factor values
        self.set_tab.df_1.indicator.change_value(str(current_list[9]))
        self.set_tab.df_2.indicator.change_value(str(current_list[10]))
        self.set_tab.df_tot.change_value(str(current_list[11])) # total DF in set tab
        self.status_tab.df_tot.change_value(str(current_list[11])) # total DF in status tab
        # change color of active mode if it differs from current mode
        if current_list[0] != self.current_mode:
            # change color of all mode buttons to default
            for mode in self.mode_dict:
                self.mode_dict[mode].change_color(0)
            # if current mode is not nan
            if str(current_list[0]) != "nan":
                # change color of active mode button
                self.mode_dict[current_list[0]].change_color(1)
                self.current_mode = current_list[0] # update current mode

# TSI CPC widget
class TSIWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for TSI CPC
        self.plot_tab = SinglePlot(device_type=CPC)
        self.addTab(self.plot_tab, "TSI CPC plot")

# Example device widget
class ExampleDeviceWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for CO2
        self.plot_tab = SinglePlot(device_type=Example_device)
        self.addTab(self.plot_tab, "Example device plot")

class eDiluterSetTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QVBoxLayout() # create vertical layout

        # horizontal layout for mode settings
        # INIT, WARMUP, STANDBY, MEASUREMENT
        mode_layout = QHBoxLayout()
        self.init = StartButton("Init")
        mode_layout.addWidget(self.init)
        self.warmup = StartButton("Warmup")
        mode_layout.addWidget(self.warmup)
        self.standby = StartButton("Standby")
        mode_layout.addWidget(self.standby)
        self.measurement = StartButton("Measurement")
        mode_layout.addWidget(self.measurement)
        layout.addLayout(mode_layout) # add mode_layout to main vertical layout

        # horizontal layout for dilution factor settings
        df_layout = QHBoxLayout()
        self.df_1 = DFSetWidget("Dilution factor 1")
        df_layout.addWidget(self.df_1)
        self.df_2 = DFSetWidget("Dilution factor 2")
        df_layout.addWidget(self.df_2)
        self.df_tot = IndicatorWidget("Total dilution factor")
        df_layout.addWidget(self.df_tot)
        layout.addLayout(df_layout) # add df_layout to main vertical layout

        # add line edit for command input
        self.command_widget = CommandWidget("eDiluter")
        layout.addWidget(self.command_widget)

        self.setLayout(layout) # add layout to widget

class DFSetWidget(QWidget):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        layout = QHBoxLayout() # create horizontal layout

        # create previous button
        self.prev_button = QPushButton("<", objectName="button_widget")
        # create indicator widget for displaying name and value
        self.indicator = IndicatorWidget(name)
        # create next button
        self.next_button = QPushButton(">", objectName="button_widget")

        # add widgets to layout
        layout.addWidget(self.prev_button) # previous button
        layout.addWidget(self.indicator) # indicator widget
        layout.addWidget(self.next_button) # next button

        self.setLayout(layout) # add layout to widget

class eDiluterStatusTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create layout

        # temperature indicators (unit = °C)
        self.t1 = IndicatorWidget("Dilution air temperature") # T1
        layout.addWidget(self.t1, 0, 0)
        self.t2 = IndicatorWidget("Ext 1 temperature") # T2
        layout.addWidget(self.t2, 1, 0)
        self.t3 = IndicatorWidget("Ext 2 temperature") # T3
        layout.addWidget(self.t3, 2, 0)
        self.t6 = IndicatorWidget("Internal temperature") # T6
        layout.addWidget(self.t6, 0, 1)
        self.t4 = IndicatorWidget("Aux 1 temperature") # T4
        layout.addWidget(self.t4, 1, 1)
        self.t5 = IndicatorWidget("Aux 2 temperature") # T5
        layout.addWidget(self.t5, 2, 1)

        # pressure indicators (unit = mbar)
        self.p1 = IndicatorWidget("Inlet pressure") # P1
        layout.addWidget(self.p1, 0, 2)
        self.p2 = IndicatorWidget("Ambient pressure") # P2
        layout.addWidget(self.p2, 1, 2)

        # dilution factor indicator
        self.df_tot = IndicatorWidget("Total dilution factor") # DFTot
        layout.addWidget(self.df_tot, 2, 2)
        
        self.setLayout(layout) # set layout

# set tab widget containing settings and message input
# used in CPCWidget
class CPCSetTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create grid layout

        self.set_saturator_temp = SetWidget("Saturator temperature", " °C")
        layout.addWidget(self.set_saturator_temp, 0, 0)
        self.set_condenser_temp = SetWidget("Condenser temperature", " °C")
        layout.addWidget(self.set_condenser_temp, 0, 1)
        self.set_averaging_time = SetWidget("Averaging time", " s")
        layout.addWidget(self.set_averaging_time, 0, 2)
        
        self.autofill = ToggleButton("Autofill")
        layout.addWidget(self.autofill, 1, 0)
        self.water_removal = ToggleButton("Water removal")
        layout.addWidget(self.water_removal, 1, 1)
        self.drain = ToggleButton("Drain")
        layout.addWidget(self.drain, 1, 2)
        
        # add line edit for command input
        self.command_widget = CommandWidget("CPC")
        layout.addWidget(self.command_widget, 2, 0, 1, 3)

        layout.setRowStretch(0, 1) # set stretch factor of row 0
        layout.setRowStretch(1, 1) # set stretch factor of row 1
        layout.setRowStretch(2, 2) # set stretch factor of row 2

        self.setLayout(layout) # add layout to widget

# used in CPCSetTab and PSMSetTab
class CommandWidget(QWidget):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()
        layout = QVBoxLayout()
        label = QLabel("Send serial command message to " + device_type, objectName="label")
        self.command_input = QLineEdit(objectName="line_edit")
        self.command_input.setPlaceholderText("Enter command")
        self.text_box = QTextEdit(readOnly=True, objectName="text_edit")
        # add widgets to layout
        layout.addWidget(label)
        layout.addWidget(self.command_input)
        layout.addWidget(self.text_box)
        self.setLayout(layout)

    def update_text_box(self, text):
        time_stamp = dt.now().strftime("%d.%m.%Y %H:%M:%S - ") # get time stamp
        self.text_box.append(time_stamp + text) # append text box with time stamp and text

# used in CPCSetTab and PSMSetTab
class SetWidget(QWidget):
    def __init__(self, name, suffix, *args, integer=False, **kwargs):
        super().__init__()
        layout = QVBoxLayout()
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        # create label for widget name
        self.name = name
        name_label = QLabel(self.name, objectName="label")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setFont(font) # apply font to label
        layout.addWidget(name_label)
        # create normal / double spin box for setting value
        self.is_integer = integer
        if integer: # if value is integer, use spin box (int)
            self.value_spinbox = SpinBox(objectName="spin_box", maximum=9999)
            validator = QIntValidator() # create int validator
        else: # if not integer, use double spin box (float)
            if "decimals" in kwargs: # if decimals are specified in kwargs
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999, decimals=kwargs["decimals"])
            else:
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999)
            locale = QLocale(QLocale.C) # create locale to use dot as decimal separator
            validator = QDoubleValidator() # create double validator 
            validator.setLocale(locale) # set validator locale
            self.value_spinbox.setLocale(locale) # set spinbox locale
        self.value_spinbox.setSuffix(suffix) # set suffix
        self.value_spinbox.lineEdit().setReadOnly(True) # make line edit read only
        self.value_spinbox.lineEdit().setAlignment(Qt.AlignCenter) # align text in line edit
        layout.addWidget(self.value_spinbox) # add widget to layout
        # add line edit for value input
        self.value_input = QLineEdit(objectName="line_edit")
        self.value_input.setPlaceholderText("Enter value")
        self.value_input.setValidator(validator) # set validator, only allow int or float
        self.value_input.returnPressed.connect(self.value_input_return_pressed)
        layout.addWidget(self.value_input)
        # set layout
        self.setLayout(layout)
        # store default stylesheet
        self.stylesheet = self.styleSheet()
        # create error variable for storing error state
        self.error = False
    # function that handles value text input
    def value_input_return_pressed(self):
        value = self.value_input.text()
        try:
            if self.is_integer:
                self.value_spinbox.setValue(int(value))
            else:
                self.value_spinbox.setValue(float(value))
        except Exception as e:
            print(e)
        QTimer.singleShot(50, self.clear_input)
    # function that clears value input line edit after single shot timer
    def clear_input(self):
        self.value_input.clear()
    def set_red_color(self):
        if self.error == False:
            self.value_spinbox.setStyleSheet("QDoubleSpinBox { background-color : red }")
            self.error = True
    def set_default_color(self):
        if self.error == True:
            self.value_spinbox.setStyleSheet(self.stylesheet)
            self.error = False

# custom spin box class with signal for value change
# https://stackoverflow.com/questions/47874952/qspinbox-signal-for-arrow-buttons
class SpinBox(QSpinBox):
    stepChanged = pyqtSignal(int)
    # override stepBy function to emit signal when value changes
    def stepBy(self, step):
        value = self.value()
        super(SpinBox, self).stepBy(step)
        if self.value() != value:
            self.stepChanged.emit(self.value())

class DoubleSpinBox(QDoubleSpinBox):
    stepChanged = pyqtSignal(float)
    # override stepBy function to emit signal when value changes
    def stepBy(self, step):
        value = self.value()
        super(DoubleSpinBox, self).stepBy(step)
        if self.value() != value:
            self.stepChanged.emit(self.value())

class ToggleButton(QPushButton):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        self.name = name
        self.state = 0
        # create specific command messages for drying toggle
        if self.name == "Drying":
            self.messages = {0: ":SET:RUN", 1: ":SET:DRY"}
        self.setObjectName("button_widget")
        self.setCheckable(True)
        self.clicked.connect(self.toggle)
        self.setText(self.name)
        self.stylesheet = self.styleSheet() # save default stylesheet
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        self.setFont(font) # apply font
        # set size policy to expanding
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toggle() # toggle button to set initial state
    
    def toggle(self):
        if self.isChecked(): # if button is checked
            self.setText(self.name + "\nON")
            self.setStyleSheet("QPushButton { background-color : green }")
            self.state = 1
        else: # if button is not checked
            self.setText(self.name + "\nOFF")
            self.setStyleSheet(self.stylesheet)
            self.state = 0

    def update_state(self, state):
        # if received state is different from current state
        if state != self.state:
            if str(state) == 'nan': # if state is nan
                return # do nothing
            self.setChecked(int(state)) # set button checked state
            self.toggle() # toggle button

class StartButton(QPushButton):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        self.name = name
        self.state = 0
        self.setObjectName("button_widget")
        self.setText(self.name)
        self.stylesheet = self.styleSheet() # save default stylesheet
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        self.setFont(font) # apply font
        # set size policy to expanding
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def change_color(self, state):
        if state != self.state:
            if state == 1: # if this measure mode is on
                self.setStyleSheet("QPushButton { background-color : green }")
                self.state = 1
            else: # if this measure mode is off
                self.setStyleSheet(self.stylesheet)
                self.state = 0

# status tab containing status indicator widgets
# used in CPCWidget
class CPCStatusTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create layout

        # temperature indicators
        self.temp_optics = IndicatorWidget("Optics temperature") # create optics temperature indicator
        layout.addWidget(self.temp_optics, 1, 0)
        self.temp_saturator = IndicatorWidget("Saturator temperature") # create saturator temperature indicator
        layout.addWidget(self.temp_saturator, 2, 0)
        self.temp_condenser = IndicatorWidget("Condenser temperature") # create condenser temperature indicator
        layout.addWidget(self.temp_condenser, 3, 0)

        # pressure indicators
        self.pres_inlet = IndicatorWidget("Inlet pressure") # create inlet pressure indicator
        layout.addWidget(self.pres_inlet, 1, 1)
        self.pres_nozzle = IndicatorWidget("Nozzle pressure") # create nozzle pressure indicator
        layout.addWidget(self.pres_nozzle, 2, 1)
        self.pres_critical_orifice = IndicatorWidget("Critical orifice pressure") # create nozzle pressure indicator
        layout.addWidget(self.pres_critical_orifice, 3, 1)

        # misc indicators
        self.laser_power = IndicatorWidget("Laser power") # create laser power indicator
        layout.addWidget(self.laser_power, 1, 2)
        self.liquid_level = IndicatorWidget("Liquid level") # create liquid level indicator
        layout.addWidget(self.liquid_level, 2, 2)
        self.temp_cabin = IndicatorWidget("Cabin temperature") # create cabin temp indicator
        layout.addWidget(self.temp_cabin, 3, 2)

        self.setLayout(layout)

# status indicator widget
# used in CPCStatusTab and PSMStatusTab
class IndicatorWidget(QWidget):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        layout = QVBoxLayout() # create widget layout
        self.name = name # save name
        self.ok_error_indicators = ["Laser power", "Saturator liquid level", "Drain liquid level"]
        self.value_label = QLabel(self.name + "\n", objectName="label") # create value label

        self.default_color = self.value_label.styleSheet() # save default color

        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        self.value_label.setFont(font) # apply font to value label
        self.value_label.setAlignment(Qt.AlignCenter) # center label

        layout.addWidget(self.value_label) # add value label to layout
        self.setLayout(layout) # apply layout
    # change indicator value, called by main window's update_values function
    def change_value(self, value):
        self.value_label.setText(self.name + "\n" + value)
    # change background color of value, called by main window's update_errors function
    def change_color(self, bit):
        if int(bit) == 1: # if bit is 1 (error), set background color to red
            self.value_label.setStyleSheet("QLabel { background-color : red }")
            if self.name == "Laser power":
                self.change_value("ERROR")
            elif self.name == "Saturator liquid level":
                self.change_value("LOW")
            elif self.name == "Drain liquid level":
                self.change_value("HIGH")
        else: # if bit is 0 (no error), set background color to normal
            self.value_label.setStyleSheet(self.default_color)
            if self.name in self.ok_error_indicators:
                self.change_value("OK")

# widget showing measurement and saving status
# displayed under parameter tree
class StatusLights(QSplitter):
    def __init__(self, *args, **kwargs):
        super().__init__()
        font = self.font() # get current global font
        font.setPointSize(20) # set font size
        # create OK light widget
        self.error_light = QLabel(objectName="label")
        self.error_light.setFont(font) # apply font to label
        self.error_light.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter) # align text in center
        self.error_light.setAutoFillBackground(True) # automatically fill the background with color
        self.addWidget(self.error_light) # add widget to splitter
        # create saving light widget
        self.saving_light = QLabel(objectName="label")
        self.saving_light.setFont(font) # apply font to label
        self.saving_light.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.saving_light.setAutoFillBackground(True)
        self.addWidget(self.saving_light)
        # set relative sizes of widgets in splitter
        self.setSizes([100, 100])

    # set the color and text of ok light according to error flag, 1 = errors, 0 = no errors
    def set_error_light(self, flag):
        if flag == 1:
            self.error_light.setStyleSheet("QLabel { background-color : red }")
            self.error_light.setText("Error")
        else:
            self.error_light.setStyleSheet("QLabel { background-color : green }")
            self.error_light.setText("OK")
    # set the color and text of saving light, 1 = saving, 0 = saving off
    def set_saving_light(self, flag):
        if flag == 1:
            self.saving_light.setStyleSheet("QLabel { background-color : green }")
            self.saving_light.setText("Saving")
        else:
            self.saving_light.setStyleSheet("QLabel { background-color : red }")
            self.saving_light.setText("Saving off")

# application format
if __name__ == '__main__': # protects from accidentally invoking the script when not intended
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()