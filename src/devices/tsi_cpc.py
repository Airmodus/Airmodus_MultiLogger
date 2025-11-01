from plots.device_plots import SinglePlot
from config import TSI_CPC, CPC
from devices.base_device import SimpleDevice
from devices.device_data import TSI_CPCData

# TSI CPC widget
class TSIWidget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=TSI_CPC, *args, **kwargs)
        # create plot widget for TSI CPC (uses CPC plot type)
        self.plot_tab = SinglePlot(device_type=CPC)
        self.addTab(self.plot_tab, "TSI CPC plot")

    def get_read_command(self):
        """TSI CPC auto-pushes data, no read command needed."""
        return None

    def parse_message(self, message, data_holder=None):
        """Parse TSI CPC data: concentration\rinstrument_errors_hex."""
        try:
            # Parse data: concentration (float) and error hex (separated by \r)
            readings = message.split("\r")

            if len(readings) >= 2:
                concentration = float(readings[0])
                errors_hex = readings[1]

                # Update data object
                self.current_data.concentration = concentration
                self.current_data.error_hex = errors_hex

                # Data stored in self.current_data by base class

                # Check if there are any errors
                has_errors = int(errors_hex, 16) != 0

                return {
                    'type': 'data',
                    'data': [concentration, errors_hex],
                    'command': 'auto-push',
                    'raw': message,
                    'update_gui': False,
                    'has_errors': has_errors
                }
            else:
                return {
                    'type': 'error',
                    'command': 'auto-push',
                    'data': None,
                    'raw': message,
                    'error': f'Invalid data format: expected 2 parts, got {len(readings)}',
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

__all__ = ['TSIWidget']
