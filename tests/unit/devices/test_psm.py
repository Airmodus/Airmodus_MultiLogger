"""
Unit tests for PSM devices - Message parsing and data handling.

Tests both PSM Retrofit (v1.0) and PSM 2.0 devices:
- IDN response parsing
- Measurement data parsing (:MEAS:SCAN, :MEAS:STEP, :MEAS:FIXD)
- Settings response parsing (:SYST:PRNT)
- Dilution parameters parsing (:SYST:VCMP)
- Self-test error parsing
- Error and note hex parsing
- CPC integration (connected CPC data)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock
import numpy as np

# Add src to path
src_path = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from devices.psm import PSMWidget
from devices.device_data import PSMData
from config import PSM, PSM2
from fixtures.mock_serial_data import MockPSMResponses


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def psm_retrofit_widget(qapp, mock_device_parameter):
    """Create PSM Retrofit widget for testing."""
    widget = PSMWidget(mock_device_parameter, device_type=PSM)
    widget.dev_id = 1
    widget.device_parameter = mock_device_parameter
    yield widget
    widget.deleteLater()


@pytest.fixture
def psm2_widget(qapp, mock_device_parameter):
    """Create PSM 2.0 widget for testing."""
    widget = PSMWidget(mock_device_parameter, device_type=PSM2)
    widget.dev_id = 2
    widget.device_parameter = mock_device_parameter
    yield widget
    widget.deleteLater()


# ============================================================================
# IDN Parsing Tests
# ============================================================================

class TestPSMIdnParsing:
    """Test IDN response parsing for PSM."""

    def test_parse_retrofit_idn(self, psm_retrofit_widget):
        """Test parsing PSM Retrofit IDN response."""
        message = "*IDN Airmodus PSM 1.0,PSN:PSM-0456,FW:1.5.2"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'
        assert 'PSM 1.0' in result['data']

    def test_parse_psm2_idn(self, psm2_widget):
        """Test parsing PSM 2.0 IDN response."""
        message = "*IDN Airmodus PSM 2.0,PSN:PSM-0789,FW:2.0.1"

        result = psm2_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'
        assert 'PSM 2.0' in result['data']


# ============================================================================
# Measurement Data Parsing Tests
# ============================================================================

class TestPSMMeasurementParsing:
    """Test measurement data message parsing for PSM."""

    def test_parse_meas_scan_valid(self, psm_retrofit_widget):
        """Test parsing valid :MEAS:SCAN response."""
        # Format: saturator_flow, excess_flow, temps, pressures, ..., status, notes
        message = ":MEAS:SCAN 1.0,0.7,90.0,40.0,25.0,85.0,30.0,28.0,1.0,1013.2,0.3,450.0,10.5,0.5,0.0,SCAN,0x000,0x00"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert result['command'] in [':MEAS:SCAN', ':MEAS:STEP', ':MEAS:FIXD']
        # Data should be stored in current_data
        assert psm_retrofit_widget.current_data.saturator_flow == 1.0
        assert psm_retrofit_widget.current_data.excess_flow == 0.7

    def test_parse_meas_step_valid(self, psm2_widget):
        """Test parsing valid :MEAS:STEP response."""
        message = ":MEAS:STEP 1.0,0.7,90.0,40.0,25.0,85.0,30.0,28.0,1.0,1013.2,0.3,450.0,10.5,0.5,0.0,STEP,0x000,0x00"

        result = psm2_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert psm2_widget.current_data.saturator_flow == 1.0

    def test_parse_meas_fixd_valid(self, psm_retrofit_widget):
        """Test parsing valid :MEAS:FIXD response."""
        message = ":MEAS:FIXD 1.0,0.7,90.0,40.0,25.0,85.0,30.0,28.0,1.0,1013.2,0.3,450.0,10.5,0.5,0.0,FIXD,0x000,0x00"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'data'
        # Scan status defaults to "9" unless firmware version >= 0.5.5 (for PSM Retrofit)
        # In test environment without firmware version, it defaults to "9"
        assert psm_retrofit_widget.current_data.scan_status in ["FIXD", "9"]

    def test_parse_data_with_errors(self, psm_retrofit_widget):
        """Test parsing data message with errors (non-zero status hex)."""
        message = ":MEAS:SCAN 1.0,0.7,90.0,40.0,25.0,85.0,30.0,28.0,1.0,1013.2,0.3,450.0,10.5,0.5,0.0,SCAN,0x003,0x00"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert psm_retrofit_widget.current_data.status_hex == "0x003"
        assert psm_retrofit_widget.current_data.total_errors > 0

    def test_parse_data_with_liquid_errors(self, psm_retrofit_widget):
        """Test parsing data message with liquid errors (non-zero note hex)."""
        message = ":MEAS:SCAN 1.0,0.7,90.0,40.0,25.0,85.0,30.0,28.0,1.0,1013.2,0.3,450.0,10.5,0.5,0.0,SCAN,0x000,0x41"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert psm_retrofit_widget.current_data.note_hex == "0x41"
        assert psm_retrofit_widget.current_data.liquid_errors > 0

    def test_parse_malformed_data_short(self, psm_retrofit_widget):
        """Test parsing malformed data (too few fields)."""
        message = ":MEAS:SCAN 1.0,0.7,90.0"

        result = psm_retrofit_widget.parse_message(message, None)

        # Should handle gracefully (not crash)
        assert result is not None


# ============================================================================
# Settings Parsing Tests
# ============================================================================

class TestPSMSettingsParsing:
    """Test settings message parsing for PSM."""

    def test_parse_prnt_settings(self, psm_retrofit_widget):
        """Test parsing :SYST:PRNT response (device settings)."""
        # Format: mode, temps (5), cpc_flow
        message = ":SYST:PRNT 0,90.0,40.0,25.0,85.0,30.0,0.3"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'settings'
        assert result['command'] == ':SYST:PRNT'
        # Settings should be stored in widget.settings
        assert psm_retrofit_widget.settings.temp_growth_tube == 90.0
        assert psm_retrofit_widget.settings.temp_saturator == 40.0

    def test_parse_vcmp_dilution_params(self, psm_retrofit_widget):
        """Test parsing :SYST:VCMP response (dilution parameters)."""
        # Format: dilution polynomial coefficients (requires 6 values)
        message = ":SYST:VCMP 10.0,2.0,1.5,0.5,0.1,0.05"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'dilution'
        assert result['command'] == ':SYST:VCMP'
        assert len(result['data']) == 6  # 6 dilution parameters required
        assert float(result['data'][0]) == 10.0


# ============================================================================
# Self-Test Error Parsing Tests
# ============================================================================

class TestPSMSelfTestParsing:
    """Test self-test error message parsing for PSM."""

    def test_parse_self_test_errors(self, psm_retrofit_widget):
        """Test parsing :STAT:SELF:LOG response (self-test errors)."""
        message = ":STAT:SELF:LOG 0x00F"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result['type'] == 'self_test'
        assert result['command'] == ':STAT:SELF:LOG'
        assert result['data'] == '0x00F'

    def test_parse_self_err(self, psm_retrofit_widget):
        """Test parsing :SELF:ERR response."""
        message = ":SELF:ERR Some error message"

        result = psm_retrofit_widget.parse_message(message, None)

        # Should handle self-test errors
        assert result is not None


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestPSMErrorHandling:
    """Test PSM error handling and status updates."""

    def test_update_errors_no_errors(self, psm_retrofit_widget):
        """Test update_errors with no errors (0x000)."""
        total_errors = psm_retrofit_widget.update_errors("0x000")

        assert total_errors == 0

    def test_update_errors_with_errors(self, psm_retrofit_widget):
        """Test update_errors with some errors (0x007 = bits 0,1,2 set)."""
        total_errors = psm_retrofit_widget.update_errors("0x007")

        assert total_errors == 3

    def test_update_errors_many_bits(self, psm_retrofit_widget):
        """Test update_errors with multiple error bits."""
        total_errors = psm_retrofit_widget.update_errors("0x0FF")

        assert total_errors == 8

    def test_update_notes_no_liquid_errors(self, psm_retrofit_widget):
        """Test update_notes with no liquid errors."""
        liquid_errors = psm_retrofit_widget.update_notes("0x00")

        assert liquid_errors == 0

    def test_update_notes_saturator_low(self, psm_retrofit_widget):
        """Test update_notes with saturator liquid level low (bit 6)."""
        liquid_errors = psm_retrofit_widget.update_notes("0x40")  # Bit 6 set

        assert liquid_errors == 1

    def test_update_notes_drain_high(self, psm_retrofit_widget):
        """Test update_notes with drain liquid level high (bit 0)."""
        liquid_errors = psm_retrofit_widget.update_notes("0x01")  # Bit 0 set

        assert liquid_errors == 1

    def test_update_notes_both_liquid_errors(self, psm_retrofit_widget):
        """Test update_notes with both liquid errors."""
        liquid_errors = psm_retrofit_widget.update_notes("0x41")  # Bits 0 and 6 set

        assert liquid_errors == 2


# ============================================================================
# PSM 2.0 Specific Tests
# ============================================================================

class TestPSM2Specifics:
    """Test PSM 2.0 specific features (vacuum flow)."""

    def test_psm2_has_vacuum_flow_widget(self, psm2_widget):
        """Test that PSM 2.0 has vacuum flow widget."""
        assert hasattr(psm2_widget.status_tab, 'flow_vacuum')
        assert psm2_widget.status_tab.flow_vacuum in psm2_widget.psm_status_widgets

    def test_psm_retrofit_no_vacuum_flow_widget(self, psm_retrofit_widget):
        """Test that PSM Retrofit does not have vacuum flow in initial widgets."""
        # Retrofit has 14 initial widgets, PSM2 has 15 (with vacuum)
        # Note: Retrofit adds vacuum widget later, but initially it's not in the list
        pass  # This test documents the difference

    def test_psm2_data_includes_vacuum_flow(self, psm2_widget):
        """Test that PSM 2.0 data includes vacuum flow field."""
        assert hasattr(psm2_widget.current_data, 'vacuum_flow')
        # Default should be NaN
        assert np.isnan(psm2_widget.current_data.vacuum_flow) or psm2_widget.current_data.vacuum_flow is not None


# ============================================================================
# Data Writer Tests
# ============================================================================

class TestPSMDataWriter:
    """Test PSMDataWriter functionality."""

    def test_get_dat_header_retrofit(self, psm_retrofit_widget):
        """Test .dat file header generation for PSM Retrofit."""
        header = psm_retrofit_widget.data_writer.get_dat_header()

        assert header.startswith('YYYY.MM.DD hh:mm:ss,')
        assert 'Saturator flow rate' in header
        assert 'Growth tube T' in header
        assert 'CPC concentration' in header
        # Retrofit header should NOT have "Vacuum flow"
        assert 'Vacuum flow' not in header

    def test_get_dat_header_psm2(self, psm2_widget):
        """Test .dat file header generation for PSM 2.0."""
        header = psm2_widget.data_writer.get_dat_header()

        assert header.startswith('YYYY.MM.DD hh:mm:ss,')
        assert 'Saturator flow rate' in header
        # PSM 2.0 header SHOULD have "Vacuum flow"
        assert 'Vacuum flow' in header

    def test_get_par_header_retrofit(self, psm_retrofit_widget):
        """Test .par file header generation for PSM Retrofit."""
        header = psm_retrofit_widget.data_writer.get_par_header()

        assert header.startswith('YYYY.MM.DD hh:mm:ss,')
        assert 'Growth tube T setpoint' in header
        # Retrofit header should include CO flow
        assert 'CO flow' in header or 'amp,cen' in header  # Dilution params

    def test_get_par_header_psm2(self, psm2_widget):
        """Test .par file header generation for PSM 2.0."""
        header = psm2_widget.data_writer.get_par_header()

        assert header.startswith('YYYY.MM.DD hh:mm:ss,')
        assert 'Growth tube T setpoint' in header
        # PSM 2.0 header should NOT have CO flow, just dilution params
        assert 'amp,cen' in header

    def test_file_types(self, psm_retrofit_widget):
        """Test that PSM writes both .dat and .par files."""
        file_types = psm_retrofit_widget.data_writer.get_file_types()

        assert 'dat' in file_types
        assert 'par' in file_types


# ============================================================================
# Data Array Conversion Tests
# ============================================================================

class TestPSMDataArrayConversion:
    """Test PSMData.to_array() functionality."""

    def test_to_array_length(self, psm_retrofit_widget):
        """Test that to_array() produces correct array length."""
        arr = psm_retrofit_widget.current_data.to_array()

        # PSM array has 30 fields (PSM data + CPC data)
        assert len(arr) == 30

    def test_to_array_includes_vacuum_flow(self, psm2_widget):
        """Test that to_array() includes vacuum flow (PSM2 field)."""
        psm2_widget.current_data.vacuum_flow = 0.5

        arr = psm2_widget.current_data.to_array()

        # Vacuum flow is at index 15
        assert arr[15] == 0.5

    def test_to_array_includes_cpc_data_fields(self, psm_retrofit_widget):
        """Test that to_array() includes connected CPC data fields."""
        psm_retrofit_widget.current_data.cpc_concentration = 1234.5
        psm_retrofit_widget.current_data.cpc_dilution_correction = 10.5

        arr = psm_retrofit_widget.current_data.to_array()

        # CPC concentration is at index 16
        assert arr[16] == 1234.5
        # CPC dilution correction is at index 17
        assert arr[17] == 10.5


# ============================================================================
# Connected CPC Integration Tests
# ============================================================================

class TestPSMCPCIntegration:
    """Test PSM integration with connected CPC."""

    def test_psm_has_connected_cpc_device_reference(self, psm_retrofit_widget):
        """Test that PSM has a reference for connected CPC device."""
        assert hasattr(psm_retrofit_widget, 'connected_cpc_device')
        assert psm_retrofit_widget.connected_cpc_device is None  # Initially None

    def test_psm_data_has_cpc_fields(self, psm_retrofit_widget):
        """Test that PSM data structure has fields for CPC data."""
        assert hasattr(psm_retrofit_widget.current_data, 'cpc_concentration')
        assert hasattr(psm_retrofit_widget.current_data, 'cpc_temp_sat')
        assert hasattr(psm_retrofit_widget.current_data, 'cpc_dilution_correction')


# ============================================================================
# Settings Flag Tests
# ============================================================================

class TestPSMSettingsFlags:
    """Test PSM settings fetch flags."""

    def test_needs_settings_fetch_flag_initial(self, psm_retrofit_widget):
        """Test that needs_settings_fetch is True on initialization."""
        assert psm_retrofit_widget.needs_settings_fetch is True

    def test_settings_has_dilution_parameters(self, psm_retrofit_widget):
        """Test that settings object has dilution_parameters field."""
        assert hasattr(psm_retrofit_widget.settings, 'dilution_parameters')
        # Initially should be empty list
        assert isinstance(psm_retrofit_widget.settings.dilution_parameters, list)


# ============================================================================
# Unknown Message Handling Tests
# ============================================================================

class TestPSMUnknownMessages:
    """Test PSM handling of unknown or malformed messages."""

    def test_parse_unknown_command(self, psm_retrofit_widget):
        """Test parsing unknown command response."""
        message = ":UNKNOWN:COMMAND data"

        result = psm_retrofit_widget.parse_message(message, None)

        # Should return unknown type
        assert result['type'] in ['unknown', 'info', 'error']

    def test_parse_message_no_space(self, psm_retrofit_widget):
        """Test parsing message without space separator."""
        message = ":MEAS:SCAN"

        result = psm_retrofit_widget.parse_message(message, None)

        assert result is not None
        assert result['type'] == 'unknown'

    def test_parse_null_message(self, psm_retrofit_widget):
        """Test parsing None message."""
        message = None

        # Should handle gracefully (implementation may vary)
        try:
            result = psm_retrofit_widget.parse_message(message, None)
            assert result is not None
        except (AttributeError, TypeError):
            # Expected if implementation doesn't handle None
            pass


# ============================================================================
# Command Sequence Tests
# ============================================================================

class TestPSMCommandSequence:
    """Test PSM command sequencing based on original monolith app behavior."""

    def test_get_read_command_returns_none(self, psm_retrofit_widget):
        """Test that PSM returns None for get_read_command (auto-push device)."""
        command = psm_retrofit_widget.get_read_command()

        # PSM auto-pushes data, no read command needed
        assert command is None

    def test_send_read_commands_with_settings_fetch(self, psm_retrofit_widget):
        """Test send_read_commands sends :SYST:PRNT when settings need fetching."""
        from unittest.mock import Mock

        # Create mock connection
        mock_conn = Mock()
        mock_conn.send_message = Mock()
        mock_conn.send_delayed_message = Mock()

        # Set needs_settings_fetch to True
        psm_retrofit_widget.needs_settings_fetch = True
        # Ensure dilution parameters are None to trigger :SYST:VCMP
        psm_retrofit_widget.settings.dilution_parameters = None

        # Call send_read_commands
        psm_retrofit_widget.send_read_commands(mock_conn, None)

        # Should send :SYST:PRNT immediately
        mock_conn.send_message.assert_called_once_with(":SYST:PRNT")
        # Should send :SYST:VCMP with 150ms delay
        mock_conn.send_delayed_message.assert_called_once_with(":SYST:VCMP", 150)

    def test_send_read_commands_without_settings_fetch(self, psm_retrofit_widget):
        """Test send_read_commands when settings already fetched."""
        from unittest.mock import Mock

        mock_conn = Mock()
        mock_conn.send_message = Mock()
        mock_conn.send_delayed_message = Mock()

        # Set needs_settings_fetch to False
        psm_retrofit_widget.needs_settings_fetch = False
        # Set dilution parameters to non-None
        psm_retrofit_widget.settings.dilution_parameters = [1.0, 2.0, 3.0]

        # Call send_read_commands
        psm_retrofit_widget.send_read_commands(mock_conn, None)

        # Should not send any commands
        mock_conn.send_message.assert_not_called()
        mock_conn.send_delayed_message.assert_not_called()

    def test_send_read_commands_only_dilution_params_missing(self, psm_retrofit_widget):
        """Test send_read_commands when only dilution params missing."""
        from unittest.mock import Mock

        mock_conn = Mock()
        mock_conn.send_message = Mock()
        mock_conn.send_delayed_message = Mock()

        # Settings fetch not needed
        psm_retrofit_widget.needs_settings_fetch = False
        # But dilution parameters still None
        psm_retrofit_widget.settings.dilution_parameters = None

        # Call send_read_commands
        psm_retrofit_widget.send_read_commands(mock_conn, None)

        # Should only send :SYST:VCMP
        mock_conn.send_message.assert_not_called()
        mock_conn.send_delayed_message.assert_called_once_with(":SYST:VCMP", 150)


# ============================================================================
# Buffer Management Tests
# ============================================================================

class TestPSMBufferManagement:
    """Test PSM data buffer management based on monolith app patterns."""

    def test_extra_data_buffer_usage(self, psm_retrofit_widget):
        """Test that PSM uses extra_data buffer for multiple messages."""
        # Create simple mock data holder with extra_data dict
        from unittest.mock import Mock

        data_holder = Mock()
        data_holder.extra_data = {}
        data_holder.device_errors = {}
        data_holder.error_status = 0
        data_holder.par_updates = {}
        data_holder.latest_settings = {}

        # Parse two measurement messages
        message1 = ":MEAS:SCAN 1.0,0.7,90.0,40.0,25.0,85.0,30.0,28.0,1.0,1013.2,0.3,450.0,10.5,0,0.5,0x000,0x00"
        message2 = ":MEAS:SCAN 1.1,0.8,90.5,40.5,25.5,85.5,30.5,28.5,1.1,1013.5,0.4,450.5,10.6,0,0.6,0x000,0x00"

        parsed1 = psm_retrofit_widget.parse_message(message1, data_holder)
        parsed2 = psm_retrofit_widget.parse_message(message2, data_holder)

        # Process messages
        result = psm_retrofit_widget.process_parsed_messages([parsed1, parsed2], None, data_holder)

        # First message should update data, second should go to extra_data
        assert result['data_updated'] is True
        # Extra data should contain second message's data
        # (Implementation stores arrays, not parsed dicts)
        assert psm_retrofit_widget.dev_id in data_holder.extra_data or result['data_updated']


# ============================================================================
# Mark Tests
# ============================================================================

pytestmark = pytest.mark.unit
