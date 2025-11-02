from numpy import nan
from plots.device_plots import SinglePlot
from config import CO2_SENSOR
from devices.base_device import SimpleDevice, DefaultSinglePlotConfig
from devices.registry import register_device

# CO2 sensor widget
@register_device(CO2_SENSOR)
class CO2Widget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=CO2_SENSOR, *args, **kwargs)

        # Create plot widget
        self.plot_tab = SinglePlot(device_type=CO2_SENSOR)
        self.addTab(self.plot_tab, "CO2 plot")

        # Use default plot configuration (auto-plots first value from current_data)
        self.plot_config = DefaultSinglePlotConfig(self)

    def get_read_command(self):
        """CO2 sensor requires a read command."""
        return ":MEAS:CO2"

    def parse_message(self, message, data_holder=None):
        """Parse CO2 sensor data: value1;value2;..."""
        # Base class handles IDN responses
        if self.is_idn_response(message):
            return self.handle_standard_idn(message)

        try:
            # Parse semicolon-separated data
            readings = list(map(float, message.split(";")))

            # Validate data (check if first value is not 0)
            if readings[0] != 0:
                # Update data object
                self.current_data.co2 = readings[0]
                self.current_data.temperature = readings[1] if len(readings) > 1 else nan
                self.current_data.humidity = readings[2] if len(readings) > 2 else nan

                # Use base class helper to create response
                return self.data_response(message, ':MEAS:CO2')
            else:
                # Data is 0, not valid
                return self.error_response(message, 'Invalid data (zero)', ':MEAS:CO2')

        except Exception as e:
            return self.error_response(message, e)

    def supports_idn_inquiry(self):
        """CO2 sensor supports IDN inquiry."""
        return True

    # send_read_commands() uses default implementation from SimpleDevice

__all__ = ['CO2Widget']
