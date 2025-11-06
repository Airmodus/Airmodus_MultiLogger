"""
Mock serial device responses for testing.

This module provides realistic serial communication responses for each device type,
matching the actual protocol format used by physical devices.
"""


class MockCPCResponses:
    """Mock responses for Airmodus CPC device."""

    IDN = b"*IDN Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0\r"

    FIRMWARE = b"FW:2.1.0\r"

    # Normal data response (all measurements)
    # Format: conc, pulses, dead_time, pulse_dur, unused, sat_temp, opt_temp, cond_temp,
    #         cabin_temp, inlet_p, crit_p, nozzle_p, cabin_p, laser_cur, liquid_lvl, status_hex
    DATA_NORMAL = b":MEAS:ALL 1234.5,100,0.12,95.0,0,40.5,10.2,25.3,28.1,1013.2,450.3,320.1,1015.0,80,0.95,0x000\r"

    # Data with errors
    DATA_WITH_ERRORS = b":MEAS:ALL 1234.5,100,0.12,95.0,0,40.5,10.2,25.3,28.1,1013.2,450.3,320.1,1015.0,80,0.95,0x007\r"

    # Malformed data (missing fields)
    DATA_MALFORMED = b":MEAS:ALL 1234.5,0.12,100\r"

    # Partial response (incomplete buffer)
    DATA_PARTIAL = b":MEAS:ALL 1234.5,0.12,100,40.5,10.2,"

    # Settings response
    SETTINGS = b":MEAS:SETT 30,1500,800\r"

    # Pulse quality analysis
    PULSE_QUALITY = b":MEAS:PUL 45.2,123.4\r"

    # Command acknowledgment
    ACK = b"OK\r"

    # Error response
    ERROR = b"ERROR: Invalid command\r"


class MockPSMResponses:
    """Mock responses for PSM device."""

    IDN_RETROFIT = b"*IDN Airmodus PSM 1.0,PSN:PSM-0456,FW:1.5.2\r"
    IDN_V2 = b"*IDN Airmodus PSM 2.0,PSN:PSM-0789,FW:2.0.1\r"

    FIRMWARE = b"FW:1.5.2\r"

    # Normal data response
    DATA_NORMAL = b":MEAS:ALL 1.0,0.3,0.7,90.0,25.0,40.0,0,0x000\r"

    # Data with errors
    DATA_WITH_ERRORS = b":MEAS:ALL 1.0,0.3,0.7,90.0,25.0,40.0,2,0x003\r"

    # Malformed data
    DATA_MALFORMED = b":MEAS:ALL 1.0,0.3\r"

    # Settings response
    SETTINGS = b":MEAS:SETT 90.0,1.0,0.3\r"

    ACK = b"OK\r"


class MockEDiluterResponses:
    """Mock responses for eDiluter device."""

    IDN = b"*IDN Airmodus eDiluter,PSN:ED-0321,FW:1.2.3\r"

    FIRMWARE = b"FW:1.2.3\r"

    # Normal data response
    DATA_NORMAL = b":MEAS:ALL 10.5,150.0,25.5,1013.2,0,0x000\r"

    # Data with errors
    DATA_WITH_ERRORS = b":MEAS:ALL 10.5,150.0,25.5,1013.2,1,0x001\r"

    # Malformed data
    DATA_MALFORMED = b":MEAS:ALL 10.5\r"

    # Settings response
    SETTINGS = b":MEAS:SETT 10.0,2.0\r"

    ACK = b"OK\r"


class MockRHTPResponses:
    """Mock responses for RHTP sensor (simple device)."""

    IDN = b"*IDN RHTP Sensor,PSN:RHTP-001,FW:1.0.0\r"

    # Auto-pushed data (simple numeric values)
    DATA_NORMAL = b"45.2,25.3,1013.25,12.8\r"  # RH%, Temp°C, Pressure mbar, Dew point°C

    # Malformed data
    DATA_MALFORMED = b"45.2,invalid,1013.25\r"

    # Partial data
    DATA_PARTIAL = b"45.2,25."


class MockCO2Responses:
    """Mock responses for CO2 sensor (simple device)."""

    IDN = b"*IDN CO2 Sensor,PSN:CO2-001,FW:1.0.0\r"

    # Auto-pushed data
    DATA_NORMAL = b"412.5\r"  # CO2 ppm

    # Malformed data
    DATA_MALFORMED = b"invalid\r"


