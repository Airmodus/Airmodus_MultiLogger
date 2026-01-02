# PSM Inversion Data Save Process Documentation

This document describes the complete process for saving inverted PSM (Particle Size Magnifier) scan data to CSV files. Use this as a reference for implementing the same save functionality in other programs.

---

## Overview

The save process exports inverted size distribution data (dN/dlogDp) to CSV files. It supports:
- Single file output
- Daily file splitting (one file per day)
- Two timestamp formats (ISO and Matlab)

---

## Output File Format

### Filename Conventions

**Single file from single input file:**
```
{original_filename}_dNdlogDp.csv
```
Example: `PSM_data_20230815_dNdlogDp.csv`

**Single file from multiple input files (same day):**
```
{YYYYMMDD}_dNdlogDp.csv
```
Example: `20230815_dNdlogDp.csv`

**Single file from multiple input files (multiple days):**
```
{YYYYMMDD}-{YYYYMMDD}_dNdlogDp.csv
```
Example: `20230815-20230820_dNdlogDp.csv`

**Daily files (when "Create daily files" option is enabled):**
```
{YYYYMMDD}_dNdlogDp.csv
```
One file per unique date in the dataset.

---

## CSV File Structure

### Row 1: Metadata Header
```
Software version: {version} ; Calibration file: {calibration_filename}
```
Example:
```
Software version: 0.10.0 ; Calibration file: A20_size_calibration.txt
```

### Row 2: Column Headers
```
Scan start time,Bin {lower1}-{upper1} nm,Bin {lower2}-{upper2} nm,...,Dp >{highest_dp} nm total number concentration
```

**Column order:**
1. `Scan start time` - timestamp of each scan
2. Bin columns - ordered from **smallest to largest** particle diameter
3. Final column - total concentration above the largest bin

**Bin header format:**
```
Bin {LowerDp}-{UpperDp} nm
```
- LowerDp and UpperDp are rounded to 2 decimal places
- Example: `Bin 1.27-1.56 nm`

### Row 3+: Data Rows
Each row represents one scan with:
- Timestamp in first column
- dN/dlogDp values for each size bin
- Total concentration above largest bin in last column

---

## Timestamp Formats

### Standard Format (default)
ISO 8601 datetime as numpy.datetime64 string:
```
2023-08-15T14:23:01
```

### Matlab Format (optional)
When "Matlab time format" is enabled:
```
dd-mmm-yyyy HH:MM:SS
```
Example: `15-Aug-2023 14:23:01`

Python conversion:
```python
t = pd.to_datetime(numpy_datetime64_value)
matlab_format = t.strftime('%d-%b-%Y %H:%M:%S')
```

---

## Data Value Formatting

### Rounding Rules
- Values >= 1: Round to 2 decimal places
- Values < 1: Round to 2 significant figures

```python
# Values >= 1
save_data = save_data.mask(save_data >= 1, save_data.astype(float).round(2))

# Values < 1 (2 significant figures)
save_data = save_data.mask(save_data < 1, save_data.map(lambda x: float("%.2g" % x)))
```

### Negative Values
All negative dN/dlogDp values are set to NaN before saving (handled during inversion step).

---

## Input Data Structure (self.Ninv DataFrame)

The inversion result DataFrame `Ninv` has this structure:

| Column | Description |
|--------|-------------|
| `bins` | Bin category labels |
| `LowerDp` | Lower diameter boundary (nm) |
| `UpperDp` | Upper diameter boundary (nm) |
| `dlogDp` | Log diameter bin width |
| `MaxDeteff` | Maximum detection efficiency |
| `binCenter` | Center diameter of bin (nm) |
| `dN0`, `dN1`, ... | dN/dlogDp values for each scan |

**Important:** The DataFrame is stored with bins from largest to smallest. During save, columns are reversed to order from smallest to largest bin.

---

## Complete Save Algorithm

