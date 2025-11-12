"""
Background port scanner thread for non-blocking serial port discovery.

This module provides asynchronous port scanning with progressive discovery,
device identification, and real-time UI updates via Qt signals.
"""

import time
import serial
import serial.tools.list_ports
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker
import platform


class PortInfo:
    """Data class for port information."""
    def __init__(self, port: str, description: str = "", serial_number: str = "",
                 device_type: str = "Unknown", status: str = "available"):
        self.port = port
        self.description = description
        self.serial_number = serial_number
        self.device_type = device_type
        self.status = status  # 'available', 'in_use', 'connected', 'error'
        self.manufacturer = ""
        self.vid_pid = ""

    def to_dict(self) -> dict:
        return {
            'port': self.port,
            'description': self.description,
            'serial_number': self.serial_number,
            'device_type': self.device_type,
            'status': self.status,
            'manufacturer': self.manufacturer,
            'vid_pid': self.vid_pid
        }


class PortScannerThread(QThread):
    """
    Background thread for scanning serial ports and identifying devices.

    Signals:
        port_discovered: Emitted when a single port is found (progressive discovery)
        scan_progress: Emitted with (current, total) count during scanning
        scan_complete: Emitted with list of all discovered ports when scan finishes
        error_occurred: Emitted when an error occurs during scanning
        port_added: Emitted when a new port is detected (hot-plug)
        port_removed: Emitted when a port is disconnected
    """

    # Signals
    port_discovered = pyqtSignal(dict)  # Single port info as dict
    scan_progress = pyqtSignal(int, int)  # current, total
    scan_complete = pyqtSignal(list)  # List of all port dicts
    error_occurred = pyqtSignal(str)  # Error message
    port_added = pyqtSignal(str, str)  # port, description (for monitoring)
    port_removed = pyqtSignal(str)  # port (for monitoring)

    def __init__(self, continuous_monitoring: bool = False,
                 max_workers: int = 5, parent=None):
        """
        Initialize the port scanner thread.

        Args:
            continuous_monitoring: If True, continuously monitor for port changes
            max_workers: Maximum number of concurrent port queries
            parent: Parent QObject
        """
        super().__init__(parent)
        self.continuous_monitoring = continuous_monitoring
        self.max_workers = max_workers
        self._stop_requested = False
        self._mutex = QMutex()
        self._known_ports = set()
        self._port_info_cache = {}  # Cache port information
        self.inquiry_timeout = 0.8  # Timeout for IDN queries
        self.connection_timeout = 0.2  # Timeout for opening serial connections

    def stop(self):
        """Request the thread to stop."""
        with QMutexLocker(self._mutex):
            self._stop_requested = True
        self.wait()  # Wait for thread to finish

    def is_stop_requested(self) -> bool:
        """Check if stop has been requested."""
        with QMutexLocker(self._mutex):
            return self._stop_requested

    def run(self):
        """Main thread execution - performs port scanning."""
        if self.continuous_monitoring:
            self._run_continuous_monitoring()
        else:
            self._run_single_scan()

    def _run_single_scan(self):
        """Perform a single port scan with progressive discovery."""
        try:
            discovered_ports = []

            # Get list of all available ports
            ports_list = list(serial.tools.list_ports.comports())
            total_ports = len(ports_list)

            if total_ports == 0:
                self.scan_complete.emit([])
                return

            # Use ThreadPoolExecutor for parallel port queries
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all port queries
                future_to_port = {}
                for i, port_info in enumerate(ports_list):
                    if self.is_stop_requested():
                        break

                    future = executor.submit(self._query_single_port, port_info)
                    future_to_port[future] = (i, port_info)

                # Process results as they complete (progressive discovery)
                completed = 0
                for future in as_completed(future_to_port):
                    if self.is_stop_requested():
                        executor.shutdown(wait=False)
                        break

                    completed += 1
                    idx, original_port_info = future_to_port[future]

                    try:
                        port_data = future.result(timeout=self.inquiry_timeout + 0.5)
                        if port_data:
                            discovered_ports.append(port_data)
                            self.port_discovered.emit(port_data.to_dict())
                    except Exception as e:
                        # Create basic port info even if query failed
                        port_data = PortInfo(
                            port=original_port_info.device,
                            description=original_port_info.description or "",
                            status='error'
                        )
                        discovered_ports.append(port_data)
                        self.port_discovered.emit(port_data.to_dict())

                    self.scan_progress.emit(completed, total_ports)

            # Emit complete signal with all discovered ports
            if not self.is_stop_requested():
                port_dicts = [p.to_dict() for p in discovered_ports]
                self.scan_complete.emit(port_dicts)

        except Exception as e:
            self.error_occurred.emit(f"Port scanning error: {str(e)}")

    def _query_single_port(self, port_info) -> Optional[PortInfo]:
        """
        Query a single port for device information.

        Args:
            port_info: Port information from serial.tools.list_ports

        Returns:
            PortInfo object with discovered information
        """
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config'))
        from device_patterns import DeviceIdentifier

        port_data = PortInfo(
            port=port_info.device,
            description=port_info.description or ""
        )

        # Extract manufacturer and VID:PID if available
        manufacturer = ""
        vid_pid = ""
        if hasattr(port_info, 'manufacturer'):
            manufacturer = port_info.manufacturer or ""
            port_data.manufacturer = manufacturer
        if hasattr(port_info, 'vid') and hasattr(port_info, 'pid'):
            if port_info.vid and port_info.pid:
                vid_pid = f"{port_info.vid:04X}:{port_info.pid:04X}"
                port_data.vid_pid = vid_pid

        # Try to identify device by querying it
        try:
            # Check if port is already in use
            if self._is_port_in_use(port_info.device):
                port_data.status = 'in_use'
                # Try to identify from manufacturer/VID:PID even if in use
                device_type, _ = DeviceIdentifier.identify_device(
                    manufacturer=manufacturer,
                    vid_pid=vid_pid,
                    description=port_data.description
                )
                port_data.device_type = device_type
                return port_data

            # Attempt to open port and send IDN query
            serial_number = self._query_device_idn(port_info.device)
            if serial_number:
                port_data.serial_number = serial_number
                # Use comprehensive identification with all available info
                device_type, confidence = DeviceIdentifier.identify_device(
                    serial_number=serial_number,
                    manufacturer=manufacturer,
                    vid_pid=vid_pid,
                    description=port_data.description
                )
                print(f"[DEBUG IDN] Port scan: Identified {port_info.device} as {device_type} (confidence: {confidence}) from serial: {serial_number}")
                port_data.device_type = device_type
                port_data.status = 'available'
            else:
                # No IDN response, try other identification methods
                device_type, _ = DeviceIdentifier.identify_device(
                    manufacturer=manufacturer,
                    vid_pid=vid_pid,
                    description=port_data.description
                )
                port_data.device_type = device_type
                port_data.status = 'available'

        except Exception as e:
            # Port exists but couldn't query it
            port_data.status = 'error' if 'permission' not in str(e).lower() else 'permission_denied'
            # Still try to identify from available info
            device_type, _ = DeviceIdentifier.identify_device(
                manufacturer=manufacturer,
                vid_pid=vid_pid,
                description=port_data.description
            )
            port_data.device_type = device_type

        return port_data

    def _query_device_idn(self, port: str) -> str:
        """
        Query device using *IDN? command to get serial number.

        Args:
            port: Port name to query

        Returns:
            Serial number string or empty string if no response
        """
        serial_number = ""

        try:
            # Open serial connection with short timeout
            ser = serial.Serial(
                port=port,
                baudrate=9600,
                timeout=self.connection_timeout,
                write_timeout=self.connection_timeout
            )

            # Small delay before sending command
            time.sleep(0.4)

            # Send IDN query
            ser.write(b'*IDN?\n')
            print(f"[DEBUG IDN] Port scan: Sent *IDN? to port {port}")
            ser.flush()

            # Wait for response
            time.sleep(0.4)

            # Read response
            if ser.in_waiting:
                response = ser.readline().decode('utf-8', errors='ignore').strip()
                print(f"[DEBUG IDN] Port scan: Raw response from {port}: {repr(response)}")
                if response:
                    serial_number = response
                    print(f"[DEBUG IDN] Port scan: Extracted serial: {serial_number}")

            ser.close()

        except Exception:
            # Failed to query device
            pass

        return serial_number

    def _is_port_in_use(self, port: str) -> bool:
        """
        Check if a port is already in use by another process.

        Args:
            port: Port name to check

        Returns:
            True if port is in use, False otherwise
        """
        try:
            # Try to open the port exclusively
            ser = serial.Serial(port, timeout=0.05)
            ser.close()
            return False
        except serial.SerialException:
            return True
        except Exception:
            return False

    def _run_continuous_monitoring(self):
        """Run continuous monitoring for port changes (hot-plug detection)."""
        poll_interval = 2.0  # Check every 2 seconds

        while not self.is_stop_requested():
            try:
                # Get current ports
                current_ports = {p.device: p for p in serial.tools.list_ports.comports()}
                current_port_names = set(current_ports.keys())

                # Detect removed ports
                removed = self._known_ports - current_port_names
                for port in removed:
                    self.port_removed.emit(port)
                    if port in self._port_info_cache:
                        del self._port_info_cache[port]

                # Detect added ports
                added = current_port_names - self._known_ports
                for port in added:
                    port_info = current_ports[port]
                    # Query new port in background
                    port_data = self._query_single_port(port_info)
                    if port_data:
                        self._port_info_cache[port] = port_data
                        self.port_added.emit(port, port_data.description)
                        self.port_discovered.emit(port_data.to_dict())

                # Update known ports
                self._known_ports = current_port_names

                # Sleep with interruptible wait
                for _ in range(int(poll_interval * 10)):
                    if self.is_stop_requested():
                        break
                    time.sleep(0.1)

            except Exception as e:
                self.error_occurred.emit(f"Monitoring error: {str(e)}")
                time.sleep(poll_interval)


