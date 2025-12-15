"""
PSM Contour Plot Tab

Displays real-time particle size distribution as a 2D contour plot.
Each completed scan adds a new vertical line to the plot.
Requires calibration file to perform size distribution inversion.
"""

import os
import time
import logging
import numpy as np
import pandas as pd
from typing import Optional, List, Dict
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QFileDialog, QMenu, QSizePolicy, QCheckBox,
                              QLineEdit, QSpinBox, QProgressBar, QGraphicsOpacityEffect,
                              QWidgetAction, QActionGroup)
from PyQt5.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QIntValidator
import pyqtgraph as pg
from scipy.interpolate import interp1d
from dat_file_reader import load_historical_scans, get_scan_time_range


class TimeAxisItemForContour(pg.AxisItem):
    """
    Custom axis item that displays time in HH:MM format.
    X-axis values are decimal hours, with support for values > 24 (next day).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        """Convert decimal hours to HH:MM time strings."""
        ticks = []
        for value in values:
            # value is in decimal hours, may exceed 24 for next day
            hours = int(value) % 24  # Wrap to 0-23
            minutes = int((value - int(value)) * 60)
            ticks.append(f"{hours:02d}:{minutes:02d}")
        return ticks


class BinAxisItem(pg.AxisItem):
    """
    Custom Y-axis that shows bin limit labels at bin boundaries.
    Y values are bin indices (0 to num_bins), labels show actual diameter values.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bin_limits = None  # Will be set when calibration loads

    def set_bin_limits(self, bin_limits):
        """Set the bin limits for label generation."""
        self.bin_limits = bin_limits

    def tickValues(self, minVal, maxVal, size):
        """Generate tick positions at bin boundaries."""
        if self.bin_limits is None:
            return super().tickValues(minVal, maxVal, size)

        # Create ticks at each bin boundary (0, 1, 2, ..., num_bins)
        num_bins = len(self.bin_limits) - 1
        ticks = [(1, list(range(num_bins + 1)))]  # Level 1 ticks at all boundaries
        return ticks

    def tickStrings(self, values, scale, spacing):
        """Convert bin indices to diameter labels."""
        if self.bin_limits is None:
            return [f"{v:.1f}" for v in values]

        labels = []
        for v in values:
            idx = int(round(v))
            if 0 <= idx < len(self.bin_limits):
                labels.append(f"{self.bin_limits[idx]:.1f}")
            else:
                labels.append("")
        return labels


class HistoricalDataLoader(QThread):
    """
    Worker thread for loading historical scan data without blocking the UI.
    """
    # Signals for communicating with main thread
    progress = pyqtSignal(int, int, str)  # current, total, message
    scan_loaded = pyqtSignal(dict)  # individual scan data
    finished_loading = pyqtSignal(list, list)  # filepaths, all scans
    error = pyqtSignal(str)  # error message

    def __init__(self, file_path, serial_number, device_nickname, file_tag, hours):
        super().__init__()
        self.file_path = file_path
        self.serial_number = serial_number
        self.device_nickname = device_nickname
        self.file_tag = file_tag
        self.hours = hours
        self._cancelled = False

    def cancel(self):
        """Cancel the loading operation."""
        self._cancelled = True

    def _emit_progress(self, current, total, message):
        """Progress callback for load_historical_scans."""
        if not self._cancelled:
            self.progress.emit(current, total, message)

    def run(self):
        """Load historical scans in background thread."""
        try:
            self.progress.emit(0, 0, "Finding data files...")

            # Load historical scans with progress callback
            filepaths, scans = load_historical_scans(
                file_path=self.file_path,
                serial_number=self.serial_number,
                device_nickname=self.device_nickname,
                file_tag=self.file_tag,
                hours=self.hours,
                progress_callback=self._emit_progress
            )

            if self._cancelled:
                return

            if filepaths is None or len(filepaths) == 0:
                self.error.emit("No data files found")
                return

            if not scans:
                self.error.emit(f"No scans in {len(filepaths)} file(s)")
                return

            # Emit progress for scan processing phase
            total = len(scans)
            self.progress.emit(0, total, f"Found {total} scans, preparing...")

            for i, scan in enumerate(scans):
                if self._cancelled:
                    return
                self.progress.emit(i + 1, total, f"Preparing scan {i + 1}/{total}")
                self.scan_loaded.emit(scan)

            self.finished_loading.emit(filepaths, scans)

        except Exception as e:
            logging.error(f"Error in historical data loader: {e}")
            self.error.emit(str(e))


