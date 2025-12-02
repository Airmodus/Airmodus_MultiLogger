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
        self.config = main_window.config
        self.data_holder = data_holder
        self.main_plot = main_plot

    # update plot data lists
    def update_plot_data(self):
        """Update plot data arrays with latest measurements."""
        # ----- Pre-plot calculations (e.g., PSM dilution corrections) -----
        for device_config in self.config.devices:
            try:
                device_widget = self.data_holder.device_widgets.get(device_config.device_id)
                if device_widget and hasattr(device_widget, 'is_connected') and device_widget.is_connected:
                    device_widget.perform_pre_plot_calculations(self.data_holder)
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

        # ----- update plot data -----

        self.data_holder.x_time_list = _manage_plot_array(self.data_holder.x_time_list, self.data_holder.time_counter, max_reached=self.data_holder.max_reached)
        self.data_holder.x_time_list[self.data_holder.time_counter] = self.data_holder.current_time

        # go through each device
        for device_config in self.config.devices:
            # store device id to variable for clarity
            dev_id = device_config.device_id

            try: # if one device fails, continue with the next one
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

                # Check if device is connected or is example device
                is_connected = hasattr(device_widget, 'is_connected') and device_widget.is_connected
                is_example = device_config.device_type == EXAMPLE_DEVICE

                # if device is connected, use plot config to extract and store plot values
                if is_connected or is_example:
                    # Check if device is in special mode (e.g., CPC pulse analysis)
                    if hasattr(device_widget, 'plot_config'):
                        if device_widget.plot_config.should_skip_normal_plotting(dev_id, self.data_holder):
                            try:
                                # Handle special mode data collection
                                device_widget.plot_config.handle_special_mode(
                                    dev_id, self.data_holder.time_counter,
                                    self.data_holder.plot_data, self.data_holder
                                )
                            except PulseAnalysisError as e:
                                print(traceback.format_exc())
                                logging.exception(e)
                                # Stop pulse analysis if exception occurs
                                self.main_window.data_logger.pulse_analysis_stop(dev_id, device_config)
                            continue  # Skip normal plot data update during special mode

                    # Use device plot config to extract and store plot values
                    device_widget.plot_config.get_plot_values(
                        dev_id,
                        self.data_holder.time_counter,
                        self.data_holder.plot_data,
                        self.data_holder
                    )

            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

    # update plots with plot data lists
    def update_figures_and_menus(self):
        for device_config in self.config.devices:
            dev_id = device_config.device_id
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
                plot_to_main_value = device_config.plot_to_main
                device_widget.plot_config.update_main_plot(
                    dev_id,
                    self.data_holder.time_counter,
                    self.data_holder.x_time_list,
                    self.data_holder.plot_data,
                    self.data_holder.curve_dict[dev_id],
                    plot_to_main_value
                )

                # scale x-axis range if Follow is on
                if self.config.plot_settings.follow:
                    self.main_plot.plot.setXRange(
                        self.data_holder.current_time - self.config.plot_settings.time_window_s,
                        self.data_holder.current_time, padding=0
                    )

                # Check if device is connected or is example device
                is_connected = hasattr(device_widget, 'is_connected') and device_widget.is_connected
                is_example = device_config.device_type == EXAMPLE_DEVICE

                # INDIVIDUAL PLOTS
                if is_connected or is_example:
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

                        # Update auxiliary displays (e.g., PSM contour plot)
                        device_widget.update_auxiliary_displays()

                        # scale x-axis range if Follow is on
                        if self.config.plot_settings.follow:
                            device_widget.plot_config.update_follow_mode(
                                self.data_holder.current_time,
                                self.config.plot_settings.time_window_s
                            )

                # Validate connected devices (e.g., PSM-CPC flow check)
                if is_connected:
                    device_widget.validate_connected_devices(device_config, self.data_holder, self.config)

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
        for device_config in self.config.devices:
            dev_id = device_config.device_id
            device_widget = self.data_holder.device_widgets.get(dev_id)

            # Get axis configuration from device plot config
            if device_widget and hasattr(device_widget, 'plot_config'):
                axis_config = device_widget.plot_config.get_main_axis_config(
                    device_config.plot_to_main
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
        for device_config in self.config.devices:
            dev_id = device_config.device_id
            if dev_id in self.data_holder.curve_dict:
                device_name = device_config.device_nickname or device_config.device_type_name
                device_widget = self.data_holder.device_widgets.get(dev_id)
                plot_to_main_value = device_config.plot_to_main

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
