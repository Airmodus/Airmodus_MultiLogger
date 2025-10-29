from plots.device_plots import AFMPlot
from config import AFM
from devices.base_device import SimpleDevice

# AFM widget
class AFMWidget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=AFM, *args, **kwargs)
        # create plot widget for AFM
        self.plot_tab = AFMPlot()
        self.addTab(self.plot_tab, "AFM plot")

    def get_read_command(self):
        """AFM auto-pushes data, no read command needed."""
        return None

    def parse_message(self, message, data_holder=None):
        """Parse AFM data: volumetric flow, standard flow, RH, T, P (comma-separated)."""
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

            # Parse comma-separated data (volumetric flow, standard flow, RH, T, P)
            readings = message.strip('\r\n').split(", ")

            # Validate data (should have 5 values)
            if len(readings) == 5:
                self.latest_data = readings
                return {
                    'type': 'data',
                    'data': readings,
                    'command': 'auto-push',
                    'raw': message,
                    'update_gui': False
                }
            else:
                return {
                    'type': 'error',
                    'command': 'auto-push',
                    'data': None,
                    'raw': message,
                    'error': f'Invalid data length: {len(readings)} (expected 5)',
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

__all__ = ['AFMWidget']
