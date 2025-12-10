#!/usr/bin/env python3
"""
RHTP Device Simulator

Simulates an RHTP (Relative Humidity, Temperature, Pressure) sensor
using a virtual serial port (pty). This allows testing the MultiLogger
application without physical hardware.

Usage:
    python tools/rhtp_simulator.py

    Then configure an RHTP device in MultiLogger with the printed port path.
"""

import argparse
import os
import pty
import random
import select
import signal
import sys
import termios
import time


class RHTPDataGenerator:
    """Generates realistic RHTP sensor data with random variations."""

    def __init__(self, base_humidity=55.0, base_temperature=22.0, base_pressure=1013.25):
        self.base_humidity = base_humidity
        self.base_temperature = base_temperature
        self.base_pressure = base_pressure

    def generate(self):
        """Generate realistic RHTP readings with small random variations."""
        # Add random noise around base values
        humidity = self.base_humidity + random.uniform(-5.0, 5.0)
        humidity = max(0.0, min(100.0, humidity))  # Clamp to 0-100%

        temperature = self.base_temperature + random.uniform(-0.5, 0.5)

        pressure = self.base_pressure + random.uniform(-2.0, 2.0)

        return humidity, temperature, pressure

    def format_message(self):
        """Format data as RHTP protocol message."""
        h, t, p = self.generate()
        # Format: "RH, T, P\r\n" with one decimal place
        return f"{h:.1f}, {t:.1f}, {p:.1f}\r\n"

    def drift(self):
        """Slowly drift base values for more realistic long-term behavior."""
        self.base_humidity += random.uniform(-0.1, 0.1)
        self.base_humidity = max(20.0, min(80.0, self.base_humidity))

        self.base_temperature += random.uniform(-0.02, 0.02)
        self.base_temperature = max(15.0, min(30.0, self.base_temperature))

        self.base_pressure += random.uniform(-0.1, 0.1)
        self.base_pressure = max(980.0, min(1040.0, self.base_pressure))


