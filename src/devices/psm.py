from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (QSplitter, QTabWidget, QGridLayout, QWidget,
    QSizePolicy, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QStackedWidget,
    QComboBox, QCheckBox, QPushButton, QScrollArea, QFrame)
from numpy import nan
import numpy as np
import logging
import pyqtgraph as pg


# Button styles for different states
STYLE_BTN_START = """
    QPushButton { background-color: #4CAF50; color: white; padding: 6px 16px; font-size: 13px; font-weight: bold; border: none; border-radius: 4px; }
    QPushButton:hover { background-color: #45a049; }
    QPushButton:disabled { background-color: #ccc; color: #888; }
"""
STYLE_BTN_UPDATE = """
    QPushButton { background-color: #2196F3; color: white; padding: 6px 16px; font-size: 13px; font-weight: bold; border: none; border-radius: 4px; }
    QPushButton:hover { background-color: #1976D2; }
    QPushButton:disabled { background-color: #ccc; color: #888; }
"""
STYLE_BTN_RUNNING = """
    QPushButton { background-color: #9E9E9E; color: white; padding: 6px 16px; font-size: 13px; border: none; border-radius: 4px; }
    QPushButton:hover { background-color: #757575; }
    QPushButton:disabled { background-color: #ccc; color: #888; }
"""
STYLE_BTN_SENDING = """
    QPushButton { background-color: #FF9800; color: white; padding: 6px 16px; font-size: 13px; border: none; border-radius: 4px; }
    QPushButton:disabled { background-color: #ccc; color: #888; }
"""
# Keep old styles for compatibility (unused now)
STYLE_UPDATE_CLEAN = STYLE_BTN_RUNNING
STYLE_UPDATE_DIRTY = STYLE_BTN_UPDATE
STYLE_UPDATE_SENDING = STYLE_BTN_SENDING

