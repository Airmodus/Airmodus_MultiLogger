from datetime import datetime as dt
from time import time, sleep
import os
import locale
import platform
import logging
import random
import traceback
import json
import warnings
import sys

from numpy import full, nan, array, polyval, array_equal, roll, nanmean, isnan, linspace
from serial import Serial
from serial.tools import list_ports
from serial.serialutil import SerialException
from PyQt5.QtGui import QPalette, QColor, QIntValidator, QDoubleValidator, QFont, QPixmap, QIcon
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, QLocale
from PyQt5.QtWidgets import (QMainWindow, QSplitter, QApplication, QTabWidget, QGridLayout, QLabel, QWidget,
    QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox, QTextEdit, QSizePolicy,
    QFileDialog, QComboBox, QGraphicsRectItem, QMessageBox)
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, PlotCurveItem, LegendItem, PlotItem, mkPen, mkBrush
from pyqtgraph.parametertree import Parameter, ParameterTree, parameterTypes

# current version number displayed in the GUI (Major.Minor.Patch or Breaking.Feature.Fix)
version_number = "0.10.9"

# Define instrument types
CPC = 1
PSM = 2
Electrometer = 3
CO2_sensor = 4
RHTP = 5
eDiluter = 6
PSM2 = 7
TSI_CPC = 8
AFM = 9
Example_device = -1

# self test error descriptions
CPC_ERRORS = (
    "RESERVED FOR FUTURE USE", "ERROR_SELFTEST_FLASH_ID", "ERROR_SELFTEST_TEMP_OPTICS", "ERROR_SELFTEST_TEMP_SATURATOR", "ERROR_SELFTEST_TEMP_CONDENSER",
    "ERROR_SELFTEST_TEMP_BOARD", "ERROR_SELFTEST_LIQUID_SENSOR", "ERROR_SELFTEST_PRESSURE_INLET", "ERROR_SELFTEST_PRESSURE_NOZZLE", "ERROR_SELFTEST_PRESSURE_CRITICAL",
    "ERROR_SELFTEST_DISPLAY", "ERROR_SELFTEST_VOLTAGE_3V3", "ERROR_SELFTEST_VOLTAGE_5V", "ERROR_SELFTEST_VOLTAGE_12V", "ERROR_SELFTEST_VOLTAGE_REF_NTC",
    "ERROR_SELFTEST_VOLTAGE_REF_PRES", "ERROR_SELFTEST_VOLTAGE_REF_DAC", "ERROR_SELFTEST_VOLTAGE_OPC_DC", "ERROR_SELFTEST_VOLTAGE_LASER",
    "ERROR_SELFTEST_FAN1", "ERROR_SELFTEST_FAN2", "ERROR_SELFTEST_FAN3", "ERROR_SELFTEST_PRESSURE_CAB", "ERROR_SELFTEST_RTC",
    "ERROR_SELFTEST_DAC1", "ERROR_SELFTEST_DAC2", "ERROR_SELFTEST_ANALOG_OUT", "ERROR_SELFTEST_ANALOG_OUT2", "ERROR_SELFTEST_PRESSURE_WREM",
)

PSM_ERRORS = (
    "RESERVED FOR FUTURE USE", "ERROR_SELFTEST_FLASH_ID", "ERROR_SELFTEST_TEMP_GROWTH_TUBE", "ERROR_SELFTEST_TEMP_SATURATOR", "RESERVED FOR FUTURE USE",
    "ERROR_SELFTEST_TEMP_BOARD", "ERROR_SELFTEST_LIQUID_SENSOR", "ERROR_SELFTEST_PRESSURE_ABS", "ERROR_SELFTEST_PRESSURE_ABSSAT", "ERROR_SELFTEST_PRESSURE_SATDRY",
    "ERROR_SELFTEST_TEMP_PREHEATER", "ERROR_SELFTEST_VOLTAGE_3V3", "ERROR_SELFTEST_VOLTAGE_5V", "ERROR_SELFTEST_VOLTAGE_12V", "ERROR_SELFTEST_VOLTAGE_REF_NTC",
    "ERROR_SELFTEST_VOLTAGE_REF_PRES", "ERROR_SELFTEST_VOLTAGE_REF_DAC", "ERROR_SELFTEST_TEMP_INLET", "ERROR_SELFTEST_DRAIN_LIQUID_SENSOR",
    "ERROR_SELFTEST_FAN1", "ERROR_SELFTEST_FAN2", "ERROR_SELFTEST_FAN3", "ERROR_SELFTEST_RTC", "ERROR_SELFTEST_DAC1", "ERROR_SELFTEST_DAC2",
    "ERROR_SELFTEST_TEMP_DRAIN", "ERROR_SELFTEST_MFC_SATURATOR", "ERROR_SELFTEST_MFC_HEATER", "ERROR_SELFTEST_PRESSURE_CRIT", "ERROR_SELFTEST_MFC_VACUUM"
)

warnings.filterwarnings("ignore", message='Mean of empty slice')
warnings.filterwarnings("ignore", message='All-NaN slice encountered')

# Set the LC_ALL environment variable to US English (en_US)
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# set up logging
logging.basicConfig(filename='debug.log', encoding='UTF-8', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

# define file paths according to run mode (exe or script)
script_path = os.path.realpath(os.path.dirname(__file__)) # location of this file
# exe (one file)
if getattr(sys, 'frozen', False):
    save_path = os.path.realpath(os.path.dirname(sys.executable)) # save files to exe location
    resource_path = script_path + "/res" # path of /res/ folder (images, icons)
# script
else:
    save_path = os.path.dirname(script_path) # save files to repository's main folder
    resource_path = os.path.dirname(script_path) + "/res" # path of /res/ folder (images, icons)

# check if platform is OSX
if platform.system() == "Darwin":
    # OSX mode makes code compatible with OSX
    osx_mode = 1
else:
    osx_mode = 0

__all__ = [
    'version_number', 'CPC', 'PSM', 'Electrometer', 'CO2_sensor', 'RHTP', 'eDiluter', 
    'PSM2', 'TSI_CPC', 'AFM', 'Example_device', 'CPC_ERRORS', 'PSM_ERRORS', 
    'osx_mode', 'save_path', 'resource_path', 'script_path'
]
