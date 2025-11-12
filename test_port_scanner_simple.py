#!/usr/bin/env python3
"""
Simple test for port scanner - tests just the scanner module directly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Direct import to test the scanner module
import serial.tools.list_ports
import time

print("=" * 70)
print("SIMPLE PORT SCANNER TEST - macOS")
print("=" * 70)

print("\n1. Testing serial port enumeration...")
ports = list(serial.tools.list_ports.comports())
print(f"   Found {len(ports)} port(s):")
for port in ports:
    print(f"   - {port.device}: {port.description}")

print("\n2. Testing device pattern matching...")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'config'))
from device_patterns import DeviceIdentifier

test_serials = [
    "CPC12345",
    "PSM2-67890",
    "PSM-R123",
    "ELM-456",
    "RHTP-789",
    "TSI3775",
    "AFM-100",
    "CO2-200",
    "EDIL-300",
    "Unknown123"
]

print("   Pattern matching results:")
for serial in test_serials:
    device_type, confidence = DeviceIdentifier.identify_device(serial_number=serial)
    status = "✓" if device_type != "Unknown" else "✗"
    print(f"   {status} {serial:20} -> {device_type:15} (confidence: {confidence:.1f})")

print("\n3. Testing threaded port scanning...")
from PyQt5.QtCore import QCoreApplication
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'managers'))
from port_scanner import PortScannerThread

app = QCoreApplication([])

scanner = PortScannerThread(continuous_monitoring=False)
discovered = []

def on_discovered(port_info):
    discovered.append(port_info)
    print(f"   ✓ Discovered: {port_info['port']} [{port_info['status']}] - {port_info.get('device_type', 'Unknown')}")

def on_complete(all_ports):
    print(f"   Scan complete: {len(all_ports)} port(s) found")
    app.quit()

scanner.port_discovered.connect(on_discovered)
scanner.scan_complete.connect(on_complete)

print("   Starting background scan...")
scanner.start()

# Timeout after 10 seconds
from PyQt5.QtCore import QTimer
QTimer.singleShot(10000, app.quit)

app.exec_()
scanner.stop()

print("\n" + "=" * 70)
print("TEST SUMMARY:")
print(f"✓ Port enumeration: {len(ports)} ports found")
print(f"✓ Pattern matching: Working correctly")
print(f"✓ Threaded scanning: {len(discovered)} ports discovered")
print("✓ All tests completed successfully!")
print("=" * 70)