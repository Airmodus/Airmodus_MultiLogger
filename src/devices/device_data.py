"""
Data classes for device measurements and settings.

These dataclasses provide type-safe storage for device state, replacing
the dictionary-based storage in DataHolder. Each device type has its own
data class with properly typed fields.
"""

from dataclasses import dataclass, field
from numpy import nan, full
from typing import Optional, List


@dataclass
class CPCData:
    """CPC measurement data."""
    concentration: float = nan
    dead_time: float = nan
    temp_saturator: float = nan
    temp_condenser: float = nan
    temp_optics: float = nan
    temp_cabin: float = nan
    pres_inlet: float = nan
    pres_critical_orifice: float = nan
    pres_nozzle: float = nan
    pres_cabin: float = nan
    liquid_level: int = 0
    laser_current: float = nan
    pulse_duration: float = nan
    pulse_ratio: float = nan
    status_hex: str = "0"
    total_errors: int = 0

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [
            self.concentration, self.dead_time, self.temp_saturator,
            self.temp_condenser, self.temp_optics, self.temp_cabin,
            self.pres_inlet, self.pres_critical_orifice, self.pres_nozzle,
            self.pres_cabin, self.liquid_level, self.laser_current,
            self.pulse_duration, self.pulse_ratio, self.status_hex
        ]


@dataclass
class CPCSettings:
    """CPC settings data."""
    mode: int = 0
    autofill: int = 0
    drain: int = 0
    flow_adjustment: int = 0
    water_removal: int = 0
    averaging_time: float = nan
    condenser_temp: float = nan
    spare1: float = nan
    saturator_temp: float = nan
    spare2: float = nan
    spare3: float = nan
    spare4: float = nan
    spare5: float = nan

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [
            self.mode, self.autofill, self.drain, self.flow_adjustment,
            self.water_removal, self.averaging_time, self.condenser_temp,
            self.spare1, self.saturator_temp, self.spare2, self.spare3,
            self.spare4, self.spare5
        ]


@dataclass
class PSMData:
    """PSM measurement data (both Retrofit and 2.0)."""
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
    poly_correction: float = nan
    scan_status: str = "9"  # 0-7 = valid, 9 = undefined
    status_hex: str = "0"
    note_hex: str = "0"
    cpc_status_hex: str = "0"
    total_errors: int = 0
    liquid_errors: int = 0
    # Additional calculated fields
    dilution: float = nan
    cpc_concentration: float = nan

    def to_list(self, psm_version):
        """Convert to list format for backward compatibility.

        Args:
            psm_version: PSM or PSM2 constant
        """
        from config import PSM2

        base_list = [
            self.saturator_flow, self.excess_flow, self.temp_growth_tube,
            self.temp_saturator, self.temp_inlet, self.temp_heater,
            self.temp_drainage, self.temp_cabin, self.sat_flow_setpoint,
            self.pres_inlet, self.cpc_inlet_flow, self.concentration_psm,
            self.pres_critical_orifice
        ]

        if psm_version == PSM2:
            base_list.append(self.vacuum_flow)

        # Add string fields at end
        base_list.extend([
            self.poly_correction, self.scan_status, self.status_hex,
            self.note_hex, self.cpc_status_hex, self.dilution,
            self.cpc_concentration
        ])

        return base_list


@dataclass
class PSMSettings:
    """PSM settings data."""
    mode: int = 0
    temp_growth_tube: float = nan
    temp_saturator: float = nan
    temp_inlet: float = nan
    temp_heater: float = nan
    temp_drainage: float = nan
    cpc_inlet_flow: float = nan

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [
            self.mode, self.temp_growth_tube, self.temp_saturator,
            self.temp_inlet, self.temp_heater, self.temp_drainage,
            self.cpc_inlet_flow
        ]


@dataclass
class EDiluterData:
    """eDiluter measurement data."""
    status: str = "nan"
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

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [
            self.status, self.pres1, self.pres2, self.temp1, self.temp2,
            self.temp3, self.temp4, self.temp5, self.temp6, self.df1,
            self.df2, self.df_total
        ]


@dataclass
class RHTPData:
    """RHTP sensor measurement data."""
    humidity: float = nan
    temperature: float = nan
    pressure: float = nan

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [self.humidity, self.temperature, self.pressure]


@dataclass
class CO2Data:
    """CO2 sensor measurement data."""
    co2: float = nan
    temperature: float = nan
    humidity: float = nan

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [self.co2, self.temperature, self.humidity]


@dataclass
class AFMData:
    """AFM device measurement data."""
    flow: float = nan
    saturator_flow: float = nan
    humidity: float = nan
    temperature: float = nan
    pressure: float = nan

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [self.flow, self.saturator_flow, self.humidity,
                self.temperature, self.pressure]


@dataclass
class ElectrometerData:
    """Electrometer measurement data."""
    voltage1: float = nan
    voltage2: float = nan
    voltage3: float = nan

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [self.voltage1, self.voltage2, self.voltage3]


@dataclass
class TSI_CPCData:
    """TSI CPC measurement data."""
    concentration: float = nan
    error_hex: str = "0"

    def to_list(self):
        """Convert to list format for backward compatibility."""
        return [self.concentration, self.error_hex]


@dataclass
class PulseAnalysisState:
    """CPC pulse analysis state."""
    index: Optional[int] = None  # None = not running, 0-N = progress
    values: List[tuple] = field(default_factory=list)  # [(duration, threshold), ...]

    def is_running(self):
        """Check if pulse analysis is in progress."""
        return self.index is not None

    def reset(self):
        """Reset analysis state."""
        self.index = None
        self.values.clear()


# Factory function to create appropriate data object for device type
def create_device_data(device_type):
    """Create appropriate data object for given device type.

    Args:
        device_type: Device type constant from config

    Returns:
        Data object instance
    """
    from config import (CPC, PSM, PSM2, ELECTROMETER, CO2_SENSOR,
                       RHTP, AFM, EDILUTER, TSI_CPC)

    if device_type == CPC:
        return CPCData()
    elif device_type in [PSM, PSM2]:
        return PSMData()
    elif device_type == ELECTROMETER:
        return ElectrometerData()
    elif device_type == CO2_SENSOR:
        return CO2Data()
    elif device_type == RHTP:
        return RHTPData()
    elif device_type == AFM:
        return AFMData()
    elif device_type == EDILUTER:
        return EDiluterData()
    elif device_type == TSI_CPC:
        return TSI_CPCData()
    else:
        # Fallback: generic data with 15 NaN values
        return full(15, nan).tolist()


def create_device_settings(device_type):
    """Create appropriate settings object for given device type.

    Args:
        device_type: Device type constant from config

    Returns:
        Settings object instance or None if device doesn't have settings
    """
    from config import CPC, PSM, PSM2

    if device_type == CPC:
        return CPCSettings()
    elif device_type in [PSM, PSM2]:
        return PSMSettings()
    else:
        return None


__all__ = [
    'CPCData', 'CPCSettings', 'PSMData', 'PSMSettings',
    'EDiluterData', 'RHTPData', 'CO2Data', 'AFMData',
    'ElectrometerData', 'TSI_CPCData', 'PulseAnalysisState',
    'create_device_data', 'create_device_settings'
]
