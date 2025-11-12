"""
Custom COM port selector widget that combines a text input with a dropdown selector.
"""

from PyQt5 import QtWidgets, QtCore
from pyqtgraph.parametertree import Parameter, registerParameterType
from pyqtgraph.parametertree.parameterTypes import WidgetParameterItem
import platform


class ComPortWidget(QtWidgets.QWidget):
    """
    Custom widget combining a QLineEdit with a dropdown button for port selection.
    The text field allows manual entry, while the dropdown provides quick selection
    from available ports.
    """

    sigChanged = QtCore.pyqtSignal(object)  # Signal for pyqtgraph compatibility
    sigValueChanged = QtCore.pyqtSignal(object)  # Emits the port value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_osx = platform.system() == 'Darwin'
        self.available_ports = {}  # Will store {display_text: port_value}

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

        # Create menu for dropdown
        self.menu = QtWidgets.QMenu(self)
        self.dropdown_button.setMenu(self.menu)

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

    def set_available_ports(self, ports_dict):
        """
        Update the available ports in the dropdown.

        Args:
            ports_dict: Dictionary mapping "PORT - Description" to port value
                       e.g., {"COM3 - Device Name": "COM3", ...}
        """
        self.available_ports = ports_dict

        # Clear existing menu
        self.menu.clear()

        # Populate menu with new ports
        if not ports_dict or len(ports_dict) == 0:
            action = self.menu.addAction("No ports available")
            action.setEnabled(False)
        else:
            for display_text, port_value in ports_dict.items():
                if port_value is None:  # Skip the "Select port..." entry
                    continue
                action = self.menu.addAction(display_text)
                # Use lambda with default argument to capture port_value
                action.triggered.connect(
                    lambda checked=False, pv=port_value: self._on_port_selected(pv)
                )

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
            widget.set_available_ports(self.param.opts['ports'])

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

    def set_available_ports(self, ports_dict):
        """
        Update the available ports in the dropdown.

        Args:
            ports_dict: Dictionary mapping "PORT - Description" to port value
        """
        self.setOpts(ports=ports_dict)

        # Update the widget if it exists
        if hasattr(self, 'items') and len(self.items) > 0:
            for item in self.items:
                if hasattr(item, 'widget') and item.widget is not None:
                    item.widget.set_available_ports(ports_dict)


# Register the custom parameter type with pyqtgraph
registerParameterType('comport', ComPortParameter, override=True)
