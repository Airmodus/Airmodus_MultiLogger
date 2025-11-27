from PyQt5.QtGui import QPalette, QIntValidator, QDoubleValidator
from PyQt5.QtCore import Qt, pyqtSignal, QLocale, QTimer, QSize
from PyQt5.QtWidgets import (QLabel, QWidget, QVBoxLayout, QLineEdit, QPushButton,
                             QSpinBox, QDoubleSpinBox, QTextEdit, QHBoxLayout,
                             QSizePolicy, QSplitter, QTabBar, QStyleFactory, QApplication)
from datetime import datetime as dt
import sys


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
        self.command_input.setToolTip("Enter a serial command and press Enter to send")
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
        self.command_input.setToolTip("Device not connected. Select a COM port in the device settings (left panel) to connect and enable command input")
        self.command_input.setStyleSheet("QLineEdit { background-color: #FFE6E6; }")  # Light red background

    def enable_command_input(self):
        self.command_input.setReadOnly(False)
        self.command_input.setPlaceholderText("Enter command")
        self.command_input.setToolTip("Enter a serial command and press Enter to send")
        self.command_input.setStyleSheet("")  # Clear style


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

class TabConfirmationPopup(QWidget):
    """
    Inline confirmation popup that appears below a tab.

    Auto-closes when clicking outside (Qt.Popup behavior).
    Emits confirmed signal if user clicks Confirm button.
    """
    confirmed = pyqtSignal()

    def __init__(self, tab_name, parent=None):
        super().__init__(parent)

        # Set window flags for popup behavior
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Confirm button
        self.confirm_btn = QPushButton("✓ Confirm")
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-weight: bold;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #c9302c;
            }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(self.confirm_btn)

        # Cancel button
        self.cancel_btn = QPushButton("✗ Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #5bc0de;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #46b8da;
            }
        """)
        self.cancel_btn.clicked.connect(self.close)
        layout.addWidget(self.cancel_btn)

        # Set overall widget style
        self.setStyleSheet("""
            QWidget {
                background-color: white;
                border: 2px solid #ccc;
                border-radius: 4px;
            }
        """)

        # Set fixed size (smaller now without label)
        self.setFixedSize(200, 40)

    def _on_confirm(self):
        """Handle confirm button click - emit signal and close."""
        self.confirmed.emit()
        self.close()

    def show_below_tab(self, tab_bar, tab_index):
        """
        Show the popup positioned directly below the X button on the right side of the tab.

        Args:
            tab_bar: QTabBar instance
            tab_index: Index of the tab to position below
        """
        from PyQt5.QtWidgets import QTabBar, QApplication
        from PyQt5.QtCore import QPoint

        # Get the close button for positioning
        close_button = tab_bar.tabButton(tab_index, QTabBar.RightSide)

        # Try multiple positioning strategies in order of preference
        if close_button and close_button.isVisible():
            # Strategy 1: Position relative to close button using geometry
            button_geometry = close_button.geometry()
            button_global_pos = close_button.parentWidget().mapToGlobal(button_geometry.topLeft())

            popup_x = button_global_pos.x() + button_geometry.width() - self.width()
            popup_y = button_global_pos.y() + button_geometry.height() + 2
        else:
            # Strategy 2: Use tab rectangle
            tab_rect = tab_bar.tabRect(tab_index)

            if not tab_rect.isNull() and not tab_rect.isEmpty():
                global_pos = tab_bar.mapToGlobal(tab_rect.bottomRight())
                popup_x = global_pos.x() - self.width()
                popup_y = global_pos.y() + 2
            else:
                # Strategy 3: Fallback to safe position below tab bar center
                tab_bar_global = tab_bar.mapToGlobal(QPoint(0, 0))
                popup_x = tab_bar_global.x() + (tab_bar.width() // 2) - (self.width() // 2)
                popup_y = tab_bar_global.y() + tab_bar.height() + 5

        # Ensure popup is within screen bounds
        screen = QApplication.desktop().screenGeometry()
        popup_x = max(0, min(popup_x, screen.width() - self.width()))
        popup_y = max(0, min(popup_y, screen.height() - self.height()))

        self.move(popup_x, popup_y)
        self.show()
        self.raise_()  # Bring to front
        self.activateWindow()  # Ensure popup gets focus


class BrowserStyleTabBar(QTabBar):
    """Custom tab bar with fixed-width tabs and horizontal scrolling.

    Features:
    - Fixed width tabs (150-200px range based on text length)
    - Horizontal scrolling with arrow buttons when tabs overflow
    - Mouse wheel/touchpad scrolling support
    - macOS compatibility (forces Fusion style for scroll buttons)
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Enable scrolling behavior
        self.setExpanding(False)  # Don't stretch tabs to fill width
        self.setUsesScrollButtons(True)  # Show left/right arrow buttons
        self.setMovable(False)  # Disable drag-and-drop reordering
        self.setElideMode(Qt.ElideRight)  # Truncate long text with "..."

        # Fix for macOS - force Fusion style to show scroll buttons
        # macOS native style doesn't show scroll buttons by default
        if sys.platform == 'darwin':
            self.setStyle(QStyleFactory.create('Fusion'))

    def tabSizeHint(self, index):
        """Return flexible width for tabs (150-200px based on text length)."""
        size = QTabBar.tabSizeHint(self, index)

        # Constrain width between 150px and 200px
        # This allows shorter tab names to use less space
        # while preventing very long names from making tabs too wide
        width = max(150, min(size.width(), 200))

        return QSize(width, size.height())

    def wheelEvent(self, event):
        """Enable mouse wheel/touchpad to scroll through tabs horizontally.

        Changes the active tab, which automatically scrolls it into view.
        """
        delta = event.angleDelta().y()
        current = self.currentIndex()

        if delta > 0 and current > 0:
            # Scroll left (go to previous tab)
            self.setCurrentIndex(current - 1)
        elif delta < 0 and current < self.count() - 1:
            # Scroll right (go to next tab)
            self.setCurrentIndex(current + 1)

        event.accept()


__all__ = [
    'SetWidget', 'SpinBox', 'DoubleSpinBox', 'ToggleButton', 'StartButton', 'IndicatorWidget',
    'CommandWidget', 'FloatTextEdit', 'StepsWidget', 'TabConfirmationPopup', 'BrowserStyleTabBar'
]
