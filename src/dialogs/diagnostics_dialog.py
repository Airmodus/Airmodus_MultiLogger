"""
Diagnostics Dialog

Modal dialog that displays device diagnostic information in a human-readable format.
Shows device status, errors, and key measurements with color-coded indicators.
Includes 3D visualization tab for PSM devices when available.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                              QTextBrowser, QLabel, QTabWidget, QWidget)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
import logging

from diagnostics import DiagnosticsExporter
from config import CPC, PSM, TSI_CPC

# Try to import PSM 3D tab
try:
    from devices.psm_3d_tab import PSM3DTab
    HAS_3D_TAB = True
except ImportError:
    HAS_3D_TAB = False
    PSM3DTab = None


class DiagnosticsDialog(QDialog):
    """
    Dialog for viewing device diagnostics in a human-readable format.

    Displays:
    - Application info and session status
    - Error summary across all devices
    - Per-device status, errors, and key measurements
    - 3D visualization for PSM devices (if available)
    """

    def __init__(self, config, data_holder, parent=None):
        super().__init__(parent)
        self.config = config
        self.data_holder = data_holder
        self.main_window = parent

        self.setWindowTitle("Device Diagnostics")
        self.resize(800, 600)
        self.setModal(False)

        # 3D view state
        self._psm_3d_tab = None
        self._update_timer = None

        self._setup_ui()
        self._refresh_content()

        # Start update timer for 3D view if PSM is connected
        if self._psm_3d_tab is not None:
            self._start_3d_updates()

    def _setup_ui(self):
        """Create the dialog UI layout."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Header
        header = QLabel("Device Diagnostics")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        layout.addWidget(header)

        # Check if we have a PSM device for 3D view
        psm_config = self._get_psm_config()

        if psm_config is not None and HAS_3D_TAB:
            # Create tabbed interface
            self.tab_widget = QTabWidget()
            self.tab_widget.setStyleSheet("""
                QTabWidget::pane {
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }
                QTabBar::tab {
                    padding: 8px 16px;
                }
            """)

            # Diagnostics tab
            diagnostics_widget = QWidget()
            diag_layout = QVBoxLayout(diagnostics_widget)
            diag_layout.setContentsMargins(0, 0, 0, 0)

            self.content_browser = QTextBrowser()
            self.content_browser.setOpenExternalLinks(False)
            self.content_browser.setFont(QFont("Segoe UI", 10))
            self.content_browser.setStyleSheet("""
                QTextBrowser {
                    background-color: #fafafa;
                    border: none;
                    padding: 10px;
                }
            """)
            diag_layout.addWidget(self.content_browser)

            self.tab_widget.addTab(diagnostics_widget, "Diagnostics")

            # 3D View tab for PSM
            is_psm2 = psm_config.device_type == PSM and getattr(psm_config, 'is_psm2', False)
            self._psm_3d_tab = PSM3DTab(psm_config, is_psm2)
            self.tab_widget.addTab(self._psm_3d_tab, "PSM 3D View")

            layout.addWidget(self.tab_widget, stretch=1)
        else:
            # Simple layout without tabs
            self.tab_widget = None
            self.content_browser = QTextBrowser()
            self.content_browser.setOpenExternalLinks(False)
            self.content_browser.setFont(QFont("Segoe UI", 10))
            self.content_browser.setStyleSheet("""
                QTextBrowser {
                    background-color: #fafafa;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    padding: 10px;
                }
            """)
            layout.addWidget(self.content_browser, stretch=1)

        # Button row
        button_layout = QHBoxLayout()

        # Refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_content)
        refresh_button.setToolTip("Refresh diagnostic information")
        button_layout.addWidget(refresh_button)

        button_layout.addStretch()

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_button.setDefault(True)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _get_psm_config(self):
        """Find the first PSM device configuration."""
        if not hasattr(self.config, 'devices'):
            return None
        for device_config in self.config.devices:
            if device_config.device_type == PSM:
                return device_config
        return None

    def _get_psm_widget(self):
        """Find the PSM widget from main window."""
        if self.main_window is None:
            return None
        if not hasattr(self.main_window, 'device_widgets'):
            return None
        for widget in self.main_window.device_widgets:
            if hasattr(widget, 'device_config') and widget.device_config.device_type == PSM:
                return widget
        return None

    def _start_3d_updates(self):
        """Start timer for updating 3D visualization."""
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_3d_view)
        self._update_timer.start(1000)  # Update every second

    def _update_3d_view(self):
        """Update the 3D view with current PSM data."""
        if self._psm_3d_tab is None:
            return

        psm_widget = self._get_psm_widget()
        if psm_widget is None:
            return

        # Get current data from PSM widget
        if hasattr(psm_widget, 'current_data') and psm_widget.current_data is not None:
            current_data = psm_widget.current_data
            status_hex = getattr(current_data, 'system_status', '0000')
            note_hex = getattr(current_data, 'note', '0000')
            self._psm_3d_tab.update_visualization(current_data, status_hex, note_hex)

    def _refresh_content(self):
        """Refresh the diagnostic content."""
        try:
            exporter = DiagnosticsExporter(
                self.config,
                self.data_holder,
                self.main_window
            )
            diagnostics = exporter.collect_all()
            html_content = self._build_html(diagnostics)
            self.content_browser.setHtml(html_content)
        except Exception as e:
            logging.error(f"Failed to refresh diagnostics: {e}")
            self.content_browser.setHtml(
                f"<p style='color: red;'>Error loading diagnostics: {str(e)}</p>"
            )

    def closeEvent(self, event):
        """Clean up timer when dialog closes."""
        if self._update_timer is not None:
            self._update_timer.stop()
        super().closeEvent(event)

    def _build_html(self, diagnostics: dict) -> str:
        """
        Build HTML content from diagnostics data.

        Args:
            diagnostics: Dictionary from DiagnosticsExporter.collect_all()

        Returns:
            HTML string for display
        """
        html_parts = []

        # CSS styles
        html_parts.append("""
        <style>
            body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; color: #333; }
            .header-bar { background: #f0f0f0; padding: 8px 12px; border-radius: 4px; margin-bottom: 15px; }
            .section-title { font-size: 12pt; font-weight: bold; color: #333; margin: 15px 0 8px 0;
                            border-bottom: 2px solid #ddd; padding-bottom: 4px; }
            .error-box { background: #fff5f5; border: 1px solid #ffcccc; border-radius: 4px;
                        padding: 10px; margin: 8px 0; }
            .ok-box { background: #f5fff5; border: 1px solid #ccffcc; border-radius: 4px;
                     padding: 10px; margin: 8px 0; }
            .device-box { background: #fff; border: 1px solid #ddd; border-radius: 4px;
                         padding: 12px; margin: 10px 0; }
            .device-header { font-weight: bold; font-size: 11pt; margin-bottom: 8px; color: #333; }
            .connected { color: #27ae60; font-weight: 500; }
            .disconnected { color: #e74c3c; font-weight: 500; }
            .error { color: #e74c3c; }
            .warning { color: #f39c12; }
            .ok { color: #27ae60; }
            .mono { font-family: 'Consolas', 'Courier New', monospace; color: #555; }
            .label { color: #555; }
            .value { color: #222; font-weight: 500; }
            .error-item { margin: 4px 0; padding-left: 15px; }
            .measurement-row { margin: 2px 0; }
            .measurement-label { color: #555; font-weight: normal; }
            .no-devices { color: #666; font-style: italic; padding: 20px; text-align: center; }
        </style>
        """)

        # Application info bar
        app = diagnostics.get('application', {})
        session = diagnostics.get('session', {})
        data_settings = diagnostics.get('data_settings', {})

        session_time = self._format_session_time(session.get('time_counter', 0))
        saving = "Yes" if data_settings.get('save_data', False) else "No"

        html_parts.append(f"""
        <div class="header-bar">
            <span class="label">Application:</span> <span class="value">v{app.get('version', '?')}</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span class="label">Session:</span> <span class="value">{session_time}</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span class="label">Saving:</span> <span class="value">{saving}</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span class="label">Devices:</span> <span class="value">{session.get('active_device_count', 0)}</span>
        </div>
        """)

        # Error Summary Section
        error_summary = diagnostics.get('error_summary', {})
        devices_with_errors = error_summary.get('devices_with_errors', [])

        html_parts.append('<div class="section-title">Error Summary</div>')

        if devices_with_errors:
            html_parts.append('<div class="error-box">')
            html_parts.append(f'<span class="error"><b>&#9888; {len(devices_with_errors)} device(s) with errors:</b></span><br>')
            for dev_error in devices_with_errors:
                nickname = dev_error.get('nickname', 'Unknown')
                serial = dev_error.get('serial_number', '')
                html_parts.append(f'<div class="error-item">&#8226; {nickname} ({serial})</div>')
            html_parts.append('</div>')
        else:
            html_parts.append('<div class="ok-box">')
            html_parts.append('<span class="ok"><b>&#10004; All devices OK - No errors detected</b></span>')
            html_parts.append('</div>')

        # Devices Section
        html_parts.append('<div class="section-title">Devices</div>')

        devices = diagnostics.get('devices', [])
        if not devices:
            html_parts.append('<div class="no-devices">No devices configured</div>')
        else:
            for device in devices:
                html_parts.append(self._build_device_html(device))

        # Communication info
        comm = diagnostics.get('communication_summary', {})
        available_ports = comm.get('available_ports', [])
        if available_ports:
            html_parts.append('<div class="section-title">Available COM Ports</div>')
            html_parts.append(f'<p class="mono">{", ".join(available_ports)}</p>')

        return ''.join(html_parts)

    def _build_device_html(self, device: dict) -> str:
        """
        Build HTML for a single device.

        Args:
            device: Device dictionary from diagnostics

        Returns:
            HTML string for the device section
        """
        html_parts = []

        # Device header
        name = device.get('device_type_name', 'Unknown')
        nickname = device.get('nickname', '')
        serial = device.get('serial_number', '')
        is_connected = device.get('is_connected', False)
        com_port = device.get('com_port', '')
        firmware = device.get('firmware_version', '')

        # Connection status indicator
        if is_connected:
            status_indicator = '<span class="connected">&#9679; Connected</span>'
        else:
            status_indicator = '<span class="disconnected">&#9679; Disconnected</span>'

        html_parts.append('<div class="device-box">')

        # Header line
        display_name = f'{name} "{nickname}"' if nickname else name
        html_parts.append(f'''
        <div class="device-header">
            {display_name} <span class="mono">({serial})</span>
            &nbsp;&nbsp;{status_indicator}
        </div>
        ''')

        # Port and firmware
        info_parts = []
        if com_port:
            info_parts.append(f'<span class="label">Port:</span> <span class="mono">{com_port}</span>')
        if firmware:
            info_parts.append(f'<span class="label">Firmware:</span> <span class="mono">{firmware}</span>')
        if info_parts:
            html_parts.append(f'<div style="margin-bottom: 8px;">{" &nbsp;|&nbsp; ".join(info_parts)}</div>')

        # Status section
        status = device.get('current_status', {})
        if status:
            html_parts.append(self._build_status_html(device, status))

        # Key measurements
        measurements = device.get('current_measurements', {})
        if measurements and is_connected:
            html_parts.append(self._build_measurements_html(device, measurements))

        html_parts.append('</div>')

        return ''.join(html_parts)

    def _build_status_html(self, device: dict, status: dict) -> str:
        """Build HTML for device status section."""
        html_parts = []
        device_type = device.get('device_type')

        # Get status hex
        status_hex = status.get('status_hex', '') or status.get('error_hex', '')
        total_errors = status.get('total_errors', 0)
        decoded_errors = status.get('decoded_errors', [])

        if device_type in (CPC, PSM):
            if total_errors > 0:
                html_parts.append(f'''
                <div style="margin: 8px 0;">
                    <span class="label">Status:</span>
                    <span class="mono error">0x{status_hex}</span>
                    <span class="error">({total_errors} error{"s" if total_errors != 1 else ""})</span>
                </div>
                ''')
                # Show decoded errors
                for error in decoded_errors:
                    html_parts.append(f'<div class="error-item error">&#10060; {error}</div>')
            else:
                html_parts.append(f'''
                <div style="margin: 8px 0;">
                    <span class="label">Status:</span>
                    <span class="mono">0x{status_hex if status_hex else "0000"}</span>
                    <span class="ok">(OK)</span>
                </div>
                ''')

        # PSM notes (liquid level warnings)
        if device_type == PSM:
            note_hex = status.get('note_hex', '')
            liquid_errors = status.get('liquid_errors', 0)
            decoded_notes = status.get('decoded_notes', [])

            if liquid_errors > 0 and decoded_notes:
                html_parts.append('<div style="margin-top: 6px;">')
                for note in decoded_notes:
                    html_parts.append(f'<div class="error-item warning">&#9888; {note}</div>')
                html_parts.append('</div>')

        # TSI CPC error
        if device_type == TSI_CPC:
            error_hex = status.get('error_hex', '')
            if error_hex and error_hex != '0' and error_hex != '00':
                html_parts.append(f'''
                <div style="margin: 8px 0;">
                    <span class="label">Error Code:</span>
                    <span class="mono error">0x{error_hex}</span>
                </div>
                ''')

        return ''.join(html_parts)

    def _build_measurements_html(self, device: dict, measurements: dict) -> str:
        """Build HTML for key measurements section."""
        html_parts = []
        device_type = device.get('device_type')

        # Select key measurements based on device type
        key_fields = self._get_key_measurement_fields(device_type)

        displayed = []
        for field_name, display_name, unit in key_fields:
            value = measurements.get(field_name)
            if value is not None:
                if isinstance(value, float):
                    formatted = f"{value:.2f}" if abs(value) < 10000 else f"{value:.1f}"
                else:
                    formatted = str(value)
                displayed.append(f'<span class="label">{display_name}:</span> <span class="value">{formatted}{unit}</span>')

        if displayed:
            html_parts.append('<div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #eee;">')
            html_parts.append('<div style="font-weight: 500; margin-bottom: 4px;">Measurements:</div>')
            # Display in a grid-like format (2 columns)
            for i in range(0, len(displayed), 2):
                row = displayed[i:i+2]
                html_parts.append(f'<div class="measurement-row">{" &nbsp;&nbsp;&nbsp; ".join(row)}</div>')
            html_parts.append('</div>')

        return ''.join(html_parts)

    def _get_key_measurement_fields(self, device_type: int) -> list:
        """
        Get list of key measurement fields for device type.

        Returns:
            List of (field_name, display_name, unit) tuples
        """
        if device_type == CPC:
            return [
                ('concentration', 'Concentration', ' #/cm³'),
                ('temp_saturator', 'T Saturator', '°C'),
                ('temp_condenser', 'T Condenser', '°C'),
                ('temp_optics', 'T Optics', '°C'),
                ('pres_inlet', 'P Inlet', ' kPa'),
                ('liquid_level', 'Liquid', ''),
            ]
        elif device_type == PSM:
            return [
                ('concentration_psm', 'Concentration', ' #/cm³'),
                ('saturator_flow', 'Sat Flow', ' L/min'),
                ('temp_growth_tube', 'T Growth Tube', '°C'),
                ('temp_saturator', 'T Saturator', '°C'),
                ('pres_inlet', 'P Inlet', ' kPa'),
            ]
        elif device_type == TSI_CPC:
            return [
                ('concentration', 'Concentration', ' #/cm³'),
            ]
        else:
            # Generic - show first few numeric fields
            return []

    def _format_session_time(self, seconds: int) -> str:
        """Format session time in human-readable format."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            mins = seconds // 60
            return f"{mins}m"
        else:
            hours = seconds // 3600
            mins = (seconds % 3600) // 60
            return f"{hours}h {mins}m"
