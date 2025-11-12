"""
Device identification patterns for automatic device type detection.

This module contains patterns and rules for identifying device types
based on serial numbers, manufacturer strings, and other characteristics.
"""

import re
from typing import Dict, List, Optional, Tuple


class DeviceIdentifier:
    """
    Device identification system using pattern matching.

    This class provides methods to identify device types based on:
    - Serial number patterns
    - Manufacturer strings
    - VID:PID combinations
    - Custom identification rules
    """

    # Serial number patterns for Airmodus devices
    # Each pattern is a tuple of (regex_pattern, device_type, confidence_score)
    SERIAL_PATTERNS = [
        # High-priority Airmodus patterns based on actual device serials
        # CPC patterns - actual device IDs
        (re.compile(r'^cpc_id_', re.IGNORECASE), 'CPC', 1.0),  # Custom CPC ID format
        (re.compile(r'^2[A-Z0-9]{8,}$', re.IGNORECASE), 'CPC', 0.95),  # Starts with 2, 8+ alphanum
        (re.compile(r'^A2[A-Z0-9]{8,}$', re.IGNORECASE), 'CPC', 0.95),  # Starts with A2, 8+ alphanum
        # Note: NOT adding '3' prefix to avoid TSI CPC conflict

        # PSM patterns - custom ID format
        (re.compile(r'^psm_id_', re.IGNORECASE), 'PSM Retrofit', 1.0),  # Generic PSM ID (defaulting to Retrofit)

        # RHTP patterns - custom ID and 7-digit format
        (re.compile(r'^rhtp_id_', re.IGNORECASE), 'RHTP', 1.0),  # Custom RHTP ID format
        (re.compile(r'^\d{7}$'), 'RHTP', 0.9),  # Exactly 7 digits

        # Legacy CPC patterns (reduced priority)
        (re.compile(r'^CPC\d+', re.IGNORECASE), 'CPC', 0.85),
        (re.compile(r'^A20-\d+', re.IGNORECASE), 'CPC', 0.8),
        (re.compile(r'^A10-\d+', re.IGNORECASE), 'CPC', 0.8),

        # PSM devices
        (re.compile(r'^PSM2[-_]\d+', re.IGNORECASE), 'PSM 2.0', 1.0),
        (re.compile(r'^PSM-2\d+', re.IGNORECASE), 'PSM 2.0', 1.0),
        (re.compile(r'^PSMR[-_]\d+', re.IGNORECASE), 'PSM Retrofit', 1.0),
        (re.compile(r'^PSM-R\d+', re.IGNORECASE), 'PSM Retrofit', 1.0),
        (re.compile(r'^PSM1[-_]\d+', re.IGNORECASE), 'PSM Retrofit', 0.9),

        # Electrometer
        (re.compile(r'^ELM[-_]\d+', re.IGNORECASE), 'Electrometer', 1.0),
        (re.compile(r'^ELEC[-_]\d+', re.IGNORECASE), 'Electrometer', 0.9),
        (re.compile(r'^EM[-_]\d+', re.IGNORECASE), 'Electrometer', 0.8),

        # CO2 sensors
        (re.compile(r'^CO2[-_]\d+', re.IGNORECASE), 'CO2 sensor', 1.0),
        (re.compile(r'^CDX[-_]\d+', re.IGNORECASE), 'CO2 sensor', 0.9),
        (re.compile(r'^CARBOSENSE', re.IGNORECASE), 'CO2 sensor', 0.9),

        # RHTP sensors
        (re.compile(r'^RHTP[-_]\d+', re.IGNORECASE), 'RHTP', 1.0),
        (re.compile(r'^RHT[-_]\d+', re.IGNORECASE), 'RHTP', 0.9),
        (re.compile(r'^HTP[-_]\d+', re.IGNORECASE), 'RHTP', 0.8),

        # Air Flow Meter
        (re.compile(r'^AFM[-_]\d+', re.IGNORECASE), 'AFM', 1.0),
        (re.compile(r'^AIRFLOW[-_]\d+', re.IGNORECASE), 'AFM', 0.9),

        # eDiluter
        (re.compile(r'^EDIL[-_]\d+', re.IGNORECASE), 'eDiluter', 1.0),
        (re.compile(r'^ED[-_]\d+', re.IGNORECASE), 'eDiluter', 0.9),
        (re.compile(r'^DILUTER[-_]\d+', re.IGNORECASE), 'eDiluter', 0.8),

        # TSI CPCs (third-party devices)
        (re.compile(r'^TSI[-_]?\d+', re.IGNORECASE), 'TSI CPC', 0.9),
        (re.compile(r'^3750', re.IGNORECASE), 'TSI CPC', 0.8),
        (re.compile(r'^3772', re.IGNORECASE), 'TSI CPC', 0.8),
        (re.compile(r'^3775', re.IGNORECASE), 'TSI CPC', 0.8),
        (re.compile(r'^3776', re.IGNORECASE), 'TSI CPC', 0.8),
    ]

    # Manufacturer-based identification
    MANUFACTURER_PATTERNS = {
        'Airmodus': {
            'default_type': 'CPC',
            'confidence': 0.7
        },
        'TSI': {
            'default_type': 'TSI CPC',
            'confidence': 0.8
        },
        'Carbosense': {
            'default_type': 'CO2 sensor',
            'confidence': 0.9
        },
    }

    # VID:PID based identification (USB vendor and product IDs)
    VID_PID_PATTERNS = {
        '0403:6001': {'type': 'FTDI Serial', 'confidence': 0.3},  # Generic FTDI
        '10C4:EA60': {'type': 'CP2102 Serial', 'confidence': 0.3},  # Generic CP2102
        # Add specific VID:PID for known devices as discovered
    }

    @classmethod
    def identify_device(cls, serial_number: str = "",
                       manufacturer: str = "",
                       vid_pid: str = "",
                       description: str = "") -> Tuple[str, float]:
        """
        Identify device type based on available information.

        Args:
            serial_number: Device serial number from IDN query
            manufacturer: Manufacturer string from USB descriptor
            vid_pid: USB VID:PID in format "XXXX:XXXX"
            description: Port description from system

        Returns:
            Tuple of (device_type, confidence_score)
            where confidence_score is between 0.0 and 1.0
        """
        best_match = ("Unknown", 0.0)

        # Check serial number patterns (highest priority)
        if serial_number:
            print(f"[DEBUG IDN] Pattern matching: Testing serial '{serial_number}' against patterns")
            for pattern, device_type, confidence in cls.SERIAL_PATTERNS:
                if pattern.match(serial_number):
                    print(f"[DEBUG IDN] Pattern matching: MATCHED pattern {pattern.pattern} -> {device_type} (confidence: {confidence})")
                    if confidence > best_match[1]:
                        best_match = (device_type, confidence)
                    # Return immediately if confidence is 1.0
                    if confidence >= 1.0:
                        return best_match

        # Check manufacturer patterns
        if manufacturer and best_match[1] < 0.9:
            manufacturer_upper = manufacturer.upper()
            for mfg_pattern, info in cls.MANUFACTURER_PATTERNS.items():
                if mfg_pattern.upper() in manufacturer_upper:
                    if info['confidence'] > best_match[1]:
                        best_match = (info['default_type'], info['confidence'])

        # Check VID:PID patterns (lowest priority)
        if vid_pid and best_match[1] < 0.5:
            if vid_pid in cls.VID_PID_PATTERNS:
                vid_info = cls.VID_PID_PATTERNS[vid_pid]
                if vid_info['confidence'] > best_match[1]:
                    best_match = (vid_info['type'], vid_info['confidence'])

        # Check description for hints (fallback)
        if description and best_match[1] < 0.5:
            desc_upper = description.upper()
            for pattern, device_type, confidence in cls.SERIAL_PATTERNS:
                # Try to match pattern against description too
                if pattern.search(desc_upper):
                    adjusted_confidence = confidence * 0.5  # Lower confidence for description matches
                    if adjusted_confidence > best_match[1]:
                        best_match = (device_type, adjusted_confidence)

        print(f"[DEBUG IDN] Pattern matching: Final result for '{serial_number}': {best_match[0]} (confidence: {best_match[1]})")
        return best_match

    @classmethod
    def add_custom_pattern(cls, pattern: str, device_type: str, confidence: float = 0.9):
        """
        Add a custom pattern for device identification.

        Args:
            pattern: Regular expression pattern
            device_type: Device type to assign when pattern matches
            confidence: Confidence score (0.0 to 1.0)
        """
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        cls.SERIAL_PATTERNS.append((compiled_pattern, device_type, confidence))

    @classmethod
    def get_all_device_types(cls) -> List[str]:
        """
        Get a list of all known device types.

        Returns:
            List of unique device type strings
        """
        device_types = set()

        # From serial patterns
        for _, device_type, _ in cls.SERIAL_PATTERNS:
            device_types.add(device_type)

        # From manufacturer patterns
        for info in cls.MANUFACTURER_PATTERNS.values():
            device_types.add(info['default_type'])

        return sorted(list(device_types))

    @classmethod
    def suggest_device_type(cls, partial_serial: str) -> Optional[str]:
        """
        Suggest a device type based on partial serial number (for auto-complete).

        Args:
            partial_serial: Partial serial number entered by user

        Returns:
            Suggested device type or None
        """
        if not partial_serial:
            return None

        # Check if any pattern would match the partial serial
        for pattern, device_type, confidence in cls.SERIAL_PATTERNS:
            if confidence >= 0.8:  # Only suggest high-confidence matches
                # Check if the partial serial could be the start of a match
                if pattern.pattern.startswith('^'):
                    # Pattern expects string to start with something
                    pattern_start = pattern.pattern[1:].split('\\d')[0].split('[-_]')[0]
                    if partial_serial.upper().startswith(pattern_start.upper()):
                        return device_type

        return None


