from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QSplitter, QTabWidget, QGridLayout, QWidget,
    QSizePolicy)
from numpy import nan


from config import PSM, PSM2, PSM_ERRORS
from widgets import (
    CommandWidget,
    SetWidget,
    ToggleButton,
    IndicatorWidget,
    StartButton,
    StepsWidget
)

from plots.device_plots import SinglePlot
from devices.base_device import ComplexDevice
from devices.device_data import PSMData, PSMSettings
from devices.psm_contour_tab import PSMContourTab
from utils import compile_psm_settings
from plotting.device_plot_configs import PSMPlotConfig
from devices.data_writers import PSMDataWriter

# PSM widget
class PSMWidget(ComplexDevice):
    def __init__(self, device_config, *args, **kwargs):
        super().__init__(device_config, *args, **kwargs)
        # device_type is already set by BaseDevice from device_config
        device_type = device_config.device_type
        self.connected_cpc_device = None  # Direct reference to connected CPC widget
        self._needs_cpc_dropdown_update = False  # Flag for lazy dropdown updates
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
        # create contour plot tab for PSM
        self.contour_tab = PSMContourTab(self.device_config)
        self.addTab(self.contour_tab, "Contour Plot")

        # create list of PSM status widgets, used in update_errors
        self.psm_status_widgets = [
            self.status_tab.temp_growth_tube, self.status_tab.temp_saturator,
            self.status_tab.flow_saturator, self.status_tab.temp_heater,
            self.status_tab.temp_inlet, "mix1_press", "mix2_press",
            self.status_tab.pressure_inlet, self.status_tab.flow_excess,
            "drain_level", self.status_tab.temp_cabin, self.status_tab.temp_drainage,
            self.status_tab.pressure_critical_orifice, "mfc_temp"
        ]
        # if PSM 2.0, add vacuum flow widget to list
        if device_type == PSM2:
            self.psm_status_widgets.append(self.status_tab.flow_vacuum)

        # PSM-specific flags
        self.needs_settings_fetch = True  # Fetch settings on initial connection

        # Plot configuration (composition over inheritance)
        self.plot_config = PSMPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = PSMDataWriter(self)

        # Add Connected CPC dropdown to Device settings tab
        self._add_connected_cpc_dropdown()

        # Add Device tab at the end
        self._add_device_tab_at_end()

    def get_plot_keys(self):
        """PSM has a single concentration plot."""
        return ['']

    def showEvent(self, event):
        """Override showEvent to lazily update CPC dropdown when widget becomes visible."""
        super().showEvent(event)
        # Update CPC dropdown if needed (deferred from device addition)
        if self._needs_cpc_dropdown_update:
            self._needs_cpc_dropdown_update = False
            if hasattr(self, 'app_config') and hasattr(self, 'connected_cpc_dropdown'):
                # Use QTimer.singleShot to defer update to next event loop iteration
                # This allows the UI to finish showing the widget before updating dropdown
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, self._populate_cpc_dropdown)

    def set_app_config(self, app_config):
        """Set the app config reference for contour tab historical data loading."""
        if hasattr(self, 'contour_tab'):
            self.contour_tab.app_config = app_config
        # Store app_config reference for CPC dropdown
        self.app_config = app_config
        # Mark dropdown for lazy update instead of updating immediately
        # This prevents blocking during device creation
        if hasattr(self, 'connected_cpc_dropdown'):
            self._needs_cpc_dropdown_update = True

    def _add_connected_cpc_dropdown(self):
        """Add Connected CPC dropdown to Device settings tab."""
        # Add Connected CPC dropdown after standard fields
        from PyQt5.QtWidgets import QComboBox
        self.connected_cpc_dropdown = QComboBox()
        self.connected_cpc_dropdown.setStyleSheet("padding: 5px;")
        self.connected_cpc_dropdown.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        # Set minimum width for dropdown popup to show full option text
        self.connected_cpc_dropdown.view().setMinimumWidth(250)

        # Don't populate immediately - add just "None" option to avoid empty dropdown
        # Actual population will happen lazily when PSM tab is shown (via showEvent)
        self.connected_cpc_dropdown.blockSignals(True)
        self.connected_cpc_dropdown.addItem("None", "None")
        self.connected_cpc_dropdown.blockSignals(False)
        # Mark as needing update for when tab is shown
        self._needs_cpc_dropdown_update = True

        # Connect change signal
        def update_connected_cpc(index):
            selected_cpc_id = self.connected_cpc_dropdown.currentData()
            if selected_cpc_id is None:
                selected_cpc_id = 'None'
            self.device_config.extra_params['connected_cpc'] = selected_cpc_id
            # Trigger config save
            if hasattr(self, 'on_config_changed'):
                self.on_config_changed()

        self.connected_cpc_dropdown.currentIndexChanged.connect(update_connected_cpc)

        # Add to layout AFTER populating (Qt calculates width based on content)
        self._device_settings_form_layout.addRow("Connected CPC:", self.connected_cpc_dropdown)

    def _populate_cpc_dropdown(self, cpc_dict=None):
        """
        Populate Connected CPC dropdown from CPC devices.

        Args:
            cpc_dict: Optional dict of {name: device_id} for CPCs. If not provided,
                     will iterate through app_config.devices (slower).
        """
        # Store current selection
        current_cpc_id = self.device_config.extra_params.get('connected_cpc', 'None')

        # Disable updates during population to batch all Qt redraws
        self.connected_cpc_dropdown.setUpdatesEnabled(False)
        self.connected_cpc_dropdown.blockSignals(True)

        # Clear and rebuild dropdown
        self.connected_cpc_dropdown.clear()

        # Always add "None" option first
        self.connected_cpc_dropdown.addItem("None", "None")

        # Add CPC devices - use dict if provided (fast), otherwise iterate (slow)
        if cpc_dict:
            # Use pre-built dict (O(n) performance)
            for cpc_name, cpc_id in cpc_dict.items():
                if cpc_id != 'None':  # Skip the 'None' entry
                    self.connected_cpc_dropdown.addItem(cpc_name, cpc_id)
        else:
            # Fallback: iterate through devices (O(n) but called from O(n) loop = O(n²))
            if hasattr(self, 'app_config') and self.app_config:
                from config import CPC
                for device_config in self.app_config.devices:
                    if device_config.device_type == CPC:
                        device_name = device_config.device_nickname or device_config.device_type_name
                        self.connected_cpc_dropdown.addItem(device_name, device_config.device_id)

        # Restore previous selection
        index = self.connected_cpc_dropdown.findData(current_cpc_id)
        if index >= 0:
            self.connected_cpc_dropdown.setCurrentIndex(index)

        self.connected_cpc_dropdown.blockSignals(False)

        # Re-enable updates and trigger single geometry recalculation
        # Qt will automatically calculate proper dropdown width
        self.connected_cpc_dropdown.setUpdatesEnabled(True)

    # convert PSM status hex to binary and update error label colors
    def update_errors(self, status_hex):
        widget_amount = len(self.psm_status_widgets) # get amount of widgets in list
        status_bin = bin(int(status_hex, 16)) # convert hex to int and int to binary
        status_bin = status_bin[2:].zfill(widget_amount) # remove 0b from string and fill with 0s to length of widget_amount
        total_errors = status_bin.count("1") # count number of 1s in status_bin
        inverted_status_bin = status_bin[::-1] # invert status_bin for error parsing
        for i in range(widget_amount): # iterate through all status widgets
            if type(self.psm_status_widgets[i]) != str: # filter placeholder strings
                # change color of error label according to error bit
                self.psm_status_widgets[i].change_color(inverted_status_bin[i])
        
        return total_errors # return total number of errors
    
    # convert PSM notes hex to binary and update liquid mode settings
    def update_notes(self, note_hex):
        liquid_errors = 0 # increment if liquid errors occur
        note_length = 7 # if new note bits are added in firmware, change this value accordingly
        note_bin = bin(int(note_hex, 16)) # convert hex to int and int to binary
        note_bin = note_bin[2:].zfill(note_length) # remove 0b from string and fill with 0s
        total_notes = note_bin.count("1") # count number of 1s in note_bin
        inverted_note_bin = note_bin[::-1] # invert note_bin for liquid setting parsing
        # update liquid mode settings in GUI
        # 0 = autofill on, 1 = autofill off
        if inverted_note_bin[5] == "0":
            self.set_tab.autofill.update_state(1)
        elif inverted_note_bin[5] == "1":
            self.set_tab.autofill.update_state(0)
        # 0 = drying off, 1 = drying on
        self.set_tab.drying.update_state(int(inverted_note_bin[4]))
        # 0 = drain on, 1 = drain off
        if inverted_note_bin[3] == "0":
            self.set_tab.drain.update_state(1)
        elif inverted_note_bin[3] == "1":
            self.set_tab.drain.update_state(0)
        # 0 = saturator liquid level OK, 1 = saturator liquid level LOW
        self.status_tab.liquid_saturator.change_color(inverted_note_bin[6])
        if inverted_note_bin[6] == "1":
            liquid_errors += 1
        # 0 = drain liquid level OK, 1 = drain liquid level HIGH
        self.status_tab.liquid_drain.change_color(inverted_note_bin[0])
        if inverted_note_bin[0] == "1":
            liquid_errors += 1

        return liquid_errors # return total number of liquid errors

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

    def get_read_command(self):
        """PSM auto-pushes measurement data, no read command needed for data."""
        # Note: Settings queries (:SYST:PRNT, :SYST:VCMP) are sent separately
        return None

    def get_status_bar_text(self):
        """Get formatted text for status bar display."""
        # Show measurement mode and state
        if hasattr(self, 'measure_tab'):
            measure_tab = self.measure_tab
            if hasattr(measure_tab, 'scan_button') and measure_tab.scan_button.measuring:
                return "Scanning"
            elif hasattr(measure_tab, 'step_button') and measure_tab.step_button.measuring:
                return "Step scan"
            elif hasattr(measure_tab, 'fixed_button') and measure_tab.fixed_button.measuring:
                return "Fixed mode"
        return "Idle"

    def process_parsed_messages(self, parsed_messages, device_config, data_holder):
        """
        Process PSM messages with buffering, settings compilation, and error handling.
        """
        from numpy import isnan
        from utils import compile_psm_settings
        import logging
        import traceback

        result = {
            'data_updated': False,
            'settings_updated': False,
            'needs_gui_update': False
        }

        # Clear extra data buffer after 60 seconds of consecutive buffering
        if self.dev_id in data_holder.extra_data and self._extra_data_counter >= 60:
            del data_holder.extra_data[self.dev_id]
            logging.info("PSM %s extra data buffer cleared", self.device_config.serial_number)

        # Initialize from extra_data buffer
        was_present = self.dev_id in data_holder.extra_data
        if was_present:
            self._extra_data_counter += 1
        else:
            self._extra_data_counter = 0

        data_holder.par_updates[self.dev_id] = 0
        settings_fetched = False

        # Process each parsed message
        for parsed in parsed_messages:
            if parsed is None:
                continue  # Skip unparseable messages
            if parsed['type'] == 'data':
                # Store measurement data with buffering (uses current_data now)
                if isnan(float(self.current_data.saturator_flow)):
                    # First data received - no buffering needed
                    pass
                else:
                    # Buffer extra data for next update cycle
                    data_holder.extra_data[self.dev_id] = parsed['data']

                result['data_updated'] = True

                # Note: polynomial correction already stored in self.current_data.poly_correction

                # Set error flags
                if parsed.get('has_errors', False):
                    data_holder.error_status = 1
                    data_holder.device_errors[self.dev_id] = True

            elif parsed['type'] == 'settings':
                # Store PRNT settings (legacy - settings already in self.settings dataclass)
                settings_fetched = True

            elif parsed['type'] == 'dilution':
                # Store dilution parameters directly in settings
                self.settings.dilution_parameters = parsed['data']

            elif parsed['type'] == 'self_test':
                # Display self-test errors
                from config import PSM_ERRORS
                self.set_tab.command_widget.update_text_box("self test error binary: " +
                    bin(int(parsed['data'], 16))[2:].zfill(len(PSM_ERRORS)))
                for error_msg in parsed.get('errors', []):
                    self.set_tab.command_widget.update_text_box(error_msg)

            elif parsed['type'] == 'info' and parsed['command'] == '*IDN':
                # Handle device identification
                serial_number = parsed['data']
                if self.device_config.serial_number != serial_number:
                    self.device_config.serial_number = serial_number
                    if hasattr(self, 'on_config_changed') and self.on_config_changed:
                        self.on_config_changed()
                if self.dev_id in data_holder.idn_inquiry_devices:
                    data_holder.idn_inquiry_devices.remove(self.dev_id)

            elif parsed['type'] == 'firmware':
                # Update firmware version
                firmware_version = parsed['data']
                current_fw = self.device_config.extra_params.get('firmware_version', '')
                if current_fw != firmware_version:
                    self.device_config.extra_params['firmware_version'] = firmware_version

            # Show messages in command widget if requested
            if parsed.get('show_in_command_widget', False):
                self.set_tab.command_widget.update_text_box(parsed['raw'])
                if parsed['type'] == 'error' and 'error' in parsed:
                    print("PSM error: " + str(parsed['error']))

        # Compile settings if all required data is available
        if self.needs_settings_fetch and settings_fetched and self.settings.dilution_parameters:
            try:
                # Get CO flow rate (PSM Retrofit only)
                from config import PSM
                # Update settings with co_flow (dilution_parameters already set above)
                if self.dev_type == PSM:
                    self.settings.co_flow = round(self.set_tab.set_co_flow.value_spinbox.value(), 3)
                else:
                    self.settings.co_flow = nan

                # Get settings array from device's typed settings dataclass
                # Note: inlet_flow_rate is updated by plot_manager, CPC settings added by data_logger

                data_holder.par_updates[self.dev_id] = 1
                self.needs_settings_fetch = False
                result['settings_updated'] = True
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

        return result

    def handle_serial_data(self, connection, data_holder=None):
        """
        Handle PSM serial data with partial message buffering.

        PSM messages can be split across multiple reads, so we buffer
        incomplete messages in data_holder.partial_data[dev_id].
        """
        results = []
        try:
            raw_data = connection.connection.read_all()
            if not raw_data:
                return results

            # Decode and split by \r
            messages = raw_data.decode().split("\r")

            # Handle partial message from previous read
            if self._partial_data:
                messages[0] = self._partial_data + messages[0]
                self._partial_data = ""

            # Check if last message is complete (ends with \r)
            if messages[-1] == "":
                messages = messages[:-1]  # Complete, remove empty element
            else:
                # Incomplete, save for next read
                self._partial_data = messages[-1]
                messages = messages[:-1]

            # Parse each complete message
            for message in messages:
                if message:
                    parsed = self.parse_message(message, data_holder)
                    results.append(parsed)

        except Exception as e:
            results.append({
                'type': 'error',
                'command': 'serial_read',
                'data': None,
                'error': str(e),
                'raw': '',
                'update_gui': False
            })

        return results

    def parse_message(self, message, data_holder=None):
        """
        Parse PSM serial messages.

        Handles multiple message types:
        - :MEAS:SCAN/:MEAS:STEP/:MEAS:FIXD - measurement data
        - :SYST:PRNT - settings data
        - :SYST:VCMP - dilution parameters
        - :STAT:SELF:LOG - self-test errors
        - :SELF:ERR - error messages
        - *IDN - device identification
        - Firmware - firmware version
        """
        try:
            # Split command and data
            message_string = message
            parts = message.split(" ", 1)
            if len(parts) < 2:
                return {
                    'type': 'unknown',
                    'command': parts[0] if parts else '',
                    'data': None,
                    'raw': message,
                    'update_gui': False
                }

            command = parts[0]
            data = parts[1].split(",")

            # Handle measurement commands
            if command in [":MEAS:SCAN", ":MEAS:STEP", ":MEAS:FIXD"]:
                status_hex = data[-2]
                note_hex = data[-1]

                # Update error indicators
                total_errors = self.update_errors(status_hex)

                # Update liquid states
                liquid_errors = self.update_notes(note_hex)

                # Store polynomial correction value
                poly_correction = float(data[14])

                # Determine scan status (firmware version dependent)
                scan_status = "9"  # undefined by default
                try:
                    firmware_version_str = self.device_config.extra_params.get('firmware_version', '')
                    if firmware_version_str != "":
                        firmware_version = firmware_version_str.split(".")
                        # Retrofit: version >= 0.5.5
                        if self.device_type == PSM:
                            if int(firmware_version[1]) > 5:
                                scan_status = data[15]
                            elif int(firmware_version[1]) == 5 and int(firmware_version[2]) >= 5:
                                scan_status = data[15]
                        # PSM 2.0: version >= 0.6.8
                        elif self.device_type == PSM2:
                            if int(firmware_version[1]) > 6:
                                scan_status = data[15]
                            elif int(firmware_version[1]) == 6 and int(firmware_version[2]) >= 8:
                                scan_status = data[15]
                except Exception:
                    # If firmware version check fails, keep scan_status as "9" (undefined)
                    pass

                # Update new data object
                self.current_data.saturator_flow = float(data[0])
                self.current_data.excess_flow = float(data[1])
                self.current_data.temp_growth_tube = float(data[2])
                self.current_data.temp_saturator = float(data[3])
                self.current_data.temp_inlet = float(data[4])
                self.current_data.temp_heater = float(data[5])
                self.current_data.temp_drainage = float(data[6])
                self.current_data.temp_cabin = float(data[7])
                self.current_data.sat_flow_setpoint = float(data[8])
                self.current_data.pres_inlet = float(data[9])
                self.current_data.pres_inlet_saturator = float(data[10])
                self.current_data.pres_saturator_excess = float(data[11])
                self.current_data.pres_critical_orifice = float(data[12])
                if self.device_type == PSM2: 
                    self.current_data.vacuum_flow = float(data[13])
                self.current_data.poly_correction = poly_correction
                self.current_data.scan_status = scan_status # [15]
                self.current_data.status_hex = status_hex # [-2]
                self.current_data.note_hex = note_hex # [-1]
                self.current_data.total_errors = total_errors
                self.current_data.liquid_errors = liquid_errors

                # Update GUI
                self.update_values(data)
                self.measure_tab.change_mode_color(command)

                has_errors = (total_errors + liquid_errors) > 0

                return {
                    'type': 'data',
                    'command': command,
                    'data': self.current_data.to_array(),  # Use dataclass to_array() instead of compile_psm_data
                    'status_hex': status_hex,
                    'note_hex': note_hex,
                    'total_errors': total_errors,
                    'liquid_errors': liquid_errors,
                    'poly_correction': poly_correction,
                    'raw': message,
                    'update_gui': True,
                    'has_errors': has_errors
                }

            # Handle :SYST:PRNT - settings
            elif command == ":SYST:PRNT":
                # Update settings object
                self.settings.mode = int(data[0])
                self.settings.temp_growth_tube = float(data[1])
                self.settings.temp_saturator = float(data[2])
                self.settings.temp_inlet = float(data[3])
                self.settings.temp_heater = float(data[4])
                self.settings.temp_drainage = float(data[5])
                self.settings.cpc_inlet_flow = float(data[6])

                # Update GUI
                self.update_settings(data)

                return {
                    'type': 'settings',
                    'command': command,
                    'data': data,
                    'raw': message,
                    'update_gui': True,
                    'show_in_command_widget': True
                }

            # Handle :SYST:VCMP - dilution parameters
            elif command == ":SYST:VCMP":
                if len(data) == 6:
                    return {
                        'type': 'dilution',
                        'command': command,
                        'data': data,
                        'raw': message,
                        'update_gui': False,
                        'show_in_command_widget': True
                    }
                else:
                    return {
                        'type': 'error',
                        'command': command,
                        'data': None,
                        'error': f'Invalid dilution parameters: {len(data)} values (expected 6)',
                        'raw': message,
                        'update_gui': False,
                        'show_in_command_widget': True
                    }

            # Handle :STAT:SELF:LOG - self-test errors
            elif command == ":STAT:SELF:LOG":
                error_length = len(PSM_ERRORS)
                status_bin = bin(int(data[0], 16))[2:].zfill(error_length)
                inverted_status_bin = status_bin[::-1]

                # Build error messages
                error_messages = []
                for i in range(error_length):
                    if inverted_status_bin[i] == "1":
                        # Special handling for MFC_HEATER/MFC_EXCESS error (index 27)
                        if i == 27 and self.device_type == PSM:
                            error_messages.append(f"Bit {i}: ERROR_SELFTEST_MFC_EXCESS")
                        else:
                            error_messages.append(f"Bit {i}: {PSM_ERRORS[i]}")

                return {
                    'type': 'self_test',
                    'command': command,
                    'data': data[0],
                    'errors': error_messages,
                    'raw': message,
                    'update_gui': False,
                    'show_in_command_widget': True
                }

            # Handle :SELF:ERR - error message
            elif command == ":SELF:ERR":
                error_code = int(data[0])
                # Special handling for index 27
                if error_code == 27 and self.device_type == PSM:
                    error_msg = "ERROR_SELFTEST_MFC_EXCESS"
                else:
                    error_msg = PSM_ERRORS[error_code] if error_code < len(PSM_ERRORS) else "Unknown error"

                return {
                    'type': 'error',
                    'command': command,
                    'data': error_code,
                    'error': error_msg,
                    'raw': message,
                    'update_gui': False,
                    'show_in_command_widget': True
                }

            # Handle *IDN - identification
            elif command == "*IDN":
                serial_number = data[0].strip()
                return {
                    'type': 'info',
                    'command': command,
                    'data': serial_number,
                    'raw': message,
                    'update_gui': False,
                    'show_in_command_widget': True
                }

            # Handle Firmware - firmware version
            elif command == "Firmware":
                if "version: " in data[0]:
                    firmware_version = data[0].split(": ")[1]
                    return {
                        'type': 'firmware',
                        'command': command,
                        'data': firmware_version,
                        'raw': message,
                        'update_gui': False,
                        'show_in_command_widget': True
                    }

            # Unknown command
            else:
                return {
                    'type': 'unknown',
                    'command': command,
                    'data': data,
                    'raw': message,
                    'update_gui': False,
                    'show_in_command_widget': True
                }

        except Exception as e:
            # On parsing error, reset mode colors
            try:
                self.measure_tab.scan.change_color(0)
                self.measure_tab.step.change_color(0)
                self.measure_tab.fixed.change_color(0)
            except Exception:
                pass  # Widget may not exist yet

            return {
                'type': 'error',
                'command': 'unknown',
                'data': None,
                'error': str(e),
                'raw': message,
                'update_gui': False
            }

    # Device Manager Integration Methods

    def supports_firmware_inquiry(self):
        """PSM supports firmware inquiry."""
        return True

    def has_status_tab(self):
        """PSM has a status tab."""
        return True

    def get_status_tab(self):
        """Return PSM status tab."""
        return self.status_tab

    def has_device_specific_errors(self):
        """PSM has CO flow error (PSM Retrofit only)."""
        from config import PSM
        if self.device_config.device_type == PSM:
            return hasattr(self.set_tab, 'set_co_flow') and self.set_tab.set_co_flow.error
        return False

    def supports_10hz_mode(self):
        """PSM supports 10 Hz mode."""
        return True

    def on_connection_established(self):
        """
        Reset PSM state on connection.

        Clears firmware version and dilution parameters so they are re-fetched.
        """
        # Clear firmware version
        self.device_config.extra_params['firmware_version'] = ""

        # Clear dilution parameters in device settings
        if self.settings:
            self.settings.dilution_parameters = []

    def send_read_commands(self, dev_conn, device_config):
        """
        Send PSM read commands for settings and dilution parameters.

        Sends:
        - :SYST:PRNT if settings need to be fetched
        - :SYST:VCMP if dilution parameters are missing
        """
        if self.needs_settings_fetch:
            dev_conn.send_message(":SYST:PRNT")

        if self.settings and not self.settings.dilution_parameters:
            dev_conn.send_delayed_message(":SYST:VCMP", 150)

    def validate_10hz_mode(self, app_config, device_config):
        """
        Validate and synchronize PSM 10 Hz mode.

        When PSM 10 Hz is enabled, ensure connected CPC also has 10 Hz enabled.
        """
        from config import CPC

        if device_config.extra_params.get('10_hz', False):
            cpc_id = device_config.extra_params.get('connected_cpc', 'None')
            if cpc_id != 'None':
                # Find connected CPC and enable its 10 Hz mode
                for cpc_config in app_config.devices:
                    if cpc_config.device_id == cpc_id and cpc_config.device_type == CPC:
                        if not cpc_config.extra_params.get('10_hz', False):
                            cpc_config.extra_params['10_hz'] = True
                            # Trigger config save
                            if hasattr(self, 'on_config_changed'):
                                self.on_config_changed()
                        break


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
        self.set_minimum_flow.value_spinbox.setValue(0.15)
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

__all__ = ['PSMWidget']
