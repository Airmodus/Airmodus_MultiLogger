from PyQt5.QtGui import QPalette, QIntValidator, QDoubleValidator, QCursor, QPainter, QColor, QPen, QBrush
from PyQt5.QtCore import Qt, pyqtSignal, QLocale, QTimer, QSize, QRectF, QPropertyAnimation, pyqtProperty, QEasingCurve, QEvent
from PyQt5.QtWidgets import (QLabel, QWidget, QVBoxLayout, QLineEdit, QPushButton,
                             QSpinBox, QDoubleSpinBox, QTextEdit, QHBoxLayout,
                             QSizePolicy, QSplitter, QTabBar, QStyleFactory, QApplication,
                             QToolButton, QScrollArea, QFrame, QToolTip)
from datetime import datetime as dt
import sys
import logging

from tab_link_overlay import TabLinkOverlay


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


# Status indicator color styles
STATUS_GREEN = "background-color: #27ae60; border-radius: 3px;"
STATUS_YELLOW = "background-color: #f39c12; border-radius: 3px;"
STATUS_RED = "background-color: #e74c3c; border-radius: 3px;"
STATUS_GRAY = "background-color: #555; border-radius: 3px;"


# Frame styles for different states
FRAME_NORMAL = "QFrame { border: 1px solid #555; border-radius: 4px; background: #2d2d2d; }"
FRAME_ERROR = "QFrame { border: 2px solid #e74c3c; border-radius: 4px; background: rgba(231, 76, 60, 0.15); }"
FRAME_WARNING = "QFrame { border: 2px solid #f39c12; border-radius: 4px; background: rgba(243, 156, 18, 0.1); }"


