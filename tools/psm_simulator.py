#!/usr/bin/env python3
"""
PSM Device Simulator

Simulates an Airmodus PSM (Particle Size Magnifier) device
using a virtual serial port (pty). The PSM auto-pushes measurement data
and also responds to setting queries.

Usage:
    python tools/psm_simulator.py

    Then configure a PSM device in MultiLogger with the printed port path.
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


class PSMDataGenerator:
    """Generates realistic PSM sensor data with random variations."""

    def __init__(self, mode="scan"):
        self.mode = mode  # scan, step, or fixed
        self.scan_position = 0  # 0-100 for scan mode
        self.scan_direction = 1  # 1 = up, -1 = down

        # Base values for PSM measurements
        self.base_saturator_flow = 1.0
        self.base_excess_flow = 0.5
        self.base_temp_growth_tube = 90.0
        self.base_temp_saturator = 80.0
        self.base_temp_inlet = 25.0
        self.base_temp_heater = 40.0
        self.base_temp_drainage = 30.0
        self.base_temp_cabin = 25.0
        self.base_pres_inlet = 101.3
        self.base_pres_inlet_sat = 100.0
        self.base_pres_sat_excess = 99.0
        self.base_pres_critical = 50.0

        # Settings
        self.setting_mode = 1  # 1=scan
        self.setting_temp_gt = 90.0
        self.setting_temp_sat = 80.0
        self.setting_temp_inlet = 25.0
        self.setting_temp_heater = 40.0
        self.setting_temp_drain = 30.0
        self.setting_flow = 1.0

    def generate_meas_scan(self):
        """Generate :MEAS:SCAN response data."""
        # Update scan position
        self.scan_position += self.scan_direction * 2
        if self.scan_position >= 100:
            self.scan_direction = -1
        elif self.scan_position <= 0:
            self.scan_direction = 1

        sat_flow = self.base_saturator_flow + random.uniform(-0.05, 0.05)
        exc_flow = self.base_excess_flow + random.uniform(-0.05, 0.05)

        temp_gt = self.base_temp_growth_tube + random.uniform(-0.5, 0.5)
        temp_sat = self.base_temp_saturator + random.uniform(-0.5, 0.5)
        temp_inlet = self.base_temp_inlet + random.uniform(-0.5, 0.5)
        temp_heater = self.base_temp_heater + random.uniform(-0.5, 0.5)
        temp_drain = self.base_temp_drainage + random.uniform(-0.5, 0.5)
        temp_cabin = self.base_temp_cabin + random.uniform(-0.5, 0.5)

        pres_inlet = self.base_pres_inlet + random.uniform(-1, 1)
        pres_inlet_sat = self.base_pres_inlet_sat + random.uniform(-1, 1)
        pres_sat_exc = self.base_pres_sat_excess + random.uniform(-1, 1)
        pres_crit = self.base_pres_critical + random.uniform(-1, 1)

        poly_corr = 1.0 + random.uniform(-0.01, 0.01)
        scan_status = self.scan_position  # 0-100

        status_hex = "0x0000"
        note_hex = "0x0000"

        # Format matches PSM firmware output
        values = [
            f"{sat_flow:.2f}",       # 0: saturator flow
            f"{exc_flow:.2f}",       # 1: excess flow
            f"{temp_gt:.1f}",        # 2: temp growth tube
            f"{temp_sat:.1f}",       # 3: temp saturator
            f"{temp_inlet:.1f}",     # 4: temp inlet
            f"{temp_heater:.1f}",    # 5: temp heater
            f"{temp_drain:.1f}",     # 6: temp drainage
            f"{temp_cabin:.1f}",     # 7: temp cabin
            f"{pres_inlet:.1f}",     # 8: pressure inlet
            f"{pres_inlet_sat:.1f}", # 9: pressure inlet-saturator
            f"{pres_sat_exc:.1f}",   # 10: pressure saturator-excess
            f"{pres_crit:.1f}",      # 11: pressure critical orifice
            f"{poly_corr:.3f}",      # 12: polynomial correction
            str(scan_status),        # 13: scan status (0-100)
            status_hex,              # 14: status hex
            note_hex                 # 15: note hex
        ]
        return ",".join(values)

    def generate_syst_prnt(self):
        """Generate :SYST:PRNT response (settings)."""
        values = [
            str(self.setting_mode),
            f"{self.setting_temp_gt:.1f}",
            f"{self.setting_temp_sat:.1f}",
            f"{self.setting_temp_inlet:.1f}",
            f"{self.setting_temp_heater:.1f}",
            f"{self.setting_temp_drain:.1f}",
            f"{self.setting_flow:.2f}"
        ]
        return ",".join(values)

    def generate_syst_vcmp(self):
        """Generate :SYST:VCMP response (dilution/vacuum parameters)."""
        # dilution_factor, vacuum_flow, cpc_flow, dilution_enabled, vacuum_enabled, parameter
        values = ["1.0", "0.5", "1.0", "0", "0", "0"]
        return ",".join(values)

    def drift(self):
        """Slowly drift base values for more realistic long-term behavior."""
        self.base_temp_growth_tube += random.uniform(-0.05, 0.05)
        self.base_temp_saturator += random.uniform(-0.05, 0.05)


class PSMSimulator:
    """Simulates a PSM device using a virtual serial port."""

    def __init__(self, serial_number="PSM_SIM_001", push_interval=1.0, mode="scan",
                 link_path=None, verbose=False):
        self.serial_number = serial_number
        self.push_interval = push_interval
        self.mode = mode
        self.running = False
        self.master_fd = None
        self.slave_fd = None
        self.slave_path = None
        self.link_path = link_path
        self.verbose = verbose
        self.data_generator = PSMDataGenerator(mode=mode)
        self.read_buffer = ""

    def _configure_serial(self):
        """Configure the pty for serial-like operation."""
        try:
            attrs = termios.tcgetattr(self.master_fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0
            attrs[4] = termios.B115200
            attrs[5] = termios.B115200
            termios.tcsetattr(self.master_fd, termios.TCSANOW, attrs)
        except termios.error as e:
            print(f"Warning: Could not configure serial settings: {e}")

    def _create_symlink(self):
        """Create a symlink to the pty for consistent port path."""
        if not self.link_path:
            return
        try:
            if os.path.islink(self.link_path):
                os.unlink(self.link_path)
            elif os.path.exists(self.link_path):
                print(f"Warning: {self.link_path} exists and is not a symlink")
                return
        except OSError as e:
            print(f"Warning: Could not remove existing symlink: {e}")
            return
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
        self.master_fd, self.slave_fd = pty.openpty()
        self.slave_path = os.ttyname(self.slave_fd)
        self._configure_serial()
        self._create_symlink()

        mode_cmd = f":MEAS:{self.mode.upper()}"

        print("=" * 50)
        print("PSM Device Simulator")
        print("=" * 50)
        if self.link_path:
            print(f"Use this port: {self.link_path}")
            print(f"(Actual pty: {self.slave_path})")
        else:
            print(f"Virtual port: {self.slave_path}")
        print(f"Serial number: {self.serial_number}")
        print(f"Mode: {self.mode} ({mode_cmd})")
        print(f"Push interval: {self.push_interval}s")
        print("-" * 50)
        print("PSM auto-pushes measurement data and responds to:")
        print("  :SYST:PRNT - Settings")
        print("  :SYST:VCMP - Dilution parameters")
        print("  *IDN       - Device identification")
        print("-" * 50)
        print("Configure this port in MultiLogger for your PSM device")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        print()

        self.running = True
        self._main_loop()

    def _main_loop(self):
        """Main event loop - PSM auto-pushes data."""
        last_push = time.time()
        drift_counter = 0

        while self.running:
            try:
                # Check for incoming commands
                readable, _, _ = select.select([self.master_fd], [], [], 0.1)

                if readable:
                    try:
                        data = os.read(self.master_fd, 1024)
                        if data:
                            self._handle_incoming(data)
                    except OSError:
                        pass

                # Auto-push measurement data at regular intervals
                now = time.time()
                if now - last_push >= self.push_interval:
                    self._push_data()
                    last_push = now

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

            while '\r' in self.read_buffer or '\n' in self.read_buffer:
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
        """Process a received command and send response."""
        if self.verbose:
            print(f"[RX] {command}")
        response = None

        cmd_upper = command.upper()

        if '*IDN' in cmd_upper:
            response = f"*IDN {self.serial_number}"
        elif ':SYST:PRNT' in cmd_upper:
            data = self.data_generator.generate_syst_prnt()
            response = f":SYST:PRNT {data}"
        elif ':SYST:VCMP' in cmd_upper:
            data = self.data_generator.generate_syst_vcmp()
            response = f":SYST:VCMP {data}"
        elif ':SYST:VER' in cmd_upper:
            # PSM 2.0 firmware is >= 0.6.x
            response = "Firmware version: 0.6.8"
        elif ':SET:' in cmd_upper:
            # Accept SET commands silently
            if self.verbose:
                print(f"[OK] Setting accepted: {command}")
        else:
            if self.verbose:
                print(f"[??] Unknown command: {command}")

        if response:
            os.write(self.master_fd, (response + "\r\n").encode('utf-8'))
            if self.verbose:
                print(f"[TX] {response}")

    def _push_data(self):
        """Push auto-generated measurement data."""
        try:
            data = self.data_generator.generate_meas_scan()
            mode_cmd = f":MEAS:{self.mode.upper()}"
            message = f"{mode_cmd} {data}\r\n"
            os.write(self.master_fd, message.encode('utf-8'))
            if self.verbose:
                print(f"[TX] {mode_cmd} {data[:50]}...")
        except OSError as e:
            print(f"Error pushing data: {e}")

    def stop(self):
        """Stop simulation and cleanup."""
        self.running = False
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
        description='PSM Device Simulator - Creates a virtual serial port that mimics a PSM',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python psm_simulator.py
  python psm_simulator.py --link /tmp/airmodus_sim
  python psm_simulator.py --serial PSM_TEST_001 --verbose
        """
    )
    parser.add_argument('--serial', default='PSM_SIM_001',
                        help='Serial number to report (default: PSM_SIM_001)')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Data push interval in seconds (default: 1.0)')
    parser.add_argument('--mode', choices=['scan', 'step', 'fixd'], default='scan',
                        help='Measurement mode (default: scan)')
    parser.add_argument('--link', default='/tmp/airmodus_sim',
                        help='Symlink path for consistent port (default: /tmp/airmodus_sim). Use --link "" to disable.')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output (show TX/RX messages)')

    args = parser.parse_args()

    link_path = args.link if args.link else None

    simulator = PSMSimulator(
        serial_number=args.serial,
        push_interval=args.interval,
        mode=args.mode,
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
