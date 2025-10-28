# managers/plot_manager.py
import random
import traceback
import logging
from numpy import full, nan, nanmean, array, polyval
from pyqtgraph import PlotCurveItem
from config import *  # For constants like MAX_TIME_SEC, etc., if needed
from utils import _manage_plot_array, _roll_pulse_array

class PlotManager:
    def __init__(self, main_window, data_holder, main_plot):
        self.main_window = main_window
        self.params = main_window.params
        self.data_holder = data_holder
        self.main_plot = main_plot

    # update plot data lists
    def update_plot_data(self):
        """Update plot data arrays with latest measurements."""
        # ----- PSM connected CPC calculations -----
        # before setting plot data, go through each PSM and perform connected CPC calculations
        for dev in self.params.child('Device settings').children():
            try:
                dev_type = dev.child('Device type').value()
                # if device is PSM and it is connected, calculate and compile connected CPC values
                if dev_type in [PSM, PSM2] and dev.child('Connected').value(): # PSM
                    psm_id = dev.child('DevID').value()
                    cpc_id = dev.child('Connected CPC').value()
                    if cpc_id != 'None' and cpc_id not in self.data_holder.pulse_analysis_index:
                        # get connected CPC device parameter
                        for cpc in self.params.child('Device settings').children():
                            if cpc.child('DevID').value() == cpc_id:
                                cpc_device = cpc
                                break

                        # if CPC is connected, calculate missing values
                        if cpc_device.child('Connected').value():
                            cpc_data = self.data_holder.latest_data[cpc_id]

                            # Inlet flow = (CPC flow + CO flow) - Saturator flow - Excess flow

                            # get cpc flow rate from PSM latest_settings
                            cpc_flow = float(self.data_holder.latest_settings[psm_id][5])
                            if dev_type == PSM:
                                # get co flow rate from PSM widget
                                co_flow = round(self.data_holder.device_widgets[psm_id].set_tab.set_co_flow.value_spinbox.value(), 3)
                                if co_flow == 0: # if co flow is 0, not set by user
                                    self.data_holder.device_widgets[psm_id].set_tab.set_co_flow.set_red_color() # set CO flow rate widget to red
                                    self.data_holder.error_status = 1 # set data_holder.error_status flag to 1
                                else:
                                    self.data_holder.device_widgets[psm_id].set_tab.set_co_flow.set_default_color()
                                inlet_flow = cpc_flow + co_flow - float(self.data_holder.latest_data[psm_id][2]) - float(self.data_holder.latest_data[psm_id][3])
                            
                            elif dev_type == PSM2:
                                # get vacuum mfc flow rate from latest data
                                vacuum_flow = float(self.data_holder.latest_data[psm_id][15])
                                # TODO vacuum flow GUI value is updated in PSMWidget's update_values, check if it works and remove line below
                                #self.data_holder.device_widgets[psm_id].status_tab.flow_vacuum.change_value(str(round(vacuum_flow, 3)))
                                inlet_flow = cpc_flow + vacuum_flow - float(self.data_holder.latest_data[psm_id][2]) - float(self.data_holder.latest_data[psm_id][3])
                                inlet_flow0 = cpc_flow + vacuum_flow - 4 + float(self.data_holder.latest_data[psm_id][2]) + float(self.data_holder.latest_data[psm_id][3])
                            
                            # store inlet flow into PSM latest_settings, rounded to 3 decimals
                            self.data_holder.latest_settings[psm_id][6] = round(inlet_flow, 3)
                            # show inlet flow in PSM widget
                            self.data_holder.device_widgets[psm_id].status_tab.flow_inlet.change_value(str(round(inlet_flow, 3)))

                            # if received polynomial correction is 0 (placeholder)
                            if self.data_holder.latest_poly_correction[psm_id] == 0:
                                # calculate polynomial correction factor
                                if dev_type == PSM:
                                    pcor = array([-0.0272052, 0.11394213, -0.08959011, -0.20675596, 0.24343024, 1.10531145])
                                elif dev_type == PSM2:
                                    pcor = array([0.12949491, -0.50587616, 0.57214191, 0.76108161])
                                poly_correction  = polyval(pcor, float(self.data_holder.latest_data[psm_id][2]))
                            else: # if received polynomial correction is other than 0, use received value
                                poly_correction = self.data_holder.latest_poly_correction[psm_id]

                            # calculate dilution correction factor
                            # Dilution ratio = (inlet flow + Excess flow + Saturator flow) / Inlet flow
                            dilution_correction_factor = (inlet_flow + float(self.data_holder.latest_data[psm_id][3]) + float(self.data_holder.latest_data[psm_id][2])) / inlet_flow
                            if dev_type == PSM2:
                                dilution_correction_factor = (inlet_flow + 4 - float(self.data_holder.latest_data[psm_id][3]) - float(self.data_holder.latest_data[psm_id][2])) / inlet_flow0
                            
                            # calculate concentration from PSM
                            # Concentration from PSM = CPC concentration * Dilution ratio / Polynomial correction
                            concentration_from_psm = float(self.data_holder.latest_data[cpc_id][0]) * dilution_correction_factor / poly_correction
                            # add to PSM latest_data
                            self.data_holder.latest_data[psm_id][0] = round(concentration_from_psm, 2)

                            # if Connected CPC is Airmodus CPC, add CPC data to PSM latest_data
                            if cpc_device.child('Device type').value() == CPC:
                                # compile connected CPC data
                                connected_cpc_data = [
                                    cpc_data[0], round(dilution_correction_factor, 3), # concentration,  dilution correction factor
                                    cpc_data[3], cpc_data[4], cpc_data[5], cpc_data[6],# T: saturator, condenser, optics, cabin
                                    cpc_data[8], cpc_data[9], cpc_data[7],# P: critical orifice, nozzle, absolute (inlet)
                                    cpc_data[11], cpc_data[2], cpc_data[1],# liquid level, pulses, pulse duration
                                    cpc_data[13], cpc_data[14] # number of errors, system status (hex)
                                ]
                                # replace PSM's latest_data CPC placeholders with connected CPC data
                                self.data_holder.latest_data[psm_id][-16:-2] = connected_cpc_data # 14 values before status hex and note hex
                            # if Connected device is TSI CPC, add concentration and dilution correction factor to PSM latest_data
                            elif cpc_device.child('Device type').value() == TSI_CPC:
                                self.data_holder.latest_data[psm_id][-16] = cpc_data[0] # concentration
                                self.data_holder.latest_data[psm_id][-15] = round(dilution_correction_factor, 3) # dilution correction factor

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

        # ----- update plot data -----

        self.data_holder.x_time_list = _manage_plot_array(self.data_holder.x_time_list, self.data_holder.time_counter, max_reached=self.data_holder.max_reached)
        self.data_holder.x_time_list[self.data_holder.time_counter] = self.data_holder.current_time
        
        # go through each device
        for dev in self.params.child('Device settings').children():
            # store device id to variable for clarity
            dev_id = dev.child('DevID').value()

            try: # if one device fails, continue with the next one
                dev_type = dev.child('Device type').value()
                # Devices with multiple values - create lists for each value
                if dev_type in [CPC, TSI_CPC, ELECTROMETER, RHTP, AFM]:
                    # determine value types based on device type
                    if dev_type in [CPC, TSI_CPC]:
                        types = ['', ':raw'] # concentration, raw concentration
                    elif dev_type == ELECTROMETER:
                        types = [':1', ':2', ':3'] # voltage 1, voltage 2, voltage 3
                    elif dev_type == RHTP:
                        types = [':rh', ':t', ':p'] # RH, T, P
                    elif dev_type == AFM:
                        types = [':f', ':sf', ':rh', ':t', ':p'] # flow, standard flow, RH, T, P
                    
                    # if device is not yet in data_holder.plot_data dict, add it
                    if str(dev_id)+types[0] not in self.data_holder.plot_data:
                        # make the new lists the same size as x_time_list
                        for i in types:
                            self.data_holder.plot_data[str(dev_id)+i] = full(len(self.data_holder.x_time_list), nan)

                    # Manage all arrays for this device type in one go
                    for i in types:
                        self.data_holder.plot_data[str(dev_id)+i] = _manage_plot_array(self.data_holder.plot_data[str(dev_id)+i], self.data_holder.time_counter, max_reached=self.data_holder.max_reached)
                
                # other devices
                else:
                    # if device is not yet in data_holder.plot_data dict, add it
                    key = str(dev_id)
                    if key not in self.data_holder.plot_data:
                        # make the new list the same size as x_time_list
                        self.data_holder.plot_data[key] = full(len(self.data_holder.x_time_list), nan)
                    self.data_holder.plot_data[key] = _manage_plot_array(self.data_holder.plot_data[key], self.data_holder.time_counter, max_reached=self.data_holder.max_reached)
                
                # create lists for pulse duration and pulse ratio if they don't exist yet
                if dev_type == CPC:
                    key_pd = str(dev_id)+':pd'
                    self.data_holder.plot_data[key_pd] = _roll_pulse_array(self.data_holder.plot_data[key_pd])
                    key_pr = str(dev_id)+':pr'
                    self.data_holder.plot_data[key_pr] = _roll_pulse_array(self.data_holder.plot_data[key_pr])
                
                # if device is connected, add latest_values data to data_holder.plot_data according to device
                if dev.child('Connected').value():
                    if dev_type in [CPC, TSI_CPC]: # CPC
                        
                        # if CPC is in pulse analysis mode, update pulse analysis plot data instead of normal plot data
                        if dev_id in self.data_holder.pulse_analysis_index:
                            if self.data_holder.pulse_analysis_index[dev_id] is not None: # when index is None, analysis has reached its end
                                try:
                                    # calculate current pulse duration
                                    dead_time = self.data_holder.latest_data[dev_id][1]
                                    number_of_pulses = self.data_holder.latest_data[dev_id][2]
                                    if number_of_pulses == 0:
                                        pulse_duration = nan # if number of pulses is 0, set pulse duration to nan
                                    else:
                                        # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                                        pulse_duration = round(dead_time * 1000 / number_of_pulses, 2)
                                    # get current threshold value with data_holder.pulse_analysis_index
                                    threshold_value = PULSE_ANALYSIS_THRESHOLDS[self.data_holder.pulse_analysis_index[dev_id]]
                                    #print(f"threshold: {threshold_value} pulse duration: {pulse_duration} dead time: {dead_time} number of pulses: {number_of_pulses}")
                                    # add analysis point to pulse quality widget
                                    self.data_holder.device_widgets[dev_id].pulse_quality.add_analysis_point(pulse_duration, threshold_value)
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                    # stop pulse analysis if exception occurs
                                    self.main_window.pulse_analysis_stop(dev_id, dev)

                        else:
                            psm_connection = False
                            # check if this CPC is connected to any PSM
                            for psm in self.params.child('Device settings').children():
                                if psm.child('Device type').value() in [PSM, PSM2] and psm.child('Connected').value():
                                    if psm.child('Connected CPC').value() == dev_id:
                                        # if PSM connection exists, add latest PSM concentration value to data_holder.plot_data
                                        self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter] = self.data_holder.latest_data[psm.child('DevID').value()][0]
                                        psm_connection = True
                                        break
                            # if not connected to PSM, add CPC concentration value to data_holder.plot_data
                            if psm_connection == False:
                                self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][0]
                            # add raw concentration value to data_holder.plot_data
                            self.data_holder.plot_data[str(dev_id)+':raw'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][0]
                            
                            # update pulse duration and pulse ratio lists
                            if dev.child('Device type').value() == CPC:
                                try:
                                    #print("concentration", self.latest_data[dev_id][0], "* sample flow", self.latest_settings[dev_id][2], "=", self.latest_data[dev_id][0] * self.latest_settings[dev_id][2])
                                    # check if (concentration * sample flow) is above 50 and below 5000 (valid)
                                    check_value = self.data_holder.latest_data[dev_id][0] * self.data_holder.latest_settings[dev_id][2]
                                    if check_value > 50 and check_value < 5000:
                                        # calculate pulse duration
                                        if self.data_holder.latest_data[dev_id][2] == 0:
                                            pulse_duration = nan # if number of pulses is 0, set pulse duration to nan
                                        else:
                                            # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                                            pulse_duration = round(self.data_holder.latest_data[dev_id][1] * 1000 / self.data_holder.latest_data[dev_id][2], 2)
                                        # store pulse duration and pulse ratio values to data_holder.plot_data
                                        self.data_holder.plot_data[str(dev_id)+':pd'][-1] = pulse_duration
                                        self.data_holder.plot_data[str(dev_id)+':pr'][-1] = self.data_holder.latest_data[dev_id][12]
                                    else: # if concentration is outside range (invalid)
                                        # store nan values to data_holder.plot_data
                                        self.data_holder.plot_data[str(dev_id)+':pd'][-1] = nan
                                        self.data_holder.plot_data[str(dev_id)+':pr'][-1] = nan
                                except Exception as e:
                                    print(traceback.format_exc())
                                    logging.exception(e)
                                    # store nan values to data_holder.plot_data
                                    self.data_holder.plot_data[str(dev_id)+':pd'][-1] = nan
                                    self.data_holder.plot_data[str(dev_id)+':pr'][-1] = nan

                    elif dev_type in [PSM, PSM2]: # PSM
                        # add latest saturator flow rate value to data_holder.time_counter index of data_holder.plot_data
                        self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][2]
                    elif dev_type == ELECTROMETER: # ELECTROMETER
                        # add latest voltage values to data_holder.time_counter index of data_holder.plot_data
                        self.data_holder.plot_data[str(dev_id)+':1'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][0]
                        self.data_holder.plot_data[str(dev_id)+':2'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][1]
                        self.data_holder.plot_data[str(dev_id)+':3'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][2]
                    elif dev_type == CO2_SENSOR: # CO2 sensor
                        # add latest CO2 value to data_holder.time_counter index of data_holder.plot_data
                        self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][0]
                    elif dev_type == RHTP: # RHTP
                        # add latest values (RH, T, P) to data_holder.time_counter index of data_holder.plot_data
                        self.data_holder.plot_data[str(dev_id)+':rh'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][0]
                        self.data_holder.plot_data[str(dev_id)+':t'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][1]
                        self.data_holder.plot_data[str(dev_id)+':p'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][2]
                    elif dev_type == AFM: # AFM
                        # add latest values (flow, RH, T, P) to data_holder.time_counter index of data_holder.plot_data
                        self.data_holder.plot_data[str(dev_id)+':f'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][0]
                        self.data_holder.plot_data[str(dev_id)+':sf'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][1]
                        self.data_holder.plot_data[str(dev_id)+':rh'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][2]
                        self.data_holder.plot_data[str(dev_id)+':t'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][3]
                        self.data_holder.plot_data[str(dev_id)+':p'][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][4]
                    elif dev_type == EDILUTER: # eDiluter
                        # add latest T1 value to data_holder.time_counter index of data_holder.plot_data
                        self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter] = self.data_holder.latest_data[dev_id][3]
                if dev_type == -1: # Example device
                    # generate random value for plotting and logging
                    random_value = round(random.random() * 100, 2) # 0-100
                    # add random value to data_holder.time_counter index of data_holder.plot_data
                    self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter] = random_value
                    # add random value to latest_data as list object
                    self.data_holder.latest_data[dev_id] = [random_value]

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

    # update plots with plot data lists
    def update_figures_and_menus(self):
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            dev_type = dev.child('Device type').value()
            try: # if one device fails, continue with the next one
                # MAIN PLOT
                # if device is not yet in data_holder.curve_dict, add it
                # used when plotting to main plot
                if dev_id not in self.data_holder.curve_dict:
                    # create curve
                    self.data_holder.curve_dict[dev_id] = PlotCurveItem(pen=dev_id, connect="finite")
                    if dev_type == PSM2:
                        self.main_plot.viewboxes[PSM].addItem(self.data_holder.curve_dict[dev_id])
                    elif dev_type == TSI_CPC:
                        self.main_plot.viewboxes[CPC].addItem(self.data_holder.curve_dict[dev_id])
                    else: # other devices
                        self.main_plot.viewboxes[dev_type].addItem(self.data_holder.curve_dict[dev_id])
                
                # if device type is RHTP or AFM, update main plot according to selected value
                if dev_type in [RHTP, AFM]: # RHTP or AFM
                    if not dev.child("Plot to main").value():
                        self.data_holder.curve_dict[dev_id].setData(x=[], y=[])
                    elif dev_type == RHTP and dev.child("Plot to main").value() == 'RH':
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter + 1],
                            y=self.data_holder.plot_data[str(dev_id) + ':rh'][:self.data_holder.time_counter + 1]
                        )
                    elif dev_type == RHTP and dev.child("Plot to main").value() == 'T':
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter + 1],
                            y=self.data_holder.plot_data[str(dev_id) + ':t'][:self.data_holder.time_counter + 1]
                        )
                    elif dev_type == RHTP and dev.child("Plot to main").value() == 'P':
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter + 1],
                            y=self.data_holder.plot_data[str(dev_id) + ':p'][:self.data_holder.time_counter + 1]
                        )
                    elif dev_type == AFM and dev.child("Plot to main").value() == 'Flow':
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter + 1],
                            y=self.data_holder.plot_data[str(dev_id) + ':f'][:self.data_holder.time_counter + 1]
                        )
                    elif dev_type == AFM and dev.child("Plot to main").value() == 'Standard flow':
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter + 1],
                            y=self.data_holder.plot_data[str(dev_id) + ':sf'][:self.data_holder.time_counter + 1]
                        )

                # other devices: update main plot if 'Plot to main' is enabled
                elif dev.child("Plot to main").value():
                    # if device is CPC, get plot data with str(dev_id) key
                    if dev_type in [CPC, TSI_CPC]: # CPC
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], 
                            y=self.data_holder.plot_data[str(dev_id)][:self.data_holder.time_counter+1]
                        )
                    # if device is Electrometer, plot Voltage 2
                    elif dev_type == ELECTROMETER: # ELECTROMETER
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], 
                            y=self.data_holder.plot_data[str(dev_id)+':2'][:self.data_holder.time_counter+1]
                        )
                    else: # other devices
                        self.data_holder.curve_dict[dev_id].setData(
                            x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], 
                            y=self.data_holder.plot_data[str(dev_id)][:self.data_holder.time_counter+1]
                        )
                else: # if 'Plot to main' is off, hide curve from main plot (set empty data)
                    self.data_holder.curve_dict[dev_id].setData(x=[], y=[])
                
                # scale x-axis range if Follow is on
                if self.params.child('Plot settings').child('Follow').value():
                    self.main_plot.plot.setXRange(
                        self.data_holder.current_time - (self.params.child('Plot settings').child('Time window (s)').value()), 
                        self.data_holder.current_time, padding=0
                    )

                # INDIVIDUAL PLOTS
                if dev.child('Connected').value() or dev_type == EXAMPLE_DEVICE:
                    # store current time counter value as start time in dictionary if not yet stored
                    # start time is stored when first non-nan value is received
                    # start time is used to crop plot data to only show non-nan values
                    if dev_id not in self.data_holder.start_times:
                        if dev_type in [CPC, TSI_CPC] and str(self.data_holder.plot_data[str(dev_id)+':raw'][self.data_holder.time_counter]) != "nan":
                            self.data_holder.start_times[dev_id] = self.data_holder.time_counter
                        elif dev_type == ELECTROMETER and str(self.data_holder.plot_data[str(dev_id)+':1'][self.data_holder.time_counter]) != "nan":
                            self.data_holder.start_times[dev_id] = self.data_holder.time_counter
                        elif dev_type in [RHTP, AFM] and str(self.data_holder.plot_data[str(dev_id)+':rh'][self.data_holder.time_counter]) != "nan":
                            self.data_holder.start_times[dev_id] = self.data_holder.time_counter
                        elif str(self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter]) != "nan":
                            self.data_holder.start_times[dev_id] = self.data_holder.time_counter

                    # if device is in start times dictionary, update plot
                    if dev_id in self.data_holder.start_times:
                        # get start time from dictionary to determine plot start index
                        start_time = self.data_holder.start_times[dev_id]
                        # update plot in device widget
                        # TODO start times removed from curve setData, problems with array shift index - add back later if compatible
                        #self.data_holder.device_widgets[dev_id].plot_tab.curve.setData(x=self.data_holder.x_time_list[start_time:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)][start_time:self.data_holder.time_counter+1])
                        if dev_type in [CPC, TSI_CPC]: # CPC
                            # update plot with raw CPC concentration
                            self.data_holder.device_widgets[dev_id].plot_tab.curve.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':raw'][:self.data_holder.time_counter+1])
                            # update CPC pulse quality tab view (scatter plot and labels)
                            if dev_type == CPC:
                                self.pulse_quality_update(dev_id)

                        elif dev_type == ELECTROMETER: # ELECTROMETER
                            # update Electrometer plot with all 3 values
                            self.data_holder.device_widgets[dev_id].plot_tab.curve1.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':1'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curve2.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':2'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curve3.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':3'][:self.data_holder.time_counter+1])
                        elif dev_type == RHTP: # RHTP
                            # update RHTP plot with all 3 values
                            self.data_holder.device_widgets[dev_id].plot_tab.curve1.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':rh'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curve2.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':t'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curve3.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':p'][:self.data_holder.time_counter+1])
                        elif dev_type == AFM: # AFM
                            # update AFM plot with all 5 values
                            self.data_holder.device_widgets[dev_id].plot_tab.curves[0].setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':f'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curves[1].setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':sf'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curves[2].setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':rh'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curves[3].setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':t'][:self.data_holder.time_counter+1])
                            self.data_holder.device_widgets[dev_id].plot_tab.curves[4].setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)+':p'][:self.data_holder.time_counter+1])
                        else: # other devices
                            self.data_holder.device_widgets[dev_id].plot_tab.curve.setData(x=self.data_holder.x_time_list[:self.data_holder.time_counter+1], y=self.data_holder.plot_data[str(dev_id)][:self.data_holder.time_counter+1])
                        
                        # scale x-axis range if Follow is on
                        if self.params.child('Plot settings').child('Follow').value():
                            if dev_type == ELECTROMETER: # if ELECTROMETER, update all 3 plots
                                for plot in self.data_holder.device_widgets[dev_id].plot_tab.plots:
                                    plot.setXRange(self.data_holder.current_time - (self.params.child('Plot settings').child('Time window (s)').value()), self.data_holder.current_time, padding=0)
                            else: # other devices
                                self.data_holder.device_widgets[dev_id].plot_tab.plot.setXRange(self.data_holder.current_time - (self.params.child('Plot settings').child('Time window (s)').value()), self.data_holder.current_time, padding=0)

                # PSM CPC FLOW CHECK
                # warn if no CPC is connected or update Set tab's CPC sample flow value

                # if device type is PSM and it is connected
                if dev_type in [PSM ,PSM2] and dev.child('Connected').value():
                    # if no CPC is connected
                    if dev.child('Connected CPC').value() == 'None':
                        # update status_tab flow_cpc widget value and color
                        if self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.value_label.text() != "Not connected":
                            # set status_tab flow_cpc color to red and change text
                            self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.change_color(1) # change color to red
                            self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.change_value("Not connected") # update value on status_tab as well
                        # set data_holder.error_status flag to 1
                        self.data_holder.error_status = 1
                        # set device error flag
                        self.data_holder.device_errors[dev.child('DevID').value()] = True
                    # if CPC is connected
                    else:
                        # get connected CPC id
                        cpc_id = dev.child('Connected CPC').value()
                        # get connected CPC device parameter
                        for cpc in self.params.child('Device settings').children():
                            if cpc.child('DevID').value() == cpc_id:
                                cpc_device = cpc
                                break
                        # if connected CPC is Airmodus CPC, check if connected CPC sample flow has changed
                        if cpc_device.child('Device type').value() == CPC:
                            cpc_sample_flow = float(self.data_holder.latest_settings[cpc_id][2])
                            # if CPC sample flow is different from value displayed in Set tab, update displayed value
                            if self.data_holder.device_widgets[dev_id].set_tab.set_cpc_sample_flow.value_spinbox.value() != cpc_sample_flow:
                                self.data_holder.device_widgets[dev_id].set_tab.set_cpc_sample_flow.value_spinbox.setValue(cpc_sample_flow)
                        
                        # if CPC inlet flow is different from value displayed in Status tab, update displayed value
                        if self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.value_label.text() != str(self.data_holder.latest_settings[dev_id][5]) + " lpm":
                            # set status_tab flow_cpc color to normal and change text
                            self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.change_color(0)
                            self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.change_value(str(self.data_holder.latest_settings[dev_id][5]) + " lpm")

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

        # update axes # TODO add flag for updating axes, activate flag when any 'Plot to main' option is changed
        self.axis_check()
        # update legend with current values
        self.legend_check()

    def axis_check(self):
        """Update main plot axes based on Plot to main settings."""
        for key in self.main_plot.axes:
            self.main_plot.show_hide_axis(key, False)
        for dev in self.params.child('Device settings').children():
            dev_type = dev.child('Device type').value()
            if dev_type == RHTP:
                self.main_plot.change_rhtp_axis(dev.child('Plot to main').value())
            elif dev_type == AFM:
                self.main_plot.change_afm_axis(dev.child('Plot to main').value())
            elif dev.child('Plot to main').value():
                self.main_plot.show_hide_axis(dev_type, True)

    def legend_check(self):
        """Update main plot legend with current values."""
        self.main_plot.legend.clear()
        # check each device and add to legend if exists in curve_dict and Plot to main is enabled
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            if dev_id in self.data_holder.curve_dict:
                device_name = dev.child('Device nickname').value() or dev.name()
                dev_type = dev.child('Device type').value()
                if dev_type in [RHTP, AFM]:
                    # if Plot to main is enabled
                    if dev.child('Plot to main').value():
                        # add curve to legend with device name and current value of chosen parameter
                        if dev.child('Plot to main').value() == "RH":
                            legend_string = device_name + ": " + str(self.data_holder.plot_data[str(dev_id)+':rh'][self.data_holder.time_counter])
                        elif dev.child('Plot to main').value() == "T":
                            legend_string = device_name + ": " + str(self.data_holder.plot_data[str(dev_id)+':t'][self.data_holder.time_counter])
                        elif dev.child('Plot to main').value() == "P":
                            legend_string = device_name + ": " + str(self.data_holder.plot_data[str(dev_id)+':p'][self.data_holder.time_counter])
                        elif dev.child('Device type').value() == AFM and dev.child('Plot to main').value() == "Flow":
                            legend_string = device_name + ": " + str(self.data_holder.plot_data[str(dev_id) + ':f'][self.data_holder.time_counter])
                        elif dev.child('Device type').value() == AFM and dev.child('Plot to main').value() == "Standard flow":
                            legend_string = device_name + ": " + str(self.data_holder.plot_data[str(dev_id) + ':sf'][self.data_holder.time_counter])
                        self.main_plot.legend.addItem(self.data_holder.curve_dict[dev_id], legend_string)
                    else: # if disabled
                        # remove curve from legend
                        self.main_plot.legend.removeItem(self.data_holder.curve_dict[dev_id])
                # other devices
                # if Plot to main is True
                elif dev.child('Plot to main').value():
                    # compile legend string - device name and current value
                    if dev.child('Device type').value() in [CPC, TSI_CPC]: # round value to 2 decimals
                        legend_string = device_name + ": " + str(round(self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter], 2))
                    elif dev.child('Device type').value() == ELECTROMETER: # get Voltage 2 value
                        legend_string = device_name + ": " + str(self.data_holder.plot_data[str(dev_id)+':2'][self.data_holder.time_counter])
                    else: # other devices
                        legend_string = device_name + ": " + str(self.data_holder.plot_data[str(dev_id)][self.data_holder.time_counter])
                    # add curve to legend with legend string
                    self.main_plot.legend.addItem(self.data_holder.curve_dict[dev_id], legend_string)
                else: # if False
                    # remove curve from legend
                    self.main_plot.legend.removeItem(self.data_holder.curve_dict[dev_id])

    def pulse_quality_update(self, device_id):
        """Update CPC pulse quality scatter plot and labels."""
        try:
            widget = self.data_holder.device_widgets[device_id].pulse_quality
            draw_limit_h = widget.history_time
            draw_limit_s = draw_limit_h * 3600
            avg_time = widget.average_time * 3600
            avg_pulse_duration = nanmean(self.data_holder.plot_data[str(device_id) + ':pd'][-avg_time:])
            avg_pulse_ratio = nanmean(self.data_holder.plot_data[str(device_id) + ':pr'][-avg_time:])
            sliced_pd = self.data_holder.plot_data[str(device_id) + ':pd'][-1:-1 * (draw_limit_s + 1):-1 * draw_limit_h]
            sliced_pr = self.data_holder.plot_data[str(device_id) + ':pr'][-1:-1 * (draw_limit_s + 1):-1 * draw_limit_h]
            widget.data_points.setData(sliced_pd, sliced_pr)

            check_value = self.data_holder.latest_data[device_id][0] * self.data_holder.latest_settings[device_id][2]
            if 50 < check_value < 5000:
                widget.current_point.setData(x=[self.data_holder.plot_data[str(device_id) + ':pd'][-1]], y=[self.data_holder.plot_data[str(device_id) + ':pr'][-1]])
                widget.current_duration.setText(str(round(self.data_holder.plot_data[str(device_id) + ':pd'][-1], 3)))
                widget.current_ratio.setText(str(round(self.data_holder.plot_data[str(device_id) + ':pr'][-1], 3)))
            else:
                widget.current_point.setData(x=[], y=[])
                widget.current_duration.setText("Concentration out of range")
                widget.current_ratio.setText("Concentration out of range")

            widget.average_point.setData(x=[avg_pulse_duration], y=[avg_pulse_ratio])
            widget.average_duration.setText(str(round(avg_pulse_duration, 2)))
            widget.average_ratio.setText(str(round(avg_pulse_ratio, 2)))
        except Exception as e:
            logging.error(traceback.format_exc())
