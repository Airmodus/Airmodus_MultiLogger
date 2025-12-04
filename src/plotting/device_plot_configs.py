"""
Plot configuration classes for devices.

This module separates plotting logic from device logic by providing
configuration classes that define how each device type should be plotted.
Each device references a plot config instance via self.plot_config.

Design principle: Composition over inheritance - devices reference plot configs
instead of inheriting bloated plotting methods.
"""

import logging
import traceback
from numpy import nan, nanmean, array, polyval
from config import PSM, CPC, TSI_CPC, ELECTROMETER, RHTP, AFM, CO2_SENSOR, EDILUTER, EXAMPLE_DEVICE


class BasePlotConfig:
    """
    Base plot configuration class with sensible defaults.

    Each device-specific config overrides only what it needs.
    """

    def __init__(self, device_widget):
        """
        Initialize plot config.

        Args:
            device_widget: Reference to the device widget instance
        """
        self.device = device_widget

    def get_plot_keys(self):
        """
        Get plot key suffixes for this device.

        Returns:
            list of str: Plot key suffixes (e.g., [''] for single value,
                        [':1', ':2', ':3'] for multiple values)
        """
        return ['']  # Default: single plot

    def get_rolling_buffer_keys(self):
        """
        Get rolling buffer configurations for special plot types.

        Returns:
            dict: Mapping of key suffix to buffer size in seconds
                 (e.g., {':pd': 86400} for 24-hour pulse duration buffer)
        """
        return {}  # Default: no rolling buffers

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """
        Extract and store plottable values from device data.

        This method updates plot_data arrays with the current values.
        Override this in device-specific configs.

        Args:
            dev_id: Device ID
            time_counter: Current time index
            plot_data: Plot data dictionary
            data_holder: DataHolder instance (for accessing other devices)
        """
        raise NotImplementedError("Subclasses must implement get_plot_values")

    def update_main_plot(self, dev_id, time_counter, x_time_list, plot_data,
                        curve, plot_to_main_value):
        """
        Update main plot curve with data.

        Args:
            dev_id: Device ID
            time_counter: Current time index
            x_time_list: X-axis time data
            plot_data: Plot data dictionary
            curve: PlotCurveItem to update
            plot_to_main_value: Value of "Plot to main" parameter
        """
        # Default behavior: plot the primary key if enabled
        if plot_to_main_value:
            key = self.get_main_plot_key(plot_to_main_value)
            plot_key = str(dev_id) + key
            # Only plot if key exists in plot_data
            if plot_key in plot_data:
                curve.setData(
                    x=x_time_list[:time_counter+1],
                    y=plot_data[plot_key][:time_counter+1]
                )
            else:
                curve.setData(x=[], y=[])
        else:
            curve.setData(x=[], y=[])

    def update_individual_plots(self, dev_id, time_counter, x_time_list, plot_data):
        """
        Update device's individual plot tab.

        Args:
            dev_id: Device ID
            time_counter: Current time index
            x_time_list: X-axis time data
            plot_data: Plot data dictionary
        """
        # Default: single curve plot
        if hasattr(self.device, 'plot_tab') and self.device.plot_tab:
            self.device.plot_tab.curve.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)][:time_counter+1]
            )

    def get_main_plot_key(self, selector_value=None):
        """
        Get the plot data key for main plot.

        Args:
            selector_value: Value from "Plot to main" dropdown
                           - True/False for single-value devices
                           - Key string (e.g., ':rh') for multi-value devices

        Returns:
            str: Plot key suffix (e.g., '' or ':rh')
        """
        if selector_value is True:
            return ''  # Single-value device
        return selector_value if selector_value else ''

    def get_viewbox_type(self):
        """
        Get the viewbox type for main plot.

        Returns:
            int: Device type constant for viewbox selection
        """
        return self.device.dev_type  # Default: own viewbox

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """
        Get value to display in legend.

        Args:
            dev_id: Device ID
            time_counter: Current time index
            plot_data: Plot data dictionary
            selector_value: Value from "Plot to main" dropdown (if applicable)

        Returns:
            float or str: Value to display
        """
        key = self.get_main_plot_key(selector_value)
        return plot_data[str(dev_id)+key][time_counter]

    def get_start_time_key(self):
        """
        Get the plot key to use for start time detection.

        Returns:
            str: Plot key suffix for detecting first valid data point
        """
        return ''  # Default: primary key

    def should_skip_normal_plotting(self, dev_id, data_holder):
        """
        Check if device is in a special mode that skips normal plotting.

        This is used for special operational modes like CPC pulse analysis,
        calibration modes, etc. where normal data plotting should be suspended.

        Args:
            dev_id: Device ID
            data_holder: DataHolder instance

        Returns:
            bool: True if normal plotting should be skipped
        """
        return False  # Default: always plot normally

    def handle_special_mode(self, dev_id, time_counter, plot_data, data_holder):
        """
        Handle data collection during special modes.

        Called when should_skip_normal_plotting() returns True.
        Override to implement special mode data handling (e.g., pulse analysis).

        Args:
            dev_id: Device ID
            time_counter: Current time index
            plot_data: Plot data dictionary
            data_holder: DataHolder instance
        """
        pass  # Default: no special mode handling

    def update_auxiliary_plots(self, dev_id, time_counter, x_time_list, plot_data, data_holder):
        """
        Update auxiliary/secondary plots after main individual plot update.

        Override in devices with additional visualizations beyond the main plot
        (e.g., CPC pulse quality scatter plot, calibration plots).

        Args:
            dev_id: Device ID
            time_counter: Current time index
            x_time_list: X-axis time data
            plot_data: Plot data dictionary
            data_holder: DataHolder instance
        """
        pass  # Default: no auxiliary plots

    def update_follow_mode(self, current_time, time_window):
        """
        Update X-axis range for Follow mode.

        Override if device has non-standard plot structure (e.g., ELECTROMETER
        with multiple separate plots instead of single plot).

        Args:
            current_time: Current timestamp
            time_window: Time window in seconds
        """
        # Default: update single plot
        if hasattr(self.device, 'plot_tab') and hasattr(self.device.plot_tab, 'plot'):
            self.device.plot_tab.plot.setXRange(
                current_time - time_window,
                current_time,
                padding=0
            )

    def get_main_axis_config(self, plot_to_main_value):
        """
        Get axis configuration for main plot.

        Override in devices with dynamic axis labels (e.g., RHTP/AFM where
        label changes based on selector: "RH" → "RHTP RH %").

        Args:
            plot_to_main_value: Value of "Plot to main" parameter (str or bool)

        Returns:
            dict or None: {
                'viewbox_type': int,  # Device type constant
                'show': bool,         # Whether to show axis
                'label': str,         # Axis label (optional)
                'units': str,         # Units (optional)
                'color': str,         # Color (optional)
            } or None if axis should be hidden
        """
        # Default: simple show/hide based on plot_to_main_value
        if plot_to_main_value:
            return {
                'viewbox_type': self.get_viewbox_type(),
                'show': True
            }
        return None


