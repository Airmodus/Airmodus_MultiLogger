# managers/plot_manager.py
import traceback
import logging
from numpy import full, nan, nanmean, array, polyval
from pyqtgraph import PlotCurveItem
from config import *  # For constants like MAX_TIME_SEC, etc., if needed
from utils import _manage_plot_array, _roll_pulse_array
from plotting.device_plot_configs import PulseAnalysisError

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
                    # Check if device is in special mode (e.g., CPC pulse analysis)
                    if hasattr(device_widget, 'plot_config'):
                        if device_widget.plot_config.should_skip_normal_plotting(dev_id, dev, self.data_holder):
                            try:
                                # Handle special mode data collection
                                device_widget.plot_config.handle_special_mode(
                                    dev_id, self.data_holder.time_counter,
                                    self.data_holder.plot_data, dev, self.data_holder
                                )
                            except PulseAnalysisError as e:
                                print(traceback.format_exc())
                                logging.exception(e)
                                # Stop pulse analysis if exception occurs
                                self.main_window.data_logger.pulse_analysis_stop(dev_id, dev)
                            continue  # Skip normal plot data update during special mode

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

                        # Update auxiliary plots (e.g., CPC pulse quality)
                        device_widget.plot_config.update_auxiliary_plots(
                            dev_id, self.data_holder.time_counter,
                            self.data_holder.x_time_list, self.data_holder.plot_data,
                            self.data_holder
                        )

                        # Update PSM contour plot if device is PSM/PSM2
                        if dev_type in [PSM, PSM2] and hasattr(device_widget, 'contour_tab'):
                            try:
                                device_widget.contour_tab.update_contour(device_widget.current_data)
                            except Exception as e:
                                logging.error(f"Error updating PSM contour plot: {e}")
                                traceback.print_exc()

                        # scale x-axis range if Follow is on
                        if self.params.child('Plot settings').child('Follow').value():
                            device_widget.plot_config.update_follow_mode(
                                self.data_holder.current_time,
                                self.params.child('Plot settings').child('Time window (s)').value()
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

            # Get axis configuration from device plot config
            if device_widget and hasattr(device_widget, 'plot_config'):
                axis_config = device_widget.plot_config.get_main_axis_config(
                    dev.child('Plot to main').value()
                )
                if axis_config:
                    viewbox_type = axis_config['viewbox_type']
                    show = axis_config['show']

                    # If config includes axis label/units/color, apply them
                    if 'label' in axis_config:
                        self.main_plot.axes[viewbox_type].setLabel(
                            axis_config['label'],
                            units=axis_config.get('units', ''),
                            color=axis_config.get('color', 'w')
                        )
                        # Apply axis style after setting label
                        self.main_plot.set_axis_style(
                            self.main_plot.axes[viewbox_type],
                            axis_config.get('color', 'w')
                        )

                    # Show/hide the axis
                    self.main_plot.show_hide_axis(viewbox_type, show)

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
