"""
Data Settings Dialog

Popup dialog for configuring data logging settings.
Accessed via gear icon in status bar.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QPushButton, QLabel, QLineEdit, QCheckBox,
                              QFileDialog, QWidget, QSpinBox, QTabWidget)
from PyQt5.QtCore import Qt
from datetime import datetime as dt


class DataSettingsDialog(QDialog):
    """
    Dialog for configuring data logging settings.

    Provides UI for:
    - File path (with browse button)
    - File tag
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
        self.resize(500, 400)
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

        data_form = QFormLayout()
        data_form.setSpacing(15)
        data_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        data_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        # File path with browse button
        file_path_layout = QHBoxLayout()
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("Select data save location...")
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse_file_path)
        file_path_layout.addWidget(self.file_path_input, stretch=1)
        file_path_layout.addWidget(browse_button)

        file_path_widget = QWidget()
        file_path_widget.setLayout(file_path_layout)
        data_form.addRow("File path:", file_path_widget)

        # File tag
        self.file_tag_input = QLineEdit()
        self.file_tag_input.setPlaceholderText("Optional tag for data files...")
        file_tag_label = QLabel("File tag:")
        file_tag_label.setToolTip("File name: YYYYMMDD_HHMMSS_(Serial number)_(Device type)_(Device nickname)_(File tag).dat")
        data_form.addRow(file_tag_label, self.file_tag_input)

        # Checkboxes
        self.save_data_checkbox = QCheckBox()
        data_form.addRow("Save data:", self.save_data_checkbox)

        # Add status label below save data checkbox
        self.save_status_label = QLabel()
        self.save_status_label.setWordWrap(True)
        self.save_status_label.setStyleSheet("color: #666666; font-size: 11px; padding-left: 0px;")
        data_form.addRow("", self.save_status_label)

        self.generate_daily_checkbox = QCheckBox()
        self.generate_daily_checkbox.setToolTip("If on, new files are started at midnight.")
        data_form.addRow("Generate daily files:", self.generate_daily_checkbox)

        self.resume_startup_checkbox = QCheckBox()
        self.resume_startup_checkbox.setToolTip("Option to resume the last settings on startup.")
        data_form.addRow("Resume on startup:", self.resume_startup_checkbox)

        data_layout.addLayout(data_form)
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

    def _browse_file_path(self):
        """Open file dialog to select directory."""
        current_path = self.file_path_input.text()
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Data Save Location",
            current_path,
            QFileDialog.ShowDirsOnly
        )
        if directory:
            self.file_path_input.setText(directory)

    def _load_current_values(self):
        """Load current config values into dialog widgets."""
        try:
            # Data settings
            data_settings = self.config.data_settings
            self.file_path_input.setText(data_settings.file_path or "")
            self.file_tag_input.setText(data_settings.file_tag or "")
            self.save_data_checkbox.setChecked(data_settings.save_data)
            self.generate_daily_checkbox.setChecked(data_settings.generate_daily_files)
            self.resume_startup_checkbox.setChecked(data_settings.resume_on_startup)

            # Plot settings
            plot_settings = self.config.plot_settings
            self.follow_checkbox.setChecked(plot_settings.follow)
            self.time_window_spinbox.setValue(int(plot_settings.time_window_s))
            self.autoscale_y_checkbox.setChecked(plot_settings.autoscale_y)

            # Update save status label
            self._update_save_status_label()
        except Exception as e:
            print(f"Error loading settings values: {e}")

    def accept(self):
        """Save dialog values back to config and emit signals."""
        try:
            # Update Data settings
            data_settings = self.config.data_settings
            data_settings.file_path = self.file_path_input.text()
            data_settings.file_tag = self.file_tag_input.text()
            data_settings.save_data = self.save_data_checkbox.isChecked()
            data_settings.generate_daily_files = self.generate_daily_checkbox.isChecked()
            data_settings.resume_on_startup = self.resume_startup_checkbox.isChecked()

            # Update Plot settings
            plot_settings = self.config.plot_settings
            plot_settings.follow = self.follow_checkbox.isChecked()
            plot_settings.time_window_s = self.time_window_spinbox.value()
            plot_settings.autoscale_y = self.autoscale_y_checkbox.isChecked()

            # Emit signals to notify components
            if self.main_window:
                self.main_window.data_settings_changed.emit(data_settings)
                self.main_window.plot_settings_changed.emit(plot_settings)

            # Save configuration
            if self.main_window:
                self.main_window.save_configuration()

            # Close dialog
            super().accept()
        except Exception as e:
            print(f"Error saving settings: {e}")
            super().reject()

    def _update_save_status_label(self):
        """Update the save status label with current save info."""
        try:
            save_data = self.config.data_settings.save_data

            if not save_data:
                self.save_status_label.setText("Not currently saving")
            else:
                # Build status text with timestamp, path, and filename
                status_parts = []

                # Add last write timestamp
                if hasattr(self.data_holder, 'last_write_timestamp') and self.data_holder.last_write_timestamp is not None:
                    last_write_dt = dt.fromtimestamp(self.data_holder.last_write_timestamp)
                    last_write_str = last_write_dt.strftime("%H:%M:%S")
                    status_parts.append(f"Last write: {last_write_str}")
                else:
                    status_parts.append("Last write: Not yet written")

                # Add file path
                if hasattr(self.data_holder, 'file_path') and self.data_holder.file_path:
                    status_parts.append(f"Path: {self.data_holder.file_path}")

                # Add most recent filename
                if hasattr(self.data_holder, 'most_recent_filename') and self.data_holder.most_recent_filename:
                    status_parts.append(f"File: {self.data_holder.most_recent_filename}")

                self.save_status_label.setText(" | ".join(status_parts) if status_parts else "Saving enabled")
        except Exception as e:
            print(f"Error updating save status label: {e}")
            self.save_status_label.setText("")
