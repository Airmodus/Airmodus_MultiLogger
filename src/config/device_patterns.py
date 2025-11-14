"""
Simple device identification for Airmodus devices.
"""

import re


class DeviceIdentifier:
    """Simple device identification - match our devices or show what device says."""

    # Only the patterns we actually need for our devices
    # Based on real device examples from production
    PATTERNS = {
        'PSM 2.0': [r'^8\d{8,10}$'],  # 8211445616 (10 digits starting with 8)
        'PSM Retrofit': [r'^9\d{6,7}$'],  # 9142501 (7-8 digits starting with 9)
        'CPC': [
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


# Legacy compatibility
def detect_device_type_from_serial(serial_number: str) -> str:
    return DeviceIdentifier.identify_device(serial_number=serial_number)