# status indicator widget
# used in CPCStatusTab and PSMStatusTab
class IndicatorWidget(QFrame):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        # Add subtle border to separate items
        self.setFrameStyle(QFrame.StyledPanel)
        self._frame_normal = FRAME_NORMAL
        self._frame_error = FRAME_ERROR
        self.setStyleSheet(self._frame_normal)

        layout = QHBoxLayout()  # Horizontal layout for status indicator + content
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.name = name
        self.ok_error_indicators = ["Laser power", "Saturator liquid level", "Drain liquid level", "Pulse quality"]

        # Status indicator (colored dot on left side)
        self._status_indicator = QFrame()
        self._status_indicator.setFixedSize(6, 40)
        self._status_indicator.setStyleSheet(STATUS_GRAY)
        layout.addWidget(self._status_indicator)

        # Content area (vertical: name on top, value below)
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(2)

        # Name label (smaller, gray)
        self.name_label = QLabel(self.name)
        name_font = self.font()
        name_font.setPointSize(11)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet("QLabel { color: #888; background: transparent; border: none; }")
        self.name_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.name_label)

        # Value label (larger, bold)
        self.value_label = QLabel("--")
        self.default_color = "QLabel { color: #ddd; background-color: transparent; border: none; }"
        self.value_label.setStyleSheet(self.default_color)
        value_font = self.font()
        value_font.setPointSize(18)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        content_layout.addWidget(self.value_label)

        layout.addLayout(content_layout, 1)
        self.setLayout(layout)

        # Track tooltip visibility for persistence during updates
        self._tooltip_visible = False
        self._tooltip_pos = None

        # Track error state for status indicator
        self._has_error = False

        # Install event filter on name_label to track tooltip
        self.name_label.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Track tooltip show/hide on name_label."""
        if obj == self.name_label:
            if event.type() == QEvent.ToolTip:
                self._tooltip_visible = True
                self._tooltip_pos = event.globalPos()
            elif event.type() == QEvent.Leave:
                self._tooltip_visible = False
                self._tooltip_pos = None
        return super().eventFilter(obj, event)

    def _restore_tooltip(self):
        """Restore tooltip if it was visible before update."""
        if self._tooltip_visible and self._tooltip_pos and self.name_label.toolTip():
            QToolTip.showText(self._tooltip_pos, self.name_label.toolTip(), self.name_label)

    # change indicator value, called by main window's update_values function
    def change_value(self, value):
        self.value_label.setText(value)
        # Update status indicator based on error state
        if not self._has_error:
            self._status_indicator.setStyleSheet(STATUS_GREEN)
        # Restore tooltip after a brief delay to allow Qt to process the update
        if self._tooltip_visible:
            QTimer.singleShot(10, self._restore_tooltip)

    # change background color of value, called by main window's update_errors function
    def change_color(self, bit):
        if int(bit) == 1:  # if bit is 1 (error), set entire frame to error state
            self._has_error = True
            # Make the entire frame red-tinted for more prominent error display
            self.setStyleSheet(self._frame_error)
            self.value_label.setStyleSheet("QLabel { background-color: #e74c3c; color: white; border: none; border-radius: 3px; padding: 2px; }")
            self._status_indicator.setStyleSheet(STATUS_RED)
            if self.name == "Laser power":
                self.change_value("ERROR")
            elif self.name == "Saturator liquid level":
                self.change_value("LOW")
            elif self.name == "Drain liquid level":
                self.change_value("HIGH")
            elif self.name == "Pulse quality":
                self.change_value("ERROR")
        else:  # if bit is 0 (no error), set background color to normal
            self._has_error = False
            self.setStyleSheet(self._frame_normal)
            self.value_label.setStyleSheet(self.default_color)
            self._status_indicator.setStyleSheet(STATUS_GREEN)
            if self.name in self.ok_error_indicators:
                self.change_value("OK")

    def setToolTip(self, tooltip):
        """Set tooltip on the name label only, not the whole widget."""
        self.name_label.setToolTip(tooltip)


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


class ToggleSwitch(QWidget):
    """Modern toggle switch widget with sliding animation.

    A pill-shaped switch with a sliding knob that animates between
    ON (green) and OFF (gray) states.
    """

    # Signal emitted when toggle state changes
    toggled = pyqtSignal(bool)
    # Clicked signal for backward compatibility with ToggleButton
    clicked = pyqtSignal()

    def __init__(self, name, tooltip="", *args, **kwargs):
        super().__init__()
        self.name = name
        self.state = 0
        self._knob_position = 0.0  # 0.0 = left (OFF), 1.0 = right (ON)

        # Create specific command messages for drying toggle (same as ToggleButton)
        if self.name == "Drying":
            self.messages = {0: ":SET:RUN", 1: ":SET:DRY"}

        # Colors
        self._track_color_on = QColor("#4CAF50")  # Green
        self._track_color_off = QColor("#5a5a5a")  # Darker gray for better visibility
        self._knob_color = QColor("#FFFFFF")  # White
        self._text_color = QColor("#CCCCCC")  # Light gray text (visible on dark background)
        self._text_color_off = QColor("#AAAAAA")  # Slightly brighter for OFF state visibility

        # Dimensions
        self._track_width = 50
        self._track_height = 26
        self._knob_margin = 3
        self._knob_diameter = self._track_height - (2 * self._knob_margin)

        # Animation
        self._animation = QPropertyAnimation(self, b"knobPosition")
        self._animation.setDuration(150)  # 150ms animation
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)

        # Set tooltip if provided
        if tooltip:
            self.setToolTip(tooltip)

        # Set fixed size for the switch area
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Enable mouse tracking for hover effects
        self.setCursor(Qt.PointingHandCursor)

    def get_knob_position(self):
        return self._knob_position

    def set_knob_position(self, pos):
        self._knob_position = pos
        self.update()  # Trigger repaint

    # Property for animation
    knobPosition = pyqtProperty(float, get_knob_position, set_knob_position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate layout - center the switch and label
        total_height = self.height()
        switch_y = (total_height - self._track_height) // 2

        # Draw track (pill shape)
        track_rect = QRectF(10, switch_y, self._track_width, self._track_height)

        # Interpolate track color based on knob position
        r = int(self._track_color_off.red() + (self._track_color_on.red() - self._track_color_off.red()) * self._knob_position)
        g = int(self._track_color_off.green() + (self._track_color_on.green() - self._track_color_off.green()) * self._knob_position)
        b = int(self._track_color_off.blue() + (self._track_color_on.blue() - self._track_color_off.blue()) * self._knob_position)
        track_color = QColor(r, g, b)

        # Draw border for OFF state (more visible)
        if self._knob_position < 0.5:
            painter.setPen(QPen(QColor("#777"), 1))
        else:
            painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(track_rect, self._track_height / 2, self._track_height / 2)

        # Draw knob (circle)
        knob_x = 10 + self._knob_margin + self._knob_position * (self._track_width - self._knob_diameter - 2 * self._knob_margin)
        knob_y = switch_y + self._knob_margin
        knob_rect = QRectF(knob_x, knob_y, self._knob_diameter, self._knob_diameter)

        # Add subtle shadow to knob
        shadow_rect = QRectF(knob_x + 1, knob_y + 1, self._knob_diameter, self._knob_diameter)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 30)))
        painter.drawEllipse(shadow_rect)

        # Draw knob
        painter.setBrush(QBrush(self._knob_color))
        painter.drawEllipse(knob_rect)

        # Draw label text (brighter for OFF state)
        text_color = self._text_color if self.state else self._text_color_off
        painter.setPen(QPen(text_color))
        font = self.font()
        font.setPointSize(12)
        font.setBold(not self.state)  # Bold for OFF state to make it more visible
        painter.setFont(font)

        text_x = 10 + self._track_width + 10  # After switch + padding
        text_rect = QRectF(text_x, 0, self.width() - text_x, total_height)

        # Show state text with name
        state_text = "ON" if self.state else "OFF"
        display_text = f"{self.name}: {state_text}"
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, display_text)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle()

    def toggle(self):
        """Toggle the switch state with animation."""
        self.state = 1 - self.state  # Toggle between 0 and 1

        # Animate knob position
        self._animation.stop()
        self._animation.setStartValue(self._knob_position)
        self._animation.setEndValue(float(self.state))
        self._animation.start()

        # Emit signals
        self.toggled.emit(bool(self.state))
        self.clicked.emit()  # For backward compatibility with ToggleButton

    def update_state(self, state):
        """Update state from external source (e.g., device feedback)."""
        if state != self.state:
            if str(state) == 'nan':
                return
            new_state = int(state)
            if new_state != self.state:
                self.state = new_state
                # Animate to new position
                self._animation.stop()
                self._animation.setStartValue(self._knob_position)
                self._animation.setEndValue(float(self.state))
                self._animation.start()

    def isChecked(self):
        """Return whether switch is ON (for compatibility with ToggleButton)."""
        return bool(self.state)

    def setChecked(self, checked):
        """Set switch state (for compatibility with ToggleButton)."""
        new_state = 1 if checked else 0
        if new_state != self.state:
            self.state = new_state
            self._knob_position = float(self.state)
            self.update()


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

# Stylesheet for custom +/- spinbox buttons
# Uses both class and ID selectors to override global stylesheet
# Also styles the internal QLineEdit to ensure text visibility
SPINBOX_STYLE = """
    QSpinBox, QDoubleSpinBox,
    QSpinBox#spin_box, QDoubleSpinBox#double_spin_box {
        background-color: #3a3a3a;
        color: #ddd;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 2px;
        padding-right: 30px;
    }
    QSpinBox QLineEdit, QDoubleSpinBox QLineEdit {
        background-color: #3a3a3a;
        color: #ddd;
        border: none;
        selection-background-color: #555;
        selection-color: #fff;
    }
    QSpinBox::up-button, QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        background-color: #3a3a3a;
        border: 1px solid #555;
        border-top-right-radius: 3px;
        width: 28px;
    }
    QSpinBox::down-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        background-color: #3a3a3a;
        border: 1px solid #555;
        border-bottom-right-radius: 3px;
        width: 28px;
    }
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
        background-color: #505050;
        border: 1px solid #777;
    }
    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
    QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
        background-color: #606060;
    }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        image: none;
        width: 0;
        height: 0;
    }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        image: none;
        width: 0;
        height: 0;
    }
