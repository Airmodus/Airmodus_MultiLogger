from numpy import full, nan, roll
from config import MAX_TIME_SEC, CPC, PSM, PSM2

# compile settings list for CPC .par file
def compile_cpc_settings(prnt, pall):
    cpc_settings = [
        prnt[5], pall[24], prnt[10], # averaging time, nominal inlet flow rate, measured cpc flow rate
        prnt[8], prnt[6], prnt[7], # temperature set points: saturator, condenser, optics
        int(prnt[1]), pall[26], pall[27], int(prnt[4]), # autofill, OPC counter threshold voltage, OPC counter threshold voltage 2, water removal
        prnt[12], int(prnt[2]), pall[20], pall[25] # dead time correction, drain, k-factor, tau
        # TODO add Firmware version
    ]
    return cpc_settings

# compile settings list for PSM .par file
def compile_psm_settings(prnt, co_flow, dilution_parameters, psm_version):
    # inlet flow is calculated and stored in update_plot_data
    psm_settings = [
        prnt[1], prnt[2], prnt[3], prnt[4], prnt[5], # T setpoints: growth tube, PSM saturator, inlet, heater, drainage
        prnt[6], "nan" # PSM stored CPC flow rate, inlet flow rate (added when calculated),
        # CO flow (Retrofit only),
        # dilution parameters,
        # CPC values (added in write_data),
    ]

    # if PSM Retrofit, add CO flow rate
    if psm_version == PSM:
        psm_settings.append(co_flow)
    
    # add dilution parameters
    for value in dilution_parameters:
        psm_settings.append(value)

    # add CPC values later in write_data if CPC connected
    return psm_settings

def _manage_plot_array(arr, time_counter, max_reached=False):
    """Centralized array shift/double logic. Returns arr (mutated or new)."""
    if time_counter >= MAX_TIME_SEC - 1:
        if max_reached:
            # Truncate if needed 
            if len(arr) > MAX_TIME_SEC:
                arr = arr[:MAX_TIME_SEC]
            arr[:-1] = arr[1:]  # Shift left (mutates)
            arr[-1] = nan       # End with nan (mutates)
    elif time_counter >= len(arr):  # Use len() for safety
        tmp = arr.copy()
        new_size = len(tmp) * 2
        arr = full(new_size, nan)
        arr[:len(tmp)] = tmp
    return arr  # return for reassignment

def _roll_pulse_array(arr):
    arr = roll(arr, -1)
    arr[-1] = nan
    return arr

# sets needs_settings_fetch flag for specified PSM device
# when flag is True, PSM settings are requested from device in get_dev_data
def psm_update(device_id, device_widgets):
    device = device_widgets.get(device_id)
    if device and hasattr(device, 'needs_settings_fetch'):
        device.needs_settings_fetch = True

# sends set flow rate to PSM
def psm_flow_send(psm_widget, value):
    if psm_widget.connection:
        psm_widget.connection.send_set_val(value, ":SET:FLOW:CPC ", decimals=3)

# sends set flow rate to CPC
def cpc_flow_send(psm_widget, value, device_widgets):
    # get connected CPC ID from PSM device config
    cpc_id = psm_widget.device_config.extra_params.get('connected_cpc', 'None')
    # if PSM is connected to CPC, send value to CPC
    if cpc_id != 'None':
        # get connected CPC widget
        cpc_widget = device_widgets.get(cpc_id)
        if cpc_widget and cpc_widget.device_config.device_type == CPC:
            # send flow rate set value to CPC
            if cpc_widget.connection:
                cpc_widget.connection.send_set_val(value, ":SET:FLOW ", decimals=3)

# change PSM's 10 Hz parameter and button status
def ten_hz_clicked(psm_widget, config):
    # get current status of PSM 10 hz parameter from extra_params
    status = psm_widget.device_config.extra_params.get('10_hz', False)
    # if 10 hz is off, turn it on
    if status == False:
        # set 10 hz flag to True
        psm_widget.device_config.extra_params['10_hz'] = True
        psm_widget.measure_tab.ten_hz.change_color(1)
    # if 10 hz is on, turn it off
    elif status == True:
        # set 10 hz flag to False
        psm_widget.device_config.extra_params['10_hz'] = False
        psm_widget.measure_tab.ten_hz.change_color(0)


