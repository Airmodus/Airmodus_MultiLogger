"""
Integration tests for device connection flow.

Tests the complete connection sequence for devices:
1. IDN inquiry
2. Firmware version query
3. Initial data messages
4. Settings fetch (for devices that need it)

These tests verify that the connection flow matches the original monolith app behavior.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from devices.cpc import CPCWidget
from devices.psm import PSMWidget
from fixtures.mock_serial_data import (
    simulate_device_connection,
    MockCPCResponses,
    MockPSMResponses,
    MockSerialSequence
)
from config import CPC, PSM, PSM2


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_device_parameter():
    """Mock parameter object for device initialization."""
    param = Mock()
    param.name.return_value = "Test Device"

    def child_side_effect(name):
        child = Mock()
        if name == '10 hz':
            child.value.return_value = False
        elif name == 'Database enabled':
            child.value.return_value = False
        elif name == 'DB averaging interval':
            child.value.return_value = '1 min'
        elif name == 'Linked RHTP':
            child.value.return_value = None
        else:
            child.value.return_value = None
        child.setValue = Mock()
        return child

    param.child = Mock(side_effect=child_side_effect)

    # Mock parent for CPC database tab
    parent_mock = Mock()
    parent_mock.rhtp_dict = {}  # Empty dict for RHTP devices
    parent_mock.cpc_dict = {}   # Empty dict for CPC devices
    param.parent.return_value = parent_mock

    return param


@pytest.fixture
def mock_serial_connection():
    """Mock serial connection object."""
    mock_conn = Mock()
    mock_conn.connection = Mock()
    mock_conn.connection.is_open = True
    mock_conn.connection.read_all = Mock(return_value=b"")
    mock_conn.send_message = Mock()
    mock_conn.send_delayed_message = Mock()
    return mock_conn


# ============================================================================
# CPC Connection Flow Tests
# ============================================================================

class TestCPCConnectionFlow:
    """Test CPC device connection flow using simulate_device_connection."""

    def test_cpc_connection_sequence(self, qapp, mock_device_parameter):
        """Test complete CPC connection sequence: IDN → Firmware → Data."""
        # Create CPC widget
        cpc = CPCWidget(mock_device_parameter)

        # Create mock connection with simulated response sequence
        mock_conn = Mock()
        sequence = simulate_device_connection("CPC")
        mock_conn.connection = Mock()
        mock_conn.connection.read_all = sequence

        # Simulate connection flow
        # 1. First call: IDN response
        data1 = cpc.handle_serial_data(mock_conn)
        assert len(data1) == 1
        assert data1[0]['type'] == 'info'
        assert data1[0]['command'] == '*IDN'
        assert 'A11' in data1[0]['data']

        # 2. Second call: Firmware response
        data2 = cpc.handle_serial_data(mock_conn)
        assert len(data2) == 1
        # Firmware response is treated as info/unknown

        # 3. Third call: First data message
        data3 = cpc.handle_serial_data(mock_conn)
        assert len(data3) == 1
        assert data3[0]['type'] == 'data'
        assert data3[0]['command'] == ':MEAS:ALL'
        assert cpc.current_data.concentration == 1234.5

        # 4. Fourth call: Second data message (continuous operation)
        data4 = cpc.handle_serial_data(mock_conn)
        assert len(data4) == 1
        assert data4[0]['type'] == 'data'

    def test_cpc_command_sequence_after_connection(self, qapp, mock_device_parameter, mock_serial_connection):
        """Test that CPC sends correct command sequence after connection."""
        cpc = CPCWidget(mock_device_parameter)

        # Get command sequence for normal mode
        sequence = cpc.get_read_command_sequence(ten_hz=False)

        # Verify sequence matches monolith app
        assert sequence == [
            (':MEAS:ALL', 0),
            (':SYST:PRNT', 150),
            (':SYST:PALL', 300),
        ]

        # Verify commands are sent with correct delays
        # (In real implementation, these would be sent via send_multiple_messages)


# ============================================================================
# PSM Connection Flow Tests
# ============================================================================

class TestPSMConnectionFlow:
    """Test PSM device connection flow using simulate_device_connection."""

    def test_psm_retrofit_connection_sequence(self, qapp, mock_device_parameter):
        """Test complete PSM Retrofit connection sequence."""
        # Create PSM widget
        psm = PSMWidget(mock_device_parameter, device_type=PSM)

        # Create mock connection with simulated response sequence
        mock_conn = Mock()
        sequence = simulate_device_connection("PSM")
        mock_conn.connection = Mock()
        mock_conn.connection.read_all = sequence

        # 1. First call: IDN response
        data1 = psm.handle_serial_data(mock_conn)
        assert len(data1) == 1
        assert data1[0]['type'] == 'info'
        assert data1[0]['command'] == '*IDN'
        assert 'PSM 1.0' in data1[0]['data']

        # 2. Second call: Firmware response
        data2 = psm.handle_serial_data(mock_conn)
        assert len(data2) == 1

        # 3. Third call: First data message (auto-pushed)
        data3 = psm.handle_serial_data(mock_conn)
        assert len(data3) == 1
        # PSM data parsing happens here

    def test_psm2_connection_sequence(self, qapp, mock_device_parameter):
        """Test complete PSM 2.0 connection sequence."""
        psm = PSMWidget(mock_device_parameter, device_type=PSM2)

        mock_conn = Mock()
        sequence = simulate_device_connection("PSM2")
        mock_conn.connection = Mock()
        mock_conn.connection.read_all = sequence

        # 1. IDN response
        data1 = psm.handle_serial_data(mock_conn)
        assert len(data1) == 1
        assert 'PSM 2.0' in data1[0]['data']

    def test_psm_settings_fetch_on_connection(self, qapp, mock_device_parameter, mock_serial_connection):
        """Test that PSM fetches settings on initial connection."""
        psm = PSMWidget(mock_device_parameter, device_type=PSM)

        # Verify needs_settings_fetch is True initially
        assert psm.needs_settings_fetch is True

        # Call send_read_commands (simulates connection established)
        psm.send_read_commands(mock_serial_connection, None)

        # Should send :SYST:PRNT immediately
        mock_serial_connection.send_message.assert_called_once_with(":SYST:PRNT")

        # Should send :SYST:VCMP with delay
        mock_serial_connection.send_delayed_message.assert_called_once_with(":SYST:VCMP", 150)


# ============================================================================
# Multi-Device Connection Tests
# ============================================================================

class TestMultipleDeviceConnections:
    """Test connecting multiple devices simultaneously."""

    def test_cpc_and_psm_connection(self, qapp, mock_device_parameter):
        """Test connecting both CPC and PSM (common configuration)."""
        # Create both devices
        cpc = CPCWidget(mock_device_parameter)
        psm = PSMWidget(mock_device_parameter, device_type=PSM)

        # Assign device IDs (like in real app)
        cpc.dev_id = 0
        psm.dev_id = 1

        # Create separate mock connections
        mock_conn_cpc = Mock()
        mock_conn_cpc.connection = Mock()
        mock_conn_cpc.connection.read_all = simulate_device_connection("CPC")

        mock_conn_psm = Mock()
        mock_conn_psm.connection = Mock()
        mock_conn_psm.connection.read_all = simulate_device_connection("PSM")

        # Simulate parallel connections
        cpc_data = cpc.handle_serial_data(mock_conn_cpc)
        psm_data = psm.handle_serial_data(mock_conn_psm)

        # Both should receive IDN
        assert cpc_data[0]['command'] == '*IDN'
        assert psm_data[0]['command'] == '*IDN'

        # Different serial numbers
        assert 'A11' in cpc_data[0]['data']
        assert 'PSM' in psm_data[0]['data']


# ============================================================================
# Connection Error Handling Tests
# ============================================================================

class TestConnectionErrorHandling:
    """Test error handling during connection sequence."""

    def test_connection_with_partial_idn(self, qapp, mock_device_parameter):
        """Test handling of incomplete IDN response."""
        cpc = CPCWidget(mock_device_parameter)

        # Create sequence with partial IDN
        mock_conn = Mock()
        mock_conn.connection = Mock()
        mock_conn.connection.read_all = Mock(return_value=b"*IDN Airmo")  # Incomplete

        # Should handle gracefully
        data = cpc.handle_serial_data(mock_conn)
        # Will be stored in partial_data buffer
        assert isinstance(data, list)

    def test_connection_with_no_response(self, qapp, mock_device_parameter):
        """Test handling when device doesn't respond."""
        cpc = CPCWidget(mock_device_parameter)

        mock_conn = Mock()
        mock_conn.connection = Mock()
        mock_conn.connection.read_all = Mock(return_value=b"")  # Empty response

        data = cpc.handle_serial_data(mock_conn)
        assert data == []  # No data returned


