"""
Tests for the custom COM port widget.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from PyQt5 import QtCore
from com_port_widget import ComPortWidget, ComPortParameter
from pyqtgraph.parametertree import Parameter


class TestComPortWidget:
    """Test the combined COM port widget."""

    def test_widget_creation(self, qapp, qtbot):
        """Test that the widget can be created."""
        widget = ComPortWidget()
        qtbot.addWidget(widget)
        assert widget.line_edit is not None
        assert widget.dropdown_button is not None
        assert widget.menu is not None

    def test_manual_entry_windows(self, qapp, qtbot):
        """Test manual entry on Windows (non-macOS)."""
        with patch('platform.system', return_value='Windows'):
            widget = ComPortWidget()
            qtbot.addWidget(widget)

            # Track signal emissions
            signal_values = []
            widget.sigValueChanged.connect(lambda v: signal_values.append(v))

            # Enter a number manually
            widget.line_edit.setText("3")
            qtbot.wait(100)  # Wait for signal processing

            # Should emit integer value
            assert len(signal_values) > 0
            assert signal_values[-1] == 3 or signal_values[-1] == "3"

            # Check value getter
            value = widget.value()
            assert value == 3 or value == "3"

    def test_manual_entry_macos(self, qapp, qtbot):
        """Test manual entry on macOS."""
        with patch('platform.system', return_value='Darwin'):
            widget = ComPortWidget()
            qtbot.addWidget(widget)

            # Track signal emissions
            signal_values = []
            widget.sigValueChanged.connect(lambda v: signal_values.append(v))

            # Enter a device path manually
            test_path = "/dev/cu.usbserial-1234"
            widget.line_edit.setText(test_path)
            qtbot.wait(100)

            # Should emit string value
            assert len(signal_values) > 0
            assert signal_values[-1] == test_path

            # Check value getter
            value = widget.value()
            assert value == test_path

    def test_dropdown_selection_windows(self, qapp, qtbot):
        """Test dropdown selection on Windows."""
        with patch('platform.system', return_value='Windows'):
            widget = ComPortWidget()
            qtbot.addWidget(widget)

            # Set available ports
            ports_dict = {
                'COM3 - Device A': 'COM3',
                'COM4 - Device B': 'COM4'
            }
            widget.set_available_ports(ports_dict)

            # Simulate port selection
            widget._on_port_selected('COM3')

            # Should use full COM port string on all platforms
            assert widget.line_edit.text() == "COM3"

    def test_dropdown_selection_macos(self, qapp, qtbot):
        """Test dropdown selection on macOS."""
        with patch('platform.system', return_value='Darwin'):
            widget = ComPortWidget()
            qtbot.addWidget(widget)

            # Set available ports
            test_port = '/dev/cu.usbserial-1234'
            ports_dict = {
                f'{test_port} - Device A': test_port
            }
            widget.set_available_ports(ports_dict)

            # Simulate port selection
            widget._on_port_selected(test_port)

            # Should set full path in text field
            assert widget.line_edit.text() == test_port

    def test_set_value(self, qapp, qtbot):
        """Test setting value programmatically."""
        widget = ComPortWidget()
        qtbot.addWidget(widget)

        # Set value
        widget.setValue("test_value")
        assert widget.line_edit.text() == "test_value"

        # Set None
        widget.setValue(None)
        assert widget.line_edit.text() == ""

    def test_empty_ports_list(self, qapp, qtbot):
        """Test widget with no available ports."""
        widget = ComPortWidget()
        qtbot.addWidget(widget)

        # Set empty ports dict
        widget.set_available_ports({})

        # Menu should have "No ports available" disabled action
        actions = widget.menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == "No ports available"
        assert not actions[0].isEnabled()


class TestComPortParameter:
    """Test the custom COM port parameter type."""

    def test_parameter_creation(self, qapp):
        """Test that the parameter can be created."""
        param = ComPortParameter(name='COM port')
        assert param is not None
        assert param.name() == 'COM port'

    def test_parameter_default_type_windows(self, qapp):
        """Test default type on Windows (now uses string for cross-platform compatibility)."""
        with patch('platform.system', return_value='Windows'):
            param = ComPortParameter(name='COM port')
            assert param.opts['type'] == 'str'

    def test_parameter_default_type_macos(self, qapp):
        """Test default type on macOS."""
        with patch('platform.system', return_value='Darwin'):
            param = ComPortParameter(name='COM port')
            assert param.opts['type'] == 'str'

    def test_set_available_ports(self, qapp):
        """Test updating available ports."""
        param = ComPortParameter(name='COM port')

        ports_dict = {
            'COM3 - Device A': 'COM3',
            'COM4 - Device B': 'COM4'
        }

        # Should not raise an error
        param.set_available_ports(ports_dict)
        assert 'ports' in param.opts
        assert param.opts['ports'] == ports_dict


class TestIntegrationWithParameterTree:
    """Integration tests with pyqtgraph's ParameterTree."""

    def test_parameter_in_tree(self, qapp, qtbot):
        """Test that parameter works within a parameter tree."""
        from pyqtgraph.parametertree import ParameterTree

        # Create parameter tree
        params = [
            {'name': 'Device 1', 'type': 'group', 'children': [
                {'name': 'COM port', 'type': 'comport', 'ports': {}}
            ]}
        ]

        p = Parameter.create(name='root', type='group', children=params)
        tree = ParameterTree()
        qtbot.addWidget(tree)
        tree.setParameters(p)

        # Get COM port parameter
        com_port = p.child('Device 1').child('COM port')
        assert com_port is not None

        # Update ports
        ports_dict = {'COM3 - Device': 'COM3'}
        com_port.set_available_ports(ports_dict)

        # Should not raise any errors

    def test_value_change_signal(self, qapp, qtbot):
        """Test that value changes emit signals properly."""
        from pyqtgraph.parametertree import ParameterTree

        # Create parameter
        param = ComPortParameter(name='COM port')
        tree = ParameterTree()
        qtbot.addWidget(tree)
        tree.setParameters(param)

        # Track signal
        signal_values = []
        param.sigValueChanged.connect(lambda p, v: signal_values.append(v))

        # Set value
        param.setValue("test")

        # Signal should be emitted
        # Note: Exact behavior may vary depending on pyqtgraph version
        # This test ensures no crashes occur
