"""
Custom COM port selector widget that combines a text input with a dropdown selector.
Enhanced with status indicators for port availability.
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from pyqtgraph.parametertree import Parameter, registerParameterType
from pyqtgraph.parametertree.parameterTypes import WidgetParameterItem
import platform


class ComPortWidget(QtWidgets.QWidget):
    """
    Custom widget combining a QLineEdit with a dropdown button for port selection.
    The text field allows manual entry, while the dropdown provides quick selection
    from available ports with status indicators.
    """

    sigChanged = QtCore.pyqtSignal(object)  # Signal for pyqtgraph compatibility
    sigValueChanged = QtCore.pyqtSignal(object)  # Emits the port value

    # Status indicator colors and symbols
    STATUS_INDICATORS = {
        'available': ('🟢', '#4CAF50', 'Available'),
        'in_use': ('🔴', '#F44336', 'In Use'),
        'connected': ('🟡', '#FFC107', 'Connected'),
        'error': ('⚠️', '#FF9800', 'Error'),
        'permission_denied': ('🔒', '#9E9E9E', 'Permission Denied'),
        'unknown': ('❓', '#607D8B', 'Unknown')
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_osx = platform.system() == 'Darwin'
        self.available_ports = {}  # Will store {display_text: port_value}
        self.port_statuses = {}  # Will store {port_value: status}
        self.port_info = {}  # Will store {port_value: {serial_number, device_type, etc}}

        # Create layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create text input field
        self.line_edit = QtWidgets.QLineEdit()
        self.line_edit.setPlaceholderText("Enter COM port...")

        # Create dropdown button
        self.dropdown_button = QtWidgets.QToolButton()
        self.dropdown_button.setText("▼")
        self.dropdown_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)

        # Create menu for dropdown with custom styling
        self.menu = QtWidgets.QMenu(self)
        self.dropdown_button.setMenu(self.menu)

        # Apply styling for better visual appearance
        self.menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #ddd;
                padding: 5px 0px;
            }
            QMenu::item {
                padding: 5px 30px 5px 25px;
                min-width: 200px;
            }
            QMenu::item:selected {
                background-color: #e3f2fd;
            }
        """)

        # Add widgets to layout
        layout.addWidget(self.line_edit)
        layout.addWidget(self.dropdown_button)

        # Connect signals
        self.line_edit.textChanged.connect(self._on_manual_change)

    def _on_manual_change(self):
        """Handle manual text entry in the line edit."""
        value = self.line_edit.text()
        # Convert to appropriate type
        if not self.is_osx:
            # On Windows/Linux, try to convert to int
            try:
                value = int(value)
            except ValueError:
                pass  # Keep as string if not a valid integer
        self.sigChanged.emit(self)  # Emit for pyqtgraph compatibility
        self.sigValueChanged.emit(value)

    def _on_port_selected(self, port_value):
        """Handle selection from dropdown menu."""
        if port_value is None or port_value == "No ports available":
            return

        # Extract the appropriate part based on platform
        if self.is_osx:
            # On macOS, use the full path (everything before the dash)
            display_value = port_value
        else:
            # On Windows, extract just the number from COM3 -> 3
            if port_value.startswith('COM'):
                try:
                    display_value = str(int(port_value[3:]))
                except ValueError:
                    display_value = port_value
            else:
                display_value = port_value

        # Update the text field (this will trigger sigValueChanged via _on_manual_change)
        self.line_edit.setText(display_value)

    def set_available_ports(self, ports_dict, port_statuses=None, port_info=None):
        """
        Update the available ports in the dropdown with optional status indicators.

        Args:
            ports_dict: Dictionary mapping "PORT - Description" to port value
                       e.g., {"COM3 - Device Name": "COM3", ...}
            port_statuses: Optional dict mapping port_value to status
                          e.g., {"COM3": "available", "COM4": "in_use"}
            port_info: Optional dict mapping port_value to additional info
                      e.g., {"COM3": {"device_type": "CPC", "serial_number": "12345"}}
        """
        self.available_ports = ports_dict
        self.port_statuses = port_statuses or {}
        self.port_info = port_info or {}

        # Save current selection to preserve it
        current_value = self.value()

        # Clear existing menu
        self.menu.clear()

        # Populate menu with new ports
        if not ports_dict or len(ports_dict) == 0:
            action = self.menu.addAction("No ports available")
            action.setEnabled(False)
        else:
            # Sort items alphabetically to maintain stable order
            for display_text, port_value in sorted(ports_dict.items()):
                if port_value is None:  # Skip the "Select port..." entry
                    continue

                # Get status for this port
                status = self.port_statuses.get(port_value, 'unknown')
                indicator, color, status_text = self.STATUS_INDICATORS.get(
                    status, self.STATUS_INDICATORS['unknown']
                )

                # Get additional info if available
                info = self.port_info.get(port_value, {})
                device_type = info.get('device_type', '')
                serial_number = info.get('serial_number', '')

                # Build display text with status indicator
                if device_type and device_type != 'Unknown':
                    # Include detected device type
                    menu_text = f"{indicator} {display_text} [{device_type}]"
                else:
                    menu_text = f"{indicator} {display_text}"

                # Create action with enhanced tooltip
                action = self.menu.addAction(menu_text)

                # Set tooltip with detailed information
                tooltip_parts = [f"Port: {port_value}", f"Status: {status_text}"]
                if serial_number:
                    tooltip_parts.append(f"Serial: {serial_number}")
                if device_type and device_type != 'Unknown':
                    tooltip_parts.append(f"Type: {device_type}")
                action.setToolTip('\n'.join(tooltip_parts))

                # Disable if port is in use or has error (but not if just selected)
                if status in ['in_use', 'error', 'permission_denied']:
                    action.setEnabled(False)

                # Use lambda with default argument to capture port_value
                action.triggered.connect(
                    lambda checked=False, pv=port_value: self._on_port_selected(pv)
                )

        # Restore the previous selection if it's still valid
        if current_value:
            self.setValue(current_value)

    def value(self):
        """Get the current value from the line edit."""
        value = self.line_edit.text()
        if not self.is_osx:
            # On Windows/Linux, convert to int if possible
            try:
                value = int(value)
            except ValueError:
                pass
        return value

    def setValue(self, value):
        """Set the value in the line edit."""
        # Block signals to avoid triggering sigValueChanged when setting programmatically
        self.line_edit.blockSignals(True)
        try:
            if value is None:
                self.line_edit.setText("")
            else:
                self.line_edit.setText(str(value))
        finally:
            self.line_edit.blockSignals(False)


