"""
Background port monitoring for automatic device detection.
Continuously scans for serial port changes and queries device IDN.
"""

import time
import serial
import serial.tools.list_ports
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
import logging

logger = logging.getLogger(__name__)

class PortMonitor(QThread):
    """
    Background thread that monitors serial ports for changes.
    Automatically detects device connections/disconnections and queries IDN.
    """

    # Signals
    port_added = pyqtSignal(str, str)  # port_name, serial_number
    port_removed = pyqtSignal(str)  # port_name
    ports_changed = pyqtSignal(dict)  # all ports with descriptions

    def __init__(self, poll_interval=2.0, idn_delay_ms=400):
        """
        Initialize the port monitor.

        Args:
            poll_interval: Seconds between port scans (default 2.0)
            idn_delay_ms: Milliseconds to wait before IDN query (default 400)
        """
        super().__init__()
        self.poll_interval = poll_interval
        self.idn_delay_ms = idn_delay_ms / 1000.0  # Convert to seconds
        self.running = False
        self.current_ports = {}  # {port_name: serial_number}
        self.daemon = True  # Thread dies when main program exits

    def run(self):
        """Main monitoring loop."""
        self.running = True
        logger.info("Port monitor started")

        # Initial scan
        self._scan_ports()

        while self.running:
            try:
                time.sleep(self.poll_interval)
                if self.running:
                    self._scan_ports()
            except Exception as e:
                logger.error(f"Error in port monitor: {e}")

        logger.info("Port monitor stopped")

    def stop(self):
        """Stop the monitoring thread."""
        self.running = False
        self.wait(5000)  # Wait up to 5 seconds for thread to finish

    def _scan_ports(self):
        """Scan for serial ports and detect changes."""
        try:
            # Get current list of ports
            ports = serial.tools.list_ports.comports()
            new_port_dict = {}

            # Build dict of current ports
            for port in ports:
                port_name = str(port.device)
                # Skip certain system ports if needed
                if self._should_skip_port(port_name):
                    continue
                new_port_dict[port_name] = None  # Will be filled with IDN

            # Detect removed ports
            removed_ports = set(self.current_ports.keys()) - set(new_port_dict.keys())
            for port_name in removed_ports:
                logger.info(f"Port removed: {port_name}")
                self.port_removed.emit(port_name)

            # Detect added ports
            added_ports = set(new_port_dict.keys()) - set(self.current_ports.keys())
            for port_name in added_ports:
                logger.info(f"Port added: {port_name}")
                # Query IDN for new port
                serial_number = self._query_idn(port_name)
                new_port_dict[port_name] = serial_number
                self.port_added.emit(port_name, serial_number or "")

            # Copy existing serial numbers for unchanged ports
            for port_name in set(new_port_dict.keys()) & set(self.current_ports.keys()):
                new_port_dict[port_name] = self.current_ports[port_name]

            # Update current ports
            if new_port_dict != self.current_ports:
                self.current_ports = new_port_dict
                self.ports_changed.emit(self.current_ports.copy())

        except Exception as e:
            logger.error(f"Error scanning ports: {e}")

    def _query_idn(self, port_name):
        """
        Query IDN from a newly connected device.

        Args:
            port_name: Serial port path

        Returns:
            Serial number/IDN string or None if failed
        """
        try:
            # Open connection
            conn = serial.Serial(port_name, 115200, timeout=0.2)

            # Wait before sending IDN query
            time.sleep(self.idn_delay_ms)

            # Send IDN query
            conn.write(b'*IDN?\n')

            # Wait for response
            time.sleep(0.1)

            # Read response
            raw_data = conn.read_all()
            conn.close()

            if not raw_data:
                return None

            # Decode and parse response
            messages = raw_data.decode('utf-8', errors='ignore').split('\r\n')

            for message in messages:
                message = message.strip()
                if message.startswith('*IDN ') and len(message) > 5:
                    # Extract serial number (everything after "*IDN ")
                    serial_number = message[5:].strip()
                    logger.info(f"IDN response from {port_name}: {serial_number}")
                    return serial_number

                # Handle eDiluter format
                elif ' ID ' in message and ', Status' in message:
                    start_idx = message.index(' ID ') + 4
                    end_idx = message.index(', Status')
                    device_id = message[start_idx:end_idx].strip()
                    logger.info(f"eDiluter ID from {port_name}: {device_id}")
                    return device_id

        except Exception as e:
            logger.debug(f"Failed to query IDN from {port_name}: {e}")

        return None

    def _should_skip_port(self, port_name):
        """
        Determine if a port should be skipped.

        Args:
            port_name: Serial port path

        Returns:
            True if port should be skipped
        """
        # Skip Bluetooth ports on macOS
        if 'Bluetooth' in port_name:
            return True

        # Add other skip conditions as needed
        return False

    def get_current_ports(self):
        """
        Get current ports dictionary.

        Returns:
            Dict of {port_name: serial_number}
        """
        return self.current_ports.copy()