from PyQt5.QtCore import QTimer, Qt
from time import time, sleep
from datetime import datetime as dt
from config import TIMER_DELAY_MS, MAX_TIME_SEC

class TimerService:
    def __init__(self, main_window, data_holder, device_manager, plot_manager):
        self.main_window = main_window
        self.device_manager = device_manager 
        self.data_holder = data_holder
        self.plot_manager = plot_manager
        self.timer = QTimer(timerType=Qt.PreciseTimer)
        self.timer.timeout.connect(self.timer_functions)

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
        self.data_holder.current_time = int(time())
        self.data_holder.error_status = 0
        self.data_holder.saving_status = 1
        self.data_holder.device_errors = {key: False for key in self.data_holder.device_errors}
        self.device_manager.connection_test()
        if self.data_holder.first_connection:
            self.device_manager.get_dev_data()
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(TIMER_DELAY_MS, self.delayed_functions) 

    # Moved from MainWindow.delayed_functions
    def delayed_functions(self):
        self.device_manager.readIndata()
        self.device_manager.ten_hz_check()
        self.plot_manager.update_plot_data()
        self.plot_manager.update_figures_and_menus()
        self.main_window.compare_day()
        self.main_window.write_data()
        self.main_window.update_error_icons()
        self.main_window.status_lights.set_error_light(self.data_holder.error_status)
        self.main_window.status_lights.set_saving_light(self.data_holder.saving_status)
        if self.data_holder.time_counter < MAX_TIME_SEC - 1:
            self.data_holder.time_counter += 1
        else:
            self.data_holder.max_reached = True
        current_datetime = dt.fromtimestamp(self.data_holder.current_time)
        if current_datetime.hour in [11, 23] and current_datetime.minute == 59 and current_datetime.second == 59:
            self.restart()
