"""
Base class for all device widgets in Airmodus MultiLogger.

This module provides the abstract base class that all device implementations
should inherit from. It defines the common interface and shared functionality
for device widgets, data management, and serial communication parsing.
"""

from abc import ABCMeta, abstractmethod
from PyQt5.QtWidgets import QTabWidget
from numpy import full, nan


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
        latest_data: Current measurement values
        latest_settings: Current device settings (for complex devices)
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

        # Data storage (device state)
        self.latest_data = None
        self.latest_settings = None
        self.errors = {}

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
    def parse_message(self, message, data_holder=None):
        """
        Parse a serial message from the device.

        This method handles device-specific protocol parsing and updates
        the device's internal state (latest_data, latest_settings, errors).

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

    def format_data_for_logging(self):
        """
        Format current device data for writing to log file.

        Override this method to provide device-specific formatting.
        Default implementation returns latest_data as-is.

        Returns:
            str or list: Formatted data ready for file writing
        """
        if self.latest_data is not None:
            return self.latest_data
        return []

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


class SimpleDevice(BaseDevice):
    """
    Base class for simple plot-only devices.

    Simple devices only display plots and don't have control interfaces,
    status displays, or settings. Examples: CO2, RHTP, AFM, TSI_CPC, Electrometer.

    This class provides default implementations for simple devices that
    auto-push data over serial without requiring read commands.
    """

    def get_read_command(self):
        """
        Simple devices typically auto-push data or have basic commands.
        Override if device needs a specific read command.
        """
        return None

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
            self.latest_data = data

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


__all__ = ['BaseDevice', 'SimpleDevice', 'ComplexDevice']
