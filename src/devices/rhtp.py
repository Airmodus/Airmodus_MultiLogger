from PyQt5.QtWidgets import QTabWidget

from plots.device_plots import TriplePlot

from config import RHTP

# RHTP widget
class RHTPWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for RHTP
        self.plot_tab = TriplePlot(device_type=RHTP)
        self.addTab(self.plot_tab, "RHTP plot")

__all__ = ['RHTPWidget']
