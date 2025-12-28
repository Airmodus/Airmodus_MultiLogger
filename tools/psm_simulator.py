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
import json
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

        # Scan parameters (from :SET:FLOW:SCAN command)
        self.scan_min_flow = 0.15
        self.scan_max_flow = 1.9
        self.scan_bottom_wait = 10  # seconds
        self.scan_up_time = 110  # seconds
        self.scan_top_wait = 10  # seconds
        self.scan_down_time = 110  # seconds

        # Step parameters (from :SET:FLOW:STEP command)
        self.step_time = 10  # seconds per step
        self.step_flows = [0.3, 0.5, 0.7, 1.0, 1.3, 1.6, 1.9]
        self.step_index = 0
        self.step_time_in_current = 0

        # Fixed parameters (from :SET:FLOW:FXD command)
        self.fixed_flow = 1.0

        # Scan state machine
        self.scan_phase = 0  # 0=bottom_wait, 1=up_scan, 2=top_wait, 3=down_scan
        self.phase_time = 0.0  # time in current phase
        self.current_flow = self.scan_min_flow

        # Base values for PSM measurements
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

    def set_scan_params(self, bottom_wait, up_time, top_wait, down_time, min_flow, max_flow):
        self.scan_bottom_wait = bottom_wait
        self.scan_up_time = up_time
        self.scan_top_wait = top_wait
        self.scan_down_time = down_time
        self.scan_min_flow = min_flow
        self.scan_max_flow = max_flow
        self.scan_phase = 0
        self.phase_time = 0.0
        self.current_flow = min_flow
        self.mode = "scan"

    def set_step_params(self, step_time, step_flows):
        self.step_time = step_time
        self.step_flows = step_flows
        self.step_index = 0
        self.step_time_in_current = 0
        self.current_flow = step_flows[0] if step_flows else 1.0
        self.mode = "step"

    def set_fixed_params(self, flow):
        self.fixed_flow = flow
        self.current_flow = flow
        self.mode = "fixd"

    def _update_scan_flow(self, dt):
        self.phase_time += dt
        phase_durations = [
            self.scan_bottom_wait,
            self.scan_up_time,
            self.scan_top_wait,
            self.scan_down_time
        ]
        current_duration = phase_durations[self.scan_phase]

        if self.phase_time >= current_duration:
            self.phase_time = 0.0
            self.scan_phase = (self.scan_phase + 1) % 4

        if self.scan_phase == 0:
            self.current_flow = self.scan_min_flow
        elif self.scan_phase == 1:
            ratio = self.scan_max_flow / self.scan_min_flow
            power = self.phase_time / self.scan_up_time
            self.current_flow = self.scan_min_flow * (ratio ** power)
        elif self.scan_phase == 2:
            self.current_flow = self.scan_max_flow
        elif self.scan_phase == 3:
            ratio = self.scan_min_flow / self.scan_max_flow
            power = self.phase_time / self.scan_down_time
            self.current_flow = self.scan_max_flow * (ratio ** power)

        self.current_flow = max(self.scan_min_flow, min(self.scan_max_flow, self.current_flow))
        return self.scan_phase

    def _update_step_flow(self, dt):
        self.step_time_in_current += dt
        if self.step_time_in_current >= self.step_time:
            self.step_time_in_current = 0
            self.step_index = (self.step_index + 1) % len(self.step_flows)
        self.current_flow = self.step_flows[self.step_index]
        return 9

    def _update_fixed_flow(self, dt):
        self.current_flow = self.fixed_flow
        return 9

    def generate_measurement(self, dt=1.0):
        if self.mode == "scan":
            scan_status = self._update_scan_flow(dt)
        elif self.mode == "step":
            scan_status = self._update_step_flow(dt)
        else:
            scan_status = self._update_fixed_flow(dt)

        values = [
            f"{self.current_flow:.4f}",
            f"{self.base_excess_flow:.2f}",
            f"{self.base_temp_growth_tube:.1f}",
            f"{self.base_temp_saturator:.1f}",
            f"{self.base_temp_inlet:.1f}",
            f"{self.base_temp_heater:.1f}",
            f"{self.base_temp_drainage:.1f}",
            f"{self.base_temp_cabin:.1f}",
            f"{self.current_flow:.4f}",
            f"{self.base_pres_inlet:.1f}",
            f"{self.base_pres_inlet_sat:.1f}",
            f"{self.base_pres_sat_excess:.1f}",
            f"{self.base_pres_critical:.1f}",
            "4.00",
            "1.000",
            str(scan_status),
            "0x0000",
            "0x0000"
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

    def generate_syst_pout(self):
        """Generate :SYST:POUT response (factory calibration values).

        Format: 19 values total
        - Index 0: Base temp (30.0)
        - Index 1-7: Temperature limits (max/min pairs)
        - Index 8-12: Factory calibration temps (growth tube, saturator, inlet, heater, drainage)
        - Index 13-18: Calibration coefficients
        """
        # Factory calibration values (these are the "golden" reference values)
        factory_growth_tube = 90.0
        factory_saturator = 80.0
        factory_inlet = 25.0
        factory_heater = 40.0
        factory_drainage = 30.0

        values = [
            "30.0",           # 0: Base temp
            "110.0", "-110.0",  # 1-2: Temp limit 1 max/min
            "110.0", "-110.0",  # 3-4: Temp limit 2 max/min
            "110.0", "-110.00", # 5-6: Temp limit 3 max/min
            "110.00",         # 7: Temp limit max
            f"{factory_growth_tube:.2f}",   # 8: Factory growth tube temp
            f"{factory_saturator:.2f}",     # 9: Factory saturator temp
            f"{factory_inlet:.2f}",         # 10: Factory inlet temp
            f"{factory_heater:.3f}",        # 11: Factory heater temp
            f"{factory_drainage:.3f}",      # 12: Factory drainage temp
            "2.5000", "0.0000",  # 13-14: Calibration coefficients
            "1.0000", "0.0000",  # 15-16: Calibration coefficients
            "1.0000", "0.0000"   # 17-18: Calibration coefficients
        ]
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
        self.state_file = f"{link_path}.state" if link_path else None

    def _write_state(self):
        if not self.state_file:
            return
        try:
            state = {
                "flow": self.data_generator.current_flow,
                "mode": self.mode,
                "scan_phase": self.data_generator.scan_phase
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception:
            pass

    def _remove_state_file(self):
        if self.state_file and os.path.exists(self.state_file):
            try:
                os.unlink(self.state_file)
            except OSError:
                pass

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
        print("  :SYST:POUT - Factory calibration values")
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
        elif ':SYST:POUT' in cmd_upper:
            data = self.data_generator.generate_syst_pout()
            response = f":SYST:POUT {data}"
        elif ':SYST:VER' in cmd_upper:
            response = "Firmware version: 0.6.8"
        elif ':SET:FLOW:SCAN' in cmd_upper:
            try:
                parts = command.split(' ', 1)[1].split(',')
                bottom_wait = float(parts[0])
                up_time = float(parts[1])
                top_wait = float(parts[2])
                down_time = float(parts[3])
                min_flow = float(parts[4])
                max_flow = float(parts[5])
                self.data_generator.set_scan_params(bottom_wait, up_time, top_wait, down_time, min_flow, max_flow)
                self.mode = "scan"
                print(f"[SCAN] min={min_flow}, max={max_flow}, up={up_time}s, down={down_time}s")
            except Exception as e:
                print(f"[ERR] Failed to parse SCAN params: {e}")
        elif ':SET:FLOW:STEP' in cmd_upper:
            try:
                parts = command.split(' ', 1)[1].split(',')
                num_steps = int(parts[0])
                step_times = [float(parts[i]) for i in range(1, num_steps + 1)]
                step_flows = [float(parts[i]) for i in range(num_steps + 1, 2 * num_steps + 1)]
                avg_step_time = sum(step_times) / len(step_times) if step_times else 10
                self.data_generator.set_step_params(avg_step_time, step_flows)
                self.mode = "step"
                print(f"[STEP] flows={step_flows}, time={avg_step_time}s")
            except Exception as e:
                print(f"[ERR] Failed to parse STEP params: {e}")
        elif ':SET:FLOW:FXD' in cmd_upper:
            try:
                flow = float(command.split(' ', 1)[1])
                self.data_generator.set_fixed_params(flow)
                self.mode = "fixd"
                print(f"[FIXED] flow={flow}")
            except Exception as e:
                print(f"[ERR] Failed to parse FIXED params: {e}")
        elif ':SET:' in cmd_upper:
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
            data = self.data_generator.generate_measurement(dt=self.push_interval)
            mode_cmd = f":MEAS:{self.mode.upper()}"
            message = f"{mode_cmd} {data}\r\n"
            os.write(self.master_fd, message.encode('utf-8'))
            self._write_state()
            if self.verbose:
                print(f"[TX] {mode_cmd} {data[:50]}...")
        except OSError as e:
            print(f"Error pushing data: {e}")

    def stop(self):
        """Stop simulation and cleanup."""
        self.running = False
        self._remove_symlink()
        self._remove_state_file()
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
  python psm_simulator.py --link /tmp/psm_sim --verbose

To sync with CPC simulator:
  1. python psm_simulator.py --link /tmp/psm_sim
  2. python cpc_simulator.py --link /tmp/cpc_sim --psm-link /tmp/psm_sim
        """
    )
    parser.add_argument('--serial', default='PSM_SIM_001',
                        help='Serial number to report (default: PSM_SIM_001)')
    parser.add_argument('--interval', type=float, default=1.0,
                        help='Data push interval in seconds (default: 1.0)')
    parser.add_argument('--mode', choices=['scan', 'step', 'fixd'], default='scan',
                        help='Measurement mode (default: scan)')
    parser.add_argument('--link', default='/tmp/psm_sim',
                        help='Symlink path for consistent port (default: /tmp/psm_sim)')
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
