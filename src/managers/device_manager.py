# managers/device_manager.py
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon
from time import time
import traceback
from serial.tools import list_ports
from serial import Serial
import logging
from numpy import full, nan, isnan, array_equal
from serial.serialutil import SerialException
from config import *
from utils import (
    compile_cpc_settings,
    compile_psm_settings
)

class DeviceManager:
    def __init__(self, params, data_holder, device_widgets, device_tabs=None):
        self.params = params
        self.data_holder = data_holder
        self.device_widgets = device_widgets
        self.device_tabs = device_tabs  # Reference to MainWindow.device_tabs for error icon updates
        self.osx_mode = osx_mode  

    def connection_test(self):
        """Check and manage device connections, update states."""
        # Note: list_com_ports is still in MainWindow; delegate if needed or move here later
        com_port_list = self.list_com_ports()  # Temp: access via params if MainWindow ref added, or pass as arg
        self.data_holder.device_errors = {key: False for key in self.data_holder.device_errors}
        
        for dev in self.params.child('Device settings').children():
            if dev.child('Device type').value() == EXAMPLE_DEVICE:
                if not self.data_holder.first_connection:
                    self.data_holder.first_connection = True
            
            connected = dev.child('Connected').value()
            if self.osx_mode:
                port = str(dev.child('COM port').value())
            else:
                port = "COM" + str(dev.child('COM port').value())
            
            if connected and port not in com_port_list:
                try:
                    dev.child('Connection').value().close()
                except Exception as e:
                    logging.error(traceback.format_exc())
            connected = False
            
            try:
                if hasattr(dev.child('Connection').value(), 'connection') and dev.child('Connection').value().connection.is_open:
                    connected = True
                else:
                    dev.child('Connection').value().connect()
                    if dev.child('Connection').value().connection.is_open:
                        connected = True
            except AttributeError:
                try:
                    dev.child('Connection').value().set_port(port)
                    dev.child('Connection').value().connect()
                    if dev.child('Connection').value().connection.is_open:
                        connected = True
                except Exception:
                    pass
            except Exception:
                pass
            
            # IDN inquiry and updates
            dev_type = dev.child('Device type').value()
            dev_id = dev.child('DevID').value()
            if dev_type in [CPC, PSM, PSM2, CO2_SENSOR, RHTP, AFM]:
                if connected and not dev.child('Connected').value():
                    if dev_id not in self.data_holder.idn_inquiry_devices:
                        self.data_holder.idn_inquiry_devices.append(dev_id)
                    if dev_type in [PSM, PSM2]:
                        dev.child('Firmware version').setValue("")
                        if dev_id in self.data_holder.psm_dilution:
                            del self.data_holder.psm_dilution[dev_id]
                    if dev_type in [CPC, PSM, PSM2, EDILUTER]:
                        if dev_id in self.device_widgets:
                            self.device_widgets[dev_id].setObjectName("connected")
                            self.device_widgets[dev_id].setStyleSheet("")
            
            if dev_type in [CPC, PSM, PSM2, EDILUTER]:
                if not connected and dev.child('Connected').value():
                    if dev_id in self.device_widgets:
                        self.device_widgets[dev_id].set_tab.command_widget.update_text_box("Device disconnected.")
                        self.device_widgets[dev_id].setObjectName("disconnected")
                        self.device_widgets[dev_id].setStyleSheet("")
            
            dev.child('Connected').setValue(connected)
            if not self.data_holder.first_connection:
                self.data_holder.first_connection = connected

    def list_com_ports(self):
        """
        Scan and list available serial COM ports, update descriptions,
        inquire device identities for new ports, and manage connection states.
        """
        # get list of current available serial ports as ListPortInfo objects
        ports = list_ports.comports()
        com_port_list = [] # list of current port device names (like 'COM3')
        new_ports = {} # dictionary of new identified ports with active connections

        # go over sorted ports by device name
        for port in sorted(ports, key=lambda p: p.device):
            com_port_list.append(port.device)

            # add new port description if not previously known
            if port.device not in self.data_holder.com_descriptions:
                self.data_holder.com_descriptions[port.device] = port.description

            # if inquiry flag is set, inquire identity from ports not yet identified
            # (if port has a default desc so it's not yet been acquired)
            if self.data_holder.inquiry_flag and self.data_holder.com_descriptions[port.device] == port.description:
                try:
                    # attempt to open port with timeout and baud rate (throughput as bits per second)
                    serial_connection = Serial(str(port.device), 115200, timeout=0.2)
                    # do device identity inquiry (delay makes sure device state init is done with ESP32)
                    self._idn_inquiry(serial_connection)
                    # store the serial connection for later usage with port name as the key
                    # new_ports dictionary is sent to update_com_ports after delay
                    new_ports[port.device] = serial_connection

                except SerialException:
                    # on failure try to update desc using device serial number from params
                    for dev in self.params.child('Device settings').children():
                        if osx_mode:
                            if port.device == dev.child('COM port').value():
                                # set description according to device's serial number parameter
                                self.data_holder.com_descriptions[port.device] = dev.child('Serial number').value()
                        else:
                            if port.device == 'COM' + str(dev.child('COM port').value()):
                                # set description according to device's serial number parameter
                                self.data_holder.com_descriptions[port.device] = dev.child('Serial number').value()
                except Exception as e:
                    # log unexpected errors while trying to inquire the device
                    print(traceback.format_exc())
                    logging.exception(e)

        # remove descriptions of ports that are no longer connected
        disconnected_ports = [p for p in self.data_holder.com_descriptions if p not in com_port_list]
        for port in disconnected_ports:
            self.data_holder.com_descriptions.pop(port)

        # if inquiry flag is True, check timeout
        # manage inquiry flag timeout after 3 seconds
        if self.data_holder.inquiry_flag and time() > self.data_holder.inquiry_time + 3:
            self.data_holder.inquiry_flag = False

        # schedule update_com_ports to process new ports after a short delay
        QTimer.singleShot(800, lambda: self.update_com_ports(new_ports, com_port_list)) # delay increased from 600 to 800

        # return list of current port device names
        return com_port_list
    
    def update_com_ports(self, new_ports, com_port_list):
        """
        Process new serial port connections to read device identity messages,
        update port descriptions, close connections, and refresh GUI display.
        """
        # Ensure all connections are properly closed after processing
        def close_connection(port, conn):
            try:
                if conn and conn.is_open:
                    conn.close()
            except Exception as e:
                logging.exception(f"Failed to close connection for {port}: {e}")
        # read messages from new_ports and update descriptions
        for port, serial_conn in list(new_ports.items()):
            try:
                # read available messages, decode and split messages by return char
                raw_data = serial_conn.read_all()
                if not raw_data: 
                    continue # no data available, skip to close

                messages = raw_data.decode('utf-8', errors='ignore').split('\r\n')
                print("update_com_ports -", port, "messages:", messages)

                for message in messages:
                    message = message.strip()
                    if len(message) <= 5: # message needs to be above 5 ("*IDN " + device IDN)
                        continue

                    # handle *IDN response for serial number
                    if message.startswith('*IDN '):
                        serial_number = message[5:].strip()
                        self.data_holder.com_descriptions[port] = serial_number
                        close_connection(port, serial_conn)
                        del new_ports[port]  # Remove after successful processing
                        break  # Assume one IDN response per inquiry

                    # handle eDiluter ID response
                    elif ' ID ' in message and ', Status' in message:
                        start_idx = message.index(' ID ') + 4
                        end_idx = message.index(', Status')
                        device_id = message[start_idx:end_idx].strip()
                        self.data_holder.com_descriptions[port] = device_id
                        close_connection(port, serial_conn)
                        del new_ports[port]  # Remove after successful processing
                        break  # Assume one ID response per inquiry

            except UnicodeDecodeError as e:
                logging.warning(f"Unicode decode error for {port}: {e}")
            except Exception as e:
                logging.exception(f"Error processing messages for {port}: {e}")

        # close any remaining open connections (like when no IDN response received)
        if not self.data_holder.inquiry_flag:
            for port, conn in list(new_ports.items()):
                close_connection(port, conn)
                del new_ports[port]

        # formatted text for connected ports only, sorted by port name
        connected_descriptions = {
            key: desc for key, desc in self.data_holder.com_descriptions.items()
            if key in com_port_list
        }
        sorted_ports = sorted(connected_descriptions.items())
        com_ports_text = '\n'.join(f"{port} - {desc}" for port, desc in sorted_ports)

        # update GUI 'Available serial ports' text box if com port list has changed
        current_value = self.params.child('Serial ports').child('Available serial ports').value()
        if com_ports_text != current_value:
            self.params.child('Serial ports').child('Available serial ports').setValue(com_ports_text)
            logging.debug(f"Updated GUI with new COM ports text:\n{com_ports_text}")


    def get_dev_data(self):
        """Send read commands to connected devices."""
        for dev in self.params.child('Device settings').children():
            if dev.child('Connected').value():
                dev_type = dev.child('Device type').value()
                dev_id = dev.child('DevID').value()
                dev_conn = dev.child('Connection').value()
                try:
                    if dev_type in [CPC, TSI_CPC]:
                        if dev_type == CPC and dev_id in self.data_holder.pulse_analysis_index:
                            if self.data_holder.pulse_analysis_index[dev_id] is not None:
                                threshold = PULSE_ANALYSIS_THRESHOLDS[self.data_holder.pulse_analysis_index[dev_id]]
                                dev_conn.send_pulse_analysis_messages(threshold)
                        elif dev_type == CPC and dev.child('10 hz').value():
                            dev_conn.send_multiple_messages(dev_type, ten_hz=True)
                        else:
                            dev_conn.send_multiple_messages(dev_type)
                    elif dev_type in [PSM, PSM2]:
                        if self.data_holder.psm_settings_updates[dev_id]:
                            dev_conn.send_message(":SYST:PRNT")
                        if dev_id not in self.data_holder.psm_dilution:
                            dev_conn.send_delayed_message(":SYST:VCMP", 150)
                    elif dev_type == ELECTROMETER:
                        dev_conn.connection.reset_input_buffer()
                        dev_conn.connection.reset_output_buffer()
                        dev_conn.connection.read_all()
                        dev_conn.send_message(":MEAS:V")
                    elif dev_type == CO2_SENSOR:
                        dev_conn.connection.reset_input_buffer()
                        dev_conn.connection.reset_output_buffer()
                        dev_conn.connection.read_all()
                        dev_conn.send_message(":MEAS:CO2")
                   
                    # Auto-push devices: IDN/firmware
                    if dev_type in [CPC, PSM, PSM2, CO2_SENSOR, RHTP, AFM]:
                        if dev_id in self.data_holder.idn_inquiry_devices:
                            self._idn_inquiry(dev_conn.connection)
                        elif dev_type in [PSM, PSM2]:
                            if dev.child('Firmware version').value() == "":
                                self._firmware_inquiry(dev_conn.connection)
                except Exception as e:
                    logging.error(traceback.format_exc())
 

    def _idn_inquiry(self, connection):
        """Delayed IDN send."""
        QTimer.singleShot(IDN_INQUIRY_DELAY_MS, lambda: connection.write(b'*IDN?\n'))

    def _firmware_inquiry(self, connection):
        """Delayed firmware send."""
        QTimer.singleShot(FIRMWARE_INQUIRY_DELAY_MS, lambda: connection.write(b':SYST:VER\n'))


    def readIndata(self):
        """
        Read data from all connected devices.

        This method is completely generic - it works for ALL device types without
        any device-specific if/elif clauses. Each device handles its own logic via:
        - device.handle_serial_data() - reads and parses serial data
        - device.process_parsed_messages() - processes results and updates state
        """
        for dev in self.params.child('Device settings').children():
            if dev.child('Connected').value():
                dev_id = dev.child('DevID').value()
                dev_conn = dev.child('Connection').value()
                widget = self.data_holder.device_widgets.get(dev_id)

                if not widget:
                    continue  # Skip if widget not found

                try:
                    # Step 1: Device reads and parses its serial data
                    parsed_messages = widget.handle_serial_data(dev_conn, self.data_holder)

                    # Step 2: Device processes parsed messages and updates state
                    result = widget.process_parsed_messages(parsed_messages, dev, self.data_holder)

                except Exception as e:
                    print(traceback.format_exc())
                    logging.exception(e)

    # check and update 10 hz settings
    def ten_hz_check(self):
        # go through devices
        for dev in self.params.child('Device settings').children():
            try:
                # if device is Airmodus CPC, set TAVG according to 10 hz parameter and check connection to PSM
                dev_type = dev.child('Device type').value()
                dev_id = dev.child('DevID').value()
                if dev_type == CPC:
                    if dev.child('10 hz').value():
                        if dev.child('Connected').value():
                            # if TAVG is not 0.1, set it to 0.1
                            cpc_settings = self.data_holder.get_device_settings(dev_id)
                            if cpc_settings and cpc_settings.averaging_time != 0.1:
                                dev.child('Connection').value().send_message(":SET:TAVG 0.1")
                        # check CPC connection to PSM with 10hz on
                        ten_hz_connected = any(
                            psm.child('Connected CPC').value() == dev_id and psm.child('10 hz').value()
                            for psm in self.params.child('Device settings').children()
                            if psm.child('Device type').value() in [PSM, PSM2]
                        )
                        if not ten_hz_connected:
                            dev.child('10 hz').setValue(False)
                        
                    # if 10 hz is off
                    else:
                        # if device is connected
                        if dev.child('Connected').value():
                            # if TAVG is smaller than 1, set it to 1
                            cpc_settings = self.data_holder.get_device_settings(dev_id)
                            if cpc_settings and cpc_settings.averaging_time < 1:
                                dev.child('Connection').value().send_message(":SET:TAVG 1")
                
                # if device is PSM and 10 hz is on, check if connected CPC has 10 hz on
                elif dev_type in [PSM, PSM2]:
                    if dev.child('10 hz').value():
                        cpc_id = dev.child('Connected CPC').value()
                        if cpc_id != 'None':
                            for cpc in self.params.child('Device settings').children():
                                # check if connected CPC is Airmodus CPC
                                if cpc.child('DevID').value() == cpc_id and cpc.child('Device type').value() == CPC:
                                        # if connected CPC has 10 hz off, set it on
                                    if not cpc.child('10 hz').value():
                                        cpc.child('10 hz').setValue(True)
                                    break
            except Exception as e:
                logging.error(traceback.format_exc())

    def update_error_icons(self):
        """Update tab error icons according to device error status."""
        if not self.device_tabs:
            return  # Skip if device_tabs not provided

        for dev in self.params.child('Device settings').children():
            try:
                device_id = dev.child('DevID').value()
                error = self.data_holder.device_errors[device_id]
                device_type = dev.child('Device type').value()
                device_widget = self.data_holder.device_widgets[device_id]
                tab_index = self.device_tabs.indexOf(device_widget)
                connected = dev.child('Connected').value()

                # Disconnected devices (except Example device)
                if not connected and device_type != EXAMPLE_DEVICE:
                    self.device_tabs.setTabIcon(tab_index, self.data_holder.disconnected_icon)
                    self.data_holder.error_status = 1
                # Devices with errors
                elif error:
                    self.device_tabs.setTabIcon(tab_index, self.data_holder.error_icon)
                    if device_type in [CPC, PSM, PSM2]:
                        status_tab_index = device_widget.indexOf(device_widget.status_tab)
                        device_widget.setTabIcon(status_tab_index, self.data_holder.error_icon)
                # Connected devices without errors
                else:
                    self.device_tabs.setTabIcon(tab_index, QIcon())
                    if device_type in [CPC, PSM, PSM2]:
                        status_tab_index = device_widget.indexOf(device_widget.status_tab)
                        device_widget.setTabIcon(status_tab_index, QIcon())

                # PSM-specific CO flow error check
                if device_type == PSM:
                    if device_widget.set_tab.set_co_flow.error:
                        self.device_tabs.setTabIcon(tab_index, self.data_holder.error_icon)
                        set_tab_index = device_widget.indexOf(device_widget.set_tab)
                        device_widget.setTabIcon(set_tab_index, self.data_holder.error_icon)
                    else:
                        set_tab_index = device_widget.indexOf(device_widget.set_tab)
                        device_widget.setTabIcon(set_tab_index, QIcon())
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

    def set_status_lights(self):
        """Set error and saving lights on status lights widget."""
        self.data_holder.status_lights.set_error_light(self.data_holder.error_status)
        self.data_holder.status_lights.set_saving_light(self.data_holder.saving_status)
