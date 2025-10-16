from PyQt5.QtGui import QPalette, QIntValidator, QDoubleValidator, QFont
from PyQt5.QtCore import Qt, pyqtSignal, QLocale, QTimer
from PyQt5.QtWidgets import (QLabel, QWidget, QVBoxLayout, QLineEdit, QPushButton,
                             QSpinBox, QDoubleSpinBox, QTextEdit, QGridLayout,
                             QMessageBox, QSizePolicy, QSplitter)

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
        

# widget showing measurement and saving status
# displayed under parameter tree
class StatusLights(QSplitter):
    def __init__(self, *args, **kwargs):
        super().__init__()
        font = self.font() # get current global font
        font.setPointSize(20) # set font size
        # create OK light widget
        self.error_light = QLabel(objectName="label")
        self.error_light.setFont(font) # apply font to label
        self.error_light.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter) # align text in center
        self.error_light.setAutoFillBackground(True) # automatically fill the background with color
        self.addWidget(self.error_light) # add widget to splitter
        # create saving light widget
        self.saving_light = QLabel(objectName="label")
        self.saving_light.setFont(font) # apply font to label
        self.saving_light.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.saving_light.setAutoFillBackground(True)
        self.addWidget(self.saving_light)
        # set relative sizes of widgets in splitter
        self.setSizes([100, 100])

    # set the color and text of ok light according to error flag, 1 = errors, 0 = no errors
    def set_error_light(self, flag):
        if flag == 1:
            self.error_light.setStyleSheet("QLabel { background-color : red }")
            self.error_light.setText("Error")
        else:
            self.error_light.setStyleSheet("QLabel { background-color : green }")
            self.error_light.setText("OK")
    # set the color and text of saving light, 1 = saving, 0 = saving off
    def set_saving_light(self, flag):
        if flag == 1:
            self.saving_light.setStyleSheet("QLabel { background-color : green }")
            self.saving_light.setText("Saving")
        else:
            self.saving_light.setStyleSheet("QLabel { background-color : red }")
            self.saving_light.setText("Saving off")

