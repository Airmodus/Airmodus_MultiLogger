"""
Device Data Classes - Typed data structures for all device types.

This module defines dataclasses for each device type, providing:
- Type safety with named fields instead of magic array indices
- Automatic array generation via to_array() for backward compatibility
- Clear documentation of each device's data structure
"""

from dataclasses import dataclass
from numpy import nan, isnan
from typing import Protocol


class DeviceDataProtocol(Protocol):
    """Common interface all device data must implement."""
    def to_array(self) -> list:
        """Convert dataclass to array for legacy code compatibility."""
        ...


@dataclass
class CPCData:
    """Airmodus CPC data structure (14 fields in array, plus extra typed fields)."""
    concentration: float = nan
    dead_time: float = nan
    number_of_pulses: int = 0
    temp_saturator: float = nan
    temp_condenser: float = nan
    temp_optics: float = nan
    temp_cabin: float = nan
    pres_inlet: float = nan
    pres_critical_orifice: float = nan
    pres_nozzle: float = nan
    pres_cabin: float = nan
    liquid_level: int = 0
    pulse_ratio: float = nan
    total_errors: int = 0
    status_hex: str = ""
    # Extra fields not in legacy array (for pulse quality analysis)
    laser_current: float = nan
    pulse_duration: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code (matches compile_cpc_data in utils.py)."""
        return [
            self.concentration,
            self.dead_time,
            self.number_of_pulses,
            self.temp_saturator,
            self.temp_condenser,
            self.temp_optics,
            self.temp_cabin,
            self.pres_inlet,
            self.pres_critical_orifice,
            self.pres_nozzle,
            self.pres_cabin,
            self.liquid_level,
            self.pulse_ratio,
            self.total_errors,
            self.status_hex
        ]


@dataclass
class PSMData:
    """Airmodus PSM data structure (33 fields for PSM, 34 for PSM2)."""
    saturator_flow: float = nan
    excess_flow: float = nan
    temp_growth_tube: float = nan
    temp_saturator: float = nan
    temp_inlet: float = nan
    temp_heater: float = nan
    temp_drainage: float = nan
    temp_cabin: float = nan
    sat_flow_setpoint: float = nan
    pres_inlet: float = nan
    cpc_inlet_flow: float = nan
    concentration_psm: float = nan
    pres_critical_orifice: float = nan
    vacuum_flow: float = nan  # PSM2 only
    poly_correction: float = 0.0
    scan_status: str = ""
    status_hex: str = ""
    note_hex: str = ""
    total_errors: int = 0
    liquid_errors: int = 0
    # Placeholders for connected CPC data (14 fields from CPC + 2 calculated fields)
    cpc_concentration: float = nan
    cpc_dilution_correction: float = nan  # Calculated dilution correction factor
    cpc_temp_sat: float = nan
    cpc_temp_con: float = nan
    cpc_temp_opt: float = nan
    cpc_temp_cab: float = nan
    cpc_pres_crit: float = nan
    cpc_pres_noz: float = nan
    cpc_pres_in: float = nan
    cpc_liquid: int = 0
    cpc_pulses: int = 0
    cpc_dead_time: float = nan
    cpc_total_errors: int = 0
    cpc_status_hex: str = ""

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [
            self.saturator_flow,              # 0
            self.excess_flow,                 # 1
            self.concentration_psm,           # 2
            self.temp_growth_tube,            # 3
            self.temp_saturator,              # 4
            self.temp_inlet,                  # 5
            self.temp_heater,                 # 6
            self.pres_inlet,                  # 7
            self.sat_flow_setpoint,           # 8
            self.pres_critical_orifice,       # 9
            self.cpc_inlet_flow,              # 10
            self.temp_drainage,               # 11
            self.temp_cabin,                  # 12
            self.poly_correction,             # 13
            self.scan_status,                 # 14
            self.vacuum_flow,                 # 15 - Always included (nan for Retrofit, value for PSM2)
            # Connected CPC data (14 fields) starts at index 16
            self.cpc_concentration,           # 16
            self.cpc_dilution_correction,     # 17
            self.cpc_temp_sat,                # 18
            self.cpc_temp_con,                # 19
            self.cpc_temp_opt,                # 20
            self.cpc_temp_cab,                # 21
            self.cpc_pres_crit,               # 22
            self.cpc_pres_noz,                # 23
            self.cpc_pres_in,                 # 24
            self.cpc_liquid,                  # 25
            self.cpc_pulses,                  # 26
            self.cpc_dead_time,               # 27
            self.cpc_total_errors,            # 28
            self.cpc_status_hex               # 29
        ]


@dataclass
class ElectrometerData:
    """Electrometer data structure (3 fields)."""
    voltage1: float = nan
    voltage2: float = nan
    voltage3: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [self.voltage1, self.voltage2, self.voltage3]


@dataclass
class CO2Data:
    """CO2 Sensor data structure (3 fields)."""
    co2: float = nan
    temperature: float = nan
    humidity: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [self.co2, self.temperature, self.humidity]


@dataclass
class RHTPData:
    """RHTP Sensor data structure (3 fields)."""
    humidity: float = nan
    temperature: float = nan
    pressure: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [self.humidity, self.temperature, self.pressure]


@dataclass
class AFMData:
    """AFM (Airmodus Flow Meter) data structure (5 fields)."""
    flow: float = nan
    saturator_flow: float = nan
    humidity: float = nan
    temperature: float = nan
    pressure: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [
            self.flow,
            self.saturator_flow,
            self.humidity,
            self.temperature,
            self.pressure
        ]


@dataclass
class EDiluterData:
    """eDiluter data structure (12 fields)."""
    status: str = ""
    pres1: float = nan
    pres2: float = nan
    temp1: float = nan
    temp2: float = nan
    temp3: float = nan
    temp4: float = nan
    temp5: float = nan
    temp6: float = nan
    df1: float = nan
    df2: float = nan
    df_total: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [
            self.status,
            self.pres1,
            self.pres2,
            self.temp1,
            self.temp2,
            self.temp3,
            self.temp4,
            self.temp5,
            self.temp6,
            self.df1,
            self.df2,
            self.df_total
        ]


@dataclass
class TSI_CPCData:
    """TSI CPC data structure (2 fields)."""
    concentration: float = nan
    error_hex: str = ""

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [self.concentration, self.error_hex]


@dataclass
class ExampleDeviceData:
    """Example Device data structure (1 field)."""
    random_value: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [self.random_value]


# Factory functions for creating device data instances
def create_device_data(device_type):
    """
    Create appropriate data object for device type.

    Args:
        device_type: Device type constant from config.py

    Returns:
        Appropriate DeviceData instance
    """
    from config import (CPC, PSM, PSM2, ELECTROMETER, CO2_SENSOR,
                       RHTP, AFM, EDILUTER, TSI_CPC, EXAMPLE_DEVICE)

    data_classes = {
        CPC: CPCData,
        PSM: PSMData,
        PSM2: PSMData,
        ELECTROMETER: ElectrometerData,
        CO2_SENSOR: CO2Data,
        RHTP: RHTPData,
        AFM: AFMData,
        EDILUTER: EDiluterData,
        TSI_CPC: TSI_CPCData,
        EXAMPLE_DEVICE: ExampleDeviceData
    }

    data_class = data_classes.get(device_type)
    if data_class is None:
        raise ValueError(f"Unknown device type: {device_type}")

    return data_class()


@dataclass
class CPCSettings:
    """
    CPC settings data structure.

    Based on compile_cpc_settings() format:
    [averaging_time, nominal_inlet_flow, measured_cpc_flow,
     temp_saturator, temp_condenser, temp_optics,
     autofill, opc_threshold, opc_threshold_2, water_removal,
     dead_time_correction, drain, k_factor, tau]
    """
    # From :SYST:PRNT response
    mode: float = nan
    autofill: float = nan
    drain: float = nan
    flow_adjustment: float = nan
    water_removal: float = nan
    averaging_time: float = nan
    condenser_temp: float = nan
    spare1: float = nan  # temp_optics in older firmware
    saturator_temp: float = nan
    spare2: float = nan
    spare3: float = nan
    spare4: float = nan
    spare5: float = nan

    # Additional fields from compile_cpc_settings (from pall array)
    nominal_inlet_flow: float = nan
    measured_cpc_flow: float = nan
    opc_threshold: float = nan
    opc_threshold_2: float = nan
    dead_time_correction: float = nan
    k_factor: float = nan
    tau: float = nan

    def to_array(self) -> list:
        """
        Convert to array matching compile_cpc_settings() format.
        [0] averaging_time, [1] nominal_inlet_flow, [2] measured_cpc_flow,
        [3] temp_saturator, [4] temp_condenser, [5] temp_optics,
        [6] autofill, [7] opc_threshold, [8] opc_threshold_2, [9] water_removal,
        [10] dead_time_correction, [11] drain, [12] k_factor, [13] tau
        """
        return [
            self.averaging_time,           # [0]
            self.nominal_inlet_flow,       # [1]
            self.measured_cpc_flow,        # [2]
            self.saturator_temp,           # [3]
            self.condenser_temp,           # [4]
            self.spare1,                   # [5] temp_optics
            self.autofill,                 # [6]
            self.opc_threshold,            # [7]
            self.opc_threshold_2,          # [8]
            self.water_removal,            # [9]
            self.dead_time_correction,     # [10]
            self.drain,                    # [11]
            self.k_factor,                 # [12]
            self.tau                       # [13]
        ]


@dataclass
class PSMSettings:
    """
    PSM settings data structure.

    Based on compile_psm_settings() format:
    [temp_growth_tube, temp_saturator, temp_inlet, temp_heater, temp_drainage,
     cpc_flow_rate, inlet_flow_rate, CO_flow?, dilution_params..., CPC_settings...]
    """
    # From :SYST:PRNT response
    mode: int = 0
    temp_growth_tube: float = nan
    temp_saturator: float = nan
    temp_inlet: float = nan
    temp_heater: float = nan
    temp_drainage: float = nan
    cpc_inlet_flow: float = nan  # This is stored as cpc_flow_rate in array

    # Additional fields for array generation
    inlet_flow_rate: float = nan  # Calculated and stored by plot_manager
    co_flow: float = nan  # CO flow (Retrofit PSM only)
    dilution_parameters: list = None  # Variable length, stored as list
    cpc_settings: list = None  # CPC settings (added in write_data)

    def __post_init__(self):
        """Initialize list fields if None."""
        if self.dilution_parameters is None:
            self.dilution_parameters = []
        if self.cpc_settings is None:
            self.cpc_settings = []

    def to_array(self) -> list:
        """
        Convert to array matching compile_psm_settings() format.
        [0-4] temps, [5] cpc_flow, [6] inlet_flow, [7?] CO_flow, [...] dilution
        Note: CPC settings are appended separately by data_logger.py (lines 288-310)
        """
        result = [
            self.temp_growth_tube,     # [0]
            self.temp_saturator,       # [1]
            self.temp_inlet,           # [2]
            self.temp_heater,          # [3]
            self.temp_drainage,        # [4]
            self.cpc_inlet_flow,       # [5] (cpc_flow_rate)
            self.inlet_flow_rate       # [6]
        ]

        # Add CO flow if not nan (indicates Retrofit PSM)
        if not (isinstance(self.co_flow, float) and isnan(self.co_flow)):
            result.append(self.co_flow)

        # Add dilution parameters if present
        if self.dilution_parameters:
            result.extend(self.dilution_parameters)

        # CPC settings are NOT included here - they're handled by data_logger
        # when writing .par files (see data_logger.py lines 288-310)

        return result


def create_device_settings(device_type):
    """
    Create appropriate settings object for device type.

    Args:
        device_type: Device type constant from config.py

    Returns:
        Appropriate DeviceSettings instance or None
    """
    from config import CPC, PSM, PSM2

    if device_type == CPC:
        return CPCSettings()
    elif device_type in [PSM, PSM2]:
        return PSMSettings()

    # Other devices don't have typed settings yet
    return None
