from PyQt5.QtGui import QPalette, QColor, QIntValidator, QDoubleValidator, QFont, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QLocale
from numpy import full, nan, isnan, array_equal
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, PlotCurveItem, LegendItem, PlotItem, mkPen, mkBrush
from PyQt5.QtWidgets import (QTabWidget, QGridLayout, QLabel, QWidget,
    QPushButton, QComboBox, QGraphicsRectItem, QTableWidget, QTableWidgetItem,
    QTextEdit, QCheckBox, QHeaderView, QLineEdit)
from config import CPC, CPC_ERRORS
from ui_helpers import GuidedComboBox

from widgets import (
    CommandWidget,
    SetWidget,
    ToggleButton,
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
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=CPC, *args, **kwargs)

        # CPC-specific data (device owns its data)
        self.ten_hz_data = full(10, nan)  # 10 Hz logging data buffer
        self.pulse_analysis_index = None  # None = not in analysis mode, 0-6 = threshold index

        # create set tab widget for cpc settings
        self.set_tab = CPCSetTab()
        self.addTab(self.set_tab, "Set")
        # create status tab widget showing CPC values
        self.status_tab = CPCStatusTab()
        self.addTab(self.status_tab, "Status")
        # create database/ACTRIS tab for database settings and status
        self.database_tab = CPCDatabaseTab(device_parameter)
        self.addTab(self.database_tab, "ACTRIS")
        # create plot widget for Concentration
        self.plot_tab = SinglePlot(device_type=CPC)
        self.addTab(self.plot_tab, "Concentration")
        # create pulse quality widget for CPC pulse quality monitoring
        self.pulse_quality = PulseQuality()
        self.addTab(self.pulse_quality, "Pulse quality")

        # create list of widget references for updating gui with cpc system status
        self.cpc_status_widgets = [
            self.status_tab.temp_optics, self.status_tab.temp_saturator,
            self.status_tab.temp_condenser, self.status_tab.pres_inlet,
            self.status_tab.pres_nozzle, self.status_tab.laser_power,
            self.status_tab.liquid_level, self.status_tab.temp_cabin,
            self.status_tab.pres_critical_orifice, self.status_tab.pulse_quality
        ]

        # Plot configuration (composition over inheritance)
        self.plot_config = CPCPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = CPCDataWriter(self)

    def get_plot_keys(self):
        """CPC has concentration and raw concentration plots."""
        return ['', ':raw']

    def get_rolling_buffer_keys(self):
        """CPC has 24-hour rolling buffers for pulse analysis."""
        return {':pd': 86400, ':pr': 86400}

    def get_read_command_sequence(self, ten_hz=False):
        """
        CPC requires multiple sequential commands with timing delays.

        Sequence:
        1. :MEAS:ALL - Request all measurement data
        2. :SYST:PRNT (150ms delay) - Request print settings
        3. :SYST:PALL (300ms delay) - Request all system parameters
        4. :MEAS:OPC_CONC_LOG (450ms delay) - Request 10Hz data (if enabled)
        """
        sequence = [
            (':MEAS:ALL', 0),
            (':SYST:PRNT', 150),
            (':SYST:PALL', 300),
        ]
        if ten_hz:
            sequence.append((':MEAS:OPC_CONC_LOG', 450))
        return sequence

    # convert CPC status hex to binary and update error label colors
    def update_errors(self, status_hex, cabin_p_error):
        widget_amount = len(self.cpc_status_widgets) # get amount of widgets
        status_bin = bin(int(status_hex, 16)) # convert hex to int and int to binary
        status_bin = status_bin[2:].zfill(widget_amount) # remove 0b from string and fill with 0s
        total_errors = status_bin.count("1") # count number of 1s in status_bin
        inverted_status_bin = status_bin[::-1] # invert status_bin for error parsing
        for i in range(widget_amount): # iterate through all status widgets
            # change color of error label according to error bit
            self.cpc_status_widgets[i].change_color(inverted_status_bin[i])
        # update cabin pressure label color according to error status
        if cabin_p_error:
            self.status_tab.pres_cabin.change_color(1)
            total_errors += 1
        else:
            self.status_tab.pres_cabin.change_color(0)
        
        return total_errors # return total number of errors
    
    def update_settings(self, settings):
        # update GUI set values if they differ from CPC set values
        # TODO remove repetition

        # saturator temperature
        if self.set_tab.set_saturator_temp.value_spinbox.value() != settings[8]:
            # update value
            self.set_tab.set_saturator_temp.value_spinbox.setValue(settings[8])
            # if saturator temperature is nan, clear visible value
            if str(settings[8]) == 'nan':
                self.set_tab.set_saturator_temp.value_spinbox.clear()
            # if text is empty (without suffix), set text with value
            # TODO ? change this to text().split(" ")[0] == ""
            elif self.set_tab.set_saturator_temp.value_spinbox.text()[:-3] == "":
                self.set_tab.set_saturator_temp.value_spinbox.lineEdit().setText(str(settings[8]))

        # condenser temperature
        if self.set_tab.set_condenser_temp.value_spinbox.value() != settings[6]:
            # update value
            self.set_tab.set_condenser_temp.value_spinbox.setValue(settings[6])
            # if condenser temperature is nan, clear visible value
            if str(settings[6]) == 'nan':
                self.set_tab.set_condenser_temp.value_spinbox.clear()
            # if text is empty (without suffix), set text with value
            elif self.set_tab.set_condenser_temp.value_spinbox.text()[:-3] == "":
                self.set_tab.set_condenser_temp.value_spinbox.lineEdit().setText(str(settings[6]))

        # averaging time
        if self.set_tab.set_averaging_time.value_spinbox.value() != settings[5]:
            # update value
            if str(settings[5]) == 'nan': # if nan, set to 0
                self.set_tab.set_averaging_time.value_spinbox.setValue(0)
            else: # else update value
                self.set_tab.set_averaging_time.value_spinbox.setValue(settings[5])
            # if averaging time is nan, clear visible value
            if str(settings[5]) == 'nan':
                self.set_tab.set_averaging_time.value_spinbox.clear()
            # if text is empty (without suffix), update value set text with value
            elif self.set_tab.set_averaging_time.value_spinbox.text()[:-2] == "":
                self.set_tab.set_averaging_time.value_spinbox.lineEdit().setText(str(settings[5]))
        
        # update mode settings
        self.set_tab.autofill.update_state(settings[1]) # autofill
        self.set_tab.water_removal.update_state(settings[4]) # water removal
        self.set_tab.drain.update_state(settings[2]) # drain
    
    # update all data values in status tab
    def update_values(self, current_list):
        # update temperature values
        self.status_tab.temp_optics.change_value(str(current_list[5]) + " °C")
        self.status_tab.temp_saturator.change_value(str(current_list[3]) + " °C")
        self.status_tab.temp_condenser.change_value(str(current_list[4]) + " °C")
        # update pressure values
        self.status_tab.pres_inlet.change_value(str(current_list[7]) + " kPa")
        self.status_tab.pres_nozzle.change_value(str(current_list[9]) + " kPa")
        self.status_tab.pres_critical_orifice.change_value(str(current_list[8]) + " kPa")
        self.status_tab.pres_cabin.change_value(str(current_list[10]) + " kPa")
        # update misc values
        if current_list[11] == 0:
            self.status_tab.liquid_level.change_value("LOW")
        elif current_list[11] == 1:
            self.status_tab.liquid_level.change_value("OK")
        elif current_list[11] == 2:
            self.status_tab.liquid_level.change_value("OVERFILL")
        self.status_tab.temp_cabin.change_value(str(current_list[6]) + " °C")

    def get_read_command(self):
        """Get CPC read command(s)."""
        # Note: Actual command sending logic is in DeviceManager.get_dev_data()
        # This method is for documentation/future use
        return ":MEAS:ALL"

    def process_parsed_messages(self, parsed_messages, device_param, data_holder):
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
        if device_param.child('10 hz').value():
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

                # Set error flags
                if parsed.get('total_errors', 0) != 0:
                    data_holder.error_status = 1
                    data_holder.device_errors[self.dev_id] = True

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
                if device_param.child('Serial number').value() != serial_number:
                    device_param.child('Serial number').setValue(serial_number)
                    # Update CPC dict in params
                    device_param.parent().update_cpc_dict()
                if self.dev_id in data_holder.idn_inquiry_devices:
                    data_holder.idn_inquiry_devices.remove(self.dev_id)

            # Show messages in command widget if requested
            if parsed.get('show_in_command_widget', False):
                self.set_tab.command_widget.update_text_box(parsed['raw'])
                if parsed['type'] == 'error' and 'error' in parsed:
                    print("CPC error: " + str(parsed['error']))

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

    def send_read_commands(self, dev_conn, device_param):
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
        elif device_param.child('10 hz').value():
            dev_conn.send_multiple_messages(self, ten_hz=True)
        # Normal mode
        else:
            dev_conn.send_multiple_messages(self)

    def validate_10hz_mode(self, params, device_param):
        """
        Validate and synchronize CPC 10 Hz mode.

        When 10 Hz is enabled:
        - Set TAVG to 0.1 if not already
        - Validate that at least one PSM with 10 Hz is connected

        When 10 Hz is disabled:
        - Set TAVG to 1.0 if currently < 1
        """
        from config import PSM, PSM2

        dev_id = device_param.child('DevID').value()
        ten_hz_enabled = device_param.child('10 hz').value()

        if ten_hz_enabled:
            # When 10 Hz ON: Set TAVG to 0.1 if needed
            if device_param.child('Connected').value():
                if self.settings and self.settings.averaging_time != 0.1:
                    device_param.child('Connection').value().send_message(":SET:TAVG 0.1")

            # Validate PSM connection - check if any PSM has this CPC connected with 10Hz
            ten_hz_connected = any(
                psm.child('Connected CPC').value() == dev_id and psm.child('10 hz').value()
                for psm in params.child('Device settings').children()
                if psm.child('Device type').value() in [PSM, PSM2]
            )

            # If no PSM with 10Hz is connected, disable 10Hz mode
            if not ten_hz_connected:
                device_param.child('10 hz').setValue(False)
        else:
            # When 10 Hz OFF: Set TAVG to 1.0 if currently < 1
            if device_param.child('Connected').value():
                if self.settings and self.settings.averaging_time < 1:
                    device_param.child('Connection').value().send_message(":SET:TAVG 1")

