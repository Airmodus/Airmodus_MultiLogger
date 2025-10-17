from PyQt5.QtGui import QFont
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, PlotCurveItem, PlotItem
from config import RHTP, CPC, PSM, CO2_SENSOR, EDILUTER, AFM, EXAMPLE_DEVICE

# triple plot widget containing three plots
class TriplePlot(GraphicsLayoutWidget):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()

        if device_type == RHTP:
            value_names = ["RH", "T", "P"]
            unit_names = ["%", "°C", "Pa"]
            colors = [(100,188,255), (255,100,100), (255, 255, 100)]
        else: # other devices
            value_names = ["val1", "val2", "val3"]
            unit_names = ["unit1", "unit2", "unit3"]
            colors = [(255,255,255), (255,100,100), (100,188,255)]
        
        # create plot by adding it to widget
        self.plot = self.addPlot()

        # time axis
        self.plot.setAxisItems({'bottom':DateAxisItem()}) # set time axis to bottom
        self.plot.setLabel('bottom', "Time") # set time axis label
        self.axis_time = self.plot.getAxis('bottom') # store time axis to variable
        self.set_axis_style(self.axis_time, 'w') # set axis style

        # viewbox 1
        self.viewbox1 = self.plot.getViewBox() # store default viewbox to variable
        # axis 1
        self.axis1 = self.plot.getAxis('left') # store left axis to variable
        self.axis1.setLabel(value_names[0], units=unit_names[0], color=colors[0]) # set label
        self.set_axis_style(self.axis1, colors[0]) # set axis style
        # curve 1
        self.curve1 = PlotCurveItem(pen=colors[0], connect="finite") # create curve 1
        self.viewbox1.addItem(self.curve1) # add curve 1 to viewbox 1

        # viewbox 2
        self.viewbox2 = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewbox2) # add viewbox to scene
        self.viewbox2.setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # axis 2
        self.axis2 = AxisItem('right') # create second axis
        self.plot.layout.addItem(self.axis2, 2, 3) # add axis to plot
        self.axis2.setLabel(value_names[1], units=unit_names[1], color=colors[1]) # set label
        self.set_axis_style(self.axis2, colors[1]) # set axis style
        self.axis2.linkToView(self.viewbox2) # link axis to viewbox
        # curve 2
        self.curve2 = PlotCurveItem(pen=colors[1], connect="finite") # create curve 2
        self.viewbox2.addItem(self.curve2) # add curve 2 to viewbox 2

        # viewbox 3
        self.viewbox3 = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewbox3) # add viewbox to scene
        self.viewbox3.setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # axis 3
        self.axis3 = AxisItem('right') # create third axis
        self.plot.layout.addItem(self.axis3, 2, 4) # add axis to plot
        self.axis3.setLabel(value_names[2], units=unit_names[2], color=colors[2]) # set label
        self.set_axis_style(self.axis3, colors[2]) # set axis style
        self.axis3.linkToView(self.viewbox3) # link axis to viewbox
        # curve 3
        self.curve3 = PlotCurveItem(pen=colors[2], connect="finite") # create curve 3
        self.viewbox3.addItem(self.curve3) # add curve 3 to viewbox 3

        # create list of viewboxes
        self.viewboxes = [self.viewbox1, self.viewbox2, self.viewbox3]

        # connect viewbox resize event to updateViews function
        self.plot.vb.sigResized.connect(self.updateViews)
        # call updateViews function to set viewboxes to same size
        self.updateViews()
        
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)
    
    # handle view resizing
    # called when plot widget (or window) is resized
    # source: https://stackoverflow.com/questions/42931474/how-can-i-have-multiple-left-axisitems-with-the-same-alignment-position-using-py
    def updateViews(self):
        # set viewbox geometry to plot geometry
        for viewbox in self.viewboxes[1:]: # exclude viewbox 1
            viewbox.setGeometry(self.plot.vb.sceneBoundingRect())
            # update linked axes
            viewbox.linkedViewChanged(self.plot.vb, viewbox.XAxis)

    def set_axis_style(self, axis, color):
        axis.setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
        axis.setPen(color)
        axis.setTextPen(color)
        axis.label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font
        axis.enableAutoSIPrefix(enable=False) # disable auto SI prefix


