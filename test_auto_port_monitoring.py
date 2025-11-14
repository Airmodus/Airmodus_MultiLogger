#!/usr/bin/env python3
"""
Test script to verify automatic port monitoring functionality.
This script simulates the app startup and checks if continuous monitoring starts.
"""

import sys
import os
import time
import logging

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
import signal

def test_port_monitoring():
    """Test that continuous port monitoring works."""
    app = QApplication(sys.argv)

    # Import after QApplication is created
    from managers.port_scanner import PortScannerManager

    print("\n=== Testing Automatic Port Monitoring ===\n")

    # Create port scanner manager
    scanner = PortScannerManager()

    # Track events
    events = {
        'ports_added': [],
        'ports_removed': [],
        'ports_discovered': []
    }

    def on_port_added(port, description):
        print(f"✅ PORT ADDED: {port} - {description}")
        events['ports_added'].append((port, description))

    def on_port_removed(port):
        print(f"❌ PORT REMOVED: {port}")
        events['ports_removed'].append(port)

    def on_port_discovered(port_info):
        print(f"🔍 PORT DISCOVERED: {port_info.get('port')} - Type: {port_info.get('device_type')} - Serial: {port_info.get('serial_number', 'N/A')}")
        events['ports_discovered'].append(port_info)

    # Connect discovery callback for monitoring thread
    if scanner.monitoring_thread is None:
        print("Starting continuous port monitoring...")
        scanner.start_monitoring(
            callback_added=on_port_added,
            callback_removed=on_port_removed
        )

        # Also connect discovery signal
        if scanner.monitoring_thread:
            scanner.monitoring_thread.port_discovered.connect(on_port_discovered)

    print("\nMonitoring for port changes...")
    print("Try plugging/unplugging USB devices to test detection.")
    print("The monitor checks every 2 seconds for changes.")
    print("\nPress Ctrl+C to stop...\n")

    # Set up graceful shutdown
    def shutdown():
        print("\nStopping port monitoring...")
        scanner.stop_all()
        app.quit()

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, lambda *args: shutdown())

    # Also stop after 30 seconds for automated testing
    QTimer.singleShot(30000, shutdown)

    # Run the event loop
    app.exec_()

    # Print summary
    print("\n=== Summary ===")
    print(f"Ports added: {len(events['ports_added'])}")
    print(f"Ports removed: {len(events['ports_removed'])}")
    print(f"Ports discovered with IDN: {len(events['ports_discovered'])}")

    if events['ports_discovered']:
        print("\nDiscovered devices:")
        for port_info in events['ports_discovered']:
            if port_info.get('serial_number'):
                print(f"  - {port_info['port']}: {port_info['device_type']} (Serial: {port_info['serial_number']})")

if __name__ == "__main__":
    test_port_monitoring()