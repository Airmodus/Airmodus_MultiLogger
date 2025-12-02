from datetime import datetime as dt
from time import time
import os
import traceback
import json
import logging

from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QSize
from PyQt5.QtWidgets import (QMainWindow, QSplitter, QApplication, QTabWidget, QLabel,
    QFileDialog, QPushButton, QWidget, QHBoxLayout, QVBoxLayout, QTabBar, QStackedWidget, QStyle, QLayout, QSizePolicy)
from PyQt5.QtGui import QCursor
from widgets import TabConfirmationPopup, BrowserStyleTabBar

from config import *
from utils import (
    psm_update,
    psm_flow_send,
    cpc_flow_send,
    ten_hz_clicked,
    command_entered
)
from plots import (
    MainPlot,
)

from devices import (
    CPCWidget,
    PSMWidget,
    CO2Widget,
    ElectrometerWidget,
    RHTPWidget,
    eDiluterWidget,
    AFMWidget,
    TSIWidget,
    ExampleDeviceWidget
)

from managers import (
    DataHolder,
    TimerService,
    DeviceManager,
    PlotManager,
    DataLogger
)

from serial_connection import SerialDeviceConnection
from devices.device_data import AppConfig, DataSettings, PlotSettings, DeviceConfig
from config_migration import params_dict_to_app_config


