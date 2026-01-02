"""
PSM 3D Visualization Tab.

Provides an interactive 3D view of the PSM device with live data visualization,
clickable components, and diagnostic information.
"""

import logging
from typing import Optional, Dict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QToolBar, QLabel, QFrame, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
import numpy as np

# Try to import OpenGL components
try:
    import pyqtgraph.opengl as gl
    from OpenGL.GL import GL_DEPTH_TEST, glEnable
    HAS_OPENGL = True
except ImportError as e:
    HAS_OPENGL = False
    gl = None
    logging.warning(f"OpenGL not available for 3D visualization: {e}")

from visualization.psm_3d_model import PSMModelBuilder, PSM_FLOW_CONNECTIONS
from visualization.psm_3d_items import PSMComponent, PSMFlowLine
from visualization.psm_3d_data_mapper import PSMDataMapper, COLOR_HOUSING
from visualization.psm_3d_info_panel import PSM3DInfoPanel, PSM3DStatusBar


logger = logging.getLogger(__name__)


# Toolbar button style
STYLE_TOOLBAR_BTN = """
    QPushButton {
        background-color: #3d3d3d;
        color: #ffffff;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 6px 12px;
        font-size: 12px;
    }
    QPushButton:hover {
        background-color: #4d4d4d;
    }
    QPushButton:pressed {
        background-color: #2d2d2d;
    }
    QPushButton:checked {
        background-color: #27ae60;
        border-color: #27ae60;
    }
"""


