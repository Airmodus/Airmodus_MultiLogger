# Test Suite for Airmodus MultiLogger

This directory contains the complete test suite for the Airmodus MultiLogger application.

## Quick Start

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific category
pytest -m unit
pytest -m integration
```

See [TESTING.md](../TESTING.md) for comprehensive testing documentation.

## Directory Structure

```
tests/
├── README.md                    # This file
├── conftest.py                  # Shared fixtures for all tests
├── fixtures/
│   └── mock_serial_data.py      # Mock serial device responses
├── unit/                        # Unit tests (fast, isolated)
│   ├── devices/
│   │   ├── test_device_data.py       # ✅ Dataclass tests (COMPLETE)
│   │   ├── test_data_writers.py      # ⏳ Data writer tests (TODO)
│   │   ├── test_cpc.py               # ✅ CPC device tests (COMPLETE)
│   │   ├── test_psm.py               # ✅ PSM device tests (COMPLETE)
│   │   ├── test_ediluter.py          # ✅ eDiluter tests (COMPLETE)
│   │   └── test_simple_devices.py    # ✅ Simple device tests (COMPLETE)
│   ├── managers/
│   │   ├── test_device_manager.py    # ⏳ Device manager tests (TODO)
│   │   ├── test_data_logger.py       # ⏳ Data logger tests (TODO)
│   │   ├── test_plot_manager.py      # ⏳ Plot manager tests (TODO)
│   │   └── test_timer_service.py     # ⏳ Timer service tests (TODO)
│   ├── test_utils.py                 # ✅ Utility function tests (COMPLETE)
│   └── test_serial_connection.py     # ⏳ Serial comm tests (TODO)
└── integration/                 # Integration tests (slower)
    ├── test_device_lifecycle.py      # ⏳ Full device lifecycle (TODO)
    ├── test_data_flow.py             # ⏳ Data flow pipeline (TODO)
    └── test_file_writing.py          # ⏳ File I/O integration (TODO)
```

## Status Legend

- ✅ **COMPLETE** - Fully implemented tests
- ✅ **TEMPLATE** - Example implementation to follow for similar components
- ⏳ **TODO** - Not yet implemented (follow templates and patterns)

## Completed Tests

### 1. `test_utils.py` ✅
Tests pure utility functions:
- Array management (`_manage_plot_array`, `_roll_pulse_array`)
- Response parsing (`parse_idn_response`)
- Response creation (`create_data_response`, `create_error_response`)
- Settings compilation (`compile_cpc_settings`, `compile_psm_settings`)

**Coverage**: ~95% of utils.py

### 2. `test_device_data.py` ✅
Tests all device dataclasses:
- Default initialization (NaN values)
- `to_array()` conversions for all device types
- Field assignment and retrieval
- Factory functions (`create_device_data`, `create_device_settings`)
- Settings dataclasses (CPCSettings, PSMSettings)

**Coverage**: 100% of device_data.py

### 3. `test_cpc.py` ✅
Complete CPC device tests:
- IDN parsing
- Data message parsing (valid, malformed, errors)
- Settings parsing
- Pulse quality parsing
- Data writer functionality
- Error handling

### 4. `test_psm.py` ✅
Complete PSM/PSM 2.0 device tests:
- IDN parsing for both versions
- Measurement data parsing (:MEAS:SCAN, :MEAS:STEP, :MEAS:FIXD)
- Settings parsing (:SYST:PRNT)
- Dilution parameters (:SYST:VCMP)
- Error/note hex parsing
- Vacuum flow (PSM 2.0 specific)
- CPC integration fields
- Self-test error parsing

### 5. `test_ediluter.py` ✅
Complete eDiluter device tests:
- IDN parsing
- Data push message parsing (147-character format)
- SUCCESS/ERROR responses
- Settings parsing
- Data writer functionality
- Status field handling

### 6. `test_simple_devices.py` ✅
Complete tests for all simple devices:
- **RHTP**: RH, Temperature, Pressure parsing
- **CO2 Sensor**: CO2 concentration (with optional T/RH)
- **AFM**: Flow, saturator flow, environmental data
- **Electrometer**: Single/triple voltage channels
- **TSI CPC**: Concentration with error hex
- **Example Device**: Template device implementation
- Parametrized tests for common features across all simple devices

**All device tests now complete!**

## Adding New Tests

### For a New Device

1. Copy `tests/unit/devices/test_cpc.py` as a template
2. Rename to `test_<device_name>.py`
3. Update the import to your device widget
4. Add mock responses to `fixtures/mock_serial_data.py`:
   ```python
   class MockMyDeviceResponses:
       IDN = b"*IDN My Device,PSN:001,FW:1.0.0\r"
       DATA_NORMAL = b"<your device response format>\r"
   ```
5. Update test methods to match your device's message format
6. Run tests: `pytest tests/unit/devices/test_<device_name>.py -v`

### For a Manager

1. Create `tests/unit/managers/test_<manager_name>.py`
2. Import the manager class
3. Use fixtures from `conftest.py`:
   - `mock_data_holder` - Mock data holder
   - `mock_device_parameter` - Mock parameter tree
   - `mock_serial_connection` - Mock serial I/O
4. Test key methods:
   ```python
   def test_manager_initialization(mock_data_holder):
       manager = MyManager(mock_data_holder)
       assert manager is not None

   def test_manager_key_function(mock_data_holder, mock_device_parameter):
       manager = MyManager(mock_data_holder)
       result = manager.do_something(mock_device_parameter)
       assert result == expected_value
   ```

### For Integration Tests

1. Create `tests/integration/test_<feature>.py`
2. Mark with `@pytest.mark.integration`
3. Test multiple components together:
   ```python
   @pytest.mark.integration
   def test_full_device_flow(qapp, mock_serial_connection):
       # Set up mock responses
       from fixtures.mock_serial_data import simulate_device_connection
       mock_serial_connection.read_all = simulate_device_connection("CPC")

       # Test full flow: connect → read → parse → write
       device = CPCWidget(mock_device_parameter)
       # ... test complete workflow
   ```

## Testing Priorities

Focus on these areas first (highest impact on data integrity):

### Priority 1: Data Parsing (CRITICAL)
- ✅ `test_device_data.py` - DONE
- ✅ `test_cpc.py` - Template complete
- ⏳ `test_psm.py` - Copy CPC pattern
- ⏳ `test_ediluter.py` - Copy CPC pattern
- ⏳ `test_simple_devices.py` - Simpler than CPC

**Why**: Data parsing errors cause data loss/corruption.

### Priority 2: File Writing (CRITICAL)
- ⏳ `test_data_writers.py` - Test all DataWriter classes
- ⏳ `test_data_logger.py` - Test file creation, headers, writing
- ⏳ `integration/test_file_writing.py` - End-to-end file tests

**Why**: File writing errors corrupt experimental data.

### Priority 3: Device Lifecycle (HIGH)
- ⏳ `test_device_manager.py` - Connection/disconnection logic
- ⏳ `test_serial_connection.py` - Serial communication
- ⏳ `integration/test_device_lifecycle.py` - Full connect → data → disconnect

**Why**: Connection issues block all data collection.

### Priority 4: Plot & Timer (MEDIUM)
- ⏳ `test_plot_manager.py` - Array management, updates
- ⏳ `test_timer_service.py` - Timer synchronization

**Why**: Important but bugs are non-destructive.

## Available Fixtures

See `conftest.py` for all fixtures. Key ones:

- **`qapp`** - QApplication for GUI tests
- **`mock_serial_connection`** - Mock pyserial.Serial
- **`mock_device_connection`** - Mock SerialDeviceConnection
- **`mock_device_parameter`** - Mock Parameter tree
- **`mock_data_holder`** - Mock DataHolder
- **`sample_cpc_data`** - Pre-filled CPCData
- **`sample_psm_data`** - Pre-filled PSMData
- **`temp_data_dir`** - Temporary directory for file tests
- **`fixed_datetime`** - Fix time for deterministic tests

## Mock Serial Responses

See `fixtures/mock_serial_data.py` for all mock responses:

```python
from fixtures.mock_serial_data import (
    MockCPCResponses,
    MockPSMResponses,
    MockSerialSequence,
    simulate_device_connection
)

