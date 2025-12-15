"""
PSM .dat File Reader

Utility functions for parsing MultiLogger .dat files to extract historical scan data.
Supports both PSM 1.0 (Retrofit) and PSM 2.0 file formats.
Auto-detects format from file header (presence of "Vacuum flow" column).
"""

import os
import glob
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional, List, Dict, Tuple


def _detect_psm2_from_file(filepath: str) -> bool:
    """
    Auto-detect if a .dat file is PSM 2.0 format by checking header for Vacuum flow column.

    Returns True if PSM 2.0 (has Vacuum flow column), False if Retrofit.
    """
    try:
        with open(filepath, 'r', encoding='UTF-8') as f:
            header = f.readline()
            return 'Vacuum flow' in header
    except Exception:
        return False  # Default to Retrofit on error


def find_psm_files_last_24h(file_path: str, hours: int = 24) -> List[str]:
    """
    Find ALL PSM .dat files from the specified time window.
    Handles multiple files per day (e.g., from program restarts).

    Args:
        file_path: Directory where .dat files are saved
        hours: Number of hours to look back (default 24, max 48 covers 3 days)

    Returns:
        List of paths to matching .dat files, sorted chronologically by filename
    """
    from datetime import timedelta

    # Get dates to search based on hours parameter
    now = datetime.now()
    dates_to_search = set()

    # Calculate how many days back we need to search
    days_back = (hours // 24) + 1  # +1 to include partial days
    for i in range(days_back + 1):
        date_str = (now - timedelta(days=i)).strftime("%Y%m%d")
        dates_to_search.add(date_str)

    # Search for all PSM filename variants
    device_type_names = ["PSM", "PSM2", "PSM Retrofit", "PSM 2.0"]
    all_matching_files = set()

    for date_str in dates_to_search:
        for device_type_name in device_type_names:
            pattern = os.path.join(file_path, f"{date_str}_*{device_type_name}*.dat")
            all_matching_files.update(glob.glob(pattern))

    # Sort by filename (chronological) and filter out tiny files
    return sorted([f for f in all_matching_files if os.path.getsize(f) > 500])


def read_psm_dat_file(filepath: str) -> pd.DataFrame:
    """
    Read PSM .dat file and extract relevant columns.
    Auto-detects PSM version (2.0 vs Retrofit) from file header.

    Args:
        filepath: Path to .dat file

    Returns:
        DataFrame with columns: timestamp, satflow, scan_status, concentration_psm

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    try:
        # Auto-detect PSM version from header
        is_psm2 = _detect_psm2_from_file(filepath)

        # Read CSV file
        df = pd.read_csv(filepath)

        # Validate minimum columns
        if len(df.columns) < 16:
            raise ValueError(f"Invalid file format: expected at least 16 columns, got {len(df.columns)}")

        timestamp_col = df.columns[0]
        concentration_psm_col = df.columns[1]  # Already dilution + poly corrected
        satflow_col = df.columns[3]
        scan_status_col = df.columns[15]

        result = pd.DataFrame({
            'timestamp': df[timestamp_col],
            'satflow': pd.to_numeric(df[satflow_col], errors='coerce'),
            'scan_status': df[scan_status_col].astype(str),
            'concentration_psm': pd.to_numeric(df[concentration_psm_col], errors='coerce')
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

    Scan status values:
    - 0 = bottom wait (pause at bottom of scan)
    - 1 = up scan (saturator flow increasing)
    - 2 = top wait (pause at top of scan)
    - 3 = down scan (saturator flow decreasing)
    - 4 = don't log (skip entirely)
    - 9 = idle (not scanning)

    Two scans per cycle:
    - Up scan: status 1 + status 2 (top wait)
    - Down scan: status 3 + status 0 (bottom wait)

    Args:
        df: DataFrame with columns: timestamp, satflow, scan_status, concentration_psm

    Returns:
        List of scan dicts with keys:
        - 'times': np.ndarray of pandas.Timestamp objects
        - 'satflows': np.ndarray of float values (lpm)
        - 'concentrations_psm': np.ndarray of corrected concentration values (1/cm3)
    """
    scans = []
    current_scan = None
    prev_status = None

    for idx, row in df.iterrows():
        scan_status_raw = str(row['scan_status']).strip()

        # Normalize scan status - handle both "1" and "1.0" formats
        try:
            scan_status = str(int(float(scan_status_raw)))
        except (ValueError, TypeError):
            scan_status = scan_status_raw  # Keep as-is if not a number (e.g., "nan")

        # Skip status 4 entirely (don't log)
        if scan_status == "4":
            prev_status = scan_status
            continue

        # Detect scan start transitions
        # Up scan starts when transitioning TO status "1"
        if scan_status == "1" and prev_status != "1":
            # Finalize previous scan if exists and has enough data
            if current_scan is not None and len(current_scan['satflows']) >= 3:
                scans.append({
                    'times': np.array(current_scan['times']),
                    'satflows': np.array(current_scan['satflows']),
                    'concentrations_psm': np.array(current_scan['concentrations_psm'])
                })
            # Start new UP scan
            current_scan = {'times': [], 'satflows': [], 'concentrations_psm': [], 'type': 'up'}

        # Down scan starts when transitioning TO status "3"
        elif scan_status == "3" and prev_status != "3":
            # Finalize previous scan if exists and has enough data
            if current_scan is not None and len(current_scan['satflows']) >= 3:
                scans.append({
                    'times': np.array(current_scan['times']),
                    'satflows': np.array(current_scan['satflows']),
                    'concentrations_psm': np.array(current_scan['concentrations_psm'])
                })
            # Start new DOWN scan
            current_scan = {'times': [], 'satflows': [], 'concentrations_psm': [], 'type': 'down'}

        # Accumulate data during scan
        # Up scan: include status 1 and 2 (top wait)
        # Down scan: include status 3 and 0 (bottom wait)
        if current_scan is not None:
            include_point = False
            if current_scan['type'] == 'up' and scan_status in ["1", "2"]:
                include_point = True
            elif current_scan['type'] == 'down' and scan_status in ["3", "0"]:
                include_point = True

            if include_point and not pd.isna(row['satflow']) and not pd.isna(row['concentration_psm']):
                current_scan['times'].append(row['timestamp'])
                current_scan['satflows'].append(row['satflow'])
                current_scan['concentrations_psm'].append(row['concentration_psm'])

        prev_status = scan_status

    # Finalize last scan
    if current_scan is not None and len(current_scan['satflows']) >= 3:
        scans.append({
            'times': np.array(current_scan['times']),
            'satflows': np.array(current_scan['satflows']),
            'concentrations_psm': np.array(current_scan['concentrations_psm'])
        })

    return scans


def load_historical_scans(
    file_path: str,
    serial_number: str = "",
    device_nickname: str = "",
    file_tag: str = "",
    hours: int = 24
) -> Tuple[Optional[List[str]], List[Dict[str, np.ndarray]]]:
    """
    Load and merge scans from ALL PSM .dat files in the specified time window.
    Handles multiple files per day and merges them intelligently.

    For overlapping timestamps, prefers data from the file with the longest
    continuous data range.

    Args:
        file_path: Directory where .dat files are saved
        serial_number: Device serial number (unused, kept for compatibility)
        device_nickname: Device nickname (unused, kept for compatibility)
        file_tag: File tag from settings (unused, kept for compatibility)
        hours: Number of hours to look back (default 24)

    Returns:
        Tuple of (filepaths, scans):
        - filepaths: List of loaded file paths (or None if none found)
        - scans: Merged list of scan dicts with 'times', 'satflows', 'concentrations'
    """
    # Find all files from the specified time window
    filepaths = find_psm_files_last_24h(file_path, hours=hours)

    if not filepaths:
        return None, []

    # Read scans from each file along with file's data range info
    file_scans = []  # List of (filepath, scans, row_count)
    for fp in filepaths:
        try:
            df = read_psm_dat_file(fp)
            scans = detect_scans_from_dat(df)
            if scans:
                file_scans.append((fp, scans, len(df)))
        except Exception as e:
            logging.error(f"Error reading {fp}: {e}")
            continue

    if not file_scans:
        return filepaths, []

    # Merge scans from all files
    # Strategy: for each time period, use scans from file with most data (longest continuous range)
    # Sort file_scans by row count (descending) so files with more data take priority
    file_scans.sort(key=lambda x: x[2], reverse=True)

    merged_scans = []
    used_times = set()  # Track scan start times we've already used

    for fp, scans, _ in file_scans:
        for scan in scans:
            if len(scan['times']) == 0:
                continue
            # Use first timestamp as scan identifier (rounded to minute for fuzzy matching)
            scan_time = scan['times'][0]
            if hasattr(scan_time, 'floor'):
                time_key = scan_time.floor('min')  # Round to minute
            else:
                time_key = pd.Timestamp(scan_time).floor('min')

            # Only add if we haven't seen this time period from a better file
            if time_key not in used_times:
                # Add source file info to scan
                scan['source_file'] = os.path.basename(fp)
                merged_scans.append(scan)
                used_times.add(time_key)

    # Sort merged scans by time
    merged_scans.sort(key=lambda s: s['times'][0] if len(s['times']) > 0 else pd.Timestamp.min)

    return filepaths, merged_scans


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
