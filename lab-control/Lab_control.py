#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar 15 11:57:22 2022

@author: au657379
"""

import pyvisa as visa
import numpy as np
import time
import matplotlib.pyplot as plt
import os
import re
from datetime import datetime
from TLPM import TLPM
from tkinter import Tk, filedialog
import sys
import socket
import struct
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

# %%
cwd = os.getcwd()

def datestring():
    now = datetime.now()
    datestring = now.strftime('%Y-%m-%d')
    return datestring


def timestring():
    now = datetime.now()
    timestring =  now.strftime('%H-%M-%S')
    return timestring


def datetimestring(microsecond=False):
    now = datetime.now()
    if microsecond:
        datestring =  now.strftime('%Y-%m-%d_%H-%M-%S-%f')
    else:
        datestring =  now.strftime('%Y-%m-%d_%H-%M-%S')
    return datestring

def change_folder(my_path, data_folder_name, meas_type = ''): #Added an option for a meas_type
    old_directory = os.getcwd()
    print("\nYour current working directory is:\n {0}\n".format(old_directory))
    try:
        my_directory_aux = os.path.join(my_path,
                                        meas_type + 'Measurements_' + datestring())
        my_directory = os.path.join (my_directory_aux, data_folder_name)
        os.makedirs(my_directory, exist_ok = True)
        print("Your data will be saved in: '%s'\n" % my_directory)
        os.chdir(my_directory)
    except OSError as error:
        print(error)
        print("Folder '%s' cannot be created" % my_directory)
        pass
    return old_directory, my_directory


def choose_folder():
    # Print the current working directory
    my_directory = os.getcwd()
    print("Current working directory:\n {0}\n".format(my_directory))
    
    root = Tk() # pointing root to Tk() to use it as Tk() in program.
    root.withdraw() # Hides small tkinter window.
    root.attributes('-topmost', True) # 'always on top'
    try:
        my_directory = filedialog.askdirectory() # Returns opened path as str
        # Change the current working directory
        os.chdir(my_directory)
        # Print the current working directory
        print("New working directory:\n {0}\n".format(os.getcwd()))
    except OSError as error:
        print(error)
        pass
    return my_directory



# %%
# =============================================================================
# TOSA - OE
# =============================================================================
   
class AimValley_CurrentSource: #developer: Mónica
    """ Class to control the low noise Aimvalley current sources.  
        (it requires a dll to work)

    
    Parameters/attributes
    ---------------------
    port : str, optional
        COM port where the instrument is connected. The default is 'COM10'.
    path : str, optional
        folder where the .dll is located. The default is os.getcwd().
    
    
    Functions
    ----------
    SetCurrent : Sets current in mA
    
    GetVoltage : Gets voltages in V
    
    openCommunication : Opens connection with the instrument.    
    
    closeCommunication : Closes connection with the instrument.    
    """
    
    def __init__(self,
                 port = 6, # com port of the instrument
                 path=cwd, #where the .dll is
                 ):
       
        self.path = path
        self.port = port
        sys.path.append(self.path)

        #full path to the .dll, with default name
        dll_file = os.path.join(self.path,'TosaControlx64.dll')
        
        # load dll
       # dll_ref = System.Reflection.Assembly.LoadFile(dll_file)
        TosaB = clr.AddReference(r"C:\Users\Group Login\Documents\Simon\TosaControlx64.dll")
        # Check to see if DLL is loaded correctly, should print DLL information
        print (TosaB)
        # import dll functions
        from TosaControl_NS import BoxControl
        
        # Initialize all settings for the current control box
        BoxControl.InitializeEverything()

        # Change COM Port number to the correct one, shown in device manager
        BoxControl.TosaBox._serialPort.PortName = 'COM' + str(self.port)
        #BoxControl.TosaBox.OpenSession()
        self.instr = BoxControl
    
    def openCommunication(self):
        """ Opens connection with the device.
        
        Returns
        -------
        None.

        """
        self.instr.TosaBox.OpenSession()
        return

    def closeCommunication(self):
        """ Close connection with the device.
        
        Returns
        -------
        None.

        """
        # Close com port session when everything is done
        if self.instr.TosaBox._serialPort.IsOpen == True:
            self.instr.TosaBox.CloseSession()
        return

    def getMPDphotocurrent(self,number=1):
        """ Get MPD photocurrent
        
        Parameters
        ----------
        number: int {1,2}
            MPD number: 1 or 2 (one per output waveguide).
        
        Returns
        -------
        Photocurrent at selected MPD.

        """
        # Close com port session when everything is done
        if self.instr.TosaBox._serialPort.IsOpen == False: 
            raise SystemError('Port not open')
            
        if number == 1:
            self.instr.MPD1.Update()
            photocurrent = self.instr.MPD1.AdcCurrent
        if number == 2:
            self.instr.MPD2.Update()
            photocurrent = self.instr.MPD2.AdcCurrent
        return photocurrent

    def setCurrent(self, channel, value=0):
        """Set currents in mA.
        
        Parameters
        ----------
        channel: str
            Which output to set the current to.
            Possible channels:
                M1 (Mirror 1): 0 - 65 mA
                M2 (Mirror 2): 0 - 65 mA
                LPh (Laser Phase): 0 - 20 mA
                LG (Laser Gain): 0 - 250mA?
                SOA1: 0 - 160 mA
                SOA2: 0 - 160 mA
                Ph1 (Phase 1): 0 - 20 mA
                Ph2 (Phase 2): 0 - 20 mA
        
        value: float, optional
            Current to set. The default is 0.
      
        Returns
        -------
        None.
        """
        if self.instr.TosaBox._serialPort.IsOpen == False: 
            raise SystemError('Port not open')

        if channel not in {'M1', 'M2', 'LPh', 'LG',
                           'SOA1', 'SOA2', 'Ph1', 'Ph2'}:
            raise ValueError('Chosen location not valid. Please choose ' +
                             'one of the following: M1, M2, LPh, LG, SOA1,' +
                             'SOA2, Ph1, Ph2')
        
        try:
            float(value)
        except ValueError:
                print('Please input correct value')
        
        if value < 0:
            raise ValueError('Please input positive current value')

        if channel == 'M1':
            if value > 65:
                raise ValueError('Max current is 65 mA')
            else:
                self.instr.Mirror1.IdacCurrent = value
                self.instr.Mirror1.Update()
        elif channel == 'M2':
            if value > 65:
                raise ValueError('Max current is 65 mA')
            else:
                self.instr.Mirror2.IdacCurrent = value
                self.instr.Mirror2.Update()

        elif channel == 'LPh':
            if value > 20:
                raise ValueError('Max current is 20 mA')
            else:
                self.instr.LaserPhase.IdacCurrent = value
                self.instr.LaserPhase.Update()

        elif channel == 'LG':
            if value > 200:
                raise ValueError('Max current is 200 mA')
            else:
                self.instr.LaserGain.IdacCurrent = value
                self.instr.LaserGain.Update()

        elif channel == 'SOA1':
            if value > 160:
                raise ValueError('Max current is 160 mA')
            else:
                self.instr.SOA1.IdacCurrent = value
                self.instr.SOA1.Update()


        elif channel == 'SOA2':
            if value > 160:
                raise ValueError('Max current is 160 mA')
            else:
                self.instr.SOA2.IdacCurrent = value
                self.instr.SOA2.Update()


        elif channel == 'Ph1':
            if value > 20:
                raise ValueError('Max current is 20 mA')
            else:
                self.instr.Phase1.IdacCurrent = value
                self.instr.Phase1.Update()

        else: # channel == 'Ph2':
            if value > 20:
                raise ValueError('Max current is 20 mA')
            else:
                self.instr.Phase2.IdacCurrent = value
                self.instr.Phase2.Update()

        return #print('Set ' + str(value) + ' mA in ' + channel )

    def getVoltage(self, channel):
        '''
         Get voltages in volts.
        
        Parameters
        ----------
        channel: str
            Which output to set the current to.
            Possible channels:
                M1 (Mirror 1): 0 - 65 mA
                M2 (Mirror 2): 0 - 65 mA
                LPh (Laser Phase): 0 - 20 mA
                LG (Laser Gain): 0 - 250mA?
                SOA1: 0 - 160 mA
                SOA2: 0 - 160 mA
                Ph1 (Phase 1): 0 - 20 mA
                Ph2 (Phase 2): 0 - 20 mA      
        
        Returns
        -------
        data: float
            voltage in volts. Max Voltage 2.25V?

        '''
      
        if channel not in {'M1', 'M2', 'LPh', 'LG',
                           'SOA1', 'SOA2', 'Ph1', 'Ph2'}:
            raise ValueError('Chosen location not valid. Please choose ' +
                             'one of the following: M1, M2, LPh, LG, SOA1,' +
                             'SOA2, Ph1, Ph2')

        if channel == 'M1':
            volt = self.instr.Mirror1.AdcVoltage
        elif channel == 'M2':
            volt = self.instr.Mirror2.AdcVoltage
        elif channel == 'LPh':
            volt = self.instr.LaserPhase.AdcVoltage
        elif channel == 'LG':
            volt = self.instr.LaserGain.AdcVoltage
        elif channel == 'SOA1':
            volt = self.instr.SOA1.AdcVoltage
        elif channel == 'SOA2':
            volt = self.instr.SOA2.AdcVoltage
        elif channel == 'Ph1':
            volt = self.instr.Phase1.AdcVoltage
        else:# channel == 'Ph2':
            volt = self.instr.Phase2.AdcVoltage

        #print(channel + ': ' + str(volt))
        return volt
# =============================================================================
# HP_86120B_wavemeter
# =============================================================================

class HP_86120B_wavemeter:  # developer: Mónica Far
    '''
    Class to control the HP 86120B wavemeter.
    Manual can be found either at:
    https://www.keysight.com/dk/en/assets/9018-05330/user-manuals/9018-05330.pdf?success=true
    or at:
    # O:\ST_Photonics\Literature\Manuals_hardware\Keysight 86120B Multi-Wavelength Meter.pdf
    '''

    def __init__(self,
                 channel=20,
                 GPIB_interface=0,
                 threshold=20,
                 wlimit_start = 1500*10**(-9), 
                 wlimit_stop=1570*10**(-9)):
        self.channel = channel   # GPIB channel
        rm = visa.ResourceManager()  # Open VISA resource manager
        resourceName = ('GPIB'
                        + str(int(GPIB_interface))
                        + '::'
                        + str(channel)
                        + '::INSTR')  # Create string with resource name
        self.instr = rm.open_resource(resourceName)  # open communication
        alive = self.instr.query('*IDN?')  # Ask the instrument for its name
        self.instr.read_termination = '\n'  # Set insturment read termination
        self.instr.write_termination = '\n'  # Set insturment write termination
        # Show if insturment is alive
        # Set peak db threshold
        self.instr.write(':CALC2:PTHR ' + str(threshold))
        
        #Set range of spectrum sweeped for peaks
        self.instr.write(':CALC2:WLIM ON')
        self.instr.write(':CALC2:WLIM:STAR ' + str(wlimit_start))
        self.instr.write(':CALC2:WLIM:STOP ' + str(wlimit_stop))
        

    
        if alive != 0:
            print('HP 86120B wavemeter is alive')
            print(alive)

        else:
            print('Could not connect')

        #self.instr.write('INIT:CONT OFF')   # Turn off continuos mode

    def getWavelength(self):
        '''
        Queries the wavemeter for the measured wavelengths.
        The queried value is a string with the values separated by commas, thus
        this function then creates a numpy array with the values.
        Additionally, this instruments sometimes yields a value of 100 for the
        wavelenght, so it is eliminated when appropriate.

        Parameters
        ----------
        self :  class attribute
            Instrument resource.

        Returns
        -------
        wavelengths : numpy array
            Array containing the measured wavelengths.
        '''
        # starts continuos mode
        self.instr.write('INIT:CONT ON')
        # stops continuos mode
        self.instr.write('INIT:CONT OFF')

        # Query the measured wavlengths
        wavelength_list = self.instr.query('MEAS:ARR:POW:WAV?')
        # Split the obtained string and create numpy array
        wavelengths = np.array(wavelength_list.split(',')).astype(float)
        # Delete if necessary
        if wavelengths[0] > 0.1:
            wavelengths = np.delete(wavelengths, 0)
        return wavelengths

    def getPowerOnly(self):
        '''
        Queries the wavemeter for the measured power.
        The queried value is a string with the values separated by commas, thus
        this function then creates a numpy array with the values.
        Additionally, this instruments sometimes yields a value of 100 for the
        power, so it is eliminated when appropriate.

        Parameters
        ----------
        self :  class attribute
            Instrument resource.

        Returns
        -------
        powers : numpy array
            Array containing the measured powers.
        '''
        # starts continuos mode
        self.instr.write('INIT:CONT ON')
        time.sleep(0.1)
        # stops continuos mode
        self.instr.write('INIT:CONT OFF')

        # Query the measured power
        power_list = self.instr.query('FETC:ARR:POW?')  # Query the power
        # Split the obtained string and create numpy array
        try:
            powers = np.array(power_list.split(',')).astype(float)
            if round(powers[0]) > 0:
                powers = np.delete(powers, 0)
        except ValueError:
            powers = -1000
        # Delete if necessary

        return powers

    def getPower(self):
        '''
        Queries the wavemeter for the measured power.
        The queried value is a string with the values separated by commas, thus
        this function then creates a numpy array with the values.
        Additionally, this instruments sometimes yields a value of 100 for the
        power, so it is eliminated when appropriate.

        Parameters
        ----------
        self :  class attribute
            Instrument resource.

        Returns
        -------
        powers : numpy array
            Array containing the measured powers.
        '''

        # Query the measured power
        power_list = self.instr.query('FETC:ARR:POW?')  # Query the power
        # Split the obtained string and create numpy array
        powers = np.array(power_list.split(',')).astype(float)
        # Delete if necessary
        if round(powers[0]) > 0:
            powers = np.delete(powers, 0)
        return powers


    def getSNR(self):
        '''
        Queries the wavemeter for the Signal to noise ratio (SNR).
        The queried value is a string with the values separated by commas, thus
        this function then creates a numpy array with the values.
        Additionally, this instruments sometimes yields a value of 100 for the
        power, so it is eliminated when appropriate.

        Parameters
        ----------
        self :  class attribute
            Instrument resource.

        Returns
        -------
        snr : numpy array
            Array containing the measured signal to noise ratio.
        '''

        # turn on SNR measurement
        self.instr.write(':CALC3:SNR:STAT ON')
        # Query the measured snr
        snr_list = self.instr.query(':CALC3:DATA? POW')
        # Split the obtained string and create numpy array
        snr = np.array(snr_list.split(',')).astype(float)
        return snr

    # The following is so it is compatible with sweep2D

    def getAll(self, length=10):
        wavelength = self.getWavelength()
        time.sleep(1)
        power = self.getPower()
        time.sleep(0.1)
        snr = self.getSNR()
        aux_vector = np.zeros(len(wavelength))
        return [[wavelength, power, snr], aux_vector]

    def getWavPow(self):
        wavelength = self.getWavelength()
        #time.sleep(0.5)
        power = self.getPower()
        return np.array([wavelength,power])
        
    def getAll_2(self, length=10):
        aux_vector = np.zeros(length)
        wav_vector = aux_vector * 1
        pow_vector = aux_vector * 1
        snr_vector = aux_vector * 1

        wavelength = self.getWavelength()
        time.sleep(1)
        power = self.getPower()
        time.sleep(0.1)
        snr = self.getSNR()

        if len(wavelength) < length:
            for index, element in enumerate(wavelength):
                wav_vector[index] = element
                pow_vector[index] = power[index]
                snr_vector[index] = snr[index]
            return [[wav_vector, pow_vector, snr_vector], aux_vector]
        else:
            raise ValueError('Pick larger length. Now: ' + str(length)
                             + 'wavelength number:' + str(len(wavelength)))

    def closeConnection(self):
        self.instr.close()


# =============================================================================
#       Yokogawa OSA
# =============================================================================
class OSA_YOKOGAWA:  # developer: Peter Tønning, modified by Mónica Far
    """
    - DESCRIPTION:
        This class is for controlling the YOKOGAWA OSA
        Sensitivity choices (fast to slow): 'normal', 'mid', 'high'
    """
    def __init__(self,
                 sampPoints=10001,
                 GPIB_interface=-1,
                 IP_address='192.168.1.14',
                 channel=1,
                 ):
        self.samplingpoints = sampPoints
        rm = visa.ResourceManager()
        # Set GPIB_interface to use GPIB instead of TCP/IP
        if GPIB_interface > -1:
            interface = str(int(GPIB_interface))
            resourceName = 'GPIB' + interface + '::' + str(channel) + '::INSTR'
        else:
            resourceName = 'TCPIP0::' + IP_address + '::inst0::INSTR'
        #print(resourceName)
        self.instr = rm.open_resource(resourceName)
        # self.instr.open()
        alive = self.instr.query('*IDN?')

        #if alive != 0:
            #print('OSA_YOKOGAWA is alive')
            #print(alive)

        self.instr.write("*RST")
        self.instr.write("CFORM1")
        self.instr.write(':SENSE:SWEEP:POINTS '+str(self.samplingpoints))
        self.instr.timeout = 30000


    def SetParameters(self,
                      centerWave=1530,
                      spanWave=60,
                      resolutionBW=0.05,
                      dbres=6,
                      reflev=-30,
                      sensitivity='normal'):
        # Set the OSA scanning parameters:
        # Center frequency
        self.instr.write(':sens:wav:cent '+str(centerWave)+'nm')
        # Frequency span
        self.instr.write(':sens:wav:span '+str(spanWave)+'nm')
        # Resolution bandwidth
        self.instr.write(':sens:band '+str(resolutionBW)+'nm')
        # Ref level
        self.instr.write(':DISPLAY:TRACE:Y1:RLEVEL ' + str(reflev) + 'dbm')
        # log scale
        self.instr.write(':DISP:TRAC:Y1:PDIV ' +str(dbres))
        self.instr.write(":sens:sens "+sensitivity)
        # Set sampling points
        self.instr.write(':SENSE:SWEEP:POINTS '+str(self.samplingpoints))

    def ReadSpectrum(self):
        # Set the OSA scanning parameters:
        # Start   measurement:
        self.instr.write(":init:smode 1")
        self.instr.write("*CLS")
        self.instr.write(":init")  
        # Wait for 20 seconds or until the measurement is done
        count = 0
        while int(self.instr.query(':STAT:OPER:even?')) == 0:
            time.sleep(1)
            count = count+1
            if count > 20:
                break
        # Initilize parameters for trace fetch:
        wav = self.instr.query_ascii_values(':TRACE:X? TRA')
        power = self.instr.query_ascii_values(':TRACE:Y? TRA')
        return np.array([wav,power])
    
    def setPeaksSearch(self):
        # Automatic sweep points
        self.instr.write(':SENSE:SWE:POINTS:AUTO ON')
        # double sweep speed
        self.instr.write(':SENSE:SWE:SPE 2x')
        # lower resolution for faster sweep
        self.instr.write(':SENSE:BAND 0.2nm')
        # 3db peak difference
        self.instr.write(':CALC:PAR:COMM:MDIF 3')
        # Start OSA measurement:
        self.instr.write(":init:smode REP")
        self.instr.write("*CLS")
        self.instr.write(":init") 

    def getPeaks(self,single=True):
        self.setPeaksSearch()
        if single:
            self.instr.write(':CALC:MARK:MSE OFF')
        else:
            self.instr.write(':CALC:MARK:MSE ON')
            self.instr.write(':CALC:MARK:MSE:SORT LEV')
        self.instr.write(':INIT:SMOD 1')
        self.instr.write(":init") 
        time.sleep(0.1)
        self.instr.write(':CALC:MARK:MAX')
        wav = self.instr.query_ascii_values(':CALC:MARK:X? ALL')
        power = self.instr.query_ascii_values(':CALC:MARK:Y? ALL')
        return np.array([wav,power])
        
    def closeConnection(self):
        self.instr.close()


# =============================================================================
#        Thorlabs PM
# =============================================================================

class PM100USB: # developer: Lars Nielsen, modified by Mónica Far and later Jeppe Surrow

    def __init__(self,
                 lambda0=1550,PM_name='P0024530'):
        self.PDinstr = TLPM()
        deviceCount = c_uint32()
        self.PDinstr.findRsrc(byref(deviceCount))
        
        print(f'There are {deviceCount.value} device(s) found')

        
        resourceName = []
        modelName = []
        serialNumber = []
        manufacturer = []
        deviceAvailable = []
        
        decoded_serialNumber = [None]*deviceCount.value
        
        self.PDinstr.close()

        
        for i in range(0,deviceCount.value):
            resourceName.append(create_string_buffer(1024))
            modelName.append(create_string_buffer(1024))
            serialNumber.append(create_string_buffer(1024))
            manufacturer.append(create_string_buffer(1024))
            deviceAvailable.append(create_string_buffer(1024))
            

            
            self.PDinstr.getRsrcName(c_int(i), resourceName[i])
        
            self.PDinstr.getRsrcInfo(c_int(i), modelName[i], serialNumber[i], manufacturer[i], byref(c_int16()))
            
            decoded_serialNumber[i] = serialNumber[i].value.decode("utf-8")
            
            self.PDinstr.close()

        
        PM_index = decoded_serialNumber.index(PM_name)
    

        
        print(f'The connected device is {modelName[PM_index].value.decode("utf-8")} {serialNumber[PM_index].value.decode("utf-8")}')
        self.PDinstr.open(resourceName[PM_index], c_bool(True), c_bool(True))
        self.PDinstr.setWavelength(c_double(lambda0))
        message = create_string_buffer(1024)
        self.PDinstr.getCalibrationMsg(message)
        print(f'Last calibrated {message.value.decode("utf-8")}\n')
            


    

    def closeConnection(self):
        self.PDinstr.close()

    def GetPower(self):
        power = c_double()
        pU = c_int16()
        lam0 = c_double()
        self.PDinstr.setAvgTime(c_double(0.001))
        self.PDinstr.measPower(byref(power))
        self.PDinstr.getPowerUnit(byref(pU))
        self.PDinstr.getPhotodiodeResponsivity(c_int16(0), byref(lam0))
        #time.sleep(0.01)
        # print('Power unit:',lam0)
        # print('Power unit:',self.PDinstr.getPowerUnit(byref(lam)))
        return power.value

# =============================================================================
#  Siglent ESA
# =============================================================================

class ESA_SIGLENT: #developer: Lars , modified by Mónica Far & Jeppe Surrow

    def __init__(self, USB_interface = 0,
                 IP_address='192.168.1.11',
                 spanFreq=50,
                 centerFreq=120,
                 videoBW=0.000100,
                 resolutionBW=0.000100,
                 dataPointsInSweep=20001,
                 averageNo=50):
        
        
        rm = visa.ResourceManager()
        if USB_interface > -1: #Set USB_interface = 0 to use USB instead of TCP/IP
            resourceName = 'USB0::0xF4EC::0x1300::SSA3XLBX3R0767::INSTR'
        else:
            resourceName ='TCPIP0::' + IP_address + '::inst0::INSTR'
        self.instr = rm.open_resource(resourceName)
        alive = self.instr.query('*IDN?')
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        
        self.instr.timeout = 10000
        
        if alive != 0:
            print('ESA_SIGLENT is alive')
            print(alive)
        #self.instr.write('*RST')  # Reset
        self.instr.write(':INIT')
        self.instr.write(':INITiate:CONTinuous ON')
        self.instr.write(':FORMat ASCii')
        self.instr.write(':BWID:AUTO OFF')
        self.instr.write(':BWID:VID:AUTO OFF')
        self.instr.write(':BWID:VID:RAT:CONfig 0')        

        self.spanFreq = spanFreq
        self.centerFreq = centerFreq
        self.videoBW = videoBW
        self.resolutionBW = resolutionBW
        self.dataPointsInSweep = dataPointsInSweep
        self.averageNo = averageNo
        self.instr.write('SYST:DISP:UPD ON')  # Show on ESA display as well

    def SetSpectrumParameters(self,
                              spanFreq=50,
                              centerFreq=120,
                              videoBW=0.0001,
                              resolutionBW=0.0001,
                              dataPointsInSweep=20001):
        self.spanFreq = spanFreq
        self.centerFreq = centerFreq
        self.videoBW = videoBW
        self.resolutionBW = resolutionBW
        self.dataPointsInSweep = dataPointsInSweep
        
        #self.instr.clear()
        # Center frequency
        self.instr.write('FREQ:CENT '+ str(self.centerFreq) + ' MHz')
        # Frequency span
        self.instr.write('FREQ:SPAN '+ str(self.spanFreq) + ' MHz')
        # Resolution bandwidth
        self.instr.write('BWIDth ' + str(self.resolutionBW) + ' MHz')
        # Video bandwidth
        self.instr.write('BWIDth:VID '+ str(self.videoBW) + ' MHz')
        # Number of data points in sweep
        self.instr.write('SWE:POIN '+ str(int(self.dataPointsInSweep)))
        self.instr.write(':INITiate:CONT ON')  # Start frequency sweep
        self.instr.write('*WAI')  # Wait until

    def ReadSpectrum(self):  
        #self.SetSpectrumParameters()
        if self.averageNo>0:
            self.instr.write(':TRAC1:MODE AVER')
            self.instr.write(':AVER:TRAC1:COUN ' + str(self.averageNo))
            for i in range(self.averageNo):
                self.instr.write(':INITiate:IMMediate')
                self.instr.query('*OPC?')

        else:
            self.instr.write(':INITiate:CONT ON')
            self.instr.query('*OPC?')            

        dataOut = self.instr.query(':TRACe:DATA? 1').split(',')[:-1]
        dataOut = np.array(dataOut).astype(float)
        center = self.centerFreq
        span = self.spanFreq
        freqAxis = np.linspace(center - (span/2),
                               center + (span/2),
                               len(dataOut)) #Generate corresponding frequency axis

        return np.array([freqAxis, dataOut])

    def ReadPeakPower(self, Nread=3):
        # Peak of the trace in dBm (clear-write, single sweeps). Same behaviour as ESA_RS_FSW50.ReadPeakPower.
        self.instr.write(':UNIT:POWer DBM')
        self.instr.write(':TRAC1:MODE WRITe')
        self.instr.write('FREQ:CENT ' + str(self.centerFreq) + ' MHz')
        self.instr.write('FREQ:SPAN ' + str(self.spanFreq) + ' MHz')
        self.instr.write('BWIDth ' + str(self.resolutionBW) + ' MHz')
        self.instr.write('BWIDth:VID ' + str(self.videoBW) + ' MHz')
        self.instr.write(':INITiate:CONTinuous OFF')
        power = []
        for x in range(Nread):
            self.instr.write(':INITiate:IMMediate')
            self.instr.query('*OPC?')
            dataOut = [v for v in self.instr.query(':TRACe:DATA? 1').split(',') if v.strip() != '']
            self.last_trace = np.array(dataOut).astype(float)   # trace of the last sweep (dBm), for saving
            power.append(np.max(self.last_trace))
        self.instr.write(':INITiate:CONTinuous ON')
        return float(np.max(power))

    def saveScreenshotToPC(self, local_path):
        """Save the screen as a BMP file on the controlling PC (:HCOPy:SDUMp:DATA?, SSA3000X programming guide 3.2.16).

        The guide only says the query returns the BMP data, so both a raw BMP and an IEEE block (#<n><len><data>) are handled.
        """
        old_timeout, old_term = self.instr.timeout, self.instr.read_termination
        self.instr.timeout = 60000
        self.instr.read_termination = None      # BMP bytes contain 0x0A
        try:
            self.instr.write(':HCOPy:SDUMp:DATA?')
            raw = self.instr.read_raw()
        finally:
            self.instr.timeout, self.instr.read_termination = old_timeout, old_term
        if raw[:1] == b'#':
            ndig = int(raw[1:2])
            n = int(raw[2:2 + ndig])
            raw = raw[2 + ndig:2 + ndig + n]
        else:
            i = raw.find(b'BM')
            raw = raw[i:] if 0 <= i < 64 else raw
        with open(local_path, 'wb') as f:
            f.write(raw)

    def CloseConnection(self):
        self.instr.close()

# =============================================================================
# Siglent Function Generator
# =============================================================================

class AFG_Siglent:
    
    def __init__(self,
                 channel=1,
                 IP_address='192.168.1.101',
                 frequency=120000000,
                 waveform='SINE',
                 vpp=1.8,
                 offset=0, 
                 load = 50 # Use 50 or 'HZ'
                 ):
        
        self.frequency = frequency
        self.vpp = vpp
        self.waveform = waveform
        self.channel = channel
        self.offset = offset
        self.load = load
        
        rm = visa.ResourceManager()
        resourceName ='TCPIP0::' + IP_address + '::inst0::INSTR'
        self.instr = rm.open_resource(resourceName)
        alive = self.instr.query('*IDN?')

        self.instr.write('C' + str(channel) + ':BSWV WVTP,' + waveform )
        self.instr.write('C' + str(channel) + ':BSWV FRQ,' + str(frequency))  # hz
        self.instr.write('C' + str(channel) + ':BSWV AMP,' + str(vpp))  # Vpp
        self.instr.write('C' + str(channel) + ':BSWV OFST,' + ('+' if offset >= 0 else '-') + str(abs(offset)))  # sign is required by the SDG

        self.instr.write('C' + str(channel) + ':OUTP LOAD,' + str(load))

        if alive != 0:
            print('AFG_SIGLENT is alive')
            print(alive)
            
    def setParameters(self,
                      channel=1,
                      waveform='SINE',
                      frequency=120000000,
                      vpp=1.8,
                      offset=0,
                      load = 50 # Use 50 or 'HZ'
                      ):
    
        self.instr.write('C' + str(channel) + ':BSWV WVTP,' + waveform )
        
        if waveform != 'DC':
            self.instr.write('C' + str(channel) + ':BSWV FRQ,' + str(frequency))  # hz
            self.instr.write('C' + str(channel) + ':BSWV AMP,' + str(vpp))  # Vpp
        
        if offset >= 0: 
            self.instr.write('C' + str(channel) + ':BSWV OFST,+' + str(offset))  # Vpp
        else:
            self.instr.write('C' + str(channel) + ':BSWV OFST,-' + str(abs(offset)))  # Vpp
                
        self.instr.write('C' + str(channel) + ':OUTP LOAD,' + str(load))


    def setPRBS(self, channel=1, bit_rate=1e9, sequence='PRBS7',
                amplitude=1.0, load=50):
        """Output a PRBS sequence (pure AC, zero DC offset).

        The DC bias offset for the amplitude modulator must be supplied externally by a DC supply.

        Parameters
        ----------
        channel : int
            Output channel (1 or 2).
        bit_rate : float
            Data bit rate in bps.
        sequence : str
            PRBS sequence: 'PRBS3', 'PRBS7', 'PRBS9', 'PRBS15', 'PRBS23', 'PRBS31'.
        amplitude : float
            Peak-to-peak amplitude in V.
        load : int or str
            Load impedance in Ohm, or 'HZ' for high-impedance.
        """
        ch = 'C' + str(channel)
        self.instr.write(ch + ':BSWV WVTP,PRBS')
        self.instr.write(ch + ':BSWV FRQ,' + str(int(bit_rate)))   # SDG6022X uses FRQ for PRBS bit rate
        self.instr.write(ch + ':PRBS BRAT,' + str(int(bit_rate)))  # belt-and-suspenders
        self.instr.write(ch + ':PRBS SEQ,' + sequence)
        self.instr.write(ch + ':BSWV AMP,' + str(amplitude))
        self.instr.write(ch + ':BSWV OFST,0')  # pure AC; DC offset handled by SPD3303X
        self.instr.write(ch + ':BSWV PHSE,0')  # reference phase for clock alignment
        self.instr.write(ch + ':OUTP LOAD,' + str(load))

    def setClock(self, channel=2, bit_rate=1e9, amplitude=3.3, offset=1.65,
                load='HZ', rise_time=2e-9):
        """Output a square-wave clock for oscilloscope triggering during eye diagram.

        Clock frequency = bit rate (one edge per bit period).

        Both SDG6022X channels share the same internal master oscillator, so
        the clock and PRBS are inherently phase-locked and cannot drift.
        Default values produce a 0–3.3 V logic-level signal (LVCMOS 3.3 V
        compatible) with a 2 ns rise time, suitable for clean edge triggering.

        Parameters
        ----------
        channel : int
            Output channel (1 or 2).
        bit_rate : float
            Bit rate in bps; square-wave frequency = bit_rate.
        amplitude : float
            Peak-to-peak amplitude in V (default 3.3 V).
        offset : float
            DC offset in V (default 1.65 V → signal swings 0 to 3.3 V).
        load : int or str
            Load impedance in Ohm, or 'HZ' for high-impedance (default).
        rise_time : float
            Rise/fall time in seconds (default 2 ns — SDG6022X minimum).
        """
        ch = 'C' + str(channel)
        self.instr.write(ch + ':BSWV WVTP,SQUARE')
        self.instr.write(ch + ':BSWV FRQ,' + str(bit_rate))
        self.instr.write(ch + ':BSWV AMP,' + str(amplitude))
        self.instr.write(ch + ':BSWV OFST,+' + str(offset))
        self.instr.write(ch + ':BSWV DUTY,50')
        self.instr.write(ch + ':BSWV RISE,' + str(rise_time))
        self.instr.write(ch + ':BSWV PHSE,0')   # align starting edge to channel 1
        self.instr.write(ch + ':OUTP LOAD,' + str(load))

    def output_status(self, channel=1, status='ON'):
        self.instr.write('C' + str(channel) + ':OUTP ' + str(status))

    def CloseConnection(self):
        self.instr.close()

# =============================================================================
# Siglent DC Supply SPD3003X
# =============================================================================


def _spd3303x_vxi11_write(ip_address, command):
    """Send a write-only SCPI command to an SPD3303X via raw VXI11 RPC.

    OUTPut ON/OFF is silently ignored over the raw SCPI socket (port 5025)
    even with correct syntax and inter-command delays (confirmed on firmware
    1.01.01.02.05).  VXI11 is required.  Two firmware quirks are handled:
    - device_write response reports len(cmd)-1 bytes written; accepted as long
      as the VXI11 error code is 0.
    - Querying over VXI11 corrupts the socket (device sends the SCPI response
      before a device_read is issued); we therefore never issue reads here.
    """
    VXI11_PROG = 0x607AF

    def _build_record(xid, prog, vers, proc, body):
        hdr  = struct.pack('>IIIIII', xid, 0, 2, prog, vers, proc)
        cred = struct.pack('>IIII',   0, 0, 0, 0)   # AUTH_NULL credentials + verifier
        payload = hdr + cred + body
        return struct.pack('>I', 0x80000000 | len(payload)) + payload

    def _recv_record(sock):
        mark = sock.recv(4)
        if len(mark) < 4:
            return b''
        length = struct.unpack('>I', mark)[0] & 0x7FFFFFFF
        data = b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                break
            data += chunk
        return data

    # Step 1: ask portmapper (port 111) which port VXI11 core is on
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as pm:
        pm.settimeout(3.0)
        pm.connect((ip_address, 111))
        body = struct.pack('>IIII', VXI11_PROG, 1, 6, 0)    # prog, ver, TCP, port
        pm.sendall(_build_record(1, 0x186A0, 2, 3, body))   # portmapper GETPORT
        resp = _recv_record(pm)
    vxi11_port = struct.unpack('>I', resp[-4:])[0]
    if vxi11_port == 0:
        raise RuntimeError('SPD3303X: VXI11 not registered on portmapper — power-cycle the device')

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5.0)
        s.connect((ip_address, vxi11_port))

        # Step 2: create_link
        dev  = b'inst0'
        body = struct.pack('>III', 0x5D3303, 0, 10000)          # client_id, no_lock, lock_timeout
        body += struct.pack('>I', len(dev)) + dev + b'\x00' * ((-len(dev)) % 4)
        s.sendall(_build_record(2, VXI11_PROG, 1, 10, body))
        resp = _recv_record(s)
        # RPC reply header is 24 bytes; VXI11 result starts at byte 24
        if len(resp) < 28:
            raise RuntimeError(f'SPD3303X VXI11: create_link short response ({len(resp)} B) — '
                               'power-cycle the device to reset stale link state')
        vxi11_err = struct.unpack('>I', resp[24:28])[0]
        if vxi11_err != 0:
            raise RuntimeError(f'SPD3303X VXI11: create_link error {vxi11_err} — '
                               'power-cycle the device to reset stale link state')
        lid = struct.unpack('>I', resp[28:32])[0]

        # Step 3: device_write — send command, read acknowledgment
        # Never issue device_read: device sends SCPI response immediately,
        # which would corrupt the RPC stream if we tried to read it later.
        data = command.encode() + b'\n'
        body = struct.pack('>IIII', lid, 5000, 10000, 8)        # lid, io_timeout, lock_timeout, flags=END
        body += struct.pack('>I', len(data)) + data + b'\x00' * ((-len(data)) % 4)
        s.sendall(_build_record(3, VXI11_PROG, 1, 11, body))
        resp = _recv_record(s)
        if len(resp) >= 28:
            vxi11_err = struct.unpack('>I', resp[24:28])[0]
            if vxi11_err != 0:
                raise RuntimeError(f'SPD3303X VXI11: device_write error {vxi11_err} for {command!r}')
        # size field (resp[28:32]) is intentionally not checked:
        # SPD3303X firmware reports len(cmd)-1 bytes written (off-by-one bug)

        # Step 4: destroy_link so the device doesn't accumulate stale links
        s.sendall(_build_record(4, VXI11_PROG, 1, 23, struct.pack('>I', lid)))
        _recv_record(s)


class DC_Siglent: #Developer: Jeppe Surrow
        def __init__(self,
                     channel=1,
                     current=0,
                     voltage=1, TCP = True, IP_address = '192.168.1.31',
                     max_voltage=7):
            self.current = current
            self.channel = channel
            self.max_voltage = max_voltage
            self.ip_address = IP_address
            self.TCP = TCP

            if voltage > self.max_voltage:
                raise ValueError(
                    f'Requested voltage {voltage} V exceeds max_voltage '
                    f'{self.max_voltage} V. Refusing to set output.')
            self.voltage = voltage

            rm = visa.ResourceManager()
            if TCP:
                resourceName = 'TCPIP0::' + IP_address + '::5025::SOCKET'
            else:
                resourceName = 'USB0::0x0483::0x7540::SPD3XHCQ3R2187::INSTR'

            self.instr = rm.open_resource(resourceName)
            self.instr.write_termination = '\n'
            self.instr.read_termination = '\n'
            self.instr.timeout = 5000

            time.sleep(0.1)

            alive = self.instr.query('*IDN?')

            # Set voltage and current BEFORE enabling output
            self.instr.write('CH' + str(channel) + ':CURR ' + str(current))
            time.sleep(0.04)
            self.instr.write('CH' + str(channel) + ':VOLT ' + str(voltage))
            time.sleep(0.1)

            if alive:
                print('DC_SIGLENT is alive')
                print(str(alive))


        def setParameters(self,
                     channel=1,
                     current=0,
                     voltage=1):

            if voltage > self.max_voltage:
                raise ValueError(
                    f'Requested voltage {voltage} V exceeds max_voltage '
                    f'{self.max_voltage} V. Refusing to set output.')

            self.instr.write('CH' + str(channel) + ':CURR ' + str(current))
            time.sleep(0.1)
            self.instr.write('CH' + str(channel) + ':VOLT ' + str(voltage))
            time.sleep(0.1)


        def outputStatus(self, channel=1, status='ON'):
            if self.TCP:
                # OUTPut ON/OFF is silently ignored over the raw socket (port 5025)
                # even with correct syntax — VXI11 is required (confirmed firmware 1.01.01.02.05)
                _spd3303x_vxi11_write(self.ip_address, f'OUTPut CH{channel},{status}')
            else:
                self.instr.write(f'OUTPut CH{channel},{status}')


        def closeConnection(self):
            self.instr.close()
        
    
    
class DC_KEITHLEY: #developer: Andreas Hänsel + functionalities added by Hanna Becker (SetIntegrationtime, GetIntegrationtime;SetMode, GetMode, SetWire, GetWire)
    # For Keithley 2400 series (GPIB / RS-232). For the 2450 use DC_KEITHLEY_2450.

    def __init__(self,channel=21,GPIB_interface=0,IP_address='192.168.1.151'):
        self.Meas='Volt'
        self.Source='Current'
        self.channel = channel
        self.__wire__ = None       # fix: initialise so GetWire() never crashes
        self.__integtime__ = None  # fix: initialise so GetIntegrationtime() never crashes
        rm= visa.ResourceManager()
        if GPIB_interface>-1: #Set GPIB_interface=0 to use GPIB instead of TCP/IP
            resourceName = 'GPIB'+str(int(GPIB_interface))+'::'+str(channel)+'::INSTR'
        else:
            resourceName ='TCPIP0::'+IP_address+'::inst0::INSTR'
        self.instr = rm.open_resource(resourceName)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.timeout = 10000
        self.instr.baud_rate = 57600
        alive = self.instr.query('*IDN?')
        if alive != 0:
            print('Keithley is alive')
            print(alive)
        time.sleep(1)
        self.IsOn=int(self.instr.query(':OUTP?'))
        if self.IsOn == 1:
            print('Source output is ON')
        else:
          if self.IsOn == 0:
                print('Source output is OFF')

    def SwitchOn(self):
        if int(self.instr.query(':OUTP?')) != 1:  # fix: int() cast so string '1' compares correctly
            self.instr.write(':OUTP ON')
            print('Source output turned ON')
            self.IsOn = 1
        else: print('Source output was already ON')

    def SwitchOff(self):
        if int(self.instr.query(':OUTP?')) != 0:  # fix: int() cast
            self.instr.write(':OUTP OFF')
            print('Source output turned OFF')
            self.IsOn = 0
        else: print('Source output was already OFF')

    def SetMeasCurr(self):
        self.instr.write(":SENS:FUNC 'CURR'")
        self.instr.write(":FORM:ELEM CURR")
        self.Meas='Current'

    def SetMeasVolt(self):
        self.instr.write(":SENS:FUNC 'VOLT'")
        self.instr.write(":FORM:ELEM VOLT")
        self.Meas='Volt'

    def SetSourceVolt(self):
        self.instr.write('SOUR:FUNC VOLT')  # fix: was SOUR:FUNC:MODE (invalid on 2400)
        self.Source='Volt'

    def SetSourceValue(self, Value):
        if (self.Source == 'Volt'):
            self.instr.write('SOUR:VOLT '+str(Value))
        else:
           if (self.Source == 'Current'):
               self.instr.write('SOUR:CURR '+str(Value))

    def SetSourceCurr(self):
        self.instr.write('SOUR:FUNC CURR')  # fix: was SOUR:FUNC:MODE (invalid on 2400)
        self.Source='Current'

    def SetCompliance(self, Compliance=0.05):
        if (self.Meas == 'Current'):
            self.instr.write('SENS:CURR:PROT '+str(Compliance))
        else:
          if (self.Meas == 'Volt'):
              self.instr.write('SENS:VOLT:PROT '+str(Compliance))
          else:
              print('Measurement function undefined')

    def GetMeas(self):
        if (self.Meas == 'Current'):
            Value = float((self.instr.query_ascii_values('READ?'))[0])
        else:
          if (self.Meas == 'Volt'):
              Value = float((self.instr.query_ascii_values('READ?'))[0])
          else:
              print('Measurement function undefined')
              Value=0
        return Value

    def WriteGPIB(self, string):
        self.instr.write(string)

    def QueryGPIB(self, string):
        return self.instr.query(string)

    def CloseConnection(self):
        self.instr.close()

    def SetMode(self, mode_string):
        #set 'Voltage' for voltage source, measure current
        #set 'Current' for current source, measure voltage
        # ATTENTION: this setting includes a full reset and resets the compliance levels each time used!!!
        if mode_string == 'Voltage':
                self.instr.write("*RST;*CLS;*SRE 32;*ESE 1")
                print ("The current limit will be set to 0.010A.")
                print ("The voltage limit will be set to 20V.")
                self.instr.write('SENS:CURR:PROT 0.01')
                self.instr.write('SENS:VOLT:PROT 20')
                self.instr.write(":SYST:RSEN OFF")
                self.instr.write(":SOUR:FUNC VOLT")
                print("The machine has been set to 2-wire (2-probe) sensing, change this by typing myInstrument.SetWire = 'Four'")
                print("The machine has been set to VOLTAGE mode, change this by typing myInstrument.SetMode = 'Current'")
                print("---------------------------------------------------------------")
                self.instr.write(":SOUR:VOLT:MODE FIX")
                self.instr.write(':SENS:FUNC "CURR"')
                self.instr.write(":FORM:ELEM CURR")
                self.Source='Volt'
                self.Meas = 'Current'

        elif mode_string == 'Current':
                self.instr.write("*RST;*CLS;*SRE 32;*ESE 1")
                print ("The current limit will be set to 0.010A.")
                print ("The voltage limit will be set to 20V.")
                self.instr.write('SENS:CURR:PROT 0.01')
                self.instr.write('SENS:VOLT:PROT 20')
                self.instr.write(":SYST:RSEN OFF")
                self.instr.write(":SOUR:FUNC CURR")
                print("The machine has been set to 2-wire (2-probe) sensing, change this by typing myInstrument.SetWire = 'Four'")
                print("The machine has been set to CURRENT mode, change this by typing myInstrument.SetMode = 'Voltage'")
                print("---------------------------------------------------------------")
                self.instr.write(":SOUR:CURR:MODE FIX")
                self.instr.write(':SENS:FUNC "VOLT"')
                self.instr.write(":FORM:ELEM VOLT")
                self.Source='Current'
                self.Meas = 'Volt'
        else:
                AttributeError("Got invalid reponse for mode of the instrument: requires 'Voltage' or 'Current' but got %s" %str(mode_string))

    def GetMode(self):
        return self.Source

    def SetWire(self,wire):
        if wire == None:
                self.instr.write(":SYST:RSEN OFF")
        elif wire == 'Two':
                self.instr.write(":SYST:RSEN OFF")
                self.__wire__ = 'Two'
        elif wire == 'Four':
                if self.Source == 'Volt':
                        print("4-wire sensing possible only with 'Current' mode. Change mode from 'Voltage' to 'Current'. Now executing 2-wire sensing.")
                elif self.Source == 'Current':
                        self.instr.write(":SYST:RSEN ON")
                        self.__wire__ = 'Four'
                        print("Sensing set by user as 4-wire. Resetting machine to 4-wire sensing")
        else:
                AttributeError("Got invalid reponse for mode of the instrument: requires 'Two' or 'Four' but got %s" %str(wire))

    def GetWire(self):
        return self.__wire__

    def SetIntegrationtime(self, int_time=1.00):
        #  integration time is specified in parameters based on the number of power line cycles (NPLC)
        # FAST — Sets speed to 0.01 PLC and sets display resolution to 3½ digits.
        # MED — Sets speed to 0.10 PLC and sets display resolution to 4½ digits.
        # NORMAL — Sets speed to 1.00 PLC and sets display resolution to 5½ digits.
        # HI ACCURACY — Sets speed to 10.00 PLC and sets display resolution to 6½digits.
        # OTHER — Use to set speed to any PLC value from 0.01 to 10
        if (self.Meas == 'Current'):
                self.instr.write(":SENS:CURR:NPLC %g" % int_time)
        else:
                self.instr.write(":SENS:VOLT:NPLC %g" % int_time)
        self.__integtime__ = int_time

    def GetIntegrationtime(self):
        return self.__integtime__


# =============================================================================
# Keithley 2450 SourceMeter (LAN / USB / GPIB)
# =============================================================================

class DC_KEITHLEY_2450: #developer: Jeppe Surrow — 2450-specific SCPI commands
    # Compliance lives on the source side (SOUR:VOLT:ILIM / SOUR:CURR:VLIM).
    # Remote sense uses per-function commands (SENS:CURR:RSEN / SENS:VOLT:RSEN).
    # Default connection is LAN at 192.168.1.151 (VXI-11).

    def __init__(self, channel=21, GPIB_interface=-1, IP_address='192.168.1.151'):
        self.Meas = 'Volt'
        self.Source = 'Current'
        self.channel = channel
        self.__wire__ = None
        self.__integtime__ = None
        rm = visa.ResourceManager()
        if GPIB_interface > -1:
            resourceName = 'GPIB' + str(int(GPIB_interface)) + '::' + str(channel) + '::INSTR'
        else:
            resourceName = 'TCPIP0::' + IP_address + '::inst0::INSTR'
        self.instr = rm.open_resource(resourceName)
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.timeout = 10000
        alive = self.instr.query('*IDN?')
        if alive != 0:
            print('Keithley 2450 is alive')
            print(alive)
        time.sleep(1)
        self.IsOn = int(self.instr.query(':OUTP?'))
        if self.IsOn == 1:
            print('Source output is ON')
        else:
            if self.IsOn == 0:
                print('Source output is OFF')

    def SwitchOn(self):
        if int(self.instr.query(':OUTP?')) != 1:
            self.instr.write(':OUTP ON')
            print('Source output turned ON')
            self.IsOn = 1
        else: print('Source output was already ON')

    def SwitchOff(self):
        if int(self.instr.query(':OUTP?')) != 0:
            self.instr.write(':OUTP OFF')
            print('Source output turned OFF')
            self.IsOn = 0
        else: print('Source output was already OFF')

    def SetMeasCurr(self):
        self.instr.write(":SENS:FUNC 'CURR'")
        self.Meas = 'Current'

    def SetMeasVolt(self):
        self.instr.write(":SENS:FUNC 'VOLT'")
        self.Meas = 'Volt'

    def SetSourceVolt(self):
        self.instr.write('SOUR:FUNC VOLT')
        self.Source = 'Volt'

    def SetSourceValue(self, Value):
        if self.Source == 'Volt':
            self.instr.write('SOUR:VOLT ' + str(Value))
        elif self.Source == 'Current':
            self.instr.write('SOUR:CURR ' + str(Value))

    def SetSourceCurr(self):
        self.instr.write('SOUR:FUNC CURR')
        self.Source = 'Current'

    def SetCompliance(self, Compliance=0.05):
        # 2450: compliance is set on the source side, not the sense side
        if self.Source == 'Volt':
            self.instr.write('SOUR:VOLT:ILIM ' + str(Compliance))   # current limit (A)
        elif self.Source == 'Current':
            self.instr.write('SOUR:CURR:VLIM ' + str(Compliance))   # voltage limit (V)
        else:
            print('Source function undefined')

    def GetMeas(self):
        if self.Meas in ('Current', 'Volt'):
            Value = float((self.instr.query_ascii_values('READ?'))[0])
        else:
            print('Measurement function undefined')
            Value = 0
        return Value

    def WriteGPIB(self, string):
        self.instr.write(string)

    def QueryGPIB(self, string):
        return self.instr.query(string)

    def CloseConnection(self):
        self.instr.close()

    def SetMode(self, mode_string):
        # 'Voltage' → source 0 V, measure current (ammeter mode)
        # 'Current' → source 0 A, measure voltage
        # ATTENTION: performs *RST — resets compliance; call SetCompliance() afterwards if needed
        if mode_string == 'Voltage':
                self.instr.write("*RST;*CLS;*SRE 32;*ESE 1")
                self.instr.write(':SOUR:FUNC VOLT')
                self.instr.write('SOUR:VOLT:ILIM 0.01')   # 10 mA current limit
                self.instr.write(':SENS:CURR:RSEN OFF')    # 2-wire
                self.instr.write(':SENS:FUNC "CURR"')
                self.Source = 'Volt'
                self.Meas = 'Current'
                print('Keithley 2450: VOLTAGE source / CURRENT measure. Current limit = 10 mA, 2-wire.')

        elif mode_string == 'Current':
                self.instr.write("*RST;*CLS;*SRE 32;*ESE 1")
                self.instr.write(':SOUR:FUNC CURR')
                self.instr.write('SOUR:CURR:VLIM 20')     # 20 V voltage limit
                self.instr.write(':SENS:VOLT:RSEN OFF')    # 2-wire
                self.instr.write(':SENS:FUNC "VOLT"')
                self.Source = 'Current'
                self.Meas = 'Volt'
                print('Keithley 2450: CURRENT source / VOLTAGE measure. Voltage limit = 20 V, 2-wire.')

        else:
                raise AttributeError("SetMode requires 'Voltage' or 'Current', got '%s'" % str(mode_string))

    def GetMode(self):
        return self.Source

    def SetWire(self, wire):
        # 2450: remote sense is per-function, not a global SYST:RSEN switch
        if wire is None or wire == 'Two':
                self.instr.write(':SENS:CURR:RSEN OFF')
                self.instr.write(':SENS:VOLT:RSEN OFF')
                self.__wire__ = 'Two'
        elif wire == 'Four':
                if self.Source == 'Volt':
                        self.instr.write(':SENS:CURR:RSEN ON')
                else:
                        self.instr.write(':SENS:VOLT:RSEN ON')
                self.__wire__ = 'Four'
                print('Keithley 2450: 4-wire sensing enabled.')
        else:
                raise AttributeError("SetWire requires 'Two' or 'Four', got '%s'" % str(wire))

    def GetWire(self):
        return self.__wire__

    def SetIntegrationtime(self, int_time=1.00):
        #  integration time in power line cycles (NPLC): 0.01 (fast) to 10 (hi accuracy)
        if self.Meas == 'Current':
                self.instr.write(":SENS:CURR:NPLC %g" % int_time)
        else:
                self.instr.write(":SENS:VOLT:NPLC %g" % int_time)
        self.__integtime__ = int_time

    def GetIntegrationtime(self):
        return self.__integtime__

    def SetHighZVoltmeter(self, vlim=20, nplc=1.0):
        # High-impedance DC monitor (e.g. for the DC port of the bias tee): source 0 A, measure voltage.
        # The 2450 voltmeter input is >10 GOhm, so (almost) no current flows through the bias tee inductors.
        # NEVER source voltage into the bias tee DC port.  Output-off state is set to high impedance.
        # ATTENTION: performs *RST (via SetMode). Output is left OFF; call SwitchOn() afterwards.
        self.SetMode('Current')                       # *RST, source current, measure voltage, 2-wire
        self.instr.write(':SOUR:CURR 0')
        self.instr.write(':SOUR:CURR:VLIM ' + str(vlim))
        self.instr.write(':SENS:VOLT:RANG:AUTO ON')
        self.instr.write(':SENS:VOLT:NPLC ' + str(nplc))
        self.__integtime__ = nplc
        # Output-off state is stored per source function (2450 Ref. Manual, :OUTPut[1]:<function>:SMODe).
        # NORMAL (default) = 0 V source with a current limit, i.e. a near short on the bias tee DC port!
        self.instr.write(':OUTP:CURR:SMOD HIMP')      # output relay opens when the output is off
        self.instr.write(':OUTP:VOLT:SMOD HIMP')      # same for the voltage function, in case the function is changed
        self.AssertHighZ()
        print('Keithley 2450: HIGH-IMPEDANCE voltmeter mode (source 0 A, measure V, Vlim = %g V).' % vlim)

    def AssertHighZ(self):
        # Raises if the 2450 is not sourcing 0 A with the HIGH-Z output-off state. Call before connecting the bias tee.
        func = self.instr.query(':SOUR:FUNC?').strip().upper()
        amps = float(self.instr.query(':SOUR:CURR?'))
        offstate = self.instr.query(':OUTP:CURR:SMOD?').strip().upper()
        if not func.startswith('CURR') or amps != 0.0 or not offstate.startswith('HIMP'):
            raise RuntimeError('Keithley 2450 is NOT in 0 A high-impedance mode (SOUR:FUNC=%s, SOUR:CURR=%g, off-state=%s)'
                               % (func, amps, offstate))


#ELECTRICAL SPECTRUM ANALYZERS:#
class ESA_RS_FSW50:  # R&S FSW50 (USB product ID 0x00CB); formerly misnamed ESA_RS_FSV30

    def __init__(self,
                 channel=20,
                 GPIB_interface=-1,
                 IP_address='192.168.1.7',
                 spanFreq=1000,
                 centerFreq=15000,
                 videoBW=0.01,
                 resolutionBW=1,
                 dataPointsInSweep=100001,
                 sweepCount=1):
        self.channel = channel
        rm= visa.ResourceManager()
        
        if GPIB_interface == 'usb':
            resourceName = 'USB0::0x0AAD::0x00CB::101308::INSTR'
        
        elif GPIB_interface>-1: #Set GPIB_interface=0 to use GPIB instead of TCP/IP
            resourceName = 'GPIB'+str(int(GPIB_interface))+'::'+str(channel)+'::INSTR'

        else:
            resourceName ='TCPIP0::'+IP_address+'::inst0::INSTR'
            
        #print(rm.list_resources(),resourceName)
        self.instr = rm.open_resource(resourceName)
        alive = self.instr.query('*IDN?')
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.timeout = 10000
        #if alive != 0:
            #print('ESA_RS_FSW50 is alive')
            #print(alive)

        self.spanFreq = spanFreq
        self.centerFreq = centerFreq
        self.videoBW = videoBW
        self.resolutionBW = resolutionBW
        self.dataPointsInSweep = dataPointsInSweep
        self.sweepCount = sweepCount #Number of sweeps used for the traces. If the trace configuration "Average" is used, it also determines the number of averaging procedures. 
        
        #self.instr.write('*RST')                                #Reset
        self.instr.write('SYST:DISP:UPD ON')                    #Show on ESA display as well
        self.instr.write('INIT:CONT OFF')                       #Single sweep
        self.instr.write('BAND:AUTO OFF')
        self.instr.write('BAND:VID:AUTO OFF')

    def SetSpectrumParameters(self,spanFreq=1000,
                              centerFreq=15000,
                              videoBW=0.01,
                              resolutionBW=1,
                              dataPointsInSweep=100001,
                              sweepCount=1):
        self.spanFreq = spanFreq
        self.centerFreq = centerFreq
        self.videoBW = videoBW
        self.resolutionBW = resolutionBW
        self.dataPointsInSweep = dataPointsInSweep
        self.sweepCount = sweepCount
    
    def SetSpectrum(self):
        self.instr.clear()
        self.instr.write('FREQ:CENT '+str(self.centerFreq)+' MHz')   #Center frequency
        self.instr.write('FREQ:SPAN '+str(self.spanFreq)+' MHz')     #Frequency span
        self.instr.write('BAND '+str(self.resolutionBW)+' MHz')      #Resolution bandwidth
        self.instr.write('BAND:VID '+str(self.videoBW*1000)+' kHz')  #Video bandwidth
        self.instr.write('SWE:POIN '+str(int(self.dataPointsInSweep)))                    #Number of data points in sweep
        self.instr.write('SWE:COUN '+str(int(self.sweepCount)))       #Number of sweeps used in a trace.
        
        
    def ReadSpectrum(self):
        self.SetSpectrum()
        

        self.instr.write('INIT')                                #Start frequency sweep
        self.instr.query('*OPC?')                               #Wait until

        dataOut = np.array(self.instr.query_binary_values('FORM REAL,32;:TRAC? TRACE1'))
        
        freqAxis = (10**6)*np.arange(self.centerFreq-self.spanFreq/2,self.centerFreq+self.spanFreq/2,self.spanFreq/len(dataOut)) #Generate corresponding frequency axis

        return np.array([freqAxis,dataOut])  #Return x and y values, corresponding to frequency and power/res respectively
    
    def ReadDisplay(self, tracenumber=1):
        
        self.tracenumber = tracenumber
        dataOut = np.array(self.instr.query_binary_values(f'FORM REAL,32;:TRAC? TRACE{tracenumber}'))
        freqAxis = np.array(self.instr.query_binary_values(f'FORM REAL,32;:TRAC:X? TRACE{tracenumber}'))

        
        #freqAxis = (10**6)*np.arange(self.centerFreq-self.spanFreq/2,self.centerFreq+self.spanFreq/2,self.spanFreq/len(dataOut)) #Generate corresponding frequency axis

        return np.array([freqAxis,dataOut])  #Return x and y values, corresponding to frequency and power/res respectively

    def ReadPeakPower(self,Nread=5):
        power=[]
        for x in range(Nread): #Make "N" sweeps to make sure that no "dead" readouts are happening due to the instability of the heterodyne system.
            time.sleep(0.2)
            self.instr.clear()
            self.instr.write('FREQ:CENT '+str(self.centerFreq)+' MHz')   #Center frequency
            self.instr.write('FREQ:SPAN '+str(self.spanFreq)+' MHz')     #Frequency span
            self.instr.write('BAND '+str(self.resolutionBW)+' MHz')      #Resolution bandwidth
            self.instr.write('BAND:VID '+str(self.videoBW*1000)+' kHz')  #Video bandwidth
            self.instr.write('SWE:POIN '+str(int(self.dataPointsInSweep)))                 #Number of data points in sweep
            self.instr.write('SWE:COUN '+str(int(self.sweepCount)))       #Number of sweeps used in a trace.
        
    
            self.instr.write('INIT')                                #Start frequency sweep
            self.instr.query('*OPC?')                               #Wait until
    
            dataOut = np.array(self.instr.query_binary_values('FORM REAL,32;:TRAC? TRACE1'))
            self.last_trace = dataOut             #Trace of the last sweep, for saving
            power.append(np.max(dataOut)) #Record the maximum point on all 5 sweeps
        powermax=np.max(power)#Only pass on the maximum of the 5 peak values found
        return float(powermax)  #Return only the power value of the maximum within the sweep

    def ReadSpectrumPN(self):
        self.instr.clear()
        self.instr.write('INST:SEL PNO')
        self.instr.write('FREQ:STAR 10kHZ')
        self.instr.write('FREQ:STOP 1GHZ')
        self.instr.write('SWE:MODE NORM')
        self.instr.write('FREQ:TRAC ON')
        #self.instr.query_binary_values('FETC:PNO2:RPM?')

        self.instr.query('INIT;*WAI')                                #Start frequency sweep
        #self.instr.query('*OPC?')                               #Wait until

        dataOut = np.array(self.instr.query_binary_values('FORM REAL,32;:TRAC? TRACE1'))
        freqAxis = (10**6)*np.arange(self.centerFreq-self.spanFreq/2,self.centerFreq+self.spanFreq/2,self.spanFreq/len(dataOut)) #Generate corresponding frequency axis

        return [dataOut.tolist(),freqAxis.tolist()]  #Return x and y values, corresponding to frequency and power/res respectively

    def SetCoupling(self, coupling='DC'):
        # RF input coupling (FSW default is AC). WARNING (R&S FSW manual): with DC coupling you must protect the
        # input from DC voltage yourself - see the data sheet for the maximum DC voltage. AC coupling distorts very low frequencies.
        coupling = str(coupling).upper()
        if coupling not in ('AC', 'DC'):
            raise AttributeError("SetCoupling requires 'AC' or 'DC', got '%s'" % coupling)
        self.instr.write('INP:COUP ' + coupling)

    def GetCoupling(self):
        return self.instr.query('INP:COUP?').strip().upper()

    def ContDisplay(self):
        self.instr.write('INIT:CONT ON')

    def saveScreenshotToPC(self, local_path):
        """Save a PNG screenshot on the controlling PC (FSW manual: HCOPy:DEVice:LANGuage, MMEMory:NAME, HCOPy[:IMMediate]).

        The screenshot is printed to a temporary file on the instrument, read back with MMEMory:DATA? and deleted.
        """
        scope_tmp = 'C:\\R_S\\instr\\user\\screenshot_tmp.png'
        old_timeout = self.instr.timeout
        self.instr.timeout = 60000
        try:
            self.instr.write('HCOP:DEV:LANG PNG')
            self.instr.write("MMEM:NAME '" + scope_tmp + "'")
            self.instr.write('HCOP:IMM')
            self.instr.query('*OPC?')
            raw = self.instr.query_binary_values("MMEM:DATA? '" + scope_tmp + "'",
                                                 datatype='B', container=bytes)
        finally:
            self.instr.timeout = old_timeout
        try:
            self.instr.write("MMEM:DEL:IMM '" + scope_tmp + "'")
        except Exception:
            pass
        with open(local_path, 'wb') as f:
            f.write(raw)

    def CloseConnection(self):
        self.instr.close()

ESA_RS_FSV30 = ESA_RS_FSW50   # backward-compatible alias for old scripts

#%%

class LMS_ANDO_AQ4321A: #developer: Andreas  
    
    def __init__(self,channel=19,GPIB_interface=0):
        self.channel = channel
        rm= visa.ResourceManager()
        resourceName = 'GPIB'+str(int(GPIB_interface))+'::'+str(channel)+'::INSTR'
        self.instr = rm.open_resource(resourceName)
        alive = self.instr.query('*IDN?')
        #self.instr.read_termination = '\n'
        #self.instr.write_termination = '\n'
        self.instr.timeout = 10000
        if alive != 0:
            print('Ando AQ4321A is alive')
            print(alive)

    def Unlock(self, password=4321):
        #Does not work; manual password entry on startup is still needed;
        #this function is for locking the device and has nothng to do with the startup
        if str(self.instr.query('LOCK?')) == 1:
            self.instr.write('LOCK0 '+str(password));
            print('Device unlocked.');
        else: print('Device has already been unlocked.');
         
    def InitialiseDevice(self):
        #Not sure if this does anything
        self.instr.write('INIT');
        while (int(self.instr.query('INIT?'))  == 1):
            time.sleep(0.5);
        print('Device initialised.'); 
    
    def SetLaserState(self, onoff = 1):
        self.instr.write('L'+str(onoff));
        if (self.instr.query('L?') == 0): 
            print('Laser off')
        else:
            if (self.instr.query('L?') == 1): 
                print('Laser on');
                
    def SetPower(self, mW=5.0):
        self.instr.write('TPMW'+str(mW));
        
    def SetWL(self, nm=1550.0):
        self.instr.write('TWL'+str(nm));
        
    def WriteGPIB(self, string):
        self.instr.write(string);   
        
    def QueryGPIB(self, string):
        return self.instr.query(string);
        
    def CloseConnection(self):
        self.instr.close()

#%%

#The ANDO OSA (AQ6315A)
class ANDO_OSA:
    def __init__(self, channel=30, GPIB_interface=1):
        self.channel = channel
        rm = visa.ResourceManager()
        resourceName = 'GPIB' + str(int(GPIB_interface)) + '::' + str(channel) + '::INSTR'
        # print(rm.list_resources())
        self.instr = rm.open_resource(resourceName);
        self.instr.write('ATREF0');
        #self.instr.write('SMPL1001')
        #self.instr.write('SNAT')

        # alive = self.instr.query('*IDN?')
        # self.instr.read_termination = '\n'
        # self.instr.write_termination = '\n'
        # self.instr.timeout = 10000
        # if alive != 0:
        #    print('Ando AQ4321A is alive')
        #    # print(alive)

    def SetLeveldB(self, Level=-65.0):
        self.instr.write('REFL' + str(Level));  # in dBm XXX.X

    def SetLevelnW(self, Level=1.00):
        self.instr.write('REFN' + str(Level));  # in nW X.XX

    def SetLeveluW(self, Level=1.00):
        self.instr.write('REFU' + str(Level));  # in uW X.XX 0.01 --> 1 to 9.99, 0.1-->10 to 99.9,

    def SetLevelmW(self, Level=1.00):
        self.instr.write('REFM' + str(Level));  # in mW X.XX 0.01 --> 1 to 9.99, 0.1-->10 to 99.9

    def CenterWL(self, WL=450.0):
        self.instr.write('CTRWL' + str(WL));

    def SingleSweep(self):
        self.instr.write('SGL');

    def AutoSweep(self):
        self.instr.write('AUTO');

    def ContinousSweep(self):
        self.instr.write('RPT');

    def SetupOSA(self, CenterWL=950, Span=10, Level=0, Resolution=0.05, Sensitivity=0, Preview=0):
        self.instr.write('CTRWL' + str(CenterWL));  # in nm
        self.instr.write('SPAN' + str(Span));  # in nm
        self.instr.write('RESLN' + str(Resolution))  # in nm XX.XX
        if Sensitivity == 0:
            self.instr.write('SNAT');
        else:
            self.instr.write('SHI' + str(Sensitivity))

        if Level == 0:
            self.instr.write('ATREF1');
        else:
            self.instr.write('REFL' + str(Level));  # in dBm XXX.X
        if Preview == 1:
            self.instr.write('SGL');

    def Stop(self):
        self.instr.write('STP');

    def stop(self):
        self.instr.write('STP');

    def StopSweep(self):
        self.instr.write('STP');

    def GetSpectrum(self):
        # time.sleep(5)
        self.instr.write('SGL');
        self.instr.write('SD0')
        Status = 1
        StatusOut = []


        while Status == 1:
            Mode = self.instr.query('SWEEP?')[0:-2]  # Something is broken here... Check up on the output of mode
            Status = float(Mode)
            time.sleep(0.2)
            StatusOut.append(Status)

        Power = self.instr.query('LDATAR0001-R1001')

        # Power=Power.replace("−", "-")
        print(Power)
        PowerF = [float(value) for value in Power.split(',')]

        WL = self.instr.query('WDATAR0001-R1001')

        WLF = [float(value) for value in WL.split(', ')]
        return [PowerF[1:], WLF[1:]]


# %%
class FILT_WLTF: #developer: Lars Nielsen
    '''
    Class to control narrowband tunable band pass filter.
    '''
    def __init__(self,COMport=4):
        rm = visa.ResourceManager()
        resourceName = 'COM' + str(int(COMport))
        self.instr = rm.open_resource(resourceName)
        self.instr.read_termination = '\r\n'  
        self.instr.write_termination = '\r\n' 
        self.instr.baud_rate = 115200
        self.instr.timeout = 10000
        alive = self.instr.query('DEV?')

        if alive != 0:
            print('FILT_WLTF is alive')
            print(alive)
            #print(self.instr.read())
            
    def SetCenterWavelength(self,lambda0=1550.000,tries=10): # Take into accont an offset of 1 nm: Set the center to the desired WL minus 1 nm
        messageODL = 'NONE'
        messageODL = self.instr.query('WL'+ str(lambda0))
        i=0
        while not messageODL == 'OK':
            i=i+1
            #time.sleep(0.1)
            messageODL = self.instr.query('WL'+str(lambda0))
            #print(messageODL)
            if i==tries:
                print('Maximum number of write attempts reached. Try again.')	
        return messageODL

    def StepDiscrete(self,steps=1):
        if steps>0: #forward
            messageODL = self.instr.query('SF:'+str(int(steps)))
            if messageODL == 'OK':
                doNothing = 1
            else:
                print('Did not recieve an OK from FILT_WLTF - did not step!')	
        else: #backward
            messageODL = self.instr.query('SB:'+str(int(steps)))
            if messageODL == 'OK':
                doNothing = 1
            else:
                print('Did not recieve an OK from FILT_WLTF - did not step!')	
        return 1

    def GetCenterWavelength(self,tries=10):
        messageODL = 'NONE'
        i=0
        while not messageODL.startswith('Wavelength:'):
            time.sleep(1)
            i=i+1
            if i==tries:
                print('Maximum number of read attempts reached.')	
                lambda0 ='error'
                return lambda0
            messageODL = self.instr.query('WL?')
            #print(messageODL)
        lambda0  = float(messageODL[11:19])       
        return lambda0

    def CloseConnection(self):
        self.instr.close()
# %%

# Classes for the communication layer:#######################
# Needed for Yenista OSA20


class socketInstrument: #developer: Lars Nielsen
    def __init__(self,ip_address='192.168.1.3',tcp_port=5025,timeoutVal=120):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect((ip_address, tcp_port))
        self.s.settimeout(timeoutVal)

    def write(self,command='*IDN?'):
        self.s.send((command+"\r\n").encode())

    def read(self):
        endFlag = 0
        data = ''
        while endFlag==0:
            data=data+self.s.recv(1).decode()
            if data[-1]=='\n':
                break

        return data[:(len(data)-1)]
                
        
    def query(self,command):
        self.write(command)

        return self.read()

    def query_ascii_values(self,command):
        self.write(command)

        return np.array(self.read().split(',')).astype(float).tolist()

    def close(self):
        self.s.close()

# %%

class OSA_YENISTA_OSA20: #developer: Lars Nielsen, Andreas. Modified by Maria Paula Montes
    """
    - DESCRIPTION:
        This class is for controlling the Yenista OSA20

        channel : integer
            For choosing the GPIB channel of the GPIB communication.
            
        GPIB_interface : integer
            For choosing the GPIB interface of the GPIB communication. Set to -1 if ethernet communcation is used instead

        spanWave : float
            The span of the spectrum which is to be read from the instrument. Given in nanometers.

        centerWave : float
            The center wavelength of the spectrum which is to be read from the instrument. Given in nanometers.

        resolutionBW : float
            The resolution of the spectrum which is to be read from the instrument. Given in nanometers.

        sensitivity : int
            Chooses the dynamic sensitivity of the spectrum.
                1: -55 dBm (2000 nm/s) 
                2: -60 dBm (700 nm/s)
                3: -65 dBm (200 nm/s)
                4: -70 dBm (20 nm/s)
                5: -75 dBm (2 nm/s)
                6: High (0.5 nm/s)
                7: Burst

        ip_address : string
            Sets the ip address of the TCP IP commuication when ethernet is used.

        tcp_port : integer
            Sets the port of the TCP IP commuication when ethernet is used.
    """

    def __init__(self,channel=16,GPIB_interface=1,spanWave=60,centerWave=1535,resolutionBW=0.05,sensitivity=5,ip_address='192.168.1.3',tcp_port=5025):
        self.channel = channel
        rm= visa.ResourceManager()
        
        if GPIB_interface>-1:
            resourceName = 'GPIB'+str(int(GPIB_interface))+'::'+str(channel)+'::INSTR'
            self.instr = rm.open_resource(resourceName)
            self.instr.open()
        #elif GPIB_interface == 'usb':
            #resourceName = 'USB0::0x0AAD::0x00CB::101308::INSTR'
        elif GPIB_interface==-1:
            self.instr = socketInstrument(ip_address=ip_address,tcp_port=tcp_port)
                   
        alive = self.instr.query('*IDN?')
        #if alive != 0:
            #print('OSA_YENISTA_OSA20 is alive')
            #print(alive)

        #Initalization:
        self.instr.write(':OSA 1')              #OSA mode
        self.instr.write(':STOP')               #Make sure that no scan is running
        self.instr.write(':INIT:SMOD SING')     #Set single sweep mode
        self.instr.write(':DISP: ON')           #Show on OSA display as well
        self.instr.write(':CALC:AUTO ON')       #Calculations -> automatic

        self.spanWave = spanWave
        self.centerWave = centerWave
        self.resolutionBW = resolutionBW
        self.sensitivity = sensitivity        

    def StartMeasurement(self):
        self.instr.write(':INIT:IMM')                                               #Start frequency sweep
        #Ask OSA if measurement is done x20:
        count=0
        while int(self.instr.query(':STAT:OPER:COND?')): #Wait for 20 seconds or until the measurement is done
            time.sleep(1)                             
            count=count+1
            if count>20:
                break
        return 0; 
    
    def ReadSpectrumSimple(self):
        #Leaves OSA scanning parameters untouched
        #Works better for testing when there is no laser input 
        #Start OSA measurement:

        
        #Initilize parameters for trace fetch:
        dataOut = []
        waveAxis = []
        startTRACE = ( self.instr.query_ascii_values(':TRAC1:DATA:STAR?')[0] )*(10**9)
        lengthTRACE = int(self.instr.query_ascii_values(':TRAC1:DATA:LENG?')[0])
        sampTRACE = (self.instr.query_ascii_values(':TRAC1:DATA:SAMP?')[0] )*(10**9)
              
       #Fetch trace data:
        for i in range(lengthTRACE):
            waveAxis.append(startTRACE+i*sampTRACE)
        dataOut = self.instr.query_ascii_values(':TRAC1:DATA? 0,0')

        return np.array([waveAxis, dataOut]) #Return x-axis in nm and y-axis in W!

    def ReadSpectrum(self):
        #Set the OSA scanning parameters:
        self.instr.write(':SENS:WAV:CENT '+str(self.centerWave)+'NM')               #Center frequency
        self.instr.write(':SENS:WAV:SPAN '+str(self.spanWave)+'NM')                 #Frequency span
        self.instr.write(':SENS:BAND '+str(self.resolutionBW*(10**3))+'pm')         #Resolution bandwidth
        self.instr.write(':SENS '+str(self.sensitivity))

        #Start OSA measurement:
        self.instr.write(':INIT:IMM')                                               #Start frequency sweep
        #Ask OSA if measurement is done x20:
        count=0
        while int(self.instr.query(':STAT:OPER:COND?')): #Wait for 20 seconds or until the measurement is done
            time.sleep(1)                             
            count=count+1
            if count>20:
                break
        
        #Initilize parameters for trace fetch:
        dataOut = []
        waveAxis = []
        startTRACE = ( self.instr.query_ascii_values(':TRAC1:DATA:STAR?')[0] )*(10**9)
        lengthTRACE = int(self.instr.query_ascii_values(':TRAC1:DATA:LENG?')[0])
        sampTRACE = (self.instr.query_ascii_values(':TRAC1:DATA:SAMP?')[0] )*(10**9)
              
       #Fetch trace data:
        for i in range(lengthTRACE):
            waveAxis.append(startTRACE+i*sampTRACE)
        dataOut = self.instr.query_ascii_values(':TRAC1:DATA? 0,0')

        return [waveAxis, dataOut] #Return x-axis in nm and y-axis in dBm

    #### Andreas


    def ReadPeakData(self):
        #returns dictionary; dictionaries are pythons version of structures
        self.instr.write(':CALC:PAR:SMSR ON');
        
        FullString = self.instr.query(":CALC:DATA:SMSR?")
        SplitString = FullString.split(','); #splits into array; sep: comma
        
        
        try:
            PWL = float(SplitString[5])
        except:
            PWL = 0
        try:
            PL = float(SplitString[8])
        except:
            PL = 0           
        try:
            S1WL = float(SplitString[14])
        except:
            S1WL = 0            
        try:
            S1L = float(SplitString[17])
        except:
            S1L = 0            
        try:
            S1DWL = float(SplitString[20])
        except:
            S1DWL = 0  
        try:
            S1SMSR = float(SplitString[23])
        except:
            S1SMSR = 0            
        try:
            S2WL = float(SplitString[29])
        except:
            S2WL = 0            
        try:
            S2L = float(SplitString[32])
        except:
            S2L = 0
        try:
            S2DWL = float(SplitString[35])
        except:
            S2DWL = 0            
        try:
            S2SMSR = float(SplitString[38])
        except:
            S2SMSR = 0
            
        ReturnDict = {
        'Peak_WL' : PWL,
        'Peak_WL_Unit' : SplitString[6], #physical unit used; e.g. m
        'Peak_Level' : PL,
        'Peak_Level_Unit' : SplitString[9],
        'SideMode1_WL' : S1WL,
        'SideMode1_WL_Unit' : SplitString[15],
        'SideMode1_Level' : S1L,
        'SideMode1_Level_Unit' : SplitString[18],
        'SideMode1_DiffWL' : S1DWL,
        'SideMode1_DiffWL_Unit' : SplitString[21],
        'SideMode1_SMSR' : S1SMSR,
        'SideMode1_SMSR_Unit' : SplitString[24],
        'SideMode2_WL' : S2WL,
        'SideMode2_WL_Unit' : SplitString[30],
        'SideMode2_Level' : S2L,
        'SideMode2_Level_Unit' : SplitString[33],
        'SideMode2_DiffWL' : S2DWL,
        'SideMode2_DiffWL_Unit' : SplitString[36],
        'SideMode2_SMSR' : S2SMSR,
        'SideMode2_SMSR_Unit' : SplitString[39]
        }
        return ReturnDict;
        # Peak_WL = ReturnDict['Peak_WL']
        
    def ReadValue(self, Value='Peak_WL'):
        ReturnDict=self.ReadPeakData()
        return ReturnDict[Value]
        #return ReturnDict.get(Value)
    
    def WriteGPIB(self, string):
        self.instr.write(string);    
        
    def QueryGPIB(self, string):
        return self.instr.query(string); 
    
    def CloseConnection(self):
        self.instr.close()

# %%
# OSW22 - 2x2 fiber optical MEMS switch   
class OSW22: #developer: Hanna Becker status 16-11-2020
 
    def __init__(self,COMport=5):
        rm= visa.ResourceManager()
        resourceName = 'COM'+str(int(COMport))
        #print(resourceName)
        self.instr = rm.open_resource(resourceName,baud_rate=115200)
        self.instr.read_termination = '\r'
        self.instr.write_termination = '\n'
        self.instr.timeout = 10000
        alive = self.instr.query("I?")
        if alive != 0:
            #print('OSW22 is alive')
            print(alive)
             
    def Switch1(self): # switch to "1" switch configuration
        self.instr.write("S 1")
        print('OSW22 switched to'+str(self.instr.query("S?")))
         
    def Switch2(self): # switch to "2" switch configuration
        self.instr.write("S 2");
        print('OSW22 switched to'+str(self.instr.query("S?")))
         
    def Switch212(self):
        #initial state must be "2"
        self.instr.write("S 1\n S 1\n S 2");
        print('OSW22 switch opened')
        # ultrashort opening of "S 1\n S 2" does often not lead to full opening of switch
        # "S 1\n S 1\n S 2" in single command line, leads to more or less stable opening window of 0.7-0.8ms
 
    def Switch121(self):
        #initial state must be "1"
        self.instr.write("S 2\n S 2\n S 1");
        print('OSW22 switch opened') 
 
    def Switch212b(self):
        #initial state must be "2"
        self.instr.write("S 1");
        time.sleep(0.1) # switch opening time now heavily dependent on communication speed and not intrinsic switch speed (variations between 1.0-1.3 ms observed)
        self.instr.write("S 2");
        print('OSW22 switch opened')
 
    def CloseConnection(self):
        self.instr.close()
        print('OSW22 connection closed')

# =============================================================================
# R&S RTO1024 Oscilloscope
# =============================================================================

class RTO1024:
    """Rohde & Schwarz RTO1024 oscilloscope over Ethernet.

    Parameters
    ----------
    IP_address : str
        Instrument IP address on the local network.
    """

    def __init__(self, IP_address='192.168.1.87'):
        rm = visa.ResourceManager()
        resourceName = 'TCPIP0::' + IP_address + '::hislip0::INSTR'
        self.instr = rm.open_resource(resourceName)
        self.instr.timeout = 30000
        alive = self.instr.query('*IDN?')
        if alive:
            print('RTO1024 is alive')
            print(alive)
        self.instr.write('SYSTem:DISPlay:UPDate ON')

    def setupEyeDiagram(self, signal_channel=1, trigger_source='CH2',
                        time_scale=2e-9, volt_scale=0.2,
                        signal_offset=0.0, clock_offset=0.0,
                        trigger_level=2.0, clock_volt_scale=1.0,
                        persistence_time=10):
        """Configure the oscilloscope to display an eye diagram.

        Connect the PRBS data signal to signal_channel and the SDG6022X
        clock output to the trigger_source channel (or EXT input).
        Timed persistence accumulates successive bit-period waveforms
        into an eye pattern.

        Parameters
        ----------
        signal_channel : int
            Channel receiving the PRBS / modulated signal.
        trigger_source : str
            Trigger input: 'CH1', 'CH2', 'CH3', 'CH4', or 'EXT'.
        time_scale : float
            Horizontal scale in seconds per division. 20 ns/div shows
            ~2 bit periods at 100 Mbps.
        volt_scale : float
            Vertical scale in V/div for the signal channel.
        trigger_level : float
            Trigger threshold for the clock channel in V. For a 0–3.3 V
            clock the midpoint is 1.65 V; 2.0 V gives clean rising-edge
            triggering.
        clock_volt_scale : float
            Vertical scale in V/div for the clock channel. 1.0 V/div
            shows the full 3.3 V swing with headroom.
        persistence_time : float
            Persistence display duration in seconds (10 s is sufficient
            for visual accumulation).
        """
        ch = str(signal_channel)

        # Extract trigger channel number from 'CH2' -> '2'
        trig_ch_num = trigger_source.replace('CH', '')
        trig_src_rto = 'CHAN' + trig_ch_num if trigger_source.startswith('CH') else trigger_source

        # Signal channel
        self.instr.write('CHANnel' + ch + ':STATe ON')
        self.instr.write('CHANnel' + ch + ':SCALe ' + str(volt_scale))
        self.instr.write('CHANnel' + ch + ':OFFSet ' + str(signal_offset))

        # Clock / trigger channel
        if trigger_source.startswith('CH'):
            self.instr.write('CHANnel' + trig_ch_num + ':STATe ON')
            self.instr.write('CHANnel' + trig_ch_num + ':SCALe ' + str(clock_volt_scale))
            self.instr.write('CHANnel' + trig_ch_num + ':OFFSet ' + str(clock_offset))

        # Timebase — position 0 centres the trigger event on screen
        self.instr.write('TIMebase:SCALe ' + str(time_scale))
        self.instr.write('TIMebase:POSition 0')

        # Trigger — this scope uses TRIGger1:* (TRIGger:A:* times out on RTO firmware 3.70)
        self.instr.write('TRIGger1:SOURce ' + trig_src_rto)
        self.instr.write('TRIGger1:LEVel' + trig_ch_num + ' ' + str(trigger_level))
        self.instr.write('TRIGger1:EDGE:SLOPe POSitive')
        self.instr.write('TRIGger1:MODE NORMal')

        self.instr.write('DISPlay:PERSistence ON')
        self.instr.write('DISPlay:PERSistence:TIME ' + str(persistence_time))

        self.instr.write('RUN')

    def clearPersistence(self):
        """Clear the infinite-persistence display."""
        self.instr.write('DISPlay:PERSistence:RESet')

    def run(self):
        self.instr.write('RUN')

    def stop(self):
        self.instr.write('STOP')

    def single(self):
        """Trigger a single acquisition and wait for completion."""
        self.instr.write('SINGle')
        self.instr.query('*OPC?')

    def getWaveform(self, channel=1):
        """Read waveform data from the specified channel.

        Returns
        -------
        time_axis : np.ndarray
            Sample times in seconds.
        voltage : np.ndarray
            Voltage samples in V.
        """
        ch = str(channel)
        # Ensure single-channel export so CHANnel<n>:DATA? returns only this channel.
        # When MULTichannel is ON the scope returns all active channels interleaved.
        self.instr.write('EXPort:WAVeform:MULTichannel OFF')

        header = self.instr.query('CHANnel' + ch + ':DATA:HEADer?')
        parts = header.strip().split(',')
        t_start = float(parts[0])
        t_stop = float(parts[1])

        # REAL,32 carries the full HD 16-bit word as well (24-bit mantissa)
        self.instr.write('FORMat REAL,32')
        voltage = np.array(self.instr.query_binary_values('CHANnel' + ch + ':DATA?',
                                                          datatype='f'))
        # Header gives the acquisition window [start, stop); the sample interval
        # is (stop - start)/N. np.linspace(start, stop, N) would stretch it by N/(N-1).
        dt = (t_stop - t_start) / len(voltage)
        time_axis = t_start + np.arange(len(voltage)) * dt
        return time_axis, voltage

    # ------------------------------------------------------------------
    # Resolution helpers (vertical ADC levels, HD mode, sample rate)
    # ------------------------------------------------------------------

    def _query_or(self, cmd, default=None, timeout_ms=3000):
        """Query with a short timeout; return default if unsupported."""
        old = self.instr.timeout
        self.instr.timeout = timeout_ms
        try:
            return self.instr.query(cmd).strip()
        except Exception:
            try:
                self.instr.clear()
            except Exception:
                pass
            return default
        finally:
            self.instr.timeout = old

    def getOptions(self):
        """Installed options (*OPT?) as a list of strings, e.g. ['K17', 'B200']."""
        resp = self._query_or('*OPT?', '') or ''
        return [o.strip().strip('"') for o in resp.split(',')
                if o.strip().strip('"') not in ('', '0')]

    def hasHighDefinition(self):
        """True if option R&S RTO-K17 (High Definition mode) is installed."""
        return any(o.upper().endswith('K17') for o in self.getOptions())

    def setHighDefinition(self, state=True, bandwidth=None):
        """Enable/disable High Definition mode (option K17).

        HD applies a digital low-pass filter after the 8-bit ADC and gives up
        to 16-bit resolution (lower bandwidth -> more bits). In HD mode the
        sample rate is halved and the per-channel BANDwidth setting is
        replaced by the HD filter bandwidth (max 1 GHz for >= 1 GHz models).

        Returns
        -------
        (enabled : bool, eff_bits : float)
            eff_bits is HDEFinition:RESolution? when enabled, else 8.0.
        """
        if not self.hasHighDefinition():
            if state:
                print('  HD mode requested but option K17 is not installed — using 8-bit.')
            return False, 8.0
        if state:
            self.instr.write('HDEFinition:STATe ON')
            if bandwidth:
                self.instr.write(f'HDEFinition:BWIDth {float(bandwidth):.0f}')
        else:
            self.instr.write('HDEFinition:STATe OFF')
        self.instr.query('*OPC?')
        on = self._query_or('HDEFinition:STATe?', '0') in ('1', 'ON')
        bits = 8.0
        if on:
            try:
                bits = float(self._query_or('HDEFinition:RESolution?', 'nan'))
            except ValueError:
                bits = float('nan')
            bw = self._query_or('HDEFinition:BWIDth?', '?')
            print(f'  HD mode ON: filter bandwidth {bw} Hz, resolution {bits} bit')
        else:
            print('  HD mode OFF: 8-bit ADC resolution')
        return on, bits

    def getHighDefinition(self):
        """Current (enabled, eff_bits, bandwidth_Hz) without changing anything."""
        if not self.hasHighDefinition():
            return False, 8.0, None
        on = self._query_or('HDEFinition:STATe?', '0') in ('1', 'ON')
        if not on:
            return False, 8.0, None
        try:
            bits = float(self._query_or('HDEFinition:RESolution?', 'nan'))
            bw = float(self._query_or('HDEFinition:BWIDth?', 'nan'))
        except ValueError:
            bits, bw = float('nan'), None
        return True, bits, bw

    def getVerticalInfo(self, channel, hd_state=None):
        """Vertical settings and resulting ADC level spacing for a channel.

        From the RTO manual (raw data conversion, p. 462):
            step = VerticalScale * 10 div / 253           (8 bit)
            step = VerticalScale * 10 div / (253 * 256)   (HD, 16-bit words)
        The effective HD resolution (fewer bits than the word) is
        HDEFinition:RESolution?. The ADC range is offset ± 5 div.
        """
        ch = str(channel)
        scale = float(self.instr.query(f'CHANnel{ch}:SCALe?'))
        offset = float(self.instr.query(f'CHANnel{ch}:OFFSet?'))
        pos = self._query_or(f'CHANnel{ch}:POSition?', 'nan')
        hd, bits, _ = hd_state if hd_state else self.getHighDefinition()
        step8 = scale * 10 / 253
        return dict(channel=int(channel),
                    volt_scale_V_per_div=scale,
                    offset_V=offset,
                    position_div=float(pos),
                    hd_mode=hd,
                    adc_bits_effective=bits,
                    adc_word_step_V=step8 / 256 if hd else step8,
                    adc_range_min_V=offset - 5 * scale,
                    adc_range_max_V=offset + 5 * scale)

    def getMaxRealSampleRate(self, hd=None):
        """Highest real-time (non-interpolated) sample rate [Sa/s].

        ADC rate from ACQuire:POINts:ARATe? (10 GSa/s on the RTO1024),
        halved in HD mode.
        """
        try:
            adc = float(self._query_or('ACQuire:POINts:ARATe?', '10e9'))
        except ValueError:
            adc = 10e9
        if hd is None:
            hd = self.getHighDefinition()[0]
        return adc / 2 if hd else adc

    def acquireLongWaveform(self, channel=1, n_periods=10000, bit_rate=20e6,
                            volt_scale=0.4, record_length=None,
                            extra_channels=None, real_time=True):
        """Acquire a long waveform for time-series and eye diagram analysis.

        Disables the automatic record-length mode (which otherwise locks the scope
        to screen-resolution ~2000 pts), sets record_length explicitly, then
        restores both settings after the acquisition.

        Parameters
        ----------
        n_periods : int
            Number of bit periods to capture (sets the time window).
        record_length : int or None
            Number of samples to acquire. None (default) = the maximum
            real-time sample rate over the window (10 GSa/s, or 5 GSa/s in
            HD mode). Larger values are capped to that, so no interpolated
            points are recorded.
        extra_channels : list of int, optional
            Additional channel numbers to read from the same acquisition.
            Returns a dict {ch: (t, v)} as a third return value when provided.
        real_time : bool
            Use ACQuire:MODE RTIMe (only real ADC samples, no interpolation)
            during the acquisition; the previous mode is restored afterwards.

        After the call, self.last_acquisition holds sample interval, sample
        rate, HD state and per-channel vertical info (see getVerticalInfo).
        """
        ch = str(channel)
        long_time_scale = n_periods / (bit_rate * 10)
        window = 10 * long_time_scale

        # Save originals
        orig_time_scale = self.instr.query('TIMebase:SCALe?').strip()
        orig_auto       = self.instr.query('ACQuire:POINts:AUTO?').strip()
        orig_mode       = self._query_or('ACQuire:MODE?')

        self.instr.write('DISPlay:PERSistence OFF')
        if real_time:
            self.instr.write('ACQuire:MODE RTIMe')

        hd_state = self.getHighDefinition()
        max_rate = self.getMaxRealSampleRate(hd=hd_state[0])
        max_pts = int(round(window * max_rate))
        max_pts -= max_pts % 2                      # increment is 2
        if record_length is None or record_length > max_pts:
            if record_length is not None:
                print(f'  Record length {record_length:,} exceeds the real-time maximum '
                      f'({max_rate/1e9:.3g} GSa/s × {window*1e6:.1f} µs) — using {max_pts:,}.')
            record_length = max_pts

        # Time scale MUST be set before ACQuire:POINts — the scope rejects a record
        # length that would require a sample rate above its hardware maximum at the
        # current time scale and silently keeps the old value.
        self.instr.write('TIMebase:SCALe ' + str(long_time_scale))
        self.instr.write('ACQuire:POINts ' + str(record_length))
        actual_pts = self.instr.query('ACQuire:POINts?').strip()
        res = self._query_or('ACQuire:RESolution?')
        print(f'  Record length: requested {record_length:,}, scope accepted {actual_pts}'
              + (f', sample interval {float(res)*1e12:.1f} ps' if res else ''))

        self.instr.write('CHANnel' + ch + ':SCALe ' + str(volt_scale))
        self.instr.write('SINGle')
        self.instr.query('*OPC?')
        t, v = self.getWaveform(channel)

        extra = {}
        if extra_channels:
            for ch_extra in extra_channels:
                t_e, v_e = self.getWaveform(ch_extra)
                extra[ch_extra] = (t_e, v_e)

        # Record what the data actually is (read before restoring settings)
        hd, bits, hd_bw = hd_state
        dt = float(t[1] - t[0]) if len(t) > 1 else float('nan')
        vinfo = {int(c): self.getVerticalInfo(c, hd_state=hd_state)
                 for c in [channel] + list(extra_channels or [])}
        self.last_acquisition = dict(
            sample_interval_s=dt,
            sample_rate_Sa_s=1.0 / dt if dt else float('nan'),
            max_real_sample_rate_Sa_s=max_rate,
            acquire_mode='RTIMe' if real_time else orig_mode,
            record_length=len(t),
            hd_mode=hd, hd_resolution_bits=bits, hd_bandwidth_Hz=hd_bw,
            vertical=vinfo)

        # Restore
        self.instr.write('ACQuire:POINts:AUTO ' + orig_auto)
        self.instr.write('TIMebase:SCALe ' + orig_time_scale)
        if real_time and orig_mode:
            self.instr.write('ACQuire:MODE ' + orig_mode)
        print(f'  Got {len(t):,} samples, '
              f'{(t[-1]-t[0])*1e6:.1f} µs ({(t[-1]-t[0])*bit_rate:.0f} bit periods), '
              f'{len(t)/((t[-1]-t[0])*bit_rate):.0f} samples/period')

        if extra_channels:
            return t, v, extra
        return t, v

    def saveScreenshot(self, filepath='C:\\eye_diagram.png'):
        """Save a PNG screenshot to the scope's own file system."""
        self.instr.write('HCOPy:DESTination "FILE"')
        self.instr.write('HCOPy:FORMat PNG')
        self.instr.write('HCOPy:FILE "' + filepath + '"')
        self.instr.write('HCOPy:IMMediate')
        self.instr.query('*OPC?')

    def saveScreenshotToPC(self, local_path):
        """Transfer a PNG screenshot over VISA and save it on the controlling PC.

        Saves to scope's internal disk first (MMEM), retrieves via MMEMory:DATA?,
        then deletes the temp file. This is the correct approach per the RTO1024 manual
        — DESTination "BUS" / HCOPy:DATA? does not exist on this instrument.
        """
        scope_tmp = 'C:\\rto_screenshot_tmp.png'
        old_timeout = self.instr.timeout
        self.instr.timeout = 60000
        try:
            self.instr.write("HCOPy:DESTination 'MMEM'")
            self.instr.write("HCOPy:DEVice:LANGuage PNG")
            self.instr.write("MMEMory:NAME '" + scope_tmp + "'")
            self.instr.write('HCOPy:IMMediate')
            self.instr.query('*OPC?')
            raw = self.instr.query_binary_values(
                "MMEMory:DATA? '" + scope_tmp + "'",
                datatype='B', container=bytes)
        finally:
            self.instr.timeout = old_timeout
        try:
            self.instr.write("MMEMory:DELete '" + scope_tmp + "'")
        except Exception:
            pass
        with open(local_path, 'wb') as f:
            f.write(raw)

    def closeConnection(self):
        self.instr.close()

# =============================================================================
# Siglent SDS2000X-E Oscilloscope (e.g. SDS2352X-E)
# =============================================================================

class SCOPE_SIGLENT_SDS:  #developer: Jeppe Surrow. Commands from the Siglent SDS programming guide PG01-E02B
    """Siglent SDS2000X-E oscilloscope over LAN (VXI-11) or any VISA resource string.

    Waveforms are read as raw 8-bit codes (C1:WF? DAT2) and converted with
        volt = code * vdiv / 25 - offset
    The input is 1 MOhm: terminate the signal with an external 50 ohm feed-through
    if a 50 ohm load is required.

    Parameters
    ----------
    IP_address : str
        Instrument IP address (used if resource is None).
    resource : str
        Full VISA resource string, e.g. 'USB0::0xF4EC::...::INSTR'.
    """

    # discrete settings from the programming guide (TIME_DIV: 1 ns ... 100 s, VOLT_DIV: 500 uV ... 10 V)
    TDIV_LIST = [m * 10.0 ** e for e in range(-9, 2) for m in (1, 2, 5)] + [100.0]
    VDIV_LIST = [m * 10.0 ** e for e in range(-4, 1) for m in (1, 2, 5)][2:] + [10.0]

    def __init__(self, IP_address=None, resource=None):
        rm = visa.ResourceManager()
        if resource is None:
            if IP_address is None:
                raise ValueError('Give IP_address or resource')
            resource = 'TCPIP0::' + IP_address + '::inst0::INSTR'
        self.instr = rm.open_resource(resource)
        self.instr.timeout = 30000
        self.instr.chunk_size = 20 * 1024 * 1024   # waveform blocks are large (default 20 kB)
        self.instr.write('CHDR OFF')                # numbers only, no header/units in replies
        alive = self.instr.query('*IDN?').strip()
        if alive:
            print('SCOPE_SIGLENT_SDS is alive')
            print(alive)
        self.idn = alive
        self.vdiv = {}
        self.offset = {}

    @staticmethod
    def _num(text):
        """First number in a reply, with optional k/K/M/G suffix (e.g. '5.00E+08', '1.00GSa/s', '140K')."""
        m = re.search(r'([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*([kKMG]?)', str(text))
        if not m:
            raise ValueError('No number in reply: %r' % (text,))
        return float(m.group(1)) * {'': 1.0, 'k': 1e3, 'K': 1e3, 'M': 1e6, 'G': 1e9}[m.group(2)]

    @classmethod
    def nearest_vdiv(cls, vdiv, round_up=True):
        """Smallest allowed V/div >= vdiv (or the nearest below if round_up is False)."""
        vals = [v for v in cls.VDIV_LIST if (v >= vdiv * 0.9999 if round_up else v <= vdiv * 1.0001)]
        return (min(vals) if round_up else max(vals)) if vals else (cls.VDIV_LIST[-1] if round_up else cls.VDIV_LIST[0])

    @classmethod
    def nearest_tdiv(cls, tdiv):
        """Smallest allowed time/div >= tdiv."""
        vals = [t for t in cls.TDIV_LIST if t >= tdiv * 0.9999]
        return min(vals) if vals else cls.TDIV_LIST[-1]

    def SetChannel(self, channel=1, coupling='D1M', vdiv=0.1, offset=0.0, bandwidth_limit=False, attenuation=1):
        # coupling: 'A1M','D1M' (1 MOhm AC/DC) or 'GND'; 50 ohm options (A50/D50) only exist on some models
        ch = 'C' + str(channel)
        self.instr.write(ch + ':TRA ON')
        self.instr.write(ch + ':ATTN ' + str(attenuation))
        self.instr.write(ch + ':CPL ' + coupling)
        got = self.instr.query(ch + ':CPL?').strip()
        if coupling.upper() not in got.upper():
            raise RuntimeError('Scope coupling is "%s", wanted %s' % (got, coupling))
        self.instr.write('BWL ' + ch + ',' + ('ON' if bandwidth_limit else 'OFF'))
        self.SetVertical(channel, vdiv, offset)

    def SetVertical(self, channel=1, vdiv=0.1, offset=0.0):
        ch = 'C' + str(channel)
        self.instr.write(ch + ':VDIV ' + str(vdiv))
        self.instr.write(ch + ':OFST ' + str(offset))
        self.vdiv[channel] = self._num(self.instr.query(ch + ':VDIV?'))
        self.offset[channel] = self._num(self.instr.query(ch + ':OFST?'))
        return self.vdiv[channel], self.offset[channel]

    def SetTimebase(self, tdiv, memory_depth=None):
        self.instr.write('TDIV ' + ('%g' % tdiv) + 'S')
        if memory_depth is not None:
            self.instr.write('MSIZ ' + str(memory_depth))
        self.instr.write('TRDL 0S')
        self.instr.write('ACQW SAMPLING')
        self.instr.query('*OPC?')   # let the scope finish reconfiguring
        self.tdiv = self._num(self.instr.query('TDIV?'))
        return self.tdiv

    def GetAcquisitionInfo(self, channel=1):
        sara = self._num(self.instr.query('SARA?'))
        npts = self._num(self.instr.query('SANU? C' + str(channel)))
        return {'sample_rate_Sa_s': sara, 'points': npts, 'tdiv': self._num(self.instr.query('TDIV?')),
                'memory_depth': self.instr.query('MSIZ?').strip()}

    def Run(self):
        self.instr.write('TRMD AUTO')

    def Stop(self):
        self.instr.write('STOP')

    def Acquire(self, channel=1, wait=None):
        """Free-run until a NEW acquisition has completed, stop, and read the stopped record of one channel.

        'Acquisition done' = INR bit 0 'new signal acquired'. INR? reads and clears it, so it is cleared first.
        `wait` is only the time-out of the polling (default: at least 1 s).
        """
        tdiv = self._num(self.instr.query('TDIV?'))
        if wait is None:
            wait = max(1.0, 20 * 14 * tdiv)
        self.instr.query('INR?')                       # clear 'new signal acquired'
        self.instr.write('TRMD AUTO')
        t0 = time.time()
        self.acq_done = False
        while time.time() - t0 < wait:
            time.sleep(0.05)
            if int(self._num(self.instr.query('INR?'))) & 1:
                self.acq_done = True
                break
        self.instr.write('STOP')
        self.instr.query('*OPC?')
        time.sleep(0.1)
        return self.ReadStopped(channel)

    def ReadStopped(self, channel=1, npts=None):
        ch = 'C' + str(channel)
        vdiv = self._num(self.instr.query(ch + ':VDIV?'))
        ofst = self._num(self.instr.query(ch + ':OFST?'))
        sara = self._num(self.instr.query('SARA?'))
        # NP,0 = all available points (SDS2000X-E programming guide, WFSU command)
        self.instr.write('WFSU SP,1,NP,0,FP,0')
        time.sleep(0.05)
        self.instr.write(ch + ':WF? DAT2')
        raw = self.instr.read_raw()
        # reply: [header]#<n><n-digit length><data...>\n\n  (header absent/present depending on CHDR)
        if b'#' not in raw:
            print('  DEBUG WF? raw (first 100 bytes): %r' % raw[:100])
            return np.array([], dtype=np.int8), vdiv, ofst, 1.0 / sara
        i = raw.index(b'#')
        ndig = int(raw[i + 1:i + 2])
        length = int(raw[i + 2:i + 2 + ndig])
        data = raw[i + 2 + ndig:i + 2 + ndig + length]
        if len(data) != length:
            raise RuntimeError('Waveform block truncated: got %d of %d bytes' % (len(data), length))
        codes = np.frombuffer(data, dtype=np.int8)   # two's complement 8-bit
        return codes, vdiv, ofst, 1.0 / sara

    def Diagnose(self, channel=1):
        """Raw replies of the scope's acquisition state (for error messages)."""
        out = {}
        for q in ('SAST?', 'TRMD?', 'TDIV?', 'SARA?', 'MSIZ?', 'SANU? C%d' % channel, 'WFSU?'):
            try:
                out[q] = self.instr.query(q).strip()
            except Exception as e:
                out[q] = 'ERR %s' % e
        return out

    def getWaveform(self, channel=1):
        """Acquire and return (time_axis [s], voltage [V]); same call signature as RTO1024.getWaveform."""
        codes, vdiv, ofst, dt = self.Acquire(channel)
        volt = codes.astype(float) * vdiv / 25.0 - ofst
        return np.arange(len(volt)) * dt, volt

    def saveScreenshotToPC(self, local_path):
        """Save the screen as a BMP file on the controlling PC (SCDP query, SDS programming guide 'PRINT Commands')."""
        old_timeout = self.instr.timeout
        self.instr.timeout = 60000
        try:
            self.instr.write('SCDP')
            raw = self.instr.read_raw()
        finally:
            self.instr.timeout = old_timeout
        i = raw.find(b'BM')
        raw = raw[i:] if 0 <= i < 64 else raw      # BMP signature (drops any text header)
        with open(local_path, 'wb') as f:
            f.write(raw)

    def closeConnection(self):
        self.instr.close()
