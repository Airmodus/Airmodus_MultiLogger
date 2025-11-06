"""
Device Data Classes - Typed data structures for all device types.

This module defines dataclasses for each device type, providing:
- Type safety with named fields instead of magic array indices
- Automatic array generation via to_array() for backward compatibility
- Clear documentation of each device's data structure
"""

from dataclasses import dataclass
from numpy import nan, isnan
from typing import Protocol, List
import math

class DeviceDataProtocol(Protocol):
    """Common interface all device data must implement."""
    def to_array(self) -> list:
        """Convert dataclass to array for legacy code compatibility."""
        ...


@dataclass
class CPCData:
    """Airmodus CPC data structure (14 fields in array, plus extra typed fields)."""
    concentration: float = nan # [0]
    dead_time: float = nan # [2]
    number_of_pulses: int = 0 # [1]
    temp_saturator: float = nan # [5]
    temp_condenser: float = nan # [7]
    temp_optics: float = nan # [6]
    temp_cabin: float = nan # [8]
    pres_inlet: float = nan # [9]
    pres_critical_orifice: float = nan # [10]
    pres_nozzle: float = nan # [11]
    pres_cabin: float = nan # [12]
    liquid_level: int = 0 # [14]
    pulse_ratio: float = nan # calculated from [3]
    total_errors: int = 0 # calculated from [12]
    status_hex: str = "" # [-1]
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
    concentration_psm: float = nan
    cut_off_diameter: float = nan
    saturator_flow: float = nan # [0] TODO is this correct
    excess_flow: float = nan # [1]
    temp_growth_tube: float = nan # [2]
    temp_saturator: float = nan # [3]
    temp_inlet: float = nan # [4]
    temp_heater: float = nan # [5]
    temp_drainage: float = nan # [6]
    temp_cabin: float = nan # [7]
    sat_flow_setpoint: float = nan # [8]
    pres_inlet: float = nan # [9]
    pres_inlet_saturator: float = nan # [10]
    pres_saturator_excess: float = nan # [11]
    pres_critical_orifice: float = nan # [12]
    vacuum_flow: float = nan  # PSM2 only [13]
    poly_correction: float = 0.0 # [14]
    scan_status: str = "" # [15]
    status_hex: str = "" # [-2]
    note_hex: str = "" # [-1]
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

    def to_array(self) -> List:
        """Convert to array in order expected by legacy code."""
        # Build base PSM data up to scan_status (indices 0-14 in legacy)
        base = [
            nan,  # [legacy 0: placeholder]
            nan,  # [1: placeholder]
            self.saturator_flow,  # [2: but aligned to legacy sat_flow at ~4; comments below use legacy-ish labels]
            self.excess_flow,  # [~5]
            self.temp_saturator,  # [~6, legacy 3]
            self.temp_growth_tube,  # [~7, legacy 2]
            self.temp_inlet,  # [~8, legacy 4]
            self.temp_drainage,  # [~9, legacy 6]
            self.temp_heater,  # [~10, legacy 5]
            self.temp_cabin,  # [~11, legacy 7]
            self.pres_inlet,  # [~12, legacy 9]
            self.pres_inlet_saturator,  # [~13, legacy 10]
            self.pres_saturator_excess,  # [~14, legacy 11]
            self.pres_critical_orifice,  # [~15, legacy 12]
            self.scan_status,  # [~16, legacy 14]
        ]
        
        # Conditionally include vacuum_flow only if it's not NaN (i.e., for PSM2)
        if not math.isnan(self.vacuum_flow):
            base.append(self.vacuum_flow)  # Inserted at legacy-equivalent 15
        # determine PSM status
        if int(self.status_hex, 16) == 0:
            psm_status = 1
        else:
            psm_status = 0
        # determine PSM note
        if int(self.note_hex, 16) == 0:
            psm_note = 1
        else:
            psm_note = 0

        base.append(psm_status)
        base.append(psm_note)
        
        # Append connected CPC data (14 fields, starting at legacy 17 for PSM1 or 18 for PSM2)
        cpc_data = [
            self.cpc_concentration,  # [legacy ~17/18]
            self.cpc_dilution_correction,  # [~18/19]
            self.cpc_temp_sat,  # [~19/20]
            self.cpc_temp_con,  # [~20/21]
            self.cpc_temp_opt,  # [~21/22]
            self.cpc_temp_cab,  # [~22/23]
            self.cpc_pres_crit,  # [~23/24]
            self.cpc_pres_noz,  # [~24/25]
            self.cpc_pres_in,  # [~25/26]
            self.cpc_liquid,  # [~26/27]
            self.cpc_pulses,  # [~27/28]
            self.cpc_dead_time,  # [~28/29]
            self.cpc_total_errors,  # [~29/30]
            self.cpc_status_hex,  # [~30/31]
        ]
        base.extend(cpc_data)
        base.append(self.status_hex)
        base.append(self.note_hex)
        
        return base
    


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
    optics_temp: float = nan
    saturator_temp: float = nan
    measured_cpc_flow: float = nan
    dead_time_correction: float = nan

    # From :SYST:PALL response
    nominal_inlet_flow: float = nan # nominal inlet flow rate
    opc_threshold: float = nan # OPC counter threshold voltage
    opc_threshold_2: float = nan # OPC counter threshold voltage 2
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
            self.optics_temp,              # [5]
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
    cpc_inlet_flow: float = nan

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

        # CPC settings are NOT included here - they're handled by PSMDataWriter.get_par_data()
        # which fetches and appends connected CPC settings when writing .par files

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
