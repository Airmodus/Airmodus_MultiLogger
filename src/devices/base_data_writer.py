"""
Base class for device data writing logic.

This module provides an abstract base class that defines the interface for
writing device data to files. Each device type can implement its own DataWriter
subclass to handle device-specific file formats, headers, and special cases.

The design follows the same composition pattern as the plotting system
(BasePlotConfig), allowing the DataLogger to be generic and device-agnostic.
"""

from abc import ABC, abstractmethod


class BaseDataWriter(ABC):
    """
    Abstract base class for device data writing.

    Each device type should implement this interface to define:
    - What file types it writes (.dat, .par, .csv, etc.)
    - File headers for each file type
    - Data formatting logic
    - Special file handling (e.g., 10Hz logging)

    This allows the DataLogger to be completely generic and work with
    any device through polymorphism.
    """

    def __init__(self, device_widget):
        """
        Initialize the data writer with a reference to its device.

        Args:
            device_widget: The device widget instance (CPCWidget, PSMWidget, etc.)
        """
        self.device = device_widget

    def get_file_types(self):
        """
        Return list of file types this device writes.

        Returns:
            list: File extensions without dots (e.g., ['dat'], ['dat', 'par'])
        """
        return ['dat']  # Default: only .dat file

    def get_dat_filename_suffix(self):
        """
        Return suffix for .dat filename for special cases.

        For example, CPC 10Hz mode might return '10hz'.
        Most devices return empty string.

        Returns:
            str: Filename suffix (without underscore) or empty string
        """
        return ''

    @abstractmethod
    def get_dat_header(self):
        """
        Return the header line for the .dat file.

        Must include timestamp column and all data columns.
        Format: 'YYYY.MM.DD hh:mm:ss,column1,column2,...'

        Returns:
            str: Complete header line (without newline)
        """
        raise NotImplementedError("Subclasses must implement get_dat_header()")

    def get_par_header(self):
        """
        Return the header line for the .par file (if applicable).

        Only devices that write .par files need to implement this.
        Format: 'YYYY.MM.DD hh:mm:ss,param1,param2,...'

        Returns:
            str: Complete header line (without newline), or None if not applicable
        """
        return None  # Most devices don't have .par files

    def get_dat_data(self, device_param, data_holder, timestamp_str):
        """
        Return the data string to write to .dat file.

        Default implementation uses the device's current_data.to_array().
        Override for custom formatting.

        Args:
            device_param: The device parameter from parameter tree
            data_holder: The DataHolder instance
            timestamp_str: Formatted timestamp string

        Returns:
            str: Comma-separated data values (without timestamp or newline)
        """
        data_array = self.device.current_data.to_array()
        return ','.join(str(val) for val in data_array)

    def should_write_dat(self, device_param, data_holder):
        """
        Check if .dat file should be written this cycle.

        Most devices always write. Override for conditional writing.

        Args:
            device_param: The device parameter from parameter tree
            data_holder: The DataHolder instance

        Returns:
            bool: True if data should be written
        """
        return True  # Default: always write

    def should_write_par(self, device_param, data_holder):
        """
        Check if .par file should be written this cycle.

        Typically checks par_updates flag in data_holder.

        Args:
            device_param: The device parameter from parameter tree
            data_holder: The DataHolder instance

        Returns:
            bool: True if settings should be written
        """
        return False  # Default: no .par file

    def get_par_data(self, device_param, data_holder, timestamp_str):
        """
        Return the data string to write to .par file.

        Typically uses the device's settings.to_array().

        Args:
            device_param: The device parameter from parameter tree
            data_holder: The DataHolder instance
            timestamp_str: Formatted timestamp string

        Returns:
            str: Comma-separated settings values (without timestamp or newline),
                 or None if not applicable
        """
        return None  # Default: no .par file

    def has_special_files(self, device_param):
        """
        Check if device needs special file handling.

        For example, CPC with 10Hz logging enabled.

        Args:
            device_param: The device parameter from parameter tree

        Returns:
            bool: True if special files need to be written
        """
        return False  # Default: no special files

    def write_special_files(self, device_param, data_holder, timestamp_str, filenames_dict):
        """
        Write any special files (override in subclasses).

        This method is called if has_special_files() returns True.
        The subclass is responsible for all file creation and writing.

        Args:
            device_param: The device parameter from parameter tree
            data_holder: The DataHolder instance
            timestamp_str: Formatted timestamp string
            filenames_dict: Dictionary to store special filenames
        """
        pass  # Default: no special files
