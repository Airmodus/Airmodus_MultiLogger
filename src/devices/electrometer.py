from plots.device_plots import ElectrometerPlot
from config import ELECTROMETER
from devices.base_device import SimpleDevice

# ELECTROMETER widget
class ElectrometerWidget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=ELECTROMETER, *args, **kwargs)
        # create plot widget for Electrometer
        self.plot_tab = ElectrometerPlot()
        self.addTab(self.plot_tab, "Electrometer plot")

    def get_read_command(self):
        """Electrometer requires a read command."""
        return ":MEAS:V"

    def parse_message(self, message, data_holder=None):
        """Parse Electrometer data: value1;value2;... (semicolon-separated)."""
        try:
            # Parse semicolon-separated data
            readings = list(map(float, message.split(";")))
            self.latest_data = readings

            return {
                'type': 'data',
                'data': readings,
                'command': ':MEAS:V',
                'raw': message,
                'update_gui': False
            }
        except Exception as e:
            return {
                'type': 'error',
                'command': ':MEAS:V',
                'data': None,
                'raw': message,
                'error': str(e),
                'update_gui': False
            }

__all__ = ['ElectrometerWidget']
