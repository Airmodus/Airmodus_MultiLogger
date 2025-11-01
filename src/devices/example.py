from plots.device_plots import SinglePlot
from config import EXAMPLE_DEVICE
from devices.base_device import SimpleDevice
from devices.device_data import ExampleDeviceData

# Example device widget
class ExampleDeviceWidget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=EXAMPLE_DEVICE, *args, **kwargs)
        # create plot widget for example device
        self.plot_tab = SinglePlot(device_type=EXAMPLE_DEVICE)
        self.addTab(self.plot_tab, "Example device plot")

    def get_read_command(self):
        """Example device auto-pushes data, no read command needed."""
        return None

    def parse_message(self, message, data_holder=None):
        """Parse example device data."""
        try:
            # Handle IDN responses
            if "*IDN " in message:
                serial_number = message.split(" ", 1)[1].strip()
                return {
                    'type': 'info',
                    'command': '*IDN',
                    'data': serial_number,
                    'raw': message,
                    'update_gui': False
                }

            # Parse data (expecting a single float value)
            value = float(message.strip())

            # Update data object
            self.current_data.random_value = value

            # Data stored in self.current_data by base class
            return {
                'type': 'data',
                'data': [value],
                'command': 'auto-push',
                'raw': message,
                'update_gui': False
            }
        except Exception as e:
            return {
                'type': 'error',
                'command': 'unknown',
                'data': None,
                'raw': message,
                'error': str(e),
                'update_gui': False
            }

__all__ = ['ExampleDeviceWidget']
