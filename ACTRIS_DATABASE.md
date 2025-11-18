# ACTRIS Database Format Documentation

## Overview

The Airmodus MultiLogger supports logging CPC (Condensation Particle Counter) data combined with RHTP (Relative Humidity, Temperature, Pressure) measurements to a PostgreSQL database for ACTRIS-compliant data archiving.

## Features

- **Time-averaged data**: Configurable averaging intervals (1 minute, 5 minutes, 10 minutes, 15 minutes, 1 hour, 3 hours)
- **Combined measurements**: CPC particle concentration data merged with environmental RHTP data
- **Shared connection**: Multiple CPC devices can use the same PostgreSQL database connection
- **Automatic schema management**: Tables are created automatically with proper indexing
- **Data integrity**: Primary key constraint on timestamp and instrument ID
- **Live preview**: View and edit the 10 most recent records in the ACTRIS tab
- **Record management**: Delete or edit individual records directly from the UI

## Database Connection

### Connection String Format

```
postgresql://username:password@host:port/database_name
```

### Examples

```bash
# Local database with password
postgresql://postgres:mypassword@localhost:5432/actris_data

# Remote database
postgresql://user:pass@db.example.com:5432/cpc_data

# Local trusted connection (no password)
postgresql://username@localhost:5432/actris_data
```

### Required Permissions

The database user must have the following privileges:
- `CREATE` on schema (for table creation)
- `SELECT`, `INSERT`, `UPDATE`, `DELETE` on the `cpc_measurements` table

For PostgreSQL 15+, grant schema privileges:
```sql
GRANT ALL ON SCHEMA public TO your_username;
```

## Table Schema

### Table Name: `cpc_measurements`

The application automatically creates this table on first connection with the following schema:

```sql
CREATE TABLE IF NOT EXISTS public.cpc_measurements (
    -- Timestamp fields
    time timestamp with time zone NOT NULL,           -- End time of averaging interval
    starttime timestamp with time zone,               -- Start time of averaging interval
    duration interval,                                -- Duration text (e.g., "5 minutes")

    -- Instrument identification
    instr_id text COLLATE pg_catalog."default",       -- CPC serial number
    device_id integer,                                 -- Internal device ID

    -- Status indicators
    stat_dev text COLLATE pg_catalog."default",       -- Device status
    stat_enbl text COLLATE pg_catalog."default",      -- Enabled status
    stat_log integer,                                  -- Error count
    status_hex text COLLATE pg_catalog."default",     -- Status flags (hexadecimal)

    -- CPC flow measurements
    flow_inl real,                                     -- Inlet flow rate (L/min)
    flow_aer real,                                     -- Aerosol flow rate (L/min)
    flow_sam real,                                     -- Sample flow rate (L/min)

    -- CPC temperature measurements (°C)
    temp_cond real,                                    -- Condenser temperature
    temp_condtr real,                                  -- Condenser target temperature
    temp_sat real,                                     -- Saturator temperature
    temp_initr real,                                   -- Initiator temperature
    temp_cab real,                                     -- Cabinet temperature
    temp_optics real,                                  -- Optics temperature

    -- CPC pressure measurements (kPa)
    diff_pres_orf real,                                -- Critical orifice pressure drop
    pres_amb real,                                     -- Ambient pressure
    diff_pres_inl real,                                -- Inlet pressure drop
    diff_pres_noz real,                                -- Nozzle pressure drop
    pres_inl real,                                     -- Inlet pressure

    -- CPC operational parameters
    lvl_liq real,                                      -- Liquid level
    nano_enh integer,                                  -- Nano enhancement mode
    conc real,                                         -- Particle concentration (#/cm³)
    pulse_height real,                                 -- Average pulse height/duration (ns)
    current_laser real,                                -- Laser current (mA)
    counts bigint,                                     -- Total particle counts
    mem_avbl real,                                     -- Available memory
    numflag numeric(42,42),                            -- Numeric flags

    -- RHTP measurements (environmental conditions at inlet)
    humidity_inlet real,                               -- Relative humidity (%)
    temp_inlet real,                                   -- Temperature (°C)
    pressure_inlet real,                               -- Pressure (hPa)

    -- Primary key constraint
    CONSTRAINT cpc_measurements_pkey PRIMARY KEY (time, instr_id)
) TABLESPACE pg_default;
```

### Primary Key

The table uses a composite primary key consisting of:
- `time`: End timestamp of the averaging interval
- `instr_id`: CPC serial number