class AFMPlot(GraphicsLayoutWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        # define value names, units and colors
        value_names = ["Flow", "Standard flow", "RH", "T", "P"]
        unit_names = ["lpm", "slpm", "%", "°C", "Pa"]
        colors = [(255,255,255), (255,100,255), (100,188,255), (255, 100, 100), (255, 255, 100)]

        # create plot item and hide its default axes
        self.plot = PlotItem()
        self.plot.hideAxis('left')
        self.plot.hideAxis('bottom')
        # add plot to widget column 2, leave space for left axes
        self.addItem(self.plot, row=0, col=2)

        # create viewboxes for each axis
        self.viewboxes = []
        # store default viewbox
        self.viewboxes.append(self.plot.getViewBox())
        # create 4 additional viewboxes
        for i in range(4):
            viewbox = ViewBox() # create viewbox
            self.plot.scene().addItem(viewbox) # add viewbox to scene
            viewbox.setXLink(self.plot) # link x axis of viewbox to x axis of plot
            self.viewboxes.append(viewbox) # store viewbox to list
        
        # create axes for each viewbox
        self.axes = []
        for i in range(2):
            axis = AxisItem('left') # create left axis
            self.axes.append(axis) # store axis to list
            self.addItem(axis, row=0, col=i) # add axis to widget
        for i in range(3):
            axis = AxisItem('right') # create right axis
            self.axes.append(axis) # store axis to list
            self.addItem(axis, row=0, col=i+3) # add axis to widget, skip left axes and plot
        
        # link axes to viewboxes
        for i in range(5):
            self.axes[i].linkToView(self.viewboxes[i])
        
        # set axis labels and styles
        for i in range(5):
            # set label
            self.axes[i].setLabel(value_names[i], units=unit_names[i], color=colors[i])
            # set style
            self.axes[i].setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
            self.axes[i].setPen(colors[i])
            self.axes[i].setTextPen(colors[i])
            self.axes[i].label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font
            self.axes[i].enableAutoSIPrefix(enable=False) # disable auto SI prefix
        
        # create bottom time axis
        self.axis_time = DateAxisItem('bottom')
        # link time axis to viewbox
        self.axis_time.linkToView(self.viewboxes[0])
        # set botton axis label and style
        self.axis_time.setLabel("Time")
        self.axis_time.setStyle(tickFont=QFont("Arial", 12, QFont.Normal), tickLength=-20)
        self.axis_time.setPen('w')
        self.axis_time.setTextPen('w')
        self.axis_time.label.setFont(QFont("Arial", 12, QFont.Normal)) # change axis label font
        self.axis_time.enableAutoSIPrefix(enable=False) # disable auto SI prefix

        # add bottom time axis to widget, same column as plot but on next row
        self.addItem(self.axis_time, row=1, col=2)

        # create curves for each viewbox
        self.curves = []
        for i in range(5):
            curve = PlotCurveItem(pen=colors[i], connect="finite") # create curve
            self.curves.append(curve) # store curve to list
            self.viewboxes[i].addItem(curve) # add curve to viewbox
        
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)
        
        # connect viewbox resize event to updateViews function
        self.plot.vb.sigResized.connect(self.updateViews)
        # call updateViews function to set viewboxes to same size
        self.updateViews()
    
    def updateViews(self):
        # set viewbox geometry to plot geometry
        for viewbox in self.viewboxes[1:]: # exclude first viewbox
            viewbox.setGeometry(self.plot.vb.sceneBoundingRect())
            # update linked axes
            viewbox.linkedViewChanged(self.plot.vb, viewbox.XAxis)

class ElectrometerPlot(GraphicsLayoutWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()

        # list for storing references to plots
        self.plots = []
        # create plots and curves
        # Voltage 1
        self.plot1 = self.addPlot()
        self.curve1 = self.plot1.plot(pen="g", connect="finite")
        self.plots.append(self.plot1)
        self.nextRow()
        # Voltage 2
        self.plot2 = self.addPlot()
        self.curve2 = self.plot2.plot(pen="r", connect="finite")
        self.plots.append(self.plot2)
        self.nextRow()
        # Voltage 3
        self.plot3 = self.addPlot()
        self.curve3 = self.plot3.plot(pen="b", connect="finite")
        self.plots.append(self.plot3)
        # set up plots
        for i in range(3):
            label = "Voltage " + str(i+1)
            self.plots[i].setLabel('left', label, units='V') # set y-axis label
            self.plots[i].setLabel('bottom', "Time") # set time axis label
            self.plots[i].setAxisItems({'bottom':DateAxisItem()})
            #self.plots[i].getAxis('left').enableAutoSIPrefix(enable=False) # disable auto SI prefix
            self.plots[i].getAxis('bottom').enableAutoSIPrefix(enable=False) # disable auto SI prefix
            self.plots[i].showGrid(x=True, y=True) # show grid by default
            self.plots[i].setDownsampling(mode='peak')
            self.plots[i].setClipToView(True)

# single plot widget containing plot
class SinglePlot(GraphicsLayoutWidget):
    def __init__(self, device_type, *args, **kwargs):
        super().__init__()

        # create plot and curve
        self.plot = self.addPlot() # create plot by adding it to widget
        self.curve = self.plot.plot(pen="w", connect="finite") # create plot curve

        # plot settings
        self.plot.setAxisItems({'bottom':DateAxisItem()}) # set time axis to bottom
        self.plot.getAxis('bottom').enableAutoSIPrefix(enable=False) # disable auto SI prefix 
        self.plot.setLabel('bottom', "Time") # set time axis label
        self.plot.showGrid(x=True, y=True) # show grid by default
        self.plot.getAxis('left').enableAutoSIPrefix(enable=False) # disable auto SI prefix
        # use automatic downsampling and clipping to reduce the drawing load
        self.plot.setDownsampling(mode='peak')
        self.plot.setClipToView(True)

        # set y-axis label and units based on device type
        if device_type == CPC:
            self.plot.setLabel('left', "Concentration", units='#/cc')
        elif device_type == PSM:
            self.plot.setLabel('left', "Saturator flow", units='lpm')
        elif device_type == CO2_SENSOR:
            self.plot.setLabel('left', "CO2", units='ppm')
        elif device_type == EDILUTER:
            self.plot.setLabel('left', "eDiluter temperature", units='°C')
        elif device_type == AFM:
            self.plot.setLabel('left', "Flow", units='lpm')
        elif device_type == EXAMPLE_DEVICE:
            self.plot.setLabel('left', "Example device", units='units')
        
        self.viewbox = self.plot.getViewBox() # store viewbox to variable

__all__ = ['TriplePlot', 'AFMPlot', 'ElectrometerPlot', 'SinglePlot']
