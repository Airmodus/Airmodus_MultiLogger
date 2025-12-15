"""
Unit tests for simple devices - Message parsing and data handling.

Tests all simple device types:
- RHTP (Relative Humidity, Temperature, Pressure)
- CO2 Sensor
- AFM (Airmodus Flow Meter)
- Electrometer
- TSI CPC
- Example Device

Simple devices have auto-push data (no commands needed) and simpler parsing.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock
import numpy as np

# Add src to path
src_path = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from devices.rhtp import RHTPWidget
from devices.co2 import CO2Widget
from devices.afm import AFMWidget
from devices.electrometer import ElectrometerWidget
from devices.tsi_cpc import TSIWidget
from devices.example import ExampleDeviceWidget
from config import RHTP, CO2_SENSOR, AFM, ELECTROMETER, TSI_CPC, EXAMPLE_DEVICE


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def rhtp_widget(qapp, mock_rhtp_config):
    """Create RHTPWidget for testing."""
    widget = RHTPWidget(mock_rhtp_config)
    yield widget
    widget.deleteLater()


@pytest.fixture
def co2_widget(qapp, mock_co2_config):
    """Create CO2Widget for testing."""
    widget = CO2Widget(mock_co2_config)
    yield widget
    widget.deleteLater()


@pytest.fixture
def afm_widget(qapp, mock_afm_config):
    """Create AFMWidget for testing."""
    widget = AFMWidget(mock_afm_config)
    yield widget
    widget.deleteLater()


@pytest.fixture
def electrometer_widget(qapp, mock_electrometer_config):
    """Create ElectrometerWidget for testing."""
    widget = ElectrometerWidget(mock_electrometer_config)
    yield widget
    widget.deleteLater()


@pytest.fixture
def tsi_cpc_widget(qapp, mock_tsi_cpc_config):
    """Create TSIWidget for testing."""
    widget = TSIWidget(mock_tsi_cpc_config)
    yield widget
    widget.deleteLater()


@pytest.fixture
def example_widget(qapp, mock_example_config):
    """Create ExampleDeviceWidget for testing."""
    widget = ExampleDeviceWidget(mock_example_config)
    yield widget
    widget.deleteLater()


# ============================================================================
# RHTP Tests
# ============================================================================

class TestRHTPDevice:
    """Test RHTP sensor device."""

    def test_parse_valid_data(self, rhtp_widget):
        """Test parsing valid RHTP data (RH, T, P)."""
        message = "45.2, 25.3, 1013.25"

        result = rhtp_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert result['command'] == 'auto-push'
        assert rhtp_widget.current_data.humidity == 45.2
        assert rhtp_widget.current_data.temperature == 25.3
        assert rhtp_widget.current_data.pressure == 1013.25

    def test_parse_idn(self, rhtp_widget):
        """Test parsing IDN response."""
        message = "*IDN RHTP Sensor,PSN:RHTP-001,FW:1.0.0"

        result = rhtp_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'
        assert 'RHTP' in result['data']

    def test_parse_malformed_data_short(self, rhtp_widget):
        """Test parsing malformed data (too few values)."""
        message = "45.2, 25.3"

        result = rhtp_widget.parse_message(message, None)

        # Should not parse as data (need 3 values)
        assert result['type'] in ['error', 'info', 'unknown']

    def test_parse_malformed_data_invalid_number(self, rhtp_widget):
        """Test parsing data with invalid number format."""
        message = "invalid, 25.3, 1013.25"

        result = rhtp_widget.parse_message(message, None)

        # Should handle gracefully (not crash)
        assert result is not None

    def test_to_array_length(self, rhtp_widget):
        """Test that RHTP data array has 3 fields."""
        arr = rhtp_widget.current_data.to_array()
        assert len(arr) == 3

    def test_data_writer_header(self, rhtp_widget):
        """Test RHTP .dat file header."""
        header = rhtp_widget.data_writer.get_dat_header()
        assert 'Humidity' in header or 'RH' in header
        assert 'Temperature' in header or 'T' in header
        assert 'Pressure' in header or 'P' in header


# ============================================================================
# CO2 Sensor Tests
# ============================================================================

class TestCO2Device:
    """Test CO2 sensor device."""

    def test_parse_valid_data_single_value(self, co2_widget):
        """Test parsing valid CO2 data (single value)."""
        message = "412.5"

        result = co2_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert co2_widget.current_data.co2 == 412.5

    def test_parse_valid_data_three_values(self, co2_widget):
        """Test parsing CO2 data with temperature and humidity."""
        # CO2 sensor uses semicolon-separated values
        message = "412.5;25.0;50.0"

        result = co2_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert co2_widget.current_data.co2 == 412.5
        assert co2_widget.current_data.temperature == 25.0
        assert co2_widget.current_data.humidity == 50.0

    def test_parse_idn(self, co2_widget):
        """Test parsing IDN response."""
        message = "*IDN CO2 Sensor,PSN:CO2-001,FW:1.0.0"

        result = co2_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'

    def test_parse_malformed_data(self, co2_widget):
        """Test parsing invalid data."""
        message = "invalid"

        result = co2_widget.parse_message(message, None)

        # Should handle gracefully
        assert result is not None

    def test_to_array_length(self, co2_widget):
        """Test that CO2 data array has 3 fields."""
        arr = co2_widget.current_data.to_array()
        assert len(arr) == 3

    def test_data_writer_header(self, co2_widget):
        """Test CO2 .dat file header."""
        header = co2_widget.data_writer.get_dat_header()
        assert 'CO2' in header or 'co2' in header


# ============================================================================
# AFM (Airmodus Flow Meter) Tests
# ============================================================================

class TestAFMDevice:
    """Test AFM (Airmodus Flow Meter) device."""

    def test_parse_valid_data(self, afm_widget):
        """Test parsing valid AFM data (flow, standard_flow, RH, T, P)."""
        message = "1.25, 0.8, 45.0, 25.3, 1013.2"

        result = afm_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert afm_widget.current_data.flow == 1.25
        assert afm_widget.current_data.standard_flow == 0.8
        assert afm_widget.current_data.humidity == 45.0
        assert afm_widget.current_data.temperature == 25.3
        assert afm_widget.current_data.pressure == 1013.2

    def test_parse_idn(self, afm_widget):
        """Test parsing IDN response."""
        message = "*IDN Airmodus Flow Meter,PSN:AFM-001,FW:1.0.0"

        result = afm_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'

    def test_parse_malformed_data(self, afm_widget):
        """Test parsing malformed data (too few values)."""
        message = "1.25, 0.8"

        result = afm_widget.parse_message(message, None)

        # Should not parse as data (need 5 values)
        assert result['type'] in ['error', 'info', 'unknown']

    def test_to_array_length(self, afm_widget):
        """Test that AFM data array has 5 fields."""
        arr = afm_widget.current_data.to_array()
        assert len(arr) == 5

    def test_data_writer_header(self, afm_widget):
        """Test AFM .dat file header."""
        header = afm_widget.data_writer.get_dat_header()
        assert 'Flow' in header or 'flow' in header


# ============================================================================
# Electrometer Tests
# ============================================================================

class TestElectrometerDevice:
    """Test Electrometer device."""

    def test_parse_valid_data_single_voltage(self, electrometer_widget):
        """Test parsing valid electrometer data (single voltage)."""
        message = "123.45"

        result = electrometer_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert electrometer_widget.current_data.voltage1 == 123.45

    def test_parse_valid_data_three_voltages(self, electrometer_widget):
        """Test parsing electrometer data with 3 channels."""
        # Electrometer uses semicolon-separated values
        message = "123.45;234.56;345.67"

        result = electrometer_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert electrometer_widget.current_data.voltage1 == 123.45
        assert electrometer_widget.current_data.voltage2 == 234.56
        assert electrometer_widget.current_data.voltage3 == 345.67

    def test_parse_idn(self, electrometer_widget):
        """Test parsing IDN response."""
        message = "*IDN Electrometer,PSN:ELEC-001,FW:1.0.0"

        result = electrometer_widget.parse_message(message, None)

        # Electrometer doesn't handle IDN, returns error
        assert result['type'] == 'error'

    def test_parse_malformed_data(self, electrometer_widget):
        """Test parsing invalid data."""
        message = "invalid"

        result = electrometer_widget.parse_message(message, None)

        # Should handle gracefully
        assert result is not None

    def test_to_array_length(self, electrometer_widget):
        """Test that Electrometer data array has 3 fields."""
        arr = electrometer_widget.current_data.to_array()
        assert len(arr) == 3

    def test_data_writer_header(self, electrometer_widget):
        """Test Electrometer .dat file header."""
        header = electrometer_widget.data_writer.get_dat_header()
        assert 'Voltage' in header or 'voltage' in header


# ============================================================================
# TSI CPC Tests
# ============================================================================

class TestTSICPCDevice:
    """Test TSI CPC device."""

    def test_parse_valid_data_single_value(self, tsi_cpc_widget):
        """Test parsing valid TSI CPC data (concentration and error hex)."""
        # TSI CPC format: "concentration\rerror_hex"
        message = "5678.9\r0x000"

        result = tsi_cpc_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert tsi_cpc_widget.current_data.concentration == 5678.9
        assert tsi_cpc_widget.current_data.error_hex == "0x000"

    def test_parse_valid_data_with_error(self, tsi_cpc_widget):
        """Test parsing TSI CPC data with error hex showing errors."""
        # TSI CPC format: "concentration\rerror_hex"
        message = "5678.9\r0x001"

        result = tsi_cpc_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert tsi_cpc_widget.current_data.concentration == 5678.9
        assert tsi_cpc_widget.current_data.error_hex == "0x001"
        assert result.get('has_errors', False) == True

    def test_parse_idn(self, tsi_cpc_widget):
        """Test parsing IDN response."""
        message = "*IDN TSI CPC 3776,PSN:TSI-001,FW:1.0.0"

        result = tsi_cpc_widget.parse_message(message, None)

        # TSI CPC doesn't handle IDN, returns error
        assert result['type'] == 'error'

    def test_parse_malformed_data(self, tsi_cpc_widget):
        """Test parsing invalid data."""
        message = "invalid"

        result = tsi_cpc_widget.parse_message(message, None)

        # Should handle gracefully
        assert result is not None

    def test_to_array_length(self, tsi_cpc_widget):
        """Test that TSI CPC data array has 2 fields."""
        arr = tsi_cpc_widget.current_data.to_array()
        assert len(arr) == 2

    def test_data_writer_header(self, tsi_cpc_widget):
        """Test TSI CPC .dat file header."""
        header = tsi_cpc_widget.data_writer.get_dat_header()
        assert 'Concentration' in header or 'concentration' in header


# ============================================================================
# Example Device Tests
# ============================================================================

class TestExampleDevice:
    """Test Example device (template for adding new devices)."""

    def test_parse_valid_data(self, example_widget):
        """Test parsing valid Example device data."""
        message = "42.5"

        result = example_widget.parse_message(message, None)

        assert result['type'] == 'data'
        assert result['command'] == 'auto-push'
        assert example_widget.current_data.random_value == 42.5

    def test_parse_idn(self, example_widget):
        """Test parsing IDN response."""
        message = "*IDN SERIAL123"

        result = example_widget.parse_message(message, None)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'
        assert result['data'] == 'SERIAL123'

    def test_parse_invalid_data(self, example_widget):
        """Test parsing invalid data."""
        message = "invalid"

        result = example_widget.parse_message(message, None)

        # Should return unknown type
        assert result['type'] in ['info', 'unknown']
        assert result['command'] == 'unknown'

    def test_to_array_length(self, example_widget):
        """Test that Example device data array has 1 field."""
        arr = example_widget.current_data.to_array()
        assert len(arr) == 1
        # Both should be NaN initially (can't use == for NaN comparison)
        import numpy as np
        assert np.isnan(arr[0]) == np.isnan(example_widget.current_data.random_value)

    def test_data_writer_header(self, example_widget):
        """Test Example device .dat file header."""
        header = example_widget.data_writer.get_dat_header()
        assert 'Random value' in header


# ============================================================================
# Common Simple Device Tests
# ============================================================================

class TestSimpleDeviceCommonFeatures:
    """Test features common to all simple devices."""

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "co2_widget", "afm_widget",
        "electrometer_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_all_have_data_writer(self, widget_fixture, request):
        """Test that all simple devices have data_writer."""
        widget = request.getfixturevalue(widget_fixture)
        assert hasattr(widget, 'data_writer')
        assert widget.data_writer is not None

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "co2_widget", "afm_widget",
        "electrometer_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_all_have_current_data(self, widget_fixture, request):
        """Test that all simple devices have current_data."""
        widget = request.getfixturevalue(widget_fixture)
        assert hasattr(widget, 'current_data')
        assert widget.current_data is not None

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "co2_widget", "afm_widget",
        "electrometer_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_all_have_plot_config(self, widget_fixture, request):
        """Test that all simple devices have plot_config."""
        widget = request.getfixturevalue(widget_fixture)
        assert hasattr(widget, 'plot_config')
        assert widget.plot_config is not None

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "co2_widget", "afm_widget",
        "electrometer_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_all_have_parse_message(self, widget_fixture, request):
        """Test that all simple devices implement parse_message."""
        widget = request.getfixturevalue(widget_fixture)
        assert hasattr(widget, 'parse_message')
        assert callable(widget.parse_message)

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "co2_widget", "afm_widget",
        "electrometer_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_all_data_have_to_array(self, widget_fixture, request):
        """Test that all simple device data classes have to_array method."""
        widget = request.getfixturevalue(widget_fixture)
        assert hasattr(widget.current_data, 'to_array')
        assert callable(widget.current_data.to_array)

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "afm_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_auto_push_devices_return_none(self, widget_fixture, request):
        """Test that auto-push devices return None for get_read_command."""
        widget = request.getfixturevalue(widget_fixture)
        assert widget.get_read_command() is None

    @pytest.mark.parametrize("widget_fixture", [
        "co2_widget", "electrometer_widget"
    ])
    def test_command_based_devices_return_command(self, widget_fixture, request):
        """Test that command-based devices return a command string for get_read_command."""
        widget = request.getfixturevalue(widget_fixture)
        command = widget.get_read_command()
        assert command is not None
        assert isinstance(command, str)
        assert len(command) > 0


# ============================================================================
# Empty/Null Message Tests
# ============================================================================

class TestSimpleDeviceErrorHandling:
    """Test error handling for simple devices."""

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "co2_widget", "afm_widget",
        "electrometer_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_parse_empty_message(self, widget_fixture, request):
        """Test parsing empty message."""
        widget = request.getfixturevalue(widget_fixture)
        result = widget.parse_message("", None)
        assert result is not None

    @pytest.mark.parametrize("widget_fixture", [
        "rhtp_widget", "co2_widget", "afm_widget",
        "electrometer_widget", "tsi_cpc_widget", "example_widget"
    ])
    def test_parse_whitespace_message(self, widget_fixture, request):
        """Test parsing whitespace-only message."""
        widget = request.getfixturevalue(widget_fixture)
        result = widget.parse_message("   \r\n  ", None)
        assert result is not None


# ============================================================================
# Mark Tests
# ============================================================================

pytestmark = pytest.mark.unit