This ensures that each instrument can only have one record per timestamp, preventing duplicate entries.

## Data Fields Reference

### Time Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `time` | timestamp with time zone | End time of averaging interval | `2025-11-17 10:05:00+00` |
| `starttime` | timestamp with time zone | Start time of averaging interval | `2025-11-17 10:00:00+00` |
| `duration` | interval | Length of averaging period | `5 minutes` |

### Identification Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `instr_id` | text | CPC serial number | `A10-0123` |
| `device_id` | integer | Internal application device ID | `1` |

### CPC Concentration Data

| Field | Type | Unit | Description | Typical Range |
|-------|------|------|-------------|---------------|
| `conc` | real | #/cm³ | Time-averaged particle concentration | 0 - 100,000 |
| `counts` | bigint | counts | Total particle count | 0 - 1,000,000 |
| `pulse_height` | real | ns | Average pulse duration | 50 - 600 |

### CPC Temperature Data

| Field | Type | Unit | Description | Typical Range |
|-------|------|------|-------------|---------------|
| `temp_sat` | real | °C | Saturator temperature | 35 - 45 |
| `temp_cond` | real | °C | Condenser temperature | 5 - 15 |
| `temp_optics` | real | °C | Optics block temperature | 45 - 55 |
| `temp_cab` | real | °C | Cabinet internal temperature | 20 - 40 |

### CPC Pressure Data

| Field | Type | Unit | Description | Typical Range |
|-------|------|------|-------------|---------------|
| `pres_inl` | real | kPa | Inlet pressure | 80 - 110 |
| `pres_amb` | real | kPa | Ambient/cabinet pressure | 80 - 110 |
| `diff_pres_orf` | real | kPa | Critical orifice differential pressure | 0 - 20 |
| `diff_pres_noz` | real | kPa | Nozzle differential pressure | 0 - 10 |

### CPC Flow Data

| Field | Type | Unit | Description | Typical Range |
|-------|------|------|-------------|---------------|
| `flow_inl` | real | L/min | Inlet flow rate (from settings) | 0.1 - 2.5 |

### RHTP Data (Inlet Environmental Conditions)

| Field | Type | Unit | Description | Typical Range |
|-------|------|------|-------------|---------------|
| `temp_inlet` | real | °C | Inlet air temperature | -40 - 60 |
| `pressure_inlet` | real | hPa | Inlet air pressure | 800 - 1100 |
| `humidity_inlet` | real | % | Inlet air relative humidity | 0 - 100 |

### Status Data

| Field | Type | Description |
|-------|------|-------------|
| `stat_log` | integer | Total number of error flags set |
| `status_hex` | text | Hexadecimal status flags from CPC firmware |

## Sample Data

### Example 1: 5-Minute Averaged Record

```sql
INSERT INTO cpc_measurements VALUES (
    '2025-11-17 10:05:00+00',           -- time (end of interval)
    '2025-11-17 10:00:00+00',           -- starttime
    '5 minutes',                         -- duration
    'A10-0123',                          -- instr_id (CPC serial number)
    1,                                   -- device_id
    NULL,                                -- stat_dev
    NULL,                                -- stat_enbl
    0,                                   -- stat_log (0 errors)
    '0000',                              -- status_hex (no errors)
    0.30,                                -- flow_inl (L/min)
    NULL,                                -- flow_aer
    NULL,                                -- flow_sam
    10.2,                                -- temp_cond (°C)
    NULL,                                -- temp_condtr
    39.8,                                -- temp_sat (°C)
    NULL,                                -- temp_initr
    25.3,                                -- temp_cab (°C)
    50.1,                                -- temp_optics (°C)
    8.5,                                 -- diff_pres_orf (kPa)
    101.3,                               -- pres_amb (kPa)
    NULL,                                -- diff_pres_inl
    2.1,                                 -- diff_pres_noz (kPa)
    102.5,                               -- pres_inl (kPa)
    1.0,                                 -- lvl_liq (OK level)
    NULL,                                -- nano_enh
    1543.2,                              -- conc (#/cm³)
    285.0,                               -- pulse_height (ns)
    45.2,                                -- current_laser (mA)
    NULL,                                -- counts
    NULL,                                -- mem_avbl
    NULL,                                -- numflag
    45.2,                                -- humidity_inlet (%)
    22.5,                                -- temp_inlet (°C)
    1013.0                               -- pressure_inlet (hPa)
);
```

