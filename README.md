# Airmodus MultiLogger

A desktop application for logging, monitoring, and controlling multiple Airmodus scientific instruments used in aerosol research. Provides real-time data visualization, device control, and comprehensive data logging capabilities.

![Version](https://img.shields.io/badge/version-0.10.9-blue)
![Python](https://img.shields.io/badge/python-3.x-green)

An .exe version of the software can be downloaded from the repository's [Releases](https://github.com/Airmodus/Airmodus_MultiLogger/releases) section.

## Features

- **Multi-Device Support**: Connect and monitor multiple devices simultaneously
- **Real-Time Visualization**: Live plotting of measurements with customizable views
- **Data Logging**: Automatic timestamped data and parameter logging
- **Database Logging**: PostgreSQL integration for time-averaged CPC+RHTP data (ACTRIS-compliant)
- **Device Control**: Configure and control device settings remotely
- **Flexible Configuration**: Save and resume complete application states
- **Auto-Reconnection**: Automatic device detection and reconnection
- **Time Synchronization**: Precise timer system synchronized to system clock

## Supported Devices

| Device | Description | Type |
|--------|-------------|------|
| **CPC** | Condensation Particle Counter (Airmodus) | Complex |
| **PSM Retrofit** | Particle Size Magnifier v1.0 | Complex |
| **PSM 2.0** | Particle Size Magnifier v2.0 | Complex |
| **eDiluter** | Dilution System | Complex |
| **Electrometer** | Voltage Measurement Device | Simple |
| **CO2 Sensor** | Environmental CO2 Monitoring | Simple |
| **RHTP** | Relative Humidity, Temperature, Pressure | Simple |
| **AFM** | Air Flow Meter | Simple |
| **TSI CPC** | TSI Condensation Particle Counter | Simple |

**Device Types:**
- **Complex**: Devices with control interfaces and configurable settings
- **Simple**: Monitor-only devices with automatic data push

## Installation

### Prerequisites

- **Anaconda or Miniconda**: Python distribution with conda package manager ([Installation Guide](https://docs.anaconda.com/anaconda/install/))
- **Windows/Mac/Linux**: Compatible with all major operating systems
- **Serial Port Drivers**: Ensure USB-to-Serial drivers are installed for your devices

### Environment Setup

#### 1. Clone the repository
```bash
git clone <repository-url>
cd Airmodus_MultiLogger
```

#### 2. Create the conda environment
All required [dependencies](#dependencies) are specified in the `environment.yaml` file. Create a new environment using:
```bash
conda env create -f environment.yaml
```

The default environment name is `multilogger-env`. To specify a different name:
```bash
conda env create -f environment.yaml -n env_name
```

#### 3. Activate the environment
```bash
conda activate multilogger-env
```
If you used a different environment name, replace `multilogger-env` with your chosen name.

#### 4. Run the application
Navigate to the repository's `src` folder and run:
```bash
python main.py
```
Or alternatively:
```bash
python app.py
```

## Dependencies

### External Python Packages
- **NumPy**: Array operations and data storage
- **pySerial**: Serial port communication
- **PyQt5**: GUI framework
- **PyQtGraph** (version 0.13.3): Real-time plotting library
- **psycopg2**: PostgreSQL database adapter (for ACTRIS database logging)
- **PyInstaller**: (Optional) For creating standalone executables

### Testing Dependencies (Development)
- **pytest**: Testing framework
- **pytest-qt**: PyQt testing utilities
- **pytest-mock**: Mocking utilities
- **pytest-cov**: Coverage reporting
- **pytest-timeout**: Timeout handling

### Python Standard Library Modules
time, datetime, os, locale, platform, logging, random, traceback, json, warnings, sys

## Quick Start Guide

### 1. Adding a Device

1. Click the **"Add Device"** button in the parameter tree
2. Select the device type from the dropdown menu
3. Configure device parameters:
   - **Nickname**: Custom name for identification
   - **COM Port**: Serial port (e.g., `COM3`, `/dev/ttyUSB0`)
   - **Serial Number**: (Optional) Device serial number
   - **Device Type**: Confirm the selected device type

### 2. Connecting to Devices

Devices automatically connect when:
- The correct COM port is specified
- The device is powered on and connected
- The serial port is not in use by another application

**Connection Status Indicators:**
- **Green checkmark**: Connected and receiving data
- **Grey icon**: Disconnected
- **Red exclamation**: Error state

### 3. Viewing Data

**Main Plot Window:**
- All connected devices share a common time-series plot
- Legend shows device nicknames and current values
- Auto-scaling Y-axis with manual override option

**Individual Device Tabs:**
- Each device has dedicated tabs for detailed views
- Complex devices show control interfaces and settings
- Simple devices show focused data plots

### 4. Data Logging

**Starting Data Logging:**
1. Expand "Data Settings" in the parameter tree
2. Check **"Save"** for the device you want to log
3. Configure:
   - **Folder**: Output directory path
   - **Filename**: Base filename (auto-adds timestamp)
   - **New file at midnight**: Optional daily file rollover

**Output Files:**
- **`.dat`**: Timestamped measurement data (CSV format)
- **`.par`**: Device settings/parameters (for CPC, PSM)
- **`.csv`**: Special logs (10Hz mode, pulse analysis)

**File Format Example** (`.dat`):
```csv
YYYY.MM.DD hh:mm:ss,Concentration,Dead Time,Inlet Temp,...
2025.11.03 10:15:30,1234.5,0.12,25.3,...
2025.11.03 10:15:31,1256.8,0.13,25.3,...
```

### 5. Database Logging (ACTRIS)

The application supports logging CPC data to PostgreSQL with time-averaged measurements for ACTRIS-compliant data archiving.

#### Features
- **Combined CPC+RHTP data**: Links CPC measurements with RHTP environmental data
- **Time averaging**: Configurable intervals (1 minute, 5 minutes, 1 hour)
- **Shared connection**: Multiple CPCs can use the same database connection
- **Automatic table creation**: `cpc_measurements` table created on first connection

#### Database Requirements

**Connection String Format:**
```
postgresql://username:password@host:port/database_name
```

**Examples:**
```bash
# Local database with password
postgresql://postgres:mypassword@localhost:5432/actris_data

# Remote database
postgresql://user:pass@db.example.com:5432/cpc_data

# Local trusted connection (no password)
postgresql://username@localhost:5432/actris_data
```

**Required Permissions:**
The database user must have CREATE privileges on the schema. For PostgreSQL 15+:
```sql
GRANT ALL ON SCHEMA public TO your_username;
```

The application automatically creates the `cpc_measurements` table if it doesn't exist.

#### Using the ACTRIS Tab

1. **Connect a CPC device** to the application
2. **Navigate to the ACTRIS tab** in the CPC device window
3. **Enter connection string** and click "Test Connection"
4. **Link an RHTP device** from the dropdown (required)
5. **Select averaging interval** (1 minute, 5 minutes, or 1 hour)
6. **Enable database** by checking "Enable database for this device"

#### Database Schema

**Table:** `cpc_measurements`

Time-averaged records include:
- **CPC measurements**: Concentration, saturation temp, condenser temp, growth tube temp, optics temp, cabinet temp, inlet flow, critical flow, nozzle flow
- **RHTP data**: Temperature, pressure, relative humidity
- **Metadata**: Timestamp, averaging duration, serial numbers, status flags

All numeric values are averaged over the selected interval. The application writes one record per interval.

#### Troubleshooting

**"permission denied for schema public":**
- Grant CREATE privileges: `GRANT ALL ON SCHEMA public TO your_username;`
- Required for PostgreSQL 15+ by default

**"No RHTP device linked":**
- RHTP must be connected and selected in the ACTRIS tab before enabling database

**Connection string errors:**
- Verify format matches examples above
- Check database credentials and host accessibility
- Use "Test Connection" button to diagnose issues

### 6. Saving and Loading Configuration

**Save Configuration:**
- File → Save Configuration (or Ctrl+S)
- Saves all device settings, parameters, plot configurations, and database connection string to `resume_config.json`

**Auto-Resume:**
- On startup, the application can automatically load the last saved configuration
- Configured via `config.ini` file

**Manual Load:**
- File → Load Configuration
- Select a previously saved `.json` configuration file

## Usage Tips

### Managing Multiple Devices

- **Nicknames**: Use descriptive nicknames to identify devices (e.g., "CPC_Inlet", "CPC_Outlet")
- **Color Coding**: Each device automatically gets a unique plot color
- **Tab Organization**: Device tabs can be rearranged by dragging

### Plot Customization

- **Y-Axis Range**: Right-click plot → "View All" or set manual range
- **Time Window**: Adjust "Plot Settings" → "Plot Length" for visible time span
- **Legend**: Toggle visibility via right-click menu

### Serial Port Tips

**Finding COM Ports:**
- Windows: Device Manager → Ports (COM & LPT)
- Linux: `ls /dev/ttyUSB* /dev/ttyACM*`
- Mac: `ls /dev/tty.usb*`

**Common Issues:**
- **Port in use**: Close other applications using the serial port
- **Permission denied** (Linux): Add user to `dialout` group: `sudo usermod -a -G dialout $USER`
- **Device not found**: Check cable connections and device power

## Special Features

### CPC Pulse Analysis
Monitor detector health by scanning OPC threshold from 15-1500 mV:
1. Navigate to CPC device tab → "Pulse Analysis"
2. Click "Start Scan"
3. Results saved to `_pulse_analysis.csv`

### PSM-CPC Integration
Link a PSM to a CPC for combined measurements:
1. In PSM settings, select linked CPC from dropdown
2. PSM automatically corrects for dilution flow
3. Combined data saved in PSM log files

### 10Hz Mode (CPC)
High-frequency concentration logging:
1. Enable "10Hz mode" in CPC settings
2. Separate `.csv` file created with 10 readings/second
3. Useful for fast transient measurements

## Troubleshooting

### Device Won't Connect

**Check:**
1. COM port is correct and not in use
2. Device is powered on
3. USB cable is functional (try different cable/port)
4. Device firmware is compatible

**Solutions:**
- Close other serial monitor applications
- Restart the application
- Check `debug.log` for detailed error messages

### Data Not Logging

**Check:**
1. "Save" checkbox is enabled for the device
2. Output folder path exists and is writable
3. Sufficient disk space available
4. Device is connected and receiving data

### Plots Not Updating

**Check:**
1. Device is connected (green checkmark)
2. Plot length setting is appropriate for time scale
3. Y-axis auto-scale is enabled or manual range is correct
4. Application window is not minimized (some OS suspend background rendering)

### Application Crashes on Startup

**Solutions:**
1. Delete or rename `resume_config.json` to reset configuration
2. Check Python and package versions match `environment.yaml`
3. Review `debug.log` for error details
4. Reinstall conda environment:
   ```bash
   conda env remove -n multilogger-env
   conda env create -f environment.yaml
   ```

## Configuration Files

### `config.ini`
Runtime configuration for resume functionality:
```ini
[DEFAULT]
resume = True
resume_config_path = resume_config.json
```

### `resume_config.json`
Complete application state including:
- Device configurations and parameters
- Plot settings and preferences
- Data logging paths and filenames
- Window layout and splitter positions

### `debug.log`
Detailed application log including:
- Device connection events
- Serial communication messages
- Error stack traces
- Performance warnings

## Development

For information on extending the application, adding new devices, or understanding the architecture:
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Technical deep dive into system design
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)**: Step-by-step guide for developers
- **[TESTING.md](TESTING.md)**: Comprehensive testing guide

### Running Tests

The project includes a comprehensive test suite for ensuring code quality and preventing regressions:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=html

# Run specific test categories
pytest -m unit          # Fast unit tests
pytest -m integration   # Integration tests
pytest -m gui           # GUI tests
```

See [TESTING.md](TESTING.md) for detailed testing documentation, including how to write new tests and use fixtures.

### Quick Architecture Overview

The application follows a modern **composition-based architecture**:

```
MainWindow (Orchestrator)
    ├── DeviceManager (Connection & Communication)
    ├── PlotManager (Visualization)
    ├── DataLogger (File I/O)
    ├── TimerService (Synchronization)
    └── DataHolder (Storage)
            └── Devices (BaseDevice subclasses)
                    ├── plot_config (BasePlotConfig)
                    ├── data_writer (BaseDataWriter)
                    └── current_data (Device-specific dataclass)
```

### Adding a New Device

Thanks to the refactored architecture, adding a device requires only:
1. Define device type constant
2. Create data class for measurements
3. Create plot configuration
4. Create data writer
5. Create device widget (inherit from `SimpleDevice` or `ComplexDevice`)
6. Register device with `@register_device` decorator

See **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** for detailed instructions.

## Project Structure

```
Airmodus_MultiLogger/
├── src/
│   ├── main.py                 # Application entry point
│   ├── app.py                  # Main window & orchestration
│   ├── config.py               # Constants & configuration
│   ├── params.py               # Parameter tree definition
│   ├── managers/               # Manager classes (device, plot, data, timer)
│   ├── devices/                # Device implementations
│   ├── plotting/               # Plot configurations
│   └── plots/                  # Plot widgets
├── res/                        # Resources (images, icons)
├── environment.yaml            # Conda environment specification
├── config.ini                  # Runtime configuration
└── README.md                   # This file
```

## Version History

**Current Version: 0.10.9**

Recent updates focus on architectural refactoring:
- BaseDevice abstract class for easier device addition
- Typed dataclasses for device data and settings
- Composition pattern (devices own plot_config and data_writer)
- Generic managers with no device-type checking
- Improved maintainability and extensibility

## Acknowledgments

Built with:
- **PyQt5**: Cross-platform GUI framework
- **PyQtGraph**: Fast real-time plotting library
- **NumPy**: Numerical computing
- **pySerial**: Serial communication

---

**Happy Logging!**
