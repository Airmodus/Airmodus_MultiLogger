"""
PSM .dat File Reader

Utility functions for parsing MultiLogger .dat files to extract historical scan data.
Supports both PSM 1.0 (Retrofit) and PSM 2.0 file formats.
"""

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from config import PSM, PSM2


def find_todays_psm_file(
    file_path: str,
    device_type: int,
    serial_number: str = "",
    device_nickname: str = "",
    file_tag: str = ""
) -> Optional[str]:
    """
    Find today's .dat file for a PSM device.

    Args:
        file_path: Directory where .dat files are saved
        device_type: PSM (2) or PSM2 (7)
        serial_number: Device serial number (optional)
        device_nickname: Device nickname (optional)
        file_tag: File tag from settings (optional)

    Returns:
        Path to the most recent matching .dat file, or None if not found
    """
    # Get today's date
    today = datetime.now().strftime("%Y%m%d")

    # Determine device type name
    device_type_names = {
        PSM: "PSM Retrofit",
        PSM2: "PSM 2.0"
    }
    device_type_name = device_type_names.get(device_type, "PSM Retrofit")

    # Build filename pattern with wildcards
    # Format: YYYYMMDD_HHMMSS[_SerialNumber]_DeviceType[_DeviceNickname][_FileTag].dat
    pattern_parts = [today, "*"]  # wildcard for timestamp

    if serial_number:
        pattern_parts.append(f"*{serial_number}*")

    pattern_parts.append(device_type_name)

    if device_nickname:
        pattern_parts.append(f"*{device_nickname}*")

    if file_tag:
        pattern_parts.append(f"*{file_tag}*")

    # Create glob pattern
    pattern = os.path.join(file_path, "_".join(pattern_parts) + ".dat")

    # Find matching files
    matching_files = glob.glob(pattern)

    if not matching_files:
        # Try without optional fields
        simple_pattern = os.path.join(file_path, f"{today}_*{device_type_name}*.dat")
        matching_files = glob.glob(simple_pattern)

    if matching_files:
        # Return most recent file (by modification time)
        return max(matching_files, key=os.path.getmtime)

    return None


def read_psm_dat_file(filepath: str, device_type: int) -> pd.DataFrame:
    """
    Read PSM .dat file and extract relevant columns.

    Args:
        filepath: Path to .dat file
        device_type: PSM (2) or PSM2 (7)

    Returns:
        DataFrame with columns: timestamp, satflow, scan_status, concentration

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    try:
        # Read CSV file
        df = pd.read_csv(filepath)

        # Validate minimum columns
        if len(df.columns) < 20:
            raise ValueError(f"Invalid file format: expected at least 20 columns, got {len(df.columns)}")

        # Column indices differ between PSM 1.0 and PSM 2.0
        is_psm2 = (device_type == PSM2)

        # Extract column names (handle potential variations)
        timestamp_col = df.columns[0]
        satflow_col = df.columns[3]  # Saturator flow rate (lpm)
        scan_status_col = df.columns[16 if is_psm2 else 15]  # Scan status
        concentration_col = df.columns[19 if is_psm2 else 18]  # CPC concentration (1/cm3)

        # Create result dataframe with standardized column names
        result = pd.DataFrame({
            'timestamp': df[timestamp_col],
            'satflow': pd.to_numeric(df[satflow_col], errors='coerce'),
            'scan_status': df[scan_status_col].astype(str),
            'concentration': pd.to_numeric(df[concentration_col], errors='coerce')
        })

        # Parse timestamps
        result['timestamp'] = pd.to_datetime(result['timestamp'], format='%Y.%m.%d %H:%M:%S', errors='coerce')

        # Remove rows with invalid timestamps
        result = result.dropna(subset=['timestamp'])

        return result

    except Exception as e:
        raise ValueError(f"Error reading .dat file: {e}")


def detect_scans_from_dat(df: pd.DataFrame) -> List[Dict[str, np.ndarray]]:
    """
    Detect and extract individual scans from .dat file data.

    Scans are detected by transitions in scan_status field:
    - Scan starts: transition from "9" to ["0", "1", "2"]
    - Scan continues: scan_status in ["0", "1", "2"]
    - Scan ends: transition back to "9" or status change

    Args:
        df: DataFrame with columns: timestamp, satflow, scan_status, concentration

    Returns:
        List of scan dicts with keys:
        - 'times': np.ndarray of pandas.Timestamp objects
        - 'satflows': np.ndarray of float values (lpm)
        - 'concentrations': np.ndarray of float values (1/cm3)
    """
    scans = []
    current_scan = None
    prev_status = "9"

    for idx, row in df.iterrows():
        scan_status = str(row['scan_status']).strip()

        # Detect scan transition
        is_scan_active = scan_status in ["0", "1", "2"]
        status_changed = scan_status != prev_status

        # Start new scan on transition to active scan state
        if is_scan_active and status_changed:
            # Finalize previous scan if it exists and has enough data
            if current_scan is not None and len(current_scan['satflows']) >= 3:
                scans.append({
                    'times': np.array(current_scan['times']),
                    'satflows': np.array(current_scan['satflows']),
                    'concentrations': np.array(current_scan['concentrations'])
                })

            # Initialize new scan
            current_scan = {
                'times': [],
                'satflows': [],
                'concentrations': []
            }

        # Accumulate data during active scan
        if current_scan is not None and is_scan_active:
            # Only add valid data (not NaN)
            if not pd.isna(row['satflow']) and not pd.isna(row['concentration']):
                current_scan['times'].append(row['timestamp'])
                current_scan['satflows'].append(row['satflow'])
                current_scan['concentrations'].append(row['concentration'])

        prev_status = scan_status

    # Finalize last scan
    if current_scan is not None and len(current_scan['satflows']) >= 3:
        scans.append({
            'times': np.array(current_scan['times']),
            'satflows': np.array(current_scan['satflows']),
            'concentrations': np.array(current_scan['concentrations'])
        })

    return scans


def load_historical_scans(
    file_path: str,
    device_type: int,
    serial_number: str = "",
    device_nickname: str = "",
    file_tag: str = ""
) -> Tuple[Optional[str], List[Dict[str, np.ndarray]]]:
    """
    High-level function to find, read, and parse today's PSM .dat file.

    Args:
        file_path: Directory where .dat files are saved
        device_type: PSM (2) or PSM2 (7)
        serial_number: Device serial number (optional)
        device_nickname: Device nickname (optional)
        file_tag: File tag from settings (optional)

    Returns:
        Tuple of (filepath, scans):
        - filepath: Path to the loaded file (or None if not found)
        - scans: List of scan dicts with 'times', 'satflows', 'concentrations'

    Raises:
        Exception: If file reading or parsing fails
    """
    # Find today's file
    filepath = find_todays_psm_file(
        file_path=file_path,
        device_type=device_type,
        serial_number=serial_number,
        device_nickname=device_nickname,
        file_tag=file_tag
    )

    if filepath is None:
        return None, []

    # Read and parse file
    df = read_psm_dat_file(filepath, device_type)
    scans = detect_scans_from_dat(df)

    return filepath, scans


def get_scan_time_range(scans: List[Dict[str, np.ndarray]]) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """
    Get the time range covered by a list of scans.

    Args:
        scans: List of scan dicts with 'times' arrays

    Returns:
        Tuple of (start_time, end_time) or (None, None) if no scans
    """
    if not scans:
        return None, None

    all_times = []
    for scan in scans:
        if len(scan['times']) > 0:
            all_times.extend(scan['times'])

    if not all_times:
        return None, None

    return min(all_times), max(all_times)
