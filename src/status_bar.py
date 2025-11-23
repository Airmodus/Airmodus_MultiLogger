"""
Always-visible status bar for field monitoring.

Shows device connection status, current values, errors, and saving status.
"""

from PyQt5.QtWidgets import QStatusBar, QLabel, QWidget, QHBoxLayout, QToolTip, QFrame
from PyQt5.QtCore import Qt, QEvent, QTimer
from PyQt5.QtGui import QCursor, QFontMetrics, QFont
from datetime import datetime as dt


class VerticalSeparator(QFrame):
    """Thin vertical line separator for status bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Plain)
        self.setStyleSheet("QFrame { color: #E0E0E0; }")  # Light gray separator
        self.setFixedWidth(1)


class DeviceStatusWidget(QLabel):
    """
    Widget showing status for a single device.

    Format: [●] Device Name: Current Value
    Color: Green=OK, Yellow=Warning, Red=Error/Disconnected
    """

    def __init__(self, dev_id, device_name, parent=None):
        super().__init__(parent)
        self.dev_id = dev_id
        self.device_name = device_name

        # Timer for keeping tooltip visible
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.timeout.connect(self._refresh_tooltip)
        self._last_tooltip_pos = None

        # Make clickable
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAttribute(Qt.WA_Hover, True)  # Enable hover event tracking for rich text
        self.setTextInteractionFlags(Qt.LinksAccessibleByMouse)  # Enable mouse interaction
        self.setStyleSheet("padding: 2px 8px; border-radius: 3px;")

        # Calculate minimum width to prevent jittering
        # Use typical long value like "12345.6 #/cc" to calculate width
        font_metrics = QFontMetrics(self.font())
        typical_text = f"● {device_name}: 12345.6 #/cc"
        min_width = font_metrics.horizontalAdvance(typical_text) + 20  # +20 for padding
        self.setMinimumWidth(min_width)

        # Initialize with disconnected state
        self.update_status(connected=False, value="", has_error=False)

    def update_status(self, connected=False, value="", has_error=False, error_msg=""):
        """
        Update the device status display.

        Args:
            connected: Is device connected
            value: Current measurement value to display
            has_error: Does device have an error
            error_msg: Error message for tooltip
        """
        # Determine icon, colors, and text
        if not connected:
            icon = "⚠"
            bg_color = "#D32F2F"  # Dark red
            text_color = "#FFFFFF"  # White text for better contrast
            status_text = "Disconnected"
        elif has_error:
            icon = "●"
            bg_color = "#F57C00"  # Dark orange
            text_color = "#FFFFFF"  # White text for better contrast
            status_text = value if value else "Error"
        else:
            icon = "●"
            bg_color = "transparent"
            text_color = "#2E7D32"  # Dark green
            status_text = value if value else "Connected"

        # Wrap numeric values in monospace font to prevent width changes
        # Check if status_text contains numbers
        if value and any(char.isdigit() for char in value):
            status_text_html = f'<span style="font-family: monospace;">{status_text}</span>'
        else:
            status_text_html = status_text

        # Set text with consistent color scheme
        display_text = f'<span style="color: {text_color}; font-size: 14px;">{icon}</span> <span style="color: {text_color};"><b>{self.device_name}</b>: {status_text_html}</span>'
        self.setText(display_text)

        # Set background color and styling
        self.setStyleSheet(f"padding: 2px 8px; border-radius: 3px; background-color: {bg_color};")

        # Build tooltip
        tooltip_lines = [
            f"<b>{self.device_name}</b>",
            f"Connection: {'Connected ✓' if connected else 'Disconnected ✗'}",
        ]

        if value:
            tooltip_lines.append(f"Current: {value}")

        if has_error and error_msg:
            tooltip_lines.append(f"<span style='color: red;'>Error: {error_msg}</span>")
        elif has_error:
            tooltip_lines.append(f"<span style='color: red;'>Error: Check device status</span>")

        tooltip_lines.append("<i>(Click to view device tab)</i>")

        self.setToolTip("<br>".join(tooltip_lines))

    def mousePressEvent(self, event):
        """Handle click event."""
        if event.button() == Qt.LeftButton:
            # Walk up the parent chain to find the MultiLoggerStatusBar
            widget = self.parent()
            while widget:
                if hasattr(widget, 'device_clicked'):
                    widget.device_clicked(self.dev_id)
                    return
                widget = widget.parent()

    def event(self, event):
        """Handle custom tooltip behavior for persistent display."""
        if event.type() == QEvent.ToolTip:
            # Store position and show tooltip
            self._last_tooltip_pos = event.globalPos()
            QToolTip.showText(self._last_tooltip_pos, self.toolTip(), self, self.rect())

            # Start timer to refresh tooltip every 500ms to keep it visible
            if not self._tooltip_timer.isActive():
                self._tooltip_timer.start(500)
            return True
        elif event.type() == QEvent.Leave:
            # Mouse left widget - stop timer and hide tooltip
            self._tooltip_timer.stop()
            self._last_tooltip_pos = None
            QToolTip.hideText()
        return super().event(event)

    def _refresh_tooltip(self):
        """Refresh tooltip to keep it visible."""
        if self._last_tooltip_pos:
            # Re-show tooltip to reset the timeout
            QToolTip.showText(self._last_tooltip_pos, self.toolTip(), self, self.rect())


class PersistentTooltipLabel(QLabel):
    """QLabel with persistent tooltip using timer-based refresh."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Timer for keeping tooltip visible
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.timeout.connect(self._refresh_tooltip)
        self._last_tooltip_pos = None

    def event(self, event):
        """Handle custom tooltip behavior for persistent display."""
        if event.type() == QEvent.ToolTip:
            # Store position and show tooltip
            self._last_tooltip_pos = event.globalPos()
            QToolTip.showText(self._last_tooltip_pos, self.toolTip(), self, self.rect())

            # Start timer to refresh tooltip every 500ms to keep it visible
            if not self._tooltip_timer.isActive():
                self._tooltip_timer.start(500)
            return True
        elif event.type() == QEvent.Leave:
            # Mouse left widget - stop timer and hide tooltip
            self._tooltip_timer.stop()
            self._last_tooltip_pos = None
            QToolTip.hideText()
        return super().event(event)

    def _refresh_tooltip(self):
        """Refresh tooltip to keep it visible."""
        if self._last_tooltip_pos:
            # Re-show tooltip to reset the timeout
            QToolTip.showText(self._last_tooltip_pos, self.toolTip(), self, self.rect())


