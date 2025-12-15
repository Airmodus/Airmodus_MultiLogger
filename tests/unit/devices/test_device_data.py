"""
Unit tests for device_data.py - Device dataclasses and factories.

Tests dataclass initialization, to_array() methods, and factory functions
for all device types.
"""

import pytest
import numpy as np
from numpy import nan, isnan


# Import device data classes
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from devices.device_data import (
    CPCData, PSMData, ElectrometerData, CO2Data, RHTPData,
    AFMData, EDiluterData, TSI_CPCData, ExampleDeviceData,
    CPCSettings, PSMSettings,
    create_device_data, create_device_settings
)
from config import (
    CPC, PSM, PSM2, ELECTROMETER, CO2_SENSOR, RHTP,
    AFM, EDILUTER, TSI_CPC, EXAMPLE_DEVICE
)


# ============================================================================
# CPC Data Tests
# ============================================================================

class TestCPCData:
    """Test CPCData dataclass."""

    def test_default_initialization(self):
        """Test that CPC data initializes with NaN defaults."""
        data = CPCData()

        assert np.isnan(data.concentration)
        assert np.isnan(data.dead_time)
        assert data.number_of_pulses == 0
        assert np.isnan(data.temp_saturator)
        assert data.total_errors == 0
        assert data.status_hex == ""

    def test_to_array_length(self):
        """Test that to_array() returns correct number of fields."""
        data = CPCData()

        arr = data.to_array()

        assert len(arr) == 15, "CPC array should have 15 fields"

    def test_to_array_order(self):
        """Test that to_array() returns fields in correct order."""
        data = CPCData()
        data.concentration = 1234.5
        data.dead_time = 0.12
        data.number_of_pulses = 100
        data.temp_saturator = 40.5
        data.status_hex = "0x007"

        arr = data.to_array()

        assert arr[0] == 1234.5, "Index 0 should be concentration"
        assert arr[1] == 0.12, "Index 1 should be dead_time"
        assert arr[2] == 100, "Index 2 should be number_of_pulses"
        assert arr[3] == 40.5, "Index 3 should be temp_saturator"
        assert arr[14] == "0x007", "Index 14 should be status_hex"

    def test_extra_fields_not_in_array(self):
        """Test that extra fields (laser_current, pulse_duration) are NOT in array."""
        data = CPCData()
        data.laser_current = 123.4
        data.pulse_duration = 45.6

        arr = data.to_array()

        assert len(arr) == 15, "Extra fields should not be in array"
        assert 123.4 not in arr, "laser_current should not be in array"
        assert 45.6 not in arr, "pulse_duration should not be in array"

    def test_field_assignment(self):
        """Test that fields can be assigned and retrieved."""
        data = CPCData()

        data.concentration = 5678.9
        data.liquid_level = 75

        assert data.concentration == 5678.9
        assert data.liquid_level == 75


# ============================================================================
# PSM Data Tests
# ============================================================================

class TestPSMData:
    """Test PSMData dataclass."""

    def test_default_initialization(self):
        """Test PSM data initializes with NaN defaults."""
        data = PSMData()

        assert np.isnan(data.saturator_flow)
        assert np.isnan(data.temp_growth_tube)
        assert data.total_errors == 0
        assert data.poly_correction == 0.0
        assert data.scan_status == ""

    def test_to_array_length(self):
        """Test that to_array() returns correct number of fields."""
        data = PSMData(status_hex="0x000", note_hex="0x000")

        arr = data.to_array()

        assert len(arr) == 33, "PSM array should have 33 fields (PSM data + CPC data + hex fields)"

    def test_to_array_includes_cpc_fields(self):
        """Test that to_array() includes CPC data fields."""
        data = PSMData(status_hex="0x000", note_hex="0x000")
        data.cpc_concentration = 1234.5
        data.cpc_dilution_correction = 10.5
        data.cpc_temp_sat = 40.0

        arr = data.to_array()

        assert arr[17] == 1234.5, "Index 17 should be cpc_concentration"
        assert arr[18] == 10.5, "Index 18 should be cpc_dilution_correction"
        assert arr[19] == 40.0, "Index 19 should be cpc_temp_sat"

    def test_vacuum_flow_in_array(self):
        """Test that vacuum_flow (PSM2 field) is included in array when not NaN."""
        data = PSMData(status_hex="0x000", note_hex="0x000")
        data.vacuum_flow = 0.5

        arr = data.to_array()

        assert arr[15] == 0.5, "Index 15 should be vacuum_flow for PSM2"
        assert arr[16] == 1, "Index 16 should be psm_status"
        assert arr[17] == 1, "Index 17 should be psm_note"

    def test_psm_retrofit_without_vacuum(self):
        """Test PSM Retrofit (vacuum_flow = nan) doesn't include vacuum_flow in array."""
        data = PSMData(status_hex="0x000", note_hex="0x000")
        # vacuum_flow defaults to nan for Retrofit

        arr = data.to_array()

        # For Retrofit, vacuum_flow is NOT in array, so psm_status is at index 15
        assert arr[15] == 1, "Index 15 should be psm_status (1 = OK) for Retrofit"
        assert arr[16] == 1, "Index 16 should be psm_note (1 = OK) for Retrofit"


