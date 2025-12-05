"""
Concrete implementations of BaseDataWriter for each device type.

Each device has its own DataWriter class that defines how its data
should be written to files, including headers, file types, and
special cases like 10Hz logging or connected device handling.
"""

from config import CPC, PSM, PSM2
from devices.base_data_writer import BaseDataWriter


class CPCDataWriter(BaseDataWriter):
    """Data writer for Airmodus CPC devices."""

    def get_file_types(self):
        """CPC writes both .dat and .par files."""
        return ['dat', 'par']

    def get_dat_header(self):
        """Return CPC .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Concentration (#/cc),Dead time (µs),Number of pulses,Saturator T (C),Condenser T (C),Optics T (C),Cabin T (C),Inlet P (kPa),Critical orifice P (kPa),Nozzle P (kPa),Cabin P (kPa),Liquid level,Pulse ratio,Total CPC errors,System status error'

    def get_par_header(self):
        """Return CPC .par file header."""
        return 'YYYY.MM.DD hh:mm:ss,Averaging time (s),Nominal flow rate (lpm),Flow rate (lpm),Saturator T setpoint (C),Condenser T setpoint (C),Optics T setpoint (C),Autofill,OPC counter threshold voltage (mV),OPC counter threshold 2 voltage (mV),Water removal,Dead time correction,Drain,K-factor,Tau,Command input'

    def should_write_par(self, data_holder):
        """Check if .par file should be written."""
        dev_id = self.device.dev_id

        # Check device's par_updates flag
        if data_holder.par_updates.get(dev_id, 0) == 1:
            return True

        # Check if device has latest_command
        if hasattr(self.device, 'latest_command') and self.device.latest_command is not None:
            return True

        return False

    def get_par_data(self, data_holder, timestamp_str):
        """Return CPC settings data for .par file."""
        dev_id = self.device.dev_id
        settings = self.device.settings

        if not settings:
            return None

        # Get settings array
        settings_array = settings.to_array()
        data_str = ','.join(str(val) for val in settings_array)

        # Add command if present
        if self.device.latest_command is not None:
            data_str += ',' + self.device.latest_command
            self.device.latest_command = None

        return data_str

    def has_special_files(self):
        """Check if 10Hz logging is enabled."""
        return self.device.device_config.extra_params.get('10_hz', False)

    def write_special_files(self, file_path, timestamp_str, filenames_dict):
        """Write 10Hz data file for CPC."""
        dev_id = self.device.dev_id

        # Check if device has ten_hz_data attribute
        if not hasattr(self.device, 'ten_hz_data'):
            return

        # Get filename from dict
        if dev_id not in filenames_dict:
            return

        filename = file_path + filenames_dict[dev_id]

        # Write 10Hz data
        with open(filename, 'a', newline='\n', encoding='UTF-8') as file:
            file.write("\n")
            file.write(timestamp_str + ',')
            write_data = ','.join(str(val) for val in self.device.ten_hz_data)
            file.write(write_data)


class PSMDataWriter(BaseDataWriter):
    """Data writer for PSM and PSM 2.0 devices."""

    def get_file_types(self):
        """PSM writes both .dat and .par files."""
        return ['dat', 'par']

    def get_dat_header(self):
        """Return PSM .dat file header (different for PSM vs PSM2)."""
        if self.device.dev_type == PSM2:
            # PSM 2.0 includes vacuum flow
            return 'YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),Scan status,Vacuum flow (lpm),PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)'
        else:
            # PSM 1.0
            return 'YYYY.MM.DD hh:mm:ss,Concentration from PSM (1/cm3),Cut-off diameter (nm),Saturator flow rate (lpm),Excess flow rate (lpm),PSM saturator T (C),Growth tube T (C),Inlet T (C),Drainage T (C),Heater T (C),PSM cabin T (C),Absolute P (kPa),dP saturator line (kPa),dP Excess line (kPa),Critical orifice P (kPa),Scan status,PSM status value,PSM note value,CPC concentration (1/cm3),Dilution correction factor,CPC saturator T (C),CPC condenser T (C),CPC optics T (C),CPC cabin T (C),CPC critical orifice P (kPa),CPC nozzle P (kPa),CPC absolute P (kPa),CPC liquid level,OPC pulses,OPC pulse duration,CPC number of errors,CPC system status errors (hex),PSM system status errors (hex),PSM notes (hex)'

    def get_par_header(self):
        """Return PSM .par file header (different for PSM vs PSM2)."""
        if self.device.dev_type == PSM2:
            # PSM 2.0 has no CO flow
            return 'YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),amp,cen,sig,slope,intercept,modeInUse,CPC IDN,CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input'
        else:
            # PSM 1.0 includes CO flow
            return 'YYYY.MM.DD hh:mm:ss,Growth tube T setpoint (C),PSM saturator T setpoint (C),Inlet T setpoint (C),Heater T setpoint (C),Drainage T setpoint (C),PSM stored CPC flow rate (lpm),Inlet flow rate (lpm),CO flow rate (lpm),amp,cen,sig,slope,intercept,modeInUse,CPC IDN,CPC autofill,CPC drain,CPC water removal,CPC saturator T setpoint (C),CPC condenser T setpoint (C),CPC optics T setpoint (C),CPC inlet flow rate (lpm),CPC averaging time (s),Command input'

    def should_write_par(self, data_holder):
        """
        Check if .par file should be written.

        PSM writes .par when:
        1. par_updates flag is set for this device
        2. Device has a latest_command
        3. Connected CPC parameter changed
        4. Connected CPC has par_updates flag set
        """
        dev_id = self.device.dev_id

        # Check device's par_updates flag
        if data_holder.par_updates.get(dev_id, 0) == 1:
            return True

        # Check if device has latest_command
        if hasattr(self.device, 'latest_command') and self.device.latest_command is not None:
            return True

        # Check connected CPC changes
        if hasattr(self.device, 'cpc_changed') and self.device.cpc_changed:
            return True

        # Check connected CPC par_updates
        cpc_id = self.device.device_config.extra_params.get('connected_cpc', 'None')
        if cpc_id != 'None':
            if cpc_id in data_holder.par_updates and data_holder.par_updates[cpc_id] == 1:
                return True

        return False

    def get_par_data(self, data_holder, timestamp_str):
        """Return PSM settings data for .par file."""
        dev_id = self.device.dev_id
        settings = self.device.settings

        if not settings:
            return None

        # Get PSM settings array
        settings_array = settings.to_array()
        data_str = ','.join(str(val) for val in settings_array)

        # Add connected CPC settings if applicable
        cpc_id = self.device.device_config.extra_params.get('connected_cpc', 'None')
        if cpc_id != 'None':
            # Find CPC device widget in device_widgets
            cpc_widget = data_holder.device_widgets.get(cpc_id)

            # If CPC widget exists and is Airmodus CPC, write settings
            if cpc_widget and cpc_widget.device_config.device_type == CPC:
                cpc_idn = cpc_widget.device_config.serial_number
                cpc_settings = data_holder.get_device_settings(cpc_id)

                if cpc_settings:
                    connected_cpc_settings = [
                        cpc_idn,  # CPC serial number (IDN)
                        cpc_settings.autofill,
                        cpc_settings.drain,
                        cpc_settings.water_removal,
                        cpc_settings.saturator_temp,
                        cpc_settings.condenser_temp,
                        cpc_settings.optics_temp,  # optics temp
                        cpc_settings.measured_cpc_flow,
                        cpc_settings.averaging_time
                    ]
                    data_str += ',' + ','.join(str(val) for val in connected_cpc_settings)
                else:
                    data_str += ',nan,nan,nan,nan,nan,nan,nan,nan,nan'
            else:
                # CPC not connected or not Airmodus CPC
                data_str += ',nan,nan,nan,nan,nan,nan,nan,nan,nan'
        else:
            # No connected CPC selected
            data_str += ',nan,nan,nan,nan,nan,nan,nan,nan,nan'

        # Add command if present
        if self.device.latest_command is not None:
            data_str += ',' + self.device.latest_command
            self.device.latest_command = None

        # Reset cpc_changed flag if it exists
        if hasattr(self.device, 'cpc_changed'):
            self.device.cpc_changed = False

        return data_str


class ElectrometerDataWriter(BaseDataWriter):
    """Data writer for Electrometer devices."""

    def get_dat_header(self):
        """Return Electrometer .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Voltage 1 (V),Voltage 2 (V),Voltage 3 (V)'