class MultiLoggerStatusBar(QStatusBar):
    """
    Always-visible status bar showing device and global status.

    Layout:
    [Device1] [Device2] [Device3] | [Saving] | [Errors] | [Time]
    """

    def __init__(self, data_holder, params, parent=None):
        super().__init__(parent)
        self.data_holder = data_holder
        self.params = params
        self.device_widgets = {}  # dev_id -> DeviceStatusWidget
        self.device_separators = {}  # dev_id -> VerticalSeparator (separator after this device)
        self.main_window = None  # Set by MainWindow after creation

        # Set fixed height
        self.setFixedHeight(30)

        # Create container widget for device status widgets
        self.device_container = QWidget()
        self.device_container.setStyleSheet("background-color: #FFFFFF;")  # White background
        self.device_layout = QHBoxLayout(self.device_container)
        self.device_layout.setContentsMargins(0, 0, 0, 0)
        self.device_layout.setSpacing(5)
        self.device_layout.addStretch()  # Push devices to the left

        self.addWidget(self.device_container, 1)  # Stretch factor 1

        # Create global status widgets
        self._create_global_widgets()

        # Set style
        self.setStyleSheet("""
            QStatusBar {
                border-top: 1px solid #ccc;
                background-color: #FFFFFF;
            }
        """)

    def _create_global_widgets(self):
        """Create global status widgets (saving, errors, time)."""
        # Saving status
        self.saving_label = PersistentTooltipLabel("✗ Not Saving")
        self.saving_label.setStyleSheet("""
            padding: 2px 8px;
            color: #424242;
            background-color: transparent;
        """)
        self.saving_label.setToolTip("Data saving is disabled")
        self.saving_label.setAttribute(Qt.WA_Hover, True)  # Enable hover for tooltips

        # Set minimum width to prevent jittering (use longest text)
        font_metrics = QFontMetrics(self.saving_label.font())
        saving_width = font_metrics.horizontalAdvance("✗ Not Saving") + 20  # +20 for padding
        self.saving_label.setMinimumWidth(saving_width)

        self.addPermanentWidget(self.saving_label)

        # Error count
        self.error_label = PersistentTooltipLabel("Errors: 0")
        self.error_label.setStyleSheet("""
            padding: 2px 8px;
            color: #2E7D32;
            background-color: transparent;
        """)
        self.error_label.setToolTip("No errors")
        self.error_label.setCursor(QCursor(Qt.PointingHandCursor))
        self.error_label.setAttribute(Qt.WA_Hover, True)  # Enable hover for tooltips

        # Set minimum width to prevent jittering (handle up to 99 errors)
        font_metrics = QFontMetrics(self.error_label.font())
        error_width = font_metrics.horizontalAdvance("Errors: 99") + 20  # +20 for padding
        self.error_label.setMinimumWidth(error_width)

        self.addPermanentWidget(self.error_label)

        # Time
        self.time_label = PersistentTooltipLabel("--:--:--")

        # Set monospace font programmatically (not via CSS) to ensure fixed-width
        time_font = QFont()
        time_font.setFamily("Courier New")  # Good cross-platform monospace
        time_font.setStyleHint(QFont.TypeWriter)  # TypeWriter is stricter than Monospace
        time_font.setFixedPitch(True)  # Ensure fixed pitch
        self.time_label.setFont(time_font)

        # Remove font-family from stylesheet to avoid CSS/QFont conflicts
        # Use dark gray color to ensure visibility
        self.time_label.setStyleSheet("padding: 2px 8px; background-color: transparent; color: #424242;")
        self.time_label.setToolTip("Current time")
        self.time_label.setAttribute(Qt.WA_Hover, True)  # Enable hover for tooltips

        # Calculate width using the ACTUAL font, with widest possible digits
        font_metrics = QFontMetrics(time_font)
        time_width = font_metrics.horizontalAdvance("88:88:88") + 20  # Widest digits + padding
        self.time_label.setFixedWidth(time_width)  # Use setFixedWidth to prevent any jitter

        self.addPermanentWidget(self.time_label)

    def add_device_status(self, dev_id, device_name):
        """Add a device to the status bar."""
        if dev_id in self.device_widgets:
            return  # Already exists

        # Create device widget
        device_widget = DeviceStatusWidget(dev_id, device_name, self)
        self.device_widgets[dev_id] = device_widget

        # Add separator before the device if there are already other devices
        # (so we have: Device1 | Device2 | Device3)
        if len(self.device_widgets) > 1:
            separator = VerticalSeparator(self)
            self.device_separators[dev_id] = separator
            # Insert separator before the stretch
            self.device_layout.insertWidget(self.device_layout.count() - 1, separator)

        # Add device widget to layout (before the stretch)
        self.device_layout.insertWidget(self.device_layout.count() - 1, device_widget)

    def remove_device_status(self, dev_id):
        """Remove a device from the status bar."""
        if dev_id not in self.device_widgets:
            return

        # Remove device widget from layout and delete
        widget = self.device_widgets[dev_id]
        self.device_layout.removeWidget(widget)
        widget.deleteLater()
        del self.device_widgets[dev_id]

        # Remove associated separator if it exists
        if dev_id in self.device_separators:
            separator = self.device_separators[dev_id]
            self.device_layout.removeWidget(separator)
            separator.deleteLater()
            del self.device_separators[dev_id]

    def update_device_status(self, dev_id):
        """
        Update status for a specific device.

        Extracts current connection, value, and error state.
        """
        if dev_id not in self.device_widgets:
            return

        # Get device parameter
        device_param = None
        for dev in self.params.child('Device settings').children():
            if dev.child('DevID').value() == dev_id:
                device_param = dev
                break

        if not device_param:
            return

        # Get connection status
        connected = device_param.child('Connected').value()

        # Get error status
        has_error = self.data_holder.device_errors.get(dev_id, False)

        # Get current value from device widget using get_status_bar_text()
        value = self._get_device_value(dev_id)

        # Update widget
        self.device_widgets[dev_id].update_status(
            connected=connected,
            value=value,
            has_error=has_error,
            error_msg=""
        )

    def _get_device_value(self, dev_id):
        """
        Get current measurement value for a device.

        Calls the device's get_status_bar_text() method.
        """
        # Get device widget from data_holder
        if not hasattr(self.data_holder, 'device_widgets'):
            return ""

        device_widget = self.data_holder.device_widgets.get(dev_id)
        if not device_widget:
            return ""

        # Call device's get_status_bar_text() method
        if hasattr(device_widget, 'get_status_bar_text'):
            try:
                return device_widget.get_status_bar_text()
            except Exception as e:
                print(f"Error getting status bar text for dev_id {dev_id}: {e}")
                return ""

        # Fallback
        return "Connected" if hasattr(device_widget, 'current_data') and device_widget.current_data else ""

    def update_all_devices(self):
        """Update status for all devices."""
        for dev_id in list(self.device_widgets.keys()):
            self.update_device_status(dev_id)

    def update_global_status(self):
        """Update global status (saving, errors, time)."""
        # Update saving status
        save_data = self.params.child('Data settings').child('Save data').value()
        saving_status = self.data_holder.saving_status

        if not save_data:
            self.saving_label.setText("✗ Not Saving")
            self.saving_label.setStyleSheet("padding: 2px 8px; color: #424242; background-color: transparent;")
            self.saving_label.setToolTip("Data saving is disabled")
        elif saving_status == 1:
            # Build tooltip with timestamp and file info
            tooltip_parts = ["<b>Data is being saved successfully</b>"]

            # Add last write timestamp
            if self.data_holder.last_write_timestamp is not None:
                last_write_dt = dt.fromtimestamp(self.data_holder.last_write_timestamp)
                last_write_str = last_write_dt.strftime("%H:%M:%S")
                tooltip_parts.append(f"<br><br><b>Last write:</b> {last_write_str}")

            # Add file path
            if self.data_holder.file_path:
                tooltip_parts.append(f"<br><b>Path:</b> {self.data_holder.file_path}")

            # Add most recent filename
            if self.data_holder.most_recent_filename:
                tooltip_parts.append(f"<br><b>File:</b> {self.data_holder.most_recent_filename}")

            self.saving_label.setText("✓ Saving")
            self.saving_label.setStyleSheet("padding: 2px 8px; color: #2E7D32; background-color: transparent;")  # Dark green
            self.saving_label.setToolTip("".join(tooltip_parts))
        else:
            self.saving_label.setText("! Save Error")
            self.saving_label.setStyleSheet("padding: 2px 8px; color: #FFFFFF; background-color: #D32F2F; border-radius: 3px;")  # White text on dark red for consistency
            self.saving_label.setToolTip("Error occurred while saving data")

        # Update error count
        error_count = sum(1 for has_error in self.data_holder.device_errors.values() if has_error)

        if error_count == 0:
            self.error_label.setText("Errors: 0")
            self.error_label.setStyleSheet("padding: 2px 8px; color: #2E7D32; background-color: transparent;")  # Dark green
            self.error_label.setToolTip("No errors")
        else:
            self.error_label.setText(f"Errors: {error_count}")
            self.error_label.setStyleSheet("padding: 2px 8px; color: #FFFFFF; background-color: #F57C00; border-radius: 3px;")  # White text on dark orange for consistency

            # Build error tooltip
            error_devices = []
            for dev in self.params.child('Device settings').children():
                dev_id = dev.child('DevID').value()
                if self.data_holder.device_errors.get(dev_id, False):
                    device_name = dev.child('Device nickname').value() or dev.name()
                    error_devices.append(f"• {device_name}")

            tooltip = "<b>Devices with errors:</b><br>" + "<br>".join(error_devices)
            self.error_label.setToolTip(tooltip)

        # Update time
        if hasattr(self.data_holder, 'current_time'):
            timestamp = dt.fromtimestamp(self.data_holder.current_time)
            time_str = timestamp.strftime("%H:%M:%S")
            self.time_label.setText(time_str)
        else:
            self.time_label.setText("--:--:--")

    def device_clicked(self, dev_id):
        """Handle device widget click - switch to that device's tab."""
        if not self.main_window:
            return

        # Find the tab index for this device
        device_tabs = self.main_window.device_tabs

        for i in range(device_tabs.count()):
            tab_widget = device_tabs.widget(i)
            if hasattr(tab_widget, 'dev_id') and tab_widget.dev_id == dev_id:
                device_tabs.setCurrentIndex(i)
                return