class PortScannerManager:
    """
    Manager class for coordinating port scanning operations.
    Provides a simpler interface to the scanning thread.
    """

    def __init__(self):
        self.scanner_thread = None
        self.monitoring_thread = None

    def start_single_scan(self, callback_discovered=None, callback_complete=None):
        """
        Start a single port scan.

        Args:
            callback_discovered: Function to call when port is discovered
            callback_complete: Function to call when scan completes
        """
        if self.scanner_thread and self.scanner_thread.isRunning():
            return  # Scan already in progress

        self.scanner_thread = PortScannerThread(continuous_monitoring=False)

        if callback_discovered:
            self.scanner_thread.port_discovered.connect(callback_discovered)
        if callback_complete:
            self.scanner_thread.scan_complete.connect(callback_complete)

        self.scanner_thread.start()

    def start_monitoring(self, callback_added=None, callback_removed=None):
        """
        Start continuous port monitoring.

        Args:
            callback_added: Function to call when port is added
            callback_removed: Function to call when port is removed
        """
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            return  # Already monitoring

        self.monitoring_thread = PortScannerThread(continuous_monitoring=True)

        if callback_added:
            self.monitoring_thread.port_added.connect(callback_added)
        if callback_removed:
            self.monitoring_thread.port_removed.connect(callback_removed)

        self.monitoring_thread.start()

    def stop_all(self):
        """Stop all scanning threads."""
        if self.scanner_thread:
            self.scanner_thread.stop()
        if self.monitoring_thread:
            self.monitoring_thread.stop()