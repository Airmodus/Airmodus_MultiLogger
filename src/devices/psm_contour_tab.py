"""
PSM Contour Plot Tab

Displays real-time particle size distribution as a 2D contour plot.
Each completed scan adds a new vertical line to the plot.
Requires calibration file to perform size distribution inversion.
"""

import os
import numpy as np
import pandas as pd
from typing import Optional, List, Dict
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QFileDialog, QMenu, QSizePolicy)
from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QIcon
import pyqtgraph as pg
from scipy.interpolate import interp1d
from dat_file_reader import load_historical_scans, get_scan_time_range
from config import PSM, PSM2


class PSMContourTab(QWidget):
    """
    PSM Contour Plot Tab Widget

    Shows a real-time 2D heatmap of particle size distribution vs time.
    - X-axis: Time (scan timestamps)
    - Y-axis: Particle diameter (nm)
    - Color: log10(dN/dlogDp) concentration
    """

    def __init__(self, device_parameter):
        super().__init__()
        self.device_parameter = device_parameter

        # State flags
        self.calibration_loaded = False
        self.plot_initialized = False

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
        self.max_scans = 50  # Maximum number of scans to display

        # Create UI
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(self.main_layout)

        # Create initial calibration prompt view
        self._create_calibration_prompt()

        # Try to auto-load calibration on startup
        self._try_autoload_calibration()

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
        """Create the plot view with settings icon."""
        # Create plot widget container
        self.plot_widget = QWidget()
        plot_layout = QVBoxLayout()
        plot_layout.setContentsMargins(0, 0, 0, 0)

        # Top bar with settings button
        top_bar = QHBoxLayout()
        top_bar.addStretch()

        # Settings button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(30, 30)
        self.settings_btn.setStyleSheet("font-size: 18px;")
        self.settings_btn.clicked.connect(self._show_settings_menu)
        top_bar.addWidget(self.settings_btn)

        plot_layout.addLayout(top_bar)

        # Create PyQtGraph widget
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.plot = self.graphics_widget.addPlot()

        # Configure axes
        self.plot.setLabel('bottom', 'Time')
        self.plot.setLabel('left', 'Particle Diameter', units='nm')
        self.plot.showGrid(x=True, y=True, alpha=0.3)

        # Create image item for contour
        self.image_item = pg.ImageItem()
        self.plot.addItem(self.image_item)

        # Create colorbar
        self.colorbar = pg.ColorBarItem(
            values=(0, 1),
            colorMap=pg.colormap.get('CET-R4'),
            label='log10(dN/dlogDp) [cm⁻³]'
        )
        self.colorbar.setImageItem(self.image_item)
        self.graphics_widget.addItem(self.colorbar)

        plot_layout.addWidget(self.graphics_widget)
        self.plot_widget.setLayout(plot_layout)

        # Hide initially
        self.plot_widget.hide()
        self.main_layout.addWidget(self.plot_widget)

    def _try_autoload_calibration(self):
        """Try to auto-load calibration file from saved parameter."""
        try:
            # Check if parameter exists (may not exist for devices loaded from old configs)
            calib_param = self.device_parameter.child('Calibration file path')
            if calib_param is None:
                return

            calib_path = calib_param.value()
            if calib_path and os.path.exists(calib_path):
                self._load_calibration(calib_path)
        except Exception as e:
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

    def _load_calibration(self, file_path: str):
        """
        Load calibration file and initialize bins.

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

            # Calculate 6 fixed bins
            min_diameter = self.calibration_df['cal_diameter'].min()
            max_diameter = self.calibration_df['cal_diameter'].max()

            # Create 7 bin edges (for 6 bins) logarithmically spaced
            num_bins = 6
            num_limits = num_bins + 1
            self.bin_limits_dp = np.power(10, np.linspace(
                np.log10(min_diameter),
                np.log10(max_diameter),
                num_limits
            ))

            # Calculate bin centers (geometric mean)
            self.bin_centers_dp = np.array([
                np.sqrt(self.bin_limits_dp[i] * self.bin_limits_dp[i+1])
                for i in range(num_bins)
            ])

            # Convert diameter bins to flow bins using calibration
            self.bin_limits_flow = self._diameter_to_flow(self.bin_limits_dp)

            # Create detection efficiency interpolator
            self.detection_efficiency = interp1d(
                self.calibration_df['cal_diameter'],
                self.calibration_df['cal_maxdeteff'],
                kind='linear',
                bounds_error=False,
                fill_value=(self.calibration_df['cal_maxdeteff'].iloc[0],
                           self.calibration_df['cal_maxdeteff'].iloc[-1])
            )

            # Save calibration path to parameter
            self.device_parameter.child('Calibration file path').setValue(file_path)

            # Mark calibration as loaded
            self.calibration_loaded = True

            # Switch to plot view
            self.prompt_widget.hide()
            if not self.plot_initialized:
                self._create_plot_view()
                self.plot_initialized = True
            self.plot_widget.show()

            print(f"Calibration loaded: {num_bins} bins from {min_diameter:.2f} to {max_diameter:.2f} nm")

            # Auto-load historical data after calibration loads
            self._load_historical_data()

        except Exception as e:
            print(f"Error loading calibration file: {e}")
            import traceback
            traceback.print_exc()

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
        reload_action.triggered.connect(self._load_historical_data)

        # Show menu at button position
        menu.exec_(self.settings_btn.mapToGlobal(QPoint(0, self.settings_btn.height())))

    def _clear_calibration(self):
        """Clear calibration and return to prompt view."""
        self.calibration_loaded = False
        self.calibration_df = None
        self.bin_limits_dp = None
        self.bin_centers_dp = None
        self.bin_limits_flow = None
        self.detection_efficiency = None
        self.scan_buffer = []
        self._current_scan = None

        # Clear parameter
        self.device_parameter.child('Calibration file path').setValue('')

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

        Args:
            current_data: PSMData dataclass instance
        """
        if not self.calibration_loaded:
            return

        # Detect scan transitions using scan_status field
        scan_status = str(current_data.scan_status)

        # Check for scan start (transition to scanning state)
        if scan_status != "9" and scan_status != self._prev_scan_status:
            if scan_status in ["0", "1", "2"]:  # Active scan states
                # Finalize previous scan if exists
                if self._current_scan is not None:
                    self._finalize_scan()

                # Start new scan
                self._current_scan = {
                    'times': [],
                    'satflows': [],
                    'concentrations': []
                }

        # Accumulate data during scan
        if self._current_scan is not None and scan_status in ["0", "1", "2"]:
            # Only add valid data
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

            # Bin the data by saturator flow
            binned_concentrations = self._bin_scan_data(satflows, concentrations)

            # Perform step inversion
            dN_dlogDp = self._step_inversion(binned_concentrations)

            # Store scan result
            scan_result = {
                'time': times[0],  # Use first timestamp as scan time
                'bin_centers': self.bin_centers_dp.copy(),
                'dN_dlogDp': dN_dlogDp
            }

            self.scan_buffer.append(scan_result)

            # Limit buffer size
            if len(self.scan_buffer) > self.max_scans:
                self.scan_buffer.pop(0)

            # Update plot
            self._render_contour()

        except Exception as e:
            print(f"Error finalizing scan: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._current_scan = None

    def _bin_scan_data(self, satflows: np.ndarray, concentrations: np.ndarray) -> np.ndarray:
        """
        Bin scan data by saturator flow.

        Returns:
            Array of mean concentrations for each bin (6 values)
        """
        binned = np.zeros(6)

        for i in range(6):
            # Find measurements in this flow bin
            mask = (satflows >= self.bin_limits_flow[i]) & (satflows < self.bin_limits_flow[i+1])
            if np.any(mask):
                binned[i] = np.mean(concentrations[mask])
            else:
                binned[i] = np.nan

        return binned

    def _step_inversion(self, binned_concentrations: np.ndarray) -> np.ndarray:
        """
        Perform stepwise inversion to get dN/dlogDp.

        Algorithm:
        1. Calculate dN = concentration[i] - concentration[i+1] (difference between adjacent bins)
        2. Calculate dlogDp = log10(upper_dp) - log10(lower_dp) for each bin
        3. Get detection efficiency at bin center
        4. dN/dlogDp = dN / (dlogDp * detection_efficiency)

        Returns:
            Array of dN/dlogDp values (6 values)
        """
        dN_dlogDp = np.zeros(6)

        for i in range(6):
            # Calculate dN (difference from next bin, or zero for last bin)
            if i < 5:
                dN = binned_concentrations[i] - binned_concentrations[i+1]
            else:
                dN = binned_concentrations[i]  # Last bin

            # Calculate dlogDp
            dlogDp = np.log10(self.bin_limits_dp[i+1]) - np.log10(self.bin_limits_dp[i])

            # Get detection efficiency at bin center
            det_eff = self.detection_efficiency(self.bin_centers_dp[i])

            # Calculate dN/dlogDp
            if dlogDp > 0 and det_eff > 0 and not np.isnan(dN):
                dN_dlogDp[i] = dN / (dlogDp * det_eff)
            else:
                dN_dlogDp[i] = 0

        return dN_dlogDp

    def _render_contour(self):
        """Render the contour plot from scan buffer."""
        if not self.calibration_loaded or len(self.scan_buffer) == 0:
            # Clear plot
            self.image_item.clear()
            return

        try:
            # Extract data and timestamps from scan buffer
            n_scans = len(self.scan_buffer)
            data_matrix = np.zeros((6, n_scans))
            scan_times = []

            for i, scan in enumerate(self.scan_buffer):
                data_matrix[:, i] = scan['dN_dlogDp']
                scan_times.append(scan['time'])

            # Convert timestamps to seconds from first scan
            first_time = scan_times[0]
            time_seconds = np.array([(t - first_time).total_seconds() for t in scan_times])

            # Take log10 and handle invalid values
            data_matrix = np.where(data_matrix > 0, data_matrix, 1e-3)  # Set floor
            z = np.log10(data_matrix)

            # Normalize to 0-1 range
            min_z = np.nanmin(z)
            max_z = np.nanmax(z)

            if max_z > min_z:
                z_normalized = (z - min_z) / (max_z - min_z)
            else:
                z_normalized = np.zeros_like(z)

            # Update image
            self.image_item.setImage(z_normalized, autoLevels=False)

            # Set scale and position with time-aware X-axis
            # X-axis: time in seconds (shows gaps)
            # Y-axis: diameter bins (min to max diameter)
            total_time_span = time_seconds[-1] - time_seconds[0] if len(time_seconds) > 1 else 1
            pos_x = time_seconds[0]
            pos_y = self.bin_limits_dp[0]

            # Width spans from first to last scan time
            width = max(total_time_span, 1)  # At least 1 second wide
            height = self.bin_limits_dp[-1] - self.bin_limits_dp[0]

            self.image_item.setRect(pos_x, pos_y, width, height)

            # Update X-axis to show time labels
            if hasattr(self.plot, 'setLabel'):
                # Calculate time labels relative to first scan
                time_label = f"Time (s) - Starting at {scan_times[0].strftime('%H:%M:%S')}"
                self.plot.setLabel('bottom', time_label)

            # Update colorbar range
            self.colorbar.setLevels((min_z, max_z))

        except Exception as e:
            print(f"Error rendering contour: {e}")
            import traceback
            traceback.print_exc()

    def _load_historical_data(self):
        """
        Load historical scan data from today's .dat file.
        Called automatically after calibration loads, or manually from settings menu.
        """
        if not self.calibration_loaded:
            print("Cannot load historical data: calibration not loaded")
            return

        try:
            # Get device information from parameters
            device_type = self.device_parameter.child('Device type').value()
            serial_number = self.device_parameter.child('Serial number').value()
            device_nickname = self.device_parameter.child('Device nickname').value()

            # Get file path from global settings
            # Navigate up to root parameter tree
            # device_parameter -> Device settings -> root
            device_settings = self.device_parameter.parent()
            if device_settings is None:
                print("Cannot access Device settings")
                return

            root_params = device_settings.parent()
            if root_params is None:
                print("Cannot access root parameters")
                return

            file_path = root_params.child('Data settings').child('File path').value()
            file_tag = root_params.child('Data settings').child('File tag').value()

            print(f"Searching for today's .dat file in: {file_path}")

            # Load historical scans from .dat file
            filepath, scans = load_historical_scans(
                file_path=file_path,
                device_type=device_type,
                serial_number=serial_number,
                device_nickname=device_nickname,
                file_tag=file_tag
            )

            if filepath is None:
                print("No existing data file found for today")
                return

            if not scans:
                print(f"No valid scans found in {filepath}")
                return

            print(f"Loading historical data from: {os.path.basename(filepath)}")
            print(f"Found {len(scans)} scan(s) in file")

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

            # Get time range
            start_time, end_time = get_scan_time_range(scans)
            if start_time and end_time:
                time_range = f"{start_time.strftime('%H:%M:%S')} - {end_time.strftime('%H:%M:%S')}"
                print(f"Loaded {len(self.scan_buffer)} scans from {time_range}")

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

        # Bin the data by saturator flow
        binned_concentrations = self._bin_scan_data(satflows, concentrations)

        # Perform step inversion
        dN_dlogDp = self._step_inversion(binned_concentrations)

        # Store scan result
        scan_result = {
            'time': times[0],  # Use first timestamp as scan time
            'bin_centers': self.bin_centers_dp.copy(),
            'dN_dlogDp': dN_dlogDp
        }

        self.scan_buffer.append(scan_result)

        # Limit buffer size
        if len(self.scan_buffer) > self.max_scans:
            self.scan_buffer.pop(0)
