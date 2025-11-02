"""
Base class for all device widgets in Airmodus MultiLogger.

This module provides the abstract base class that all device implementations
should inherit from. It defines the common interface and shared functionality
for device widgets, data management, and serial communication parsing.
"""

from abc import ABCMeta, abstractmethod
from PyQt5.QtWidgets import QTabWidget
from numpy import full, nan
from devices.device_data import create_device_data, create_device_settings


# Create a metaclass that combines Qt's metaclass with ABC's metaclass
class QABCMeta(type(QTabWidget), ABCMeta):
    """Metaclass that combines PyQt5's wrapper type with ABC's metaclass."""
    pass


class BaseDevice(QTabWidget, metaclass=QABCMeta):
    """
    Abstract base class for all device widgets.

    All device classes should inherit from this base class and implement
    the required abstract methods. This ensures a consistent interface
    across all devices and makes it easy to add new device types.

    Attributes:
        device_parameter: Reference to the device's parameter tree
        name: Device name from parameter tree
        dev_id: Device ID for tracking
        dev_type: Device type constant from config
        plot_tab: Widget for plotting device data
        current_data: Typed dataclass containing current measurement values
        settings: Typed dataclass containing device settings (for complex devices)
        errors: Current error state
    """

    def __init__(self, device_parameter, device_type=None, *args, **kwargs):
        """
        Initialize base device.

        Args:
            device_parameter: Parameter tree reference for this device
            device_type: Device type constant from config (optional)
            *args, **kwargs: Additional arguments passed to QTabWidget
        """
        super().__init__()
        self.device_parameter = device_parameter
        self.name = device_parameter.name()
        self.dev_id = None  # Will be set by app when device is added
        self.dev_type = device_type
        self.plot_tab = None  # Should be set by subclass

        # Data storage (device owns its data now)
        self.current_data = create_device_data(device_type) if device_type else None
        self.settings = create_device_settings(device_type)
        self.errors = {}

        # Serial communication state
        self._partial_data = ""  # Buffer for incomplete messages (PSM, eDiluter)

        # Command logging (for .par files)
        self.latest_command = None  # Latest user-entered command message

        # Multi-message buffering timeout counter
        self._extra_data_counter = 0  # Used by PSM to clear stale buffers after 60s

    @abstractmethod
    def get_read_command(self):
        """
        Get the serial command to read data from this device.

        Returns:
            str or list: Command string(s) to send to device for reading data.
                        Can return None if device auto-pushes data.

        Example:
            return ":MEAS:ALL"  # For CPC
            return [":MEAS:SCAN", ":MEAS:STEP", ":MEAS:FIXD"]  # For PSM (handles multiple)
        """
        pass

    @abstractmethod
    def get_plot_keys(self):
        """
        Get the plot key suffixes for this device.

        This method defines which plot data arrays should be created for this device.
        Keys are combined with device ID to form plot_data dict keys.

        Returns:
            list of str: Plot key suffixes (e.g., ['', ':raw'] for CPC with two channels)
                        Single-value devices return ['']
                        Multi-channel devices return [':suffix1', ':suffix2', ...]

        Examples:
            CPC: ['', ':raw'] → creates plot_data['5'] and plot_data['5:raw']
            ELECTROMETER: [':1', ':2', ':3'] → creates plot_data['3:1'], plot_data['3:2'], plot_data['3:3']
            PSM: [''] → creates plot_data['7']
        """
        pass

    def get_rolling_buffer_keys(self):
        """
        Get rolling buffer configurations for long-term data storage.

        Override this method in devices that need rolling buffers separate from
        standard plot data (e.g., CPC pulse analysis 24h buffers).

        Returns:
            dict: {key_suffix: buffer_size} or {} if no rolling buffers
                 key_suffix: Plot key suffix (e.g., ':pd', ':pr')
                 buffer_size: Number of elements (e.g., 86400 for 24 hours at 1 Hz)

        Example:
            CPC: {':pd': 86400, ':pr': 86400} → 24-hour pulse duration/ratio buffers
            Most devices: {} → no rolling buffers needed
        """
        return {}

    # Device Manager Integration Methods
    # These methods allow devices to control their own lifecycle and behavior
    # without device_manager needing device-type checks

    def supports_idn_inquiry(self):
        """
        Whether device supports *IDN? identity inquiry.

        Override to return True for devices that respond to *IDN? command.

        Returns:
            bool: True if device supports IDN inquiry, False otherwise
        """
        return False

    def supports_firmware_inquiry(self):
        """
        Whether device supports firmware version inquiry.

        Override to return True for devices that have firmware version commands.

        Returns:
            bool: True if device supports firmware inquiry, False otherwise
        """
        return False

    def has_command_widget(self):
        """
        Whether device has a command widget for showing connection messages.

        Override to return True for devices with set_tab.command_widget.

        Returns:
            bool: True if device has command widget, False otherwise
        """
        return False

    def has_status_tab(self):
        """
        Whether device has a status tab for error icon display.

        Override to return True for devices with status_tab.

        Returns:
            bool: True if device has status tab, False otherwise
        """
        return False

    def get_status_tab(self):
        """
        Get the status tab widget for error icon display.

        Override to return the status_tab attribute if it exists.

        Returns:
            QWidget or None: Status tab widget or None
        """
        return None

    def has_device_specific_errors(self):
        """
        Whether device has additional device-specific error states beyond standard errors.

        Override to return True for devices with special error conditions
        (e.g., PSM CO flow error).

        Returns:
            bool: True if device has specific error states, False otherwise
        """
        return False

    def supports_10hz_mode(self):
        """
        Whether device supports 10 Hz logging mode.

        Override to return True for devices that have 10 Hz mode (CPC, PSM).

        Returns:
            bool: True if device supports 10 Hz mode, False otherwise
        """
        return False

    def on_connection_established(self, device_param):
        """
        Called when device connection is established.

        Override to perform device-specific connection setup like:
        - Clearing firmware version
        - Resetting dilution parameters
        - Initializing device state

        Args:
            device_param: Parameter tree reference for this device
        """
        pass

    def on_disconnection(self, device_param):
        """
        Called when device disconnects.

        Override to perform device-specific cleanup like:
        - Showing disconnection message
        - Resetting state

        Args:
            device_param: Parameter tree reference for this device
        """
        pass

    def send_read_commands(self, dev_conn, device_param):
        """
        Send device-specific read commands to request data.

        Override to implement device-specific command sending logic like:
        - CPC: Pulse analysis, 10Hz mode, or normal commands
        - PSM: Settings fetch, dilution parameters
        - ELECTROMETER: Buffer reset + measurement command
        - Auto-push devices: Do nothing

        Args:
            dev_conn: Connection object with send_message() method
            device_param: Parameter tree reference for this device
        """
        pass

    def validate_10hz_mode(self, params, device_param):
        """
        Validate and synchronize 10 Hz mode settings.

        Override in devices that support 10 Hz mode to implement:
        - CPC: Manage TAVG based on 10Hz state, validate PSM connection
        - PSM: Ensure connected CPC has 10Hz enabled

        Args:
            params: Root parameter tree (for accessing other devices)
            device_param: Parameter tree reference for this device
        """
        pass

    @abstractmethod
    def parse_message(self, message, data_holder=None):
        """
        Parse a serial message from the device.

        This method handles device-specific protocol parsing and updates
        the device's internal state (current_data, latest_settings, errors).

        Args:
            message: Raw message string from serial connection
            data_holder: Reference to DataHolder for accessing shared state

        Returns:
            dict: Parsed data with keys:
                - 'type': Message type ('data', 'settings', 'error', 'info', 'unknown')
                - 'data': Parsed data array/dict (for 'data' type)
                - 'settings': Parsed settings (for 'settings' type)
                - 'command': Original command name
                - 'raw': Raw message for logging
                - 'update_gui': Boolean indicating if GUI should be updated

        Example return:
            {
                'type': 'data',
                'data': [1.5, 2.3, ...],
                'command': ':MEAS:ALL',
                'raw': ':MEAS:ALL 1.5,2.3,...',
                'update_gui': True
            }
        """
        pass

    def update_values(self, current_list):
        """
        Update GUI with current measurement values.

        Override this method in devices that have a status display tab.
        Simple devices (plot-only) don't need to implement this.

        Args:
            current_list: List of current measurement values
        """
        pass

    def update_settings(self, settings):
        """
        Update GUI with current device settings.

        Override this method in devices that have settings displays.
        Simple devices don't need to implement this.

        Args:
            settings: List or dict of device settings
        """
        pass

    def update_errors(self, status_hex, *args):
        """
        Update error indicators in GUI based on status value.

        Override this method in devices that have error monitoring.
        Simple devices don't need to implement this.

        Args:
            status_hex: Hexadecimal status code from device
            *args: Additional device-specific error parameters

        Returns:
            int: Total number of errors (0 if no errors)
        """
        return 0

    def get_column_headers(self):
        """
        Get column headers for data log file.

        Override this method to provide device-specific column names.

        Returns:
            list: List of column header strings
        """
        return []

    def set_device_id(self, dev_id):
        """
        Set the device ID after initialization.

        Called by app.py when device is added to the system.

        Args:
            dev_id: Unique device identifier
        """
        self.dev_id = dev_id

    def initialize_data(self, default_value=nan):
        """
        Initialize data storage with default values.

        Can be overridden for device-specific initialization.

        Args:
            default_value: Default value to use (default: nan)
        """
        # Subclasses can override to set appropriate data structure
        pass

    def handle_idn_response(self, serial_number):
        """
        Handle device identification response.

        Override if device needs special handling of IDN response.

        Args:
            serial_number: Serial number from *IDN response

        Returns:
            bool: True if handled successfully
        """
        return True

    def handle_firmware_response(self, firmware_version):
        """
        Handle firmware version response.

        Override if device needs special handling of firmware response.

        Args:
            firmware_version: Firmware version string

        Returns:
            bool: True if handled successfully
        """
        return True

    def handle_serial_data(self, connection, data_holder=None):
        """
        Read and process serial data from device connection.

        This is the main entry point for device communication. Override this
        method if device needs special serial handling (e.g., partial message
        buffering, multiple read commands).

        Default implementation:
        1. Reads all available data from serial connection
        2. Splits into messages by \\r
        3. Calls parse_message() for each message
        4. Returns list of parsed results

        Args:
            connection: Serial connection object (has .connection attribute)
            data_holder: Reference to DataHolder for accessing shared state

        Returns:
            list: List of parsed message dictionaries from parse_message()
        """
        results = []
        try:
            # Read all available data
            raw_data = connection.connection.read_all()
            if not raw_data:
                return results

            # Decode and split into messages
            messages = raw_data.decode().split("\r")[:-1]  # Remove last empty element

            # Parse each message
            for message in messages:
                if message:  # Skip empty messages
                    parsed = self.parse_message(message, data_holder)
                    results.append(parsed)

        except Exception as e:
            results.append({
                'type': 'error',
                'command': 'serial_read',
                'data': None,
                'error': str(e),
                'raw': '',
                'update_gui': False
            })

        return results

    def process_parsed_messages(self, parsed_messages, device_param, data_holder):
        """
        Process parsed messages and update device state.

        This method is called by DeviceManager after handle_serial_data().
        Override this to add device-specific post-processing logic like:
        - Managing data buffers
        - Updating GUI elements
        - Compiling settings
        - Special error handling

        Default implementation handles simple data storage.

        Args:
            parsed_messages: List of parsed message dicts from handle_serial_data()
            device_param: Parameter tree reference for this device
            data_holder: Reference to DataHolder for shared state

        Returns:
            dict: Processing results with keys:
                - 'data_updated': bool, whether new data was received
                - 'settings_updated': bool, whether settings changed
                - 'needs_gui_update': bool, whether GUI should refresh
        """
        result = {
            'data_updated': False,
            'settings_updated': False,
            'needs_gui_update': False
        }

        # Process each parsed message
        for parsed in parsed_messages:
            if parsed['type'] == 'data':
                # Data already stored in current_data by parse_message
                result['data_updated'] = True

            elif parsed['type'] == 'info' and parsed['command'] == '*IDN':
                # Handle device identification
                serial_number = parsed['data']
                if device_param.child('Serial number').value() != serial_number:
                    device_param.child('Serial number').setValue(serial_number)
                if self.dev_id in data_holder.idn_inquiry_devices:
                    data_holder.idn_inquiry_devices.remove(self.dev_id)

            elif parsed['type'] == 'error':
                # On error, reset current_data to defaults (handled in parse_message)
                pass

        return result


