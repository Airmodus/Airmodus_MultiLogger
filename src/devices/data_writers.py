"""
Concrete implementations of BaseDataWriter for each device type.

Each device has its own DataWriter class that defines how its data
should be written to files, including headers, file types, and
special cases like 10Hz logging or connected device handling.
"""

import os
import logging
import numpy as np
import pandas as pd
from config import CPC, PSM, version_number, osx_mode
from devices.base_data_writer import BaseDataWriter


class CPCDataWriter(BaseDataWriter):
    """Data writer for Airmodus CPC devices."""

    def get_file_types(self):
        """CPC writes both .dat and .par files."""
        return ['dat', 'par']

    def get_dat_header(self):
        """Return CPC .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Concentration (#/cc),Dead time (µs),Number of pulses,Saturator T (C),Condenser T (C),Optics T (C),Cabin T (C),Inlet P (kPa),Critical orifice P (kPa),Nozzle P (kPa),Cabin P (kPa),Liquid level,Pulse ratio,Total CPC errors,System status error'

    def get_par_header(self):
        """Return CPC .par file header."""
        return 'YYYY.MM.DD hh:mm:ss,Averaging time (s),Nominal flow rate (lpm),Flow rate (lpm),Saturator T setpoint (C),Condenser T setpoint (C),Optics T setpoint (C),Autofill,OPC counter threshold voltage (mV),OPC counter threshold 2 voltage (mV),Water removal,Dead time correction,Drain,K-factor,Tau,Command input'

    def should_write_par(self, data_holder):
        """Check if .par file should be written."""
        dev_id = self.device.dev_id

        # Check device's par_updates flag
        if data_holder.par_updates.get(dev_id, 0) == 1:
            return True

        # Check if device has latest_command
        if hasattr(self.device, 'latest_command') and self.device.latest_command is not None:
            return True

        return False

    def get_par_data(self, data_holder, timestamp_str):
        """Return CPC settings data for .par file."""
        dev_id = self.device.dev_id
        settings = self.device.settings

        if not settings:
            return None

        # Get settings array
        settings_array = settings.to_array()
        data_str = ','.join(str(val) for val in settings_array)

        # Add command if present
        if self.device.latest_command is not None:
            data_str += ',' + self.device.latest_command
            self.device.latest_command = None

        return data_str

    def has_special_files(self):
        """Check if 10Hz logging is enabled."""
        return self.device.device_config.extra_params.get('10_hz', False)

    def write_special_files(self, file_path, timestamp_str, filenames_dict):
        """Write 10Hz data file for CPC."""
        dev_id = self.device.dev_id

        # Check if device has ten_hz_data attribute
        if not hasattr(self.device, 'ten_hz_data'):
            return

        # Get filename from dict
        if dev_id not in filenames_dict:
            return

        filename = file_path + filenames_dict[dev_id]

        # Write 10Hz data
        with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
            file.write("\n")
            file.write(timestamp_str + ',')
            write_data = ','.join(str(val) for val in self.device.ten_hz_data)
            file.write(write_data)


class PSMDataWriter(BaseDataWriter):
    """Data writer for PSM and PSM 2.0 devices."""

    def get_file_types(self):
        """PSM writes both .dat and .par files."""
        return ['dat', 'par']

    def get_dat_header(self):
        """Return PSM .dat file header (different for PSM 2.0 vs Retrofit)."""
        if self.device.is_psm2:
            # PSM 2.0 includes vacuum flow
            return 'YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),Scan status,Vacuum flow (lpm),PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)'
        else:
            # Retrofit
            return 'YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),Scan status,PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)'

    def get_par_header(self):
        """Return PSM .par file header (different for PSM 2.0 vs Retrofit)."""
        if self.device.is_psm2:
            # PSM 2.0 has no CO flow
            return 'YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),amp,cen,sig,slope,intercept,modeInUse,CPC IDN,CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input'
        else:
            # Retrofit includes CO flow
            return 'YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),CO flow rate (lpm),amp,cen,sig,slope,intercept,modeInUse,CPC IDN,CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input'

    def should_write_par(self, data_holder):
        """
        Check if .par file should be written.

        PSM writes .par when:
        1. par_updates flag is set for this device
        2. Device has a latest_command
        3. Connected CPC parameter changed
        4. Connected CPC has par_updates flag set
        """
        dev_id = self.device.dev_id

        # Check device's par_updates flag
        if data_holder.par_updates.get(dev_id, 0) == 1:
            return True

        # Check if device has latest_command
        if hasattr(self.device, 'latest_command') and self.device.latest_command is not None:
            return True

        # Check connected CPC changes
        if hasattr(self.device, 'cpc_changed') and self.device.cpc_changed:
            return True

        # Check connected CPC par_updates
        cpc_id = self.device.device_config.extra_params.get('connected_cpc', 'None')
        if cpc_id != 'None':
            # Convert to int for lookup (JSON stores as string)
            try:
                cpc_id_int = int(cpc_id)
            except (ValueError, TypeError):
                cpc_id_int = None
            if cpc_id_int in data_holder.par_updates and data_holder.par_updates[cpc_id_int] == 1:
                return True

        return False

    def get_par_data(self, data_holder, timestamp_str):
        """Return PSM settings data for .par file."""
        dev_id = self.device.dev_id
        settings = self.device.settings

        if not settings:
            return None

        # Get PSM settings array
        settings_array = settings.to_array()
        data_str = ','.join(str(val) for val in settings_array)

        # Add connected CPC settings if applicable
        cpc_id = self.device.device_config.extra_params.get('connected_cpc', 'None')
        if cpc_id != 'None':
            # Convert to int for lookup (JSON stores as string)
            try:
                cpc_id_int = int(cpc_id)
            except (ValueError, TypeError):
                cpc_id_int = None
            # Find CPC device widget in device_widgets
            cpc_widget = data_holder.device_widgets.get(cpc_id_int)

            # If CPC widget exists and is Airmodus CPC, write settings
            if cpc_widget and cpc_widget.device_config.device_type == CPC:
                cpc_idn = cpc_widget.device_config.serial_number
                cpc_settings = data_holder.get_device_settings(cpc_id_int)

                if cpc_settings:
                    connected_cpc_settings = [
                        cpc_idn,  # CPC serial number (IDN)
                        cpc_settings.autofill,
                        cpc_settings.drain,
                        cpc_settings.water_removal,
                        cpc_settings.saturator_temp,
                        cpc_settings.condenser_temp,
                        cpc_settings.optics_temp,  # optics temp
                        cpc_settings.measured_cpc_flow,
                        cpc_settings.averaging_time
                    ]
                    data_str += ',' + ','.join(str(val) for val in connected_cpc_settings)
                else:
                    data_str += ',nan,nan,nan,nan,nan,nan,nan,nan,nan'
            else:
                # CPC not connected or not Airmodus CPC
                data_str += ',nan,nan,nan,nan,nan,nan,nan,nan,nan'
        else:
            # No connected CPC selected
            data_str += ',nan,nan,nan,nan,nan,nan,nan,nan,nan'

        # Add command if present
        if self.device.latest_command is not None:
            data_str += ',' + self.device.latest_command
            self.device.latest_command = None

        # Reset cpc_changed flag if it exists
        if hasattr(self.device, 'cpc_changed'):
            self.device.cpc_changed = False

        return data_str

    # ========== Inversion Data Save Methods ==========

    def __init__(self, device_widget):
        """Initialize PSMDataWriter with inversion file tracking."""
        super().__init__(device_widget)
        self._current_inversion_file = None
        self._current_inversion_date = None

    def write_inversion_scan(self, file_path, scan_data, config):
        """
        Write a single inversion scan to CSV file.

        Creates new file with header on first scan or date change (if daily files enabled).
        Appends subsequent scans to existing file.

        Args:
            file_path: Directory path where files are saved
            scan_data: Dict with 'timestamp', 'dN_dlogDp', 'bin_limits', 'calibration_filename'
            config: AppConfig with data_settings for file naming options
        """
        try:
            # Extract data
            timestamp = scan_data['timestamp']
            dN_dlogDp = scan_data['dN_dlogDp']
            bin_limits = scan_data['bin_limits']
            calibration_filename = scan_data['calibration_filename']

            # Determine if we need a new file
            need_new_file = False
            scan_date = pd.Timestamp(timestamp).date()

            if self._current_inversion_file is None:
                need_new_file = True
            elif config.data_settings.generate_daily_files:
                if self._current_inversion_date != scan_date:
                    need_new_file = True

            if need_new_file:
                self._current_inversion_file = self._create_inversion_file(
                    file_path, timestamp, calibration_filename, bin_limits, config
                )
                self._current_inversion_date = scan_date

            # Append data row
            self._append_inversion_row(timestamp, dN_dlogDp, bin_limits)

        except Exception as e:
            logging.error(f"Failed to write inversion scan: {e}")
            # Reset file tracking to force new file on next scan
            self._current_inversion_file = None

    def _create_inversion_file(self, file_path, timestamp, calibration_filename, bin_limits, config):
        """
        Create new inversion CSV file with metadata and column headers.

        Returns:
            Full path to created file
        """
        # Generate filename
        ts = pd.Timestamp(timestamp)
        timestamp_str = ts.strftime("%Y%m%d_%H%M%S")

        serial_number = self.device.device_config.serial_number
        serial_suffix = f"_{serial_number}" if serial_number else ""

        device_type = "PSM2" if self.device.is_psm2 else "PSM"

        nickname = self.device.device_config.device_nickname
        nickname_suffix = f"_{nickname}" if nickname else ""

        file_tag = config.data_settings.file_tag
        tag_suffix = f"_{file_tag}" if file_tag else ""

        separator = '/' if osx_mode else '\\'
        filename = f"{timestamp_str}{serial_suffix}_{device_type}{nickname_suffix}{tag_suffix}_dNdlogDp.csv"
        full_path = file_path + separator + filename

        # Build column headers from bin limits (smallest to largest)
        # bin_limits is already in ascending order
        column_headers = ["Scan start time"]
        num_bins = len(bin_limits) - 1
        for i in range(num_bins):
            lower = round(bin_limits[i], 2)
            upper = round(bin_limits[i + 1], 2)
            column_headers.append(f"Bin {lower}-{upper} nm")

        # Last column for concentration above largest bin (empty for live scans)
        highest_dp = round(bin_limits[-1], 2)
        column_headers.append(f"Dp >{highest_dp} nm total number concentration")

        # Write file with metadata header
        with open(full_path, 'w', encoding='UTF-8', newline='\n') as f:
            # Row 1: Metadata
            f.write(f"Software version: {version_number} ; Calibration file: {calibration_filename}\n")
            # Row 2: Column headers
            f.write(','.join(column_headers))

        logging.info(f"Created inversion file: {full_path}")
        return full_path

    def _append_inversion_row(self, timestamp, dN_dlogDp, bin_limits):
        """Append a single data row to the inversion file."""
        if self._current_inversion_file is None:
            return

        # Format timestamp (ISO 8601)
        ts = pd.Timestamp(timestamp)
        timestamp_str = ts.strftime("%Y-%m-%dT%H:%M:%S")

        # Format dN/dlogDp values
        # dN_dlogDp is already ordered from smallest to largest bin
        formatted_values = [self._format_inversion_value(v) for v in dN_dlogDp]

        # Concentration above bins not tracked in live mode - use empty
        formatted_values.append("")

        # Build row
        row = [timestamp_str] + formatted_values

        with open(self._current_inversion_file, 'a', encoding='UTF-8', newline='\n') as f:
            f.write('\n')
            f.write(','.join(str(v) for v in row))

    def _format_inversion_value(self, value):
        """
        Format inversion value according to documentation rules:
        - Values >= 1: 2 decimal places
        - Values < 1: 2 significant figures
        - NaN/None: empty string
        """
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return ""

        if value >= 1:
            return f"{value:.2f}"
        elif value > 0:
            return f"{value:.2g}"
        else:
            return "0"

    def reset_inversion_file(self):
        """Reset inversion file tracking (called on path change or new session)."""
        self._current_inversion_file = None
        self._current_inversion_date = None


class ElectrometerDataWriter(BaseDataWriter):
    """Data writer for Electrometer devices."""

    def get_dat_header(self):
        """Return Electrometer .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Voltage 1 (V),Voltage 2 (V),Voltage 3 (V)'


