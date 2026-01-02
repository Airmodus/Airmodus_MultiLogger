"""
Custom 3D items for PSM visualization.

Provides clickable mesh items that can be highlighted and selected,
with color updates based on live data.
"""

from typing import Optional, Tuple, Callable, Any, TYPE_CHECKING
import numpy as np

try:
    import pyqtgraph.opengl as gl
    from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False
    gl = None

from PyQt5.QtCore import pyqtSignal, QObject

from .psm_3d_data_mapper import COLOR_GRAY

# Type alias for GLMeshItem when OpenGL is not available
GLMeshItemType = Any  # Use Any to avoid import issues


class PSMComponent(QObject):
    """
    A clickable 3D mesh component representing part of the PSM device.

    This wraps a GLMeshItem and adds selection/highlighting functionality.
    """

    # Signal emitted when component is clicked
    clicked = pyqtSignal(str)  # component_name

    def __init__(self, name: str, mesh_data, position: Tuple[float, float, float],
                 parent: Optional[QObject] = None):
        """
        Initialize a PSM component.

        Args:
            name: Component identifier (e.g., 'growth_tube')
            mesh_data: PyQtGraph MeshData object
            position: (x, y, z) position in model space
            parent: Optional parent QObject
        """
        super().__init__(parent)

        self.name = name
        self._position = position
        self._base_color = COLOR_GRAY
        self._current_color = COLOR_GRAY
        self._is_selected = False
        self._is_highlighted = False
        self._mesh_item: Optional[gl.GLMeshItem] = None

        if HAS_OPENGL and mesh_data is not None:
            self._mesh_item = gl.GLMeshItem(
                meshdata=mesh_data,
                smooth=True,
                drawEdges=True,
                edgeColor=(0.2, 0.2, 0.2, 1.0),
                shader='shaded',
                glOptions='opaque'
            )
            self._mesh_item.translate(*position)
            self.set_color(COLOR_GRAY)

    @property
    def mesh_item(self) -> Optional[GLMeshItemType]:
        """Get the underlying GLMeshItem."""
        return self._mesh_item

    @property
    def position(self) -> Tuple[float, float, float]:
        """Get the component position."""
        return self._position

    @property
    def is_selected(self) -> bool:
        """Check if component is selected."""
        return self._is_selected

    def set_color(self, color: Tuple[float, float, float, float]) -> None:
        """
        Set the base color of the component.

        Args:
            color: RGBA tuple (0-1 range)
        """
        self._base_color = color
        self._update_display_color()

    def _update_display_color(self) -> None:
        """Update the displayed color based on state."""
        if self._mesh_item is None:
            return

        if self._is_selected:
            # Selected: brighten the color
            r, g, b, a = self._base_color
            color = (min(1.0, r + 0.3), min(1.0, g + 0.3), min(1.0, b + 0.3), a)
        elif self._is_highlighted:
            # Highlighted: slightly brighten
            r, g, b, a = self._base_color
            color = (min(1.0, r + 0.15), min(1.0, g + 0.15), min(1.0, b + 0.15), a)
        else:
            color = self._base_color

        self._current_color = color

        # Set the color using GLMeshItem's setColor method
        self._mesh_item.setColor(color)

    def set_selected(self, selected: bool) -> None:
        """
        Set the selection state.

        Args:
            selected: True to select, False to deselect
        """
        if self._is_selected != selected:
            self._is_selected = selected
            self._update_display_color()

    def set_highlighted(self, highlighted: bool) -> None:
        """
        Set the highlight state (hover effect).

        Args:
            highlighted: True to highlight, False to remove highlight
        """
        if self._is_highlighted != highlighted:
            self._is_highlighted = highlighted
            self._update_display_color()

    def set_transparent(self, transparent: bool) -> None:
        """
        Set whether the component should be rendered transparently.

        Args:
            transparent: True for transparent rendering
        """
        if self._mesh_item is None:
            return

        if transparent:
            self._mesh_item.setGLOptions('translucent')
            r, g, b, _ = self._base_color
            self._base_color = (r, g, b, 0.3)
        else:
            self._mesh_item.setGLOptions('opaque')
            r, g, b, _ = self._base_color
            self._base_color = (r, g, b, 1.0)

        self._update_display_color()

    def get_bounding_box(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get the bounding box of this component in world space.

        Returns:
            (min_corner, max_corner) as numpy arrays
        """
        if self._mesh_item is None:
            pos = np.array(self._position)
            return (pos, pos)

        # Access mesh data via opts dictionary
        meshdata = self._mesh_item.opts.get('meshdata')
        if meshdata is None:
            pos = np.array(self._position)
            return (pos, pos)

        verts = meshdata.vertexes()
        pos = np.array(self._position)

        min_corner = verts.min(axis=0) + pos
        max_corner = verts.max(axis=0) + pos

        return (min_corner, max_corner)

    def contains_point(self, point: Tuple[float, float, float],
                      tolerance: float = 0.5) -> bool:
        """
        Check if a point is within this component's bounding box.

        Args:
            point: (x, y, z) point to test
            tolerance: Extra tolerance around bounding box

        Returns:
            True if point is within bounds
        """
        min_corner, max_corner = self.get_bounding_box()
        point = np.array(point)

        return (np.all(point >= min_corner - tolerance) and
                np.all(point <= max_corner + tolerance))


class PSMFlowLine:
    """
    A flow line connecting two PSM components.

    Visualizes the flow path between components with optional animation.
    """

    def __init__(self, from_pos: Tuple[float, float, float],
                 to_pos: Tuple[float, float, float],
                 flow_type: str = 'air',
                 width: float = 2.0):
        """
        Initialize a flow line.

        Args:
            from_pos: Starting position
            to_pos: Ending position
            flow_type: Type of flow ('air', 'sample', 'liquid', 'condensate')
            width: Line width
        """
        self.from_pos = from_pos
        self.to_pos = to_pos
        self.flow_type = flow_type
        self._line_item: Optional[Any] = None  # GLLinePlotItem when OpenGL available

        if HAS_OPENGL:
            # Choose color based on flow type
            colors = {
                'air': (0.6, 0.8, 1.0, 0.8),      # Light blue
                'sample': (1.0, 0.9, 0.5, 0.8),    # Yellow
                'liquid': (0.2, 0.6, 0.9, 0.8),    # Blue
                'condensate': (0.5, 0.7, 0.9, 0.6), # Light blue transparent
            }
            color = colors.get(flow_type, (0.5, 0.5, 0.5, 0.8))

            # Create line with intermediate points for curved appearance
            points = self._create_flow_path(from_pos, to_pos)

            self._line_item = gl.GLLinePlotItem(
                pos=points,
                color=color,
                width=width,
                antialias=True
            )

    def _create_flow_path(self, from_pos: Tuple[float, float, float],
                         to_pos: Tuple[float, float, float]) -> np.ndarray:
        """Create a smooth path between two points."""
        # Simple straight line for now
        # Could be enhanced with bezier curves
        return np.array([from_pos, to_pos])

    @property
    def line_item(self) -> Optional[Any]:
        """Get the underlying GLLinePlotItem."""
        return self._line_item

    def set_visible(self, visible: bool) -> None:
        """Set visibility of the flow line."""
        if self._line_item is not None:
            self._line_item.setVisible(visible)


class ComponentLabel:
    """
    A 3D text label for a component.

    Shows the component name floating near the component.
    """

    def __init__(self, text: str, position: Tuple[float, float, float],
                 color: Tuple[float, float, float, float] = (1, 1, 1, 1)):
        """
        Initialize a component label.

        Args:
            text: Label text
            position: (x, y, z) position
            color: RGBA color
        """
        self.text = text
        self.position = position
        self._text_item: Optional[Any] = None  # GLTextItem when OpenGL available

        # Note: GLTextItem may not be available in all pyqtgraph versions
        # We'll handle this gracefully
        if HAS_OPENGL:
            try:
                self._text_item = gl.GLTextItem(
                    pos=np.array(position),
                    text=text,
                    color=color
                )
            except AttributeError:
                # GLTextItem not available, skip labels
                pass

    @property
    def text_item(self):
        """Get the underlying GLTextItem."""
        return self._text_item

    def set_visible(self, visible: bool) -> None:
        """Set visibility of the label."""
        if self._text_item is not None:
            self._text_item.setVisible(visible)
