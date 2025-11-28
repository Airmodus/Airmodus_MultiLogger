from plots.device_plots import SinglePlot
from config import TSI_CPC, CPC
from devices.base_device import SimpleDevice
from devices.device_data import TSI_CPCData
from plotting.device_plot_configs import TSICPCPlotConfig
from devices.data_writers import TSICPCDataWriter

# TSI CPC widget
class TSIWidget(SimpleDevice):
    def __init__(self, device_config, *args, **kwargs):
        super().__init__(device_config, *args, **kwargs)
        # create plot widget for TSI CPC (uses CPC plot type)
        self.plot_tab = SinglePlot(device_type=CPC)
        self.addTab(self.plot_tab, "Plot")

        # Plot configuration (composition over inheritance)
        self.plot_config = TSICPCPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = TSICPCDataWriter(self)

        # Add Device tab at the end
        self._add_device_tab_at_end()

    def get_plot_keys(self):
        """TSI CPC has concentration and raw concentration plots like Airmodus CPC."""
        return ['', ':raw']

    def get_plot_value_labels(self):
        """Return labels for TSI CPC plot values."""
        return {
            '': 'Concentration (#/cc)',
            ':raw': 'Raw Concentration (#/cc)'
        }

    def get_read_command(self):
        """TSI CPC auto-pushes data, no read command needed."""
        return None

    def get_status_bar_text(self):
        """Get formatted text for status bar display."""
        if self.current_data and hasattr(self.current_data, 'concentration'):
            conc = self.current_data.concentration
            if conc is not None:
                return f"{conc:.1f} #/cc"
        return super().get_status_bar_text()

    def get_read_command_sequence(self, ten_hz=False):
        """
        TSI CPC requires multiple sequential commands with timing delays.

        Sequence:
        1. RD - Read concentration
        2. RIE (150ms delay) - Read instrument errors
        """
        return [
            ('RD', 0),
            ('RIE', 150),
        ]

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

    def send_read_commands(self, dev_conn, device_config):
        """Send TSI CPC read commands."""
        dev_conn.send_multiple_messages(self)

__all__ = ['TSIWidget']