class MockAFMResponses:
    """Mock responses for Air Flow Meter (simple device)."""

    IDN = b"*IDN Air Flow Meter,PSN:AFM-001,FW:1.0.0\r"

    # Auto-pushed data
    DATA_NORMAL = b"1.25,25.3,1013.2\r"  # Flow L/min, Temp°C, Pressure mbar

    # Malformed data
    DATA_MALFORMED = b"1.25,invalid\r"


class MockElectrometerResponses:
    """Mock responses for Electrometer (simple device)."""

    IDN = b"*IDN Electrometer,PSN:ELEC-001,FW:1.0.0\r"

    # Auto-pushed data
    DATA_NORMAL = b"123.45\r"  # Voltage mV

    # Malformed data
    DATA_MALFORMED = b"invalid\r"


class MockTSICPCResponses:
    """Mock responses for TSI CPC (simple device)."""

    IDN = b"*IDN TSI CPC 3776,PSN:TSI-001,FW:1.0.0\r"

    # Auto-pushed data
    DATA_NORMAL = b"5678.9\r"  # Concentration #/cc

    # Malformed data
    DATA_MALFORMED = b"invalid\r"


# ============================================================================
# Mock Response Sequences
# ============================================================================

class MockSerialSequence:
    """
    Helper class to simulate sequential responses from a serial device.

    Usage:
        seq = MockSerialSequence([
            MockCPCResponses.IDN,
            MockCPCResponses.FIRMWARE,
            MockCPCResponses.DATA_NORMAL,
        ])
        mock_serial.read_all = seq
    """

    def __init__(self, responses):
        """
        Initialize with list of responses.

        Args:
            responses: List of bytes objects to return in sequence
        """
        self.responses = responses
        self.index = 0

    def __call__(self, *args, **kwargs):
        """Return next response in sequence."""
        if self.index < len(self.responses):
            response = self.responses[self.index]
            self.index += 1
            return response
        return b""  # Empty after sequence exhausted

    def reset(self):
        """Reset sequence to beginning."""
        self.index = 0


class MockSerialCycle:
    """
    Helper class to simulate cyclic responses (e.g., repeated data messages).

    Usage:
        cycle = MockSerialCycle(MockCPCResponses.DATA_NORMAL)
        mock_serial.read_all = cycle
    """

    def __init__(self, response):
        """
        Initialize with response to repeat.

        Args:
            response: bytes object to return repeatedly
        """
        self.response = response

    def __call__(self, *args, **kwargs):
        """Return the same response every time."""
        return self.response


# ============================================================================
# Connection Simulation Helpers
# ============================================================================

def simulate_device_connection(device_type="CPC"):
    """
    Create a mock serial connection sequence for initial device connection.

    Returns:
        MockSerialSequence configured for device connection flow:
        1. IDN response
        2. Firmware response
        3. Subsequent data messages

    Args:
        device_type: One of "CPC", "PSM", "eDiluter", "RHTP", etc.
    """
    sequences = {
        "CPC": [
            MockCPCResponses.IDN,
            MockCPCResponses.FIRMWARE,
            MockCPCResponses.DATA_NORMAL,
            MockCPCResponses.DATA_NORMAL,
        ],
        "PSM": [
            MockPSMResponses.IDN_RETROFIT,
            MockPSMResponses.FIRMWARE,
            MockPSMResponses.DATA_NORMAL,
            MockPSMResponses.DATA_NORMAL,
        ],
        "PSM2": [
            MockPSMResponses.IDN_V2,
            MockPSMResponses.FIRMWARE,
            MockPSMResponses.DATA_NORMAL,
            MockPSMResponses.DATA_NORMAL,
        ],
        "eDiluter": [
            MockEDiluterResponses.IDN,
            MockEDiluterResponses.FIRMWARE,
            MockEDiluterResponses.DATA_NORMAL,
            MockEDiluterResponses.DATA_NORMAL,
        ],
        "RHTP": [
            MockRHTPResponses.IDN,
            MockRHTPResponses.DATA_NORMAL,
            MockRHTPResponses.DATA_NORMAL,
        ],
        "CO2": [
            MockCO2Responses.IDN,
            MockCO2Responses.DATA_NORMAL,
            MockCO2Responses.DATA_NORMAL,
        ],
    }

    return MockSerialSequence(sequences.get(device_type, []))
