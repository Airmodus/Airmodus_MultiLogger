"""Visual overlay for drawing connector lines between linked device tabs."""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QPainter, QPen, QColor, QPainterPath


class TabLinkOverlay(QWidget):
    """Transparent overlay that draws connector lines between linked device tabs.

    Draws U-shaped bracket connectors below the tab bar to show which devices
    are linked together. Different link types have different colors:
    - PSM -> CPC: Blue
    - CPC -> RHTP: Green
    """

    # Link type colors
    COLORS = {
        'psm_cpc': QColor(66, 133, 244, 220),    # Blue
        'cpc_rhtp': QColor(52, 168, 83, 220),    # Green
    }

    def __init__(self, tab_bar, parent=None):
        """Initialize the overlay.

        Args:
            tab_bar: The BrowserStyleTabBar this overlay is attached to
            parent: Parent widget
        """
        super().__init__(parent)
        self._tab_bar = tab_bar
        self._links = {'psm_cpc': {}, 'cpc_rhtp': {}}
        self._device_widgets = {}  # device_id -> widget reference
        self._stacked_widget = None  # Reference to device_tabs QStackedWidget

        # Make overlay transparent and non-interactive
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    def set_links(self, links, device_widgets, stacked_widget):
        """Update link data for rendering.

        Args:
            links: Dict like {'psm_cpc': {psm_id: cpc_id}, 'cpc_rhtp': {cpc_id: rhtp_id}}
            device_widgets: Dict of device_id -> widget
            stacked_widget: QStackedWidget containing device widgets
        """
        self._links = links
        self._device_widgets = device_widgets
        self._stacked_widget = stacked_widget
        self.update()

    def _get_tab_index_for_device(self, device_id):
        """Get the tab index for a device.

        Args:
            device_id: The device ID to look up

        Returns:
            Tab index, or -1 if not found
        """
        widget = self._device_widgets.get(device_id)
        if widget and self._stacked_widget:
            return self._stacked_widget.indexOf(widget)
        return -1

    def _get_tab_center_x(self, tab_index):
        """Get the center X coordinate of a tab in overlay coordinates.

        Args:
            tab_index: Index of the tab

        Returns:
            X coordinate of tab center in overlay coordinates, or None if not visible
        """
        if tab_index < 0 or tab_index >= self._tab_bar.count():
            return None

        # Get tab rect from inner tab bar
        tab_rect = self._tab_bar.tabRect(tab_index)
        if tab_rect.isNull():
            return None

        # Get center of tab
        tab_center = tab_rect.center()

        # Map from tab bar coordinates to global, then to overlay coordinates
        global_pos = self._tab_bar.mapTabToGlobal(tab_index, tab_center)
        local_pos = self.mapFromGlobal(global_pos)

        return local_pos.x()

    def _lines_overlap(self, line1, line2):
        """Check if two horizontal line segments overlap in X range.

        Args:
            line1: Tuple (x1, x2) for first line
            line2: Tuple (x1, x2) for second line

        Returns:
            True if the lines' X ranges intersect
        """
        x1_min, x1_max = min(line1), max(line1)
        x2_min, x2_max = min(line2), max(line2)

        # Check if ranges intersect
        return x1_min < x2_max and x2_min < x1_max

    def _assign_line_levels(self, line_segments):
        """Assign vertical levels to lines, using higher levels only when overlapping.

        Args:
            line_segments: List of (source_id, target_id, x1, x2) tuples

        Returns:
            Dict mapping (source_id, target_id) -> level (0, 1, 2, ...)
        """
        if not line_segments:
            return {}

        levels = {}
        lines_at_level = {}  # level -> list of (x1, x2)

        for source_id, target_id, x1, x2 in line_segments:
            line = (x1, x2)
            # Find first level with no overlaps
            level = 0
            while True:
                lines_at_this_level = lines_at_level.get(level, [])
                has_overlap = any(self._lines_overlap(line, other) for other in lines_at_this_level)
                if not has_overlap:
                    break
                level += 1

            levels[(source_id, target_id)] = level
            lines_at_level.setdefault(level, []).append(line)

        return levels

    def paintEvent(self, event):
        """Draw connector lines between linked tabs."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw PSM -> CPC connections (blue)
        self._draw_connections(painter, 'psm_cpc')

        # Draw CPC -> RHTP connections (green)
        self._draw_connections(painter, 'cpc_rhtp')

    def _draw_connections(self, painter, link_type):
        """Draw connections for a specific link type.

        Args:
            painter: QPainter instance
            link_type: 'psm_cpc' or 'cpc_rhtp'
        """
        links = self._links.get(link_type, {})
        color = self.COLORS.get(link_type, QColor(100, 100, 100))

        # Collect all line segments first
        line_segments = []
        for source_id, target_id in links.items():
            if target_id == 'None' or target_id is None:
                continue

            source_idx = self._get_tab_index_for_device(source_id)
            target_idx = self._get_tab_index_for_device(target_id)

            source_x = self._get_tab_center_x(source_idx)
            target_x = self._get_tab_center_x(target_idx)

            if source_x is not None and target_x is not None:
                line_segments.append((source_id, target_id, source_x, target_x))

        # Assign levels to avoid overlapping lines
        levels = self._assign_line_levels(line_segments)

        # Draw each line at its assigned level
        pen = QPen(color, 3)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)

        for source_id, target_id, x1, x2 in line_segments:
            level = levels.get((source_id, target_id), 0)
            self._draw_bracket(painter, x1, x2, color, level)

    def _draw_bracket(self, painter, x1, x2, color, level=0):
        """Draw a horizontal line connector between two tabs.

        Args:
            painter: QPainter instance
            x1: X coordinate of first tab center
            x2: X coordinate of second tab center
            color: Color for the bracket
            level: Vertical level (0 = closest to tabs, higher = further up)
        """
        # Draw near top of overlay (like before), with higher levels going down
        # Level 0 = near top, level 1 = 10px lower, etc.
        y_line = 8 + (level * 10)

        # Draw the horizontal connecting line
        pen = QPen(color, 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(x1), int(y_line), int(x2), int(y_line))

        # Draw small circles at the endpoints for visual emphasis
        painter.setBrush(color)
        radius = 5
        painter.drawEllipse(QPoint(int(x1), int(y_line)), radius, radius)
        painter.drawEllipse(QPoint(int(x2), int(y_line)), radius, radius)
