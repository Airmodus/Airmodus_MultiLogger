#!/usr/bin/env python3
"""
Test script to verify that COM port dropdowns are auto-populated when adding a new device.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
import time

# Import the parameter tree
from params import p

def test_auto_population():
    """Test that COM port dropdowns are populated automatically."""
    app = QApplication(sys.argv)

    print("=" * 70)
    print("TESTING COM PORT DROPDOWN AUTO-POPULATION")
    print("=" * 70)

    # Get the device settings group
    device_settings = p.child('Device settings')

    # Test 1: Check initial state
    print("\n1. Initial State:")
    print(f"   Number of devices: {len(device_settings.children())}")
    print(f"   Cached ports: {device_settings.cached_ports}")

    # Test 2: Simulate port data being available
    print("\n2. Simulating available ports...")
    test_ports = {
        'COM1 - Test Device 1': 'COM1',
        'COM2 - Test Device 2': 'COM2',
        'COM3 - Test Device 3': 'COM3'
    }
    test_statuses = {
        'COM1': 'available',
        'COM2': 'in_use',
        'COM3': 'available'
    }
    test_info = {
        'COM1': {'device_type': 'CPC', 'serial_number': 'CPC123'},
        'COM2': {'device_type': 'PSM 2.0', 'serial_number': 'PSM2-456'},
        'COM3': {'device_type': 'Unknown', 'serial_number': ''}
    }

    # Update the dropdowns (this would normally be called by DeviceManager)
    device_settings.update_com_port_dropdowns(
        {'COM1': 'Test Device 1', 'COM2': 'Test Device 2', 'COM3': 'Test Device 3'},
        test_statuses,
        test_info
    )

    print(f"   Cached ports after update: {len(device_settings.cached_ports)} ports")
    print(f"   Port values: {list(device_settings.cached_ports.keys())[:4]}...")  # Show first few

    # Test 3: Add a new device
    print("\n3. Adding a new CPC device...")
    device_settings.addNew("CPC", "Test CPC")

    # Check if the new device has ports populated
    new_device = device_settings.children()[-1]
    com_port_param = new_device.child('COM port')

    print(f"   New device name: {new_device.name()}")
    print(f"   COM port parameter exists: {com_port_param is not None}")

    if com_port_param and hasattr(com_port_param, 'opts'):
        ports_in_param = com_port_param.opts.get('ports', {})
        print(f"   Ports in COM port dropdown: {len(ports_in_param)} ports")
        print(f"   Port options: {list(ports_in_param.keys())[:4]}...")  # Show first few

        # Check if status info is also present
        statuses_in_param = com_port_param.opts.get('port_statuses', {})
        info_in_param = com_port_param.opts.get('port_info', {})
        print(f"   Has status info: {len(statuses_in_param) > 0}")
        print(f"   Has device info: {len(info_in_param) > 0}")

    # Test 4: Add another device
    print("\n4. Adding a PSM device...")
    device_settings.addNew("PSM 2.0", "Test PSM")

    new_device2 = device_settings.children()[-1]
    com_port_param2 = new_device2.child('COM port')

    print(f"   New device name: {new_device2.name()}")
    if com_port_param2 and hasattr(com_port_param2, 'opts'):
        ports_in_param2 = com_port_param2.opts.get('ports', {})
        print(f"   Ports in COM port dropdown: {len(ports_in_param2)} ports")

    print("\n" + "=" * 70)
    print("TEST RESULTS:")

    # Verify results
    success = True
    if len(device_settings.cached_ports) == 0:
        print("✗ FAILED: No ports cached")
        success = False
    else:
        print(f"✓ Ports cached: {len(device_settings.cached_ports)} ports")

    if com_port_param and hasattr(com_port_param, 'opts'):
        ports_in_param = com_port_param.opts.get('ports', {})
        if len(ports_in_param) > 0:
            print(f"✓ New device has ports: {len(ports_in_param)} ports")
        else:
            print("✗ FAILED: New device has no ports in dropdown")
            success = False
    else:
        print("✗ FAILED: COM port parameter not created properly")
        success = False

    if success:
        print("\n✓ ALL TESTS PASSED - Dropdowns are auto-populated!")
    else:
        print("\n✗ SOME TESTS FAILED")

    print("=" * 70)

    return success

if __name__ == '__main__':
    success = test_auto_population()
    sys.exit(0 if success else 1)