# main program
class MainWindow(QMainWindow):
    # Qt signals for configuration changes
    data_settings_changed = pyqtSignal(DataSettings)
    plot_settings_changed = pyqtSignal(PlotSettings)
    device_config_changed = pyqtSignal(int, DeviceConfig)  # device_id, config

    def __init__(self, parent=None):
        super().__init__() # super init function must be called when subclassing a Qt class
        self.setWindowTitle("Airmodus MultiLogger v. " + version_number) # set window title

        # New typed configuration (replaces params)
        self.config = AppConfig()
        self.config_file_path = "" # path to the configuration file

        # Device ID counter (replaces ScalableGroup.n_devices)
        self._next_device_id = 0

        # CPC/RHTP dictionaries for inter-device linking
        self.cpc_dict = {'None': 'None'}
        self.rhtp_dict = {'None': 'None'}

        # Track active confirmation popup to prevent stacking
        self._active_popup = None

        # Extracted inits
        self.data_holder = DataHolder()
        self.data_holder.error_icon = QIcon(resource_path + "/icons/error.png")
        self.data_holder.disconnected_icon = QIcon(resource_path + "/icons/disconnected.png")

        self._setup_gui()

        # Add any existing devices from config AFTER GUI setup
        for device_config in self.config.devices:
            self._add_device_from_config(device_config)

        self.device_manager = DeviceManager(self.config, self.data_holder, self.data_holder.device_widgets)

        # Update device_manager with device_tabs and device_tab_bar references after GUI setup
        self.device_manager.device_tabs = self.device_tabs
        self.device_manager.device_tab_bar = self.device_tab_bar

        # Start initial port scan to populate dropdowns
        QTimer.singleShot(100, self.device_manager.list_com_ports)

        # Start continuous port monitoring for automatic device detection
        QTimer.singleShot(500, self.device_manager.start_port_monitoring)

        self.plot_manager = PlotManager(self, self.data_holder, self.main_plot)
        self.data_logger = DataLogger(self.data_holder, self.config)

        # Initialize database manager
        from managers.database_manager import DatabaseManager
        self.database_manager = DatabaseManager()

        self._connect_signals()

        self.timer_service = TimerService(self, self.data_holder, self.device_manager, self.plot_manager, self.data_logger)
        self.timer_service.start()

        # load ini file if available (with auto-migration)
        self.load_ini()

        # Update PSM connected CPC references after all devices are loaded
        self._update_psm_cpc_connections()

        # Set initial window size
        self.resize(1500, 1040)

        # Set minimum width to prevent window from becoming too narrow
        self.setMinimumWidth(1000)

    def _setup_gui(self):
        """Build main layout, splitters, tabs, etc."""
        # Load CSS style and apply it to the main window
        with open(script_path + "/style.css", "r") as f:
            self.style = f.read()
        self.setStyleSheet(self.style)

        # create main container widget to hold all UI elements
        main_container = QWidget()
        container_layout = QVBoxLayout(main_container)
        # Prevent layout from resizing window when widgets change size
        container_layout.setSizeConstraint(QLayout.SetNoConstraint)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # create horizontal top bar: [Logo] [Plus] [Tab Bar] [Gear]
        top_bar_widget = QWidget()
        top_bar_widget.setFixedHeight(70)  # Fix height to prevent stretching
        # Set size policy to prevent horizontal expansion from tab bar
        top_bar_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        top_bar_layout = QHBoxLayout(top_bar_widget)
        # Prevent layout from adjusting window size when content changes
        top_bar_layout.setSizeConstraint(QLayout.SetNoConstraint)
        top_bar_layout.setContentsMargins(0, 5, 5, 5)  # Left=0, minimal margins elsewhere
        top_bar_layout.setSpacing(4)  # Reduce spacing between elements

        # create logo pixmap label (smaller for horizontal layout)
        self.logo = QLabel(alignment=Qt.AlignCenter, objectName="logo")
        pixmap = QPixmap(resource_path + "/images/airmodus-envea-logo.png")
        self.logo.setPixmap(pixmap.scaled(220, 55, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.logo.setFixedSize(220, 55)
        top_bar_layout.addWidget(self.logo, stretch=0)

        # Create container for tab bar
        tab_bar_container = QWidget()
        tab_bar_container_layout = QHBoxLayout(tab_bar_container)
        tab_bar_container_layout.setContentsMargins(0, 0, 0, 0)
        tab_bar_container_layout.setSpacing(0)

        # create tab bar (ONLY the tabs, not the content)
        self.device_tab_bar = BrowserStyleTabBar()
        self.device_tab_bar.setStyleSheet("""
            QTabBar::tab {
                min-width: 150px;
                max-width: 200px;
                height: 53px;
                padding: 8px 14px;
                background-color: #3a3a3a;
                color: #cccccc;
                border: none;
                margin-right: 2px;
                font-size: 14px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #2a2a2a;
                color: #ffffff;
            }
            QTabBar::tab:hover {
                background-color: #4a4a4a;
            }

            /* Hide native scroll buttons (we use custom overlays) */
            QTabBar::scroller {
                width: 0px;
            }
            QTabBar QToolButton {
                width: 0px;
                height: 0px;
            }
        """)
        self.device_tab_bar.currentChanged.connect(self._on_tab_changed)

        tab_bar_container_layout.addWidget(self.device_tab_bar, stretch=1)

        top_bar_layout.addWidget(tab_bar_container, stretch=1)

        # create add device button (in top bar after tabs, before gear)
        self.add_device_button = QPushButton("+")
        self.add_device_button.setToolTip("Add New Device")
        self.add_device_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.add_device_button.setFixedSize(48, 48)
        self.add_device_button.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                font-size: 48px;
                color: #555555;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                color: #4CAF50;
            }
            QPushButton:pressed {
                color: #388E3C;
            }
        """)
        self.add_device_button.clicked.connect(self._add_new_device)
        top_bar_layout.addWidget(self.add_device_button, stretch=0)

        # create settings gear button (in top bar at end)
        self.settings_button = QPushButton("⚙")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.settings_button.setFixedSize(48, 48)  # Clean, compact size
        self.settings_button.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                font-size: 48px;
                color: #555555;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                color: #2196F3;
            }
            QPushButton:pressed {
                color: #1976D2;
            }
        """)
        self.settings_button.clicked.connect(self._open_settings_dialog)
        top_bar_layout.addWidget(self.settings_button, stretch=0)

        # Add top bar to main container
        container_layout.addWidget(top_bar_widget)

        # create stacked widget for content area (below top bar)
        self.device_tabs = QStackedWidget()
        container_layout.addWidget(self.device_tabs, stretch=1)  # Takes remaining vertical space

        # Add main plot as first tab/page
        self.main_plot = MainPlot()
        self.device_tabs.addWidget(self.main_plot)
        self.device_tab_bar.addTab("Main plot")
        # Note: Main plot tab has no close button (we only add close buttons to device tabs)

        # Set central widget
        self.setCentralWidget(main_container)

        # Create and add status bar for always-visible field monitoring
        from status_bar import MultiLoggerStatusBar
        self.status_bar = MultiLoggerStatusBar(self.data_holder, self.config, self)
        self.status_bar.main_window = self  # Set reference for tab switching
        self.setStatusBar(self.status_bar)

    def _on_tab_changed(self, index):
        """Handle tab bar selection changes - switch the stacked widget page."""
        self.device_tabs.setCurrentIndex(index)
        self._update_close_button_visibility()

        # Restore device's last viewed internal tab (default to Plot tab index 0)
        device_widget = self.device_tabs.widget(index)
        if device_widget and hasattr(device_widget, 'device_config'):
            saved = device_widget.device_config.extra_params.get('last_tab_index', 0)
            if 0 <= saved < device_widget.count():
                device_widget.setCurrentIndex(saved)

    def _create_error_indicator_icon(self, color="#F57C00"):
        """Create a small colored dot icon for tab error indicators.

        Args:
            color: Hex color for the dot (default orange for errors)

        Returns:
            QIcon with a colored dot
        """
        # Create a 16x16 pixmap with transparency
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)

        # Draw a filled circle
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 12, 12)  # 12x12 dot with 2px margin
        painter.end()

        return QIcon(pixmap)

    def update_tab_error_indicator(self, dev_id, has_error, is_connected=True):
        """Update the error indicator icon on a device's tab.

        Args:
            dev_id: Device ID to update
            has_error: True if device has an error, False otherwise
            is_connected: True if device is connected, False if disconnected
        """
        # Find the tab index for this device
        for i in range(self.device_tabs.count()):
            widget = self.device_tabs.widget(i)
            if hasattr(widget, 'dev_id') and widget.dev_id == dev_id:
                # Skip Main plot tab (index 0)
                if i == 0:
                    return

                # Set or clear error indicator icon
                if not is_connected:
                    # Red dot for disconnected
                    error_icon = self._create_error_indicator_icon("#D32F2F")
                    self.device_tab_bar.setTabIcon(i, error_icon)
                elif has_error:
                    # Orange dot for errors
                    error_icon = self._create_error_indicator_icon("#F57C00")
                    self.device_tab_bar.setTabIcon(i, error_icon)
                else:
                    # Clear icon - device is OK
                    self.device_tab_bar.setTabIcon(i, QIcon())
                return

    def _add_close_button_to_tab(self, tab_index):
        """
        Add a custom close button to the specified tab on the right side.

        Args:
            tab_index: Index of the tab to add close button to
        """
        close_button = QPushButton("×")
        close_button.setFixedSize(39, 39)
        close_button.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #999;
                font-size: 39px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
                margin-top: -5px;
                margin-right: 8px;
                border-radius: 0px;
            }
            QPushButton:hover {
                color: #fff;
                background-color: rgba(255, 255, 255, 0.1);
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
        """)
        close_button.setToolTip("Remove device")
        close_button.setCursor(QCursor(Qt.PointingHandCursor))

        # Connect to show confirmation popup - find current index dynamically
        # (indices shift when tabs are removed, so we can't capture index at creation time)
        close_button.clicked.connect(lambda checked=False, btn=close_button: self._show_close_confirmation_for_button(btn))

        # Add button to right side of tab
        self.device_tab_bar.setTabButton(tab_index, QTabBar.RightSide, close_button)

    def _show_close_confirmation_for_button(self, button):
        """
        Find the tab index for the given close button and show confirmation.

        Args:
            button: The close button that was clicked
        """
        for i in range(self.device_tab_bar.count()):
            if self.device_tab_bar.tabButton(i, QTabBar.RightSide) == button:
                self._show_close_confirmation(i)
                return

    def _show_close_confirmation(self, index):
        """
        Show inline confirmation popup below the tab.

        Args:
            index: Tab index to close
        """
        # Don't allow closing the Main plot tab
        if index == 0:
            return

        # Close any existing popup before showing a new one
        if self._active_popup is not None:
            try:
                self._active_popup.close()
            except RuntimeError:
                pass  # Popup was already deleted
            self._active_popup = None

        # Get device name for confirmation message
        device_name = self.device_tab_bar.tabText(index)

        # Create and show confirmation popup
        popup = TabConfirmationPopup(device_name, self)
        popup.confirmed.connect(lambda: self._remove_device_at_index(index))
        popup.show_below_tab(self.device_tab_bar, index)

        # Track this popup so we can close it if another is opened
        self._active_popup = popup

    def _remove_device_at_index(self, index):
        """
        Remove the device at the specified tab index.

        This is called after the user confirms removal in the popup.

        Args:
            index: Tab index to remove
        """
        # Don't allow closing the Main plot tab
        if index == 0:
            return

        # Find the device widget at this tab index
        widget = self.device_tabs.widget(index)
        if not widget:
            return

        # Find the device ID from the widget
        dev_id = None
        for device_id, dev_widget in self.data_holder.device_widgets.items():
            if dev_widget == widget:
                dev_id = device_id
                break

        if dev_id is None:
            return

        # Find device config
        device_config = next((d for d in self.config.devices if d.device_id == dev_id), None)
        if not device_config:
            return

        # Remove from status bar
        if hasattr(self, 'status_bar'):
            self.status_bar.remove_device_status(dev_id)

        # If it's a CPC with database enabled, unregister from database manager
        if device_config.device_type == CPC and hasattr(self, 'database_manager'):
            db_enabled = device_config.extra_params.get('database_enabled', False)
            if db_enabled:
                self.database_manager.unregister_device(dev_id)

                # Update global status in all remaining CPC tabs
                for dev_id_other, widget_other in self.data_holder.device_widgets.items():
                    if dev_id_other != dev_id and hasattr(widget_other, 'device_type') and widget_other.device_type == CPC:
                        if hasattr(widget_other, 'database_tab'):
                            widget_other.database_tab.update_global_connection_status()
                            widget_other.database_tab.sync_global_status_to_all_cpcs()

        # Close serial connection if open
        if hasattr(widget, 'connection'):
            try:
                widget.connection.close()
            except AttributeError:
                pass

        # Remove curve from main plot
        try:
            self.data_holder.curve_dict[dev_id].setData(x=[], y=[])
        except KeyError:
            pass

        # Remove from GUI
        widget_index = self.device_tabs.indexOf(widget)
        if widget_index >= 0:
            self.device_tabs.removeWidget(widget)
            self.device_tab_bar.removeTab(widget_index)

        # Clear data holder
        self.data_holder.clear_for_device(dev_id)

        # Remove from device_widgets dict
        if dev_id in self.data_holder.device_widgets:
            del self.data_holder.device_widgets[dev_id]

        # Remove from config
        self.config.devices = [d for d in self.config.devices if d.device_id != dev_id]

        # Update CPC/RHTP dicts
        self._update_cpc_dict()
        self._update_rhtp_dict()

        # Refresh PSM Connected CPC dropdowns
        self._refresh_psm_cpc_dropdowns()

        # Save configuration
        self.save_ini()

    def _update_close_button_visibility(self):
        """Show close button only on selected tab (except Main plot)."""
        current_index = self.device_tab_bar.currentIndex()

        for i in range(self.device_tab_bar.count()):
            # Get close button from right side (our custom buttons)
            close_button = self.device_tab_bar.tabButton(i, QTabBar.RightSide)

            if close_button is None:
                # No close button exists for this tab (Main plot)
                continue

            if i == 0:
                # Main plot tab - always hide close button
                close_button.hide()
            elif i == current_index:
                # Currently selected tab - show close button
                close_button.show()
            else:
                # Non-selected tabs - hide close button
                close_button.hide()

    def _open_settings_dialog(self):
        """Open the data settings dialog."""
        from dialogs.data_settings_dialog import DataSettingsDialog
        dialog = DataSettingsDialog(self.config, self.data_holder, self)
        dialog.exec_()

    def _add_new_device(self):
        """Open dialog to add a new device."""
        from dialogs import PortSelectionDialog
        from devices.device_data import create_device_settings
        from config_migration import _get_device_type_name

        # Show port selection dialog
        dialog = PortSelectionDialog(self.device_manager, self.data_holder)
        if dialog.exec_() != dialog.Accepted:
            return  # User cancelled

        selected_port = dialog.get_selected_port()
        device_type_name = dialog.get_selected_type()
        serial_number = dialog.get_selected_serial_number()

        if not selected_port or not device_type_name:
            return  # Invalid selection

        # Generate nickname with device type + unique short ID if serial number is available
        device_nickname = ""
        if serial_number:
            from utils import compute_unique_short_ids

            # Build dict of all existing device serial numbers + new one
            serial_numbers = {-1: serial_number}  # -1 as temp key for new device
            for dev_cfg in self.config.devices:
                if dev_cfg.serial_number:
                    serial_numbers[dev_cfg.device_id] = dev_cfg.serial_number

            unique_ids = compute_unique_short_ids(serial_numbers)
            short_id = unique_ids.get(-1, "")
            if short_id:
                device_nickname = f"{device_type_name} {short_id}"

        # Convert device type name to device ID
        name_to_id = {name: dev_id for dev_id, name in self.data_holder.device_names.items()}
        device_type = name_to_id.get(device_type_name)

        if device_type is None:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Unknown Device Type",
                f"Cannot create device of type '{device_type_name}'.\n\n"
                f"This device type is not supported."
            )
            return

        # Create device configuration
        device_config = DeviceConfig(
            device_id=self._next_device_id,
            device_type=device_type,
            device_type_name=device_type_name,
            com_port=selected_port,
            serial_number=serial_number,
            device_nickname=device_nickname,
            plot_to_main=True,
            settings=create_device_settings(device_type),
            extra_params={}
        )

        # Add device-specific parameters
        if device_type in [CPC, TSI_CPC]:
            device_config.extra_params['10_hz'] = False
            if device_type == CPC:
                device_config.extra_params['database_enabled'] = False
                device_config.extra_params['linked_rhtp'] = 'None'
                device_config.extra_params['db_averaging_interval'] = '1 minute'

        if device_type in [PSM, PSM2]:
            device_config.extra_params['10_hz'] = False
            device_config.extra_params['connected_cpc'] = 'None'
            device_config.extra_params['calibration_file_path'] = ''
            device_config.extra_params['firmware_version'] = ''
            if device_type == PSM:
                device_config.extra_params['co_flow'] = ''

        # Increment device ID counter
        self._next_device_id += 1

        # Add to configuration
        self.config.devices.append(device_config)

        # Create and add the actual device widget
        self._add_device_from_config(device_config)

        # Select the newly added tab
        new_tab_index = self.device_tab_bar.count() - 1
        self.device_tab_bar.setCurrentIndex(new_tab_index)

        # Update CPC/RHTP dictionaries
        self._update_cpc_dict()
        self._update_rhtp_dict()

        # Don't refresh PSM CPC dropdowns immediately - they'll update lazily when PSM tabs are shown
        # This prevents blocking the main thread during device addition
        # Mark all PSMs as needing dropdown updates
        for device_config in self.config.devices:
            if device_config.device_type in [PSM, PSM2]:
                psm_widget = self.data_holder.device_widgets.get(device_config.device_id)
                if psm_widget and hasattr(psm_widget, '_needs_cpc_dropdown_update'):
                    psm_widget._needs_cpc_dropdown_update = True

        # Save configuration
        self.save_ini()

    def _connect_signals(self):
        """Wire up all signals/slots."""

        # Connect config change signals to managers and save
        # Note: Individual setting changes will emit these signals from dialogs/widgets
        self.data_settings_changed.connect(self.data_logger.on_data_settings_changed)
        self.data_settings_changed.connect(lambda: self.save_ini())
        self.plot_settings_changed.connect(lambda: self.save_ini())
        self.device_config_changed.connect(lambda: self.save_ini())

        # connect main_plot's viewboxes' sigXRangeChanged signals to x_range_changed function
        for viewbox in self.main_plot.viewboxes.values():
            viewbox.sigXRangeChanged.connect(self.x_range_changed)
        # connect main_plot's auto range button click to auto_range_clicked function
        self.main_plot.plot.autoBtn.clicked.connect(self.auto_range_clicked)

        # connect DeviceManager port scanning signals for progressive UI updates
        self.device_manager.port_scan_started.connect(self._on_port_scan_started)
        self.device_manager.port_scan_complete.connect(self._on_port_scan_complete)
        self.device_manager.port_scan_progress.connect(self._on_port_scan_progress)

    # set COM port inquiry flag
    def set_inquiry_flag(self):
        # Check if a scan is already in progress to prevent double-clicking
        if hasattr(self.device_manager, '_scanning') and self.device_manager._scanning:
            import logging
            logging.info("Port scan already in progress, ignoring button click")
            return

        self.data_holder.inquiry_flag = True
        self.data_holder.inquiry_time = time()
        self.data_holder.com_descriptions = {} # reset com descriptions
        # Trigger the new threaded port scanning
        self.device_manager.list_com_ports()

    def _on_port_scan_started(self):
        """Handle port scan start."""
        import logging
        logging.info("Port scan started")

    def _on_port_scan_complete(self):
        """Handle port scan completion."""
        import logging
        logging.info("Port scan completed")

    def _on_port_scan_progress(self, current: int, total: int):
        """Handle port scan progress updates."""
        import logging
        logging.debug(f"Port scan progress: {current}/{total}")
    

    def save_ini(self):
        """Save configuration to resume_config.json."""
        # check if resume on startup is on
        resume_measurements = 1 if self.config.data_settings.resume_on_startup else 0

        # store resume config path
        self.config_file_path = os.path.join(save_path, 'resume_config.json')

        # Write config.ini with path and resume flag
        with open(os.path.join(save_path, 'config.ini'),'w') as f:
            f.write(self.config_file_path)
            f.write(';')
            f.write(str(resume_measurements))

        # Save the configuration using AppConfig
        self.save_configuration(self.config_file_path)
    
    def load_ini(self):
        """Load configuration with automatic migration from old format."""
        try:
            # load the configuration file "config.ini" from the save_path
            with open(os.path.join(save_path, 'config.ini'),'r') as f:
                config = f.read()
                json_path = config.split(';')[0]
                resume_measurements = config.split(';')[1]
                # If json path is empty
                if not json_path:
                    json_path = os.path.join(save_path, 'resume_config.json')
                self.config_file_path = json_path
                resume_measurements = int(resume_measurements)
                # if resume on startup is on, load the stored configuration
                if resume_measurements:
                    self.load_configuration(json_path)
        except FileNotFoundError:
            # First run - no config file exists yet, this is normal
            logging.info("No config.ini found (first run). Configuration will be saved on exit.")
        except Exception as e:
            # Unexpected error - print full traceback
            logging.error(f"Error loading config.ini: {e}")
            logging.error(traceback.format_exc())
        
    def save_configuration(self, json_path):
        """Save AppConfig to JSON file."""
        # Build configuration dict
        config_dict = self.config.to_dict()

        # Add database connection string
        if hasattr(self, 'database_manager') and hasattr(self.database_manager, 'connection_string_cached'):
            config_dict['database_connection_string'] = self.database_manager.connection_string_cached

        # Save to JSON file
        with open(json_path, 'w') as file:
            json.dump(config_dict, file, indent=2)

    def load_configuration(self, json_path=None):
        """Load configuration with automatic migration from old parameter tree format."""
        if not json_path:
            return

        # Load the configuration from the JSON file
        with open(json_path, 'r') as file:
            data = json.load(file)

        # Detect format: old (parameter tree) vs new (AppConfig)
        is_old_format = 'Data settings' in data or 'Device settings' in data

        if is_old_format:
            logging.info(f"Detected old configuration format in {json_path}, auto-migrating...")
            # Migrate old format to new AppConfig
            self.config = params_dict_to_app_config(data)
            logging.info("Migration complete. Configuration will be saved in new format.")
        else:
            # Load new format directly
            self.config = AppConfig.from_dict(data)

        # Update config references in all managers since we replaced self.config
        if hasattr(self, 'device_manager'):
            self.device_manager.config = self.config
        if hasattr(self, 'data_logger'):
            self.data_logger.config = self.config
            self.data_logger._last_file_path = self.config.data_settings.file_path
        if hasattr(self, 'plot_manager'):
            self.plot_manager.config = self.config
        if hasattr(self, 'status_bar'):
            self.status_bar.config = self.config

        # Load database connection string
        if 'database_connection_string' in data:
            conn_string = data['database_connection_string']
            if hasattr(self, 'database_manager'):
                self.database_manager.connection_string_cached = conn_string

        # Clear existing devices and load from config
        self._load_devices_from_config()

        # Update device ID counter to avoid collisions
        if self.config.devices:
            self._next_device_id = max(d.device_id for d in self.config.devices) + 1

        # Restore database connections for CPCs
        self._restore_database_connections(data.get('database_connection_string'))

    def _load_devices_from_config(self):
        """Load all devices from self.config and create widgets."""
        for device_config in self.config.devices:
            self._add_device_from_config(device_config)

    def _add_device_from_config(self, device_config: DeviceConfig):
        """Create and add a device widget from a DeviceConfig."""
        from devices.registry import create_device_widget, setup_device_connections

        # Create serial connection (runtime state, stored in widget)
        connection = SerialDeviceConnection()
        if device_config.com_port:
            # Don't connect immediately - just set the port
            # The device_manager.connection_test() will handle actual connection
            # This prevents blocking the main thread during device creation
            connection.set_port(device_config.com_port)

        # Create widget using device registry
        try:
            widget = create_device_widget(device_config.device_type, device_config)
        except ValueError as e:
            logging.error(f"Error creating device widget: {e}")
            return

        # Set device ID and store connection in widget
        widget.dev_id = device_config.device_id
        widget.connection = connection

        # Connect config change callback for nickname and other settings
        def on_device_config_changed():
            """Handle device config changes (nickname, main plot value, etc.)."""
            # Save configuration
            self.save_configuration(self.config_file_path)

            # Update tab name
            self.rename_tab(device_config.device_id)

            # Update device settings display (nickname field, etc.)
            if hasattr(widget, '_update_device_settings_display'):
                widget._update_device_settings_display()

            # Update status bar device name if status bar exists
            if hasattr(self, 'status_bar') and device_config.device_id in self.status_bar.device_widgets:
                status_widget = self.status_bar.device_widgets[device_config.device_id]
                # Update device name from nickname or serial number
                if device_config.device_nickname:
                    status_widget.device_name = device_config.device_nickname
                elif device_config.serial_number:
                    status_widget.device_name = f"{device_config.device_type_name} {device_config.serial_number}"
                else:
                    status_widget.device_name = device_config.device_type_name
                # Refresh the status display
                self.status_bar.update_device_status(device_config.device_id)

        widget.on_config_changed = on_device_config_changed

        # Set up device-specific connections using device registry
        setup_device_connections(device_config.device_type, widget, device_config, connection, self)

        # Restore device-specific UI states from extra_params
        if device_config.device_type in [PSM, PSM2]:
            # Set app config for contour tab historical data loading
            if hasattr(widget, 'set_app_config'):
                widget.set_app_config(self.config)

            # Restore 10 Hz button state
            if '10_hz' in device_config.extra_params:
                widget.measure_tab.ten_hz.change_color(int(device_config.extra_params['10_hz']))

            # Restore CO flow (PSM Retrofit only)
            if device_config.device_type == PSM and 'co_flow' in device_config.extra_params:
                try:
                    co_flow_val = float(device_config.extra_params['co_flow'])
                    widget.set_tab.set_co_flow.value_spinbox.setValue(round(co_flow_val, 3))
                except (ValueError, AttributeError):
                    pass

        # Restore last viewed tab and connect signal to save tab changes
        saved_tab = device_config.extra_params.get('last_tab_index', 0)
        if 0 <= saved_tab < widget.count():
            widget.setCurrentIndex(saved_tab)
        widget.currentChanged.connect(
            lambda idx, dc=device_config: dc.extra_params.__setitem__('last_tab_index', idx)
        )

        if device_config.device_type == CPC:
            # Set app config for database tab RHTP dropdown
            if hasattr(widget, 'set_app_config'):
                widget.set_app_config(self.config)

        # Connect viewbox x-range change for autoscale
        if device_config.device_type == ELECTROMETER:
            for plot in widget.plot_tab.plots:
                plot.getViewBox().sigXRangeChanged.connect(self.x_range_changed)
        elif device_config.device_type in [RHTP, AFM]:
            for viewbox in widget.plot_tab.viewboxes:
                viewbox.sigXRangeChanged.connect(self.x_range_changed)
        else:
            widget.plot_tab.viewbox.sigXRangeChanged.connect(self.x_range_changed)

        # Register widget and initialize data structures
        self.data_holder.device_widgets[device_config.device_id] = widget
        self.data_holder.reset_for_device(device_config.device_id, widget)
        self.data_holder.init_plot_data_for_device(device_config.device_id, widget)

        # Add widget to GUI
        self.device_tabs.addWidget(widget)
        # Tab name: prefer nickname, fallback to "Type Serial", or just "Type"
        if device_config.device_nickname:
            tab_name = device_config.device_nickname
        elif device_config.serial_number:
            tab_name = f"{device_config.device_type_name} {device_config.serial_number}"
        else:
            tab_name = device_config.device_type_name
        tab_index = self.device_tab_bar.addTab(tab_name)
        self._add_close_button_to_tab(tab_index)
        self._update_close_button_visibility()

        # Initialize error tracking
        self.data_holder.device_errors[device_config.device_id] = False

        # Add device to status bar
        if hasattr(self, 'status_bar'):
            self.status_bar.add_device_status(device_config.device_id, tab_name)

        # Set main_window reference for CPC database tab
        if device_config.device_type == CPC and hasattr(widget, 'database_tab'):
            widget.database_tab.main_window = self
            if hasattr(self.database_manager, 'connection_string_cached'):
                widget.database_tab.connection_string_input.setText(self.database_manager.connection_string_cached)
            widget.database_tab.update_global_connection_status()

    def _restore_database_connections(self, conn_string):
        """Restore database connections for CPC devices."""
        if not conn_string or not hasattr(self, 'database_manager'):
            return

        # Update all CPC ACTRIS tabs with connection string
        for dev_id, widget in self.data_holder.device_widgets.items():
            if hasattr(widget, 'device_type') and widget.device_type == CPC:
                if hasattr(widget, 'database_tab'):
                    widget.database_tab.connection_string_input.setText(conn_string)

        # Restore database enabled state for CPCs
        for device_config in self.config.devices:
            if device_config.device_type != CPC:
                continue

            db_enabled = device_config.extra_params.get('database_enabled', False)
            if not db_enabled:
                continue

            cpc_widget = self.data_holder.device_widgets.get(device_config.device_id)
            if not cpc_widget or not hasattr(cpc_widget, 'database_tab'):
                continue

            # Block signals during restoration
            cpc_widget.database_tab.db_enabled_checkbox.blockSignals(True)

            # Populate RHTP dropdown
            cpc_widget.database_tab.populate_rhtp_dropdown()

            # Restore linked RHTP selection (by device_id, not index)
            linked_rhtp = device_config.extra_params.get('linked_rhtp', 'None')
            if linked_rhtp != 'None':
                index = cpc_widget.database_tab.linked_rhtp_dropdown.findData(linked_rhtp)
                if index >= 0:
                    cpc_widget.database_tab.linked_rhtp_dropdown.setCurrentIndex(index)

            # Set checkbox
            cpc_widget.database_tab.db_enabled_checkbox.setChecked(True)
            cpc_widget.database_tab.db_enabled_checkbox.blockSignals(False)

            # Connect to database
            interval_str = device_config.extra_params.get('db_averaging_interval', '1 minute')
            interval_map = {'1 minute': 1, '5 minutes': 5, '10 minutes': 10, '15 minutes': 15, '1 hour': 60, '3 hours': 180}
            interval_minutes = interval_map.get(interval_str, 1)

            success, message = self.database_manager.register_device(device_config.device_id, conn_string)
            if success:
                self.database_manager.create_averager(device_config.device_id, interval_minutes)
                cpc_widget.database_tab.db_status_value.setText("Enabled")
                cpc_widget.database_tab.db_status_value.setStyleSheet("color: green;")
                cpc_widget.database_tab.update_global_connection_status()
                cpc_widget.database_tab.sync_global_status_to_all_cpcs()

    def _update_psm_cpc_connections(self):
        """Update PSM connected CPC references after all devices are loaded."""
        for device_config in self.config.devices:
            if device_config.device_type not in [PSM, PSM2]:
                continue

            cpc_id = device_config.extra_params.get('connected_cpc', 'None')
            if cpc_id == 'None':
                continue

            psm_widget = self.data_holder.device_widgets.get(device_config.device_id)
            if psm_widget and hasattr(psm_widget, 'connected_cpc_device'):
                cpc_widget = self.data_holder.device_widgets.get(cpc_id)
                if cpc_widget:
                    psm_widget.connected_cpc_device = cpc_widget

    def _update_cpc_dict(self):
        """Update CPC dictionary for PSM device linking."""
        self.cpc_dict = {'None': 'None'}
        for device_config in self.config.devices:
            if device_config.device_type in [CPC, TSI_CPC]:
                name = device_config.device_nickname or f"{device_config.device_type_name} {device_config.serial_number}"
                if not name.strip():
                    name = device_config.device_type_name
                self.cpc_dict[name] = device_config.device_id

    def _update_rhtp_dict(self):
        """Update RHTP dictionary for CPC database linking."""
        self.rhtp_dict = {'None': 'None'}
        for device_config in self.config.devices:
            if device_config.device_type == RHTP:
                name = device_config.device_nickname or f"{device_config.device_type_name} {device_config.serial_number}"
                if not name.strip():
                    name = device_config.device_type_name
                self.rhtp_dict[name] = device_config.device_id

    def _refresh_psm_cpc_dropdowns(self):
        """Refresh Connected CPC dropdowns in all PSM widgets."""
        # Use pre-built cpc_dict for performance (avoids nested iteration)
        for device_config in self.config.devices:
            if device_config.device_type in [PSM, PSM2]:
                psm_widget = self.data_holder.device_widgets.get(device_config.device_id)
                if psm_widget and hasattr(psm_widget, '_populate_cpc_dropdown'):
                    psm_widget._populate_cpc_dropdown(self.cpc_dict)

    def x_range_changed(self, viewbox):
        # if autoscale y is on
        if self.config.plot_settings.autoscale_y:
            viewbox.enableAutoRange(axis='y')
            viewbox.setAutoVisible(y=True)

    # called when main plot's auto range button is clicked
    def auto_range_clicked(self):
        # disable follow
        self.config.plot_settings.follow = False
        # emit signal to save config
        self.plot_settings_changed.emit(self.config.plot_settings)

        # set autorange on for individual plots
        for device_config in self.config.devices:
            widget = self.data_holder.device_widgets.get(device_config.device_id)
            if not widget:
                continue

            if device_config.device_type == ELECTROMETER:
                for plot in widget.plot_tab.plots:
                    plot.enableAutoRange()
            else:
                widget.plot_tab.plot.enableAutoRange()

    # update device tab name according to nickname or serial number
    def rename_tab(self, device_id: int):
        """Update tab name for a device based on nickname or serial number."""
        # Find device config
        device_config = next((d for d in self.config.devices if d.device_id == device_id), None)
        if not device_config:
            return

        # Check if device widget exists
        if device_id not in self.data_holder.device_widgets:
            return

        device_widget = self.data_holder.device_widgets[device_id]
        tab_index = self.device_tabs.indexOf(device_widget)

        # Build tab name: nickname, or "Type SerialNumber"
        if device_config.device_nickname:
            device_name = device_config.device_nickname
        elif device_config.serial_number:
            device_name = f"{device_config.device_type_name} {device_config.serial_number}"
        else:
            device_name = device_config.device_type_name

        # update tab name in tab bar
        if tab_index >= 0:
            self.device_tab_bar.setTabText(tab_index, device_name)

    def closeEvent(self, event):
        """Handle application close event - cleanup all resources."""
        logging.info("Application closing, cleaning up resources...")

        # Stop timer service first (stops data acquisition loop)
        if hasattr(self, 'timer_service'):
            try:
                self.timer_service.stop()
                logging.info("Timer service stopped")
            except Exception as e:
                logging.error(f"Error stopping timer service: {e}")

        # Stop port scanner threads
        if hasattr(self, 'device_manager') and hasattr(self.device_manager, 'port_scanner'):
            try:
                self.device_manager.port_scanner.stop_all()
                logging.info("Port scanner stopped")
            except Exception as e:
                logging.error(f"Error stopping port scanner: {e}")

        # Close all device serial connections
        for dev_id, widget in self.data_holder.device_widgets.items():
            if hasattr(widget, 'connection'):
                try:
                    widget.connection.close()
                    logging.debug(f"Closed serial connection for device {dev_id}")
                except Exception as e:
                    logging.debug(f"Error closing device {dev_id} connection: {e}")

        # Disconnect from database if connected
        if hasattr(self, 'database_manager') and self.database_manager.connected:
            try:
                self.database_manager.disconnect()
                logging.info("Database disconnected")
            except Exception as e:
                logging.error(f"Error disconnecting database: {e}")

        logging.info("Cleanup complete, accepting close event")
        event.accept()


# application format
if __name__ == '__main__': # protects from accidentally invoking the script when not intended
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
