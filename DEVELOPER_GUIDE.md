# Airmodus MultiLogger - Developer Guide

**Version**: 0.11.0
**Last Updated**: November 2025

This guide provides step-by-step instructions for developers to extend the Airmodus MultiLogger application, with a focus on adding new devices.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Adding a New Device](#adding-a-new-device)
3. [Device Implementation Details](#device-implementation-details)
4. [Testing Your Device](#testing-your-device)
5. [Advanced Features](#advanced-features)
6. [Coding Conventions](#coding-conventions)
7. [Migration Guide](#migration-guide)
8. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Development Environment Setup

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd Airmodus_MultiLogger
   conda env create -f environment.yaml
   conda activate multilogger-env
   ```

2. **Understand the architecture**:
   - Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design details
   - Review existing device implementations in `src/devices/`
   - Examine the `example_device.py` template

3. **Key files to know**:
   - `src/config.py`: Device type constants
   - `src/devices/base_device.py`: Abstract base classes
   - `src/devices/registry.py`: Device registration system
   - `src/devices/device_data.py`: Data class definitions
   - `src/plotting/device_plot_configs.py`: Plot configurations
   - `src/devices/data_writers.py`: Data file writers

---

## Adding a New Device

This section provides a complete walkthrough for adding a new device type to the MultiLogger.

### Overview

Adding a new device requires creating 6 components:

1. **Device Type Constant** - Unique identifier
2. **Data Class** - Typed data structure for measurements
3. **Settings Class** - (Optional) Typed data structure for device settings
4. **Plot Configuration** - How to plot the device's data
5. **Data Writer** - How to write data to files
6. **Device Widget** - Main device implementation

Let's walk through each step with a complete example.

### Example: Adding a Flow Meter Device

We'll create a simple flow meter that measures volumetric flow rate in L/min.

---

### Step 1: Define Device Type Constant

**File**: `src/config.py`

Add a unique integer constant for your device type:

```python
# Device type constants
CPC = 0
PSM_RETROFIT = 1
PSM_2 = 2
ELECTROMETER = 3
CO2 = 4
RHTP = 5
AFM = 6
EDILUTER = 7
TSI_CPC = 8
EXAMPLE_DEVICE = 9
FLOW_METER = 10  # ← Add your new device
```

**Guidelines**:
- Use the next available integer
- Use UPPERCASE with underscores
- Choose a descriptive name

---

### Step 2: Create Data Class

**File**: `src/devices/device_data.py`

Define a dataclass to hold your device's measurements:

```python
from dataclasses import dataclass
from math import nan

@dataclass
class FlowMeterData:
    """Flow meter measurement data"""
    flow_rate: float = nan          # L/min
    temperature: float = nan        # °C
    pressure: float = nan           # hPa
    status: str = 'Unknown'         # Device status string

    def to_array(self) -> list:
        """Convert to array format"""
        return [
            self.flow_rate,
            self.temperature,
            self.pressure
        ]
```

**Guidelines**:
- Use `@dataclass` decorator
- Initialize numeric fields to `nan` from `math` module
- Initialize string fields to sensible defaults
- Add docstrings describing each field
- Implement `to_array()` method
- Use descriptive field names with units in comments

**Benefits of Dataclasses**:
- Named fields instead of magic indices
- IDE autocomplete support
- Type hints for better tooling
- Self-documenting code

---

### Step 3: Create Settings Class (Optional)

**File**: `src/devices/device_data.py`

If your device has configurable settings (makes it a `ComplexDevice`), create a settings dataclass:

```python
@dataclass
class FlowMeterSettings:
    """Flow meter configuration settings"""
    sampling_rate: int = 1          # Hz
    alarm_threshold: float = 10.0   # L/min
    calibration_factor: float = 1.0 # Dimensionless
```

**Note**: Skip this step if your device is monitor-only (SimpleDevice).

---

### Step 4: Create Plot Configuration

**File**: `src/plotting/device_plot_configs.py`

Define how your device's data should be plotted:

```python
from plotting.base_plot_config import BasePlotConfig

class FlowMeterPlotConfig(BasePlotConfig):
    """Flow meter plotting configuration"""

    def get_plot_keys(self) -> list[str]:
        """
        Return list of plot array keys needed.

        Keys are appended to device ID:
        - '' (empty string) = main plot (e.g., '0')
        - '_temp' = auxiliary plot (e.g., '0_temp')
        """
        return ['', '_temp', '_pressure']

    def get_plot_values(self, dev_id, time_counter, plot_data,
                       device_param, data_holder):
        """
        Extract values from device data into plot arrays.

        Args:
            dev_id: Device ID (0, 1, 2, ...)
            time_counter: Current time index
            plot_data: Dictionary of numpy arrays
            device_param: Device's parameter tree entry
            data_holder: Central data storage
        """
        # Main plot shows flow rate
        plot_data[str(dev_id)][time_counter] = \
            self.device.current_data.flow_rate

        # Auxiliary plots for other measurements
        plot_data[f'{dev_id}_temp'][time_counter] = \
            self.device.current_data.temperature

        plot_data[f'{dev_id}_pressure'][time_counter] = \
            self.device.current_data.pressure

    def update_main_plot(self, curve, data):
        """
        Optional: Custom main plot rendering.
        Default implementation just calls curve.setData(data).
        """
        # Use default implementation
        super().update_main_plot(curve, data)

    def update_individual_plots(self, plot_data):
        """
        Optional: Update device's individual plot tabs.
        Only needed if your device has custom plot tabs.
        """
        pass  # No custom plots for this simple device
```

**Key Methods**:

| Method | Required | Purpose |
|--------|----------|---------|
| `get_plot_keys()` | Yes | Define which plot arrays to create |
| `get_plot_values()` | Yes | Extract data into plot arrays |
| `update_main_plot()` | No | Custom rendering for main plot |
| `update_individual_plots()` | No | Update device-specific plot tabs |

**Plot Key Naming**:
- `''` (empty string): Main plot value
- `'_suffix'`: Auxiliary plots (temperature, pressure, etc.)
- Keys become: `{dev_id}{suffix}` (e.g., `'0'`, `'0_temp'`)

---

### Step 5: Create Data Writer

**File**: `src/devices/data_writers.py`

Define how your device's data is written to files:

```python
from devices.base_data_writer import BaseDataWriter
from utils import get_timestamp

class FlowMeterDataWriter(BaseDataWriter):
    """Flow meter data file writer"""

    def get_dat_header(self) -> str:
        """Return .dat file header line"""
        return 'YYYY.MM.DD hh:mm:ss,Flow Rate (L/min),Temperature (C),Pressure (hPa),Status'

    def get_dat_data(self, time_counter, params) -> str:
        """Return .dat file data line"""
        timestamp = get_timestamp(time_counter)
        data = self.device.current_data

        return (f'{timestamp},'
                f'{data.flow_rate:.2f},'
                f'{data.temperature:.1f},'
                f'{data.pressure:.1f},'
                f'{data.status}')

    def supports_par_file(self) -> bool:
        """Does this device write a .par (parameters) file?"""
        return False  # Simple device, no settings to log

    def get_par_header(self) -> str:
        """Return .par file header (only if supports_par_file = True)"""
        raise NotImplementedError('Flow meter does not support .par files')

    def get_par_data(self, time_counter, params) -> str:
        """Return .par file data line (only if supports_par_file = True)"""
        raise NotImplementedError('Flow meter does not support .par files')
```

**For Complex Devices with Settings**:

```python
class FlowMeterDataWriter(BaseDataWriter):
    # ... dat methods same as above ...

    def supports_par_file(self) -> bool:
        return True  # We have settings to log

    def get_par_header(self) -> str:
        return 'YYYY.MM.DD hh:mm:ss,Sampling Rate (Hz),Alarm Threshold (L/min),Calibration'

    def get_par_data(self, time_counter, params) -> str:
        timestamp = get_timestamp(time_counter)
        settings = self.device.settings

        return (f'{timestamp},'
                f'{settings.sampling_rate},'
                f'{settings.alarm_threshold:.1f},'
                f'{settings.calibration_factor:.3f}')
```

**Key Methods**:

| Method | Required | Purpose |
|--------|----------|---------|
| `get_dat_header()` | Yes | Column headers for .dat file |
| `get_dat_data()` | Yes | Data line for .dat file |
| `supports_par_file()` | Yes | Whether device has .par file |
| `get_par_header()` | If supports_par | Column headers for .par file |
| `get_par_data()` | If supports_par | Data line for .par file |

---

### Step 6: Create Device Widget

**File**: `src/devices/flow_meter.py` (create new file)

This is the main device implementation:

```python
"""Flow Meter Device Implementation"""
from PyQt5 import QtWidgets
from devices.base_device import SimpleDevice
from devices.registry import register_device
from devices.device_data import FlowMeterData
from devices.data_writers import FlowMeterDataWriter
from plotting.device_plot_configs import FlowMeterPlotConfig
from config import FLOW_METER
import logging

@register_device(FLOW_METER)
class FlowMeterWidget(SimpleDevice):
    """Flow meter device widget"""

    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=FLOW_METER)

        # Initialize data storage
        self.current_data = FlowMeterData()
        self.settings = None  # SimpleDevice has no settings

        # Initialize composition objects
        self.plot_config = FlowMeterPlotConfig(self)
        self.data_writer = FlowMeterDataWriter(self)

        # Build GUI
        self._create_ui()

    def _create_ui(self):
        """Create device's tab interface"""
        # Create a simple display tab
        display_tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()

        # Add value labels
        self.flow_label = QtWidgets.QLabel('Flow Rate: -- L/min')
        self.temp_label = QtWidgets.QLabel('Temperature: -- °C')
        self.pressure_label = QtWidgets.QLabel('Pressure: -- hPa')
        self.status_label = QtWidgets.QLabel('Status: Unknown')

        layout.addWidget(self.flow_label)
        layout.addWidget(self.temp_label)
        layout.addWidget(self.pressure_label)
        layout.addWidget(self.status_label)
        layout.addStretch()

        display_tab.setLayout(layout)
        self.addTab(display_tab, 'Flow Meter')

    # ===================================================================
    # Abstract method implementations (REQUIRED)
    # ===================================================================

    def get_read_command(self) -> str:
        """
        Return serial command to request data, or None for auto-push.

        For devices that push data automatically, return None.
        For request-response devices, return the command string.
        """
        return None  # Flow meter auto-pushes data

    def parse_message(self, message: str, data_holder=None):
        """
        Parse a serial message from the device.

        Args:
            message: Raw serial message (without terminator)
            data_holder: Optional reference to DataHolder

        Returns:
            ParseResult indicating success/failure
        """
        try:
            # Handle IDN response if device supports it
            if self.is_idn_response(message):
                return self.handle_standard_idn(message)

            # Parse data message
            # Expected format: "12.5,23.1,1013.2,OK"
            parts = message.split(',')

            if len(parts) != 4:
                return self.error_response(message,
                    f'Expected 4 fields, got {len(parts)}')

            # Update current data
            self.current_data.flow_rate = float(parts[0])
            self.current_data.temperature = float(parts[1])
            self.current_data.pressure = float(parts[2])
            self.current_data.status = parts[3].strip()

            # Update GUI labels
            self.flow_label.setText(
                f'Flow Rate: {self.current_data.flow_rate:.2f} L/min')
            self.temp_label.setText(
                f'Temperature: {self.current_data.temperature:.1f} °C')
            self.pressure_label.setText(
                f'Pressure: {self.current_data.pressure:.1f} hPa')
            self.status_label.setText(
                f'Status: {self.current_data.status}')

            return self.data_response(message, 'data')

        except ValueError as e:
            logging.error(f'Flow meter parse error: {e}')
            return self.error_response(message,
                f'Parse error: {str(e)}')
        except Exception as e:
            logging.error(f'Flow meter unexpected error: {e}')
            return self.error_response(message,
                f'Unexpected error: {str(e)}')

    # ===================================================================
    # Optional lifecycle hooks (override if needed)
    # ===================================================================

    def on_connection_established(self):
        """Called once when device connects"""
        logging.info(f'Flow meter {self.device_id} connected')
        # Reset data to initial state
        self.current_data = FlowMeterData()

    def on_disconnection(self):
        """Called once when device disconnects"""
        logging.info(f'Flow meter {self.device_id} disconnected')
        # Clear GUI
        self.flow_label.setText('Flow Rate: -- L/min')
        self.temp_label.setText('Temperature: -- °C')
        self.pressure_label.setText('Pressure: -- hPa')
        self.status_label.setText('Status: Disconnected')

    # ===================================================================
    # Optional capability flags (override if needed)
    # ===================================================================

    def supports_idn_inquiry(self) -> bool:
        """Does device respond to *IDN? command?"""
        return True  # Yes, supports identification

    def supports_firmware_inquiry(self) -> bool:
        """Does device have firmware version?"""
        return False  # No firmware version

    def has_command_widget(self) -> bool:
        """Does device have a command interface tab?"""
        return False  # No manual commands

    def has_status_tab(self) -> bool:
        """Does device have a status display tab?"""
        return False  # No special status tab
```

**Key Components**:

1. **@register_device decorator**: Automatically registers device type
2. **Inherit from SimpleDevice or ComplexDevice**: Determines capabilities
3. **Initialize composition objects**: data, plot_config, data_writer
4. **Implement abstract methods**: get_read_command(), parse_message()
5. **Override lifecycle hooks**: (optional) connection events
6. **Create GUI**: Device-specific tabs and widgets

---

### Step 7: Update Device Names

**File**: `src/managers/data_holder.py`

Add your device to the name mapping:

```python
class DataHolder:
    def __init__(self):
        # ... other initialization ...

        self.device_names = {
            CPC: 'CPC',
            PSM_RETROFIT: 'PSM Retrofit',
            PSM_2: 'PSM 2.0',
            ELECTROMETER: 'Electrometer',
            CO2: 'CO2',
            RHTP: 'RHTP',
            AFM: 'AFM',
            EDILUTER: 'eDiluter',
            TSI_CPC: 'TSI CPC',
            EXAMPLE_DEVICE: 'Example Device',
            FLOW_METER: 'Flow Meter',  # ← Add your device
        }
```

---

### Step 8: Add to Parameter Tree

**File**: `src/params.py`

Add your device to the "Add Device" dropdown:

```python
def create_device_params():
    # ... existing code ...

    opts["addList"] = [
        "CPC",
        "PSM Retrofit",
        "PSM 2.0",
        "Electrometer",
        "CO2",
        "RHTP",
        "AFM",
        "eDiluter",
        "TSI CPC",
        "Example Device",
        "Flow Meter",  # ← Add your device
    ]
```

---

### Step 9: Import Your Device Module

**File**: `src/app.py`

Add import for your device module to ensure the decorator runs:

```python
# Device imports (ensures @register_device decorators run)
from devices.cpc import CPCWidget
from devices.psm import PSMWidget
# ... other imports ...
from devices.flow_meter import FlowMeterWidget  # ← Add your import
```

---

## Device Implementation Details

### SimpleDevice vs ComplexDevice

**When to use SimpleDevice**:
- Device only monitors (no control)
- Auto-push communication (no commands to send)
- No configurable settings
- Examples: RHTP, AFM, CO2, Electrometer

**When to use ComplexDevice**:
- Device has control interface
- Request-response communication
- Configurable settings
- Command widget for manual commands
- Status display tab
- Examples: CPC, PSM, eDiluter

**ComplexDevice Template**:

```python
@register_device(MY_DEVICE)
class MyDeviceWidget(ComplexDevice):
    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=MY_DEVICE)

        # Initialize data AND settings
        self.current_data = MyDeviceData()
        self.settings = MyDeviceSettings()

        # Composition objects
        self.plot_config = MyDevicePlotConfig(self)
        self.data_writer = MyDeviceDataWriter(self)

        # Additional tabs
        self.command_widget = CommandWidget(self)
        self.status_tab = StatusTab(self)

        self.addTab(self.command_widget, 'Commands')
        self.addTab(self.status_tab, 'Status')

    def get_read_command(self):
        return ':READ:DATA\r\n'  # Request-response

    def send_read_commands(self, connection, params):
        """Override to send multiple commands"""
        # Always request data
        connection.write(':READ:DATA\r\n')

        # Conditionally request settings
        if params['Settings']['Read Settings']:
            connection.write(':READ:SETTINGS\r\n')

    def parse_message(self, message, data_holder=None):
        # Handle different message types
        if message.startswith(':DATA:'):
            return self._parse_data(message)
        elif message.startswith(':SETTINGS:'):
            return self._parse_settings(message)
        elif self.is_idn_response(message):
            return self.handle_standard_idn(message)
        else:
            return self.error_response(message, 'Unknown message type')
```

### Parsing Messages

**Best Practices**:

```python
def parse_message(self, message, data_holder=None):
    """Parse device messages with robust error handling"""
    try:
        # 1. Handle special message types first
        if self.is_idn_response(message):
            return self.handle_standard_idn(message)

        # 2. Validate message format
        if not message.startswith(':DATA:'):
            return self.error_response(message,
                'Expected :DATA: prefix')

        # 3. Extract and validate fields
        data_str = message[6:]  # Remove ':DATA:' prefix
        fields = data_str.split(',')

        if len(fields) != EXPECTED_COUNT:
            return self.error_response(message,
                f'Expected {EXPECTED_COUNT} fields, got {len(fields)}')

        # 4. Parse each field with type conversion
        self.current_data.value1 = float(fields[0])
        self.current_data.value2 = float(fields[1])
        self.current_data.status = fields[2].strip()

        # 5. Validate ranges (optional)
        if self.current_data.value1 < 0:
            logging.warning('Negative value detected')

        # 6. Update GUI if needed
        self._update_display()

        # 7. Return success
        return self.data_response(message, 'data')

    except ValueError as e:
        # Handle conversion errors
        logging.error(f'Parse error: {e}')
        return self.error_response(message, f'Conversion error: {e}')

    except IndexError as e:
        # Handle missing fields
        logging.error(f'Missing fields: {e}')
        return self.error_response(message, 'Missing fields')

    except Exception as e:
        # Catch-all for unexpected errors
        logging.error(f'Unexpected error: {e}', exc_info=True)
        return self.error_response(message, f'Unexpected: {e}')
```

**ParseResult Types**:

```python
# Success responses
self.data_response(message, 'data')        # Data parsed successfully
self.data_response(message, 'settings')    # Settings parsed
self.data_response(message, 'idn')         # IDN response

# Error response
self.error_response(message, 'Error description')
```

### Serial Communication Patterns

**Auto-Push Device** (SimpleDevice):

```python
def get_read_command(self):
    return None  # Device sends data automatically

# Device sends: "12.5,23.1,1013.2\r" every second
# No command needed
```

**Request-Response Device** (ComplexDevice):

```python
def get_read_command(self):
    return ':READ:DATA\r\n'

# Application sends: ":READ:DATA\r\n"
# Device responds: ":DATA:12.5,23.1,1013.2\r"
```

**Multi-Command Device**:

```python
def send_read_commands(self, connection, params):
    """Override to send multiple commands"""
    # Always request data
    connection.write(':READ:DATA\r\n')

    # Conditionally request other info
    if self.request_settings:
        connection.write(':READ:SETTINGS\r\n')

    if self.request_status:
        connection.write(':READ:STATUS\r\n')
```

**Expected Timing**:
- Commands sent at `t = 0ms`
- Responses read at `t = 600ms`
- Your device should respond within 500ms

### Lifecycle Hooks

**Connection Established**:

```python
def on_connection_established(self):
    """Called once when device connects"""
    logging.info(f'{self.device_name} connected')

    # Reset data to clean state
    self.current_data = MyDeviceData()

    # Send initialization commands
    if hasattr(self, 'connection'):
        self.connection.write(':INIT\r\n')

    # Update GUI
    self.status_label.setText('Connected')
    self.status_label.setStyleSheet('color: green')
```

**Disconnection**:

```python
def on_disconnection(self):
    """Called once when device disconnects"""
    logging.info(f'{self.device_name} disconnected')

    # Clean up resources
    self.stop_background_tasks()

    # Update GUI
    self.status_label.setText('Disconnected')
    self.status_label.setStyleSheet('color: grey')
```

**10Hz Mode Validation** (CPC-specific):

```python
def validate_10hz_mode(self):
    """Called to check if 10Hz mode is active"""
    # Check if averaging time is set to 0.1s
    return self.settings.averaging_time == 0.1
```

---

## Testing Your Device

### 1. Unit Testing (Parsing)

Create a test file: `tests/test_flow_meter.py`

```python
import unittest
from devices.flow_meter import FlowMeterWidget
from PyQt5.QtWidgets import QApplication
import sys

class TestFlowMeterParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Create QApplication (required for Qt widgets)"""
        cls.app = QApplication(sys.argv)

    def setUp(self):
        """Create device instance for each test"""
        # Create mock parameter
        from params import create_device_params
        self.param = create_device_params(0)
        self.device = FlowMeterWidget(self.param)

    def test_parse_valid_message(self):
        """Test parsing a valid data message"""
        message = "12.5,23.1,1013.2,OK"
        result = self.device.parse_message(message)

        self.assertTrue(result.success)
        self.assertEqual(result.message_type, 'data')
        self.assertEqual(self.device.current_data.flow_rate, 12.5)
        self.assertEqual(self.device.current_data.temperature, 23.1)
        self.assertEqual(self.device.current_data.pressure, 1013.2)
        self.assertEqual(self.device.current_data.status, 'OK')

    def test_parse_invalid_field_count(self):
        """Test parsing with wrong number of fields"""
        message = "12.5,23.1"  # Only 2 fields instead of 4
        result = self.device.parse_message(message)

        self.assertFalse(result.success)
        self.assertIn('Expected 4 fields', result.error_message)

    def test_parse_invalid_number(self):
        """Test parsing with non-numeric value"""
        message = "ABC,23.1,1013.2,OK"
        result = self.device.parse_message(message)

        self.assertFalse(result.success)
        self.assertIn('error', result.error_message.lower())

    def test_idn_response(self):
        """Test IDN response parsing"""
        message = "Airmodus,FlowMeter,SN12345,v1.0"
        result = self.device.parse_message(message)

        self.assertTrue(result.success)
        self.assertEqual(result.message_type, 'idn')

if __name__ == '__main__':
    unittest.main()
```

Run tests:
```bash
python -m unittest tests/test_flow_meter.py
```

### 2. Integration Testing (Live Device)

**Test Checklist**:

1. **Connection**:
   - [ ] Device appears in parameter tree
   - [ ] Correct COM port selection
   - [ ] Connection status updates (grey → green)
   - [ ] IDN response received (if supported)

2. **Data Reception**:
   - [ ] parse_message() handles all message types
   - [ ] current_data fields update correctly
   - [ ] No exceptions in debug.log
   - [ ] GUI displays update

3. **Plotting**:
   - [ ] Main plot shows correct values
   - [ ] Auxiliary plots (if any) work
   - [ ] Legend shows device nickname
   - [ ] Plot color is unique

4. **Data Logging**:
   - [ ] .dat file created with correct name
   - [ ] Header row is correct
   - [ ] Data rows are correctly formatted
   - [ ] Timestamp format is correct
   - [ ] .par file (if applicable)

5. **Disconnection**:
   - [ ] Device handles disconnect gracefully
   - [ ] Reconnection works
   - [ ] No crashes

6. **Configuration Save/Load**:
   - [ ] Device parameters save correctly
   - [ ] Device parameters restore correctly
   - [ ] Device widget recreated correctly

### 3. Serial Communication Testing

**Without Physical Device** (Simulated):

Use a serial port emulator like `com0com` (Windows) or `socat` (Linux):

```bash
# Linux: Create virtual serial port pair
socat -d -d pty,raw,echo=0 pty,raw,echo=0
# Outputs: N PTY is /dev/pts/2
#          N PTY is /dev/pts/3

# Connect MultiLogger to /dev/pts/2
# Send test data to /dev/pts/3
echo "12.5,23.1,1013.2,OK" > /dev/pts/3
```

**With Physical Device**:

Use a serial terminal (PuTTY, RealTerm) to verify:

1. **Device sends expected format**:
   ```
   12.5,23.1,1013.2,OK\r
   ```

2. **Device responds to commands**:
   ```
   Send: :READ:DATA\r\n
   Receive: :DATA:12.5,23.1,1013.2,OK\r
   ```

3. **IDN response** (if supported):
   ```
   Send: *IDN?\r\n
   Receive: Airmodus,FlowMeter,SN12345,v1.0\r
   ```

---

## Advanced Features

### Custom Plot Tabs

Add device-specific plot widgets:

```python
class FlowMeterWidget(SimpleDevice):
    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=FLOW_METER)
        # ... standard initialization ...

        # Create custom plot tab
        from plots.single_plot import SinglePlot
        self.flow_plot = SinglePlot(device_type=FLOW_METER)
        self.addTab(self.flow_plot, 'Flow History')

    def update_custom_plots(self, plot_data):
        """Called by plot manager to update custom plots"""
        # Update the custom plot with device data
        self.flow_plot.update_plot(plot_data[f'{self.device_id}'])
```

### Command Widget

Add manual command interface (ComplexDevice):

```python
from widgets import CommandWidget

class FlowMeterWidget(ComplexDevice):
    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=FLOW_METER)

        # Create command widget
        self.command_widget = CommandWidget(self)
        self.addTab(self.command_widget, 'Commands')

        # Connect command signal
        self.command_widget.command_sent.connect(self.send_command)

    def send_command(self, command):
        """Send manual command to device"""
        if self.device_id in self.connections:
            connection = self.connections[self.device_id]
            connection.write(command + '\r\n')
            logging.info(f'Sent command: {command}')
```

### Settings Widget

Add configurable settings (ComplexDevice):

```python
from PyQt5 import QtWidgets

class FlowMeterWidget(ComplexDevice):
    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=FLOW_METER)

        # Create settings tab
        self.settings_tab = QtWidgets.QWidget()
        self._create_settings_ui()
        self.addTab(self.settings_tab, 'Settings')

    def _create_settings_ui(self):
        """Build settings UI"""
        layout = QtWidgets.QFormLayout()

        # Sampling rate spinbox
        self.sampling_rate_spin = QtWidgets.QSpinBox()
        self.sampling_rate_spin.setRange(1, 100)
        self.sampling_rate_spin.setValue(self.settings.sampling_rate)
        self.sampling_rate_spin.valueChanged.connect(self.update_sampling_rate)
        layout.addRow('Sampling Rate (Hz):', self.sampling_rate_spin)

        # Alarm threshold spinbox
        self.alarm_spin = QtWidgets.QDoubleSpinBox()
        self.alarm_spin.setRange(0, 100)
        self.alarm_spin.setValue(self.settings.alarm_threshold)
        self.alarm_spin.valueChanged.connect(self.update_alarm)
        layout.addRow('Alarm Threshold (L/min):', self.alarm_spin)

        # Apply button
        apply_btn = QtWidgets.QPushButton('Apply Settings')
        apply_btn.clicked.connect(self.apply_settings)
        layout.addRow(apply_btn)

        self.settings_tab.setLayout(layout)

    def apply_settings(self):
        """Send updated settings to device"""
        command = (f':WRITE:SETTINGS:'
                  f'{self.settings.sampling_rate},'
                  f'{self.settings.alarm_threshold}')

        if self.device_id in self.connections:
            self.connections[self.device_id].write(command + '\r\n')
```

### Special File Types

**10Hz Data Logging** (like CPC):

```python
class FlowMeterDataWriter(BaseDataWriter):
    def __init__(self, device):
        super().__init__(device)
        self.high_freq_buffer = []

    def write_high_frequency_data(self, file_handle):
        """Write buffered high-frequency data"""
        if self.high_freq_buffer:
            for line in self.high_freq_buffer:
                file_handle.write(line + '\n')
            self.high_freq_buffer.clear()
```

**Pulse Analysis** (like CPC):

```python
def run_pulse_analysis(self):
    """Scan and analyze detector pulses"""
    results = []
    for threshold in range(15, 1500, 10):
        # Send threshold command
        self.send_command(f':SET:THRESHOLD:{threshold}')
        time.sleep(0.5)

        # Read pulse duration
        duration = self.current_data.pulse_duration
        results.append((threshold, duration))

    # Save results
    self.save_pulse_analysis(results)
```

### Device Linking (PSM-CPC Style)

```python
class PSMWidget(ComplexDevice):
    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=PSM_2)
        self.linked_cpc_id = None

    def link_cpc(self, cpc_id):
        """Link this PSM to a CPC"""
        self.linked_cpc_id = cpc_id
        logging.info(f'PSM {self.device_id} linked to CPC {cpc_id}')

    def get_linked_cpc_data(self, data_holder):
        """Get data from linked CPC"""
        if self.linked_cpc_id is not None:
            cpc = data_holder.devices.get(self.linked_cpc_id)
            if cpc:
                return cpc.current_data
        return None
```

---

## Coding Conventions

### Style Guidelines

**Follow PEP 8**:
- 4 spaces for indentation
- Max line length: 100 characters
- Two blank lines between top-level definitions
- Use descriptive variable names

**Naming Conventions**:
```python
# Constants: UPPER_CASE
FLOW_METER = 10
MAX_TIMEOUT = 5.0

# Classes: PascalCase
class FlowMeterWidget(SimpleDevice):
    pass

# Functions/methods: snake_case
def parse_message(self, message):
    pass

# Private methods: _leading_underscore
def _update_display(self):
    pass

# Variables: snake_case
flow_rate = 12.5
current_data = FlowMeterData()
```

### Documentation

**Docstrings** (Google style):

```python
def parse_message(self, message, data_holder=None):
    """
    Parse a serial message from the flow meter.

    Expects format: "flow,temp,pressure,status"
    Example: "12.5,23.1,1013.2,OK"

    Args:
        message: Raw serial message without terminators
        data_holder: Optional reference to central data storage

    Returns:
        ParseResult: Success/failure with message type and errors

    Raises:
        None - All exceptions caught and returned as error responses
    """
```

**Type Hints**:

```python
from typing import Optional, List, Dict

def get_plot_keys(self) -> List[str]:
    return ['', '_temp']

def parse_message(self, message: str, data_holder: Optional[DataHolder] = None) -> ParseResult:
    pass
```

### Logging

**Use logging module**:

```python
import logging

# Info: Normal operation
logging.info('Flow meter connected')

# Warning: Unexpected but handled
logging.warning('Negative flow rate detected')

# Error: Exception or failure
logging.error(f'Parse error: {e}')

# Debug: Detailed diagnostic info
logging.debug(f'Received message: {message}')

# Critical: Severe error
logging.critical('Device firmware mismatch')

# Exception: Auto-includes traceback
try:
    value = float(field)
except ValueError as e:
    logging.exception('Conversion failed')
```

**Log Levels in MultiLogger**:
- Default: INFO
- Debug mode: DEBUG
- Logs written to: `debug.log`

### Error Handling

**Principle**: Never crash, always log

```python
def parse_message(self, message, data_holder=None):
    try:
        # Main parsing logic
        fields = message.split(',')
        self.current_data.value = float(fields[0])
        return self.data_response(message, 'data')

    except (ValueError, IndexError) as e:
        # Expected errors: log and return error response
        logging.error(f'Parse error: {e}')
        return self.error_response(message, str(e))

    except Exception as e:
        # Unexpected errors: log with traceback
        logging.exception(f'Unexpected error in parse_message')
        return self.error_response(message, f'Unexpected: {e}')
```

---

## Migration Guide

### Updating Legacy Device Code

If you're migrating an existing device from the old architecture:

#### Old Pattern

```python
# In device_manager.py
if dev_type == FLOW_METER:
    connection.write(':READ:DATA\r\n')

# In plot_manager.py
if dev_type == FLOW_METER:
    plot_data[str(dev_id)][time] = device_data[dev_id][0]  # Magic index!

# In data_logger.py
if dev_type == FLOW_METER:
    line = f'{time},{device_data[dev_id][0]},{device_data[dev_id][1]}'
```

#### New Pattern

```python
# All in devices/flow_meter.py
@register_device(FLOW_METER)
class FlowMeterWidget(SimpleDevice):
    def get_read_command(self):
        return ':READ:DATA\r\n'

    def parse_message(self, message):
        self.current_data.flow_rate = float(fields[0])  # Named field!
        return self.data_response(message, 'data')

# In plotting/device_plot_configs.py
class FlowMeterPlotConfig(BasePlotConfig):
    def get_plot_values(self, ...):
        plot_data[str(dev_id)][time] = self.device.current_data.flow_rate

# In devices/data_writers.py
class FlowMeterDataWriter(BaseDataWriter):
    def get_dat_data(self, ...):
        return f'{time},{self.device.current_data.flow_rate}'
```

#### Migration Steps

1. **Create data class** from old array indices
2. **Create device widget** with parse logic
3. **Create plot config** to replace plot_manager code
4. **Create data writer** to replace data_logger code
5. **Remove old if/elif blocks** from managers
6. **Test thoroughly**

---

## Troubleshooting

### Device Not Appearing

**Symptom**: Device not in "Add Device" dropdown

**Fixes**:
1. Check `@register_device` decorator is present
2. Verify device module is imported in `app.py`
3. Check device type constant is defined in `config.py`
4. Verify device name in `params.py` addList

### Connection Fails

**Symptom**: Device stays grey, never connects

**Fixes**:
1. Verify COM port is correct
2. Check device is powered on
3. Test with serial terminal (PuTTY)
4. Check baud rate matches device (default 115200)
5. Look for errors in `debug.log`

```python
# Add custom baud rate
class FlowMeterWidget(SimpleDevice):
    def get_baudrate(self):
        return 19200  # Override default 115200
```

### Parse Errors

**Symptom**: Errors in debug.log, no data updating

**Fixes**:
1. Print raw message in parse_message():
   ```python
   def parse_message(self, message):
       print(f'RAW: {repr(message)}')  # See exact bytes
       # ... rest of parsing
   ```

2. Check for unexpected terminators (`\r`, `\n`)
3. Verify field count and order
4. Check data types (int vs float)

### Plot Not Updating

**Symptom**: Plot stays flat or shows NaN

**Fixes**:
1. Verify `get_plot_keys()` matches `get_plot_values()`
2. Check plot array key naming (`str(dev_id)` vs `f'{dev_id}'`)
3. Ensure parse_message() actually updates current_data
4. Check for NaN values in data

```python
# Debug plot values
def get_plot_values(self, dev_id, time_counter, plot_data, ...):
    value = self.device.current_data.flow_rate
    print(f'Plot value at {time_counter}: {value}')
    plot_data[str(dev_id)][time_counter] = value
```

### File Not Created

**Symptom**: No .dat file when "Save" is checked

**Fixes**:
1. Verify output folder exists and is writable
2. Check device is connected (must be connected to save)
3. Look for file I/O errors in `debug.log`
4. Check `get_dat_header()` and `get_dat_data()` are implemented

### GUI Not Updating

**Symptom**: Data parsing works but GUI doesn't update

**Fixes**:
1. Ensure GUI updates are in parse_message():
   ```python
   def parse_message(self, message):
       # ... parse data ...
       self.flow_label.setText(f'Flow: {self.current_data.flow_rate}')
       # ... return result ...
   ```

2. Check widgets are created in `__init__()`
3. Use Qt signals for thread-safe updates if needed

---

## Best Practices Summary

1. **Always inherit from SimpleDevice or ComplexDevice** - Don't use BaseDevice directly
2. **Use @register_device decorator** - Auto-registers your device
3. **Create typed dataclasses** - Named fields instead of arrays
4. **Implement all abstract methods** - get_read_command(), parse_message()
5. **Use composition** - plot_config, data_writer, current_data
6. **Handle all errors gracefully** - Never crash, always log
7. **Test with real hardware** - Serial emulators miss edge cases
8. **Document message protocols** - Comment expected formats
9. **Use logging extensively** - Makes debugging easier
10. **Follow existing patterns** - Look at similar devices for examples

---

## Additional Resources

- **Architecture Deep Dive**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **User Guide**: [README.md](README.md)
- **Example Device**: `src/devices/example_device.py`
- **Simple Device Example**: `src/devices/rhtp.py`
- **Complex Device Example**: `src/devices/cpc.py`

---

## Getting Help

**Common Questions**:
1. Check this guide first
2. Review ARCHITECTURE.md for design details
3. Look at similar existing devices
4. Check debug.log for error details

**Issues**:
- Use descriptive issue titles
- Include debug.log excerpts
- Provide message examples
- Specify OS and Python version

---

**Happy Developing!**
