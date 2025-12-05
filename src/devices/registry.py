"""
Device Registry - Declarative configuration for all device types.

This registry eliminates the need for device-specific if/elif chains in app.py.
To add a new device, simply add one entry to this registry.

New devices can use the @register_device decorator for automatic registration.
"""

from config import (CPC, PSM, ELECTROMETER, CO2_SENSOR, RHTP, AFM,
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

    def create_widget(self, device_config):
        """Create widget instance for this device type."""
        return self.widget_class(device_config)

    def setup_connections(self, widget, device_config, connection, app):
        """Set up device-specific signal/slot connections."""
        if self.setup_connections_func:
            self.setup_connections_func(widget, device_config, connection, app)


# Connection setup functions for each device type
def setup_cpc_connections(widget, device_config, connection, app):
    """Set up CPC-specific connections."""
    from utils import command_entered

    device_id = device_config.device_id

    # Set tab buttons
    widget.set_tab.drain.clicked.connect(
        lambda: connection.send_message(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
    widget.set_tab.autofill.clicked.connect(
        lambda: connection.send_message(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
    widget.set_tab.water_removal.clicked.connect(
        lambda: connection.send_message(":SET:WREM " + str(int(widget.set_tab.water_removal.isChecked()))))

    # Command input
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: command_entered(device_id, app.data_holder.device_widgets, app.config))

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
        lambda: app.data_logger.pulse_analysis_start(device_id, device_config))


def setup_psm_connections(widget, device_config, connection, app):
    """Set up PSM-specific connections."""
    from utils import command_entered, ten_hz_clicked, psm_update, psm_flow_send, cpc_flow_send

    device_id = device_config.device_id
    device_type = device_config.device_type

    # Measure tab buttons
    widget.measure_tab.scan.clicked.connect(
        lambda: connection.send_message(widget.measure_tab.compile_scan()))
    widget.measure_tab.step.clicked.connect(
        lambda: connection.send_message(widget.measure_tab.compile_step()))
    widget.measure_tab.fixed.clicked.connect(
        lambda: connection.send_message(widget.measure_tab.compile_fixed()))
    widget.measure_tab.ten_hz.clicked.connect(
        lambda: ten_hz_clicked(widget, app.config))

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
        lambda value: psm_flow_send(widget, value))
    widget.set_tab.set_cpc_inlet_flow.value_spinbox.stepChanged.connect(
        lambda: psm_update(device_id, app.data_holder.device_widgets))
    widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(
        lambda: psm_flow_send(widget, float(widget.set_tab.set_cpc_inlet_flow.value_input.text())))
    widget.set_tab.set_cpc_inlet_flow.value_input.returnPressed.connect(
        lambda: psm_update(device_id, app.data_holder.device_widgets))

    # CPC sample flow
    widget.set_tab.set_cpc_sample_flow.value_spinbox.stepChanged.connect(
        lambda value: cpc_flow_send(widget, value, app.data_holder.device_widgets))
    widget.set_tab.set_cpc_sample_flow.value_input.returnPressed.connect(
        lambda: cpc_flow_send(widget, float(widget.set_tab.set_cpc_sample_flow.value_input.text()), app.data_holder.device_widgets))

    # CO flow (PSM Retrofit only) - Save to extra_params
    from config import PSM
    if device_type == PSM:
        widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(
            lambda: psm_update(device_id, app.data_holder.device_widgets))
        widget.set_tab.set_co_flow.value_input.returnPressed.connect(
            lambda: psm_update(device_id, app.data_holder.device_widgets))
        widget.set_tab.set_co_flow.value_spinbox.stepChanged.connect(
            lambda value: device_config.extra_params.update({'co_flow': str(round(value, 3))}))
        widget.set_tab.set_co_flow.value_input.returnPressed.connect(
            lambda: device_config.extra_params.update({'co_flow': widget.set_tab.set_co_flow.value_input.text()}))

    # Command input
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: command_entered(device_id, app.data_holder.device_widgets, app.config))
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: psm_update(device_id, app.data_holder.device_widgets))

    # Liquid operations
    widget.set_tab.autofill.clicked.connect(
        lambda: connection.send_message(":SET:AFLL " + str(int(widget.set_tab.autofill.isChecked()))))
    widget.set_tab.drain.clicked.connect(
        lambda: connection.send_message(":SET:DRN " + str(int(widget.set_tab.drain.isChecked()))))
    widget.set_tab.drying.clicked.connect(
        lambda: connection.send_message(widget.set_tab.drying.messages[int(widget.set_tab.drying.isChecked())]))