class EDiluterPlotConfig(BasePlotConfig):
    """Plot configuration for eDiluter."""

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """Store temp1 value."""
        ediluter_data = self.device.current_data
        plot_data[str(dev_id)][time_counter] = ediluter_data.temp1


class CPCPlotConfig(BasePlotConfig):
    """Plot configuration for CPC."""

    def get_plot_keys(self):
        """CPC has concentration and raw concentration."""
        return ['', ':raw']

    def get_rolling_buffer_keys(self):
        """CPC has 24-hour rolling buffers for pulse analysis."""
        return {':pd': 86400, ':pr': 86400}

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """
        Store CPC concentration values and pulse quality data.

        Handles:
        - Pulse analysis mode
        - PSM connection (plot PSM concentration instead of CPC)
        - Pulse duration/ratio calculation
        """
        # Check if in pulse analysis mode
        if hasattr(self.device, 'pulse_analysis_index'):
            if self.device.pulse_analysis_index is not None and self.device.pulse_analysis_index >= 0:
                # Pulse analysis mode - handled separately
                return

        # Check if this CPC is connected to any PSM
        psm_connection = False
        if data_holder and hasattr(data_holder, 'device_widgets'):
            for widget in data_holder.device_widgets.values():
                if widget.device_config.device_type == PSM:
                    connected_cpc = widget.device_config.extra_params.get('connected_cpc', 'None')
                    if connected_cpc == dev_id:
                        # Plot PSM concentration instead of CPC
                        psm_id = widget.device_config.device_id
                        psm_data = data_holder.get_device_data(psm_id)
                        if psm_data:
                            plot_data[str(dev_id)][time_counter] = psm_data.concentration_psm
                            psm_connection = True
                        break

        # If not connected to PSM, plot CPC concentration
        if not psm_connection:
            cpc_data = self.device.current_data
            plot_data[str(dev_id)][time_counter] = cpc_data.concentration

        # Always store raw concentration
        cpc_data = self.device.current_data
        plot_data[str(dev_id)+':raw'][time_counter] = cpc_data.concentration

        # Update pulse duration and pulse ratio for rolling buffers
        self._update_pulse_quality(dev_id, time_counter, plot_data)

    def _update_pulse_quality(self, dev_id, time_counter, plot_data):
        """Calculate and store pulse duration and pulse ratio."""
        try:
            cpc_data = self.device.current_data
            cpc_settings = self.device.settings

            # Check if concentration is in valid range for pulse analysis
            check_value = cpc_data.concentration * cpc_settings.measured_cpc_flow if cpc_settings else 0
            if check_value > 50 and check_value < 5000:
                # Calculate pulse duration
                if cpc_data.number_of_pulses == 0:
                    pulse_duration = nan
                else:
                    # pulse duration = dead time * 1000 (micro to nano) / number of pulses
                    pulse_duration = round(cpc_data.dead_time * 1000 / cpc_data.number_of_pulses, 2)

                # Update the data object so database can use the calculated value
                cpc_data.pulse_duration = pulse_duration

                # Store values
                plot_data[str(dev_id)+':pd'][-1] = pulse_duration
                plot_data[str(dev_id)+':pr'][-1] = cpc_data.pulse_ratio
            else:
                # Out of range - store NaN
                cpc_data.pulse_duration = nan
                plot_data[str(dev_id)+':pd'][-1] = nan
                plot_data[str(dev_id)+':pr'][-1] = nan
        except Exception as e:
            print(traceback.format_exc())
            logging.exception(e)
            # Store NaN on error
            plot_data[str(dev_id)+':pd'][-1] = nan
            plot_data[str(dev_id)+':pr'][-1] = nan

    def update_individual_plots(self, dev_id, time_counter, x_time_list, plot_data):
        """Update CPC plot with raw concentration."""
        if hasattr(self.device, 'plot_tab') and self.device.plot_tab:
            self.device.plot_tab.curve.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':raw'][:time_counter+1]
            )

    def get_start_time_key(self):
        """Use raw concentration for start time detection."""
        return ':raw'

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """Round CPC values to 2 decimals for legend."""
        value = plot_data[str(dev_id)][time_counter]
        return round(value, 2)

    def update_auxiliary_plots(self, dev_id, time_counter, x_time_list, plot_data, data_holder):
        """Update CPC pulse quality scatter plot and labels."""
        try:
            widget = self.device.pulse_quality
            draw_limit_h = widget.history_time
            draw_limit_s = draw_limit_h * 3600
            avg_time = widget.average_time * 3600

            # Calculate averages from rolling buffers
            avg_pulse_duration = nanmean(plot_data[str(dev_id) + ':pd'][-avg_time:])
            avg_pulse_ratio = nanmean(plot_data[str(dev_id) + ':pr'][-avg_time:])

            # Slice data for visualization (history time window)
            sliced_pd = plot_data[str(dev_id) + ':pd'][-1:-1 * (draw_limit_s + 1):-1 * draw_limit_h]
            sliced_pr = plot_data[str(dev_id) + ':pr'][-1:-1 * (draw_limit_s + 1):-1 * draw_limit_h]
            widget.data_points.setData(sliced_pd, sliced_pr)

            # Update current point if concentration in valid range
            cpc_data = self.device.current_data
            cpc_settings = self.device.settings
            check_value = cpc_data.concentration * cpc_settings.measured_cpc_flow if cpc_settings else 0
            if 50 < check_value < 5000:
                widget.current_point.setData(
                    x=[plot_data[str(dev_id) + ':pd'][-1]],
                    y=[plot_data[str(dev_id) + ':pr'][-1]]
                )
                widget.current_duration.setText(str(round(plot_data[str(dev_id) + ':pd'][-1], 3)))
                widget.current_ratio.setText(str(round(plot_data[str(dev_id) + ':pr'][-1], 3)))
            else:
                widget.current_point.setData(x=[], y=[])
                widget.current_duration.setText("Concentration out of range")
                widget.current_ratio.setText("Concentration out of range")

            # Update average point
            widget.average_point.setData(x=[avg_pulse_duration], y=[avg_pulse_ratio])
            widget.average_duration.setText(str(round(avg_pulse_duration, 2)))
            widget.average_ratio.setText(str(round(avg_pulse_ratio, 2)))
        except Exception as e:
            logging.error(traceback.format_exc())

    def should_skip_normal_plotting(self, dev_id, data_holder):
        """Check if CPC is in pulse analysis mode."""
        if hasattr(self.device, 'pulse_analysis_index'):
            return (self.device.pulse_analysis_index is not None and
                    self.device.pulse_analysis_index >= 0)
        return False

    def handle_special_mode(self, dev_id, time_counter, plot_data, data_holder):
        """Handle CPC pulse analysis mode data collection."""
        try:
            # Get device data
            cpc_data = self.device.current_data

            # Calculate current pulse duration
            dead_time = cpc_data.dead_time
            number_of_pulses = cpc_data.number_of_pulses
            if number_of_pulses == 0:
                pulse_duration = nan
            else:
                pulse_duration = round(dead_time * 1000 / number_of_pulses, 2)

            # Get current threshold value
            from config import PULSE_ANALYSIS_THRESHOLDS
            threshold_value = PULSE_ANALYSIS_THRESHOLDS[self.device.pulse_analysis_index]

            # Add analysis point to pulse quality widget
            self.device.pulse_quality.add_analysis_point(pulse_duration, threshold_value)
        except Exception as e:
            print(traceback.format_exc())
            logging.exception(e)
            # Raise exception to signal error - plot_manager will catch and stop analysis
            raise PulseAnalysisError(f"Pulse analysis failed for device {dev_id}") from e


