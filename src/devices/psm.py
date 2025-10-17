from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QSplitter, QTabWidget, QGridLayout, QWidget,
    QSizePolicy)

from config import PSM, PSM2
from widgets import (
    CommandWidget,
    SetWidget,
    ToggleButton,
    IndicatorWidget,
    StartButton,
)

from plots.device_plots import SinglePlot

# PSM widget
class PSMWidget(QTabWidget):
    def __init__(self, device_parameter, device_type, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
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