class ComPortParameterItem(WidgetParameterItem):
    """
    Parameter item that creates and manages the ComPortWidget.
    """

    def makeWidget(self):
        """Create the custom COM port widget."""
        widget = ComPortWidget()
        widget.sigValueChanged.connect(self.widgetValueChanged)

        # Set initial available ports if provided in parameter options
        if 'ports' in self.param.opts:
            port_statuses = self.param.opts.get('port_statuses', None)
            port_info = self.param.opts.get('port_info', None)
            widget.set_available_ports(self.param.opts['ports'], port_statuses, port_info)

        return widget

    def widgetValueChanged(self):
        """Called when the widget value changes."""
        # Get value from widget and update parameter
        value = self.widget.value()
        self.param.setValue(value)


class ComPortParameter(Parameter):
    """
    Custom parameter type for COM port selection with combined text input and dropdown.
    """
    itemClass = ComPortParameterItem

    def __init__(self, **opts):
        # Set default options
        if 'type' not in opts:
            # Default to 'str' on macOS, 'int' on Windows/Linux
            opts['type'] = 'str' if platform.system() == 'Darwin' else 'int'

        super().__init__(**opts)

    def set_available_ports(self, ports_dict, port_statuses=None, port_info=None):
        """
        Update the available ports in the dropdown with optional status indicators.

        Args:
            ports_dict: Dictionary mapping "PORT - Description" to port value
            port_statuses: Optional dict mapping port_value to status
            port_info: Optional dict with additional port information
        """
        self.setOpts(ports=ports_dict, port_statuses=port_statuses, port_info=port_info)

        # Update the widget if it exists
        if hasattr(self, 'items') and len(self.items) > 0:
            for item in self.items:
                if hasattr(item, 'widget') and item.widget is not None:
                    item.widget.set_available_ports(ports_dict, port_statuses, port_info)


# Register the custom parameter type with pyqtgraph
registerParameterType('comport', ComPortParameter, override=True)
