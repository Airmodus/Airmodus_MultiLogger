from PyQt5.QtWidgets import QWidget, QVBoxLayout
from widgets import SetWidget, IndicatorWidget
from plots.device_plots import SinglePlot
from config import AFC
from devices.base_device import ComplexDevice
from devices.device_data import AFCData
from plotting.device_plot_configs import AFCPlotConfig
from devices.data_writers import AFCDataWriter

# AFC Widget
class AFCWidget(ComplexDevice):
    def __init__(self, device_config, *args, **kwargs):
        super().__init__(device_config, *args, **kwargs)

        # Initialize current data and settings
        self.current_data = AFCData()

        # Plot configuration (composition over inheritance)
        self.plot_config = AFCPlotConfig(self)
        # Data writer configuration (composition over inheritance)
        self.data_writer = AFCDataWriter(self)

        # create plot widget for AFC
        self.plot_tab = SinglePlot(device_type=AFC)
        self.addTab(self.plot_tab, "Plot")

        # create control tab for flow setpoint and monitor value
        self.control_tab = AFCControlTab()
        self.addTab(self.control_tab, "Control")

        # Add Device tab at the end
        self._add_device_tab_at_end()
    
    def get_plot_keys(self):
        """AFC has a single flow plot."""
        return ['']
    
    def send_read_commands(self, dev_conn, device_config):
        """Send AFC read command :MEAS:ALL to get all relevant values."""
        dev_conn.send_message(":MEAS:ALL")

    def get_read_command(self):
        """AFC read command :MEAS:ALL requests all relevant values."""
        return ":MEAS:ALL"
    
    def parse_message(self, message, data_holder=None):
        """
        Parse AFC serial messages.

        :MEAS:ALL - all relevant values:
        standard flow, average flow, temperature, flow setpoint, error status.
        """
        try:
            # Split command and data
            message_string = message
            parts = message.split(" ", 1)
            if len(parts) < 2:
                return {
                    'type': 'unknown',
                    'command': parts[0] if parts else '',
                    'data': None,
                    'raw': message,
                    'update_gui': False
                }

            command = parts[0]
            data = parts[1].split(",")

            # Handle :MEAS:ALL response
            if command == ":MEAS:ALL":
                # Validate data length
                if len(data) == 5:
                    # update data object
                    self.current_data.flow = float(data[0])
                    self.current_data.average_flow = float(data[1])
                    self.current_data.temperature = float(data[2])
                    self.current_data.flow_setpoint = float(data[3])
                    self.current_data.error_status = int(data[4])

                    # update GUI elements
                    self.update_errors()
                    self.update_settings()
                    self.update_values()

                    # set error flags
                    if self.current_data.error_status != 0:
                        data_holder.error_status = True
                        data_holder.device_errors[self.dev_id] = True

                    return {
                        'type': 'data',
                        'command': command,
                        'data': self.current_data.to_array(),
                        'raw': message,
                        'update_gui': True
                    }
            
            # Handle *IDN response
            elif command == "*IDN":
                serial_number = data[0].strip()
                return {
                    'type': 'info',
                    'command': command,
                    'data': serial_number,
                    'raw': message,
                    'update_gui': False
                }
            
            # Unknown command
            else:
                return {
                    'type': 'unknown',
                    'command': command,
                    'data': data,
                    'raw': message,
                    'update_gui': False
                }
            
        except Exception as e:
            return {
                'type': 'error',
                'command': 'unknown',
                'data': None,
                'error': str(e),
                'raw': message,
                'update_gui': False
            }
    
    def update_errors(self):
        """Update AFC error status in the GUI."""
        self.control_tab.measured_flow.change_color(self.current_data.error_status)
    
    def update_settings(self):
        """Update AFC settings in the GUI."""
        if self.control_tab.set_flow.value_spinbox.value() != self.current_data.flow_setpoint:
            self.control_tab.set_flow.value_spinbox.setValue(self.current_data.flow_setpoint)
    
    def update_values(self):
        """Update AFC measured values in the GUI."""
        self.control_tab.measured_flow.change_value(str(self.current_data.flow) + " slm")

    def get_status_bar_text(self):
        """Get formatted text for status bar display."""
        if self.current_data and hasattr(self.current_data, 'flow'):
            flow = self.current_data.flow
            if flow is not None:
                return f"{flow:.2f} slm"
        return super().get_status_bar_text()

class AFCControlTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QVBoxLayout()
        
        self.set_flow = SetWidget("Flow setpoint", " slm")
        layout.addWidget(self.set_flow)

        self.measured_flow = IndicatorWidget("Measured flow", " slm")
        layout.addWidget(self.measured_flow)

        self.setLayout(layout)