class SimpleDevice(BaseDevice):
    """
    Base class for simple plot-only devices.

    Simple devices only display plots and don't have control interfaces,
    status displays, or settings. Examples: CO2, RHTP, AFM, TSI_CPC, Electrometer.

    This class provides default implementations for simple devices that
    auto-push data over serial without requiring read commands.
    """

    def get_plot_keys(self):
        """
        Default: single-value devices return [''].
        Override in multi-channel devices (ELECTROMETER, RHTP, AFM).
        """
        return ['']

    def get_read_command(self):
        """
        Simple devices typically auto-push data or have basic commands.
        Override if device needs a specific read command.
        """
        return None

    # Helper methods for common parsing patterns
    def is_idn_response(self, message):
        """Check if message is an IDN response."""
        return message.startswith("*IDN ")

    def handle_standard_idn(self, message):
        """Parse and return standardized IDN response."""
        from utils import parse_idn_response
        return parse_idn_response(message)

    def data_response(self, message, command='data'):
        """
        Create data response dict with auto-conversion from current_data.

        Args:
            message: Raw message string
            command: Command name

        Returns:
            dict: Standardized data response with data from current_data.to_array()
        """
        from utils import create_data_response
        data_array = self.current_data.to_array() if hasattr(self.current_data, 'to_array') else []
        return create_data_response(message, command, data_array)

    def error_response(self, message, error, command='unknown'):
        """
        Create error response dict.

        Args:
            message: Raw message string
            error: Error message or Exception object
            command: Command name

        Returns:
            dict: Standardized error response
        """
        from utils import create_error_response
        return create_error_response(message, command, error)

    def send_read_commands(self, dev_conn, device_param):
        """
        Default implementation for simple read-command devices.

        Clears buffers and sends the read command from get_read_command().
        Override for more complex behavior.
        """
        cmd = self.get_read_command()
        if cmd:
            dev_conn.connection.reset_input_buffer()
            dev_conn.connection.reset_output_buffer()
            dev_conn.connection.read_all()
            dev_conn.send_message(cmd)

    def parse_message(self, message, data_holder=None):
        """
        Default parsing for simple devices.

        Most simple devices send data in format: "value1;value2;value3"
        Override for device-specific protocols.
        """
        try:
            # Handle IDN responses
            if message.startswith("*IDN "):
                serial_number = message[5:].strip()
                return {
                    'type': 'info',
                    'command': '*IDN',
                    'data': serial_number,
                    'raw': message,
                    'update_gui': False
                }

            # Default data parsing (semicolon-separated)
            data = message.split(";")

            return {
                'type': 'data',
                'data': data,
                'command': 'data',
                'raw': message,
                'update_gui': False  # Simple devices update via plot only
            }
        except Exception as e:
            return {
                'type': 'error',
                'command': 'unknown',
                'data': None,
                'raw': message,
                'error': str(e),
                'update_gui': False
            }


