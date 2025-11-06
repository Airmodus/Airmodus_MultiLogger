# Testing Guide for Airmodus MultiLogger

This document provides comprehensive information about testing the Airmodus MultiLogger application.

## Table of Contents

- [Getting Started](#getting-started)
- [Running Tests](#running-tests)
- [Test Structure](#test-structure)
- [Writing New Tests](#writing-new-tests)
- [Testing Patterns](#testing-patterns)
- [Fixtures](#fixtures)
- [Mocking Strategies](#mocking-strategies)
- [Coverage](#coverage)
- [CI/CD](#cicd)
- [Troubleshooting](#troubleshooting)

## Getting Started

### Install Test Dependencies

The testing dependencies are included in `environment.yaml`. If you haven't set up the environment yet:

```bash
# Create or update the conda environment
conda env update -f environment.yaml

# Activate the environment
conda activate multilogger-env
```

### Verify Installation

```bash
# Check pytest is installed
pytest --version

# Should show pytest 7.x or higher
```

## Running Tests

### Run All Tests

```bash
# From the repository root
pytest
```

### Run Specific Test Categories

```bash
# Only unit tests (fast)
pytest -m unit

# Only integration tests
pytest -m integration

# Only GUI tests
pytest -m gui

# Exclude slow tests
pytest -m "not slow"
```

### Run Specific Test Files

```bash
# Single file
pytest tests/unit/test_utils.py

# Multiple files
pytest tests/unit/test_utils.py tests/unit/devices/test_device_data.py

# Specific test class
pytest tests/unit/test_utils.py::TestManagePlotArray

# Specific test method
pytest tests/unit/test_utils.py::TestManagePlotArray::test_initial_growth_doubles_array
```

### Verbose Output

```bash
# Show test names and output
pytest -v

# Show local variables on failures
pytest -l

# Show print statements
pytest -s
```

### Stop on First Failure

```bash
pytest -x
```

### Re-run Failed Tests

```bash
# Run only tests that failed last time
pytest --lf

# Run failed tests first, then others
pytest --ff
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── fixtures/
│   └── mock_serial_data.py  # Mock serial responses
├── unit/                    # Unit tests (fast, isolated)
│   ├── devices/
│   │   ├── test_device_data.py      # Dataclass tests
│   │   ├── test_data_writers.py     # Data writer tests
│   │   ├── test_cpc.py              # CPC device tests
│   │   ├── test_psm.py              # PSM device tests
│   │   ├── test_ediluter.py         # eDiluter tests
│   │   └── test_simple_devices.py   # Simple device tests
│   ├── managers/
│   │   ├── test_device_manager.py   # Device manager tests
│   │   ├── test_data_logger.py      # Data logger tests
│   │   ├── test_plot_manager.py     # Plot manager tests
│   │   └── test_timer_service.py    # Timer service tests
│   ├── test_utils.py                # Utility function tests
│   └── test_serial_connection.py    # Serial communication tests
└── integration/             # Integration tests (slower)
    ├── test_device_lifecycle.py     # Full device lifecycle
    ├── test_data_flow.py            # Data flow pipeline
    └── test_file_writing.py         # File I/O integration
```

### Test Markers

Tests are marked with categories for selective running:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests (multiple components)
- `@pytest.mark.gui` - GUI-related tests (require QApplication)
- `@pytest.mark.serial` - Tests involving serial communication mocking
- `@pytest.mark.slow` - Slow tests (>1s)

## Writing New Tests

### Test File Template

```python
"""
Unit tests for <module_name>.py - <brief description>

Tests:
- Feature 1
- Feature 2
"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from module_name import function_to_test


class TestFeatureName:
    """Test <feature name> functionality."""

    def test_basic_case(self):
        """Test basic functionality."""
        result = function_to_test(input_data)

        assert result == expected_value
        assert isinstance(result, ExpectedType)

    def test_edge_case(self):
        """Test edge case behavior."""
        result = function_to_test(edge_case_input)

        assert result is not None

    def test_error_handling(self):
        """Test that errors are handled correctly."""
        with pytest.raises(ValueError, match="error message"):
            function_to_test(invalid_input)


# Mark all tests in this file as unit tests
pytestmark = pytest.mark.unit
```

### Naming Conventions

- **Test files**: `test_<module>.py` or `<module>_test.py`
- **Test classes**: `Test<FeatureName>`
- **Test methods**: `test_<what_it_tests>`

### Good Test Practices

1. **One assertion per concept** - Test one thing per test method
2. **Clear test names** - Describe what's being tested
3. **Arrange-Act-Assert** - Structure tests clearly:
   ```python
   def test_something(self):
       # Arrange - Set up test data
       data = create_test_data()

       # Act - Perform the operation
       result = function(data)

       # Assert - Verify the result
       assert result == expected
   ```
4. **Use fixtures** - Reuse common setup code
5. **Test both success and failure** - Test valid inputs and error cases

## Testing Patterns

### Testing Device Parsing

```python
def test_parse_valid_data(self, device_widget):
    """Test parsing valid data message."""
    # Arrange
    message = ":MEAS:ALL 1234.5,0.12,100,40.5,10.2"

    # Act
    result = device_widget.parse_message(message, None)

    # Assert
    assert result['type'] == 'data'
    assert result['command'] == ':MEAS:ALL'
    assert device_widget.current_data.concentration == 1234.5
    assert device_widget.current_data.dead_time == 0.12
```

### Testing File Writing

```python
def test_dat_file_creation(self, tmp_path, device_widget):
    """Test .dat file creation and headers."""
    # Arrange - Use pytest's tmp_path fixture
    output_file = tmp_path / "test_device.dat"

    # Act
    device_widget.data_writer.write_dat_file(
        str(output_file),
        timestamp="2025.11.03 10:30:00",
        data=device_widget.current_data
    )

    # Assert
    assert output_file.exists()
    content = output_file.read_text()
    assert content.startswith("YYYY.MM.DD hh:mm:ss,")
    assert "1234.5" in content
```

### Testing with Mock Serial

```python
def test_device_connection(self, mock_serial_connection, device_manager):
    """Test device connection flow."""
    # Arrange
    from fixtures.mock_serial_data import simulate_device_connection
    mock_serial_connection.read_all = simulate_device_connection("CPC")

    # Act
    device_manager.connect_device(device_id=1, port="COM3")

    # Assert
    assert device_manager.data_holder.devices[1].connected is True
    assert device_manager.data_holder.devices[1].serial_number != ""
```

### Testing GUI Components

```python
@pytest.mark.gui
def test_cpc_widget_initialization(self, qapp, mock_device_parameter):
    """Test CPC widget initializes correctly."""
    # Arrange & Act
    from devices.cpc import CPCWidget
    widget = CPCWidget(mock_device_parameter)

    # Assert
    assert widget.device_tab is not None
    assert widget.data_tab is not None
    assert widget.set_tab is not None

    # Cleanup
    widget.deleteLater()
```

### Testing Dataclasses

```python
def test_cpc_data_to_array(self):
    """Test CPCData.to_array() conversion."""
    # Arrange
    from devices.device_data import CPCData
    data = CPCData()
    data.concentration = 1234.5
    data.dead_time = 0.12

    # Act
    arr = data.to_array()

    # Assert
    assert len(arr) == 15  # CPC has 15 data fields
    assert arr[0] == 1234.5  # Index 0 is concentration
    assert arr[1] == 0.12    # Index 1 is dead_time
```

## Fixtures

### Available Fixtures (from conftest.py)

#### PyQt Fixtures

- **`qapp`** - QApplication instance for GUI tests (session scope)
  ```python
  def test_gui_component(qapp):
      widget = MyWidget()
      assert widget is not None
  ```

#### Mock Serial Fixtures

- **`mock_serial_connection`** - Mock pyserial.Serial object
  ```python
  def test_serial_write(mock_serial_connection):
      mock_serial_connection.write.return_value = 10
      # Test your code
  ```

- **`mock_device_connection`** - Mock SerialDeviceConnection
  ```python
  def test_device_communication(mock_device_connection):
      mock_device_connection.send_message("*IDN")
      # Test your code
  ```

#### Parameter Tree Fixtures

- **`mock_device_parameter`** - Mock Parameter object
  ```python
  def test_device_init(mock_device_parameter):
      device = CPCWidget(mock_device_parameter)
  ```

- **`mock_params_tree`** - Mock entire parameter tree

#### Manager Fixtures

- **`mock_data_holder`** - Mock DataHolder
- **`mock_device_manager`** - Mock DeviceManager
- **`mock_plot_manager`** - Mock PlotManager
- **`mock_data_logger`** - Mock DataLogger

#### Data Fixtures

- **`sample_cpc_data`** - Pre-filled CPCData instance
- **`sample_psm_data`** - Pre-filled PSMData instance

#### File System Fixtures

- **`temp_data_dir`** - Temporary directory for file tests
  ```python
  def test_file_creation(temp_data_dir):
      output_file = temp_data_dir / "test.dat"
      # Write to file
      assert output_file.exists()
  ```

#### Time Fixtures

- **`fixed_datetime`** - Fix datetime.now() to specific time
  ```python
  def test_midnight_rollover(fixed_datetime):
      # Test time-dependent code
  ```

### Creating Custom Fixtures

```python
# In conftest.py or test file
@pytest.fixture
def my_custom_fixture():
    """Description of what this fixture provides."""
    # Setup
    resource = create_resource()

    # Provide to test
    yield resource

    # Teardown (optional)
    resource.cleanup()
```

## Mocking Strategies

### Mocking Serial Communication

```python
from unittest.mock import Mock
from fixtures.mock_serial_data import MockCPCResponses, MockSerialSequence

def test_serial_read():
    # Simple mock
    mock_serial = Mock()
    mock_serial.read_all.return_value = MockCPCResponses.DATA_NORMAL

    # Sequential responses
    sequence = MockSerialSequence([
        MockCPCResponses.IDN,
        MockCPCResponses.DATA_NORMAL
    ])
    mock_serial.read_all = sequence
```

### Mocking File I/O

```python
# Use pytest's tmp_path - don't mock!
def test_file_writing(tmp_path):
    output_file = tmp_path / "output.dat"
    write_data_to_file(str(output_file))
    assert output_file.exists()
```

### Mocking Time

```python
def test_time_dependent_code(monkeypatch):
    from datetime import datetime

    class FixedDatetime:
        @staticmethod
        def now():
            return datetime(2025, 11, 3, 23, 59, 59)

    import datetime as dt_module
    monkeypatch.setattr(dt_module, 'datetime', FixedDatetime)

    # Your code will now see fixed time
```

### Mocking QTimer

```python
def test_timer_callback(qtbot):
    from PyQt5.QtCore import QTimer

    callback_called = []

    def callback():
        callback_called.append(True)

    # Use qtbot to wait for signals
    timer = QTimer()
    timer.timeout.connect(callback)
    timer.start(100)

    qtbot.waitUntil(lambda: len(callback_called) > 0, timeout=1000)
    assert callback_called[0] is True
```

## Coverage

### Run Tests with Coverage

```bash
# Basic coverage report
pytest --cov=src

# With missing lines highlighted
pytest --cov=src --cov-report=term-missing

# Generate HTML report
pytest --cov=src --cov-report=html

# Then open htmlcov/index.html in browser
```

### Coverage Configuration

Coverage settings are in `pytest.ini`:

```ini
[coverage:run]
source = src
omit =
    */tests/*
    */test_*.py
    */__pycache__/*

[coverage:report]
precision = 2
skip_empty = True
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
    if __name__ == .__main__.:
```

### Coverage Goals

- **Unit tests**: Aim for >80% coverage of testable code
- **Critical paths**: Data parsing, file writing should be 100%
- **GUI code**: Lower priority for coverage (visual bugs are non-destructive)

## CI/CD

### GitHub Actions Workflow

Tests run automatically on:
- Push to any branch
- Pull requests
- Manual trigger

See `.github/workflows/tests.yml` for configuration.

### Local CI Simulation

```bash
# Run tests exactly as CI does
pytest -v --cov=src --cov-report=term-missing --cov-report=html
```

### Test Matrix

CI tests on multiple Python versions:
- Python 3.8
- Python 3.9
- Python 3.10
- Python 3.11

## Troubleshooting

### QApplication Already Created

**Problem**: `RuntimeError: QApplication instance already created`

**Solution**: Use the `qapp` fixture (session scope) instead of creating new QApplication:

```python
def test_my_widget(qapp):  # Use qapp fixture
    widget = MyWidget()
    # Don't create QApplication here
```

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'devices'`

**Solution**: Tests add `src/` to path. Ensure you're running pytest from repository root:

```bash
cd /path/to/Airmodus_MultiLogger
pytest
```

### Serial Port Errors

**Problem**: Tests try to open real serial ports

**Solution**: Ensure you're using mock fixtures:

```python
def test_connection(mock_serial_connection):  # Use mock
    # Not: serial.Serial('COM3')  # Don't open real ports
```

### Slow Tests

**Problem**: Tests take too long

**Solution**:
1. Mark slow tests: `@pytest.mark.slow`
2. Run fast tests only: `pytest -m "not slow"`
3. Use mocks instead of real I/O
4. Reduce test data size

### Fixture Not Found

**Problem**: `fixture 'my_fixture' not found`

**Solution**:
1. Check fixture is defined in `conftest.py` or test file
2. Check fixture name matches exactly
3. Ensure `conftest.py` is in correct location

### Failed to Import Module

**Problem**: Test file won't import

**Solution**:
1. Check test file naming (`test_*.py`)
2. Ensure `__init__.py` not present in tests/ (not needed)
3. Check syntax errors in test file

## Best Practices Summary

✅ **DO**:
- Write tests for all new features
- Use descriptive test names
- Test both success and failure cases
- Use fixtures for common setup
- Mock external dependencies (serial, file system via tmp_path, time)
- Run tests before committing
- Keep tests fast (<1s per unit test)
- Use markers to categorize tests

❌ **DON'T**:
- Access real serial ports in tests
- Write to real file system (use tmp_path)
- Create multiple QApplication instances
- Test implementation details
- Skip writing tests for "simple" code
- Commit broken tests
- Mix unit and integration tests

## Additional Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-qt documentation](https://pytest-qt.readthedocs.io/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)
- Project architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- Developer guide: [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)

---

**Questions or issues with testing?** Open an issue on GitHub or contact the development team.
