"""
Unit tests for utils.py - Utility functions and helpers.

Tests pure functions that don't require complex dependencies:
- Array management (_manage_plot_array, _roll_pulse_array)
- Response parsing (parse_idn_response)
- Response creation (create_data_response, create_error_response)
- Settings compilation (compile_cpc_settings, compile_psm_settings)
"""

import pytest
import numpy as np
from numpy import nan, isnan


# Import utility functions
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from utils import (
    _manage_plot_array,
    _roll_pulse_array,
    parse_idn_response,
    create_data_response,
    create_error_response,
    compile_cpc_settings,
    compile_psm_settings
)
from config import MAX_TIME_SEC, PSM, PSM2


# ============================================================================
# Array Management Tests
# ============================================================================

class TestManagePlotArray:
    """Test _manage_plot_array function for rolling buffer logic."""

    def test_initial_growth_doubles_array(self):
        """Test that array doubles when time_counter exceeds length."""
        arr = np.full(10, nan)
        time_counter = 10

        result = _manage_plot_array(arr, time_counter, max_reached=False)

        assert len(result) == 20, "Array should double in size"
        assert np.isnan(result[10:]).all(), "New elements should be NaN"

    def test_no_change_when_within_limits(self):
        """Test that array is unchanged when time_counter < length."""
        arr = np.full(100, nan)
        arr[5] = 42.0
        time_counter = 5

        result = _manage_plot_array(arr, time_counter, max_reached=False)

        assert len(result) == 100, "Array size should not change"
        assert result[5] == 42.0, "Data should be preserved"

    def test_shift_left_when_max_reached(self):
        """Test left shift behavior when max time is reached."""
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        time_counter = MAX_TIME_SEC

        result = _manage_plot_array(arr, time_counter, max_reached=True)

        assert result[0] == 2.0, "First element should shift left"
        assert result[3] == 5.0, "Data should shift left"
        assert np.isnan(result[-1]), "Last element should be NaN"

    def test_truncate_when_exceeds_max_time(self):
        """Test array truncation when it exceeds MAX_TIME_SEC."""
        arr = np.full(MAX_TIME_SEC + 100, 42.0)
        time_counter = MAX_TIME_SEC

        result = _manage_plot_array(arr, time_counter, max_reached=True)

        assert len(result) == MAX_TIME_SEC, "Array should be truncated to MAX_TIME_SEC"

    def test_preserves_data_during_doubling(self):
        """Test that existing data is preserved when array doubles."""
        arr = np.array([10.0, 20.0, 30.0])
        arr[1] = 99.9
        time_counter = 3

        result = _manage_plot_array(arr, time_counter, max_reached=False)

        assert len(result) == 6, "Array should double"
        assert result[0] == 10.0, "Original data preserved"
        assert result[1] == 99.9, "Modified data preserved"
        assert result[2] == 30.0, "Original data preserved"


class TestRollPulseArray:
    """Test _roll_pulse_array function for pulse buffer management."""

    def test_rolls_array_left(self):
        """Test that array elements roll left by 1."""
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        result = _roll_pulse_array(arr)

        assert result[0] == 2.0, "First element should be second"
        assert result[3] == 5.0, "Elements should shift left"

    def test_last_element_becomes_nan(self):
        """Test that last element is set to NaN."""
        arr = np.array([1.0, 2.0, 3.0])

        result = _roll_pulse_array(arr)

        assert np.isnan(result[-1]), "Last element should be NaN"

    def test_preserves_array_length(self):
        """Test that array length is unchanged."""
        arr = np.full(10, 42.0)

        result = _roll_pulse_array(arr)

        assert len(result) == 10, "Array length should be preserved"


# ============================================================================
# Response Parsing Tests
# ============================================================================

class TestParseIdnResponse:
    """Test parse_idn_response function."""

    def test_parse_valid_idn(self):
        """Test parsing valid IDN response."""
        message = "*IDN Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0"

        result = parse_idn_response(message)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'
        assert result['data'] == "Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0"
        assert result['raw'] == message
        assert result['update_gui'] is False

    def test_parse_idn_no_space(self):
        """Test parsing IDN with no space (edge case)."""
        message = "*IDN"

        result = parse_idn_response(message)

        assert result['type'] == 'info'
        assert result['command'] == '*IDN'
        assert result['data'] == ""
        assert result['raw'] == message

    def test_parse_idn_extra_spaces(self):
        """Test parsing IDN with extra whitespace."""
        message = "*IDN    Multiple   Spaces   Here"

        result = parse_idn_response(message)

        assert result['data'] == "Multiple   Spaces   Here"


# ============================================================================
# Response Creation Tests
# ============================================================================

class TestCreateDataResponse:
    """Test create_data_response function."""

    def test_creates_valid_data_response(self):
        """Test creating standard data response."""
        message = ":MEAS:ALL 1,2,3"
        command = ":MEAS:ALL"
        data = [1.0, 2.0, 3.0]

        result = create_data_response(message, command, data)

        assert result['type'] == 'data'
        assert result['command'] == command
        assert result['data'] == data
        assert result['raw'] == message
        assert result['update_gui'] is False

    def test_preserves_data_array_reference(self):
        """Test that data array reference is preserved (not copied)."""
        data = [1, 2, 3]

        result = create_data_response("msg", "cmd", data)

        assert result['data'] is data, "Should preserve array reference"


