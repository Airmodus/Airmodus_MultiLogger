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

    def __init__(self, device_manager, data_holder, parent=None):
        super().__init__(parent)
        self.device_manager = device_manager
        self.data_holder = data_holder
        self.selected_port = None
        self.selected_type = None

        self.setWindowTitle("Select COM Port for New Device")
        self.resize(700, 400)

        # Query fresh port data from device_manager
        self.port_info = self._get_port_info()

        # Build UI
        self._setup_ui()

        # Connect to device_manager signals for real-time updates
        if self.device_manager:
            self.device_manager.port_discovered.connect(self._on_port_update)
            self.device_manager.port_scan_complete.connect(self._on_scan_complete)

    def _get_port_info(self):
        """Get current port information from device_manager."""
        try:
            # Use device_manager's cached port info (updated on every scan)
            if hasattr(self.device_manager, 'get_cached_port_info'):
                return self.device_manager.get_cached_port_info()

            return {}
        except Exception as e:
            print(f"Error getting port info: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _setup_ui(self):
        """Create and layout UI components."""
        layout = QVBoxLayout()

        # Header label
        header = QLabel("Select a COM port to add a device:")
        header.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(header)

        # Port table
        self.port_table = QTableWidget()
        self.port_table.setColumnCount(4)
        self.port_table.setHorizontalHeaderLabels(["Port", "Device Type", "Serial Number", "Status"])
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

    def _populate_table(self):
        """Fill table with port information."""
        if not self.port_info:
            # No ports available
            self.port_table.setRowCount(1)
            no_ports_item = QTableWidgetItem("No COM ports detected")
            no_ports_item.setForeground(QColor('#999'))
            self.port_table.setItem(0, 0, no_ports_item)
            self.port_table.setSpan(0, 0, 1, 4)
            return

        self.port_table.setRowCount(len(self.port_info))

        for row, (port, info) in enumerate(self.port_info.items()):
            # Port
            port_item = QTableWidgetItem(port)
            self.port_table.setItem(row, 0, port_item)

            # Device Type
            device_type = info.get('device_type', 'Unknown')
            type_item = QTableWidgetItem(device_type)
            if device_type and device_type != 'Unknown':
                type_item.setForeground(QColor('green'))
                type_item.setToolTip("Device type detected automatically")
            self.port_table.setItem(row, 1, type_item)

            # Serial Number
            serial = info.get('serial_number', '-')
            if serial and len(serial) > 15:
                # Truncate long serial numbers
                serial = serial[:12] + "..."
            serial_item = QTableWidgetItem(serial)
            self.port_table.setItem(row, 2, serial_item)

            # Status
            status = info.get('status', 'unknown')
            status_text = status.replace('_', ' ').title()
            status_item = QTableWidgetItem(status_text)

            # Color code by status
            if status == 'available':
                status_item.setForeground(QColor('green'))
                port_item.setToolTip("Click to add device on this port")
            elif status in ['in_use', 'connected']:
                status_item.setForeground(QColor('red'))
                # Gray out entire row
                for col in range(4):
                    item = self.port_table.item(row, col)
                    if item:
                        item.setForeground(QColor('#999'))
                        item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                port_item.setToolTip("Port already in use by another device")
            elif status == 'error':
                status_item.setForeground(QColor('orange'))
                port_item.setToolTip("Error communicating with port")

            self.port_table.setItem(row, 3, status_item)

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
        if status in ['in_use', 'connected']:
            QMessageBox.warning(
                self,
                "Port In Use",
                f"Port {port} is already connected to another device.\n\n"
                f"Please select a different port or disconnect the existing device first."
            )
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

        # Check if detected type is one of our known device types
        known_device_types = set(self.data_holder.device_names.values())
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
