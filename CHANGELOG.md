# Airmodus MultiLogger - Software change log

### 0.11.4 - 2026.01.07
- AFC flow value in status bar
- AFC error flag setting
- renamed AFC "Set" tab to "Control"
- removed AFCSettings, moved flow_setpoint to AFCData

### 0.11.3 - 2025.12.15
- AFC device type detection
- AFM value saturator_flow renamed to standard_flow

### 0.11.2 - 2025.12.12
- changed DTR disable to RTS disable (esp32 reboot problem)
- set main plot value when adding device (multi-value devices)
- added send_read_commands() function to AFCWidget

### 0.11.1 - 2025.12.05
- AFC device type (WIP)

### 0.11.0 - 2025.11.10
- Refactor merge

### 0.10.9 - 2025.10.09
- Removed PSM CPC inlet flow reset (when CPC not connected)
- Added pulse quality indicator to CPC status tab

### 0.10.8 - 2025.09.19
- New logo
- Save TSI CPC concentration and dilution correction to PSM file

### 0.10.7 - 2025.08.12
- Simplified ParameterTree structure

### 0.10.6 - 2025.08.11
- Set disconnected device's values to grey
- CSS: ParameterTree (QTreeView) style improvements

### 0.10.5 - 2025.07.03
- Disconnected icon & error flag

### 0.10.4 - 2025.05.15
- PSM liquid level error fix

### 0.10.3 - 2025.05.13
- PSM partial data handling
- PSM extra data handling

### 0.10.2 - 2025.05.12
- PSM Retrofit scan status logging (.dat)
- PSM dilution parameters logging (.par)
- PSM initial nan list fix

### 0.10.1 - 2025.03.17
- CPC pulse quality: pulse ratio index fix
- RHTP & AFM: improved data reading
- Timer fixes: duplicate timestamps, daily file start time
- Example device: irrelevant parameters hidden
- Error handling for ten_hz_check()