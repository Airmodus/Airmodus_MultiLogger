"""
PSM Contour Plot Tab

Displays real-time particle size distribution as a 2D contour plot.
Each completed scan adds a new vertical line to the plot.
Requires calibration file to perform size distribution inversion.
"""

import os
import time
import numpy as np
import pandas as pd
from typing import Optional, List, Dict
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QFileDialog, QMenu, QSizePolicy, QCheckBox,
                              QLineEdit, QSpinBox)
from PyQt5.QtCore import Qt, QPoint
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


class PSMContourTab(QWidget):
    """
    PSM Contour Plot Tab Widget

    Shows a real-time 2D heatmap of particle size distribution vs time.
    - X-axis: Time (scan timestamps)
    - Y-axis: Particle diameter (nm)
    - Color: log10(dN/dlogDp) concentration
    """

    def __init__(self, device_config, app_config=None):
        super().__init__()
        self.device_config = device_config
        self.app_config = app_config  # Will be set later by PSM widget
        self.on_config_changed = None  # Callback to notify parent when config changes

        # State flags
        self.calibration_loaded = False
        self.plot_initialized = False
        self._historical_data_loaded = False  # Track if we've loaded historical data

        # Calibration data
        self.calibration_df = None
        self.bin_limits_dp = None  # Diameter bin edges (7 values for 6 bins)
        self.bin_centers_dp = None  # Diameter bin centers (6 values)
        self.bin_limits_flow = None  # Saturator flow bin edges (7 values)
        self.detection_efficiency = None  # Detection efficiency interpolator

        # Scan detection state
        self._prev_scan_status = "9"
        self._current_scan = None  # Dict with 'times', 'satflows', 'concentrations'

        # Scan buffer (stores completed scans)
        self.scan_buffer = []  # List of dicts: {'time': float, 'bin_centers': array, 'dN_dlogDp': array}
        # No max_scans limit - show all available data

        # Averaging settings
        self.averaging_enabled = False
        self.avg_n = 5  # Default: average over 5 scans

        # Custom time axis for contour plot
        self.time_axis = None

        # Currently loaded file
        self.loaded_file_path = None

        # File boundary markers for visualization
        self.file_boundary_lines = []  # List of InfiniteLine items
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
        """Override showEvent to lazily load historical data when tab becomes visible."""
        super().showEvent(event)
        # Load historical data on first show (if calibration is loaded)
        # Only load if this widget is actually visible to the user (not just being initialized)
        if self.calibration_loaded and not self._historical_data_loaded and self.isVisible():
            self._historical_data_loaded = True
            # Defer to next event loop to avoid blocking tab switch
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self._load_historical_data)

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

        # Top bar with averaging controls and settings button
        top_bar = QHBoxLayout()

        # Averaging controls
        self.avg_checkbox = QCheckBox("Average")
        self.avg_checkbox.setChecked(self.averaging_enabled)
        self.avg_checkbox.toggled.connect(self._on_avg_toggle)
        top_bar.addWidget(self.avg_checkbox)

        self.avg_spinbox = QSpinBox()
        self.avg_spinbox.setRange(1, 50)
        self.avg_spinbox.setValue(self.avg_n)
        self.avg_spinbox.setFixedWidth(50)
        self.avg_spinbox.setSuffix(" scans")
        self.avg_spinbox.valueChanged.connect(self._on_avg_n_changed)
        self.avg_spinbox.setEnabled(self.averaging_enabled)
        top_bar.addWidget(self.avg_spinbox)

        top_bar.addSpacing(20)

        # File label to show which data file is loaded
        self.file_label = QLabel("")
        self.file_label.setStyleSheet("color: #666; font-size: 11px;")
        top_bar.addWidget(self.file_label)

        top_bar.addStretch()

        # Settings button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setStyleSheet("font-size: 18px;")
        self.settings_btn.clicked.connect(self._show_settings_menu)
        top_bar.addWidget(self.settings_btn)

        plot_layout.addLayout(top_bar)

        # Create custom time axis for X-axis (shows HH:MM:SS based on scan index)
        self.time_axis = TimeAxisItemForContour(orientation='bottom')

        # Create PyQtGraph widget with custom axis
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.plot = self.graphics_widget.addPlot(axisItems={'bottom': self.time_axis})

        # Configure axes
        self.plot.setLabel('bottom', 'Scan Time')
        self.plot.setLabel('left', 'Particle Diameter', units='nm')
        self.plot.showGrid(x=True, y=True, alpha=0.3)

        # Create image item for contour
        self.image_item = pg.ImageItem()
        self.plot.addItem(self.image_item)

        # Use standard CET-R4 colormap for data
        self.data_cmap = pg.colormap.get('CET-R4')

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

        plot_layout.addWidget(self.graphics_widget)
        self.plot_widget.setLayout(plot_layout)

        # Hide initially
        self.plot_widget.hide()
        self.main_layout.addWidget(self.plot_widget)

    def _on_avg_toggle(self, enabled: bool):
        """Handle averaging checkbox toggle."""
        self.averaging_enabled = enabled
        self.avg_spinbox.setEnabled(enabled)
        self._render_contour()

    def _on_avg_n_changed(self, value: int):
        """Handle averaging N spinbox change."""
        self.avg_n = value
        if self.averaging_enabled:
            self._render_contour()

    def initialize_after_config_set(self):
        """
        Initialize contour tab after app_config is set.
        Called by PSMWidget after setting app_config.
        This triggers auto-load of calibration and historical data.
        """
        self._try_autoload_calibration()

    def _try_autoload_calibration(self):
        """Try to auto-load calibration file from saved parameter."""
        try:
            # Get calibration path from device config extra_params
            calib_path = self.device_config.extra_params.get('calibration_file_path', '')
            if calib_path and os.path.exists(calib_path):
                self._load_calibration(calib_path, auto_load=True)
        except Exception as e:
            # Silently ignore if parameter doesn't exist (old config)
            print(f"Error auto-loading calibration: {e}")

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

            print(f"Calibration loaded: {num_bins} bins from {min_diameter:.2f} to {max_diameter:.2f} nm")
            print(f"Bin limits (dp): {self.bin_limits_dp}")
            print(f"Bin limits (flow): {self.bin_limits_flow}")

            # Trigger config save for manual calibration load (not auto-load)
            if not auto_load and self.on_config_changed:
                self.on_config_changed()

            # Auto-load historical data after calibration loads
            # Use QTimer to defer and avoid blocking
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(100, self._load_historical_data_if_ready)

        except Exception as e:
            print(f"Error loading calibration file: {e}")
            import traceback
            traceback.print_exc()

    def _load_historical_data_if_ready(self):
        """Load historical data if calibration and app_config are ready."""
        if self.calibration_loaded and self.app_config and not self._historical_data_loaded:
            self._historical_data_loaded = True
            self._load_historical_data()

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

    def _calculate_flow_bins(self, fixed_bin_limits: np.ndarray) -> np.ndarray:
        """
        Calculate saturator flow bin limits from diameter limits.

        This follows the PSM Inversion Tool algorithm:
        1. Calculate geometric mean diameters between fixed limits (binning_limit)
        2. Add min and max edges to binning_limit
        3. Convert diameter binning limits to flow via calibration interpolation

        Args:
            fixed_bin_limits: Array of diameter bin edges (nm)

        Returns:
            Array of saturator flow bin limits (lpm), flipped order (high flow = small diameter)
        """
        fixed_bin_limits = np.array(fixed_bin_limits)

        # Calculate geometric mean diameters between bin limits
        binning_limit = self._geom_means(fixed_bin_limits)

        # Add min and max edges
        max_bin_edge = fixed_bin_limits[-1]
        min_bin_edge = fixed_bin_limits[0]
        binning_limit = np.append(min_bin_edge, binning_limit)
        binning_limit = np.append(binning_limit, max_bin_edge)

        # Convert diameter to flow via calibration interpolation
        # binning_limit is in ascending diameter order: [small_dp, ..., large_dp]
        # Calibration: small diameter -> high flow, large diameter -> low flow
        # So interp result is [high_flow, ..., low_flow] - DESCENDING order
        # This is what we want: bin 0 = highest flow = smallest diameter = highest concentration
        bin_lims = np.interp(
            binning_limit,
            self.calibration_df['cal_diameter'].values,
            self.calibration_df['cal_satflow'].values
        )
        # DO NOT flip - we want bin_lims in descending order (high flow to low flow)

        print(f"DEBUG _calculate_flow_bins:")
        print(f"  binning_limit (diameters): {binning_limit}")
        print(f"  bin_lims (flows): {bin_lims}")

        return bin_lims

    def _show_settings_menu(self):
        """Show settings dropdown menu."""
        menu = QMenu(self)

        change_action = menu.addAction("Change calibration file")
        change_action.triggered.connect(self._browse_calibration_file)

        clear_action = menu.addAction("Clear calibration")
        clear_action.triggered.connect(self._clear_calibration)

        clear_buffer_action = menu.addAction("Clear scan buffer")
        clear_buffer_action.triggered.connect(self._clear_scan_buffer)

        reload_action = menu.addAction("Reload historical data")
        reload_action.triggered.connect(lambda: (setattr(self, '_historical_data_loaded', False), self._load_historical_data()))

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
        self._render_contour()

    def update_contour(self, current_data):
        """
        Update contour plot with new data point.
        Called every second from plot_manager.

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
        """
        if not self.calibration_loaded:
            return

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
                if not np.isnan(current_data.saturator_flow) and not np.isnan(current_data.cpc_concentration):
                    self._current_scan['times'].append(pd.Timestamp.now())
                    self._current_scan['satflows'].append(current_data.saturator_flow)
                    self._current_scan['concentrations'].append(current_data.cpc_concentration)

        # Update previous status
        self._prev_scan_status = scan_status

    def _finalize_scan(self):
        """Process and store a completed scan."""
        if self._current_scan is None or len(self._current_scan['times']) < 3:
            self._current_scan = None
            return

        try:
            # Convert to numpy arrays
            times = np.array(self._current_scan['times'])
            satflows = np.array(self._current_scan['satflows'])
            concentrations = np.array(self._current_scan['concentrations'])

            # Bin and invert in one step (matching reference tool algorithm)
            dN_dlogDp = self._bin_and_invert_scan(satflows, concentrations)

            # Store scan result
            scan_result = {
                'time': times[0],  # Use first timestamp as scan time
                'bin_centers': self.bin_centers_dp.copy(),
                'dN_dlogDp': dN_dlogDp,
                'source_file': 'live'  # Mark as live scan
            }

            self.scan_buffer.append(scan_result)

            # Update plot
            self._render_contour()

        except Exception as e:
            print(f"Error finalizing scan: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._current_scan = None

    def _bin_and_invert_scan(self, satflows: np.ndarray, concentrations: np.ndarray) -> np.ndarray:
        """
        Bin scan data and perform inversion - matching the reference PSM Inversion Tool algorithm.

        Uses pd.cut for binning (like reference) and computes dN/dlogDp.

        Returns:
            Array of dN/dlogDp values for each bin (num_bins - 1 valid values + 1 zero)
        """
        # Debug: show satflow range for first few scans
        if not hasattr(self, '_bin_debug_count'):
            self._bin_debug_count = 0

        # Create DataFrame like reference tool
        df = pd.DataFrame({'satflow': satflows, 'concentration': concentrations})

        # Use pd.cut to bin by satflow - bins must be sorted
        # Sort flow limits ascending for pd.cut
        bins_sorted = np.sort(self.bin_limits_flow)
        df['bins'] = pd.cut(df['satflow'], bins_sorted)

        # Calculate mean concentration per bin
        bin_means = df.groupby('bins', observed=True)['concentration'].mean()

        if self._bin_debug_count < 3:
            self._bin_debug_count += 1
            print(f"\n=== Binning Debug (call {self._bin_debug_count}) ===")
            print(f"Satflow range in scan: {np.min(satflows):.3f} - {np.max(satflows):.3f}")
            print(f"Concentration range: {np.min(concentrations):.1f} - {np.max(concentrations):.1f}")
            print(f"Bin means (ascending flow order):\n{bin_means}")

        # Calculate dN using diff (like reference line 187)
        # bin_means is sorted by interval (ascending flow = ascending index)
        # diff() gives: bin_means[i] - bin_means[i-1]
        # Higher flow bin has higher concentration, so diff is positive
        dN = bin_means.diff()

        # Get calibration data
        cal_satflow = self.calibration_df['cal_satflow'].values
        cal_diameter = self.calibration_df['cal_diameter'].values
        cal_maxdeteff = self.calibration_df['cal_maxdeteff'].values

        # Calculate dlogDp and MaxDeteff for each bin
        # Use the bin intervals to get flow edges
        num_output_bins = len(bin_means) - 1  # First bin has NaN from diff
        dN_dlogDp = np.zeros(self.num_bins)

        bin_intervals = bin_means.index.tolist()

        for i, interval in enumerate(bin_intervals):
            if i == 0:
                continue  # Skip first bin (NaN from diff)

            # Get flow edges for this bin
            lower_flow = interval.left  # Lower flow edge
            upper_flow = interval.right  # Upper flow edge

            # Convert flow to diameter
            lower_dp = np.interp(lower_flow, np.flip(cal_satflow), np.flip(cal_diameter))
            upper_dp = np.interp(upper_flow, np.flip(cal_satflow), np.flip(cal_diameter))

            # dlogDp = log10(larger_dp) - log10(smaller_dp)
            # lower_flow -> larger_dp, upper_flow -> smaller_dp
            dlogDp = np.log10(lower_dp) - np.log10(upper_dp)

            # MaxDeteff at the smaller diameter (upper_dp, from upper_flow)
            max_det_eff = np.interp(upper_dp, cal_diameter, cal_maxdeteff)

            # Get dN for this bin
            dN_val = dN.iloc[i]

            if self._bin_debug_count <= 3 and i == 1:
                print(f"Bin {i}: flow=[{lower_flow:.3f}, {upper_flow:.3f}], dp=[{lower_dp:.2f}, {upper_dp:.2f}]")
                print(f"  dlogDp={dlogDp:.4f}, deteff={max_det_eff:.3f}, dN={dN_val:.2f}")

            # Calculate dN/dlogDp with detection efficiency correction
            # Set negative dN to 0 first (like reference line 192-194)
            if pd.isna(dN_val) or dN_val < 0:
                dN_val = 0

            if abs(dlogDp) > 0.001 and max_det_eff > 0:
                # Map to output array - bin i-1 because we skip first bin
                # Output bins go from smallest diameter to largest
                output_idx = self.num_bins - i  # Reverse order for display
                dN_dlogDp[output_idx] = dN_val / abs(dlogDp) / max_det_eff

        if self._bin_debug_count <= 3:
            print(f"Final dN/dlogDp: {dN_dlogDp}")

        return dN_dlogDp

    def _step_inversion(self, binned_concentrations: np.ndarray) -> np.ndarray:
        """
        Perform stepwise inversion to get dN/dlogDp.

        This follows the PSM Inversion Tool algorithm:
        1. Calculate dN using diff (difference between adjacent bins)
        2. For each bin i, dN[i] = conc[i] - conc[i+1] (higher flow - lower flow)
           Since higher flow has higher cumulative concentration, this gives positive dN
        3. Calculate dlogDp = log10(LowerDp) - log10(UpperDp) where LowerDp > UpperDp
        4. Get MaxDeteff at the larger diameter (LowerDp)
        5. dN/dlogDp = dN / dlogDp / MaxDeteff

        The key insight: bin_limits_flow is ordered from high flow to low flow.
        - High flow = small diameter = high cumulative concentration
        - Low flow = large diameter = low cumulative concentration
        - dN = particles in size range = conc[high_flow] - conc[low_flow] > 0

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
        # binned_concentrations[0] = highest flow = smallest diameter = highest conc
        # binned_concentrations[n-1] = lowest flow = largest diameter = lowest conc
        # dN[i] = conc[i] - conc[i+1] = particles in size range between bin i and i+1
        # Use np.diff which computes arr[i+1] - arr[i], so negate to get arr[i] - arr[i+1]
        dN_values = -np.diff(binned_concentrations)
        # dN_values has num_bins - 1 elements

        # Debug output (only for first few calls)
        if not hasattr(self, '_debug_count'):
            self._debug_count = 0
        if self._debug_count < 3:
            self._debug_count += 1
            print(f"\n=== Step Inversion Debug (call {self._debug_count}) ===")
            print(f"Binned concentrations: {binned_concentrations}")
            print(f"  - Has NaN: {np.any(np.isnan(binned_concentrations))}")
            print(f"  - Min/Max: {np.nanmin(binned_concentrations):.1f} / {np.nanmax(binned_concentrations):.1f}")
            print(f"dN values (-diff): {dN_values}")
            print(f"Flow bin limits: {self.bin_limits_flow}")
            # Debug per-bin calculation for first bin
            higher_flow = self.bin_limits_flow[0]
            lower_flow = self.bin_limits_flow[1]
            smaller_dp = np.interp(higher_flow, np.flip(cal_satflow), np.flip(cal_diameter))
            larger_dp = np.interp(lower_flow, np.flip(cal_satflow), np.flip(cal_diameter))
            dlogDp = np.log10(larger_dp) - np.log10(smaller_dp)
            max_det_eff = np.interp(larger_dp, cal_diameter, cal_maxdeteff)
            print(f"Bin 0 calc: higher_flow={higher_flow:.3f}, lower_flow={lower_flow:.3f}")
            print(f"  smaller_dp={smaller_dp:.3f}, larger_dp={larger_dp:.3f}")
            print(f"  dlogDp={dlogDp:.4f}, max_det_eff={max_det_eff:.3f}")
            if len(dN_values) > 0 and not np.isnan(dN_values[0]):
                print(f"  dN={dN_values[0]:.2f}, dN/dlogDp/eff={dN_values[0]/dlogDp/max_det_eff:.2f}")

        for i in range(num_bins):
            # Get flow bin edges for this bin
            # bin_limits_flow[i] = higher flow (smaller diameter)
            # bin_limits_flow[i+1] = lower flow (larger diameter)
            higher_flow = self.bin_limits_flow[i]
            lower_flow = self.bin_limits_flow[i+1] if i+1 < len(self.bin_limits_flow) else self.bin_limits_flow[i]

            # Calculate diameters by interpolating from flow
            # Need to flip because calibration has diameter increasing with decreasing flow
            smaller_dp = np.interp(higher_flow, np.flip(cal_satflow), np.flip(cal_diameter))
            larger_dp = np.interp(lower_flow, np.flip(cal_satflow), np.flip(cal_diameter))

            # Calculate dlogDp = log10(larger) - log10(smaller) > 0
            if larger_dp > 0 and smaller_dp > 0:
                dlogDp = np.log10(larger_dp) - np.log10(smaller_dp)
            else:
                dlogDp = 0

            # Get MaxDeteff at the larger diameter (as in PSM Inversion Tool)
            max_det_eff = np.interp(larger_dp, cal_diameter, cal_maxdeteff)

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
            # Clear plot
            self.image_item.clear()
            return

        try:
            n_scans = len(self.scan_buffer)
            num_bins = self.num_bins

            # Get current time and calculate 24-hour window
            now = pd.Timestamp.now()
            time_24h_ago = now - pd.Timedelta(hours=24)

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

            # Filter scans to last 24 hours
            scans_in_range = [(ts, scan) for ts, scan in zip(scan_timestamps, self.scan_buffer)
                              if ts >= time_24h_ago]

            # Create time grid for full 24-hour window with ~4 minute bins
            time_bin_size_seconds = 240  # 4 minutes
            n_time_bins = int(24 * 3600 / time_bin_size_seconds)  # 360 bins for 24 hours

            # Create data matrix with NaN for gaps (will show as black)
            data_matrix = np.full((num_bins, n_time_bins), np.nan)

            # Place each scan at its time position within the 24h window
            for ts, scan in scans_in_range:
                # Calculate seconds since 24h ago
                seconds_since_start = (ts - time_24h_ago).total_seconds()
                time_idx = int(seconds_since_start / time_bin_size_seconds)
                time_idx = max(0, min(time_idx, n_time_bins - 1))  # Clamp to valid range

                dN_dlogDp = scan['dN_dlogDp']
                if len(dN_dlogDp) == num_bins:
                    # If multiple scans fall in same bin, average them
                    if np.isnan(data_matrix[0, time_idx]):
                        data_matrix[:, time_idx] = dN_dlogDp
                    else:
                        data_matrix[:, time_idx] = (data_matrix[:, time_idx] + dN_dlogDp) / 2

            # Debug output
            if not hasattr(self, '_render_debug_done') or not self._render_debug_done:
                self._render_debug_done = True
                print(f"\n=== Contour Render Debug ===")
                print(f"Total scans in buffer: {n_scans}")
                print(f"Scans in last 24h: {len(scans_in_range)}")
                print(f"Time window: {time_24h_ago.strftime('%Y-%m-%d %H:%M')} to {now.strftime('%Y-%m-%d %H:%M')}")
                print(f"Time bins: {n_time_bins}")
                valid_count = np.count_nonzero(~np.isnan(data_matrix[0, :]))
                print(f"Time bins with data: {valid_count} / {n_time_bins}")

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
            # X-axis: hours from start of 24h window (0 = 24h ago, 24 = now)
            # Convert to "hours since 24h ago" which maps to actual clock times
            start_hour = time_24h_ago.hour + time_24h_ago.minute / 60
            pos_x = start_hour
            pos_y = self.bin_limits_dp[0]
            width = 24  # 24 hours
            height = self.bin_limits_dp[-1] - self.bin_limits_dp[0]

            self.image_item.setRect(pos_x, pos_y, width, height)

            # Update axis label
            self.plot.setLabel('bottom', 'Time')

            # Update colorbar range (don't include the "gap" value)
            self.colorbar.setLevels((min_z, max_z))

            # Add file boundary markers
            self._draw_file_boundaries(scans_in_range, time_24h_ago, pos_y, height)

        except Exception as e:
            print(f"Error rendering contour: {e}")
            import traceback
            traceback.print_exc()

    def _draw_file_boundaries(self, scans_in_range, time_24h_ago, y_min, y_height):
        """Draw vertical lines and labels at file boundaries."""
        # Remove old markers
        for line in self.file_boundary_lines:
            self.plot.removeItem(line)
        for label in self.file_boundary_labels:
            self.plot.removeItem(label)
        self.file_boundary_lines = []
        self.file_boundary_labels = []

        if not scans_in_range:
            return

        # Find file boundaries (where source_file changes)
        current_file = None
        file_ranges = []  # List of (file_name, start_time, end_time)

        for ts, scan in scans_in_range:
            source_file = scan.get('source_file', 'unknown')
            if source_file != current_file:
                # New file started
                if current_file is not None and file_ranges:
                    # Update end time of previous file
                    file_ranges[-1] = (file_ranges[-1][0], file_ranges[-1][1], ts)
                # Start new file range
                file_ranges.append((source_file, ts, ts))
                current_file = source_file
            else:
                # Update end time of current file
                if file_ranges:
                    file_ranges[-1] = (file_ranges[-1][0], file_ranges[-1][1], ts)

        # Draw markers for each file boundary (skip the first one)
        start_hour = time_24h_ago.hour + time_24h_ago.minute / 60
        y_top = y_min + y_height

        for i, (file_name, start_ts, end_ts) in enumerate(file_ranges):
            # Calculate x positions (hours since 24h ago, adjusted to clock time)
            hours_start = (start_ts - time_24h_ago).total_seconds() / 3600
            hours_end = (end_ts - time_24h_ago).total_seconds() / 3600
            x_start = start_hour + hours_start
            x_end = start_hour + hours_end

            # Draw white vertical line at file start
            line_start = pg.InfiniteLine(
                pos=x_start,
                angle=90,
                pen=pg.mkPen(color='w', width=1, style=Qt.SolidLine)
            )
            self.plot.addItem(line_start)
            self.file_boundary_lines.append(line_start)

            # Draw white vertical line at file end
            line_end = pg.InfiniteLine(
                pos=x_end,
                angle=90,
                pen=pg.mkPen(color='w', width=1, style=Qt.SolidLine)
            )
            self.plot.addItem(line_end)
            self.file_boundary_lines.append(line_end)

            # Show time from filename (HHMMSS format)
            # Format: YYYYMMDD_HHMMSS_DeviceType_Tag.dat
            display_name = file_name.replace('.dat', '')
            parts = display_name.split('_')
            if len(parts) >= 2:
                display_name = parts[1]  # The HHMMSS time part
            else:
                display_name = f"#{i + 1}"

            # Add file name label at top of plot (centered between start and end)
            x_center = (x_start + x_end) / 2
            label = pg.TextItem(
                text=display_name,
                color='w',
                anchor=(0.5, 1)  # Anchor at center-bottom
            )
            label.setPos(x_center, y_top)
            label.setFont(pg.QtGui.QFont('Arial', 9))
            self.plot.addItem(label)
            self.file_boundary_labels.append(label)

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
        averaged = df.rolling(n, min_periods=1, axis=1).mean()
        return averaged.values

    def _load_historical_data(self):
        """
        Load historical scan data from today's .dat file.
        Called automatically after calibration loads, or manually from settings menu.
        """
        if not self.calibration_loaded:
            print("Cannot load historical data: calibration not loaded")
            return

        try:
            # Get device information from config
            serial_number = self.device_config.serial_number
            device_nickname = self.device_config.device_nickname

            # Get file path from global config
            if not self.app_config:
                print("Cannot access app config")
                return

            file_path = self.app_config.data_settings.file_path
            file_tag = self.app_config.data_settings.file_tag

            print(f"Searching for today's .dat file in: {file_path}")

            # Reset debug flags for fresh output
            self._render_debug_done = False
            self._debug_count = 0
            self._bin_debug_count = 0

            # Load historical scans from ALL .dat files in last 24 hours
            filepaths, scans = load_historical_scans(
                file_path=file_path,
                serial_number=serial_number,
                device_nickname=device_nickname,
                file_tag=file_tag
            )

            if filepaths is None or len(filepaths) == 0:
                print("No data files found for last 24 hours")
                self.file_label.setText("No data files found")
                return

            if not scans:
                file_names = ", ".join(os.path.basename(f) for f in filepaths)
                print(f"No valid scans found in: {file_names}")
                self.file_label.setText(f"No scans in {len(filepaths)} file(s)")
                return

            # Store loaded file paths
            self.loaded_file_path = filepaths

            print(f"Loading historical data from {len(filepaths)} file(s)")
            for fp in filepaths:
                print(f"  - {os.path.basename(fp)}")
            print(f"Found {len(scans)} merged scan(s)")

            # Clear existing buffer before loading historical data
            self.scan_buffer = []

            # Process each scan
            for i, scan_data in enumerate(scans):
                try:
                    self._process_historical_scan(scan_data)
                except Exception as e:
                    print(f"Error processing scan {i+1}: {e}")
                    import traceback
                    traceback.print_exc()

            # Get time range and update label with full info
            start_time, end_time = get_scan_time_range(scans)
            if start_time and end_time:
                time_range = f"{start_time.strftime('%H:%M:%S')} - {end_time.strftime('%H:%M:%S')}"
                print(f"Loaded {len(self.scan_buffer)} scans from {time_range}")
                # Show file count and scan count in label
                if len(filepaths) == 1:
                    self.file_label.setText(f"File: {os.path.basename(filepaths[0])} ({len(self.scan_buffer)} scans)")
                else:
                    self.file_label.setText(f"{len(filepaths)} files ({len(self.scan_buffer)} scans)")

            # Render contour with loaded data
            self._render_contour()

        except Exception as e:
            print(f"Error loading historical data: {e}")
            import traceback
            traceback.print_exc()

    def _process_historical_scan(self, scan_data: Dict[str, np.ndarray]):
        """
        Process a historical scan and add it to the scan buffer.

        Args:
            scan_data: Dict with keys 'times', 'satflows', 'concentrations'
        """
        times = scan_data['times']
        satflows = scan_data['satflows']
        concentrations = scan_data['concentrations']

        if len(times) < 3:
            return  # Skip incomplete scans

        # Bin and invert in one step (matching reference tool algorithm)
        dN_dlogDp = self._bin_and_invert_scan(satflows, concentrations)

        # Store scan result
        scan_result = {
            'time': times[0],  # Use first timestamp as scan time
            'bin_centers': self.bin_centers_dp.copy(),
            'dN_dlogDp': dN_dlogDp,
            'source_file': scan_data.get('source_file', 'live')  # Track source file
        }

        self.scan_buffer.append(scan_result)
