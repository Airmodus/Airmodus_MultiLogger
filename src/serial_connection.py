import sys
from time import time 
from PyQt5.QtCore import QTimer
from serial import Serial
from serial.tools import list_ports
from serial.serialutil import SerialException
from config import osx_mode, TSI_CPC 

class SerialDeviceConnection():
    def __init__(self):
        self.serial_port = "NaN"
        self.timeout = 0.2
        self.baud_rate = 115200
        
    def set_port(self, serial_port):
        self.serial_port = serial_port
    
    def set_baud_rate(self, baud_rate):
        self.baud_rate = baud_rate
    
    # open serial connection
    def connect(self):
        try: # Try to close with the port that was last used (needed if the port has been changed)
            self.connection.close()
        except: # if fails (i.e. port has not been open) continue normally
            pass
        self.connection = Serial(self.serial_port, self.baud_rate, timeout=self.timeout) #, rtscts=True)
        print("Connected to %s" % self.serial_port)
    
    # close serial connection
    def close(self):
        # if connection exist, it is closed
        try:
            # Try to close with the port that was last used (needed if the port has been changed)
            self.connection.close()
            #print("Connection closed")
        except:
            pass
    
    # close old connection and open new connection
    def change_port(self, serial_port):
        # close current connection
        self.close()
        # set new port
        self.set_port(serial_port)
        try:
            # connect to new port
            self.connect()
        except Exception as e:
            print("change_port:", e)
    
    def send_message(self, message):
        # add line termination and convert to bytes
        message = bytes((str(message)+'\r\n'), 'utf-8')
        try:
            # send message if connection exists
            self.connection.write(message)
        except AttributeError:
            # print message if connection does not exist
            print("send_message - no connection, message -", message)
    
    def send_delayed_message(self, message, delay):
        QTimer.singleShot(delay, lambda: self.send_message(message))
    
    def send_multiple_messages(self, device_type, ten_hz=False):

        if device_type == 1: # CPC
            self.send_message(":MEAS:ALL")
            QTimer.singleShot(150, lambda: self.send_message(":SYST:PRNT"))
            QTimer.singleShot(300, lambda: self.send_message(":SYST:PALL"))
            if ten_hz:
                QTimer.singleShot(450, lambda: self.send_message(":MEAS:OPC_CONC_LOG"))
        
        elif device_type == TSI_CPC: # TSI CPC
            self.send_message("RD") # read concentration
            QTimer.singleShot(150, lambda: self.send_message("RIE")) # read instrument errors
    
    def send_pulse_analysis_messages(self, threshold):
        # send required messages for pulse analysis
        self.send_message(":SET:OPC:THRS " + str(threshold))
        QTimer.singleShot(150, lambda: self.send_message(":MEAS:ALL"))
    
    # --- CPC & PSM set/command functions ---

    # # send set message
    def send_set(self, message):
        if message == None:
            # if message is None, do nothing
            return
        else:
            # send message
            self.send_message(message)
    
    # add value to set message
    def send_set_val(self, value, message, **kwargs):
        if isinstance(value, float): # if value is float, round to 2 or x decimals
            if kwargs: # if kwargs is not empty
                value = round(value, kwargs['decimals']) # round value to kwargs['decimals'] decimals
            else: # otherwise, round to 2 decimals
                value = round(value, 2)
        message = message + str(value) # add value to message
        #print("send_set_val -", message) # print message for debugging
        self.send_set(message) # send message using send_message()

__all__ = ['SerialDeviceConnection']
