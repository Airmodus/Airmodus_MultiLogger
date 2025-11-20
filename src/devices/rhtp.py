from plots.device_plots import TriplePlot
from config import RHTP
from devices.base_device import SimpleDevice
from devices.device_data import RHTPData
from plotting.device_plot_configs import RHTPPlotConfig
from devices.data_writers import RHTPDataWriter

# RHTP widget
class RHTPWidget(SimpleDevice):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__(device_parameter, device_type=RHTP, *args, **kwargs)
        # create plot widget for RHTP
        self.plot_tab = TriplePlot(device_type=RHTP)
        self.addTab(self.plot_tab, "RHTP plot")

        # Plot configuration (composition over inheritance)
        self.plot_config = RHTPPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = RHTPDataWriter(self)

    def get_plot_keys(self):
        """RHTP has relative humidity, temperature, and pressure."""
        return [':rh', ':t', ':p']

    def get_read_command(self):
        """RHTP auto-pushes data, no read command needed."""
        return None

    def get_status_bar_text(self):
        """Get formatted text for status bar display."""
        if self.current_data and hasattr(self.current_data, 'temperature'):
            temp = self.current_data.temperature
            if temp is not None:
                return f"T: {temp:.1f}°C"
        return super().get_status_bar_text()

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
                # Update data object
                self.current_data.humidity = float(readings[0])
                self.current_data.temperature = float(readings[1])
                self.current_data.pressure = float(readings[2])

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

    def supports_idn_inquiry(self):
        """RHTP supports IDN inquiry."""
        return True

__all__ = ['RHTPWidget']
