#!/usr/bin/env python3
"""
Test script for the refactored port scanner on macOS.
This tests the background scanning, device detection, and UI updates.
"""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget, QPushButton, QLabel
from PyQt5.QtCore import Qt
from src.managers.port_scanner import PortScannerManager

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Port Scanner Test")
        self.setGeometry(100, 100, 800, 600)

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Status label
        self.status_label = QLabel("Ready to scan ports")
        layout.addWidget(self.status_label)

        # Scan button
        self.scan_button = QPushButton("Start Port Scan")
        self.scan_button.clicked.connect(self.start_scan)
        layout.addWidget(self.scan_button)

        # Results text area
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        layout.addWidget(self.results_text)

        # Initialize port scanner
        self.scanner = PortScannerManager()

    def start_scan(self):
        """Start the port scan."""
        self.status_label.setText("Scanning ports...")
        self.results_text.clear()
        self.scan_button.setEnabled(False)

        # Start scan with callbacks
        self.scanner.start_single_scan(
            callback_discovered=self.on_port_discovered,
            callback_complete=self.on_scan_complete
        )

    def on_port_discovered(self, port_info):
        """Handle progressive port discovery."""
        # Format port information
        text = f"\n{'='*60}\n"
        text += f"Port: {port_info['port']}\n"
        text += f"Status: {port_info.get('status', 'unknown')}\n"
        text += f"Device Type: {port_info.get('device_type', 'Unknown')}\n"
        text += f"Serial Number: {port_info.get('serial_number', 'N/A')}\n"
        text += f"Description: {port_info.get('description', 'N/A')}\n"
        text += f"Manufacturer: {port_info.get('manufacturer', 'N/A')}\n"
        text += f"VID:PID: {port_info.get('vid_pid', 'N/A')}\n"

        # Append to results
        current_text = self.results_text.toPlainText()
        self.results_text.setPlainText(current_text + text)

        # Scroll to bottom
        scrollbar = self.results_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_scan_complete(self, all_ports):
        """Handle scan completion."""
        self.status_label.setText(f"Scan complete! Found {len(all_ports)} port(s)")
        self.scan_button.setEnabled(True)

        # Add summary
        summary = f"\n{'='*60}\n"
        summary += f"SCAN SUMMARY:\n"
        summary += f"Total ports found: {len(all_ports)}\n"

        # Count by status
        status_counts = {}
        for port in all_ports:
            status = port.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in status_counts.items():
            summary += f"  {status}: {count}\n"

        # Count by device type
        type_counts = {}
        for port in all_ports:
            dev_type = port.get('device_type', 'Unknown')
            type_counts[dev_type] = type_counts.get(dev_type, 0) + 1

        summary += "\nDevice types detected:\n"
        for dev_type, count in type_counts.items():
            summary += f"  {dev_type}: {count}\n"

        current_text = self.results_text.toPlainText()
        self.results_text.setPlainText(current_text + summary)

        # Scroll to bottom
        scrollbar = self.results_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        """Clean up on close."""
        self.scanner.stop_all()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()