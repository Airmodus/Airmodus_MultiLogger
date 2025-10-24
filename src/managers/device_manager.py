# managers/device_manager.py
from PyQt5.QtCore import QTimer
from time import time
import traceback
from serial.tools import list_ports
import logging
from numpy import full, nan, isnan, array, array_equal
from serial.serialutil import SerialException
from config import * 
from utils import (
    compile_cpc_data,
    compile_cpc_settings,
    compile_psm_data,
    compile_psm_settings,
    psm_update
)
from params import params

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

                    # check if there's data from last round in extra_data dictionary
                    # if no extra data, start with nan lists
                    self.data_holder.latest_data[dev_id] = self.data_holder.extra_data.pop(dev_id, self.data_holder.get_default_data_array(dev_type))

                    prnt_list = self.data_holder.extra_data.pop(str(dev_id) + ":prnt", full(13, nan))
                    pall_list = self.data_holder.extra_data.pop(str(dev_id) + ":pall", full(28, nan))
                    # if 10 hz is True, initialize 10 hz data with extra data or nan list
                    if dev.child('10 hz').value():
                        self.data_holder.latest_ten_hz[dev_id] = self.data_holder.extra_data.pop(str(dev_id) + ":10hz", self.data_holder.latest_ten_hz[dev_id])

                    try:
                        readings = dev_conn.connection.read_all()
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
                                total_errors = self.data_holder.device_widgets[dev_id].update_errors(status_hex, cabin_p_error)
                                
                                # set data_holder.error_status flag if total errors is not 0
                                if total_errors != 0:
                                    self.data_holder.error_status = 1
                                    # set device error flag
                                    self.set_device_error(dev_id, True)

                                meas_list = list(map(float,data[:-1])) # convert to float without status hex
                                # compile data list
                                # if latest_data is nan, store data normally
                                if isnan(self.data_holder.latest_data[dev_id][0]):
                                    self.data_holder.latest_data[dev_id] = compile_cpc_data(meas_list, status_hex, total_errors)
                                else: # if not nan, store data to extra_data dictionary
                                    self.data_holder.extra_data[dev_id] = compile_cpc_data(meas_list, status_hex, total_errors)

                            elif command == ":SYST:PRNT":
                                # if prnt_list is nan, store data normally
                                if isnan(prnt_list[0]):
                                    prnt_list = list(map(float,data)) # convert to float
                                else: # if not nan, store data to extra_data dictionary
                                    self.data_holder.extra_data[str(dev_id)+":prnt"] = list(map(float,data))

                            elif command == ":SYST:PALL":
                                data[22] = "NaN" # set device id and firmware variant letter to NaN before float conversion
                                data[23] = "NaN" # TODO store device id and firmware variant letter somewhere
                                # if pall_list is nan, store data normally
                                if isnan(pall_list[0]): # TODO make sure this value (inlet press lower limit) is never nan in valid data
                                    pall_list = list(map(float,data))
                                else: # if not nan, store data to extra_data dictionary
                                    self.data_holder.extra_data[str(dev_id)+":pall"] = list(map(float,data))
                            
                            elif command == ":MEAS:OPC_CONC_LOG":
                                del data[0] # remove first item (timestamp)
                                # if latest_ten_hz is nan, store data normally
                                if isnan(float(self.data_holder.latest_ten_hz[dev_id][0])):
                                    self.data_holder.latest_ten_hz[dev_id] = data
                                else: # if not nan, store data to extra_data dictionary
                                    self.data_holder.extra_data[str(dev_id)+":10hz"] = data
                            
                            elif command == ":STAT:SELF:LOG":
                                error_length = len(CPC_ERRORS) # get amount of CPC errors
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                status_bin = bin(int(data[0], 16)) # convert hex to int and int to binary
                                status_bin = status_bin[2:].zfill(error_length) # remove 0b from string and fill with 0s
                                # print self test error binary
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error binary: " + status_bin)
                                inverted_status_bin = status_bin[::-1] # invert status_bin for error parsing
                                # print error indices
                                for i in range(error_length): # loop through errors
                                    if inverted_status_bin[i] == "1":
                                        self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error bit index: " + str(i))
                                        self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error: " + CPC_ERRORS[i])

                            elif command == ":SELF:ERR":
                                try:
                                    self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                    error_code = int(data[0])
                                    print("self test error: " + CPC_ERRORS[error_code])
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                            
                            elif command == "*IDN":
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                serial_number = data[0]
                                serial_number = serial_number.strip("\n")
                                serial_number = serial_number.strip("\r")
                                # check if serial number has changed
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)
                                    # update PSM 'Connected CPC' list
                                    self.params.child('Device settings').update_cpc_dict()
                                # remove device from IDN inquiry list
                                if dev_id in self.data_holder.idn_inquiry_devices:
                                    self.data_holder.idn_inquiry_devices.remove(dev_id)

                            else: # print these to command widget text box
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                #logging.warning("readIndata - unknown command: %s", command)

                    except Exception as e: # if reading fails, print error message
                        print(traceback.format_exc())
                        logging.exception(e)
                    
                    # update CPC widget data values
                    self.data_holder.device_widgets[dev_id].update_values(self.data_holder.latest_data[dev_id])
                    # update CPC widget set values
                    self.data_holder.device_widgets[dev_id].update_settings(prnt_list)

                    # set settings update flag if both lists are successfully read
                    if str(prnt_list[0]) != "nan" and str(pall_list[0]) != "nan": # if both lists are not nan (checks first item only)
                        settings_update = True
                    else:
                        settings_update = False
                    
                    # if pulse analysis is in progress, skip settings update
                    # this keeps the original threshold value intact in latest_settings dictionary
                    if dev_id in self.data_holder.pulse_analysis_index:
                        settings_update = False
                    
                    # update settings if settings are valid
                    if settings_update == True: # if settings are valid, not nan
                        
                        # get previous settings form latest_settings dictionary
                        previous_settings = self.data_holder.latest_settings[dev_id]
                        # compile settings list
                        settings = compile_cpc_settings(prnt_list, pall_list)

                        if not array_equal(settings, previous_settings, equal_nan=True): # if values have changed
                            # update latest settings
                            self.data_holder.latest_settings[dev_id] = settings
                            # set .par update flag
                            self.data_holder.par_updates[dev_id] = 1
                        else:
                            # clear .par update flag
                            self.data_holder.par_updates[dev_id] = 0
                    
                    else: # if settings are not valid, clear .par update flag
                        self.data_holder.par_updates[dev_id] = 0
                
                if dev_type in [PSM, PSM2]: # PSM

                    # clear extra data buffer after 60 seconds of consecutive buffering
                    # this ensures data is real time and not delayed by 1 second
                    if dev_id in self.data_holder.extra_data and self.data_holder.extra_data_counter[dev_id] >= 60:
                        del self.data_holder.extra_data[dev_id]
                        logging.info("PSM %s extra data buffer cleared", dev.child('Serial number').value())
                    
                    default_nan = self.data_holder.get_default_data_array(dev_type)
                    was_present = dev_id in self.data_holder.extra_data  # Check BEFORE pop
                    self.data_holder.latest_data[dev_id] = self.data_holder.extra_data.pop(dev_id, default_nan)
                    if was_present:
                        self.data_holder.extra_data_counter[dev_id] += 1
                    else:
                        self.data_holder.extra_data_counter[dev_id] = 0  # Add reset

                    # clear par update flag
                    self.data_holder.par_updates[dev_id] = 0

                    # set settings_fetched flag to False
                    # flag is set to True when settings are successfully fetched
                    settings_fetched = False

                    try: # try to read data, decode and split
                        #print("inWaiting():", dev_conn.connection.inWaiting())
                        readings = dev_conn.connection.read_all()
                        # decode and separate messages
                        readings = readings.decode().split("\r")

                        # check if first message is expected as second half of partial message
                        if dev_id in self.data_holder.partial_data:
                            # add stored partial message to the front of first message
                            readings[0] = self.data_holder.partial_data[dev_id] + readings[0]
                            # remove partial message from dictionary
                            del self.data_holder.partial_data[dev_id]
                            #logging.info("PSM %s combined message: %s", dev.child('Serial number').value(), readings[0])

                        # check if last message is empty or partial
                        if readings[-1] == "": # if empty, remove it from readings
                            readings = readings[:-1]
                        else: # if not empty, store partial message and remove it from readings
                            self.data_holder.partial_data[dev_id] = readings[-1]
                            readings = readings[:-1]
                            #logging.info("PSM %s partial message: %s", dev.child('Serial number').value(), self.data_holder.partial_data[dev_id])
                        
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
                                self.data_holder.device_widgets[dev_id].update_values(data)
                                # update active measure mode color
                                self.data_holder.device_widgets[dev_id].measure_tab.change_mode_color(command)
                                # status hex handling
                                status_hex = data[-2]
                                try:
                                    # update widget errors colors
                                    total_errors = self.data_holder.device_widgets[dev_id].update_errors(status_hex)
                                    # set data_holder.error_status flag if total errors is not 0
                                    if total_errors != 0:
                                        self.data_holder.error_status = 1
                                        # set device error flag
                                        self.set_device_error(dev_id, True)
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                # note hex handling
                                note_hex = data[-1]
                                # update widget liquid states with note hex
                                liquid_errors = self.data_holder.device_widgets[dev_id].update_notes(note_hex)
                                # set error flags if liquid errors is not 0
                                if liquid_errors != 0:
                                    self.data_holder.error_status = 1
                                    # set device error flag
                                    self.set_device_error(dev_id, True)
                                # store polynomial correction value as float to dictionary
                                self.data_holder.latest_poly_correction[dev_id] = float(data[14])

                                scan_status = "9" # set scan status to 9 (undefined) as default
                                # check firmware number to determine if scan status is included in data
                                try:
                                    if dev.child('Firmware version').value() != "":
                                        firmware_version = dev.child('Firmware version').value().split(".")
                                        # Retrofit: version >= 0.5.5
                                        if dev_type == PSM:
                                            if int(firmware_version[1]) > 5:
                                                scan_status = data[15]
                                            elif int(firmware_version[1]) == 5 and int(firmware_version[2]) >= 5:
                                                scan_status = data[15]
                                        # PSM 2.0: version >= 0.6.8
                                        elif dev_type == PSM2:
                                            if int(firmware_version[1]) > 6:
                                                scan_status = data[15]
                                            elif int(firmware_version[1]) == 6 and int(firmware_version[2]) >= 8:
                                                scan_status = data[15]
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                
                                # compile psm data
                                compiled_data = compile_psm_data(data, status_hex, note_hex, scan_status, psm_version=dev_type)
                                # if latest_data is nan, store data normally
                                if isnan(float(self.data_holder.latest_data[dev_id][2])): # check saturator flow rate value (index 2)
                                    self.data_holder.latest_data[dev_id] = compiled_data
                                else: # if not nan, store data to extra_data dictionary
                                    self.data_holder.extra_data[dev_id] = compiled_data
                                    #logging.info("PSM %s extra data: %s", dev.child('Serial number').value(), str(compiled_data))
                            
                            elif command == ":SYST:PRNT":
                                # update GUI set points
                                self.data_holder.device_widgets[dev_id].update_settings(data)
                                # store settings to latest PSM prnt dictionary with device id as key
                                self.data_holder.latest_psm_prnt[dev_id] = data
                                # print settings to command widget text box
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                # set settings_fetched flag to True
                                settings_fetched = True
                            
                            elif command == ":STAT:SELF:LOG":
                                error_length = len(PSM_ERRORS) # get amount of PSM errors
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                status_bin = bin(int(data[0], 16)) # convert hex to int and int to binary
                                status_bin = status_bin[2:].zfill(error_length) # remove 0b from string and fill with 0s
                                # print self test error binary
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error binary: " + status_bin)
                                inverted_status_bin = status_bin[::-1] # invert status_bin for error parsing
                                # print error indices
                                for i in range(error_length): # loop through binary digits
                                    if inverted_status_bin[i] == "1":
                                        self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error bit index: " + str(i))
                                        # if error is MFC_HEATER / MFC_EXCESS, check device type
                                        if i == 27 and dev_type == PSM: # Retrofit has different error at index 27
                                            self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error: " + "ERROR_SELFTEST_MFC_EXCESS")
                                        else:
                                            self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box("self test error: " + PSM_ERRORS[i])
                            
                            elif command == ":SELF:ERR":
                                try:
                                    self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                    error_code = int(data[0])
                                    # if error is MFC_HEATER / MFC_EXCESS, check device type
                                    if error_code == 27 and dev_type == PSM:
                                        print("self test error: " + "ERROR_SELFTEST_MFC_EXCESS")
                                    else:
                                        print("self test error: " + PSM_ERRORS[int(error_code)])
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                            
                            elif command == "*IDN":
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                serial_number = data[0]
                                serial_number = serial_number.strip("\n")
                                serial_number = serial_number.strip("\r")
                                # check if serial number has changed
                                if dev.child('Serial number').value() != serial_number:
                                    dev.child('Serial number').setValue(serial_number)
                                # remove device from IDN inquiry list
                                if dev_id in self.data_holder.idn_inquiry_devices:
                                    self.data_holder.idn_inquiry_devices.remove(dev_id)
                            
                            elif command == "Firmware":
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                if "version: " in data[0]:
                                    firmware_version = data[0].split(": ")[1]
                                    if dev.child('Firmware version').value() != firmware_version:
                                        dev.child('Firmware version').setValue(firmware_version)
                            
                            elif command == ":SYST:VCMP":
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)
                                if len(data) == 6: # make sure data is valid
                                    # store dilution parameters to dictionary
                                    self.data_holder.psm_dilution[dev_id] = data
                                else:
                                    print("PSM dilution parameters invalid:", data)
                            
                            else: # print other messages to command widget text box
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message_string)

                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        # update widget error colors
                        self.data_holder.device_widgets[dev_id].measure_tab.scan.change_color(0)
                        self.data_holder.device_widgets[dev_id].measure_tab.step.change_color(0)
                        self.data_holder.device_widgets[dev_id].measure_tab.fixed.change_color(0)
                        try:
                            # print message_string to log
                            logging.info("PSM message_string: %s", message_string)
                        except Exception:
                            print(traceback.format_exc())
                    
                    # compile settings list if update flag is True, settings_fetched is True and dilution parameters have been fetched
                    if self.data_holder.psm_settings_updates[dev_id] == True and settings_fetched == True and dev_id in self.data_holder.psm_dilution:
                        try:
                            psm_version = dev_type
                            if psm_version == PSM:
                                # get CO flow rate from PSM widget
                                co_flow = round(self.data_holder.device_widgets[dev_id].set_tab.set_co_flow.value_spinbox.value(), 3)
                            elif psm_version == PSM2:
                                # set nan as placeholder
                                co_flow = "nan"
                            dilution_parameters = self.data_holder.psm_dilution[dev_id]
                            # compile settings with latest PSM prnt settings and CO flow rate
                            settings = compile_psm_settings(self.data_holder.latest_psm_prnt[dev_id], co_flow, dilution_parameters, psm_version)
                            # store settings to latest settings dictionary with device id as key
                            self.data_holder.latest_settings[dev_id] = settings
                            # add par update flag
                            self.data_holder.par_updates[dev_id] = 1
                            # remove update settings flag once settings have been updated and compiled
                            self.data_holder.psm_settings_updates[dev_id] = False
                        except Exception as e:
                            print(traceback.format_exc())
                            logging.exception(e)
                
                if dev_type == ELECTROMETER: # ELECTROMETER
                    try: # try to read data, decode, split and convert to float
                        readings = dev_conn.connection.read_until(b'\r\n').decode()
                        readings = list(map(float,readings.split(";")))
                        # store to latest_data dictionary with device id as key
                        self.data_holder.latest_data[dev_id] = readings
                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)

                if dev_type == CO2_SENSOR: # CO2 sensor TODO make CO2 process similar to RHTP?
                    try:
                        # if device is in IDN inquiry list, look for *IDN
                        if dev_id in self.data_holder.idn_inquiry_devices:
                            # read all data from buffer
                            messages = dev_conn.connection.read_all().decode().split("\r\n")
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
                                        if dev_id in self.data_holder.idn_inquiry_devices:
                                            self.data_holder.idn_inquiry_devices.remove(dev_id)
                            # store nan values to latest_data
                            self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)

                        # if Serial number has been acquired, read data normally
                        else:
                            # read data, decode, split and convert to float
                            readings = dev_conn.connection.read_until(b'\r\n').decode()
                            readings = list(map(float,readings.split(";")))
                            if readings[0] != 0: # if data is something else than 0
                                # store to latest_data dictionary with device id as key
                                self.data_holder.latest_data[dev_id] = readings
                            else: # if data is 0, not valid
                                self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type) 

                    except Exception as e: # if reading fails, store nan values to latest_data
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type) 
                        logging.exception(e)
                
                if dev_type == RHTP: # RHTP
                    try:
                        # if device is in IDN inquiry list, look for *IDN
                        if dev_id in self.data_holder.idn_inquiry_devices:
                            # read all data from buffer
                            messages = dev_conn.connection.read_all().decode().split("\r\n")
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
                                        if dev_id in self.data_holder.idn_inquiry_devices:
                                            self.data_holder.idn_inquiry_devices.remove(dev_id)
                        
                        # if Serial number has been acquired, read data normally
                        else:
                            # read and decode a line of data
                            readings = dev_conn.connection.read_until(b'\r\n').decode()
                            # remove '\r\n' from end
                            readings = readings.strip('\r\n')
                            # split data to list
                            readings = readings.split(", ")

                            # check if data is valid and store to latest_data
                            # readings length should be 3 (RH, T, P)
                            if len(readings) == 3:
                                self.data_holder.latest_data[dev_id] = readings

                            # check if there's extra data in buffer
                            # max message length is 23 (normal 20 + 2 \r\n + 1 if negative T)
                            buffer_length = dev_conn.connection.inWaiting()
                            if buffer_length >= 24:
                                # create log entry
                                # serial_number = dev.child('Serial number').value()
                                # logging.warning("RHTP %s buffer: %i", serial_number, buffer_length)

                                # read next line
                                extra_data = dev_conn.connection.read_until(b'\r\n').decode()
                                # remove '\r\n' and split data to list
                                extra_data = extra_data.strip('\r\n').split(", ")
                                # use extra data as latest_data if valid
                                if len(extra_data) == 3:
                                    self.data_holder.latest_data[dev_id] = extra_data

                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)
                
                if dev_type == AFM: # AFM
                    try:
                        # if device is in IDN inquiry list, look for *IDN
                        if dev_id in self.data_holder.idn_inquiry_devices:
                            # read all data from buffer
                            messages = dev_conn.connection.read_all().decode().split("\r\n")
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
                                        if dev_id in self.data_holder.idn_inquiry_devices:
                                            self.data_holder.idn_inquiry_devices.remove(dev_id)
                        
                        # if Serial number has been acquired, read data normally
                        else:
                            # read and decode a line of data
                            readings = dev_conn.connection.read_until(b'\r\n').decode()
                            # remove '\r\n' from end
                            readings = readings.strip('\r\n')
                            # split data to list
                            readings = readings.split(", ")

                            # check if data is valid and store to latest_data
                            # readings length should be 5 (volumetric flow, standard flow, RH, T, P)
                            if len(readings) == 5:
                                self.data_holder.latest_data[dev_id] = readings

                            # check if there's extra data in buffer
                            # max message length is 39 (normal 34 + 2 \r\n + 1 if negative T + 2 if flow values >= 10)
                            buffer_length = dev_conn.connection.inWaiting()
                            if buffer_length >= 40:
                                # create log entry
                                # serial_number = dev.child('Serial number').value()
                                # logging.warning("AFM %s buffer: %i", serial_number, buffer_length)

                                # read next line
                                extra_data = dev_conn.connection.read_until(b'\r\n').decode()
                                # remove '\r\n' and split data to list
                                extra_data = extra_data.strip('\r\n').split(", ")
                                # use extra data as latest_data if valid
                                if len(extra_data) == 5:
                                    self.data_holder.latest_data[dev_id] = extra_data
                    
                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type) 
                        logging.exception(e)
                
                if dev_type == EDILUTER: # eDiluter
                    try:
                        # flag indicating if data has already been received, used for handling extra data
                        data_received = False
                        # check if there's extra data from last round
                        if dev_id in self.data_holder.extra_data:
                            # store extra data to latest_data
                            self.data_holder.latest_data[dev_id] = self.data_holder.extra_data[dev_id]
                            # remove extra data from dictionary
                            del self.data_holder.extra_data[dev_id]
                        # read all data from buffer
                        readings = dev_conn.connection.read_all()
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
                                        self.data_holder.extra_data[dev_id] = data
                                    # if data has not been received yet
                                    else:
                                        # store data to latest_data dictionary with device id as key
                                        self.data_holder.latest_data[dev_id] = data
                                        # set data received flag to True
                                        data_received = True
                                else: # if message is not full
                                    # TODO store partial message and expect the rest on next round
                                    print("readIndata - eDiluter message not full:", message)
                                    logging.error("readIndata - eDiluter message not full: %s", message)

                            # if message starts with "SUCCESS:" - command message response
                            elif message.split(" ")[0] == "SUCCESS:":
                                # append device's command widget text box
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message)
                            
                            # if message starts with "ERROR:" - command message response
                            elif message.split(" ")[0] == "ERROR:":
                                # append device's command widget text box
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message)
                            
                            else: # if message is not recognized
                                logging.error("readIndata - eDiluter unknown message: %s", message)
                                # append device's command widget text box
                                self.data_holder.device_widgets[dev_id].set_tab.command_widget.update_text_box(message)
                        
                    except Exception as e:
                        print(traceback.format_exc())
                        self.data_holder.latest_data[dev_id] = self.data_holder.get_default_data_array(dev_type)
                        logging.exception(e)
                    
                    # update eDiluter status tab values
                    self.data_holder.device_widgets[dev_id].update_values(self.data_holder.latest_data[dev_id])
                
                if dev_type == TSI_CPC:
                    try: # try to read data, decode and split
                        readings = dev_conn.connection.read_all()
                        readings = readings.decode().split("\r")[:-1]
                        readings[0] = float(readings[0]) # convert concentration to float

                        # store to latest data dictionary
                        self.data_holder.latest_data[dev_id] = readings

                        # set data_holder.error_status flag if instrument errors is not equal to 0
                        if int(readings[1], 16) != 0:
                            self.data_holder.error_status = 1
                            # set device error flag
                            self.set_device_error(dev_id, True)
                    
                    except Exception as e: # if reading fails, store nan values to latest_data
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
