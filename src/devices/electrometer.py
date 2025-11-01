from numpy import nan
from plots.device_plots import ElectrometerPlot
from config import ELECTROMETER
from devices.base_device import SimpleDevice
from devices.device_data import ElectrometerData

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

            # Update data object
            self.current_data.voltage1 = readings[0]
            self.current_data.voltage2 = readings[1] if len(readings) > 1 else nan
            self.current_data.voltage3 = readings[2] if len(readings) > 2 else nan

            # Data stored in self.current_data by base class
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
