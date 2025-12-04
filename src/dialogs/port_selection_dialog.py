"""
Port Selection Dialog

Shows available COM ports when adding a new device.
User clicks a port to auto-create device (if type detected) or select type manually.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                              QTableWidgetItem, QPushButton, QLabel, QHeaderView,
                              QMessageBox, QMenu)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QCursor
import serial.tools.list_ports


class PortSelectionDialog(QDialog):
    """
    Dialog for selecting a COM port when adding a new device.

    Shows all available ports with detected device types.
    User clicks a port to create device automatically or choose type manually.
    """

    def __init__(self, device_manager, data_holder=None, parent=None, filter_device_type=None):
        super().__init__(parent)
        self.device_manager = device_manager
        self.data_holder = data_holder
        self.selected_port = None
        self.selected_type = None
        self.filter_device_type = filter_device_type

        # Set window title based on mode
        if filter_device_type:
            self.setWindowTitle(f"Change COM Port for {filter_device_type}")
        else:
            self.setWindowTitle("Select COM Port for New Device")
        self.resize(700, 400)

        # Query fresh port data from device_manager
        self.port_info = self._get_port_info()

        # Track port name to table row mapping for incremental updates
        self._port_to_row = {}

        # Build UI
        self._setup_ui()

        # Connect to device_manager signals for real-time updates
        if self.device_manager:
            self.device_manager.port_discovered.connect(self._on_port_update)
            self.device_manager.port_scan_complete.connect(self._on_scan_complete)

        # Trigger fresh port scan for accurate status (non-blocking)
        # This ensures the dialog shows current port availability after recent changes
        if self.device_manager:
            self.device_manager.list_com_ports()

    def _get_port_info(self):
        """Get current port information from device_manager."""
        try:
            # Use device_manager's cached port info (updated on every scan)
            if hasattr(self.device_manager, 'get_cached_port_info'):
                all_ports = self.device_manager.get_cached_port_info()

                # Apply filtering if filter_device_type is set
                if self.filter_device_type:
                    return self._filter_ports(all_ports)

                return all_ports

            return {}
        except Exception as e:
            print(f"Error getting port info: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _compute_short_ids(self):
        """
        Compute unique short identifiers for all ports.

        Returns:
            dict: Mapping of port -> short_id
        """
        from utils import compute_unique_short_ids

        # Build serial_numbers dict from port_info
        serial_numbers = {
            port: info.get('serial_number', '')
            for port, info in self.port_info.items()
        }

        return compute_unique_short_ids(serial_numbers)

    def _filter_ports(self, all_ports):
        """
        Filter ports based on device type.

        Rules:
        - If device is Airmodus type: show only ports identified as that type + unidentified ports
        - If device is Unknown: show all unidentified ports
        - Exclude ports identified as different device types
        - Allow selection of in-use ports (for swapping)
        """
        if not self.filter_device_type:
            return all_ports

        filtered = {}

        for port, info in all_ports.items():
            detected_type = info.get('device_type', 'Unknown')

            # Always include ports with matching device type
            if detected_type == self.filter_device_type:
                filtered[port] = info
                continue

            # Include unidentified ports
            if detected_type == 'Unknown' or not detected_type:
                filtered[port] = info
                continue

            # If current device is Unknown type, include all unidentified ports
            if self.filter_device_type == 'Unknown':
                if detected_type == 'Unknown' or not detected_type:
                    filtered[port] = info
                continue

        return filtered

    def _setup_ui(self):
        """Create and layout UI components."""
        layout = QVBoxLayout()

        # Header label
        if self.filter_device_type:
            header = QLabel(f"Select a COM port for {self.filter_device_type}:")
        else:
            header = QLabel("Select a COM port to add a device:")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # Port table
        self.port_table = QTableWidget()
        self.port_table.setColumnCount(4)
        self.port_table.setHorizontalHeaderLabels(["Port", "Device Type", "ID", "Status"])
        self.port_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.port_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.port_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.port_table.verticalHeader().setVisible(False)
        self._populate_table()

        # Connect click signal
        self.port_table.cellClicked.connect(self._on_port_clicked)

        layout.addWidget(self.port_table)

        # Info label
        info_label = QLabel("💡 Tip: Click a port with detected device type to auto-create, "
                           "or click unknown port to choose type manually.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(info_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _add_port_row(self, port, port_data, short_id):
        """Add a new row for the given port."""
        # Insert new row at the end
        row = self.port_table.rowCount()
        self.port_table.insertRow(row)

        # Track this port's row
        self._port_to_row[port] = row

        # Populate the row
        # Port
        port_item = QTableWidgetItem(port)
        self.port_table.setItem(row, 0, port_item)

        # Device Type
        device_type = port_data.get('device_type', 'Unknown')
        type_item = QTableWidgetItem(device_type)
        self.port_table.setItem(row, 1, type_item)

        # Serial Number - show unique short identifier
        serial = port_data.get('serial_number', '')
        serial_item = QTableWidgetItem(short_id if short_id else '-')
        if serial and short_id != serial:
            serial_item.setToolTip(f"Full serial: {serial}")
        self.port_table.setItem(row, 2, serial_item)

        # Status
        status = port_data.get('status', 'unknown')
        status_text = status.replace('_', ' ').title()
        status_item = QTableWidgetItem(status_text)
        self.port_table.setItem(row, 3, status_item)

        # Apply styling
        self._update_row_styling(row, port, port_data)

    def _remove_port_row(self, port):
        """Remove the row for the given port and update row indices."""
        if port not in self._port_to_row:
            return

        row = self._port_to_row[port]
        self.port_table.removeRow(row)

        # Remove from tracking
        del self._port_to_row[port]

        # Update indices for all rows after the removed row
        for p, idx in list(self._port_to_row.items()):
            if idx > row:
                self._port_to_row[p] = idx - 1

    def _update_port_row(self, row, port, port_data, short_id):
        """Update an existing row only if data has changed."""
        changed = False

        # Check and update Device Type
        device_type = port_data.get('device_type', 'Unknown')
        type_item = self.port_table.item(row, 1)
        if type_item and type_item.text() != device_type:
            type_item.setText(device_type)
            changed = True

        # Check and update Serial Number - show unique short identifier
        serial = port_data.get('serial_number', '')
        display_serial = short_id if short_id else '-'
        serial_item = self.port_table.item(row, 2)
        if serial_item and serial_item.text() != display_serial:
            serial_item.setText(display_serial)
            if serial and short_id != serial:
                serial_item.setToolTip(f"Full serial: {serial}")
            changed = True

        # Check and update Status
        status = port_data.get('status', 'unknown')
        status_text = status.replace('_', ' ').title()
        status_item = self.port_table.item(row, 3)
        if status_item and status_item.text() != status_text:
            status_item.setText(status_text)
            changed = True

        # If any data changed, update styling
        if changed:
            self._update_row_styling(row, port, port_data)

    def _update_row_styling(self, row, port, port_data):
        """Apply styling to a row based on port data."""
        device_type = port_data.get('device_type', 'Unknown')
        status = port_data.get('status', 'unknown')

        port_item = self.port_table.item(row, 0)
        type_item = self.port_table.item(row, 1)
        status_item = self.port_table.item(row, 3)

        # Style device type
        if device_type and device_type != 'Unknown':
            type_item.setForeground(QColor('green'))
            type_item.setToolTip("Device type detected automatically")
        else:
            type_item.setForeground(QColor('black'))
            type_item.setToolTip("")

        # Style status and entire row based on status
        if status == 'available':
            status_item.setForeground(QColor('green'))
            port_item.setToolTip("Click to add device on this port")
            # Ensure row is enabled
            for col in range(4):
                item = self.port_table.item(row, col)
                if item:
                    item.setFlags(item.flags() | Qt.ItemIsEnabled)
                    if col != 1 and (device_type == 'Unknown' or not device_type):
                        item.setForeground(QColor('black'))
        elif status in ['in_use', 'connected']:
            # In filter mode, allow selection of in-use ports (show in yellow/orange)
            if self.filter_device_type:
                status_item.setForeground(QColor('orange'))
                port_item.setToolTip("Click to switch this device to this port (will disconnect other device)")
                # Ensure row is enabled
                for col in range(4):
                    item = self.port_table.item(row, col)
                    if item:
                        item.setFlags(item.flags() | Qt.ItemIsEnabled)
            else:
                # In add new device mode, disable in-use ports
                status_item.setForeground(QColor('red'))
                port_item.setToolTip("Port already in use by another device")
                # Gray out entire row
                for col in range(4):
                    item = self.port_table.item(row, col)
                    if item:
                        item.setForeground(QColor('#999'))
                        item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
        elif status == 'error':
            status_item.setForeground(QColor('orange'))
            port_item.setToolTip("Error communicating with port")
            # Ensure row is enabled
            for col in range(4):
                item = self.port_table.item(row, col)
                if item:
                    item.setFlags(item.flags() | Qt.ItemIsEnabled)

    def _populate_table(self):
        """Fill table with port information using incremental updates."""
        # Handle transition between empty and non-empty states
        if not self.port_info:
            # No ports available - show message if not already showing
            if self.port_table.rowCount() != 1 or not self._is_showing_no_ports_message():
                self.port_table.clearSpans()
                self.port_table.setRowCount(1)
                self._port_to_row.clear()
                no_ports_item = QTableWidgetItem("No COM ports detected")
                no_ports_item.setForeground(QColor('#999'))
                self.port_table.setItem(0, 0, no_ports_item)
                self.port_table.setSpan(0, 0, 1, 4)
            return

        # If we were showing "no ports" message, clear it and reset tracking
        if self._is_showing_no_ports_message():
            self.port_table.clearSpans()
            self.port_table.setRowCount(0)
            self._port_to_row.clear()

        # Compute unique short IDs for all ports
        short_ids = self._compute_short_ids()

        # Build sets of current vs new ports
        current_ports = set(self._port_to_row.keys())
        new_ports = set(self.port_info.keys())

        # Remove ports that disappeared
        ports_to_remove = current_ports - new_ports
        for port in ports_to_remove:
            self._remove_port_row(port)

        # Add new ports
        ports_to_add = new_ports - current_ports
        for port in ports_to_add:
            self._add_port_row(port, self.port_info[port], short_ids.get(port, ''))

        # Update existing ports (only if data changed)
        ports_to_update = current_ports & new_ports
        for port in ports_to_update:
            row = self._port_to_row[port]
            self._update_port_row(row, port, self.port_info[port], short_ids.get(port, ''))

    def _is_showing_no_ports_message(self):
        """Check if the table is currently showing the 'no ports' message."""
        if self.port_table.rowCount() == 1:
            first_item = self.port_table.item(0, 0)
            if first_item and first_item.text() == "No COM ports detected":
                return True
        return False

    def _on_port_clicked(self, row, column):
        """Handle port selection."""
        port_item = self.port_table.item(row, 0)
        if not port_item:
            return

        port = port_item.text()

        # Check if this is the "no ports" message
        if port == "No COM ports detected":
            return

        # Get port data
        if port not in self.port_info:
            return

        port_data = self.port_info[port]
        status = port_data.get('status')

        # Check if port is available
        # In filter mode (changing device port), allow selection of in-use ports
        if not self.filter_device_type and status in ['in_use', 'connected']:
            QMessageBox.warning(
                self,
                "Port In Use",
                f"Port {port} is already connected to another device.\n\n"
                f"Please select a different port or disconnect the existing device first."
            )
            return

        # In filter mode, warn but allow swapping
        if self.filter_device_type and status in ['in_use', 'connected']:
            reply = QMessageBox.question(
                self,
                "Port In Use",
                f"Port {port} is already connected to another device.\n\n"
                f"Selecting this port will disconnect the other device and reconnect "
                f"this device to it.\n\nDo you want to continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        if status == 'error':
            reply = QMessageBox.question(
                self,
                "Port Error",
                f"There was an error communicating with port {port}.\n\n"
                f"Do you still want to try adding a device on this port?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        # Get detected device type
        detected_type = port_data.get('device_type', 'Unknown')

        # If in filter mode (changing port), accept any port selection
        if self.filter_device_type:
            self.selected_port = port
            self.selected_type = detected_type or self.filter_device_type
            self.accept()
            return

        # Check if detected type is one of our known device types
        known_device_types = set(self.data_holder.device_names.values()) if self.data_holder else set()
        is_known_type = detected_type in known_device_types

        if detected_type and detected_type != 'Unknown' and is_known_type:
            # Auto-create device of detected type (only if it's a known type)
            self.selected_port = port
            self.selected_type = detected_type
            self.accept()
        else:
            # Show type selection menu for unknown/unrecognized ports
            self._show_type_menu(port)

    def _show_type_menu(self, port):
        """Show device type selection menu for unknown ports."""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { font-size: 12px; }")

        # Get device type names from data_holder (sourced from config)
        # This automatically includes all device types defined in config.py
        device_names = self.data_holder.device_names

        # Add menu item for each device type
        for device_type_id, device_type_name in device_names.items():
            action = menu.addAction(device_type_name)
            action.triggered.connect(
                lambda checked, p=port, t=device_type_name: self._type_selected(p, t)
            )

        # Show menu at cursor position
        menu.exec_(QCursor.pos())

    def _type_selected(self, port, device_type):
        """Handle manual device type selection."""
        self.selected_port = port
        self.selected_type = device_type
        self.accept()

    def _on_port_update(self, port_info_dict):
        """Handle real-time port discovery updates."""
        # Refresh port info and repopulate table
        self.port_info = self._get_port_info()
        self._populate_table()

    def _on_scan_complete(self):
        """Handle scan completion - final refresh."""
        # Refresh port info and repopulate table
        self.port_info = self._get_port_info()
        self._populate_table()

    def get_selected_port(self):
        """Return selected port path."""
        return self.selected_port

    def get_selected_type(self):
        """Return selected device type."""
        return self.selected_type

    def get_selected_serial_number(self):
        """Return serial number of the selected port (if detected)."""
        if self.selected_port and self.selected_port in self.port_info:
            return self.port_info[self.selected_port].get('serial_number', '')
        return ''

    def get_selected_firmware(self):
        """Return firmware version of the selected port (if detected)."""
        if self.selected_port and self.selected_port in self.port_info:
            return self.port_info[self.selected_port].get('firmware', '')
        return ''

    def showEvent(self, event):
        """Enable fast port scanning when dialog is shown."""
        super().showEvent(event)
        # Switch to fast polling (2s) for responsive UI updates
        if self.device_manager and hasattr(self.device_manager, 'port_scanner'):
            self.device_manager.port_scanner.set_fast_mode(True)

    def done(self, result):
        """Disable fast port scanning when dialog is closed."""
        # Switch back to slow polling (10s) for background detection
        if self.device_manager and hasattr(self.device_manager, 'port_scanner'):
            self.device_manager.port_scanner.set_fast_mode(False)
        super().done(result)
