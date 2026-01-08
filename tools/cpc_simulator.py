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
import json
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

    def __init__(self, psm_link=None):
        self.psm_state_file = f"{psm_link}.state" if psm_link else None
        self.psm_flow = 0.15
        self.min_flow = 0.15
        self.max_flow = 1.9
        # Concentration range matching expected output (~100-300 at low flow, ~900-1100 at peaks)
        self.base_concentration = 200.0  # Base concentration at minimum flow
        self.max_concentration = 1000.0  # Max concentration at maximum flow
        # Noise parameters for realistic CPC behavior
        self.noise_base_std = 50.0  # Standard deviation of noise at base level
        self.noise_peak_std = 100.0  # Standard deviation of noise at peak level
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
        self.base_liquid_level = 1

    def _read_psm_state(self):
        if not self.psm_state_file:
            return
        try:
            with open(self.psm_state_file, 'r') as f:
                state = json.load(f)
                self.psm_flow = state.get("flow", 0.15)
        except Exception:
            pass

    def _calculate_concentration(self):
        self._read_psm_state()
        flow_ratio = (self.psm_flow - self.min_flow) / (self.max_flow - self.min_flow)
        flow_ratio = max(0, min(1, flow_ratio))

        # Linear relationship so CPC mirrors the PSM's exponential flow shape directly
        mean_concentration = self.base_concentration + (self.max_concentration - self.base_concentration) * flow_ratio

        # Add realistic noise that scales with concentration level
        # Higher concentrations have proportionally more noise (Poisson-like behavior)
        noise_std = self.noise_base_std + (self.noise_peak_std - self.noise_base_std) * flow_ratio
        noise = random.gauss(0, noise_std)

        # Add some random spikes (occasional particle bursts)
        if random.random() < 0.05:  # 5% chance of spike
            noise += random.uniform(50, 200) * (1 + flow_ratio)

        concentration = mean_concentration + noise
        # Ensure concentration stays positive and realistic
        concentration = max(50, concentration)

        return concentration

    def generate_meas_all(self):
        """Generate :MEAS:ALL response data."""
        concentration = self._calculate_concentration()
        pulses = int(concentration / 10)

        values = [
            f"{concentration:.1f}",
            str(pulses),
            f"{self.base_dead_time:.4f}",
            "0.0010",
            "0",
            f"{self.base_temp_saturator:.1f}",
            f"{self.base_temp_optics:.1f}",
            f"{self.base_temp_condenser:.1f}",
            f"{self.base_temp_cabin:.1f}",
            f"{self.base_pres_inlet:.1f}",
            f"{self.base_pres_critical:.1f}",
            f"{self.base_pres_nozzle:.1f}",
            f"{self.base_pres_cabin:.1f}",
            f"{self.base_laser_current:.2f}",
            str(self.base_liquid_level),
            "0x0000"
        ]
        return ",".join(values)

    def generate_syst_prnt(self):
        """Generate :SYST:PRNT response (settings).

        Format (13 values):
        0: mode
        1: autofill
        2: drain
        3: flow_adjustment
        4: water_removal
        5: averaging_time
        6: condenser_temp setpoint
        7: optics_temp setpoint
        8: saturator_temp setpoint
        9: unused
        10: measured_cpc_flow
        11: unused
        12: dead_time_correction
        """
        values = [
            "1",      # 0: mode
            "1",      # 1: autofill (on)
            "0",      # 2: drain (off)
            "1.0",    # 3: flow_adjustment
            "0",      # 4: water_removal (off)
            "1.0",    # 5: averaging_time
            "30.50",  # 6: condenser_temp setpoint (matches POUT factory value)
            "40.0",   # 7: optics_temp setpoint
            "39.00",  # 8: saturator_temp setpoint (matches POUT factory value)
            "0",      # 9: unused
            "1.0",    # 10: measured_cpc_flow
            "0",      # 11: unused
            "0.02",   # 12: dead_time_correction
        ]
        return ",".join(values)

    def generate_syst_pall(self):
        """Generate :SYST:PALL response (all parameters)."""
        # Extended parameters - simplified simulation
        values = [str(i) for i in range(28)]
        values[0] = "1"  # mode
        return ",".join(values)

    def generate_syst_pout(self):
        """Generate :SYST:POUT response (factory calibration values)."""
        # Factory calibration format:
        # indices 0-5: limits/config, 6: saturator_temp, 7: condenser_temp, 8-9: coefficients, 10: unknown
        values = [
            "20",      # 0: unknown
            "130",     # 1: max temp limit
            "-1",      # 2: min temp limit
            "45",      # 3: max temp limit
            "-2",      # 4: min temp limit
            "5",       # 5: unknown
            "39.00",   # 6: factory saturator temp
            "30.50",   # 7: factory condenser temp
            "0.15049", # 8: calibration coefficient
            "5.21817", # 9: calibration coefficient
            "0"        # 10: unknown
        ]
        return ",".join(values)

    def drift(self):
        """Slowly drift base values for more realistic long-term behavior."""
        self.base_concentration += random.uniform(-50, 50)
        self.base_concentration = max(100, min(50000, self.base_concentration))

        self.base_temp_saturator += random.uniform(-0.02, 0.02)
        self.base_temp_condenser += random.uniform(-0.02, 0.02)


class CPCSimulator:
    """Simulates a CPC device using a virtual serial port."""

    def __init__(self, serial_number="CPC_SIM_001", link_path=None, verbose=False, psm_link=None):
        self.serial_number = serial_number
        self.running = False
        self.master_fd = None
        self.slave_fd = None
        self.slave_path = None
        self.link_path = link_path
        self.verbose = verbose
        self.psm_link = psm_link
        self.data_generator = CPCDataGenerator(psm_link=psm_link)
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
        if self.psm_link:
            print(f"PSM sync: {self.psm_link}.state")
        print("-" * 50)
        print("CPC is command-based. It responds to:")
        print("  :MEAS:ALL  - Measurement data")
        print("  :SYST:PRNT - Settings")
        print("  :SYST:PALL - All parameters")
        print("  *IDN       - Device identification")
        if self.psm_link:
            print("-" * 50)
            print("Concentration synced with PSM flow:")
            print("  Low flow (0.15) -> ~1000 particles/cc")
            print("  High flow (1.9) -> ~50000 particles/cc")
        print("-" * 50)
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
        elif ':SYST:POUT' in cmd_upper:
            data = self.data_generator.generate_syst_pout()
            response = f":SYST:POUT {data}"
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
  python cpc_simulator.py --link /tmp/cpc_sim --psm-link /tmp/psm_sim
  python cpc_simulator.py --serial CPC_TEST_001 --verbose
        """
    )
    parser.add_argument('--serial', default='CPC_SIM_001',
                        help='Serial number to report (default: CPC_SIM_001)')
    parser.add_argument('--link', default='/tmp/cpc_sim',
                        help='Symlink path for consistent port (default: /tmp/cpc_sim)')
    parser.add_argument('--psm-link', default=None,
                        help='PSM simulator link path to sync concentration with PSM flow')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable verbose output (show TX/RX messages)')

    args = parser.parse_args()

    link_path = args.link if args.link else None
    psm_link = args.psm_link if args.psm_link else None

    simulator = CPCSimulator(
        serial_number=args.serial,
        link_path=link_path,
        verbose=args.verbose,
        psm_link=psm_link
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
