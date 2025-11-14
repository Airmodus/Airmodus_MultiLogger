#!/usr/bin/env python3
"""
Test script to verify IDN parsing is working correctly.
Tests the parsing logic with various IDN response formats.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils import parse_idn_response

def test_idn_parsing():
    """Test IDN parsing with various formats."""
    print("Testing IDN Response Parsing\n" + "="*50)

    test_cases = [
        # Test case 1: Standard format with newlines
        ("*IDN Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0\r\n", "Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0"),

        # Test case 2: Simple serial number
        ("*IDN SERIAL123\r", "SERIAL123"),

        # Test case 3: With only \n
        ("*IDN MyDevice123\n", "MyDevice123"),

        # Test case 4: With both \r and \n
        ("*IDN TestDevice456\r\n", "TestDevice456"),

        # Test case 5: No newlines
        ("*IDN PlainSerial789", "PlainSerial789"),

        # Test case 6: Complex serial with spaces
        ("*IDN Airmodus PSM 2.0,PSN:PSM-0789,FW:2.0.1\r", "Airmodus PSM 2.0,PSN:PSM-0789,FW:2.0.1"),

        # Test case 7: Extra spaces and newlines
        ("*IDN   SerialWithSpaces  \r\n", "SerialWithSpaces"),
    ]

    passed = 0
    failed = 0

    for i, (input_msg, expected) in enumerate(test_cases, 1):
        print(f"\nTest {i}: {repr(input_msg[:30])}...")
        result = parse_idn_response(input_msg)
        actual = result['data']

        if actual == expected:
            print(f"  ✅ PASSED: Got '{actual}'")
            passed += 1
        else:
            print(f"  ❌ FAILED:")
            print(f"     Expected: '{expected}'")
            print(f"     Got:      '{actual}'")
            failed += 1

    print("\n" + "="*50)
    print(f"Results: {passed} passed, {failed} failed")

    return failed == 0


def test_port_scanner_parsing():
    """Test the actual port scanner parsing logic."""
    print("\n\nTesting Port Scanner IDN Extraction\n" + "="*50)

    # Simulate what port_scanner does
    def extract_idn_from_messages(raw_data):
        """Simulate port_scanner._query_device_idn parsing."""
        decoded = raw_data.decode('utf-8', errors='ignore')
        messages = decoded.split('\r')

        for message in messages:
            message = message.strip('\n').strip('\r').strip()

            # Check if message is long enough and contains *IDN
            if len(message) > 5 and '*IDN ' in message:
                # Extract everything after "*IDN " (position 5)
                idx = message.index('*IDN ')
                serial_number = message[idx + 5:].strip()
                return serial_number
        return None

    test_data = [
        # Multi-line response as bytes
        (b'*IDN Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0\r\n', "Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0"),
        (b'Some junk\r*IDN MyDevice\rMore junk\r', "MyDevice"),
        (b'*IDN SerialNumber123\r', "SerialNumber123"),
    ]

    passed = 0
    failed = 0

    for i, (raw_bytes, expected) in enumerate(test_data, 1):
        print(f"\nTest {i}: {repr(raw_bytes[:30])}...")
        result = extract_idn_from_messages(raw_bytes)

        if result == expected:
            print(f"  ✅ PASSED: Got '{result}'")
            passed += 1
        else:
            print(f"  ❌ FAILED:")
            print(f"     Expected: '{expected}'")
            print(f"     Got:      '{result}'")
            failed += 1

    print("\n" + "="*50)
    print(f"Port Scanner Results: {passed} passed, {failed} failed")

    return failed == 0


if __name__ == "__main__":
    utils_ok = test_idn_parsing()
    scanner_ok = test_port_scanner_parsing()

    if utils_ok and scanner_ok:
        print("\n✅ All IDN parsing tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the parsing logic.")
        sys.exit(1)