# ============================================================================
# Simple Device Data Tests
# ============================================================================

class TestSimpleDeviceData:
    """Test simple device dataclasses (RHTP, CO2, Electrometer, etc.)."""

    def test_rhtp_data(self):
        """Test RHTP data structure."""
        data = RHTPData()
        data.humidity = 45.2
        data.temperature = 25.3
        data.pressure = 1013.25

        arr = data.to_array()

        assert len(arr) == 3
        assert arr[0] == 45.2
        assert arr[1] == 25.3
        assert arr[2] == 1013.25

    def test_co2_data(self):
        """Test CO2 sensor data structure."""
        data = CO2Data()
        data.co2 = 412.5
        data.temperature = 25.0
        data.humidity = 50.0

        arr = data.to_array()

        assert len(arr) == 3
        assert arr[0] == 412.5

    def test_electrometer_data(self):
        """Test Electrometer data structure."""
        data = ElectrometerData()
        data.voltage1 = 123.45
        data.voltage2 = 234.56
        data.voltage3 = 345.67

        arr = data.to_array()

        assert len(arr) == 3
        assert arr[0] == 123.45
        assert arr[1] == 234.56
        assert arr[2] == 345.67

    def test_afm_data(self):
        """Test AFM (Airmodus Flow Meter) data structure."""
        data = AFMData()
        data.flow = 1.25
        data.standard_flow = 0.8
        data.temperature = 25.3
        data.pressure = 1013.2
        data.humidity = 45.0

        arr = data.to_array()

        assert len(arr) == 5
        assert arr[0] == 1.25
        assert arr[1] == 0.8

    def test_tsi_cpc_data(self):
        """Test TSI CPC data structure."""
        data = TSI_CPCData()
        data.concentration = 5678.9
        data.error_hex = "0x000"

        arr = data.to_array()

        assert len(arr) == 2
        assert arr[0] == 5678.9
        assert arr[1] == "0x000"

    def test_example_device_data(self):
        """Test Example device data structure."""
        data = ExampleDeviceData()
        data.random_value = 42.5

        arr = data.to_array()

        assert len(arr) == 1
        assert arr[0] == 42.5


# ============================================================================
# eDiluter Data Tests
# ============================================================================

class TestEDiluterData:
    """Test EDiluterData dataclass."""

    def test_default_initialization(self):
        """Test eDiluter data initializes correctly."""
        data = EDiluterData()

        assert data.status == ""
        assert np.isnan(data.pres1)
        assert np.isnan(data.df_total)

    def test_to_array_length(self):
        """Test to_array() returns correct number of fields."""
        data = EDiluterData()

        arr = data.to_array()

        assert len(arr) == 12

    def test_to_array_order(self):
        """Test to_array() field order."""
        data = EDiluterData()
        data.status = "OK"
        data.pres1 = 1013.2
        data.df_total = 10.5

        arr = data.to_array()

        assert arr[0] == "OK"
        assert arr[1] == 1013.2
        assert arr[11] == 10.5


# ============================================================================
# Factory Function Tests
# ============================================================================

