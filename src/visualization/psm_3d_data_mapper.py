"""
Maps PSM device data to visual properties for 3D visualization.

This module handles the translation of PSMData values to colors,
status indicators, and display information for the 3D model.
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional, List


# Color constants (RGB 0-1 range for OpenGL)
COLOR_GREEN = (0.15, 0.68, 0.38, 1.0)   # #27ae60 - Normal
COLOR_YELLOW = (0.95, 0.61, 0.07, 1.0)  # #f39c12 - Warning
COLOR_RED = (0.91, 0.30, 0.24, 1.0)     # #e74c3c - Error
COLOR_GRAY = (0.4, 0.4, 0.4, 1.0)       # No data / disconnected
COLOR_BLUE = (0.2, 0.6, 0.9, 1.0)       # Flow indicator
COLOR_HOUSING = (0.3, 0.3, 0.35, 0.3)   # Transparent housing


@dataclass
class ComponentInfo:
    """Information about a PSM component for visualization."""
    name: str
    display_name: str
    description: str
    data_field: Optional[str] = None
    setpoint_field: Optional[str] = None
    unit: str = ""
    nominal_value: Optional[float] = None
    tolerance: float = 0.5  # For determining yellow/green status
    error_bit: Optional[int] = None  # Bit index in STATUS_HEX
    category: str = "general"  # temperature, flow, pressure, liquid


# Component definitions for PSM device
PSM_COMPONENTS: Dict[str, ComponentInfo] = {
    # Temperature components
    'growth_tube': ComponentInfo(
        name='growth_tube',
        display_name='Growth Tube',
        description='Heated tube where particles grow by vapor condensation',
        data_field='temp_growth_tube',
        setpoint_field='set_growth_tube_temp',
        unit='°C',
        nominal_value=90.0,
        tolerance=1.0,
        error_bit=0,
        category='temperature'
    ),
    'saturator': ComponentInfo(
        name='saturator',
        display_name='Saturator',
        description='Chamber where air becomes saturated with working fluid vapor',
        data_field='temp_saturator',
        setpoint_field='set_saturator_temp',
        unit='°C',
        nominal_value=80.0,
        tolerance=1.0,
        error_bit=1,
        category='temperature'
    ),
    'inlet': ComponentInfo(
        name='inlet',
        display_name='Inlet',
        description='Sample inlet where aerosol enters the device',
        data_field='temp_inlet',
        setpoint_field='set_inlet_temp',
        unit='°C',
        nominal_value=25.0,
        tolerance=2.0,
        error_bit=2,
        category='temperature'
    ),
    'heater': ComponentInfo(
        name='heater',
        display_name='Heater Block',
        description='Heater that preheats the sample flow',
        data_field='temp_heater',
        setpoint_field='set_heater_temp',
        unit='°C',
        nominal_value=40.0,
        tolerance=2.0,
        error_bit=3,
        category='temperature'
    ),
    'drainage': ComponentInfo(
        name='drainage',
        display_name='Drainage',
        description='Drainage system for condensed working fluid',
        data_field='temp_drainage',
        setpoint_field='set_drainage_temp',
        unit='°C',
        nominal_value=30.0,
        tolerance=2.0,
        error_bit=4,
        category='temperature'
    ),
    'cabin': ComponentInfo(
        name='cabin',
        display_name='Cabin',
        description='Internal device enclosure temperature',
        data_field='temp_cabin',
        unit='°C',
        nominal_value=25.0,
        tolerance=10.0,
        category='temperature'
    ),

    # Flow components
    'mfc_saturator': ComponentInfo(
        name='mfc_saturator',
        display_name='Saturator Flow',
        description='Mass flow controller for saturator air flow',
        data_field='saturator_flow',
        setpoint_field='sat_flow_setpoint',
        unit='lpm',
        nominal_value=1.0,
        tolerance=0.05,
        error_bit=2,
        category='flow'
    ),
    'mfc_excess': ComponentInfo(
        name='mfc_excess',
        display_name='Excess Flow',
        description='Mass flow controller for excess air removal',
        data_field='excess_flow',
        unit='lpm',
        nominal_value=0.5,
        tolerance=0.1,
        error_bit=8,
        category='flow'
    ),
    'mfc_vacuum': ComponentInfo(
        name='mfc_vacuum',
        display_name='Vacuum Flow',
        description='Mass flow controller for vacuum pump (PSM 2.0 only)',
        data_field='vacuum_flow',
        unit='lpm',
        nominal_value=3.0,
        tolerance=0.2,
        category='flow'
    ),

    # Pressure components
    'pressure_inlet': ComponentInfo(
        name='pressure_inlet',
        display_name='Inlet Pressure',
        description='Pressure at the sample inlet',
        data_field='pres_inlet',
        unit='kPa',
        nominal_value=101.3,
        tolerance=5.0,
        error_bit=7,
        category='pressure'
    ),
    'pressure_saturator': ComponentInfo(
        name='pressure_saturator',
        display_name='Saturator Pressure',
        description='Pressure at inlet-saturator junction',
        data_field='pres_inlet_saturator',
        unit='kPa',
        nominal_value=100.0,
        tolerance=5.0,
        category='pressure'
    ),
    'pressure_excess': ComponentInfo(
        name='pressure_excess',
        display_name='Excess Pressure',
        description='Pressure at saturator-excess junction',
        data_field='pres_saturator_excess',
        unit='kPa',
        nominal_value=99.0,
        tolerance=5.0,
        category='pressure'
    ),
    'pressure_critical': ComponentInfo(
        name='pressure_critical',
        display_name='Critical Orifice',
        description='Pressure at critical orifice (flow limiting)',
        data_field='pres_critical_orifice',
        unit='kPa',
        nominal_value=50.0,
        tolerance=10.0,
        error_bit=12,
        category='pressure'
    ),

    # Liquid components
    'liquid_saturator': ComponentInfo(
        name='liquid_saturator',
        display_name='Saturator Liquid',
        description='Working fluid level in saturator',
        category='liquid'
    ),
    'liquid_drain': ComponentInfo(
        name='liquid_drain',
        display_name='Drain Reservoir',
        description='Collected condensate in drain reservoir',
        category='liquid'
    ),

    # Housing (visual only)
    'housing': ComponentInfo(
        name='housing',
        display_name='Device Housing',
        description='External enclosure of the PSM device',
        category='general'
    ),
}


class PSMDataMapper:
    """Maps PSM sensor data to 3D visual properties."""

    def __init__(self, is_psm2: bool = False):
        """
        Initialize the data mapper.

        Args:
            is_psm2: True if this is PSM 2.0, False for Retrofit
        """
        self.is_psm2 = is_psm2
        self._error_bits = 0
        self._note_bits = 0

    def update_status(self, status_hex: str, note_hex: str) -> None:
        """
        Update internal status from hex strings.

        Args:
            status_hex: STATUS_HEX string from PSM (e.g., "0000")
            note_hex: NOTE_HEX string from PSM
        """
        try:
            self._error_bits = int(status_hex, 16) if status_hex else 0
        except ValueError:
            self._error_bits = 0

        try:
            self._note_bits = int(note_hex, 16) if note_hex else 0
        except ValueError:
            self._note_bits = 0

    def get_component_color(self, component_name: str,
                           psm_data: Optional[object] = None) -> Tuple[float, float, float, float]:
        """
        Get the color for a component based on its current status.

        Args:
            component_name: Name of the component (e.g., 'growth_tube')
            psm_data: PSMData object with current values

        Returns:
            RGBA tuple (0-1 range) for the component color
        """
        if component_name not in PSM_COMPONENTS:
            return COLOR_GRAY

        info = PSM_COMPONENTS[component_name]

        # Housing is always transparent gray
        if component_name == 'housing':
            return COLOR_HOUSING

        # Check for error bit first (highest priority)
        if info.error_bit is not None and self._error_bits & (1 << info.error_bit):
            return COLOR_RED

        # If no data, return gray
        if psm_data is None or info.data_field is None:
            return COLOR_GRAY

        # Get current value
        try:
            current_value = getattr(psm_data, info.data_field, None)
            if current_value is None:
                return COLOR_GRAY
        except AttributeError:
            return COLOR_GRAY

        # Check against setpoint or nominal value
        target = info.nominal_value
        if info.setpoint_field and psm_data:
            try:
                setpoint = getattr(psm_data, info.setpoint_field, None)
                if setpoint is not None:
                    target = setpoint
            except AttributeError:
                pass

        if target is None:
            return COLOR_GREEN  # No target to compare, assume OK

        # Calculate deviation
        deviation = abs(current_value - target)

        if deviation <= info.tolerance:
            return COLOR_GREEN
        elif deviation <= info.tolerance * 3:
            return COLOR_YELLOW
        else:
            return COLOR_RED

    def get_component_value(self, component_name: str,
                           psm_data: Optional[object] = None) -> Optional[float]:
        """
        Get the current value for a component.

        Args:
            component_name: Name of the component
            psm_data: PSMData object with current values

        Returns:
            Current value or None if not available
        """
        if component_name not in PSM_COMPONENTS:
            return None

        info = PSM_COMPONENTS[component_name]
        if info.data_field is None or psm_data is None:
            return None

        try:
            return getattr(psm_data, info.data_field, None)
        except AttributeError:
            return None

    def get_component_status(self, component_name: str,
                            psm_data: Optional[object] = None) -> str:
        """
        Get a status string for a component.

        Args:
            component_name: Name of the component
            psm_data: PSMData object with current values

        Returns:
            Status string: "OK", "Warning", "Error", or "No Data"
        """
        if component_name not in PSM_COMPONENTS:
            return "Unknown"

        info = PSM_COMPONENTS[component_name]

        # Check error bit
        if info.error_bit is not None and self._error_bits & (1 << info.error_bit):
            return "Error"

        # Check value against tolerance
        if psm_data is None or info.data_field is None:
            return "No Data"

        try:
            current_value = getattr(psm_data, info.data_field, None)
            if current_value is None:
                return "No Data"
        except AttributeError:
            return "No Data"

        target = info.nominal_value
        if info.setpoint_field and psm_data:
            try:
                setpoint = getattr(psm_data, info.setpoint_field, None)
                if setpoint is not None:
                    target = setpoint
            except AttributeError:
                pass

        if target is None:
            return "OK"

        deviation = abs(current_value - target)

        if deviation <= info.tolerance:
            return "OK"
        elif deviation <= info.tolerance * 3:
            return "Warning"
        else:
            return "Error"

    def get_liquid_state(self) -> Dict[str, bool]:
        """
        Get the liquid system state from note_hex.

        Returns:
            Dictionary with autofill, drain, drying states
        """
        return {
            'autofill': bool(self._note_bits & 0x01),
            'drain': bool(self._note_bits & 0x02),
            'drying': bool(self._note_bits & 0x04),
        }

    def get_all_component_names(self) -> List[str]:
        """Get list of all component names."""
        names = list(PSM_COMPONENTS.keys())
        # Remove vacuum MFC if not PSM2
        if not self.is_psm2 and 'mfc_vacuum' in names:
            names.remove('mfc_vacuum')
        return names

    def get_component_info(self, component_name: str) -> Optional[ComponentInfo]:
        """Get ComponentInfo for a given component name."""
        return PSM_COMPONENTS.get(component_name)