### Example 2: 1-Hour Averaged Record with Error

```sql
INSERT INTO cpc_measurements VALUES (
    '2025-11-17 11:00:00+00',           -- time
    '2025-11-17 10:00:00+00',           -- starttime
    '1 hour',                            -- duration
    'A10-0124',                          -- instr_id
    2,                                   -- device_id
    NULL,                                -- stat_dev
    NULL,                                -- stat_enbl
    2,                                   -- stat_log (2 errors detected)
    '0120',                              -- status_hex (error flags)
    0.30,                                -- flow_inl
    NULL,                                -- flow_aer
    NULL,                                -- flow_sam
    10.8,                                -- temp_cond
    NULL,                                -- temp_condtr
    40.1,                                -- temp_sat
    NULL,                                -- temp_initr
    26.7,                                -- temp_cab
    51.3,                                -- temp_optics
    8.2,                                 -- diff_pres_orf
    100.8,                               -- pres_amb
    NULL,                                -- diff_pres_inl
    2.3,                                 -- diff_pres_noz
    103.1,                               -- pres_inl
    0.8,                                 -- lvl_liq (low level warning)
    NULL,                                -- nano_enh
    2187.5,                              -- conc
    298.5,                               -- pulse_height
    44.8,                                -- current_laser
    NULL,                                -- counts
    NULL,                                -- mem_avbl
    NULL,                                -- numflag
    38.5,                                -- humidity_inlet
    21.8,                                -- temp_inlet
    1015.5                               -- pressure_inlet
);
```

### Example 3: Record without RHTP Data

If no RHTP device is linked or available, the inlet environmental fields will be `NULL`:

```sql
INSERT INTO cpc_measurements VALUES (
    '2025-11-17 12:05:00+00',
    '2025-11-17 12:00:00+00',
    '5 minutes',
    'A10-0125',
    3,
    NULL, NULL,
    0,
    '0000',
    0.30, NULL, NULL,
    10.5, NULL, 40.0, NULL, 25.1, 50.4,
    8.7, 101.5, NULL, 2.0, 102.8,
    1.0, NULL,
    1876.3,
    290.0,
    45.5,
    NULL, NULL, NULL,
    NULL,                                -- humidity_inlet (no RHTP)
    NULL,                                -- temp_inlet (no RHTP)
    NULL                                 -- pressure_inlet (no RHTP)
);
```

## SQL Query Examples

### Query 1: Get Latest 10 Records for Specific CPC

```sql
SELECT
    starttime,
    time,
    conc,
    temp_sat,
    temp_cond,
    humidity_inlet,
    temp_inlet,
    stat_log,
    status_hex
FROM cpc_measurements
WHERE instr_id = 'A10-0123'
ORDER BY time DESC
LIMIT 10;
```

### Query 2: Calculate Daily Average Concentration

```sql
SELECT
    DATE(time) as date,
    instr_id,
    AVG(conc) as avg_concentration,
    MIN(conc) as min_concentration,
    MAX(conc) as max_concentration,
    COUNT(*) as num_records
FROM cpc_measurements
WHERE time >= NOW() - INTERVAL '7 days'
GROUP BY DATE(time), instr_id
ORDER BY date DESC, instr_id;
```

### Query 3: Find Records with Errors

```sql
SELECT
    time,
    instr_id,
    stat_log,
    status_hex,
    conc,
    temp_sat,
    temp_cond
FROM cpc_measurements
WHERE stat_log > 0
ORDER BY time DESC
LIMIT 50;
```

### Query 4: Temperature Correlation Analysis

```sql
SELECT
    temp_inlet,
    temp_sat,
    temp_cond,
    conc,
    humidity_inlet
FROM cpc_measurements
WHERE time >= NOW() - INTERVAL '24 hours'
    AND instr_id = 'A10-0123'
    AND temp_inlet IS NOT NULL
ORDER BY time;
```

### Query 5: Export Data for Time Period (CSV-ready)

```sql
COPY (
    SELECT
        starttime as "Start Time",
        time as "End Time",
        instr_id as "CPC Serial",
        conc as "Concentration [#/cm3]",
        temp_sat as "T Saturator [°C]",
        temp_cond as "T Condenser [°C]",
        temp_inlet as "T Inlet [°C]",
        pressure_inlet as "P Inlet [hPa]",
        humidity_inlet as "RH Inlet [%]",
        stat_log as "Errors"
    FROM cpc_measurements
    WHERE time BETWEEN '2025-11-01' AND '2025-11-30'
        AND instr_id = 'A10-0123'
    ORDER BY time
) TO '/path/to/export/november_2025_cpc_data.csv'
WITH CSV HEADER;
```