from config import PSM, PSM_ERRORS
from widgets import (
    CommandWidget,
    SetWidget,
    SetStatusWidget,
    ToggleButton,
    ToggleSwitch,
    IndicatorWidget,
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
    # Signal emitted when device link changes: (device_id, link_type, old_target, new_target)
    link_changed = pyqtSignal(int, str, object, object)

    def __init__(self, device_config, *args, **kwargs):
        super().__init__(device_config, *args, **kwargs)
        self._needs_cpc_dropdown_update = False  # Flag for lazy dropdown updates

        # Update device type label to show version (2.0 or Retrofit)
        if hasattr(self, 'device_type_label'):
            self.device_type_label.setText(self.display_device_type)

        # create plot widget for PSM (first tab)
        self.plot_tab = SinglePlot(device_type=PSM)
        self.addTab(self.plot_tab, "Plot")
        # create contour plot tab for PSM (next to Plot tab)
        self.contour_tab = PSMContourTab(self.device_config, self.is_psm2)
        self.addTab(self.contour_tab, "Distribution")
        # create combined control tab for PSM (merges Set and Status tabs)
        self.control_tab = PSMControlTab(self.is_psm2)
        self.addTab(self.control_tab, "Control")
        # Backward compatibility aliases
        self.set_tab = self.control_tab
        self.status_tab = self.control_tab
        # create mode tab for PSM
        self.measure_tab = PSMMeasureTab()
        self.addTab(self.measure_tab, "Measure")

        # create list of PSM status widgets, used in update_errors
        self.psm_status_widgets = [
            self.control_tab.temp_growth_tube, self.control_tab.temp_saturator,
            self.control_tab.flow_saturator, self.control_tab.temp_heater,
            self.control_tab.temp_inlet, "mix1_press", "mix2_press",
            self.control_tab.pressure_inlet, self.control_tab.flow_excess,
            "drain_level", self.control_tab.temp_cabin, self.control_tab.temp_drainage,
            self.control_tab.pressure_critical_orifice, "mfc_temp"
        ]
        # if PSM 2.0, add vacuum flow widget to list
        if self.is_psm2:
            self.psm_status_widgets.append(self.control_tab.flow_vacuum)

        # PSM-specific flags
        self.needs_settings_fetch = True  # Fetch settings on initial connection

        # Plot configuration (composition over inheritance)
        self.plot_config = PSMPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = PSMDataWriter(self)

        # Add Connected CPC dropdown to Device settings tab
        self._add_connected_cpc_dropdown()

        # Ensure CO flow visibility matches PSM type
        # This handles case where PSMSetTab was created with incorrect is_psm2
        # (e.g., firmware_version was empty during widget creation)
        self._update_psm_type_ui()

        # Add Device tab at the end
        self._add_device_tab_at_end()

    @property
    def is_psm2(self) -> bool:
        """Determine if this is PSM 2.0 based on firmware version.

        Returns True if firmware >= 0.6.x (PSM 2.0)
        Returns False if firmware < 0.6.x (Retrofit) or unknown

        Retrofit firmware is always 0.x.x where x < 6
        """
        fw = self.device_config.extra_params.get('firmware_version', '')
        if not fw:
            return False  # Default to Retrofit behavior if unknown
        try:
            parts = fw.split('.')
            major = int(parts[0])
            minor = int(parts[1])
            # Retrofit is always 0.x.x where x < 6
            # PSM 2.0 is 0.6.x and above, or any 1.x.x+
            if major == 0:
                return minor >= 6
            else:
                return True  # Assume 1.x.x+ is PSM 2.0 or newer
        except (IndexError, ValueError):
            return False

    @property
    def display_device_type(self) -> str:
        """Get display name for device type including version.

        Returns "PSM (2.0)", "PSM (Retrofit)", or "PSM" if version unknown.
        """
        fw = self.device_config.extra_params.get('firmware_version', '')
        if not fw:
            return "PSM"  # Version unknown
        if self.is_psm2:
            return "PSM (2.0)"
        else:
            return "PSM (Retrofit)"

    def get_plot_keys(self):
        """PSM has saturator flow plot. Concentration is plotted via connected CPC."""
        return ['']

    def get_plot_value_labels(self):
        """Return labels for PSM plot values in main plot dropdown.

        Returns empty dict since PSM only has one plot value (Saturator Flow).
        No dropdown needed when there's only one option.
        """
        return {}

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
            # Connect config change callback so calibration changes are saved
            self.contour_tab.on_config_changed = lambda: (
                self.on_config_changed() if hasattr(self, 'on_config_changed') and self.on_config_changed else None
            )
            # Trigger auto-load of calibration and historical data now that app_config is set
            self.contour_tab.initialize_after_config_set()
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
            # Get old value before updating
            old_cpc_id = self.device_config.extra_params.get('connected_cpc', 'None')
            self.device_config.extra_params['connected_cpc'] = selected_cpc_id
            # Emit link changed signal for tab grouping
            self.link_changed.emit(
                self.device_config.device_id,
                'psm_cpc',
                old_cpc_id,
                selected_cpc_id
            )
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
        self.control_tab.liquid_saturator.change_color(inverted_note_bin[6])
        if inverted_note_bin[6] == "1":
            liquid_errors += 1
        # 0 = drain liquid level OK, 1 = drain liquid level HIGH
        self.control_tab.liquid_drain.change_color(inverted_note_bin[0])
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
        # update vacuum flow if PSM 2.0 (check hasattr in case widget created before firmware known)
        if self.is_psm2 and hasattr(self.status_tab, 'flow_vacuum'):
            self.status_tab.flow_vacuum.change_value(str(current_list[13]) + " lpm")
        # liquid level values are updated in PSMWidget's update_notes()

    def get_read_command(self):
        """PSM auto-pushes measurement data, no read command needed for data."""
        # Note: Settings queries (:SYST:PRNT, :SYST:VCMP) are sent separately
        return None

    def get_status_bar_text(self):
        if hasattr(self, 'measure_tab') and hasattr(self.measure_tab, '_current_device_mode'):
            mode = self.measure_tab._current_device_mode
            satflow = self.current_data.saturator_flow if hasattr(self, 'current_data') else 0
            if mode == ":MEAS:SCAN":
                return f"Scanning ({satflow:.2f} lpm)"
            elif mode == ":MEAS:STEP":
                return f"Step ({satflow:.2f} lpm)"
            elif mode == ":MEAS:FIXD":
                return f"Fixed ({satflow:.2f} lpm)"
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
                    # Update GUI display
                    self._update_device_settings_display()
                    if hasattr(self, 'on_config_changed') and self.on_config_changed:
                        self.on_config_changed()
                if self.dev_id in data_holder.idn_inquiry_devices:
                    data_holder.idn_inquiry_devices.remove(self.dev_id)

            elif parsed['type'] == 'firmware':
                # Update firmware version
                firmware_version = parsed['data']
                self.device_config.extra_params['firmware_version'] = firmware_version
                # Save config so firmware version persists across restarts
                if hasattr(self, 'on_config_changed') and self.on_config_changed:
                    self.on_config_changed()
                # Always update UI based on PSM type (2.0 vs Retrofit)
                # This ensures CO flow visibility is correct even if firmware was same
                self._update_psm_type_ui()

            # Show messages in command widget if requested
            if parsed.get('show_in_command_widget', False):
                self.set_tab.command_widget.update_text_box(parsed['raw'])
                if parsed['type'] == 'error' and 'error' in parsed:
                    logging.error("PSM error: " + str(parsed['error']))

        # Compile settings if all required data is available
        if self.needs_settings_fetch and settings_fetched and self.settings.dilution_parameters:
            try:
                # Get CO flow rate (Retrofit only)
                # Update settings with co_flow (dilution_parameters already set above)
                if not self.is_psm2:
                    self.settings.co_flow = round(self.set_tab.set_co_flow.value_spinbox.value(), 3)
                else:
                    self.settings.co_flow = nan

                # Get settings array from device's typed settings dataclass
                # Note: inlet_flow_rate is updated by plot_manager, CPC settings added by data_logger

                data_holder.par_updates[self.dev_id] = 1
                self.needs_settings_fetch = False
                result['settings_updated'] = True
            except Exception as e:
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
            message_string = message.strip()
            parts = message_string.split(" ", 1)
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
                        parts = firmware_version_str.split(".")
                        major = int(parts[0])
                        minor = int(parts[1])
                        patch = int(parts[2])
                        # PSM 2.0 (firmware >= 0.6.x): scan_status available in >= 0.6.8
                        if self.is_psm2:
                            if major > 0 or minor > 6 or (minor == 6 and patch >= 8):
                                scan_status = data[15]
                        # Retrofit (firmware 0.x.x where x < 6): scan_status available in >= 0.5.5
                        else:
                            if minor > 5 or (minor == 5 and patch >= 5):
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
                if self.is_psm2:
                    self.current_data.vacuum_flow = float(data[13])
                self.current_data.poly_correction = poly_correction
                self.current_data.scan_status = scan_status # [15]
                self.current_data.status_hex = status_hex # [-2]
                self.current_data.note_hex = note_hex # [-1]
                self.current_data.total_errors = total_errors
                self.current_data.liquid_errors = liquid_errors

                self.measure_tab.change_mode_color(command, self.current_data.saturator_flow)

                # Update GUI status tab values
                self.update_values(data)

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
                        # Special handling for MFC_HEATER/MFC_EXCESS error (index 27) - Retrofit only
                        if i == 27 and not self.is_psm2:
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
                # Special handling for index 27 - Retrofit only
                if error_code == 27 and not self.is_psm2:
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
            # Log which message caused the exception
            logging.warning(f"PSM parse_message exception: {e}, message: {message[:100] if message else 'None'}")

            # Don't reset mode colors on parsing errors - let them persist
            # from the last valid measurement message

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
        """PSM has CO flow error (Retrofit only)."""
        if not self.is_psm2:
            return hasattr(self.set_tab, 'set_co_flow') and self.set_tab.set_co_flow.error
        return False

    def supports_10hz_mode(self):
        """PSM supports 10 Hz mode."""
        return True

    def _update_psm_type_ui(self):
        """Update UI elements based on PSM type (2.0 vs Retrofit).

        Called when firmware version is received and PSM type can be determined.
        Updates device type label, hides CO flow widget for PSM 2.0, shows for Retrofit.
        """
        # Update device type label to show version (2.0 or Retrofit)
        if hasattr(self, 'device_type_label'):
            self.device_type_label.setText(self.display_device_type)

        if hasattr(self.set_tab, 'set_co_flow'):
            if self.is_psm2:
                self.set_tab.set_co_flow.hide()
            else:
                self.set_tab.set_co_flow.show()

        # Update status tab vacuum flow visibility
        if hasattr(self.status_tab, 'flow_vacuum'):
            if self.is_psm2:
                self.status_tab.flow_vacuum.show()
            else:
                self.status_tab.flow_vacuum.hide()

    def on_connection_established(self):
        """
        Reset PSM state on connection.

        Clears dilution parameters so they are re-fetched.
        """
        # Clear dilution parameters in device settings
        if self.settings:
            self.settings.dilution_parameters = []

    def send_read_commands(self, dev_conn, device_config):
        """
        Send PSM read commands for settings, dilution parameters, and firmware.

        Sends:
        - :SYST:PRNT if settings need to be fetched
        - :SYST:VCMP if dilution parameters are missing
        - :SYST:VER if firmware version is unknown
        """
        if self.needs_settings_fetch:
            dev_conn.send_message(":SYST:PRNT")

        if self.settings and not self.settings.dilution_parameters:
            dev_conn.send_delayed_message(":SYST:VCMP", 150)

        # Query firmware if not yet known (determines PSM 2.0 vs Retrofit)
        fw = device_config.extra_params.get('firmware_version', '')
        if not fw:
            dev_conn.send_delayed_message(":SYST:VER", 300)

    def validate_10hz_mode(self, app_config, device_config):
        """
        Validate and synchronize PSM 10 Hz mode.

        When PSM 10 Hz is enabled, ensure connected CPC also has 10 Hz enabled.
        """
        from config import CPC

        if device_config.extra_params.get('10_hz', False):
            cpc_id = device_config.extra_params.get('connected_cpc', 'None')
            if cpc_id != 'None':
                # Convert to int for comparison (JSON stores as string)
                try:
                    cpc_id_int = int(cpc_id)
                except (ValueError, TypeError):
                    cpc_id_int = None
                # Find connected CPC and enable its 10 Hz mode
                for cpc_config in app_config.devices:
                    if cpc_config.device_id == cpc_id_int and cpc_config.device_type == CPC:
                        if not cpc_config.extra_params.get('10_hz', False):
                            cpc_config.extra_params['10_hz'] = True
                            # Trigger config save
                            if hasattr(self, 'on_config_changed'):
                                self.on_config_changed()
                        break

    # App Integration Methods

    def supports_idn_inquiry(self):
        """PSM supports *IDN? identity inquiry."""
        return True

    @classmethod
    def get_default_extra_params(cls, device_type: int) -> dict:
        """Return default extra_params for PSM devices."""
        # co_flow included for all PSM - only used by Retrofit UI
        return {
            '10_hz': False,
            'connected_cpc': 'None',
            'calibration_file_path': '',
            'firmware_version': '',
            'co_flow': ''
        }

    def restore_ui_state(self, device_config, app_config):
        """Restore PSM UI state from configuration."""
        # Set app config for contour tab historical data loading
        if hasattr(self, 'set_app_config'):
            self.set_app_config(app_config)

        # Restore 10 Hz toggle state
        if '10_hz' in device_config.extra_params:
            self.measure_tab.ten_hz_checkbox.update_state(int(device_config.extra_params['10_hz']))

        # Restore measure tab settings (scan/step/fixed parameters)
        self.measure_tab.restore_settings(device_config.extra_params)

        # Connect measure tab value changes to save settings
        self._connect_measure_tab_save(device_config)

        # Update PSM type UI (CO flow visibility, vacuum flow visibility)
        # This ensures correct UI state based on firmware version from config
        self._update_psm_type_ui()

        # Restore CO flow value (Retrofit only)
        if not self.is_psm2 and 'co_flow' in device_config.extra_params:
            try:
                co_flow_val = float(device_config.extra_params['co_flow'])
                self.set_tab.set_co_flow.value_spinbox.setValue(round(co_flow_val, 3))
            except (ValueError, AttributeError):
                pass

    def _connect_measure_tab_save(self, device_config):
        """Connect measure tab value changes to save settings."""
        def save_measure_settings():
            self.measure_tab.save_settings(device_config.extra_params)
            if hasattr(self, 'on_config_changed'):
                self.on_config_changed()

        # Connect scan mode controls
        self.measure_tab.set_minimum_flow.value_spinbox.valueChanged.connect(save_measure_settings)
        self.measure_tab.set_max_flow.value_spinbox.valueChanged.connect(save_measure_settings)
        self.measure_tab.scan_time_preset.currentIndexChanged.connect(save_measure_settings)
        self.measure_tab.set_bottom_wait.value_spinbox.valueChanged.connect(save_measure_settings)
        self.measure_tab.set_up_scan_time.value_spinbox.valueChanged.connect(save_measure_settings)
        self.measure_tab.set_top_wait.value_spinbox.valueChanged.connect(save_measure_settings)
        self.measure_tab.set_down_scan_time.value_spinbox.valueChanged.connect(save_measure_settings)

        # Connect step mode controls
        self.measure_tab.step_time.value_spinbox.valueChanged.connect(save_measure_settings)
        self.measure_tab.steps.text_box.textChanged.connect(save_measure_settings)

        # Connect fixed mode control
        self.measure_tab.set_flow.value_spinbox.valueChanged.connect(save_measure_settings)

    def update_auxiliary_displays(self, data_holder=None):
        """Update PSM contour plot."""
        import logging
        import traceback
        if hasattr(self, 'contour_tab') and self.is_connected:
            try:
                self.contour_tab.update_contour(self.current_data, data_holder)
            except Exception as e:
                logging.error(f"Error updating PSM contour plot: {e}")
                traceback.print_exc()

    def validate_connected_devices(self, device_config, data_holder, config):
        """Validate PSM-CPC connection and update flow status."""
        from config import CPC
        dev_id = device_config.device_id

        # Get connected CPC id from extra params
        connected_cpc_id = device_config.extra_params.get('connected_cpc', 'None')

        # If no CPC is connected
        if connected_cpc_id == 'None':
            data_holder.error_status = 1
            data_holder.device_errors[dev_id] = True
        else:
            # Convert to int for comparison (JSON stores as string)
            try:
                connected_cpc_id_int = int(connected_cpc_id)
            except (ValueError, TypeError):
                connected_cpc_id_int = None
            # Find connected CPC device config
            cpc_config = next((d for d in config.devices if d.device_id == connected_cpc_id_int), None)
            if cpc_config:
                # If connected CPC is Airmodus CPC, sync sample flow
                if cpc_config.device_type == CPC:
                    cpc_settings = data_holder.get_device_settings(connected_cpc_id_int)
                    cpc_sample_flow = float(cpc_settings.measured_cpc_flow) if cpc_settings else 0.0
                    if self.set_tab.set_cpc_sample_flow.value_spinbox.value() != cpc_sample_flow:
                        self.set_tab.set_cpc_sample_flow.value_spinbox.setValue(cpc_sample_flow)

    def perform_pre_plot_calculations(self, data_holder):
        """Calculate PSM dilution-corrected CPC values."""
        if self.is_connected and hasattr(self, 'plot_config'):
            self.plot_config.calculate_connected_cpc_values(data_holder)


class PSMControlTab(QWidget):
    """Combined control tab merging Set and Status functionality.

    Compact layout designed to fit on one screen without scrolling.
    """
    def __init__(self, is_psm2: bool, *args, **kwargs):
        super().__init__()

        # Scroll area for when content exceeds screen (e.g., Serial Commands expanded)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # === TEMPERATURES GROUP ===
        temp_group = QGroupBox("🌡️ Temperatures")
        temp_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e67e22;
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                background-color: #3a3a3a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #e67e22;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        temp_layout = QGridLayout()
        temp_layout.setSpacing(4)

        # Row 0: Growth tube, Saturator, Inlet (setpoint + actual)
        self.set_growth_tube_temp = SetStatusWidget("Growth tube T", " °C")
        self.set_growth_tube_temp.setToolTip("Growth tube temperature - controls particle growth conditions")
        temp_layout.addWidget(self.set_growth_tube_temp, 0, 0)
        self.set_saturator_temp = SetStatusWidget("Saturator T", " °C")
        self.set_saturator_temp.setToolTip("Saturator temperature - controls working fluid vapor saturation")
        temp_layout.addWidget(self.set_saturator_temp, 0, 1)
        self.set_inlet_temp = SetStatusWidget("Inlet T", " °C")
        self.set_inlet_temp.setToolTip("Inlet temperature - aerosol sample inlet heating")
        temp_layout.addWidget(self.set_inlet_temp, 0, 2)

        # Row 1: Heater, Drainage (setpoint + actual), Cabin (read-only)
        self.set_heater_temp = SetStatusWidget("Heater T", " °C")
        self.set_heater_temp.setToolTip("Heater temperature - preheater for incoming flow")
        temp_layout.addWidget(self.set_heater_temp, 1, 0)
        self.set_drainage_temp = SetStatusWidget("Drainage T", " °C")
        self.set_drainage_temp.setToolTip("Drainage temperature - excess liquid drainage heating")
        temp_layout.addWidget(self.set_drainage_temp, 1, 1)
        self.temp_cabin = IndicatorWidget("Cabin T")
        self.temp_cabin.setToolTip("Cabin temperature - internal instrument temperature (read-only)")
        temp_layout.addWidget(self.temp_cabin, 1, 2)

        temp_group.setLayout(temp_layout)
        main_layout.addWidget(temp_group)

        # === FLOW RATES GROUP ===
        flow_group = QGroupBox("💨 Flow Rates")
        flow_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #3498db;
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                background-color: #3a3a3a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #3498db;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        flow_layout = QGridLayout()
        flow_layout.setSpacing(4)

        # Row 0: Setpoint flows
        self.set_cpc_inlet_flow = SetWidget("CPC inlet", " lpm", decimals=3)
        self.set_cpc_inlet_flow.setToolTip("CPC inlet flow - used in dilution correction")
        flow_layout.addWidget(self.set_cpc_inlet_flow, 0, 0)

        self.set_cpc_sample_flow = SetWidget("CPC sample", " lpm", decimals=3)
        self.set_cpc_sample_flow.setToolTip("CPC sample flow - used in concentration calculation")
        flow_layout.addWidget(self.set_cpc_sample_flow, 0, 1)

        # CO flow rate widget - always created, visibility updated when firmware received
        self.set_co_flow = SetWidget("CO flow", " lpm", decimals=3)
        self.set_co_flow.setToolTip("Cut-off flow rate for PSM Retrofit")
        flow_layout.addWidget(self.set_co_flow, 0, 2)
        if is_psm2:
            self.set_co_flow.hide()

        # Row 1: Read-only flow indicators (first two)
        self.flow_saturator = IndicatorWidget("Saturator")
        self.flow_saturator.setToolTip("Saturator flow - saturated air flow rate")
        flow_layout.addWidget(self.flow_saturator, 1, 0)
        self.flow_excess = IndicatorWidget("Excess")
        self.flow_excess.setToolTip("Excess flow - excess sample flow rate")
        flow_layout.addWidget(self.flow_excess, 1, 1)

        # Row 2: Read-only flow indicators (inlet + vacuum for PSM 2.0)
        self.flow_inlet = IndicatorWidget("Inlet")
        self.flow_inlet.setToolTip("Inlet flow - total sample inlet flow rate")
        flow_layout.addWidget(self.flow_inlet, 2, 0)

        if is_psm2:
            self.flow_vacuum = IndicatorWidget("Vacuum")
            self.flow_vacuum.setToolTip("Vacuum flow - vacuum pump flow rate")
            flow_layout.addWidget(self.flow_vacuum, 2, 1)

        flow_group.setLayout(flow_layout)
        main_layout.addWidget(flow_group)

        # === CONTROLS, PRESSURES & LIQUID LEVELS (combined row) ===
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        # Liquid Controls (vertical stacked toggles)
        controls_group = QGroupBox("🎛️ Controls")
        controls_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #27ae60;
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                background-color: #3a3a3a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #27ae60;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(2)
        controls_layout.setContentsMargins(4, 4, 4, 4)

        self.autofill = ToggleSwitch("Autofill", "Automatically refill saturator liquid when low")
        controls_layout.addWidget(self.autofill)

        self.drain = ToggleSwitch("Drain", "Enable liquid drainage from the system")
        controls_layout.addWidget(self.drain)

        self.drying = ToggleSwitch("Drying", "Run drying cycle to remove moisture")
        controls_layout.addWidget(self.drying)

        controls_group.setLayout(controls_layout)
        status_row.addWidget(controls_group, 1)  # Equal stretch

        # Pressures
        pressure_group = QGroupBox("📊 Pressures")
        pressure_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #9b59b6;
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                background-color: #3a3a3a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #9b59b6;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        pressure_layout = QVBoxLayout()
        pressure_layout.setSpacing(4)
        pressure_layout.setContentsMargins(4, 4, 4, 4)
        self.pressure_inlet = IndicatorWidget("Inlet")
        self.pressure_inlet.setToolTip("Inlet pressure - sample inlet pressure")
        pressure_layout.addWidget(self.pressure_inlet)
        if is_psm2:
            self.pressure_critical_orifice = IndicatorWidget("Vacuum line")
            self.pressure_critical_orifice.setToolTip("Vacuum line pressure - vacuum system pressure")
        else:
            self.pressure_critical_orifice = IndicatorWidget("Crit. orifice")
            self.pressure_critical_orifice.setToolTip("Critical orifice pressure - flow control orifice pressure")
        pressure_layout.addWidget(self.pressure_critical_orifice)
        pressure_group.setLayout(pressure_layout)
        status_row.addWidget(pressure_group, 1)  # Equal stretch

        # Liquid Levels
        liquid_level_group = QGroupBox("💧 Levels")
        liquid_level_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #1abc9c;
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                background-color: #3a3a3a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #1abc9c;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        liquid_level_layout = QVBoxLayout()
        liquid_level_layout.setSpacing(4)
        liquid_level_layout.setContentsMargins(4, 4, 4, 4)
        self.liquid_saturator = IndicatorWidget("Saturator")
        self.liquid_saturator.setToolTip("Saturator liquid level - working fluid reservoir level")
        liquid_level_layout.addWidget(self.liquid_saturator)
        self.liquid_drain = IndicatorWidget("Drain")
        self.liquid_drain.setToolTip("Drain liquid level - excess liquid drain level")
        liquid_level_layout.addWidget(self.liquid_drain)
        liquid_level_group.setLayout(liquid_level_layout)
        status_row.addWidget(liquid_level_group, 1)  # Equal stretch

        main_layout.addLayout(status_row)

        # === SERIAL COMMANDS GROUP (Collapsible) ===
        self.commands_group = QGroupBox("📡 Serial Commands")
        self.commands_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #7f8c8d;
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                background-color: #3a3a3a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #7f8c8d;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        self.commands_group.setCheckable(True)
        self.commands_group.setChecked(False)
        commands_layout = QVBoxLayout()
        commands_layout.setContentsMargins(4, 4, 4, 4)

        self.command_widget = CommandWidget("PSM")
        commands_layout.addWidget(self.command_widget)

        self.commands_group.setLayout(commands_layout)
        self.commands_group.toggled.connect(self._on_commands_toggled)
        self.command_widget.setVisible(False)

        main_layout.addWidget(self.commands_group)
        main_layout.addStretch()

        # Set up scroll area
        scroll_area.setWidget(content_widget)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll_area)

    def _on_commands_toggled(self, checked):
        """Show/hide command widget content when group is toggled."""
        self.command_widget.setVisible(checked)

    # Backward compatibility properties for status tab access patterns
    # These expose the actual value indicators from SetStatusWidgets
    @property
    def temp_growth_tube(self):
        """Backward compatible access to growth tube temperature indicator."""
        return self.set_growth_tube_temp

    @property
    def temp_saturator(self):
        """Backward compatible access to saturator temperature indicator."""
        return self.set_saturator_temp

    @property
    def temp_inlet(self):
        """Backward compatible access to inlet temperature indicator."""
        return self.set_inlet_temp

    @property
    def temp_heater(self):
        """Backward compatible access to heater temperature indicator."""
        return self.set_heater_temp

    @property
    def temp_drainage(self):
        """Backward compatible access to drainage temperature indicator."""
        return self.set_drainage_temp


