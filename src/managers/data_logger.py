# managers/data_logger.py
from datetime import datetime as dt
import logging
import traceback
from numpy import isnan, nan
from config import osx_mode, TSI_CPC, CPC, PSM, PSM2, ELECTROMETER, CO2_SENSOR, RHTP, AFM, EDILUTER, EXAMPLE_DEVICE, PULSE_ANALYSIS_THRESHOLDS

class DataLogger:
    def __init__(self, data_holder, params):
        self.data_holder = data_holder
        self.params = params

    def _is_device_in_pulse_analysis(self, dev_id):
        """Check if device is in pulse analysis mode."""
        device_widget = self.data_holder.get_device(dev_id)
        if device_widget and hasattr(device_widget, 'pulse_analysis_index'):
            # 0-6 = analyzing, -1 = ending, None = not analyzing
            return device_widget.pulse_analysis_index is not None and device_widget.pulse_analysis_index >= 0
        return False

    def save_changed(self):
        """Triggered when saving is toggled on/off."""
        # if saving is toggled on
        if self.params.child('Data settings').child('Save data').value():
            # store start day
            self.data_holder.start_day = dt.now().strftime("%m%d")
            # get file path
            self.data_holder.file_path = self.params.child('Data settings').child('File path').value()
            # set file path as read only
            self.params.child('Data settings').child('File path').setReadonly(True)
        # if saving is toggled off, reset filename dictionaries
        else:
            self.reset_all_filenames()
            # disable read only file path
            self.params.child('Data settings').child('File path').setReadonly(False)

    def filepath_changed(self, new_path):
        """Set file path and reset filename dictionaries."""
        self.data_holder.file_path = new_path
        self.reset_all_filenames()

    def reset_device_filenames(self, dev_id):
        """Remove specific device from filename dictionaries, results in new files being created."""
        if dev_id in self.data_holder.dat_filenames:
            self.data_holder.dat_filenames.pop(dev_id)
        if dev_id in self.data_holder.par_filenames:
            self.data_holder.par_filenames.pop(dev_id)
        if dev_id in self.data_holder.par_updates:
            self.data_holder.par_updates.pop(dev_id)
        if dev_id in self.data_holder.ten_hz_filenames:
            self.data_holder.ten_hz_filenames.pop(dev_id)

    def reset_all_filenames(self):
        """Reset all filename dictionaries, results in new files being created."""
        self.data_holder.dat_filenames = {}
        self.data_holder.par_filenames = {}
        self.data_holder.ten_hz_filenames = {}
        self.data_holder.par_updates = {}

    def compare_day(self):
        """Compare current day to file start day (self.start_day defined in save_changed)."""
        # check if saving is on
        if self.params.child('Data settings').child('Save data').value():
            # check if new file should be started at midnight
            if self.params.child("Data settings").child('Generate daily files').value():
                current_day = dt.fromtimestamp(self.data_holder.current_time).strftime("%m%d")
                if current_day != self.data_holder.start_day:
                    self.reset_all_filenames() # start new file if day has changed
                    # update start day
                    self.data_holder.start_day = current_day

    def write_data(self):
        """Write data to file(s)."""
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
                elif self._is_device_in_pulse_analysis(dev.child('DevID').value()):
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
                            with open(self.data_holder.file_path + filename ,"w",encoding='UTF-8'):
                                pass
                           
                            # if CPC or PSM, create .par file and add filename to data_holder.par_filenames
                            if dev.child('Device type').value() in [CPC, PSM, PSM2]:
                                if osx_mode:
                                    filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.par'
                                else:
                                    filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.par'
                                self.data_holder.par_filenames[dev_id] = filename
                                with open(self.data_holder.file_path + filename ,"w",encoding='UTF-8'):
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
                                with open(self.data_holder.file_path + filename ,"w",encoding='UTF-8') as file:
                                    # write header
                                    file.write('YYYY.MM.DD hh:mm:ss,Concentration 1 (#/cc),Concentration 2 (#/cc),Concentration 3 (#/cc),Concentration 4 (#/cc),Concentration 5 (#/cc),Concentration 6 (#/cc),Concentration 7 (#/cc),Concentration 8 (#/cc),Concentration 9 (#/cc),Concentration 10 (#/cc)')
                           
                        # get filename from dictionary and add path to front
                        filename = self.data_holder.file_path + self.data_holder.dat_filenames[dev_id]
                       
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
                            # convert data to string using typed dataclass to_array()
                            device_data = self.data_holder.get_device_data(dev_id)
                            write_data = ','.join(str(vals) for vals in device_data.to_array())
                            # write data
                            file.write(write_data)
                       
                        # if CPC or PSM, append .par file with new settings
                        if dev.child('Device type').value() in [CPC, PSM, PSM2]:
                            # get filename from dictionary and add path to front
                            filename = self.data_holder.file_path + self.data_holder.par_filenames[dev_id]
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
                                    # Convert data to string from device settings dataclass
                                    device_settings = self.data_holder.get_device_settings(dev_id)
                                    write_data = ','.join(str(vals) for vals in device_settings.to_array()) if device_settings else ''
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
                                                cpc_settings = self.data_holder.get_device_settings(cpc_id)
                                                file.write(',') # separate PSM and CPC settings with comma
                                                # compile connected CPC settings from typed dataclass
                                                if cpc_settings:
                                                    connected_cpc_settings = [
                                                        cpc_idn, # connected CPC serial number (IDN)
                                                        cpc_settings.autofill, cpc_settings.drain, cpc_settings.water_removal, # autofill, drain, water removal
                                                        cpc_settings.saturator_temp, cpc_settings.condenser_temp, cpc_settings.spare1, # T set: saturator, condenser, optics
                                                        cpc_settings.measured_cpc_flow, cpc_settings.averaging_time # inlet flow rate (measured), aveaging time
                                                    ]
                                                else:
                                                    connected_cpc_settings = []
                                                # write connected CPC settings
                                                write_data = ','.join(str(vals) for vals in connected_cpc_settings)
                                                file.write(write_data)
                                           
                                            else: # if CPC is not connected or not Airmodus CPC, write nan values
                                                file.write(',nan,nan,nan,nan,nan,nan,nan,nan,nan')
                                       
                                        else: # if no connected CPC selected, write nan values
                                            file.write(',nan,nan,nan,nan,nan,nan,nan,nan,nan')
                                       
                                    # check if device has latest command
                                    device_widget = self.data_holder.get_device(dev_id)
                                    if device_widget and device_widget.latest_command is not None:
                                        # write latest command to file and clear from device
                                        file.write(',' + device_widget.latest_command)
                                        device_widget.latest_command = None
                       
                        # check if device is Airmodus CPC and 10hz parameter is on
                        if dev.child('Device type').value() == CPC and dev.child('10 hz').value():
                            # Get device widget to access ten_hz_data
                            device_widget = self.data_holder.get_device(dev_id)
                            if device_widget and hasattr(device_widget, 'ten_hz_data'):
                                # get filename from dictionary and add path to front
                                filename = self.data_holder.file_path + self.data_holder.ten_hz_filenames[dev_id]
                                # append file with new data
                                with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                                    file.write("\n")
                                    # Add timestamp
                                    file.write(timeStampStr+',')
                                    # Convert data to string
                                    write_data = ','.join(str(vals) for vals in device_widget.ten_hz_data)
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
            device_widget = self.data_holder.get_device(dev_id)
            if device_widget and hasattr(device_widget, 'pulse_analysis_index'):
                if device_widget.pulse_analysis_index is not None: # when index is None, analysis has reached its end
                    try:
                        # Get device data
                        cpc_data = self.data_holder.get_device_data(dev_id)
                        # calculate current pulse duration
                        dead_time = cpc_data.dead_time
                        number_of_pulses = cpc_data.number_of_pulses
                        if number_of_pulses == 0:
                            pulse_duration = nan # if number of pulses is 0, set pulse duration to nan
                        else:
                            # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                            pulse_duration = round(dead_time * 1000 / number_of_pulses, 2)
                        # get current threshold value with device.pulse_analysis_index
                        threshold_value = PULSE_ANALYSIS_THRESHOLDS[device_widget.pulse_analysis_index]
                        # get filename from dictionary (includes file path)
                        filename = self.data_holder.pulse_analysis_filenames[dev_id]
                        # append file with new data
                        with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                            file.write('\n') # create new line
                            file.write(str(threshold_value) + ',' + str(number_of_pulses) + ',' + str(dead_time) + ',' + str(pulse_duration))
                        # increase device.pulse_analysis_index by 1
                        device_widget.pulse_analysis_index += 1
                        # if all thresholds have been gone through, end pulse analysis
                        if device_widget.pulse_analysis_index >= len(PULSE_ANALYSIS_THRESHOLDS):
                            self.pulse_analysis_stop(dev_id, dev)
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        # stop pulse analysis if exception occurs
                        self.pulse_analysis_stop(dev_id, dev)

    def pulse_analysis_stop(self, device_id, device_param):
        """Stop CPC pulse analysis, resume normal operation."""
        # restore original threshold value to device
        try:
            cpc_settings = self.data_holder.get_device_settings(device_id)
            if cpc_settings:
                device_param.child('Connection').value().send_message(":SET:OPC:THRS " + str(cpc_settings.opc_threshold))
        except Exception as e:
            print(traceback.format_exc())
            logging.exception(e)
        # clear current threshold value
        device_widget = self.data_holder.device_widgets[device_id]
        device_widget.pulse_quality.current_threshold.setText("")
        # set device.pulse_analysis_index to -1 (signaling analysis ending, waiting for threshold restore)
        # then set to None after delay to resume normal measurement
        # delay ensures CPC has time to set original threshold before measurement continues
        from PyQt5.QtCore import QTimer
        device_widget.pulse_analysis_index = -1  # -1 = ending, waiting for threshold restore
        QTimer.singleShot(1000, lambda: setattr(device_widget, 'pulse_analysis_index', None))
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

    
    # start CPC pulse analysis, stop normal operation
    def pulse_analysis_start(self, device_id, device_param):
        # ask for user confirmation before starting
        from PyQt5.QtWidgets import QMessageBox
        start = QMessageBox.question(self, 'Start pulse analysis?', 'Regular measurement for this device will pause for one minute.\nStart pulse analysis?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if start == QMessageBox.No:
            return
        try:
            # set device.pulse_analysis_index to 0 (start analysis)
            device_widget = self.data_holder.device_widgets[device_id]
            device_widget.pulse_analysis_index = 0
            # update pulse analysis status
            device_widget.pulse_quality.update_pa_status(True)
            # disable command input
            self.data_holder.device_widgets[device_id].set_tab.command_widget.disable_command_input()

            # get original threshold value from device settings
            # value should stay intact during pulse analysis, settings are not updated
            cpc_settings = self.data_holder.get_device_settings(device_id)
            original_threshold = cpc_settings.opc_threshold if cpc_settings else nan
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
