from numpy import full, nan, array, polyval, array_equal, roll, nanmean, isnan, linspace
from config import MAX_TIME_SEC, PULSE_ANALYSIS_THRESHOLDS, CPC, PSM, PSM2, TSI_CPC, ELECTROMETER, RHTP, AFM, EDILUTER, EXAMPLE_DEVICE
from params import p  # For accessing params in some helpers if needed

# compile data list for CPC .dat file
def compile_cpc_data(meas, status_hex, total_errors):
    # determine pulse ratio
    if str(meas[3]) == "nan":
        pulse_ratio = "nan"
    elif meas[1] == 0:
        pulse_ratio = 0
    else:
        pulse_ratio = round(meas[3]/meas[1], 2) # calculate and round to 2 decimals

    cpc_data = [ # TODO nominal flow concentration
        meas[0], meas[2], meas[1], # concentration, dead time, number of pulses during average
        meas[5], meas[7], meas[6], meas[8], # T: saturator, condenser, optics, cabin
        meas[9], meas[10], meas[11], meas[12], # P: inlet, critical orifice, nozzle, cabin
        int(meas[14]), pulse_ratio, # liquid level, pulse ratio
        total_errors, status_hex # total number of errors, hexadecimal system status
        # TODO add OPC voltage level when added to firmware
    ]
    return cpc_data

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

# compile data list for PSM .dat file
def compile_psm_data(meas, status_hex, note_hex, scan_status, psm_version):
    # determine PSM status
    if int(status_hex, 16) == 0:
        psm_status = 1
    else:
        psm_status = 0
    # determine PSM note
    if int(note_hex, 16) == 0:
        psm_note = 1
    else:
        psm_note = 0

    # concentration form PSM is calculated and stored later in write_data
    # cut-off diameter is left with a "nan" placeholder for now
    psm_data = [
        "nan", "nan", meas[0], meas[1], # concentration from PSM, cut-off diameter, saturator flow rate, excess flow rate
        meas[3], meas[2], meas[4], meas[6], meas[5], meas[7], # psm saturator t, growth tube t, inlet t, drainage t, heater t, psm cabin t
        meas[9], meas[10], meas[11], meas[12], # inlet p, inlet-sat p, sat-excess p, critical orifice p,
        scan_status, # scan status number (9 if undefined)
        psm_status, psm_note, # PSM status (1 ok / 0 nok), PSM notes (1 ok / 0 notes)
        # CPC nan placeholders, replaced later if CPC is connected
        "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan", "nan",
        status_hex, note_hex # PSM status (hex), PSM notes (hex)
    ]
    # if PSM 2.0, insert vacuum flow rate (before PSM status number)
    if psm_version == PSM2:
        psm_data.insert(15, meas[13]) # vacuum flow rate

    return psm_data

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

# sets psm_settings_updates flag for specified PSM device
# when flag is True, PSM settings are requested from device in get_dev_data
def psm_update(device_id, psm_settings_updates):
    psm_settings_updates[device_id] = True

# sends set flow rate to PSM
def psm_flow_send(device, value):
    device.child("Connection").value().send_set_val(value, ":SET:FLOW:CPC ", decimals=3)

# sends set flow rate to CPC
def cpc_flow_send(device, value):
    # get connected CPC ID
    cpc_id = device.child("Connected CPC").value()
    # if PSM is connected to CPC, send value to CPC
    if cpc_id != 'None':
        # get connected CPC device parameter
        for cpc in p.child('Device settings').children():
            if cpc.child('DevID').value() == cpc_id:
                cpc_device = cpc
                break
        # if device is Airmodus CPC
        if cpc_device.child('Device type').value() == CPC:
            # send flow rate set value to CPC
            cpc_device.child("Connection").value().send_set_val(value, ":SET:FLOW ", decimals=3)

# change PSM's 10 Hz parameter and button status
def ten_hz_clicked(psm_param, psm_widget):
    # get current status of PSM 10 hz parameter
    status = psm_param.child('10 hz').value()
    # if 10 hz is off, turn it on
    if status == False:
        # set 10 hz flag to True
        psm_param.child('10 hz').setValue(True)
        psm_widget.measure_tab.ten_hz.change_color(1)       
    # if 10 hz is on, turn it off
    elif status == True:
        # set 10 hz flag to False
        psm_param.child('10 hz').setValue(False)
        psm_widget.measure_tab.ten_hz.change_color(0)


# when command is entered, send message to device and update .par file
def command_entered(dev_id, dev_param, device_widgets, latest_command):
    try:
        # get message from command input and clear input
        command_widget = device_widgets[dev_id].set_tab.command_widget
        message = command_widget.command_input.text()
        command_widget.command_input.clear()
        # update command_widget's text box
        command_widget.update_text_box(message)

        # send message to device
        dev_param.child('Connection').value().send_message(message)

        # if saving is on, store command to latest_command dictionary
        if p.child('Data settings').child('Save data').value():
            latest_command[dev_id] = message
    
    except Exception as e:
        device_widgets[dev_id].set_tab.command_widget.update_text_box(str(e))


__all__ = [
    'compile_cpc_data', 'compile_cpc_settings', 'compile_psm_data', 'compile_psm_settings',
    '_manage_plot_array', '_roll_pulse_array', 'psm_update', 'psm_flow_send', 'cpc_flow_send',
    'ten_hz_clicked', 'command_entered'
]
