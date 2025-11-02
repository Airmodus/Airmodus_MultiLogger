"""
Device Registry - Declarative configuration for all device types.

This registry eliminates the need for device-specific if/elif chains in app.py.
To add a new device, simply add one entry to this registry.

New devices can use the @register_device decorator for automatic registration.
"""

from config import (CPC, PSM, PSM2, ELECTROMETER, CO2_SENSOR, RHTP, AFM,
                   EDILUTER, TSI_CPC, EXAMPLE_DEVICE)


# Decorator for automatic device registration
def register_device(device_type, setup_connections_func=None, has_special_setup=False):
    """
    Decorator to automatically register a device widget class.

    Usage:
        @register_device(MY_DEVICE, simple=True)
        class MyDeviceWidget(SimpleDevice):
            ...

    Args:
        device_type: Device type constant from config
        setup_connections_func: Optional function to set up device-specific connections
        has_special_setup: Whether device needs special viewbox setup

    Returns:
        Decorator function that registers the class
    """
    def decorator(widget_class):
        # Register the device in the global registry
        DEVICE_REGISTRY[device_type] = DeviceConfig(
            widget_class=widget_class,
            setup_connections_func=setup_connections_func,
            has_special_setup=has_special_setup
        )
        return widget_class
    return decorator


class DeviceConfig:
    """Configuration for a single device type."""

    def __init__(self, widget_class, setup_connections_func=None, has_special_setup=False):
        """
        Args:
            widget_class: The widget class to instantiate (e.g., CPCWidget)
            setup_connections_func: Optional function to set up device-specific connections
            has_special_setup: Whether device needs special setup beyond basic connections
        """
        self.widget_class = widget_class
        self.setup_connections_func = setup_connections_func
        self.has_special_setup = has_special_setup

    def create_widget(self, device_param, device_type=None):
        """Create widget instance for this device type."""
        if device_type:
            return self.widget_class(device_param, device_type)
        else:
            return self.widget_class(device_param)

    def setup_connections(self, widget, device_param, connection, app):
        """Set up device-specific signal/slot connections."""
        if self.setup_connections_func:
            self.setup_connections_func(widget, device_param, connection, app)