# set tab widget containing settings and message input
# used in CPCWidget
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


class CPCDatabaseTab(QWidget):
    """Database/ACTRIS tab for CPC devices showing database status and settings."""

    def __init__(self, device_param, *args, **kwargs):
        super().__init__()

        self.device_param = device_param

        layout = QGridLayout()

        row = 0

        # Connection section (global, shared across all CPCs)
        connection_label = QLabel("<b>Database Connection (shared)</b>")
        layout.addWidget(connection_label, row, 0, 1, 2)
        row += 1

        # Connection string input
        conn_string_label = QLabel("Connection string:")
        layout.addWidget(conn_string_label, row, 0)
        self.connection_string_input = QLineEdit()
        self.connection_string_input.setPlaceholderText("postgresql://user:password@host:port/database")
        self.connection_string_input.textChanged.connect(self.connection_string_changed)
        layout.addWidget(self.connection_string_input, row, 1)
        row += 1

        # Test connection button
        self.test_connection_btn = QPushButton("Test Connection + Refresh Preview")
        self.test_connection_btn.clicked.connect(self.test_connection_clicked)
        layout.addWidget(self.test_connection_btn, row, 0, 1, 2)
        row += 1

        # Global connection status
        global_status_label = QLabel("Global status:")
        layout.addWidget(global_status_label, row, 0)
        self.global_connection_status = QLabel("Disconnected")
        self.global_connection_status.setStyleSheet("color: gray;")
        layout.addWidget(self.global_connection_status, row, 1)
        row += 1

        # Active devices count
        active_devices_label = QLabel("Active devices:")
        layout.addWidget(active_devices_label, row, 0)
        self.active_devices_count = QLabel("0 CPCs using database")
        layout.addWidget(self.active_devices_count, row, 1)
        row += 1

        # Separator
        row += 1

        # Device Settings section
        settings_label = QLabel("<b>This Device Settings</b>")
        layout.addWidget(settings_label, row, 0, 1, 2)
        row += 1

        # Database enabled checkbox (connected to device parameter)
        self.db_enabled_checkbox = QCheckBox("Enable database for this device")
        self.db_enabled_checkbox.stateChanged.connect(self.db_enabled_changed)
        layout.addWidget(self.db_enabled_checkbox, row, 0, 1, 2)
        row += 1

        # Linked RHTP dropdown (with guidance when disabled)
        linked_rhtp_label = QLabel("Linked RHTP device:")
        layout.addWidget(linked_rhtp_label, row, 0)
        self.linked_rhtp_dropdown = GuidedComboBox()
        self.linked_rhtp_dropdown.set_tooltips(
            enabled_tooltip="Select the RHTP sensor to link with this CPC for database recording",
            disabled_tooltip="Disable database first to change linked RHTP device"
        )
        # Guide target will be set after checkbox is created
        self.linked_rhtp_dropdown.currentIndexChanged.connect(self.linked_rhtp_changed)
        layout.addWidget(self.linked_rhtp_dropdown, row, 1)
        row += 1

        # Averaging interval dropdown (with guidance when disabled)
        interval_label = QLabel("Averaging interval:")
        layout.addWidget(interval_label, row, 0)
        self.interval_dropdown = GuidedComboBox()
        self.interval_dropdown.addItems(['1 minute', '5 minutes', '10 minutes', '15 minutes', '1 hour', '3 hours'])
        self.interval_dropdown.set_tooltips(
            enabled_tooltip="Select the time period for data averaging",
            disabled_tooltip="Disable database first to change averaging interval"
        )
        # Guide target will be set after checkbox is created
        self.interval_dropdown.currentTextChanged.connect(self.interval_changed)
        layout.addWidget(self.interval_dropdown, row, 1)
        row += 1

        # Separator
        row += 1

        # Status section
        status_label = QLabel("<b>This Device Status</b>")
        layout.addWidget(status_label, row, 0, 1, 2)
        row += 1

        # Database status indicator
        db_status_label = QLabel("Status:")
        layout.addWidget(db_status_label, row, 0)
        self.db_status_value = QLabel("Disabled")
        layout.addWidget(self.db_status_value, row, 1)
        row += 1

        # Last write timestamp
        last_write_label = QLabel("Last write:")
        layout.addWidget(last_write_label, row, 0)
        self.last_write_value = QLabel("Never")
        layout.addWidget(self.last_write_value, row, 1)
        row += 1

        # Records written counter
        records_label = QLabel("Records written:")
        layout.addWidget(records_label, row, 0)
        self.records_value = QLabel("0")
        layout.addWidget(self.records_value, row, 1)
        row += 1

        # Current interval progress
        progress_label = QLabel("Current interval:")
        layout.addWidget(progress_label, row, 0)
        self.progress_value = QLabel("No data")
        self.progress_value.setStyleSheet("color: gray;")
        layout.addWidget(self.progress_value, row, 1)
        row += 1

        # Next write countdown
        next_write_label = QLabel("Next write in:")
        layout.addWidget(next_write_label, row, 0)
        self.next_write_value = QLabel("-")
        self.next_write_value.setStyleSheet("color: gray;")
        layout.addWidget(self.next_write_value, row, 1)
        row += 1

        # Latest saved data table
        data_table_label = QLabel("<b>Latest Saved Data</b>")
        layout.addWidget(data_table_label, row, 0, 1, 2)
        row += 1

        self.data_table = QTableWidget()
        self.data_table.setColumnCount(12)
        self.data_table.setHorizontalHeaderLabels([
            "Start", "End", "Conc", "Flow In", "T Sat", "T Cond",
            "T Inlet", "P Inlet", "RH In", "Pulse", "Err", "Status"
        ])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.data_table.setRowCount(10)
        self.data_table.setMaximumHeight(300)
        # Enable row selection for deletion
        self.data_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.data_table.setSelectionMode(QTableWidget.MultiSelection)
        # Connect cell changed signal for editing
        self.data_table.cellChanged.connect(self.cell_edited)
        layout.addWidget(self.data_table, row, 0, 1, 2)
        row += 1

        # Delete button for selected rows
        self.delete_button = QPushButton("Delete Selected Rows")
        self.delete_button.clicked.connect(self.delete_selected_rows)
        layout.addWidget(self.delete_button, row, 0, 1, 2)
        row += 1

        # Store original row data for tracking changes
        self.row_data = {}  # {row_index: {'time': ..., 'instr_id': ..., 'data': {...}}}
        self.editing_in_progress = False  # Flag to prevent recursive cell updates

        # Error/info section
        error_label = QLabel("<b>Messages</b>")
        layout.addWidget(error_label, row, 0, 1, 2)
        row += 1

        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setMaximumHeight(100)
        layout.addWidget(self.error_text, row, 0, 1, 2)
        row += 1

        # Set row stretches (data table and error text)
        data_table_row = row - 2
        error_text_row = row - 1
        layout.setRowStretch(data_table_row, 2)  # Data table gets more space
        layout.setRowStretch(error_text_row, 1)  # Error text gets some space

        self.setLayout(layout)

        # Get reference to main window for accessing database_manager
        # Will be set when tab is added to device
        self.main_window = None

        # Set up guidance targets for dropdowns (point to checkbox when clicked while disabled)
        self.linked_rhtp_dropdown.set_guide_target(
            self.db_enabled_checkbox,
            "Uncheck 'Enable database' to change linked RHTP device"
        )
        self.interval_dropdown.set_guide_target(
            self.db_enabled_checkbox,
            "Uncheck 'Enable database' to change averaging interval"
        )

        # Timer for periodic refresh (every 5 seconds)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_status)
        self.refresh_timer.start(5000)  # 5 seconds

        # Initialize dropdowns with current values
        self.populate_rhtp_dropdown()
        self.refresh_status()  # Populate other fields and sync to parameters

    def populate_rhtp_dropdown(self):
        """Populate linked RHTP dropdown from rhtp_dict in device settings."""
        device_settings = self.device_param.parent()
        if not hasattr(device_settings, 'rhtp_dict'):
            return

        # Store current selection (handle case where parameter doesn't exist yet)
        current_rhtp_id = None
        try:
            linked_rhtp_param = self.device_param.child('Linked RHTP')
            if linked_rhtp_param is not None:
                current_rhtp_id = linked_rhtp_param.value()
        except KeyError:
            # Parameter doesn't exist yet (during initialization)
            pass

        # Clear and rebuild dropdown
        self.linked_rhtp_dropdown.blockSignals(True)
        self.linked_rhtp_dropdown.clear()

        # Add RHTP devices from rhtp_dict
        for rhtp_name, rhtp_id in device_settings.rhtp_dict.items():
            self.linked_rhtp_dropdown.addItem(rhtp_name, rhtp_id)

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

        # Update linked RHTP dropdown
        try:
            linked_rhtp_param = self.device_param.child('Linked RHTP')
            if linked_rhtp_param is not None:
                rhtp_id = linked_rhtp_param.value()
                # Find index in dropdown that matches this ID
                index = self.linked_rhtp_dropdown.findData(rhtp_id)
                if index >= 0:
                    self.linked_rhtp_dropdown.blockSignals(True)
                    self.linked_rhtp_dropdown.setCurrentIndex(index)
                    self.linked_rhtp_dropdown.blockSignals(False)
        except KeyError:
            pass  # Parameter doesn't exist yet

        # Update averaging interval dropdown
        try:
            interval_param = self.device_param.child('DB averaging interval')
            if interval_param is not None:
                interval = interval_param.value()
                index = self.interval_dropdown.findText(interval)
                if index >= 0:
                    self.interval_dropdown.blockSignals(True)
                    self.interval_dropdown.setCurrentIndex(index)
                    self.interval_dropdown.blockSignals(False)
        except KeyError:
            pass  # Parameter doesn't exist yet

        # Update database enabled status
        try:
            db_enabled_param = self.device_param.child('Database enabled')
            if db_enabled_param is not None:
                enabled = db_enabled_param.value()
                self.db_enabled_checkbox.setChecked(enabled)

                # Disable dropdowns when database is active (prevent changing settings during recording)
                self.linked_rhtp_dropdown.setEnabled(not enabled)
                self.interval_dropdown.setEnabled(not enabled)

                if enabled:
                    self.db_status_value.setText("Enabled")
                    self.db_status_value.setStyleSheet("color: green;")
                else:
                    self.db_status_value.setText("Disabled")
                    self.db_status_value.setStyleSheet("color: gray;")
        except KeyError:
            pass  # Parameter doesn't exist yet

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
        self.progress_value.setStyleSheet("color: green;" if samples_collected > 0 else "color: gray;")

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
                self.next_write_value.setStyleSheet("color: orange;")
            else:
                self.next_write_value.setText("Writing...")
                self.next_write_value.setStyleSheet("color: green;")
        else:
            self.next_write_value.setText("-")
            self.next_write_value.setStyleSheet("color: gray;")

    def reset_progress(self):
        """Reset progress indicators."""
        self.progress_value.setText("No data")
        self.progress_value.setStyleSheet("color: gray;")
        self.next_write_value.setText("-")
        self.next_write_value.setStyleSheet("color: gray;")

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
                'instr_id': row.get('instr_id', self.device_param.child('Serial number').value()),
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
            # Refresh table to show updated data
            dev_id = self.device_param.child('DevID').value()
            latest_rows = self.main_window.database_manager.get_latest_rows(10, dev_id)
            self.update_data_table(latest_rows)
            # Clear row selection after deletion
            self.data_table.clearSelection()
        else:
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - {message}")

    def linked_rhtp_changed(self, index):
        """Handle linked RHTP dropdown selection change."""
        # Get the selected RHTP device ID from the dropdown
        rhtp_id = self.linked_rhtp_dropdown.currentData()

        # Update the hidden parameter
        try:
            linked_rhtp_param = self.device_param.child('Linked RHTP')
            if linked_rhtp_param is not None:
                linked_rhtp_param.setValue(rhtp_id)
        except KeyError:
            pass  # Parameter doesn't exist yet

    def interval_changed(self, text):
        """Handle averaging interval dropdown selection change."""
        from datetime import datetime

        # Update the hidden parameter
        try:
            interval_param = self.device_param.child('DB averaging interval')
            if interval_param is not None:
                interval_param.setValue(text)
        except KeyError:
            pass  # Parameter doesn't exist yet

        # If database is enabled, recreate the averager with new interval
        if self.main_window and hasattr(self.main_window, 'database_manager'):
            db_enabled_param = self.device_param.child('Database enabled')
            if db_enabled_param and db_enabled_param.value():
                dev_id = self.device_param.child('DevID').value()

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

    def db_enabled_changed(self, state):
        """Handle database enabled checkbox state change with full validation and connection management."""
        from PyQt5.QtWidgets import QMessageBox
        from datetime import datetime

        enabled = state == Qt.Checked

        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - Database manager not available")
            self.db_enabled_checkbox.setChecked(False)
            return

        dev_id = self.device_param.child('DevID').value()

        if enabled:
            # Validation 1: Check connection string is not empty
            conn_string = self.connection_string_input.text().strip()
            if not conn_string:
                QMessageBox.warning(self, "Database Error", "Please enter a connection string first.")
                self.db_enabled_checkbox.setChecked(False)
                self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - No connection string provided")
                return

            # Validation 2: Check RHTP is linked (use dropdown value)
            rhtp_id = self.linked_rhtp_dropdown.currentData()
            if rhtp_id is None or rhtp_id == 'None':
                QMessageBox.warning(
                    self,
                    "Database Error",
                    "Please link an RHTP device first.\n\nSelect an RHTP device in the 'Linked RHTP' dropdown above."
                )
                self.db_enabled_checkbox.setChecked(False)
                self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Error - No RHTP device linked")
                return

            # Validation 3: Check RHTP device exists and is connected
            rhtp_widget = self.main_window.data_holder.device_widgets.get(rhtp_id)
            if not rhtp_widget:
                QMessageBox.warning(self, "Database Error", "Linked RHTP device not found.")
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

                # Update device parameter
                self.device_param.child('Database enabled').setValue(True)

                # Update UI
                self.db_status_value.setText("Enabled")
                self.db_status_value.setStyleSheet("color: green;")
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

            # Update device parameter
            self.device_param.child('Database enabled').setValue(False)

            # Update UI
            self.db_status_value.setText("Disabled")
            self.db_status_value.setStyleSheet("color: gray;")
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

    def test_connection_clicked(self):
        """Test database connection with current connection string."""
        from PyQt5.QtWidgets import QMessageBox

        conn_string = self.connection_string_input.text()

        if not conn_string:
            QMessageBox.warning(self, "Database Test", "Please enter a connection string first.")
            return

        if not self.main_window or not hasattr(self.main_window, 'database_manager'):
            QMessageBox.warning(self, "Database Test", "Database manager not available.")
            return

        success, message = self.main_window.database_manager.test_connection(conn_string)

        if success:
            QMessageBox.information(self, "Database Test", f"Success!\n\n{message}")

            # Refresh the preview table to show latest data
            dev_id = self.device_param.child('DevID').value()
            latest_rows = self.main_window.database_manager.get_latest_rows(10, dev_id)
            self.update_data_table(latest_rows)
            from datetime import datetime
            self.add_message(f"{datetime.now().strftime('%H:%M:%S')}: Preview table refreshed")
        else:
            QMessageBox.warning(self, "Database Test", f"Connection failed:\n\n{message}")

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
