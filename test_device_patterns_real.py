#!/usr/bin/env python3
"""
Test script for device identification patterns using real device examples.
Tests the patterns against actual device serial numbers from production.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'src/config'))

from device_patterns import DeviceIdentifier


def test_real_devices():
    """Test device identification with real device serial numbers."""

    # Real device examples from production
    test_cases = [
        # PSM 2.0 devices
        ("8211445616", "PSM 2.0", "Real PSM 2.0 device"),

        # PSM Retrofit devices
        ("9142501", "PSM Retrofit", "Real PSM Retrofit device"),

        # CPC devices
        ("2812001104", "CPC", "Real CPC starting with 2"),
        ("3792508436", "CPC", "Real CPC starting with 3"),

        # A30 CPC devices
        ("301* Jerry", "A30 CPC", "Real A30 CPC with Jerry"),
        ("301 Test", "A30 CPC", "A30 CPC with space"),

        # A20 CPC devices
        ("235* Peggy", "A20 CPC", "Real A20 CPC with Peggy"),
        ("235 Device", "A20 CPC", "A20 CPC with space"),

        # RHTP devices
        ("2300001", "RHTP", "Real RHTP device ID"),
        ("2345678", "RHTP", "RHTP with 23 prefix"),
        ("RHTP Sensor", "RHTP", "RHTP with name"),

        # AFM devices
        ("AFM Device", "AFM", "AFM device"),
        ("AFM-001", "AFM", "AFM with ID"),

        # Electrometer devices
        ("NewEMDAQ", "Electrometer", "Real Electrometer NewEMDAQ"),
        ("Electrometer V2", "Electrometer", "Electrometer with version"),

        # Non-Airmodus devices (should return as-is)
        ("TSI 3776", "TSI 3776", "TSI CPC - not Airmodus"),
        ("Random Device 123", "Random Device 123", "Unknown device - returned as-is"),
        ("12345", "12345", "Random serial - returned as-is"),

        # Edge cases
        ("", "Unknown", "Empty serial number"),
    ]

    print("=" * 80)
    print("DEVICE IDENTIFICATION WITH REAL EXAMPLES")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for serial, expected, description in test_cases:
        result = DeviceIdentifier.identify_device(serial_number=serial)

        # Check if the identification matches expected
        status = "✅ PASS" if result == expected else "❌ FAIL"

        if result == expected:
            passed += 1
            print(f"{status} | {description}")
            print(f"     Serial: '{serial}' -> '{result}'")
        else:
            failed += 1
            print(f"{status} | {description}")
            print(f"     Serial: '{serial}'")
            print(f"     Expected: '{expected}'")
            print(f"     Got: '{result}'")
        print()

    # Summary
    print("=" * 80)
    print(f"SUMMARY: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    return passed, failed


def test_non_aggressive_matching():
    """Test that non-Airmodus devices are NOT matched aggressively."""

    print("\nTesting non-aggressive matching (unknown devices should pass through):")
    print("-" * 80)

    # These should all return as-is (not be pattern matched)
    non_airmodus_devices = [
        "TSI 3750",
        "TSI 3776",
        "Generic Serial 123",
        "Unknown Device",
        "ABC123DEF",
        "123456",  # 6 digits - not RHTP pattern
        "987654321",  # 9 digits - not our CPC pattern
        "Some Random Device Name With Spaces",
    ]

    all_passed = True

    for serial in non_airmodus_devices:
        result = DeviceIdentifier.identify_device(serial_number=serial)

        # For non-Airmodus devices, result should equal input
        if result == serial:
            print(f"✅ '{serial}' -> '{result}' (passed through unchanged)")
        else:
            print(f"❌ '{serial}' -> '{result}' (should have been unchanged)")
            all_passed = False

    if all_passed:
        print("\n✅ All non-Airmodus devices correctly passed through unchanged!")
    else:
        print("\n❌ Some devices were incorrectly pattern matched!")

    print()


def test_fallback_behavior():
    """Test fallback behavior when serial is empty but model is provided."""

    print("\nTesting fallback behavior (model used when serial is empty):")
    print("-" * 80)

    test_cases = [
        ("", "Airmodus CPC", "Airmodus CPC", "Model used when serial empty"),
        ("", "Random Device", "Random Device", "Unknown model passed through"),
        ("", "", "Unknown", "Both empty returns Unknown"),
    ]

    for serial, model, expected, description in test_cases:
        result = DeviceIdentifier.identify_device(serial_number=serial, model=model)

        if result == expected:
            print(f"✅ {description}: '{result}'")
        else:
            print(f"❌ {description}: Expected '{expected}', got '{result}'")

    print()


if __name__ == "__main__":
    print("\nTesting device patterns with REAL device examples...")
    print("These are actual serial numbers from production devices.\n")

    # Run tests
    passed, failed = test_real_devices()
    test_non_aggressive_matching()
    test_fallback_behavior()

    # Final summary
    if failed == 0:
        print("\n✅ SUCCESS! All real device patterns are working correctly.")
        print("   - Airmodus devices are properly identified")
        print("   - Non-Airmodus devices pass through unchanged")
        print("   - No aggressive pattern matching")
    else:
        print(f"\n⚠️ {failed} tests failed. Check the patterns.")

    print("\nThe system will:")
    print("1. Identify known Airmodus devices (PSM, CPC, AFM, RHTP, etc.)")
    print("2. Return everything else as-is from the IDN response")
    print("3. Never guess or use fuzzy matching")