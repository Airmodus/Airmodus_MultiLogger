from PyQt5.QtCore import QTimer
from serial import Serial
from serial.serialutil import PortNotOpenError
import logging
import threading

class SerialDeviceConnection():
    def __init__(self):
        self.serial_port = "NaN"
        self.timeout = 0.2
        self.baud_rate = 115200
        self._connecting = False  # Flag to prevent duplicate connection attempts
        self._connection_thread = None
        self._pending_timers = []  # Track pending message timers for cancellation
        
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

    def connect_async(self, callback=None):
        """
        Attempt connection in background thread (non-blocking).

        Args:
            callback: Optional callback(success: bool) called when done
        """
        if self._connecting:
            return  # Already attempting connection

        self._connecting = True

        def _connect_worker():
            success = False
            try:
                self.connect()  # Existing blocking connect
                success = hasattr(self, 'connection') and self.connection.is_open
            except Exception as e:
                logging.debug(f"[SERIAL CONNECT ASYNC] Failed to connect to {self.serial_port}: {e}")
            finally:
                self._connecting = False
                if callback:
                    try:
                        callback(success)
                    except Exception as e:
                        logging.error(f"[SERIAL CONNECT ASYNC] Callback error: {e}")

        self._connection_thread = threading.Thread(target=_connect_worker, daemon=True)
        self._connection_thread.start()

    def is_connecting(self):
        """Return True if connection attempt is in progress."""
        return self._connecting

    # close serial connection
    def close(self):
        # Cancel all pending message timers first
        self._cancel_pending_timers()
        # if connection exist, it is closed
        try:
            # Try to close with the port that was last used (needed if the port has been changed)
            self.connection.close()
            #print("Connection closed")
        except Exception:
            pass  # Connection already closed or doesn't exist

    def _cancel_pending_timers(self):
        """Cancel all pending delayed message timers."""
        for timer in self._pending_timers:
            timer.stop()
        self._pending_timers.clear()
    
    def send_message(self, message):
        if message is None:
            return
        # add line termination and convert to bytes
        message_str = str(message)
        message_bytes = bytes((message_str + '\r\n'), 'utf-8')
        try:
            # log before sending
            logging.debug(f"[SERIAL TX] Port={self.serial_port} Data={message_str}")
            # send message if connection exists and is open
            if not hasattr(self, 'connection') or not self.connection.is_open:
                logging.debug(f"[SERIAL TX SKIP] Port closed - Port={self.serial_port} Data={message_str}")
                return
            self.connection.write(message_bytes)
        except (AttributeError, PortNotOpenError):
            # log message if connection does not exist or port was closed
            logging.debug(f"[SERIAL TX SKIP] Port not available - Port={self.serial_port} Data={message_str}")
    
    def send_delayed_message(self, message, delay):
        """Send a message after a delay, with cancellation support."""
        timer = QTimer()
        timer.setSingleShot(True)

        def on_timeout():
            self.send_message(message)
            # Clean up: remove this timer from pending list
            if timer in self._pending_timers:
                self._pending_timers.remove(timer)

        timer.timeout.connect(on_timeout)
        self._pending_timers.append(timer)
        timer.start(delay)

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
        self.send_delayed_message(":MEAS:ALL", 150)
    
    # --- CPC & PSM set/command functions ---

    # add value to set message
    def send_set_val(self, value, message, **kwargs):
        if isinstance(value, float): # if value is float, round to 2 or x decimals
            if kwargs: # if kwargs is not empty
                value = round(value, kwargs['decimals']) # round value to kwargs['decimals'] decimals
            else: # otherwise, round to 2 decimals
                value = round(value, 2)
        message = message + str(value) # add value to message
        self.send_message(message)

__all__ = ['SerialDeviceConnection']