# Legacy compatibility function
def detect_device_type_from_serial(serial_number: str) -> str:
    """
    Legacy function for device type detection.

    Args:
        serial_number: Device serial number

    Returns:
        Detected device type or "Unknown"
    """
    device_type, _ = DeviceIdentifier.identify_device(serial_number=serial_number)
    return device_type


# Configuration for learning mode (future enhancement)
class DevicePatternLearner:
    """
    Machine learning-based pattern discovery for unknown devices.
    This is a placeholder for future enhancement.
    """

    def __init__(self):
        self.unknown_devices = []  # Store unidentified devices
        self.user_classifications = {}  # Store user-provided classifications

    def record_unknown_device(self, serial_number: str, characteristics: dict):
        """Record an unknown device for later analysis."""
        self.unknown_devices.append({
            'serial_number': serial_number,
            'characteristics': characteristics,
            'timestamp': None  # Add timestamp in production
        })

    def learn_from_user_classification(self, serial_number: str, device_type: str):
        """Learn from user's manual classification."""
        self.user_classifications[serial_number] = device_type
        # In production, this could trigger pattern analysis
        # to find commonalities and suggest new patterns

    def suggest_new_patterns(self) -> List[Tuple[str, str, float]]:
        """
        Analyze classified devices to suggest new patterns.

        Returns:
            List of (pattern, device_type, confidence) tuples
        """
        # Placeholder for ML-based pattern discovery
        return []