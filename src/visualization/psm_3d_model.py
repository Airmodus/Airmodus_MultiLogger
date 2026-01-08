"""
PSM 3D Model Builder using primitive geometry.

Creates a simplified 3D representation of the PSM device using
basic shapes (boxes, cylinders) that can be colored based on live data.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional

try:
    import pyqtgraph.opengl as gl
    from pyqtgraph.opengl import MeshData
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False
    gl = None
    MeshData = None


def create_cylinder_mesh(radius: float, height: float, segments: int = 32) -> Optional[MeshData]:
    """
    Create a cylinder mesh.

    Args:
        radius: Cylinder radius
        height: Cylinder height
        segments: Number of segments around circumference

    Returns:
        MeshData object or None if OpenGL not available
    """
    if not HAS_OPENGL:
        return None

    # Create vertices for top and bottom circles
    angles = np.linspace(0, 2 * np.pi, segments, endpoint=False)

    # Bottom circle vertices
    bottom_verts = np.zeros((segments, 3))
    bottom_verts[:, 0] = radius * np.cos(angles)
    bottom_verts[:, 1] = radius * np.sin(angles)
    bottom_verts[:, 2] = 0

    # Top circle vertices
    top_verts = np.zeros((segments, 3))
    top_verts[:, 0] = radius * np.cos(angles)
    top_verts[:, 1] = radius * np.sin(angles)
    top_verts[:, 2] = height

    # Center vertices for caps
    bottom_center = np.array([[0, 0, 0]])
    top_center = np.array([[0, 0, height]])

    # Combine all vertices
    verts = np.vstack([bottom_verts, top_verts, bottom_center, top_center])

    # Create faces
    faces = []

    # Bottom cap faces
    bottom_center_idx = 2 * segments
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([bottom_center_idx, next_i, i])

    # Top cap faces
    top_center_idx = 2 * segments + 1
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.append([top_center_idx, segments + i, segments + next_i])

    # Side faces (quads as two triangles)
    for i in range(segments):
        next_i = (i + 1) % segments
        # First triangle
        faces.append([i, next_i, segments + next_i])
        # Second triangle
        faces.append([i, segments + next_i, segments + i])

    faces = np.array(faces)

    return MeshData(vertexes=verts, faces=faces)


def create_box_mesh(width: float, depth: float, height: float) -> Optional[MeshData]:
    """
    Create a box mesh.

    Args:
        width: Box width (X)
        depth: Box depth (Y)
        height: Box height (Z)

    Returns:
        MeshData object or None if OpenGL not available
    """
    if not HAS_OPENGL:
        return None

    w, d, h = width / 2, depth / 2, height

    verts = np.array([
        # Bottom face
        [-w, -d, 0], [w, -d, 0], [w, d, 0], [-w, d, 0],
        # Top face
        [-w, -d, h], [w, -d, h], [w, d, h], [-w, d, h],
    ])

    faces = np.array([
        # Bottom
        [0, 2, 1], [0, 3, 2],
        # Top
        [4, 5, 6], [4, 6, 7],
        # Front
        [0, 1, 5], [0, 5, 4],
        # Back
        [2, 3, 7], [2, 7, 6],
        # Left
        [0, 4, 7], [0, 7, 3],
        # Right
        [1, 2, 6], [1, 6, 5],
    ])

    return MeshData(vertexes=verts, faces=faces)


class PSMComponentGeometry:
    """Stores geometry and position for a single PSM component."""

    def __init__(self, name: str, mesh_data: MeshData,
                 position: Tuple[float, float, float],
                 rotation: Tuple[float, float, float, float] = (0, 0, 0, 1)):
        """
        Initialize component geometry.

        Args:
            name: Component name (matches PSM_COMPONENTS keys)
            mesh_data: PyQtGraph MeshData for this component
            position: (x, y, z) position in model space
            rotation: (angle, x, y, z) rotation quaternion
        """
        self.name = name
        self.mesh_data = mesh_data
        self.position = position
        self.rotation = rotation


class PSMModelBuilder:
    """
    Builds a 3D model of the PSM device using primitive shapes.

    The model represents the key components of the PSM:
    - Inlet tube
    - Heater block
    - Saturator chamber
    - Growth tube
    - Drainage system
    - Mass flow controllers (MFCs)
    - Pressure sensors
    - Housing (transparent)
    """

    # Scale factor for the model (mm to model units)
    SCALE = 0.01

    def __init__(self, is_psm2: bool = False):
        """
        Initialize the model builder.

        Args:
            is_psm2: True if building PSM 2.0 model, False for Retrofit
        """
        self.is_psm2 = is_psm2
        self._components: Dict[str, PSMComponentGeometry] = {}

    def build_model(self) -> Dict[str, PSMComponentGeometry]:
        """
        Build the complete PSM 3D model.

        Returns:
            Dictionary mapping component names to their geometry
        """
        if not HAS_OPENGL:
            return {}

        self._components = {}

        # Build each component with realistic relative positions
        # All measurements are approximate and can be adjusted

        # Inlet tube (vertical cylinder at top)
        self._add_component(
            'inlet',
            create_cylinder_mesh(radius=0.3, height=1.5),
            position=(0, 0, 8)
        )

        # Heater block (box around inlet)
        self._add_component(
            'heater',
            create_box_mesh(width=1.5, depth=1.5, height=1.0),
            position=(0, 0, 7)
        )

        # Saturator chamber (large box)
        self._add_component(
            'saturator',
            create_box_mesh(width=3.0, depth=2.5, height=2.5),
            position=(0, 0, 4)
        )

        # Growth tube (long vertical cylinder)
        self._add_component(
            'growth_tube',
            create_cylinder_mesh(radius=0.4, height=3.5),
            position=(0, 0, 0)
        )

        # Drainage (small box below saturator)
        self._add_component(
            'drainage',
            create_box_mesh(width=1.5, depth=1.0, height=0.8),
            position=(0, 1.5, 3.5)
        )

        # Cabin temperature sensor (small cylinder)
        self._add_component(
            'cabin',
            create_cylinder_mesh(radius=0.15, height=0.3),
            position=(2.0, 0, 5)
        )

        # Saturator MFC (box on the side)
        self._add_component(
            'mfc_saturator',
            create_box_mesh(width=0.8, depth=0.6, height=1.2),
            position=(-2.5, 0, 5)
        )

        # Excess MFC (box on the side)
        self._add_component(
            'mfc_excess',
            create_box_mesh(width=0.8, depth=0.6, height=1.2),
            position=(-2.5, 0, 3)
        )

        # Vacuum MFC (PSM2 only)
        if self.is_psm2:
            self._add_component(
                'mfc_vacuum',
                create_box_mesh(width=0.8, depth=0.6, height=1.2),
                position=(-2.5, 0, 1)
            )

        # Pressure sensors (small cylinders)
        self._add_component(
            'pressure_inlet',
            create_cylinder_mesh(radius=0.2, height=0.4),
            position=(1.8, 0, 7.5)
        )

        self._add_component(
            'pressure_saturator',
            create_cylinder_mesh(radius=0.2, height=0.4),
            position=(1.8, 0, 5.5)
        )

        self._add_component(
            'pressure_excess',
            create_cylinder_mesh(radius=0.2, height=0.4),
            position=(1.8, 0, 4.0)
        )

        self._add_component(
            'pressure_critical',
            create_cylinder_mesh(radius=0.2, height=0.4),
            position=(1.8, 0, 1.5)
        )

        # Liquid reservoirs (small boxes)
        self._add_component(
            'liquid_saturator',
            create_box_mesh(width=0.6, depth=0.6, height=0.5),
            position=(1.5, 1.2, 4.5)
        )

        self._add_component(
            'liquid_drain',
            create_box_mesh(width=0.6, depth=0.6, height=0.5),
            position=(1.5, 1.5, 3.2)
        )

        # Housing (transparent outer shell)
        self._add_component(
            'housing',
            create_box_mesh(width=7.0, depth=5.0, height=10.0),
            position=(0, 0, -0.5)
        )

        return self._components

    def _add_component(self, name: str, mesh_data: Optional[MeshData],
                      position: Tuple[float, float, float],
                      rotation: Tuple[float, float, float, float] = (0, 0, 0, 1)) -> None:
        """Add a component to the model."""
        if mesh_data is not None:
            self._components[name] = PSMComponentGeometry(
                name=name,
                mesh_data=mesh_data,
                position=position,
                rotation=rotation
            )

    def get_component(self, name: str) -> Optional[PSMComponentGeometry]:
        """Get geometry for a specific component."""
        return self._components.get(name)

    def get_all_components(self) -> List[str]:
        """Get list of all component names in the model."""
        return list(self._components.keys())

    def get_model_bounds(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Get the bounding box of the entire model.

        Returns:
            ((min_x, min_y, min_z), (max_x, max_y, max_z))
        """
        # Based on housing dimensions
        return ((-3.5, -2.5, -0.5), (3.5, 2.5, 9.5))

    def get_model_center(self) -> Tuple[float, float, float]:
        """Get the center point of the model."""
        return (0, 0, 4.5)


# Connection lines between components for flow visualization
PSM_FLOW_CONNECTIONS = [
    # (from_component, to_component, line_type)
    ('inlet', 'heater', 'sample'),
    ('heater', 'saturator', 'sample'),
    ('saturator', 'growth_tube', 'sample'),
    ('mfc_saturator', 'saturator', 'air'),
    ('saturator', 'mfc_excess', 'air'),
    ('growth_tube', 'drainage', 'condensate'),
    ('liquid_saturator', 'saturator', 'liquid'),
    ('drainage', 'liquid_drain', 'liquid'),
]
