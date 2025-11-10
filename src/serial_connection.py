from PyQt5.QtCore import QTimer
from serial import Serial
import logging

class SerialDeviceConnection():
    def __init__(self):
        self.serial_port = "NaN"
        self.timeout = 0.2
        self.baud_rate = 115200
        
    def set_port(self, serial_port):
        self.serial_port = serial_port
    
    def set_baud_rate(self, baud_rate):
        self.baud_rate = baud_rate
    
    # open serial connection
    def connect(self):
        try: # Try to close with the port that was last used (needed if the port has been changed)
            self.connection.close()
        except: # if fails (i.e. port has not been open) continue normally
            pass
        self.connection = Serial(self.serial_port, self.baud_rate, timeout=self.timeout) #, rtscts=True)
        print("Connected to %s" % self.serial_port)
    
    # close serial connection
    def close(self):
        # if connection exist, it is closed
        try:
            # Try to close with the port that was last used (needed if the port has been changed)
            self.connection.close()
            #print("Connection closed")
        except Exception:
            pass  # Connection already closed or doesn't exist
    
    # close old connection and open new connection
    def change_port(self, serial_port):
        # close current connection
        self.close()
        # set new port
        self.set_port(serial_port)
        try:
            # connect to new port
            self.connect()
        except Exception as e:
            print("change_port:", e)
    
    def send_message(self, message):
        # add line termination and convert to bytes
        message_str = str(message)
        message_bytes = bytes((message_str + '\r\n'), 'utf-8')
        try:
            # log before sending
            logging.debug(f"[SERIAL TX] Port={self.serial_port} Data={message_str}")
            # send message if connection exists
            self.connection.write(message_bytes)
        except AttributeError:
            # log and print message if connection does not exist
            logging.warning(f"[SERIAL TX FAIL] No connection - Port={self.serial_port} Data={message_str}")
            print("send_message - no connection, message -", message_bytes)
    
    def send_delayed_message(self, message, delay):
        QTimer.singleShot(delay, lambda: self.send_message(message))

    def send_multiple_messages(self, device_widget, ten_hz=False):
        """
        Send a sequence of commands to a device with timing delays.

        This method now uses the device's get_read_command_sequence() method
        to determine which commands to send and their timing, eliminating
        device-specific if statements from the connection layer.

        Args:
            device_widget: The device widget instance (must have get_read_command_sequence())
            ten_hz (bool): Whether 10Hz logging is enabled (CPC-specific)
        """
        # Get command sequence from device
        command_sequence = device_widget.get_read_command_sequence(ten_hz)

        # Send commands with appropriate delays
        for command, delay in command_sequence:
            if delay == 0:
                self.send_message(command)
            else:
                self.send_delayed_message(command, delay)
    
    def send_pulse_analysis_messages(self, threshold):
        # send required messages for pulse analysis
        self.send_message(":SET:OPC:THRS " + str(threshold))
        QTimer.singleShot(150, lambda: self.send_message(":MEAS:ALL"))
    
    # --- CPC & PSM set/command functions ---

    # send set message
    def send_set(self, message):
        if message == None:
            # if message is None, do nothing
            return
        else:
            # send message
            self.send_message(message)
    
    # add value to set message
    def send_set_val(self, value, message, **kwargs):
        if isinstance(value, float): # if value is float, round to 2 or x decimals
            if kwargs: # if kwargs is not empty
                value = round(value, kwargs['decimals']) # round value to kwargs['decimals'] decimals
            else: # otherwise, round to 2 decimals
                value = round(value, 2)
        message = message + str(value) # add value to message
        #print("send_set_val -", message) # print message for debugging
        self.send_set(message) # send message using send_message()

__all__ = ['SerialDeviceConnection']
