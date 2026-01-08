from PyQt5.QtGui import QPalette, QColor, QIntValidator, QDoubleValidator, QFont, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QLocale
from numpy import full, nan, isnan, array_equal
import logging
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, PlotCurveItem, LegendItem, PlotItem, mkPen, mkBrush
from PyQt5.QtWidgets import (QTabWidget, QGridLayout, QLabel, QWidget,
    QPushButton, QComboBox, QGraphicsRectItem, QTableWidget, QTableWidgetItem,
    QTextEdit, QCheckBox, QHeaderView, QLineEdit, QVBoxLayout, QHBoxLayout,
    QGroupBox, QScrollArea, QFrame, QStackedWidget, QMessageBox, QToolButton,
    QSizePolicy)
from config import CPC, CPC_ERRORS
from ui_helpers import GuidedComboBox

from widgets import (
    CommandWidget,
    SetWidget,
    SetStatusWidget,
    SimpleStatusWidget,
    ToggleButton,
    ToggleSwitch,
    IndicatorWidget,
)
from plots.device_plots import SinglePlot
from devices.base_device import ComplexDevice
from devices.device_data import CPCData, CPCSettings
from utils import compile_cpc_settings
from plotting.device_plot_configs import CPCPlotConfig
from devices.data_writers import CPCDataWriter