# ============================================================================
# Real-World Sequence Tests
# ============================================================================

class TestRealWorldSequences:
    """Test sequences that match real device behavior."""

    def test_cpc_with_settings_query(self, qapp, mock_device_parameter):
        """Test CPC connection with settings query (full sequence)."""
        cpc = CPCWidget(mock_device_parameter)
        cpc.dev_id = 0

        # Create realistic sequence: IDN, DATA, PRNT, PALL
        responses = MockSerialSequence([
            MockCPCResponses.IDN,
            MockCPCResponses.DATA_NORMAL,
            b":SYST:PRNT 30,1,1500,800,90,40,10,1,150,200,0,1,1\r",
            b":SYST:PALL 0,200,1000,90,40,10,1.5,150,200,0,1,1,0,0,0,0,0,0,0,0,0,0,A,2.1,1.0,100,120,130\r",
        ])

        mock_conn = Mock()
        mock_conn.connection = Mock()
        mock_conn.connection.read_all = responses

        # Process sequence
        results = []
        for _ in range(4):
            data = cpc.handle_serial_data(mock_conn)
            if data:
                results.extend(data)

        # Should have IDN, DATA, PRNT, PALL
        assert len(results) == 4
        assert results[0]['command'] == '*IDN'
        assert results[1]['command'] == ':MEAS:ALL'
        assert results[2]['command'] == ':SYST:PRNT'
        assert results[3]['command'] == ':SYST:PALL'

    def test_psm_with_dilution_params(self, qapp, mock_device_parameter):
        """Test PSM connection with dilution parameter query."""
        psm = PSMWidget(mock_device_parameter, device_type=PSM)
        psm.dev_id = 1

        # Create realistic sequence: IDN, DATA, PRNT, VCMP
        responses = MockSerialSequence([
            MockPSMResponses.IDN_RETROFIT,
            b":MEAS:SCAN 1.0,0.7,90.0,40.0,25.0,85.0,30.0,28.0,1.0,1013.2,0.3,450.0,10.5,0,0.5,0x000,0x00\r",
            b":SYST:PRNT 1,90.0,40.0,25.0,85.0,30.0,1.5\r",
            b":SYST:VCMP 0.24343024,-0.20675596,-0.08959011,0.11394213,-0.0272052,1.10531145\r",
        ])

        mock_conn = Mock()
        mock_conn.connection = Mock()
        mock_conn.connection.read_all = responses

        # Create mock data holder
        data_holder = Mock()
        data_holder.extra_data = {}
        data_holder.device_errors = {}
        data_holder.error_status = 0
        data_holder.par_updates = {}
        data_holder.latest_settings = {}

        # Process sequence
        results = []
        for _ in range(4):
            data = psm.handle_serial_data(mock_conn, data_holder)
            if data:
                results.extend(data)

        # Should have IDN, DATA, PRNT, VCMP
        assert len(results) >= 4

        # Find VCMP response
        vcmp_found = False
        for result in results:
            if result['command'] == ':SYST:VCMP':
                vcmp_found = True
                # Should have 6 dilution parameters
                assert len(result['data']) == 6
                break

        assert vcmp_found, "VCMP response not found in sequence"


# ============================================================================
# Mark Tests
# ============================================================================

pytestmark = pytest.mark.integration