class RHTPSimulator:
    """Simulates an RHTP device using a virtual serial port."""

    def __init__(self, serial_number="RHTP_SIM_001", push_interval=1.0,
                 base_humidity=55.0, base_temperature=22.0, base_pressure=1013.25,
                 link_path=None, verbose=False):
        self.serial_number = serial_number
        self.push_interval = push_interval
        self.running = False
        self.master_fd = None
        self.slave_fd = None
        self.slave_path = None
        self.link_path = link_path
        self.verbose = verbose
        self.data_generator = RHTPDataGenerator(
            base_humidity=base_humidity,
            base_temperature=base_temperature,
            base_pressure=base_pressure
        )
        self.read_buffer = ""

    def _configure_serial(self):
        """Configure the pty for serial-like operation."""
        try:
            attrs = termios.tcgetattr(self.master_fd)

            # Configure for raw mode
            attrs[0] = 0  # iflag - input modes (no processing)
            attrs[1] = 0  # oflag - output modes (no processing)
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag - 8 bits, enable receiver
            attrs[3] = 0  # lflag - local modes (no echo, no canonical)

            # Set baud rate to 115200
            attrs[4] = termios.B115200  # ispeed
            attrs[5] = termios.B115200  # ospeed

            termios.tcsetattr(self.master_fd, termios.TCSANOW, attrs)
        except termios.error as e:
            print(f"Warning: Could not configure serial settings: {e}")

    def _create_symlink(self):
        """Create a symlink to the pty for consistent port path."""
        if not self.link_path:
            return

        # Remove existing symlink if present
        try:
            if os.path.islink(self.link_path):
                os.unlink(self.link_path)
            elif os.path.exists(self.link_path):
                print(f"Warning: {self.link_path} exists and is not a symlink")
                return
        except OSError as e:
            print(f"Warning: Could not remove existing symlink: {e}")
            return

        # Create new symlink
        try:
            os.symlink(self.slave_path, self.link_path)
        except OSError as e:
            print(f"Warning: Could not create symlink: {e}")

    def _remove_symlink(self):
        """Remove the symlink on shutdown."""
        if not self.link_path:
            return
        try:
            if os.path.islink(self.link_path):
                os.unlink(self.link_path)
        except OSError:
            pass

    def start(self):
        """Create PTY and start simulation."""
        # Create pty pair
        self.master_fd, self.slave_fd = pty.openpty()
        self.slave_path = os.ttyname(self.slave_fd)

        # Configure serial settings
        self._configure_serial()

        # Create symlink for consistent port path
        self._create_symlink()

        # Print connection info
        print("=" * 50)
        print("RHTP Device Simulator")
        print("=" * 50)
        if self.link_path:
            print(f"Use this port: {self.link_path}")
            print(f"(Actual pty: {self.slave_path})")
        else:
            print(f"Virtual port: {self.slave_path}")
        print(f"Serial number: {self.serial_number}")
        print(f"Push interval: {self.push_interval}s")
        print("-" * 50)
        print("Configure this port in MultiLogger for your RHTP device")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        print()

        self.running = True
        self._main_loop()

    def _main_loop(self):
        """Main event loop."""
        last_push = time.time()
        drift_counter = 0

        while self.running:
            try:
                # Check for incoming data (IDN queries) with 0.1s timeout
                readable, _, _ = select.select([self.master_fd], [], [], 0.1)

                if readable:
                    try:
                        data = os.read(self.master_fd, 1024)
                        if data:
                            self._handle_incoming(data)
                    except OSError:
                        # Connection closed
                        pass

                # Push data at regular intervals
                now = time.time()
                if now - last_push >= self.push_interval:
                    self._push_data()
                    last_push = now

                    # Apply drift every 10 pushes
                    drift_counter += 1
                    if drift_counter >= 10:
                        self.data_generator.drift()
                        drift_counter = 0

            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(0.1)

    def _handle_incoming(self, data):
        """Handle incoming commands."""
        try:
            text = data.decode('utf-8', errors='ignore')
            self.read_buffer += text

            # Process complete lines
            while '\r' in self.read_buffer or '\n' in self.read_buffer:
                # Find line ending
                end_idx = -1
                for i, c in enumerate(self.read_buffer):
                    if c in '\r\n':
                        end_idx = i
                        break

                if end_idx == -1:
                    break

                line = self.read_buffer[:end_idx].strip()
                self.read_buffer = self.read_buffer[end_idx + 1:]

                if line:
                    self._process_command(line)

        except Exception as e:
            print(f"Error handling incoming data: {e}")

    def _process_command(self, command):
        """Process a received command."""
        if self.verbose:
            print(f"[RX] {command}")

        # Handle IDN query (various formats)
        if '*IDN' in command.upper():
            response = f"*IDN {self.serial_number}\r\n"
            os.write(self.master_fd, response.encode('utf-8'))
            if self.verbose:
                print(f"[TX] *IDN {self.serial_number}")
        else:
            if self.verbose:
                print(f"[??] Unknown command: {command}")

    def _push_data(self):
        """Push auto-generated data."""
        try:
            message = self.data_generator.format_message()
            os.write(self.master_fd, message.encode('utf-8'))
            if self.verbose:
                print(f"[TX] {message.strip()}")
        except OSError as e:
            print(f"Error pushing data: {e}")

    def stop(self):
        """Stop simulation and cleanup."""
        self.running = False

        # Remove symlink first
        self._remove_symlink()

        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass

        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except OSError:
                pass

        print("\nSimulator stopped")


def main():
    parser = argparse.ArgumentParser(
        description='RHTP Device Simulator - Creates a virtual serial port that mimics an RHTP sensor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rhtp_simulator.py
  python rhtp_simulator.py --link /tmp/airmodus_sim
  python rhtp_simulator.py --serial RHTP_TEST_001 --verbose
        """
    )
    parser.add_argument('--serial', default='RHTP_SIM_001',
                        help='Serial number to report (default: RHTP_SIM_001)')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Data push interval in seconds (default: 1.0)')
    parser.add_argument('--humidity', type=float, default=55.0,
                        help='Base humidity %% (default: 55.0)')
    parser.add_argument('--temperature', type=float, default=22.0,
                        help='Base temperature C (default: 22.0)')
    parser.add_argument('--pressure', type=float, default=1013.25,
                        help='Base pressure hPa (default: 1013.25)')
    parser.add_argument('--link', default='/tmp/airmodus_sim',
                        help='Symlink path for consistent port (default: /tmp/airmodus_sim). Use --link "" to disable.')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output (show TX/RX messages)')

    args = parser.parse_args()

    # Handle empty link path
    link_path = args.link if args.link else None

    simulator = RHTPSimulator(
        serial_number=args.serial,
        push_interval=args.interval,
        base_humidity=args.humidity,
        base_temperature=args.temperature,
        base_pressure=args.pressure,
        link_path=link_path,
        verbose=args.verbose
    )

    def signal_handler(signum, frame):
        simulator.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        simulator.start()
    except KeyboardInterrupt:
        simulator.stop()


if __name__ == "__main__":
    main()
