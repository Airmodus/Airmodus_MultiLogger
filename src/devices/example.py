from plots.device_plots import SinglePlot
from config import EXAMPLE_DEVICE
from devices.base_device import SimpleDevice, DefaultSinglePlotConfig
from devices.registry import register_device
from devices.data_writers import ExampleDataWriter
from plotting.device_plot_configs import ExampleDevicePlotConfig

# Example device widget - demonstrates minimal device pattern
@register_device(EXAMPLE_DEVICE)
class ExampleDeviceWidget(SimpleDevice):
    def __init__(self, device_config, *args, **kwargs):
        super().__init__(device_config, *args, **kwargs)

        # Create plot widget
        self.plot_tab = SinglePlot(device_type=EXAMPLE_DEVICE)
        self.addTab(self.plot_tab, "Plot")

        # Use example plot configuration (generates random test data)
        self.plot_config = ExampleDevicePlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = ExampleDataWriter(self)

    def get_read_command(self):
        """Example device auto-pushes data, no read command needed."""
        return None

    def parse_message(self, message, data_holder=None):
        """Parse example device data."""
        # Base class handles IDN responses
        if self.is_idn_response(message):
            return self.handle_standard_idn(message)

        try:
            # Parse data (expecting a single float value)
            value = float(message.strip())

            # Update data object
            self.current_data.random_value = value

            # Use base class helper to create response
            return self.data_response(message, 'auto-push')

        except Exception as e:
            # Example device - ignore errors silently
            return {
                'type': 'info',
                'command': 'unknown',
                'data': None,
                'raw': message,
                'update_gui': False
            }

__all__ = ['ExampleDeviceWidget']
