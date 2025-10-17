from PyQt5.QtWidgets import (QTabWidget, QVBoxLayout, QHBoxLayout, QPushButton,
QGridLayout, QWidget)

from plots.device_plots import SinglePlot

from widgets import StartButton, IndicatorWidget, CommandWidget
from config import EDILUTER

# eDiluter widget
class eDiluterWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        self.current_mode = None # used for storing current mode
        # create set tab for eDiluter
        self.set_tab = eDiluterSetTab()
        self.addTab(self.set_tab, "Set")
        # create status tab for eDiluter
        self.status_tab = eDiluterStatusTab()
        self.addTab(self.status_tab, "Status")
        # create plot widget for eDiluter
        self.plot_tab = SinglePlot(device_type=EDILUTER)
        self.addTab(self.plot_tab, "eDiluter plot")
        # create dictionary with mode names and corresponding widgets
        self.mode_dict = {"INIT": self.set_tab.init, "WARMUP": self.set_tab.warmup,
                          "STANDBY": self.set_tab.standby, "MEASUREMENT": self.set_tab.measurement}
    
    # update all data values in status tab and set tab
    # current list: Status, P1, P2, T1, T2, T3, T4, T5, T6, DF1, DF2, DFTot
    def update_values(self, current_list):
        # update temperature values
        self.status_tab.t1.change_value(str(current_list[3]) + " °C")
        self.status_tab.t2.change_value(str(current_list[4]) + " °C")
        self.status_tab.t3.change_value(str(current_list[5]) + " °C")
        self.status_tab.t4.change_value(str(current_list[6]) + " °C")
        self.status_tab.t5.change_value(str(current_list[7]) + " °C")
        self.status_tab.t6.change_value(str(current_list[8]) + " °C")
        # update pressure values
        self.status_tab.p1.change_value(str(current_list[1]) + " mbar")
        self.status_tab.p2.change_value(str(current_list[2]) + " mbar")
        # update dilution factor values
        self.set_tab.df_1.indicator.change_value(str(current_list[9]))
        self.set_tab.df_2.indicator.change_value(str(current_list[10]))
        self.set_tab.df_tot.change_value(str(current_list[11])) # total DF in set tab
        self.status_tab.df_tot.change_value(str(current_list[11])) # total DF in status tab
        # change color of active mode if it differs from current mode
        if current_list[0] != self.current_mode:
            # change color of all mode buttons to default
            for mode in self.mode_dict:
                self.mode_dict[mode].change_color(0)
            # if current mode is not nan
            if str(current_list[0]) != "nan":
                # change color of active mode button
                self.mode_dict[current_list[0]].change_color(1)
                self.current_mode = current_list[0] # update current mode


class eDiluterSetTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QVBoxLayout() # create vertical layout

        # horizontal layout for mode settings
        # INIT, WARMUP, STANDBY, MEASUREMENT
        mode_layout = QHBoxLayout()
        self.init = StartButton("Init")
        mode_layout.addWidget(self.init)
        self.warmup = StartButton("Warmup")
        mode_layout.addWidget(self.warmup)
        self.standby = StartButton("Standby")
        mode_layout.addWidget(self.standby)
        self.measurement = StartButton("Measurement")
        mode_layout.addWidget(self.measurement)
        layout.addLayout(mode_layout) # add mode_layout to main vertical layout

        # horizontal layout for dilution factor settings
        df_layout = QHBoxLayout()
        self.df_1 = DFSetWidget("Dilution factor 1")
        df_layout.addWidget(self.df_1)
        self.df_2 = DFSetWidget("Dilution factor 2")
        df_layout.addWidget(self.df_2)
        self.df_tot = IndicatorWidget("Total dilution factor")
        df_layout.addWidget(self.df_tot)
        layout.addLayout(df_layout) # add df_layout to main vertical layout

        # add line edit for command input
        self.command_widget = CommandWidget("eDiluter")
        layout.addWidget(self.command_widget)

        self.setLayout(layout) # add layout to widget


class eDiluterStatusTab(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        layout = QGridLayout() # create layout

        # temperature indicators (unit = °C)
        self.t1 = IndicatorWidget("Dilution air temperature") # T1
        layout.addWidget(self.t1, 0, 0)
        self.t2 = IndicatorWidget("Ext 1 temperature") # T2
        layout.addWidget(self.t2, 1, 0)
        self.t3 = IndicatorWidget("Ext 2 temperature") # T3
        layout.addWidget(self.t3, 2, 0)
        self.t6 = IndicatorWidget("Internal temperature") # T6
        layout.addWidget(self.t6, 0, 1)
        self.t4 = IndicatorWidget("Aux 1 temperature") # T4
        layout.addWidget(self.t4, 1, 1)
        self.t5 = IndicatorWidget("Aux 2 temperature") # T5
        layout.addWidget(self.t5, 2, 1)

        # pressure indicators (unit = mbar)
        self.p1 = IndicatorWidget("Inlet pressure") # P1
        layout.addWidget(self.p1, 0, 2)
        self.p2 = IndicatorWidget("Ambient pressure") # P2
        layout.addWidget(self.p2, 1, 2)

        # dilution factor indicator
        self.df_tot = IndicatorWidget("Total dilution factor") # DFTot
        layout.addWidget(self.df_tot, 2, 2)
        
        self.setLayout(layout) # set layout


class DFSetWidget(QWidget):
    def __init__(self, name, *args, **kwargs):
        super().__init__()
        layout = QHBoxLayout() # create horizontal layout

        # create previous button
        self.prev_button = QPushButton("<", objectName="button_widget")
        # create indicator widget for displaying name and value
        self.indicator = IndicatorWidget(name)
        # create next button
        self.next_button = QPushButton(">", objectName="button_widget")

        # add widgets to layout
        layout.addWidget(self.prev_button) # previous button
        layout.addWidget(self.indicator) # indicator widget
        layout.addWidget(self.next_button) # next button

        self.setLayout(layout) # add layout to widget


__all__ = ['eDiluterWidget']
