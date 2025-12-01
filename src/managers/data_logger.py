# managers/data_logger.py
from datetime import datetime as dt
import logging
import traceback
from numpy import isnan, nan
from config import osx_mode, TSI_CPC, EXAMPLE_DEVICE, PULSE_ANALYSIS_THRESHOLDS

class DataLogger:
    def __init__(self, data_holder, config):
        self.data_holder = data_holder
        self.config = config
        self._last_file_path = ""  # Track last written path for change detection

    def on_data_settings_changed(self, data_settings):
        """Called when data settings change (connected to signal from app.py)."""
        # Reset filenames if path changed
        if data_settings.file_path != self._last_file_path:
            self._last_file_path = data_settings.file_path
            self.reset_all_filenames()

        # Reset state when saving is off
        if not data_settings.save_data:
            self.reset_all_filenames()
            self.data_holder.last_write_timestamp = None
            self.data_holder.most_recent_filename = ""

    def _is_device_in_pulse_analysis(self, dev_id):
        """Check if device is in pulse analysis mode."""
        device_widget = self.data_holder.device_widgets.get(dev_id)
        if device_widget and hasattr(device_widget, 'pulse_analysis_index'):
            # 0-6 = analyzing, -1 = ending, None = not analyzing
            return device_widget.pulse_analysis_index is not None and device_widget.pulse_analysis_index >= 0
        return False

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
        """Compare current day to file start day and reset files at midnight if needed."""
        # check if saving is on
        if self.config.data_settings.save_data:
            # check if new file should be started at midnight
            if self.config.data_settings.generate_daily_files:
                current_day = dt.fromtimestamp(self.data_holder.current_time).strftime("%m%d")
                if current_day != self.data_holder.start_day:
                    self.reset_all_filenames() # start new file if day has changed
                    # update start day
                    self.data_holder.start_day = current_day

    def _create_data_file(self, device_config, timestamp, file_extension):
        """
        Create a new data file (.dat, .par, etc.) for a device.

        Returns:
            str: The filename (with path separator but without full path)
        """
        # format timestamp for filename
        timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))

        # get serial number from device config
        serial_number = device_config.serial_number
        if serial_number != "":
            serial_number = '_' + serial_number

        # get device type name from device config
        device_type_name = device_config.device_type_name

        # get device nickname from device config
        device_nickname = device_config.device_nickname
        if device_nickname != "":
            device_nickname = '_' + device_nickname

        # get file tag from data settings
        file_tag = self.config.data_settings.file_tag
        if file_tag != "":
            file_tag = '_' + file_tag

        # compile filename
        if osx_mode:
            filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.' + file_extension
        else:
            filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + file_tag + '.' + file_extension

        # create empty file
        with open(self.config.data_settings.file_path + filename, "w", encoding='UTF-8'):
            pass

        # Track most recent filename (store just the filename without path separator for display)
        self.data_holder.most_recent_filename = filename.lstrip('/\\')

        return filename

    def _create_10hz_file(self, device_config, timestamp):
        """
        Create a 10Hz CSV file for CPC devices.

        Returns:
            str: The filename (with path separator but without full path)
        """
        # format timestamp for filename
        timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))

        # get serial number from device config
        serial_number = device_config.serial_number
        if serial_number != "":
            serial_number = '_' + serial_number

        # get device type name from device config
        device_type_name = device_config.device_type_name

        # get device nickname from device config
        device_nickname = device_config.device_nickname
        if device_nickname != "":
            device_nickname = '_' + device_nickname

        # get file tag from data settings
        file_tag = self.config.data_settings.file_tag
        if file_tag != "":
            file_tag = '_' + file_tag

        # compile filename with _10hz suffix
        if osx_mode:
            filename = '/' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + '_10hz' + file_tag + '.csv'
        else:
            filename = '\\' + timestamp_file + serial_number + '_' + device_type_name + device_nickname + '_10hz' + file_tag + '.csv'

        # create file and write header
        with open(self.config.data_settings.file_path + filename, "w", encoding='UTF-8') as file:
            file.write('YYYY.MM.DD hh:mm:ss,Concentration 1 (#/cc),Concentration 2 (#/cc),Concentration 3 (#/cc),Concentration 4 (#/cc),Concentration 5 (#/cc),Concentration 6 (#/cc),Concentration 7 (#/cc),Concentration 8 (#/cc),Concentration 9 (#/cc),Concentration 10 (#/cc)')

        # Track most recent filename (store just the filename without path separator for display)
        self.data_holder.most_recent_filename = filename.lstrip('/\\')

        return filename

    def write_data(self):
        """Write data to file(s)."""
        # if saving is on
        if self.config.data_settings.save_data:
            # Validate file path before attempting to save
            if not self.config.data_settings.file_path:
                self.data_holder.saving_status = 0
                return

            # create timestamp from data_holder.current_time
            timestamp = dt.fromtimestamp(self.data_holder.current_time)
            timeStampStr = str(timestamp.strftime("%Y.%m.%d %H:%M:%S"))
            # go through each device
            for device_config in self.config.devices:
                # if device is TSI CPC, do nothing
                if device_config.device_type == TSI_CPC:
                    pass
                # if device is in pulse analysis mode, do nothing
                elif self._is_device_in_pulse_analysis(device_config.device_id):
                    pass
                else:
                    device_widget = self.data_holder.device_widgets.get(device_config.device_id)
                    if not device_widget:
                        continue

                    # Check if device is connected OR example device
                    is_connected = hasattr(device_widget, 'is_connected') and device_widget.is_connected
                    is_example = device_config.device_type == EXAMPLE_DEVICE

                    if is_connected or is_example:
                        try:
                            # store device id to variable for clarity
                            dev_id = device_config.device_id

                            # Verify device has data_writer
                            if not hasattr(device_widget, 'data_writer'):
                                continue

                            data_writer = device_widget.data_writer

                            # if device is not yet in data_holder.dat_filenames dict, create files
                            if dev_id not in self.data_holder.dat_filenames:
                                # Create .dat file
                                filename = self._create_data_file(device_config, timestamp, 'dat')
                                self.data_holder.dat_filenames[dev_id] = filename

                                # Create .par file if device writes .par files
                                if 'par' in data_writer.get_file_types():
                                    filename = self._create_data_file(device_config, timestamp, 'par')
                                    self.data_holder.par_filenames[dev_id] = filename
                                    self.data_holder.par_updates[dev_id] = 1  # set .par update flag

                            # Check if device needs special files (e.g., 10Hz logging)
                            if data_writer.has_special_files():
                                if dev_id not in self.data_holder.ten_hz_filenames:
                                    filename = self._create_10hz_file(device_config, timestamp)
                                    self.data_holder.ten_hz_filenames[dev_id] = filename

                            # Write .dat file
                            filename = self.config.data_settings.file_path + self.data_holder.dat_filenames[dev_id]

                            # Check if header exists
                            with open(filename, 'r', encoding='UTF-8') as file:
                                file.seek(0)
                                header_row1 = file.readline()
                                write_headers = len(header_row1) == 0

                            # Append file with new data
                            with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                                # Write header if it doesn't exist
                                if write_headers:
                                    file.write(data_writer.get_dat_header())

                                # Write the actual data
                                file.write("\n")
                                file.write(timeStampStr + ',')
                                # Get data from data_writer
                                write_data = data_writer.get_dat_data(self.data_holder, timeStampStr)
                                file.write(write_data)

                            # Update last write timestamp after successful write
                            self.data_holder.last_write_timestamp = self.data_holder.current_time

                            # Write .par file if device has one and should be updated
                            if 'par' in data_writer.get_file_types() and data_writer.should_write_par(self.data_holder):
                                # Get filename from dictionary and add path to front
                                filename = self.config.data_settings.file_path + self.data_holder.par_filenames[dev_id]

                                # Check if header exists
                                with open(filename, 'r', encoding='UTF-8') as file:
                                    file.seek(0)
                                    header_row1 = file.readline()
                                    write_headers = len(header_row1) == 0

                                # Append file with new data
                                with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
                                    # Write header if it doesn't exist
                                    if write_headers:
                                        file.write(data_writer.get_par_header())

                                    # Write settings data
                                    file.write("\n")
                                    file.write(timeStampStr + ',')
                                    write_data = data_writer.get_par_data(self.data_holder, timeStampStr)
                                    if write_data:
                                        file.write(write_data)

                                # Reset par_updates flag after writing
                                if dev_id in self.data_holder.par_updates:
                                    self.data_holder.par_updates[dev_id] = 0

                            # Write special files if device needs them (e.g., 10Hz)
                            if data_writer.has_special_files():
                                data_writer.write_special_files(self.config.data_settings.file_path, timeStampStr,
                                                               self.data_holder.ten_hz_filenames)
                        # if saving fails, set saving status to 0
                        except Exception as e:
                            print(traceback.format_exc())
                            logging.exception(e)
                            self.data_holder.saving_status = 0 # set saving status to 0
        else: # if saving is toggled off
            self.data_holder.saving_status = 0 # set saving status to 0
       
        # write data to pulse analysis file if pulse analysis is on
        for device_config in self.config.devices:
            dev_id = device_config.device_id
            device_widget = self.data_holder.device_widgets.get(dev_id)
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
                            self.pulse_analysis_stop(dev_id, device_config)
                    except Exception as e:
                        print(traceback.format_exc())
                        logging.exception(e)
                        # stop pulse analysis if exception occurs
                        self.pulse_analysis_stop(dev_id, device_config)

    def pulse_analysis_stop(self, device_id, device_config):
        """Stop CPC pulse analysis, resume normal operation."""
        # restore original threshold value to device
        try:
            cpc_settings = self.data_holder.get_device_settings(device_id)
            device_widget = self.data_holder.device_widgets[device_id]
            if cpc_settings and hasattr(device_widget, 'connection'):
                device_widget.connection.send_message(":SET:OPC:THRS " + str(cpc_settings.opc_threshold))
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
    def pulse_analysis_start(self, device_id, device_config):
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
                self.pulse_analysis_stop(device_id, device_config)
                return

            # clear previous pulse analysis points
            self.data_holder.device_widgets[device_id].pulse_quality.clear_analysis_points()

            # create file and store threshold value
            filepath = self.config.data_settings.file_path
            # timestamp
            timestamp = dt.fromtimestamp(self.data_holder.current_time)
            timestamp_file = str(timestamp.strftime("%Y%m%d_%H%M%S"))
            # serial number
            serial_number = device_config.serial_number
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
            self.pulse_analysis_stop(device_id, device_config)