class PSM3DTab(QWidget):
    """
    Interactive 3D visualization tab for PSM devices.

    Features:
    - 3D model of PSM with primitive shapes
    - Color-coded components based on live data status
    - Click to select components and see details
    - Camera controls (orbit, zoom, pan)
    - Toggle labels, flow lines, exploded view
    """

    # Signal emitted when a component is clicked
    component_selected = pyqtSignal(str)  # component_name

    def __init__(self, device_config, is_psm2: bool = False,
                 parent: Optional[QWidget] = None):
        """
        Initialize the 3D visualization tab.

        Args:
            device_config: Device configuration object
            is_psm2: True if this is PSM 2.0, False for Retrofit
            parent: Optional parent widget
        """
        super().__init__(parent)

        self.device_config = device_config
        self.is_psm2 = is_psm2
        self._current_data = None
        self._selected_component: Optional[str] = None

        # Components
        self._components: Dict[str, PSMComponent] = {}
        self._flow_lines: list = []
        self._gl_widget: Optional[gl.GLViewWidget] = None

        # Data mapper
        self.data_mapper = PSMDataMapper(is_psm2=is_psm2)

        # Build UI
        self._setup_ui()

        # Build 3D model if OpenGL available
        if HAS_OPENGL:
            self._build_model()
        else:
            self._show_no_opengl_message()

    def _setup_ui(self) -> None:
        """Set up the tab UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Main content splitter
        splitter = QSplitter(Qt.Horizontal)

        # 3D view (left side)
        self._3d_container = QWidget()
        self._3d_layout = QVBoxLayout(self._3d_container)
        self._3d_layout.setContentsMargins(0, 0, 0, 0)

        if HAS_OPENGL:
            self._gl_widget = gl.GLViewWidget()
            self._gl_widget.setBackgroundColor('#1e1e1e')
            self._gl_widget.setCameraPosition(distance=20, elevation=25, azimuth=45)
            self._3d_layout.addWidget(self._gl_widget)

        else:
            # Placeholder when OpenGL not available
            placeholder = QLabel("3D visualization requires PyOpenGL.\n\n"
                               "Install with: pip install PyOpenGL")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #888888; font-size: 14px;")
            self._3d_layout.addWidget(placeholder)

        splitter.addWidget(self._3d_container)

        # Info panel (right side)
        self.info_panel = PSM3DInfoPanel(self.data_mapper)
        splitter.addWidget(self.info_panel)

        # Set splitter proportions (70% 3D view, 30% info panel)
        splitter.setSizes([700, 300])

        layout.addWidget(splitter, stretch=1)

        # Status bar at bottom
        self.status_bar = PSM3DStatusBar(self.data_mapper)
        layout.addWidget(self.status_bar)

    def _create_toolbar(self) -> QToolBar:
        """Create the toolbar with view controls."""
        toolbar = QToolBar()
        toolbar.setStyleSheet("QToolBar { background-color: #2b2b2b; border: none; padding: 4px; }")

        # Reset view button
        reset_btn = QPushButton("Reset View")
        reset_btn.setStyleSheet(STYLE_TOOLBAR_BTN)
        reset_btn.clicked.connect(self._reset_camera)
        toolbar.addWidget(reset_btn)

        toolbar.addSeparator()

        # Labels toggle
        self.labels_btn = QPushButton("Labels")
        self.labels_btn.setStyleSheet(STYLE_TOOLBAR_BTN)
        self.labels_btn.setCheckable(True)
        self.labels_btn.setChecked(False)
        self.labels_btn.clicked.connect(self._toggle_labels)
        toolbar.addWidget(self.labels_btn)

        # Flow lines toggle
        self.flow_btn = QPushButton("Flow Lines")
        self.flow_btn.setStyleSheet(STYLE_TOOLBAR_BTN)
        self.flow_btn.setCheckable(True)
        self.flow_btn.setChecked(True)
        self.flow_btn.clicked.connect(self._toggle_flow_lines)
        toolbar.addWidget(self.flow_btn)

        # Housing toggle
        self.housing_btn = QPushButton("Housing")
        self.housing_btn.setStyleSheet(STYLE_TOOLBAR_BTN)
        self.housing_btn.setCheckable(True)
        self.housing_btn.setChecked(True)
        self.housing_btn.clicked.connect(self._toggle_housing)
        toolbar.addWidget(self.housing_btn)

        toolbar.addSeparator()

        # View presets
        top_btn = QPushButton("Top")
        top_btn.setStyleSheet(STYLE_TOOLBAR_BTN)
        top_btn.clicked.connect(lambda: self._set_camera_view('top'))
        toolbar.addWidget(top_btn)

        front_btn = QPushButton("Front")
        front_btn.setStyleSheet(STYLE_TOOLBAR_BTN)
        front_btn.clicked.connect(lambda: self._set_camera_view('front'))
        toolbar.addWidget(front_btn)

        side_btn = QPushButton("Side")
        side_btn.setStyleSheet(STYLE_TOOLBAR_BTN)
        side_btn.clicked.connect(lambda: self._set_camera_view('side'))
        toolbar.addWidget(side_btn)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().Expanding, spacer.sizePolicy().Preferred)
        toolbar.addWidget(spacer)

        # PSM type indicator
        type_label = QLabel(f"PSM {'2.0' if self.is_psm2 else 'Retrofit'}")
        type_label.setStyleSheet("color: #888888; padding-right: 10px;")
        toolbar.addWidget(type_label)

        return toolbar

    def _build_model(self) -> None:
        """Build the 3D model and add to scene."""
        if not HAS_OPENGL or self._gl_widget is None:
            return

        # Create model builder
        builder = PSMModelBuilder(is_psm2=self.is_psm2)
        geometries = builder.build_model()

        # Add grid for reference
        grid = gl.GLGridItem()
        grid.setSize(15, 15, 1)
        grid.setSpacing(1, 1, 1)
        grid.translate(0, 0, -0.5)
        self._gl_widget.addItem(grid)

        # Create components from geometries
        for name, geom in geometries.items():
            component = PSMComponent(
                name=name,
                mesh_data=geom.mesh_data,
                position=geom.position
            )

            if component.mesh_item is not None:
                self._gl_widget.addItem(component.mesh_item)

                # Make housing transparent
                if name == 'housing':
                    component.set_transparent(True)

            self._components[name] = component

        # Create flow lines
        self._create_flow_lines(geometries)

        # Set initial camera
        self._reset_camera()

    def _create_flow_lines(self, geometries: dict) -> None:
        """Create flow lines connecting components."""
        if not HAS_OPENGL or self._gl_widget is None:
            return

        for from_name, to_name, flow_type in PSM_FLOW_CONNECTIONS:
            if from_name not in geometries or to_name not in geometries:
                continue

            # Skip vacuum MFC connections if not PSM2
            if not self.is_psm2 and 'vacuum' in from_name.lower():
                continue

            from_geom = geometries[from_name]
            to_geom = geometries[to_name]

            # Adjust positions to connect at component edges
            from_pos = np.array(from_geom.position)
            to_pos = np.array(to_geom.position)

            # Offset to connect at sides rather than centers
            from_pos[2] += 0.5
            to_pos[2] += 0.5

            flow_line = PSMFlowLine(
                from_pos=tuple(from_pos),
                to_pos=tuple(to_pos),
                flow_type=flow_type,
                width=2.0
            )

            if flow_line.line_item is not None:
                self._gl_widget.addItem(flow_line.line_item)
                self._flow_lines.append(flow_line)

    def _show_no_opengl_message(self) -> None:
        """Show message when OpenGL is not available."""
        logger.warning("OpenGL not available for 3D visualization")

    def _reset_camera(self) -> None:
        """Reset camera to default position."""
        if self._gl_widget is not None:
            self._gl_widget.setCameraPosition(distance=20, elevation=25, azimuth=45)

    def _set_camera_view(self, view: str) -> None:
        """Set camera to a preset view."""
        if self._gl_widget is None:
            return

        if view == 'top':
            self._gl_widget.setCameraPosition(distance=20, elevation=90, azimuth=0)
        elif view == 'front':
            self._gl_widget.setCameraPosition(distance=20, elevation=0, azimuth=0)
        elif view == 'side':
            self._gl_widget.setCameraPosition(distance=20, elevation=0, azimuth=90)

    def _toggle_labels(self, checked: bool) -> None:
        """Toggle component labels visibility."""
        # Labels not yet implemented - placeholder for future
        pass

    def _toggle_flow_lines(self, checked: bool) -> None:
        """Toggle flow lines visibility."""
        for flow_line in self._flow_lines:
            flow_line.set_visible(checked)

    def _toggle_housing(self, checked: bool) -> None:
        """Toggle housing visibility."""
        if 'housing' in self._components:
            housing = self._components['housing']
            if housing.mesh_item is not None:
                housing.mesh_item.setVisible(checked)

    def _select_component(self, component_name: Optional[str]) -> None:
        """Select a component and update UI."""
        # Deselect previous
        if self._selected_component and self._selected_component in self._components:
            self._components[self._selected_component].set_selected(False)

        # Select new
        self._selected_component = component_name
        if component_name and component_name in self._components:
            self._components[component_name].set_selected(True)

        # Update info panel
        self.info_panel.set_component(component_name)

        # Emit signal
        if component_name:
            self.component_selected.emit(component_name)

    def update_visualization(self, psm_data, status_hex: str = "", note_hex: str = "") -> None:
        """
        Update the visualization with new PSM data.

        Args:
            psm_data: PSMData object with current values
            status_hex: STATUS_HEX string from PSM
            note_hex: NOTE_HEX string from PSM
        """
        self._current_data = psm_data

        # Update data mapper status
        self.data_mapper.update_status(status_hex, note_hex)

        # Update component colors
        for name, component in self._components.items():
            color = self.data_mapper.get_component_color(name, psm_data)
            component.set_color(color)

        # Update info panel if component selected
        if self._selected_component:
            self.info_panel.update_data(psm_data)

        # Update status bar
        self.status_bar.update_status(psm_data)

    def showEvent(self, event) -> None:
        """Handle show event."""
        super().showEvent(event)
        # Could trigger initial data refresh here if needed

    def hideEvent(self, event) -> None:
        """Handle hide event."""
        super().hideEvent(event)
        # Could pause updates when hidden for performance
