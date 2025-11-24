"""
File parser module for CPC and RHTP data files.

This module provides parsers for historical CPC and RHTP data files to enable
backfilling the ACTRIS database with historical measurements.
"""

import re
import csv
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class CPCFileParser:
    """Parser for CPC .dat and .par files."""

    def __init__(self):
        self.serial_number = None

    def extract_serial_from_filename(self, filepath: str) -> Optional[str]:
        """
        Extract CPC serial number from filename.

        Expected format: YYYYMMDD_HHMMSS_SERIALNUMBER_CPC.dat
        Example: 20250817_000000_2491701211_CPC.dat -> 2491701211

        Args:
            filepath: Path to the .dat or .par file

        Returns:
            Serial number as string, or None if not found
        """
        filename = Path(filepath).name
        # Pattern: date_time_serial_CPC.ext or just serial_CPC.ext
        # Try full format first
        pattern = r'\d{8}_\d{6}_(\d+)_CPC\.'
        match = re.search(pattern, filename)
        if match:
            return match.group(1)

        # Try simplified format: anything_serial_CPC.ext
        pattern2 = r'_(\d+)_CPC\.'
        match2 = re.search(pattern2, filename)
        if match2:
            return match2.group(1)

        return None

    def parse_dat_file(self, filepath: str) -> Tuple[List[Dict], str]:
        """
        Parse CPC .dat file containing 1Hz measurement data.

        Format: CSV with 16 columns
        Header: YYYY.MM.DD hh:mm:ss, Concentration (#/cc), Dead time (µs), ...

        Args:
            filepath: Path to the .dat file

        Returns:
            Tuple of (list of data records, serial number)
            Each record is a dict with timestamp and measurement values
        """
        records = []
        serial = self.extract_serial_from_filename(filepath)

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header row

            for row in reader:
                if len(row) < 16:
                    continue  # Skip malformed rows

                # Check if entire row is nan (except timestamp)
                if all(val.strip().lower() == 'nan' for val in row[1:]):
                    continue

                try:
                    # Parse timestamp: "YYYY.MM.DD hh:mm:ss"
                    timestamp_str = row[0].strip()
                    timestamp = datetime.strptime(timestamp_str, "%Y.%m.%d %H:%M:%S")
                    # Make timezone aware (assume UTC)
                    timestamp = timestamp.replace(tzinfo=timezone.utc)

                    # Parse numeric values, handle nan
                    def parse_float(val):
                        val = val.strip().lower()
                        if val == 'nan' or val == '':
                            return None
                        return float(val)

                    def parse_hex(val):
                        """Parse hex status like 0x0000"""
                        val = val.strip()
                        if val.lower() == 'nan' or val == '':
                            return None
                        return val

                    record = {
                        'timestamp': timestamp,
                        'concentration': parse_float(row[1]),
                        'dead_time': parse_float(row[2]),
                        'num_pulses': parse_float(row[3]),
                        'temp_saturator': parse_float(row[4]),
                        'temp_condenser': parse_float(row[5]),
                        'temp_optics': parse_float(row[6]),
                        'temp_cabin': parse_float(row[7]),
                        'pressure_inlet': parse_float(row[8]),
                        'pressure_critical_orifice': parse_float(row[9]),
                        'pressure_nozzle': parse_float(row[10]),
                        'pressure_cabin': parse_float(row[11]),
                        'liquid_level': parse_float(row[12]),
                        'pulse_ratio': parse_float(row[13]),
                        'total_errors': parse_float(row[14]),
                        'status_error': parse_hex(row[15])
                    }

                    records.append(record)

                except (ValueError, IndexError) as e:
                    # Skip rows that can't be parsed
                    continue

        return records, serial

    def parse_par_file(self, filepath: str) -> Dict[datetime, float]:
        """
        Parse CPC .par file containing settings changes.

        This file is sparse - only contains rows when settings change.
        We extract the flow rate values with their timestamps.

        Format: CSV with 16 columns
        Column 3 (index 3): Flow rate (lpm)

        Args:
            filepath: Path to the .par file

        Returns:
            Dict mapping timestamp -> flow_rate (lpm)
        """
        flow_map = {}

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header row

            for row in reader:
                if len(row) < 4:
                    continue  # Need at least timestamp and flow columns

                try:
                    # Parse timestamp
                    timestamp_str = row[0].strip()
                    timestamp = datetime.strptime(timestamp_str, "%Y.%m.%d %H:%M:%S")
                    timestamp = timestamp.replace(tzinfo=timezone.utc)

                    # Parse flow rate (column 3, index 3)
                    flow_str = row[3].strip().lower()
                    if flow_str != 'nan' and flow_str != '':
                        flow_rate = float(flow_str)
                        flow_map[timestamp] = flow_rate

                except (ValueError, IndexError):
                    continue

        return flow_map

    def merge_dat_par(self, dat_records: List[Dict], par_flow_map: Dict[datetime, float]) -> List[Dict]:
        """
        Merge CPC .dat measurements with .par flow settings.

        For each .dat record, find the most recent flow rate from .par file.
        If no .par data provided, flow_rate will be None.

        Args:
            dat_records: List of measurement records from .dat file
            par_flow_map: Dict of timestamp -> flow_rate from .par file

        Returns:
            List of records with 'flow_rate' field added
        """
        if not par_flow_map:
            # No .par file - set all flow rates to None
            for record in dat_records:
                record['flow_rate'] = None
            return dat_records

        # Sort par timestamps for efficient lookup
        par_timestamps = sorted(par_flow_map.keys())

        for record in dat_records:
            timestamp = record['timestamp']

            # Find most recent par timestamp before or equal to this timestamp
            flow_rate = None
            for par_ts in reversed(par_timestamps):
                if par_ts <= timestamp:
                    flow_rate = par_flow_map[par_ts]
                    break

            record['flow_rate'] = flow_rate

        return dat_records


