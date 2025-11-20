from pyqtgraph.parametertree import Parameter, ParameterTree, parameterTypes
from config import (CPC, PSM, ELECTROMETER, CO2_SENSOR, RHTP, EDILUTER, PSM2, TSI_CPC, AFM, EXAMPLE_DEVICE, save_path, osx_mode)
from serial_connection import SerialDeviceConnection
from com_port_widget import ComPortParameter

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
        self.rhtp_dict = {'None': 'None'}
        self.cached_ports = {}  # Cache available ports for new devices
        self.cached_port_statuses = {}  # Cache port statuses
        self.cached_port_info = {}  # Cache port info
        # update cpc_dict and rhtp_dict when device is removed
        self.sigChildRemoved.connect(self.update_cpc_dict)
        self.sigChildRemoved.connect(self.update_rhtp_dict)

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
        child = self.addChild({'name': device_name, 'removable': True, 'type': 'group', 'children': [
                dict(name="Device nickname", type='str', value="", renamable=True),
                dict(name="COM port", type='comport', ports=self.cached_ports, port_statuses=self.cached_port_statuses, port_info=self.cached_port_info),
                dict(name="Serial number", type='str', value="", readonly=True),
                #dict(name="Baud rate", type='int', value=115200, visible=False),
                dict(name = "Connection", value = SerialDeviceConnection(), visible=False),
                {'name': 'Device type', 'type': 'list', 'values': {"CPC": CPC, "PSM Retrofit": PSM, "PSM 2.0": PSM2, "Electrometer": ELECTROMETER, "CO2 sensor": CO2_SENSOR, "RHTP": RHTP, "AFM": AFM, "eDiluter": EDILUTER, "TSI CPC": TSI_CPC, "Example device": -1}, 'value': device_value, 'readonly': True, 'visible': False},
                dict(name = "Connected", type='bool', value=False, readonly = True),
                dict(name = "DevID", type='int', value=self.n_devices,readonly = True, visible = False),
                dict(name = "Plot to main", type='bool', value=True),
                ]})

        self.n_devices += 1 # increase device counter

        # Update the COM port dropdown for the newly added device with cached data
        if self.cached_ports:
            new_device = self.children()[-1]
            com_port_param = new_device.child('COM port')
            if com_port_param and hasattr(com_port_param, 'set_available_ports'):
                com_port_param.set_available_ports(self.cached_ports, self.cached_port_statuses, self.cached_port_info)

            # Connect signal to update status when port is selected
            if com_port_param:
                com_port_param.sigValueChanged.connect(self.on_com_port_selected)

        # if added device is CPC, update cpc_dict
        if device_value in [CPC, TSI_CPC]:
            self.update_cpc_dict()
            # if Airmodus CPC, add hidden 10 hz parameter
            # when 10 hz is True, OPC concentration is polled
            if device_value == CPC:
                self.children()[-1].addChild({'name': '10 hz', 'type': 'bool', 'value': False, 'readonly': True, 'visible': False})
                # Add database-related parameters for CPC (hidden - controlled via ACTRIS tab)
                self.children()[-1].addChild({'name': 'Database enabled', 'type': 'bool', 'value': False, 'visible': False})
                self.children()[-1].addChild({'name': 'Linked RHTP', 'type': 'list', 'values': self.rhtp_dict, 'value': 'None', 'visible': False})
                self.children()[-1].addChild({'name': 'DB averaging interval', 'type': 'list', 'values': ['1 minute', '5 minutes', '10 minutes', '15 minutes', '1 hour', '3 hours'], 'value': '1 minute', 'visible': False})

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
            # add calibration file path parameter for contour plot
            self.children()[-1].addChild({'name': 'Calibration file path', 'type': 'str', 'value': '', 'visible': False})
        
        # if added device is RHTP, add options for plotted value
        if device_value == RHTP:
            self.update_rhtp_dict()
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

    def on_com_port_selected(self, param):
        """
        Called when a COM port is selected from the dropdown.
        Updates the port status and refreshes all dropdowns.
        """
        # Reset all port statuses to available first (except those actually in use by the system)
        for port in self.cached_port_statuses:
            if self.cached_port_statuses[port] not in ['in_use', 'error', 'permission_denied']:
                self.cached_port_statuses[port] = 'available'

        # Check all devices to update port statuses based on their selections
        for device in self.children():
            com_port_param = device.child('COM port')
            if com_port_param and com_port_param.value():
                port_value = com_port_param.value()
                # Skip if it's the placeholder value
                if port_value and port_value != 'Select port...':
                    # Mark this port as connected (reserved for this device)
                    if port_value in self.cached_port_statuses:
                        self.cached_port_statuses[port_value] = 'connected'

        # Update all dropdowns with new status
        for device in self.children():
            com_port_param = device.child('COM port')
            if com_port_param and hasattr(com_port_param, 'set_available_ports'):
                # Preserve the current selection
                current_value = com_port_param.value()
                com_port_param.set_available_ports(
                    self.cached_ports,
                    self.cached_port_statuses,
                    self.cached_port_info
                )
                # Restore the selection if it was valid
                if current_value:
                    com_port_param.setValue(current_value)

    def update_rhtp_dict(self):
        """Update rhtp_dict with current RHTP devices."""
        self.rhtp_dict = {'None': 'None'}  # reset rhtp_dict
        # add device name to rhtp_dict if device is RHTP
        for device in self.children():
            if device.child('Device type').value() == RHTP:
                # check if device has a nickname
                if device.child('Device nickname').value() != "":
                    self.rhtp_dict[device.child('Device nickname').value()] = device.child('DevID').value()
                else:  # if no nickname, use device parameter name (device type and serial number)
                    self.rhtp_dict[device.name()] = device.child('DevID').value()
        # update Linked RHTP parameter for all CPC devices
        for device in self.children():
            if device.child('Device type').value() == CPC:
                if device.child('Linked RHTP') is not None:
                    # store current value (ID) of Linked RHTP parameter
                    current_rhtp = device.child('Linked RHTP').value()
                    # remove Linked RHTP parameter
                    device.removeChild(device.child('Linked RHTP'))
                    # add updated Linked RHTP parameter (hidden - only visible in ACTRIS tab)
                    device.addChild({'name': 'Linked RHTP', 'type': 'list', 'values': self.rhtp_dict, 'visible': False})
                    # set Linked RHTP parameter to previous value if it is still in the list
                    if current_rhtp in self.rhtp_dict.values():
                        device.child('Linked RHTP').setValue(current_rhtp)
                    else:
                        device.child('Linked RHTP').setValue('None')

    def update_com_port_dropdowns(self, available_ports_dict, port_statuses=None, port_info=None):
        """
        Update COM port selector dropdown values for all devices with status indicators.

        Args:
            available_ports_dict: Dictionary {port: description} from data_holder.com_descriptions
            port_statuses: Optional dict {port: status} with status info
            port_info: Optional dict {port: {device_type, serial_number, etc}} with additional info
        """
        # Build dropdown values dict: {"COM3 - Description": "COM3"}
        if available_ports_dict:
            port_values = {f"{port} - {desc}": port for port, desc in sorted(available_ports_dict.items())}
            # Add default "Select port..." option at the beginning
            port_values = {'Select port...': None, **port_values}
        else:
            port_values = {'No ports available': None}

        # Cache the port data for new devices
        self.cached_ports = port_values
        self.cached_port_statuses = port_statuses or {}
        self.cached_port_info = port_info or {}

        # Update all device COM port dropdowns
        for device in self.children():
            com_port_param = device.child('COM port')
            if com_port_param is not None and hasattr(com_port_param, 'set_available_ports'):
                # Check if this device has a port selected
                current_port = com_port_param.value()
                if port_statuses and current_port and current_port in port_statuses:
                    # Mark as connected if a port is selected for this device
                    port_statuses[current_port] = 'connected'

                # Update the available ports in the combined widget with status info
                com_port_param.set_available_ports(port_values, port_statuses, port_info)

                # Connect signal if not already connected
                try:
                    com_port_param.sigValueChanged.disconnect(self.on_com_port_selected)
                except:
                    pass  # Not connected
                com_port_param.sigValueChanged.connect(self.on_com_port_selected)

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
        # Update serial ports button removed - continuous monitoring is now automatic
    ]},

    ScalableGroup(name="Device settings", children=[
        # devices will be added here
    ]),
]

# Create tree of Parameter objects
p = Parameter.create(name='params', type='group', children=params)

__all__ = ['ScalableGroup', 'params', 'p'] 
