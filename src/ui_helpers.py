"""
Reusable UI helper components and functions for user guidance and interaction.

This module provides generic widgets and utilities that can guide users to
the correct UI elements when they try to interact with disabled controls.
"""

from PyQt5.QtWidgets import QComboBox, QLineEdit, QPushButton, QWidget
from PyQt5.QtCore import QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QPalette, QColor


def highlight_widget(widget: QWidget, color: str = "#FFFACD", duration_ms: int = 2000, pulses: int = 1):
    """
    Highlight a widget with a gentle glow effect to draw user attention.
    Uses a transparent overlay to avoid changing the widget's size.

    Args:
        widget: The QWidget to highlight
        color: Hex color string for the highlight (default: lemon chiffon)
        duration_ms: Total duration of the highlight effect in milliseconds
        pulses: Number of times to pulse the highlight

    Example:
        highlight_widget(some_checkbox, color="#FFFACD", duration_ms=2000, pulses=1)
    """
    from PyQt5.QtWidgets import QLabel
    from PyQt5.QtCore import Qt

    # Create a semi-transparent overlay label
    overlay = QLabel(widget.parent())
    overlay.setGeometry(widget.geometry())
    overlay.setAttribute(Qt.WA_TransparentForMouseEvents)  # Allow clicks to pass through

    # Convert hex color to rgba with transparency (30% opacity)
    qcolor = QColor(color)
    rgba_color = f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, 0.3)"

    overlay.setStyleSheet(f"""
        QLabel {{
            background-color: {rgba_color};
            border-radius: 3px;
        }}
    """)
    overlay.show()
    overlay.raise_()  # Bring to front

    # Single slow pulse timing
    hold_duration = 800     # ms to hold at peak (slow glow)
    fade_out_duration = 1200 # ms for slow fade out

    def fade_out():
        # Remove the overlay
        overlay.deleteLater()

    # Hold at peak brightness, then fade out
    QTimer.singleShot(hold_duration + fade_out_duration, fade_out)