class RHTPFileParser:
    """Parser for RHTP .dat files."""

    def parse_dat_file(self, filepath: str) -> List[Dict]:
        """
        Parse RHTP .dat file containing 1Hz environmental data.

        Format: CSV with 4 columns
        Header: YYYY.MM.DD hh:mm:ss, RH (%), T (C), P (Pa)

        Note: Pressure is in Pa in the file but needs to be converted to hPa for database.

        Args:
            filepath: Path to the .dat file

        Returns:
            List of data records with timestamp, humidity, temperature, pressure (hPa)
        """
        records = []

        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header row

            for row in reader:
                if len(row) < 4:
                    continue  # Skip malformed rows

                # Check if all values are nan
                if all(val.strip().lower() == 'nan' for val in row[1:]):
                    continue

                try:
                    # Parse timestamp
                    timestamp_str = row[0].strip()
                    timestamp = datetime.strptime(timestamp_str, "%Y.%m.%d %H:%M:%S")
                    timestamp = timestamp.replace(tzinfo=timezone.utc)

                    # Parse values
                    def parse_float(val):
                        val = val.strip().lower()
                        if val == 'nan' or val == '':
                            return None
                        return float(val)

                    humidity = parse_float(row[1])
                    temperature = parse_float(row[2])
                    pressure_pa = parse_float(row[3])

                    # Convert pressure from Pa to hPa
                    pressure_hpa = None
                    if pressure_pa is not None:
                        pressure_hpa = pressure_pa / 100.0

                    record = {
                        'timestamp': timestamp,
                        'humidity': humidity,
                        'temperature': temperature,
                        'pressure': pressure_hpa  # Converted to hPa
                    }

                    records.append(record)

                except (ValueError, IndexError):
                    continue

        return records


class TimestampMerger:
    """Utility for merging CPC and RHTP data by timestamp."""

    @staticmethod
    def merge_cpc_rhtp(cpc_records: List[Dict], rhtp_records: List[Dict],
                       tolerance_seconds: float = 1.0) -> List[Dict]:
        """
        Merge CPC and RHTP records by matching timestamps.

        For each CPC record, find the nearest RHTP record within tolerance window.
        If no match found, RHTP fields will be None.

        Args:
            cpc_records: List of CPC measurement records
            rhtp_records: List of RHTP measurement records
            tolerance_seconds: Maximum time difference for matching (default 1.0 second)

        Returns:
            List of merged records with both CPC and RHTP data
        """
        if not rhtp_records:
            # No RHTP data - set all RHTP fields to None
            for record in cpc_records:
                record['humidity_inlet'] = None
                record['temp_inlet'] = None
                record['pressure_inlet'] = None
            return cpc_records

        # Create a dict for fast RHTP lookup
        rhtp_dict = {r['timestamp']: r for r in rhtp_records}
        rhtp_timestamps = sorted(rhtp_dict.keys())

        # Use binary search for efficient matching
        import bisect

        for cpc_record in cpc_records:
            cpc_ts = cpc_record['timestamp']

            # Try exact match first (most common case for synchronized data)
            if cpc_ts in rhtp_dict:
                rhtp_data = rhtp_dict[cpc_ts]
                cpc_record['humidity_inlet'] = rhtp_data['humidity']
                cpc_record['temp_inlet'] = rhtp_data['temperature']
                cpc_record['pressure_inlet'] = rhtp_data['pressure']
            else:
                # Use binary search to find closest timestamp
                idx = bisect.bisect_left(rhtp_timestamps, cpc_ts)

                # Check nearby timestamps (before and after)
                candidates = []
                if idx > 0:
                    candidates.append(rhtp_timestamps[idx - 1])
                if idx < len(rhtp_timestamps):
                    candidates.append(rhtp_timestamps[idx])

                # Find best match within tolerance
                best_match = None
                min_diff = float('inf')

                for rhtp_ts in candidates:
                    diff = abs((rhtp_ts - cpc_ts).total_seconds())
                    if diff <= tolerance_seconds and diff < min_diff:
                        min_diff = diff
                        best_match = rhtp_ts

                if best_match:
                    rhtp_data = rhtp_dict[best_match]
                    cpc_record['humidity_inlet'] = rhtp_data['humidity']
                    cpc_record['temp_inlet'] = rhtp_data['temperature']
                    cpc_record['pressure_inlet'] = rhtp_data['pressure']
                else:
                    cpc_record['humidity_inlet'] = None
                    cpc_record['temp_inlet'] = None
                    cpc_record['pressure_inlet'] = None

        return cpc_records
