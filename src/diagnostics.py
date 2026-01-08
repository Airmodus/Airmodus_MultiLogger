"""
Diagnostics Export Module

Collects comprehensive diagnostic information from all application components
for debugging field device issues.
"""

import json
import platform
import sys
import os
import locale
import logging
from datetime import datetime
from dataclasses import asdict, fields, is_dataclass
from typing import Dict, Any, List
from math import isnan
from collections import deque

from PyQt5.QtCore import QT_VERSION_STR

from config import (
    version_number, CPC, PSM, TSI_CPC, EDILUTER, ELECTROMETER,
    CO2_SENSOR, RHTP, AFM, CPC_ERRORS, PSM_ERRORS
)


class DiagnosticsExporter:
    """
    Collects and exports diagnostic information from the application.

    Gathers device status, error codes, measurements, settings, and system
    information for debugging field device issues.
    """

    EXPORT_FORMAT_VERSION = "1.1"
    DEBUG_LOG_LINES = 200  # Number of recent log lines to include

    # Device type ID to name mapping
    DEVICE_TYPE_NAMES = {
        CPC: 'CPC',
        PSM: 'PSM',
        TSI_CPC: 'TSI_CPC',
        EDILUTER: 'eDiluter',
        ELECTROMETER: 'Electrometer',
        CO2_SENSOR: 'CO2_Sensor',
        RHTP: 'RHTP',
        AFM: 'AFM',
    }

    def __init__(self, config, data_holder, main_window=None):
        """
        Initialize the diagnostics exporter.

        Args:
            config: AppConfig instance with application configuration
            data_holder: DataHolder instance with runtime data
            main_window: Optional reference to main window for additional data
        """
        self.config = config
        self.data_holder = data_holder
        self.main_window = main_window

    def collect_all(self, include_logs: bool = True) -> Dict[str, Any]:
        """
        Collect all diagnostic information.

        Args:
            include_logs: Whether to include debug.log entries (default True)

        Returns:
            Dictionary containing all diagnostic data
        """
        result = {
            "export_info": self._collect_export_info(),
            "application": self._collect_application_info(),
            "session": self._collect_session_info(),
            "data_settings": self._collect_data_settings(),
            "plot_settings": self._collect_plot_settings(),
            "devices": self._collect_all_devices(),
            "error_summary": self._collect_error_summary(),
            "error_history": self._collect_error_history(),
            "communication_summary": self._collect_communication_summary()
        }

        if include_logs:
            result["recent_logs"] = self._collect_recent_logs()

        return result

    def export_to_file(self, diagnostics: Dict[str, Any], filepath: str) -> None:
        """
        Export diagnostics to JSON file.

        Args:
            diagnostics: Collected diagnostic data
            filepath: Path to write JSON file
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(diagnostics, f, indent=2, default=self._json_serializer)

    @staticmethod
    def _json_serializer(obj):
        """
        Custom JSON serializer for non-standard types.

        Handles numpy types, NaN values, and dataclasses.
        """
        # Handle numpy scalar types
        if hasattr(obj, 'item'):
            return obj.item()
        # Handle numpy arrays
        if hasattr(obj, 'tolist'):
            return obj.tolist()
        # Handle dataclasses
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        # Handle NaN floats
        if isinstance(obj, float) and isnan(obj):
            return None
        # Fallback to string representation
        return str(obj)

    def _collect_export_info(self) -> Dict[str, Any]:
        """Collect export metadata."""
        return {
            "export_timestamp": datetime.now().isoformat(),
            "format_version": self.EXPORT_FORMAT_VERSION
        }

    def _collect_application_info(self) -> Dict[str, Any]:
        """Collect application and system information."""
        try:
            current_locale = locale.getlocale()
            locale_str = f"{current_locale[0]}.{current_locale[1]}" if current_locale[0] else "Unknown"
        except Exception:
            locale_str = "Unknown"

        return {
            "version": version_number,
            "python_version": sys.version,
            "pyqt_version": QT_VERSION_STR,
            "platform": platform.platform(),
            "os_name": platform.system(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "locale": locale_str
        }

    def _collect_session_info(self) -> Dict[str, Any]:
        """Collect session state information."""
        dh = self.data_holder

        return {
            "first_connection_made": getattr(dh, 'first_connection', False),
            "time_counter": getattr(dh, 'time_counter', 0),
            "current_time": getattr(dh, 'current_time', 0),
            "max_time_reached": getattr(dh, 'max_reached', False),
            "saving_status": getattr(dh, 'saving_status', 0),
            "last_save_error": getattr(dh, 'last_save_error', None),
            "global_error_status": getattr(dh, 'error_status', 0),
            "last_write_timestamp": self._format_timestamp(getattr(dh, 'last_write_timestamp', None)),
            "most_recent_filename": getattr(dh, 'most_recent_filename', ""),
            "active_device_count": len(getattr(dh, 'device_widgets', {}))
        }

    def _collect_data_settings(self) -> Dict[str, Any]:
        """Collect data logging settings."""
        ds = self.config.data_settings
        return {
            "file_path": ds.file_path,
            "file_tag": ds.file_tag,
            "save_data": ds.save_data,
            "generate_daily_files": ds.generate_daily_files,
            "resume_on_startup": ds.resume_on_startup
        }

    def _collect_plot_settings(self) -> Dict[str, Any]:
        """Collect plot display settings."""
        ps = self.config.plot_settings
        return {
            "follow": ps.follow,
            "time_window_s": ps.time_window_s,
            "autoscale_y": ps.autoscale_y
        }

    def _collect_all_devices(self) -> List[Dict[str, Any]]:
        """Collect information from all configured devices."""
        devices = []

        for device_config in self.config.devices:
            device_info = self._collect_device_info(device_config)
            devices.append(device_info)

        return devices

    def _collect_device_info(self, device_config) -> Dict[str, Any]:
        """
        Collect comprehensive information for a single device.

        Args:
            device_config: DeviceConfig instance

        Returns:
            Dictionary with all device information
        """
        dev_id = device_config.device_id
        device_widget = self.data_holder.device_widgets.get(dev_id)

        # Basic device info from config
        info = {
            "device_id": dev_id,
            "device_type": device_config.device_type,
            "device_type_name": device_config.device_type_name,
            "serial_number": device_config.serial_number,
            "nickname": device_config.device_nickname,
            "com_port": device_config.com_port,
            "plot_to_main": device_config.plot_to_main,
            "extra_params": device_config.extra_params or {}
        }

        # Add widget-based information if device is active
        if device_widget:
            info["is_connected"] = getattr(device_widget, 'is_connected', False)
            info["firmware_version"] = getattr(device_widget, 'firmware_version', "")
            info["current_status"] = self._collect_device_status(device_widget, device_config)
            info["current_measurements"] = self._collect_device_measurements(device_widget)
            info["current_settings"] = self._collect_device_settings(device_widget)
            info["connection_info"] = self._collect_connection_info(device_widget)
        else:
            info["is_connected"] = False
            info["firmware_version"] = ""
            info["current_status"] = {}
            info["current_measurements"] = {}
            info["current_settings"] = {}
            info["connection_info"] = {}

        # Add file information
        info["data_files"] = self._collect_device_files(dev_id)

        return info

    def _collect_device_status(self, device_widget, device_config) -> Dict[str, Any]:
        """
        Collect and decode device status information.

        Args:
            device_widget: The device widget instance
            device_config: DeviceConfig instance

        Returns:
            Dictionary with status hex, binary, and decoded errors
        """
        status = {}
        current_data = getattr(device_widget, 'current_data', None)

        if current_data is None:
            return status

        device_type = device_config.device_type

        # CPC status
        if device_type == CPC:
            status_hex = getattr(current_data, 'status_hex', '')
            status["status_hex"] = status_hex
            status["status_binary"] = self._hex_to_binary(status_hex, 29)
            status["total_errors"] = getattr(current_data, 'total_errors', 0)
            status["decoded_errors"] = self._decode_cpc_errors(status_hex)

        # PSM status
        elif device_type == PSM:
            status_hex = getattr(current_data, 'status_hex', '')
            note_hex = getattr(current_data, 'note_hex', '')
            status["status_hex"] = status_hex
            status["status_binary"] = self._hex_to_binary(status_hex, 30)
            status["total_errors"] = getattr(current_data, 'total_errors', 0)
            status["decoded_errors"] = self._decode_psm_errors(status_hex)
            status["note_hex"] = note_hex
            status["note_binary"] = self._hex_to_binary(note_hex, 7)
            status["liquid_errors"] = getattr(current_data, 'liquid_errors', 0)
            status["decoded_notes"] = self._decode_psm_notes(note_hex)

        # TSI CPC status
        elif device_type == TSI_CPC:
            error_hex = getattr(current_data, 'error_hex', '')
            status["error_hex"] = error_hex

        # eDiluter status
        elif device_type == EDILUTER:
            status["status"] = getattr(current_data, 'status', '')

        return status

    def _collect_device_measurements(self, device_widget) -> Dict[str, Any]:
        """
        Collect current measurement values from device.

        Args:
            device_widget: The device widget instance

        Returns:
            Dictionary with all current measurement values
        """
        current_data = getattr(device_widget, 'current_data', None)

        if current_data is None:
            return {}

        # Convert dataclass to dict, filtering out internal fields
        if is_dataclass(current_data):
            measurements = {}
            for f in fields(current_data):
                value = getattr(current_data, f.name)
                # Skip status fields (handled separately)
                if f.name in ('status_hex', 'note_hex', 'error_hex', 'total_errors', 'liquid_errors'):
                    continue
                # Handle NaN values
                if isinstance(value, float) and isnan(value):
                    measurements[f.name] = None
                else:
                    measurements[f.name] = value
            return measurements

        return {}

    def _collect_device_settings(self, device_widget) -> Dict[str, Any]:
        """
        Collect current settings from device.

        Args:
            device_widget: The device widget instance

        Returns:
            Dictionary with all device settings
        """
        settings = getattr(device_widget, 'settings', None)

        if settings is None:
            return {}

        # Convert dataclass to dict
        if is_dataclass(settings):
            settings_dict = {}
            for f in fields(settings):
                value = getattr(settings, f.name)
                # Handle NaN values
                if isinstance(value, float) and isnan(value):
                    settings_dict[f.name] = None
                elif isinstance(value, list):
                    # Handle list fields (like dilution_parameters)
                    settings_dict[f.name] = value
                else:
                    settings_dict[f.name] = value
            return settings_dict

        return {}

    def _collect_connection_info(self, device_widget) -> Dict[str, Any]:
        """
        Collect serial connection information.

        Args:
            device_widget: The device widget instance

        Returns:
            Dictionary with connection details
        """
        connection = getattr(device_widget, 'connection', None)

        if connection is None:
            return {"is_open": False}

        try:
            return {
                "port": getattr(connection, 'port', ''),
                "baudrate": getattr(connection, 'baudrate', 0),
                "is_open": getattr(connection, 'is_open', False),
                "timeout": getattr(connection, 'timeout', None)
            }
        except Exception:
            return {"is_open": False}

    def _collect_device_files(self, dev_id: int) -> Dict[str, Any]:
        """
        Collect data file information for device.

        Args:
            dev_id: Device ID

        Returns:
            Dictionary with file names
        """
        dh = self.data_holder

        return {
            "dat_filename": dh.dat_filenames.get(dev_id, ""),
            "par_filename": dh.par_filenames.get(dev_id, ""),
            "ten_hz_filename": dh.ten_hz_filenames.get(dev_id, ""),
            "pulse_analysis_filename": dh.pulse_analysis_filenames.get(dev_id, "")
        }

    def _collect_error_summary(self) -> Dict[str, Any]:
        """Collect aggregate error information."""
        dh = self.data_holder

        devices_with_errors = []
        for dev_id, has_error in dh.device_errors.items():
            if has_error:
                # Find device config to get name
                for dc in self.config.devices:
                    if dc.device_id == dev_id:
                        devices_with_errors.append({
                            "device_id": dev_id,
                            "nickname": dc.device_nickname,
                            "serial_number": dc.serial_number
                        })
                        break

        return {
            "global_error_status": getattr(dh, 'error_status', 0),
            "devices_with_errors": devices_with_errors,
            "total_devices_with_errors": len(devices_with_errors)
        }

    def _collect_error_history(self) -> Dict[str, Any]:
        """Collect error history from the session."""
        dh = self.data_holder

        if not hasattr(dh, 'error_history'):
            return {
                "total_errors": 0,
                "errors": [],
                "errors_by_device": {},
                "errors_by_type": {}
            }

        error_history = dh.error_history
        all_errors = error_history.to_dict_list()

        # Group errors by device
        errors_by_device = {}
        for error in all_errors:
            dev_id = error.get('device_id')
            dev_name = error.get('device_name', 'Unknown')
            key = f"{dev_name} (ID: {dev_id})" if dev_id is not None else "System"
            if key not in errors_by_device:
                errors_by_device[key] = 0
            errors_by_device[key] += 1

        # Group errors by type
        errors_by_type = {}
        for error in all_errors:
            error_type = error.get('error_type', 'unknown')
            if error_type not in errors_by_type:
                errors_by_type[error_type] = 0
            errors_by_type[error_type] += 1

        return {
            "total_errors": len(all_errors),
            "errors": all_errors,
            "errors_by_device": errors_by_device,
            "errors_by_type": errors_by_type
        }

    def _collect_communication_summary(self) -> Dict[str, Any]:
        """Collect serial port information."""
        dh = self.data_holder

        available_ports = []
        for port in getattr(dh, 'current_ports', []):
            if hasattr(port, 'device'):
                available_ports.append(port.device)
            else:
                available_ports.append(str(port))

        return {
            "available_ports": available_ports,
            "port_descriptions": getattr(dh, 'com_descriptions', {})
        }

    def _decode_cpc_errors(self, status_hex: str) -> List[str]:
        """
        Decode CPC status hex to list of error descriptions.

        Args:
            status_hex: Hexadecimal status string

        Returns:
            List of active error descriptions
        """
        errors = []
        if not status_hex:
            return errors

        try:
            status_int = int(status_hex, 16)
            for i, error_desc in enumerate(CPC_ERRORS):
                if status_int & (1 << i):
                    errors.append(f"Bit {i}: {error_desc}")
        except (ValueError, TypeError):
            pass

        return errors

    def _decode_psm_errors(self, status_hex: str) -> List[str]:
        """
        Decode PSM status hex to list of error descriptions.

        Args:
            status_hex: Hexadecimal status string

        Returns:
            List of active error descriptions
        """
        errors = []
        if not status_hex:
            return errors

        try:
            status_int = int(status_hex, 16)
            for i, error_desc in enumerate(PSM_ERRORS):
                if status_int & (1 << i):
                    errors.append(f"Bit {i}: {error_desc}")
        except (ValueError, TypeError):
            pass

        return errors

    def _decode_psm_notes(self, note_hex: str) -> List[str]:
        """
        Decode PSM note hex to list of note descriptions.

        Args:
            note_hex: Hexadecimal note string

        Returns:
            List of active note descriptions
        """
        NOTE_DESCRIPTIONS = [
            "Autofill active",
            "Drain active",
            "Liquid low",
            "Liquid overfill",
            "Drain liquid low",
            "Drain liquid overfill",
            "Reserved"
        ]

        notes = []
        if not note_hex:
            return notes

        try:
            note_int = int(note_hex, 16)
            for i, desc in enumerate(NOTE_DESCRIPTIONS):
                if note_int & (1 << i):
                    notes.append(f"Bit {i}: {desc}")
        except (ValueError, TypeError):
            pass

        return notes

    def _hex_to_binary(self, hex_str: str, bit_count: int) -> str:
        """
        Convert hex string to binary string with specified bit count.

        Args:
            hex_str: Hexadecimal string
            bit_count: Number of bits to show

        Returns:
            Binary string representation
        """
        if not hex_str:
            return ""

        try:
            value = int(hex_str, 16)
            return bin(value)[2:].zfill(bit_count)
        except (ValueError, TypeError):
            return ""

    def _format_timestamp(self, timestamp) -> str:
        """
        Format a Unix timestamp to ISO format.

        Args:
            timestamp: Unix timestamp or None

        Returns:
            ISO format string or empty string
        """
        if timestamp is None:
            return ""

        try:
            return datetime.fromtimestamp(timestamp).isoformat()
        except Exception:
            return ""

    def _collect_recent_logs(self) -> Dict[str, Any]:
        """
        Collect recent entries from debug.log file.

        Returns:
            Dictionary with log file info and recent entries
        """
        from config import script_path

        log_path = os.path.join(script_path, 'debug.log')

        result = {
            "log_file": log_path,
            "lines_included": 0,
            "entries": []
        }

        if not os.path.exists(log_path):
            result["error"] = "Log file not found"
            return result

        try:
            # Read last N lines efficiently using deque
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                # Use deque to keep only the last N lines
                recent_lines = deque(f, maxlen=self.DEBUG_LOG_LINES)

            result["entries"] = list(recent_lines)
            result["lines_included"] = len(result["entries"])

            # Get file size for reference
            file_size = os.path.getsize(log_path)
            result["file_size_bytes"] = file_size
            result["file_size_mb"] = round(file_size / (1024 * 1024), 2)

        except Exception as e:
            result["error"] = f"Failed to read log file: {str(e)}"

        return result
