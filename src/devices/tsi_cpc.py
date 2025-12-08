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

        # Hide main plot dropdown by default (will be shown when PSM connects)
        if hasattr(self, 'main_plot_dropdown') and self.main_plot_dropdown:
            self.main_plot_dropdown.hide()
            if hasattr(self, '_main_plot_label') and self._main_plot_label:
                self._main_plot_label.hide()

    def get_plot_keys(self):
        """TSI CPC has concentration and raw concentration plots like Airmodus CPC."""
        return [':conc', ':raw']

    def get_plot_value_labels(self):
        """Return labels for TSI CPC plot values."""
        return {
            ':conc': 'Dilution Corrected Concentration (#/cc)',
            ':raw': 'Raw Concentration (#/cc)'
        }

    def is_connected_to_psm(self, app_config=None):
        """Check if any PSM has this CPC as its connected CPC."""
        if not app_config:
            return False
        from config import PSM
        dev_id = self.device_config.device_id
        for device_config in app_config.devices:
            if device_config.device_type == PSM:
                connected_cpc = device_config.extra_params.get('connected_cpc', 'None')
                try:
                    if connected_cpc != 'None' and int(connected_cpc) == dev_id:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    def update_main_plot_dropdown_visibility(self, app_config):
        """Show/hide main plot dropdown based on PSM connection."""
        if not hasattr(self, 'main_plot_dropdown') or not self.main_plot_dropdown:
            return

        has_psm = self.is_connected_to_psm(app_config)

        if has_psm:
            self.main_plot_dropdown.show()
            if hasattr(self, '_main_plot_label'):
                self._main_plot_label.show()
            if self.device_config.plot_to_main != ':conc':
                index = self.main_plot_dropdown.findData(':conc')
                if index >= 0:
                    self.main_plot_dropdown.setCurrentIndex(index)
                    self.device_config.plot_to_main = ':conc'
                    if hasattr(self, 'on_config_changed') and self.on_config_changed:
                        self.on_config_changed()
        else:
            self.main_plot_dropdown.hide()
            if hasattr(self, '_main_plot_label'):
                self._main_plot_label.hide()
            if self.device_config.plot_to_main != ':raw':
                self.device_config.plot_to_main = ':raw'
                if hasattr(self, 'on_config_changed') and self.on_config_changed:
                    self.on_config_changed()

    def restore_ui_state(self, device_config, app_config):
        """Restore TSI CPC UI state from configuration."""
        self.update_main_plot_dropdown_visibility(app_config)

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

    @classmethod
    def get_default_extra_params(cls, device_type: int) -> dict:
        """Return default extra_params for TSI CPC devices."""
        return {'10_hz': False}


__all__ = ['TSIWidget']
