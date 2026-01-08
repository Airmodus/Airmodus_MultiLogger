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


def find_cpc_10hz_files(file_path: str, hours: int = 24) -> Dict[str, List[str]]:
    """
    Find 10Hz CPC CSV files matching the time window.

    Args:
        file_path: Directory where CSV files are saved
        hours: Number of hours to look back

    Returns:
        Dict mapping CPC serial number (or 'default' if no serial) to list of file paths, sorted by time
    """
    from datetime import timedelta
    import re

    # Get dates to search based on hours parameter
    now = datetime.now()
    dates_to_search = set()

    days_back = (hours // 24) + 1
    for i in range(days_back + 1):
        date_str = (now - timedelta(days=i)).strftime("%Y%m%d")
        dates_to_search.add(date_str)

    # Search for 10Hz files: YYYYMMDD_*CPC*10hz*.csv
    all_matching_files = set()
    for date_str in dates_to_search:
        pattern = os.path.join(file_path, f"{date_str}_*CPC*10hz*.csv")
        all_matching_files.update(glob.glob(pattern))

    # Group files by CPC serial number
    # Filename formats:
    # - With serial: YYYYMMDD_HHMMSS_SERIAL_CPC_NICKNAME_10hz_FILETAG.csv
    # - Without serial: YYYYMMDD_HHMMSS_CPC_NICKNAME_10hz_FILETAG.csv
    serial_to_files: Dict[str, List[str]] = {}

    for filepath in all_matching_files:
        if os.path.getsize(filepath) < 100:
            continue

        filename = os.path.basename(filepath)

        # Try to extract serial number - it's between the timestamp and _CPC
        # Pattern with serial: YYYYMMDD_HHMMSS_SERIAL_CPC_...
        match = re.match(r'\d{8}_\d{6}_([^_]+)_CPC', filename)
        if match:
            potential_serial = match.group(1)
            # Check if this looks like a serial (not 'CPC' itself)
            if potential_serial.upper() != 'CPC':
                serial = potential_serial
            else:
                serial = 'default'
        else:
            # No serial found, use 'default'
            serial = 'default'

        if serial not in serial_to_files:
            serial_to_files[serial] = []
        serial_to_files[serial].append(filepath)

    # Sort each serial's files chronologically
    for serial in serial_to_files:
        serial_to_files[serial] = sorted(serial_to_files[serial])

    return serial_to_files


def read_cpc_10hz_csv(filepath: str) -> pd.DataFrame:
    """
    Read CPC 10Hz CSV file and return DataFrame with expanded timestamps.

    Each row in the CSV has 1-second timestamp + 10 concentration values.
    This expands to 10 rows with 100ms interval timestamps.

    Returns:
        DataFrame with columns:
        - timestamp: pd.Timestamp (100ms resolution)
        - concentration: float (raw CPC concentration)
    """
    try:
        df = pd.read_csv(filepath, encoding='UTF-8')

        if len(df.columns) < 11:
            logging.warning(f"10Hz file {filepath} has insufficient columns")
            return pd.DataFrame(columns=['timestamp', 'concentration'])

        timestamps = []
        concentrations = []

        timestamp_col = df.columns[0]

        for _, row in df.iterrows():
            try:
                # Parse base timestamp
                ts_str = str(row[timestamp_col]).strip()
                base_ts = pd.to_datetime(ts_str, format='%Y.%m.%d %H:%M:%S')

                # Expand to 10 rows with 100ms intervals
                # Index 0 = -900ms (oldest), Index 9 = 0ms (newest/current)
                for i in range(10):
                    conc_val = row.iloc[i + 1]  # Columns 1-10 are concentrations
                    try:
                        conc = float(conc_val)
                    except (ValueError, TypeError):
                        conc = np.nan

                    if not np.isnan(conc):
                        # Time offset: i=0 is -900ms, i=9 is 0ms
                        time_offset = pd.Timedelta(milliseconds=(i - 9) * 100)
                        timestamps.append(base_ts + time_offset)
                        concentrations.append(conc)

            except Exception as e:
                logging.debug(f"Error parsing row in 10Hz file: {e}")
                continue

        return pd.DataFrame({
            'timestamp': timestamps,
            'concentration': concentrations
        })

    except Exception as e:
        logging.error(f"Error reading 10Hz file {filepath}: {e}")
        return pd.DataFrame(columns=['timestamp', 'concentration'])


def calculate_scan_flows_exponential(
    timestamps: np.ndarray,
    scan_start_time: pd.Timestamp,
    scan_type: str,
    min_flow: float,
    max_flow: float,
    scan_time: float
) -> np.ndarray:
    """
    Calculate saturator flow values using exponential profile for timestamps.

    Matches the reference PSM Inversion Tool approach - calculates flow based on
    time since scan start. CPC transit delay is applied via concentration shift
    in _bin_and_invert_scan, not here.

    Args:
        timestamps: Array of pd.Timestamp values
        scan_start_time: When the scan started
        scan_type: 'up' or 'down'
        min_flow: Minimum saturator flow (lpm)
        max_flow: Maximum saturator flow (lpm)
        scan_time: Scan duration in seconds

    Returns:
        Array of saturator flow values
    """
    # Calculate scan power for exponential profile
    scan_power = (max_flow / min_flow) ** (1.0 / scan_time)

    flows = np.zeros(len(timestamps))

    for i, ts in enumerate(timestamps):
        # Time since scan started
        t = (ts - scan_start_time).total_seconds()
        if t < 0:
            t = 0

        if scan_type == 'up':
            flows[i] = min_flow * (scan_power ** t)
        else:  # down
            flows[i] = max_flow * ((1 / scan_power) ** t)

    # Clamp to valid range
    flows = np.clip(flows, min_flow, max_flow)

    return flows


def merge_10hz_data_into_scans(
    scans: List[Dict],
    ten_hz_df: pd.DataFrame,
    scan_timing_params: dict,
    cpc_transit_delay: float = 3.0
) -> List[Dict]:
    """
    Merge 10Hz concentration data into detected scans.

    For each scan, if sufficient 10Hz data exists within its time range,
    replaces the 1Hz data with 10Hz data and calculates flows using
    the exponential formula.

    Also extracts trailing concentration data (from after scan ends) for use
    in time-shifting, so the shift doesn't create NaN values at the end.

    Args:
        scans: List of scan dicts from detect_scans_from_dat()
        ten_hz_df: DataFrame with 'timestamp' and 'concentration' columns
        scan_timing_params: Dict with up_scan_time, down_scan_time, min_flow, max_flow
        cpc_transit_delay: CPC transit delay in seconds (for trailing data extraction)

    Returns:
        Enhanced scans list with 10Hz data where available
    """
    if ten_hz_df.empty or not scan_timing_params:
        return scans

    min_flow = scan_timing_params.get('min_flow')
    max_flow = scan_timing_params.get('max_flow')
    up_scan_time = scan_timing_params.get('up_scan_time', 110)
    down_scan_time = scan_timing_params.get('down_scan_time', 110)

    if min_flow is None or max_flow is None:
        return scans

    enhanced_scans = []

    for scan in scans:
        times = scan['times']
        if len(times) < 3:
            enhanced_scans.append(scan)
            continue

        scan_start = times[0]
        scan_end = times[-1]

        # Handle both Timestamp and datetime64
        if isinstance(scan_start, np.datetime64):
            scan_start = pd.Timestamp(scan_start)
        if isinstance(scan_end, np.datetime64):
            scan_end = pd.Timestamp(scan_end)

        # Find 10Hz data within scan time range
        mask = (ten_hz_df['timestamp'] >= scan_start) & (ten_hz_df['timestamp'] <= scan_end)
        scan_10hz = ten_hz_df[mask].copy()

        # Calculate expected number of 10Hz points
        scan_duration = (scan_end - scan_start).total_seconds()
        expected_points = scan_duration * 10  # 10 points per second

        # Use 10Hz data if we have sufficient coverage (>= 50%)
        if len(scan_10hz) >= expected_points * 0.5 and len(scan_10hz) >= 30:
            # Determine scan type from satflow direction in original data
            scan_type = scan.get('type', 'up')
            if scan_type not in ['up', 'down']:
                # Detect from flow direction
                satflows = scan['satflows']
                if len(satflows) >= 2:
                    scan_type = 'up' if satflows[-1] > satflows[0] else 'down'
                else:
                    scan_type = 'up'

            # Select appropriate scan time
            scan_time = up_scan_time if scan_type == 'up' else down_scan_time

            # Calculate flows using exponential formula
            timestamps_10hz = scan_10hz['timestamp'].values
            # Convert to pandas Timestamps if needed
            timestamps_10hz = pd.to_datetime(timestamps_10hz)

            flows_10hz = calculate_scan_flows_exponential(
                timestamps=timestamps_10hz,
                scan_start_time=scan_start,
                scan_type=scan_type,
                min_flow=min_flow,
                max_flow=max_flow,
                scan_time=scan_time
            )

            # Extract trailing concentration data (for time-shift)
            # Get concentration values from after scan ends, for cpc_transit_delay seconds
            trailing_end = scan_end + pd.Timedelta(seconds=cpc_transit_delay + 0.5)
            trailing_mask = (ten_hz_df['timestamp'] > scan_end) & (ten_hz_df['timestamp'] <= trailing_end)
            trailing_10hz = ten_hz_df[trailing_mask].copy()
            trailing_concs = trailing_10hz['concentration'].values.tolist() if len(trailing_10hz) > 0 else []

            # Create enhanced scan with 10Hz data
            enhanced_scan = {
                'times': timestamps_10hz,
                'satflows': flows_10hz,
                'concentrations_psm': scan_10hz['concentration'].values,
                'trailing_concentrations': trailing_concs,
                'type': scan_type,
                'is_10hz': True
            }
            enhanced_scans.append(enhanced_scan)
        else:
            # Keep original 1Hz scan
            scan['is_10hz'] = False
            enhanced_scans.append(scan)

    return enhanced_scans


def _calculate_concentration_psm(satflow: float, excess_flow: float, cpc_conc: float,
                                   is_psm2: bool, vacuum_flow: float = 0.0,
                                   cpc_flow: float = 1.0) -> float:
    """
    Calculate PSM concentration from raw CPC concentration.
    Used for backwards compatibility with older .dat files that don't have
    pre-calculated concentration_psm values.

    Args:
        satflow: Saturator flow rate (lpm)
        excess_flow: Excess flow rate (lpm)
        cpc_conc: Raw CPC concentration (#/cc)
        is_psm2: True if PSM 2.0, False if Retrofit
        vacuum_flow: Vacuum flow (lpm), only used for PSM 2.0
        cpc_flow: CPC flow rate (lpm), default 1.0

    Returns:
        Dilution and poly corrected concentration from PSM
    """
    if np.isnan(satflow) or np.isnan(cpc_conc) or cpc_conc == 0:
        return np.nan

    # Calculate polynomial correction factor from saturator flow
    if is_psm2:
        # PSM 2.0 polynomial coefficients
        pcor = np.array([0.12949491, -0.50587616, 0.57214191, 0.76108161])
    else:
        # Retrofit polynomial coefficients
        pcor = np.array([-0.0272052, 0.11394213, -0.08959011, -0.20675596, 0.24343024, 1.10531145])

    poly_correction = np.polyval(pcor, satflow)
    if poly_correction == 0:
        return np.nan

    # Calculate inlet flow and dilution correction factor
    if is_psm2:
        inlet_flow = cpc_flow + vacuum_flow - satflow - excess_flow
        if inlet_flow <= 0:
            return np.nan
        dilution_correction = (inlet_flow + 4 - excess_flow - satflow) / inlet_flow
    else:
        # Retrofit: simplified calculation
        inlet_flow = cpc_flow - satflow - excess_flow
        if inlet_flow <= 0:
            inlet_flow = 0.1  # Fallback to avoid division by zero
        dilution_correction = (inlet_flow + excess_flow + satflow) / inlet_flow

    # Calculate concentration from PSM
    return cpc_conc * dilution_correction / poly_correction


def read_psm_dat_file(filepath: str, progress_callback: Optional[callable] = None) -> pd.DataFrame:
    """
    Read PSM .dat file and extract relevant columns.
    Auto-detects PSM version (2.0 vs Retrofit) from file header.

    For older files where concentration_psm (column 1) is empty/NaN,
    calculates it on the fly from CPC concentration and flow values.

    Args:
        filepath: Path to .dat file
        progress_callback: Optional callback(current, total, message) for progress updates

    Returns:
        DataFrame with columns: timestamp, satflow, scan_status, concentration_psm

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    filename = os.path.basename(filepath)

    try:
        # Auto-detect PSM version from header
        is_psm2 = _detect_psm2_from_file(filepath)

        if progress_callback:
            progress_callback(0, 100, f"Reading {filename}...")

        # Read CSV file
        df = pd.read_csv(filepath)

        if progress_callback:
            progress_callback(30, 100, f"Processing {len(df)} rows...")

        # Validate minimum columns
        if len(df.columns) < 16:
            raise ValueError(f"Invalid file format: expected at least 16 columns, got {len(df.columns)}")

        timestamp_col = df.columns[0]
        concentration_psm_col = df.columns[1]  # Already dilution + poly corrected (may be empty in old files)
        satflow_col = df.columns[3]
        excess_flow_col = df.columns[4]
        scan_status_col = df.columns[15]

        # Get CPC concentration column index (differs between PSM 2.0 and Retrofit)
        # PSM 2.0 has Vacuum flow at column 16, shifting CPC concentration to column 19
        # Retrofit has CPC concentration at column 18
        cpc_conc_col_idx = 19 if is_psm2 else 18
        vacuum_flow_col_idx = 16 if is_psm2 else None

        # Extract base columns
        result = pd.DataFrame({
            'timestamp': df[timestamp_col],
            'satflow': pd.to_numeric(df[satflow_col], errors='coerce'),
            'scan_status': df[scan_status_col].astype(str),
            'concentration_psm': pd.to_numeric(df[concentration_psm_col], errors='coerce')
        })

        # Check if we need to calculate concentration_psm for rows where it's missing
        missing_conc_mask = result['concentration_psm'].isna()
        missing_count = missing_conc_mask.sum()

        if missing_count > 0 and len(df.columns) > cpc_conc_col_idx:
            if progress_callback:
                progress_callback(40, 100, f"Calculating {missing_count} concentrations...")

            # Read additional columns needed for calculation
            excess_flow = pd.to_numeric(df[excess_flow_col], errors='coerce')
            cpc_conc = pd.to_numeric(df.iloc[:, cpc_conc_col_idx], errors='coerce')

            vacuum_flow = pd.Series(0.0, index=df.index)
            if is_psm2 and vacuum_flow_col_idx and len(df.columns) > vacuum_flow_col_idx:
                vacuum_flow = pd.to_numeric(df.iloc[:, vacuum_flow_col_idx], errors='coerce')

            # Calculate concentration_psm for rows where it's missing
            missing_indices = result[missing_conc_mask].index.tolist()
            for i, idx in enumerate(missing_indices):
                calculated_conc = _calculate_concentration_psm(
                    satflow=result.loc[idx, 'satflow'],
                    excess_flow=excess_flow.loc[idx],
                    cpc_conc=cpc_conc.loc[idx],
                    is_psm2=is_psm2,
                    vacuum_flow=vacuum_flow.loc[idx] if is_psm2 else 0.0
                )
                result.loc[idx, 'concentration_psm'] = calculated_conc

                # Report progress every 500 rows
                if progress_callback and i % 500 == 0:
                    pct = 40 + int(50 * i / len(missing_indices))
                    progress_callback(pct, 100, f"Calculating row {i}/{missing_count}...")

        if progress_callback:
            progress_callback(90, 100, f"Parsing timestamps...")

        # Parse timestamps
        result['timestamp'] = pd.to_datetime(result['timestamp'], format='%Y.%m.%d %H:%M:%S', errors='coerce')

        # Remove rows with invalid timestamps
        result = result.dropna(subset=['timestamp'])

        if progress_callback:
            progress_callback(100, 100, f"Done: {len(result)} rows")

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
    hours: int = 24,
    progress_callback: Optional[callable] = None,
    connected_cpc_serial: Optional[str] = None,
    scan_timing_params: Optional[dict] = None,
    cpc_transit_delay: float = 3.0
) -> Tuple[Optional[List[str]], List[Dict[str, np.ndarray]]]:
    """
    Load and merge scans from ALL PSM .dat files in the specified time window.
    Handles multiple files per day and merges them intelligently.
    Optionally merges 10Hz CPC data for higher resolution.

    For overlapping timestamps, prefers data from the file with the longest
    continuous data range.

    Args:
        file_path: Directory where .dat files are saved
        serial_number: Device serial number (unused, kept for compatibility)
        device_nickname: Device nickname (unused, kept for compatibility)
        file_tag: File tag from settings (unused, kept for compatibility)
        hours: Number of hours to look back (default 24)
        progress_callback: Optional callback(current, total, message) for progress updates
        connected_cpc_serial: CPC serial number to match 10Hz files (optional)
        scan_timing_params: Dict with up_scan_time, down_scan_time, min_flow, max_flow (optional)
        cpc_transit_delay: CPC transit delay in seconds (default 3.0)

    Returns:
        Tuple of (filepaths, scans):
        - filepaths: List of loaded file paths (or None if none found)
        - scans: Merged list of scan dicts with 'times', 'satflows', 'concentrations_psm', 'is_10hz'
    """
    # Find all files from the specified time window
    if progress_callback:
        progress_callback(0, 0, "Finding data files...")

    filepaths = find_psm_files_last_24h(file_path, hours=hours)

    if not filepaths:
        return None, []

    if progress_callback:
        progress_callback(0, len(filepaths), f"Found {len(filepaths)} file(s)")

    # Read scans from each file along with file's data range info
    file_scans = []  # List of (filepath, scans, row_count)
    total_files = len(filepaths)
    for i, fp in enumerate(filepaths):
        try:
            filename = os.path.basename(fp)

            # Create a nested progress callback that includes file context
            def file_progress_callback(pct, total_pct, msg):
                if progress_callback:
                    # Show file X/Y and the detail message
                    progress_callback(i, total_files, f"[{i+1}/{total_files}] {msg}")

            file_progress_callback(0, 100, f"Reading {filename}...")

            df = read_psm_dat_file(fp, progress_callback=file_progress_callback)

            file_progress_callback(95, 100, f"Detecting scans...")
            scans = detect_scans_from_dat(df)
            if scans:
                file_scans.append((fp, scans, len(df)))
                file_progress_callback(100, 100, f"Found {len(scans)} scans")
        except Exception as e:
            logging.error(f"Error reading {fp}: {e}")
            continue

    if progress_callback:
        progress_callback(len(filepaths), len(filepaths), "Merging scans...")

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

    # Try to merge 10Hz data if CPC serial and timing params are provided
    if connected_cpc_serial and scan_timing_params and merged_scans:
        if progress_callback:
            progress_callback(len(filepaths), len(filepaths), "Looking for 10Hz data...")

        try:
            # Find 10Hz files for the connected CPC
            cpc_10hz_files = find_cpc_10hz_files(file_path, hours=hours)

            # Look for 10Hz files matching the CPC serial, or use 'default' if no serial match
            ten_hz_files = None
            if connected_cpc_serial and connected_cpc_serial in cpc_10hz_files:
                ten_hz_files = cpc_10hz_files[connected_cpc_serial]
            elif 'default' in cpc_10hz_files:
                # Use default (no serial) files if no specific serial match
                ten_hz_files = cpc_10hz_files['default']

            if ten_hz_files:

                if progress_callback:
                    progress_callback(len(filepaths), len(filepaths),
                                    f"Loading {len(ten_hz_files)} 10Hz file(s)...")

                # Read and combine all 10Hz files
                all_10hz_data = []
                for f in ten_hz_files:
                    df_10hz = read_cpc_10hz_csv(f)
                    if not df_10hz.empty:
                        all_10hz_data.append(df_10hz)

                if all_10hz_data:
                    combined_10hz = pd.concat(all_10hz_data, ignore_index=True)
                    combined_10hz = combined_10hz.sort_values('timestamp').reset_index(drop=True)

                    if progress_callback:
                        progress_callback(len(filepaths), len(filepaths),
                                        f"Merging {len(combined_10hz)} 10Hz points...")

                    # Merge 10Hz data into scans
                    merged_scans = merge_10hz_data_into_scans(
                        scans=merged_scans,
                        ten_hz_df=combined_10hz,
                        scan_timing_params=scan_timing_params,
                        cpc_transit_delay=cpc_transit_delay
                    )

                    # Count how many scans got 10Hz data
                    count_10hz = sum(1 for s in merged_scans if s.get('is_10hz', False))
                    if progress_callback:
                        progress_callback(len(filepaths), len(filepaths),
                                        f"Enhanced {count_10hz}/{len(merged_scans)} scans with 10Hz data")

        except Exception as e:
            logging.error(f"Error loading 10Hz data: {e}")
            # Continue with 1Hz data if 10Hz loading fails

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


# ============================================================================
# Inversion CSV File Functions
# ============================================================================

def find_inversion_csv_files(file_path: str, serial_number: str = None,
                              hours: int = 24) -> List[str]:
    """
    Find existing _dNdlogDp.csv files (pre-inverted scan data) in directory.

    Args:
        file_path: Directory where CSV files are saved
        serial_number: Optional serial number to filter by
        hours: Number of hours to look back (default 24)

    Returns:
        List of paths to matching CSV files, sorted chronologically by filename
    """
    from datetime import timedelta

    if not file_path or not os.path.isdir(file_path):
        return []

    # Get dates to search based on hours parameter
    now = datetime.now()
    dates_to_search = set()

    # Calculate how many days back we need to search
    days_back = (hours // 24) + 1
    for i in range(days_back + 1):
        date_str = (now - timedelta(days=i)).strftime("%Y%m%d")
        dates_to_search.add(date_str)

    # Search for *_dNdlogDp.csv files
    all_matching_files = []

    for date_str in dates_to_search:
        # Pattern: YYYYMMDD_*_dNdlogDp.csv
        if serial_number:
            pattern = os.path.join(file_path, f"{date_str}_*{serial_number}*_dNdlogDp.csv")
        else:
            pattern = os.path.join(file_path, f"{date_str}_*_dNdlogDp.csv")
        all_matching_files.extend(glob.glob(pattern))

    # Don't filter by file creation timestamp - the timestamp in the filename
    # is when the file was created (typically at midnight), not when data ends.
    # Files from relevant dates may contain data within the time window.
    # Actual time filtering happens when loading individual scans from the CSV.
    # Just return all files from relevant dates, sorted chronologically.
    return sorted(all_matching_files)


def load_scans_from_inversion_csv(csv_path: str, expected_bin_limits: np.ndarray = None) -> Tuple[Optional[List[Dict]], bool]:
    """
    Load pre-inverted scans from _dNdlogDp.csv file.

    Args:
        csv_path: Path to the CSV file
        expected_bin_limits: Current calibration bin limits for validation.
                            If provided, validates CSV bins match.

    Returns:
        Tuple of (scans_list, bin_limits_match):
        - scans_list: List of scan dicts with 'time', 'bin_centers', 'dN_dlogDp', 'source_file'
                     Returns None if bin mismatch or parse error
        - bin_limits_match: True if CSV bins match expected (or no expected provided),
                           False if mismatch
    """
    import re

    try:
        with open(csv_path, 'r', encoding='UTF-8') as f:
            lines = f.readlines()

        if len(lines) < 3:
            logging.warning(f"Inversion CSV too short: {csv_path}")
            return None, False

        # Row 1: Metadata - "Software version: X.X.X ; Calibration file: name.txt"
        # (optional parsing, not used currently)

        # Row 2: Column headers
        header_line = lines[1].strip()
        columns = header_line.split(',')

        # Parse bin limits from column headers: "Bin X-Y nm"
        bin_pattern = re.compile(r'Bin\s+([\d.]+)-([\d.]+)\s*nm')
        bin_limits = []
        bin_columns_start = 1  # Skip "Scan start time"
        bin_columns_end = len(columns)

        # Find where bin columns end (before "Dp >X nm..." column)
        for i, col in enumerate(columns):
            if col.startswith('Dp >'):
                bin_columns_end = i
                break

        # Extract bin limits from headers
        for i in range(bin_columns_start, bin_columns_end):
            match = bin_pattern.match(columns[i].strip())
            if match:
                lower = float(match.group(1))
                upper = float(match.group(2))
                if not bin_limits:
                    bin_limits.append(lower)
                bin_limits.append(upper)

        if not bin_limits:
            logging.warning(f"Could not parse bin limits from CSV header: {csv_path}")
            return None, False

        bin_limits = np.array(bin_limits)
        num_bins = len(bin_limits) - 1

        # Validate against expected bin limits if provided
        if expected_bin_limits is not None:
            if len(bin_limits) != len(expected_bin_limits):
                logging.info(f"CSV bin count mismatch: {len(bin_limits)} vs {len(expected_bin_limits)}")
                return None, False
            # Check if bin limits are close enough (within 0.01 nm tolerance)
            if not np.allclose(bin_limits, expected_bin_limits, atol=0.01):
                logging.info(f"CSV bin limits don't match current calibration")
                return None, False

        # Calculate bin centers (geometric mean of adjacent limits)
        bin_centers = np.sqrt(bin_limits[:-1] * bin_limits[1:])

        # Parse data rows
        scans = []
        for line_num, line in enumerate(lines[2:], start=3):
            line = line.strip()
            if not line:
                continue

            values = line.split(',')
            if len(values) < num_bins + 1:
                logging.warning(f"Skipping short row {line_num} in {csv_path}")
                continue

            # Parse timestamp
            try:
                timestamp = pd.Timestamp(values[0])
            except Exception as e:
                logging.warning(f"Could not parse timestamp in row {line_num}: {e}")
                continue

            # Parse dN/dlogDp values
            dN_dlogDp = np.zeros(num_bins)
            for i in range(num_bins):
                val_str = values[i + 1].strip()
                if val_str == '' or val_str.lower() == 'nan':
                    dN_dlogDp[i] = np.nan
                else:
                    try:
                        dN_dlogDp[i] = float(val_str)
                    except ValueError:
                        dN_dlogDp[i] = np.nan

            scans.append({
                'time': timestamp,
                'bin_centers': bin_centers.copy(),
                'dN_dlogDp': dN_dlogDp,
                'source_file': os.path.basename(csv_path)
            })

        logging.info(f"Loaded {len(scans)} scans from inversion CSV: {csv_path}")
        return scans, True

    except Exception as e:
        logging.error(f"Error loading inversion CSV {csv_path}: {e}")
        return None, False