class PulseAnalysisError(Exception):
    """Exception raised when pulse analysis encounters an error."""
    pass


class TSICPCPlotConfig(BasePlotConfig):
    """Plot configuration for TSI CPC."""

    def get_plot_keys(self):
        """TSI CPC has concentration and raw concentration."""
        return ['', ':raw']

    def get_viewbox_type(self):
        """TSI CPC uses CPC viewbox."""
        return CPC

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """Store TSI CPC concentration (same as CPC but no pulse quality)."""
        # Check for PSM connection (same logic as CPC)
        psm_connection = False
        if data_holder and hasattr(data_holder, 'device_widgets'):
            for widget in data_holder.device_widgets.values():
                if widget.device_config.device_type == PSM:
                    connected_cpc = widget.device_config.extra_params.get('connected_cpc', 'None')
                    if connected_cpc == dev_id:
                        psm_id = widget.device_config.device_id
                        psm_data = data_holder.get_device_data(psm_id)
                        if psm_data:
                            plot_data[str(dev_id)][time_counter] = psm_data.concentration_psm
                            psm_connection = True
                        break

        if not psm_connection:
            cpc_data = self.device.current_data
            plot_data[str(dev_id)][time_counter] = cpc_data.concentration

        # Raw concentration
        cpc_data = self.device.current_data
        plot_data[str(dev_id)+':raw'][time_counter] = cpc_data.concentration

    def update_individual_plots(self, dev_id, time_counter, x_time_list, plot_data):
        """Update TSI CPC plot with raw concentration."""
        if hasattr(self.device, 'plot_tab') and self.device.plot_tab:
            self.device.plot_tab.curve.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':raw'][:time_counter+1]
            )

    def get_start_time_key(self):
        """Use raw concentration for start time detection."""
        return ':raw'

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """Round TSI CPC values to 2 decimals for legend."""
        value = plot_data[str(dev_id)][time_counter]
        return round(value, 2)


