from PyQt5.QtGui import QPalette, QColor, QIntValidator, QDoubleValidator, QFont, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QLocale
from PyQt5.QtWidgets import (QTabWidget, QGridLayout, QLabel, QWidget,
    QPushButton, QComboBox, QGraphicsRectItem)

from widgets import (
    CommandWidget,
    SetWidget,
    ToggleButton,
    IndicatorWidget,
)
from plots.device_plots import SinglePlot

# CPC widget containing CPC related GUI elements as tabs
class CPCWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create set tab widget for cpc settings
        self.set_tab = CPCSetTab()
        self.addTab(self.set_tab, "Set")
        # create status tab widget showing CPC values
        self.status_tab = CPCStatusTab()
        self.addTab(self.status_tab, "Status")
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
        

__all__ = ['CPCWidget']