## Data Averaging Process

### How Averaging Works

1. **Sample Collection**: 1 Hz samples from CPC and linked RHTP are collected in memory buffers
2. **Interval Alignment**: Intervals are aligned to clock boundaries (e.g., 5-minute intervals start at :00, :05, :10, etc.)
3. **Arithmetic Mean**: Most values are averaged using arithmetic mean over the interval
4. **Exception - Status**: Error status and status_hex use the **last value** in the interval (not averaged)
5. **Database Write**: One record is written when the interval completes

### Example Timeline (5-minute interval)

```
Time                CPC Reading    Buffer Size    Action
10:00:00           1500 #/cm³     1 sample       Start interval
10:00:01           1520 #/cm³     2 samples
10:00:02           1510 #/cm³     3 samples
...
10:04:58           1530 #/cm³     299 samples
10:04:59           1540 #/cm³     300 samples    End interval
10:05:00           Write record   0 samples      Calculate average (1525 #/cm³) → DB
10:05:00           1550 #/cm³     1 sample       Start new interval
```

### Interval Configuration Options

| Interval | Samples | Use Case |
|----------|---------|----------|
| 1 minute | ~60 | High temporal resolution, large data volume |
| 5 minutes | ~300 | ACTRIS standard, good balance |
| 10 minutes | ~600 | Reduced data volume |
| 15 minutes | ~900 | Medium temporal resolution |
| 1 hour | ~3600 | Low temporal resolution, small data volume |
| 3 hours | ~10800 | Very coarse averaging |

## ACTRIS Tab UI Features

### Connection Section
- **Connection String Input**: Enter PostgreSQL connection string
- **Test Connection Button**: Verify database connectivity and refresh preview table
- **Global Status**: Shows if database is connected
- **Active Devices**: Count of CPCs currently using the database

### Device Settings
- **Enable Database**: Checkbox to activate database logging for this CPC
- **Linked RHTP**: Dropdown to select which RHTP device provides inlet environmental data
- **Averaging Interval**: Dropdown to select time averaging period

### Status Section
- **Status**: Enabled/Disabled indicator
- **Last Write**: Timestamp of most recent database record
- **Records Written**: Total count of records written by this device
- **Current Interval**: Progress indicator (samples collected / total needed)
- **Next Write In**: Countdown timer to next database write

### Data Preview Table

