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

# Polling interval constants for adaptive scanning
POLL_INTERVAL_SLOW = 10.0  # When port selection dialog is closed
POLL_INTERVAL_FAST = 2.0   # When port selection dialog is open


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
        self.model = ""  # Device model/descriptor from IDN
        self.firmware = ""  # Firmware version from IDN

    def to_dict(self) -> dict:
        return {
            'port': self.port,
            'description': self.description,
            'serial_number': self.serial_number,
            'device_type': self.device_type,
            'status': self.status,
            'manufacturer': self.manufacturer,
            'vid_pid': self.vid_pid,
            'model': self.model,
            'firmware': self.firmware
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
                 max_workers: int = 5, poll_interval: float = POLL_INTERVAL_SLOW,
                 parent=None):
        """
        Initialize the port scanner thread.

        Args:
            continuous_monitoring: If True, continuously monitor for port changes
            max_workers: Maximum number of concurrent port queries
            poll_interval: Interval between port scans in seconds
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
        self._poll_interval = poll_interval  # Dynamic polling interval

    def stop(self):
        """Request the thread to stop and clear caches."""
        with QMutexLocker(self._mutex):
            self._stop_requested = True
        self.wait()  # Wait for thread to finish
        # Clear caches to prevent memory leaks
        self._port_info_cache.clear()
        self._known_ports.clear()

    def is_stop_requested(self) -> bool:
        """Check if stop has been requested."""
        with QMutexLocker(self._mutex):
            return self._stop_requested

    def set_poll_interval(self, interval: float):
        """
        Set the polling interval dynamically (thread-safe).

        Args:
            interval: New polling interval in seconds
        """
        with QMutexLocker(self._mutex):
            self._poll_interval = interval

    def get_poll_interval(self) -> float:
        """Get the current polling interval (thread-safe)."""
        with QMutexLocker(self._mutex):
            return self._poll_interval

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
                # Try to identify even if in use
                device_type = DeviceIdentifier.identify_device(
                    manufacturer=manufacturer,
                    vid_pid=vid_pid,
                    description=port_data.description
                )
                # Only use device_type if it's a known type, otherwise mark as Unknown
                known_types = DeviceIdentifier.get_all_device_types()
                port_data.device_type = device_type if device_type in known_types else 'Unknown'
                return port_data

            # Attempt to open port and send IDN query
            idn_info = self._query_device_idn(port_info.device)
            if idn_info:
                # Store parsed IDN information
                port_data.serial_number = idn_info.get('serial_number', '')
                port_data.model = idn_info.get('model', '')
                port_data.firmware = idn_info.get('firmware', '')

                # Use IDN manufacturer if available, otherwise use USB manufacturer
                idn_manufacturer = idn_info.get('manufacturer', '')
                if idn_manufacturer:
                    manufacturer = idn_manufacturer

                # Simple identification with available info
                device_type = DeviceIdentifier.identify_device(
                    serial_number=idn_info.get('serial_number', ''),
                    model=idn_info.get('model', ''),
                    raw_response=idn_info.get('raw_response', ''),
                    manufacturer=manufacturer,
                    vid_pid=vid_pid,
                    description=port_data.description
                )
                # Only use device_type if it's a known type, otherwise mark as Unknown
                known_types = DeviceIdentifier.get_all_device_types()
                port_data.device_type = device_type if device_type in known_types else 'Unknown'
                port_data.status = 'available'
            else:
                # No IDN response, just return Unknown
                device_type = DeviceIdentifier.identify_device(
                    manufacturer=manufacturer,
                    vid_pid=vid_pid,
                    description=port_data.description
                )
                # Only use device_type if it's a known type, otherwise mark as Unknown
                known_types = DeviceIdentifier.get_all_device_types()
                port_data.device_type = device_type if device_type in known_types else 'Unknown'
                port_data.status = 'available'

        except Exception as e:
            # Port exists but couldn't query it
            port_data.status = 'error' if 'permission' not in str(e).lower() else 'permission_denied'
            # Still try to identify from available info
            device_type = DeviceIdentifier.identify_device(
                manufacturer=manufacturer,
                vid_pid=vid_pid,
                description=port_data.description
            )
            # Only use device_type if it's a known type, otherwise mark as Unknown
            known_types = DeviceIdentifier.get_all_device_types()
            port_data.device_type = device_type if device_type in known_types else 'Unknown'

        return port_data

    def _parse_idn_response(self, response: str) -> dict:
        """
        Parse IDN response into structured components.

        Typical format: "*IDN Airmodus A11 nCNC,PSN:A11-0123,FW:2.1.0"

        Args:
            response: Raw IDN response string

        Returns:
            Dictionary with parsed components:
            - raw_response: Full original response
            - model: Device model/descriptor (e.g., "Airmodus A11 nCNC")
            - serial_number: Extracted serial from PSN field or full response
            - firmware: Firmware version from FW field
            - manufacturer: Extracted manufacturer name
        """
        parsed = {
            'raw_response': response,
            'model': '',
            'serial_number': '',
            'firmware': '',
            'manufacturer': ''
        }

        # Validate this is actually an IDN response
        # Reject pure numbers (sensor data)
        try:
            float(response.replace(',', '.'))
            # This is just a number, not an IDN response
            return {}
        except ValueError:
            pass  # Not a pure number, continue parsing

        # Reject structured data formats
        if any(c in response for c in ['<', '>', '=', '[', ']', '{', '}']):
            return {}  # Looks like XML, JSON, or other structured data

        # Remove *IDN prefix if present
        cleaned_response = response
        if response.startswith('*IDN '):
            cleaned_response = response[5:]
        elif response.startswith('*IDN'):
            cleaned_response = response[4:].lstrip()
        elif response.startswith('IDN '):
            cleaned_response = response[4:]
        elif response.startswith('IDN'):
            cleaned_response = response[3:].lstrip()

        # Split by comma to get model and fields
        parts = cleaned_response.split(',')
        if parts and cleaned_response:
            # First part is usually the model/device descriptor or just the serial
            parsed['model'] = parts[0].strip()

            # If there's no PSN field, treat the model as the serial number
            parsed['serial_number'] = parts[0].strip()

            # Extract manufacturer from model if possible
            model_words = parsed['model'].split()
            if model_words:
                # First word is often manufacturer
                parsed['manufacturer'] = model_words[0]

            # Parse PSN and FW fields (override serial if PSN exists)
            for part in parts[1:]:
                part = part.strip()
                if part.startswith('PSN:'):
                    parsed['serial_number'] = part[4:].strip()
                elif part.startswith('FW:'):
                    parsed['firmware'] = part[3:].strip()

        return parsed

    def _query_device_idn(self, port: str) -> dict:
        """
        Query device using *IDN? command and parse the response.

        Args:
            port: Port name to query

        Returns:
            Dictionary with parsed IDN components or empty dict if no response
        """
        idn_info = {}

        try:
            # Open serial connection with short timeout
            ser = serial.Serial(
                port=port,
                baudrate=115200,  # Standard baud rate for Airmodus devices
                timeout=self.connection_timeout,
                write_timeout=self.connection_timeout,
                dsrdtr=False,
                dtr=False
            )

            # Small delay before sending command
            time.sleep(0.4)

            # Send IDN query
            ser.write(b'*IDN?\n')
            ser.flush()

            # Wait for response
            time.sleep(0.4)

            # Read all available data
            raw_data = ser.read_all()
            if raw_data:
                # Decode and split messages by \r
                decoded = raw_data.decode('utf-8', errors='ignore')
                messages = decoded.split('\r')

                # Process each message
                for message in messages:
                    message = message.strip('\n').strip('\r').strip()

                    # Check if message is long enough and contains *IDN
                    if len(message) > 5 and '*IDN ' in message:
                        # Extract everything after "*IDN " (position 5)
                        idx = message.index('*IDN ')
                        serial_number = message[idx + 5:].strip()
                        idn_info = {
                            'serial_number': serial_number,
                            'raw_response': message,
                            'model': serial_number,  # Use full serial as model
                            'firmware': '',
                            'manufacturer': ''
                        }
                        break  # Found IDN response, no need to continue

                    # Handle eDiluter format
                    elif ' ID ' in message and ', Status' in message:
                        try:
                            start_idx = message.index(' ID ') + 4
                            end_idx = message.index(', Status')
                            device_id = message[start_idx:end_idx].strip()
                            idn_info = {
                                'serial_number': device_id,
                                'raw_response': message,
                                'model': device_id,
                                'firmware': '',
                                'manufacturer': 'eDiluter'
                            }
                            break
                        except (ValueError, IndexError):
                            pass

            ser.close()

        except Exception:
            # Failed to query device
            pass

        return idn_info

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
            ser = serial.Serial(port, timeout=0.05, dsrdtr=False, dtr=False)
            ser.close()
            return False
        except serial.SerialException:
            return True
        except Exception:
            return False

    def _run_continuous_monitoring(self):
        """Run continuous monitoring for port changes (hot-plug detection)."""
        while not self.is_stop_requested():
            try:
                # Get current polling interval (can change dynamically)
                poll_interval = self.get_poll_interval()

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

                # Sleep with interruptible wait (check interval frequently to respond to changes)
                sleep_steps = int(poll_interval * 10)
                for _ in range(sleep_steps):
                    if self.is_stop_requested():
                        break
                    time.sleep(0.1)

            except Exception as e:
                self.error_occurred.emit(f"Monitoring error: {str(e)}")
                time.sleep(self.get_poll_interval())


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

    def set_fast_mode(self, enabled: bool):
        """
        Set the port scanning speed mode.

        Args:
            enabled: If True, use fast polling (2s) for responsive UI.
                     If False, use slow polling (10s) for background detection.
        """
        interval = POLL_INTERVAL_FAST if enabled else POLL_INTERVAL_SLOW
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            self.monitoring_thread.set_poll_interval(interval)

    def get_port_info(self) -> dict:
        """
        Get current port information from the monitoring thread's cache.

        Returns:
            Dictionary mapping port names to their info dicts.
            Example: {'COM3': {'device_type': 'CPC', 'serial_number': 'A12-1234', ...}}
        """
        if self.monitoring_thread and hasattr(self.monitoring_thread, '_port_info_cache'):
            # Convert PortInfo objects to dicts
            return {
                port: info.to_dict()
                for port, info in self.monitoring_thread._port_info_cache.items()
            }
        return {}