class GuidedComboBox(QComboBox):
    """
    A QComboBox that redirects user attention to a target widget when clicked while disabled.

    When the user tries to click this combobox while it's disabled, it will:
    1. Visually highlight the target widget
    2. Update its tooltip to explain why it's disabled

    Example:
        combo = GuidedComboBox()
        combo.set_guide_target(enable_checkbox, "Uncheck 'Enable' to change this setting")
        combo.setEnabled(False)  # When clicked, will highlight the checkbox
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._guide_target = None
        self._guide_message = "Disabled - check related settings"
        self._enabled_tooltip = ""
        self._disabled_tooltip = ""
        self._is_disabled = False
        self._tooltip_widget = None  # Custom tooltip widget

        # Install event filter on self to catch events even when disabled
        self.installEventFilter(self)

    def set_guide_target(self, target_widget: QWidget, guide_message: str = None):
        """
        Set the widget to highlight when this combobox is clicked while disabled.

        Args:
            target_widget: The widget to highlight (e.g., a checkbox that needs to be toggled)
            guide_message: Optional message to show in tooltip when disabled
        """
        self._guide_target = target_widget
        if guide_message:
            self._guide_message = guide_message

    def set_tooltips(self, enabled_tooltip: str, disabled_tooltip: str):
        """
        Set separate tooltips for enabled and disabled states.

        Args:
            enabled_tooltip: Tooltip to show when combobox is enabled
            disabled_tooltip: Tooltip to show when combobox is disabled
        """
        self._enabled_tooltip = enabled_tooltip
        self._disabled_tooltip = disabled_tooltip
        # Set current tooltip based on current state
        self._update_tooltip()

    def setEnabled(self, enabled: bool):
        """Override to update tooltip when enabled state changes."""
        super().setEnabled(enabled)
        self._is_disabled = not enabled
        self._update_tooltip()

    def _update_tooltip(self):
        """Update tooltip based on current enabled state."""
        if self.isEnabled():
            self.setToolTip(self._enabled_tooltip)
        else:
            self.setToolTip(self._disabled_tooltip)

    def eventFilter(self, obj, event):
        """Event filter to catch mouse clicks even when disabled."""
        from PyQt5.QtCore import QEvent, QPoint, Qt
        from PyQt5.QtWidgets import QLabel

        # Check if this is a mouse press event on our widget while disabled
        if obj == self and event.type() == QEvent.MouseButtonPress and self._is_disabled:
            if self._guide_target:
                # Highlight the target widget to guide user (single slow pulse)
                highlight_widget(self._guide_target)

                # Create a persistent custom tooltip widget
                if not self._tooltip_widget:
                    self._tooltip_widget = QLabel(self._guide_message, self.window())
                    self._tooltip_widget.setStyleSheet("""
                        QLabel {
                            background-color: #FFFFCC;
                            border: 1px solid #888888;
                            border-radius: 3px;
                            padding: 5px;
                            color: #000000;
                        }
                    """)
                    self._tooltip_widget.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
                    self._tooltip_widget.setAttribute(Qt.WA_TransparentForMouseEvents)

                # Position it below the dropdown
                global_pos = self.mapToGlobal(QPoint(0, self.height()))
                self._tooltip_widget.move(global_pos)
                self._tooltip_widget.adjustSize()
                self._tooltip_widget.show()
                self._tooltip_widget.raise_()
            return True  # Event handled, don't propagate

        # Hide tooltip when mouse is released
        if obj == self and event.type() == QEvent.MouseButtonRelease and self._is_disabled:
            if self._tooltip_widget:
                self._tooltip_widget.hide()
            return True

        # Pass through all other events
        return super().eventFilter(obj, event)


class GuidedLineEdit(QLineEdit):
    """
    A QLineEdit that redirects user attention to a target widget when clicked while disabled.

    Similar to GuidedComboBox but for line edit fields.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._guide_target = None
        self._guide_message = "Disabled - check related settings"
        self._enabled_tooltip = ""
        self._disabled_tooltip = ""
        self._is_disabled = False
        self._tooltip_widget = None  # Custom tooltip widget

        # Install event filter on self to catch events even when disabled
        self.installEventFilter(self)

    def set_guide_target(self, target_widget: QWidget, guide_message: str = None):
        """Set the widget to highlight when this line edit is clicked while disabled."""
        self._guide_target = target_widget
        if guide_message:
            self._guide_message = guide_message

    def set_tooltips(self, enabled_tooltip: str, disabled_tooltip: str):
        """Set separate tooltips for enabled and disabled states."""
        self._enabled_tooltip = enabled_tooltip
        self._disabled_tooltip = disabled_tooltip
        self._update_tooltip()

    def setEnabled(self, enabled: bool):
        """Override to update tooltip when enabled state changes."""
        super().setEnabled(enabled)
        self._is_disabled = not enabled
        self._update_tooltip()

    def _update_tooltip(self):
        """Update tooltip based on current enabled state."""
        if self.isEnabled():
            self.setToolTip(self._enabled_tooltip)
        else:
            self.setToolTip(self._disabled_tooltip)

    def eventFilter(self, obj, event):
        """Event filter to catch mouse clicks even when disabled."""
        from PyQt5.QtCore import QEvent, QPoint, Qt
        from PyQt5.QtWidgets import QLabel

        # Check if this is a mouse press event on our widget while disabled
        if obj == self and event.type() == QEvent.MouseButtonPress and self._is_disabled:
            if self._guide_target:
                # Highlight the target widget to guide user (single slow pulse)
                highlight_widget(self._guide_target)

                # Create a persistent custom tooltip widget
                if not self._tooltip_widget:
                    self._tooltip_widget = QLabel(self._guide_message, self.window())
                    self._tooltip_widget.setStyleSheet("""
                        QLabel {
                            background-color: #FFFFCC;
                            border: 1px solid #888888;
                            border-radius: 3px;
                            padding: 5px;
                            color: #000000;
                        }
                    """)
                    self._tooltip_widget.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
                    self._tooltip_widget.setAttribute(Qt.WA_TransparentForMouseEvents)

                # Position it below the line edit
                global_pos = self.mapToGlobal(QPoint(0, self.height()))
                self._tooltip_widget.move(global_pos)
                self._tooltip_widget.adjustSize()
                self._tooltip_widget.show()
                self._tooltip_widget.raise_()
            return True  # Event handled, don't propagate

        # Hide tooltip when mouse is released
        if obj == self and event.type() == QEvent.MouseButtonRelease and self._is_disabled:
            if self._tooltip_widget:
                self._tooltip_widget.hide()
            return True

        # Pass through all other events
        return super().eventFilter(obj, event)


def create_guided_widget(widget_class, parent=None, guide_target=None, guide_message=None,
                         enabled_tooltip="", disabled_tooltip=""):
    """
    Factory function to create a guided widget of any supported type.

    Args:
        widget_class: The widget class to instantiate (QComboBox, QLineEdit, etc.)
        parent: Parent widget
        guide_target: Widget to highlight when clicked while disabled
        guide_message: Message to show in disabled tooltip
        enabled_tooltip: Tooltip when enabled
        disabled_tooltip: Tooltip when disabled

    Returns:
        Instance of the guided widget

    Example:
        dropdown = create_guided_widget(
            QComboBox,
            parent=self,
            guide_target=enable_checkbox,
            guide_message="Disable database to change interval",
            enabled_tooltip="Select averaging interval",
            disabled_tooltip="Disable database first to change this setting"
        )
    """
    # Map standard widgets to their guided versions
    guided_classes = {
        QComboBox: GuidedComboBox,
        QLineEdit: GuidedLineEdit,
    }

    # Get the guided version or return None if not supported
    guided_class = guided_classes.get(widget_class)
    if not guided_class:
        raise ValueError(f"Widget class {widget_class.__name__} does not have a guided version")

    # Create the widget
    widget = guided_class(parent)

    # Configure guidance
    if guide_target:
        widget.set_guide_target(guide_target, guide_message)

    if enabled_tooltip or disabled_tooltip:
        widget.set_tooltips(enabled_tooltip, disabled_tooltip)

    return widget