class ComplexDevice(BaseDevice):
    """
    Base class for complex devices with settings and status monitoring.

    Complex devices have multiple tabs (Set, Status, Plot, etc.) and require
    more sophisticated data handling, error monitoring, and settings management.
    Examples: CPC, PSM, eDiluter.
    """

    def __init__(self, device_parameter, device_type=None, *args, **kwargs):
        """Initialize complex device with additional tabs and widgets."""
        super().__init__(device_parameter, device_type, *args, **kwargs)
        self.set_tab = None  # Should be set by subclass
        self.status_tab = None  # Should be set by subclass

    @abstractmethod
    def update_values(self, current_list):
        """Complex devices must implement value updates for status tab."""
        pass

    @abstractmethod
    def update_settings(self, settings):
        """Complex devices must implement settings updates for set tab."""
        pass

    @abstractmethod
    def update_errors(self, status_hex, *args):
        """Complex devices must implement error monitoring."""
        pass

    # ComplexDevice default implementations

    def supports_idn_inquiry(self):
        """Complex devices typically support IDN inquiry."""
        return True

    def has_command_widget(self):
        """Complex devices have command widgets."""
        return True

    def on_disconnection(self, device_param):
        """Show disconnection message in command widget."""
        if self.set_tab and hasattr(self.set_tab, 'command_widget'):
            self.set_tab.command_widget.update_text_box("Device disconnected.")


