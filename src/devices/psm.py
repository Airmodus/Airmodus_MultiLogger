from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QSplitter, QTabWidget, QGridLayout, QWidget,
    QSizePolicy)


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
from utils import compile_psm_data, compile_psm_settings

# PSM widget
class PSMWidget(ComplexDevice):
    def __init__(self, device_parameter, device_type, *args, **kwargs):
        super().__init__(device_parameter, device_type=device_type, *args, **kwargs)
        self.device_type = device_type # store device type (PSM or PSM 2.0)
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
                    firmware_version_str = self.device_parameter.child('Firmware version').value()
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

                # Compile PSM data
                compiled_data = compile_psm_data(data, status_hex, note_hex, scan_status, psm_version=self.device_type)
                self.latest_data = compiled_data

                # Update GUI
                self.update_values(data)
                self.measure_tab.change_mode_color(command)

                has_errors = (total_errors + liquid_errors) > 0

                return {
                    'type': 'data',
                    'command': command,
                    'data': compiled_data,
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
            except:
                pass

            return {
                'type': 'error',
                'command': 'unknown',
                'data': None,
                'error': str(e),
                'raw': message,
                'update_gui': False
            }


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
