"""
Unit tests for device_patterns.py - Device identification and display name extraction.

Tests:
- Device type identification from serial numbers
- Display name extraction with proper formatting
- Nickname extraction for A30/A20 CPCs
- Unknown device handling
"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from device_patterns import DeviceIdentifier


class TestDeviceIdentification:
    """Test device type identification from serial numbers."""

    def test_psm_20_identification(self):
        """Test PSM 2.0 pattern matching (serials starting with 9)."""
        assert DeviceIdentifier.identify_device(serial_number="9142501") == "PSM 2.0"
        assert DeviceIdentifier.identify_device(serial_number="9123456") == "PSM 2.0"

    def test_psm_retrofit_identification(self):
        """Test PSM Retrofit pattern matching (serials starting with 8)."""
        assert DeviceIdentifier.identify_device(serial_number="8211445616") == "PSM Retrofit"
        assert DeviceIdentifier.identify_device(serial_number="8123456789") == "PSM Retrofit"

    def test_cpc_identification(self):
        """Test CPC pattern matching."""
        assert DeviceIdentifier.identify_device(serial_number="Z812001104") == "CPC"
        assert DeviceIdentifier.identify_device(serial_number="2812001104") == "CPC"
        assert DeviceIdentifier.identify_device(serial_number="3792508436") == "CPC"

    def test_a30_cpc_identification(self):
        """Test A30 CPC pattern matching with asterisk and space."""
        assert DeviceIdentifier.identify_device(serial_number="301* Jerry") == "A30 CPC"
        assert DeviceIdentifier.identify_device(serial_number="301 Jerry") == "A30 CPC"
        assert DeviceIdentifier.identify_device(serial_number="301*") == "A30 CPC"

    def test_a20_cpc_identification(self):
        """Test A20 CPC pattern matching with asterisk and space."""
        assert DeviceIdentifier.identify_device(serial_number="235* Peggy") == "A20 CPC"
        assert DeviceIdentifier.identify_device(serial_number="235 Peggy") == "A20 CPC"
        assert DeviceIdentifier.identify_device(serial_number="235*") == "A20 CPC"

    def test_rhtp_identification(self):
        """Test RHTP pattern matching."""
        assert DeviceIdentifier.identify_device(serial_number="2300001") == "RHTP"
        assert DeviceIdentifier.identify_device(serial_number="2312345") == "RHTP"

    def test_afm_identification(self):
        """Test AFM pattern matching."""
        assert DeviceIdentifier.identify_device(serial_number="AFM123") == "AFM"
        assert DeviceIdentifier.identify_device(serial_number="afm456") == "AFM"

    def test_electrometer_identification(self):
        """Test Electrometer pattern matching."""
        assert DeviceIdentifier.identify_device(serial_number="NewEMDAQ") == "Electrometer"
        assert DeviceIdentifier.identify_device(serial_number="Electrometer123") == "Electrometer"

    def test_unknown_device(self):
        """Test unknown device returns serial number."""
        assert DeviceIdentifier.identify_device(serial_number="1234567890") == "1234567890"
        assert DeviceIdentifier.identify_device(serial_number="XYZ999") == "XYZ999"


class TestDisplayNameExtraction:
    """Test display name extraction for Airmodus devices."""

    def test_a30_cpc_with_nickname(self):
        """Test A30 CPC with nickname 'Jerry'."""
        result = DeviceIdentifier.extract_display_name("301* Jerry", "A30 CPC")
        assert result == "Airmodus CPC Jerry"

    def test_a20_cpc_with_nickname(self):
        """Test A20 CPC with nickname 'Peggy'."""
        result = DeviceIdentifier.extract_display_name("235* Peggy", "A20 CPC")
        assert result == "Airmodus CPC Peggy"

    def test_a30_cpc_with_space_separator(self):
        """Test A30 CPC with space separator instead of asterisk."""
        result = DeviceIdentifier.extract_display_name("301 Jerry", "A30 CPC")
        assert result == "Airmodus CPC Jerry"

    def test_rhtp_with_suffix(self):
        """Test RHTP shows last 3 digits."""
        result = DeviceIdentifier.extract_display_name("2300001", "RHTP")
        assert result == "Airmodus RHTP [..001]"

    def test_psm_20_with_suffix(self):
        """Test PSM 2.0 shows last 3 digits (serials starting with 9)."""
        result = DeviceIdentifier.extract_display_name("9142501", "PSM 2.0")
        assert result == "Airmodus PSM 2.0 [..501]"

    def test_psm_retrofit_with_suffix(self):
        """Test PSM Retrofit shows last 3 digits (serials starting with 8)."""
        result = DeviceIdentifier.extract_display_name("8211445616", "PSM Retrofit")
        assert result == "Airmodus PSM Retrofit [..616]"

    def test_cpc_z_serial_with_suffix(self):
        """Test CPC with Z-prefix serial shows last 3 digits."""
        result = DeviceIdentifier.extract_display_name("Z812001104", "CPC")
        assert result == "Airmodus CPC [..104]"

    def test_cpc_numeric_serial_with_suffix(self):
        """Test CPC with numeric serial shows last 3 digits."""
        result = DeviceIdentifier.extract_display_name("2812001104", "CPC")
        assert result == "Airmodus CPC [..104]"

        result = DeviceIdentifier.extract_display_name("3792508436", "CPC")
        assert result == "Airmodus CPC [..436]"

    def test_unknown_device_returns_empty(self):
        """Test unknown devices return empty string."""
        result = DeviceIdentifier.extract_display_name("1234567890")
        assert result == ""

        result = DeviceIdentifier.extract_display_name("XYZ999", "XYZ999")
        assert result == ""

    def test_empty_serial_returns_empty(self):
        """Test empty serial returns empty string."""
        result = DeviceIdentifier.extract_display_name("")
        assert result == ""

    def test_auto_identify_device_type(self):
        """Test that device type is auto-identified if not provided."""
        result = DeviceIdentifier.extract_display_name("301* Jerry")
        assert result == "Airmodus CPC Jerry"

        result = DeviceIdentifier.extract_display_name("9142501")
        assert result == "Airmodus PSM 2.0 [..501]"

    def test_nickname_extraction_with_extra_spaces(self):
        """Test nickname extraction handles extra spaces."""
        result = DeviceIdentifier.extract_display_name("301*  Jerry  ", "A30 CPC")
        assert result == "Airmodus CPC Jerry"

        result = DeviceIdentifier.extract_display_name("235*   Peggy", "A20 CPC")
        assert result == "Airmodus CPC Peggy"

    def test_short_serial_no_crash(self):
        """Test that very short serials don't crash."""
        # Serials shorter than 3 chars get no suffix
        result = DeviceIdentifier.extract_display_name("12", "CPC")
        assert result == "Airmodus CPC"

        # Serials with 3+ chars get suffix
        result = DeviceIdentifier.extract_display_name("123", "CPC")
        assert result == "Airmodus CPC [..123]"

    def test_electrometer_with_suffix(self):
        """Test Electrometer shows proper name."""
        result = DeviceIdentifier.extract_display_name("NewEMDAQ", "Electrometer")
        assert result == "Airmodus Electrometer [..DAQ]"

    def test_afm_with_suffix(self):
        """Test AFM shows proper name."""
        result = DeviceIdentifier.extract_display_name("AFM12345", "AFM")
        assert result == "Airmodus AFM [..345]"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_none_values(self):
        """Test handling of None values."""
        result = DeviceIdentifier.extract_display_name(None)
        assert result == ""

    def test_device_type_unknown_string(self):
        """Test 'Unknown' device type returns empty."""
        result = DeviceIdentifier.extract_display_name("123456", "Unknown")
        assert result == ""

    def test_all_device_types_listed(self):
        """Test that all device types are accessible."""
        device_types = DeviceIdentifier.get_all_device_types()
        assert "PSM 2.0" in device_types
        assert "PSM Retrofit" in device_types
        assert "CPC" in device_types
        assert "A30 CPC" in device_types
        assert "A20 CPC" in device_types
        assert "RHTP" in device_types
        assert "AFM" in device_types
        assert "Electrometer" in device_types


