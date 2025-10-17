from PyQt5.QtWidgets import QTabWidget

from plots.device_plots import SinglePlot

from config import CO2_SENSOR

# CO2 widget
class CO2Widget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for CO2
        self.plot_tab = SinglePlot(device_type=CO2_SENSOR)
        self.addTab(self.plot_tab, "CO2 plot")

__all__ = ['CO2Widget']
