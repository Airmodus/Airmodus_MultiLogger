# main.py
from PyQt5.QtWidgets import QApplication
from config import version_number
from app import MainWindow  # temp; MainWindow comes here later

if __name__ == '__main__':
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()
