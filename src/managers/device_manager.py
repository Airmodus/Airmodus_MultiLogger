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

class DeviceManager(QObject):
    # Signals for port scanning events
    port_scan_started = pyqtSignal()
    port_scan_progress = pyqtSignal(int, int)  # current, total
    port_scan_complete = pyqtSignal()
    port_discovered = pyqtSignal(dict)  # port info dict

    def __init__(self, params, data_holder, device_widgets, device_tabs=None, parent=None):
        super().__init__(parent)
        self.params = params
        self.data_holder = data_holder
        self.device_widgets = device_widgets
        self.device_tabs = device_tabs  # Reference to MainWindow.device_tabs (QStackedWidget) for widget lookup
        self.device_tab_bar = None  # Reference to MainWindow.device_tab_bar (QTabBar) for tab icons
        self.osx_mode = osx_mode

        # Initialize port scanner manager
        self.port_scanner = PortScannerManager()
        self._scanning = False
        self._com_port_list = []  # Cache current port list
        self._port_info_cache = {}  # Cache port info for dialogs  

    def connection_test(self):
        """Check and manage device connections, update states."""
        # Use cached port list from last scan
        com_port_list = self._com_port_list
        self.data_holder.device_errors = {key: False for key in self.data_holder.device_errors}

        for dev in self.params.child('Device settings').children():
            connected = dev.child('Connected').value()
            if self.osx_mode:
                port = str(dev.child('COM port').value())
            else:
                port = "COM" + str(dev.child('COM port').value())
            
            if connected and port not in com_port_list:
                try:
                    dev.child('Connection').value().close()
                except Exception as e:
                    logging.error(traceback.format_exc())
            connected = False
            
            try:
                if hasattr(dev.child('Connection').value(), 'connection') and dev.child('Connection').value().connection.is_open:
                    connected = True
                else:
                    dev.child('Connection').value().connect()
                    if dev.child('Connection').value().connection.is_open:
                        connected = True
            except AttributeError:
                try:
                    dev.child('Connection').value().set_port(port)
                    dev.child('Connection').value().connect()
                    if dev.child('Connection').value().connection.is_open:
                        connected = True
                except Exception:
                    pass
            except Exception:
                pass
            
            # IDN inquiry and connection state management
            dev_id = dev.child('DevID').value()
            device_widget = self.data_holder.get_device(dev_id)

            if device_widget:
                # Handle connection established
                if connected and not dev.child('Connected').value():
                    # Log connection
                    logging.info(f"[SERIAL CONNECT] DevID={dev_id} Port={port} DeviceType={device_widget.dev_type}")

                    # Register for IDN inquiry if device supports it
                    if device_widget.supports_idn_inquiry():
                        if dev_id not in self.data_holder.idn_inquiry_devices:
                            self.data_holder.idn_inquiry_devices.append(dev_id)
                            print(f"[DEBUG IDN] Device manager: Added device {dev_id} to IDN inquiry list")

                    # Device-specific connection setup
                    device_widget.on_connection_established(dev)

                    # Update UI styling if device has command widget
                    if device_widget.has_command_widget():
                        if dev_id in self.device_widgets:
                            self.device_widgets[dev_id].setObjectName("connected")
                            self.device_widgets[dev_id].setStyleSheet("")

                # Handle disconnection
                if not connected and dev.child('Connected').value():
                    # Log disconnection
                    logging.info(f"[SERIAL DISCONNECT] DevID={dev_id} Port={port}")

                    # Device-specific cleanup
                    device_widget.on_disconnection(dev)

                    # Update UI styling if device has command widget
                    if device_widget.has_command_widget():
                        if dev_id in self.device_widgets:
                            self.device_widgets[dev_id].setObjectName("disconnected")
                            self.device_widgets[dev_id].setStyleSheet("")

            dev.child('Connected').setValue(connected)
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
        if self._scanning:
            logging.debug("Port scan already in progress, skipping")
            return self._com_port_list

        self._scanning = True
        self.port_scan_started.emit()

        # Start asynchronous port scan
        self.port_scanner.start_single_scan(
            callback_discovered=self._on_port_discovered,
            callback_complete=self._on_scan_complete
        )

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
                'vid_pid': port_info.get('vid_pid', '')
            }
        }

        # Update dropdowns progressively with new port info
        self.params.child('Device settings').update_com_port_dropdowns(
            self.data_holder.com_descriptions,
            port_statuses,
            port_info_dict
        )

        # Emit signal for UI updates
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
                'vid_pid': port_data.get('vid_pid', '')
            }

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

        # Update dropdowns for all devices with status and type info
        self.params.child('Device settings').update_com_port_dropdowns(
            self.data_holder.com_descriptions,
            port_statuses,
            port_info_dict
        )

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

            # Update all device dropdowns to include the new port
            self.params.child('Device settings').update_com_port_dropdowns(
                self.data_holder.com_descriptions,
                port_statuses,
                port_info_dict
            )

    def _on_port_removed(self, port: str):
        """Handle port disconnection - automatically disconnect devices using this port."""
        logging.info(f"Port removed: {port}")

        # Find and disconnect any devices using this port
        for dev in self.params.child('Device settings').children():
            if self.osx_mode:
                device_port = str(dev.child('COM port').value())
            else:
                device_port = "COM" + str(dev.child('COM port').value())

            # If this device is using the removed port, disconnect it
            if device_port == port and dev.child('Connected').value():
                try:
                    # Close the connection
                    if hasattr(dev.child('Connection').value(), 'connection'):
                        dev.child('Connection').value().connection.close()
                    logging.info(f"Auto-disconnected device on removed port: {port}")
                except Exception as e:
                    logging.error(f"Error disconnecting device on port {port}: {e}")

                # Update connected status
                dev.child('Connected').setValue(False)

                # Update UI for device-specific handling
                dev_id = dev.child('DevID').value()
                device_widget = self.data_holder.get_device(dev_id)
                if device_widget:
                    device_widget.on_disconnection(dev)
                    # Update UI styling if device has command widget
                    if device_widget.has_command_widget():
                        if dev_id in self.device_widgets:
                            self.device_widgets[dev_id].setObjectName("disconnected")
                            self.device_widgets[dev_id].setStyleSheet("")

        # Remove from cache
        if port in self._com_port_list:
            self._com_port_list.remove(port)
        if port in self.data_holder.com_descriptions:
            del self.data_holder.com_descriptions[port]
            self._update_gui_port_display()

    def get_dev_data(self):
        """Send read commands to connected devices."""
        for dev in self.params.child('Device settings').children():
            if dev.child('Connected').value():
                dev_id = dev.child('DevID').value()
                dev_conn = dev.child('Connection').value()
                device_widget = self.data_holder.get_device(dev_id)

                if device_widget:
                    try:
                        # Device-specific read commands
                        device_widget.send_read_commands(dev_conn, dev)

                        # IDN/firmware inquiry
                        if device_widget.supports_idn_inquiry():
                            if dev_id in self.data_holder.idn_inquiry_devices:
                                print(f"[DEBUG IDN] Device manager: Sending *IDN? query to device {dev_id} on port {dev.child('COM port').value()}")
                                self._idn_inquiry(dev_conn.connection)
                            elif device_widget.supports_firmware_inquiry():
                                if dev.child('Firmware version').value() == "":
                                    self._firmware_inquiry(dev_conn.connection)
                    except Exception as e:
                        logging.error(traceback.format_exc())
 

    def _idn_inquiry(self, connection):
        """Delayed IDN send."""
        QTimer.singleShot(IDN_INQUIRY_DELAY_MS, lambda: connection.write(b'*IDN?\n'))

    def _firmware_inquiry(self, connection):
        """Delayed firmware send."""
        QTimer.singleShot(FIRMWARE_INQUIRY_DELAY_MS, lambda: connection.write(b':SYST:VER\n'))


    def readIndata(self):
        """
        Read data from all connected devices.

        This method is completely generic - it works for ALL device types without
        any device-specific if/elif clauses. Each device handles its own logic via:
        - device.handle_serial_data() - reads and parses serial data
        - device.process_parsed_messages() - processes results and updates state
        """
        for dev in self.params.child('Device settings').children():
            if dev.child('Connected').value():
                dev_id = dev.child('DevID').value()
                dev_conn = dev.child('Connection').value()
                widget = self.data_holder.device_widgets.get(dev_id)

                if not widget:
                    continue  # Skip if widget not found

                try:
                    # Step 1: Device reads and parses its serial data
                    parsed_messages = widget.handle_serial_data(dev_conn, self.data_holder)

                    # Step 2: Device processes parsed messages and updates state
                    result = widget.process_parsed_messages(parsed_messages, dev, self.data_holder)

                except Exception as e:
                    print(traceback.format_exc())
                    logging.exception(e)

    # check and update 10 hz settings
    def ten_hz_check(self):
        # go through devices
        for dev in self.params.child('Device settings').children():
            try:
                dev_id = dev.child('DevID').value()
                device_widget = self.data_holder.get_device(dev_id)

                # Delegate 10 Hz validation to device
                if device_widget and device_widget.supports_10hz_mode():
                    device_widget.validate_10hz_mode(self.params, dev)

            except Exception as e:
                logging.error(traceback.format_exc())

    def update_error_icons(self):
        """Update tab error icons according to device error status."""
        if not self.device_tabs:
            return  # Skip if device_tabs not provided

        for dev in self.params.child('Device settings').children():
            try:
                device_id = dev.child('DevID').value()

                # Skip if device not fully initialized yet
                if device_id not in self.data_holder.device_widgets:
                    continue

                error = self.data_holder.device_errors.get(device_id, False)
                device_widget = self.data_holder.device_widgets[device_id]
                tab_index = self.device_tabs.indexOf(device_widget)
                connected = dev.child('Connected').value()

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
                print(traceback.format_exc())
                logging.exception(e)