class TestIntegerDeviceTypes:
    """Test that integer device type constants work correctly."""

    def test_cpc_with_integer_type(self):
        """Test CPC with integer device type constant (1)."""
        result = DeviceIdentifier.extract_display_name("Z812001104", 1)
        assert result == "Airmodus CPC [..104]"

    def test_psm_retrofit_with_integer_type(self):
        """Test PSM Retrofit with integer device type constant (2)."""
        result = DeviceIdentifier.extract_display_name("8211445616", 2)
        assert result == "Airmodus PSM Retrofit [..616]"

    def test_rhtp_with_integer_type(self):
        """Test RHTP with integer device type constant (5)."""
        result = DeviceIdentifier.extract_display_name("2300001", 5)
        assert result == "Airmodus RHTP [..001]"

    def test_psm2_with_integer_type(self):
        """Test PSM 2.0 with integer device type constant (7)."""
        result = DeviceIdentifier.extract_display_name("9142501", 7)
        assert result == "Airmodus PSM 2.0 [..501]"

    def test_electrometer_with_integer_type(self):
        """Test Electrometer with integer device type constant (3)."""
        result = DeviceIdentifier.extract_display_name("NewEMDAQ", 3)
        assert result == "Airmodus Electrometer [..DAQ]"

    def test_afm_with_integer_type(self):
        """Test AFM with integer device type constant (9)."""
        result = DeviceIdentifier.extract_display_name("AFM12345", 9)
        assert result == "Airmodus AFM [..345]"

    def test_unknown_integer_type(self):
        """Test unknown integer device type returns empty."""
        result = DeviceIdentifier.extract_display_name("123456", 999)
        assert result == ""

    def test_string_type_still_works(self):
        """Test that string device types still work after adding int support."""
        result = DeviceIdentifier.extract_display_name("2300001", "RHTP")
        assert result == "Airmodus RHTP [..001]"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
