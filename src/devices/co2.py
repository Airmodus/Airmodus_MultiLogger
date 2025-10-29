from plots.device_plots import SinglePlot
from config import CO2_SENSOR
from devices.base_device import SimpleDevice

# CO2 widget
class CO2Widget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=CO2_SENSOR, *args, **kwargs)
        # create plot widget for CO2
        self.plot_tab = SinglePlot(device_type=CO2_SENSOR)
        self.addTab(self.plot_tab, "CO2 plot")

    def get_read_command(self):
        """CO2 sensor requires a read command."""
        return ":MEAS:CO2"

    def parse_message(self, message, data_holder=None):
        """Parse CO2 sensor data: value1;value2;..."""
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

            # Parse semicolon-separated data
            readings = list(map(float, message.split(";")))

            # Validate data (check if first value is not 0)
            if readings[0] != 0:
                self.latest_data = readings
                return {
                    'type': 'data',
                    'data': readings,
                    'command': ':MEAS:CO2',
                    'raw': message,
                    'update_gui': False
                }
            else:
                # Data is 0, not valid
                return {
                    'type': 'error',
                    'command': ':MEAS:CO2',
                    'data': None,
                    'raw': message,
                    'error': 'Invalid data (zero)',
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

__all__ = ['CO2Widget']
