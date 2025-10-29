from plots.device_plots import TriplePlot
from config import RHTP
from devices.base_device import SimpleDevice

# RHTP widget
class RHTPWidget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=RHTP, *args, **kwargs)
        # create plot widget for RHTP
        self.plot_tab = TriplePlot(device_type=RHTP)
        self.addTab(self.plot_tab, "RHTP plot")

    def get_read_command(self):
        """RHTP auto-pushes data, no read command needed."""
        return None

    def parse_message(self, message, data_holder=None):
        """Parse RHTP data: RH, T, P (comma-separated)."""
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

            # Parse comma-separated data (RH, T, P)
            readings = message.strip('\r\n').split(", ")

            # Validate data (should have 3 values)
            if len(readings) == 3:
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
                    'error': f'Invalid data length: {len(readings)} (expected 3)',
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

__all__ = ['RHTPWidget']
