"""
Simple device identification for Airmodus devices.
"""

import re
from typing import Union, Optional


# Mapping from device type integer constants to string names
# Kept in sync with data_holder.py device_names
# Note: PSM 2.0 (7) kept for backwards compatibility with existing configs
DEVICE_TYPE_NAMES = {
    1: 'CPC',
    2: 'PSM',  # User sees just "PSM", version detected from firmware
    3: 'Electrometer',
    4: 'CO2 sensor',
    5: 'RHTP',
    6: 'eDiluter',
    7: 'PSM',  # PSM 2.0 - maps to same "PSM" for backwards compatibility
    8: 'TSI CPC',
    9: 'AFM',
    -1: 'Example device'
}


class DeviceIdentifier:
    """Simple device identification - match our devices or show what device says."""

    # Only the patterns we actually need for our devices
    # Based on real device examples from production
    # Note: PSM patterns combined - version (2.0/Retrofit) determined by firmware
    PATTERNS = {
        'PSM': [
            r'^9\d{6,7}$',   # PSM 2.0 serial: 9142501 (7-8 digits starting with 9)
            r'^8\d{8,10}$',  # PSM Retrofit serial: 8211445616 (10 digits starting with 8)
        ],
        'CPC': [
            r'^Z812',  # Z812001104 (starts with Z812)
            r'^2\d{9}$',  # 2812001104 (10 digits starting with 2)
            r'^3\d{9}$',  # 3792508436 (10 digits starting with 3)
        ],
        'A30 CPC': [
            r'^301\*',  # Starts with "301*" (e.g., "301* Jerry")
            r'^301\s',  # Or "301 " with space
        ],
        'A20 CPC': [
            r'^235\*',  # Starts with "235*" (e.g., "235* Peggy")
            r'^235\s',  # Or "235 " with space
        ],
        'AFM': [
            r'(?i)AFM',  # Contains "AFM" (case insensitive)
        ],
        'RHTP': [
            r'^2300001$',  # Exact ID: 2300001
            r'^23\d{5}$',  # Or any 7 digits starting with 23
            r'(?i)RHTP',  # Or contains "RHTP"
        ],
        'Electrometer': [
            r'(?i)NewEMDAQ',  # Contains "NewEMDAQ" (case insensitive)
            r'(?i)Electrometer',  # Or contains "Electrometer"
        ],
    }

    @classmethod
    def identify_device(cls, serial_number: str = "", model: str = "", **kwargs) -> str:
        """
        Match our patterns or return what the device says. That's it.

        Args:
            serial_number: Device serial
            model: Device model name
            **kwargs: Ignored

        Returns:
            Device type or device's own name
        """
        # Check our patterns
        if serial_number:
            for device_type, patterns in cls.PATTERNS.items():
                for pattern in patterns:
                    if re.match(pattern, serial_number, re.IGNORECASE):
                        return device_type

        # Not our device? Show what it says
        if serial_number:
            return serial_number
        if model:
            return model
        return "Unknown"

    @classmethod
    def get_all_device_types(cls):
        """Get list of our device types."""
        return list(cls.PATTERNS.keys())

    @classmethod
    def extract_display_name(cls, serial_number: str, device_type: Union[str, int, None] = None) -> str:
        """
        Extract a display name from serial number for Airmodus devices.

        Format: "Airmodus [Device Type] [Nickname] [..last3-4digits]"

        Examples:
            "301* Jerry" -> "Airmodus CPC Jerry"
            "235* Peggy" -> "Airmodus CPC Peggy"
            "2300001" -> "Airmodus RHTP [..001]"
            "9142501" -> "Airmodus PSM [..501]"
            "8211445616" -> "Airmodus PSM [..616]"
            "Z812001104" -> "Airmodus CPC [..104]"
            "unknown123" -> "" (empty, show raw serial instead)

        Args:
            serial_number: Device serial number
            device_type: Optional pre-identified device type (can be string name or integer constant)

        Returns:
            Formatted display name or empty string for unknown devices
        """
        if not serial_number:
            return ""

        # Convert integer device type to string name
        if isinstance(device_type, int):
            device_type = DEVICE_TYPE_NAMES.get(device_type)
            if not device_type:
                # Unknown device type integer, return empty
                return ""

        # Identify device type if not provided
        if not device_type:
            device_type = cls.identify_device(serial_number=serial_number)

        # If device type is just the serial number, it's unknown - return empty
        if device_type == serial_number or device_type == "Unknown":
            return ""

        # Extract nickname for A30/A20 CPCs (e.g., "301* Jerry" -> "Jerry")
        nickname = ""
        if re.match(r'^(301|235)[\*\s]', serial_number):
            # Extract everything after "301*" or "235*" or "301 " or "235 "
            match = re.match(r'^(?:301|235)[\*\s]\s*(.+)', serial_number)
            if match:
                nickname = match.group(1).strip()

        # Extract last 3-4 digits for suffix
        # For serials with nickname (301* Jerry), use the prefix digits
        suffix = ""
        if nickname:
            # For nicknamed devices, don't add suffix - name is unique enough
            pass
        else:
            # Extract last 3-4 characters from serial
            if len(serial_number) >= 3:
                suffix = f" [..{serial_number[-3:]}]"

        # Build display name
        parts = ["Airmodus"]

        # Add device type (normalize "A30 CPC" and "A20 CPC" to just "CPC")
        if device_type in ['A30 CPC', 'A20 CPC']:
            parts.append('CPC')
        else:
            parts.append(device_type)

        # Add nickname if present
        if nickname:
            parts.append(nickname)

        # Add suffix if present
        if suffix:
            display_name = ' '.join(parts) + suffix
        else:
            display_name = ' '.join(parts)

        return display_name


# Legacy compatibility
def detect_device_type_from_serial(serial_number: str) -> str:
    return DeviceIdentifier.identify_device(serial_number=serial_number)