class PSMPlotConfig(BasePlotConfig):
    """Plot configuration for PSM."""

    def get_plot_keys(self):
        """PSM has saturator flow and concentration."""
        return ['', ':conc']

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """Store PSM saturator flow and concentration."""
        psm_data = self.device.current_data
        # Saturator flow (default key '')
        plot_data[str(dev_id)][time_counter] = psm_data.saturator_flow
        # Concentration (key ':conc') - calculated in calculate_connected_cpc_values
        plot_data[str(dev_id)+':conc'][time_counter] = psm_data.concentration_psm

    def get_viewbox_type(self):
        """PSM uses PSM viewbox (both 2.0 and Retrofit)."""
        return PSM

    def update_main_plot(self, dev_id, time_counter, x_time_list, plot_data,
                        curve, plot_to_main_value):
        """Update main plot with selected value (Flow or Concentration)."""
        # None means "don't plot", empty string '' means Flow (default)
        if plot_to_main_value is not None:
            key = self.get_main_plot_key(plot_to_main_value)
            curve.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+key][:time_counter+1]
            )
        else:
            curve.setData(x=[], y=[])

    def get_main_axis_config(self, plot_to_main_value):
        """
        Get axis configuration for PSM main plot.

        Label changes based on selector: Flow or Concentration.
        """
        # None means "don't plot" - hide axis
        if plot_to_main_value is None:
            return None

        # Map selector value to axis configuration
        axis_configs = {
            '': {'label': 'PSM saturator flow rate', 'units': 'lpm', 'color': 'w'},
            ':conc': {'label': 'PSM concentration', 'units': '#/cc', 'color': 'w'},
        }

        config = axis_configs.get(plot_to_main_value)
        if config:
            return {
                'viewbox_type': PSM,
                'show': True,
                **config
            }
        return None

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """Get value for legend based on selector (Flow or Concentration)."""
        key = self.get_main_plot_key(selector_value)
        if key is not None:
            value = plot_data[str(dev_id)+key][time_counter]
            return round(value, 2) if value == value else value  # Handle NaN
        return ''

    def calculate_connected_cpc_values(self, data_holder):
        """
        Calculate PSM concentration from connected CPC.

        This is called before plot data updates to compute dilution-corrected
        concentration from the connected CPC.

        Args:
            data_holder: DataHolder instance with device data
        """
        # Get PSM config from device widget
        psm_widget = self.device
        dev_type = psm_widget.device_config.device_type
        psm_id = psm_widget.device_config.device_id
        cpc_id = psm_widget.device_config.extra_params.get('connected_cpc', 'None')

        if cpc_id == 'None':
            return

        # Check if connected CPC is doing pulse analysis
        cpc_widget = data_holder.device_widgets.get(cpc_id)
        if cpc_widget and hasattr(cpc_widget, 'pulse_analysis_index'):
            if cpc_widget.pulse_analysis_index is not None and cpc_widget.pulse_analysis_index >= 0:
                return  # CPC is in pulse analysis mode, don't use its data

        # Check if CPC is connected (runtime state)
        if not cpc_widget or not cpc_widget.is_connected:
            return

        # Get PSM and CPC widgets
        psm_widget = self.device
        cpc_widget = psm_widget.connected_cpc_device
        if not cpc_widget:
            return

        cpc_data = cpc_widget.current_data
        psm_data = psm_widget.current_data
        psm_settings = psm_widget.settings

        # Get CPC flow rate from PSM settings
        cpc_flow = float(psm_settings.cpc_inlet_flow) if psm_settings else 0.0

        # Calculate inlet flow based on PSM type
        if not self.device.is_psm2:
            # Retrofit: Get CO flow rate from PSM widget
            co_flow = round(psm_widget.set_tab.set_co_flow.value_spinbox.value(), 3)
            if co_flow == 0:  # CO flow not set
                psm_widget.set_tab.set_co_flow.set_red_color()
                data_holder.error_status = 1
            else:
                psm_widget.set_tab.set_co_flow.set_default_color()
            inlet_flow = cpc_flow + co_flow - float(psm_data.saturator_flow) - float(psm_data.excess_flow)

        else:
            # PSM 2.0: Get vacuum flow from PSM data
            vacuum_flow = float(psm_data.vacuum_flow)
            inlet_flow = cpc_flow + vacuum_flow - float(psm_data.saturator_flow) - float(psm_data.excess_flow)
            inlet_flow0 = cpc_flow + vacuum_flow - 4 + float(psm_data.saturator_flow) + float(psm_data.excess_flow)

        # Store inlet flow in PSM settings
        if psm_settings:
            psm_settings.inlet_flow_rate = round(inlet_flow, 3)
        # Show inlet flow in PSM widget
        psm_widget.status_tab.flow_inlet.change_value(str(round(inlet_flow, 3)))

        # Calculate polynomial correction factor
        if psm_data.poly_correction == 0:
            # Calculate from saturator flow
            if not self.device.is_psm2:
                # Retrofit polynomial coefficients
                pcor = array([-0.0272052, 0.11394213, -0.08959011, -0.20675596, 0.24343024, 1.10531145])
            else:
                # PSM 2.0 polynomial coefficients
                pcor = array([0.12949491, -0.50587616, 0.57214191, 0.76108161])
            poly_correction = polyval(pcor, float(psm_data.saturator_flow))
        else:
            poly_correction = psm_data.poly_correction

        # Calculate dilution correction factor
        if not self.device.is_psm2:
            # Retrofit dilution calculation
            dilution_correction_factor = (inlet_flow + float(psm_data.excess_flow) + float(psm_data.saturator_flow)) / inlet_flow
        else:
            # PSM 2.0 dilution calculation
            dilution_correction_factor = (inlet_flow + 4 - float(psm_data.excess_flow) - float(psm_data.saturator_flow)) / inlet_flow

        # Calculate concentration from PSM
        concentration_from_psm = float(cpc_data.concentration) * dilution_correction_factor / poly_correction
        psm_data.concentration_psm = round(concentration_from_psm, 2)

        # Copy CPC data to PSM data if Airmodus CPC
        if cpc_widget.device_config.device_type == CPC:
            psm_data.cpc_concentration = cpc_data.concentration
            psm_data.cpc_dilution_correction = round(dilution_correction_factor, 3)
            psm_data.cpc_temp_sat = cpc_data.temp_saturator
            psm_data.cpc_temp_con = cpc_data.temp_condenser
            psm_data.cpc_temp_opt = cpc_data.temp_optics
            psm_data.cpc_temp_cab = cpc_data.temp_cabin
            psm_data.cpc_pres_crit = cpc_data.pres_critical_orifice
            psm_data.cpc_pres_noz = cpc_data.pres_nozzle
            psm_data.cpc_pres_in = cpc_data.pres_inlet
            psm_data.cpc_liquid = cpc_data.liquid_level
            psm_data.cpc_pulses = cpc_data.number_of_pulses
            psm_data.cpc_dead_time = cpc_data.dead_time
            psm_data.cpc_total_errors = cpc_data.total_errors
            psm_data.cpc_status_hex = cpc_data.status_hex
        # If TSI CPC
        elif cpc_widget.device_config.device_type == TSI_CPC:
            psm_data.cpc_concentration = cpc_data.concentration
            psm_data.cpc_dilution_correction = round(dilution_correction_factor, 3)


