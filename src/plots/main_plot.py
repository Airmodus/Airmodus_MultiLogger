from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, LegendItem
from config import CPC, PSM, ELECTROMETER, CO2_SENSOR, RHTP, AFM, EDILUTER, EXAMPLE_DEVICE, AFC, TSI_CPC


# main plot widget
class MainPlot(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        # Create main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create graphics layout widget for the plot
        self.graphics_widget = GraphicsLayoutWidget()

        # create plot by adding it to widget
        self.plot = self.graphics_widget.addPlot()
        # create legend
        self.legend = LegendItem(offset=(70,20), labelTextColor='w', labelTextSize='11pt')
        self.legend.setParentItem(self.plot.graphicsItem())

        # Add graphics widget to main layout
        layout.addWidget(self.graphics_widget)
        # create dictionaries for viewboxes and axes, use device type as key
        self.viewboxes = {}
        self.axes = {}

        # time axis
        self.plot.setAxisItems({'bottom':DateAxisItem()}) # set time axis to bottom
        self.plot.setLabel('bottom', "Time") # set time axis label
        self.axis_time = self.plot.getAxis('bottom') # store time axis to variable
        self.set_axis_style(self.axis_time, 'w') # set axis style
        self.axis_time.enableAutoSIPrefix(enable=False) # disable auto SI prefix

        # CPC viewbox
        self.viewboxes[CPC] = self.plot.getViewBox() # store default viewbox to dictionary
        # CPC axis
        self.axes[CPC] = self.plot.getAxis('left') # store left axis to dictionary
        self.axes[CPC].setLabel('CPC concentration', units='#/cc', color='w') # set label
        self.set_axis_style(self.axes[CPC], 'w') # set axis style

        # PSM viewbox # TODO create function for viewbox and axis creation
        self.viewboxes[PSM] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[PSM]) # add viewbox to scene
        self.viewboxes[PSM].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # PSM axis
        self.axes[PSM] = AxisItem('right') # create second axis
        self.plot.layout.addItem(self.axes[PSM], 2, 3) # add axis to plot
        self.axes[PSM].setLabel('PSM saturator flow rate', units='lpm', color='w') # set label
        self.set_axis_style(self.axes[PSM], 'w') # set axis style
        self.axes[PSM].linkToView(self.viewboxes[PSM]) # link axis to viewbox

        # ELECTROMETER viewbox
        self.viewboxes[ELECTROMETER] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[ELECTROMETER]) # add viewbox to scene
        self.viewboxes[ELECTROMETER].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # ELECTROMETER axis
        self.axes[ELECTROMETER] = AxisItem('right') # create third axis
        self.plot.layout.addItem(self.axes[ELECTROMETER], 2, 4) # add axis to plot
        self.axes[ELECTROMETER].setLabel('ELECTROMETER voltage 2', units='V', color='w') # set label
        self.set_axis_style(self.axes[ELECTROMETER], 'w') # set axis style
        self.axes[ELECTROMETER].linkToView(self.viewboxes[ELECTROMETER]) # link axis to viewbox

        # CO2 viewbox
        self.viewboxes[CO2_SENSOR] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[CO2_SENSOR]) # add viewbox to scene
        self.viewboxes[CO2_SENSOR].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # CO2 axis
        self.axes[CO2_SENSOR] = AxisItem('right') # create fourth axis
        self.plot.layout.addItem(self.axes[CO2_SENSOR], 2, 5) # add axis to plot
        self.axes[CO2_SENSOR].setLabel('CO2 concentration', units='ppm', color='w') # set label
        self.set_axis_style(self.axes[CO2_SENSOR], 'w') # set axis style
        self.axes[CO2_SENSOR].linkToView(self.viewboxes[CO2_SENSOR]) # link axis to viewbox

        # RHTP viewbox
        self.viewboxes[RHTP] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[RHTP]) # add viewbox to scene
        self.viewboxes[RHTP].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # RHTP axis
        self.axes[RHTP] = AxisItem('right') # create fifth axis
        self.plot.layout.addItem(self.axes[RHTP], 2, 6) # add axis to plot
        self.axes[RHTP].setLabel('RHTP', color='w') # set label
        self.set_axis_style(self.axes[RHTP], 'w') # set axis style
        self.axes[RHTP].linkToView(self.viewboxes[RHTP]) # link axis to viewbox

        # AFM viewbox
        self.viewboxes[AFM] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[AFM]) # add viewbox to scene
        self.viewboxes[AFM].setXLink(self.plot)
        # AFM axis
        self.axes[AFM] = AxisItem('right') # create sixth axis
        self.plot.layout.addItem(self.axes[AFM], 2, 7) # add axis to plot
        self.axes[AFM].setLabel('AFM', color='w')
        self.set_axis_style(self.axes[AFM], 'w')
        self.axes[AFM].linkToView(self.viewboxes[AFM])

        # eDiluter viewbox
        self.viewboxes[EDILUTER] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[EDILUTER]) # add viewbox to scene
        self.viewboxes[EDILUTER].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # eDiluter axis
        self.axes[EDILUTER] = AxisItem('right') # create axis
        self.plot.layout.addItem(self.axes[EDILUTER], 2, 8) # add axis to plot
        self.axes[EDILUTER].setLabel('eDiluter temperature', units='°C', color='w') # set label
        self.set_axis_style(self.axes[EDILUTER], 'w') # set axis style
        self.axes[EDILUTER].linkToView(self.viewboxes[EDILUTER]) # link axis to viewbox
        
        # AFC viewbox
        self.viewboxes[AFC] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[AFC]) # add viewbox to scene
        self.viewboxes[AFC].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # AFC axis
        self.axes[AFC] = AxisItem('right') # create axis
        self.plot.layout.addItem(self.axes[AFC], 2, 9) # add axis to plot
        self.axes[AFC].setLabel('AFC flow', units='slm', color='w') # set label
        self.set_axis_style(self.axes[AFC], 'w') # set axis style
        self.axes[AFC].linkToView(self.viewboxes[AFC]) # link axis to viewbox

        # Example device viewbox
        self.viewboxes[EXAMPLE_DEVICE] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[EXAMPLE_DEVICE]) # add viewbox to scene
        self.viewboxes[EXAMPLE_DEVICE].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # Example device axis
        self.axes[EXAMPLE_DEVICE] = AxisItem('right') # create axis
        self.plot.layout.addItem(self.axes[EXAMPLE_DEVICE], 2, 10) # add axis to plot
        self.axes[EXAMPLE_DEVICE].setLabel('Example device', units='units', color='w') # set label
        self.set_axis_style(self.axes[EXAMPLE_DEVICE], 'w') # set axis style
        self.axes[EXAMPLE_DEVICE].linkToView(self.viewboxes[EXAMPLE_DEVICE]) # link axis to viewbox
        
        # connect viewbox resize event to updateViews function
        self.plot.vb.sigResized.connect(self.updateViews)
        # call updateViews function to set viewboxes to same size
        self.updateViews()

        # connect plot's auto range button to set_auto_range function
        self.plot.autoBtn.clicked.connect(self.set_auto_range)

        # hide axes and disable SI scaling by default
        for key in self.axes:
            self.axes[key].hide()
            self.axes[key].enableAutoSIPrefix(enable=False) # disable auto SI prefix
        
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)
        # TODO does this affect all viewboxes?
    
    # handle view resizing
    # called when plot widget (or window) is resized
    # source: https://stackoverflow.com/questions/42931474/how-can-i-have-multiple-left-axisitems-with-the-same-alignment-position-using-py
    def updateViews(self):
        # set viewbox geometry to plot geometry
        for viewbox in self.viewboxes.values():
            # exclude CPC viewbox
            if viewbox != self.viewboxes[CPC]:
                viewbox.setGeometry(self.plot.vb.sceneBoundingRect())
                # update linked axes
                viewbox.linkedViewChanged(self.plot.vb, viewbox.XAxis)
    
    # set auto range on for all viewboxes
    def set_auto_range(self):
        for viewbox in self.viewboxes.values():
            viewbox.enableAutoRange()
    
    def set_axis_style(self, axis, color):
        axis.setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
        axis.setPen(color)
        axis.setTextPen(color)
        axis.label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font

    def show_hide_axis(self, device_type, show):
        # TSI CPC uses same axis as Airmodus CPC
        if device_type == TSI_CPC:
            axis = self.axes[CPC]
        else:
            axis = self.axes[device_type]
        if show:
            axis.show() # show axis
        else:
            axis.hide() # hide axis

__all__ = ['MainPlot']
