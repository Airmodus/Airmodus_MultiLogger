from PyQt5.QtWidgets import QTabWidget

from plots.device_plots import SinglePlot

from config import CPC

# TSI CPC widget
class TSIWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for TSI CPC
        self.plot_tab = SinglePlot(device_type=CPC)
        self.addTab(self.plot_tab, "TSI CPC plot")

__all__ = ['TSIWidget']
