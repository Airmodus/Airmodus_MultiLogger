"""
Data Settings Dialog

Popup dialog for configuring data logging settings.
Accessed via gear icon in status bar.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QPushButton, QLabel, QLineEdit, QCheckBox,
                              QFileDialog, QWidget, QSpinBox, QTabWidget,
                              QGroupBox, QMessageBox, QFrame, QMenu)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCursor
from datetime import datetime as dt
import logging


class FilePathBuilder(QWidget):
    """
    Visual file path builder widget - minimalistic style.

    Shows the full file path as a template with editable and non-editable parts:
    /path/to/folder / YYYYMMDD_HHMMSS _ serial _ type _ nickname _ [tag].dat
    """

    def __init__(self, config, data_holder, parent=None):
        super().__init__(parent)
        self.config = config
        self.data_holder = data_holder
        self._current_device_id = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # "Save to:" row - file path template
        save_row = QHBoxLayout()
        save_row.setSpacing(0)

        save_label = QLabel("Save to:")
        save_label.setStyleSheet("color: #ccc; font-size: 13px;")
        save_label.setFixedWidth(70)
        save_row.addWidget(save_label)

        # Folder path (clickable)
        self.folder_btn = QPushButton()
        self.folder_btn.setFlat(True)
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.setStyleSheet("""
            QPushButton {
                color: #4a9eff;
                background: transparent;
                border: none;
                text-align: left;
                padding: 0px;
                font-family: monospace;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #6bb3ff;
                text-decoration: underline;
            }
        """)
        self.folder_btn.clicked.connect(self._browse_folder)
        self.folder_btn.setToolTip("Click to change save location")
        save_row.addWidget(self.folder_btn)

        # Separator
        sep1 = QLabel("/")
        sep1.setStyleSheet("color: #666; font-family: monospace; font-size: 12px;")
        save_row.addWidget(sep1)

        # Timestamp (static placeholder)
        self.timestamp_label = QLabel("YYYYMMDD_HHMMSS")
        self.timestamp_label.setStyleSheet("color: #666; font-family: monospace; font-size: 12px;")
        self.timestamp_label.setToolTip("Timestamp when file is created")
        save_row.addWidget(self.timestamp_label)

        # Underscore separator
        sep2 = QLabel("_")
        sep2.setStyleSheet("color: #666; font-family: monospace; font-size: 12px;")
        save_row.addWidget(sep2)

        # Device info button (clickable to show all devices)
        self.device_info_btn = QPushButton()
        self.device_info_btn.setFlat(True)
        self.device_info_btn.setCursor(Qt.PointingHandCursor)
        self.device_info_btn.setStyleSheet("""
            QPushButton {
                color: #888;
                background: transparent;
                border: none;
                padding: 0px;
                font-family: monospace;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #4a9eff;
            }
        """)
        self.device_info_btn.clicked.connect(self._show_devices_menu)
        self.device_info_btn.setToolTip("Click to see all devices being saved")
        save_row.addWidget(self.device_info_btn)

        # File tag (editable)
        self.tag_sep = QLabel("_")
        self.tag_sep.setStyleSheet("color: #666; font-family: monospace; font-size: 12px;")
        save_row.addWidget(self.tag_sep)

        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("tag")
        self.tag_input.setMaximumWidth(80)
        self.tag_input.setStyleSheet("""
            QLineEdit {
                color: #4a9eff;
                background: transparent;
                border: 1px solid #3d3d3d;
                border-radius: 3px;
                padding: 1px 4px;
                font-family: monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #4a9eff;
            }
            QLineEdit::placeholder {
                color: #555;
            }
        """)
        self.tag_input.setToolTip("Optional file tag (editable)")
        save_row.addWidget(self.tag_input)

        # Extension
        self.ext_label = QLabel(".dat")
        self.ext_label.setStyleSheet("color: #666; font-family: monospace; font-size: 12px;")
        save_row.addWidget(self.ext_label)

        save_row.addStretch()
        layout.addLayout(save_row)

        # "Last write:" row - single line like the checkbox hints
        last_write_row = QHBoxLayout()
        last_write_row.setSpacing(0)

        self.last_write_label = QLabel("Last write:")
        self.last_write_label.setStyleSheet("color: #ccc; font-size: 13px;")
        self.last_write_label.setFixedWidth(70)
        last_write_row.addWidget(self.last_write_label)

        # Last write info (path and time as inline hint style)
        self.last_write_info = QLabel()
        self.last_write_info.setStyleSheet("color: #666; font-size: 11px;")
        self.last_write_info.setWordWrap(True)
        last_write_row.addWidget(self.last_write_info)

        last_write_row.addStretch()
        layout.addLayout(last_write_row)

    def _browse_folder(self):
        """Open folder selection dialog."""
        current_path = self.config.data_settings.file_path or ""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Data Save Location",
            current_path,
            QFileDialog.ShowDirsOnly
        )
        if directory:
            self.config.data_settings.file_path = directory
            self._update_folder_display()

    def _update_folder_display(self):
        """Update the folder path button text."""
        path = self.config.data_settings.file_path
        if path:
            # Show path, truncate middle if too long
            max_len = 40
            if len(path) > max_len:
                # Show start and end
                path = path[:15] + "..." + path[-(max_len-18):]
            self.folder_btn.setText(path)
            self.folder_btn.setToolTip(f"Click to change: {self.config.data_settings.file_path}")
        else:
            self.folder_btn.setText("Click to select folder...")
            self.folder_btn.setToolTip("Click to select save location")

    def _show_devices_menu(self):
        """Show popup menu listing all devices being saved."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                color: #ccc;
                padding: 6px 12px;
                font-family: monospace;
                font-size: 11px;
            }
            QMenu::item:disabled {
                color: #888;
            }
            QMenu::separator {
                height: 1px;
                background: #3d3d3d;
                margin: 4px 8px;
            }
        """)

        if not self.config.devices:
            action = menu.addAction("No devices configured")
            action.setEnabled(False)
        else:
            # Header
            header = menu.addAction("Files being saved:")
            header.setEnabled(False)
            menu.addSeparator()

            for device in self.config.devices:
                # Build filename preview for this device
                serial = device.serial_number or "(serial)"
                dev_type = device.device_type_name or "(type)"
                nickname = f"_{device.device_nickname}" if device.device_nickname else ""
                tag = f"_{self.config.data_settings.file_tag}" if self.config.data_settings.file_tag else ""

                filename = f"YYYYMMDD_HHMMSS_{serial}_{dev_type}{nickname}{tag}.dat"

                display_name = device.device_nickname or device.device_type_name or f"Device {device.device_id}"
                action = menu.addAction(f"{display_name}:\n  {filename}")
                action.setEnabled(False)  # Just for display

        # Show menu at button position
        menu.exec_(QCursor.pos())

    def _update_device_info_display(self):
        """Update the device info button text."""
        if not self.config.devices:
            self.device_info_btn.setText("(device)")
            return

        # Show first device info, user can click to see all
        dev = self.config.devices[0]
        parts = []
        if dev.serial_number:
            parts.append(dev.serial_number)
        parts.append(dev.device_type_name or "(type)")
        if dev.device_nickname:
            parts.append(dev.device_nickname)
        self.device_info_btn.setText("_".join(parts))

    def load_values(self):
        """Load current values into the widget."""
        self._update_folder_display()
        self.tag_input.setText(self.config.data_settings.file_tag or "")
        self._update_device_info_display()
        self._update_last_write()
        self.start_live_updates()  # Start live updates for last write info

    def _update_last_write(self):
        """Update last write info based on save_data status."""
        # Check if saving is enabled (check both config and checkbox if available)
        save_enabled = self.config.data_settings.save_data
        if hasattr(self, '_save_data_checkbox_ref') and self._save_data_checkbox_ref:
            save_enabled = self._save_data_checkbox_ref.isChecked()

        if not save_enabled:
            # Show warning when save data is off
            self.last_write_label.setText("Not saving:")
            self.last_write_label.setStyleSheet("color: #f0c040; font-size: 13px;")
            self.last_write_info.setText("save data is turned off")
            self.last_write_info.setStyleSheet("color: #f0c040; font-size: 11px;")
            return

        # Normal state - saving is enabled
        self.last_write_label.setText("Last write:")
        self.last_write_label.setStyleSheet("color: #ccc; font-size: 13px;")
        self.last_write_info.setStyleSheet("color: #666; font-size: 11px;")

        # Show just the timestamp
        if hasattr(self.data_holder, 'last_write_timestamp') and self.data_holder.last_write_timestamp:
            last_dt = dt.fromtimestamp(self.data_holder.last_write_timestamp)
            self.last_write_info.setText(last_dt.strftime("%H:%M:%S"))
        else:
            self.last_write_info.setText("--:--:--")

    def set_save_checkbox_ref(self, checkbox):
        """Set reference to save_data checkbox for live status updates."""
        self._save_data_checkbox_ref = checkbox

    def get_file_tag(self):
        """Get the current file tag value."""
        return self.tag_input.text()

    def start_live_updates(self):
        """Start timer for live updates of last write info."""
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_last_write)
        self._update_timer.start(1000)  # Update every second

    def stop_live_updates(self):
        """Stop the live update timer."""
        if hasattr(self, '_update_timer') and self._update_timer:
            self._update_timer.stop()


class DataSettingsDialog(QDialog):
    """
    Dialog for configuring data logging settings.

    Provides UI for:
    - Visual file path builder with folder selection and file tag
    - Save data checkbox
    - Generate daily files checkbox
    - Resume on startup checkbox
    """

    def __init__(self, config, data_holder, parent=None):
        super().__init__(parent)
        self.config = config
        self.data_holder = data_holder
        self.main_window = parent  # Store parent (MainWindow) for signal emission

        self.setWindowTitle("Settings")
        self.resize(600, 450)
        self.setModal(True)

        self._setup_ui()
        self._load_current_values()

    def _setup_ui(self):
        """Create the dialog UI layout."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Create tab widget
        tab_widget = QTabWidget()

        # === Data Tab ===
        data_tab = QWidget()
        data_layout = QVBoxLayout(data_tab)
        data_layout.setContentsMargins(15, 15, 15, 15)
        data_layout.setSpacing(15)

        # File path builder widget
        self.file_path_builder = FilePathBuilder(self.config, self.data_holder, self)
        data_layout.addWidget(self.file_path_builder)

        # Checkboxes with inline hints
        options_layout = QVBoxLayout()
        options_layout.setSpacing(10)

        # Save data checkbox with hint
        save_row = QHBoxLayout()
        self.save_data_checkbox = QCheckBox("Save data")
        self.save_data_checkbox.setToolTip("Enable/disable data saving")
        self.save_data_checkbox.stateChanged.connect(self._on_save_data_changed)
        save_row.addWidget(self.save_data_checkbox)
        self.save_hint = QLabel("— writes .dat files to the folder above")
        self.save_hint.setStyleSheet("color: #666; font-size: 11px;")
        save_row.addWidget(self.save_hint)
        save_row.addStretch()
        options_layout.addLayout(save_row)

        # Connect checkbox to file path builder for live status updates
        self.file_path_builder.set_save_checkbox_ref(self.save_data_checkbox)

        # Generate daily files checkbox with hint
        daily_row = QHBoxLayout()
        self.generate_daily_checkbox = QCheckBox("Generate daily files")
        self.generate_daily_checkbox.setToolTip("If on, new files are started at midnight")
        self.generate_daily_checkbox.stateChanged.connect(self._on_daily_files_changed)
        daily_row.addWidget(self.generate_daily_checkbox)
        self.daily_hint = QLabel("— new file at midnight")
        self.daily_hint.setStyleSheet("color: #666; font-size: 11px;")
        daily_row.addWidget(self.daily_hint)
        daily_row.addStretch()
        options_layout.addLayout(daily_row)

        # Resume on startup checkbox with hint
        resume_row = QHBoxLayout()
        self.resume_startup_checkbox = QCheckBox("Resume on startup")
        self.resume_startup_checkbox.setToolTip("Auto-connect to devices and restore settings on startup")
        resume_row.addWidget(self.resume_startup_checkbox)
        self.resume_hint = QLabel("— auto-connect devices on launch")
        self.resume_hint.setStyleSheet("color: #666; font-size: 11px;")
        resume_row.addWidget(self.resume_hint)
        resume_row.addStretch()
        options_layout.addLayout(resume_row)

        data_layout.addLayout(options_layout)

        # === Diagnostics Export Section ===
        data_layout.addSpacing(10)

        diagnostics_group = QGroupBox("Diagnostics")
        diagnostics_layout = QHBoxLayout()
        diagnostics_layout.setContentsMargins(10, 10, 10, 10)

        self.view_diagnostics_button = QPushButton("View Diagnostics")
        self.view_diagnostics_button.setToolTip(
            "View device status and errors in a readable format"
        )
        self.view_diagnostics_button.clicked.connect(self._view_diagnostics)
        diagnostics_layout.addWidget(self.view_diagnostics_button)

        self.export_diagnostics_button = QPushButton("Export to File...")
        self.export_diagnostics_button.setToolTip(
            "Export comprehensive diagnostic information to a JSON file for debugging field device issues"
        )
        self.export_diagnostics_button.clicked.connect(self._export_diagnostics)
        diagnostics_layout.addWidget(self.export_diagnostics_button)
        diagnostics_layout.addStretch()

        diagnostics_group.setLayout(diagnostics_layout)
        data_layout.addWidget(diagnostics_group)

        data_layout.addStretch()

        # === Plot Tab ===
        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        plot_layout.setContentsMargins(15, 15, 15, 15)

        plot_form = QFormLayout()
        plot_form.setSpacing(15)
        plot_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        plot_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.follow_checkbox = QCheckBox()
        plot_form.addRow("Follow:", self.follow_checkbox)

        self.time_window_spinbox = QSpinBox()
        self.time_window_spinbox.setRange(1, 3600)
        self.time_window_spinbox.setSuffix(" s")
        plot_form.addRow("Time window:", self.time_window_spinbox)

        self.autoscale_y_checkbox = QCheckBox()
        plot_form.addRow("Autoscale Y:", self.autoscale_y_checkbox)

        plot_layout.addLayout(plot_form)
        plot_layout.addStretch()

        # Add tabs
        tab_widget.addTab(data_tab, "Data")
        tab_widget.addTab(plot_tab, "Plot")

        layout.addWidget(tab_widget)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        apply_button = QPushButton("Apply")
        apply_button.clicked.connect(self.accept)
        apply_button.setDefault(True)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(apply_button)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _on_save_data_changed(self, state):
        """Handle save data checkbox state change."""
        # Immediately update the file path builder display
        self.file_path_builder._update_last_write()

    def _on_daily_files_changed(self, state):
        """Handle daily files checkbox state change."""
        if state:
            self.daily_hint.setText("— new file at midnight")
        else:
            self.daily_hint.setText("— single continuous file")

    def _load_current_values(self):
        """Load current config values into dialog widgets."""
        try:
            # Data settings
            data_settings = self.config.data_settings
            self.save_data_checkbox.setChecked(data_settings.save_data)
            self.generate_daily_checkbox.setChecked(data_settings.generate_daily_files)
            self.resume_startup_checkbox.setChecked(data_settings.resume_on_startup)

            # Update hint text based on initial state
            self._on_daily_files_changed(data_settings.generate_daily_files)

            # File path builder
            self.file_path_builder.load_values()

            # Plot settings
            plot_settings = self.config.plot_settings
            self.follow_checkbox.setChecked(plot_settings.follow)
            self.time_window_spinbox.setValue(int(plot_settings.time_window_s))
            self.autoscale_y_checkbox.setChecked(plot_settings.autoscale_y)
        except Exception as e:
            logging.error(f"Error loading settings values: {e}")

    def accept(self):
        """Save dialog values back to config and emit signals."""
        try:
            # Update Data settings
            data_settings = self.config.data_settings
            data_settings.file_tag = self.file_path_builder.get_file_tag()
            data_settings.save_data = self.save_data_checkbox.isChecked()
            data_settings.generate_daily_files = self.generate_daily_checkbox.isChecked()
            data_settings.resume_on_startup = self.resume_startup_checkbox.isChecked()

            # Update Plot settings
            plot_settings = self.config.plot_settings
            plot_settings.follow = self.follow_checkbox.isChecked()
            plot_settings.time_window_s = self.time_window_spinbox.value()
            plot_settings.autoscale_y = self.autoscale_y_checkbox.isChecked()

            # Emit signals to notify components
            # Note: save_ini() is already connected to these signals, so saving happens automatically
            if self.main_window:
                self.main_window.data_settings_changed.emit(data_settings)
                self.main_window.plot_settings_changed.emit(plot_settings)

            # Close dialog
            super().accept()
        except Exception as e:
            logging.error(f"Error saving settings: {e}")
            super().reject()

    def _export_diagnostics(self):
        """Handle diagnostics export button click."""
        from diagnostics import DiagnosticsExporter
        from datetime import datetime

        # Generate default filename with timestamp
        default_filename = f"diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Get save path from user
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Diagnostics",
            default_filename,
            "JSON Files (*.json);;All Files (*)"
        )

        if not filepath:
            return  # User cancelled

        try:
            # Create exporter and collect diagnostics
            exporter = DiagnosticsExporter(
                self.config,
                self.data_holder,
                self.main_window
            )
            diagnostics = exporter.collect_all()

            # Export to file
            exporter.export_to_file(diagnostics, filepath)

            # Show success message
            QMessageBox.information(
                self,
                "Export Complete",
                f"Diagnostics exported successfully to:\n{filepath}"
            )
        except Exception as e:
            logging.error(f"Failed to export diagnostics: {e}")
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export diagnostics:\n{str(e)}"
            )

    def _view_diagnostics(self):
        """Open the diagnostics viewer dialog."""
        from dialogs.diagnostics_dialog import DiagnosticsDialog

        dialog = DiagnosticsDialog(
            self.config,
            self.data_holder,
            self.main_window
        )
        dialog.exec_()
