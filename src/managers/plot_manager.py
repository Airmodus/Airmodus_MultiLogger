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
        # Before setting plot data, calculate PSM-CPC dilution corrections
        for dev in self.params.child('Device settings').children():
            try:
                dev_type = dev.child('Device type').value()
                # if device is PSM and it is connected, calculate connected CPC values
                if dev_type in [PSM, PSM2] and dev.child('Connected').value():
                    psm_id = dev.child('DevID').value()
                    psm_widget = self.data_holder.device_widgets.get(psm_id)
                    if psm_widget and hasattr(psm_widget, 'plot_config'):
                        # Use PSM plot config's calculation method
                        psm_widget.plot_config.calculate_connected_cpc_values(dev, self.data_holder)

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
                device_widget = self.data_holder.device_widgets.get(dev_id)

                # Skip if device doesn't have plot config (shouldn't happen)
                if not device_widget or not hasattr(device_widget, 'plot_config'):
                    continue

                # Get plot keys from device's plot config
                plot_keys = device_widget.plot_config.get_plot_keys()

                # if device is not yet in data_holder.plot_data dict, add it
                if str(dev_id)+plot_keys[0] not in self.data_holder.plot_data:
                    # make the new lists the same size as x_time_list
                    for key in plot_keys:
                        self.data_holder.plot_data[str(dev_id)+key] = full(len(self.data_holder.x_time_list), nan)

                # Manage all arrays for this device
                for key in plot_keys:
                    self.data_holder.plot_data[str(dev_id)+key] = _manage_plot_array(
                        self.data_holder.plot_data[str(dev_id)+key],
                        self.data_holder.time_counter,
                        max_reached=self.data_holder.max_reached
                    )

                # create rolling buffers (e.g., CPC pulse duration/ratio)
                rolling_buffers = device_widget.plot_config.get_rolling_buffer_keys()
                for buffer_key, buffer_size in rolling_buffers.items():
                    key = str(dev_id) + buffer_key
                    self.data_holder.plot_data[key] = _roll_pulse_array(self.data_holder.plot_data[key])
                
                # if device is connected, use plot config to extract and store plot values
                if dev.child('Connected').value() or dev_type == EXAMPLE_DEVICE:
                    # Handle pulse analysis mode for CPC
                    if dev_type == CPC and hasattr(device_widget, 'pulse_analysis_index'):
                        if device_widget.pulse_analysis_index is not None and device_widget.pulse_analysis_index >= 0:
                            try:
                                # Get device data
                                cpc_data = self.data_holder.get_device_data(dev_id)
                                # calculate current pulse duration
                                dead_time = cpc_data.dead_time
                                number_of_pulses = cpc_data.number_of_pulses
                                if number_of_pulses == 0:
                                    pulse_duration = nan
                                else:
                                    pulse_duration = round(dead_time * 1000 / number_of_pulses, 2)
                                # get current threshold value
                                threshold_value = PULSE_ANALYSIS_THRESHOLDS[device_widget.pulse_analysis_index]
                                # add analysis point to pulse quality widget
                                device_widget.pulse_quality.add_analysis_point(pulse_duration, threshold_value)
                            except Exception as e:
                                print(traceback.format_exc())
                                logging.exception(e)
                                # stop pulse analysis if exception occurs
                                self.main_window.pulse_analysis_stop(dev_id, dev)
                            continue  # Skip normal plot data update during pulse analysis

                    # Handle example device random value generation
                    if dev_type == EXAMPLE_DEVICE:
                        random_value = round(random.random() * 100, 2)  # 0-100
                        example_data = self.data_holder.get_device_data(dev_id)
                        example_data.random_value = random_value

                    # Use device plot config to extract and store plot values
                    device_widget.plot_config.get_plot_values(
                        dev_id,
                        self.data_holder.time_counter,
                        self.data_holder.plot_data,
                        dev,
                        self.data_holder
                    )

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

    # update plots with plot data lists
    def update_figures_and_menus(self):
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            dev_type = dev.child('Device type').value()
            device_widget = self.data_holder.device_widgets.get(dev_id)

            try: # if one device fails, continue with the next one
                # Skip if device doesn't have plot config
                if not device_widget or not hasattr(device_widget, 'plot_config'):
                    continue

                # MAIN PLOT
                # if device is not yet in data_holder.curve_dict, add it
                if dev_id not in self.data_holder.curve_dict:
                    # create curve and add to appropriate viewbox
                    self.data_holder.curve_dict[dev_id] = PlotCurveItem(pen=dev_id, connect="finite")
                    viewbox_type = device_widget.plot_config.get_viewbox_type()
                    self.main_plot.viewboxes[viewbox_type].addItem(self.data_holder.curve_dict[dev_id])

                # Update main plot curve using device's plot config
                plot_to_main_value = dev.child("Plot to main").value()
                device_widget.plot_config.update_main_plot(
                    dev_id,
                    self.data_holder.time_counter,
                    self.data_holder.x_time_list,
                    self.data_holder.plot_data,
                    self.data_holder.curve_dict[dev_id],
                    dev,
                    plot_to_main_value
                )
                
                # scale x-axis range if Follow is on
                if self.params.child('Plot settings').child('Follow').value():
                    self.main_plot.plot.setXRange(
                        self.data_holder.current_time - (self.params.child('Plot settings').child('Time window (s)').value()), 
                        self.data_holder.current_time, padding=0
                    )

                # INDIVIDUAL PLOTS
                if dev.child('Connected').value() or dev_type == EXAMPLE_DEVICE:
                    # Detect start time (first non-NaN value)
                    if dev_id not in self.data_holder.start_times:
                        try:
                            start_key = device_widget.plot_config.get_start_time_key()
                            key = str(dev_id) + start_key
                            if key in self.data_holder.plot_data:
                                if str(self.data_holder.plot_data[key][self.data_holder.time_counter]) != "nan":
                                    self.data_holder.start_times[dev_id] = self.data_holder.time_counter
                        except (KeyError, IndexError):
                            # Plot data not yet initialized for this device
                            pass

                    # if device is in start times dictionary, update individual plot
                    if dev_id in self.data_holder.start_times:
                        # Use device plot config to update individual plot
                        device_widget.plot_config.update_individual_plots(
                            dev_id,
                            self.data_holder.time_counter,
                            self.data_holder.x_time_list,
                            self.data_holder.plot_data
                        )

                        # Update CPC pulse quality plot
                        if dev_type == CPC:
                            self.pulse_quality_update(dev_id)

                        # scale x-axis range if Follow is on
                        if self.params.child('Plot settings').child('Follow').value():
                            if dev_type == ELECTROMETER: # if ELECTROMETER, update all 3 plots
                                for plot in device_widget.plot_tab.plots:
                                    plot.setXRange(
                                        self.data_holder.current_time - self.params.child('Plot settings').child('Time window (s)').value(),
                                        self.data_holder.current_time,
                                        padding=0
                                    )
                            elif hasattr(device_widget, 'plot_tab') and hasattr(device_widget.plot_tab, 'plot'):
                                device_widget.plot_tab.plot.setXRange(
                                    self.data_holder.current_time - self.params.child('Plot settings').child('Time window (s)').value(),
                                    self.data_holder.current_time,
                                    padding=0
                                )

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
                            cpc_settings = self.data_holder.get_device_settings(cpc_id)
                            cpc_sample_flow = float(cpc_settings.measured_cpc_flow) if cpc_settings else 0.0
                            # if CPC sample flow is different from value displayed in Set tab, update displayed value
                            if self.data_holder.device_widgets[dev_id].set_tab.set_cpc_sample_flow.value_spinbox.value() != cpc_sample_flow:
                                self.data_holder.device_widgets[dev_id].set_tab.set_cpc_sample_flow.value_spinbox.setValue(cpc_sample_flow)
                        
                        # if CPC inlet flow is different from value displayed in Status tab, update displayed value
                        psm_settings = self.data_holder.get_device_settings(dev_id)
                        if psm_settings:
                            cpc_flow_str = str(psm_settings.cpc_inlet_flow) + " lpm"
                            if self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.value_label.text() != cpc_flow_str:
                                # set status_tab flow_cpc color to normal and change text
                                self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.change_color(0)
                                self.data_holder.device_widgets[dev_id].status_tab.flow_cpc.change_value(cpc_flow_str)

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
            dev_id = dev.child('DevID').value()
            dev_type = dev.child('Device type').value()
            device_widget = self.data_holder.device_widgets.get(dev_id)

            # Handle special axis changes for RHTP and AFM (device-specific UI logic)
            if dev_type == RHTP:
                self.main_plot.change_rhtp_axis(dev.child('Plot to main').value())
            elif dev_type == AFM:
                self.main_plot.change_afm_axis(dev.child('Plot to main').value())
            elif dev.child('Plot to main').value() and device_widget:
                # Use viewbox type from plot config
                if hasattr(device_widget, 'plot_config'):
                    viewbox_type = device_widget.plot_config.get_viewbox_type()
                    self.main_plot.show_hide_axis(viewbox_type, True)
                else:
                    self.main_plot.show_hide_axis(dev_type, True)

    def legend_check(self):
        """Update main plot legend with current values."""
        self.main_plot.legend.clear()
        # check each device and add to legend if exists in curve_dict and Plot to main is enabled
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            if dev_id in self.data_holder.curve_dict:
                device_name = dev.child('Device nickname').value() or dev.name()
                device_widget = self.data_holder.device_widgets.get(dev_id)
                plot_to_main_value = dev.child('Plot to main').value()

                # if Plot to main is enabled
                if plot_to_main_value and device_widget and hasattr(device_widget, 'plot_config'):
                    # Use device plot config to get legend value
                    value = device_widget.plot_config.get_legend_value(
                        dev_id,
                        self.data_holder.time_counter,
                        self.data_holder.plot_data,
                        plot_to_main_value
                    )
                    legend_string = device_name + ": " + str(value)
                    # add curve to legend with legend string
                    self.main_plot.legend.addItem(self.data_holder.curve_dict[dev_id], legend_string)
                else:
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

            cpc_data = self.data_holder.get_device_data(device_id)
            cpc_settings = self.data_holder.get_device_settings(device_id)
            check_value = cpc_data.concentration * cpc_settings.measured_cpc_flow if cpc_settings else 0
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
