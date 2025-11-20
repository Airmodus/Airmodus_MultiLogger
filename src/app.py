from datetime import datetime as dt
from time import time
import os
import traceback
import json

from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (QMainWindow, QSplitter, QApplication, QTabWidget, QLabel,
    QFileDialog)
from pyqtgraph.parametertree import ParameterTree

from config import *
from utils import (
    psm_update,
    psm_flow_send,
    cpc_flow_send,
    ten_hz_clicked,
    command_entered
)
from plots import (
    MainPlot,
)

from devices import (
    CPCWidget, 
    PSMWidget, 
    CO2Widget, 
    ElectrometerWidget, 
    RHTPWidget,
    eDiluterWidget, 
    AFMWidget, 
    TSIWidget, 
    ExampleDeviceWidget
)

from managers import (
    DataHolder,
    TimerService,
    DeviceManager,
    PlotManager,
    DataLogger
)

from serial_connection import SerialDeviceConnection
from params import p


# main program
class MainWindow(QMainWindow):

    def __init__(self, params=p, parent=None):
        super().__init__() # super init function must be called when subclassing a Qt class
        self.setWindowTitle("Airmodus MultiLogger v. " + version_number) # set window title

        self.params = params # predefined parameter tree
        self.config_file_path = "" # path to the configuration file

        # Extracted inits
        self.data_holder = DataHolder()
        self.data_holder.error_icon = QIcon(resource_path + "/icons/error.png")
        self.data_holder.disconnected_icon = QIcon(resource_path + "/icons/disconnected.png")

        self._setup_parameter_tree()
        self._setup_gui()

        # Add any existing devices AFTER GUI setup (so device_tabs exists)
        for child in self.params.child('Device settings').children():
            self.device_added(self.params.child('Device settings'), child)

        self.device_manager = DeviceManager(self.params, self.data_holder, self.data_holder.device_widgets)

        # Update device_manager with device_tabs reference after GUI setup
        self.device_manager.device_tabs = self.device_tabs

        # Set device_manager and data_holder in ScalableGroup for port selection dialog
        device_settings = self.params.child('Device settings')
        if device_settings:
            device_settings.device_manager = self.device_manager
            device_settings.data_holder = self.data_holder

        # Start initial port scan to populate dropdowns
        QTimer.singleShot(100, self.device_manager.list_com_ports)

        # Start continuous port monitoring for automatic device detection
        QTimer.singleShot(500, self.device_manager.start_port_monitoring)

        self.plot_manager = PlotManager(self, self.data_holder, self.main_plot)
        self.data_logger = DataLogger(self.data_holder, self.params)

        # Initialize database manager
        from managers.database_manager import DatabaseManager
        self.database_manager = DatabaseManager()

        self._connect_signals()

        self.timer_service = TimerService(self, self.data_holder, self.device_manager, self.plot_manager, self.data_logger)
        self.timer_service.start()

        # load ini file if available
        self.load_ini()

        # Update PSM connected CPC references after all devices are loaded
        # This is needed because during device creation, the CPC device might not exist yet
        from config import PSM, PSM2
        for dev in self.params.child('Device settings').children():
            if dev.child('Device type').value() in [PSM, PSM2]:
                dev_id = dev.child('DevID').value()
                psm_widget = self.data_holder.device_widgets.get(dev_id)
                if psm_widget and hasattr(psm_widget, 'connected_cpc_device'):
                    try:
                        cpc_id = dev.child('Connected CPC').value()
                        if cpc_id != 'None':
                            cpc_widget = self.data_holder.device_widgets.get(cpc_id)
                            psm_widget.connected_cpc_device = cpc_widget
                    except KeyError:
                        pass

    def _setup_parameter_tree(self):
        """Create and configure the ParameterTree."""
        # create parameter tree
        self.t = ParameterTree()
        self.t.setParameters(self.params, showTop=False)
        self.t.setHeaderHidden(True)

        # load CSS style and apply it to the main window
        with open(script_path + "/style.css", "r") as f:
            self.style = f.read()
        self.setStyleSheet(self.style)


    def _setup_gui(self):
        """Build main layout, splitters, tabs, etc."""
        # create and set central widget (requirement of QMainWindow)
        self.main_splitter = QSplitter()
        self.setCentralWidget(self.main_splitter)
        # create logo pixmap label
        self.logo = QLabel(alignment=Qt.AlignCenter, objectName="logo")
        pixmap = QPixmap(resource_path + "/images/airmodus-envea-logo.png")
        self.logo.setPixmap(pixmap.scaled(400, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        # create left side vertical splitter
        # contains parameter tree
        left_splitter = QSplitter(Qt.Vertical) # split vertically
        left_splitter.addWidget(self.logo) # add logo
        left_splitter.addWidget(self.t) # add parameter tree widget
        left_splitter.setSizes([100, 900]) # set relative sizes of widgets
        # create right side tab widget containing device widgets as tabs
        # new devices are added to this as tabs in device_added function
        self.device_tabs = QTabWidget()
        self.main_plot = MainPlot() # create main plot widget instance
        self.device_tabs.addTab(self.main_plot, "Main plot") # add main plot widget to tab widget
        # add widgets to main_splitter (MainWindow's central widget)
        self.main_splitter.addWidget(left_splitter) # contains parameter tree and status lights
        self.main_splitter.addWidget(self.device_tabs) # contains devices as tabs
        self.main_splitter.setSizes([2000, 8000]) # set relative sizes of widgets

        # Create and add status bar for always-visible field monitoring
        from status_bar import MultiLoggerStatusBar
        self.status_bar = MultiLoggerStatusBar(self.data_holder, self.params, self)
        self.status_bar.main_window = self  # Set reference for tab switching
        self.setStatusBar(self.status_bar)

        # resize window (int x, int y)
        self.resize(1400, 800)

    def _connect_signals(self):
        """Wire up all signals/slots."""

        # connect parameter tree's save data parameter
        self.params.child('Data settings').child('Save data').sigValueChanged.connect(self.data_logger.save_changed)
        # connect file path parameter to filepath_changed function
        self.params.child('Data settings').child('File path').sigValueChanged.connect(self.data_logger.filepath_changed)
        # connect file tag parameter to reset_all_filenames function
        self.params.child('Data settings').child('File tag').sigValueChanged.connect(self.data_logger.reset_all_filenames)
        # Note: Update serial ports button removed - continuous monitoring is now automatic

        # connect parameter tree's sigChildAdded signal to device_added function
        self.params.child("Device settings").sigChildAdded.connect(self.device_added)
        # connect parameter tree's sigChildRemoved signal to device_removed function
        self.params.child("Device settings").sigChildRemoved.connect(self.device_removed)
        # connect main_plot's viewboxes' sigXRangeChanged signals to x_range_changed function
        for viewbox in self.main_plot.viewboxes.values():
            viewbox.sigXRangeChanged.connect(self.x_range_changed)
        # connect main_plot's auto range button click to auto_range_clicked function
        self.main_plot.plot.autoBtn.clicked.connect(self.auto_range_clicked)

        # connect DeviceManager port scanning signals for progressive UI updates
        self.device_manager.port_scan_started.connect(self._on_port_scan_started)
        self.device_manager.port_scan_complete.connect(self._on_port_scan_complete)
        self.device_manager.port_scan_progress.connect(self._on_port_scan_progress)

        # connect parameter tree's sigTreeStateChanged signal to save_ini function
        self.params.sigTreeStateChanged.connect(self.save_ini)

    # set COM port inquiry flag
    def set_inquiry_flag(self):
        # Check if a scan is already in progress to prevent double-clicking
        if hasattr(self.device_manager, '_scanning') and self.device_manager._scanning:
            import logging
            logging.info("Port scan already in progress, ignoring button click")
            return

        self.data_holder.inquiry_flag = True
        self.data_holder.inquiry_time = time()
        self.data_holder.com_descriptions = {} # reset com descriptions
        # Trigger the new threaded port scanning
        self.device_manager.list_com_ports()

    def _on_port_scan_started(self):
        """Handle port scan start."""
        import logging
        logging.info("Port scan started")

    def _on_port_scan_complete(self):
        """Handle port scan completion."""
        import logging
        logging.info("Port scan completed")

    def _on_port_scan_progress(self, current: int, total: int):
        """Handle port scan progress updates."""
        import logging
        logging.debug(f"Port scan progress: {current}/{total}")
    

    def save_ini(self):
        # check if resume on startup is on
        resume_measurements = 0
        if self.params.child('Data settings').child('Resume on startup').value():
            resume_measurements = 1
        # store resume config path
        self.config_file_path = os.path.join(save_path, 'resume_config.json')
        with open(os.path.join(save_path, 'config.ini'),'w') as f:
            f.write(self.config_file_path)
            f.write(';')
            f.write(str(resume_measurements))
        # save the configuration to the JSON file
        self.save_configuration(self.config_file_path)
    
    def load_ini(self):
        try:
            # load the configuration file "config.ini" from the save_path
            with open(os.path.join(save_path, 'config.ini'),'r') as f:
                config = f.read()
                json_path = config.split(';')[0]
                resume_measurements = config.split(';')[1]
                # If json path is empty
                if not json_path:
                    json_path = os.path.join(save_path, 'resume_config.json')
                self.config_file_path = json_path
                resume_measurements = int(resume_measurements)
                # if resume on startup is on, load the stored configuration
                if resume_measurements:
                    self.load_configuration(json_path)
        except Exception as e:
            # If the file does not exist, raise an exception saying that the file does not exist
            #print("No ini file found")
            print(traceback.format_exc())
        
    def save_configuration(self, json_path):
        # Get the parameter tree values
        parameter_values = self.save_parameters_recursive(self.params)
        # Add database connection string
        if hasattr(self, 'database_manager') and hasattr(self.database_manager, 'connection_string_cached'):
            parameter_values['database_connection_string'] = self.database_manager.connection_string_cached
        # Save the configuration to the JSON file
        with open(json_path, 'w') as file:
            json.dump(parameter_values, file)
    
    def save_parameters_recursive(self, parameters):
        result = {}
        for param in parameters:
            if param.hasChildren():
                result[param.name()] = self.save_parameters_recursive(param.children())
            else:
                # Check if the parameter value is an instance of SerialDeviceConnection
                if isinstance(param.value(), SerialDeviceConnection):
                    # store parameter value as None
                    result[param.name()] = None
                else:
                    result[param.name()] = param.value()
        return result

    def load_configuration(self, json_path=None):
        if json_path:
            # Load the configuration from the JSON file
            with open(json_path, 'r') as file:
                parameter_values = json.load(file)
            # Add devices in configuration file to the parameter tree
            self.load_devices(parameter_values.get('Device settings', {}))
            # Set the loaded parameter values to the parameter tree
            self.load_parameters_recursive(self.params, parameter_values)

            # Load database connection string
            if 'database_connection_string' in parameter_values:
                conn_string = parameter_values['database_connection_string']
                if hasattr(self, 'database_manager'):
                    self.database_manager.connection_string_cached = conn_string

                # Update all CPC ACTRIS tabs with the connection string
                from config import CPC
                for dev_id, widget in self.data_holder.device_widgets.items():
                    if hasattr(widget, 'device_type') and widget.device_type == CPC:
                        if hasattr(widget, 'database_tab'):
                            widget.database_tab.connection_string_input.setText(conn_string)

                # Restore database enabled state for CPCs that had it enabled
                # This must happen AFTER connection string is set and parameters are loaded
                device_settings_group = self.params.child('Device settings')
                if device_settings_group:
                    for dev_param in device_settings_group.children():
                        if dev_param.child('Device type').value() == CPC:
                            db_enabled_param = dev_param.child('Database enabled')
                            if db_enabled_param and db_enabled_param.value():
                                # Get the CPC widget
                                dev_id = dev_param.child('DevID').value()
                                cpc_widget = self.data_holder.device_widgets.get(dev_id)

                                if cpc_widget and hasattr(cpc_widget, 'database_tab'):
                                    # Block signals to prevent validation during restoration
                                    cpc_widget.database_tab.db_enabled_checkbox.blockSignals(True)

                                    # Ensure connection string is set in the input field
                                    if not cpc_widget.database_tab.connection_string_input.text():
                                        cpc_widget.database_tab.connection_string_input.setText(conn_string)

                                    # Repopulate RHTP dropdown (it might be empty at this point)
                                    cpc_widget.database_tab.populate_rhtp_dropdown()

                                    # Restore the linked RHTP selection
                                    try:
                                        linked_rhtp_param = dev_param.child('Linked RHTP')
                                        if linked_rhtp_param:
                                            rhtp_id = linked_rhtp_param.value()
                                            if rhtp_id != 'None':
                                                index = cpc_widget.database_tab.linked_rhtp_dropdown.findData(rhtp_id)
                                                if index >= 0:
                                                    cpc_widget.database_tab.linked_rhtp_dropdown.setCurrentIndex(index)
                                    except KeyError:
                                        pass

                                    # Set checkbox visually (signals blocked, won't trigger validation)
                                    cpc_widget.database_tab.db_enabled_checkbox.setChecked(True)

                                    # Unblock signals
                                    cpc_widget.database_tab.db_enabled_checkbox.blockSignals(False)

                                    # Manually connect to database (bypass validation)
                                    interval_param = dev_param.child('DB averaging interval')
                                    interval_str = interval_param.value() if interval_param else '1 minute'
                                    interval_map = {'1 minute': 1, '5 minutes': 5, '10 minutes': 10, '15 minutes': 15, '1 hour': 60, '3 hours': 180}
                                    interval_minutes = interval_map.get(interval_str, 1)

                                    # Register device with database manager
                                    success, message = self.database_manager.register_device(dev_id, conn_string)
                                    if success:
                                        # Create averager
                                        self.database_manager.create_averager(dev_id, interval_minutes)

                                        # Update UI status
                                        cpc_widget.database_tab.db_status_value.setText("Enabled")
                                        cpc_widget.database_tab.db_status_value.setStyleSheet("color: green;")

                                        # Update device parameter
                                        dev_param.child('Database enabled').setValue(True)

                                        # Update global status
                                        cpc_widget.database_tab.update_global_connection_status()
                                        cpc_widget.database_tab.sync_global_status_to_all_cpcs()
    
    def load_devices(self, device_settings):
        # remove all devices from the parameter tree
        self.params.child('Device settings').clearChildren()
        # Handle None or empty device settings
        if not device_settings:
            return
        try:
            # go through each device in the device settings
            for dev_name, dev_values in device_settings.items():
                # get 'DevID' and 'Device type' values
                dev_id = dev_values.get('DevID', None)
                dev_type = dev_values.get('Device type', None)
                # Skip if device type is invalid
                if dev_type is None or dev_type == '' or dev_type not in self.data_holder.device_names:
                    continue
                # set n_devices to current dev_id
                self.params.child('Device settings').n_devices = dev_id
                # add device to the parameter tree
                self.params.child('Device settings').addNew(self.data_holder.device_names[dev_type], device_name=dev_name)
        except (AttributeError, KeyError) as e:
            print(f"Error loading devices: {e}")
            pass
            
    def load_parameters_recursive(self, parameters, values):
        for param in parameters:
            if param.hasChildren():
                self.load_parameters_recursive(param.children(), values.get(param.name(), {}))
            else:
                if param.name() == 'Connection':
                    # skip 'Connection' parameter (SerialDeviceConnection)
                    # SerialDeviceConnection was created when the device was added (load_devices)
                    pass
                elif param.name() == 'Connected':
                    # skip 'Connected' parameter, this is checked in connection_test()
                    pass
                # Check if parameter name is CO flow
                elif param.name() == 'CO flow':
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
                    # Set CO flow value to related PSM widget
                    try:
                        self.data_holder.device_widgets[param.parent().child("DevID").value()].set_tab.set_co_flow.value_spinbox.setValue(round(float(param.value()), 3))
                    except ValueError:
                        pass # if value has not been saved, skip
                # Check if parameter name is 10 hz
                elif param.name() == '10 hz':
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
                    # if device type is PSM or PSM2
                    if param.parent().child('Device type').value() in [PSM, PSM2]:
                        # Set 10 hz status (True/False) to ten_hz button
                        self.data_holder.device_widgets[param.parent().child("DevID").value()].measure_tab.ten_hz.change_color(int(values.get(param.name(), param.value())))
                else:
                    # Set the parameter value as usual
                    param.setValue(values.get(param.name(), param.value()))
    
    def x_range_changed(self, viewbox):
        # if autoscale y is on
        if self.params.child("Plot settings").child('Autoscale Y').value():
            viewbox.enableAutoRange(axis='y')
            viewbox.setAutoVisible(y=True)
    
    # called when main plot's auto range button is clicked
    def auto_range_clicked(self):
        # disable follow
        self.params.child("Plot settings").child('Follow').setValue(False)
        # set autorange on for individual plots
        for dev in self.params.child('Device settings').children():
            dev_id = dev.child('DevID').value()
            dev_type = dev.child('Device type').value()
            if dev_type == ELECTROMETER:
                for plot in self.data_holder.device_widgets[dev_id].plot_tab.plots:
                    plot.enableAutoRange()
            else:
                self.data_holder.device_widgets[dev_id].plot_tab.plot.enableAutoRange()
            
    
    # set the 'Plot to main' selection of all RHTP devices to the same value
    # called when 'Plot to main' selection of any RHTP device is changed
    def rhtp_axis_changed(self, value):
        for dev in self.params.child('Device settings').children():
            if dev.child('Device type').value() == RHTP and dev.child('Plot to main').value() != value:
                dev.child('Plot to main').setValue(value)
    # same as above but for AFM devices
    def afm_axis_changed(self, value):
        for dev in self.params.child('Device settings').children():
            if dev.child('Device type').value() == AFM and dev.child('Plot to main').value() != value:
                dev.child('Plot to main').setValue(value)
    
    
    
    # rename device parameter according to device type and serial number
    def rename_device(self, device):
        # combine device type name and serial number into device name
        device_type = device.child('Device type').value() # device type number
        device_type_name = self.data_holder.device_names[device_type] # device type name
        serial_number = device.child('Serial number').value() # serial number
        device_name = device_type_name + " " + serial_number
        # set device name
        device.setName(device_name)
        # update tab name
        self.rename_tab(device)

    # update device tab name according to device parameter name or nickname
    def rename_tab(self, device):
        # get tab index of device widget
        device_id = device.child('DevID').value()
        device_widget = self.data_holder.device_widgets[device_id]
        tab_index = self.device_tabs.indexOf(device_widget)
        # check if device has a nickname
        if device.child('Device nickname').value() != "":
            device_name = device.child('Device nickname').value()
        else: # if no nickname, use device parameter name (device type and serial number)
            device_name = device.name()
        # update tab name
        self.device_tabs.setTabText(tab_index, device_name)

    # triggered when a new device is added to the parameter tree
    # sigChildAdded(self, param, child, index) - Emitted when a child (device) is added
    def device_added(self, param, child):
        """
        Handle device addition to the application.

        Creates the device widget and sets up signal/slot connections
        using the device registry for a declarative, maintainable approach.
        """
        if param.name() != "Device settings":
            return

        from devices.registry import create_device_widget, setup_device_connections

        # Extract device parameters
        device_param = child
        device_type = child.child("Device type").value()
        device_id = child.child("DevID").value()
        device_port = child.child("COM port")
        connection = device_param.child('Connection').value()

        # Set up common signal connections for all devices
        device_param.child("Serial number").sigValueChanged.connect(
            lambda: self.data_logger.reset_device_filenames(device_id))
        device_param.child("Device nickname").sigValueChanged.connect(
            lambda: self.data_logger.reset_device_filenames(device_id))
        device_param.child("Device nickname").sigValueChanged.connect(
            lambda: self.rename_tab(device_param))
        device_param.child("Serial number").sigValueChanged.connect(
            lambda: self.rename_device(device_param))

        # Connect COM port change to SerialDeviceConnection
        if osx_mode:
            device_port.sigValueChanged.connect(
                lambda: connection.change_port(str(device_port.value())))
        else:
            device_port.sigValueChanged.connect(
                lambda: connection.change_port('COM' + str(device_port.value())))

        # Create widget using device registry
        try:
            widget = create_device_widget(device_type, device_param)
        except ValueError as e:
            print(f"Error creating device widget: {e}")
            return

        # Set device ID in widget (required for device to manage its own state)
        widget.dev_id = device_id

        # Set up device-specific connections using device registry
        setup_device_connections(device_type, widget, device_param, connection, self)

        # Connect viewbox x-range change for autoscale
        from config import ELECTROMETER, RHTP, AFM
        if device_type == ELECTROMETER:
            for plot in widget.plot_tab.plots:
                plot.getViewBox().sigXRangeChanged.connect(self.x_range_changed)
        elif device_type in [RHTP, AFM]:
            for viewbox in widget.plot_tab.viewboxes:
                viewbox.sigXRangeChanged.connect(self.x_range_changed)
        else:
            widget.plot_tab.viewbox.sigXRangeChanged.connect(self.x_range_changed)

        # Register widget and initialize data structures
        self.data_holder.device_widgets[device_id] = widget
        self.data_holder.reset_for_device(device_id, widget)
        self.data_holder.init_plot_data_for_device(device_id, widget)

        # Add widget to GUI and initialize error tracking
        self.device_tabs.addTab(widget, widget.name)
        self.data_holder.device_errors[device_id] = False

        # Add device to status bar
        if hasattr(self, 'status_bar'):
            device_name = child.child('Device nickname').value() or child.name()
            self.status_bar.add_device_status(device_id, device_name)

        # Set main_window reference for CPC database tab
        from config import CPC
        if device_type == CPC and hasattr(widget, 'database_tab'):
            widget.database_tab.main_window = self
            # Load connection string from cached value
            if hasattr(self.database_manager, 'connection_string_cached'):
                widget.database_tab.connection_string_input.setText(self.database_manager.connection_string_cached)
            # Update global connection status
            widget.database_tab.update_global_connection_status()

    # triggered when a device is removed from the parameter tree
    # sigChildRemoved(self, parent, child, index) - Emitted when a child (device) is removed
    def device_removed(self, param, child):
        if param == self.params.child("Device settings"):
            device_id = child.child("DevID").value()
            device_type = child.child("Device type").value()

            # Remove from status bar
            if hasattr(self, 'status_bar'):
                self.status_bar.remove_device_status(device_id)

            # If it's a CPC with database enabled, unregister from database manager
            from config import CPC
            if device_type == CPC and hasattr(self, 'database_manager'):
                # Check if database was enabled for this device
                db_enabled_param = child.child('Database enabled')
                if db_enabled_param and db_enabled_param.value():
                    # Unregister device (will disconnect if last device)
                    self.database_manager.unregister_device(device_id)

                    # Update global status in all remaining CPC tabs
                    for dev_id, widget in self.data_holder.device_widgets.items():
                        if dev_id != device_id and hasattr(widget, 'device_type') and widget.device_type == CPC:
                            if hasattr(widget, 'database_tab'):
                                widget.database_tab.update_global_connection_status()
                                widget.database_tab.sync_global_status_to_all_cpcs()

            # remove device widget from main tab widget
            self.device_tabs.removeTab(self.device_tabs.indexOf(self.data_holder.device_widgets[device_id]))
            # close serial connection if open
            try:
                child.child('Connection').value().close()
            except AttributeError:
                pass
            # set empty data to data_holder.curve_dict (remove curve from Main plot)
            try:
                self.data_holder.curve_dict[device_id].setData(x=[], y=[])
            except KeyError:
                pass

            self.data_holder.clear_for_device(device_id)

    def closeEvent(self, event):
        """Handle application close event - cleanup database connections."""
        # Disconnect from database if connected
        if hasattr(self, 'database_manager') and self.database_manager.connected:
            self.database_manager.disconnect()

        # Accept the close event
        event.accept()


# application format
if __name__ == '__main__': # protects from accidentally invoking the script when not intended
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
