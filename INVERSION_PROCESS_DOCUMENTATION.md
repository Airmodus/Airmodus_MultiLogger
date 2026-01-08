# PSM Inversion Process - Complete Technical Documentation

This document describes the complete data processing pipeline from raw PSM and CPC data files to the final particle size distribution (dN/dlogDp).

---

## Table of Contents

1. [Overview](#overview)
2. [Input Data Files](#input-data-files)
3. [Calibration Data](#calibration-data)
4. [10 Hz Data Expansion](#10-hz-data-expansion)
5. [Dilution Correction](#dilution-correction)
6. [Time Lag Correction](#time-lag-correction)
7. [Scan Detection](#scan-detection)
8. [Binning](#binning)
9. [Scan Averaging](#scan-averaging)
10. [Stepwise Inversion](#stepwise-inversion)
11. [Complete Data Flow Summary](#complete-data-flow-summary)
12. [Example with Numbers](#example-with-numbers)

---

## Overview

The PSM (Particle Size Magnifier) measures particle concentrations by sweeping its saturator flow rate. At different flow rates, particles of different minimum sizes are activated and counted by the CPC (Condensation Particle Counter).

**Key principle:**
- **High saturator flow** → high supersaturation → detects **small** particles (≥1 nm)
- **Low saturator flow** → low supersaturation → detects only **large** particles (≥4-10 nm)

The concentration at each flow rate is **cumulative** - it counts all particles above the cutoff size. The inversion process converts these cumulative counts into a **differential size distribution** (dN/dlogDp).

---

## Input Data Files

### PSM Data File (1 Hz, .dat format)

Columns used:
| Column | Name | Description |
|--------|------|-------------|
| 0 | timestamp | `DD.MM.YYYY HH:MM:SS` format |
| 1 | concentration | Particle concentration from PSM (#/cm³) |
| 3 | satflow | Saturator flow rate (L/min) |
| 17 | dilution | Internal dilution factor |
| 44 | CPC_system_status_error | Hex error code |
| 46 | PSM_system_status_error | Hex error code |
| Scan status | (if PSM 2.0) | 0=low, 1=rising, 2=high, 3=falling |

### CPC 10 Hz Data File (.csv format)

Each row contains:
| Column | Description |
|--------|-------------|
| 0 | timestamp | `YYYY.MM.DD HH:MM:SS` format |
| 1-10 | c0-c9 | 10 concentration values (100ms intervals, packed) |

The 10 values represent concentrations measured during the **previous** second:
- c0 = concentration at timestamp - 900ms
- c1 = concentration at timestamp - 800ms
- ...
- c9 = concentration at timestamp (current)

---

## Calibration Data

### Calibration File Format (tab-delimited)

| cal_satflow | cal_diameter | cal_maxdeteff |
|-------------|--------------|---------------|
| 1.30 | 1.0 | 0.70 |
| 1.00 | 1.5 | 0.82 |
| 0.70 | 2.0 | 0.90 |
| 0.50 | 3.0 | 0.95 |
| 0.30 | 5.0 | 0.98 |
| 0.15 | 10.0 | 1.00 |

**Columns:**
- `cal_satflow`: Saturator flow rate (L/min)
- `cal_diameter`: D50 cutoff diameter (nm) - diameter at which 50% of particles are detected
- `cal_maxdeteff`: Maximum detection efficiency at this cutoff (0-1)

**Relationship:** Higher satflow → smaller cutoff diameter

### Size Calibration Curve Fitting

The calibration data is fitted with:

```
Dp(Q) = Q/(Q-a) + b + Q/((Q+c)^d)
```

Parameters (a, b, c, d) are determined by `scipy.optimize.curve_fit` with initial guesses `[3.5, 2.5, 0.5, 10]`.

### Detection Efficiency Curve Fitting

Detection efficiency is modeled as a sigmoid:

```
η(Dp) = max_val / (1 + exp(-(Dp - shift) / scale))
```

Parameters (shift, scale, max_val) are fitted with initial guesses `[1.5, 0.015, 1]`.

---

## 10 Hz Data Expansion

### Purpose

Convert 1 Hz PSM data and packed CPC data into aligned 10 Hz (100ms resolution) data.

### Step 1: Expand PSM Data (`expand_psm_data`)

**Input:** 1 Hz PSM dataframe with satflow values

**Process:**

1. **Resample to 100ms:**
```python
df = df.set_index('t').resample('100ms').asfreq().reset_index()
```

2. **Forward fill status columns:**
```python
df['Scan status'] = df['Scan status'].ffill()
df['dilution'] = df['dilution'].ffill()
```

3. **Calculate scan parameters:**
```python
# Get flow limits from data
min_flow = df.loc[df['Scan status'] == 0, 'satflow'].median()  # typically ~0.15
max_flow = df.loc[df['Scan status'] == 2, 'satflow'].median()  # typically ~1.9

# Calculate scan time (duration of one up or down scan)
scan_time = median(phase_times) + 0.1  # seconds

# Calculate exponential base for flow calculation
scan_power = (max_flow / min_flow) ** (1.0 / scan_time)
```

4. **Calculate flow at each 100ms point:**

The PSM scans exponentially, not linearly. For each 100ms timestamp:

```python
# For rising scan (Scan status = 1):
flow = min_flow * (scan_power ** time_since_change)

# For falling scan (Scan status = 3):
flow = max_flow * ((1/scan_power) ** time_since_change)

# For stationary phases:
# Scan status = 0: flow = min_flow
# Scan status = 2: flow = max_flow
```

5. **Apply scan offset correction:**

There's typically a timing offset between when the scan status changes and when the flow actually starts changing. This is calculated and corrected:

```python
rising_offset = log(first_rising_mean / min_flow) / log(scan_power)
falling_offset = log(first_falling_mean / max_flow) / log(1/scan_power)
scan_offset_time = (rising_offset + falling_offset) / 2
```

**Output:** Dataframe with 100ms timestamps and calculated satflow values

### Step 2: Expand CPC Data (`expand_cpc_data`)

**Input:** CPC dataframe with 10 concentration columns per row

**Process:**

```python
for each row:
    base_time = row timestamp
    for i in range(10):
        offset_index = i - 9  # i=0 → -900ms, i=9 → 0ms
        new_time = base_time + timedelta(milliseconds=100 * offset_index)
        concentration = row[column i+1]
        append (new_time, concentration)
```

**Output:** Dataframe with 100ms timestamps and individual concentration values

### Step 3: Merge on Timestamp

```python
merged_df = pd.merge(expanded_psm_df, expanded_cpc_df, on='t')
```

**Result:** Each 100ms timestamp now has both calculated satflow AND measured concentration.

---

## Dilution Correction

### Source of Parameters

Dilution parameters come from a `.par` file (same name as data file, different extension):

| Parameter | Name in file | Description |
|-----------|--------------|-------------|
| α (alpha) | amp | Skewness of correction curve |
| μ (mu) | cen | Center flow rate |
| σ (sigma) | sig | Width of correction curve |
| slope | slope | Linear trend component |
| intercept | intercept | Baseline offset |

### The Correction Formula

```python
def correct_concentration(df, alpha, mu, sigma, slope, intercept, shift):
    flow = df['flow']

    # Skewed Gaussian + linear correction
    dilution_correction = (
        (exp(-0.5 * ((flow - mu) / sigma)**2) / sqrt(2 * pi * sigma**2)) *
        ((1 + tanh(alpha * (flow - mu) / sigma)) / sigma)
        + flow * slope + intercept
    )

    # Apply correction
    df['concentration'] = df['CPC_concentration'] * df['dilution'] / dilution_correction
```

### Physical Meaning

The PSM mixes saturated air with clean air before mixing with sample air:
- `Q_saturator + Q_clean = Q_total` (constant)
- Different saturator flows → different mixing ratios → different dilution effects

The correction accounts for these flow-dependent dilution effects.

---

## Time Lag Correction

### Purpose

Account for the time delay between when particles pass the satflow measurement point and when they're counted by the CPC.

### Implementation (`shift_concentration`)

```python
def shift_concentration(df, time_lag):
    # Detect if 10 Hz data
    median_time_diff = df['t'].diff().dt.total_seconds().median()
    ten_hz = (median_time_diff == 0.1)

    # Convert time lag to index
    if ten_hz:
        time_lag_index = int(float(time_lag) * 10)  # 0.1s precision
    else:
        time_lag_index = int(round(float(time_lag)))  # 1s precision

    # Shift concentration values backwards (negative = move up in dataframe)
    df['concentration'] = df['concentration'].shift(-1 * time_lag_index)
```

### Gap Handling

If there are gaps >2 seconds in the data, values before the gap are set to NaN to prevent incorrect shifting across gaps:

```python
gap_indices = df.index[df['t'].diff().dt.total_seconds() > 2]
for gap_index in gap_indices:
    for i in range(abs(time_lag_index)):
        df.iloc[gap_index - 1 - i, 'concentration'] = np.nan
```

### When Applied

Time lag correction is applied **after** 10 Hz conversion but **before** binning, at the start of the inversion process.

---

## Scan Detection

### Method 1: Using Scan Status Column (PSM 2.0)

If the data has a `Scan status` column:
- 0 = stationary at low flow
- 1 = rising (low → high flow, small → large Dp)
- 2 = stationary at high flow
- 3 = falling (high → low flow, large → small Dp)

```python
df['up_scan'] = df['Scan status'].apply(lambda x: 1 if x in [1,2] else -1 if x in [3,0] else 0)
df['scan_no'] = np.cumsum(abs(df['up_scan'].diff() / 2))
```

### Method 2: Derivative-Based Detection (Older PSM)

If no scan status column, detect scans from satflow changes:

```python
n_average = 20
satflow_diff = np.convolve(np.diff(df['satflow']), np.ones(n_average)/n_average, mode='valid')
df['up_scan'] = np.sign(moving_average(satflow_diff, 5))
df['scan_no'] = np.cumsum(abs(df['up_scan'].diff() / 2))
```

---

## Binning

### Step 1: User Defines Bin Limits (Diameter Space)

User specifies bin edges in nanometers, e.g., `[1.0, 2.0, 4.0, 8.0]`

For custom bins with min/max/number:
```python
def calculate_bin_limits(min_size, max_size, num_bins):
    num_limits = num_bins + 1
    # Logarithmically spaced
    bin_limits = 10 ** np.linspace(np.log10(min_size), np.log10(max_size), num_limits)
    return bin_limits
```

### Step 2: Calculate Binning Limits with Geometric Means

```python
def calculateBins(calibration_df, fixed_bin_limits):
    # Calculate geometric means between adjacent bin edges
    binning_limit = geom_means(fixed_bin_limits)

    # Add outer edges
    binning_limit = np.append(binning_limit, fixed_bin_limits[-1])
    binning_limit = np.append(fixed_bin_limits[0], binning_limit)

    # Convert diameter → satflow via calibration interpolation
    bin_lims = np.flip(np.interp(binning_limit,
                                  calibration_df['cal_diameter'],
                                  calibration_df['cal_satflow']))
    return bin_lims

def geom_means(x):
    # Geometric mean of adjacent pairs
    result = np.zeros(len(x)-1)
    for i in range(len(x)-1):
        result[i] = np.sqrt(x[i] * x[i+1])
    return result
```

**Example:**
```
User bins: [1.0, 2.0, 4.0, 8.0] nm
Geometric means: [1.41, 2.83, 5.66] nm
Binning limits: [1.0, 1.41, 2.83, 5.66, 8.0] nm
→ Converted to satflow: [1.30, 1.12, 0.55, 0.27, 0.18] L/min
```

### Step 3: Assign Data Points to Bins

```python
df['bins'] = pd.cut(df['satflow'], bins)
```

### Step 4: Calculate Mean Concentration per Bin per Scan

```python
df['bin_mean_c'] = df.groupby(['bins', 'scan_no'])['concentration'].transform('mean')
```

### Step 5: Apply External Dilution Factor

```python
df['bin_mean_c'] = df['bin_mean_c'] * external_dilution_factor
```

### Step 6: Build Nbinned DataFrame

```python
Nbinned = DataFrame({
    'lower': satflow_bins[:-1],
    'upper': satflow_bins[1:],
    'bins': bin_labels,
    'UpperDp': interpolate(lower, calibration),  # larger Dp at lower satflow
    'LowerDp': interpolate(upper, calibration),
    'dlogDp': log10(UpperDp) - log10(LowerDp),
    'MaxDeteff': interpolate(UpperDp, calibration_deteff),
    'scanN0': mean_conc_scan_0,
    'scanN1': mean_conc_scan_1,
    ...
})
```

---

## Scan Averaging

Optional smoothing across multiple scans:

```python
def averagedata(Ninv, Sn):
    # Rolling mean across Sn scans (columns)
    temp = Ninv.iloc[:, skip:]  # skip metadata columns
    temp = temp.rolling(Sn, min_periods=1, axis=1).mean()
    return result
```

If `Sn = 3`, each scan becomes the average of itself and the 2 previous scans.

---

## Stepwise Inversion

### The Core Algorithm

```python
def step_inversion(self):
    for each scan i:
        # 1. Get binned concentrations for this scan
        conc = Nbinned['scanN' + str(i)]

        # 2. Calculate difference between adjacent bins
        delta_N = conc.diff()

        # 3. Normalize by logarithmic bin width
        dN_dlogDp = delta_N / Nbinned['dlogDp']

        # 4. Correct for detection efficiency
        dN_dlogDp_corrected = dN_dlogDp / Nbinned['MaxDeteff']

        Ninv['dN' + str(i)] = dN_dlogDp_corrected

    # 5. Drop first row (no diff possible)
    Ninv = Ninv.drop(Ninv.index[0])

    # 6. Set negative values to NaN (unphysical)
    Ninv[Ninv < 0] = np.nan
```

### The Formula

```
dN/dlogDp = ΔN / dlogDp / η

Where:
- ΔN = Concentration[bin_i] - Concentration[bin_i+1]
- dlogDp = log₁₀(Dp_upper) - log₁₀(Dp_lower)
- η = MaxDeteff (detection efficiency at bin edge)
```

### Why Each Step

1. **diff()**: Converts cumulative concentration to differential (particles in this size range only)
2. **/ dlogDp**: Normalizes for bin width so different-sized bins are comparable
3. **/ MaxDeteff**: Corrects for particles that were present but not detected

---

## Complete Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                     INPUT FILES                                  │
├─────────────────────────────────────────────────────────────────┤
│  PSM Data (.dat)     CPC 10Hz (.csv)     Calibration     .par   │
│  - timestamp         - timestamp          - satflow      - amp  │
│  - satflow           - 10 conc values     - diameter     - cen  │
│  - scan status       (packed)             - maxdeteff    - sig  │
│  - dilution                                              - slope│
│                                                          - int  │
└────────┬─────────────────────┬───────────────────────────┬──────┘
         │                     │                           │
         ▼                     ▼                           │
┌─────────────────┐  ┌─────────────────┐                   │
│ Expand PSM      │  │ Expand CPC      │                   │
│ to 10 Hz        │  │ to 10 Hz        │                   │
│                 │  │                 │                   │
│ - Resample      │  │ - Unpack 10     │                   │
│   to 100ms      │  │   values/row    │                   │
│ - Calculate     │  │ - Spread        │                   │
│   flow(t)       │  │   backwards     │                   │
│   exponentially │  │   in time       │                   │
└────────┬────────┘  └────────┬────────┘                   │
         │                    │                            │
         └─────────┬──────────┘                            │
                   ▼                                       │
         ┌─────────────────┐                               │
         │ Merge on        │                               │
         │ timestamp       │                               │
         └────────┬────────┘                               │
                  │                                        │
                  ▼                                        │
         ┌─────────────────┐                               │
         │ Dilution        │◄──────────────────────────────┘
         │ Correction      │
         │                 │
         │ conc = CPC_conc │
         │   × dilution    │
         │   / correction  │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Time Lag        │◄─── User input (seconds)
         │ Correction      │
         │                 │
         │ Shift conc      │
         │ backwards       │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Scan Detection  │
         │                 │
         │ Identify up/    │
         │ down scans      │
         │ Assign scan_no  │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Binning         │◄─── User bin limits + Calibration
         │                 │
         │ - Convert Dp    │
         │   bins → satflow│
         │ - Assign data   │
         │   to bins       │
         │ - Mean conc     │
         │   per bin/scan  │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Scan Averaging  │◄─── User input (Sn)
         │ (optional)      │
         │                 │
         │ Rolling mean    │
         │ across Sn scans │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ Stepwise        │
         │ Inversion       │
         │                 │
         │ dN/dlogDp =     │
         │   diff(conc)    │
         │   / dlogDp      │
         │   / MaxDeteff   │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ OUTPUT          │
         │                 │
         │ Ninv dataframe: │
         │ - LowerDp       │
         │ - UpperDp       │
         │ - binCenter     │
         │ - dN0, dN1, ... │
         │   (dN/dlogDp    │
         │    per scan)    │
         └─────────────────┘
```

---

## Example with Numbers

### Input Data (1 scan, simplified)

**Raw PSM (1 Hz):**
```
| time     | satflow | Scan status | concentration |
|----------|---------|-------------|---------------|
| 10:00:01 | 1.30    | 3           | 450           |
| 10:00:02 | 1.10    | 3           | 500           |
| 10:00:03 | 0.90    | 3           | 570           |
| 10:00:04 | 0.70    | 3           | 650           |
| 10:00:05 | 0.50    | 3           | 750           |
| 10:00:06 | 0.30    | 3           | 900           |
```

**Calibration:**
```
| satflow | diameter | maxdeteff |
|---------|----------|-----------|
| 1.30    | 1.0      | 0.70      |
| 0.90    | 1.5      | 0.82      |
| 0.70    | 2.0      | 0.90      |
| 0.50    | 3.0      | 0.95      |
| 0.30    | 5.0      | 0.98      |
```

### Step 1: User Bin Limits

User wants: `[1.0, 2.0, 4.0]` nm (2 bins: 1-2nm and 2-4nm)

### Step 2: Calculate Binning Limits

```
Geometric means: [√(1×2), √(2×4)] = [1.41, 2.83] nm
Binning limits: [1.0, 1.41, 2.83, 4.0] nm
Convert to satflow: [1.30, 1.05, 0.55, 0.40] L/min (interpolated)
```

### Step 3: Assign to Bins and Average

```
| satflow range | Dp range   | data points    | mean_conc |
|---------------|------------|----------------|-----------|
| (1.05, 1.30]  | 1.0-1.41   | 450, 500       | 475       |
| (0.55, 1.05]  | 1.41-2.83  | 570, 650       | 610       |
| (0.40, 0.55]  | 2.83-4.0   | 750            | 750       |
```

### Step 4: Build Nbinned

```
| bin          | LowerDp | UpperDp | dlogDp | MaxDeteff | scanN0 |
|--------------|---------|---------|--------|-----------|--------|
| (1.05,1.30]  | 1.0     | 1.41    | 0.149  | 0.76      | 475    |
| (0.55,1.05]  | 1.41    | 2.83    | 0.302  | 0.87      | 610    |
| (0.40,0.55]  | 2.83    | 4.0     | 0.150  | 0.93      | 750    |
```

### Step 5: Stepwise Inversion

**Order data large Dp first (flip):**
```
| UpperDp | conc | dlogDp | MaxDeteff |
|---------|------|--------|-----------|
| 4.0     | 750  | 0.150  | 0.93      |
| 2.83    | 610  | 0.302  | 0.87      |
| 1.41    | 475  | 0.149  | 0.76      |
```

**Calculate diff:**
```
ΔN[0] = 750 - 610 = 140  (particles 2.83-4.0 nm)
ΔN[1] = 610 - 475 = 135  (particles 1.41-2.83 nm)
ΔN[2] = 475 - ? = dropped (first bin, no previous)
```

**Divide by dlogDp:**
```
dN/dlogDp[0] = 140 / 0.150 = 933
dN/dlogDp[1] = 135 / 0.302 = 447
```

**Divide by MaxDeteff:**
```
(dN/dlogDp)_corrected[0] = 933 / 0.93 = 1003
(dN/dlogDp)_corrected[1] = 447 / 0.87 = 514
```

### Final Output

```
| LowerDp | UpperDp | binCenter | dN/dlogDp |
|---------|---------|-----------|-----------|
| 2.83    | 4.0     | 3.36      | 1003      |
| 1.41    | 2.83    | 2.0       | 514       |
```

This is the particle size distribution: more particles per unit logDp in the 2.83-4.0 nm range than in the 1.41-2.83 nm range.

---

## Key Constants and Parameters

| Parameter | Typical Value | Source |
|-----------|---------------|--------|
| min_flow | 0.1-0.15 L/min | Data or default |
| max_flow | 1.3-1.9 L/min | Data or default |
| scan_time | ~120 s | Calculated from data |
| n_average (scan detection) | 20 | Hardcoded |
| skip (metadata columns) | 6-7 | Depends on dataframe structure |

---

## Common Issues to Check

1. **Time alignment**: Ensure PSM and CPC timestamps are properly aligned after expansion
2. **Scan direction**: Concentration should increase as satflow decreases (detecting more particles)
3. **Negative dN values**: Should be set to NaN (indicates noise or bad scan)
4. **Bin ordering**: After diff(), bins should be ordered from large to small Dp for positive differences
5. **Detection efficiency**: Values should be between 0 and 1, increasing with particle size
6. **Time lag**: Typical values 0.3-2 seconds depending on tubing length

---

## File References

- Main app: `src/app.py`
- Inversion functions: `src/PSM_inv/InversionFunctions.py`
- Helper functions: `src/PSM_inv/HelperFunctions.py`
- Key functions:
  - `expand_psm_data()`: PSM 10 Hz expansion
  - `expand_cpc_data()`: CPC 10 Hz expansion
  - `correct_concentration()`: Dilution correction
  - `shift_concentration()`: Time lag correction
  - `calculateBins()`: Bin limit calculation
  - `bin_data()`: Data binning
  - `step_inversion()`: Core inversion algorithm
