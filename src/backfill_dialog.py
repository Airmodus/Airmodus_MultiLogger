"""
Backfill dialog UI for importing historical CPC and RHTP data files.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QPushButton, QLabel, QLineEdit, QFileDialog,
                             QComboBox, QRadioButton, QButtonGroup, QProgressBar,
                             QCheckBox, QTextEdit)
from PyQt5.QtCore import Qt, QThread
from pathlib import Path


class BackfillDialog(QDialog):
    """Dialog for selecting and configuring file backfill."""

    def __init__(self, parent=None, database_manager=None):
        super().__init__(parent)
        self.database_manager = database_manager
        self.backfill_thread = None

        # File paths
        self.cpc_dat_path = None
        self.cpc_par_path = None
        self.rhtp_dat_path = None

        # Detected info
        self.serial_number = None
        self.date_range = None
        self.num_records = 0

        self.setWindowTitle("Backfill Data from Files")
        self.setMinimumWidth(600)
        self.setMinimumHeight(600)

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # CPC Files Section
        cpc_group = self._create_cpc_files_section()
        layout.addWidget(cpc_group)

        # RHTP File Section
        rhtp_group = self._create_rhtp_files_section()
        layout.addWidget(rhtp_group)

        # Configuration Section
        config_group = self._create_configuration_section()
        layout.addWidget(config_group)

        # Info Display Section
        info_group = self._create_info_section()
        layout.addWidget(info_group)

        # Progress Section
        progress_group = self._create_progress_section()
        layout.addWidget(progress_group)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Backfill")
        self.start_button.clicked.connect(self.start_backfill)
        self.start_button.setEnabled(False)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _create_cpc_files_section(self):
        """Create CPC files selection section."""
        group = QGroupBox("CPC Files (Required)")
        layout = QVBoxLayout()

        # .dat file
        dat_layout = QHBoxLayout()
        dat_layout.addWidget(QLabel(".dat file (measurements):"))
        self.cpc_dat_edit = QLineEdit()
        self.cpc_dat_edit.setReadOnly(True)
        dat_layout.addWidget(self.cpc_dat_edit)
        self.cpc_dat_button = QPushButton("Browse...")
        self.cpc_dat_button.clicked.connect(self.browse_cpc_dat)
        dat_layout.addWidget(self.cpc_dat_button)
        layout.addLayout(dat_layout)

        # .par file
        par_layout = QHBoxLayout()
        par_layout.addWidget(QLabel(".par file (settings, optional):"))
        self.cpc_par_edit = QLineEdit()
        self.cpc_par_edit.setReadOnly(True)
        par_layout.addWidget(self.cpc_par_edit)
        self.cpc_par_button = QPushButton("Browse...")
        self.cpc_par_button.clicked.connect(self.browse_cpc_par)
        par_layout.addWidget(self.cpc_par_button)
        layout.addLayout(par_layout)

        group.setLayout(layout)
        return group

    def _create_rhtp_files_section(self):
        """Create RHTP file selection section."""
        group = QGroupBox("RHTP File (Optional)")
        layout = QVBoxLayout()

        # Enable checkbox
        self.rhtp_enabled_checkbox = QCheckBox("Include RHTP inlet conditions")
        self.rhtp_enabled_checkbox.stateChanged.connect(self.on_rhtp_enabled_changed)
        layout.addWidget(self.rhtp_enabled_checkbox)

        # .dat file
        dat_layout = QHBoxLayout()
        dat_layout.addWidget(QLabel(".dat file (RH, T, P):"))
        self.rhtp_dat_edit = QLineEdit()
        self.rhtp_dat_edit.setReadOnly(True)
        self.rhtp_dat_edit.setEnabled(False)
        dat_layout.addWidget(self.rhtp_dat_edit)
        self.rhtp_dat_button = QPushButton("Browse...")
        self.rhtp_dat_button.clicked.connect(self.browse_rhtp_dat)
        self.rhtp_dat_button.setEnabled(False)
        dat_layout.addWidget(self.rhtp_dat_button)
        layout.addLayout(dat_layout)

        group.setLayout(layout)
        return group

    def _create_configuration_section(self):
        """Create configuration section."""
        group = QGroupBox("Configuration")
        layout = QVBoxLayout()

        # Averaging interval
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("Averaging interval:"))
        self.interval_combo = QComboBox()
        self.interval_combo.addItems([
            "1 minute",
            "5 minutes",
            "10 minutes",
            "15 minutes",
            "1 hour",
            "3 hours"
        ])
        self.interval_combo.setCurrentIndex(1)  # Default to 5 minutes
        interval_layout.addWidget(self.interval_combo)
        interval_layout.addStretch()
        layout.addLayout(interval_layout)

        # Conflict handling
        conflict_label = QLabel("If record already exists:")
        layout.addWidget(conflict_label)

        self.conflict_button_group = QButtonGroup()
        self.skip_radio = QRadioButton("Skip existing records")
        self.overwrite_radio = QRadioButton("Overwrite existing records")
        self.skip_radio.setChecked(True)

        self.conflict_button_group.addButton(self.skip_radio)
        self.conflict_button_group.addButton(self.overwrite_radio)

        layout.addWidget(self.skip_radio)
        layout.addWidget(self.overwrite_radio)

        group.setLayout(layout)
        return group

    def _create_info_section(self):
        """Create info display section."""
        group = QGroupBox("Detected Information")
        layout = QVBoxLayout()

        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(100)
        self.info_text.setText("Select CPC .dat file to see information...")

        layout.addWidget(self.info_text)

        group.setLayout(layout)
        return group

    def _create_progress_section(self):
        """Create progress display section."""
        group = QGroupBox("Progress")
        layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        group.setLayout(layout)
        return group

    def browse_cpc_dat(self):
        """Browse for CPC .dat file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select CPC .dat file",
            "",
            "Data files (*.dat);;All files (*)"
        )

        if filepath:
            self.cpc_dat_path = filepath
            self.cpc_dat_edit.setText(filepath)
            self.analyze_cpc_file()
            self.update_start_button_state()

    def browse_cpc_par(self):
        """Browse for CPC .par file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select CPC .par file",
            "",
            "Parameter files (*.par);;All files (*)"
        )

        if filepath:
            self.cpc_par_path = filepath
            self.cpc_par_edit.setText(filepath)

    def browse_rhtp_dat(self):
        """Browse for RHTP .dat file."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select RHTP .dat file",
            "",
            "Data files (*.dat);;All files (*)"
        )

        if filepath:
            self.rhtp_dat_path = filepath
            self.rhtp_dat_edit.setText(filepath)

    def on_rhtp_enabled_changed(self, state):
        """Handle RHTP enabled checkbox state change."""
        enabled = (state == Qt.Checked)
        self.rhtp_dat_edit.setEnabled(enabled)
        self.rhtp_dat_button.setEnabled(enabled)

        if not enabled:
            self.rhtp_dat_path = None
            self.rhtp_dat_edit.clear()

    def analyze_cpc_file(self):
        """Analyze the selected CPC .dat file and display info."""
        if not self.cpc_dat_path:
            return

        try:
            from managers.file_parser import CPCFileParser

            parser = CPCFileParser()

            # Quick analysis: read first and last few lines
            with open(self.cpc_dat_path, 'r') as f:
                lines = f.readlines()

            # Extract serial number
            self.serial_number = parser.extract_serial_from_filename(self.cpc_dat_path)

            # Count non-header, non-empty lines
            valid_lines = 0
            first_timestamp = None
            last_timestamp = None

            for i, line in enumerate(lines):
                if i == 0:  # Skip header
                    continue
                line = line.strip()
                if not line:
                    continue

                parts = line.split(',')
                if len(parts) >= 1:
                    # Check if not all nan
                    if not all(p.strip().lower() == 'nan' for p in parts[1:]):
                        valid_lines += 1
                        if first_timestamp is None:
                            first_timestamp = parts[0]
                        last_timestamp = parts[0]

            self.num_records = valid_lines

            # Build info text
            info_parts = []
            if self.serial_number:
                info_parts.append(f"Serial Number: {self.serial_number}")
            else:
                info_parts.append("Serial Number: Unknown (check filename format)")

            info_parts.append(f"Valid Records: {valid_lines:,}")

            if first_timestamp and last_timestamp:
                info_parts.append(f"Date Range: {first_timestamp} to {last_timestamp}")

            # Calculate estimated averaged records
            interval_text = self.interval_combo.currentText()
            interval_map = {
                "1 minute": 1,
                "5 minutes": 5,
                "10 minutes": 10,
                "15 minutes": 15,
                "1 hour": 60,
                "3 hours": 180
            }
            interval_mins = interval_map.get(interval_text, 5)
            estimated_averaged = valid_lines // (interval_mins * 60) if valid_lines > 0 else 0
            info_parts.append(f"Estimated averaged records: ~{estimated_averaged:,} ({interval_text} intervals)")

            self.info_text.setText("\n".join(info_parts))

        except Exception as e:
            self.info_text.setText(f"Error analyzing file: {str(e)}")

    def update_start_button_state(self):
        """Enable/disable start button based on required inputs."""
        has_cpc_dat = self.cpc_dat_path is not None
        has_database = self.database_manager and self.database_manager.connected

        self.start_button.setEnabled(has_cpc_dat and has_database)

        if not has_database:
            self.progress_label.setText("⚠ Database not connected")

    def get_averaging_interval_minutes(self):
        """Get the selected averaging interval in minutes."""
        interval_map = {
            "1 minute": 1,
            "5 minutes": 5,
            "10 minutes": 10,
            "15 minutes": 15,
            "1 hour": 60,
            "3 hours": 180
        }
        return interval_map.get(self.interval_combo.currentText(), 5)

    def start_backfill(self):
        """Start the backfill process."""
        from managers.file_backfill import FileBackfillManager
        from PyQt5.QtCore import QThread

        # Disable UI during processing
        self.start_button.setEnabled(False)
        self.cpc_dat_button.setEnabled(False)
        self.cpc_par_button.setEnabled(False)
        self.rhtp_dat_button.setEnabled(False)
        self.rhtp_enabled_checkbox.setEnabled(False)
        self.interval_combo.setEnabled(False)
        self.skip_radio.setEnabled(False)
        self.overwrite_radio.setEnabled(False)

        # Get configuration
        averaging_interval = self.get_averaging_interval_minutes()
        overwrite = self.overwrite_radio.isChecked()

        # Get RHTP path if enabled
        rhtp_path = self.rhtp_dat_path if self.rhtp_enabled_checkbox.isChecked() else None

        # Create backfill manager
        manager = FileBackfillManager(self.database_manager)

        # Connect signals
        manager.progress.connect(self.on_progress)
        manager.finished.connect(self.on_finished)

        # Create worker thread
        class BackfillThread(QThread):
            def __init__(self, manager, cpc_dat, cpc_par, rhtp_dat, interval, overwrite):
                super().__init__()
                self.manager = manager
                self.cpc_dat = cpc_dat
                self.cpc_par = cpc_par
                self.rhtp_dat = rhtp_dat
                self.interval = interval
                self.overwrite = overwrite
                self.success = False
                self.statistics = {}

            def run(self):
                self.success, self.statistics = self.manager.backfill_from_files(
                    self.cpc_dat,
                    self.cpc_par,
                    self.rhtp_dat,
                    self.interval,
                    self.overwrite
                )

        self.backfill_thread = BackfillThread(
            manager,
            self.cpc_dat_path,
            self.cpc_par_path,
            rhtp_path,
            averaging_interval,
            overwrite
        )

        self.backfill_thread.finished.connect(lambda: self.on_thread_finished(
            self.backfill_thread.success,
            self.backfill_thread.statistics
        ))

        self.backfill_thread.start()

    def on_progress(self, current, total, message):
        """Handle progress updates."""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
        self.progress_label.setText(message)

    def on_finished(self, success, statistics):
        """Handle backfill completion."""
        # This is called from the manager, but we wait for thread to finish

    def on_thread_finished(self, success, statistics):
        """Handle thread completion."""
        if success:
            errors = statistics.get('errors', 0)
            written = statistics.get('records_written', 0)

            # Check if there were errors
            if errors > 0 and written == 0:
                # All records failed - this is actually a failure
                info_parts = [
                    f"✗ Backfill failed - all records had errors!",
                    f"",
                    f"CPC records parsed: {statistics.get('cpc_records_parsed', 0):,}",
                    f"RHTP records parsed: {statistics.get('rhtp_records_parsed', 0):,}",
                    f"Averaged records: {statistics.get('averaged_records', 0):,}",
                    f"Records written: {written:,}",
                    f"Errors: {errors:,}",
                    f"",
                    f"Error messages:"
                ]
                error_messages = statistics.get('error_messages', [])
                if error_messages:
                    for msg in error_messages[:5]:  # Show first 5 errors
                        info_parts.append(f"  • {msg}")
                else:
                    info_parts.append("  (No error details available)")

                self.info_text.setText("\n".join(info_parts))
                self.progress_label.setText("Failed - all records had errors")
            elif errors > 0:
                # Partial success
                info_parts = [
                    f"⚠ Backfill completed with errors",
                    f"",
                    f"CPC records parsed: {statistics.get('cpc_records_parsed', 0):,}",
                    f"RHTP records parsed: {statistics.get('rhtp_records_parsed', 0):,}",
                    f"Averaged records: {statistics.get('averaged_records', 0):,}",
                    f"Records written: {written:,}",
                    f"Records skipped: {statistics.get('records_skipped', 0):,}",
                    f"Errors: {errors:,}",
                    f"",
                    f"Sample error messages:"
                ]
                error_messages = statistics.get('error_messages', [])
                if error_messages:
                    for msg in error_messages[:3]:
                        info_parts.append(f"  • {msg}")
                self.info_text.setText("\n".join(info_parts))
                self.progress_label.setText("Completed with errors")
            else:
                # Full success
                info_parts = [
                    f"✓ Backfill completed successfully!",
                    f"",
                    f"CPC records parsed: {statistics.get('cpc_records_parsed', 0):,}",
                    f"RHTP records parsed: {statistics.get('rhtp_records_parsed', 0):,}",
                    f"Averaged records: {statistics.get('averaged_records', 0):,}",
                    f"Records written: {written:,}",
                    f"Records skipped: {statistics.get('records_skipped', 0):,}",
                ]
                self.info_text.setText("\n".join(info_parts))
                self.progress_label.setText("Complete!")

            self.progress_bar.setValue(100)

            # Change button to close
            self.start_button.setText("Close")
            self.start_button.setEnabled(True)
            self.start_button.clicked.disconnect()
            self.start_button.clicked.connect(self.accept)
        else:
            # Show error
            error_msg = statistics.get('error', 'Unknown error')
            self.info_text.setText(f"✗ Backfill failed:\n\n{error_msg}")
            self.progress_label.setText("Failed")

            # Re-enable UI
            self.start_button.setEnabled(True)
            self.cpc_dat_button.setEnabled(True)
            self.cpc_par_button.setEnabled(True)
            self.rhtp_dat_button.setEnabled(True)
            self.rhtp_enabled_checkbox.setEnabled(True)
            self.interval_combo.setEnabled(True)
            self.skip_radio.setEnabled(True)
            self.overwrite_radio.setEnabled(True)
