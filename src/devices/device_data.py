"""
Device Data Classes - Typed data structures for all device types.

This module defines dataclasses for each device type, providing:
- Type safety with named fields instead of magic array indices
- Automatic array generation via to_array() for backward compatibility
- Clear documentation of each device's data structure
- Device configuration dataclasses (replacing parameter tree)
"""

from dataclasses import dataclass, field, asdict
from numpy import nan, isnan
from typing import Protocol, List, Optional, Dict, Any
import math
from config import (CPC, PSM, PSM2, ELECTROMETER, CO2_SENSOR, RHTP,
                    AFM, EDILUTER, TSI_CPC, AFC, EXAMPLE_DEVICE)

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
            self.laser_current,       # [12] - laser current for laser power display
            self.pulse_ratio,         # [13] - pulse ratio for pulse quality display
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
            self.concentration_psm,  # [0: Concentration from PSM (dilution + poly corrected)]
            nan,  # [1: Cut-off diameter placeholder - not calculated]
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
        # determine PSM status (handle empty string)
        if not self.status_hex or int(self.status_hex, 16) == 0:
            psm_status = 1
        else:
            psm_status = 0
        # determine PSM note (handle empty string)
        if not self.note_hex or int(self.note_hex, 16) == 0:
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
    standard_flow: float = nan
    humidity: float = nan
    temperature: float = nan
    pressure: float = nan

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [
            self.flow,
            self.standard_flow,
            self.humidity,
            self.temperature,
            self.pressure
        ]


@dataclass
class AFCData:
    """AFC (Airmodus Flow Controller) data structure (4 fields)."""
    flow: float = nan               # slm (standard liters per minute)
    average_flow: float = nan       # slm average (10 seconds)
    temperature: float = nan        # °C
    flow_setpoint: float = nan      # slm setpoint
    error_status: int = 0           # 0 = no error, 1 = error

    def to_array(self) -> list:
        """Convert to array in order expected by legacy code."""
        return [
            self.flow,
            self.average_flow,
            self.temperature,
            self.flow_setpoint,
            self.error_status
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

    data_classes = {
        CPC: CPCData,
        PSM: PSMData,
        ELECTROMETER: ElectrometerData,
        CO2_SENSOR: CO2Data,
        RHTP: RHTPData,
        AFM: AFMData,
        EDILUTER: EDiluterData,
        TSI_CPC: TSI_CPCData,
        AFC: AFCData,
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
    calibration_file_path: str = ""  # Path to calibration file for contour plot

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

    if device_type == CPC:
        return CPCSettings()
    elif device_type == PSM:
        return PSMSettings()

    # Other devices don't have typed settings yet
    return None


# ============================================================================
# Configuration Dataclasses (replacing parameter tree)
# ============================================================================

@dataclass
class DataSettings:
    """Global data logging settings."""
    file_path: str = ""
    file_tag: str = ""
    save_data: bool = False
    generate_daily_files: bool = False
    resume_on_startup: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DataSettings':
        """Deserialize from dictionary."""
        return cls(**data)


@dataclass
class PlotSettings:
    """Global plot display settings."""
    follow: bool = True
    time_window_s: float = 600.0  # 10 minutes default
    autoscale_y: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlotSettings':
        """Deserialize from dictionary."""
        return cls(**data)


@dataclass
class DeviceConfig:
    """
    Device configuration (connection info + device-specific settings).

    This replaces the parameter tree structure for device configuration,
    providing a single source of truth for all device config data.
    """
    # Connection configuration
    device_id: int
    device_type: int  # From config.py constants (CPC, PSM, etc.)
    device_type_name: str  # Human-readable name ("CPC", "PSM", etc.)
    com_port: str = ""
    serial_number: str = ""
    device_nickname: str = ""

    # Plot configuration
    plot_to_main: bool = True

    # Device-specific settings (CPCSettings, PSMSettings, etc.)
    # Use None as default for devices without typed settings
    settings: Optional[Any] = None  # Will be CPCSettings, PSMSettings, etc.

    # Device-specific parameters (stored as dict for flexibility)
    # Examples: {"10_hz": True, "connected_cpc_serial": "12345"}
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        result = {
            'device_id': self.device_id,
            'device_type': self.device_type,
            'device_type_name': self.device_type_name,
            'com_port': self.com_port,
            'serial_number': self.serial_number,
            'device_nickname': self.device_nickname,
            'plot_to_main': self.plot_to_main,
            'extra_params': self.extra_params,
        }

        # Serialize settings if present
        if self.settings is not None:
            result['settings'] = asdict(self.settings)
            result['settings_type'] = type(self.settings).__name__
        else:
            result['settings'] = None
            result['settings_type'] = None

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeviceConfig':
        """Deserialize from dictionary."""
        # Extract settings and reconstruct typed settings object
        settings_data = data.get('settings')
        settings_type = data.get('settings_type')
        settings_obj = None

        if settings_data and settings_type:
            # Reconstruct the appropriate settings dataclass
            if settings_type == 'CPCSettings':
                settings_obj = CPCSettings(**settings_data)
            elif settings_type == 'PSMSettings':
                # Handle list fields properly
                settings_obj = PSMSettings(**settings_data)

        # Create config without settings-related keys
        config_data = {k: v for k, v in data.items()
                      if k not in ('settings', 'settings_type')}
        config_data['settings'] = settings_obj

        # Convert old integer COM port format to string format (Windows)
        # Old configs stored port as int (e.g., 5), new format uses string (e.g., "COM5")
        raw_port = config_data.get('com_port', '')
        if isinstance(raw_port, int) and raw_port > 0:
            config_data['com_port'] = f"COM{raw_port}"

        # Migrate PSM2 (7) to PSM (2) - version now determined by firmware
        from config import PSM
        if config_data.get('device_type') == 7:  # PSM2 legacy constant
            config_data['device_type'] = PSM
            config_data['device_type_name'] = 'PSM'

        # Normalize PSM device_type_name (old configs may have "PSM Retrofit" or "PSM 2.0")
        if config_data.get('device_type') == PSM:
            if config_data.get('device_type_name') in ('PSM Retrofit', 'PSM 2.0'):
                config_data['device_type_name'] = 'PSM'

        return cls(**config_data)


@dataclass
class AppConfig:
    """
    Complete application configuration.

    Single source of truth for all configuration data,
    replacing the parameter tree system.
    """
    data_settings: DataSettings = field(default_factory=DataSettings)
    plot_settings: PlotSettings = field(default_factory=PlotSettings)
    devices: List[DeviceConfig] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            'data_settings': self.data_settings.to_dict(),
            'plot_settings': self.plot_settings.to_dict(),
            'devices': [device.to_dict() for device in self.devices]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """Deserialize from dictionary."""
        return cls(
            data_settings=DataSettings.from_dict(data.get('data_settings', {})),
            plot_settings=PlotSettings.from_dict(data.get('plot_settings', {})),
            devices=[DeviceConfig.from_dict(d) for d in data.get('devices', [])]
        )

    def save_to_file(self, filepath: str) -> None:
        """Save configuration to JSON file."""
        import json
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> 'AppConfig':
        """Load configuration from JSON file."""
        import json
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
