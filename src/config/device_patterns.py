"""
Simple device identification for Airmodus devices.
"""

import re


class DeviceIdentifier:
    """Simple device identification - match our devices or show what device says."""

    # Only the patterns we actually need for our devices
    PATTERNS = {
        'PSM 2.0': [r'^8\d{8}$'],  # 821445616
        'PSM Retrofit': [r'^9\d{6}$'],  # 9142501
        'CPC': [r'^2\d{9}$', r'^3\d{9}$'],  # 2812001104, 3792508436
        'Electrometer': [r'NewEMDAQ'],  # NewEMDAQ
        'RHTP': [r'^2300001$'],  # Exact match for 2300001
        'A30 CPC': [r'^301.*Jerry$'],  # 301* Jerry (must end with Jerry)
        'A20 CPC': [r'^235.*Peggy$'],  # 235* Peggy (must end with Peggy)
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