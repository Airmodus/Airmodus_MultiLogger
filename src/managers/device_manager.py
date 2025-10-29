# managers/device_manager.py
from PyQt5.QtCore import QTimer
from time import time
import traceback
from serial.tools import list_ports
from serial import Serial
import logging
from numpy import full, nan, isnan, array_equal
from serial.serialutil import SerialException
from config import * 
from utils import (
    compile_cpc_data,
    compile_cpc_settings,
    compile_psm_data,
    compile_psm_settings
)

class DeviceManager:
    def __init__(self, params, data_holder, device_widgets):
        self.params = params
        self.data_holder = data_holder
        self.device_widgets = device_widgets
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
        for dev in self.params.child('Device settings').children():
            if dev.child('Connected').value():
                # store device ID for convenience
                dev_id = dev.child('DevID').value()
                dev_type = dev.child('Device type').value() 
                dev_conn = dev.child('Connection').value()

                if dev_type == CPC: # CPC

                    # Get device widget for parsing
                    widget = self.data_holder.device_widgets[dev_id]

                    # Initialize from extra_data buffer
                    self.data_holder.latest_data[dev_id] = self.data_holder.extra_data.pop(dev_id, self.data_holder.get_default_data_array(dev_type))
                    prnt_list = self.data_holder.extra_data.pop(str(dev_id) + ":prnt", full(13, nan))
                    pall_list = self.data_holder.extra_data.pop(str(dev_id) + ":pall", full(28, nan))

                    # Handle 10 Hz data if enabled
                    if dev.child('10 hz').value():
                        self.data_holder.latest_ten_hz[dev_id] = self.data_holder.extra_data.pop(str(dev_id) + ":10hz", self.data_holder.latest_ten_hz[dev_id])

                    try:
                        readings = dev_conn.connection.read_all()
                        readings = readings.decode().split("\r")[:-1]  # decode, split messages, remove last empty

                        for message in readings:
                            # Parse message using device's parse_message method
                            parsed = widget.parse_message(message, self.data_holder)

                            # Handle based on parsed type
                            if parsed['type'] == 'data':
                                # Store measurement data
                                if isnan(self.data_holder.latest_data[dev_id][0]):
                                    self.data_holder.latest_data[dev_id] = parsed['data']
                                else:
                                    self.data_holder.extra_data[dev_id] = parsed['data']

                                # Set error flags
                                if parsed.get('total_errors', 0) != 0:
                                    self.data_holder.error_status = 1
                                    self.data_holder.device_errors[dev_id] = True

                            elif parsed['type'] == 'settings':
                                # Handle PRNT or PALL settings
                                if parsed['command'] == ':SYST:PRNT':
                                    if isnan(prnt_list[0]):
                                        prnt_list = parsed['data']
                                    else:
                                        self.data_holder.extra_data[str(dev_id)+":prnt"] = parsed['data']
                                elif parsed['command'] == ':SYST:PALL':
                                    if isnan(pall_list[0]):
                                        pall_list = parsed['data']
                                    else:
                                        self.data_holder.extra_data[str(dev_id)+":pall"] = parsed['data']

                            elif parsed['type'] == 'ten_hz':
                                # Handle 10 Hz logging data
                                if isnan(float(self.data_holder.latest_ten_hz[dev_id][0])):
                                    self.data_holder.latest_ten_hz[dev_id] = parsed['data']
                                else:
                                    self.data_holder.extra_data[str(dev_id)+":10hz"] = parsed['data']

                            elif parsed['type'] == 'self_test':
                                # Display self-test errors in command widget
                                widget.set_tab.command_widget.update_text_box(parsed['raw'])
                                widget.set_tab.command_widget.update_text_box("self test error binary: " + bin(int(parsed['data'], 16))[2:].zfill(len(CPC_ERRORS)))
                                for error_msg in parsed.get('errors', []):
                                    widget.set_tab.command_widget.update_text_box(error_msg)

                            elif parsed['type'] == 'info' and parsed['command'] == '*IDN':
                                # Handle device identification
                                widget.set_tab.command_widget.update_text_box(parsed['raw'])
                                serial_number = parsed['data']
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)
                                    self.params.child('Device settings').update_cpc_dict()
                                if dev_id in self.data_holder.idn_inquiry_devices:
                                    self.data_holder.idn_inquiry_devices.remove(dev_id)

                            # Show messages in command widget if requested
                            if parsed.get('show_in_command_widget', False):
                                widget.set_tab.command_widget.update_text_box(parsed['raw'])
                                if parsed['type'] == 'error' and 'error' in parsed:
                                    print("CPC error: " + str(parsed['error']))

                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)

                    # Update GUI with current data
                    widget.update_values(self.data_holder.latest_data[dev_id])
                    widget.update_settings(prnt_list)

                    # Compile and update settings if both PRNT and PALL are available
                    settings_update = (str(prnt_list[0]) != "nan" and str(pall_list[0]) != "nan")

                    # Skip settings update if pulse analysis is in progress
                    if dev_id in self.data_holder.pulse_analysis_index:
                        settings_update = False

                    if settings_update:
                        previous_settings = self.data_holder.latest_settings[dev_id]
                        settings = compile_cpc_settings(prnt_list, pall_list)

                        if not array_equal(settings, previous_settings, equal_nan=True):
                            self.data_holder.latest_settings[dev_id] = settings
                            self.data_holder.par_updates[dev_id] = 1
                        else:
                            self.data_holder.par_updates[dev_id] = 0
                    else:
                        self.data_holder.par_updates[dev_id] = 0
                
                if dev_type in [PSM, PSM2]: # PSM

                    # Get device widget for parsing
                    widget = self.data_holder.device_widgets[dev_id]

                    # Clear extra data buffer after 60 seconds of consecutive buffering
                    if dev_id in self.data_holder.extra_data and self.data_holder.extra_data_counter[dev_id] >= 60:
                        del self.data_holder.extra_data[dev_id]
                        logging.info("PSM %s extra data buffer cleared", dev.child('Serial number').value())

                    # Initialize from extra_data buffer
                    default_nan = self.data_holder.get_default_data_array(dev_type)
                    was_present = dev_id in self.data_holder.extra_data
                    self.data_holder.latest_data[dev_id] = self.data_holder.extra_data.pop(dev_id, default_nan)
                    if was_present:
                        self.data_holder.extra_data_counter[dev_id] += 1
                    else:
                        self.data_holder.extra_data_counter[dev_id] = 0

                    self.data_holder.par_updates[dev_id] = 0
                    settings_fetched = False

                    try:
                        readings = dev_conn.connection.read_all()
                        readings = readings.decode().split("\r")

                        # Handle partial messages
                        if dev_id in self.data_holder.partial_data:
                            readings[0] = self.data_holder.partial_data[dev_id] + readings[0]
                            del self.data_holder.partial_data[dev_id]

                        # Store/remove last message if partial/empty
                        if readings[-1] == "":
                            readings = readings[:-1]
                        else:
                            self.data_holder.partial_data[dev_id] = readings[-1]
                            readings = readings[:-1]

                        for message in readings:
                            # Parse message using device's parse_message method
                            parsed = widget.parse_message(message, self.data_holder)

                            # Handle based on parsed type
                            if parsed['type'] == 'data':
                                # Store measurement data
                                if isnan(float(self.data_holder.latest_data[dev_id][2])):
                                    self.data_holder.latest_data[dev_id] = parsed['data']
                                else:
                                    self.data_holder.extra_data[dev_id] = parsed['data']

                                # Store polynomial correction
                                self.data_holder.latest_poly_correction[dev_id] = parsed.get('poly_correction', 0.0)

                                # Set error flags
                                if parsed.get('has_errors', False):
                                    self.data_holder.error_status = 1
                                    self.data_holder.device_errors[dev_id] = True

                            elif parsed['type'] == 'settings':
                                # Store PRNT settings
                                self.data_holder.latest_psm_prnt[dev_id] = parsed['data']
                                settings_fetched = True

                            elif parsed['type'] == 'dilution':
                                # Store dilution parameters
                                self.data_holder.psm_dilution[dev_id] = parsed['data']

                            elif parsed['type'] == 'self_test':
                                # Display self-test errors
                                widget.set_tab.command_widget.update_text_box("self test error binary: " + bin(int(parsed['data'], 16))[2:].zfill(len(PSM_ERRORS)))
                                for error_msg in parsed.get('errors', []):
                                    widget.set_tab.command_widget.update_text_box(error_msg)

                            elif parsed['type'] == 'info' and parsed['command'] == '*IDN':
                                # Handle device identification
                                serial_number = parsed['data']
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)
                                if dev_id in self.data_holder.idn_inquiry_devices:
                                    self.data_holder.idn_inquiry_devices.remove(dev_id)

                            elif parsed['type'] == 'firmware':
                                # Update firmware version
                                firmware_version = parsed['data']
                                if dev.child('Firmware version').value() != firmware_version:
                                    dev.child('Firmware version').setValue(firmware_version)

                            # Show messages in command widget if requested
                            if parsed.get('show_in_command_widget', False):
                                widget.set_tab.command_widget.update_text_box(parsed['raw'])
                                if parsed['type'] == 'error' and 'error' in parsed:
                                    print("PSM error: " + str(parsed['error']))

                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        # Reset mode colors on error
                        widget.measure_tab.scan.change_color(0)
                        widget.measure_tab.step.change_color(0)
                        widget.measure_tab.fixed.change_color(0)

                    # Compile settings if all required data is available
                    if self.data_holder.psm_settings_updates[dev_id] and settings_fetched and dev_id in self.data_holder.psm_dilution:
                        try:
                            # Get CO flow rate (PSM Retrofit only)
                            if dev_type == PSM:
                                co_flow = round(widget.set_tab.set_co_flow.value_spinbox.value(), 3)
                            else:
                                co_flow = "nan"

                            dilution_parameters = self.data_holder.psm_dilution[dev_id]
                            settings = compile_psm_settings(self.data_holder.latest_psm_prnt[dev_id], co_flow, dilution_parameters, dev_type)

                            self.data_holder.latest_settings[dev_id] = settings
                            self.data_holder.par_updates[dev_id] = 1
                            self.data_holder.psm_settings_updates[dev_id] = False
                        except Exception as e:
                            print(traceback.format_exc())
                            logging.exception(e)
                
                if dev_type == ELECTROMETER: # ELECTROMETER
                    widget = self.data_holder.device_widgets[dev_id]
                    try:
                        readings = dev_conn.connection.read_until(b'\r\n').decode()
                        parsed = widget.parse_message(readings, self.data_holder)

                        if parsed['type'] == 'data':
                            self.data_holder.latest_data[dev_id] = parsed['data']
                        else:
                            self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)

                if dev_type == CO2_SENSOR: # CO2 sensor
                    widget = self.data_holder.device_widgets[dev_id]
                    try:
                        # Check if looking for IDN
                        if dev_id in self.data_holder.idn_inquiry_devices:
                            messages = dev_conn.connection.read_all().decode().split("\r\n")
                            for message in messages:
                                if len(message) > 5:
                                    parsed = widget.parse_message(message, self.data_holder)
                                    if parsed['type'] == 'info' and parsed['command'] == '*IDN':
                                        serial_number = parsed['data']
                                        if dev.child('Serial number').value() != serial_number:
                                            dev.child('Serial number').setValue(serial_number)
                                        if dev_id in self.data_holder.idn_inquiry_devices:
                                            self.data_holder.idn_inquiry_devices.remove(dev_id)
                            self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        else:
                            # Read normal data
                            readings = dev_conn.connection.read_until(b'\r\n').decode()
                            parsed = widget.parse_message(readings, self.data_holder)

                            if parsed['type'] == 'data':
                                self.data_holder.latest_data[dev_id] = parsed['data']
                            else:
                                self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)

                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)
                
                if dev_type == RHTP: # RHTP
                    widget = self.data_holder.device_widgets[dev_id]
                    try:
                        # Check if looking for IDN
                        if dev_id in self.data_holder.idn_inquiry_devices:
                            messages = dev_conn.connection.read_all().decode().split("\r\n")
                            for message in messages:
                                if len(message) > 5:
                                    parsed = widget.parse_message(message, self.data_holder)
                                    if parsed['type'] == 'info' and parsed['command'] == '*IDN':
                                        serial_number = parsed['data']
                                        if dev.child('Serial number').value() != serial_number:
                                            dev.child('Serial number').setValue(serial_number)
                                        if dev_id in self.data_holder.idn_inquiry_devices:
                                            self.data_holder.idn_inquiry_devices.remove(dev_id)
                        else:
                            # Read normal data
                            readings = dev_conn.connection.read_until(b'\r\n').decode()
                            parsed = widget.parse_message(readings, self.data_holder)

                            if parsed['type'] == 'data':
                                self.data_holder.latest_data[dev_id] = parsed['data']

                            # Check for extra data in buffer
                            buffer_length = dev_conn.connection.inWaiting()
                            if buffer_length >= 24:
                                extra_data = dev_conn.connection.read_until(b'\r\n').decode()
                                parsed_extra = widget.parse_message(extra_data, self.data_holder)
                                if parsed_extra['type'] == 'data':
                                    self.data_holder.latest_data[dev_id] = parsed_extra['data']

                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)
                
                if dev_type == AFM: # AFM
                    widget = self.data_holder.device_widgets[dev_id]
                    try:
                        # Check if looking for IDN
                        if dev_id in self.data_holder.idn_inquiry_devices:
                            messages = dev_conn.connection.read_all().decode().split("\r\n")
                            for message in messages:
                                if len(message) > 5:
                                    parsed = widget.parse_message(message, self.data_holder)
                                    if parsed['type'] == 'info' and parsed['command'] == '*IDN':
                                        serial_number = parsed['data']
                                        if dev.child('Serial number').value() != serial_number:
                                            dev.child('Serial number').setValue(serial_number)
                                        if dev_id in self.data_holder.idn_inquiry_devices:
                                            self.data_holder.idn_inquiry_devices.remove(dev_id)
                        else:
                            # Read normal data
                            readings = dev_conn.connection.read_until(b'\r\n').decode()
                            parsed = widget.parse_message(readings, self.data_holder)

                            if parsed['type'] == 'data':
                                self.data_holder.latest_data[dev_id] = parsed['data']

                            # Check for extra data in buffer
                            buffer_length = dev_conn.connection.inWaiting()
                            if buffer_length >= 40:
                                extra_data = dev_conn.connection.read_until(b'\r\n').decode()
                                parsed_extra = widget.parse_message(extra_data, self.data_holder)
                                if parsed_extra['type'] == 'data':
                                    self.data_holder.latest_data[dev_id] = parsed_extra['data']

                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)
                
                if dev_type == EDILUTER: # eDiluter
                    widget = self.data_holder.device_widgets[dev_id]
                    data_received = False

                    try:
                        # Check for extra data from last round
                        if dev_id in self.data_holder.extra_data:
                            self.data_holder.latest_data[dev_id] = self.data_holder.extra_data[dev_id]
                            del self.data_holder.extra_data[dev_id]

                        # Read all data from buffer
                        readings = dev_conn.connection.read_all()
                        readings = readings.decode().split("\r\n")[:-1]

                        for message in readings:
                            parsed = widget.parse_message(message, self.data_holder)

                            if parsed['type'] == 'data':
                                if data_received:
                                    self.data_holder.extra_data[dev_id] = parsed['data']
                                else:
                                    self.data_holder.latest_data[dev_id] = parsed['data']
                                    data_received = True

                            elif parsed['type'] == 'error' and parsed['command'] == 'auto-push':
                                # Incomplete message
                                print("readIndata - " + parsed.get('error', 'eDiluter error'))
                                logging.error(parsed.get('error', 'eDiluter error'))

                            # Show messages in command widget if requested
                            if parsed.get('show_in_command_widget', False):
                                widget.set_tab.command_widget.update_text_box(parsed['raw'])

                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)

                    # Update eDiluter status tab
                    widget.update_values(self.data_holder.latest_data[dev_id])
                
                if dev_type == TSI_CPC:
                    widget = self.data_holder.device_widgets[dev_id]
                    try:
                        readings = dev_conn.connection.read_all()
                        readings = readings.decode()
                        parsed = widget.parse_message(readings, self.data_holder)

                        if parsed['type'] == 'data':
                            self.data_holder.latest_data[dev_id] = parsed['data']

                            # Set error flags if device has errors
                            if parsed.get('has_errors', False):
                                self.data_holder.error_status = 1
                                self.data_holder.device_errors[dev_id] = True
                        else:
                            self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)

                    except Exception as e:
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.error(traceback.format_exc())

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
                            if self.data_holder.latest_settings[dev_id][0] != 0.1:
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
                            if self.data_holder.latest_settings[dev_id][0] < 1:
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
