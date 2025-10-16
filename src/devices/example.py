from PyQt5.QtWidgets import QTabWidget

from plots.device_plots import SinglePlot

from config import EXAMPLE_DEVICE

# Example device widget
class ExampleDeviceWidget(QTabWidget):
    def __init__(self, device_parameter, *args, **kwargs):
        super().__init__()
        self.device_parameter = device_parameter # store device parameter tree reference
        self.name = device_parameter.name() # store device name
        # create plot widget for CO2
        self.plot_tab = SinglePlot(device_type=EXAMPLE_DEVICE)
        self.addTab(self.plot_tab, "Example device plot")

__all__ = ['ExampleDeviceWidget']