class ElectrometerPlotConfig(BasePlotConfig):
    """Plot configuration for Electrometer (3 voltage channels)."""

    def get_plot_keys(self):
        """Electrometer has 3 voltage channels."""
        return [':1', ':2', ':3']

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """Store all 3 voltage values."""
        elec_data = self.device.current_data
        plot_data[str(dev_id)+':1'][time_counter] = elec_data.voltage1
        plot_data[str(dev_id)+':2'][time_counter] = elec_data.voltage2
        plot_data[str(dev_id)+':3'][time_counter] = elec_data.voltage3

    def get_main_plot_key(self, selector_value=None):
        """Electrometer plots Voltage 2 on main."""
        return ':2'

    def update_individual_plots(self, dev_id, time_counter, x_time_list, plot_data):
        """Update Electrometer plot with all 3 voltages."""
        if hasattr(self.device, 'plot_tab') and self.device.plot_tab:
            self.device.plot_tab.curve1.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':1'][:time_counter+1]
            )
            self.device.plot_tab.curve2.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':2'][:time_counter+1]
            )
            self.device.plot_tab.curve3.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':3'][:time_counter+1]
            )

    def get_start_time_key(self):
        """Use voltage 1 for start time detection."""
        return ':1'

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """Return Voltage 2 for legend."""
        return plot_data[str(dev_id)+':2'][time_counter]

    def update_follow_mode(self, current_time, time_window):
        """Update all 3 ELECTROMETER plots for Follow mode."""
        if hasattr(self.device, 'plot_tab'):
            for plot in self.device.plot_tab.plots:
                plot.setXRange(
                    current_time - time_window,
                    current_time,
                    padding=0
                )