class DefaultSinglePlotConfig:
    """
    Default plot configuration for simple single-value devices.

    This eliminates the need to create custom plot config classes for devices
    that only plot a single value from current_data.to_array()[0].
    """

    def __init__(self, device_widget):
        """Initialize with device widget reference."""
        self.device = device_widget

    def get_plot_keys(self):
        """Single value devices use empty string key."""
        return ['']

    def get_rolling_buffer_keys(self):
        """No rolling buffers by default."""
        return {}

    def get_plot_values(self, dev_id, time_counter, plot_data, device_param, data_holder=None):
        """Extract first value from device's current_data."""
        if self.device.current_data and hasattr(self.device.current_data, 'to_array'):
            data_array = self.device.current_data.to_array()
            if len(data_array) > 0:
                plot_data[str(dev_id)][time_counter] = data_array[0]

    def update_main_plot(self, dev_id, time_counter, x_time_list, plot_data,
                        curve, device_param, plot_to_main_value):
        """Update main plot with single value."""
        if plot_to_main_value:
            curve.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)][:time_counter+1]
            )
        else:
            curve.setData(x=[], y=[])

    def update_individual_plots(self, dev_id, time_counter, x_time_list, plot_data):
        """Update device's individual plot tab."""
        if hasattr(self.device, 'plot_tab') and self.device.plot_tab:
            if hasattr(self.device.plot_tab, 'curve'):
                self.device.plot_tab.curve.setData(
                    x=x_time_list[:time_counter+1],
                    y=plot_data[str(dev_id)][:time_counter+1]
                )

    def get_main_plot_key(self, selector_value=None):
        """Return empty string for single value."""
        return ''

    def get_viewbox_type(self):
        """Use device's own viewbox."""
        return self.device.dev_type

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """Get value to display in legend."""
        return plot_data[str(dev_id)][time_counter]

    def get_start_time_key(self):
        """Use primary key for start time detection."""
        return ''


__all__ = ['BaseDevice', 'SimpleDevice', 'ComplexDevice', 'DefaultSinglePlotConfig']
