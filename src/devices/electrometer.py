from numpy import nan
from plots.device_plots import ElectrometerPlot
from config import ELECTROMETER
from devices.base_device import SimpleDevice
from devices.device_data import ElectrometerData
from plotting.device_plot_configs import ElectrometerPlotConfig
from devices.data_writers import ElectrometerDataWriter

# ELECTROMETER widget
class ElectrometerWidget(SimpleDevice):
    def __init__(self, device_config, *args, **kwargs):
        super().__init__(device_config, *args, **kwargs)
        # create plot widget for Electrometer
        self.plot_tab = ElectrometerPlot()
        self.addTab(self.plot_tab, "Electrometer plot")

        # Plot configuration (composition over inheritance)
        self.plot_config = ElectrometerPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = ElectrometerDataWriter(self)

        # Add Device tab at the end
        self._add_device_tab_at_end()

    def get_plot_keys(self):
        """Electrometer has three voltage channels."""
        return [':1', ':2', ':3']

    def get_plot_value_labels(self):
        """Return labels for Electrometer plot values."""
        return {
            ':1': 'Channel 1 (V)',
            ':2': 'Channel 2 (V)',
            ':3': 'Channel 3 (V)'
        }

    def get_read_command(self):
        """Electrometer requires a read command."""
        return ":MEAS:V"

    def get_status_bar_text(self):
        """Get formatted text for status bar display."""
        if self.current_data and hasattr(self.current_data, 'current'):
            current = self.current_data.current
            if current is not None:
                return f"{current:.2e} A"
        return super().get_status_bar_text()

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

    def send_read_commands(self, dev_conn, device_config):
        """
        Send Electrometer read command.

        Resets buffers and sends measurement command.
        """
        dev_conn.connection.reset_input_buffer()
        dev_conn.connection.reset_output_buffer()
        dev_conn.connection.read_all()
        dev_conn.send_message(":MEAS:V")

__all__ = ['ElectrometerWidget']
