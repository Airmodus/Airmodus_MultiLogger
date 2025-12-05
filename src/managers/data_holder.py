from numpy import full, nan
from time import time
from utils import _manage_plot_array
from config import (CPC, PSM, ELECTROMETER, CO2_SENSOR, RHTP, AFM, EDILUTER, EXAMPLE_DEVICE, PSM2, TSI_CPC, AFC)

class DataHolder:
    """Holds all app data dicts/lists. No logic—just storage."""
    def __init__(self):

        # Data related - multi-message buffering (shared coordination state)
        self.extra_data = {} # contains extra data, used when multiple data prints are received at once
        # Plot related
        self.plot_data = {} # contains plotted values
        self.curve_dict = {} # contains curve objects for main plot
        self.start_times = {} # contains start times of measurements
        # Device related
        self.current_ports = [] # contains current available ports as serial objects
        self.com_descriptions = {} # contains com port descriptions
        self.device_widgets = {} # contains device widgets, appended in device_added function
        # Filenames
        self.dat_filenames = {} # contains filenames of .dat files
        self.par_filenames = {} # contains filenames of .par files (CPC and PSM)
        self.ten_hz_filenames = {} # contains filenames of 10 hz OPC concentration log files (CPC)
        self.pulse_analysis_filenames = {} # contains filenames of pulse analysis files (CPC)
        # Flags
        self.par_updates = {} # contains .par update flags: 1 = update, 0 = no update
        self.device_errors = {} # contains device error flags: 0 = ok, 1 = errors
        self.idn_inquiry_devices = [] # contains IDs of devices that need IDN inquiry
        # Device names (static, move here for centralization)
        self.device_names = {CPC: 'CPC', PSM: 'PSM Retrofit', ELECTROMETER: 'Electrometer', CO2_SENSOR: 'CO2 sensor', RHTP: 'RHTP', AFM: 'AFM', EDILUTER: 'eDiluter', PSM2: 'PSM 2.0', TSI_CPC: 'TSI CPC', AFC: 'AFC', EXAMPLE_DEVICE: 'Example device'} # Use actual constants like CPC=0, etc.

        # Timer variables
        self.first_connection = False # once first connection has been made, set to True
        self.x_time_list = full(10, nan) # 60 # list for saving x-axis time values
        self.current_time = 0
        self.time_counter = 0 # used as index value, incremented every second
        self.max_reached = False # flag for checking if MAX_TIME_SEC has been reached
        self.error_status = 0
        self.saving_status = 1

        self.start_day = None  # For daily rollover
        self.last_write_timestamp = None  # Last successful write time
        self.most_recent_filename = ""  # Most recently created filename

        self.error_icon = None
        self.disconnected_icon = None

        self.inquiry_flag = False # when COM ports change, this is set to True to inquire device IDNs
        self.inquiry_time = time()

    def init_plot_data_for_device(self, dev_id, device_widget):
        """Initialize plot_data arrays for a new device with NaN defaults."""
        from numpy import full, nan
        x_len = len(self.x_time_list)

        # Get plot keys from device (no device-type checks!)
        for key_suffix in device_widget.get_plot_keys():
            key = str(dev_id) + key_suffix
            self.plot_data[key] = full(x_len, nan)
            self.plot_data[key] = _manage_plot_array(self.plot_data[key], 0, max_reached=False)

        # Initialize rolling buffers if device has any
        for key_suffix, buffer_size in device_widget.get_rolling_buffer_keys().items():
            key = str(dev_id) + key_suffix
            self.plot_data[key] = full(buffer_size, nan)

    def reset_for_device(self, dev_id, device_widget):
        """Initialize shared coordination state - NO device-type checks!"""
        # Device-owned data is initialized in device classes themselves
        # Rolling buffers are initialized in init_plot_data_for_device()
        # Only initialize truly shared coordination state here

        # Generic device flags (all devices need these)
        self.par_updates[dev_id] = 0  # default: no .par update needed
        self.device_errors[dev_id] = False  # default: no errors

    def clear_for_device(self, dev_id):
        """Clean up dicts when device removed (call from device_removed)."""
        # Note: Device-owned data (latest_command, ten_hz_data, pulse_analysis_index,
        # _partial_data, _extra_data_counter, needs_settings_fetch) is cleaned up
        # automatically when device widget is destroyed
        dict_names = [
            'extra_data',  # multi-message buffering
            'plot_data', 'curve_dict', 'start_times',  'device_widgets', # plots
            'dat_filenames', 'par_filenames', 'ten_hz_filenames', 'pulse_analysis_filenames',  # filenames
            'par_updates', 'device_errors'  # flags
        ]
        for dict_name in dict_names:
            d = getattr(self, dict_name, None)
            if d is not None:  # safety for missing attrs
                d.pop(dev_id, None)  # non-destructive pop

        # Remove string keys from plot_data (generic: any key containing str(dev_id))
        to_remove = [k for k in list(self.plot_data) if str(dev_id) in k]  # list() to avoid runtime mod
        for k in to_remove:
            self.plot_data.pop(k, None)

    def get_device_data(self, dev_id):
        """
        Get typed current_data dataclass from device.

        Args:
            dev_id: Device ID (integer)

        Returns:
            Device's current_data dataclass (CPCData, PSMData, etc.) or None
        """
        device = self.device_widgets.get(dev_id)
        return device.current_data if device else None

    def get_device_settings(self, dev_id):
        """
        Get typed settings dataclass from device.

        Args:
            dev_id: Device ID (integer)

        Returns:
            DeviceSettings instance or None if device not found/no settings
        """
        device = self.device_widgets.get(dev_id)
        return device.settings if device and hasattr(device, 'settings') else None

