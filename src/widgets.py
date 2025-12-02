from PyQt5.QtGui import QPalette, QIntValidator, QDoubleValidator, QCursor
from PyQt5.QtCore import Qt, pyqtSignal, QLocale, QTimer, QSize
from PyQt5.QtWidgets import (QLabel, QWidget, QVBoxLayout, QLineEdit, QPushButton,
                             QSpinBox, QDoubleSpinBox, QTextEdit, QHBoxLayout,
                             QSizePolicy, QSplitter, QTabBar, QStyleFactory, QApplication,
                             QToolButton, QScrollArea, QFrame)
from datetime import datetime as dt
import sys

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
        self.setElideMode(Qt.ElideRight)

    def tabSizeHint(self, index):
        """Return flexible width for tabs (150-200px based on text length)."""
        size = QTabBar.tabSizeHint(self, index)
        width = max(150, min(size.width(), 200))
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

    def __init__(self, parent=None):
        super().__init__(parent)

        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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
        layout.addWidget(self._scroll_area, stretch=1)

        # The actual tab bar inside the scroll area
        self._tab_bar = _InnerTabBar()
        self._tab_bar.currentChanged.connect(self.currentChanged.emit)
        self._tab_bar.tabMoved.connect(self.tabMoved.emit)  # Forward tab drag events
        self._scroll_area.setWidget(self._tab_bar)

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

        # Height for the link overlay bracket area
        self._overlay_height = 12

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
        # Calculate total width needed
        total_width = 0
        for i in range(self._tab_bar.count()):
            total_width += self._tab_bar.tabRect(i).width()

        # Add some padding
        total_width += 10

        # Set the tab bar width
        self._tab_bar.setFixedWidth(max(total_width, self._scroll_area.width()))
        self._tab_bar.setFixedHeight(53)

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
    'SetWidget', 'SpinBox', 'DoubleSpinBox', 'ToggleButton', 'StartButton', 'IndicatorWidget',
    'CommandWidget', 'FloatTextEdit', 'StepsWidget', 'TabConfirmationPopup', 'BrowserStyleTabBar'
]