class ScanPreviewWidget(QWidget):
    """Visual preview of scan/step flow profile."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Create plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.setMinimumHeight(150)

        # Style the plot
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Flow', units='lpm')
        self.plot_widget.setLabel('bottom', 'Time', units='s')

        # Create the curve
        self.curve = self.plot_widget.plot(pen=pg.mkPen(color='#2196F3', width=2))

        # Add phase labels (will be positioned dynamically)
        self.phase_labels = []

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def update_scan_preview(self, bottom_wait, up_scan, top_wait, down_scan, min_flow, max_flow):
        """Update preview with scan mode exponential profile."""
        # Calculate total time and generate time points
        total_time = bottom_wait + up_scan + top_wait + down_scan

        # Generate flow profile
        times = []
        flows = []

        # Calculate scan power for exponential profile
        scan_power = (max_flow / min_flow) ** (1.0 / up_scan)

        # Phase 1: Bottom wait (flat at min_flow)
        t_points = np.linspace(0, bottom_wait, max(2, int(bottom_wait)))
        times.extend(t_points)
        flows.extend([min_flow] * len(t_points))

        # Phase 2: Up scan (exponential rise)
        t_points = np.linspace(0, up_scan, max(10, int(up_scan)))
        times.extend(t_points + bottom_wait)
        flows.extend(min_flow * (scan_power ** t_points))

        # Phase 3: Top wait (flat at max_flow)
        t_points = np.linspace(0, top_wait, max(2, int(top_wait)))
        times.extend(t_points + bottom_wait + up_scan)
        flows.extend([max_flow] * len(t_points))

        # Phase 4: Down scan (exponential fall)
        t_points = np.linspace(0, down_scan, max(10, int(down_scan)))
        times.extend(t_points + bottom_wait + up_scan + top_wait)
        flows.extend(max_flow * ((1 / scan_power) ** t_points))

        # Update curve
        self.curve.setData(times, flows)

        # Set axis ranges with padding
        self.plot_widget.setXRange(0, total_time, padding=0.02)
        self.plot_widget.setYRange(min_flow * 0.9, max_flow * 1.05, padding=0.02)

        # Clear old labels
        for label in self.phase_labels:
            self.plot_widget.removeItem(label)
        self.phase_labels.clear()

        # Add phase indicator regions with subtle colors
        # Bottom wait region
        if bottom_wait > 5:
            label = pg.TextItem(f"Wait\n{bottom_wait}s", anchor=(0.5, 1), color='#666')
            label.setPos(bottom_wait / 2, min_flow * 0.95)
            self.plot_widget.addItem(label)
            self.phase_labels.append(label)

        # Up scan region
        label = pg.TextItem(f"Up\n{up_scan}s", anchor=(0.5, 0.5), color='#666')
        label.setPos(bottom_wait + up_scan / 2, (min_flow + max_flow) / 2)
        self.plot_widget.addItem(label)
        self.phase_labels.append(label)

        # Top wait region
        if top_wait > 5:
            label = pg.TextItem(f"Wait\n{top_wait}s", anchor=(0.5, 0), color='#666')
            label.setPos(bottom_wait + up_scan + top_wait / 2, max_flow * 1.02)
            self.plot_widget.addItem(label)
            self.phase_labels.append(label)

        # Down scan region
        label = pg.TextItem(f"Down\n{down_scan}s", anchor=(0.5, 0.5), color='#666')
        label.setPos(bottom_wait + up_scan + top_wait + down_scan / 2, (min_flow + max_flow) / 2)
        self.plot_widget.addItem(label)
        self.phase_labels.append(label)

    def update_step_preview(self, step_time, steps):
        """Update preview with step mode staircase profile."""
        if not steps:
            self.curve.setData([], [])
            return

        times = []
        flows = []

        current_time = 0
        for step_flow in steps:
            # Add horizontal line for this step
            times.extend([current_time, current_time + step_time])
            flows.extend([step_flow, step_flow])
            current_time += step_time

        # Update curve
        self.curve.setData(times, flows)

        # Set axis ranges
        min_flow = min(steps) if steps else 0.1
        max_flow = max(steps) if steps else 1.9
        self.plot_widget.setXRange(0, current_time, padding=0.02)
        self.plot_widget.setYRange(min_flow * 0.9, max_flow * 1.1, padding=0.02)

        # Clear old labels
        for label in self.phase_labels:
            self.plot_widget.removeItem(label)
        self.phase_labels.clear()

    def update_fixed_preview(self, flow):
        """Show flat line for fixed mode."""
        times = [0, 60]  # 60 second window
        flows = [flow, flow]
        self.curve.setData(times, flows)
        self.plot_widget.setXRange(0, 60, padding=0.02)
        self.plot_widget.setYRange(0, 2.1, padding=0.02)

        # Clear old labels
        for label in self.phase_labels:
            self.plot_widget.removeItem(label)
        self.phase_labels.clear()

        # Add label showing flow value
        label = pg.TextItem(f"Fixed: {flow:.2f} lpm", anchor=(0.5, 0.5), color='#666')
        label.setPos(30, flow)
        self.plot_widget.addItem(label)
        self.phase_labels.append(label)


class PSMMeasureTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        main_layout = QVBoxLayout()
        main_layout.setSpacing(8)

        # === HEADER ROW: Mode selector, Start button, 10Hz checkbox (all on left) ===
        header_widget = QWidget()
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # Mode selector dropdown (larger)
        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.mode_selector = QComboBox()
        self.mode_selector.addItems(["Scan", "Step", "Fixed"])
        self.mode_selector.setMinimumWidth(120)
        self.mode_selector.setMinimumHeight(35)
        self.mode_selector.setStyleSheet("QComboBox { font-size: 14px; padding: 5px; }")

        # Live status indicator (shows actual device state)
        self.status_label = QLabel("● Idle")
        self.status_label.setStyleSheet("color: #888; font-size: 13px;")
        self.status_label.setMinimumWidth(120)

        # Dynamic action button (Start/Update/Switch based on state)
        self.update_button = QPushButton("▶ Start Scan")
        self.update_button.setStyleSheet(STYLE_BTN_START)
        self.update_button.setMinimumHeight(32)
        self._device_mode = None  # Track device mode for button logic

        # 10 Hz toggle switch
        self.ten_hz_checkbox = ToggleSwitch("10 Hz", "Enable 10 Hz data logging rate")

        # Layout: Mode selector, status, action button, stretch, 10Hz on right
        header_layout.addWidget(mode_label)
        header_layout.addWidget(self.mode_selector)
        header_layout.addWidget(self.status_label)
        header_layout.addWidget(self.update_button)
        header_layout.addStretch()  # Push 10Hz to right
        header_layout.addWidget(self.ten_hz_checkbox)
        header_widget.setLayout(header_layout)
        main_layout.addWidget(header_widget)

        # === CONTENT AREA: Settings on left, Preview on right ===
        content_widget = QWidget()
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        # Left side: Settings + Update button in vertical layout
        left_container = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # Stacked widget for mode-specific settings
        self.mode_settings = QStackedWidget()
        self.mode_settings.setMaximumWidth(300)

        # Create scan settings widget
        self.mode_settings.addWidget(self._create_scan_settings())

        # Create step settings widget
        self.mode_settings.addWidget(self._create_step_settings())

        # Create fixed settings widget
        self.mode_settings.addWidget(self._create_fixed_settings())

        left_layout.addWidget(self.mode_settings, 1)  # stretch factor 1

        left_container.setLayout(left_layout)
        left_container.setMaximumWidth(300)
        content_layout.addWidget(left_container)

        # Right side: Preview graph (takes remaining space)
        self.scan_preview = ScanPreviewWidget()
        content_layout.addWidget(self.scan_preview, 1)  # stretch factor 1

        content_widget.setLayout(content_layout)
        main_layout.addWidget(content_widget, 1)  # stretch factor 1

        self.setLayout(main_layout)

        # Connect mode selector to switch settings and update preview
        self.mode_selector.currentIndexChanged.connect(self._on_mode_changed)

        # Connect individual timing controls to update total display
        # (Preset selector handles setting all values when selected)
        self.set_bottom_wait.value_spinbox.valueChanged.connect(self._update_total_from_individual)
        self.set_up_scan_time.value_spinbox.valueChanged.connect(self._update_total_from_individual)
        self.set_top_wait.value_spinbox.valueChanged.connect(self._update_total_from_individual)
        self.set_down_scan_time.value_spinbox.valueChanged.connect(self._update_total_from_individual)

        # Connect all scan controls to preview update
        self.set_minimum_flow.value_spinbox.valueChanged.connect(self._update_scan_preview)
        self.set_max_flow.value_spinbox.valueChanged.connect(self._update_scan_preview)
        self.set_bottom_wait.value_spinbox.valueChanged.connect(self._update_scan_preview)
        self.set_up_scan_time.value_spinbox.valueChanged.connect(self._update_scan_preview)
        self.set_top_wait.value_spinbox.valueChanged.connect(self._update_scan_preview)
        self.set_down_scan_time.value_spinbox.valueChanged.connect(self._update_scan_preview)

        # Connect step mode controls to preview
        self.step_time.value_spinbox.valueChanged.connect(self._update_step_preview)
        self.steps.text_box.textChanged.connect(self._update_step_preview)

        # Connect fixed mode control to preview
        self.set_flow.value_spinbox.valueChanged.connect(self._update_fixed_preview)

        self.ten_hz = self.ten_hz_checkbox

        # Dirty state tracking for Update button
        self._saved_settings = {}

        # Connect value changes to dirty check (in addition to preview updates)
        self.set_minimum_flow.value_spinbox.valueChanged.connect(self._check_settings_dirty)
        self.set_max_flow.value_spinbox.valueChanged.connect(self._check_settings_dirty)
        self.scan_time_preset.currentIndexChanged.connect(self._check_settings_dirty)
        self.set_bottom_wait.value_spinbox.valueChanged.connect(self._check_settings_dirty)
        self.set_up_scan_time.value_spinbox.valueChanged.connect(self._check_settings_dirty)
        self.set_top_wait.value_spinbox.valueChanged.connect(self._check_settings_dirty)
        self.set_down_scan_time.value_spinbox.valueChanged.connect(self._check_settings_dirty)
        self.step_time.value_spinbox.valueChanged.connect(self._check_settings_dirty)
        self.steps.text_box.textChanged.connect(self._check_settings_dirty)
        self.set_flow.value_spinbox.valueChanged.connect(self._check_settings_dirty)

        # Initial preview update
        self._update_scan_preview()

    def _get_current_settings(self):
        """Get current settings from UI as a dict for dirty comparison."""
        return {
            'scan_min_flow': self.set_minimum_flow.value_spinbox.value(),
            'scan_max_flow': self.set_max_flow.value_spinbox.value(),
            'scan_preset_index': self.scan_time_preset.currentIndex(),
            'scan_bottom_wait': self.set_bottom_wait.value_spinbox.value(),
            'scan_up_time': self.set_up_scan_time.value_spinbox.value(),
            'scan_top_wait': self.set_top_wait.value_spinbox.value(),
            'scan_down_time': self.set_down_scan_time.value_spinbox.value(),
            'step_time': self.step_time.value_spinbox.value(),
            'step_values': self.steps.text_box.toPlainText(),
            'fixed_flow': self.set_flow.value_spinbox.value(),
        }

    def _check_settings_dirty(self):
        """Check if current settings differ from saved, update button."""
        self._update_action_button()

    def _mark_settings_clean(self):
        """Snapshot current settings as 'saved' state."""
        self._saved_settings = self._get_current_settings()
        self._update_action_button()

    def _on_update_sending(self):
        """Show sending state and disable briefly to prevent spam."""
        self.update_button.setText("Sending...")
        self.update_button.setStyleSheet(STYLE_BTN_SENDING)
        self.update_button.setEnabled(False)
        # Re-enable after 1 second
        QTimer.singleShot(1000, self._on_update_complete)

    def _on_update_complete(self):
        self.update_button.setEnabled(True)
        self._update_action_button()

    def update_device_status(self, mode_command: str, satflow: float):
        """Update status label and action button based on device state."""
        # Store current device mode for button logic
        self._device_mode = mode_command

        # Update status label
        if mode_command == ":MEAS:SCAN":
            self.status_label.setText(f"● Scanning ({satflow:.2f} lpm)")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
        elif mode_command == ":MEAS:STEP":
            self.status_label.setText(f"● Step ({satflow:.2f} lpm)")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
        elif mode_command == ":MEAS:FIXD":
            self.status_label.setText(f"● Fixed ({satflow:.2f} lpm)")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 13px; font-weight: bold;")
        else:
            self.status_label.setText("● Idle")
            self.status_label.setStyleSheet("color: #888; font-size: 13px;")

        # Update action button
        self._update_action_button()

    def _update_action_button(self):
        """Update action button text and style based on device and UI state."""
        if not hasattr(self, '_device_mode'):
            self._device_mode = None

        ui_mode_index = self.mode_selector.currentIndex()
        mode_names = ["Scan", "Step", "Fixed"]
        ui_mode_name = mode_names[ui_mode_index] if ui_mode_index < len(mode_names) else "Scan"

        # Map UI index to device mode command
        ui_to_device_mode = {0: ":MEAS:SCAN", 1: ":MEAS:STEP", 2: ":MEAS:FIXD"}
        ui_device_mode = ui_to_device_mode.get(ui_mode_index)

        is_idle = self._device_mode not in [":MEAS:SCAN", ":MEAS:STEP", ":MEAS:FIXD"]
        is_same_mode = self._device_mode == ui_device_mode

        if is_idle:
            # Device is idle - show Start button
            self.update_button.setText(f"▶ Start {ui_mode_name}")
            self.update_button.setStyleSheet(STYLE_BTN_START)
        elif is_same_mode:
            # Running same mode - show Update if settings changed
            if self._is_settings_dirty():
                self.update_button.setText("Update Settings")
                self.update_button.setStyleSheet(STYLE_BTN_UPDATE)
            else:
                self.update_button.setText(f"● {ui_mode_name} Running")
                self.update_button.setStyleSheet(STYLE_BTN_RUNNING)
        else:
            # Running different mode - show Switch button
            self.update_button.setText(f"Switch to {ui_mode_name}")
            self.update_button.setStyleSheet(STYLE_BTN_UPDATE)

    def _is_settings_dirty(self):
        """Check if current settings differ from saved."""
        if not self._saved_settings:
            return False
        return self._get_current_settings() != self._saved_settings

    @staticmethod
    def compile_scan_from_params(params):
        bottom_wait = params.get('scan_bottom_wait', 10)
        up_time = params.get('scan_up_time', 110)
        top_wait = params.get('scan_top_wait', 10)
        down_time = params.get('scan_down_time', 110)
        min_flow = params.get('scan_min_flow', 0.15)
        max_flow = params.get('scan_max_flow', 1.9)
        return f":SET:FLOW:SCAN {bottom_wait},{up_time},{top_wait},{down_time},{min_flow},{max_flow}"

    @staticmethod
    def compile_step_from_params(params):
        step_time = params.get('step_time', 30)
        step_values = params.get('step_values', '0.1\n0.7\n1.3\n1.9')
        step_list = [s.strip() for s in step_values.split('\n') if s.strip()]
        if not step_list:
            return None
        step_amount = len(step_list)
        step_times = [step_time] * step_amount
        return f":SET:FLOW:STEP {step_amount},{','.join(map(str, step_times))},{','.join(step_list)}"

    @staticmethod
    def compile_fixed_from_params(params):
        flow = params.get('fixed_flow', 1.9)
        return f":SET:FLOW:FXD {round(flow, 3)}"

    def _create_scan_settings(self):
        """Create widget with scan mode settings (compact layout)."""
        widget = QWidget()
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.setVerticalSpacing(4)

        def make_compact(set_widget):
            """Reduce font size for compact display."""
            # Reduce label font size for Windows compatibility
            label = set_widget.findChild(QLabel, "label")
            if label:
                font = label.font()
                font.setPointSize(12)  # Smaller font to prevent text overflow
                label.setFont(font)
            return set_widget

        # Flow range (side by side)
        self.set_minimum_flow = make_compact(SetWidget("Min flow", " lpm"))
        self.set_minimum_flow.value_spinbox.setValue(0.15)
        layout.addWidget(self.set_minimum_flow, 0, 0)

        self.set_max_flow = make_compact(SetWidget("Max flow", " lpm"))
        self.set_max_flow.value_spinbox.setValue(1.9)
        layout.addWidget(self.set_max_flow, 0, 1)

        # Total scan time preset selector
        total_label = QLabel("Total scan time")
        total_label.setAlignment(Qt.AlignCenter)
        total_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(total_label, 1, 0, 1, 2)

        self.scan_time_preset = QComboBox()
        self.scan_time_preset.setMinimumHeight(30)
        self.scan_time_preset.setStyleSheet("QComboBox { font-size: 14px; padding: 4px; }")
        # Preset values (seconds)
        self._scan_time_presets = [60, 120, 180, 240, 300, 360, 480]
        for preset in self._scan_time_presets:
            self.scan_time_preset.addItem(f"{preset} s")
        self.scan_time_preset.setCurrentIndex(3)  # Default 240s
        layout.addWidget(self.scan_time_preset, 2, 0, 1, 2)

        # Hidden spinbox for compatibility (stores actual value)
        self.set_scan_time = SetWidget("Total time", " s", integer=True)
        self.set_scan_time.value_spinbox.setValue(240)
        self.set_scan_time.hide()  # Hidden, just for storing value

        # Timing controls in 2x2 grid
        self.set_bottom_wait = make_compact(SetWidget("Bottom wait", " s", integer=True))
        self.set_bottom_wait.value_spinbox.setValue(10)
        self.set_bottom_wait.value_spinbox.setRange(1, 60)
        layout.addWidget(self.set_bottom_wait, 3, 0)

        self.set_up_scan_time = make_compact(SetWidget("Up scan", " s", integer=True))
        self.set_up_scan_time.value_spinbox.setValue(110)
        self.set_up_scan_time.value_spinbox.setRange(10, 600)
        layout.addWidget(self.set_up_scan_time, 3, 1)

        self.set_top_wait = make_compact(SetWidget("Top wait", " s", integer=True))
        self.set_top_wait.value_spinbox.setValue(10)
        self.set_top_wait.value_spinbox.setRange(1, 60)
        layout.addWidget(self.set_top_wait, 4, 0)

        self.set_down_scan_time = make_compact(SetWidget("Down scan", " s", integer=True))
        self.set_down_scan_time.value_spinbox.setValue(110)
        self.set_down_scan_time.value_spinbox.setRange(10, 600)
        layout.addWidget(self.set_down_scan_time, 4, 1)

        # Connect preset selector
        self.scan_time_preset.currentIndexChanged.connect(self._on_preset_selected)

        # Add stretch at bottom
        layout.setRowStretch(5, 1)
        widget.setLayout(layout)

        # Note: Initial preset is applied in __init__ after scan_preview is created

        return widget

    def _on_preset_selected(self, index):
        """Apply preset scan time and calculate individual times."""
        if index < 0 or index >= len(self._scan_time_presets):
            return

        total_time = self._scan_time_presets[index]

        # Default wait times
        bottom_wait = 10
        top_wait = 10

        # Calculate scan times (remaining split evenly)
        remaining = total_time - bottom_wait - top_wait
        if remaining < 20:
            remaining = 20
        up_time = remaining // 2
        down_time = remaining // 2
        # Extra second to top wait if odd
        if remaining % 2 != 0:
            top_wait += 1

        # Block signals to prevent circular updates
        self.set_scan_time.value_spinbox.blockSignals(True)
        self.set_bottom_wait.value_spinbox.blockSignals(True)
        self.set_up_scan_time.value_spinbox.blockSignals(True)
        self.set_top_wait.value_spinbox.blockSignals(True)
        self.set_down_scan_time.value_spinbox.blockSignals(True)

        self.set_scan_time.value_spinbox.setValue(total_time)
        self.set_bottom_wait.value_spinbox.setValue(bottom_wait)
        self.set_up_scan_time.value_spinbox.setValue(up_time)
        self.set_top_wait.value_spinbox.setValue(top_wait)
        self.set_down_scan_time.value_spinbox.setValue(down_time)

        self.set_scan_time.value_spinbox.blockSignals(False)
        self.set_bottom_wait.value_spinbox.blockSignals(False)
        self.set_up_scan_time.value_spinbox.blockSignals(False)
        self.set_top_wait.value_spinbox.blockSignals(False)
        self.set_down_scan_time.value_spinbox.blockSignals(False)

        # Update preview
        self._update_scan_preview()

    def _create_step_settings(self):
        """Create widget with step mode settings."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.step_time = SetWidget("Step time", " s", integer=True)
        self.step_time.value_spinbox.setValue(30)
        layout.addWidget(self.step_time)

        self.steps = StepsWidget()
        self.steps.text_box.setText("0.1\n0.7\n1.3\n1.9")
        layout.addWidget(self.steps, 1)  # stretch factor 1

        widget.setLayout(layout)
        return widget

    def _create_fixed_settings(self):
        """Create widget with fixed mode settings."""
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.set_flow = SetWidget("Saturator flow", " lpm")
        self.set_flow.value_spinbox.setValue(1.9)
        layout.addWidget(self.set_flow)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _on_mode_changed(self, index):
        """Handle mode selector change."""
        self.mode_settings.setCurrentIndex(index)
        if index == 0:  # Scan
            self._update_scan_preview()
        elif index == 1:  # Step
            self._update_step_preview()
        elif index == 2:  # Fixed
            self._update_fixed_preview()
        # Update action button text for new mode
        self._update_action_button()

    def get_current_mode(self):
        """Return the currently selected mode command."""
        mode_commands = [":MEAS:SCAN", ":MEAS:STEP", ":MEAS:FIXD"]
        return mode_commands[self.mode_selector.currentIndex()]
    
    def _update_scan_times_from_total(self, total_time):
        """Recalculate individual scan times from total scan time."""
        bottom_wait = self.set_bottom_wait.value_spinbox.value()
        top_wait = self.set_top_wait.value_spinbox.value()

        remaining = total_time - bottom_wait - top_wait
        if remaining < 20:
            remaining = 20  # Minimum 10s each for up/down

        # Split remaining time evenly between up and down scans
        up_time = remaining // 2
        down_time = remaining // 2

        # If odd remaining, add extra 1s to top wait instead
        if remaining % 2 != 0:
            self.set_top_wait.value_spinbox.blockSignals(True)
            self.set_top_wait.value_spinbox.setValue(top_wait + 1)
            self.set_top_wait.value_spinbox.blockSignals(False)

        # Update spinboxes without triggering circular updates
        self.set_up_scan_time.value_spinbox.blockSignals(True)
        self.set_down_scan_time.value_spinbox.blockSignals(True)
        self.set_up_scan_time.value_spinbox.setValue(up_time)
        self.set_down_scan_time.value_spinbox.setValue(down_time)
        self.set_up_scan_time.value_spinbox.blockSignals(False)
        self.set_down_scan_time.value_spinbox.blockSignals(False)

        # Update preview since signals were blocked
        self._update_scan_preview()

    def _update_total_from_individual(self):
        """Update total scan time display when individual times change."""
        total = (self.set_bottom_wait.value_spinbox.value() +
                 self.set_up_scan_time.value_spinbox.value() +
                 self.set_top_wait.value_spinbox.value() +
                 self.set_down_scan_time.value_spinbox.value())

        # Update hidden spinbox for compatibility
        self.set_scan_time.value_spinbox.blockSignals(True)
        self.set_scan_time.value_spinbox.setValue(total)
        self.set_scan_time.value_spinbox.blockSignals(False)

        # Update preset dropdown to show current total
        # Check if it matches a preset
        self.scan_time_preset.blockSignals(True)
        if total in self._scan_time_presets:
            idx = self._scan_time_presets.index(total)
            self.scan_time_preset.setCurrentIndex(idx)
        else:
            # Show custom value - add temporarily if not in list
            custom_text = f"{total} s (custom)"
            # Check if we already have a custom entry
            last_idx = self.scan_time_preset.count() - 1
            if "(custom)" in self.scan_time_preset.itemText(last_idx):
                self.scan_time_preset.setItemText(last_idx, custom_text)
                self.scan_time_preset.setCurrentIndex(last_idx)
            else:
                self.scan_time_preset.addItem(custom_text)
                self.scan_time_preset.setCurrentIndex(self.scan_time_preset.count() - 1)
        self.scan_time_preset.blockSignals(False)

    def _update_scan_preview(self):
        """Update scan mode preview graph."""
        self.scan_preview.update_scan_preview(
            bottom_wait=self.set_bottom_wait.value_spinbox.value(),
            up_scan=self.set_up_scan_time.value_spinbox.value(),
            top_wait=self.set_top_wait.value_spinbox.value(),
            down_scan=self.set_down_scan_time.value_spinbox.value(),
            min_flow=self.set_minimum_flow.value_spinbox.value(),
            max_flow=self.set_max_flow.value_spinbox.value()
        )

    def _update_step_preview(self):
        """Update step mode preview graph."""
        step_list = self.steps.text_box.toPlainText().split("\n")
        steps = []
        for step in step_list:
            try:
                steps.append(float(step))
            except ValueError:
                continue
        self.scan_preview.update_step_preview(
            step_time=self.step_time.value_spinbox.value(),
            steps=steps
        )

    def _update_fixed_preview(self):
        """Update fixed mode preview graph."""
        self.scan_preview.update_fixed_preview(
            flow=self.set_flow.value_spinbox.value()
        )

    def compile_scan(self):
        """Compile scan command with individual timing parameters."""
        bottom_wait = self.set_bottom_wait.value_spinbox.value()
        up_scan = self.set_up_scan_time.value_spinbox.value()
        top_wait = self.set_top_wait.value_spinbox.value()
        down_scan = self.set_down_scan_time.value_spinbox.value()
        min_flow = round(self.set_minimum_flow.value_spinbox.value(), 3)
        max_flow = round(self.set_max_flow.value_spinbox.value(), 3)

        parameters = [bottom_wait, up_scan, top_wait, down_scan, min_flow, max_flow]
        scan_string = ":SET:FLOW:SCAN " + ",".join(map(str, parameters))
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
    
    def change_mode_color(self, command, satflow=0.0):
        self._current_device_mode = command
        self.update_device_status(command, satflow)

    def save_settings(self, extra_params: dict):
        """Save all measure tab settings to extra_params dict."""
        # Scan mode settings
        extra_params['scan_min_flow'] = self.set_minimum_flow.value_spinbox.value()
        extra_params['scan_max_flow'] = self.set_max_flow.value_spinbox.value()
        extra_params['scan_preset_index'] = self.scan_time_preset.currentIndex()
        extra_params['scan_bottom_wait'] = self.set_bottom_wait.value_spinbox.value()
        extra_params['scan_up_time'] = self.set_up_scan_time.value_spinbox.value()
        extra_params['scan_top_wait'] = self.set_top_wait.value_spinbox.value()
        extra_params['scan_down_time'] = self.set_down_scan_time.value_spinbox.value()

        # Step mode settings
        extra_params['step_time'] = self.step_time.value_spinbox.value()
        extra_params['step_values'] = self.steps.text_box.toPlainText()

        # Fixed mode settings
        extra_params['fixed_flow'] = self.set_flow.value_spinbox.value()

    def restore_settings(self, extra_params: dict):
        """Restore measure tab settings from extra_params dict."""
        # Block signals to prevent triggering saves during restore
        widgets_to_block = [
            self.set_minimum_flow.value_spinbox,
            self.set_max_flow.value_spinbox,
            self.scan_time_preset,
            self.set_bottom_wait.value_spinbox,
            self.set_up_scan_time.value_spinbox,
            self.set_top_wait.value_spinbox,
            self.set_down_scan_time.value_spinbox,
            self.step_time.value_spinbox,
            self.steps.text_box,
            self.set_flow.value_spinbox,
        ]

        for widget in widgets_to_block:
            widget.blockSignals(True)

        try:
            # Scan mode settings
            if 'scan_min_flow' in extra_params:
                self.set_minimum_flow.value_spinbox.setValue(extra_params['scan_min_flow'])
            if 'scan_max_flow' in extra_params:
                self.set_max_flow.value_spinbox.setValue(extra_params['scan_max_flow'])
            if 'scan_bottom_wait' in extra_params:
                self.set_bottom_wait.value_spinbox.setValue(extra_params['scan_bottom_wait'])
            if 'scan_up_time' in extra_params:
                self.set_up_scan_time.value_spinbox.setValue(extra_params['scan_up_time'])
            if 'scan_top_wait' in extra_params:
                self.set_top_wait.value_spinbox.setValue(extra_params['scan_top_wait'])
            if 'scan_down_time' in extra_params:
                self.set_down_scan_time.value_spinbox.setValue(extra_params['scan_down_time'])
            if 'scan_preset_index' in extra_params:
                self.scan_time_preset.setCurrentIndex(extra_params['scan_preset_index'])

            # Step mode settings
            if 'step_time' in extra_params:
                self.step_time.value_spinbox.setValue(extra_params['step_time'])
            if 'step_values' in extra_params:
                self.steps.text_box.setPlainText(extra_params['step_values'])

            # Fixed mode settings
            if 'fixed_flow' in extra_params:
                self.set_flow.value_spinbox.setValue(extra_params['fixed_flow'])
        finally:
            for widget in widgets_to_block:
                widget.blockSignals(False)

        self._update_scan_preview()
        self._mark_settings_clean()


__all__ = ['PSMWidget']
