#!/usr/bin/env python3
"""
Test that monitoring starts after the QTimer delay.
"""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
import pyqtgraph as pg

def check_monitoring(main_window):
    """Check if monitoring has started."""
    if hasattr(main_window, 'device_manager') and hasattr(main_window.device_manager, 'port_scanner'):
        scanner = main_window.device_manager.port_scanner
        if scanner.monitoring_thread and scanner.monitoring_thread.isRunning():
            print("✅ SUCCESS: Continuous monitoring is now running!")
            print(f"  - Thread: {scanner.monitoring_thread}")
            print(f"  - Continuous mode: {scanner.monitoring_thread.continuous_monitoring}")
            return True
        else:
            print("⏳ Monitoring not started yet...")
            return False
    return False

def test_delayed_startup():
    """Test that monitoring starts after delay."""
    app = QApplication(sys.argv)

    print("\n=== Testing Delayed Monitoring Startup ===\n")

    from app import MainWindow

    print("Creating MainWindow...")
    main_window = MainWindow()

    # Schedule periodic checks
    check_count = [0]
    max_checks = 10

    def periodic_check():
        check_count[0] += 1
        print(f"\nCheck {check_count[0]} (after {check_count[0] * 500}ms):")

        if check_monitoring(main_window):
            print("\n🎉 Monitoring successfully started!")
            app.quit()
        elif check_count[0] >= max_checks:
            print("\n❌ Monitoring did not start after 5 seconds")
            app.quit()
        else:
            QTimer.singleShot(500, periodic_check)

    # Start checking after 500ms
    QTimer.singleShot(500, periodic_check)

    app.exec_()

if __name__ == "__main__":
    test_delayed_startup()