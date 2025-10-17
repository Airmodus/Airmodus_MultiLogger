from PyQt5.QtWidgets import QTabWidget

from plots.device_plots import ElectrometerPlot

# ELECTROMETER widget
class ElectrometerWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for Electrometer
        self.plot_tab = ElectrometerPlot()
        self.addTab(self.plot_tab, "Electrometer plot")

__all__ = ['ElectrometerWidget']
