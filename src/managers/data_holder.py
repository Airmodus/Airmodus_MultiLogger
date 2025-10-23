# managers/data_holder.py
from numpy import full, nan, array_equal  # Add these imports if not global
from config import (CPC, PSM, ELECTROMETER, CO2_SENSOR, RHTP, AFM, EDILUTER, EXAMPLE_DEVICE, PSM2, TSI_CPC)

class DataHolder:
    """Holds all app data dicts/lists. No logic—just storage."""
    def __init__(self):

        # Data related (exact copy from _init_data_structs)
        self.latest_data = {} # contains latest values
        self.latest_settings = {} # contains latest CPC and PSM settings
        self.latest_psm_prnt = {} # contains latest PSM prnt values
        self.latest_poly_correction = {} # contains latest polynomial correction values from PSM
        self.latest_command = {} # contains latest user entered command message
        self.latest_ten_hz = {} # contains latest 10 hz OPC concentration log values
        self.extra_data = {} # contains extra data, used when multiple data prints are received at once
        self.extra_data_counter = {} # contains extra data counter, used to determine when extra data buffer is safe to clear
        self.partial_data = {} # contains partial data, used when incomplete messages are received
        self.pulse_analysis_index = {} # contains CPC pulse analysis index, used for pulse analysis progress tracking
        self.psm_dilution = {} # contains PSM dilution parameters
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
        self.psm_settings_updates = {} # contains PSM settings update flags: 1 = update, 0 = no update
        self.device_errors = {} # contains device error flags: 0 = ok, 1 = errors
        self.idn_inquiry_devices = [] # contains IDs of devices that need IDN inquiry
        # Device names (static, move here for centralization)
        self.device_names = {CPC: 'CPC', PSM: 'PSM Retrofit', ELECTROMETER: 'Electrometer', CO2_SENSOR: 'CO2 sensor', RHTP: 'RHTP', AFM: 'AFM', EDILUTER: 'eDiluter', PSM2: 'PSM 2.0', TSI_CPC: 'TSI CPC', EXAMPLE_DEVICE: 'Example device'} # Use actual constants like CPC=0, etc.

        # Timer variables
        self.first_connection = False # once first connection has been made, set to True
        self.x_time_list = full(10, nan) # 60 # list for saving x-axis time values
        self.current_time = 0
        self.time_counter = 0 # used as index value, incremented every second
        self.max_reached = False # flag for checking if MAX_TIME_SEC has been reached
        self.error_status = 0
        self.saving_status = 1

    def reset_for_device(self, dev_id, dev_type):
        """Init dicts for a new device with type-specific defaults."""
        if dev_type == CPC:
            self.latest_data[dev_id] = full(15, nan)
            self.latest_settings[dev_id] = full(13, nan)
            self.pulse_analysis_index[dev_id] = None  # default: not in analysis mode
            self.plot_data[f"{dev_id}:pd"] = full(86400, nan)  # 24h rolling buffer
            self.plot_data[f"{dev_id}:pr"] = full(86400, nan)
            self.latest_ten_hz[dev_id] = full(10, nan)
        elif dev_type in [PSM, PSM2]:
            self.latest_settings[dev_id] = []  # will be populated in readIndata
            self.latest_psm_prnt[dev_id] = []  # PSM-specific subset; avoids KeyError in update_plot_data
            self.psm_settings_updates[dev_id] = True # PSM-specific: fetch settings on connect (from device_added)
            self.latest_poly_correction[dev_id] = 0.0  # default poly factor (placeholder; updated in readIndata)
            self.extra_data_counter[dev_id] = 0  # buffer clear timer
            self.partial_data[dev_id] = ""  # incomplete msg storage
            # convert from array to list to allow string insertion (CPC status hex)
            if dev_type == PSM:
                self.latest_data[dev_id] = full(33, nan).tolist()
            else: # PSM2
                self.latest_data[dev_id] = full(34, nan).tolist()
        elif dev_type in [ELECTROMETER, CO2_SENSOR, RHTP, AFM]:
            self.latest_data[dev_id] = full(3, nan)
        elif dev_type == EDILUTER:
            self.latest_data[dev_id] = full(12, nan)
            self.extra_data_counter[dev_id] = 0  # buffer clear timer
            self.partial_data[dev_id] = ""  # incomplete msg storage
        elif dev_type == TSI_CPC:
            self.latest_data[dev_id] = full(2, nan)

        self.par_updates[dev_id] = 0  # default: no .par update needed
        self.device_errors[dev_id] = False  # default: no errors; set True in readIndata if needed

    def clear_for_device(self, dev_id):
        """Clean up dicts when device removed (call from device_removed)."""
        # Full list from original loop—use getattr for dynamic access
        dict_names = [
            'latest_data', 'latest_settings', 'latest_psm_prnt',  # data
            'latest_poly_correction', 'latest_command', 'latest_ten_hz',  # data 
            'extra_data', 'extra_data_counter', 'partial_data', 'psm_dilution',  # data 
            'plot_data', 'curve_dict', 'start_times',  'device_widgets', # plots 
            'dat_filenames', 'par_filenames', 'ten_hz_filenames', 'pulse_analysis_filenames',  # filenames 
            'par_updates', 'psm_settings_updates', 'device_errors'  # flags
        ]
        for dict_name in dict_names:
            d = getattr(self, dict_name, None)
            if d is not None:  # fafety for missing attrs
                d.pop(dev_id, None)  # non-destructive pop

        # Remove string keys from plot_data (generic: any key containing str(dev_id))
        to_remove = [k for k in list(self.plot_data) if str(dev_id) in k]  # list() to avoid runtime mod
        for k in to_remove:
            self.plot_data.pop(k, None)

    def get_default_data_array(self, dev_type):
        """Return type-specific NaN array/list for latest_data init."""
        from numpy import full, nan
        if dev_type == CPC:
            return full(15, nan)
        elif dev_type == PSM:
            return full(33, nan).tolist()
        elif dev_type == PSM2:
            return full(34, nan).tolist()
        elif dev_type in [ELECTROMETER, CO2_SENSOR, RHTP]:
            return full(3, nan)
        elif dev_type == AFM:
            return full(5, nan)
        elif dev_type == EDILUTER:
            return full(12, nan)
        elif dev_type == TSI_CPC:
            return full(2, nan)
        else:
            return full(15, nan)  # Fallback

    # reset filename dictionaries, results in new files being created
    def reset_all_filenames(self):
        self.dat_filenames = {}
        self.par_filenames = {}
        self.ten_hz_filenames = {}
        self.par_updates = {}
