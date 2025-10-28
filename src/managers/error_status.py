# managers/error_status.py
from PyQt5.QtGui import QIcon
from config import CPC, PSM, PSM2, EXAMPLE_DEVICE
import logging
import traceback

class ErrorStatus:
    def __init__(self, data_holder, params, device_tabs):
        self.data_holder = data_holder
        self.params = params
        self.device_tabs = device_tabs  # Reference to MainWindow.device_tabs for icon updates

    def update_error_icons(self):
        """Updates tab error icons according to data_holder.device_errors dictionary."""
        # TODO add comparison list of previous values to avoid unnecessary icon updates
        # go through each device
        for dev in self.params.child('Device settings').children():
            try:
                # device id
                device_id = dev.child('DevID').value()
                # error status from data_holder.device_errors
                error = self.data_holder.device_errors[device_id]
                # device type
                device_type = dev.child('Device type').value()
                # device widget
                device_widget = self.data_holder.device_widgets[device_id]
                # device widget tab index
                tab_index = self.device_tabs.indexOf(device_widget)
                # connected status
                connected = dev.child('Connected').value() # True or False
                # if connected is False
                if not connected and device_type != EXAMPLE_DEVICE: # exclude Example device
                    # set disconnected icon
                    self.device_tabs.setTabIcon(tab_index, self.data_holder.disconnected_icon)
                    # set general error status flag
                    self.data_holder.error_status = 1
                # if error is True
                elif error:
                    # change tab icon to error icon
                    self.device_tabs.setTabIcon(tab_index, self.data_holder.error_icon)
                    # change status tab icon to error icon if device is CPC or PSM
                    if device_type in [CPC, PSM, PSM2]:
                        status_tab_index = device_widget.indexOf(device_widget.status_tab)
                        device_widget.setTabIcon(status_tab_index, self.data_holder.error_icon)
                # if connected and no error
                else:
                    # remove error icon with empty QIcon object
                    self.device_tabs.setTabIcon(tab_index, QIcon())
                    # remove status tab error icon if device is CPC or PSM
                    if device_type in [CPC, PSM, PSM2]:
                        status_tab_index = device_widget.indexOf(device_widget.status_tab)
                        device_widget.setTabIcon(status_tab_index, QIcon())
               
                # if device is PSM, check co flow status
                if device_type == PSM:
                    # if co flow is red (error)
                    if device_widget.set_tab.set_co_flow.error == True:
                        # change tab icon to error icon
                        self.device_tabs.setTabIcon(tab_index, self.data_holder.error_icon)
                        # change set tab icon to error icon
                        set_tab_index = device_widget.indexOf(device_widget.set_tab)
                        device_widget.setTabIcon(set_tab_index, self.data_holder.error_icon)
                    else:
                        # remove error icon with empty QIcon object
                        set_tab_index = device_widget.indexOf(device_widget.set_tab)
                        device_widget.setTabIcon(set_tab_index, QIcon())
            except Exception as e:
                print(traceback.format_exc())
                logging.exception(e)

    def set_status_lights(self):
        """Set error and saving lights on status lights widget."""
        self.data_holder.status_lights.set_error_light(self.data_holder.error_status)
        self.data_holder.status_lights.set_saving_light(self.data_holder.saving_status)
