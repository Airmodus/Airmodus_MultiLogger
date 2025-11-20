from plots.device_plots import AFMPlot
from config import AFM
from devices.base_device import SimpleDevice
from devices.device_data import AFMData
from plotting.device_plot_configs import AFMPlotConfig
from devices.data_writers import AFMDataWriter

# AFM widget
class AFMWidget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=AFM, *args, **kwargs)
        # create plot widget for AFM
        self.plot_tab = AFMPlot()
        self.addTab(self.plot_tab, "AFM plot")

        # Plot configuration (composition over inheritance)
        self.plot_config = AFMPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = AFMDataWriter(self)

    def get_plot_keys(self):
        """AFM has flow, standard flow, RH, temperature, and pressure."""
        return [':f', ':sf', ':rh', ':t', ':p']

    def get_read_command(self):
        """AFM auto-pushes data, no read command needed."""
        return None

    def get_status_bar_text(self):
        """Get formatted text for status bar display."""
        if self.current_data and hasattr(self.current_data, 'flow'):
            flow = self.current_data.flow
            if flow is not None:
                return f"{flow:.2f} L/min"
        return super().get_status_bar_text()

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
                # Update data object
                self.current_data.flow = float(readings[0])
                self.current_data.saturator_flow = float(readings[1])
                self.current_data.humidity = float(readings[2])
                self.current_data.temperature = float(readings[3])
                self.current_data.pressure = float(readings[4])

                # Data stored in self.current_data by base class
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

    def supports_idn_inquiry(self):
        """AFM supports IDN inquiry."""
        return True

__all__ = ['AFMWidget']