# when command is entered, send message to device and update .par file
def command_entered(dev_id, device_widgets, config):
    try:
        # get message from command input and clear input
        device_widget = device_widgets[dev_id]
        command_widget = device_widget.set_tab.command_widget
        message = command_widget.command_input.text()
        command_widget.command_input.clear()
        # update command_widget's text box
        command_widget.update_text_box(message)

        # send message to device
        if device_widget.connection:
            device_widget.connection.send_message(message)

        # if saving is on, store command in device's latest_command property
        if config.data_settings.save_data:
            device_widget.latest_command = message

    except Exception as e:
        device_widgets[dev_id].set_tab.command_widget.update_text_box(str(e))


# Common device parsing utilities
def parse_idn_response(message):
    """
    Parse *IDN response and return standardized result dict.

    Args:
        message: Raw message string like "*IDN SERIAL123"

    Returns:
        dict: Standardized info response with serial number
    """
    # Strip any newlines and carriage returns first
    clean_message = message.strip('\n').strip('\r').strip()

    # Extract everything after "*IDN " if present
    if '*IDN ' in clean_message and len(clean_message) > 5:
        idx = clean_message.index('*IDN ')
        serial_number = clean_message[idx + 5:].strip('\n').strip('\r').strip()
    elif clean_message.startswith('*IDN'):
        # Handle case where there's no space after *IDN
        serial_number = clean_message[4:].strip()
    else:
        # Fallback to old logic
        serial_number = clean_message.split(" ", 1)[1].strip() if " " in clean_message else ""

    return {
        'type': 'info',
        'command': '*IDN',
        'data': serial_number,
        'raw': message,
        'update_gui': False
    }


def create_data_response(message, command, data_array):
    """
    Create standardized data response dict.

    Args:
        message: Raw message string
        command: Command name (e.g., ':MEAS:DATA')
        data_array: List or array of parsed data values

    Returns:
        dict: Standardized data response
    """
    return {
        'type': 'data',
        'data': data_array,
        'command': command,
        'raw': message,
        'update_gui': False
    }


def create_error_response(message, command, error):
    """
    Create standardized error response dict.

    Args:
        message: Raw message string
        command: Command name or 'unknown'
        error: Error message or Exception object

    Returns:
        dict: Standardized error response
    """
    return {
        'type': 'error',
        'command': command,
        'data': None,
        'raw': message,
        'error': str(error),
        'update_gui': False
    }


def compute_unique_short_ids(serial_numbers):
    """
    Compute unique short IDs for a collection of serial numbers.

    Starts with first 4 chars, adds more until each ID is unique.

    Args:
        serial_numbers: dict mapping key -> serial_number (e.g., port -> serial or device_id -> serial)

    Returns:
        dict: Mapping of key -> unique short_id
    """
    import re

    short_ids = {}
    needs_resolution = {}  # key -> serial for non-nickname serials

    # First pass: extract nicknames or collect serials needing resolution
    for key, serial in serial_numbers.items():
        if not serial:
            short_ids[key] = ""
            continue

        # Check for Airmodus CPC with nickname
        match = re.match(r'^(?:301|235)[\*\s]\s*(.+)', serial)
        if match:
            short_ids[key] = match.group(1).strip()
        else:
            needs_resolution[key] = serial

    # Second pass: resolve collisions by adding characters
    if needs_resolution:
        chars = 4
        pending = dict(needs_resolution)

        while pending and chars <= 50:
            # Compute current short IDs
            current = {key: serial[:chars] if len(serial) >= chars else serial
                       for key, serial in pending.items()}

            # Group by short ID to find collisions
            id_to_keys = {}
            for key, short in current.items():
                id_to_keys.setdefault(short, []).append(key)

            # Assign unique ones, keep collisions for next round
            new_pending = {}
            for short, keys in id_to_keys.items():
                if len(keys) == 1:
                    short_ids[keys[0]] = short
                else:
                    # Check if we've used full serial
                    for key in keys:
                        serial = pending[key]
                        if len(serial) <= chars:
                            short_ids[key] = serial
                        else:
                            new_pending[key] = serial

            pending = new_pending
            chars += 1

        # Safety: assign any remaining
        for key, serial in pending.items():
            short_ids[key] = serial

    return short_ids


__all__ = [
    'compile_cpc_settings', 'compile_psm_settings',
    '_manage_plot_array', '_roll_pulse_array', 'psm_update', 'psm_flow_send', 'cpc_flow_send',
    'ten_hz_clicked', 'command_entered',
    'parse_idn_response', 'create_data_response', 'create_error_response',
    'compute_unique_short_ids'
]
