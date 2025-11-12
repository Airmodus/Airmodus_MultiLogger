#!/usr/bin/env python3
"""
Command-line test script for the refactored port scanner.
Tests background scanning, device detection, and status indicators.
"""

import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt5.QtCore import QCoreApplication, QTimer
from src.managers.port_scanner import PortScannerManager

def test_port_scanning():
    """Test the port scanner functionality."""
    print("=" * 70)
    print("PORT SCANNER TEST - macOS")
    print("=" * 70)

    app = QCoreApplication(sys.argv)
    scanner = PortScannerManager()

    # Track discovered ports
    discovered_ports = []
    scan_complete = [False]

    def on_port_discovered(port_info):
        """Handle progressive port discovery."""
        discovered_ports.append(port_info)
        print(f"\n✓ Port discovered: {port_info['port']}")
        print(f"  Status: {port_info.get('status', 'unknown')}")
        print(f"  Device Type: {port_info.get('device_type', 'Unknown')}")
        print(f"  Serial Number: {port_info.get('serial_number', 'N/A')}")
        print(f"  Description: {port_info.get('description', 'N/A')}")

    def on_scan_complete(all_ports):
        """Handle scan completion."""
        print("\n" + "=" * 70)
        print(f"SCAN COMPLETE - Found {len(all_ports)} port(s)")
        print("=" * 70)

        # Summary by status
        status_counts = {}
        for port in all_ports:
            status = port.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1

        print("\nPorts by Status:")
        for status, count in status_counts.items():
            print(f"  {status}: {count}")

        # Summary by device type
        type_counts = {}
        for port in all_ports:
            dev_type = port.get('device_type', 'Unknown')
            type_counts[dev_type] = type_counts.get(dev_type, 0) + 1

        print("\nDevice Types Detected:")
        for dev_type, count in type_counts.items():
            print(f"  {dev_type}: {count}")

        # Test pattern matching
        print("\n" + "=" * 70)
        print("DEVICE PATTERN MATCHING TEST")
        print("=" * 70)

        try:
            from src.config.device_patterns import DeviceIdentifier
        except ImportError:
            from config.device_patterns import DeviceIdentifier

        test_serials = [
            "CPC12345",
            "PSM2-67890",
            "PSM-R123",
            "ELM-456",
            "RHTP-789",
            "TSI3775",
            "Unknown123"
        ]

        for serial in test_serials:
            device_type, confidence = DeviceIdentifier.identify_device(serial_number=serial)
            print(f"  {serial:20} -> {device_type:15} (confidence: {confidence:.1f})")

        scan_complete[0] = True
        app.quit()

    print("\nStarting port scan...")
    scanner.start_single_scan(
        callback_discovered=on_port_discovered,
        callback_complete=on_scan_complete
    )

    # Set timeout
    QTimer.singleShot(15000, lambda: app.quit() if not scan_complete[0] else None)

    # Run event loop
    app.exec_()

    # Cleanup
    scanner.stop_all()

    print("\n✓ Test completed successfully!")
    return len(discovered_ports) > 0

if __name__ == '__main__':
    success = test_port_scanning()
    sys.exit(0 if success else 1)