# PSM Calibration Fitting

This document explains how calibration file processing works in the MultiLogger contour plot compared to the original PSM Inversion Tool.

## Overview

When a PSM calibration file is loaded, we may need to ensure the calibration data covers the full instrument range:
- **PSM 2.0**: 12nm max diameter
- **Retrofit**: 4nm max diameter

## MultiLogger Implementation

Location: `src/devices/psm_contour_tab.py` - `_fit_calibration()`

### Logic

1. **Check if extrapolation is needed**: If the calibration file already has measurements >= max_dp (12nm or 4nm), use the data as-is with no modifications.

2. **Extrapolate only when needed**: If calibration doesn't reach max_dp, use linear fit of last 3 points to add an extrapolated point at max_dp.

```python
# If calibration already reaches max_dp, no extrapolation needed
if calibration_df['cal_diameter'].max() >= max_dp:
    return calibration_df

# Otherwise, extrapolate using last 3 points
slope, intercept = np.polyfit(last_3_satflows, last_3_diameters, 1)
satflow_for_max_dp = (max_dp - intercept) / slope
```

### Example

Calibration file with points up to 15.9nm:
```
satflow | diameter
--------|----------
1.0     | 1nm
0.5     | 5nm
0.3     | 10nm
0.15    | 13nm
0.08    | 15.9nm
```

**Result**: No changes - calibration already covers 12nm range. All points preserved.

Calibration file with points only up to 10nm:
```
satflow | diameter
--------|----------
1.0     | 1nm
0.5     | 5nm
0.3     | 10nm
```

**Result**: Extrapolate to add 12nm point using fit from last 3 points.

## Original PSM Inversion Tool Implementation

Location: `tmp/PSM_Inversion_Tool/src/PSM_inv/InversionFunctions.py` - `inst_calib()`

### Logic

1. **Always fit last 3 points** regardless of whether calibration exceeds max_dp

2. **Overwrite the last row** with the calculated max_dp point:
```python
calibration_df['cal_satflow'][len(calibration_df)-1] = satflowlimit
calibration_df['cal_diameter'][len(calibration_df)-1] = maxDp
```

3. **Sort by satflow** descending

### Example

Calibration file with points up to 15.9nm:
```
Before:
satflow | diameter
--------|----------
1.0     | 1nm
0.5     | 5nm
0.3     | 10nm
0.15    | 13nm
0.08    | 15.9nm  <- last row, will be overwritten

After overwrite + sort:
satflow | diameter
--------|----------
1.0     | 1nm
0.5     | 5nm
0.3     | 10nm
0.18    | 12nm    <- replaced 15.9nm
0.15    | 13nm    <- still here (above 12nm)
```

## Key Differences

| Aspect | MultiLogger | Original Inversion Tool |
|--------|-------------|------------------------|
| When to modify | Only if cal < max_dp | Always |
| How to modify | Add new row | Overwrite last row |
| Points above max_dp | Preserved | Preserved (except last) |
| Highest measured point | Preserved | Lost (overwritten) |

## Rationale for MultiLogger Approach

1. **Preserve measured data**: If calibration already covers the range, we have real measurements - no need for synthetic points.

2. **No data loss**: We never delete or overwrite calibration points.

3. **Simpler logic**: Only extrapolate when actually needed.

4. **User promise**: We support up to 12nm range. If calibration goes beyond, that's fine - the data is still valid and useful.