class CO2DataWriter(BaseDataWriter):
    """Data writer for CO2 sensor devices."""

    def get_dat_header(self):
        """Return CO2 sensor .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,CO2 (ppm),T (C),RH (%)'


class RHTPDataWriter(BaseDataWriter):
    """Data writer for RHTP (Humidity, Temperature, Pressure) devices."""

    def get_dat_header(self):
        """Return RHTP .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,RH (%),T (C),P (Pa)'


class AFMDataWriter(BaseDataWriter):
    """Data writer for AFM (Air Flow Meter) devices."""

    def get_dat_header(self):
        """Return AFM .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Flow (lpm),Standard flow (slpm),RH (%),T (C),P (Pa)'


class EDiluterDataWriter(BaseDataWriter):
    """Data writer for eDiluter devices."""

    def get_dat_header(self):
        """Return eDiluter .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Status,P1,P2,T1,T2,T3,T4,T5,T6,DF1,DF2,DFTot'


class TSICPCDataWriter(BaseDataWriter):
    """Data writer for TSI CPC devices."""

    def get_dat_header(self):
        """Return TSI CPC .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Concentration (#/cc),Instrument errors (hex)'


class ExampleDataWriter(BaseDataWriter):
    """Data writer for example device."""

    def get_dat_header(self):
        """Return example device .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Random value (0-100)'


class DefaultDataWriter(BaseDataWriter):
    """Default data writer for unknown device types."""

    def get_dat_header(self):
        """Return generic .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,value1,value2,value3'