class RHTPPlotConfig(BasePlotConfig):
    """Plot configuration for RHTP (humidity, temperature, pressure)."""

    def get_plot_keys(self):
        """RHTP has RH, T, and P."""
        return [':rh', ':t', ':p']

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """Store RH, T, P values."""
        rhtp_data = self.device.current_data
        plot_data[str(dev_id)+':rh'][time_counter] = rhtp_data.humidity
        plot_data[str(dev_id)+':t'][time_counter] = rhtp_data.temperature
        plot_data[str(dev_id)+':p'][time_counter] = rhtp_data.pressure

    def update_individual_plots(self, dev_id, time_counter, x_time_list, plot_data):
        """Update RHTP plot with all 3 values."""
        if hasattr(self.device, 'plot_tab') and self.device.plot_tab:
            self.device.plot_tab.curve1.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':rh'][:time_counter+1]
            )
            self.device.plot_tab.curve2.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':t'][:time_counter+1]
            )
            self.device.plot_tab.curve3.setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':p'][:time_counter+1]
            )

    def get_start_time_key(self):
        """Use RH for start time detection."""
        return ':rh'

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """Get value for legend based on selector."""
        key = self.get_main_plot_key(selector_value)
        if key:
            return plot_data[str(dev_id)+key][time_counter]
        return ''

    def get_main_axis_config(self, plot_to_main_value):
        """
        Get axis configuration for RHTP main plot.

        Label changes based on selector: :rh, :t, or :p.
        """
        if not plot_to_main_value:
            return None

        axis_configs = {
            ':rh': {'label': 'RHTP RH', 'units': '%', 'color': 'w'},
            ':t': {'label': 'RHTP T', 'units': '°C', 'color': 'w'},
            ':p': {'label': 'RHTP P', 'units': 'Pa', 'color': 'w'},
        }

        config = axis_configs.get(plot_to_main_value)
        if config:
            return {
                'viewbox_type': RHTP,
                'show': True,
                **config
            }
        return None


