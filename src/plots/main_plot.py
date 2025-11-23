from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel, QComboBox, QHBoxLayout
from PyQt5.QtCore import Qt
from pyqtgraph import GraphicsLayoutWidget, DateAxisItem, AxisItem, ViewBox, LegendItem
from config import CPC, PSM, ELECTROMETER, CO2_SENSOR, RHTP, AFM, EDILUTER, EXAMPLE_DEVICE, PSM2, TSI_CPC

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

        # Create checkbox container (top-left overlay)
        # First create the scroll area as the parent
        from PyQt5.QtWidgets import QScrollArea, QSizePolicy
        self.checkbox_scroll_area = QScrollArea(self.graphics_widget)
        self.checkbox_scroll_area.setWidgetResizable(True)
        self.checkbox_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.checkbox_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.checkbox_scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.checkbox_scroll_area.setMaximumHeight(1200)  # Prevent covering entire plot
        self.checkbox_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: rgba(60, 60, 60, 150);
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(120, 120, 120, 200);
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: rgba(150, 150, 150, 220);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Create the checkbox widget inside the scroll area
        self.checkbox_widget = QWidget()
        self.checkbox_widget.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 180);
                border-radius: 5px;
                padding: 5px;
            }
            QCheckBox {
                color: white;
                spacing: 5px;
                font-size: 12pt;
                min-height: 24px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 12pt;
                padding-bottom: 5px;
            }
        """)
        checkbox_layout = QVBoxLayout(self.checkbox_widget)
        checkbox_layout.setContentsMargins(10, 10, 10, 10)
        checkbox_layout.setSpacing(6)

        # Add header label
        header = QLabel("Show Devices:")
        checkbox_layout.addWidget(header)

        # Dictionary to store device checkboxes {dev_id: checkbox}
        self.device_checkboxes = {}

        # Set the checkbox widget as the scroll area's widget
        self.checkbox_scroll_area.setWidget(self.checkbox_widget)

        # Position scroll area in top-left
        self.checkbox_scroll_area.move(10, 10)
        self.checkbox_scroll_area.show()

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

        # Example device viewbox
        self.viewboxes[EXAMPLE_DEVICE] = ViewBox() # create viewbox
        self.plot.scene().addItem(self.viewboxes[EXAMPLE_DEVICE]) # add viewbox to scene
        self.viewboxes[EXAMPLE_DEVICE].setXLink(self.plot) # link x axis of viewbox to x axis of plot
        # Example device axis
        self.axes[EXAMPLE_DEVICE] = AxisItem('right') # create axis
        self.plot.layout.addItem(self.axes[EXAMPLE_DEVICE], 2, 9) # add axis to plot
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
        if device_type == PSM2:
            axis = self.axes[PSM]
        elif device_type == TSI_CPC:
            axis = self.axes[CPC]
        else:
            axis = self.axes[device_type]
        if show:
            axis.show() # show axis
        else:
            axis.hide() # hide axis
    
    # change rhtp axis label according to value type
    # None, "RH", "T", "P"
    def change_rhtp_axis(self, value):
        # TODO: only change axis if value differs from current axis
        if value == None:
            self.axes[RHTP].setLabel('RHTP', units=None, color='w')
            self.axes[RHTP].hide() # hide axis
        else:
            if value == "RH":
                self.axes[RHTP].setLabel('RHTP RH', units='%', color='w')
            elif value == "T":
                self.axes[RHTP].setLabel('RHTP T', units='°C', color='w')
            elif value == "P":
                self.axes[RHTP].setLabel('RHTP P', units='Pa', color='w')
            self.axes[RHTP].show() # show axis
        # set axis style
        self.set_axis_style(self.axes[RHTP], 'w')
    
    def change_afm_axis(self, value):
        if value == None:
            self.axes[AFM].setLabel('AFM', units=None, color='w')
            self.axes[AFM].hide() # hide axis
        else:
            if value == "Flow":
                self.axes[AFM].setLabel('AFM flow', units='lpm', color='w')
            elif value == "Standard flow":
                self.axes[AFM].setLabel('AFM standard flow', units='slpm', color='w')
            elif value == "RH":
                self.axes[AFM].setLabel('AFM RH', units='%', color='w')
            elif value == "T":
                self.axes[AFM].setLabel('AFM T', units='°C', color='w')
            elif value == "P":
                self.axes[AFM].setLabel('AFM P', units='Pa', color='w')
            self.axes[AFM].show() # show axis
        # set axis style
        self.set_axis_style(self.axes[AFM], 'w')

    def add_device_checkbox(self, dev_id, device_name, device_param, device_widget=None):
        """Add a checkbox or dropdown for a device to control its visibility on the main plot."""
        if dev_id in self.device_checkboxes:
            return  # Already exists

        # Get current "Plot to main" value and parameter
        plot_to_main = device_param.child('Plot to main').value()
        plot_to_main_param = device_param.child('Plot to main')

        # Check if this is a list-type parameter (has dropdown options)
        # Use type() method instead of opts.get('type')
        is_list_param = (plot_to_main_param.type() == 'list')

        layout = self.checkbox_widget.layout()

        if is_list_param:
            # For devices with multiple plot options (RHTP, AFM), create a dropdown
            values = plot_to_main_param.opts.get('values', [])

            # Create horizontal layout for device control
            device_row = QWidget()
            device_layout = QHBoxLayout(device_row)
            device_layout.setContentsMargins(0, 0, 0, 0)
            device_layout.setSpacing(5)

            # Add label
            label = QLabel(device_name + ":")
            label.setStyleSheet("color: white; font-size: 12pt;")
            device_layout.addWidget(label)

            # Create dropdown
            dropdown = QComboBox()
            dropdown.setStyleSheet("""
                QComboBox {
                    background-color: #3a3a3a;
                    color: white;
                    border: 1px solid #555;
                    padding: 4px 8px;
                    min-width: 100px;
                    min-height: 24px;
                    font-size: 12pt;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 6px solid white;
                    margin-right: 5px;
                }
                QComboBox QAbstractItemView {
                    background-color: #3a3a3a;
                    color: white;
                    selection-background-color: #4a4a4a;
                    font-size: 12pt;
                }
            """)

            # Add "None" option first, then other values
            dropdown.addItem("None", None)
            for value in values:
                if value is not None:
                    dropdown.addItem(str(value), value)

            # Set current value
            if plot_to_main is None:
                dropdown.setCurrentIndex(0)
            else:
                index = dropdown.findData(plot_to_main)
                if index >= 0:
                    dropdown.setCurrentIndex(index)

            # Connect to parameter update
            def on_dropdown_changed(index):
                selected_value = dropdown.itemData(index)
                plot_to_main_param.setValue(selected_value)

            dropdown.currentIndexChanged.connect(on_dropdown_changed)
            device_layout.addWidget(dropdown)

            # Add to main layout
            layout.addWidget(device_row)

            # Store reference (store the container widget)
            self.device_checkboxes[dev_id] = device_row

        else:
            # For boolean devices, create a simple checkbox
            checkbox = QCheckBox(device_name)
            checkbox.setChecked(bool(plot_to_main))

            # Connect to parameter update
            def on_checkbox_changed(state):
                checked = (state == Qt.Checked)
                plot_to_main_param.setValue(checked)

            checkbox.stateChanged.connect(on_checkbox_changed)
            layout.addWidget(checkbox)

            # Store reference
            self.device_checkboxes[dev_id] = checkbox

        # Adjust scroll area size to fit content
        self.checkbox_widget.adjustSize()
        # Update scroll area size based on content
        content_size = self.checkbox_widget.sizeHint()
        # Set scroll area width to content width, let height be managed by max height
        scroll_width = content_size.width() + 15  # Add space for potential scrollbar
        scroll_height = min(content_size.height(), 1200)  # Respect max height
        self.checkbox_scroll_area.resize(scroll_width, scroll_height)

    def remove_device_checkbox(self, dev_id):
        """Remove a device checkbox when device is removed."""
        if dev_id in self.device_checkboxes:
            widget = self.device_checkboxes[dev_id]
            layout = self.checkbox_widget.layout()

            # Disconnect all signals before deletion to prevent RuntimeError
            if isinstance(widget, QCheckBox):
                try:
                    widget.stateChanged.disconnect()
                except:
                    pass
            elif isinstance(widget, QWidget):
                # For dropdown containers, disconnect the combobox
                dropdown = widget.findChild(QComboBox)
                if dropdown:
                    try:
                        dropdown.currentIndexChanged.disconnect()
                    except:
                        pass

            layout.removeWidget(widget)
            widget.deleteLater()
            del self.device_checkboxes[dev_id]

            # Adjust scroll area size after removal
            self.checkbox_widget.adjustSize()
            content_size = self.checkbox_widget.sizeHint()
            scroll_width = content_size.width() + 15
            scroll_height = min(content_size.height(), 1200)
            self.checkbox_scroll_area.resize(scroll_width, scroll_height)

    def update_device_checkbox_name(self, dev_id, new_name):
        """Update the display name of a device checkbox or dropdown."""
        if dev_id in self.device_checkboxes:
            widget = self.device_checkboxes[dev_id]
            # Check if it's a checkbox or a dropdown widget
            if isinstance(widget, QCheckBox):
                widget.setText(new_name)
            elif isinstance(widget, QWidget):
                # It's a dropdown container, find the label
                label = widget.findChild(QLabel)
                if label:
                    label.setText(new_name + ":")
            self.checkbox_widget.adjustSize()

__all__ = ['MainPlot']