Shows the 10 most recent records with columns:
- **Start**: Interval start time (HH:MM:SS)
- **End**: Interval end time (HH:MM:SS)
- **Conc**: Concentration (#/cm³)
- **Flow In**: Inlet flow (L/min)
- **T Sat**: Saturator temp (°C)
- **T Cond**: Condenser temp (°C)
- **T Inlet**: Inlet temp from RHTP (°C)
- **P Inlet**: Inlet pressure from RHTP (hPa)
- **RH In**: Inlet humidity from RHTP (%)
- **Pulse**: Pulse duration (ns)
- **Err**: Error count
- **Status**: Status hex flags

**Features:**
- **Editable**: Click any cell (except timestamps) to edit values
- **Multi-select**: Select multiple rows using Ctrl+Click or Shift+Click
- **Delete**: Delete selected rows using "Delete Selected Rows" button
- **Auto-refresh**: Table updates every 5 seconds when database is active

### Messages Section
- Real-time log of database operations
- Timestamped success/error messages
- Update confirmations
- Delete confirmations

## Troubleshooting

### Common Issues

#### "Permission denied for schema public"
**Cause**: PostgreSQL 15+ changed default permissions
**Solution**:
```sql
GRANT ALL ON SCHEMA public TO your_username;
```

#### "No RHTP device linked"
**Cause**: Database enabled before RHTP selection
**Solution**:
1. Uncheck "Enable database"
2. Select RHTP from dropdown
3. Re-enable database

#### "Connection failed: could not connect to server"
**Causes**:
- PostgreSQL server not running
- Incorrect host/port in connection string
- Firewall blocking connection
- Wrong credentials

**Solutions**:
- Verify PostgreSQL is running: `sudo systemctl status postgresql`
- Test connection with psql: `psql "postgresql://user:pass@host:port/db"`
- Check firewall rules
- Verify connection string format

#### Records Not Being Written
**Causes**:
- Database not enabled
- CPC not connected
- RHTP not connected
- Insufficient samples collected

**Check**:
1. ACTRIS tab shows "Status: Enabled" in green
2. CPC device has green checkmark (connected)
3. Linked RHTP device is connected
4. "Current Interval" shows sample collection progress

#### Preview Table Not Updating
**Cause**: No records exist in database yet
**Solution**: Wait for first averaging interval to complete and record to be written

## Best Practices

### Data Management
1. **Regular Backups**: Schedule PostgreSQL backups for long-term data preservation
2. **Disk Space**: Monitor database size, especially with 1-minute intervals
3. **Indexing**: The primary key index on (time, instr_id) is sufficient for most queries
4. **Partitioning**: For very large datasets (years of 1-minute data), consider partitioning by time

### Measurement Quality
1. **RHTP Placement**: Position RHTP sensor at CPC inlet for accurate environmental data
2. **Error Monitoring**: Regularly check `stat_log` > 0 to identify instrument issues
3. **Interval Selection**: Choose averaging interval based on measurement variability and storage capacity
4. **Validation**: Periodically compare database averages with raw `.dat` files

### Connection Management
1. **Connection String Storage**: Saved in `resume_config.json` for convenience
2. **Multiple CPCs**: All CPCs can share one database connection
3. **Reconnection**: Database reconnects automatically if connection is lost
4. **Graceful Shutdown**: Disable database before closing application to ensure final write completes

## Data Export and Analysis

### Exporting to CSV
Use the `COPY` command (see Query Example 5 above) or GUI tools like pgAdmin

### Python Analysis Example

```python
import psycopg2
import pandas as pd

# Connect to database
conn = psycopg2.connect("postgresql://user:pass@localhost:5432/actris_data")

# Query data into pandas DataFrame
query = """
    SELECT time, conc, temp_sat, temp_cond, humidity_inlet
    FROM cpc_measurements
    WHERE time >= NOW() - INTERVAL '7 days'
        AND instr_id = 'A10-0123'
    ORDER BY time
"""
df = pd.read_sql_query(query, conn)

# Analysis
print(df.describe())
df.plot(x='time', y='conc', figsize=(12, 6))
```

### R Analysis Example

```r
library(RPostgreSQL)
library(ggplot2)

# Connect to database
drv <- dbDriver("PostgreSQL")
con <- dbConnect(drv,
    host="localhost", port=5432,
    dbname="actris_data",
    user="username", password="password")

# Query data
query <- "
    SELECT time, conc, temp_sat, temp_cond
    FROM cpc_measurements
    WHERE time >= NOW() - INTERVAL '30 days'
    ORDER BY time
"
data <- dbGetQuery(con, query)

# Plot
ggplot(data, aes(x=time, y=conc)) +
    geom_line() +
    labs(title="CPC Concentration - Last 30 Days")
```

## Internal Name Mappings

This section documents the mapping between internal device names and data fields to ACTRIS database column names.

### Device Type Mappings

| Internal ID | Internal Name | Display Name | Data Class | Database Usage |
|-------------|---------------|--------------|------------|----------------|
| `1` | `CPC` | "CPC" | `CPCData` | Primary measurement device |
| `5` | `RHTP` | "RHTP" | `RHTPData` | Inlet environmental conditions |

### CPC Data Field Mappings

This table shows how internal CPC data fields map to ACTRIS database columns:

| CPCData Field | Data Type | ACTRIS DB Column | DB Type | Notes |
|---------------|-----------|------------------|---------|-------|
| `concentration` | float | `conc` | real | Particle concentration (#/cm³) |
| `temp_saturator` | float | `temp_sat` | real | Saturator temperature (°C) |
| `temp_condenser` | float | `temp_cond` | real | Condenser temperature (°C) |
| `temp_optics` | float | `temp_optics` | real | Optics temperature (°C) |
| `temp_cabin` | float | `temp_cab` | real | Cabinet temperature (°C) |
| `pres_inlet` | float | `pres_inl` | real | Inlet pressure (kPa) |
| `pres_critical_orifice` | float | `diff_pres_orf` | real | Critical orifice pressure drop (kPa) |
| `pres_nozzle` | float | `diff_pres_noz` | real | Nozzle pressure drop (kPa) |
| `pres_cabin` | float | `pres_amb` | real | Ambient/cabin pressure (kPa) |
| `liquid_level` | int | `lvl_liq` | real | Liquid level indicator |
| `total_errors` | int | `stat_log` | integer | Total error count |
| `status_hex` | str | `status_hex` | text | Status flags in hexadecimal |
| `laser_current` | float | `current_laser` | real | Laser current (mA) |
| `pulse_duration` | float | `pulse_height` | real | Average pulse duration (ns) |
| `dead_time` | float | — | — | Not written to database |
| `number_of_pulses` | int | — | — | Not written to database |
| `pulse_ratio` | float | — | — | Not written to database |

### RHTP Data Field Mappings

This table shows how internal RHTP data fields map to ACTRIS database columns (inlet conditions):

| RHTPData Field | Data Type | ACTRIS DB Column | DB Type | Notes |
|----------------|-----------|------------------|---------|-------|
| `humidity` | float | `humidity_inlet` | real | Inlet relative humidity (%) |
| `temperature` | float | `temp_inlet` | real | Inlet temperature (°C) |
| `pressure` | float | `pressure_inlet` | real | Inlet pressure (Pa in data, hPa in DB) |

**Note**: RHTP pressure is stored internally in Pascals but written to the database in hectopascals (hPa).

### UI Column Mappings (ACTRIS Tab)

The ACTRIS tab data table displays the following columns with their corresponding database fields:

| Column Index | Table Header | ACTRIS DB Column | Editable | Data Type |
|--------------|--------------|------------------|----------|-----------|
| 0 | "Start" | `starttime` | No | timestamp |
| 1 | "End" | `time` | No | timestamp |
| 2 | "Conc" | `conc` | Yes | float |
| 3 | "Flow In" | `flow_inl` | Yes | float |
| 4 | "T Sat" | `temp_sat` | Yes | float |
| 5 | "T Cond" | `temp_cond` | Yes | float |
| 6 | "T Inlet" | `temp_inlet` | Yes | float |
| 7 | "P Inlet" | `pressure_inlet` | Yes | float |
| 8 | "RH In" | `humidity_inlet` | Yes | float |
| 9 | "Pulse" | `pulse_height` | Yes | float |
| 10 | "Err" | `stat_log` | Yes | int |
| 11 | "Status" | `status_hex` | Yes | str |

**Edit functionality**: Double-click any cell in columns 2-11 to edit the value. Changes are immediately written to the database.

### Data Flow Summary

```
┌─────────────┐         ┌──────────────┐         ┌──────────────┐
│  CPC Device │ ──1Hz──>│ CPCData      │ ──avg──>│ ACTRIS DB    │
│  (Serial)   │         │ concentration│         │ conc         │
│             │         │ temp_sat     │         │ temp_sat     │
│             │         │ temp_cond    │         │ temp_cond    │
│             │         │ ...          │         │ ...          │
└─────────────┘         └──────────────┘         └──────────────┘

┌─────────────┐         ┌──────────────┐         ┌──────────────┐
│ RHTP Device │ ──1Hz──>│ RHTPData     │ ──avg──>│ ACTRIS DB    │
│  (Serial)   │         │ humidity     │         │ humidity_inl │
│             │         │ temperature  │         │ temp_inlet   │
│             │         │ pressure     │         │ pressure_inl │
└─────────────┘         └──────────────┘         └──────────────┘
```

**Averaging Process**:
1. Raw 1 Hz data collected in `CPCData` and `RHTPData` objects
2. Data accumulated in `CPCDataAverager` buffer
3. At interval boundary, arithmetic mean calculated for most fields
4. Status fields (`stat_log`, `status_hex`) use last value in interval
5. Single averaged record written to `cpc_measurements` table

**Code References**:
- Device constants: `src/config.py:15-25`
- Data classes: `src/devices/device_data.py:10-120`
- Database schema: `src/managers/database_manager.py:50-150`
- Write operations: `src/managers/database_manager.py:200-350`
- UI table: `src/devices/cpc.py:1200-1400`

## Related Documentation

- **[README.md](README.md)**: General application documentation and quick start
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)**: Developer documentation for extending the codebase
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System architecture and design patterns

## Support

For issues or questions:
1. Check this documentation
2. Review `debug.log` for error details
3. Submit issue on GitHub repository
4. Contact Airmodus support

---

**ACTRIS Compliance Note**: This database format is designed to support ACTRIS (Aerosol, Clouds and Trace Gases Research Infrastructure) data requirements for long-term atmospheric observations. Ensure your PostgreSQL instance has adequate backup and archival procedures for scientific data preservation.
