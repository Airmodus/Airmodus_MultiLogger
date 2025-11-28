"""
Configuration Migration Utilities

Helper functions to migrate between old parameter tree format and new AppConfig dataclasses.
This module helps with the transition from PyQtGraph ParameterTree to typed dataclasses.
"""

from typing import Dict, Any
from devices.device_data import AppConfig, DataSettings, PlotSettings, DeviceConfig, create_device_settings
import config


def params_dict_to_app_config(params_dict: Dict[str, Any]) -> AppConfig:
    """
    Convert a saved parameter tree dictionary (from JSON) to AppConfig.

    Args:
        params_dict: Dictionary loaded from old config JSON format

    Returns:
        AppConfig instance with migrated data
    """
    # Extract data settings
    data_settings_dict = params_dict.get('Data settings', {})
    data_settings = DataSettings(
        file_path=data_settings_dict.get('File path', ''),
        file_tag=data_settings_dict.get('File tag', ''),
        save_data=data_settings_dict.get('Save data', False),
        generate_daily_files=data_settings_dict.get('Generate daily files', True),
        resume_on_startup=data_settings_dict.get('Resume on startup', False)
    )

    # Extract plot settings
    plot_settings_dict = params_dict.get('Plot settings', {})
    plot_settings = PlotSettings(
        follow=plot_settings_dict.get('Follow', True),
        time_window_s=float(plot_settings_dict.get('Time window (s)', 600)),
        autoscale_y=plot_settings_dict.get('Autoscale Y', True)
    )

    # Extract device configurations
    devices = []
    device_settings_dict = params_dict.get('Device settings', {})

    for device_name, device_params in device_settings_dict.items():
        # Skip if device params is empty or invalid
        if not device_params or not isinstance(device_params, dict):
            continue

        device_type = device_params.get('Device type')
        if device_type is None:
            continue

        # Get device type name
        device_type_name = _get_device_type_name(device_type)

        # Create typed settings object if available
        settings = create_device_settings(device_type)

        # Extract device-specific parameters (10 hz, Connected CPC, etc.)
        extra_params = {}
        if '10 hz' in device_params:
            extra_params['10_hz'] = device_params['10 hz']
        if 'Connected CPC' in device_params:
            extra_params['connected_cpc'] = device_params['Connected CPC']
        if 'Calibration file path' in device_params:
            extra_params['calibration_file_path'] = device_params['Calibration file path']
        if 'CO flow' in device_params:
            extra_params['co_flow'] = device_params['CO flow']
        if 'Firmware version' in device_params:
            extra_params['firmware_version'] = device_params['Firmware version']
        if 'Database enabled' in device_params:
            extra_params['database_enabled'] = device_params['Database enabled']
        if 'Linked RHTP' in device_params:
            extra_params['linked_rhtp'] = device_params['Linked RHTP']
        if 'DB averaging interval' in device_params:
            extra_params['db_averaging_interval'] = device_params['DB averaging interval']

        # Get COM port and convert old integer format to string format
        # Old configs stored port as int (e.g., 5), new format uses string (e.g., "COM5")
        raw_port = device_params.get('COM port', '')
        if isinstance(raw_port, int) and raw_port > 0:
            com_port = f"COM{raw_port}"
        else:
            com_port = raw_port

        # Create device config
        device_config = DeviceConfig(
            device_id=device_params.get('DevID', 0),
            device_type=device_type,
            device_type_name=device_type_name,
            com_port=com_port,
            serial_number=device_params.get('Serial number', ''),
            device_nickname=device_params.get('Device nickname', ''),
            plot_to_main=device_params.get('Plot to main', True),
            settings=settings,
            extra_params=extra_params
        )

        devices.append(device_config)

    return AppConfig(
        data_settings=data_settings,
        plot_settings=plot_settings,
        devices=devices
    )


def _get_device_type_name(device_type: int) -> str:
    """Convert device type ID to human-readable name."""
    type_map = {
        config.CPC: "CPC",
        config.PSM: "PSM Retrofit",
        config.PSM2: "PSM 2.0",
        config.ELECTROMETER: "Electrometer",
        config.CO2_SENSOR: "CO2 sensor",
        config.RHTP: "RHTP",
        config.AFM: "AFM",
        config.EDILUTER: "eDiluter",
        config.TSI_CPC: "TSI CPC",
        config.EXAMPLE_DEVICE: "Example device"
    }
    return type_map.get(device_type, "Unknown")


def app_config_to_params_dict(app_config: AppConfig) -> Dict[str, Any]:
    """
    Convert AppConfig to old parameter tree dictionary format (for compatibility).

    Args:
        app_config: AppConfig instance

    Returns:
        Dictionary in old parameter tree format
    """
    params_dict = {
        'Data settings': {
            'File path': app_config.data_settings.file_path,
            'File tag': app_config.data_settings.file_tag,
            'Save data': app_config.data_settings.save_data,
            'Generate daily files': app_config.data_settings.generate_daily_files,
            'Resume on startup': app_config.data_settings.resume_on_startup
        },
        'Plot settings': {
            'Follow': app_config.plot_settings.follow,
            'Time window (s)': int(app_config.plot_settings.time_window_s),
            'Autoscale Y': app_config.plot_settings.autoscale_y
        },
        'Device settings': {}
    }

    # Convert devices
    for device in app_config.devices:
        device_dict = {
            'DevID': device.device_id,
            'Device type': device.device_type,
            'COM port': device.com_port,
            'Serial number': device.serial_number,
            'Device nickname': device.device_nickname,
            'Plot to main': device.plot_to_main,
            'Connection': None,  # SerialDeviceConnection not serialized
            'Connected': False  # Runtime state, not serialized
        }

        # Add extra params
        if '10_hz' in device.extra_params:
            device_dict['10 hz'] = device.extra_params['10_hz']
        if 'connected_cpc' in device.extra_params:
            device_dict['Connected CPC'] = device.extra_params['connected_cpc']
        if 'calibration_file_path' in device.extra_params:
            device_dict['Calibration file path'] = device.extra_params['calibration_file_path']
        if 'co_flow' in device.extra_params:
            device_dict['CO flow'] = device.extra_params['co_flow']
        if 'firmware_version' in device.extra_params:
            device_dict['Firmware version'] = device.extra_params['firmware_version']
        if 'database_enabled' in device.extra_params:
            device_dict['Database enabled'] = device.extra_params['database_enabled']
        if 'linked_rhtp' in device.extra_params:
            device_dict['Linked RHTP'] = device.extra_params['linked_rhtp']
        if 'db_averaging_interval' in device.extra_params:
            device_dict['DB averaging interval'] = device.extra_params['db_averaging_interval']

        # Use device type name as key (will be made unique if needed)
        device_name = device.device_nickname or device.device_type_name
        if device.serial_number:
            device_name = f"{device.device_type_name} ({device.serial_number})"

        params_dict['Device settings'][device_name] = device_dict

    return params_dict