class CO2DataWriter(BaseDataWriter):
    """Data writer for CO2 sensor devices."""

    def get_dat_header(self):
        """Return CO2 sensor .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,CO2 (ppm),T (C),RH (%)'


class RHTPDataWriter(BaseDataWriter):
    """Data writer for RHTP (Humidity, Temperature, Pressure) devices."""

    def get_dat_header(self):
        """Return RHTP .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,RH (%),T (C),P (Pa)'


class AFMDataWriter(BaseDataWriter):
    """Data writer for AFM (Air Flow Meter) devices."""

    def get_dat_header(self):
        """Return AFM .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Flow (lpm),Standard flow (slpm),RH (%),T (C),P (Pa)'


class AFCDataWriter(BaseDataWriter):
    """Data writer for AFC (Airmodus Flow Controller) devices."""

    def get_dat_header(self):
        """Return AFC .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Standard flow (slpm),10 second average (slpm),T (C),Flow setpoint (slpm),Error status'


class EDiluterDataWriter(BaseDataWriter):
    """Data writer for eDiluter devices."""

    def get_dat_header(self):
        """Return eDiluter .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Status,P1,P2,T1,T2,T3,T4,T5,T6,DF1,DF2,DFTot'


class TSICPCDataWriter(BaseDataWriter):
    """Data writer for TSI CPC devices."""

    def get_dat_header(self):
        """Return TSI CPC .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Concentration (#/cc),Instrument errors (hex)'


class ExampleDataWriter(BaseDataWriter):
    """Data writer for example device."""

    def get_dat_header(self):
        """Return example device .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,Random value (0-100)'


class DefaultDataWriter(BaseDataWriter):
    """Default data writer for unknown device types."""

    def get_dat_header(self):
        """Return generic .dat file header."""
        return 'YYYY.MM.DD hh:mm:ss,value1,value2,value3'