class PSMContourTab(QWidget):
    """
    PSM Contour Plot Tab Widget

    Shows a real-time 2D heatmap of particle size distribution vs time.
    - X-axis: Time (scan timestamps)
    - Y-axis: Particle diameter (nm)
    - Color: log10(dN/dlogDp) concentration
    """

    def __init__(self, device_config, is_psm2: bool = False, app_config=None):
        super().__init__()
        self.device_config = device_config
        self.is_psm2 = is_psm2  # True for PSM 2.0, False for Retrofit
        self.app_config = app_config  # Will be set later by PSM widget
        self.on_config_changed = None  # Callback to notify parent when config changes

        # Set longer tooltip duration for this widget and children (10 seconds)
        self.setToolTipDuration(10000)

        # Try to set application-wide tooltip duration
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.setStyleSheet(app.styleSheet() + """
                    QToolTip {
                        background-color: #333;
                        color: white;
                        border: 1px solid #555;
                        padding: 8px;
                        font-size: 12px;
                    }
                """)
        except:
            pass

        # State flags
        self.calibration_loaded = False
        self.plot_initialized = False
        self._historical_data_loaded = False  # Track if we've loaded historical data
        self._loading_in_progress = False  # Track if loading is currently happening
        self._loader_thread = None  # Background thread for loading historical data

        # Calibration data
        self.calibration_df = None
        self.bin_limits_dp = None  # Diameter bin edges (7 values for 6 bins)
        self.bin_centers_dp = None  # Diameter bin centers (6 values)
        self.bin_limits_flow = None  # Saturator flow bin edges (7 values)
        self.detection_efficiency = None  # Detection efficiency interpolator

        # Scan detection state
        self._prev_scan_status = "9"
        self._current_scan = None  # Dict with 'times', 'satflows', 'concentrations'
        self._prev_saturator_flow = None  # For 10Hz saturator flow interpolation
        self._scan_start_time = None  # Timestamp when current scan phase started (for exponential flow calc)

        # CPC transit delay: time for particles to travel from saturator to CPC counter
        # Matches PSM Inversion Tool's CPC_time_lag = -3 seconds
        # Concentration is shifted forward (paired with satflow from 3 seconds earlier)
        self.cpc_transit_delay = 3  # seconds

        # Scan buffer (stores completed scans)
        self.scan_buffer = []  # List of dicts: {'time': float, 'bin_centers': array, 'dN_dlogDp': array}
        # No max_scans limit - show all available data

        # Averaging settings
        self.averaging_enabled = False
        self.avg_n = 5  # Default: average over 5 scans

        # Follow latest setting - auto-scroll to show newest data
        self.follow_latest = True  # Default: follow new scans

        # Time window and colormap settings
        self.time_window_hours = 24  # Default: 24 hours (options: 1, 6, 12, 24, 48)
        self.current_colormap = 'CET-R4'  # Default colormap
        self.crosshair_enabled = True  # Show crosshair by default
        self.contour_10hz_enabled = False  # 10Hz contour mode disabled by default (experimental)

        # Custom time axis for contour plot
        self.time_axis = None

        # Currently loaded file
        self.loaded_file_path = None

        # File boundary markers for visualization
        self.file_boundary_lines = []  # List of PlotCurveItem items
        self.file_boundary_labels = []  # List of TextItem items

        # Create UI
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(self.main_layout)

        # Create initial calibration prompt view
        self._create_calibration_prompt()

        # Note: Auto-load is triggered later via initialize_after_config_set()
        # when app_config is available

    def showEvent(self, event):
        """Override showEvent - historical data is loaded manually via button."""
        super().showEvent(event)
        # Historical data loading is now manual (via Load History button)
        # to avoid freezing the UI on tab switch

    def _create_calibration_prompt(self):
        """Create the initial calibration file prompt view."""
        # Center widget
        self.prompt_widget = QWidget()
        prompt_layout = QVBoxLayout()
        prompt_layout.setAlignment(Qt.AlignCenter)

        # Prompt label
        prompt_label = QLabel("Load a calibration file to start visualizing particle size distribution")
        prompt_label.setAlignment(Qt.AlignCenter)
        prompt_label.setWordWrap(True)
        prompt_label.setStyleSheet("font-size: 14px; color: #666;")

        # Load button
        self.load_calib_btn = QPushButton("Load Calibration File")
        self.load_calib_btn.setFixedSize(200, 40)
        self.load_calib_btn.clicked.connect(self._browse_calibration_file)

        prompt_layout.addWidget(prompt_label)
        prompt_layout.addSpacing(20)
        prompt_layout.addWidget(self.load_calib_btn, alignment=Qt.AlignCenter)

        self.prompt_widget.setLayout(prompt_layout)
        self.main_layout.addWidget(self.prompt_widget)

    def _create_plot_view(self):
        """Create the plot view with settings icon and averaging controls."""
        # Create plot widget container
        self.plot_widget = QWidget()
        plot_layout = QVBoxLayout()
        plot_layout.setContentsMargins(0, 0, 0, 0)

        # Top bar with controls and settings button
        top_bar = QHBoxLayout()

        # Follow latest toggle - auto-scroll to show newest data
        self.follow_checkbox = QCheckBox("Follow")
        self.follow_checkbox.setChecked(self.follow_latest)
        self.follow_checkbox.setToolTip("Auto-scroll to show latest scan data")
        self.follow_checkbox.setToolTipDuration(10000)  # 10 seconds
        self.follow_checkbox.toggled.connect(self._on_follow_toggle)
        top_bar.addWidget(self.follow_checkbox)

        top_bar.addSpacing(10)

        # File label to show which data file is loaded
        self.file_label = QLabel("")
        self.file_label.setStyleSheet("color: #666; font-size: 11px;")
        top_bar.addWidget(self.file_label)

        top_bar.addSpacing(10)

        # Date label showing current date
        self.date_label = QLabel("")
        self.date_label.setStyleSheet("color: #888; font-size: 11px;")
        top_bar.addWidget(self.date_label)

        top_bar.addStretch()

        # Scan progress indicator
        self.scan_status_label = QLabel("Idle")
        self.scan_status_label.setStyleSheet("color: #888; font-size: 11px; min-width: 70px;")
        top_bar.addWidget(self.scan_status_label)

        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setFixedWidth(80)
        self.scan_progress_bar.setFixedHeight(16)
        self.scan_progress_bar.setRange(0, 100)
        self.scan_progress_bar.setValue(0)
        self.scan_progress_bar.setTextVisible(False)
        self.scan_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555;
                border-radius: 3px;
                background-color: #333;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """)
        top_bar.addWidget(self.scan_progress_bar)

        top_bar.addSpacing(10)

        # Scan counter
        self.scan_counter_label = QLabel("Scans: 0")
        self.scan_counter_label.setStyleSheet("color: #aaa; font-size: 11px; font-weight: bold;")
        top_bar.addWidget(self.scan_counter_label)

        top_bar.addSpacing(10)

        # Load History button
        self.load_history_btn = QPushButton("Load History")
        self.load_history_btn.setFixedHeight(26)
        self.load_history_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                color: white;
                border: 1px solid #666;
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
            QPushButton:disabled {
                background-color: #333;
                color: #666;
            }
        """)
        self.load_history_btn.setToolTip("Load historical scan data from .dat files")
        self.load_history_btn.setToolTipDuration(10000)
        self.load_history_btn.clicked.connect(self._start_historical_data_load)
        top_bar.addWidget(self.load_history_btn)

        top_bar.addSpacing(5)

        # Settings button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setStyleSheet("font-size: 18px;")
        self.settings_btn.setToolTip("Contour plot settings")
        self.settings_btn.setToolTipDuration(10000)
        self.settings_btn.clicked.connect(self._show_settings_menu)
        top_bar.addWidget(self.settings_btn)

        plot_layout.addLayout(top_bar)

        # Create custom time axis for X-axis (shows HH:MM:SS based on scan index)
        self.time_axis = TimeAxisItemForContour(orientation='bottom')

        # Create custom bin axis for Y-axis (shows diameter values at bin boundaries)
        self.bin_axis = BinAxisItem(orientation='left')

        # Create PyQtGraph widget with custom axes
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.plot = self.graphics_widget.addPlot(axisItems={'bottom': self.time_axis, 'left': self.bin_axis})

        # Configure axes
        self.plot.setLabel('bottom', 'Scan Time')
        self.plot.setLabel('left', 'Particle Diameter (nm)')
        self.plot.showGrid(x=True, y=True, alpha=0.3)

        # Add extra padding at top for crosshair values overlay
        self.plot.getViewBox().setDefaultPadding(padding=0.08)

        # Create image item for contour
        self.image_item = pg.ImageItem()
        self.plot.addItem(self.image_item)

        # Use colormap from settings (default: CET-R4)
        self.data_cmap = pg.colormap.get(self.current_colormap)

        # Create colorbar (will show actual data range, not gaps)
        self.colorbar = pg.ColorBarItem(
            values=(0, 1),
            colorMap=self.data_cmap,
            label='log10(dN/dlogDp) [cm⁻³]'
        )
        self.colorbar.setImageItem(self.image_item)
        self.graphics_widget.addItem(self.colorbar)

        # Set background to black so NaN gaps show as black
        self.graphics_widget.setBackground('k')

        # Crosshair lines for value readout
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('w', width=1, style=Qt.DashLine))
        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('w', width=1, style=Qt.DashLine))
        self.plot.addItem(self.vLine, ignoreBounds=True)
        self.plot.addItem(self.hLine, ignoreBounds=True)
        self.vLine.hide()
        self.hLine.hide()

        # Value overlay label (top-left corner)
        self.value_label = pg.TextItem(text="", color='w', anchor=(0, 0))
        value_font = pg.QtGui.QFont()
        value_font.setStyleHint(pg.QtGui.QFont.Monospace)
        value_font.setPointSize(8)
        self.value_label.setFont(value_font)
        self.plot.addItem(self.value_label, ignoreBounds=True)
        self.value_label.hide()

        # Connect mouse move signal for crosshair
        self.plot.scene().sigMouseMoved.connect(self._on_mouse_moved)

        # Connect view range change to update file labels on zoom
        self.plot.sigRangeChanged.connect(self._on_view_range_changed)

        plot_layout.addWidget(self.graphics_widget)
        self.plot_widget.setLayout(plot_layout)

        # Create loading overlay (shown while historical data loads)
        self.loading_overlay = QWidget(self.plot_widget)
        self.loading_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.7);")
        loading_layout = QVBoxLayout(self.loading_overlay)
        loading_layout.setAlignment(Qt.AlignCenter)

        # Loading label
        self.loading_label = QLabel("Loading historical data...")
        self.loading_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        self.loading_label.setAlignment(Qt.AlignCenter)
        loading_layout.addWidget(self.loading_label)

        # Progress bar for loading overlay
        self.loading_progress_bar = QProgressBar()
        self.loading_progress_bar.setFixedWidth(300)
        self.loading_progress_bar.setFixedHeight(20)
        self.loading_progress_bar.setRange(0, 100)
        self.loading_progress_bar.setValue(0)
        self.loading_progress_bar.setTextVisible(True)
        self.loading_progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #666;
                border-radius: 5px;
                background-color: #333;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
        """)
        loading_layout.addWidget(self.loading_progress_bar, alignment=Qt.AlignCenter)

        # Detail label for current operation
        self.loading_detail_label = QLabel("")
        self.loading_detail_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.loading_detail_label.setAlignment(Qt.AlignCenter)
        loading_layout.addWidget(self.loading_detail_label)

        self.loading_overlay.hide()

        # Hide initially
        self.plot_widget.hide()
        self.main_layout.addWidget(self.plot_widget)

    def _show_loading_overlay(self):
        """Show loading overlay on the plot."""
        if hasattr(self, 'loading_overlay') and hasattr(self, 'plot_widget'):
            self.loading_overlay.setGeometry(self.plot_widget.rect())
            self.loading_overlay.raise_()
            self.loading_overlay.show()
            # Process events to ensure overlay is visible
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()

    def _hide_loading_overlay(self):
        """Hide loading overlay."""
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay.hide()

    def resizeEvent(self, event):
        """Handle resize to keep loading overlay properly sized."""
        super().resizeEvent(event)
        if hasattr(self, 'loading_overlay') and hasattr(self, 'plot_widget'):
            self.loading_overlay.setGeometry(self.plot_widget.rect())

    def _on_avg_toggle(self, enabled: bool):
        """Handle averaging checkbox toggle."""
        self.averaging_enabled = enabled
        self._render_contour()

    def _on_avg_n_changed(self, value: int):
        """Handle averaging N spinbox change."""
        self.avg_n = value
        if self.averaging_enabled:
            self._render_contour()

    def _on_follow_toggle(self, enabled: bool):
        """Handle follow latest checkbox toggle."""
        self.follow_latest = enabled
        if enabled:
            # Scroll to show latest data
            self._render_contour()

    def _on_mouse_moved(self, pos):
        """Handle mouse move events to show crosshair and values."""
        if not hasattr(self, 'plot') or not hasattr(self, 'vLine'):
            return

        # Skip if crosshair is disabled
        if not self.crosshair_enabled:
            return

        try:
            if self.plot.sceneBoundingRect().contains(pos):
                mouse_point = self.plot.vb.mapSceneToView(pos)
                x, y = mouse_point.x(), mouse_point.y()

                # Update crosshair position
                self.vLine.setPos(x)
                self.hLine.setPos(y)
                self.vLine.show()
                self.hLine.show()

                # Get concentration value from image at position
                conc_value = self._get_value_at_position(x, y)

                # Format time from decimal hours
                hours = int(x) % 24
                minutes = int((x - int(x)) * 60)
                time_str = f"{hours:02d}:{minutes:02d}"

                # Find which bin the cursor is in
                # Y-axis uses bin indices (0 to num_bins)
                dp_range_str = f"{y:.1f}"  # Default if no bins
                inside_data_region = False
                if hasattr(self, 'bin_limits_dp') and self.bin_limits_dp is not None and hasattr(self, 'num_bins'):
                    bin_limits = self.bin_limits_dp
                    num_bins = self.num_bins

                    # Check if cursor is inside the data region (bin index 0 to num_bins)
                    if y >= 0 and y < num_bins:
                        inside_data_region = True
                        # Get the bin index directly from y coordinate
                        bin_idx = int(y)
                        bin_idx = max(0, min(bin_idx, num_bins - 1))

                        # Get the actual bin limits for that bin index
                        dp_range_str = f"{bin_limits[bin_idx]:.1f} - {bin_limits[bin_idx + 1]:.1f} nm"
                    elif y < 0:
                        dp_range_str = f"< {bin_limits[0]:.1f} nm"
                    else:
                        dp_range_str = f"> {bin_limits[-1]:.1f} nm"

                # Update value label
                # conc_value is log10(dN/dlogDp), show the actual value only if inside data region
                if inside_data_region and conc_value is not None and not np.isnan(conc_value):
                    actual_conc = 10 ** conc_value

                    # Calculate cumulative sums below and above current bin
                    cumul_below, cumul_above = self._get_cumulative_at_position(x, bin_idx)
                    cumul_str = f"Σ<: {cumul_below:.0f} | Σ>: {cumul_above:.0f}" if cumul_below is not None else ""

                    label_text = f"Time: {time_str}\nDp: {dp_range_str}\ndN/dlogDp: {actual_conc:.0f}"
                    if cumul_str:
                        label_text += f"\n{cumul_str}"
                    self.value_label.setText(label_text)
                else:
                    self.value_label.setText(f"Time: {time_str}\nDp: {dp_range_str}\ndN/dlogDp: --")

                # Position label in top-left of visible area
                view_range = self.plot.viewRange()
                self.value_label.setPos(view_range[0][0], view_range[1][1])
                self.value_label.show()
            else:
                self.vLine.hide()
                self.hLine.hide()
                self.value_label.hide()
        except Exception:
            pass  # Silently ignore errors during hover

    def _get_value_at_position(self, x, y):
        """Get concentration value from image at given plot coordinates (y is bin index)."""
        if not hasattr(self, '_last_z_data') or self._last_z_data is None:
            return None

        try:
            # Get stored transform info (y is in bin index coordinates)
            pos_x = getattr(self, '_last_pos_x', 0)
            width = getattr(self, '_last_width', 24)
            num_bins = getattr(self, '_last_num_bins', 6)

            # Convert plot coordinates to image indices
            z_data = self._last_z_data
            n_time, n_bins = z_data.shape

            # X index
            x_frac = (x - pos_x) / width
            x_idx = int(x_frac * n_time)

            # Y index (y is bin index, directly maps to image row)
            y_idx = int(y)

            # Check bounds
            if 0 <= x_idx < n_time and 0 <= y_idx < n_bins:
                return z_data[x_idx, y_idx]
            return None
        except Exception:
            return None

    def _on_view_range_changed(self, view_box=None, range_changed=None):
        """Handle view range changes (zoom/pan) to update file boundary labels visibility."""
        # Only update if we have scans and file boundaries to show
        if not hasattr(self, 'scan_buffer') or len(self.scan_buffer) == 0:
            return
        if not hasattr(self, '_last_scans_in_range'):
            return

        # Redraw file boundaries with updated view range
        try:
            self._update_file_boundary_labels()
        except Exception:
            pass  # Silently ignore errors during updates

    def _update_file_boundary_labels(self):
        """Update file boundary labels based on current zoom level."""
        if not hasattr(self, '_last_file_ranges') or not self._last_file_ranges:
            return

        # Get current view range
        view_range = self.plot.viewRange()
        view_x_min, view_x_max = view_range[0]
        view_width_hours = view_x_max - view_x_min

        # Get plot widget width in pixels
        plot_width_pixels = self.plot.width() if self.plot.width() > 0 else 800

        # Remove old labels only (keep tick marks)
        for label in self.file_boundary_labels:
            self.plot.removeItem(label)
        self.file_boundary_labels = []

        # Get stored positions
        y_top = getattr(self, '_last_y_top', self.num_bins if hasattr(self, 'num_bins') else 6)

        for file_name, x_start, x_end in self._last_file_ranges:
            range_width_hours = x_end - x_start

            # Calculate what fraction of the view this file range occupies
            view_fraction = range_width_hours / view_width_hours if view_width_hours > 0 else 0

            # Calculate approximate pixel width for this file range
            range_width_pixels = view_fraction * plot_width_pixels

            # Estimate label width in pixels (~7 pixels per character at 8pt font)
            base_name = file_name.replace('.dat', '')
            estimated_label_pixels = len(base_name) * 7

            # Only show label if it fits with some margin
            if range_width_pixels >= estimated_label_pixels + 10:
                # Position label centered in file's time range
                x_center = (x_start + x_end) / 2
                label = pg.TextItem(
                    text=base_name,
                    color='w',
                    anchor=(0.5, 1)  # Anchor at center-bottom
                )
                label.setPos(x_center, y_top)
                label.setFont(pg.QtGui.QFont('Arial', 8))
                self.plot.addItem(label)
                self.file_boundary_labels.append(label)

    def _get_cumulative_at_position(self, x, bin_idx):
        """Get cumulative dN/dlogDp below and above the current bin at given x position.

        Returns:
            Tuple of (sum_below, sum_above) or (None, None) if data unavailable
        """
        if not hasattr(self, '_last_z_data') or self._last_z_data is None:
            return None, None

        try:
            pos_x = getattr(self, '_last_pos_x', 0)
            width = getattr(self, '_last_width', 24)

            z_data = self._last_z_data
            n_time, n_bins = z_data.shape

            # Get x index
            x_frac = (x - pos_x) / width
            x_idx = int(x_frac * n_time)

            if x_idx < 0 or x_idx >= n_time:
                return None, None

            # Get the column of values at this time point
            column = z_data[x_idx, :]

            # Convert from log10 to linear values, handling NaN
            linear_values = np.zeros(n_bins)
            for i in range(n_bins):
                if not np.isnan(column[i]):
                    linear_values[i] = 10 ** column[i]

            # Sum below current bin (smaller particles, lower indices)
            sum_below = np.sum(linear_values[:bin_idx]) if bin_idx > 0 else 0

            # Sum above current bin (larger particles, higher indices)
            sum_above = np.sum(linear_values[bin_idx + 1:]) if bin_idx < n_bins - 1 else 0

            return sum_below, sum_above
        except Exception:
            return None, None

    def _set_time_window(self, hours):
        """Set the time window for the contour plot."""
        old_hours = self.time_window_hours
        self.time_window_hours = hours
        self._save_contour_settings()

        # If increasing the time window, need to reload historical data
        if hours > old_hours:
            self._historical_data_loaded = False
            self._start_historical_data_load()
        else:
            self._render_contour()

    def _set_colormap(self, cmap_name):
        """Set the colormap for the contour plot."""
        self.current_colormap = cmap_name
        self.data_cmap = pg.colormap.get(cmap_name)
        self.colorbar.setColorMap(self.data_cmap)
        self._save_contour_settings()
        self._render_contour()

    def _toggle_crosshair(self, enabled):
        """Toggle crosshair visibility."""
        self.crosshair_enabled = enabled
        self._save_contour_settings()
        if not enabled:
            # Hide crosshair elements
            if hasattr(self, 'vLine'):
                self.vLine.hide()
            if hasattr(self, 'hLine'):
                self.hLine.hide()
            if hasattr(self, 'value_label'):
                self.value_label.hide()

    def _toggle_10hz_contour(self, enabled):
        """Toggle 10Hz contour mode."""
        self.contour_10hz_enabled = enabled
        self._save_contour_settings()

    def initialize_after_config_set(self):
        """
        Initialize contour tab after app_config is set.
        Called by PSMWidget after setting app_config.
        This triggers auto-load of calibration and historical data.
        """
        # Load saved contour settings
        self._load_contour_settings()
        self._try_autoload_calibration()

    def _load_contour_settings(self):
        """Load saved contour plot settings from device config."""
        try:
            extra = self.device_config.extra_params
            self.time_window_hours = extra.get('contour_time_window', 24)
            self.current_colormap = extra.get('contour_colormap', 'CET-R4')
            self.crosshair_enabled = extra.get('contour_crosshair', True)
            self.contour_10hz_enabled = extra.get('contour_10hz_enabled', False)

            # Apply colormap if plot exists
            if hasattr(self, 'data_cmap'):
                self.data_cmap = pg.colormap.get(self.current_colormap)
                if hasattr(self, 'colorbar'):
                    self.colorbar.setColorMap(self.data_cmap)
        except Exception:
            pass  # Use defaults

    def _save_contour_settings(self):
        """Save contour plot settings to device config."""
        try:
            self.device_config.extra_params['contour_time_window'] = self.time_window_hours
            self.device_config.extra_params['contour_colormap'] = self.current_colormap
            self.device_config.extra_params['contour_crosshair'] = self.crosshair_enabled
            self.device_config.extra_params['contour_10hz_enabled'] = self.contour_10hz_enabled
            if self.on_config_changed:
                self.on_config_changed()
        except Exception:
            pass

    def _try_autoload_calibration(self):
        """Try to auto-load calibration file from saved parameter."""
        try:
            # Get calibration path from device config extra_params
            calib_path = self.device_config.extra_params.get('calibration_file_path', '')
            if calib_path and os.path.exists(calib_path):
                self._load_calibration(calib_path, auto_load=True)
        except Exception:
            # Silently ignore if parameter doesn't exist (old config)
            pass

    def _browse_calibration_file(self):
        """Open file dialog to select calibration file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            'Select Calibration File',
            '',
            'All Files (*.*);;Text Files (*.txt);;TSV Files (*.tsv)'
        )
        if file_path:
            self._load_calibration(file_path)

    def _fit_calibration(self, calibration_df: pd.DataFrame) -> pd.DataFrame:
        """
        Extend calibration to instrument max range ONLY if needed.

        For PSM 2.0: max range is 12nm
        For Retrofit: max range is 4nm

        If calibration already covers the range (has points >= max_dp),
        no extrapolation is needed - use calibration data as-is.
        Only extrapolates using last 3 points when calibration doesn't reach max_dp.
        """
        max_dp = 12.0 if self.is_psm2 else 4.0
        min_satflow = 0.05 if self.is_psm2 else 0.1

        # If calibration already reaches max_dp, no extrapolation needed
        if calibration_df['cal_diameter'].max() >= max_dp:
            return calibration_df

        # Extrapolate: fit last 3 points to extend to max_dp
        slope, intercept = np.polyfit(
            calibration_df['cal_satflow'].iloc[-3:],
            calibration_df['cal_diameter'].iloc[-3:],
            1
        )

        # Calculate satflow where diameter equals max_dp
        satflow_for_max_dp = (max_dp - intercept) / slope

        # Enforce minimum satflow limit
        if satflow_for_max_dp < min_satflow:
            satflow_for_max_dp = min_satflow

        # Get detection efficiency from last point (use same value for extrapolated point)
        last_efficiency = calibration_df['cal_maxdeteff'].iloc[-1]

        # Add new row with extrapolated values
        new_row = pd.DataFrame({
            'cal_satflow': [satflow_for_max_dp],
            'cal_diameter': [max_dp],
            'cal_maxdeteff': [last_efficiency]
        })
        calibration_df = pd.concat([calibration_df, new_row], ignore_index=True)

        # Sort by satflow in descending order and reset index
        calibration_df = calibration_df.sort_values(by=['cal_satflow'], ascending=False)
        calibration_df = calibration_df.reset_index(drop=True)

        return calibration_df

    def _load_calibration(self, file_path: str, auto_load: bool = False):
        """
        Load calibration file and initialize bins using fixed PSM 2.0 bin limits.

        Args:
            file_path: Path to calibration file
            auto_load: If True, this is an auto-load on startup (don't save config again)

        Expected format: Tab-delimited with columns:
        - cal_satflow (lpm)
        - cal_diameter (nm)
        - cal_maxdeteff (detection efficiency)
        """
        try:
            # Read calibration file
            self.calibration_df = pd.read_csv(file_path, delimiter='\t')

            # Ensure required columns exist
            if len(self.calibration_df.columns) < 3:
                raise ValueError("Calibration file must have at least 3 columns: satflow, diameter, efficiency")

            # Rename columns if they don't have standard names
            if 'cal_satflow' not in self.calibration_df.columns:
                self.calibration_df.columns = ['cal_satflow', 'cal_diameter', 'cal_maxdeteff'] + list(self.calibration_df.columns[3:])

            # Extend calibration to full instrument range (12nm for PSM 2.0, 4nm for Retrofit)
            self.calibration_df = self._fit_calibration(self.calibration_df)

            # Get min/max diameter from calibration
            min_diameter = self.calibration_df['cal_diameter'].min()
            max_diameter = self.calibration_df['cal_diameter'].max()

            # Fixed PSM 2.0 6-bin limits (intermediate values between min and max)
            fixed_inner_limits = [1.5, 1.7, 2.5, 5.0, 8.0]

            # Build bin limits array: min_dp + inner limits within range + max_dp
            inner_limits_in_range = [x for x in fixed_inner_limits if min_diameter < x < max_diameter]
            self.bin_limits_dp = np.array([min_diameter] + inner_limits_in_range + [max_diameter])

            num_bins = len(self.bin_limits_dp) - 1

            # Calculate bin centers (geometric mean between adjacent limits)
            self.bin_centers_dp = self._geom_means(self.bin_limits_dp)

            # Calculate saturator flow bin limits for data binning
            # Uses the same algorithm as PSM Inversion Tool
            self.bin_limits_flow = self._calculate_flow_bins(self.bin_limits_dp)

            # Store number of bins
            self.num_bins = num_bins

            # Create detection efficiency interpolator (still useful for some operations)
            self.detection_efficiency = interp1d(
                self.calibration_df['cal_diameter'],
                self.calibration_df['cal_maxdeteff'],
                kind='linear',
                bounds_error=False,
                fill_value=(self.calibration_df['cal_maxdeteff'].iloc[0],
                           self.calibration_df['cal_maxdeteff'].iloc[-1])
            )

            # Save calibration path to config
            self.device_config.extra_params['calibration_file_path'] = file_path

            # Mark calibration as loaded
            self.calibration_loaded = True

            # Switch to plot view
            self.prompt_widget.hide()
            if not self.plot_initialized:
                self._create_plot_view()
                self.plot_initialized = True
            self.plot_widget.show()

            # Trigger config save for manual calibration load (not auto-load)
            if not auto_load and self.on_config_changed:
                self.on_config_changed()

        except Exception:
            pass  # Silently handle calibration loading errors

    def _diameter_to_flow(self, diameters: np.ndarray) -> np.ndarray:
        """Convert particle diameters to saturator flow rates using calibration."""
        # Interpolate diameter -> flow relationship
        flow_interp = interp1d(
            self.calibration_df['cal_diameter'],
            self.calibration_df['cal_satflow'],
            kind='linear',
            bounds_error=False,
            fill_value=(self.calibration_df['cal_satflow'].iloc[0],
                       self.calibration_df['cal_satflow'].iloc[-1])
        )
        return flow_interp(diameters)

    def _geom_means(self, x: np.ndarray) -> np.ndarray:
        """
        Calculate geometric mean between adjacent elements.
        Used for calculating bin centers from bin limits.
        """
        return np.sqrt(x[:-1] * x[1:])

    def _get_scan_times(self) -> tuple:
        """Get scan timing parameters from PSM measure tab.

        Returns:
            Tuple of (up_scan_time, down_scan_time) in seconds
        """
        # Try to get from parent PSM widget's measure tab
        try:
            # self is PSMContourTab, parent should be PSMWidget
            parent = self.parent()
            if parent and hasattr(parent, 'measure_tab'):
                measure_tab = parent.measure_tab
                up_time = measure_tab.set_up_scan_time.value_spinbox.value()
                down_time = measure_tab.set_down_scan_time.value_spinbox.value()
                return (up_time, down_time)
        except Exception:
            pass

        # Fallback defaults (typical 240s total: 10+110+10+110)
        return (110, 110)

    def _calculate_flow_bins(self, fixed_bin_limits: np.ndarray) -> np.ndarray:
        """
        Calculate saturator flow bin limits from diameter limits.

        This follows the PSM Inversion Tool algorithm exactly:
        1. Calculate geometric mean diameters between fixed limits (binning_limit)
        2. Append max edge, then prepend min edge to binning_limit
        3. Convert diameter binning limits to flow via calibration interpolation
        4. Flip to get ascending flow order (matches original algorithm)

        Args:
            fixed_bin_limits: Array of diameter bin edges (nm)

        Returns:
            Array of saturator flow bin limits (lpm) in ASCENDING order (low flow to high flow)
        """
        fixed_bin_limits = np.array(fixed_bin_limits)

        # Calculate geometric mean diameters between bin limits
        binning_limit = self._geom_means(fixed_bin_limits)

        # Add min and max edges (same order as original: append max, then prepend min)
        max_bin_edge = fixed_bin_limits[-1]
        min_bin_edge = fixed_bin_limits[0]
        binning_limit = np.append(binning_limit, max_bin_edge)
        binning_limit = np.append(min_bin_edge, binning_limit)
        # Result: [min_dp, geom_means..., max_dp] in ascending diameter order

        # Convert diameter to flow via calibration interpolation and FLIP
        # This matches the original: np.flip(np.interp(binning_limit, cal_diameter, cal_satflow))
        bin_lims = np.flip(np.interp(
            binning_limit,
            self.calibration_df['cal_diameter'].values,
            self.calibration_df['cal_satflow'].values
        ))
        # Result: ascending flow order [low_flow, ..., high_flow]
        # low_flow = large diameter, high_flow = small diameter

        return bin_lims

    def _show_settings_menu(self):
        """Show settings dropdown menu."""
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        menu.setToolTipDuration(10000)  # 10 seconds for menu tooltips
        menu.setStyleSheet("""
            QMenu {
                padding: 5px;
            }
            QToolTip {
                background-color: #333;
                color: white;
                border: 1px solid #555;
                padding: 8px;
                font-size: 12px;
            }
        """)

        # --- Averaging controls ---
        avg_widget = QWidget()
        avg_widget.setStyleSheet("QWidget { background: transparent; }")
        avg_layout = QHBoxLayout(avg_widget)
        avg_layout.setContentsMargins(10, 5, 10, 5)

        avg_checkbox = QCheckBox("Average over")
        avg_checkbox.setChecked(self.averaging_enabled)
        avg_checkbox.toggled.connect(self._on_avg_toggle)
        avg_layout.addWidget(avg_checkbox)

        avg_spinbox = QSpinBox()
        avg_spinbox.setRange(1, 50)
        avg_spinbox.setValue(self.avg_n)
        avg_spinbox.setMinimumWidth(80)
        avg_spinbox.setSuffix(" scans")
        avg_spinbox.setStyleSheet("""
            QSpinBox {
                padding: 3px 5px;
                border: 1px solid #555;
                border-radius: 3px;
                background: #2a2a2a;
                color: white;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                border: none;
                background: #444;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background: #555;
            }
            QSpinBox::up-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 6px solid #aaa;
            }
            QSpinBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #aaa;
            }
        """)
        avg_spinbox.valueChanged.connect(self._on_avg_n_changed)
        avg_layout.addWidget(avg_spinbox)

        avg_action = QWidgetAction(menu)
        avg_action.setDefaultWidget(avg_widget)
        menu.addAction(avg_action)

        menu.addSeparator()

        # --- Time window selector ---
        time_label = menu.addAction("Time window:")
        time_label.setEnabled(False)

        time_group = QActionGroup(menu)
        time_group.setExclusive(True)
        for hours in [1, 6, 12, 24, 48]:
            action = menu.addAction(f"  {hours}h")
            action.setCheckable(True)
            action.setChecked(self.time_window_hours == hours)
            action.triggered.connect(lambda checked, h=hours: self._set_time_window(h))
            time_group.addAction(action)

        menu.addSeparator()

        # --- Colormap selector ---
        cmap_label = menu.addAction("Color map:")
        cmap_label.setEnabled(False)

        cmap_group = QActionGroup(menu)
        cmap_group.setExclusive(True)
        colormaps = ['CET-R4', 'viridis', 'plasma', 'inferno', 'magma', 'cividis']
        for cmap_name in colormaps:
            action = menu.addAction(f"  {cmap_name}")
            action.setCheckable(True)
            action.setChecked(self.current_colormap == cmap_name)
            action.triggered.connect(lambda checked, c=cmap_name: self._set_colormap(c))
            cmap_group.addAction(action)

        menu.addSeparator()

        # --- Crosshair toggle ---
        crosshair_action = menu.addAction("Show crosshair")
        crosshair_action.setCheckable(True)
        crosshair_action.setChecked(self.crosshair_enabled)
        crosshair_action.setToolTip("Show crosshair and values when hovering over the plot")
        crosshair_action.triggered.connect(self._toggle_crosshair)

        # --- 10Hz contour toggle ---
        hz10_action = menu.addAction("10Hz contour mode (experimental)")
        hz10_action.setCheckable(True)
        hz10_action.setChecked(self.contour_10hz_enabled)
        hz10_action.setToolTip("Use 10Hz data for live contour updates (requires 10Hz logging enabled)")
        hz10_action.triggered.connect(self._toggle_10hz_contour)

        menu.addSeparator()

        # --- Data actions ---
        reload_action = menu.addAction("Reload historical data")
        reload_action.setToolTip("Reload scan data from .dat files")
        reload_action.triggered.connect(lambda: (setattr(self, '_historical_data_loaded', False), self._start_historical_data_load()))

        clear_buffer_action = menu.addAction("Clear scan buffer")
        clear_buffer_action.setToolTip("Clear all stored scans (historical and live) and reset the contour plot")
        clear_buffer_action.triggered.connect(self._clear_scan_buffer)

        menu.addSeparator()

        # --- Export ---
        export_action = menu.addAction("Export as PNG")
        export_action.setToolTip("Save the current contour plot as a PNG image")
        export_action.triggered.connect(self._export_png)

        menu.addSeparator()

        # --- Calibration ---
        change_action = menu.addAction("Change calibration file")
        change_action.setToolTip("Select a different calibration file (.cal) for the PSM")
        change_action.triggered.connect(self._browse_calibration_file)

        clear_action = menu.addAction("Clear calibration")
        clear_action.setToolTip("Remove the current calibration and return to calibration file selection")
        clear_action.triggered.connect(self._clear_calibration)

        # Show menu at button position
        menu.exec_(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))

    def _clear_calibration(self):
        """Clear calibration and return to prompt view."""
        self.calibration_loaded = False
        self._historical_data_loaded = False  # Reset flag
        self.calibration_df = None
        self.bin_limits_dp = None
        self.bin_centers_dp = None
        self.bin_limits_flow = None
        self.detection_efficiency = None
        self.scan_buffer = []
        self._current_scan = None

        # Clear parameter
        self.device_config.extra_params['calibration_file_path'] = ''

        # Switch back to prompt view
        self.plot_widget.hide()
        self.prompt_widget.show()

    def _clear_scan_buffer(self):
        """Clear the scan buffer and reset plot."""
        self.scan_buffer = []
        self._current_scan = None
        self._prev_saturator_flow = None  # Reset 10Hz interpolation state
        self._render_contour()

    def _export_png(self):
        """Export the current contour plot as a PNG image."""
        if not hasattr(self, 'graphics_widget'):
            return

        from PyQt5.QtWidgets import QFileDialog
        from datetime import datetime

        # Generate default filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"PSM_contour_{timestamp}.png"

        # Get save path from user
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Contour Plot",
            default_name,
            "PNG Images (*.png);;All Files (*)"
        )

        if file_path:
            try:
                # Use pyqtgraph's built-in export
                import pyqtgraph.exporters as exporters
                exporter = exporters.ImageExporter(self.graphics_widget.scene())
                exporter.parameters()['width'] = 1920  # High resolution
                exporter.export(file_path)
            except Exception as e:
                logging.error(f"Error exporting PNG: {e}")

    def _should_use_10hz(self, data_holder) -> bool:
        """Check if 10Hz mode should be used for live inversion.

        Returns True only if:
        - contour_10hz_enabled is True (user setting)
        - data_holder is available
        - 10Hz logging is enabled in PSM config
        - A CPC is connected
        - CPC widget has valid ten_hz_data
        """
        # Check if 10Hz contour mode is enabled (user toggle)
        if not self.contour_10hz_enabled:
            return False

        if data_holder is None:
            return False

        # Check if 10Hz logging is enabled in PSM config
        if not self.device_config.extra_params.get('10_hz', False):
            return False

        # Get connected CPC ID
        cpc_id = self.device_config.extra_params.get('connected_cpc', 'None')
        if cpc_id == 'None':
            return False

        try:
            cpc_id = int(cpc_id)
        except (ValueError, TypeError):
            return False

        # Get CPC widget
        cpc_widget = data_holder.device_widgets.get(cpc_id)
        if cpc_widget is None or not hasattr(cpc_widget, 'ten_hz_data'):
            return False

        ten_hz_data = cpc_widget.ten_hz_data
        if ten_hz_data is None or len(ten_hz_data) != 10:
            return False

        # Check at least some values are valid
        valid_count = sum(1 for v in ten_hz_data if not np.isnan(float(v)))
        return valid_count > 0

    def update_contour(self, current_data, data_holder=None):
        """
        Update contour plot with new data point(s).
        Called every second from plot_manager.

        When 10Hz is enabled and available:
        - Gets 10 concentration values from CPC's ten_hz_data
        - Interpolates saturator flow from previous to current (linear)
        - Adds 10 data points per call instead of 1

        When 10Hz is disabled or unavailable:
        - Falls back to 1Hz behavior (single point per call)

        Scan status values:
        - 0 = bottom wait (end of down scan)
        - 1 = up scan (saturator flow increasing)
        - 2 = top wait (end of up scan)
        - 3 = down scan (saturator flow decreasing)
        - 4 = don't log
        - 9 = idle

        Two scans per cycle:
        - UP scan: status 1 + status 2
        - DOWN scan: status 3 + status 0

        Args:
            current_data: PSMData dataclass instance
            data_holder: DataHolder for accessing connected CPC widget (optional)
        """
        if not self.calibration_loaded:
            return

        # Dispatch based on 10Hz availability
        if self._should_use_10hz(data_holder):
            self._update_contour_10hz(current_data, data_holder)
        else:
            self._update_contour_1hz(current_data)

    def _update_contour_1hz(self, current_data):
        """Handle 1Hz data collection for contour plot (original behavior)."""
        # Normalize scan status
        scan_status_raw = str(current_data.scan_status).strip()
        try:
            scan_status = str(int(float(scan_status_raw)))
        except (ValueError, TypeError):
            scan_status = scan_status_raw

        # Skip status 4 (don't log)
        if scan_status == "4":
            self._prev_scan_status = scan_status
            return

        # Detect scan start transitions
        # UP scan starts when transitioning TO status "1"
        if scan_status == "1" and self._prev_scan_status != "1":
            # Finalize previous scan if exists
            if self._current_scan is not None:
                self._finalize_scan()
            # Start new UP scan
            self._current_scan = {
                'times': [],
                'satflows': [],
                'concentrations': [],
                'type': 'up'
            }

        # DOWN scan starts when transitioning TO status "3"
        elif scan_status == "3" and self._prev_scan_status != "3":
            # Finalize previous scan if exists
            if self._current_scan is not None:
                self._finalize_scan()
            # Start new DOWN scan
            self._current_scan = {
                'times': [],
                'satflows': [],
                'concentrations': [],
                'type': 'down'
            }

        # Accumulate data during scan
        if self._current_scan is not None:
            include_point = False
            # UP scan: include status 1 and 2 (top wait)
            if self._current_scan['type'] == 'up' and scan_status in ["1", "2"]:
                include_point = True
            # DOWN scan: include status 3 and 0 (bottom wait)
            elif self._current_scan['type'] == 'down' and scan_status in ["3", "0"]:
                include_point = True

            if include_point:
                # Only add data if dilution-corrected concentration is available
                if not np.isnan(current_data.saturator_flow) and not np.isnan(current_data.concentration_psm):
                    self._current_scan['times'].append(pd.Timestamp.now())
                    self._current_scan['satflows'].append(current_data.saturator_flow)
                    self._current_scan['concentrations'].append(current_data.concentration_psm)

        # Update scan progress UI
        self._update_scan_progress(scan_status, current_data.saturator_flow)

        # Update previous status
        self._prev_scan_status = scan_status

    def _update_contour_10hz(self, current_data, data_holder):
        """Handle 10Hz data collection for contour plot.

        Collects 10 concentration values from CPC's ten_hz_data buffer
        and interpolates saturator flow from previous to current value.
        """
        # Get CPC widget and 10Hz data
        cpc_id = int(self.device_config.extra_params.get('connected_cpc'))
        cpc_widget = data_holder.device_widgets.get(cpc_id)
        ten_hz_data = cpc_widget.ten_hz_data

        current_flow = current_data.saturator_flow

        # Normalize scan status
        scan_status_raw = str(current_data.scan_status).strip()
        try:
            scan_status = str(int(float(scan_status_raw)))
        except (ValueError, TypeError):
            scan_status = scan_status_raw

        # Skip status 4 (don't log)
        if scan_status == "4":
            self._prev_scan_status = scan_status
            self._prev_saturator_flow = current_flow
            return

        # Detect scan start transitions
        if scan_status == "1" and self._prev_scan_status != "1":
            if self._current_scan is not None:
                self._finalize_scan()
            self._current_scan = {
                'times': [], 'satflows': [], 'concentrations': [], 'type': 'up'
            }
            self._scan_start_time = pd.Timestamp.now()  # Track when scan started
            self._prev_saturator_flow = None  # Reset on new scan

        elif scan_status == "3" and self._prev_scan_status != "3":
            if self._current_scan is not None:
                self._finalize_scan()
            self._current_scan = {
                'times': [], 'satflows': [], 'concentrations': [], 'type': 'down'
            }
            self._scan_start_time = pd.Timestamp.now()  # Track when scan started
            self._prev_saturator_flow = None  # Reset on new scan

        # Accumulate data during scan
        if self._current_scan is not None:
            include_point = False
            if self._current_scan['type'] == 'up' and scan_status in ["1", "2"]:
                include_point = True
            elif self._current_scan['type'] == 'down' and scan_status in ["3", "0"]:
                include_point = True

            if include_point and not np.isnan(current_flow):
                # Skip if corrections not available
                dilution_corr = current_data.cpc_dilution_correction
                poly_corr = current_data.poly_correction
                if np.isnan(dilution_corr) or np.isnan(poly_corr) or poly_corr == 0:
                    # Store flow for next interpolation but don't add data
                    self._prev_saturator_flow = current_flow
                    self._prev_scan_status = scan_status
                    return

                # Calculate saturator flow for 10 points using exponential scan profile
                if self._scan_start_time is None or self.bin_limits_flow is None:
                    # Fallback to current flow if we don't have timing info
                    flows = np.full(10, current_flow)
                else:
                    # Get scan parameters
                    up_scan_time, down_scan_time = self._get_scan_times()
                    min_flow = self.bin_limits_flow.min()
                    max_flow = self.bin_limits_flow.max()

                    # Select scan time based on scan type
                    if self._current_scan['type'] == 'up':
                        scan_time = up_scan_time
                    else:
                        scan_time = down_scan_time

                    # Calculate scan power for exponential profile
                    scan_power = (max_flow / min_flow) ** (1.0 / scan_time)

                    # Calculate time since scan started
                    base_time = pd.Timestamp.now()
                    time_since_start = (base_time - self._scan_start_time).total_seconds()

                    # Generate 10 flow values at 100ms intervals
                    flows = np.zeros(10)
                    for i in range(10):
                        # Time offset: index 0 is -900ms, index 9 is now (0ms)
                        t = time_since_start + (i - 9) * 0.1
                        if t < 0:
                            t = 0

                        if self._current_scan['type'] == 'up':
                            flows[i] = min_flow * (scan_power ** t)
                        else:  # down
                            flows[i] = max_flow * ((1 / scan_power) ** t)

                    # Clamp flows to valid range
                    flows = np.clip(flows, min_flow, max_flow)

                # Add 10 data points
                base_time = pd.Timestamp.now()
                for i in range(10):
                    try:
                        conc_float = float(ten_hz_data[i])
                    except (ValueError, TypeError):
                        continue

                    if not np.isnan(conc_float):
                        # Apply dilution and poly corrections
                        corrected_conc = conc_float * dilution_corr / poly_corr
                        # Time offset: index 0 is -900ms, index 9 is now (0ms)
                        time_offset = pd.Timedelta(milliseconds=(i - 9) * 100)
                        self._current_scan['times'].append(base_time + time_offset)
                        self._current_scan['satflows'].append(flows[i])
                        self._current_scan['concentrations'].append(corrected_conc)

        # Store current flow for next interpolation
        self._prev_saturator_flow = current_flow

        # Update scan progress UI
        self._update_scan_progress(scan_status, current_flow)
        self._prev_scan_status = scan_status

    def _update_scan_progress(self, scan_status: str, current_satflow: float):
        """Update the scan progress bar and status label."""
        if not hasattr(self, 'scan_status_label') or not hasattr(self, 'scan_progress_bar'):
            return

        # Get satflow range from calibration
        if self.bin_limits_flow is None:
            return

        min_flow = self.bin_limits_flow.min()
        max_flow = self.bin_limits_flow.max()
        flow_range = max_flow - min_flow

        if flow_range <= 0:
            return

        # Update status label and progress based on scan type
        if self._current_scan is not None and scan_status in ["1", "2", "3", "0"]:
            scan_type = self._current_scan['type']

            if scan_type == 'up':
                self.scan_status_label.setText("Up scan")
                self.scan_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; min-width: 70px;")
                # Progress: 0% at min_flow, 100% at max_flow
                progress = (current_satflow - min_flow) / flow_range * 100
            else:  # down
                self.scan_status_label.setText("Down scan")
                self.scan_status_label.setStyleSheet("color: #2196F3; font-size: 11px; min-width: 70px;")
                # Progress: 0% at max_flow, 100% at min_flow
                progress = (max_flow - current_satflow) / flow_range * 100

            # Clamp progress to 0-100
            progress = max(0, min(100, progress))
            self.scan_progress_bar.setValue(int(progress))

            # Update progress bar color based on scan type
            if scan_type == 'up':
                self.scan_progress_bar.setStyleSheet("""
                    QProgressBar { border: 1px solid #555; border-radius: 3px; background-color: #333; }
                    QProgressBar::chunk { background-color: #4CAF50; border-radius: 2px; }
                """)
            else:
                self.scan_progress_bar.setStyleSheet("""
                    QProgressBar { border: 1px solid #555; border-radius: 3px; background-color: #333; }
                    QProgressBar::chunk { background-color: #2196F3; border-radius: 2px; }
                """)
        elif scan_status == "9":
            self.scan_status_label.setText("Idle")
            self.scan_status_label.setStyleSheet("color: #888; font-size: 11px; min-width: 70px;")
            self.scan_progress_bar.setValue(0)

    def _finalize_scan(self):
        """Process and store a completed scan."""
        if self._current_scan is None or len(self._current_scan['times']) < 3:
            self._current_scan = None
            return

        try:
            # Show processing status
            if hasattr(self, 'scan_status_label'):
                self.scan_status_label.setText("Processing...")
                self.scan_status_label.setStyleSheet("color: #FFC107; font-size: 11px; min-width: 70px;")

            # Convert to numpy arrays
            times = np.array(self._current_scan['times'])
            satflows = np.array(self._current_scan['satflows'])
            concentrations = np.array(self._current_scan['concentrations'])

            # Bin and invert (time shift applied inside _bin_and_invert_scan)
            dN_dlogDp = self._bin_and_invert_scan(satflows, concentrations)

            # Store scan result
            scan_result = {
                'time': times[0],  # Use first timestamp as scan time
                'bin_centers': self.bin_centers_dp.copy(),
                'dN_dlogDp': dN_dlogDp,
                'source_file': 'live'  # Mark as live scan
            }

            self.scan_buffer.append(scan_result)

            # Update scan counter with flash effect
            self._update_scan_counter_with_flash()

            # Reset progress bar
            if hasattr(self, 'scan_progress_bar'):
                self.scan_progress_bar.setValue(0)

            # Update plot
            self._render_contour()

            # Flash the newly added scan on the plot
            self._flash_last_scan()

        except Exception as e:
            logging.error(f"Error finalizing scan: {e}")
        finally:
            self._current_scan = None

    def _update_scan_counter_with_flash(self):
        """Update the scan counter and flash it to indicate new scan added."""
        if not hasattr(self, 'scan_counter_label'):
            return

        # Update counter text
        scan_count = len(self.scan_buffer)
        self.scan_counter_label.setText(f"Scans: {scan_count}")

        # Flash effect - briefly highlight the counter
        self.scan_counter_label.setStyleSheet(
            "color: #4CAF50; font-size: 11px; font-weight: bold; background-color: #1a3d1a; border-radius: 3px; padding: 2px;"
        )

        # Reset style after delay
        QTimer.singleShot(500, self._reset_counter_style)

        # Also briefly show "Scan added!" status
        if hasattr(self, 'scan_status_label'):
            self.scan_status_label.setText("Scan added!")
            self.scan_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; min-width: 70px; font-weight: bold;")
            QTimer.singleShot(1000, self._reset_status_to_idle)

    def _reset_counter_style(self):
        """Reset counter label to normal style."""
        if hasattr(self, 'scan_counter_label'):
            self.scan_counter_label.setStyleSheet("color: #aaa; font-size: 11px; font-weight: bold;")

    def _reset_status_to_idle(self):
        """Reset status label to idle."""
        if hasattr(self, 'scan_status_label'):
            self.scan_status_label.setText("Idle")
            self.scan_status_label.setStyleSheet("color: #888; font-size: 11px; min-width: 70px;")

    def _flash_last_scan(self):
        """Flash a vertical highlight on the plot at the position of the last added scan."""
        if not hasattr(self, 'plot') or len(self.scan_buffer) == 0:
            return

        try:
            # Get the last scan's timestamp
            last_scan = self.scan_buffer[-1]
            scan_time = last_scan['time']

            # Calculate x position (same logic as in _render_contour)
            time_24h_ago = pd.Timestamp.now() - pd.Timedelta(hours=24)
            hours_since_24h_ago = (scan_time - time_24h_ago).total_seconds() / 3600
            start_hour = time_24h_ago.hour + time_24h_ago.minute / 60
            x_pos = start_hour + hours_since_24h_ago

            # Get y range (in bin index coordinates: 0 to num_bins)
            y_min = 0
            y_max = self.num_bins if hasattr(self, 'num_bins') else 6

            # Create a semi-transparent vertical highlight bar
            # Remove old flash item if exists
            if hasattr(self, '_flash_item') and self._flash_item is not None:
                try:
                    self.plot.removeItem(self._flash_item)
                except:
                    pass

            # Create vertical line/bar at the scan position (in bin index coordinates)
            self._flash_item = pg.PlotCurveItem(
                x=[x_pos, x_pos],
                y=[y_min, y_max],
                pen=pg.mkPen(color=(76, 175, 80, 200), width=4)  # Green, semi-transparent
            )
            self.plot.addItem(self._flash_item)

            # Start fade-out animation
            self._flash_alpha = 200
            self._flash_timer = QTimer()
            self._flash_timer.timeout.connect(self._fade_flash)
            self._flash_timer.start(50)  # Update every 50ms

        except Exception as e:
            logging.error(f"Error flashing scan: {e}")

    def _fade_flash(self):
        """Gradually fade out the flash highlight."""
        if not hasattr(self, '_flash_item') or self._flash_item is None:
            if hasattr(self, '_flash_timer'):
                self._flash_timer.stop()
            return

        self._flash_alpha -= 25  # Fade by 25 each step

        if self._flash_alpha <= 0:
            # Remove flash item and stop timer
            try:
                self.plot.removeItem(self._flash_item)
            except:
                pass
            self._flash_item = None
            self._flash_timer.stop()
        else:
            # Update pen with new alpha
            self._flash_item.setPen(pg.mkPen(color=(76, 175, 80, self._flash_alpha), width=4))

    def _bin_and_invert_scan(self, satflows: np.ndarray, concentrations: np.ndarray) -> np.ndarray:
        """
        Bin scan data and perform inversion - matching the reference PSM Inversion Tool algorithm.

        Uses pd.cut for binning (like reference) and computes dN/dlogDp.

        The algorithm follows generateNinv() from InversionFunctions.py:
        1. Bin data by satflow using pd.cut
        2. Calculate mean concentration per bin
        3. Calculate dN using diff() - first value is NaN, skip it
        4. For each bin: dN/dlogDp = dN / dlogDp / MaxDeteff

        Returns:
            Array of dN/dlogDp values for each bin
        """
        # Create DataFrame like reference tool
        df = pd.DataFrame({'satflow': satflows, 'concentration': concentrations})

        # Apply CPC transit delay: concentration measured at time T corresponds to
        # particles that passed through the saturator at time T-3 seconds.
        # Shift concentration backward to align with the correct satflow.
        df['concentration'] = df['concentration'].shift(-self.cpc_transit_delay)

        # Use pd.cut to bin by satflow
        # bin_limits_flow is now in ascending order (matches original after flip)
        df['bins'] = pd.cut(df['satflow'], self.bin_limits_flow)

        # Calculate mean concentration per bin (like reference groupRawData)
        bin_means = df.groupby('bins', observed=True)['concentration'].mean()

        # Calculate dN using diff (like reference line 187)
        # bin_means is sorted by interval (ascending flow = ascending index)
        # diff() gives: bin_means[i] - bin_means[i-1]
        dN = bin_means.diff()

        # Get calibration data
        cal_satflow = self.calibration_df['cal_satflow'].values
        cal_diameter = self.calibration_df['cal_diameter'].values
        cal_maxdeteff = self.calibration_df['cal_maxdeteff'].values

        # Initialize output array
        dN_dlogDp = np.zeros(self.num_bins)

        bin_intervals = bin_means.index.tolist()

        for i, interval in enumerate(bin_intervals):
            if i == 0:
                continue  # Skip first bin (NaN from diff, like reference drops first row)

            # Get flow edges for this bin (like reference lines 172, 176-177)
            lower_flow = interval.left   # Lower flow edge
            upper_flow = interval.right  # Upper flow edge

            # Convert flow to diameter (like reference lines 176-177)
            # Need to flip cal arrays for interp since cal is sorted by satflow descending
            lower_dp = np.interp(lower_flow, np.flip(cal_satflow), np.flip(cal_diameter))
            upper_dp = np.interp(upper_flow, np.flip(cal_satflow), np.flip(cal_diameter))

            # dlogDp = log10(LowerDp) - log10(UpperDp) (like reference line 178)
            # lower_flow -> larger_dp (LowerDp), upper_flow -> smaller_dp (UpperDp)
            dlogDp = np.log10(lower_dp) - np.log10(upper_dp)

            # MaxDeteff at UpperDp (the smaller diameter) (like reference line 179)
            max_det_eff = np.interp(upper_dp, cal_diameter, cal_maxdeteff)

            # Get dN for this bin
            dN_val = dN.iloc[i]

            # Set negative dN to 0 (like reference lines 192-194)
            if pd.isna(dN_val) or dN_val < 0:
                dN_val = 0

            # Calculate dN/dlogDp (like reference lines 197, 199-200)
            if abs(dlogDp) > 0.001 and max_det_eff > 0:
                # Direct indexing: i=1 -> output[0], i=2 -> output[1], etc.
                # This matches reference which drops first row
                output_idx = i - 1
                if 0 <= output_idx < self.num_bins:
                    dN_dlogDp[output_idx] = dN_val / abs(dlogDp) / max_det_eff

        # Flip array so index 0 = smallest diameter, matching bin_limits_dp ordering
        return np.flip(dN_dlogDp)

    def _step_inversion(self, binned_concentrations: np.ndarray) -> np.ndarray:
        """
        Perform stepwise inversion to get dN/dlogDp.

        This follows the PSM Inversion Tool algorithm:
        1. Calculate dN using diff (difference between adjacent bins)
        2. dN[i] = conc[i+1] - conc[i] (higher flow - lower flow)
           Since higher flow has higher cumulative concentration, this gives positive dN
        3. Calculate dlogDp = log10(LowerDp) - log10(UpperDp) where LowerDp > UpperDp
        4. Get MaxDeteff at UpperDp (the smaller diameter)
        5. dN/dlogDp = dN / dlogDp / MaxDeteff

        bin_limits_flow is now in ASCENDING order (low flow to high flow):
        - bin_limits_flow[0] = lowest flow = largest diameter = lowest concentration
        - bin_limits_flow[-1] = highest flow = smallest diameter = highest concentration

        Returns:
            Array of dN/dlogDp values (num_bins values, first one typically invalid)
        """
        num_bins = self.num_bins
        dN_dlogDp = np.zeros(num_bins)

        # Get calibration data for interpolation
        cal_satflow = self.calibration_df['cal_satflow'].values
        cal_diameter = self.calibration_df['cal_diameter'].values
        cal_maxdeteff = self.calibration_df['cal_maxdeteff'].values

        # Calculate dN: difference between consecutive bins
        # bin_limits_flow is ASCENDING: [low_flow, ..., high_flow]
        # binned_concentrations[0] = lowest flow = largest diameter = lowest conc
        # binned_concentrations[n-1] = highest flow = smallest diameter = highest conc
        # np.diff computes arr[i+1] - arr[i], which gives positive dN (higher conc - lower conc)
        dN_values = np.diff(binned_concentrations)
        # dN_values has num_bins - 1 elements

        for i in range(num_bins):
            # Get flow bin edges for this bin
            # bin_limits_flow[i] = lower flow (larger diameter)
            # bin_limits_flow[i+1] = higher flow (smaller diameter)
            lower_flow = self.bin_limits_flow[i]
            higher_flow = self.bin_limits_flow[i+1] if i+1 < len(self.bin_limits_flow) else self.bin_limits_flow[i]

            # Calculate diameters by interpolating from flow
            # Need to flip because calibration has diameter increasing with decreasing flow
            larger_dp = np.interp(lower_flow, np.flip(cal_satflow), np.flip(cal_diameter))
            smaller_dp = np.interp(higher_flow, np.flip(cal_satflow), np.flip(cal_diameter))

            # Calculate dlogDp = log10(LowerDp) - log10(UpperDp) (like reference line 178)
            # LowerDp = larger_dp (from lower flow), UpperDp = smaller_dp (from higher flow)
            if larger_dp > 0 and smaller_dp > 0:
                dlogDp = np.log10(larger_dp) - np.log10(smaller_dp)
            else:
                dlogDp = 0

            # Get MaxDeteff at UpperDp (the smaller diameter) - like reference line 179
            max_det_eff = np.interp(smaller_dp, cal_diameter, cal_maxdeteff)

            # Get dN for this bin
            # For bin i, we need dN between bin i and bin i+1
            # dN_values has num_bins-1 elements, index i corresponds to diff between i and i+1
            if i < len(dN_values):
                dN = dN_values[i]
            else:
                # Last bin has no next bin to diff with
                dN = 0

            # Calculate dN/dlogDp with detection efficiency correction
            if dlogDp > 0 and max_det_eff > 0 and not np.isnan(dN):
                dN_dlogDp[i] = dN / dlogDp / max_det_eff
            else:
                dN_dlogDp[i] = 0

            # Set negative values to 0 (as in PSM Inversion Tool)
            if dN_dlogDp[i] < 0:
                dN_dlogDp[i] = 0

        return dN_dlogDp

    def _render_contour(self):
        """
        Render the contour plot from scan buffer.

        X-axis: Time (last 24 hours, with HH:MM labels)
        Y-axis: Particle diameter in nm
        Color: log10(dN/dlogDp), with gaps shown as black
        """
        if not self.calibration_loaded or len(self.scan_buffer) == 0:
            # Clear plot and file boundary markers
            self.image_item.clear()
            for line in self.file_boundary_lines:
                self.plot.removeItem(line)
            for label in self.file_boundary_labels:
                self.plot.removeItem(label)
            self.file_boundary_lines = []
            self.file_boundary_labels = []
            return

        try:
            n_scans = len(self.scan_buffer)
            num_bins = self.num_bins

            # Get current time and calculate time window
            now = pd.Timestamp.now()
            time_window_ago = now - pd.Timedelta(hours=self.time_window_hours)

            # Update date label
            if hasattr(self, 'date_label'):
                self.date_label.setText(now.strftime("%Y-%m-%d"))

            # Convert scan times to pandas Timestamps
            def to_timestamp(ts):
                if isinstance(ts, pd.Timestamp):
                    return ts
                elif isinstance(ts, np.datetime64):
                    return pd.Timestamp(ts)
                elif hasattr(ts, 'timestamp'):
                    return pd.Timestamp(ts)
                return pd.Timestamp(ts)

            scan_timestamps = [to_timestamp(scan['time']) for scan in self.scan_buffer]

            # Filter scans to time window
            scans_in_range = [(ts, scan) for ts, scan in zip(scan_timestamps, self.scan_buffer)
                              if ts >= time_window_ago]

            # Create time grid with bin size scaled to window (more bins for shorter windows)
            # Aim for ~360 bins regardless of window size
            time_bin_size_seconds = max(60, int(self.time_window_hours * 3600 / 360))
            n_time_bins = int(self.time_window_hours * 3600 / time_bin_size_seconds)

            # Create data matrix with NaN for gaps (will show as black)
            data_matrix = np.full((num_bins, n_time_bins), np.nan)

            # Place each scan at its time position within the time window
            for ts, scan in scans_in_range:
                # Calculate seconds since window start
                seconds_since_start = (ts - time_window_ago).total_seconds()
                time_idx = int(seconds_since_start / time_bin_size_seconds)
                time_idx = max(0, min(time_idx, n_time_bins - 1))  # Clamp to valid range

                dN_dlogDp = scan['dN_dlogDp']
                if len(dN_dlogDp) == num_bins:
                    # If multiple scans fall in same bin, average them
                    if np.isnan(data_matrix[0, time_idx]):
                        data_matrix[:, time_idx] = dN_dlogDp
                    else:
                        data_matrix[:, time_idx] = (data_matrix[:, time_idx] + dN_dlogDp) / 2

            # Apply averaging if enabled
            if self.averaging_enabled and self.avg_n > 1:
                data_matrix = self._apply_scan_averaging(data_matrix, self.avg_n)

            # Take log10, keeping NaN for gaps
            valid_mask = ~np.isnan(data_matrix)
            data_matrix_log = np.full_like(data_matrix, np.nan)
            data_matrix_log[valid_mask] = np.where(
                data_matrix[valid_mask] > 0.1,
                data_matrix[valid_mask],
                0.1
            )
            z = np.log10(data_matrix_log)

            # Calculate min/max for colorbar from valid data only
            valid_z = z[~np.isnan(z)]
            if len(valid_z) > 0:
                min_z = np.floor(np.nanmin(valid_z))
                max_z = np.ceil(np.nanmax(valid_z))
            else:
                min_z, max_z = 0, 1

            # Keep NaN for gaps - they will show as transparent (black background)
            # Use the standard colormap for actual data values
            lut = self.data_cmap.getLookupTable(nPts=256)
            self.image_item.setImage(z.T, autoLevels=False, levels=(min_z, max_z), lut=lut)

            # Set image position and scale
            # X-axis: hours from start of time window, mapped to actual clock times
            start_hour = time_window_ago.hour + time_window_ago.minute / 60
            pos_x = start_hour
            width = self.time_window_hours

            # Y-axis uses bin indices (0 to num_bins) - equal height bins
            pos_y = 0
            height = num_bins

            self.image_item.setRect(pos_x, pos_y, width, height)

            # Update the custom Y-axis with bin limits
            if hasattr(self, 'bin_axis'):
                self.bin_axis.set_bin_limits(self.bin_limits_dp)

            # Store data for crosshair value lookup (in bin index coordinates)
            self._last_z_data = z.T  # Transposed to match image orientation
            self._last_pos_x = pos_x
            self._last_width = width
            self._last_num_bins = num_bins

            # Update axis label
            self.plot.setLabel('bottom', 'Time')

            # Update colorbar range (don't include the "gap" value)
            self.colorbar.setLevels((min_z, max_z))

            # Add file boundary markers (pass bin index coordinates)
            self._draw_file_boundaries(scans_in_range, time_window_ago, pos_y, height)

        except Exception as e:
            logging.error(f"Error rendering contour: {e}")

    def _draw_file_boundaries(self, scans_in_range, time_24h_ago, y_min, y_height):
        """Draw vertical tick marks at file boundaries showing where files start/end.

        Args:
            y_min: Y position (bin index, typically 0)
            y_height: Height (number of bins)
        """
        # Remove old markers
        for line in self.file_boundary_lines:
            self.plot.removeItem(line)
        for label in self.file_boundary_labels:
            self.plot.removeItem(label)
        self.file_boundary_lines = []
        self.file_boundary_labels = []

        # Store scans for later zoom updates
        self._last_scans_in_range = scans_in_range

        if not scans_in_range:
            self._last_file_ranges = []
            return

        # Find file boundaries (where source_file changes)
        current_file = None
        file_ranges_ts = []  # List of (file_name, start_time, end_time) in timestamps

        for ts, scan in scans_in_range:
            source_file = scan.get('source_file', 'unknown')
            if source_file != current_file:
                # New file started
                if current_file is not None and file_ranges_ts:
                    # Update end time of previous file
                    file_ranges_ts[-1] = (file_ranges_ts[-1][0], file_ranges_ts[-1][1], ts)
                # Start new file range
                file_ranges_ts.append((source_file, ts, ts))
                current_file = source_file
            else:
                # Update end time of current file
                if file_ranges_ts:
                    file_ranges_ts[-1] = (file_ranges_ts[-1][0], file_ranges_ts[-1][1], ts)

        # Draw vertical tick marks at file boundaries
        start_hour = time_24h_ago.hour + time_24h_ago.minute / 60
        y_top = y_min + y_height

        # Store y_top for label updates on zoom
        self._last_y_top = y_top

        # Tick extends from plot top upward
        tick_height = y_height * 0.03
        y_tick_bottom = y_top
        y_tick_top = y_top + tick_height

        # Convert file ranges to x-coordinates and store for zoom updates
        file_ranges_x = []  # List of (file_name, x_start, x_end) in plot coordinates

        for i, (file_name, start_ts, end_ts) in enumerate(file_ranges_ts):
            # Calculate x positions
            hours_start = (start_ts - time_24h_ago).total_seconds() / 3600
            hours_end = (end_ts - time_24h_ago).total_seconds() / 3600
            x_start = start_hour + hours_start
            x_end = start_hour + hours_end

            file_ranges_x.append((file_name, x_start, x_end))

            # Draw vertical tick at file start (skip first file at very beginning)
            if i > 0 or hours_start > 0.01:  # Only if not at the very start
                tick = pg.PlotCurveItem(
                    x=[x_start, x_start],
                    y=[y_tick_bottom, y_tick_top],
                    pen=pg.mkPen(color=(255, 255, 255, 180), width=1)
                )
                self.plot.addItem(tick)
                self.file_boundary_lines.append(tick)

        # Store file ranges in x-coordinates for zoom-based label updates
        self._last_file_ranges = file_ranges_x

        # Draw initial labels using the zoom-aware method
        self._update_file_boundary_labels()

    def _apply_scan_averaging(self, data_matrix: np.ndarray, n: int) -> np.ndarray:
        """
        Apply rolling average over N scans.

        Args:
            data_matrix: 2D array (bins x scans)
            n: Number of scans to average over

        Returns:
            Averaged data matrix
        """
        df = pd.DataFrame(data_matrix)
        averaged = df.T.rolling(n, min_periods=1).mean().T
        return averaged.values

    def _start_historical_data_load(self):
        """
        Start loading historical scan data in a background thread.
        Called when user clicks the Load History button.
        """
        if not self.calibration_loaded:
            self.file_label.setText("Load calibration file first")
            return

        if self._loading_in_progress:
            return

        # Get device information from config
        serial_number = self.device_config.serial_number
        device_nickname = self.device_config.device_nickname

        # Get file path from global config
        if not self.app_config:
            self.file_label.setText("Configuration not ready")
            return

        file_path = self.app_config.data_settings.file_path
        file_tag = self.app_config.data_settings.file_tag

        # Cancel any existing loader thread
        if self._loader_thread is not None and self._loader_thread.isRunning():
            self._loader_thread.cancel()
            self._loader_thread.wait()

        self._loading_in_progress = True
        self._show_loading_overlay()
        self.load_history_btn.setEnabled(False)
        self.load_history_btn.setText("Loading...")

        # Reset progress indicators
        if hasattr(self, 'loading_progress_bar'):
            self.loading_progress_bar.setRange(0, 0)  # Indeterminate initially
            self.loading_progress_bar.setValue(0)
        if hasattr(self, 'loading_label'):
            self.loading_label.setText("Loading...")
        if hasattr(self, 'loading_detail_label'):
            self.loading_detail_label.setText("Finding data files...")

        # Clear existing buffer before loading historical data
        self.scan_buffer = []
        self._pending_scans = []  # Collect scans for batch processing

        # Create and start loader thread
        self._loader_thread = HistoricalDataLoader(
            file_path=file_path,
            serial_number=serial_number,
            device_nickname=device_nickname,
            file_tag=file_tag,
            hours=self.time_window_hours
        )

        # Connect signals
        self._loader_thread.progress.connect(self._on_loading_progress)
        self._loader_thread.scan_loaded.connect(self._on_scan_loaded)
        self._loader_thread.finished_loading.connect(self._on_loading_finished)
        self._loader_thread.error.connect(self._on_loading_error)

        # Start the thread
        self._loader_thread.start()

    def _on_loading_progress(self, current: int, total: int, message: str):
        """Handle progress updates from the loader thread."""
        # Update overlay progress bar and labels
        if hasattr(self, 'loading_progress_bar'):
            if total > 0:
                self.loading_progress_bar.setRange(0, total)
                self.loading_progress_bar.setValue(current)
                self.loading_progress_bar.setFormat(f"{current}/{total}")
            else:
                # Indeterminate progress
                self.loading_progress_bar.setRange(0, 0)

        if hasattr(self, 'loading_label'):
            # Main status message
            if total > 0:
                self.loading_label.setText(f"Loading: {current}/{total}")
            else:
                self.loading_label.setText("Loading...")

        if hasattr(self, 'loading_detail_label'):
            # Detail message (file name, etc)
            self.loading_detail_label.setText(message)

        # Also update top bar progress
        if total > 0 and hasattr(self, 'scan_progress_bar'):
            self.scan_progress_bar.setRange(0, total)
            self.scan_progress_bar.setValue(current)

    def _on_scan_loaded(self, scan_data: dict):
        """Handle a single scan loaded from the background thread."""
        # Collect scans for batch processing (processing happens in main thread after all loaded)
        self._pending_scans.append(scan_data)

    def _on_loading_finished(self, filepaths: list, scans: list):
        """Handle completion of historical data loading."""
        try:
            # Store loaded file paths
            self.loaded_file_path = filepaths

            # Process all pending scans in main thread
            if hasattr(self, 'loading_label'):
                self.loading_label.setText("Processing scans...")

            for i, scan_data in enumerate(self._pending_scans):
                try:
                    self._process_historical_scan(scan_data)
                except Exception as e:
                    logging.error(f"Error processing scan {i+1}: {e}")

            # Update file label
            if len(filepaths) == 1:
                self.file_label.setText(f"File: {os.path.basename(filepaths[0])}")
            else:
                self.file_label.setText(f"{len(filepaths)} files loaded")

            # Update scan counter
            if hasattr(self, 'scan_counter_label'):
                self.scan_counter_label.setText(f"Scans: {len(self.scan_buffer)}")

            # Render contour with loaded data
            self._render_contour()

            self._historical_data_loaded = True

        except Exception as e:
            logging.error(f"Error processing loaded data: {e}")
        finally:
            self._loading_in_progress = False
            self._hide_loading_overlay()
            self.load_history_btn.setEnabled(True)
            self.load_history_btn.setText("Load History")
            self._pending_scans = []
            if hasattr(self, 'scan_progress_bar'):
                self.scan_progress_bar.setValue(0)

    def _on_loading_error(self, error_message: str):
        """Handle errors from the loader thread."""
        self.file_label.setText(error_message)
        self._loading_in_progress = False
        self._hide_loading_overlay()
        self.load_history_btn.setEnabled(True)
        self.load_history_btn.setText("Load History")
        self._pending_scans = []
        if hasattr(self, 'scan_progress_bar'):
            self.scan_progress_bar.setValue(0)

    def _process_historical_scan(self, scan_data: Dict[str, np.ndarray]):
        """
        Process a historical scan and add it to the scan buffer.

        Args:
            scan_data: Dict with keys 'times', 'satflows', 'concentrations_psm'
        """
        times = scan_data['times']
        satflows = scan_data['satflows']
        concentrations_psm = scan_data['concentrations_psm']

        if len(times) < 3:
            return  # Skip incomplete scans

        # Bin and invert (time shift applied inside _bin_and_invert_scan)
        dN_dlogDp = self._bin_and_invert_scan(satflows, concentrations_psm)

        # Store scan result
        scan_result = {
            'time': times[0],  # Use first timestamp as scan time
            'bin_centers': self.bin_centers_dp.copy(),
            'dN_dlogDp': dN_dlogDp,
            'source_file': scan_data.get('source_file', 'live')  # Track source file
        }

        self.scan_buffer.append(scan_result)
