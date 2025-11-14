"""
Shared pytest fixtures for Airmodus MultiLogger tests.

This module provides reusable fixtures for:
- PyQt application instance
- Mock serial connections
- Mock device parameters
- Mock managers and data holders
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
from PyQt5.QtWidgets import QApplication

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


# ============================================================================
# PyQt Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def qapp():
    """
    Create QApplication instance for GUI tests.

    Scope is 'session' to create only one QApplication for all tests,
    as PyQt doesn't allow multiple QApplication instances.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    # Note: Don't call app.quit() as it may be needed by other tests


# ============================================================================
# Mock Serial Connection Fixtures
# ============================================================================

@pytest.fixture
def mock_serial_connection():
    """
    Mock pyserial.Serial object with common methods.

    Returns a Mock configured to behave like a serial.Serial instance.
    Tests can configure specific responses using:
        mock_serial_connection.read_all.return_value = b"response\\r"
    """
    mock_serial = Mock()
    mock_serial.is_open = True
    mock_serial.in_waiting = 0
    mock_serial.read_all = Mock(return_value=b"")
    mock_serial.write = Mock()
    mock_serial.close = Mock()
    mock_serial.open = Mock()
    mock_serial.port = "COM3"
    mock_serial.baudrate = 115200
    mock_serial.timeout = 0.2
    return mock_serial


@pytest.fixture
def mock_device_connection(mock_serial_connection):
    """
    Mock SerialDeviceConnection with configured serial connection.

    Provides a ready-to-use connection object that appears connected.
    """
    from serial_connection import SerialDeviceConnection

    conn = SerialDeviceConnection()
    conn.connection = mock_serial_connection
    conn.serial_port = "COM3"
    return conn


# ============================================================================
# Mock Parameter Tree Fixtures
# ============================================================================

@pytest.fixture
def mock_device_parameter():
    """
    Mock Parameter object (from pyqtgraph.parametertree).

    Used for device initialization without real parameter tree.
    """
    param = Mock()
    param.name.return_value = "Test Device"

    # Mock child parameters with specific values for CPC database tab
    def child_side_effect(name):
        child_param = Mock()
        # Set specific values for database-related parameters
        if name == 'Database enabled':
            child_param.value.return_value = False
        elif name == 'DB averaging interval':
            child_param.value.return_value = '1 min'
        elif name == 'Linked RHTP':
            child_param.value.return_value = None
        elif name == '10 hz':
            child_param.value.return_value = False
        else:
            child_param.value.return_value = None
        child_param.setValue = Mock()

        # Nested children for 'Data Settings'
        def nested_child(nested_name):
            nested_param = Mock()
            nested_param.value.return_value = None
            nested_param.setValue = Mock()
            return nested_param

        child_param.child = Mock(side_effect=nested_child)
        return child_param

    param.child = Mock(side_effect=child_side_effect)

    # Mock parent for CPC database tab requirements
    parent_mock = Mock()
    parent_mock.rhtp_dict = {}  # Empty dict for RHTP devices
    parent_mock.cpc_dict = {}   # Empty dict for CPC devices
    param.parent.return_value = parent_mock

    return param


@pytest.fixture
def mock_params_tree():
    """
    Mock entire parameter tree structure.

    Useful for manager tests that need to access multiple parameters.
    """
    params = Mock()

    def child_side_effect(name):
        child = Mock()
        child.value.return_value = None
        child.setValue = Mock()
        child.child = Mock(side_effect=child_side_effect)
        child.children = Mock(return_value=[])
        return child

    params.child = Mock(side_effect=child_side_effect)
    params.children = Mock(return_value=[])
    return params


# ============================================================================
# Mock Manager Fixtures
# ============================================================================

@pytest.fixture
def mock_data_holder():
    """
    Mock DataHolder with device management.

    Provides common device access patterns used by managers.
    """
    holder = Mock()
    holder.devices = []
    holder.dev_id_counter = 0

    def add_device(device):
        holder.devices.append(device)
        device.dev_id = holder.dev_id_counter
        holder.dev_id_counter += 1

    holder.add_device = add_device
    holder.get_device = Mock(return_value=None)
    return holder


@pytest.fixture
def mock_device_manager(mock_data_holder):
    """Mock DeviceManager for testing."""
    from managers.device_manager import DeviceManager

    manager = Mock(spec=DeviceManager)
    manager.data_holder = mock_data_holder
    manager.connect_device = Mock()
    manager.disconnect_device = Mock()
    manager.send_command = Mock()
    return manager


@pytest.fixture
def mock_plot_manager():
    """Mock PlotManager for testing."""
    manager = Mock()
    manager.update_plot = Mock()
    manager.add_device_to_plot = Mock()
    manager.remove_device_from_plot = Mock()
    return manager


@pytest.fixture
def mock_data_logger():
    """Mock DataLogger for testing."""
    manager = Mock()
    manager.write_data = Mock()
    manager.create_files = Mock()
    manager.close_files = Mock()
    return manager


# ============================================================================
# Device Data Fixtures
# ============================================================================

@pytest.fixture
def sample_cpc_data():
    """Sample CPC data for testing."""
    from devices.device_data import CPCData

    data = CPCData()
    data.concentration = 1234.5
    data.dead_time = 0.12
    data.number_of_pulses = 100
    data.temp_saturator = 40.5
    data.temp_condenser = 10.2
    data.temp_optics = 25.3
    data.temp_cabin = 28.1
    data.pres_inlet = 1013.2
    data.pres_critical_orifice = 450.3
    data.pres_nozzle = 320.1
    data.pres_cabin = 1015.0
    data.liquid_level = 80
    data.pulse_ratio = 0.95
    data.total_errors = 0
    data.status_hex = "0x000"
    return data


@pytest.fixture
def sample_psm_data():
    """Sample PSM data for testing."""
    from devices.device_data import PSMData

    data = PSMData()
    data.saturator_flow = 1.0
    data.cpc_inlet_flow = 0.3
    data.drain_flow = 0.7
    data.temp_growth_tube = 90.0
    data.temp_inlet = 25.0
    data.temp_saturator = 40.0
    data.total_errors = 0
    data.status_hex = "0x000"
    return data


# ============================================================================
# File System Fixtures
# ============================================================================

@pytest.fixture
def temp_data_dir(tmp_path):
    """
    Create temporary directory for data file tests.

    Uses pytest's tmp_path fixture which provides a Path object
    to a temporary directory unique to the test invocation.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


# ============================================================================
# Time Fixtures
# ============================================================================

@pytest.fixture
def fixed_datetime(monkeypatch):
    """
    Fix datetime.now() to return a specific time.

    Useful for testing time-dependent features like midnight file rollover.
    """
    from datetime import datetime

    class FixedDatetime:
        @staticmethod
        def now():
            return datetime(2025, 11, 3, 10, 30, 0)

    import datetime as dt_module
    monkeypatch.setattr(dt_module, 'datetime', FixedDatetime)
    return FixedDatetime.now()
