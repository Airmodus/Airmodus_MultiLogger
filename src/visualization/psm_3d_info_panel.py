"""
Info panel widget for displaying selected component details.

Shows component name, current values, status, and diagnostics tips
when a component is clicked in the 3D view.
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QGridLayout, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .psm_3d_data_mapper import PSMDataMapper, PSM_COMPONENTS, ComponentInfo


# Style constants matching existing app theme
STYLE_PANEL = """
    QWidget {
        background-color: #2b2b2b;
        color: #ffffff;
    }
    QGroupBox {
        border: 1px solid #555;
        border-radius: 4px;
        margin-top: 12px;
        padding-top: 8px;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
    QLabel {
        color: #ffffff;
    }
"""

STYLE_VALUE_OK = "color: #27ae60; font-weight: bold;"
STYLE_VALUE_WARNING = "color: #f39c12; font-weight: bold;"
STYLE_VALUE_ERROR = "color: #e74c3c; font-weight: bold;"
STYLE_VALUE_NODATA = "color: #888888;"


class PSM3DInfoPanel(QWidget):
    """
    Panel showing detailed information about a selected PSM component.

    Displays:
    - Component name and description
    - Current value vs setpoint
    - Status indicator
    - Diagnostic tips when errors detected
    """

    def __init__(self, data_mapper: PSMDataMapper, parent: Optional[QWidget] = None):
        """
        Initialize the info panel.

        Args:
            data_mapper: PSMDataMapper instance for getting component info
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.data_mapper = data_mapper
        self._current_component: Optional[str] = None
        self._psm_data = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        self.setStyleSheet(STYLE_PANEL)
        self.setMinimumWidth(250)
        self.setMaximumWidth(350)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Component header
        self.header_label = QLabel("Select a component")
        self.header_label.setFont(QFont("", 14, QFont.Bold))
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        # Description
        self.description_label = QLabel("")
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout.addWidget(self.description_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #555;")
        layout.addWidget(separator)

        # Values group
        values_group = QGroupBox("Current Values")
        values_layout = QGridLayout(values_group)
        values_layout.setSpacing(6)

        # Current value
        values_layout.addWidget(QLabel("Value:"), 0, 0)
        self.value_label = QLabel("--")
        self.value_label.setStyleSheet(STYLE_VALUE_NODATA)
        values_layout.addWidget(self.value_label, 0, 1)

        # Setpoint
        values_layout.addWidget(QLabel("Setpoint:"), 1, 0)
        self.setpoint_label = QLabel("--")
        values_layout.addWidget(self.setpoint_label, 1, 1)

        # Deviation
        values_layout.addWidget(QLabel("Deviation:"), 2, 0)
        self.deviation_label = QLabel("--")
        values_layout.addWidget(self.deviation_label, 2, 1)

        layout.addWidget(values_group)

        # Status group
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel("No Data")
        self.status_label.setFont(QFont("", 12, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(STYLE_VALUE_NODATA)
        status_layout.addWidget(self.status_label)

        layout.addWidget(status_group)

        # Diagnostics group (shown when there's an error)
        self.diagnostics_group = QGroupBox("Diagnostics")
        diagnostics_layout = QVBoxLayout(self.diagnostics_group)

        self.diagnostics_label = QLabel("")
        self.diagnostics_label.setWordWrap(True)
        self.diagnostics_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        diagnostics_layout.addWidget(self.diagnostics_label)

        layout.addWidget(self.diagnostics_group)
        self.diagnostics_group.setVisible(False)

        # Spacer
        layout.addStretch()

        # Instructions at bottom
        instructions = QLabel("Click on components in the 3D view\nto see their details here.")
        instructions.setAlignment(Qt.AlignCenter)
        instructions.setStyleSheet("color: #666666; font-size: 10px;")
        layout.addWidget(instructions)

    def set_component(self, component_name: Optional[str]) -> None:
        """
        Set the currently selected component.

        Args:
            component_name: Name of the component, or None to clear
        """
        self._current_component = component_name
        self._update_display()

    def update_data(self, psm_data) -> None:
        """
        Update with new PSM data.

        Args:
            psm_data: PSMData object with current values
        """
        self._psm_data = psm_data
        self._update_display()

    def _update_display(self) -> None:
        """Update the panel display with current component and data."""
        if self._current_component is None:
            self.header_label.setText("Select a component")
            self.description_label.setText("")
            self.value_label.setText("--")
            self.value_label.setStyleSheet(STYLE_VALUE_NODATA)
            self.setpoint_label.setText("--")
            self.deviation_label.setText("--")
            self.status_label.setText("No Selection")
            self.status_label.setStyleSheet(STYLE_VALUE_NODATA)
            self.diagnostics_group.setVisible(False)
            return

        # Get component info
        info = self.data_mapper.get_component_info(self._current_component)
        if info is None:
            self.header_label.setText(self._current_component)
            self.description_label.setText("Unknown component")
            return

        # Update header
        self.header_label.setText(info.display_name)
        self.description_label.setText(info.description)

        # Update values
        value = self.data_mapper.get_component_value(self._current_component, self._psm_data)

        if value is not None:
            self.value_label.setText(f"{value:.2f} {info.unit}")
        else:
            self.value_label.setText("--")

        # Get setpoint
        setpoint = info.nominal_value
        if info.setpoint_field and self._psm_data:
            try:
                sp = getattr(self._psm_data, info.setpoint_field, None)
                if sp is not None:
                    setpoint = sp
            except AttributeError:
                pass

        if setpoint is not None:
            self.setpoint_label.setText(f"{setpoint:.2f} {info.unit}")
        else:
            self.setpoint_label.setText("--")

        # Calculate and show deviation
        if value is not None and setpoint is not None:
            deviation = value - setpoint
            self.deviation_label.setText(f"{deviation:+.2f} {info.unit}")

            if abs(deviation) <= info.tolerance:
                self.deviation_label.setStyleSheet(STYLE_VALUE_OK)
            elif abs(deviation) <= info.tolerance * 3:
                self.deviation_label.setStyleSheet(STYLE_VALUE_WARNING)
            else:
                self.deviation_label.setStyleSheet(STYLE_VALUE_ERROR)
        else:
            self.deviation_label.setText("--")
            self.deviation_label.setStyleSheet(STYLE_VALUE_NODATA)

        # Update status
        status = self.data_mapper.get_component_status(self._current_component, self._psm_data)

        self.status_label.setText(status)
        if status == "OK":
            self.status_label.setStyleSheet(STYLE_VALUE_OK + "font-size: 14px;")
            self.value_label.setStyleSheet(STYLE_VALUE_OK)
        elif status == "Warning":
            self.status_label.setStyleSheet(STYLE_VALUE_WARNING + "font-size: 14px;")
            self.value_label.setStyleSheet(STYLE_VALUE_WARNING)
        elif status == "Error":
            self.status_label.setStyleSheet(STYLE_VALUE_ERROR + "font-size: 14px;")
            self.value_label.setStyleSheet(STYLE_VALUE_ERROR)
        else:
            self.status_label.setStyleSheet(STYLE_VALUE_NODATA + "font-size: 14px;")
            self.value_label.setStyleSheet(STYLE_VALUE_NODATA)

        # Show diagnostics if error
        if status == "Error":
            self._show_diagnostics(info)
        else:
            self.diagnostics_group.setVisible(False)

    def _show_diagnostics(self, info: ComponentInfo) -> None:
        """Show diagnostic tips for the component."""
        tips = self._get_diagnostic_tips(info)
        if tips:
            self.diagnostics_label.setText("\n".join(f"• {tip}" for tip in tips))
            self.diagnostics_group.setVisible(True)
        else:
            self.diagnostics_group.setVisible(False)

    def _get_diagnostic_tips(self, info: ComponentInfo) -> list:
        """Get diagnostic tips based on component type and status."""
        tips = []

        if info.category == 'temperature':
            tips = [
                "Check heater connection and power",
                "Verify temperature setpoint is correct",
                "Check for obstructions in airflow",
                "Inspect thermal insulation",
                "Allow device to stabilize (may take 10-15 min)"
            ]
        elif info.category == 'flow':
            tips = [
                "Check MFC connection and calibration",
                "Verify tubing connections are secure",
                "Check for leaks in flow path",
                "Ensure inlet is not blocked",
                "Verify vacuum pump is running (PSM 2.0)"
            ]
        elif info.category == 'pressure':
            tips = [
                "Check pressure sensor connection",
                "Verify tubing connections",
                "Check for blockages or kinks",
                "Ensure proper sealing",
                "Compare with expected operating pressure"
            ]
        elif info.category == 'liquid':
            tips = [
                "Check liquid reservoir level",
                "Verify autofill system is working",
                "Check drain valve operation",
                "Inspect for leaks",
                "Verify liquid bottle connections"
            ]

        return tips[:4]  # Limit to 4 tips


class PSM3DStatusBar(QWidget):
    """
    Compact status bar showing overall PSM status.

    Shows quick status indicators for all major systems.
    """

    def __init__(self, data_mapper: PSMDataMapper, parent: Optional[QWidget] = None):
        """
        Initialize the status bar.

        Args:
            data_mapper: PSMDataMapper instance
            parent: Optional parent widget
        """
        super().__init__(parent)
        self.data_mapper = data_mapper
        self._psm_data = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the status bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(12)

        # Temperature status
        self.temp_indicator = self._create_indicator("Temps")
        layout.addWidget(self.temp_indicator)

        # Flow status
        self.flow_indicator = self._create_indicator("Flows")
        layout.addWidget(self.flow_indicator)

        # Pressure status
        self.pressure_indicator = self._create_indicator("Pressure")
        layout.addWidget(self.pressure_indicator)

        # Liquid status
        self.liquid_indicator = self._create_indicator("Liquid")
        layout.addWidget(self.liquid_indicator)

        layout.addStretch()

    def _create_indicator(self, label: str) -> QWidget:
        """Create a status indicator widget."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        dot = QLabel("●")
        dot.setStyleSheet("color: #888888;")
        layout.addWidget(dot)

        text = QLabel(label)
        text.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout.addWidget(text)

        widget.dot = dot
        return widget

    def update_status(self, psm_data) -> None:
        """Update all status indicators."""
        self._psm_data = psm_data

        # Check temperature components
        temp_ok = self._check_category_status('temperature')
        self._set_indicator_status(self.temp_indicator, temp_ok)

        # Check flow components
        flow_ok = self._check_category_status('flow')
        self._set_indicator_status(self.flow_indicator, flow_ok)

        # Check pressure components
        pressure_ok = self._check_category_status('pressure')
        self._set_indicator_status(self.pressure_indicator, pressure_ok)

        # Check liquid state
        liquid_state = self.data_mapper.get_liquid_state()
        liquid_ok = "OK" if not any([
            liquid_state.get('drain', False),
            liquid_state.get('drying', False)
        ]) else "Warning"
        self._set_indicator_status(self.liquid_indicator, liquid_ok)

    def _check_category_status(self, category: str) -> str:
        """Check status of all components in a category."""
        worst_status = "OK"

        for name, info in PSM_COMPONENTS.items():
            if info.category == category:
                status = self.data_mapper.get_component_status(name, self._psm_data)
                if status == "Error":
                    return "Error"
                elif status == "Warning" and worst_status == "OK":
                    worst_status = "Warning"

        return worst_status

    def _set_indicator_status(self, indicator: QWidget, status: str) -> None:
        """Set the visual status of an indicator."""
        if status == "OK":
            indicator.dot.setStyleSheet("color: #27ae60;")
        elif status == "Warning":
            indicator.dot.setStyleSheet("color: #f39c12;")
        elif status == "Error":
            indicator.dot.setStyleSheet("color: #e74c3c;")
        else:
            indicator.dot.setStyleSheet("color: #888888;")
