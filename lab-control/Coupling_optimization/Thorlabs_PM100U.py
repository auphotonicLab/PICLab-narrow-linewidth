#!/usr/bin/env python
import json
import time
from matplotlib import pyplot as plt
from TLPM import TLPM
from tkinter import Tk, filedialog
import sys
#import System
import clr   # COMMON LANGUAGE RUNTIME, part of pythonnet package, do not confuse with "clr" package
from ctypes import (cdll,
                    c_long,
                    c_ulong,
                    c_uint32,
                    byref,
                    create_string_buffer,
                    c_bool,
                    c_char_p,
                    c_int,
                    c_int16,
                    c_double,
                    sizeof,
                    c_voidp)


class Thorlabs_PM100U:
    def __init__(self,  resource_manager, port, settings_path, lambda0=1550, PM_index=1):
        self.PDinstr = TLPM()
        deviceCount = c_uint32()
        self.PDinstr.findRsrc(byref(deviceCount))
        
        resourceName = []
        modelName = []
        serialNumber = []
        manufacturer = []
        deviceAvailable = []
        
        for i in range(0,deviceCount.value):
            resourceName.append(create_string_buffer(1024))
            modelName.append(create_string_buffer(1024))
            serialNumber.append(create_string_buffer(1024))
            manufacturer.append(create_string_buffer(1024))
            deviceAvailable.append(create_string_buffer(1024))
            
        
        print(f'There are {deviceCount.value} device(s) available')
        self.PDinstr.close()
        
        
        self.PDinstr.getRsrcName(c_int(PM_index), resourceName[PM_index])
        
        self.PDinstr.getRsrcInfo(c_int(PM_index), modelName[PM_index], serialNumber[PM_index], manufacturer[PM_index], byref(c_int16()))
        
        print(f'The connected device is {modelName[PM_index].value.decode("utf-8")} {serialNumber[PM_index].value.decode("utf-8")}')
        self.PDinstr.open(resourceName[PM_index], c_bool(True), c_bool(True))
        self.PDinstr.setWavelength(c_double(lambda0))
        message = create_string_buffer(1024)
        self.PDinstr.getCalibrationMsg(message)

        print(f'Last calibrated {message.value.decode("utf-8")}')

        time.sleep(2)

    def GetPower(self):
        power = c_double()
        pU = c_int16()
        lam0 = c_double()
        self.PDinstr.setAvgTime(c_double(0.005))
        self.PDinstr.measPower(byref(power))
        self.PDinstr.getPowerUnit(byref(pU))
        self.PDinstr.getPhotodiodeResponsivity(c_int16(0), byref(lam0))
        time.sleep(0.1)
        # print('Power unit:',lam0)
        # print('Power unit:',self.PDinstr.getPowerUnit(byref(lam)))
        return power.value

    def closeConnection(self):
        self.PDinstr.close()
'''

        self.is_alive()
        self.set_beam()
        self.set_auto_range()
        self.meter.write(':CONF:POW')  # configure for power
        #self.load_settings()
        self.averaging_set = self.get_averaging()
        self.detector_wavelength_set = self.get_detector_wavelength()
        self.detector_power_get = self.get_detector_power()
        
        print(f'Last calibrated {message.value.decode("utf-8")}')

    
    def is_alive(self):
        is_alive = self.meter.write('*IDN?')
        if is_alive != 0:
            print("Thorlabs detector " + self.port + " is alive")

    def zero(self):
        """Zero the sensor"""
        # msg = ':INIT'
        # self.meter.write(msg)
        msg = ':SENS:CORR:COLL:ZERO'
        self.meter.write(msg)
        wait = 0
        while (not wait):
            self.meter.write('*OPC?')
            wait = self.meter.read()

    def get_averaging_set(self):
        """Get the averaging"""
        return self.averaging_set

    def get_averaging(self):
        """Get the averaging"""
        msg = ':SENS:AVER?'
        self.meter.write(msg)
        return int(self.meter.read().replace('\n', '').replace('\r', ''))

    def set_averaging(self, average):
        """Get the averaging"""
        msg = ':SENS:AVER %s' % (str(average))
        self.averaging_set = average
        self.meter.write(msg)

    def set_config_power(self):
        msg = ':SENS:CONF:POW'
        self.meter.write(msg)

    def set_auto_range(self, auto_range='ON'):
        msg = ':SENS:POW:RANG:AUTO %s' % (str(auto_range))
        self.meter.write(msg)

    def set_beam(self, beam='MIN'):
        """Set the wavelength in nm"""
        msg = ':SENS:CORR:BEAM %s' % (str(beam))
        self.meter.write(msg)

    def set_detector_wavelength(self):
        """Set the wavelength in nm"""
        msg = ':SENS:CORR:WAV %s' % (str(self.detector_wavelength_set))
        self.meter.write(msg)

    def set_detector_wavelength_set(self, wavelength_nm):
        """Set the wavelength in nm"""

        self.detector_wavelength_set = wavelength_nm

    def set_units(self, unit_str):
        """Set the units to W or dBm"""
        msg = ':SENS:POW:UNIT %s' % (unit_str)
        self.meter.write(msg)

    def get_units(self):
        """Set the units to W or dBm"""
        msg = ':SENS:POW:UNIT?'
        self.meter.write(msg)
        return self.meter.read().replace('\n', '').replace('\r', '')

    def get_detector_power(self):
        """Get a power measurement"""
        power = 2e1
        msg = ':READ?'
        while (power > 1e1):
            self.meter.write(msg)
            power_str = self.meter.read()
            power = float(power_str[0:-1])
        if power < 0:
            power = 1e-12
        self.detector_power_get = power
        return power

    def get_detector_power_get(self):
        """Get a power measurement"""
        return self.detector_power_get

    def get_detector_wavelength_set(self):
        """Get the averaging"""
        return self.detector_wavelength_set

    def get_detector_wavelength(self):
        msg = ':SENS:CORR:WAV?'
        self.meter.write(msg)
        self.meter.write(msg)
        wavelength_str = self.meter.read()

        return float(wavelength_str.replace('\n', '').replace('\r', ''))

    def reset(self):
        """Reset"""
        self.meter.write('*RST')
        self.meter.write('*CLS')

    def get_name(self):
        return "Detector " + str(self.port)[29:31]

    def load_settings(self):
        with open(self.settings_path, "r") as text_file:
            settings_dict = json.load(text_file)
            self.set_detector_wavelength_set(settings_dict["wavelength"])
            self.set_units(settings_dict["units"])
            self.set_averaging(settings_dict["averaging"])

    def save_settings(self):
        dictionary = {
            "wavelength": self.get_detector_wavelength(),
            "units": self.get_units(),
            "averaging": self.get_averaging()
        }

        with open(self.settings_path, "w") as text_file:
            json.dump(dictionary, text_file)

    def close(self):
        """End communication"""
        self.save_settings()
        self.meter.close()    
'''




