#!/usr/bin/env python3
"""
Test that the full app starts with automatic port monitoring.
"""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
import pyqtgraph as pg

def test_app_startup():
    """Test that app starts with automatic monitoring."""
    app = QApplication(sys.argv)

    print("\n=== Testing App Integration with Auto Port Monitoring ===\n")

    # Import MainWindow after QApplication
    from app import MainWindow

    print("Creating MainWindow (this simulates app startup)...")
    main_window = MainWindow()

    # Check if device manager exists
    if hasattr(main_window, 'device_manager'):
        print("✅ DeviceManager created")

        # Wait a bit for initialization
        time.sleep(1)

        # Check if monitoring started
        if hasattr(main_window.device_manager, 'port_scanner'):
            scanner = main_window.device_manager.port_scanner
            print(f"Port scanner exists: {scanner}")

            # Check if monitoring thread is running (it should start after 500ms)
            time.sleep(1)  # Wait for QTimer.singleShot(500, ...) to trigger

            if scanner.monitoring_thread and scanner.monitoring_thread.isRunning():
                print("✅ SUCCESS: Continuous monitoring is running automatically!")
                print(f"  - Thread: {scanner.monitoring_thread}")
                print(f"  - Continuous mode: {scanner.monitoring_thread.continuous_monitoring}")
            else:
                print("❌ WARNING: Monitoring thread not running yet")
                print("  (It should start automatically after 500ms)")
        else:
            print("❌ Port scanner not found in DeviceManager")
    else:
        print("❌ DeviceManager not found")

    # Check if "Update serial ports" button was removed
    try:
        button = main_window.params.child('Serial ports').child('Update serial ports')
        print("❌ FAILED: 'Update serial ports' button still exists!")
        print(f"  Button: {button}")
    except:
        print("✅ SUCCESS: 'Update serial ports' button has been removed")

    # Check Available serial ports field still exists
    try:
        ports_field = main_window.params.child('Serial ports').child('Available serial ports')
        print(f"✅ 'Available serial ports' field exists: {ports_field}")
    except:
        print("❌ 'Available serial ports' field missing")

    print("\n=== Test Complete ===")
    print("The app should now automatically detect device plug/unplug events.")

    # Clean shutdown
    QTimer.singleShot(2000, app.quit)
    app.exec_()

if __name__ == "__main__":
    test_app_startup()