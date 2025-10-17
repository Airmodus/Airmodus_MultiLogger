from PyQt5.QtWidgets import QTabWidget

from plots.device_plots import AFMPlot

# AFM widget
class AFMWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for AFM
        self.plot_tab = AFMPlot()
        self.addTab(self.plot_tab, "AFM plot")

__all__ = ['AFMWidget']
