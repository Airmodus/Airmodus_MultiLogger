#!/usr/bin/env python3
"""
CPC Device Simulator

Simulates an Airmodus CPC (Condensation Particle Counter) device
using a virtual serial port (pty). The CPC is command-based - it responds
to queries like :MEAS:ALL, :SYST:PRNT, etc.

Usage:
    python tools/cpc_simulator.py

    Then configure a CPC device in MultiLogger with the printed port path.
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


class CPCDataGenerator:
    """Generates realistic CPC sensor data with random variations."""

    def __init__(self):
        # Base values for CPC measurements
        self.base_concentration = 5000.0  # particles/cc
        self.base_pulses = 500
        self.base_dead_time = 0.02
        self.base_temp_saturator = 35.0
        self.base_temp_optics = 40.0
        self.base_temp_condenser = 10.0
        self.base_temp_cabin = 25.0
        self.base_pres_inlet = 101.3
        self.base_pres_critical = 50.0
        self.base_pres_nozzle = 40.0
        self.base_pres_cabin = 101.0
        self.base_laser_current = 2.5
        self.base_liquid_level = 1  # 0=empty, 1=ok, 2=full

    def generate_meas_all(self):
        """Generate :MEAS:ALL response data."""
        concentration = max(0, self.base_concentration + random.uniform(-500, 500))
        pulses = max(0, int(self.base_pulses + random.uniform(-50, 50)))
        dead_time = max(0, self.base_dead_time + random.uniform(-0.005, 0.005))
        pulse_duration = 0.001  # firmware value, not used
        unused = 0

        temp_sat = self.base_temp_saturator + random.uniform(-0.5, 0.5)
        temp_opt = self.base_temp_optics + random.uniform(-0.5, 0.5)
        temp_con = self.base_temp_condenser + random.uniform(-0.5, 0.5)
        temp_cab = self.base_temp_cabin + random.uniform(-0.5, 0.5)

        pres_inlet = self.base_pres_inlet + random.uniform(-1, 1)
        pres_crit = self.base_pres_critical + random.uniform(-1, 1)
        pres_noz = self.base_pres_nozzle + random.uniform(-1, 1)
        pres_cab = self.base_pres_cabin + random.uniform(-1, 1)

        laser = self.base_laser_current + random.uniform(-0.1, 0.1)
        liquid = self.base_liquid_level

        status_hex = "0x0000"  # No errors

        # Format: conc, pulses, dead_time, pulse_dur, unused, temps (4), pressures (4), laser, liquid, status
        values = [
            f"{concentration:.1f}",
            str(pulses),
            f"{dead_time:.4f}",
            f"{pulse_duration:.4f}",
            str(unused),
            f"{temp_sat:.1f}",
            f"{temp_opt:.1f}",
            f"{temp_con:.1f}",
            f"{temp_cab:.1f}",
            f"{pres_inlet:.1f}",
            f"{pres_crit:.1f}",
            f"{pres_noz:.1f}",
            f"{pres_cab:.1f}",
            f"{laser:.2f}",
            str(liquid),
            status_hex
        ]
        return ",".join(values)

    def generate_syst_prnt(self):
        """Generate :SYST:PRNT response (settings)."""
        # mode, temp_sat_set, temp_opt_set, temp_con_set, autofill, drain_set, flow_set
        values = ["1", "35.0", "40.0", "10.0", "1", "0", "1.0"]
        return ",".join(values)

    def generate_syst_pall(self):
        """Generate :SYST:PALL response (all parameters)."""
        # Extended parameters - simplified simulation
        values = [str(i) for i in range(28)]
        values[0] = "1"  # mode
        return ",".join(values)

    def drift(self):
        """Slowly drift base values for more realistic long-term behavior."""
        self.base_concentration += random.uniform(-50, 50)
        self.base_concentration = max(100, min(50000, self.base_concentration))

        self.base_temp_saturator += random.uniform(-0.02, 0.02)
        self.base_temp_condenser += random.uniform(-0.02, 0.02)


class CPCSimulator:
    """Simulates a CPC device using a virtual serial port."""

    def __init__(self, serial_number="CPC_SIM_001", link_path=None, verbose=False):
        self.serial_number = serial_number
        self.running = False
        self.master_fd = None
        self.slave_fd = None
        self.slave_path = None
        self.link_path = link_path
        self.verbose = verbose
        self.data_generator = CPCDataGenerator()
        self.read_buffer = ""

    def _configure_serial(self):
        """Configure the pty for serial-like operation."""
        try:
            attrs = termios.tcgetattr(self.master_fd)
            attrs[0] = 0  # iflag
            attrs[1] = 0  # oflag
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0  # lflag
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

        print("=" * 50)
        print("CPC Device Simulator")
        print("=" * 50)
        if self.link_path:
            print(f"Use this port: {self.link_path}")
            print(f"(Actual pty: {self.slave_path})")
        else:
            print(f"Virtual port: {self.slave_path}")
        print(f"Serial number: {self.serial_number}")
        print("-" * 50)
        print("CPC is command-based. It responds to:")
        print("  :MEAS:ALL  - Measurement data")
        print("  :SYST:PRNT - Settings")
        print("  :SYST:PALL - All parameters")
        print("  *IDN       - Device identification")
        print("-" * 50)
        print("Configure this port in MultiLogger for your CPC device")
        print("Press Ctrl+C to stop")
        print("=" * 50)
        print()

        self.running = True
        self._main_loop()

    def _main_loop(self):
        """Main event loop - CPC only responds to commands."""
        drift_counter = 0

        while self.running:
            try:
                readable, _, _ = select.select([self.master_fd], [], [], 0.1)

                if readable:
                    try:
                        data = os.read(self.master_fd, 1024)
                        if data:
                            self._handle_incoming(data)
                    except OSError:
                        pass

                # Apply drift periodically
                drift_counter += 1
                if drift_counter >= 100:  # Every 10 seconds
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
        elif ':MEAS:ALL' in cmd_upper:
            data = self.data_generator.generate_meas_all()
            response = f":MEAS:ALL {data}"
        elif ':SYST:PRNT' in cmd_upper:
            data = self.data_generator.generate_syst_prnt()
            response = f":SYST:PRNT {data}"
        elif ':SYST:PALL' in cmd_upper:
            data = self.data_generator.generate_syst_pall()
            response = f":SYST:PALL {data}"
        elif ':MEAS:OPC_CONC_LOG' in cmd_upper:
            # 10Hz logging data - just return a simple response
            response = ":MEAS:OPC_CONC_LOG 1000,1100,1050,1020,1080,1030,1060,1090,1040,1070"
        else:
            if self.verbose:
                print(f"[??] Unknown command: {command}")

        if response:
            os.write(self.master_fd, (response + "\r\n").encode('utf-8'))
            if self.verbose:
                print(f"[TX] {response}")

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
        description='CPC Device Simulator - Creates a virtual serial port that mimics a CPC',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cpc_simulator.py
  python cpc_simulator.py --link /tmp/airmodus_sim
  python cpc_simulator.py --serial CPC_TEST_001 --verbose
        """
    )
    parser.add_argument('--serial', default='CPC_SIM_001',
                        help='Serial number to report (default: CPC_SIM_001)')
    parser.add_argument('--link', default='/tmp/airmodus_sim',
                        help='Symlink path for consistent port (default: /tmp/airmodus_sim). Use --link "" to disable.')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output (show TX/RX messages)')

    args = parser.parse_args()

    link_path = args.link if args.link else None

    simulator = CPCSimulator(
        serial_number=args.serial,
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