class TestCreateDeviceData:
    """Test create_device_data factory function."""

    def test_creates_cpc_data(self):
        """Test creating CPC data instance."""
        data = create_device_data(CPC)

        assert isinstance(data, CPCData)
        assert np.isnan(data.concentration)

    def test_creates_psm_data(self):
        """Test creating PSM data instance."""
        data = create_device_data(PSM)

        assert isinstance(data, PSMData)

    def test_creates_psm2_data(self):
        """Test creating PSM 2.0 data instance."""
        data = create_device_data(PSM2)

        assert isinstance(data, PSMData), "PSM2 uses same data class as PSM"

    def test_creates_simple_device_data(self):
        """Test creating simple device data instances."""
        rhtp = create_device_data(RHTP)
        co2 = create_device_data(CO2_SENSOR)
        electro = create_device_data(ELECTROMETER)
        afm = create_device_data(AFM)
        tsi = create_device_data(TSI_CPC)

        assert isinstance(rhtp, RHTPData)
        assert isinstance(co2, CO2Data)
        assert isinstance(electro, ElectrometerData)
        assert isinstance(afm, AFMData)
        assert isinstance(tsi, TSI_CPCData)

    def test_creates_ediluter_data(self):
        """Test creating eDiluter data instance."""
        data = create_device_data(EDILUTER)

        assert isinstance(data, EDiluterData)

    def test_creates_example_device_data(self):
        """Test creating Example device data instance."""
        data = create_device_data(EXAMPLE_DEVICE)

        assert isinstance(data, ExampleDeviceData)

    def test_raises_on_unknown_device_type(self):
        """Test that unknown device type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown device type"):
            create_device_data("INVALID_DEVICE")


# ============================================================================
# CPC Settings Tests
# ============================================================================

class TestCPCSettings:
    """Test CPCSettings dataclass."""

    def test_default_initialization(self):
        """Test CPC settings initialize with NaN defaults."""
        settings = CPCSettings()

        assert np.isnan(settings.averaging_time)
        assert np.isnan(settings.saturator_temp)
        assert np.isnan(settings.opc_threshold)

    def test_to_array_length(self):
        """Test to_array() returns 14 fields."""
        settings = CPCSettings()

        arr = settings.to_array()

        assert len(arr) == 14, "CPC settings array should have 14 fields"

    def test_to_array_order_matches_compile_cpc_settings(self):
        """Test that to_array() matches compile_cpc_settings format."""
        settings = CPCSettings()
        settings.averaging_time = 1.0          # [0]
        settings.nominal_inlet_flow = 1.5      # [1]
        settings.measured_cpc_flow = 0.3       # [2]
        settings.saturator_temp = 40.0         # [3]
        settings.condenser_temp = 10.0         # [4]
        settings.spare1 = 25.0                 # [5] temp_optics
        settings.autofill = 1.0                # [6]
        settings.opc_threshold = 30.0          # [7]
        settings.opc_threshold_2 = 1500.0      # [8]
        settings.water_removal = 0.0           # [9]
        settings.dead_time_correction = 0.12   # [10]
        settings.drain = 0.0                   # [11]
        settings.k_factor = 1.0                # [12]
        settings.tau = 0.0                     # [13]

        arr = settings.to_array()

        assert arr[0] == 1.0, "Index 0 should be averaging_time"
        assert arr[3] == 40.0, "Index 3 should be saturator_temp"
        assert arr[7] == 30.0, "Index 7 should be opc_threshold"
        assert arr[10] == 0.12, "Index 10 should be dead_time_correction"


# ============================================================================
# PSM Settings Tests
# ============================================================================

class TestPSMSettings:
    """Test PSMSettings dataclass."""

    def test_default_initialization(self):
        """Test PSM settings initialize correctly."""
        settings = PSMSettings()

        assert settings.mode == 0
        assert np.isnan(settings.temp_growth_tube)
        assert settings.dilution_parameters == []
        assert settings.cpc_settings == []

    def test_post_init_initializes_lists(self):
        """Test that __post_init__ initializes None lists."""
        settings = PSMSettings(dilution_parameters=None, cpc_settings=None)

        assert isinstance(settings.dilution_parameters, list)
        assert isinstance(settings.cpc_settings, list)

    def test_to_array_base_fields(self):
        """Test to_array() base fields (temps + flows)."""
        settings = PSMSettings()
        settings.temp_growth_tube = 90.0
        settings.temp_saturator = 40.0
        settings.cpc_inlet_flow = 0.3
        settings.inlet_flow_rate = 1.0

        arr = settings.to_array()

        assert arr[0] == 90.0, "Index 0 should be temp_growth_tube"
        assert arr[1] == 40.0, "Index 1 should be temp_saturator"
        assert arr[5] == 0.3, "Index 5 should be cpc_inlet_flow"
        assert arr[6] == 1.0, "Index 6 should be inlet_flow_rate"

    def test_to_array_includes_co_flow_when_not_nan(self):
        """Test that CO flow is included for Retrofit PSM."""
        settings = PSMSettings()
        settings.temp_growth_tube = 90.0
        settings.temp_saturator = 40.0
        settings.temp_inlet = 25.0
        settings.temp_heater = 85.0
        settings.temp_drainage = 30.0
        settings.cpc_inlet_flow = 0.3
        settings.inlet_flow_rate = 1.0
        settings.co_flow = 0.1
        settings.dilution_parameters = [10.0, 2.0]

        arr = settings.to_array()

        assert arr[7] == 0.1, "Index 7 should be CO flow for Retrofit"
        assert arr[8] == 10.0, "Dilution params follow CO flow"

    def test_to_array_excludes_co_flow_when_nan(self):
        """Test that CO flow is excluded for PSM 2.0."""
        settings = PSMSettings()
        settings.temp_growth_tube = 90.0
        settings.temp_saturator = 40.0
        settings.temp_inlet = 25.0
        settings.temp_heater = 85.0
        settings.temp_drainage = 30.0
        settings.cpc_inlet_flow = 0.3
        settings.inlet_flow_rate = 1.0
        settings.co_flow = nan  # PSM 2.0 doesn't have CO flow
        settings.dilution_parameters = [10.0, 2.0]

        arr = settings.to_array()

        # Dilution params should come right after inlet_flow (no CO flow)
        assert arr[7] == 10.0, "Index 7 should be first dilution param (no CO flow)"
        assert arr[8] == 2.0, "Index 8 should be second dilution param"

    def test_to_array_with_dilution_parameters(self):
        """Test that dilution parameters are appended."""
        settings = PSMSettings()
        settings.temp_growth_tube = 90.0
        settings.temp_saturator = 40.0
        settings.temp_inlet = 25.0
        settings.temp_heater = 85.0
        settings.temp_drainage = 30.0
        settings.cpc_inlet_flow = 0.3
        settings.inlet_flow_rate = 1.0
        settings.dilution_parameters = [10.0, 2.0, 1.5]

        arr = settings.to_array()

        assert 10.0 in arr
        assert 2.0 in arr
        assert 1.5 in arr

    def test_to_array_does_not_include_cpc_settings(self):
        """Test that CPC settings are NOT included (handled separately by data_logger)."""
        settings = PSMSettings()
        settings.temp_growth_tube = 90.0
        settings.temp_saturator = 40.0
        settings.temp_inlet = 25.0
        settings.temp_heater = 85.0
        settings.temp_drainage = 30.0
        settings.cpc_inlet_flow = 0.3
        settings.inlet_flow_rate = 1.0
        settings.cpc_settings = [1.0, 2.0, 3.0]  # Should NOT be in array

        arr = settings.to_array()

        # CPC settings should not be in the array
        assert 1.0 not in arr or arr[0] != 1.0  # Could be inlet_flow_rate coincidentally
        assert len(arr) == 7, "Should only have 7 base fields (no CPC settings)"


# ============================================================================
# Settings Factory Tests
# ============================================================================

class TestCreateDeviceSettings:
    """Test create_device_settings factory function."""

    def test_creates_cpc_settings(self):
        """Test creating CPC settings instance."""
        settings = create_device_settings(CPC)

        assert isinstance(settings, CPCSettings)

    def test_creates_psm_settings(self):
        """Test creating PSM settings instance."""
        settings = create_device_settings(PSM)

        assert isinstance(settings, PSMSettings)

    def test_creates_psm2_settings(self):
        """Test creating PSM 2.0 settings instance."""
        settings = create_device_settings(PSM2)

        assert isinstance(settings, PSMSettings)

    def test_returns_none_for_simple_devices(self):
        """Test that simple devices return None (no typed settings yet)."""
        assert create_device_settings(RHTP) is None
        assert create_device_settings(CO2_SENSOR) is None
        assert create_device_settings(ELECTROMETER) is None
        assert create_device_settings(EDILUTER) is None


# ============================================================================
# Mark Tests
# ============================================================================

pytestmark = pytest.mark.unit
