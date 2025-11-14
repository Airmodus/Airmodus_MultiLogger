#!/usr/bin/env python3
"""
Simple test to verify port monitoring starts correctly.
"""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt5.QtWidgets import QApplication
from managers.port_scanner import PortScannerManager

def test_monitoring_startup():
    """Test that monitoring thread starts correctly."""
    app = QApplication(sys.argv)

    print("Creating PortScannerManager...")
    scanner = PortScannerManager()

    # Check initial state
    print(f"Initial monitoring_thread: {scanner.monitoring_thread}")

    # Start monitoring
    print("Starting continuous monitoring...")
    scanner.start_monitoring(
        callback_added=lambda p, d: print(f"Port added: {p} - {d}"),
        callback_removed=lambda p: print(f"Port removed: {p}")
    )

    # Check if thread started
    time.sleep(0.5)
    if scanner.monitoring_thread and scanner.monitoring_thread.isRunning():
        print("✅ SUCCESS: Monitoring thread is running!")
        print(f"Thread object: {scanner.monitoring_thread}")
        print(f"Continuous monitoring: {scanner.monitoring_thread.continuous_monitoring}")
    else:
        print("❌ FAILED: Monitoring thread is not running")

    # Let it run for a few seconds
    print("\nLetting monitoring run for 5 seconds...")
    time.sleep(5)

    # Stop monitoring
    print("Stopping monitoring...")
    scanner.stop_all()

    print("Test complete!")

if __name__ == "__main__":
    test_monitoring_startup()