# CPC widget containing CPC related GUI elements as tabs
class CPCWidget(ComplexDevice):
    # Signal emitted when device link changes: (device_id, link_type, old_target, new_target)
    link_changed = pyqtSignal(int, str, object, object)

    def __init__(self, device_config, *args, **kwargs):
        super().__init__(device_config, *args, **kwargs)

        # Track last known device settings to prevent spinbox jumping
        # Only update spinbox when DEVICE value changes, not when spinbox differs
        self._last_device_settings = {}

        # CPC-specific data (device owns its data)
        self.ten_hz_data = full(10, nan)  # 10 Hz logging data buffer
        self.pulse_analysis_index = None  # None = not in analysis mode, 0-6 = threshold index
        self.needs_calibration_fetch = True  # Fetch factory calibration on initial connection

        # create plot widget (first tab)
        self.plot_tab = SinglePlot(device_type=CPC)
        self.addTab(self.plot_tab, "Plot")
        # create combined control tab (merges Set and Status tabs)
        self.control_tab = CPCControlTab()
        self.addTab(self.control_tab, "Control")
        # Backward compatibility aliases
        self.set_tab = self.control_tab
        self.status_tab = self.control_tab
        # create database/ACTRIS tab for database settings and status
        self.database_tab = CPCDatabaseTab(device_config)
        self.addTab(self.database_tab, "ACTRIS")
        # create pulse quality widget for CPC pulse quality monitoring
        self.pulse_quality = PulseQuality()
        self.addTab(self.pulse_quality, "Pulse")

        # create list of widget references for updating gui with cpc system status (Advanced mode)
        self.cpc_status_widgets = [
            self.control_tab.temp_optics, self.control_tab.temp_saturator,
            self.control_tab.temp_condenser, self.control_tab.pres_inlet,
            self.control_tab.pres_nozzle, self.control_tab.laser_power,
            self.control_tab.liquid_level, self.control_tab.temp_cabin,
            self.control_tab.pres_critical_orifice, self.control_tab.pulse_quality
        ]
        # Simple mode status widgets for error coloring (same order as cpc_status_widgets)
        self.cpc_simple_status_widgets = [
            self.control_tab.simple_optics_temp, self.control_tab.simple_saturator_temp,
            self.control_tab.simple_condenser_temp, self.control_tab.simple_pres_inlet,
            self.control_tab.simple_pres_nozzle, self.control_tab.simple_laser_power,
            self.control_tab.simple_liquid_level, self.control_tab.simple_cabin_temp,
            self.control_tab.simple_pres_critical_orifice, self.control_tab.simple_pulse_quality
        ]

        # Plot configuration (composition over inheritance)
        self.plot_config = CPCPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = CPCDataWriter(self)

        # Add Device tab at the end
        self._add_device_tab_at_end()

        # Hide main plot dropdown by default (will be shown when PSM connects)
        if hasattr(self, 'main_plot_dropdown') and self.main_plot_dropdown:
            self.main_plot_dropdown.hide()
            if hasattr(self, '_main_plot_label') and self._main_plot_label:
                self._main_plot_label.hide()

    def get_plot_keys(self):
        """CPC has concentration and raw concentration plots."""
        return [':conc', ':raw']

    def get_plot_value_labels(self):
        """Return labels for CPC plot values."""
        return {
            ':conc': 'Dilution Corrected Concentration (#/cc)',
            ':raw': 'Raw CPC Concentration (#/cc)'
        }

    def get_rolling_buffer_keys(self):
        """CPC has 24-hour rolling buffers for pulse analysis."""
        return {':pd': 86400, ':pr': 86400}

    def is_connected_to_psm(self, app_config=None):
        """Check if any PSM has this CPC as its connected CPC."""
        if not app_config:
            return False
        from config import PSM
        dev_id = self.device_config.device_id
        for device_config in app_config.devices:
            if device_config.device_type == PSM:
                connected_cpc = device_config.extra_params.get('connected_cpc', 'None')
                try:
                    if connected_cpc != 'None' and int(connected_cpc) == dev_id:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    def update_main_plot_dropdown_visibility(self, app_config):
        """Show/hide main plot dropdown based on PSM connection."""
        if not hasattr(self, 'main_plot_dropdown') or not self.main_plot_dropdown:
            return

        has_psm = self.is_connected_to_psm(app_config)

        if has_psm:
            # Show dropdown, select :conc by default
            self.main_plot_dropdown.show()
            if hasattr(self, '_main_plot_label'):
                self._main_plot_label.show()
            # Set to :conc if not already
            if self.device_config.plot_to_main != ':conc':
                index = self.main_plot_dropdown.findData(':conc')
                if index >= 0:
                    self.main_plot_dropdown.setCurrentIndex(index)
                    self.device_config.plot_to_main = ':conc'
                    if hasattr(self, 'on_config_changed') and self.on_config_changed:
                        self.on_config_changed()
        else:
            # Hide dropdown, set to :raw
            self.main_plot_dropdown.hide()
            if hasattr(self, '_main_plot_label'):
                self._main_plot_label.hide()
            if self.device_config.plot_to_main != ':raw':
                self.device_config.plot_to_main = ':raw'
                if hasattr(self, 'on_config_changed') and self.on_config_changed:
                    self.on_config_changed()

    def set_app_config(self, app_config):
        """Set the app config reference for database tab RHTP dropdown."""
        if hasattr(self, 'database_tab'):
            self.database_tab.app_config = app_config
            # Don't populate immediately - the 5-second refresh timer will handle it
            # This prevents blocking the main thread during device creation

    def get_read_command_sequence(self, ten_hz=False):
        """
        CPC requires multiple sequential commands with timing delays.

        Sequence:
        1. :MEAS:ALL - Request all measurement data
        2. :SYST:PRNT (150ms delay) - Request print settings
        3. :SYST:PALL (300ms delay) - Request all system parameters
        4. :SYST:POUT (450ms delay) - Request factory calibration (once on connection)
        5. :MEAS:OPC_CONC_LOG (600ms delay) - Request 10Hz data (if enabled)
        """
        sequence = [
            (':MEAS:ALL', 0),
            (':SYST:PRNT', 150),
            (':SYST:PALL', 300),
        ]
        # Request factory calibration on initial connection
        if self.needs_calibration_fetch:
            sequence.append((':SYST:POUT', 450))
        if ten_hz:
            delay = 600 if self.needs_calibration_fetch else 450
            sequence.append((':MEAS:OPC_CONC_LOG', delay))
        return sequence

    # convert CPC status hex to binary and update error label colors
    def update_errors(self, status_hex, cabin_p_error):
        widget_amount = len(self.cpc_status_widgets) # get amount of widgets
        status_bin = bin(int(status_hex, 16)) # convert hex to int and int to binary
        status_bin = status_bin[2:].zfill(widget_amount) # remove 0b from string and fill with 0s
        total_errors = status_bin.count("1") # count number of 1s in status_bin
        inverted_status_bin = status_bin[::-1] # invert status_bin for error parsing
        for i in range(widget_amount): # iterate through all status widgets
            # change color of error label according to error bit (Advanced mode)
            self.cpc_status_widgets[i].change_color(inverted_status_bin[i])
            # change color of simple mode widgets as well
            self.cpc_simple_status_widgets[i].change_color(inverted_status_bin[i])
        # update cabin pressure label color according to error status (both modes)
        if cabin_p_error:
            self.status_tab.pres_cabin.change_color(1)
            self.control_tab.simple_pres_cabin.change_color(1)
            total_errors += 1
        else:
            self.status_tab.pres_cabin.change_color(0)
            self.control_tab.simple_pres_cabin.change_color(0)
        
        return total_errors # return total number of errors

    def _decode_error_hex(self, status_hex):
        """Decode CPC status hex to list of error descriptions."""
        from config import CPC_ERRORS
        errors = []
        if not status_hex:
            return errors
        try:
            status_int = int(status_hex, 16)
            for i, error_desc in enumerate(CPC_ERRORS):
                if status_int & (1 << i):
                    errors.append(error_desc)
        except (ValueError, TypeError):
            pass
        return errors

    def update_settings(self, settings):
        # Update GUI set values only when DEVICE value changes (not spinbox differs)
        # This prevents the jumping bug where stale device values overwrite user input

        # saturator temperature - only update if device value changed
        prev_sat = self._last_device_settings.get('saturator_temp')
        if prev_sat != settings[8]:
            self._last_device_settings['saturator_temp'] = settings[8]
            if str(settings[8]) == 'nan':
                self.set_tab.set_saturator_temp.value_spinbox.clear()
            else:
                self.set_tab.set_saturator_temp.value_spinbox.setValue(settings[8])
                if self.set_tab.set_saturator_temp.value_spinbox.text()[:-3] == "":
                    self.set_tab.set_saturator_temp.value_spinbox.lineEdit().setText(str(settings[8]))

        # condenser temperature - only update if device value changed
        prev_con = self._last_device_settings.get('condenser_temp')
        if prev_con != settings[6]:
            self._last_device_settings['condenser_temp'] = settings[6]
            if str(settings[6]) == 'nan':
                self.set_tab.set_condenser_temp.value_spinbox.clear()
            else:
                self.set_tab.set_condenser_temp.value_spinbox.setValue(settings[6])
                if self.set_tab.set_condenser_temp.value_spinbox.text()[:-3] == "":
                    self.set_tab.set_condenser_temp.value_spinbox.lineEdit().setText(str(settings[6]))

        # averaging time - only update if device value changed
        prev_avg = self._last_device_settings.get('averaging_time')
        if prev_avg != settings[5]:
            self._last_device_settings['averaging_time'] = settings[5]
            if str(settings[5]) == 'nan':
                self.set_tab.set_averaging_time.value_spinbox.setValue(0)
                self.set_tab.set_averaging_time.value_spinbox.clear()
            else:
                self.set_tab.set_averaging_time.value_spinbox.setValue(settings[5])
                if self.set_tab.set_averaging_time.value_spinbox.text()[:-2] == "":
                    self.set_tab.set_averaging_time.value_spinbox.lineEdit().setText(str(settings[5]))
        
        # update mode settings (Advanced mode)
        self.set_tab.autofill.update_state(settings[1]) # autofill
        self.set_tab.water_removal.update_state(settings[4]) # water removal
        self.set_tab.drain.update_state(settings[2]) # drain

        # update mode settings (Simple mode)
        self.control_tab.simple_autofill.update_state(settings[1])
        self.control_tab.simple_water_removal.update_state(settings[4])
        self.control_tab.simple_drain.update_state(settings[2])

        # update simple mode temperature setpoints for status bar coloring
        # settings[8] = saturator_temp, settings[6] = condenser_temp
        self.control_tab.simple_saturator_temp.set_setpoint(settings[8])
        self.control_tab.simple_condenser_temp.set_setpoint(settings[6])

        # update simple mode averaging time (read-only display)
        # settings[5] = averaging_time
        if str(settings[5]) != 'nan':
            self.control_tab.simple_averaging_time.change_value(f"{settings[5]} s")
    
    # update all data values in status tab
    def update_values(self, current_list):
        # update temperature values (Advanced mode)
        self.status_tab.temp_optics.change_value(str(current_list[5]) + " °C")
        self.status_tab.temp_saturator.change_value(str(current_list[3]) + " °C")
        self.status_tab.temp_condenser.change_value(str(current_list[4]) + " °C")
        self.status_tab.temp_cabin.change_value(str(current_list[6]) + " °C")

        # update temperature values (Simple mode)
        self.control_tab.simple_optics_temp.change_value(f"{current_list[5]} °C")
        self.control_tab.simple_saturator_temp.change_value(f"{current_list[3]} °C")
        self.control_tab.simple_condenser_temp.change_value(f"{current_list[4]} °C")
        self.control_tab.simple_cabin_temp.change_value(f"{current_list[6]} °C")

        # update pressure values (Advanced mode)
        self.status_tab.pres_inlet.change_value(str(current_list[7]) + " kPa")
        self.status_tab.pres_nozzle.change_value(str(current_list[9]) + " kPa")
        self.status_tab.pres_critical_orifice.change_value(str(current_list[8]) + " kPa")
        self.status_tab.pres_cabin.change_value(str(current_list[10]) + " kPa")

        # update pressure values (Simple mode)
        self.control_tab.simple_pres_inlet.change_value(f"{current_list[7]} kPa")
        self.control_tab.simple_pres_nozzle.change_value(f"{current_list[9]} kPa")
        self.control_tab.simple_pres_critical_orifice.change_value(f"{current_list[8]} kPa")
        self.control_tab.simple_pres_cabin.change_value(f"{current_list[10]} kPa")

        # update liquid level (both modes)
        if current_list[11] == 0:
            level_text = "LOW"
        elif current_list[11] == 1:
            level_text = "OK"
        elif current_list[11] == 2:
            level_text = "OVERFILL"
        else:
            level_text = "---"
        self.status_tab.liquid_level.change_value(level_text)
        self.control_tab.simple_liquid_level.change_value(level_text)

        # update laser power (both modes) - uses laser current value from index 12
        laser_current = current_list[12] if len(current_list) > 12 else None
        if laser_current is not None and not isnan(laser_current):
            laser_text = f"{laser_current:.2f} mA"
        else:
            laser_text = "---"
        self.status_tab.laser_power.change_value(laser_text)
        self.control_tab.simple_laser_power.change_value(laser_text)

        # update pulse quality (both modes) - uses pulse_ratio from index 13
        pulse_ratio = current_list[13] if len(current_list) > 13 else None
        if pulse_ratio is not None and not isnan(pulse_ratio):
            pulse_text = f"{pulse_ratio:.2f} %"
        else:
            pulse_text = "---"
        self.status_tab.pulse_quality.change_value(pulse_text)
        self.control_tab.simple_pulse_quality.change_value(pulse_text)

    def get_read_command(self):
        """Get CPC read command(s)."""
        # Note: Actual command sending logic is in DeviceManager.get_dev_data()
        # This method is for documentation/future use
        return ":MEAS:ALL"

    def get_status_bar_text(self):
        """Get formatted text for status bar display."""
        if self.current_data and hasattr(self.current_data, 'concentration'):
            conc = self.current_data.concentration
            if conc is not None:
                return f"{conc:.1f} #/cc"
        return super().get_status_bar_text()

    def process_parsed_messages(self, parsed_messages, device_config, data_holder):
        """
        Process CPC messages with buffering, settings compilation, and GUI updates.
        """
        from numpy import isnan, full, nan, array_equal
        from utils import compile_cpc_settings

        result = {
            'data_updated': False,
            'settings_updated': False,
            'needs_gui_update': False
        }

        # Initialize from extra_data buffer
        prnt_list = data_holder.extra_data.pop(str(self.dev_id) + ":prnt", full(13, nan))
        pall_list = data_holder.extra_data.pop(str(self.dev_id) + ":pall", full(28, nan))

        # Handle 10 Hz data if enabled
        if device_config.extra_params.get('10_hz', False):
            self.ten_hz_data = data_holder.extra_data.pop(
                str(self.dev_id) + ":10hz", self.ten_hz_data)

        # Process each parsed message
        for parsed in parsed_messages:
            if parsed['type'] == 'data':
                # Store measurement data with buffering 
                if isnan(self.current_data.concentration):
                    # First data received - no buffering needed
                    pass
                else:
                    # Buffer extra data for next update cycle
                    data_holder.extra_data[self.dev_id] = parsed['data']

                result['data_updated'] = True

                # Set error flags and record to error history
                if parsed.get('total_errors', 0) != 0:
                    data_holder.error_status = 1
                    data_holder.device_errors[self.dev_id] = True
                    # Record error to history with decoded description
                    status_hex = parsed.get('status_hex', '')
                    error_descriptions = self._decode_error_hex(status_hex)
                    device_name = getattr(self, 'device_nickname', None) or 'CPC'
                    data_holder.error_history.add_error(
                        device_id=self.dev_id,
                        device_name=device_name,
                        error_type='device_error',
                        description='; '.join(error_descriptions) if error_descriptions else 'Device error detected',
                        error_code=status_hex,
                        severity='error'
                    )

            elif parsed['type'] == 'settings':
                # Handle PRNT or PALL settings
                if parsed['command'] == ':SYST:PRNT':
                    if isnan(prnt_list[0]):
                        prnt_list = parsed['data']
                    else:
                        data_holder.extra_data[str(self.dev_id)+":prnt"] = parsed['data']
                elif parsed['command'] == ':SYST:PALL':
                    if isnan(pall_list[0]):
                        pall_list = parsed['data']
                    else:
                        data_holder.extra_data[str(self.dev_id)+":pall"] = parsed['data']

            elif parsed['type'] == 'ten_hz':
                # Handle 10 Hz logging data
                if isnan(float(self.ten_hz_data[0])):
                    self.ten_hz_data = parsed['data']
                else:
                    data_holder.extra_data[str(self.dev_id)+":10hz"] = parsed['data']

            elif parsed['type'] == 'self_test':
                # Display self-test errors in command widget
                from config import CPC_ERRORS
                self.set_tab.command_widget.update_text_box(parsed['raw'])
                self.set_tab.command_widget.update_text_box("self test error binary: " +
                    bin(int(parsed['data'], 16))[2:].zfill(len(CPC_ERRORS)))
                for error_msg in parsed.get('errors', []):
                    self.set_tab.command_widget.update_text_box(error_msg)

            elif parsed['type'] == 'info' and parsed['command'] == '*IDN':
                # Handle device identification
                self.set_tab.command_widget.update_text_box(parsed['raw'])
                serial_number = parsed['data']
                if device_config.serial_number != serial_number:
                    device_config.serial_number = serial_number
                    # Update GUI display
                    self._update_device_settings_display()
                    # Trigger config save
                    if hasattr(self, 'on_config_changed'):
                        self.on_config_changed()
                if self.dev_id in data_holder.idn_inquiry_devices:
                    data_holder.idn_inquiry_devices.remove(self.dev_id)

            # Show messages in command widget if requested
            if parsed.get('show_in_command_widget', False):
                self.set_tab.command_widget.update_text_box(parsed['raw'])
                if parsed['type'] == 'error' and 'error' in parsed:
                    logging.error("CPC error: " + str(parsed['error']))

        # Update GUI with current data
        self.update_values(self.current_data.to_array())
        self.update_settings(prnt_list)
        result['needs_gui_update'] = True

        # Compile and update settings if both PRNT and PALL are available
        settings_update = (str(prnt_list[0]) != "nan" and str(pall_list[0]) != "nan")

        # Skip settings update if pulse analysis is in progress
        if self.pulse_analysis_index is not None:
            settings_update = False

        if settings_update:
            # Get current settings array from device's typed settings dataclass
            settings = self.settings.to_array()

            # Compare with previous settings (stored in device)
            if not hasattr(self, 'previous_settings_array'):
                self.previous_settings_array = full(14, nan)

            if not array_equal(settings, self.previous_settings_array, equal_nan=True):
                self.previous_settings_array = settings.copy()
                data_holder.par_updates[self.dev_id] = 1
                result['settings_updated'] = True
            else:
                data_holder.par_updates[self.dev_id] = 0
        else:
            data_holder.par_updates[self.dev_id] = 0

        return result

    def parse_message(self, message, data_holder=None):
        """
        Parse CPC serial messages.

        Handles multiple message types:
        - :MEAS:ALL - measurement data with status
        - :SYST:PRNT - settings data
        - :SYST:PALL - all parameters
        - :MEAS:OPC_CONC_LOG - 10 Hz logging data
        - :STAT:SELF:LOG - self-test errors
        - :SELF:ERR - error messages
        - *IDN - device identification
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

            # Handle :MEAS:ALL - main measurement data
            if command == ":MEAS:ALL":
                status_hex = data[-1]

                # Check cabin pressure validity (0-200 kPa)
                # NaN is treated as "no data" (not an error)
                cabin_p_value = float(data[12])
                cabin_p_error = not isnan(cabin_p_value) and not (0 <= cabin_p_value <= 200)

                # Update error indicators
                total_errors = self.update_errors(status_hex, cabin_p_error)

                # Convert data to float (excluding status hex)
                meas_list = list(map(float, data[:-1]))

                # Update new data object (indices match firmware :MEAS:ALL response)
                self.current_data.concentration = meas_list[0]
                self.current_data.number_of_pulses = int(meas_list[1])
                self.current_data.dead_time = meas_list[2]
                # meas_list[3] = pulse_duration_firmware (not used, we calculate our own)
                # meas_list[4] = unused
                self.current_data.temp_saturator = meas_list[5]
                self.current_data.temp_optics = meas_list[6]
                self.current_data.temp_condenser = meas_list[7]
                self.current_data.temp_cabin = meas_list[8]
                self.current_data.pres_inlet = meas_list[9]
                self.current_data.pres_critical_orifice = meas_list[10]
                self.current_data.pres_nozzle = meas_list[11]
                self.current_data.pres_cabin = meas_list[12]
                self.current_data.laser_current = meas_list[13]
                self.current_data.liquid_level = int(meas_list[14])
                # Calculate pulse_duration and pulse_ratio
                if str(meas_list[3]) == "nan":
                    self.current_data.pulse_ratio = nan
                elif meas_list[1] == 0:
                    self.current_data.pulse_ratio = 0
                else:
                    self.current_data.pulse_ratio = round(meas_list[3]/meas_list[1], 2)
                # pulse_duration is calculated later in plot_manager for pulse quality plot
                self.current_data.pulse_duration = meas_list[3] if len(meas_list) > 3 else nan
                self.current_data.status_hex = status_hex
                self.current_data.total_errors = total_errors

                return {
                    'type': 'data',
                    'command': command,
                    'data': self.current_data.to_array(),
                    'status_hex': status_hex,
                    'total_errors': total_errors,
                    'raw': message,
                    'update_gui': True
                }

            # Handle :SYST:PRNT - settings data
            elif command == ":SYST:PRNT":
                prnt_list = list(map(float, data))

                # Update settings object
                self.settings.mode = prnt_list[0]
                self.settings.autofill = prnt_list[1]
                self.settings.drain = prnt_list[2]
                self.settings.flow_adjustment = prnt_list[3]
                self.settings.water_removal = prnt_list[4]
                self.settings.averaging_time = prnt_list[5]
                self.settings.condenser_temp = prnt_list[6]
                self.settings.optics_temp = prnt_list[7]
                self.settings.saturator_temp = prnt_list[8]
                self.settings.measured_cpc_flow = prnt_list[10]
                self.settings.dead_time_correction = prnt_list[12]

                return {
                    'type': 'settings',
                    'command': command,
                    'data': prnt_list,
                    'raw': message,
                    'update_gui': True
                }

            # Handle :SYST:POUT - factory calibration values
            elif command == ":SYST:POUT":
                # Parse factory calibration values (indices 6-7 are temp setpoints)
                if len(data) >= 8:
                    self.factory_calibration = {
                        'saturator_temp': float(data[6]),
                        'condenser_temp': float(data[7]),
                    }
                    # Update UI to show factory values
                    self.update_factory_calibration_display()
                    self.needs_calibration_fetch = False

                return {
                    'type': 'calibration',
                    'command': command,
                    'data': data,
                    'raw': message,
                    'update_gui': False
                }

            # Handle :SYST:PALL - all parameters
            elif command == ":SYST:PALL":
                data[22] = "NaN"  # device id
                data[23] = "NaN"  # firmware variant letter TODO store device id and firmware variant letter somewhere
                pall_list = list(map(float, data))

                # Update settings object with pall fields
                self.settings.nominal_inlet_flow = pall_list[24]
                self.settings.opc_threshold = pall_list[26]
                self.settings.opc_threshold_2 = pall_list[27]
                self.settings.k_factor = pall_list[20]
                self.settings.tau = pall_list[25]

                return {
                    'type': 'settings',
                    'command': command,
                    'data': pall_list,
                    'raw': message,
                    'update_gui': False
                }

            # Handle :MEAS:OPC_CONC_LOG - 10 Hz logging
            elif command == ":MEAS:OPC_CONC_LOG":
                del data[0]  # remove timestamp
                return {
                    'type': 'ten_hz',
                    'command': command,
                    'data': data,
                    'raw': message,
                    'update_gui': False
                }

            # Handle :STAT:SELF:LOG - self-test errors
            elif command == ":STAT:SELF:LOG":
                error_length = len(CPC_ERRORS)
                # convert hex to int and int to binary + remove 0b from string and fill with 0s
                status_bin = bin(int(data[0], 16))[2:].zfill(error_length)
                inverted_status_bin = status_bin[::-1]

                # Build error message
                error_messages = []
                for i in range(error_length):
                    if inverted_status_bin[i] == "1":
                        error_messages.append(f"Bit {i}: {CPC_ERRORS[i]}")

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
                error_msg = CPC_ERRORS[error_code] if error_code < len(CPC_ERRORS) else "Unknown error"
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
            return {
                'type': 'error',
                'command': 'unknown',
                'data': None,
                'error': str(e),
                'raw': message,
                'update_gui': False
            }

    # Device Manager Integration Methods

    def has_status_tab(self):
        """CPC has a status tab."""
        return True

    def get_status_tab(self):
        """Return CPC status tab."""
        return self.status_tab

    def supports_10hz_mode(self):
        """CPC supports 10 Hz mode."""
        return True

    def update_factory_calibration_display(self):
        """Update SetStatusWidgets with factory calibration values."""
        if not hasattr(self, 'factory_calibration'):
            return

        cal = self.factory_calibration
        self.control_tab.set_saturator_temp.set_factory_value(cal['saturator_temp'])
        self.control_tab.set_condenser_temp.set_factory_value(cal['condenser_temp'])

    def send_read_commands(self, dev_conn, device_config):
        """
        Send CPC read commands based on mode.

        Handles three modes:
        1. Pulse analysis mode: Send pulse analysis messages
        2. 10 Hz mode: Send 10 Hz messages
        3. Normal mode: Send standard measurement messages
        """
        from config import PULSE_ANALYSIS_THRESHOLDS

        # Check if in pulse analysis mode
        if self.pulse_analysis_index is not None and self.pulse_analysis_index >= 0:
            threshold = PULSE_ANALYSIS_THRESHOLDS[self.pulse_analysis_index]
            dev_conn.send_pulse_analysis_messages(threshold)
        # Check if in 10 Hz mode
        elif device_config.extra_params.get('10_hz', False):
            dev_conn.send_multiple_messages(self, ten_hz=True)
        # Normal mode
        else:
            dev_conn.send_multiple_messages(self)

    def validate_10hz_mode(self, app_config, device_config):
        """
        Validate and synchronize CPC 10 Hz mode.

        When 10 Hz is enabled:
        - Set TAVG to 0.1 if not already
        - Validate that at least one PSM with 10 Hz is connected

        When 10 Hz is disabled:
        - Set TAVG to 1.0 if currently < 1
        """
        from config import PSM

        dev_id = device_config.device_id
        ten_hz_enabled = device_config.extra_params.get('10_hz', False)

        if ten_hz_enabled:
            # When 10 Hz ON: Set TAVG to 0.1 if needed
            if self.is_connected:
                if self.settings and self.settings.averaging_time != 0.1:
                    self.connection.send_message(":SET:TAVG 0.1")

            # Validate PSM connection - check if any PSM has this CPC connected with 10Hz
            def _cpc_matches(psm_config):
                connected_cpc = psm_config.extra_params.get('connected_cpc', 'None')
                try:
                    return int(connected_cpc) == dev_id if connected_cpc != 'None' else False
                except (ValueError, TypeError):
                    return False
            ten_hz_connected = any(
                _cpc_matches(psm_config) and psm_config.extra_params.get('10_hz', False)
                for psm_config in app_config.devices
                if psm_config.device_type == PSM
            )

            # If no PSM with 10Hz is connected, disable 10Hz mode
            if not ten_hz_connected:
                device_config.extra_params['10_hz'] = False
                if hasattr(self, 'on_config_changed'):
                    self.on_config_changed()
        else:
            # When 10 Hz OFF: Set TAVG to 1.0 if currently < 1
            if self.is_connected:
                if self.settings and self.settings.averaging_time < 1:
                    self.connection.send_message(":SET:TAVG 1")

    # App Integration Methods

    def supports_idn_inquiry(self):
        """CPC supports *IDN? identity inquiry."""
        return True

    @classmethod
    def get_default_extra_params(cls, device_type: int) -> dict:
        """Return default extra_params for CPC devices."""
        return {
            '10_hz': False,
            'database_enabled': False,
            'linked_rhtp': 'None',
            'db_averaging_interval': '1 minute'
        }

    def restore_ui_state(self, device_config, app_config):
        """Restore CPC UI state from configuration."""
        if hasattr(self, 'set_app_config'):
            self.set_app_config(app_config)
        # Initialize dropdown visibility based on PSM connection
        self.update_main_plot_dropdown_visibility(app_config)

    def setup_main_window_references(self, main_window):
        """Set up CPC database tab references to main window."""
        if hasattr(self, 'database_tab'):
            self.database_tab.main_window = main_window
            if hasattr(main_window, 'database_manager') and hasattr(main_window.database_manager, 'connection_string_cached'):
                self.database_tab.connection_string_input.setText(main_window.database_manager.connection_string_cached)
            self.database_tab.update_global_connection_status()


class CPCControlTab(QWidget):
    """Combined control tab merging Set and Status functionality.

    Supports two modes:
    - Simple Mode (default): Clean read-only view with status indicators
    - Advanced Mode: Full control with setpoints and serial commands
    """

    # Signal emitted when mode changes (for persistence)
    mode_changed = pyqtSignal(bool)  # True = advanced mode

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._advanced_mode = False

        # Main layout with mode toggle at top
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Mode toggle header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 4, 8, 4)

        header_layout.addStretch()

        self.mode_toggle_btn = QPushButton("⚙ Advanced Mode")
        self.mode_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                padding: 4px 12px;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)
        self.mode_toggle_btn.clicked.connect(self._toggle_mode)
        header_layout.addWidget(self.mode_toggle_btn)

        outer_layout.addWidget(header_widget)

        # Stacked widget for simple/advanced views
        self.mode_stack = QStackedWidget()
        outer_layout.addWidget(self.mode_stack)

        # Create both views
        self._create_simple_mode_view()
        self._create_advanced_mode_view()

        # Start in simple mode
        self.mode_stack.setCurrentIndex(0)

    def _toggle_mode(self):
        """Toggle between simple and advanced modes."""
        self._advanced_mode = not self._advanced_mode
        if self._advanced_mode:
            self.mode_stack.setCurrentIndex(1)
            self.mode_toggle_btn.setText("◀ Simple Mode")
        else:
            self.mode_stack.setCurrentIndex(0)
            self.mode_toggle_btn.setText("⚙ Advanced Mode")
        self.mode_changed.emit(self._advanced_mode)

    def set_advanced_mode(self, advanced: bool):
        """Set mode programmatically (for restoring from settings)."""
        if advanced != self._advanced_mode:
            self._toggle_mode()

    def _get_group_style(self, color):
        """Return group box stylesheet with the given accent color."""
        return f"""
            QGroupBox {{
                border: 1px solid {color};
                border-radius: 6px;
                margin-top: 14px;
                padding: 12px 8px 8px 8px;
                background-color: #3a3a3a;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: {color};
                font-weight: bold;
                font-size: 14px;
            }}
        """

    def _create_simple_mode_view(self):
        """Create the simple mode view with read-only status widgets."""
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # === TEMPERATURES GROUP (Simple) ===
        temp_group = QGroupBox("🌡️ Temperatures")
        temp_group.setStyleSheet(self._get_group_style("#e67e22"))
        temp_layout = QGridLayout()
        temp_layout.setSpacing(4)

        # Row 0: Saturator T, Condenser T
        self.simple_saturator_temp = SimpleStatusWidget("Saturator T", " °C", is_temperature=True, error_name="Saturator Error")
        temp_layout.addWidget(self.simple_saturator_temp, 0, 0)
        self.simple_condenser_temp = SimpleStatusWidget("Condenser T", " °C", is_temperature=True, error_name="Condenser Error")
        temp_layout.addWidget(self.simple_condenser_temp, 0, 1)

        # Row 1: Cabin T, Optics T
        self.simple_cabin_temp = SimpleStatusWidget("Cabin T", " °C", is_temperature=True, error_name="Cabin Error")
        temp_layout.addWidget(self.simple_cabin_temp, 1, 0)
        self.simple_optics_temp = SimpleStatusWidget("Optics T", " °C", is_temperature=True, error_name="Optics Error")
        temp_layout.addWidget(self.simple_optics_temp, 1, 1)

        # Equal column stretch for consistent layout
        temp_layout.setColumnStretch(0, 1)
        temp_layout.setColumnStretch(1, 1)

        temp_group.setLayout(temp_layout)
        main_layout.addWidget(temp_group)

        # === PRESSURES GROUP (Simple) ===
        pressure_group = QGroupBox("📊 Pressures")
        pressure_group.setStyleSheet(self._get_group_style("#9b59b6"))
        pressure_layout = QGridLayout()
        pressure_layout.setSpacing(4)

        # Row 0: Inlet, Nozzle
        self.simple_pres_inlet = SimpleStatusWidget("Inlet", " kPa", is_temperature=False, error_name="Inlet Pressure Error")
        pressure_layout.addWidget(self.simple_pres_inlet, 0, 0)
        self.simple_pres_nozzle = SimpleStatusWidget("Nozzle", " kPa", is_temperature=False, error_name="Nozzle Pressure Error")
        pressure_layout.addWidget(self.simple_pres_nozzle, 0, 1)

        # Row 1: Critical orifice, Cabin
        self.simple_pres_critical_orifice = SimpleStatusWidget("Critical orifice", " kPa", is_temperature=False, error_name="Critical Orifice Error")
        pressure_layout.addWidget(self.simple_pres_critical_orifice, 1, 0)
        self.simple_pres_cabin = SimpleStatusWidget("Cabin", " kPa", is_temperature=False, error_name="Cabin Pressure Error")
        pressure_layout.addWidget(self.simple_pres_cabin, 1, 1)

        # Equal column stretch for consistent layout
        pressure_layout.setColumnStretch(0, 1)
        pressure_layout.setColumnStretch(1, 1)

        pressure_group.setLayout(pressure_layout)
        main_layout.addWidget(pressure_group)

        # === CONTROLS & STATUS (combined row - Simple) ===
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        # Controls (still interactive in simple mode)
        controls_group = QGroupBox("🎛️ Controls")
        controls_group.setStyleSheet(self._get_group_style("#27ae60"))
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(2)
        controls_layout.setContentsMargins(4, 4, 4, 4)
        controls_layout.setAlignment(Qt.AlignTop)

        # Toggle switches for simple mode
        self.simple_autofill = ToggleSwitch("Autofill", "Automatically refill liquid when low")
        controls_layout.addWidget(self.simple_autofill)
        self.simple_water_removal = ToggleSwitch("Water removal", "Enable water removal cycle")
        controls_layout.addWidget(self.simple_water_removal)
        self.simple_drain = ToggleSwitch("Drain", "Enable liquid drainage")
        controls_layout.addWidget(self.simple_drain)

        controls_group.setLayout(controls_layout)
        status_row.addWidget(controls_group, 1)

        # Status Group (Simple)
        status_group = QGroupBox("Status")
        status_group.setStyleSheet(self._get_group_style("#17a2b8"))
        status_layout = QVBoxLayout()
        status_layout.setSpacing(4)
        status_layout.setContentsMargins(4, 4, 4, 4)
        status_layout.setAlignment(Qt.AlignTop)

        self.simple_laser_power = SimpleStatusWidget("Laser power", "", is_temperature=False, error_name="Laser Error")
        status_layout.addWidget(self.simple_laser_power)
        self.simple_liquid_level = SimpleStatusWidget("Liquid level", "", is_temperature=False, error_name="Level LOW")
        status_layout.addWidget(self.simple_liquid_level)
        self.simple_pulse_quality = SimpleStatusWidget("Pulse quality", " %", is_temperature=False, error_name="Pulse Quality Error")
        status_layout.addWidget(self.simple_pulse_quality)

        status_group.setLayout(status_layout)
        status_row.addWidget(status_group, 1)

        # Settings Group (Simple - read-only averaging time)
        settings_group = QGroupBox("Settings")
        settings_group.setStyleSheet(self._get_group_style("#6c757d"))
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(4)
        settings_layout.setContentsMargins(4, 4, 4, 4)
        settings_layout.setAlignment(Qt.AlignTop)

        self.simple_averaging_time = SimpleStatusWidget("Averaging time", " s", is_temperature=False, error_name="")
        settings_layout.addWidget(self.simple_averaging_time)

        settings_group.setLayout(settings_layout)
        status_row.addWidget(settings_group, 1)

        main_layout.addLayout(status_row)
        main_layout.addStretch()

        scroll_area.setWidget(content_widget)
        self.mode_stack.addWidget(scroll_area)

    def _create_advanced_mode_view(self):
        """Create the advanced mode view with full controls."""
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
        temp_group.setStyleSheet(self._get_group_style("#e67e22"))
        temp_layout = QGridLayout()
        temp_layout.setSpacing(4)

        # Row 0: Saturator T, Condenser T (setpoint + actual)
        self.set_saturator_temp = SetStatusWidget("Saturator T", " °C")
        self.set_saturator_temp.setToolTip("Saturator temperature setpoint and actual value")
        temp_layout.addWidget(self.set_saturator_temp, 0, 0)

        self.set_condenser_temp = SetStatusWidget("Condenser T", " °C")
        self.set_condenser_temp.setToolTip("Condenser temperature setpoint and actual value")
        temp_layout.addWidget(self.set_condenser_temp, 0, 1)

        # Row 1: Cabin T, Optics T (read-only)
        self.temp_cabin = IndicatorWidget("Cabin T")
        self.temp_cabin.setToolTip("Cabin temperature (read-only)")
        temp_layout.addWidget(self.temp_cabin, 1, 0)

        self.temp_optics = IndicatorWidget("Optics T")
        self.temp_optics.setToolTip("Optics temperature (read-only)")
        temp_layout.addWidget(self.temp_optics, 1, 1)

        temp_group.setLayout(temp_layout)
        main_layout.addWidget(temp_group)

        # === PRESSURES GROUP ===
        pressure_group = QGroupBox("📊 Pressures")
        pressure_group.setStyleSheet(self._get_group_style("#9b59b6"))
        pressure_layout = QGridLayout()
        pressure_layout.setSpacing(4)

        # Row 0: Inlet, Nozzle
        self.pres_inlet = IndicatorWidget("Inlet")
        self.pres_inlet.setToolTip("Inlet pressure")
        pressure_layout.addWidget(self.pres_inlet, 0, 0)

        self.pres_nozzle = IndicatorWidget("Nozzle")
        self.pres_nozzle.setToolTip("Nozzle pressure")
        pressure_layout.addWidget(self.pres_nozzle, 0, 1)

        # Row 1: Critical orifice, Cabin
        self.pres_critical_orifice = IndicatorWidget("Critical orifice")
        self.pres_critical_orifice.setToolTip("Critical orifice pressure")
        pressure_layout.addWidget(self.pres_critical_orifice, 1, 0)

        self.pres_cabin = IndicatorWidget("Cabin")
        self.pres_cabin.setToolTip("Cabin pressure")
        pressure_layout.addWidget(self.pres_cabin, 1, 1)

        pressure_group.setLayout(pressure_layout)
        main_layout.addWidget(pressure_group)

        # === CONTROLS, STATUS & SETTINGS (combined row) ===
        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        # Controls Group (toggles)
        controls_group = QGroupBox("🎛️ Controls")
        controls_group.setStyleSheet(self._get_group_style("#27ae60"))
        controls_layout = QVBoxLayout()
        controls_layout.setSpacing(2)
        controls_layout.setContentsMargins(4, 4, 4, 4)
        controls_layout.setAlignment(Qt.AlignTop)

        self.autofill = ToggleSwitch("Autofill", "Automatically refill liquid when low")
        controls_layout.addWidget(self.autofill)

        self.water_removal = ToggleSwitch("Water removal", "Enable water removal cycle")
        controls_layout.addWidget(self.water_removal)

        self.drain = ToggleSwitch("Drain", "Enable liquid drainage")
        controls_layout.addWidget(self.drain)

        controls_group.setLayout(controls_layout)
        status_row.addWidget(controls_group, 1)

        # Status Group (indicators)
        status_group = QGroupBox("Status")
        status_group.setStyleSheet(self._get_group_style("#17a2b8"))
        status_layout = QVBoxLayout()
        status_layout.setSpacing(2)
        status_layout.setContentsMargins(4, 4, 4, 4)
        status_layout.setAlignment(Qt.AlignTop)

        self.laser_power = IndicatorWidget("Laser power")
        self.laser_power.setToolTip("Laser power status")
        status_layout.addWidget(self.laser_power)

        self.liquid_level = IndicatorWidget("Liquid level")
        self.liquid_level.setToolTip("Saturator liquid level")
        status_layout.addWidget(self.liquid_level)

        self.pulse_quality = IndicatorWidget("Pulse quality")
        self.pulse_quality.setToolTip("Pulse quality status")
        status_layout.addWidget(self.pulse_quality)

        status_group.setLayout(status_layout)
        status_row.addWidget(status_group, 1)

        # Settings Group (Advanced only)
        settings_group = QGroupBox("Settings")
        settings_group.setStyleSheet(self._get_group_style("#6c757d"))
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(4)
        settings_layout.setContentsMargins(4, 4, 4, 4)
        settings_layout.setAlignment(Qt.AlignTop)

        self.set_averaging_time = SetWidget("Averaging time", " s")
        self.set_averaging_time.setToolTip("Data averaging time in seconds")
        settings_layout.addWidget(self.set_averaging_time)

        settings_group.setLayout(settings_layout)
        status_row.addWidget(settings_group, 1)

        main_layout.addLayout(status_row)

        # === SERIAL COMMANDS GROUP (collapsible, Advanced only) ===
        self.commands_group = QGroupBox("📡 Serial Commands")
        self.commands_group.setCheckable(True)
        self.commands_group.setChecked(False)
        self.commands_group.setStyleSheet(self._get_group_style("#7f8c8d"))
        commands_layout = QVBoxLayout()
        commands_layout.setContentsMargins(4, 4, 4, 4)

        self.command_widget = CommandWidget("CPC")
        commands_layout.addWidget(self.command_widget)

        self.commands_group.setLayout(commands_layout)
        self.commands_group.toggled.connect(self._toggle_commands)
        self.command_widget.setVisible(False)
        main_layout.addWidget(self.commands_group)

        # Add stretch at end
        main_layout.addStretch()

        scroll_area.setWidget(content_widget)
        self.mode_stack.addWidget(scroll_area)

    def _toggle_commands(self, checked):
        """Toggle visibility of serial commands section."""
        self.command_widget.setVisible(checked)

    # === Backward compatibility properties ===
    @property
    def temp_saturator(self):
        """Alias for backward compatibility with status tab."""
        return self.set_saturator_temp

    @property
    def temp_condenser(self):
        """Alias for backward compatibility with status tab."""
        return self.set_condenser_temp


# set tab widget containing settings and message input
# used in CPCWidget (kept for backward compatibility)
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



# status tab containing status indicator widgets
# used in CPCWidget
class CPCStatusTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create layout

        # temperature indicators
        self.temp_optics = IndicatorWidget("Optics temperature") # create optics temperature indicator
        layout.addWidget(self.temp_optics, 0, 0)
        self.temp_saturator = IndicatorWidget("Saturator temperature") # create saturator temperature indicator
        layout.addWidget(self.temp_saturator, 1, 0)
        self.temp_condenser = IndicatorWidget("Condenser temperature") # create condenser temperature indicator
        layout.addWidget(self.temp_condenser, 2, 0)
        self.temp_cabin = IndicatorWidget("Cabin temperature") # create cabin temp indicator
        layout.addWidget(self.temp_cabin, 3, 0)

        # pressure indicators
        self.pres_inlet = IndicatorWidget("Inlet pressure") # create inlet pressure indicator
        layout.addWidget(self.pres_inlet, 0, 1)
        self.pres_nozzle = IndicatorWidget("Nozzle pressure") # create nozzle pressure indicator
        layout.addWidget(self.pres_nozzle, 1, 1)
        self.pres_critical_orifice = IndicatorWidget("Critical orifice pressure") # create nozzle pressure indicator
        layout.addWidget(self.pres_critical_orifice, 2, 1)
        self.pres_cabin = IndicatorWidget("Cabin pressure") # create cabin pressure indicator
        layout.addWidget(self.pres_cabin, 3, 1)

        # misc indicators
        self.laser_power = IndicatorWidget("Laser power") # create laser power indicator
        layout.addWidget(self.laser_power, 0, 2, 1, 1)
        self.liquid_level = IndicatorWidget("Liquid level") # create liquid level indicator
        layout.addWidget(self.liquid_level, 1, 2, 1, 1)
        self.pulse_quality = IndicatorWidget("Pulse quality") # create pulse quality indicator
        layout.addWidget(self.pulse_quality, 2, 2, 1, 1)

        self.setLayout(layout)


class PulseQuality(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create layout
        self.setLayout(layout) # set layout

        # PULSE MONITOR

        # average time and history time values
        self.average_time = 0
        self.history_time = 0

        # pulse monitor graphics layout and plot
        pm_graphics = GraphicsLayoutWidget()
        layout.addWidget(pm_graphics, 0, 0)
        pm_plot = pm_graphics.addPlot()
        pm_viewbox = pm_plot.getViewBox()
        pm_viewbox.setDefaultPadding(padding=0.2) # set default padding
        # set graphics layout size to square
        #pm_graphics.setFixedSize(500, 500)
        # use automatic downsampling and clipping to reduce the drawing load
        pm_plot.setDownsampling(mode='peak')
        pm_plot.setClipToView(True)
        # create color zones (yellow, black, green)
        yellow_zone = QGraphicsRectItem(-40000, -10, 80000, 20) # x, y, w, h
        yellow_zone.setPen(mkPen(0, 0, 0))
        yellow_zone.setBrush(mkBrush(150, 150, 0))
        pm_viewbox.addItem(yellow_zone, ignoreBounds=True)
        black_zone = QGraphicsRectItem(0, 0.8, 800, 0.25) # x, y, w, h
        black_zone.setPen(mkPen(0, 0, 0)) # black pen
        black_zone.setBrush(mkBrush(0, 0, 0)) # black brush
        pm_viewbox.addItem(black_zone, ignoreBounds=True)
        green_zone = QGraphicsRectItem(150, 0.95, 500, 0.1) # x, y, w, h
        green_zone.setPen(mkPen(0, 0, 0))
        green_zone.setBrush(mkBrush(0, 130, 0))
        pm_viewbox.addItem(green_zone, ignoreBounds=True)
        # create data points, average point and current point plots
        self.data_points = pm_plot.plot(pen=None, symbol='o', symbolPen=None, symbolSize=8, symbolBrush=(255, 255, 255, 50))
        self.average_point = pm_plot.plot(pen=None, symbol='o', symbolPen={'color':(255, 0, 255), 'width':3}, symbolSize=14, symbolBrush=None)
        self.current_point = pm_plot.plot(pen=None, symbol='o', symbolPen={'color':(0, 0, 0), 'width':2}, symbolSize=14, symbolBrush=(255, 255, 255))
        # set up axis labels and styles
        y_axis = pm_plot.getAxis('left')
        y_axis.setLabel('Pulse ratio', color='w')
        y_axis.enableAutoSIPrefix(False)
        self.set_axis_style(y_axis, 'w')
        x_axis = pm_plot.getAxis('bottom')
        x_axis.setLabel('Pulse duration', units='ns', color='w')
        x_axis.enableAutoSIPrefix(False)
        self.set_axis_style(x_axis, 'w')
        # create legend and add items
        self.legend = LegendItem(offset=(-1, 1), labelTextColor='w', labelTextSize='8pt')
        self.legend.setParentItem(pm_plot.graphicsItem())

        # pulse monitor options layout
        pm_options = QGridLayout()
        layout.addLayout(pm_options, 1, 0)
        # set font for main labels
        label_font = self.font() # get current global font
        label_font.setPointSize(12) # set font size
        # add values label
        values_label = QLabel("Values", objectName="label")
        values_label.setAlignment(Qt.AlignCenter)
        values_label.setFont(label_font) # apply font to value label
        pm_options.addWidget(values_label, 0, 0, 1, 2)
        # current values
        pm_options.addWidget(QLabel("Pulse duration (ns)", objectName="label"), 1, 0)
        self.current_duration = QLabel("", objectName="value-label")
        self.current_duration.setWordWrap(True)
        pm_options.addWidget(self.current_duration, 1, 1)
        pm_options.addWidget(QLabel("Pulse ratio", objectName="label"), 2, 0)
        self.current_ratio = QLabel("", objectName="value-label")
        self.current_ratio.setWordWrap(True)
        pm_options.addWidget(self.current_ratio, 2, 1)
        # average values
        self.average_duration_label = QLabel("", objectName="label")
        pm_options.addWidget(self.average_duration_label, 3, 0)
        self.average_duration = QLabel("", objectName="value-label")
        pm_options.addWidget(self.average_duration, 3, 1)
        self.average_ratio_label = QLabel("", objectName="label")
        pm_options.addWidget(self.average_ratio_label, 4, 0)
        self.average_ratio = QLabel("", objectName="value-label")
        pm_options.addWidget(self.average_ratio, 4, 1)
        # add options label
        options_label = QLabel("Options", objectName="label")
        options_label.setAlignment(Qt.AlignCenter)
        options_label.setFont(label_font)
        pm_options.addWidget(options_label, 5, 0, 1, 2)
        # history time selection dropdown
        pm_options.addWidget(QLabel("History draw limit", objectName="label"), 6, 0)
        self.history_time_select = QComboBox(objectName="combo_box")
        self.history_time_select.addItems(["1h", "2h", "6h", "12h", "24h"])
        self.history_time_select.setCurrentIndex(0)
        self.history_time_select.currentIndexChanged.connect(self.update_pm_labels)
        pm_options.addWidget(self.history_time_select, 6, 1)
        # average time selection dropdown
        pm_options.addWidget(QLabel("Average time", objectName="label"), 7, 0)
        self.average_time_select = QComboBox(objectName="combo_box")
        self.average_time_select.addItems(["1h", "2h", "6h", "12h", "24h"])
        self.average_time_select.setCurrentIndex(0)
        self.average_time_select.currentIndexChanged.connect(self.update_pm_labels)
        pm_options.addWidget(self.average_time_select, 7, 1)

        # update legend and labels
        self.update_pm_labels()

        # PULSE ANALYSIS

        # pulse analysis graphics layout and plot
        pa_graphics = GraphicsLayoutWidget()
        layout.addWidget(pa_graphics, 0, 1)
        pa_plot = pa_graphics.addPlot()
        pa_viewbox = pa_plot.getViewBox()
        pa_plot.setDownsampling(mode='peak')
        pa_plot.setClipToView(True)
        pa_plot.showGrid(x=True, y=True, alpha=0.5)
        # create analysis plot and values list
        self.analysis_points = pa_plot.plot(pen=None, symbol='o', symbolPen=(0, 0, 0), symbolSize=10, symbolBrush=(255, 255, 255))
        self.analysis_values = [] # list for storing analysis values as tuples (x = duration, y = threshold)
        # set up axis labels and styles
        y_axis = pa_plot.getAxis('left')
        y_axis.setLabel('Threshold', units='mV', color='w')
        y_axis.enableAutoSIPrefix(False)
        self.set_axis_style(y_axis, 'w')
        x_axis = pa_plot.getAxis('bottom')
        x_axis.setLabel('Pulse duration', units='ns', color='w')
        x_axis.enableAutoSIPrefix(False)
        self.set_axis_style(x_axis, 'w')
        # set fixed plot scaling
        pa_viewbox.setRange(xRange=[0, 600], yRange=[0, 1500], padding=0.1)
        pa_viewbox.setMouseEnabled(x=False, y=False) # disable mouse interaction
        pa_plot.hideButtons() # remove autorange button

        # pulse analysis options layout
        pa_options = QGridLayout()
        layout.addLayout(pa_options, 1, 1)
        # start analysis button
        self.start_analysis = QPushButton("Start pulse analysis", objectName="button_widget")
        font = self.start_analysis.font() # get current font
        font.setPointSize(12) # set font size
        self.start_analysis.setFont(font) # apply font
        pa_options.addWidget(self.start_analysis, 0, 0, 1, 2)
        # current threshold
        pa_options.addWidget(QLabel("Current threshold (mV)", objectName="label"), 1, 0)
        self.current_threshold = QLabel("", objectName="value-label")
        pa_options.addWidget(self.current_threshold, 1, 1)
        # dummy widget to balance layout
        pa_options.addWidget(QWidget(), 2, 0, 2, 2)

        # update pulse analysis status
        self.update_pa_status(False)

        # TESTING

        # self.add_analysis_point(500, 150)
        # self.add_analysis_point(300, 500)
        # self.add_analysis_point(200, 800)
        # self.add_analysis_point(120, 1150)
        # self.add_analysis_point(100, 1500)

        # import numpy as np
        # # create test data arrays and plot them
        # test_size = 86400 # h = 3600, 24h = 86400
        # #test_cutoff = 3600
        # test_cutoff = 600
        # #test_x = [1, 2, 3, 4, 5]
        # #test_y = [2, 2, 1, 5, 3]
        # test_x = np.random.normal(loc=400, scale=75, size=test_size)
        # test_y = np.random.normal(loc=0.95, scale=0.02, size=test_size)
        # # plot test data, average point and current point
        # self.data_points.setData(test_x[(-1*test_cutoff):], test_y[(-1*test_cutoff):])
        # self.average_point.setData([np.average(test_x)], [np.average(test_y)])
        # self.current_point.setData([test_x[-1]], [test_y[-1]])
        # #self.current_point.setData([], []) # set empty data
    
    def set_axis_style(self, axis, color):
        axis.setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
        axis.setPen(color)
        axis.setTextPen(color)
        axis.label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font
    
    # update pulse monitor labels and legend
    def update_pm_labels(self):
        history_str = self.history_time_select.currentText() + " history"
        average_str = self.average_time_select.currentText() + " avg"
        self.legend.clear()
        self.legend.addItem(self.data_points, name=history_str)
        self.legend.addItem(self.average_point, name=average_str)
        self.legend.addItem(self.current_point, name="Current value")
        self.average_duration_label.setText(average_str + " pulse duration (ns)")
        self.average_ratio_label.setText(average_str + " pulse ratio")
        # update average and history time values
        self.history_time = int(self.history_time_select.currentText().replace("h", ""))
        self.average_time = int(self.average_time_select.currentText().replace("h", ""))
    
    def update_pa_status(self, flag):
        if flag:
            self.start_analysis.setDisabled(True)
            self.start_analysis.setText("Analysis in progress...")
        else:
            self.start_analysis.setDisabled(False)
            self.start_analysis.setText("Start pulse analysis")
    
    def add_analysis_point(self, pulse_duration, threshold_value):
        # add analysis point to list of values as tuple
        self.analysis_values.append((pulse_duration, threshold_value))
        # trim nan pulse durations from list
        trimmed_values = [n for n in self.analysis_values if not isnan(n[0])]
        # update plot with new values
        x_values = [n[0] for n in trimmed_values]
        y_values = [n[1] for n in trimmed_values]
        self.analysis_points.setData(x_values, y_values)
        # update current threshold value
        self.current_threshold.setText(str(threshold_value))
    
    def clear_analysis_points(self):
        # clear list of analysis values
        self.analysis_values.clear()
        # clear plot with empty data
        self.analysis_points.setData([], [])
        # clear current threshold value
        self.current_threshold.setText("")


class CollapsibleSection(QWidget):
    """A collapsible section widget with toggle button and content area."""

    def __init__(self, title, parent=None, initially_collapsed=False):
        super().__init__(parent)

        self.toggle_button = QToolButton()
        self.toggle_button.setStyleSheet("QToolButton { border: none; font-size: 9pt; color: #888; }")
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow if not initially_collapsed else Qt.RightArrow)
        self.toggle_button.setText(title)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(not initially_collapsed)
        self.toggle_button.clicked.connect(self._on_toggle)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.content_area)

        self.content_area.setVisible(not initially_collapsed)

    def _on_toggle(self, checked):
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.content_area.setVisible(checked)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_layout(self, layout):
        self.content_layout.addLayout(layout)

    def set_collapsed(self, collapsed):
        self.toggle_button.setChecked(not collapsed)
        self._on_toggle(not collapsed)


class CPCDatabaseTab(QWidget):
    """Database/ACTRIS tab for CPC devices showing database status and settings."""

    def __init__(self, device_config, *args, **kwargs):
        super().__init__()

        self.device_config = device_config
        self.app_config = None  # Will be set by CPC widget after creation
        self.main_window = None
        self.row_data = {}
        self.editing_in_progress = False
        self._highlight_timer = None

        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # ===== STATUS ROW (top left corner, inline) =====
        status_row = QHBoxLayout()
        status_row.setSpacing(20)

        # Next write countdown
        self.next_write_value = QLabel("--:--")
        self.next_write_value.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffa726;")
        status_row.addWidget(self.next_write_value)

        # Progress
        self.progress_value = QLabel("No data")
        self.progress_value.setStyleSheet("font-size: 11px; color: #66bb6a;")
        status_row.addWidget(self.progress_value)

        # Status badge
        self.db_status_value = QLabel("Disabled")
        self.db_status_value.setStyleSheet("font-size: 11px; color: #666;")
        status_row.addWidget(self.db_status_value)

        status_row.addStretch()
        main_layout.addLayout(status_row)

        # ===== SETTINGS SECTION (minimalistic, matching data_settings_dialog style) =====
        # Database row
        db_row = QHBoxLayout()
        db_row.setSpacing(0)

        db_label = QLabel("Database:")
        db_label.setStyleSheet("color: #ccc; font-size: 13px;")
        db_label.setFixedWidth(70)
        db_row.addWidget(db_label)

        self.connection_string_input = QLineEdit()
        self.connection_string_input.setPlaceholderText("postgresql://user:password@host:port/database")
        self.connection_string_input.setStyleSheet("""
            QLineEdit {
                color: #4a9eff;
                background: transparent;
                border: 1px solid #3d3d3d;
                border-radius: 3px;
                padding: 2px 6px;
                font-family: monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #4a9eff;
            }
        """)
        self.connection_string_input.textChanged.connect(self.connection_string_changed)
        db_row.addWidget(self.connection_string_input)

        self.global_connection_status = QLabel("Disconnected")
        self.global_connection_status.setStyleSheet("color: #666; font-size: 11px; margin-left: 10px;")
        self.global_connection_status.setFixedWidth(85)
        db_row.addWidget(self.global_connection_status)

        main_layout.addLayout(db_row)

        # RHTP + Interval row
        rhtp_row = QHBoxLayout()
        rhtp_row.setSpacing(15)

        rhtp_label = QLabel("RHTP:")
        rhtp_label.setStyleSheet("color: #ccc; font-size: 13px;")
        rhtp_row.addWidget(rhtp_label)

        self.linked_rhtp_dropdown = GuidedComboBox()
        self.linked_rhtp_dropdown.setMinimumWidth(120)
        self.linked_rhtp_dropdown.set_tooltips(
            enabled_tooltip="Select the RHTP sensor to link with this CPC",
            disabled_tooltip="Disable database first to change"
        )
        self.linked_rhtp_dropdown.currentIndexChanged.connect(self.linked_rhtp_changed)
        rhtp_row.addWidget(self.linked_rhtp_dropdown)

        interval_label = QLabel("Interval:")
        interval_label.setStyleSheet("color: #ccc; font-size: 13px;")
        rhtp_row.addWidget(interval_label)

        self.interval_dropdown = GuidedComboBox()
        self.interval_dropdown.setMinimumWidth(100)
        self.interval_dropdown.addItems(['1 minute', '5 minutes', '10 minutes', '15 minutes', '1 hour', '3 hours'])
        self.interval_dropdown.set_tooltips(
            enabled_tooltip="Select the time period for data averaging",
            disabled_tooltip="Disable database first to change"
        )
        self.interval_dropdown.currentTextChanged.connect(self.interval_changed)
        rhtp_row.addWidget(self.interval_dropdown)

        rhtp_row.addStretch()
        main_layout.addLayout(rhtp_row)

        # Enable checkbox with hint (like data_settings_dialog)
        enable_row = QHBoxLayout()
        self.db_enabled_checkbox = QCheckBox("Enable database writes")
        self.db_enabled_checkbox.setToolTip("Start writing averaged data to the ACTRIS database")
        self.db_enabled_checkbox.stateChanged.connect(self.db_enabled_changed)
        enable_row.addWidget(self.db_enabled_checkbox)

        self.active_devices_count = QLabel("0 CPCs using database")
        self.active_devices_count.setStyleSheet("color: #666; font-size: 11px; margin-left: 10px;")
        enable_row.addWidget(self.active_devices_count)
        enable_row.addStretch()
        main_layout.addLayout(enable_row)

        # Last write info row (like data_settings_dialog)
        last_row = QHBoxLayout()
        last_row.setSpacing(10)

        last_label = QLabel("Last write:")
        last_label.setStyleSheet("color: #ccc; font-size: 13px;")
        last_label.setFixedWidth(70)
        last_row.addWidget(last_label)

        self.last_write_value = QLabel("Never")
        self.last_write_value.setStyleSheet("color: #666; font-size: 11px;")
        last_row.addWidget(self.last_write_value)

        records_label = QLabel("Records:")
        records_label.setStyleSheet("color: #888; font-size: 11px; margin-left: 20px;")
        last_row.addWidget(records_label)

        self.records_value = QLabel("0")
        self.records_value.setStyleSheet("color: #666; font-size: 11px;")
        last_row.addWidget(self.records_value)

        last_row.addStretch()
        main_layout.addLayout(last_row)

        # Set up guidance targets
        self.linked_rhtp_dropdown.set_guide_target(
            self.db_enabled_checkbox,
            "Uncheck 'Enable database' to change"
        )
        self.interval_dropdown.set_guide_target(
            self.db_enabled_checkbox,
            "Uncheck 'Enable database' to change"
        )

        # ===== DATA TABLE (stretches to fill space) =====
        table_header_row = QHBoxLayout()
        table_label = QLabel("Preview")
        table_label.setStyleSheet("color: #888; font-size: 11px;")
        table_header_row.addWidget(table_label)

        table_header_row.addStretch()

        # Delete button (small, inline)
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setToolTip("Delete selected rows from database")
        self.delete_button.setStyleSheet("font-size: 10px; padding: 2px 6px; color: #888;")
        self.delete_button.clicked.connect(self.delete_selected_rows)
        table_header_row.addWidget(self.delete_button)

        self.show_more_btn = QPushButton("Show more")
        self.show_more_btn.setToolTip("Load 20 more rows from database")
        self.show_more_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.show_more_btn.clicked.connect(self.show_more_clicked)
        table_header_row.addWidget(self.show_more_btn)

        self.refresh_preview_btn = QPushButton("Refresh")
        self.refresh_preview_btn.setToolTip("Refresh preview from database")
        self.refresh_preview_btn.setStyleSheet("font-size: 11px; padding: 2px 8px;")
        self.refresh_preview_btn.clicked.connect(self.refresh_preview_clicked)
        table_header_row.addWidget(self.refresh_preview_btn)

        main_layout.addLayout(table_header_row)

        # Track how many rows we're showing
        self._preview_row_count = 10

        self.data_table = QTableWidget()
        self.data_table.setColumnCount(12)
        self.data_table.setHorizontalHeaderLabels([
            "Start", "End", "Conc", "Flow In", "T Sat", "T Cond",
            "T Inlet", "P Inlet", "RH In", "Pulse", "Err", "Status"
        ])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setRowCount(10)
        self.data_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.data_table.setSelectionMode(QTableWidget.MultiSelection)
        self.data_table.cellChanged.connect(self.cell_edited)
        main_layout.addWidget(self.data_table, 1)  # stretch factor 1 to fill space

        # ===== MESSAGES SECTION (collapsible) =====
        self.messages_section = CollapsibleSection("Messages", initially_collapsed=True)
        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setMaximumHeight(60)
        self.error_text.setStyleSheet("font-size: 11px;")
        self.messages_section.add_widget(self.error_text)
        main_layout.addWidget(self.messages_section)

        self.setLayout(main_layout)

        # Timer for periodic refresh (every 5 seconds)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_status)
        self.refresh_timer.start(5000)

    def populate_rhtp_dropdown(self):
        """Populate linked RHTP dropdown from RHTP devices in app config."""
        if not self.app_config:
            return

        # Store current selection
        current_rhtp_id = self.device_config.extra_params.get('linked_rhtp', 'None')

        # Clear and rebuild dropdown
        self.linked_rhtp_dropdown.blockSignals(True)
        self.linked_rhtp_dropdown.clear()

        # Always add "None" option first
        self.linked_rhtp_dropdown.addItem("None", "None")

        # Add RHTP devices from config
        from config import RHTP
        for device_config in self.app_config.devices:
            if device_config.device_type == RHTP:
                device_name = device_config.device_nickname or device_config.device_type_name
                self.linked_rhtp_dropdown.addItem(device_name, device_config.device_id)

        # Check if only "None" option exists (no RHTP devices available)
        if self.linked_rhtp_dropdown.count() == 1:
            # Update tooltip to be educational about optional RHTP
            self.linked_rhtp_dropdown.set_tooltips(
                enabled_tooltip="No RHTP devices available. Add an RHTP device for full ACTRIS compatibility (optional)",
                disabled_tooltip="Disable database first to change linked RHTP device"
            )
        else:
            # Restore normal tooltip when RHTP devices exist
            self.linked_rhtp_dropdown.set_tooltips(
                enabled_tooltip="Select the RHTP sensor to link with this CPC for database recording",
                disabled_tooltip="Disable database first to change linked RHTP device"
            )

        # Restore previous selection if it still exists
        if current_rhtp_id is not None:
            index = self.linked_rhtp_dropdown.findData(current_rhtp_id)
            if index >= 0:
                self.linked_rhtp_dropdown.setCurrentIndex(index)

        self.linked_rhtp_dropdown.blockSignals(False)

    def refresh_status(self):
        """Refresh database status display and dropdowns from device parameters."""
        # Refresh connection string from database_manager cache
        if self.main_window and hasattr(self.main_window, 'database_manager'):
            if hasattr(self.main_window.database_manager, 'connection_string_cached'):
                cached_conn_string = self.main_window.database_manager.connection_string_cached
                # Only update if field is empty and cache has a value
                if cached_conn_string and not self.connection_string_input.text():
                    self.connection_string_input.blockSignals(True)
                    self.connection_string_input.setText(cached_conn_string)
                    self.connection_string_input.blockSignals(False)

        # Refresh RHTP dropdown in case devices were added/removed
        self.populate_rhtp_dropdown()

        # Update linked RHTP dropdown from config
        rhtp_id = self.device_config.extra_params.get('linked_rhtp', 'None')
        index = self.linked_rhtp_dropdown.findData(rhtp_id)
        if index >= 0:
            self.linked_rhtp_dropdown.blockSignals(True)
            self.linked_rhtp_dropdown.setCurrentIndex(index)
            self.linked_rhtp_dropdown.blockSignals(False)

        # Update averaging interval dropdown from config
        interval = self.device_config.extra_params.get('db_averaging_interval', '1 minute')
        index = self.interval_dropdown.findText(interval)
        if index >= 0:
            self.interval_dropdown.blockSignals(True)
            self.interval_dropdown.setCurrentIndex(index)
            self.interval_dropdown.blockSignals(False)

        # Update database enabled status from config
        enabled = self.device_config.extra_params.get('database_enabled', False)
        self.db_enabled_checkbox.setChecked(enabled)

        # Disable dropdowns when database is active (prevent changing settings during recording)
        self.linked_rhtp_dropdown.setEnabled(not enabled)
        self.interval_dropdown.setEnabled(not enabled)

        if enabled:
            self.db_status_value.setText("Enabled")
            self.db_status_value.setStyleSheet("font-size: 11px; color: #66bb6a;")
        else:
            self.db_status_value.setText("Disabled")
            self.db_status_value.setStyleSheet("font-size: 11px; color: #666;")

    def update_last_write(self, timestamp_str):
        """Update last write timestamp display."""
        self.last_write_value.setText(timestamp_str)

    def update_record_count(self, count):
        """Update records written counter."""
        self.records_value.setText(str(count))

    def update_progress(self, samples_collected, total_samples, interval_start, interval_seconds):
        """
        Update progress indicators for current averaging interval.

        Args:
            samples_collected: Number of samples collected so far
            total_samples: Total samples needed for interval
            interval_start: Start time of current interval
            interval_seconds: Total seconds in interval
        """
        from datetime import datetime, timedelta

        # Update sample count
        self.progress_value.setText(f"{samples_collected}/{total_samples} samples")
        self.progress_value.setStyleSheet("font-size: 11px; color: #66bb6a;" if samples_collected > 0 else "font-size: 11px; color: #666;")

        # Calculate time remaining
        if interval_start:
            now = datetime.now()
            interval_end = interval_start + timedelta(seconds=interval_seconds)
            time_remaining = interval_end - now

            if time_remaining.total_seconds() > 0:
                # Format as MM:SS or HH:MM:SS
                total_seconds = int(time_remaining.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60

                if hours > 0:
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    time_str = f"{minutes:02d}:{seconds:02d}"

                self.next_write_value.setText(time_str)
                self.next_write_value.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffa726;")
            else:
                self.next_write_value.setText("Writing...")
                self.next_write_value.setStyleSheet("font-size: 20px; font-weight: bold; color: #66bb6a;")
        else:
            self.next_write_value.setText("--:--")
            self.next_write_value.setStyleSheet("font-size: 20px; font-weight: bold; color: #666;")

    def reset_progress(self):
        """Reset progress indicators."""
        self.progress_value.setText("No data")
        self.progress_value.setStyleSheet("font-size: 11px; color: #666;")
        self.next_write_value.setText("--:--")
        self.next_write_value.setStyleSheet("font-size: 20px; font-weight: bold; color: #666;")

    def update_data_table(self, rows):
        """
        Update latest data table with database rows.

        Args:
            rows: List of dictionaries with row data from database
        """
        # Block signals to prevent cellChanged from firing during population
        self.editing_in_progress = True
        self.data_table.blockSignals(True)

        self.data_table.setRowCount(len(rows))
        self.row_data.clear()  # Clear old row metadata

        for i, row in enumerate(rows):
            # Store full row data including primary key for updates/deletes
            self.row_data[i] = {
                'time': row.get('time'),  # Full timestamp with timezone
                'instr_id': row.get('instr_id', self.device_config.serial_number),
                'data': row.copy()
            }
            # Starttime
            starttime_val = row.get('starttime', '')
            if starttime_val:
                # Format: "YYYY-MM-DD HH:MM:SS+TZ" -> extract HH:MM:SS
                starttime_str = str(starttime_val)
                if ' ' in starttime_str:
                    # Split on space and take time part, then remove timezone
                    time_part = starttime_str.split(' ')[1].split('+')[0].split('-')[0]
                    starttime_val = time_part
                else:
                    starttime_val = starttime_str[:8]
            self.data_table.setItem(i, 0, QTableWidgetItem(starttime_val))

            # Endtime (time)
            time_val = row.get('time', '')
            if time_val:
                # Format: "YYYY-MM-DD HH:MM:SS+TZ" -> extract HH:MM:SS
                time_str = str(time_val)
                if ' ' in time_str:
                    # Split on space and take time part, then remove timezone
                    time_part = time_str.split(' ')[1].split('+')[0].split('-')[0]
                    time_val = time_part
                else:
                    time_val = time_str[:8]
            self.data_table.setItem(i, 1, QTableWidgetItem(time_val))

            # Concentration
            conc_val = row.get('conc')
            self.data_table.setItem(i, 2, QTableWidgetItem(f"{conc_val:.0f}" if conc_val is not None else ""))

            # Flow Inlet
            flow_inl = row.get('flow_inl')
            self.data_table.setItem(i, 3, QTableWidgetItem(f"{flow_inl:.2f}" if flow_inl is not None else ""))

            # Temp Saturator
            temp_sat = row.get('temp_sat')
            self.data_table.setItem(i, 4, QTableWidgetItem(f"{temp_sat:.1f}" if temp_sat is not None else ""))

            # Temp Condenser
            temp_cond = row.get('temp_cond')
            self.data_table.setItem(i, 5, QTableWidgetItem(f"{temp_cond:.1f}" if temp_cond is not None else ""))

            # Temp Inlet (RHTP)
            temp_inlet = row.get('temp_inlet')
            self.data_table.setItem(i, 6, QTableWidgetItem(f"{temp_inlet:.1f}" if temp_inlet is not None else ""))

            # Pressure Inlet (RHTP)
            pres_inlet = row.get('pressure_inlet')
            self.data_table.setItem(i, 7, QTableWidgetItem(f"{pres_inlet:.0f}" if pres_inlet is not None else ""))

            # RH Inlet (RHTP)
            rh_inlet = row.get('humidity_inlet')
            self.data_table.setItem(i, 8, QTableWidgetItem(f"{rh_inlet:.1f}" if rh_inlet is not None else ""))

            # Pulse height (pulse duration average)
            pulse_height = row.get('pulse_height')
            self.data_table.setItem(i, 9, QTableWidgetItem(f"{pulse_height:.0f}" if pulse_height is not None else ""))

            # Errors
            errors = row.get('stat_log')
            self.data_table.setItem(i, 10, QTableWidgetItem(str(errors) if errors is not None else ""))

            # Status hex
            status_hex = row.get('status_hex', '')
            self.data_table.setItem(i, 11, QTableWidgetItem(status_hex if status_hex else ""))

            # Make timestamp columns read-only (columns 0 and 1)
            for col in [0, 1]:
                item = self.data_table.item(i, col)
                if item:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

        # Re-enable signals after population complete
        self.data_table.blockSignals(False)
        self.editing_in_progress = False

    def add_message(self, message):
        """Add a message to the error/info text box."""
        self.error_text.append(message)

    def cell_edited(self, row, column):
        """
        Handle cell editing - save changes to database immediately.

        Args:
            row: Row index
            column: Column index
        """
        from datetime import datetime

        # Ignore if we're programmatically updating cells
        if self.editing_in_progress:
            return

        # Check if we have metadata for this row
        if row not in self.row_data:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - Cannot find row data")
            return

        # Get the cell item and new value
        item = self.data_table.item(row, column)
        if not item:
            return

        new_value_str = item.text()

        # Map column index to database column name
        column_map = {
            2: ('conc', float),
            3: ('flow_inl', float),
            4: ('temp_sat', float),
            5: ('temp_cond', float),
            6: ('temp_inlet', float),
            7: ('pressure_inlet', float),
            8: ('humidity_inlet', float),
            9: ('pulse_height', float),
            10: ('stat_log', int),
            11: ('status_hex', str),
        }

        if column not in column_map:
            # Column not editable (like timestamps)
            return

        db_column, value_type = column_map[column]
        row_meta = self.row_data[row]
        time_val = row_meta['time']
        instr_id = row_meta['instr_id']

        # Validate and convert new value
        try:
            if new_value_str.strip() == '':
                new_value = None
            elif value_type == str:
                new_value = new_value_str
            else:
                new_value = value_type(new_value_str)
        except ValueError:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - Invalid value '{new_value_str}' for {db_column}")
            # Revert to original value
            self.editing_in_progress = True
            original_val = row_meta['data'].get(db_column)
            if original_val is not None:
                if value_type == float:
                    item.setText(f"{original_val:.1f}")
                elif value_type == int:
                    item.setText(str(original_val))
                else:
                    item.setText(str(original_val))
            else:
                item.setText('')
            self.editing_in_progress = False
            return

        # Check if value actually changed
        original_value = row_meta['data'].get(db_column)
        if original_value == new_value or (original_value is None and new_value is None):
            return  # No change

        # Update database
        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - Database manager not available")
            return

        updates = {db_column: new_value}
        success, message = self.main_window.database_manager.update_record(time_val, instr_id, updates)

        if success:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Updated {db_column} = {new_value}")
            # Update our stored data
            row_meta['data'][db_column] = new_value
        else:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - {message}")
            # Revert to original value
            self.editing_in_progress = True
            if original_value is not None:
                if value_type == float:
                    item.setText(f"{original_value:.1f}")
                elif value_type == int:
                    item.setText(str(original_value))
                else:
                    item.setText(str(original_value))
            else:
                item.setText('')
            self.editing_in_progress = False

    def delete_selected_rows(self):
        """Delete selected rows from the database after confirmation."""
        from PyQt5.QtWidgets import QMessageBox
        from datetime import datetime

        # Get selected rows
        selected_rows = set(index.row() for index in self.data_table.selectedIndexes())

        if not selected_rows:
            QMessageBox.warning(self, "Delete Rows", "No rows selected.\n\nPlease select rows to delete.")
            return

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete {len(selected_rows)} row(s)?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Collect records to delete (time, instr_id pairs)
        records_to_delete = []
        for row in selected_rows:
            if row in self.row_data:
                row_meta = self.row_data[row]
                records_to_delete.append((row_meta['time'], row_meta['instr_id']))

        if not records_to_delete:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - No valid rows to delete")
            return

        # Delete from database
        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - Database manager not available")
            return

        success, message = self.main_window.database_manager.delete_records(records_to_delete)

        if success:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: {message}")
            # Refresh table to show updated data (respects current row count)
            self.refresh_preview()
            # Clear row selection after deletion
            self.data_table.clearSelection()
        else:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - {message}")

    def linked_rhtp_changed(self, index):
        """Handle linked RHTP dropdown selection change."""
        # Get the selected RHTP device ID from the dropdown
        rhtp_id = self.linked_rhtp_dropdown.currentData()

        # Get old value before updating
        old_rhtp_id = self.device_config.extra_params.get('linked_rhtp', 'None')

        # Update device config
        self.device_config.extra_params['linked_rhtp'] = rhtp_id

        # Emit link changed signal via parent CPCWidget for tab grouping
        parent_widget = self.parent()
        if parent_widget and hasattr(parent_widget, 'link_changed'):
            parent_widget.link_changed.emit(
                self.device_config.device_id,
                'cpc_rhtp',
                old_rhtp_id,
                rhtp_id
            )

        # Trigger config save (CPC widget should have on_config_changed method)
        if hasattr(self, 'on_config_changed'):
            self.on_config_changed()

    def interval_changed(self, text):
        """Handle averaging interval dropdown selection change."""
        from datetime import datetime

        # Update device config
        self.device_config.extra_params['db_averaging_interval'] = text
        # Trigger config save
        if hasattr(self, 'on_config_changed'):
            self.on_config_changed()

        # If database is enabled, recreate the averager with new interval
        if self.main_window and hasattr(self.main_window, 'database_manager'):
            db_enabled = self.device_config.extra_params.get('database_enabled', False)
            if db_enabled:
                dev_id = self.device_config.device_id

                # Convert interval string to minutes
                interval_map = {'1 minute': 1, '5 minutes': 5, '10 minutes': 10, '15 minutes': 15, '1 hour': 60, '3 hours': 180}
                interval_minutes = interval_map.get(text, 1)

                # Recreate averager with new interval
                self.main_window.database_manager.create_averager(dev_id, interval_minutes)

                # Reset progress indicators
                self.progress_value.setText("No data")
                self.next_write_value.setText("-")

                # Add message to log
                current_time = datetime.now()
                self.add_message(f"{current_time.strftime('%H:%M:%S')}: Averaging interval changed to {text}")

    def _highlight_widget(self, widget, highlight=True):
        """Temporarily highlight a widget with red border to indicate an error."""
        if highlight:
            original_style = widget.styleSheet()
            widget.setStyleSheet(original_style + " border: 2px solid #ff5555;")
            widget.setFocus()
            # Remove highlight after 2 seconds
            if self._highlight_timer:
                self._highlight_timer.stop()
            self._highlight_timer = QTimer()
            self._highlight_timer.setSingleShot(True)
            self._highlight_timer.timeout.connect(lambda: widget.setStyleSheet(original_style))
            self._highlight_timer.start(2000)

    def db_enabled_changed(self, state):
        """Handle database enabled checkbox state change with full validation and connection management."""
        from datetime import datetime

        enabled = state == Qt.Checked

        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - Database manager not available")
            self.db_enabled_checkbox.setChecked(False)
            return

        dev_id = self.device_config.device_id

        if enabled:
            # Validation 1: Check connection string is not empty
            conn_string = self.connection_string_input.text().strip()
            if not conn_string:
                self._highlight_widget(self.connection_string_input)
                self.db_enabled_checkbox.setChecked(False)
                self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - Please enter a database connection string")
                # Expand messages section to show error
                self.messages_section.set_collapsed(False)
                return

            # Validation 2: Check RHTP is linked - show confirmation if not
            rhtp_id = self.linked_rhtp_dropdown.currentData()
            if rhtp_id is None or rhtp_id == 'None':
                # Show confirmation dialog
                reply = QMessageBox.question(
                    self,
                    "No RHTP Device Linked",
                    "No RHTP device is linked to this CPC.\n\n"
                    "RHTP provides temperature, pressure, and humidity data for ACTRIS compliance.\n\n"
                    "Do you want to continue without RHTP data?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    # User chose not to continue - highlight RHTP dropdown
                    self._highlight_widget(self.linked_rhtp_dropdown)
                    self.db_enabled_checkbox.setChecked(False)
                    return
                # User chose to continue without RHTP - proceed with enabling

            # Validation 3: If RHTP is selected, check it exists
            if rhtp_id and rhtp_id != 'None':
                rhtp_widget = self.main_window.data_holder.device_widgets.get(rhtp_id)
                if not rhtp_widget:
                    QMessageBox.warning(self, "Database Error", "Linked RHTP device not found.")
                    self._highlight_widget(self.linked_rhtp_dropdown)
                    self.db_enabled_checkbox.setChecked(False)
                    self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - RHTP device not found")
                    return

            # Register device with database manager (connects if first device)
            success, message = self.main_window.database_manager.register_device(dev_id, conn_string)

            if success:
                # Create averager using dropdown value
                interval_str = self.interval_dropdown.currentText()
                interval_map = {'1 minute': 1, '5 minutes': 5, '10 minutes': 10, '15 minutes': 15, '1 hour': 60, '3 hours': 180}
                interval_minutes = interval_map.get(interval_str, 1)
                self.main_window.database_manager.create_averager(dev_id, interval_minutes)

                # Update device config
                self.device_config.extra_params['database_enabled'] = True
                if hasattr(self, 'on_config_changed'):
                    self.on_config_changed()

                # Update UI
                self.db_status_value.setText("Enabled")
                self.db_status_value.setStyleSheet("font-size: 11px; color: #66bb6a;")
                self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Database enabled - {message}")

                # Disable dropdowns to prevent changes during recording
                self.linked_rhtp_dropdown.setEnabled(False)
                self.interval_dropdown.setEnabled(False)

                # Update global status in all CPC tabs
                self.update_global_connection_status()
                self.sync_global_status_to_all_cpcs()

            else:
                # Connection failed
                QMessageBox.warning(self, "Database Error", f"Failed to enable database:\n\n{message}")
                self.db_enabled_checkbox.setChecked(False)
                self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - {message}")

        else:
            # Disabling database
            success, message = self.main_window.database_manager.unregister_device(dev_id)

            # Update device config
            self.device_config.extra_params['database_enabled'] = False
            if hasattr(self, 'on_config_changed'):
                self.on_config_changed()

            # Update UI
            self.db_status_value.setText("Disabled")
            self.db_status_value.setStyleSheet("font-size: 11px; color: #666;")
            self.reset_progress()  # Reset progress indicators
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Database disabled - {message}")

            # Re-enable dropdowns now that database is disabled
            self.linked_rhtp_dropdown.setEnabled(True)
            self.interval_dropdown.setEnabled(True)

            # Update global status in all CPC tabs
            self.update_global_connection_status()
            self.sync_global_status_to_all_cpcs()

    def connection_string_changed(self, text):
        """Handle connection string input change."""
        # Store to database manager's cached connection string
        if self.main_window and hasattr(self.main_window, 'database_manager'):
            self.main_window.database_manager.connection_string_cached = text

            # Update all other CPC ACTRIS tabs with the same connection string
            self.sync_connection_string_to_all_cpcs(text)

            # Auto-save will happen when app closes or user manually saves

    def refresh_preview_clicked(self):
        """Refresh preview table from database (resets to 10 rows)."""
        from datetime import datetime

        # Reset row count on manual refresh
        self._preview_row_count = 10

        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Database manager not available")
            return

        conn_string = self.connection_string_input.text()
        if not conn_string:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: No connection string configured")
            return

        # Test connection and refresh
        success, message = self.main_window.database_manager.test_connection(conn_string)

        if success:
            dev_id = self.device_config.device_id
            latest_rows = self.main_window.database_manager.get_latest_rows(self._preview_row_count, dev_id)
            self.update_data_table(latest_rows)
            self.global_connection_status.setText("Connected")
            self.global_connection_status.setStyleSheet("color: #66bb6a; font-size: 11px; margin-left: 10px;")
        else:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Connection failed - {message}")
            self.global_connection_status.setText("Failed")
            self.global_connection_status.setStyleSheet("color: #ff6b6b; font-size: 11px; margin-left: 10px;")

    def show_more_clicked(self):
        """Load 20 more rows into preview."""
        from datetime import datetime

        self._preview_row_count += 20

        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            return

        if not self.main_window.database_manager.connected:
            # Try to connect first
            conn_string = self.connection_string_input.text()
            if conn_string:
                self.main_window.database_manager.test_connection(conn_string)

        if self.main_window.database_manager.connected:
            dev_id = self.device_config.device_id
            latest_rows = self.main_window.database_manager.get_latest_rows(self._preview_row_count, dev_id)
            self.update_data_table(latest_rows)

    def refresh_preview(self):
        """Refresh preview table (called after writes)."""
        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            return

        if not self.main_window.database_manager.connected:
            return

        dev_id = self.device_config.device_id
        latest_rows = self.main_window.database_manager.get_latest_rows(self._preview_row_count, dev_id)
        self.update_data_table(latest_rows)

    def sync_connection_string_to_all_cpcs(self, conn_string):
        """Update connection string in all other CPC ACTRIS tabs."""
        if not self.main_window or not hasattr(self.main_window, 'data_holder'):
            return

        from config import CPC

        # Loop through all CPC devices
        for dev_id, widget in self.main_window.data_holder.device_widgets.items():
            # Check if it's a CPC and has database_tab
            if hasattr(widget, 'device_type') and widget.device_type == CPC:
                if hasattr(widget, 'database_tab') and widget.database_tab != self:
                    # Update connection string without triggering textChanged signal
                    widget.database_tab.connection_string_input.blockSignals(True)
                    widget.database_tab.connection_string_input.setText(conn_string)
                    widget.database_tab.connection_string_input.blockSignals(False)

    def update_global_connection_status(self):
        """Update global connection status display."""
        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            return

        db_manager = self.main_window.database_manager

        # Update connection status
        if db_manager.connected:
            self.global_connection_status.setText("Connected")
            self.global_connection_status.setStyleSheet("color: green;")
        else:
            self.global_connection_status.setText("Disconnected")
            self.global_connection_status.setStyleSheet("color: gray;")

        # Update active devices count
        active_count = db_manager.get_active_device_count() if hasattr(db_manager, 'get_active_device_count') else 0
        self.active_devices_count.setText(f"{active_count} CPC{'s' if active_count != 1 else ''} using database")

    def sync_global_status_to_all_cpcs(self):
        """Update global connection status in all other CPC ACTRIS tabs."""
        if not self.main_window or not hasattr(self.main_window, 'data_holder'):
            return

        from config import CPC

        # Loop through all CPC devices
        for dev_id, widget in self.main_window.data_holder.device_widgets.items():
            # Check if it's a CPC and has database_tab
            if hasattr(widget, 'device_type') and widget.device_type == CPC:
                if hasattr(widget, 'database_tab') and widget.database_tab != self:
                    # Update global status
                    widget.database_tab.update_global_connection_status()


__all__ = ['CPCWidget']