```python
def save_inversion_data(Ninv, scan_start_time, data_df, lowest_bin_limit,
                         calibration_filename, version_number,
                         use_matlab_time=False, create_daily_files=False,
                         output_path=None):
    """
    Save inverted PSM data to CSV file(s).

    Parameters:
    -----------
    Ninv : pd.DataFrame
        Inverted data with columns: bins, LowerDp, UpperDp, dlogDp, MaxDeteff,
        binCenter, dN0, dN1, dN2, ...
    scan_start_time : np.array
        Array of numpy.datetime64 values for each scan start time
    data_df : pd.DataFrame
        Original data with columns: concentration, satflow, t
    lowest_bin_limit : float
        Lowest saturation flow limit for concentration above bins calculation
    calibration_filename : str
        Name of calibration file used
    version_number : str
        Software version string
    use_matlab_time : bool
        If True, use Matlab datetime format
    create_daily_files : bool
        If True, create separate file for each day
    output_path : str
        Output file path (single file) or directory (daily files)

    Returns:
    --------
    list : List of saved filenames
    """

    # Step 1: Build column headers from bin boundaries
    dp_headers = []
    for i in range(len(Ninv)):
        row_idx = i + 1  # DataFrame index starts from 1 after dropping first row
        lower = str(round(Ninv['LowerDp'][row_idx], 2))
        upper = str(round(Ninv['UpperDp'][row_idx], 2))
        dp_headers.append(f'Bin {lower}-{upper} nm')

    # Step 2: Transpose Ninv to get scans as rows
    save_data = Ninv.T

    # Step 3: Filter to only dN columns (scan data)
    save_data = save_data.filter(regex='^dN', axis=0)

    # Step 4: Set column names
    save_data.columns = dp_headers

    # Step 5: Reverse column order (smallest to largest bin)
    save_data = save_data[save_data.columns[::-1]]

    # Step 6: Apply rounding rules
    # Values >= 1: 2 decimal places
    save_data = save_data.mask(save_data >= 1, save_data.astype(float).round(2))
    # Values < 1: 2 significant figures
    save_data = save_data.mask(save_data < 1, save_data.map(lambda x: float("%.2g" % x)))

    # Step 7: Add timestamp column
    if use_matlab_time:
        matlab_times = []
        for t in scan_start_time:
            dt = pd.to_datetime(t)
            matlab_times.append(dt.strftime('%d-%b-%Y %H:%M:%S'))
        save_data.insert(0, 'Scan start time', matlab_times)
    else:
        save_data.insert(0, 'Scan start time', scan_start_time)

    # Step 8: Calculate and add concentration above largest bin
    larger_concentration = concentration_above_bins(scan_start_time, data_df, lowest_bin_limit)
    highest_dp = str(round(Ninv['UpperDp'].iloc[0], 2))
    save_data[f'Dp >{highest_dp} nm total number concentration'] = larger_concentration

    # Step 9: Split by day if requested
    if create_daily_files:
        unique_dates = pd.to_datetime(save_data['Scan start time']).dt.date.unique()
        dataframes = []
        filenames = []
        for date in unique_dates:
            df = save_data[pd.to_datetime(save_data['Scan start time']).dt.date == date]
            filename = f"{output_path}/{date.strftime('%Y%m%d')}_dNdlogDp.csv"
            dataframes.append(df)
            filenames.append(filename)
    else:
        dataframes = [save_data]
        filenames = [output_path]

    # Step 10: Write files
    saved_files = []
    for filename, dataframe in zip(filenames, dataframes):
        # Write CSV data
        dataframe.to_csv(filename, sep=',', index=False, lineterminator='\n')

        # Prepend metadata header
        with open(filename, 'r') as f:
            data = f.read()
        with open(filename, 'w') as f:
            f.write(f"Software version: {version_number} ; Calibration file: {calibration_filename}\n")
            f.write(data)

        saved_files.append(filename)

    return saved_files
```

---

## Helper Function: Concentration Above Bins

This calculates the total particle concentration at saturator flows above the measurement range (particles larger than the largest bin).

```python
def concentration_above_bins(scan_start_time, data_df, lowest_bin_limit):
    """
    Calculate average concentration at satflow near lowest_bin_limit for each scan.

    Parameters:
    -----------
    scan_start_time : np.array
        Array of scan start times (numpy.datetime64)
    data_df : pd.DataFrame
        Data with columns: concentration, satflow, t
    lowest_bin_limit : float
        Lower saturation flow limit

    Returns:
    --------
    np.array : Average concentration values for each scan
    """
    data_df_copy = data_df[['concentration', 'satflow', 't']].copy()
    concentration_values = []

    for i in range(len(scan_start_time)):
        # Get data for current scan time window
        if i < len(scan_start_time) - 1:
            scan = data_df_copy[
                (data_df_copy['t'] >= scan_start_time[i]) &
                (data_df_copy['t'] < scan_start_time[i+1])
            ]
        else:
            scan = data_df_copy[data_df_copy['t'] >= scan_start_time[i]]

        # Filter to satflow near lowest_bin_limit (within 0.02)
        scan = scan[
            (scan['satflow'] >= lowest_bin_limit - 0.02) &
            (scan['satflow'] <= lowest_bin_limit)
        ]

        if scan.empty:
            concentration_values.append(np.nan)
        else:
            avg = round(scan['concentration'].mean(), 2)
            concentration_values.append(avg)

    return np.array(concentration_values)
```

---

## Example Output File

```csv
Software version: 0.10.0 ; Calibration file: A20_size_calibration.txt
Scan start time,Bin 1.27-1.56 nm,Bin 1.56-1.85 nm,Bin 1.85-2.14 nm,Bin 2.14-2.5 nm,Dp >2.5 nm total number concentration
2023-08-15T08:00:00,125.45,342.67,567.89,234.12,1523.45
2023-08-15T08:04:00,118.23,328.91,542.33,221.87,1489.32
2023-08-15T08:08:00,0.0087,0.012,0.045,0.089,245.67
```

Or with Matlab time format:
```csv
Software version: 0.10.0 ; Calibration file: A20_size_calibration.txt
Scan start time,Bin 1.27-1.56 nm,Bin 1.56-1.85 nm,Bin 1.85-2.14 nm,Bin 2.14-2.5 nm,Dp >2.5 nm total number concentration
15-Aug-2023 08:00:00,125.45,342.67,567.89,234.12,1523.45
15-Aug-2023 08:04:00,118.23,328.91,542.33,221.87,1489.32
15-Aug-2023 08:08:00,0.0087,0.012,0.045,0.089,245.67
```

---

## Key Implementation Notes

1. **Bin ordering**: Internal storage is largest-to-smallest, but output is smallest-to-largest
2. **Index offset**: After dropping the first row of Ninv, indices start at 1, not 0
3. **Metadata row**: The software version and calibration file are prepended after CSV write
4. **Line terminator**: Use `\n` explicitly for cross-platform compatibility
5. **No index column**: `index=False` in `to_csv()` call
6. **NaN handling**: Pandas will write NaN values as empty cells or "nan" depending on settings
7. **Significant figures**: Values < 1 use `"%.2g"` format for 2 significant figures

---

## Required Dependencies

```python
import pandas as pd
import numpy as np
```

---

## Configuration Options Summary

| Option | Description | Default |
|--------|-------------|---------|
| Daily files | Split output by date | Off |
| Matlab time | Use dd-mmm-yyyy HH:MM:SS format | Off |

