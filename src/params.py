from pyqtgraph.parametertree import Parameter, ParameterTree, parameterTypes
from config import (CPC, PSM, ELECTROMETER, CO2_SENSOR, RHTP, EDILUTER, PSM2, TSI_CPC, AFM, EXAMPLE_DEVICE, save_path, osx_mode)
from serial_connection import SerialDeviceConnection

# ScalableGroup for creating a menu where to set up new COM devices
class ScalableGroup(parameterTypes.GroupParameter):
    def __init__(self, **opts):
        #opts['type'] = 'action'
        opts['addText'] = "Add new device"
        # opts for choosing device type when adding new device
        opts["addList"] = ["CPC", "PSM Retrofit", "PSM 2.0", "Electrometer", "CO2 sensor", "RHTP", "AFM", "eDiluter", "TSI CPC", "Example device"]
        parameterTypes.GroupParameter.__init__(self, **opts)
        self.n_devices = 0
        self.cpc_dict = {'None': 'None'}
        # update cpc_dict when device is removed
        self.sigChildRemoved.connect(self.update_cpc_dict)

    def addNew(self, device_type, device_name=None): # device_type is the name of the added device type
        # device_value is used to set the default value for the Device type parameter below
        device_value = {"CPC": CPC, "PSM Retrofit": PSM, "PSM 2.0": PSM2, "Electrometer": ELECTROMETER, "CO2 sensor": CO2_SENSOR, "RHTP": RHTP, "AFM": AFM, "eDiluter": EDILUTER, "TSI CPC": TSI_CPC, "Example device": -1}[device_type]
        # if OSX mode is on, set COM port type as string to allow complex port addresses
        port_type = 'str' if osx_mode else 'int'
        # if device_name argument is not given, set device name according to device type
        if device_name == None:
            device_name = device_type
        # if device name is in use, add number to the end of the name
        if device_name in [child.name() for child in self.children()]:
            name_number = 1
            name_set = False
            while not name_set:
                name_number += 1
                if device_name + " (%d)" % (name_number) not in [child.name() for child in self.children()]:
                    device_name = device_name + " (%d)" % (name_number)
                    name_set = True
        # New types of devices should be added in the "Device type" list and given unique id number
        self.addChild({'name': device_name, 'removable': True, 'type': 'group', 'children': [
                dict(name="Device nickname", type='str', value="", renamable=True),
                dict(name="COM port", type=port_type),
                dict(name="Serial number", type='str', value="", readonly=True),
                #dict(name="Baud rate", type='int', value=115200, visible=False),
                dict(name = "Connection", value = SerialDeviceConnection(), visible=False),
                {'name': 'Device type', 'type': 'list', 'values': {"CPC": CPC, "PSM Retrofit": PSM, "PSM 2.0": PSM2, "Electrometer": ELECTROMETER, "CO2 sensor": CO2_SENSOR, "RHTP": RHTP, "AFM": AFM, "eDiluter": EDILUTER, "TSI CPC": TSI_CPC, "Example device": -1}, 'value': device_value, 'readonly': True, 'visible': False},
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
                self.children()[-1].addChild({'name': '10 hz', 'type': 'bool', 'value': False, 'readonly': True, 'visible': False})

        # if added device is PSM, add hidden parameters and option for 'Connected CPC'
        if device_value in [PSM, PSM2]:
            # if device is PSM Retrofit, add hidden CO flow parameter
            if device_value == PSM:
                self.children()[-1].addChild({'name': 'CO flow', 'type': 'str', 'visible': False})
            # add hidden 10 hz parameter for storing 10 hz status for startup
            self.children()[-1].addChild({'name': '10 hz', 'type': 'bool', 'value': False, 'readonly': True, 'visible': False})
            # add options for connected CPC
            self.children()[-1].addChild({'name': 'Connected CPC', 'type': 'list', 'values': self.cpc_dict, 'value': 'None'})
            # add cpc_changed flag to device
            self.children()[-1].cpc_changed = False
            # connect value change signal of Connected CPC to update_cpc_changed slot
            self.children()[-1].child('Connected CPC').sigValueChanged.connect(self.update_cpc_changed)
            # add firmware version parameter to index 3
            self.children()[-1].insertChild(3, {'name': 'Firmware version', 'type': 'str', 'value': "", 'readonly': True})
        
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
        
        # if added device is Example device, hide irrelevant parameters
        if device_value == EXAMPLE_DEVICE:
            self.children()[-1].child('COM port').setOpts(visible=False)
            self.children()[-1].child('Serial number').setOpts(visible=False)
            self.children()[-1].child('Connected').setOpts(visible=False)

    def update_cpc_dict(self):
        self.cpc_dict = {'None': 'None'} # reset cpc_dict
        # add device name to cpc_dict if device is CPC
        for device in self.children():
            if device.child('Device type').value() in [CPC, TSI_CPC]:
                # check if device has a nickname
                if device.child('Device nickname').value() != "":
                    self.cpc_dict[device.child('Device nickname').value()] = device.child('DevID').value()
                else: # if no nickname, use device parameter name (device type and serial number)
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
    {'name': 'Data settings', 'type': 'group', 'children': [
        {'name': 'File path', 'type': 'str', 'value': save_path},
        {'name': 'File tag', 'type': 'str', 'value': "", 'tip': "File name: YYYYMMDD_HHMMSS_(Serial number)_(Device type)_(Device nickname)_(File tag).dat"},
        {'name': 'Save data', 'type': 'bool', 'value': False},
        {'name': 'Generate daily files', 'type': 'bool', 'value': True, 'tip': "If on, new files are started at midnight."},
        {'name': 'Resume on startup', 'type': 'bool', 'value': False, 'tip': "Option to resume the last settings on startup."},
        {'name': 'Save settings', 'type': 'action'},
        {'name': 'Load settings', 'type': 'action'},
    ]},
    {'name': 'Plot settings', 'type': 'group', 'children': [
        {'name': 'Follow', 'type': 'bool', 'value': True},
        {'name': 'Time window (s)', 'type': 'int', 'value': 60},
        {'name': 'Autoscale Y', 'type': 'bool', 'value': True}
    ]},
    {'name': 'Serial ports', 'type': 'group', 'children': [
        {'name': 'Available serial ports', 'type': 'text', 'value': '', 'readonly': True},
        {'name': 'Update serial ports', 'type': 'action'},
    ]},
    
    ScalableGroup(name="Device settings", children=[
        # devices will be added here
    ]),
]

# Create tree of Parameter objects
p = Parameter.create(name='params', type='group', children=params)

__all__ = ['ScalableGroup', 'params', 'p'] 