class AFMPlotConfig(BasePlotConfig):
    """Plot configuration for AFM (flow, standard flow, RH, T, P)."""

    def get_plot_keys(self):
        """AFM has flow, standard flow, RH, T, P."""
        return [':f', ':sf', ':rh', ':t', ':p']

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """Store all AFM values."""
        afm_data = self.device.current_data
        plot_data[str(dev_id)+':f'][time_counter] = afm_data.flow
        plot_data[str(dev_id)+':sf'][time_counter] = afm_data.saturator_flow
        plot_data[str(dev_id)+':rh'][time_counter] = afm_data.humidity
        plot_data[str(dev_id)+':t'][time_counter] = afm_data.temperature
        plot_data[str(dev_id)+':p'][time_counter] = afm_data.pressure

    def update_individual_plots(self, dev_id, time_counter, x_time_list, plot_data):
        """Update AFM plot with all 5 values."""
        if hasattr(self.device, 'plot_tab') and self.device.plot_tab:
            self.device.plot_tab.curves[0].setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':f'][:time_counter+1]
            )
            self.device.plot_tab.curves[1].setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':sf'][:time_counter+1]
            )
            self.device.plot_tab.curves[2].setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':rh'][:time_counter+1]
            )
            self.device.plot_tab.curves[3].setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':t'][:time_counter+1]
            )
            self.device.plot_tab.curves[4].setData(
                x=x_time_list[:time_counter+1],
                y=plot_data[str(dev_id)+':p'][:time_counter+1]
            )

    def get_start_time_key(self):
        """Use RH for start time detection."""
        return ':rh'

    def get_legend_value(self, dev_id, time_counter, plot_data, selector_value=None):
        """Get value for legend based on selector."""
        key = self.get_main_plot_key(selector_value)
        if key:
            return plot_data[str(dev_id)+key][time_counter]
        return ''

    def get_main_axis_config(self, plot_to_main_value):
        """
        Get axis configuration for AFM main plot.

        Label changes based on selector: :f or :sf.
        """
        if not plot_to_main_value:
            return None

        axis_configs = {
            ':f': {'label': 'AFM flow', 'units': 'lpm', 'color': 'w'},
            ':sf': {'label': 'AFM standard flow', 'units': 'slpm', 'color': 'w'},
        }

        config = axis_configs.get(plot_to_main_value)
        if config:
            return {
                'viewbox_type': AFM,
                'show': True,
                **config
            }
        return None


class ExampleDevicePlotConfig(BasePlotConfig):
    """Plot configuration for example/test device."""

    def get_plot_values(self, dev_id, time_counter, plot_data, data_holder=None):
        """Generate random test value for example device."""
        import random
        random_value = round(random.random() * 100, 2)  # 0-100

        # Update device data
        self.device.current_data.random_value = random_value

        # Store in plot data
        plot_data[str(dev_id)][time_counter] = random_value