'''
    def __init__(self, resource_manager, port, settings_path):
        """Connect to and reset Thorlabs PM101USB"""
        self.port = port
        self.settings_path = settings_path
        self.resource_manager = resource_manager
        self.meter = resource_manager.open_resource(port)
        self.is_alive()
        self.set_beam()
        self.set_auto_range()
        self.meter.write(':CONF:POW')  # configure for power
        self.load_settings()
        self.averaging_set = self.get_averaging()
        self.detector_wavelength_set = self.get_detector_wavelength()
        self.detector_power_get = self.get_detector_power()

    def is_alive(self):
        is_alive = self.meter.write('*IDN?')
        if is_alive != 0:
            print("Thorlabs detector " + self.port + " is alive")

    def zero(self):
        """Zero the sensor"""
        # msg = ':INIT'
        # self.meter.write(msg)
        msg = ':SENS:CORR:COLL:ZERO'
        self.meter.write(msg)
        wait = 0
        while (not wait):
            self.meter.write('*OPC?')
            wait = self.meter.read()

    def get_averaging_set(self):
        """Get the averaging"""
        return self.averaging_set

    def get_averaging(self):
        """Get the averaging"""
        msg = ':SENS:AVER?'
        self.meter.write(msg)
        return int(self.meter.read().replace('\n', '').replace('\r', ''))

    def set_averaging(self, average):
        """Get the averaging"""
        msg = ':SENS:AVER %s' % (str(average))
        self.averaging_set = average
        self.meter.write(msg)

    def set_config_power(self):
        msg = ':SENS:CONF:POW'
        self.meter.write(msg)

    def set_auto_range(self, auto_range='ON'):
        msg = ':SENS:POW:RANG:AUTO %s' % (str(auto_range))
        self.meter.write(msg)

    def set_beam(self, beam='MIN'):
        """Set the wavelength in nm"""
        msg = ':SENS:CORR:BEAM %s' % (str(beam))
        self.meter.write(msg)

    def set_detector_wavelength(self):
        """Set the wavelength in nm"""
        msg = ':SENS:CORR:WAV %s' % (str(self.detector_wavelength_set))
        self.meter.write(msg)

    def set_detector_wavelength_set(self, wavelength_nm):
        """Set the wavelength in nm"""

        self.detector_wavelength_set = wavelength_nm

    def set_units(self, unit_str):
        """Set the units to W or dBm"""
        msg = ':SENS:POW:UNIT %s' % (unit_str)
        self.meter.write(msg)

    def get_units(self):
        """Set the units to W or dBm"""
        msg = ':SENS:POW:UNIT?'
        self.meter.write(msg)
        return self.meter.read().replace('\n', '').replace('\r', '')

    def get_detector_power(self):
        """Get a power measurement"""
        power = 2e1
        msg = ':READ?'
        while (power > 1e1):
            self.meter.write(msg)
            power_str = self.meter.read()
            power = float(power_str[0:-1])
        if power < 0:
            power = 1e-12
        self.detector_power_get = power
        return power

    def get_detector_power_get(self):
        """Get a power measurement"""
        return self.detector_power_get

    def get_detector_wavelength_set(self):
        """Get the averaging"""
        return self.detector_wavelength_set

    def get_detector_wavelength(self):
        msg = ':SENS:CORR:WAV?'
        self.meter.write(msg)
        self.meter.write(msg)
        wavelength_str = self.meter.read()

        return float(wavelength_str.replace('\n', '').replace('\r', ''))

    def reset(self):
        """Reset"""
        self.meter.write('*RST')
        self.meter.write('*CLS')

    def get_name(self):
        return "Detector " + str(self.port)[29:31]

    def load_settings(self):
        with open(self.settings_path, "r") as text_file:
            settings_dict = json.load(text_file)
            self.set_detector_wavelength_set(settings_dict["wavelength"])
            self.set_units(settings_dict["units"])
            self.set_averaging(settings_dict["averaging"])

    def save_settings(self):
        dictionary = {
            "wavelength": self.get_detector_wavelength(),
            "units": self.get_units(),
            "averaging": self.get_averaging()
        }

        with open(self.settings_path, "w") as text_file:
            json.dump(dictionary, text_file)

    def close(self):
        """End communication"""
        self.save_settings()
        self.meter.close()
'''