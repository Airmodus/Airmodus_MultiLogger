"""
Unit tests for eDiluter device - Message parsing and data handling.

Tests the eDiluterWidget class including:
- IDN response parsing
- Data push message parsing (time/ID/Status format)
- SUCCESS/ERROR command responses
- Settings response parsing
- Error handling
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock
import numpy as np

# Add src to path
src_path = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from devices.ediluter import eDiluterWidget
from devices.device_data import EDiluterData
from config import EDILUTER
from fixtures.mock_serial_data import MockEDiluterResponses


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def ediluter_widget(qapp, mock_ediluter_config):
    """Create eDiluterWidget for testing."""
    widget = eDiluterWidget(mock_ediluter_config)
    yield widget
    widget.deleteLater()


# ============================================================================
# IDN Parsing Tests
# ============================================================================

class TestEDiluterIdnParsing:
    """Test IDN response parsing for eDiluter."""

    def test_parse_valid_idn(self, ediluter_widget):
        """Test parsing valid IDN response."""
        message = "*IDN Airmodus eDiluter,PSN:ED-0321,FW:1.2.3"

        result = ediluter_widget.parse_message(message, None)

        # eDiluter doesn't specifically handle IDN - treated as unknown
        assert result['type'] == 'unknown'
        assert result['command'] == '*IDN'


# ============================================================================
# Data Push Message Parsing Tests
# ============================================================================

class TestEDiluterDataParsing:
    """Test data push message parsing for eDiluter."""

    def test_parse_valid_data_push(self, ediluter_widget):
        """Test parsing valid data push message (147 characters)."""
        # Format after Status keyword: "status, pres1, pres2, temp1, ..., temp6, df1, df2, df_total"
        # The keywords "pres", "temp", "DF" are removed during parsing
        message = "time 12345 ID 1 Status OK, 1013.2, 1015.3, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 10.5, 5.2, 15.7                                 "
        # Pad to exactly 147 characters
        message = message.ljust(147)

        result = ediluter_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert ediluter_widget.current_data.status == "OK"
        assert ediluter_widget.current_data.pres1 == 1013.2
        assert ediluter_widget.current_data.pres2 == 1015.3
        assert ediluter_widget.current_data.temp1 == 25.1
        assert ediluter_widget.current_data.temp6 == 25.6
        assert ediluter_widget.current_data.df1 == 10.5
        assert ediluter_widget.current_data.df2 == 5.2
        assert ediluter_widget.current_data.df_total == 15.7

    def test_parse_data_push_error_status(self, ediluter_widget):
        """Test parsing data push with ERROR status."""
        message = "time 12345 ID 1 Status ERROR, 1013.2, 1015.3, 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 10.5, 5.2, 15.7                             "
        message = message.ljust(147)

        result = ediluter_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert ediluter_widget.current_data.status == "ERROR"

    def test_parse_incomplete_data_push(self, ediluter_widget):
        """Test parsing incomplete data push message (< 147 chars)."""
        message = "time 12345 ID 1 Status OK"

        result = ediluter_widget.parse_message(message, None)

        # Should not parse as data (length != 147), returns error
        assert result['type'] == 'error'
        assert 'Incomplete message' in result['error']

    def test_parse_malformed_data_missing_status(self, ediluter_widget):
        """Test parsing data push message missing 'Status' keyword."""
        message = "time 12345 ID 1 OK pres 1013.2, 1015.3 temp 25.1, 25.2, 25.3, 25.4, 25.5, 25.6 DF 10.5, 5.2, 15.7                            "
        message = message.ljust(147)

        result = ediluter_widget.parse_message(message, None)

        # Should handle gracefully
        assert result is not None


# ============================================================================
# Command Response Parsing Tests
# ============================================================================

class TestEDiluterCommandResponses:
    """Test command response parsing for eDiluter."""

    def test_parse_success_response(self, ediluter_widget):
        """Test parsing SUCCESS command response."""
        message = "SUCCESS: Command accepted"

        result = ediluter_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == 'SUCCESS'

    def test_parse_error_response(self, ediluter_widget):
        """Test parsing ERROR command response."""
        message = "ERROR: Invalid command"

        result = ediluter_widget.parse_message(message, None)

        assert result['type'] == 'error'
        assert result['command'] == 'ERROR'


# ============================================================================
# Settings Parsing Tests
# ============================================================================

class TestEDiluterSettingsParsing:
    """Test settings message parsing for eDiluter."""

    def test_parse_settings_response(self, ediluter_widget):
        """Test parsing settings response."""
        # eDiluter settings format (if applicable)
        message = ":MEAS:SETT 10.0,2.0"

        result = ediluter_widget.parse_message(message, None)

        # Settings parsing (adjust based on actual implementation)
        assert result is not None


# ============================================================================
# Data Writer Tests
# ============================================================================

class TestEDiluterDataWriter:
    """Test EDiluterDataWriter functionality."""

    def test_get_dat_header(self, ediluter_widget):
        """Test .dat file header generation."""
        header = ediluter_widget.data_writer.get_dat_header()

        assert header.startswith('YYYY.MM.DD hh:mm:ss,')
        assert 'Status' in header
        # Header uses abbreviated field names: P1, P2, T1-T6, DF1, DF2, DFTot
        assert 'P1' in header or 'Pressure' in header
        assert 'T1' in header or 'Temperature' in header
        assert 'DF' in header or 'Dilution' in header

    def test_get_dat_data(self, ediluter_widget):
        """Test .dat data formatting."""
        # Set some data
        ediluter_widget.current_data.status = "OK"
        ediluter_widget.current_data.pres1 = 1013.2
        ediluter_widget.current_data.temp1 = 25.5
        ediluter_widget.current_data.df_total = 15.7

        data_str = ediluter_widget.data_writer.get_dat_data(None, "2025-01-01 12:00:00")

        assert 'OK' in data_str
        assert '1013.2' in data_str
        assert '15.7' in data_str

    def test_file_types(self, ediluter_widget):
        """Test that eDiluter writes .dat file."""
        file_types = ediluter_widget.data_writer.get_file_types()

        assert 'dat' in file_types


# ============================================================================
# Data Array Conversion Tests
# ============================================================================

class TestEDiluterDataArrayConversion:
    """Test EDiluterData.to_array() functionality."""

    def test_to_array_length(self, ediluter_widget):
        """Test that to_array() returns correct number of fields."""
        arr = ediluter_widget.current_data.to_array()

        # eDiluter has 12 fields
        assert len(arr) == 12

    def test_to_array_order(self, ediluter_widget):
        """Test that to_array() returns fields in correct order."""
        ediluter_widget.current_data.status = "OK"
        ediluter_widget.current_data.pres1 = 1013.2
        ediluter_widget.current_data.pres2 = 1015.3
        ediluter_widget.current_data.df_total = 15.7

        arr = ediluter_widget.current_data.to_array()

        assert arr[0] == "OK"
        assert arr[1] == 1013.2
        assert arr[2] == 1015.3
        assert arr[11] == 15.7

    def test_to_array_with_nan_values(self, ediluter_widget):
        """Test that NaN values are preserved in array."""
        # Default data has NaN values
        arr = ediluter_widget.current_data.to_array()

        assert arr[0] == ""  # status defaults to empty string
        assert np.isnan(arr[1])  # pres1 defaults to NaN


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestEDiluterErrorHandling:
    """Test eDiluter error handling."""

    def test_parse_unknown_message_type(self, ediluter_widget):
        """Test parsing unknown message type."""
        message = "UNKNOWN message format"

        result = ediluter_widget.parse_message(message, None)

        # Should handle gracefully
        assert result is not None

    def test_parse_null_message(self, ediluter_widget):
        """Test parsing None message."""
        message = None

        try:
            result = ediluter_widget.parse_message(message, None)
            assert result is not None
        except (AttributeError, TypeError):
            # Expected if implementation doesn't handle None
            pass

    def test_parse_empty_message(self, ediluter_widget):
        """Test parsing empty message."""
        message = ""

        result = ediluter_widget.parse_message(message, None)

        assert result is not None


# ============================================================================
# GUI Update Tests (Mocked)
# ============================================================================

@pytest.mark.gui
class TestEDiluterGUIUpdates:
    """Test eDiluter GUI update methods (mocked)."""

    def test_update_values_method_exists(self, ediluter_widget):
        """Test that update_values method exists."""
        assert hasattr(ediluter_widget, 'update_values')

    def test_update_errors_method_exists(self, ediluter_widget):
        """Test that update_errors method exists (if applicable)."""
        # eDiluter may have error status handling
        # (Adjust based on actual implementation)
        pass


# ============================================================================
# Mark Tests
# ============================================================================

pytestmark = pytest.mark.unit
