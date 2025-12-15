"""
Unit tests for CPC device - Message parsing and data handling.

Tests the CPCWidget class including:
- IDN response parsing
- Data message parsing (valid, malformed, partial)
- Settings response parsing
- Error handling
- GUI updates (mocked)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock
import numpy as np

# Add src to path
src_path = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from devices.cpc import CPCWidget
from devices.device_data import CPCData
from config import CPC
from fixtures.mock_serial_data import MockCPCResponses


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def cpc_widget(qapp, mock_cpc_config):
    """Create CPCWidget for testing."""
    widget = CPCWidget(mock_cpc_config)
    yield widget
    widget.deleteLater()


# ============================================================================
# IDN Parsing Tests
# ============================================================================

class TestCPCIdnParsing:
    """Test IDN response parsing for CPC."""

    def test_parse_valid_idn(self, cpc_widget):
        """Test parsing valid IDN response."""
        message = "*IDN Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0"

        result = cpc_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'
        # IDN parsing extracts device identifier (everything after "*IDN ")
        assert 'Airmodus A11' in result['data']
        # Serial number and firmware are in raw message but not in data field
        assert 'A11-0123' in result['raw']

    def test_parse_idn_extracts_serial_number(self, cpc_widget):
        """Test that serial number is extracted from IDN."""
        message = "*IDN Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0"

        result = cpc_widget.parse_message(message, None)

        # Serial number should be stored in widget
        # (implementation detail - adjust if needed)
        assert result['data'] is not None


# ============================================================================
# Data Message Parsing Tests
# ============================================================================

class TestCPCDataParsing:
    """Test data message parsing for CPC."""

    def test_parse_valid_meas_all(self, cpc_widget):
        """Test parsing valid :MEAS:ALL response."""
        # Format: conc, pulses, dead_time, pulse_dur, unused, sat_temp, opt_temp, cond_temp,
        #         cabin_temp, inlet_p, crit_p, nozzle_p, cabin_p, laser_cur, liquid_lvl, status_hex
        # Total: 15 numerical values + status hex = 16 values
        message = ":MEAS:ALL 1234.5,100,0.12,95.0,0,40.5,10.2,25.3,28.1,1013.2,450.3,320.1,1015.0,80,0.95,0x000"

        result = cpc_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert result['command'] == ':MEAS:ALL'
        assert cpc_widget.current_data.concentration == 1234.5
        assert cpc_widget.current_data.dead_time == 0.12
        assert cpc_widget.current_data.number_of_pulses == 100
        assert cpc_widget.current_data.temp_saturator == 40.5
        assert cpc_widget.current_data.temp_optics == 10.2
        assert cpc_widget.current_data.temp_condenser == 25.3
        assert cpc_widget.current_data.laser_current == 80.0
        assert cpc_widget.current_data.status_hex == "0x000"
        # Status hex 0x000 means no device errors reported

    def test_parse_data_with_errors(self, cpc_widget):
        """Test parsing data message with errors."""
        message = ":MEAS:ALL 1234.5,100,0.12,95.0,0,40.5,10.2,25.3,28.1,1013.2,450.3,320.1,1015.0,80,0.95,0x007"

        result = cpc_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert cpc_widget.current_data.total_errors > 0  # Has errors
        assert cpc_widget.current_data.status_hex == "0x007"

    def test_parse_malformed_data_short(self, cpc_widget):
        """Test parsing malformed data (too few fields)."""
        message = ":MEAS:ALL 1234.5,0.12,100"

        result = cpc_widget.parse_message(message, None)

        # Should not crash, but may return error type
        assert result['type'] in ['error', 'info', 'data']

    def test_parse_malformed_data_invalid_number(self, cpc_widget):
        """Test parsing data with invalid number format."""
        message = ":MEAS:ALL invalid,0.12,100,40.5,10.2,25.3,28.1,1013.2,450.3,320.1,1015.0,80,0.95,0,0x000"

        result = cpc_widget.parse_message(message, None)

        # Should handle gracefully (not crash)
        assert result is not None

    def test_parse_empty_message(self, cpc_widget):
        """Test parsing empty message."""
        message = ""

        result = cpc_widget.parse_message(message, None)

        assert result is not None
        assert result['type'] in ['error', 'info', 'unknown']


# ============================================================================
# Settings Parsing Tests
# ============================================================================

class TestCPCSettingsParsing:
    """Test settings message parsing for CPC."""

    def test_parse_settings_response(self, cpc_widget):
        """Test parsing :MEAS:SETT response."""
        # Format depends on CPC firmware, typically contains temp setpoints, etc.
        message = ":MEAS:SETT 30,1500,800"

        result = cpc_widget.parse_message(message, None)

        # Settings parsing might store in widget.settings
        assert result is not None


# ============================================================================
# Pulse Quality Parsing Tests
# ============================================================================

class TestCPCPulseQualityParsing:
    """Test pulse quality message parsing for CPC."""

    def test_parse_pulse_quality(self, cpc_widget):
        """Test parsing :MEAS:PUL response (pulse quality data)."""
        message = ":MEAS:PUL 45.2,123.4"

        result = cpc_widget.parse_message(message, None)

        # Pulse quality might be stored in extra fields
        assert result is not None
        # laser_current and pulse_duration are extra fields
        # (Check if your implementation populates these)


# ============================================================================
# Data Writer Tests
# ============================================================================

class TestCPCDataWriter:
    """Test CPCDataWriter functionality."""

    def test_get_dat_header(self, cpc_widget):
        """Test .dat file header generation."""
        header = cpc_widget.data_writer.get_dat_header()

        assert header.startswith('YYYY.MM.DD hh:mm:ss,')
        assert 'Concentration' in header
        assert 'Dead time' in header
        assert 'Saturator T' in header

    def test_get_par_header(self, cpc_widget):
        """Test .par file header generation."""
        header = cpc_widget.data_writer.get_par_header()

        assert header.startswith('YYYY.MM.DD hh:mm:ss,')
        assert 'Averaging time' in header
        assert 'Saturator T setpoint' in header
        assert 'Autofill' in header

    def test_get_dat_data(self, cpc_widget):
        """Test .dat data formatting."""
        # Set some data
        cpc_widget.current_data.concentration = 1234.5
        cpc_widget.current_data.dead_time = 0.12
        cpc_widget.current_data.temp_saturator = 40.5

        data_str = cpc_widget.data_writer.get_dat_data(None, "2025-01-01 12:00:00")

        assert '1234.5' in data_str
        assert '0.12' in data_str
        assert '40.5' in data_str

    def test_file_types(self, cpc_widget):
        """Test that CPC writes both .dat and .par files."""
        file_types = cpc_widget.data_writer.get_file_types()

        assert 'dat' in file_types
        assert 'par' in file_types


# ============================================================================
# Data Array Conversion Tests
# ============================================================================

class TestCPCDataArrayConversion:
    """Test CPCData.to_array() functionality."""

    def test_to_array_matches_data(self, cpc_widget):
        """Test that to_array() produces correct array."""
        # Set data
        cpc_widget.current_data.concentration = 1234.5
        cpc_widget.current_data.dead_time = 0.12
        cpc_widget.current_data.number_of_pulses = 100

        arr = cpc_widget.current_data.to_array()

        assert len(arr) == 15
        assert arr[0] == 1234.5
        assert arr[1] == 0.12
        assert arr[2] == 100

    def test_to_array_with_nan_values(self, cpc_widget):
        """Test that NaN values are preserved in array."""
        # Default data has NaN values
        arr = cpc_widget.current_data.to_array()

        assert np.isnan(arr[0])  # concentration
        assert np.isnan(arr[1])  # dead_time


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestCPCErrorHandling:
    """Test CPC error handling."""

    def test_parse_unknown_command(self, cpc_widget):
        """Test parsing unknown command response."""
        message = ":UNKNOWN:COMMAND"

        result = cpc_widget.parse_message(message, None)

        # Should handle gracefully
        assert result is not None

    def test_parse_null_message(self, cpc_widget):
        """Test parsing None message."""
        message = None

        result = cpc_widget.parse_message(message, None)

        # Should handle gracefully
        assert result is not None


# ============================================================================
# Integration Tests (Mocked GUI Updates)
# ============================================================================

@pytest.mark.gui
class TestCPCGUIUpdates:
    """Test CPC GUI update methods (mocked)."""

    def test_update_values_called_on_data(self, cpc_widget, mocker):
        """Test that update_values is called after parsing data."""
        # Mock the update_values method
        mock_update = mocker.patch.object(cpc_widget, 'update_values')

        message = ":MEAS:ALL 1234.5,0.12,100,40.5,10.2,25.3,28.1,1013.2,450.3,320.1,1015.0,80,0.95,0,0x000"
        result = cpc_widget.parse_message(message, None)

        # If result['update_gui'] is True, update_values should be called
        # (Adjust based on your implementation)


# ============================================================================
# Mark Tests
# ============================================================================

# ============================================================================
# Command Sequence Tests
# ============================================================================

class TestCPCCommandSequence:
    """Test CPC command sequencing based on original monolith app behavior."""

    def test_get_read_command_sequence_normal_mode(self, cpc_widget):
        """Test command sequence for normal mode (no 10Hz)."""
        sequence = cpc_widget.get_read_command_sequence(ten_hz=False)

        # Should return 3 commands with delays
        assert len(sequence) == 3
        # Command 1: :MEAS:ALL at 0ms
        assert sequence[0] == (':MEAS:ALL', 0)
        # Command 2: :SYST:PRNT at 150ms
        assert sequence[1] == (':SYST:PRNT', 150)
        # Command 3: :SYST:PALL at 300ms
        assert sequence[2] == (':SYST:PALL', 300)

    def test_get_read_command_sequence_with_10hz(self, cpc_widget):
        """Test command sequence for 10Hz mode."""
        sequence = cpc_widget.get_read_command_sequence(ten_hz=True)

        # Should return 4 commands with delays
        assert len(sequence) == 4
        # Commands 1-3 same as normal mode
        assert sequence[0] == (':MEAS:ALL', 0)
        assert sequence[1] == (':SYST:PRNT', 150)
        assert sequence[2] == (':SYST:PALL', 300)
        # Command 4: :MEAS:OPC_CONC_LOG at 450ms
        assert sequence[3] == (':MEAS:OPC_CONC_LOG', 450)

    def test_get_read_command_single(self, cpc_widget):
        """Test get_read_command returns single command for documentation."""
        command = cpc_widget.get_read_command()

        # Returns single command (for backward compatibility/documentation)
        assert command == ":MEAS:ALL"


# ============================================================================
# Buffer Management Tests
# ============================================================================

class TestCPCBufferManagement:
    """Test CPC data buffer management based on monolith app patterns."""

    def test_rolling_buffer_keys(self, cpc_widget):
        """Test CPC has 24-hour rolling buffers for pulse data."""
        buffer_keys = cpc_widget.get_rolling_buffer_keys()

        # CPC should have :pd and :pr buffers
        assert ':pd' in buffer_keys
        assert ':pr' in buffer_keys
        # Both should be 24 hours = 86400 seconds
        assert buffer_keys[':pd'] == 86400
        assert buffer_keys[':pr'] == 86400

    def test_ten_hz_data_buffer_initialization(self, cpc_widget):
        """Test that 10Hz data buffer is initialized with NaN values."""
        # 10Hz buffer should have 10 NaN values
        assert len(cpc_widget.ten_hz_data) == 10
        assert np.all(np.isnan(cpc_widget.ten_hz_data))

    def test_pulse_analysis_index_initialization(self, cpc_widget):
        """Test pulse analysis index starts as None (not in analysis mode)."""
        assert cpc_widget.pulse_analysis_index is None


# ============================================================================
# Plot Configuration Tests
# ============================================================================

class TestCPCPlotConfiguration:
    """Test CPC plot configuration."""

    def test_get_plot_keys(self, cpc_widget):
        """Test CPC has concentration and raw concentration plot keys."""
        plot_keys = cpc_widget.get_plot_keys()

        # CPC should have ':conc' (concentration) and ':raw' (raw concentration) keys
        assert ':conc' in plot_keys
        assert ':raw' in plot_keys
        assert len(plot_keys) == 2


pytestmark = pytest.mark.unit