# Use in tests:
mock_serial.read_all.return_value = MockCPCResponses.DATA_NORMAL

# Or for sequence:
sequence = MockSerialSequence([
    MockCPCResponses.IDN,
    MockCPCResponses.DATA_NORMAL
])
mock_serial.read_all = sequence
```

## Test Patterns

### Pattern 1: Pure Function Test
```python
def test_pure_function():
    result = my_function(input_data)
    assert result == expected_output
```

### Pattern 2: Device Parsing Test
```python
def test_device_parsing(device_widget):
    message = "device response format"
    result = device_widget.parse_message(message, None)

    assert result['type'] == 'data'
    assert device_widget.current_data.field == expected_value
```

### Pattern 3: File Writing Test
```python
def test_file_writing(temp_data_dir, device_widget):
    output_file = temp_data_dir / "test.dat"

    device_widget.data_writer.write_file(str(output_file))

    assert output_file.exists()
    content = output_file.read_text()
    assert "expected header" in content
```

### Pattern 4: Mock Serial Test
```python
def test_serial_communication(mock_serial_connection, device_manager):
    from fixtures.mock_serial_data import MockCPCResponses
    mock_serial_connection.read_all.return_value = MockCPCResponses.IDN

    device_manager.send_idn_request(device_id=1)

    # Verify write was called
    mock_serial_connection.write.assert_called_once()
```

## Running Specific Tests

```bash
# All tests in a file
pytest tests/unit/test_utils.py

# Specific test class
pytest tests/unit/test_utils.py::TestManagePlotArray

# Specific test method
pytest tests/unit/test_utils.py::TestManagePlotArray::test_initial_growth_doubles_array

# All unit tests
pytest -m unit

# All integration tests
pytest -m integration

# All GUI tests
pytest -m gui

# Exclude slow tests
pytest -m "not slow"
```

## Debugging Tests

```bash
# Stop on first failure
pytest -x

# Show print statements
pytest -s

# Show local variables on failure
pytest -l

# Extra verbose
pytest -vv

# Debug with pdb
pytest --pdb
```

## Coverage Goals

- **Utils**: >90% (pure functions, easy to test)
- **Device Data**: 100% (simple dataclasses)
- **Device Parsing**: >85% (critical for data integrity)
- **File Writing**: >90% (critical for data integrity)
- **Managers**: >75% (more complex, some GUI interaction)
- **GUI Components**: >50% (lower priority, visual bugs non-destructive)

## Next Steps

1. **Copy the CPC template** for other devices (PSM, eDiluter, simple devices)
2. **Add data writer tests** - Critical for file integrity
3. **Add data logger tests** - Test file creation and writing
4. **Add device manager tests** - Test connection lifecycle
5. **Add integration tests** - Test full workflows

## Questions?

- See [TESTING.md](../TESTING.md) for detailed testing guide
- See [DEVELOPER_GUIDE.md](../DEVELOPER_GUIDE.md) for architecture info
- Open an issue on GitHub for testing questions

---

**Remember**: Tests are living documentation. Keep them updated as code changes!
