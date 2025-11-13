#!/usr/bin/env python3
"""
Test script for the new device identification patterns.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src/config'))

from device_patterns import DeviceIdentifier


def test_new_patterns():
    """Test the newly added device patterns."""

    print("=" * 60)
    print("TESTING NEW DEVICE IDENTIFICATION PATTERNS")
    print("=" * 60)
    print()

    # Test cases for the new patterns
    test_cases = [
        # RHTP - exact match for 2300001
        ("2300001", "RHTP", "RHTP exact serial 2300001"),
        ("2300002", "2300002", "Should not match RHTP (returns serial)"),
        ("230000", "230000", "Should not match RHTP (returns serial)"),
        ("23000011", "23000011", "Should not match RHTP (returns serial)"),

        # A30 CPC - matches "301 Jerry" pattern (must end with Jerry)
        ("301 Jerry", "A30 CPC", "A30 CPC with exact name"),
        ("301Jerry", "A30 CPC", "A30 CPC without space"),
        ("3015Jerry", "A30 CPC", "A30 CPC with numbers between"),
        ("301 Jerry Smith", "301 Jerry Smith", "Should not match (extra text after Jerry)"),
        ("302 Jerry", "302 Jerry", "Should not match A30 (wrong prefix)"),

        # A20 CPC - matches "235 Peggy" pattern (must end with Peggy)
        ("235 Peggy", "A20 CPC", "A20 CPC with exact name"),
        ("235Peggy", "A20 CPC", "A20 CPC without space"),
        ("2359Peggy", "A20 CPC", "A20 CPC with numbers between"),
        ("235 Peggy Smith", "235 Peggy Smith", "Should not match (extra text after Peggy)"),
        ("236 Peggy", "236 Peggy", "Should not match A20 (wrong prefix)"),

        # Ensure old CPC patterns still work
        ("2812001104", "CPC", "Original CPC pattern (2 + 9 digits)"),
        ("3792508436", "CPC", "Original CPC pattern (3 + 9 digits)"),

        # PSM patterns should still work
        ("821445616", "PSM 2.0", "PSM 2.0 pattern"),
        ("9142501", "PSM Retrofit", "PSM Retrofit pattern"),

        # Electrometer should still work
        ("NewEMDAQ", "Electrometer", "Electrometer pattern"),
    ]

    passed = 0
    failed = 0

    for serial, expected, description in test_cases:
        result = DeviceIdentifier.identify_device(serial_number=serial)

        if result == expected:
            passed += 1
            status = "✓ PASS"
            color = "\033[92m"  # Green
        else:
            failed += 1
            status = "✗ FAIL"
            color = "\033[91m"  # Red

        print(f"{color}{status}\033[0m | {description}")
        print(f"  Input: '{serial}'")
        print(f"  Expected: {expected}, Got: {result}")
        print()

    # Summary
    print("=" * 60)
    print(f"SUMMARY: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 60)

    if failed == 0:
        print("\n✅ All tests passed! The new patterns are working correctly.")
    else:
        print(f"\n⚠️  {failed} tests failed. Check the patterns above.")

    return passed, failed


if __name__ == "__main__":
    test_new_patterns()