# used in PSMMeasureTab
class StepsWidget(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        layout = QVBoxLayout()
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        label = QLabel("Steps (lpm)", objectName="label")
        label.setFont(font)
        label.setAlignment(Qt.AlignCenter) # center label
        self.text_box = FloatTextEdit(objectName="text_edit")
        self.default_color = self.text_box.palette().color(QPalette.Text) # get default text color
        self.text_box.setFont(font)
        # add widgets to layout
        layout.addWidget(label)
        layout.addWidget(self.text_box)
        self.setLayout(layout)

# used in StepsWidget
class FloatTextEdit(QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # override keyPressEvent to only allow certain keys
        self.allowed_keys = [Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, 
                        Qt.Key_Home, Qt.Key_End, Qt.Key_Period, Qt.Key_Return, Qt.Key_Enter,
                        Qt.Key_0, Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5, Qt.Key_6,
                        Qt.Key_7, Qt.Key_8, Qt.Key_9]
    def keyPressEvent(self, event):
        if event.key() in self.allowed_keys:
            super().keyPressEvent(event)

# used in CPCSetTab and PSMSetTab
class CommandWidget(QWidget):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()
        layout = QVBoxLayout()
        label = QLabel("Send serial command message to " + device_type, objectName="label")
        self.command_input = QLineEdit(objectName="line_edit")
        self.command_input.setPlaceholderText("Enter command")
        self.text_box = QTextEdit(readOnly=True, objectName="text_edit")
        # add widgets to layout
        layout.addWidget(label)
        layout.addWidget(self.command_input)
        layout.addWidget(self.text_box)
        self.setLayout(layout)

    def update_text_box(self, text):
        time_stamp = dt.now().strftime("%d.%m.%Y %H:%M:%S - ") # get time stamp
        self.text_box.append(time_stamp + text) # append text box with time stamp and text
    
    def disable_command_input(self):
        self.command_input.setReadOnly(True)
        self.command_input.setPlaceholderText("Command input disabled")
    
    def enable_command_input(self):
        self.command_input.setReadOnly(False)
        self.command_input.setPlaceholderText("Enter command")


# status indicator widget
# used in CPCStatusTab and PSMStatusTab
class IndicatorWidget(QWidget):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        layout = QVBoxLayout() # create widget layout
        self.name = name # save name
        self.ok_error_indicators = ["Laser power", "Saturator liquid level", "Drain liquid level", "Pulse quality"]
        self.value_label = QLabel(self.name + "\n", objectName="label") # create value label

        self.default_color = self.value_label.styleSheet() # save default color

        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        self.value_label.setFont(font) # apply font to value label
        self.value_label.setAlignment(Qt.AlignCenter) # center label

        layout.addWidget(self.value_label) # add value label to layout
        self.setLayout(layout) # apply layout
    # change indicator value, called by main window's update_values function
    def change_value(self, value):
        self.value_label.setText(self.name + "\n" + value)
    # change background color of value, called by main window's update_errors function
    def change_color(self, bit):
        if int(bit) == 1: # if bit is 1 (error), set background color to red
            self.value_label.setStyleSheet("QLabel { background-color : red }")
            if self.name == "Laser power":
                self.change_value("ERROR")
            elif self.name == "Saturator liquid level":
                self.change_value("LOW")
            elif self.name == "Drain liquid level":
                self.change_value("HIGH")
            elif self.name == "Pulse quality":
                self.change_value("ERROR")
        else: # if bit is 0 (no error), set background color to normal
            self.value_label.setStyleSheet(self.default_color)
            if self.name in self.ok_error_indicators:
                self.change_value("OK")

class ToggleButton(QPushButton):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        self.name = name
        self.state = 0
        # create specific command messages for drying toggle
        if self.name == "Drying":
            self.messages = {0: ":SET:RUN", 1: ":SET:DRY"}
        self.setObjectName("button_widget")
        self.setCheckable(True)
        self.clicked.connect(self.toggle)
        self.setText(self.name)
        self.stylesheet = self.styleSheet() # save default stylesheet
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        self.setFont(font) # apply font
        # set size policy to expanding
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toggle() # toggle button to set initial state
    
    def toggle(self):
        if self.isChecked(): # if button is checked
            self.setText(self.name + "\nON")
            self.setStyleSheet("QPushButton { background-color : green }")
            self.state = 1
        else: # if button is not checked
            self.setText(self.name + "\nOFF")
            self.setStyleSheet(self.stylesheet)
            self.state = 0

    def update_state(self, state):
        # if received state is different from current state
        if state != self.state:
            if str(state) == 'nan': # if state is nan
                return # do nothing
            self.setChecked(int(state)) # set button checked state
            self.toggle() # toggle button

class StartButton(QPushButton):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        self.name = name
        self.state = 0
        self.setObjectName("button_widget")
        self.setText(self.name)
        self.stylesheet = self.styleSheet() # save default stylesheet
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        self.setFont(font) # apply font
        # set size policy to expanding
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    
    def change_color(self, state):
        if state != self.state:
            if state == 1: # if this measure mode is on
                self.setStyleSheet("QPushButton { background-color : green }")
                self.state = 1
            else: # if this measure mode is off
                self.setStyleSheet(self.stylesheet)
                self.state = 0

# custom spin box class with signal for value change
# https://stackoverflow.com/questions/47874952/qspinbox-signal-for-arrow-buttons
class SpinBox(QSpinBox):
    stepChanged = pyqtSignal(int)
    # override stepBy function to emit signal when value changes
    def stepBy(self, step):
        value = self.value() # store cur value before change
        super(SpinBox, self).stepBy(step) # call parent to perform the change still
        if self.value() != value: # check if val actually changed
            self.stepChanged.emit(self.value()) # emit custom signal

class DoubleSpinBox(QDoubleSpinBox):
    stepChanged = pyqtSignal(float)
    # override stepBy function to emit signal when value changes
    def stepBy(self, step):
        value = self.value() # store cur value before change
        super(DoubleSpinBox, self).stepBy(step) # call parents implementation to perform the change still
        if self.value() != value: # check if value actually changed
            self.stepChanged.emit(self.value()) # emit custom signal

# used in CPCSetTab and PSMSetTab
class SetWidget(QWidget):
    def __init__(self, name, suffix, *args, integer=False, **kwargs):
        super().__init__()
        layout = QVBoxLayout()
        font = self.font() # get current global font
        font.setPointSize(16) # set font size
        # create label for widget name
        self.name = name
        name_label = QLabel(self.name, objectName="label")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setFont(font) # apply font to label
        layout.addWidget(name_label)
        # create normal / double spin box for setting value
        self.is_integer = integer
        if integer: # if value is integer, use spin box (int)
            self.value_spinbox = SpinBox(objectName="spin_box", maximum=9999)
            validator = QIntValidator() # create int validator
        else: # if not integer, use double spin box (float)
            if "decimals" in kwargs: # if decimals are specified in kwargs
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999, decimals=kwargs["decimals"])
            else:
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999)
            locale = QLocale(QLocale.C) # create locale to use dot as decimal separator
            validator = QDoubleValidator() # create double validator 
            validator.setLocale(locale) # set validator locale
            self.value_spinbox.setLocale(locale) # set spinbox locale
        self.value_spinbox.setSuffix(suffix) # set suffix
        self.value_spinbox.lineEdit().setReadOnly(True) # make line edit read only
        self.value_spinbox.lineEdit().setAlignment(Qt.AlignCenter) # align text in line edit
        layout.addWidget(self.value_spinbox) # add widget to layout
        # add line edit for value input
        self.value_input = QLineEdit(objectName="line_edit")
        self.value_input.setPlaceholderText("Enter value")
        self.value_input.setValidator(validator) # set validator, only allow int or float
        self.value_input.returnPressed.connect(self.value_input_return_pressed)
        layout.addWidget(self.value_input)
        # set layout
        self.setLayout(layout)
        # store default stylesheet
        self.stylesheet = self.styleSheet()
        # create error variable for storing error state
        self.error = False
    # function that handles value text input
    def value_input_return_pressed(self):
        value = self.value_input.text()
        try:
            if self.is_integer:
                self.value_spinbox.setValue(int(value))
            else:
                self.value_spinbox.setValue(float(value))
        except Exception as e:
            print(e)
        QTimer.singleShot(50, self.clear_input)
    # function that clears value input line edit after single shot timer
    def clear_input(self):
        self.value_input.clear()
    def set_red_color(self):
        if self.error == False:
            self.value_spinbox.setStyleSheet("QDoubleSpinBox { background-color : red }")
            self.error = True
    def set_default_color(self):
        if self.error == True:
            self.value_spinbox.setStyleSheet(self.stylesheet)
            self.error = False

__all__ = [
    'SetWidget', 'SpinBox', 'DoubleSpinBox', 'ToggleButton', 'StartButton', 'IndicatorWidget',
    'CommandWidget', 'FloatTextEdit', 'StepsWidget', 'PulseQuality'
]