class TestCreateErrorResponse:
    """Test create_error_response function."""

    def test_creates_error_from_string(self):
        """Test creating error response from string."""
        message = "invalid data"
        command = ":MEAS:ALL"
        error = "ValueError: could not parse"

        result = create_error_response(message, command, error)

        assert result['type'] == 'error'
        assert result['command'] == command
        assert result['data'] is None
        assert result['raw'] == message
        assert result['error'] == error
        assert result['update_gui'] is False

    def test_creates_error_from_exception(self):
        """Test creating error response from Exception object."""
        message = "bad data"
        command = "unknown"
        error = ValueError("Invalid format")

        result = create_error_response(message, command, error)

        assert result['error'] == "Invalid format"
        assert result['type'] == 'error'


# ============================================================================
# Settings Compilation Tests
# ============================================================================

class TestCompileCpcSettings:
    """Test compile_cpc_settings function."""

    def test_compiles_cpc_settings_array(self):
        """Test that CPC settings are compiled in correct order."""
        # Mock prnt and pall arrays (indices based on actual usage)
        prnt = [None] * 15
        prnt[5] = 1.0      # averaging time
        prnt[10] = 0.3     # measured cpc flow rate
        prnt[8] = 40.0     # saturator temp setpoint
        prnt[6] = 10.0     # condenser temp setpoint
        prnt[7] = 25.0     # optics temp setpoint
        prnt[1] = 1        # autofill
        prnt[4] = 0        # water removal
        prnt[12] = 0.12    # dead time correction
        prnt[2] = 0        # drain

        pall = [None] * 30
        pall[24] = 1.0     # nominal inlet flow rate
        pall[26] = 30      # OPC threshold 1
        pall[27] = 1500    # OPC threshold 2
        pall[20] = 1.0     # k-factor
        pall[25] = 0.0     # tau

        result = compile_cpc_settings(prnt, pall)

        assert len(result) == 14, "Should have 14 settings"
        assert result[0] == 1.0, "First should be averaging time"
        assert result[1] == 1.0, "Second should be nominal flow"
        assert result[2] == 0.3, "Third should be measured flow"
        assert result[3] == 40.0, "Should have saturator temp"
        assert result[6] == 1, "Should have autofill (int)"
        assert result[9] == 0, "Should have water removal (int)"

    def test_preserves_int_types(self):
        """Test that integer values remain integers."""
        prnt = [None] * 15
        prnt[1] = 1  # autofill (should be int)
        prnt[4] = 0  # water removal (should be int)
        prnt[2] = 1  # drain (should be int)
        # Fill other required indices
        prnt[5] = prnt[10] = prnt[8] = prnt[6] = prnt[7] = prnt[12] = 0.0

        pall = [None] * 30
        pall[24] = pall[26] = pall[27] = pall[20] = pall[25] = 0.0

        result = compile_cpc_settings(prnt, pall)

        assert isinstance(result[6], int), "Autofill should be int"
        assert isinstance(result[9], int), "Water removal should be int"
        assert isinstance(result[11], int), "Drain should be int"


class TestCompilePsmSettings:
    """Test compile_psm_settings function."""

    def test_compiles_psm_v2_settings(self):
        """Test PSM 2.0 settings compilation (no CO flow)."""
        prnt = [None, 90.0, 40.0, 25.0, 85.0, 30.0, 0.3]  # Index 0 unused
        co_flow = 0.0  # Not used for PSM 2.0
        dilution_params = [10.0, 2.0, 1.5]

        result = compile_psm_settings(prnt, co_flow, dilution_params, PSM2)

        # Base: 7 items (5 temps + CPC flow + "nan") + 3 dilution params = 10 total
        assert len(result) == 10, "PSM 2.0 should have 10 settings (7 base + 3 dilution, no CO flow)"
        assert result[0] == 90.0, "First should be growth tube temp"
        assert result[1] == 40.0, "Second should be PSM saturator temp"
        assert result[6] == "nan", "Inlet flow placeholder"
        assert result[7] == 10.0, "First dilution param"

    def test_compiles_psm_retrofit_settings(self):
        """Test PSM Retrofit settings compilation (includes CO flow)."""
        prnt = [None, 90.0, 40.0, 25.0, 85.0, 30.0, 0.3]
        co_flow = 0.1
        dilution_params = [10.0, 2.0, 1.5]

        result = compile_psm_settings(prnt, co_flow, dilution_params, PSM)

        # Base: 7 items (5 temps + CPC flow + "nan") + 1 CO flow + 3 dilution params = 11 total
        assert len(result) == 11, "PSM Retrofit should have 11 settings (7 base + CO flow + 3 dilution)"
        assert result[7] == 0.1, "CO flow should be added for Retrofit"
        assert result[8] == 10.0, "Dilution params follow CO flow"

    def test_empty_dilution_parameters(self):
        """Test with empty dilution parameters."""
        prnt = [None, 90.0, 40.0, 25.0, 85.0, 30.0, 0.3]
        co_flow = 0.0
        dilution_params = []

        result = compile_psm_settings(prnt, co_flow, dilution_params, PSM2)

        assert len(result) == 7, "Should have base settings only"
        assert result[6] == "nan", "Inlet flow placeholder present"


# ============================================================================
# Mark Tests
# ============================================================================

pytestmark = pytest.mark.unit
