# managers/device_manager.py
from PyQt5.QtCore import QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QIcon
from time import time
import traceback
from serial.tools import list_ports
from serial import Serial
import logging
from numpy import full, nan, isnan, array_equal
from serial.serialutil import SerialException
from config import *
from utils import (
    compile_cpc_settings,
    compile_psm_settings
)
from .port_scanner import PortScannerManager, PortInfo

# Timeout for port scan recovery (if scan is stuck longer than this, reset and allow new scan)
SCAN_TIMEOUT_SECONDS = 30

class DeviceManager(QObject):
    # Signals for port scanning events
    port_scan_started = pyqtSignal()
    port_scan_progress = pyqtSignal(int, int)  # current, total
    port_scan_complete = pyqtSignal()
    port_discovered = pyqtSignal(dict)  # port info dict

    def __init__(self, config, data_holder, device_widgets, device_tabs=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.data_holder = data_holder
        self.device_widgets = device_widgets
        self.device_tabs = device_tabs  # Reference to MainWindow.device_tabs (QStackedWidget) for widget lookup
        self.device_tab_bar = None  # Reference to MainWindow.device_tab_bar (QTabBar) for tab icons
        self.osx_mode = osx_mode

        # Initialize port scanner manager
        self.port_scanner = PortScannerManager()
        self._scanning = False
        self._scan_start_time = None  # Track when scan started for timeout recovery
        self._com_port_list = []  # Cache current port list
        self._port_info_cache = {}  # Cache port info for dialogs  

    def connection_test(self):
        """Check and manage device connections, update states."""
        # Use cached port list from last scan
        com_port_list = self._com_port_list
        self.data_holder.device_errors = {key: False for key in self.data_holder.device_errors}

        for device_config in self.config.devices:
            dev_id = device_config.device_id
            device_widget = self.data_holder.device_widgets.get(dev_id)

            if not device_widget:
                continue  # Skip if widget not found

            connection = device_widget.connection

            # Get port directly - pyserial accepts just the number on Windows
            port = device_config.com_port

            # Check if currently connected
            was_connected = hasattr(connection, 'connection') and connection.connection.is_open

            # If was connected but port is no longer available, close connection
            if was_connected and port not in com_port_list:
                try:
                    connection.close()
                except Exception as e:
                    logging.error(traceback.format_exc())

            connected = False

            # Only try to connect if port is in the available port list
            # This prevents false "connected" status when port doesn't exist
            if port and port in com_port_list:
                # Check if already connected
                try:
                    if hasattr(connection, 'connection') and connection.connection.is_open:
                        connected = True
                except Exception:
                    pass

                # If not connected, check if connection attempt is in progress
                if not connected:
                    if hasattr(connection, 'is_connecting') and connection.is_connecting():
                        # Connection attempt in progress, wait for next cycle
                        pass
                    else:
                        # Start async connection attempt (non-blocking)
                        # Set port first if needed
                        if connection.serial_port != port:
                            connection.set_port(port)
                        # Start background connection - next cycle will detect success
                        connection.connect_async()

            # Handle connection state changes
            if device_widget:
                # Handle connection established
                if connected and not was_connected:
                    # Log connection
                    logging.info(f"[SERIAL CONNECT] DevID={dev_id} Port={port} DeviceType={device_widget.dev_type}")

                    # Register for IDN inquiry if device supports it
                    if device_widget.supports_idn_inquiry():
                        if dev_id not in self.data_holder.idn_inquiry_devices:
                            self.data_holder.idn_inquiry_devices.append(dev_id)

                    # Device-specific connection setup
                    device_widget.on_connection_established()

                    # Update UI styling if device has command widget
                    if device_widget.has_command_widget():
                        if dev_id in self.device_widgets:
                            self.device_widgets[dev_id].setObjectName("connected")
                            self.device_widgets[dev_id].setStyleSheet("")

                # Handle disconnection
                if not connected and was_connected:
                    # Log disconnection
                    logging.info(f"[SERIAL DISCONNECT] DevID={dev_id} Port={port}")

                    # Device-specific cleanup
                    device_widget.on_disconnection()

                    # Update UI styling if device has command widget
                    if device_widget.has_command_widget():
                        if dev_id in self.device_widgets:
                            self.device_widgets[dev_id].setObjectName("disconnected")
                            self.device_widgets[dev_id].setStyleSheet("")

            # Store connected state in widget for runtime access
            device_widget.is_connected = connected
            if not self.data_holder.first_connection:
                self.data_holder.first_connection = connected

        # Refresh port status after connections to update dropdown cache
        self.list_com_ports()

    def list_com_ports(self):
        """
        Start an asynchronous scan of available serial COM ports with device identification.

        This method now uses threaded scanning to prevent UI blocking.
        Port discovery results are delivered via signals.
        """
        # Check if scanning is stuck (timeout recovery)
        if self._scanning:
            if self._scan_start_time is not None:
                elapsed = time() - self._scan_start_time
                if elapsed > SCAN_TIMEOUT_SECONDS:
                    logging.warning(f"Port scan timeout after {elapsed:.1f}s, resetting scanner")
                    self._scanning = False
                    self._scan_start_time = None
                    # Stop any hung scanner thread
                    try:
                        self.port_scanner.stop_all()
                    except Exception as e:
                        logging.error(f"Error stopping scanner: {e}")
                    # Clean up stale port descriptions to prevent memory accumulation
                    current_ports = {p.device for p in list_ports.comports()}
                    stale_ports = [p for p in self.data_holder.com_descriptions if p not in current_ports]
                    for port in stale_ports:
                        self.data_holder.com_descriptions.pop(port, None)
                    # Also clean up port info cache
                    stale_cache_ports = [p for p in self._port_info_cache if p not in current_ports]
                    for port in stale_cache_ports:
                        self._port_info_cache.pop(port, None)
                else:
                    logging.debug("Port scan already in progress, skipping")
                    return self._com_port_list
            else:
                logging.debug("Port scan already in progress, skipping")
                return self._com_port_list

        self._scanning = True
        self._scan_start_time = time()
        self.port_scan_started.emit()

        # Start asynchronous port scan with error handling
        try:
            self.port_scanner.start_single_scan(
                callback_discovered=self._on_port_discovered,
                callback_complete=self._on_scan_complete
            )
        except Exception as e:
            logging.error(f"Failed to start port scan: {e}")
            self._scanning = False
            self._scan_start_time = None

        # Return cached port list (will be updated asynchronously)
        return self._com_port_list

    def _on_port_discovered(self, port_info: dict):
        """
        Handle progressive port discovery from scanner thread.

        Args:
            port_info: Dictionary with port information
        """
        # Update descriptions with serial number if available
        # But don't overwrite existing valid descriptions (prevents sensor data corruption)
        current_desc = self.data_holder.com_descriptions.get(port_info['port'], '')

        # Only update if:
        # 1. There's no current description
        # 2. Current description is "Unknown" or empty
        # 3. New serial number is available and doesn't look like sensor data
        should_update = (
            not current_desc or
            current_desc == 'Unknown' or
            current_desc == ''
        )

        if should_update:
            if port_info['serial_number']:
                # Don't update if serial looks like sensor data (pure number)
                try:
                    float(port_info['serial_number'].replace(',', '.'))
                    # This looks like sensor data, don't use it
                    if not current_desc:
                        # No current description, use device type instead
                        self.data_holder.com_descriptions[port_info['port']] = port_info['device_type']
                except ValueError:
                    # Not a pure number, safe to use
                    self.data_holder.com_descriptions[port_info['port']] = port_info['serial_number']
            else:
                # Use description or device type as fallback
                self.data_holder.com_descriptions[port_info['port']] = (
                    port_info['description'] or port_info['device_type']
                )

        # Update cached port list
        if port_info['port'] not in self._com_port_list:
            self._com_port_list.append(port_info['port'])

        # Build progressive status and info for this port
        port_statuses = {port_info['port']: port_info.get('status', 'unknown')}
        port_info_dict = {
            port_info['port']: {
                'device_type': port_info.get('device_type', 'Unknown'),
                'serial_number': port_info.get('serial_number', ''),
                'manufacturer': port_info.get('manufacturer', ''),
                'vid_pid': port_info.get('vid_pid', ''),
                'firmware': port_info.get('firmware', '')
            }
        }

        # Check if this port is actually connected to a device in the application
        for device_config in self.config.devices:
            widget = self.data_holder.device_widgets.get(device_config.device_id)
            if widget and hasattr(widget, 'is_connected') and widget.is_connected:
                # Get port for this device
                port = device_config.com_port

                # Mark this port as connected if it matches the discovered port
                if port and port != 'Select port...' and port == port_info['port']:
                    port_statuses[port_info['port']] = 'connected'
                    # Update device info from config (scanner can't probe busy ports)
                    port_info_dict[port_info['port']]['device_type'] = device_config.device_type_name
                    if device_config.serial_number:
                        port_info_dict[port_info['port']]['serial_number'] = device_config.serial_number
                    break

        # Update cache progressively so dialog can show real-time updates
        self._port_info_cache[port_info['port']] = {
            **port_info_dict[port_info['port']],
            'status': port_statuses.get(port_info['port'], 'unknown')
        }

        # Emit signal for UI updates (PortSelectionDialog will get fresh data when opened)
        self.port_discovered.emit(port_info)

        # Update GUI progressively
        self._update_gui_port_display()

    def _on_scan_complete(self, all_ports: list):
        """
        Handle scan completion from scanner thread.

        Args:
            all_ports: List of all discovered port dictionaries
        """
        self._scanning = False
        self._scan_start_time = None

        # Update cached port list with all discovered ports
        self._com_port_list = [p['port'] for p in all_ports]

        # Build status and info dictionaries from scan results
        port_statuses = {}
        port_info_dict = {}
        for port_data in all_ports:
            port = port_data['port']
            port_statuses[port] = port_data.get('status', 'unknown')
            port_info_dict[port] = {
                'device_type': port_data.get('device_type', 'Unknown'),
                'serial_number': port_data.get('serial_number', ''),
                'manufacturer': port_data.get('manufacturer', ''),
                'vid_pid': port_data.get('vid_pid', ''),
                'firmware': port_data.get('firmware', '')
            }

        # Check which ports are actually connected to devices in the application
        for device_config in self.config.devices:
            widget = self.data_holder.device_widgets.get(device_config.device_id)
            if widget and hasattr(widget, 'is_connected') and widget.is_connected:
                # Get port for this device
                port = device_config.com_port

                # Mark this port as connected in status dictionary
                if port and port != 'Select port...' and port in port_statuses:
                    port_statuses[port] = 'connected'
                    # Update device info from config (scanner can't probe busy ports)
                    if port in port_info_dict:
                        port_info_dict[port]['device_type'] = device_config.device_type_name
                        if device_config.serial_number:
                            port_info_dict[port]['serial_number'] = device_config.serial_number

        # Cache combined port info with status for dialogs
        self._port_info_cache = {}
        for port in port_info_dict:
            self._port_info_cache[port] = {
                **port_info_dict[port],
                'status': port_statuses.get(port, 'unknown')
            }

        # Clean up descriptions for disconnected ports
        disconnected_ports = [
            p for p in self.data_holder.com_descriptions
            if p not in self._com_port_list
        ]
        for port in disconnected_ports:
            self.data_holder.com_descriptions.pop(port)

        # Update GUI with final results
        self._update_gui_port_display()

        # Check if inquiry flag timeout
        if self.data_holder.inquiry_flag and time() > self.data_holder.inquiry_time + 3:
            self.data_holder.inquiry_flag = False

        self.port_scan_complete.emit()

    def get_cached_port_info(self):
        """
        Get cached port information from the last scan.

        Returns:
            dict: Dictionary mapping port names to their info dicts.
                  Each info dict contains: device_type, serial_number, manufacturer, vid_pid, status
        """
        return self._port_info_cache.copy()

    def _update_gui_port_display(self):
        """Update the GUI display of available COM ports."""
        # Format text for connected ports only, sorted by port name
        connected_descriptions = {
            key: desc for key, desc in self.data_holder.com_descriptions.items()
            if key in self._com_port_list
        }
        sorted_ports = sorted(connected_descriptions.items())
        com_ports_text = '\n'.join(f"{port} - {desc}" for port, desc in sorted_ports)

        # Log available ports (Serial ports text display removed)
        logging.debug(f"Available COM ports:\n{com_ports_text}")

    def start_port_monitoring(self):
        """Start continuous port monitoring for hot-plug detection."""
        self.port_scanner.start_monitoring(
            callback_added=self._on_port_added,
            callback_removed=self._on_port_removed
        )

    def _on_port_added(self, port: str, description: str):
        """Handle hot-plugged port detection - automatically query IDN and update UI."""
        logging.info(f"New port detected: {port} - {description}")

        # Add to cache
        if port not in self._com_port_list:
            self._com_port_list.append(port)
            self.data_holder.com_descriptions[port] = description

            # Update the GUI display
            self._update_gui_port_display()

            # Update device dropdowns with the new port
            port_statuses = {port: 'available'}
            port_info_dict = {
                port: {
                    'device_type': 'Unknown',  # Will be updated after IDN query
                    'serial_number': description,
                    'manufacturer': '',
                    'vid_pid': ''
                }
            }

            # Port info is cached and will be available when PortSelectionDialog opens

    def _on_port_removed(self, port: str):
        """Handle port disconnection - automatically disconnect devices using this port."""
        logging.info(f"Port removed: {port}")

        # Find and disconnect any devices using this port
        for device_config in self.config.devices:
            # Get port for this device
            device_port = device_config.com_port

            widget = self.data_holder.device_widgets.get(device_config.device_id)
            if not widget:
                continue

            # If this device is using the removed port and is connected, disconnect it
            if device_port == port and hasattr(widget, 'is_connected') and widget.is_connected:
                try:
                    # Close the connection
                    if hasattr(widget.connection, 'connection'):
                        widget.connection.connection.close()
                    logging.info(f"Auto-disconnected device on removed port: {port}")
                except Exception as e:
                    logging.error(f"Error disconnecting device on port {port}: {e}")

                # Update connected status
                widget.is_connected = False

                # Update UI for device-specific handling
                widget.on_disconnection()

                # Update UI styling if device has command widget
                if widget.has_command_widget():
                    if device_config.device_id in self.device_widgets:
                        self.device_widgets[device_config.device_id].setObjectName("disconnected")
                        self.device_widgets[device_config.device_id].setStyleSheet("")

        # Remove from cache
        if port in self._com_port_list:
            self._com_port_list.remove(port)
        if port in self.data_holder.com_descriptions:
            del self.data_holder.com_descriptions[port]
            self._update_gui_port_display()

    def get_dev_data(self):
        """Send read commands to connected devices."""
        for device_config in self.config.devices:
            widget = self.data_holder.device_widgets.get(device_config.device_id)
            if not widget:
                continue

            if hasattr(widget, 'is_connected') and widget.is_connected:
                try:
                    # Device-specific read commands
                    widget.send_read_commands(widget.connection, device_config)

                    # IDN/firmware inquiry
                    if widget.supports_idn_inquiry():
                        if device_config.device_id in self.data_holder.idn_inquiry_devices:
                            self._idn_inquiry(widget.connection.connection)
                        elif widget.supports_firmware_inquiry():
                            firmware_version = device_config.extra_params.get('firmware_version', '')
                            if firmware_version == "":
                                self._firmware_inquiry(widget.connection.connection)
                except Exception as e:
                    logging.error(traceback.format_exc())
 

    def _idn_inquiry(self, connection):
        """Delayed IDN send."""
        def send_idn():
            if hasattr(connection, 'connection') and connection.connection.is_open:
                connection.write(b'*IDN?\n')
        QTimer.singleShot(IDN_INQUIRY_DELAY_MS, send_idn)

    def _firmware_inquiry(self, connection):
        """Delayed firmware send."""
        def send_firmware():
            if hasattr(connection, 'connection') and connection.connection.is_open:
                connection.write(b':SYST:VER\n')
        QTimer.singleShot(FIRMWARE_INQUIRY_DELAY_MS, send_firmware)


    def readIndata(self):
        """
        Read data from all connected devices.

        This method is completely generic - it works for ALL device types without
        any device-specific if/elif clauses. Each device handles its own logic via:
        - device.handle_serial_data() - reads and parses serial data
        - device.process_parsed_messages() - processes results and updates state
        """
        for device_config in self.config.devices:
            widget = self.data_holder.device_widgets.get(device_config.device_id)

            if not widget:
                continue  # Skip if widget not found

            if hasattr(widget, 'is_connected') and widget.is_connected:
                try:
                    # Step 1: Device reads and parses its serial data
                    parsed_messages = widget.handle_serial_data(widget.connection, self.data_holder)

                    # Step 2: Device processes parsed messages and updates state
                    result = widget.process_parsed_messages(parsed_messages, device_config, self.data_holder)

                except Exception as e:
                    logging.exception(e)

    # check and update 10 hz settings
    def ten_hz_check(self):
        # go through devices
        for device_config in self.config.devices:
            try:
                device_widget = self.data_holder.device_widgets.get(device_config.device_id)

                # Delegate 10 Hz validation to device
                if device_widget and device_widget.supports_10hz_mode():
                    device_widget.validate_10hz_mode(self.config, device_config)

            except Exception as e:
                logging.error(traceback.format_exc())

    def update_error_icons(self):
        """Update tab error icons according to device error status."""
        if not self.device_tabs:
            return  # Skip if device_tabs not provided

        for device_config in self.config.devices:
            try:
                device_id = device_config.device_id

                # Skip if device not fully initialized yet
                if device_id not in self.data_holder.device_widgets:
                    continue

                error = self.data_holder.device_errors.get(device_id, False)
                device_widget = self.data_holder.device_widgets[device_id]
                tab_index = self.device_tabs.indexOf(device_widget)
                connected = hasattr(device_widget, 'is_connected') and device_widget.is_connected

                # Disconnected devices
                if not connected:
                    if self.device_tab_bar and tab_index >= 0:
                        self.device_tab_bar.setTabIcon(tab_index, self.data_holder.disconnected_icon)
                    self.data_holder.error_status = 1
                # Devices with errors
                elif error:
                    if self.device_tab_bar and tab_index >= 0:
                        self.device_tab_bar.setTabIcon(tab_index, self.data_holder.error_icon)
                    if device_widget.has_status_tab():
                        status_tab_index = device_widget.indexOf(device_widget.get_status_tab())
                        device_widget.setTabIcon(status_tab_index, self.data_holder.error_icon)
                # Connected devices without errors
                else:
                    if self.device_tab_bar and tab_index >= 0:
                        self.device_tab_bar.setTabIcon(tab_index, QIcon())
                    if device_widget.has_status_tab():
                        status_tab_index = device_widget.indexOf(device_widget.get_status_tab())
                        device_widget.setTabIcon(status_tab_index, QIcon())

                # Device-specific error checks (e.g., PSM CO flow error)
                if device_widget.has_device_specific_errors():
                    if self.device_tab_bar and tab_index >= 0:
                        self.device_tab_bar.setTabIcon(tab_index, self.data_holder.error_icon)
                    set_tab_index = device_widget.indexOf(device_widget.set_tab)
                    device_widget.setTabIcon(set_tab_index, self.data_holder.error_icon)
                elif hasattr(device_widget, 'set_tab'):
                    # Clear set tab icon if no device-specific errors
                    set_tab_index = device_widget.indexOf(device_widget.set_tab)
                    device_widget.setTabIcon(set_tab_index, QIcon())
            except Exception as e:
                logging.exception(e)