# Connection setup functions for each device type
def setup_cpc_connections(widget, device_param, connection, app):
    """Set up CPC-specific connections."""
    from utils import command_entered

    device_id = device_param.child('DevID').value()

    # Set tab buttons
    widget.set_tab.drain.clicked.connect(
        lambda: connection.send_set(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
    widget.set_tab.autofill.clicked.connect(
        lambda: connection.send_set(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
    widget.set_tab.water_removal.clicked.connect(
        lambda: connection.send_set(":SET:WREM " + str(int(widget.set_tab.water_removal.isChecked()))))

    # Command input
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: command_entered(device_id, device_param, app.data_holder.device_widgets,
                               app.data_holder.latest_command))

    # Set points
    widget.set_tab.set_saturator_temp.value_spinbox.stepChanged.connect(
        lambda value: connection.send_set_val(value, ":SET:TEMP:SAT "))
    widget.set_tab.set_saturator_temp.value_input.returnPressed.connect(
        lambda: connection.send_set_val(float(widget.set_tab.set_saturator_temp.value_input.text()), ":SET:TEMP:SAT "))

    widget.set_tab.set_condenser_temp.value_spinbox.stepChanged.connect(
        lambda value: connection.send_set_val(value, ":SET:TEMP:CON "))
    widget.set_tab.set_condenser_temp.value_input.returnPressed.connect(
        lambda: connection.send_set_val(float(widget.set_tab.set_condenser_temp.value_input.text()), ":SET:TEMP:CON "))

    # Averaging time with special formatting
    def send_averaging_time(value: float):
        output = value if value < 1.0 else round(value)
        connection.send_set_val(output, ":SET:TAVG ")

    widget.set_tab.set_averaging_time.value_spinbox.stepChanged.connect(send_averaging_time)
    widget.set_tab.set_averaging_time.value_input.returnPressed.connect(
        lambda: send_averaging_time(float(widget.set_tab.set_averaging_time.value_input.text())))

    # Pulse quality
    widget.pulse_quality.history_time_select.currentIndexChanged.connect(
        lambda: app.plot_manager.pulse_quality_update(device_id))
    widget.pulse_quality.average_time_select.currentIndexChanged.connect(
        lambda: app.plot_manager.pulse_quality_update(device_id))
    widget.pulse_quality.start_analysis.clicked.connect(
        lambda: app.pulse_analysis_start(device_id, device_param))

    # Update CPC dict on nickname change
    device_param.child("Device nickname").sigValueChanged.connect(
        device_param.parent().update_cpc_dict)


def setup_psm_connections(widget, device_param, connection, app):
    """Set up PSM-specific connections."""
    from utils import command_entered, ten_hz_clicked, psm_update, psm_flow_send, cpc_flow_send

    device_id = device_param.child('DevID').value()
    device_type = device_param.child('Device type').value()

    # Measure tab buttons
    widget.measure_tab.scan.clicked.connect(
        lambda: connection.send_set(widget.measure_tab.compile_scan()))
    widget.measure_tab.step.clicked.connect(
        lambda: connection.send_set(widget.measure_tab.compile_step()))
    widget.measure_tab.fixed.clicked.connect(
        lambda: connection.send_set(widget.measure_tab.compile_fixed()))
    widget.measure_tab.ten_hz.clicked.connect(
        lambda: ten_hz_clicked(device_param, widget))

    # Temperature setpoints
    temps = [
        ('set_growth_tube_temp', ':SET:TEMP:GT '),
        ('set_saturator_temp', ':SET:TEMP:SAT '),
        ('set_inlet_temp', ':SET:TEMP:INL '),
        ('set_heater_temp', ':SET:TEMP:PRE '),
        ('set_drainage_temp', ':SET:TEMP:DRN ')
    ]

    for attr_name, command in temps:
        set_widget = getattr(widget.set_tab, attr_name)
        set_widget.value_spinbox.stepChanged.connect(
            lambda value, cmd=command: connection.send_set_val(value, cmd))
        set_widget.value_spinbox.stepChanged.connect(
            lambda: psm_update(device_id, app.data_holder.device_widgets))
        set_widget.value_input.returnPressed.connect(
            lambda cmd=command, attr=attr_name: connection.send_set_val(float(getattr(widget.set_tab, attr).value_input.text()), cmd))
        set_widget.value_input.returnPressed.connect(
            lambda: psm_update(device_id, app.data_holder.device_widgets))

    # CPC inlet flow
    widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(
        lambda value: psm_flow_send(device_param, value))
    widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(
        lambda: psm_update(device_id, app.data_holder.device_widgets))
    widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(
        lambda: psm_flow_send(device_param, float(widget.set_tab.set_cpc_inlet_flow.value_input.text())))
    widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(
        lambda: psm_update(device_id, app.data_holder.device_widgets))

    # CPC sample flow
    widget.set_tab.set_cpc_sample_flow.value_spinbox.stepChanged.connect(
        lambda value: cpc_flow_send(device_param, value))
    widget.set_tab.set_cpc_sample_flow.value_input.returnPressed.connect(
        lambda: cpc_flow_send(device_param, float(widget.set_tab.set_cpc_sample_flow.value_input.text())))

    # CO flow (PSM Retrofit only)
    from config import PSM
    if device_type == PSM:
        widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(
            lambda: psm_update(device_id, app.data_holder.device_widgets))
        widget.set_tab.set_co_flow.value_input.returnPressed.connect(
            lambda: psm_update(device_id, app.data_holder.device_widgets))
        widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(
            lambda value: device_param.child('CO flow').setValue(str(round(value, 3))))
        widget.set_tab.set_co_flow.value_input.returnPressed.connect(
            lambda: device_param.child('CO flow').setValue(widget.set_tab.set_co_flow.value_input.text()))

    # Command input
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: command_entered(device_id, device_param, app.data_holder.device_widgets,
                               app.data_holder.latest_command))
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: psm_update(device_id, app.data_holder.device_widgets))

    # Liquid operations
    widget.set_tab.autofill.clicked.connect(
        lambda: connection.send_set(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
    widget.set_tab.drain.clicked.connect(
        lambda: connection.send_set(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
    widget.set_tab.drying.clicked.connect(
        lambda: connection.send_set(widget.set_tab.drying.messages[int(widget.set_tab.drying.isChecked())]))

    # Wire up connected CPC device reference
    def update_connected_cpc():
        """Update PSM's reference to connected CPC widget."""
        cpc_id = device_param.child('Connected CPC').value()
        if cpc_id != 'None':
            widget.connected_cpc_device = app.data_holder.device_widgets.get(cpc_id)
        else:
            widget.connected_cpc_device = None

    # Set initial reference and update when parameter changes
    update_connected_cpc()
    device_param.child('Connected CPC').sigValueChanged.connect(lambda: update_connected_cpc())


def setup_ediluter_connections(widget, device_param, connection, app):
    """Set up eDiluter-specific connections."""
    device_id = device_param.child('DevID').value()

    # Mode buttons
    widget.set_tab.init.clicked.connect(
        lambda: connection.send_set("do set app.measurement.state INIT"))
    widget.set_tab.warmup.clicked.connect(
        lambda: connection.send_set("do set app.measurement.state WARMUP"))
    widget.set_tab.standby.clicked.connect(
        lambda: connection.send_set("do set app.measurement.state STANDBY"))
    widget.set_tab.measurement.clicked.connect(
        lambda: connection.send_set("do set app.measurement.state MEASUREMENT"))

    # Dilution factor buttons
    widget.set_tab.df_1.prev_button.clicked.connect(
        lambda: connection.send_set("do set dilution.1st.prev true"))
    widget.set_tab.df_1.next_button.clicked.connect(
        lambda: connection.send_set("do set dilution.1st.next true"))
    widget.set_tab.df_2.prev_button.clicked.connect(
        lambda: connection.send_set("do set dilution.2nd.prev true"))
    widget.set_tab.df_2.next_button.clicked.connect(
        lambda: connection.send_set("do set dilution.2nd.next true"))

    # Command input
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: app.command_entered(device_id, device_param, app.data_holder.device_widgets,
                                    app.data_holder.latest_command))


def setup_tsi_cpc_connections(widget, device_param, connection, app):
    """Set up TSI CPC-specific connections."""
    # Add baud rate parameter
    device_param.addChild({'name': 'Baud rate', 'type': 'int', 'value': 115200})
    device_param.child('Baud rate').sigValueChanged.connect(
        lambda: connection.set_baud_rate(device_param.child('Baud rate').value()))

    # Update CPC dict on nickname change
    device_param.child("Device nickname").sigValueChanged.connect(
        device_param.parent().update_cpc_dict)


def setup_rhtp_connections(widget, device_param, connection, app):
    """Set up RHTP-specific connections."""
    from PyQt5.QtCore import QTimer
    device_id = device_param.child('DevID').value()

    # Check if there are other RHTP devices
    for dev in app.params.child('Device settings').children():
        if dev.child('Device type').value() == RHTP and dev.child('DevID').value() != device_id:
            QTimer.singleShot(50, lambda d=dev: app.rhtp_axis_changed(d.child('Plot to main').value()))
            break

    # Connect plot axis change
    QTimer.singleShot(60, lambda: device_param.child("Plot to main").sigValueChanged.connect(
        lambda parameter: app.rhtp_axis_changed(parameter.value())))


def setup_afm_connections(widget, device_param, connection, app):
    """Set up AFM-specific connections."""
    from PyQt5.QtCore import QTimer
    device_id = device_param.child('DevID').value()

    # Check if there are other AFM devices
    for dev in app.params.child('Device settings').children():
        if dev.child('Device type').value() == AFM and dev.child('DevID').value() != device_id:
            QTimer.singleShot(50, lambda d=dev: app.afm_axis_changed(d.child('Plot to main').value()))
            break

    # Connect plot axis change
    QTimer.singleShot(60, lambda: device_param.child("Plot to main").sigValueChanged.connect(
        lambda parameter: app.afm_axis_changed(parameter.value())))


from devices.cpc import CPCWidget
from devices.psm import PSMWidget
from devices.rhtp import RHTPWidget
from devices.afm import AFMWidget
from devices.ediluter import eDiluterWidget
from devices.electrometer import ElectrometerWidget
from devices.tsi_cpc import TSIWidget


DEVICE_REGISTRY = {
    CPC: DeviceConfig(
        widget_class=CPCWidget,
        setup_connections_func=setup_cpc_connections,
        has_special_setup=False
    ),

    PSM: DeviceConfig(
        widget_class=PSMWidget,
        setup_connections_func=setup_psm_connections,
        has_special_setup=False
    ),

    PSM2: DeviceConfig(
        widget_class=PSMWidget,
        setup_connections_func=setup_psm_connections,
        has_special_setup=False
    ),

    ELECTROMETER: DeviceConfig(
        widget_class=ElectrometerWidget,
        setup_connections_func=None,  # No special connections
        has_special_setup=True  # Has special viewbox setup
    ),

    # CO2_SENSOR: Now registered via @register_device decorator in co2.py

    RHTP: DeviceConfig(
        widget_class=RHTPWidget,
        setup_connections_func=setup_rhtp_connections,
        has_special_setup=True  # Has special viewbox setup
    ),

    AFM: DeviceConfig(
        widget_class=AFMWidget,
        setup_connections_func=setup_afm_connections,
        has_special_setup=True  # Has special viewbox setup
    ),

    EDILUTER: DeviceConfig(
        widget_class=eDiluterWidget,
        setup_connections_func=setup_ediluter_connections,
        has_special_setup=False
    ),

    TSI_CPC: DeviceConfig(
        widget_class=TSIWidget,
        setup_connections_func=setup_tsi_cpc_connections,
        has_special_setup=False
    ),

    # EXAMPLE_DEVICE: Now registered via @register_device decorator in example.py
}


def create_device_widget(device_type, device_param):
    """
    Factory function to create a device widget.

    Args:
        device_type: Device type constant (CPC, PSM, etc.)
        device_param: Device parameter tree reference

    Returns:
        Device widget instance

    Raises:
        ValueError: If device type is not in registry
    """
    if device_type not in DEVICE_REGISTRY:
        raise ValueError(f"Unknown device type: {device_type}")

    config = DEVICE_REGISTRY[device_type]
    return config.create_widget(device_param, device_type if device_type in [PSM, PSM2] else None)


def setup_device_connections(device_type, widget, device_param, connection, app):
    """
    Set up device-specific signal/slot connections.

    Args:
        device_type: Device type constant
        widget: Device widget instance
        device_param: Device parameter tree reference
        connection: Serial connection object
        app: Main application instance
    """
    if device_type not in DEVICE_REGISTRY:
        return

    config = DEVICE_REGISTRY[device_type]
    if config.setup_connections_func:
        config.setup_connections_func(widget, device_param, connection, app)


def has_special_viewbox_setup(device_type):
    """Check if device needs special viewbox setup."""
    if device_type not in DEVICE_REGISTRY:
        return False
    return DEVICE_REGISTRY[device_type].has_special_setup


__all__ = [
    'DEVICE_REGISTRY',
    'register_device',
    'create_device_widget',
    'setup_device_connections',
    'has_special_viewbox_setup',
]