"""

# Button width constant for paintEvent
SPINBOX_BUTTON_WIDTH = 28

# custom spin box class with signal for value change
# https://stackoverflow.com/questions/47874952/qspinbox-signal-for-arrow-buttons
class SpinBox(QSpinBox):
    stepChanged = pyqtSignal(int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(SPINBOX_STYLE)
        # Explicitly style internal line edit to ensure text visibility
        self.lineEdit().setStyleSheet("background-color: #3a3a3a; color: #ddd; border: none;")

    # override stepBy function to emit signal when value changes
    def stepBy(self, step):
        value = self.value() # store cur value before change
        super(SpinBox, self).stepBy(step) # call parent to perform the change still
        if self.value() != value: # check if val actually changed
            self.stepChanged.emit(self.value()) # emit custom signal

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw +/- on buttons
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get button areas (approximate positions)
        button_width = SPINBOX_BUTTON_WIDTH
        button_height = self.height() // 2
        right_edge = self.width() - 1

        # Draw + on up button
        painter.setPen(QPen(QColor("#ccc"), 2))
        plus_center_x = right_edge - button_width // 2
        plus_center_y = button_height // 2
        painter.drawLine(plus_center_x - 4, plus_center_y, plus_center_x + 4, plus_center_y)
        painter.drawLine(plus_center_x, plus_center_y - 4, plus_center_x, plus_center_y + 4)

        # Draw - on down button
        minus_center_y = button_height + button_height // 2
        painter.drawLine(plus_center_x - 4, minus_center_y, plus_center_x + 4, minus_center_y)

        painter.end()

class DoubleSpinBox(QDoubleSpinBox):
    stepChanged = pyqtSignal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet(SPINBOX_STYLE)
        # Explicitly style internal line edit to ensure text visibility
        self.lineEdit().setStyleSheet("background-color: #3a3a3a; color: #ddd; border: none;")

    # override stepBy function to emit signal when value changes
    def stepBy(self, step):
        value = self.value() # store cur value before change
        super(DoubleSpinBox, self).stepBy(step) # call parents implementation to perform the change still
        if self.value() != value: # check if value actually changed
            self.stepChanged.emit(self.value()) # emit custom signal

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw +/- on buttons
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get button areas (approximate positions)
        button_width = SPINBOX_BUTTON_WIDTH
        button_height = self.height() // 2
        right_edge = self.width() - 1

        # Draw + on up button
        painter.setPen(QPen(QColor("#ccc"), 2))
        plus_center_x = right_edge - button_width // 2
        plus_center_y = button_height // 2
        painter.drawLine(plus_center_x - 4, plus_center_y, plus_center_x + 4, plus_center_y)
        painter.drawLine(plus_center_x, plus_center_y - 4, plus_center_x, plus_center_y + 4)

        # Draw - on down button
        minus_center_y = button_height + button_height // 2
        painter.drawLine(plus_center_x - 4, minus_center_y, plus_center_x + 4, minus_center_y)

        painter.end()

# Editable input field style with hover and focus effects
EDITABLE_INPUT_STYLE = """
    QLineEdit {
        background-color: #2a2a2a;
        color: #ddd;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 4px 8px;
    }
    QLineEdit:hover {
        border: 1px solid #888;
        background-color: #353535;
    }
    QLineEdit:focus {
        border: 1px solid #3498db;
        background-color: #353535;
    }
    QLineEdit::placeholder {
        color: #666;
    }