def setup_ediluter_connections(widget, device_config, connection, app):
    """Set up eDiluter-specific connections."""
    from utils import command_entered
    device_id = device_config.device_id

    # Mode buttons
    widget.set_tab.init.clicked.connect(
        lambda: connection.send_message("do set app.measurement.state INIT"))
    widget.set_tab.warmup.clicked.connect(
        lambda: connection.send_message("do set app.measurement.state WARMUP"))
    widget.set_tab.standby.clicked.connect(
        lambda: connection.send_message("do set app.measurement.state STANDBY"))
    widget.set_tab.measurement.clicked.connect(
        lambda: connection.send_message("do set app.measurement.state MEASUREMENT"))

    # Dilution factor buttons
    widget.set_tab.df_1.prev_button.clicked.connect(
        lambda: connection.send_message("do set dilution.1st.prev true"))
    widget.set_tab.df_1.next_button.clicked.connect(
        lambda: connection.send_message("do set dilution.1st.next true"))
    widget.set_tab.df_2.prev_button.clicked.connect(
        lambda: connection.send_message("do set dilution.2nd.prev true"))
    widget.set_tab.df_2.next_button.clicked.connect(
        lambda: connection.send_message("do set dilution.2nd.next true"))

    # Command input
    widget.set_tab.command_widget.command_input.returnPressed.connect(
        lambda: command_entered(device_id, app.data_holder.device_widgets, app.config))


def setup_tsi_cpc_connections(widget, device_config, connection, app):
    """Set up TSI CPC-specific connections."""
    # Store baud rate in extra_params
    if 'baud_rate' not in device_config.extra_params:
        device_config.extra_params['baud_rate'] = 115200
        connection.set_baud_rate(115200)


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

    # PSM2 removed - configs migrated to PSM, version determined by firmware

    ELECTROMETER: DeviceConfig(
        widget_class=ElectrometerWidget,
        setup_connections_func=None,  # No special connections
        has_special_setup=True  # Has special viewbox setup
    ),

    # CO2_SENSOR: Now registered via @register_device decorator in co2.py

    RHTP: DeviceConfig(
        widget_class=RHTPWidget,
        has_special_setup=True  # Has special viewbox setup
    ),

    AFM: DeviceConfig(
        widget_class=AFMWidget,
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


def create_device_widget(device_type, device_config):
    """
    Factory function to create a device widget.

    Args:
        device_type: Device type constant (CPC, PSM, etc.)
        device_config: DeviceConfig instance

    Returns:
        Device widget instance

    Raises:
        ValueError: If device type is not in registry
    """
    if device_type not in DEVICE_REGISTRY:
        raise ValueError(f"Unknown device type: {device_type}")

    config = DEVICE_REGISTRY[device_type]
    return config.create_widget(device_config)


def setup_device_connections(device_type, widget, device_config, connection, app):
    """
    Set up device-specific signal/slot connections.

    Args:
        device_type: Device type constant
        widget: Device widget instance
        device_config: DeviceConfig instance
        connection: Serial connection object
        app: Main application instance
    """
    if device_type not in DEVICE_REGISTRY:
        return

    config = DEVICE_REGISTRY[device_type]
    if config.setup_connections_func:
        config.setup_connections_func(widget, device_config, connection, app)


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
