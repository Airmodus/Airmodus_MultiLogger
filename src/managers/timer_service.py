from PyQt5.QtCore import QTimer, Qt
from time import time, sleep
from datetime import datetime as dt
from config import TIMER_DELAY_MS, MAX_TIME_SEC

class TimerService:
    def __init__(self, main_window, data_holder, device_manager, plot_manager, data_logger):
        self.main_window = main_window
        self.device_manager = device_manager
        self.data_holder = data_holder
        self.plot_manager = plot_manager
        self.data_logger = data_logger
        self.timer = QTimer(timerType=Qt.PreciseTimer)
        self.timer.timeout.connect(self.timer_functions)
        # Flag to prevent overlapping delayed_functions execution
        self._delayed_running = False

    def start(self):
        start_time = time()
        sync_time = start_time - int(start_time)
        sleep(1 - sync_time)
        self.timer.start(1000)
        print("Timer start time:", time())

    def stop(self):
        self.timer.stop()

    def restart(self):
        self.stop()
        print("Restarting timer...")
        self.start()
        self.timer_functions()  # Call immediately after restart

    def timer_functions(self):
        try:
            self.data_holder.current_time = int(time())
            self.data_holder.error_status = 0
            self.data_holder.saving_status = 1
            self.data_holder.device_errors = {key: False for key in self.data_holder.device_errors}
            self.device_manager.connection_test()
            if self.data_holder.first_connection:
                self.device_manager.get_dev_data()
                # Only schedule delayed_functions if previous one has completed
                if not self._delayed_running:
                    from PyQt5.QtCore import QTimer
                    QTimer.singleShot(TIMER_DELAY_MS, self._safe_delayed_functions)
        except Exception as e:
            print(f"Error in timer_functions: {e}")
            import traceback
            traceback.print_exc() 

    def _safe_delayed_functions(self):
        """Wrapper that prevents overlapping execution and handles errors."""
        self._delayed_running = True
        try:
            self.delayed_functions()
        except Exception as e:
            print(f"Error in delayed_functions: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._delayed_running = False

    # Moved from MainWindow.delayed_functions
    def delayed_functions(self):
        self.device_manager.readIndata()
        self.device_manager.ten_hz_check()
        self.plot_manager.update_plot_data()
        self.plot_manager.update_figures_and_menus()
        self.data_logger.compare_day()
        self.data_logger.write_data()
        self.check_and_write_database()  # Database writes (if enabled)
        self.device_manager.update_error_icons()
        # Update status bar with latest device data and global status
        if hasattr(self.main_window, 'status_bar'):
            self.main_window.status_bar.update_all_devices()
            self.main_window.status_bar.update_global_status()
        if self.data_holder.time_counter < MAX_TIME_SEC - 1:
            self.data_holder.time_counter += 1
        else:
            self.data_holder.max_reached = True
        current_datetime = dt.fromtimestamp(self.data_holder.current_time)
        if current_datetime.hour in [11, 23] and current_datetime.minute == 59 and current_datetime.second == 59:
            self.restart()

    def check_and_write_database(self):
        """Check and write averaged data to database for CPC devices."""
        from config import CPC

        # Check if database manager exists and is connected
        if not hasattr(self.main_window, 'database_manager') or not self.main_window.database_manager.connected:
            return

        current_time = dt.fromtimestamp(self.data_holder.current_time)

        # Loop through all CPC devices
        for device_config in self.main_window.config.devices:
            if device_config.device_type != CPC:
                continue

            dev_id = device_config.device_id

            # Check if database enabled for this device
            db_enabled = device_config.extra_params.get('database_enabled', False)
            if not db_enabled:
                continue

            # Check if linked RHTP is set
            linked_rhtp = device_config.extra_params.get('linked_rhtp', 'None')
            if linked_rhtp == 'None':
                # Show error in database tab and disable database
                cpc_widget = self.data_holder.device_widgets.get(dev_id)
                if cpc_widget and hasattr(cpc_widget, 'database_tab'):
                    cpc_widget.database_tab.add_message(
                        f"{current_time.strftime('%H:%M:%S')}: Error - No RHTP linked. Database disabled."
                    )
                device_config.extra_params['database_enabled'] = False
                continue

            # Get device widgets
            cpc_widget = self.data_holder.device_widgets.get(dev_id)
            if not cpc_widget or not cpc_widget.current_data:
                continue

            # Get linked RHTP widget
            rhtp_id = linked_rhtp
            rhtp_widget = self.data_holder.device_widgets.get(rhtp_id)
            if not rhtp_widget or not hasattr(rhtp_widget, 'current_data') or not rhtp_widget.current_data:
                # RHTP data not available
                if hasattr(cpc_widget, 'database_tab'):
                    cpc_widget.database_tab.add_message(
                        f"{current_time.strftime('%H:%M:%S')}: Warning - RHTP data not available"
                    )
                continue

            # Get averager for this device
            averager = self.main_window.database_manager.averagers.get(dev_id)
            if not averager:
                # Create averager if missing
                interval_str = device_config.extra_params.get('db_averaging_interval', '1 minute')
                interval_map = {'1 minute': 1, '5 minutes': 5, '10 minutes': 10, '15 minutes': 15, '1 hour': 60, '3 hours': 180}
                interval_minutes = interval_map.get(interval_str, 1)
                averager = self.main_window.database_manager.create_averager(dev_id, interval_minutes)

            if not averager:
                continue

            # Add current sample to averager
            averager.add_sample(current_time, cpc_widget.current_data, rhtp_widget.current_data)

            # Update progress indicators in UI
            if hasattr(cpc_widget, 'database_tab'):
                samples_collected = len(averager.cpc_buffer)
                total_samples = averager.interval_seconds  # 1 sample per second
                cpc_widget.database_tab.update_progress(
                    samples_collected,
                    total_samples,
                    averager.interval_start,
                    averager.interval_seconds
                )

            # Check if we should write averaged data
            if averager.should_write(current_time):
                try:
                    # Calculate averages
                    averaged_data = averager.calculate_average()

                    if averaged_data:
                        # Get CPC serial number and inlet flow
                        serial_number = device_config.serial_number
                        inlet_flow = None
                        if hasattr(cpc_widget, 'settings') and cpc_widget.settings:
                            # Use measured flow (actual) first, fallback to nominal flow (setpoint)
                            if hasattr(cpc_widget.settings, 'measured_cpc_flow'):
                                inlet_flow = cpc_widget.settings.measured_cpc_flow
                            elif hasattr(cpc_widget.settings, 'nominal_inlet_flow'):
                                inlet_flow = cpc_widget.settings.nominal_inlet_flow

                        # Write to database
                        success, message = self.main_window.database_manager.write_averaged_record(
                            averaged_data,
                            dev_id,
                            serial_number,
                            inlet_flow
                        )

                        if success:
                            # Update UI
                            if hasattr(cpc_widget, 'database_tab'):
                                cpc_widget.database_tab.update_last_write(
                                    averaged_data['time'].strftime('%Y-%m-%d %H:%M:%S')
                                )
                                averager.records_written += 1
                                cpc_widget.database_tab.update_record_count(averager.records_written)

                                # Update latest data table
                                latest_rows = self.main_window.database_manager.get_latest_rows(10, dev_id)
                                cpc_widget.database_tab.update_data_table(latest_rows)
                        else:
                            # Show error
                            if hasattr(cpc_widget, 'database_tab'):
                                cpc_widget.database_tab.add_message(
                                    f"{current_time.strftime('%H:%M:%S')}: Error - {message}"
                                )
                finally:
                    # Always reset buffers to prevent unbounded growth
                    averager.reset_buffers()