"""


# used in CPCSetTab and PSMSetTab
class SetWidget(QFrame):
    def __init__(self, name, suffix, *args, integer=False, **kwargs):
        super().__init__()
        # Outer border, transparent background for inner elements
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { border: 1px solid #555; border-radius: 4px; background: #2d2d2d; } QLabel { background: transparent; border: none; }")

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        font = self.font()
        font.setPointSize(11)
        # create label for widget name
        self.name = name
        self.name_label = QLabel(self.name, objectName="label")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setFont(font)
        self.name_label.setStyleSheet("QLabel { color: #888; }")
        self.name_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        layout.addWidget(self.name_label, alignment=Qt.AlignCenter)
        # create normal / double spin box for setting value
        self.is_integer = integer
        if integer:
            self.value_spinbox = SpinBox(objectName="spin_box", maximum=9999)
            validator = QIntValidator()
        else:
            if "decimals" in kwargs:
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999, decimals=kwargs["decimals"])
            else:
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999)
            locale = QLocale(QLocale.C)
            validator = QDoubleValidator()
            validator.setLocale(locale)
            self.value_spinbox.setLocale(locale)
        self.value_spinbox.setSuffix(suffix)
        self.value_spinbox.lineEdit().setAlignment(Qt.AlignCenter)
        self.value_spinbox.setMaximumWidth(180)
        layout.addWidget(self.value_spinbox, alignment=Qt.AlignCenter)
        # set layout
        self.setLayout(layout)
        # store default stylesheet
        self.stylesheet = self.styleSheet()
        # create error variable for storing error state
        self.error = False
        # Backward compatibility - value_input no longer used
        self.value_input = None
    def set_red_color(self):
        if self.error == False:
            self.value_spinbox.setStyleSheet(SPINBOX_STYLE + " QSpinBox, QDoubleSpinBox { background-color: red; }")
            self.value_spinbox.lineEdit().setStyleSheet("background-color: red; color: #fff; border: none;")
            self.error = True

    def set_default_color(self):
        if self.error == True:
            self.value_spinbox.setStyleSheet(SPINBOX_STYLE)
            self.value_spinbox.lineEdit().setStyleSheet("background-color: #3a3a3a; color: #ddd; border: none;")
            self.error = False

    def setToolTip(self, tooltip):
        """Set tooltip on the name label only, not the whole widget."""
        self.name_label.setToolTip(tooltip)


class SetStatusWidget(QFrame):
    """Combined setpoint control and actual value display widget.

    Shows a setpoint spinbox with input field, plus a large indicator
    displaying the actual measured value. Includes status indicator,
    delta display, and trend arrows.
    """
    def __init__(self, name, suffix, actual_name=None, *args, integer=False, is_temperature=True, **kwargs):
        from collections import deque
        super().__init__()
        self.name = name
        self.actual_name = actual_name or name
        self.suffix = suffix
        self.is_temperature = is_temperature  # Used for tolerance thresholds

        # Outer border with subtle background
        self.setFrameStyle(QFrame.StyledPanel)
        self._frame_normal = "QFrame { border: 1px solid #555; border-radius: 4px; background: #2d2d2d; } QLabel { background: transparent; border: none; }"
        self._frame_error = "QFrame { border: 2px solid #e74c3c; border-radius: 4px; background: rgba(231, 76, 60, 0.15); } QLabel { background: transparent; border: none; }"
        self._frame_warning = "QFrame { border: 2px solid #f39c12; border-radius: 4px; background: rgba(243, 156, 18, 0.1); } QLabel { background: transparent; border: none; }"
        self.setStyleSheet(self._frame_normal)

        # Main horizontal layout: status indicator + content
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Status indicator (colored bar on left side)
        self._status_indicator = QFrame()
        self._status_indicator.setFixedSize(6, 80)
        self._status_indicator.setStyleSheet(STATUS_GRAY)
        main_layout.addWidget(self._status_indicator)

        # Content area - vertical: header on top, then horizontal sections below
        content_layout = QVBoxLayout()
        content_layout.setSpacing(4)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Name label at top, centered over both sections
        self.name_label = QLabel(self.name)
        name_font = self.font()
        name_font.setPointSize(11)
        self.name_label.setFont(name_font)
        self.name_label.setStyleSheet("QLabel { color: #888; }")
        self.name_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(self.name_label)

        # Grid layout for aligned Set/Actual sections
        from PyQt5.QtWidgets import QGridLayout
        values_grid = QGridLayout()
        values_grid.setSpacing(8)
        values_grid.setContentsMargins(0, 0, 0, 0)

        # Row 0: Set: | Actual:
        self.setpoint_label = QLabel("Set:")
        setpoint_label_font = self.font()
        setpoint_label_font.setPointSize(10)
        self.setpoint_label.setFont(setpoint_label_font)
        self.setpoint_label.setStyleSheet("QLabel { color: #666; }")
        self.setpoint_label.setAlignment(Qt.AlignCenter)
        values_grid.addWidget(self.setpoint_label, 0, 0)

        actual_header = QLabel("Actual:")
        actual_header_font = self.font()
        actual_header_font.setPointSize(10)
        actual_header.setFont(actual_header_font)
        actual_header.setStyleSheet("QLabel { color: #666; }")
        actual_header.setAlignment(Qt.AlignCenter)
        values_grid.addWidget(actual_header, 0, 1)

        # Row 1: Spinbox | Actual value
        self.is_integer = integer
        if integer:
            self.value_spinbox = SpinBox(objectName="spin_box", maximum=9999)
            validator = QIntValidator()
        else:
            if "decimals" in kwargs:
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999, decimals=kwargs["decimals"])
            else:
                self.value_spinbox = DoubleSpinBox(objectName="double_spin_box", singleStep=0.1, maximum=9999)
            locale = QLocale(QLocale.C)
            validator = QDoubleValidator()
            validator.setLocale(locale)
            self.value_spinbox.setLocale(locale)
        self.value_spinbox.setSuffix(suffix)
        self.value_spinbox.lineEdit().setAlignment(Qt.AlignCenter)
        self.value_spinbox.setMaximumWidth(150)
        values_grid.addWidget(self.value_spinbox, 1, 0, Qt.AlignCenter)

        self.actual_label = QLabel("--")
        self.actual_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        actual_font = self.font()
        actual_font.setPointSize(24)
        actual_font.setBold(True)
        self.actual_label.setFont(actual_font)
        self.actual_label.setStyleSheet("QLabel { color: #ddd; }")
        self.actual_label.setMinimumWidth(100)
        values_grid.addWidget(self.actual_label, 1, 1)

        # Row 2: (empty) | Delta + trend
        delta_row = QHBoxLayout()
        delta_row.setSpacing(4)

        self.delta_label = QLabel("")
        delta_font = self.font()
        delta_font.setPointSize(10)
        self.delta_label.setFont(delta_font)
        self.delta_label.setStyleSheet("QLabel { color: #888; }")
        self.delta_label.setAlignment(Qt.AlignCenter)
        delta_row.addWidget(self.delta_label, stretch=1)

        self.trend_label = QLabel("")
        trend_font = self.font()
        trend_font.setPointSize(12)
        self.trend_label.setFont(trend_font)
        self.trend_label.setStyleSheet("QLabel { color: #888; }")
        self.trend_label.setAlignment(Qt.AlignCenter)
        self.trend_label.setFixedWidth(20)
        delta_row.addWidget(self.trend_label)

        values_grid.addLayout(delta_row, 2, 1)

        # Backward compatibility - value_input no longer used
        self.value_input = None

        # Set column stretch for equal widths
        values_grid.setColumnStretch(0, 1)
        values_grid.setColumnStretch(1, 1)

        content_layout.addLayout(values_grid)
        main_layout.addLayout(content_layout, 1)
        self.setLayout(main_layout)
        self.stylesheet = self.styleSheet()
        self.error = False

        # Track tooltip visibility for persistence during updates
        self._tooltip_visible = False
        self._tooltip_pos = None

        # Value history for trend calculation (10 second window)
        self._value_history = deque(maxlen=10)
        self._current_actual = None
        self._has_error = False

        # Install event filter on name_label to track tooltip
        self.name_label.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Track tooltip show/hide on name_label."""
        if obj == self.name_label:
            if event.type() == QEvent.ToolTip:
                self._tooltip_visible = True
                self._tooltip_pos = event.globalPos()
            elif event.type() == QEvent.Leave:
                self._tooltip_visible = False
                self._tooltip_pos = None
        return super().eventFilter(obj, event)

    def _restore_tooltip(self):
        """Restore tooltip if it was visible before update."""
        if self._tooltip_visible and self._tooltip_pos and self.name_label.toolTip():
            QToolTip.showText(self._tooltip_pos, self.name_label.toolTip(), self.name_label)

    def _parse_value(self, value_str):
        """Parse numeric value from string (removes units)."""
        try:
            # Remove common suffixes
            cleaned = value_str.replace("°C", "").replace("lpm", "").replace("kPa", "").strip()
            return float(cleaned)
        except (ValueError, AttributeError):
            return None

    def _calculate_trend(self):
        """Calculate trend based on value history."""
        if len(self._value_history) < 6:
            return ""  # Not enough data

        history = list(self._value_history)
        first_half = history[:len(history)//2]
        second_half = history[len(history)//2:]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        # Threshold based on type
        threshold = 0.1 if self.is_temperature else 0.01

        diff = second_avg - first_avg
        if diff > threshold:
            return "↑"
        elif diff < -threshold:
            return "↓"
        return ""  # Stable - no arrow

    def _update_status_indicator(self, actual, setpoint):
        """Update status indicator color and frame style based on delta."""
        if actual is None or setpoint is None or setpoint == 0:
            self._status_indicator.setStyleSheet(STATUS_GRAY)
            self.setStyleSheet(self._frame_normal)
            return

        delta = abs(actual - setpoint)

        if self.is_temperature:
            # Temperature thresholds: ±0.5°C green, ±1°C yellow, else red
            if delta <= 0.5:
                self._status_indicator.setStyleSheet(STATUS_GREEN)
                self.setStyleSheet(self._frame_normal)
            elif delta <= 1.0:
                self._status_indicator.setStyleSheet(STATUS_YELLOW)
                self.setStyleSheet(self._frame_warning)
            else:
                self._status_indicator.setStyleSheet(STATUS_RED)
                self.setStyleSheet(self._frame_error)
        else:
            # Flow rate thresholds: ±5% green, ±10% yellow, else red
            pct = (delta / setpoint) * 100 if setpoint != 0 else 0
            if pct <= 5:
                self._status_indicator.setStyleSheet(STATUS_GREEN)
                self.setStyleSheet(self._frame_normal)
            elif pct <= 10:
                self._status_indicator.setStyleSheet(STATUS_YELLOW)
                self.setStyleSheet(self._frame_warning)
            else:
                self._status_indicator.setStyleSheet(STATUS_RED)
                self.setStyleSheet(self._frame_error)

    def change_value(self, value):
        """Update the actual value display (called by device update)."""
        self.actual_label.setText(value)

        # Parse numeric value for calculations
        actual = self._parse_value(value)
        self._current_actual = actual

        if actual is not None:
            # Add to history for trend
            self._value_history.append(actual)

            # Get setpoint for delta and status
            setpoint = self.value_spinbox.value()

            # Update delta display (actual - setpoint: positive means actual is above target)
            delta = actual - setpoint
            delta_sign = "+" if delta >= 0 else ""
            if self.is_temperature:
                self.delta_label.setText(f"Δ {delta_sign}{delta:.2f}°C")
            else:
                self.delta_label.setText(f"Δ {delta_sign}{delta:.3f}")

            # Color delta based on magnitude
            abs_delta = abs(delta)
            if self.is_temperature:
                if abs_delta <= 0.5:
                    self.delta_label.setStyleSheet("QLabel { color: #27ae60; }")  # Green
                elif abs_delta <= 1.0:
                    self.delta_label.setStyleSheet("QLabel { color: #f39c12; }")  # Yellow
                else:
                    self.delta_label.setStyleSheet("QLabel { color: #e74c3c; }")  # Red
            else:
                pct = (abs_delta / setpoint) * 100 if setpoint != 0 else 0
                if pct <= 5:
                    self.delta_label.setStyleSheet("QLabel { color: #27ae60; }")
                elif pct <= 10:
                    self.delta_label.setStyleSheet("QLabel { color: #f39c12; }")
                else:
                    self.delta_label.setStyleSheet("QLabel { color: #e74c3c; }")

            # Update trend arrow (only shows ↑ or ↓, empty when stable)
            trend = self._calculate_trend()
            self.trend_label.setText(trend)
            if trend == "↑":
                self.trend_label.setStyleSheet("QLabel { color: #e74c3c; }")  # Red for rising
            elif trend == "↓":
                self.trend_label.setStyleSheet("QLabel { color: #3498db; }")  # Blue for falling
            else:
                self.trend_label.setStyleSheet("QLabel { color: #888; }")  # Gray (hidden anyway)

            # Update status indicator (unless there's an error)
            if not self._has_error:
                self._update_status_indicator(actual, setpoint)

        # Restore tooltip after a brief delay
        if self._tooltip_visible:
            QTimer.singleShot(10, self._restore_tooltip)

    def set_red_color(self):
        """Set error color on spinbox."""
        if self.error == False:
            self.value_spinbox.setStyleSheet(SPINBOX_STYLE + " QSpinBox, QDoubleSpinBox { background-color: red; }")
            self.value_spinbox.lineEdit().setStyleSheet("background-color: red; color: #fff; border: none;")
            self.error = True

    def set_default_color(self):
        """Reset spinbox to default color."""
        if self.error == True:
            self.value_spinbox.setStyleSheet(SPINBOX_STYLE)
            self.value_spinbox.lineEdit().setStyleSheet("background-color: #3a3a3a; color: #ddd; border: none;")
            self.error = False

    def change_color(self, bit):
        """Change color based on error bit (for compatibility with IndicatorWidget)."""
        if int(bit) == 1:
            self._has_error = True
            # Make the entire frame red-tinted for prominent error display
            self.setStyleSheet(self._frame_error)
            self.actual_label.setStyleSheet("QLabel { background-color: #e74c3c; color: white; border-radius: 3px; padding: 2px; }")
            self._status_indicator.setStyleSheet(STATUS_RED)
        else:
            self._has_error = False
            self.setStyleSheet(self._frame_normal)
            self.actual_label.setStyleSheet("QLabel { color: #ddd; }")
            # Re-evaluate status based on current values
            if self._current_actual is not None:
                self._update_status_indicator(self._current_actual, self.value_spinbox.value())

    def setToolTip(self, tooltip):
        """Set tooltip on the name label only, not the whole widget."""
        self.name_label.setToolTip(tooltip)


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

        # Process pending events to ensure geometry is up-to-date after tab deletions
        QApplication.processEvents()

        # Validate tab index is still valid
        if tab_index < 0 or tab_index >= tab_bar.count():
            # Tab no longer exists, position at cursor as fallback
            cursor_pos = QCursor.pos()
            popup_x = cursor_pos.x() - self.width() // 2
            popup_y = cursor_pos.y() + 10
        else:
            # Get the close button for positioning
            close_button = tab_bar.tabButton(tab_index, QTabBar.RightSide)

            # Try multiple positioning strategies in order of preference
            if close_button and close_button.isVisible():
                # Strategy 1: Use mapToGlobal directly on the close button
                # This gives us the button's actual screen position
                button_global_pos = close_button.mapToGlobal(QPoint(0, 0))
                button_width = close_button.width()
                button_height = close_button.height()

                popup_x = button_global_pos.x() + button_width - self.width()
                popup_y = button_global_pos.y() + button_height + 2
            else:
                # Strategy 2: Use tab rectangle
                tab_rect = tab_bar.tabRect(tab_index)

                if not tab_rect.isNull() and not tab_rect.isEmpty():
                    # Use mapTabToGlobal if available (BrowserStyleTabBar wrapper)
                    # Otherwise fall back to mapToGlobal (plain QTabBar)
                    if hasattr(tab_bar, 'mapTabToGlobal'):
                        global_pos = tab_bar.mapTabToGlobal(tab_index, tab_rect.bottomRight())
                    else:
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


class _InnerTabBar(QTabBar):
    """Inner tab bar used by BrowserStyleTabBar. Not for direct use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setExpanding(False)  # Don't stretch tabs - we control sizing
        self.setUsesScrollButtons(False)  # Disable native scroll - we handle it
        self.setMovable(True)  # Enable drag-and-drop reordering
        self.setElideMode(Qt.ElideNone)  # Show full text, don't truncate
        self.setDrawBase(False)  # Don't draw the base line behind tabs

    def tabSizeHint(self, index):
        """Return width that fits the full tab text with padding for close button."""
        size = QTabBar.tabSizeHint(self, index)
        # Calculate text width using font metrics for accuracy
        text = self.tabText(index)
        fm = self.fontMetrics()
        text_width = fm.horizontalAdvance(text)
        # Add padding: left margin + right margin + close button space
        width = max(150, text_width + 100)
        return QSize(width, size.height())


class BrowserStyleTabBar(QWidget):
    """Custom scrollable tab bar widget using QScrollArea.

    This bypasses Qt's native tab bar scrolling (which auto-scrolls to current tab)
    by wrapping a QTabBar in a QScrollArea and handling scrolling ourselves.

    Exposes QTabBar methods via delegation for compatibility.
    """

    # Forward signals from inner tab bar
    currentChanged = pyqtSignal(int)
    tabMoved = pyqtSignal(int, int)  # (from_index, to_index) - emitted when user drags a tab
    tabBarClicked = pyqtSignal(int)  # Emitted when any tab is clicked (even if already selected)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Set transparent background to prevent visible box behind tabs
        super().setStyleSheet("background: transparent;")

        # Left scroll button
        self._left_scroll_btn = QToolButton(self)
        self._left_scroll_btn.setArrowType(Qt.LeftArrow)
        self._left_scroll_btn.clicked.connect(self._scroll_left)
        self._left_scroll_btn.setVisible(False)
        self._left_scroll_btn.setFixedSize(40, 53)
        layout.addWidget(self._left_scroll_btn)

        # Scroll area to hold the tab bar
        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Set transparent background to prevent visible box artifact
        self._scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollArea > QWidget > QWidget { background: transparent; }")
        layout.addWidget(self._scroll_area, stretch=1)

        # The actual tab bar inside the scroll area
        self._tab_bar = _InnerTabBar()
        self._tab_bar.setObjectName("mainDeviceTabBar")  # Unique name for specific styling
        self._tab_bar.currentChanged.connect(self.currentChanged.emit)
        self._tab_bar.tabMoved.connect(self.tabMoved.emit)  # Forward tab drag events
        self._tab_bar.tabBarClicked.connect(self.tabBarClicked.emit)  # Forward click events
        self._scroll_area.setWidget(self._tab_bar)

        # Make viewport transparent
        self._scroll_area.viewport().setAutoFillBackground(False)

        # Right scroll button
        self._right_scroll_btn = QToolButton(self)
        self._right_scroll_btn.setArrowType(Qt.RightArrow)
        self._right_scroll_btn.clicked.connect(self._scroll_right)
        self._right_scroll_btn.setVisible(False)
        self._right_scroll_btn.setFixedSize(40, 53)
        layout.addWidget(self._right_scroll_btn)

        # Style the scroll buttons
        button_style = """
            QToolButton {
                background-color: #3a3a3a;
                border: none;
                padding: 5px;
                color: #999999;
            }
            QToolButton:hover {
                background-color: #4a4a4a;
                color: #ffffff;
            }
            QToolButton:pressed {
                background-color: #2a2a2a;
            }
            QToolButton:disabled {
                color: #555555;
                background-color: #2a2a2a;
            }
        """
        self._left_scroll_btn.setStyleSheet(button_style)
        self._right_scroll_btn.setStyleSheet(button_style)

        # Timer to update scroll button visibility
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_scroll_buttons)
        self._update_timer.start(100)

        # Scroll step size in pixels
        self._scroll_step = 150

        # Height for the link overlay bracket area (36px to allow stacked lines)
        self._overlay_height = 36

        # Create link overlay for drawing connectors between linked tabs
        # Position it at the TOP of the tabs
        self._link_overlay = TabLinkOverlay(self, self)
        self._link_overlay.setGeometry(0, 0, self.width(), self._overlay_height)
        self._link_overlay.raise_()  # Bring to front
        self._link_overlay.show()

        # Set fixed height
        self.setFixedHeight(53)

    def update_links(self, links, device_widgets, stacked_widget):
        """Update the link overlay with current device link data.

        Args:
            links: Dict like {'psm_cpc': {psm_id: cpc_id}, 'cpc_rhtp': {cpc_id: rhtp_id}}
            device_widgets: Dict of device_id -> widget
            stacked_widget: QStackedWidget containing device widgets
        """
        self._link_overlay.set_links(links, device_widgets, stacked_widget)

    # === Delegate QTabBar methods to inner tab bar ===

    def addTab(self, *args):
        result = self._tab_bar.addTab(*args)
        self._update_tab_bar_size()
        self._update_scroll_buttons()
        return result

    def removeTab(self, index):
        self._tab_bar.removeTab(index)
        self._update_tab_bar_size()
        self._update_scroll_buttons()

    def count(self):
        return self._tab_bar.count()

    def currentIndex(self):
        return self._tab_bar.currentIndex()

    def setCurrentIndex(self, index):
        self._tab_bar.setCurrentIndex(index)
        # Note: We intentionally don't auto-scroll here - that's the fix!

    def tabText(self, index):
        return self._tab_bar.tabText(index)

    def setTabText(self, index, text):
        self._tab_bar.setTabText(index, text)
        self._update_tab_bar_size()

    def tabButton(self, index, position):
        return self._tab_bar.tabButton(index, position)

    def setTabButton(self, index, position, widget):
        self._tab_bar.setTabButton(index, position, widget)

    def tabIcon(self, index):
        return self._tab_bar.tabIcon(index)

    def setTabIcon(self, index, icon):
        self._tab_bar.setTabIcon(index, icon)

    def tabRect(self, index):
        return self._tab_bar.tabRect(index)

    def setStyleSheet(self, stylesheet):
        # Apply to inner tab bar, not the wrapper
        self._tab_bar.setStyleSheet(stylesheet)

    def mapTabToGlobal(self, index, point):
        """Map a point relative to a tab to global coordinates.

        Use this instead of mapToGlobal when working with tabRect coordinates.
        """
        return self._tab_bar.mapToGlobal(point)

    def insertTab(self, index, *args):
        """Insert a tab at the specified index."""
        result = self._tab_bar.insertTab(index, *args)
        self._update_tab_bar_size()
        self._update_scroll_buttons()
        return result

    def moveTab(self, from_index, to_index):
        """Move a tab from one position to another.

        Since QTabBar doesn't support moveTab directly, this removes and re-inserts.

        Args:
            from_index: Current tab index
            to_index: Target tab index
        """
        if from_index == to_index:
            return
        if from_index < 0 or from_index >= self.count():
            return
        if to_index < 0 or to_index > self.count():
            return

        # Store tab data before removal
        text = self._tab_bar.tabText(from_index)
        icon = self._tab_bar.tabIcon(from_index)
        data = self._tab_bar.tabData(from_index)
        close_button = self._tab_bar.tabButton(from_index, QTabBar.RightSide)

        # Detach close button before tab removal (Qt would delete it otherwise)
        if close_button:
            self._tab_bar.setTabButton(from_index, QTabBar.RightSide, None)

        # Remove tab
        self._tab_bar.removeTab(from_index)

        # Re-insert tab at new position
        if icon and not icon.isNull():
            self._tab_bar.insertTab(to_index, icon, text)
        else:
            self._tab_bar.insertTab(to_index, text)

        if data:
            self._tab_bar.setTabData(to_index, data)
        if close_button:
            self._tab_bar.setTabButton(to_index, QTabBar.RightSide, close_button)

        self._update_tab_bar_size()
        self._update_scroll_buttons()

    @property
    def innerTabBar(self):
        """Access the inner QTabBar for advanced operations."""
        return self._tab_bar

    # === Scroll handling ===

    def _update_tab_bar_size(self):
        """Update the inner tab bar's size to fit all tabs."""
        # Calculate total width needed using size hints (not tabRect which may be stale)
        total_width = 0
        for i in range(self._tab_bar.count()):
            total_width += self._tab_bar.tabSizeHint(i).width()

        # Add some padding
        total_width += 10

        # Set the tab bar width
        self._tab_bar.setFixedWidth(max(total_width, self._scroll_area.width()))
        self._tab_bar.setFixedHeight(53)
        self._update_scroll_buttons()

    def _scroll_left(self):
        """Scroll viewport to the left."""
        scrollbar = self._scroll_area.horizontalScrollBar()
        scrollbar.setValue(scrollbar.value() - self._scroll_step)
        self._update_scroll_buttons()

    def _scroll_right(self):
        """Scroll viewport to the right."""
        scrollbar = self._scroll_area.horizontalScrollBar()
        scrollbar.setValue(scrollbar.value() + self._scroll_step)
        self._update_scroll_buttons()

    def _update_scroll_buttons(self):
        """Update visibility and enabled state of scroll buttons."""
        scrollbar = self._scroll_area.horizontalScrollBar()

        # Check if scrolling is needed
        scrolling_needed = scrollbar.maximum() > 0

        if scrolling_needed:
            # Always show both buttons when scrolling is needed (prevents flicker)
            self._left_scroll_btn.setVisible(True)
            self._right_scroll_btn.setVisible(True)

            # Enable/disable buttons based on scroll position
            can_scroll_left = scrollbar.value() > scrollbar.minimum()
            can_scroll_right = scrollbar.value() < scrollbar.maximum()

            self._left_scroll_btn.setEnabled(can_scroll_left)
            self._right_scroll_btn.setEnabled(can_scroll_right)
        else:
            self._left_scroll_btn.setVisible(False)
            self._right_scroll_btn.setVisible(False)

    def resizeEvent(self, event):
        """Handle resize - update tab bar size and scroll buttons."""
        super().resizeEvent(event)
        self._update_tab_bar_size()
        self._update_scroll_buttons()
        # Update link overlay geometry
        if hasattr(self, '_link_overlay'):
            self._link_overlay.setGeometry(0, 0, self.width(), self._overlay_height)
            self._link_overlay.raise_()
            self._link_overlay.update()

    def wheelEvent(self, event):
        """Enable mouse wheel/touchpad to scroll through tabs."""
        delta = event.angleDelta().y()

        if delta > 0 and self._right_scroll_btn.isEnabled():
            self._scroll_right()
        elif delta < 0 and self._left_scroll_btn.isEnabled():
            self._scroll_left()

        event.accept()


__all__ = [
    'SetWidget', 'SetStatusWidget', 'SpinBox', 'DoubleSpinBox', 'ToggleButton', 'ToggleSwitch', 'StartButton', 'IndicatorWidget',
    'CommandWidget', 'FloatTextEdit', 'StepsWidget', 'TabConfirmationPopup', 'BrowserStyleTabBar'
]
