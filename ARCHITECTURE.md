# Airmodus MultiLogger - Architecture Documentation

**Version**: 0.11.0
**Last Updated**: November 2025

This document provides a comprehensive technical deep dive into the Airmodus MultiLogger application architecture, design patterns, data flow, and implementation details.

## Table of Contents

1. [System Overview](#system-overview)
2. [Design Patterns](#design-patterns)
3. [Component Architecture](#component-architecture)
4. [Data Flow](#data-flow)
5. [Device Architecture](#device-architecture)
6. [Manager Classes](#manager-classes)
7. [Serial Communication](#serial-communication)
8. [Timer System](#timer-system)
9. [Configuration Management](#configuration-management)
10. [Migration Notes](#migration-notes)

---

## System Overview

### High-Level Architecture

The Airmodus MultiLogger follows a **modern composition-based architecture** that eliminates device-specific conditional logic in favor of polymorphism and delegation:

```
┌─────────────────────────────────────────────────────────────┐
│                        MainWindow                           │
│                    (Orchestrator/Facade)                    │
│  - Initializes all managers                                 │
│  - Creates GUI (parameter tree, splitters, tabs)            │
│  - Connects signals/slots                                   │
│  - Handles device addition/removal                          │
└───────────────────┬─────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┬───────────┬─────────────┐
        │           │           │           │             │
        ▼           ▼           ▼           ▼             ▼
┌─────────────┐ ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌──────────┐
│DeviceManager│ │Plot     │ │Data      │ │Timer      │ │Data      │
│             │ │Manager  │ │Logger    │ │Service    │ │Holder    │
│- Connections│ │         │ │          │ │           │ │          │
│- Serial I/O │ │- Plots  │ │- Files   │ │- Timing   │ │- Storage │
│- Lifecycle  │ │- Updates│ │- I/O     │ │- Sync     │ │- State   │
└──────┬──────┘ └────┬────┘ └────┬─────┘ └─────┬─────┘ └────┬─────┘
       │             │           │             │             │
       │             │           │             │             │
       └─────────────┴───────────┴─────────────┴─────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  Device Registry       │
                    │  (Centralized lookup)  │
                    └────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
        ┌─────────────────────┐   ┌──────────────────────┐
        │   SimpleDevice      │   │   ComplexDevice      │
        │   (Monitor only)    │   │   (With controls)    │
        ├─────────────────────┤   ├──────────────────────┤
        │ - plot_config       │   │ - plot_config        │
        │ - data_writer       │   │ - data_writer        │
        │ - current_data      │   │ - current_data       │
        │                     │   │ - settings           │
        │ Examples:           │   │                      │
        │ - RHTP              │   │ Examples:            │
        │ - AFM               │   │ - CPC                │
        │ - CO2               │   │ - PSM                │
        │ - Electrometer      │   │ - eDiluter           │
        └─────────────────────┘   └──────────────────────┘
```

### Core Principles

1. **Separation of Concerns**: Each manager handles a single responsibility
2. **Composition over Inheritance**: Devices own helper objects instead of inheriting behavior
3. **Open/Closed Principle**: Easy to extend (add devices) without modifying existing code
4. **Dependency Injection**: Managers receive dependencies via constructor
5. **Type Safety**: Dataclasses provide strongly-typed data structures

---

## Design Patterns

### 1. Facade Pattern

**Location**: `src/app.py::MainWindow`

The `MainWindow` class acts as a facade, providing a simplified interface to the complex subsystem of managers:

```python
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        # Create all subsystems
        self.data_holder = DataHolder()
        self.device_manager = DeviceManager(self.data_holder)
        self.plot_manager = PlotManager(self.data_holder, ...)
        self.data_logger = DataLogger(self.data_holder, ...)
        self.timer_service = TimerService()

        # Wire them together
        self.timer_service.register_callback('connection_test',
                                            self.device_manager.connection_test)
        # ... etc
```

**Benefits**:
- Single point of orchestration
- Hides subsystem complexity from external code
- Easier to understand high-level workflow

### 2. Registry Pattern

**Location**: `src/devices/registry.py`

Centralized device registration using decorator pattern:

```python
# Device type definitions
DEVICE_REGISTRY = {}

@dataclass
class DeviceConfig:
    widget_class: type
    setup_func: callable
    name: str

def register_device(device_type: int):
    """Decorator to register device types"""
    def decorator(widget_class):
        DEVICE_REGISTRY[device_type] = DeviceConfig(
            widget_class=widget_class,
            setup_func=widget_class.setup_device,
            name=widget_class.__name__
        )
        return widget_class
    return decorator

# Usage in device modules:
@register_device(EXAMPLE_DEVICE)
class ExampleDeviceWidget(SimpleDevice):
    pass
```

**Benefits**:
- No manual registration list to maintain
- Device modules are self-contained
- Easier to add/remove devices (just delete the file)
- Supports plugin-style architecture

### 3. Strategy Pattern

**Location**: `src/devices/base_device.py`, `src/plotting/device_plot_configs.py`

Each device has pluggable strategies for plotting and data writing:

```python
class BaseDevice:
    def __init__(self):
        # Composition: device owns its strategies
        self.plot_config = None      # Strategy for plotting
        self.data_writer = None      # Strategy for file writing
        self.current_data = None     # Strategy for data storage

# Concrete implementation
class CPCWidget(ComplexDevice):
    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=CPC)
        self.plot_config = CPCPlotConfig(self)
        self.data_writer = CPCDataWriter(self)
        self.current_data = CPCData()
```

**Benefits**:
- Different plotting/writing algorithms per device
- Strategies can be swapped at runtime if needed
- Each strategy is independently testable

### 4. Template Method Pattern

**Location**: `src/devices/base_device.py`

The `BaseDevice` class defines the skeleton of device operations, with subclasses filling in specific steps:

```python
class BaseDevice(ABC):
    # Template method
    def handle_serial_data(self, connection):
        """Fixed algorithm, calls hooks"""
        raw_data = connection.read_all()
        messages = self._split_messages(raw_data)
        results = []
        for msg in messages:
            result = self.parse_message(msg)  # Hook: subclass implements
            results.append(result)
        return results

    # Hooks (must implement)
    @abstractmethod
    def parse_message(self, message):
        pass

    @abstractmethod
    def get_read_command(self):
        pass

    # Hooks (optional)
    def on_connection_established(self):
        pass  # Default: do nothing

    def on_disconnection(self):
        pass  # Default: do nothing
```

**Benefits**:
- Consistent behavior across all devices
- Subclasses only override what's unique
- Easy to add new lifecycle hooks

### 5. Observer Pattern

**Location**: Throughout via PyQt signals/slots

Qt's signal/slot mechanism implements observer pattern:

```python
# Publisher (DeviceManager)
self.device_connected.emit(device_id)

# Subscriber (PlotManager)
device_manager.device_connected.connect(self.add_device_plot)
```

**Benefits**:
- Loose coupling between components
- Components don't need to know about each other
- Easy to add new subscribers

### 6. Singleton-like Pattern

**Location**: `src/managers/data_holder.py`

While not a strict singleton, DataHolder acts as a single source of truth:

```python
class DataHolder:
    """Centralized data storage with no business logic"""
    def __init__(self):
        self.devices = {}           # All device widgets
        self.plot_data = {}         # All plot arrays
        self.device_names = {...}   # Device type -> name mapping
```

**Benefits**:
- Single source of truth for application state
- Simplifies data sharing between managers
- Easy to serialize for config save/load

---

## Component Architecture

### Entry Point

**File**: `src/main.py`

```python
if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
```

**Alternative Entry**: `src/app.py` (can also be run directly)

### MainWindow (Orchestrator)

**File**: `src/app.py`

**Responsibilities**:
1. Create and initialize all manager instances
2. Build GUI structure (parameter tree, splitters, tabs, plots)
3. Connect manager signals to appropriate handlers
4. Handle high-level events (device add/remove, save/load config)
5. Coordinate manager interactions

**Key Methods**:

| Method | Purpose |
|--------|---------|
| `__init__()` | Initialize managers, build GUI, connect signals |
| `add_device()` | Create new device widget from parameter tree |
| `remove_device()` | Clean up device and notify managers |
| `save_configuration()` | Serialize parameter tree to JSON |
| `load_configuration()` | Restore parameter tree from JSON |
| `handle_timer()` | Trigger manager update methods on timer tick |

### Parameter Tree

**File**: `src/params.py`

**Architecture**:
- Uses PyQtGraph's `ParameterTree` for hierarchical settings
- Custom `ScalableGroup` class allows dynamic child addition
- Parameters are organized in groups:
  - Data Settings (save paths, filenames)
  - Plot Settings (colors, ranges, lengths)
  - Devices (expandable list of device configs)

**Parameter Structure**:
```
Root
├── Data Settings
│   ├── Device 0
│   │   ├── Save (bool)
│   │   ├── Folder (path)
│   │   ├── Filename (string)
│   │   └── New file at midnight (bool)
│   └── Device 1 ...
├── Plot Settings
│   ├── Device 0
│   │   ├── Color (color picker)
│   │   ├── Y-axis min/max (float)
│   │   └── Plot length (seconds)
│   └── Device 1 ...
└── Devices
    ├── Device 0
    │   ├── Nickname (string)
    │   ├── COM Port (string)
    │   ├── Serial Number (string)
    │   ├── Connection (readonly bool)
    │   └── Device Type (list)
    └── Device 1 ...
```

**Key Classes**:

```python
class ScalableGroup(pTypes.GroupParameter):
    """Parameter group that can add/remove children dynamically"""
    def add_child(self):
        child = self.create_child_params()
        self.addChild(child)

    def remove_child(self, child):
        self.removeChild(child)
```

---

## Data Flow

### Complete Data Flow Pipeline

The application operates on a timer-driven cycle (1 second intervals):

```
┌──────────────────────────────────────────────────────────────┐
│                    TIMER TICK (1 second)                     │
└────────────────────┬─────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬─────────────┬──────────┐
        │            │            │             │          │
        ▼            ▼            ▼             ▼          ▼
    [1. Test]   [2. Request] [3. Read]    [4. Plot]  [5. Log]
   Connection    Commands     Data         Update     Data
        │            │            │             │          │
        │            │            │             │          │
        ▼            ▼            ▼             ▼          ▼
```

### 1. Connection Test Phase

**Function**: `DeviceManager.connection_test()`
**Timing**: Every 1 second (on timer tick)
**File**: `src/managers/device_manager.py:67`

```python
def connection_test(self, params):
    """Check and manage serial port connections"""
    for dev_id in range(num_devices):
        com_port = params['Devices'][dev_id]['COM Port']

        # Check if port is available
        if self._is_port_available(com_port):
            if dev_id not in self.connections:
                # Port available and not connected -> CONNECT
                self.connections[dev_id] = SerialDeviceConnection(com_port)
                device.on_connection_established()
                self.idn_inquiry_list.append(dev_id)  # Request ID
        else:
            if dev_id in self.connections:
                # Port unavailable but we're connected -> DISCONNECT
                self.connections[dev_id].close()
                del self.connections[dev_id]
                device.on_disconnection()
```

**Triggers**:
- `device.on_connection_established()`: Called once when connection succeeds
- `device.on_disconnection()`: Called once when connection lost

**Protocol**: IDN Inquiry
```
-> *IDN?\r\n
<- Airmodus,CPC,SN12345,v1.2.3\r
```

### 2. Command Request Phase

**Function**: `DeviceManager.get_dev_data()`
**Timing**: Every 1 second (on timer tick)
**Delay**: 0ms (immediately after connection test)
**File**: `src/managers/device_manager.py:128`

```python
def get_dev_data(self, params):
    """Send read commands to all connected devices"""
    for dev_id, connection in self.connections.items():
        device = self.data_holder.devices[dev_id]

        # Let device send its custom command sequence
        device.send_read_commands(connection, params)

    # Handle IDN inquiry for newly connected devices
    for dev_id in self.idn_inquiry_list:
        if device.supports_idn_inquiry():
            connection.write('*IDN?\r\n')
```

**Device-Specific Commands**:

| Device | Command | Protocol |
|--------|---------|----------|
| CPC | `:READ:DATA\r\n` | Request current measurements |
| PSM Retrofit | `:READ:DATA\r\n` | Request current measurements |
| PSM 2.0 | `:READ:DATA\r\n` | Request current measurements |
| eDiluter | `:READ:DATA\r\n` | Request current measurements |
| Electrometer | `None` | Auto-push (no request needed) |
| RHTP | `None` | Auto-push |
| AFM | `None` | Auto-push |
| CO2 | `None` | Auto-push |
| TSI CPC | `:READ:DATA\r\n` | Request current measurements |

**Example Command Sequence** (CPC):
```python
def send_read_commands(self, connection, params):
    # Always request data
    connection.write(':READ:DATA\r\n')

    # Request settings if enabled
    if params['CPC Settings']['Read Settings']:
        connection.write(':READ:SETTINGS\r\n')
```

### 3. Data Reading & Parsing Phase

**Function**: `DeviceManager.readIndata()`
**Timing**: Every 1 second
**Delay**: 600ms after command request (allows devices to respond)
**File**: `src/managers/device_manager.py:201`

```python
def readIndata(self, params, time_counter):
    """Read and parse serial responses"""
    for dev_id, connection in self.connections.items():
        device = self.data_holder.devices[dev_id]

        # Step 1: Device reads and splits serial buffer
        parsed_messages = device.handle_serial_data(connection)

        # Step 2: Device processes parsed messages
        device.process_parsed_messages(parsed_messages, params)
```

**Serial Protocol Details**:

**Message Format**:
- Commands end with: `\r\n`
- Responses end with: `\r`
- Multiple responses separated by: `\r`

**Message Splitting**:
```python
def handle_serial_data(self, connection):
    raw = connection.read_all()  # e.g., "DATA:1234\rSETTINGS:5678\r"
    messages = raw.split('\r')    # ["DATA:1234", "SETTINGS:5678", ""]
    messages = [m for m in messages if m]  # Remove empty

    results = []
    for message in messages:
        result = self.parse_message(message)  # Device-specific
        results.append(result)
    return results
```

**Parse Result Format**:
```python
@dataclass
class ParseResult:
    message_type: str  # 'data', 'settings', 'error', 'idn', etc.
    success: bool
    raw_message: str
    error_message: str = None
```

**Example CPC Data Message**:
```
Received: ":DATA:1234.5,0.12,25.3,102.5,20.1,0.5,50.3,...\r"

Parsed into CPCData:
    concentration = 1234.5
    dead_time = 0.12
    inlet_temp = 25.3
    saturator_temp = 102.5
    optics_temp = 20.1
    cabin_temp = 0.5
    condensator_temp = 50.3
    ...
```

### 4. Plot Update Phase

**Function**: `PlotManager.update_plot_data()`
**Timing**: Every 1 second
**Delay**: ~650ms (after data reading completes)
**File**: `src/managers/plot_manager.py:145`

```python
def update_plot_data(self, time_counter, params):
    """Extract plot values from device data"""
    for dev_id, device in self.data_holder.devices.items():
        if dev_id in connected_devices:
            # Delegate to device's plot configuration
            device.plot_config.get_plot_values(
                dev_id=dev_id,
                time_counter=time_counter,
                plot_data=self.data_holder.plot_data,
                device_param=params['Devices'][dev_id],
                data_holder=self.data_holder
            )
```

**Plot Data Structure**:
```python
# In DataHolder
self.plot_data = {
    '0': array([nan, nan, 1234.5, 1256.8, ...]),  # Device 0 main values
    '0_dead_time': array([...]),                   # Device 0 auxiliary
    '1': array([...]),                             # Device 1
}
```

**Plot Value Extraction Example** (CPC):
```python
class CPCPlotConfig(BasePlotConfig):
    def get_plot_values(self, dev_id, time_counter, plot_data, ...):
        # Main plot: concentration
        plot_data[str(dev_id)][time_counter] = \
            self.device.current_data.concentration

        # Auxiliary plots
        plot_data[f'{dev_id}_dead_time'][time_counter] = \
            self.device.current_data.dead_time
        plot_data[f'{dev_id}_inlet_temp'][time_counter] = \
            self.device.current_data.inlet_temp
```

**Plot Rendering**:

**Function**: `PlotManager.update_figures_and_menus()`
**Timing**: Every 1 second (after plot data update)

```python
def update_figures_and_menus(self, params):
    """Render plots with latest data"""
    for dev_id, device in self.data_holder.devices.items():
        # Update main plot
        curve = self.main_plot_curves[dev_id]
        data = self.data_holder.plot_data[str(dev_id)]
        device.plot_config.update_main_plot(curve, data)

        # Update individual device plots
        device.plot_config.update_individual_plots(
            self.data_holder.plot_data
        )
```

### 5. Data Logging Phase

**Function**: `DataLogger.write_data()`
**Timing**: Every 1 second
**Delay**: ~700ms (after plot update)
**File**: `src/managers/data_logger.py:156`

```python
def write_data(self, time_counter, params):
    """Write data to files"""
    for dev_id, device in self.data_holder.devices.items():
        if not params['Data Settings'][dev_id]['Save']:
            continue  # Saving disabled

        if dev_id not in connected_devices:
            continue  # Device not connected

        # Create files if needed
        if dev_id not in self.file_handles:
            self._create_files(dev_id, device, params)

        # Get data from device's data writer
        dat_line = device.data_writer.get_dat_data(time_counter, params)
        self.file_handles[dev_id]['dat'].write(dat_line + '\n')

        # Write parameter file if device supports it
        if device.data_writer.supports_par_file():
            par_line = device.data_writer.get_par_data(params)
            self.file_handles[dev_id]['par'].write(par_line + '\n')

        # Flush to ensure data is written
        self.file_handles[dev_id]['dat'].flush()
```

**File Naming Convention**:
```
{nickname}_{YYYYMMDD}_{HHMMSS}.dat
{nickname}_{YYYYMMDD}_{HHMMSS}.par
```

**Example**: `CPC_Inlet_20251103_101530.dat`

**Data File Format** (.dat):
```csv
YYYY.MM.DD hh:mm:ss,Concentration,Dead Time,Inlet Temp,Saturator Temp,...
2025.11.03 10:15:30,1234.5,0.12,25.3,102.5,...
2025.11.03 10:15:31,1256.8,0.13,25.3,102.6,...
```

**Parameter File Format** (.par):
```csv
YYYY.MM.DD hh:mm:ss,Saturator Temp Set,Growth Tube Temp Set,...
2025.11.03 10:15:30,102.0,20.0,...
2025.11.03 10:15:31,102.0,20.0,...
```

**Midnight Rollover**:
- If "New file at midnight" is enabled:
  - At 00:00:00, close current files
  - Create new files with new timestamp
  - Reset 10Hz files and pulse analysis buffers

---

## Device Architecture

### BaseDevice Hierarchy

```
BaseDevice (Abstract)
├── capabilities (class variables)
│   ├── supports_idn_inquiry: bool
│   ├── supports_firmware_inquiry: bool
│   ├── has_command_widget: bool
│   └── has_status_tab: bool
│
├── abstract methods (must implement)
│   ├── get_read_command() -> str | None
│   ├── parse_message(message) -> ParseResult
│   └── get_plot_keys() -> list[str]
│
├── lifecycle hooks (optional override)
│   ├── on_connection_established()
│   ├── on_disconnection()
│   ├── send_read_commands(connection, params)
│   └── validate_10hz_mode()
│
├── composition members
│   ├── current_data: DeviceDataClass
│   ├── plot_config: BasePlotConfig
│   └── data_writer: BaseDataWriter
│
└── standard implementations
    ├── handle_serial_data(connection)
    ├── process_parsed_messages(results, params)
    ├── is_idn_response(message) -> bool
    └── handle_standard_idn(message) -> ParseResult
```

### SimpleDevice vs ComplexDevice

**File**: `src/devices/base_device.py`

```python
class SimpleDevice(BaseDevice):
    """Devices that only monitor (no control interface)"""
    def __init__(self, device_parameter, device_type):
        super().__init__()
        self.settings = None  # No settings
        # Usually auto-push data, no read command needed

    def get_read_command(self):
        return None  # Auto-push

class ComplexDevice(BaseDevice):
    """Devices with control/settings interface"""
    def __init__(self, device_parameter, device_type):
        super().__init__()
        self.settings = DeviceSettings()  # Has configurable settings
        self.command_widget = CommandWidget()  # Manual command interface
        self.status_tab = StatusTab()  # Status display

    def get_read_command(self):
        return ':READ:DATA\r\n'  # Request-response
```

**Comparison**:

| Feature | SimpleDevice | ComplexDevice |
|---------|-------------|---------------|
| Control Interface | No | Yes (command widget) |
| Settings | None | Device-specific dataclass |
| Communication | Auto-push | Request-response |
| Status Tab | Optional | Usually yes |
| Examples | RHTP, AFM, CO2 | CPC, PSM, eDiluter |

### Device Data Classes

**File**: `src/devices/device_data.py`

Strongly-typed dataclasses replace magic array indices:

```python
@dataclass
class CPCData:
    """CPC measurement data"""
    concentration: float = nan
    dead_time: float = nan
    inlet_temp: float = nan
    saturator_temp: float = nan
    optics_temp: float = nan
    cabin_temp: float = nan
    condensator_temp: float = nan
    optical_flow: float = nan
    aerosol_flow: float = nan
    absolute_pressure: float = nan
    critical_orifice_pressure: float = nan
    nozzle_pressure: float = nan
    liquid_level: float = nan
    drain_level: float = nan
    status_bits: int = 0

    def to_array(self) -> list:
        """Convert to array format"""
        return [
            self.concentration,
            self.dead_time,
            self.inlet_temp,
            # ... all fields
        ]

@dataclass
class CPCSettings:
    """CPC configuration settings"""
    saturator_temp_set: float = nan
    growth_tube_temp_set: float = nan
    optics_temp_set: float = nan
    # ... etc
```

**Benefits**:
- Named fields instead of `data[7]`
- IDE autocomplete support
- Type checking
- Self-documenting code
- Easy to add new fields

### Plot Configuration Classes

**File**: `src/plotting/device_plot_configs.py`

Each device has a plot configuration strategy:

```python
class BasePlotConfig(ABC):
    """Abstract base for plot configurations"""
    def __init__(self, device):
        self.device = device

    @abstractmethod
    def get_plot_keys(self) -> list[str]:
        """Return list of plot keys this device needs"""
        pass

    @abstractmethod
    def get_plot_values(self, dev_id, time_counter, plot_data, ...):
        """Extract values from device data into plot arrays"""
        pass

    def update_main_plot(self, curve, data):
        """Update main plot curve (optional override)"""
        curve.setData(data)

    def update_individual_plots(self, plot_data):
        """Update device's individual plot tabs (optional)"""
        pass

class CPCPlotConfig(BasePlotConfig):
    """CPC-specific plotting"""
    def get_plot_keys(self):
        return ['', '_dead_time', '_inlet_temp', '_saturator_temp']

    def get_plot_values(self, dev_id, time_counter, plot_data, ...):
        plot_data[str(dev_id)][time_counter] = \
            self.device.current_data.concentration
        plot_data[f'{dev_id}_dead_time'][time_counter] = \
            self.device.current_data.dead_time
        # ... etc
```

### Data Writer Classes

**File**: `src/devices/data_writers.py`

Each device has a data writing strategy:

```python
class BaseDataWriter(ABC):
    """Abstract base for data writers"""
    def __init__(self, device):
        self.device = device

    @abstractmethod
    def get_dat_header(self) -> str:
        """Return .dat file header"""
        pass

    @abstractmethod
    def get_dat_data(self, time_counter, params) -> str:
        """Return .dat file data line"""
        pass

    def supports_par_file(self) -> bool:
        """Does this device write .par files?"""
        return False

class CPCDataWriter(BaseDataWriter):
    """CPC-specific data writing"""
    def get_dat_header(self):
        return 'YYYY.MM.DD hh:mm:ss,Concentration,Dead Time,...'

    def get_dat_data(self, time_counter, params):
        timestamp = utils.get_timestamp(time_counter)
        data = self.device.current_data
        return f'{timestamp},{data.concentration},{data.dead_time},...'

    def supports_par_file(self):
        return True  # CPC writes parameters

    def get_par_data(self, params):
        timestamp = utils.get_timestamp(time_counter)
        settings = self.device.settings
        return f'{timestamp},{settings.saturator_temp_set},...'
```

---

## Manager Classes

### DataHolder

**File**: `src/managers/data_holder.py`

**Purpose**: Centralized storage with **no business logic** (pure data)

**Structure**:
```python
class DataHolder:
    def __init__(self):
        # Device widgets indexed by ID
        self.devices: dict[int, BaseDevice] = {}

        # Plot arrays indexed by key (e.g., '0', '0_dead_time')
        self.plot_data: dict[str, np.ndarray] = {}

        # Time array for x-axis
        self.time_array: np.ndarray = np.zeros(10)

        # Device type -> name mapping
        self.device_names: dict[int, str] = {
            CPC: 'CPC',
            PSM_RETROFIT: 'PSM Retrofit',
            PSM_2: 'PSM 2.0',
            # ... etc
        }

        # PSM-CPC linking
        self.linked_devices: dict[int, int] = {}  # PSM ID -> CPC ID
```

**Design Philosophy**:
- Pure storage, no logic
- Easy to serialize (for save/load config)
- Single source of truth
- Managers read from and write to DataHolder

### DeviceManager

**File**: `src/managers/device_manager.py`

**Purpose**: Device lifecycle, connections, serial communication

**Responsibilities**:
1. Test serial port availability and manage connections
2. Send read commands to devices
3. Read and parse serial responses
4. Handle IDN inquiry for device identification
5. Manage firmware version queries
6. Coordinate device lifecycle events

**Key State**:
```python
class DeviceManager:
    def __init__(self, data_holder):
        self.data_holder = data_holder
        self.connections: dict[int, SerialDeviceConnection] = {}
        self.idn_inquiry_list: list[int] = []
        self.firmware_inquiry_list: list[int] = []
```

**Connection Management**:

```python
def connection_test(self, params):
    """Called every second to manage connections"""
    for dev_id in range(num_devices):
        port = params['Devices'][dev_id]['COM Port']

        if self._is_port_available(port):
            if dev_id not in self.connections:
                # CONNECT
                connection = SerialDeviceConnection(port, baudrate)
                self.connections[dev_id] = connection
                device = self.data_holder.devices[dev_id]
                device.on_connection_established()

                # Request device ID
                if device.supports_idn_inquiry():
                    self.idn_inquiry_list.append(dev_id)
        else:
            if dev_id in self.connections:
                # DISCONNECT
                self.connections[dev_id].close()
                del self.connections[dev_id]
                device.on_disconnection()
```

### PlotManager

**File**: `src/managers/plot_manager.py`

**Purpose**: Plot creation, updates, rendering

**Responsibilities**:
1. Create plot arrays when devices are added
2. Extract plot values from device data
3. Update plot curves with new data
4. Manage legend entries
5. Handle axis ranges and auto-scaling
6. Coordinate individual device plot tabs

**Key State**:
```python
class PlotManager:
    def __init__(self, data_holder, main_plot):
        self.data_holder = data_holder
        self.main_plot = main_plot  # Shared plot widget
        self.main_plot_curves: dict[int, PlotCurveItem] = {}
        self.legend_items: dict[int, LegendItem] = {}
```

**Plot Array Management**:

```python
def create_plot_arrays(self, dev_id, device):
    """Create numpy arrays for device plots"""
    plot_keys = device.plot_config.get_plot_keys()

    for key in plot_keys:
        array_key = f'{dev_id}{key}'
        # Start with size 10, will grow as needed
        self.data_holder.plot_data[array_key] = np.full(10, np.nan)
```

**Array Growth**:
Arrays automatically expand when capacity is reached:
```python
# In utils.py
def expand_array(arr):
    """Double array size: 10 -> 20 -> 40 -> 80 -> ..."""
    new_size = arr.size * 2
    new_arr = np.full(new_size, np.nan)
    new_arr[:arr.size] = arr
    return new_arr
```

**Max size**: 604,800 seconds (7 days)

### DataLogger

**File**: `src/managers/data_logger.py`

**Purpose**: File I/O, data persistence

**Responsibilities**:
1. Create data files (.dat, .par, .csv)
2. Write timestamped data lines
3. Handle midnight file rollover
4. Manage special files (10Hz, pulse analysis)
5. Flush data to ensure persistence

**Key State**:
```python
class DataLogger:
    def __init__(self, data_holder):
        self.data_holder = data_holder
        self.file_handles: dict[int, dict[str, TextIOWrapper]] = {}
        # Structure: {dev_id: {'dat': file, 'par': file, '10hz': file}}
```

**File Creation**:

```python
def _create_files(self, dev_id, device, params):
    """Create data files for a device"""
    data_settings = params['Data Settings'][dev_id]
    folder = data_settings['Folder']
    nickname = params['Devices'][dev_id]['Nickname']

    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f'{nickname}_{timestamp}'

    # Create .dat file
    dat_path = os.path.join(folder, f'{base}.dat')
    dat_file = open(dat_path, 'w')
    dat_file.write(device.data_writer.get_dat_header() + '\n')

    self.file_handles[dev_id] = {'dat': dat_file}

    # Create .par file if supported
    if device.data_writer.supports_par_file():
        par_path = os.path.join(folder, f'{base}.par')
        par_file = open(par_path, 'w')
        par_file.write(device.data_writer.get_par_header() + '\n')
        self.file_handles[dev_id]['par'] = par_file
```

### TimerService

**File**: `src/managers/timer_service.py`

**Purpose**: Precise timing and synchronization

**Responsibilities**:
1. Maintain 1-second timer synchronized to system clock
2. Trigger registered callbacks at specific intervals
3. Handle delayed callbacks (e.g., read data 600ms after command)
4. Auto-restart at midnight to prevent drift

**Key Features**:

```python
class TimerService:
    def __init__(self):
        self.timer = QtCore.QTimer()
        self.timer.setTimerType(QtCore.Qt.PreciseTimer)
        self.timer.timeout.connect(self.on_timer)

        self.callbacks: dict[str, callable] = {}
        self.time_counter = 0

        # Sync to system clock
        self._sync_to_system_clock()
        self.timer.start(1000)  # 1 second

    def _sync_to_system_clock(self):
        """Start timer at next whole second"""
        now = datetime.now()
        microseconds_into_second = now.microsecond
        delay_ms = (1_000_000 - microseconds_into_second) // 1000
        QtCore.QTimer.singleShot(delay_ms, self._start_main_timer)
```

**Callback Registration**:

```python
# In MainWindow
self.timer_service.register_callback('connection_test',
                                     self.device_manager.connection_test)
self.timer_service.register_callback('get_data',
                                     self.device_manager.get_dev_data)
self.timer_service.register_delayed_callback('read_data',
                                              self.device_manager.readIndata,
                                              delay_ms=600)
```

**Auto-Restart**:
```python
def on_timer(self):
    self.time_counter += 1

    # Restart at midnight to prevent drift
    now = datetime.now()
    if now.hour == 23 and now.minute == 59 and now.second == 59:
        self.restart_timer()

    # Execute callbacks
    for callback in self.callbacks.values():
        callback()
```

---

## Serial Communication

### SerialDeviceConnection

**File**: `src/serial_connection.py`

**Protocol Specifications**:

| Parameter | Value | Notes |
|-----------|-------|-------|
| Baud Rate | 115200 | (19200 for TSI CPC) |
| Data Bits | 8 | Standard |
| Stop Bits | 1 | Standard |
| Parity | None | No parity checking |
| Timeout | 0.2 seconds | Non-blocking read |
| Command Terminator | `\r\n` | Carriage return + line feed |
| Response Terminator | `\r` | Carriage return only |

**Implementation**:

```python
class SerialDeviceConnection:
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2
        )

    def write(self, command: str):
        """Send command to device"""
        if not command.endswith('\r\n'):
            command += '\r\n'
        self.serial.write(command.encode('utf-8'))

    def read_all(self) -> str:
        """Read all available data from buffer"""
        data = self.serial.read_all()
        return data.decode('utf-8', errors='ignore')

    def is_open(self) -> bool:
        return self.serial.is_open

    def close(self):
        if self.serial.is_open:
            self.serial.close()
```

### Communication Protocols by Device

#### CPC Protocol

**Commands**:
```
:READ:DATA\r\n          # Request current measurements
:READ:SETTINGS\r\n      # Request current settings
:WRITE:SETTINGS:<values>\r\n  # Update settings
*IDN?\r\n               # Request device identification
:READ:FIRMWARE\r\n      # Request firmware version
```

**Response Format** (`:READ:DATA`):
```
:DATA:1234.5,0.12,25.3,102.5,20.1,0.5,50.3,1.5,0.3,1013.2,50.2,100.1,80.5,10.2,0\r
```

**Field Mapping**:
```python
fields = message.split(',')
data.concentration = float(fields[0])
data.dead_time = float(fields[1])
data.inlet_temp = float(fields[2])
data.saturator_temp = float(fields[3])
# ... 15 fields total
```

#### PSM Protocol

**Commands**:
```
:READ:DATA\r\n          # Request measurements
:READ:SETTINGS\r\n      # Request settings
:WRITE:SETTINGS:<values>\r\n
*IDN?\r\n
```

**Response Format**:
```
:DATA:<flow>,<sat_temp>,<cpc_conc>,<dilution_factor>,...\r
```

**PSM-CPC Linking**:
- PSM reads linked CPC concentration directly
- Applies dilution correction automatically
- Combined data written to PSM files

#### Simple Device Protocol (RHTP, AFM, CO2, Electrometer)

**Auto-Push Format**:
```
<value1>,<value2>,<value3>\r
```

Example (RHTP):
```
45.2,23.5,1013.2\r    # RH%, Temp°C, Pressure hPa
```

**Parsing**:
```python
def parse_message(self, message):
    try:
        values = message.split(',')
        self.current_data.humidity = float(values[0])
        self.current_data.temperature = float(values[1])
        self.current_data.pressure = float(values[2])
        return self.data_response(message, 'data')
    except:
        return self.error_response(message, 'Parse error')
```

### Error Handling

**Connection Errors**:
```python
try:
    connection = serial.Serial(port, baudrate)
except serial.SerialException as e:
    logging.error(f'Failed to open {port}: {e}')
    # Device shows as disconnected (grey icon)
```

**Parse Errors**:
```python
def parse_message(self, message):
    try:
        # ... parsing logic
        return self.data_response(message, 'data')
    except Exception as e:
        logging.error(f'Parse error for {message}: {e}')
        return self.error_response(message, str(e))
```

**Timeout Handling**:
- Read timeout set to 0.2 seconds
- If no data available, returns empty string
- Device continues normal operation
- Missing data points show as NaN in plots

---

## Timer System

### Synchronization Strategy

**Problem**: QTimer has cumulative drift over long runs

**Solution**: Synchronize to system clock on startup

**Implementation**:

```python
def _sync_to_system_clock(self):
    """Wait until next whole second, then start timer"""
    now = datetime.now()
    microseconds = now.microsecond

    # Calculate delay to next whole second
    delay_ms = (1_000_000 - microseconds) // 1000

    # Use single-shot timer to start main timer
    QtCore.QTimer.singleShot(delay_ms, self._start_main_timer)

def _start_main_timer(self):
    self.timer.start(1000)  # 1 second intervals
```

**Accuracy**: ±1ms typical

### Callback Execution Order

**Timing within 1-second cycle**:

```
0ms:   Timer fires
0ms:   connection_test()
0ms:   get_dev_data() - send commands
600ms: readIndata() - read responses (delayed)
650ms: update_plot_data()
700ms: write_data()
750ms: update_figures_and_menus()
1000ms: Next timer tick
```

**Delayed Callbacks**:
```python
def register_delayed_callback(self, name, func, delay_ms):
    """Execute callback after delay"""
    self.delayed_callbacks[name] = {
        'func': func,
        'delay': delay_ms
    }

def on_timer(self):
    # Immediate callbacks
    for callback in self.callbacks.values():
        callback()

    # Delayed callbacks
    for name, info in self.delayed_callbacks.items():
        QtCore.QTimer.singleShot(info['delay'], info['func'])
```

### Auto-Restart Mechanism

**Purpose**: Prevent cumulative timer drift over days

**Implementation**:
```python
def on_timer(self):
    now = datetime.now()

    # Restart at 23:59:59 and 11:59:59
    if (now.hour in [11, 23] and
        now.minute == 59 and
        now.second == 59):
        logging.info('Auto-restarting timer to prevent drift')
        self.restart_timer()

    # ... normal callback execution

def restart_timer(self):
    self.timer.stop()
    self._sync_to_system_clock()
```

**Effect**: Timer re-synchronizes to system clock twice daily

---

## Configuration Management

### Save/Load Architecture

**Files**:
- `config.ini`: Runtime settings (resume flag, config path)
- `resume_config.json`: Full application state

### Parameter Tree Serialization

**Save Process**:

```python
def save_configuration(self, filepath):
    """Recursively serialize parameter tree to JSON"""
    config = self._serialize_parameter(self.param_tree.root)

    with open(filepath, 'w') as f:
        json.dump(config, f, indent=2)

def _serialize_parameter(self, param):
    """Recursive serialization"""
    if param.hasChildren():
        # Group parameter
        return {
            'type': param.type(),
            'children': {
                child.name(): self._serialize_parameter(child)
                for child in param.children()
            }
        }
    else:
        # Leaf parameter
        return {
            'type': param.type(),
            'value': param.value()
        }
```

**Load Process**:

```python
def load_configuration(self, filepath):
    """Restore parameter tree from JSON"""
    with open(filepath, 'r') as f:
        config = json.load(f)

    self._deserialize_parameter(self.param_tree.root, config)

    # Recreate device widgets
    self._recreate_devices_from_config(config)

def _deserialize_parameter(self, param, config):
    """Recursive deserialization"""
    if 'children' in config:
        for name, child_config in config['children'].items():
            child = param.child(name)
            self._deserialize_parameter(child, child_config)
    else:
        param.setValue(config['value'])
```

### Resume on Startup

**config.ini**:
```ini
[DEFAULT]
resume = True
resume_config_path = resume_config.json
```

**Startup Logic**:
```python
def __init__(self):
    # ... initialize GUI

    # Check if resume is enabled
    config = configparser.ConfigParser()
    config.read('config.ini')

    if config.getboolean('DEFAULT', 'resume'):
        resume_path = config.get('DEFAULT', 'resume_config_path')
        if os.path.exists(resume_path):
            self.load_configuration(resume_path)
```

---

## Migration Notes

### Legacy Architecture (Pre-v0.10)

**Old Approach** (device-type checking everywhere):

```python
# OLD: DeviceManager had device-specific code
def get_dev_data(self, params):
    for dev_id in connected_devices:
        dev_type = params['Devices'][dev_id]['Device Type']

        if dev_type == CPC:
            connection.write(':READ:DATA\r\n')
        elif dev_type == PSM_RETROFIT:
            connection.write(':READ:DATA\r\n')
        elif dev_type == RHTP:
            pass  # Auto-push
        # ... 10+ elif branches

# OLD: PlotManager had device-specific code
def update_plot_data(self):
    for dev_id in connected_devices:
        dev_type = params['Devices'][dev_id]['Device Type']

        if dev_type == CPC:
            plot_data[str(dev_id)][time] = device_data[dev_id][0]  # Magic index!
        elif dev_type == PSM:
            plot_data[str(dev_id)][time] = device_data[dev_id][3]  # Different index
        # ... 10+ elif branches

# OLD: DataLogger had device-specific code
def write_data(self):
    for dev_id in saving_devices:
        dev_type = params['Devices'][dev_id]['Device Type']

        if dev_type == CPC:
            header = 'Time,Conc,Dead Time,...'  # Hard-coded
            line = f'{time},{data[0]},{data[1]},...'  # Magic indices
        elif dev_type == PSM:
            header = 'Time,Flow,Sat Temp,...'
            line = f'{time},{data[0]},{data[1]},...'
        # ... 10+ elif branches
```

**Problems**:
1. **Hard to maintain**: Adding a device required editing 5+ files
2. **Magic indices**: `data[7]` → what field is this?
3. **Brittle**: Easy to miss a location when adding/modifying
4. **No encapsulation**: Device logic scattered across codebase
5. **Code duplication**: Similar patterns repeated in each manager

### New Architecture (v0.10+)

**New Approach** (polymorphism and composition):

```python
# NEW: DeviceManager delegates to device
def get_dev_data(self, params):
    for dev_id, connection in self.connections.items():
        device = self.data_holder.devices[dev_id]
        device.send_read_commands(connection, params)  # Polymorphic call

# NEW: PlotManager delegates to device's plot config
def update_plot_data(self, time_counter, params):
    for dev_id, device in self.data_holder.devices.items():
        device.plot_config.get_plot_values(  # Strategy pattern
            dev_id, time_counter, self.data_holder.plot_data, params
        )

# NEW: DataLogger delegates to device's data writer
def write_data(self, time_counter, params):
    for dev_id, device in saving_devices.items():
        dat_line = device.data_writer.get_dat_data(time_counter, params)
        self.file_handles[dev_id]['dat'].write(dat_line + '\n')
```

**Benefits**:
1. **Easy to add devices**: Just create device class, register with decorator
2. **Named fields**: `data.concentration` instead of `data[0]`
3. **Encapsulation**: All device logic in device module
4. **DRY**: Generic manager code, no duplication
5. **Type safety**: IDE autocomplete and type checking

### Migration Guide

**For Developers Updating Old Device Code**:

#### Step 1: Create Data Class

**Before**:
```python
# Data stored as array in DataHolder
device_data[dev_id] = [conc, dead_time, inlet_temp, ...]  # Magic indices
```

**After**:
```python
# In src/devices/device_data.py
@dataclass
class MyDeviceData:
    concentration: float = nan
    dead_time: float = nan
    inlet_temp: float = nan

    def to_array(self) -> list:
        return [self.concentration, self.dead_time, self.inlet_temp]
```

#### Step 2: Create Device Widget

**Before**:
```python
# In src/app.py (scattered logic)
if dev_type == MY_DEVICE:
    widget = QtWidgets.QTabWidget()
    # ... setup logic
```

**After**:
```python
# In src/devices/my_device.py
@register_device(MY_DEVICE)
class MyDeviceWidget(SimpleDevice):
    def __init__(self, device_parameter):
        super().__init__(device_parameter, device_type=MY_DEVICE)
        self.current_data = MyDeviceData()
        self.plot_config = MyDevicePlotConfig(self)
        self.data_writer = MyDeviceDataWriter(self)

    def get_read_command(self):
        return ':READ:DATA\r\n'

    def parse_message(self, message):
        values = message.split(',')
        self.current_data.concentration = float(values[0])
        return self.data_response(message, 'data')
```

#### Step 3: Move Plot Logic

**Before**:
```python
# In src/managers/plot_manager.py
if dev_type == MY_DEVICE:
    plot_data[str(dev_id)][time] = device_data[dev_id][0]
```

**After**:
```python
# In src/plotting/device_plot_configs.py
class MyDevicePlotConfig(BasePlotConfig):
    def get_plot_values(self, dev_id, time_counter, plot_data, ...):
        plot_data[str(dev_id)][time_counter] = \
            self.device.current_data.concentration
```

#### Step 4: Move Data Writing Logic

**Before**:
```python
# In src/managers/data_logger.py
if dev_type == MY_DEVICE:
    header = 'Time,Concentration,...'
    line = f'{time},{data[0]},...'
```

**After**:
```python
# In src/devices/data_writers.py
class MyDeviceDataWriter(BaseDataWriter):
    def get_dat_header(self):
        return 'YYYY.MM.DD hh:mm:ss,Concentration,...'

    def get_dat_data(self, time_counter, params):
        timestamp = utils.get_timestamp(time_counter)
        return f'{timestamp},{self.device.current_data.concentration},...'
```

#### Step 5: Remove Old Code

**Remove from**:
- `src/managers/device_manager.py`: Device-specific if/elif branches
- `src/managers/plot_manager.py`: Device-specific if/elif branches
- `src/managers/data_logger.py`: Device-specific if/elif branches
- `src/app.py`: Device widget creation if/elif branches (now handled by registry)

### Array Interface

Device data classes include a `to_array()` method:

```python
@dataclass
class CPCData:
    concentration: float = nan
    dead_time: float = nan

    def to_array(self) -> list:
        """Convert to array format"""
        return [self.concentration, self.dead_time, ...]
```

This method is used by:
- GUI update methods that expect array format
- Data writers for file serialization
- Default plot configurations
- Settings comparison logic

---

## Conclusion

The Airmodus MultiLogger architecture represents a well-designed, maintainable system that:

1. **Separates Concerns**: Each manager has a single, clear responsibility
2. **Enables Extension**: Adding new devices requires minimal code
3. **Promotes Reusability**: Generic managers work with all devices
4. **Ensures Type Safety**: Dataclasses provide compile-time checking
5. **Maintains Performance**: Efficient numpy arrays and Qt rendering
6. **Supports Long Runs**: Robust timing and file handling

The recent refactoring from a procedural, device-checking architecture to an object-oriented, composition-based design significantly improved code quality and maintainability while preserving all functionality.

---

**For more information**:
- **User Guide**: See [README.md](README.md)
- **Developer Guide**: See [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
