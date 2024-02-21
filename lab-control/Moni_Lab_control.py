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
from datetime import datetime
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


def datetimestring():
    now = datetime.now()
    datestring =  now.strftime('%Y-%m-%d_%H-%M-%S')
    return datestring

def change_folder(my_path, data_folder_name):
    old_directory = os.getcwd()
    print("\nYour current working directory is:\n {0}\n".format(old_directory))
    try:
        my_directory_aux = os.path.join(my_path,
                                        'Measurements_' + datestring())
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
        TosaB = clr.AddReference(dll_file)
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
            if value > 250:
                raise ValueError('Max current is 250 mA')
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
    O:\ST_Photonics\Literature\Manuals_hardware\Keysight 86120B Multi-Wavelength Meter.pdf
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

        if alive != 0:
            print('OSA_YOKOGAWA is alive')
            print(alive)

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
        # Start OSA measurement:
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
                 lambda0=1550,PM_index=0):
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

    

    def closeConnection(self):
        self.PDinstr.close()

    def GetPower(self):
        power = c_double()
        pU = c_int16()
        lam0 = c_double()
        self.PDinstr.setAvgTime(c_double(0.005))
        self.PDinstr.measPower(byref(power))
        self.PDinstr.getPowerUnit(byref(pU))
        self.PDinstr.getPhotodiodeResponsivity(c_int16(0), byref(lam0))
        time.sleep(0.01)
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
                 ):
        
        self.frequency = frequency
        self.vpp = vpp
        self.waveform = waveform
        self.channel = channel
        self.offset = offset
        
        rm = visa.ResourceManager()
        resourceName ='TCPIP0::' + IP_address + '::inst0::INSTR'
        self.instr = rm.open_resource(resourceName)
        alive = self.instr.query('*IDN?')
        
        self.instr.write('C' + str(channel) + ':BSWV WVTP,' + waveform )
        self.instr.write('C' + str(channel) + ':BSWV FRQ,' + str(frequency))  # hz
        self.instr.write('C' + str(channel) + ':BSWV AMP,' + str(vpp))  # Vpp
        self.instr.write('C' + str(channel) + ':BSWV OFST,-' + str(offset))
        
        if alive != 0:
            print('AFG_SIGLENT is alive')
            print(alive)
            
    def setParameters(self,
                      channel=1,
                      waveform='SINE',
                      frequency=120000000,
                      vpp=1.8,
                      offset=0):
    
        self.instr.write('C' + str(channel) + ':BSWV WVTP,' + waveform )
        self.instr.write('C' + str(channel) + ':BSWV FRQ,' + str(frequency))  # hz
        self.instr.write('C' + str(channel) + ':BSWV AMP,' + str(vpp))  # Vpp
        self.instr.write('C' + str(channel) + ':BSWV OFST,-' + str(offset))  # Vpp

    def output_status(self,channel=1,status='ON'):
        self.instr.write('C' + str(channel) + ':OUTP ' + str(status))
    
    def CloseConnection(self):
        self.instr.close()

# =============================================================================
# Siglent DC Supply SPD3003X
# =============================================================================

class DC_Siglent: #Developer: Jeppe Surrow
        def __init__(self,
                     channel=1,
                     current=0,
                     voltage=1):
            self.current = current
            self.voltage = voltage
            self.channel = channel
            
            if voltage > 5: #To ensure we don't fry the Variable Optical Attenuator (max 10V, operational from 0 to 5V)
                voltage=5
            
            rm = visa.ResourceManager()
            resourceName = 'USB0::0x0483::0x7540::SPD3XHCQ3R2187::INSTR'

            self.instr = rm.open_resource(resourceName)
            self.instr.write_termination='\n' #Modify termination character
            self.instr.read_termination='\n' #Modify termination character
            #self.instr.timeout = 10000
            #self.instr.baud_rate = 57600
            
            time.sleep(0.04) #Wait
            
            '''
            self.instr.write('OUTP CH1,OFF') #Turn off output
            time.sleep(2) #Wait
            '''
            self.instr.write('*IDN?') #Write instrument and ask for identification string
            time.sleep(0.5) #Wait
            alive = self.instr.read('\n') #Read instrument response
            
            time.sleep(0.04) #Wait
            
            self.instr.write('OUTP CH1,ON') #Turn on output
            time.sleep(0.5) #Wait

            
            self.instr.write('CH' + str(channel) + ':CURR ' + str(current) ) # ampere
            time.sleep(0.04) #Wait
            self.instr.write('CH' + str(channel) + ':VOLT ' + str(voltage))  # volts
            
            if alive != 0:
                print('DC_SIGLENT is alive')
                print (str(alive))
            
            '''
            self.IsOn = self.instr.read('\n')
            if self.IsOn == 1:
                print('Source output is ON')
            else: 
              if self.IsOn == 0: 
                    print('Source output is OFF')
            '''


        def setParameters(self,
                     channel=1,
                     current=0,
                     voltage=1):
            
            if voltage > 5:
                voltage=5
                
            self.instr.write('CH' + str(channel) + ':CURR ' + str(current)) #
            time.sleep(0.1) #Wait
            self.instr.write('CH' + str(channel) + ':VOLT ' + str(voltage))  # 
    
        
        def outputStatus(self,channel=1,status='ON'):
            self.instr.write('OUTP ' + 'CH' + str(channel) + ',' + str(status))
    
        
        def closeConnection(self):
            self.instr.close()
        
    
    
class DC_KEITHLEY: #developer: Andreas Hänsel + functionalities added by Hanna Becker (SetIntegrationtime, GetIntegrationtime;SetMode, GetMode, SetWire, GetWire)
                          
    def __init__(self,channel=21,GPIB_interface=0,IP_address='192.168.1.151'):
        self.Meas='Volt'
        self.Source='Current'
        self.channel = channel
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
        #:OUTP ON    
        self.IsOn=int(self.instr.query(':OUTP?'))
        if self.IsOn == 1:
            print('Source output is ON')
        else: 
          if self.IsOn == 0: 
                print('Source output is OFF')
     
    def SwitchOn(self):
        if self.instr.query(':OUTP?') != 1:
            self.instr.write(':OUTP ON')
            print('Source output turned ON')
            self.IsOn = 1;
        else: print('Source output was already ON')
        
    def SwitchOff(self):
        if self.instr.query(':OUTP?') != 0:
            self.instr.write(':OUTP OFF')
            print('Source output turned OFF')
            self.IsOn = 0;
        else: print('Source output was already OFF')

    def SetMeasCurr(self):
        self.instr.write(":SENS:FUNC 'CURR'")
        self.instr.write(":FORM:ELEM CURR")
        self.Meas='Current';
        
    def SetMeasVolt(self):
        self.instr.write(":SENS:FUNC 'VOLT'")
        self.instr.write(":FORM:ELEM VOLT")
        self.Meas='Volt';        
        
    def SetSourceVolt(self):
        self.instr.write('SOUR:FUNC:MODE VOLT')
        self.Source='Volt'; 
    
    def SetSourceValue(self, Value):
        if (self.Source == 'Volt' ):
            #self.instr.write('SOUR1:VOLT '+str(Value))
            self.instr.write('SOUR:VOLT '+str(Value))
        else: 
           if (self.Source == 'Current'):
               self.instr.write('SOUR:CURR '+str(Value)) #not tested
        
    def SetSourceCurr(self):
        self.instr.write('SOUR:FUNC:MODE CURR')
        self.Source='Current'; 
        
    def SetCompliance(self, Compliance=0.05):
        # so far compliance is based on measured value; could be changed later
        if (self.Meas == 'Current'):
            self.instr.write('SENS:CURR:PROT '+str(Compliance))
        else:
          if (self.Meas == 'Volt'):
              self.instr.write('SENS:VOLT:PROT '+str(Compliance))
          else: 
              print('Measurement function undefined')
        
    def GetMeas(self):
        if (self.Meas == 'Current'):
            #self.instr.write(":FORM:ELEM 'CURR'")
            Value = float((self.instr.query_ascii_values('READ?'))[0])
        else:
          if (self.Meas == 'Volt'):
             # self.instr.write(":FORM:ELEM 'VOLT'")
              Value = float((self.instr.query_ascii_values('READ?'))[0])
          else: 
              print('Measurement function undefined')
              Value=0;
        return Value;
    
    def WriteGPIB(self, string):
        self.instr.write(string)    
        
    def QueryGPIB(self, string):
        return self.instr.query(string) 
    
    def CloseConnection(self):
        self.instr.close()

    def SetMode(self, mode_string): 
        #set 'Voltage' for voltage source, measure current
        #set 'Current for current source, measure voltage
        # ATTENTION: this setting includes a full reset and resets the compliance levels each time used!!!
        if mode_string == 'Voltage':
                # initialization of Keithley:
                self.instr.write("*RST;*CLS;*SRE 32;*ESE 1") # reset etc
                print ("The current limit will be set to 0.010A.")
                print ("The voltage limit will be set to 20V.")
                self.instr.write('SENS:CURR:PROT 0.01')
                self.instr.write('SENS:VOLT:PROT 20')
                self.instr.write(":SYST:RSEN OFF") # set 2 wire sensing
                self.instr.write(":SOUR:FUNC VOLT")
                print( "The machine has been set to 2-wire (2-probe) sensing, change this by typing myInstrument.SetWire = 'Four'")
                print( "The machine has been set to VOLTAGE mode, change this by typing myInstrument.SetMode = 'Current'")
                print("---------------------------------------------------------------")
                self.instr.write(":SOUR:VOLT:MODE FIX") 
                self.instr.write(':SENS:FUNC "CURR" ')
                self.instr.write(":FORM:ELEM CURR")
                self.Source='Volt'
                self.Meas = 'Current'
                
        elif mode_string == 'Current':
                # initialization of Keithley:
                self.instr.write("*RST;*CLS;*SRE 32;*ESE 1") # reset etc
                print ("The current limit will be set to 0.010A.")
                print ("The voltage limit will be set to 20V.")
                self.instr.write('SENS:CURR:PROT 0.01')
                self.instr.write('SENS:VOLT:PROT 20')
                self.instr.write(":SYST:RSEN OFF") # set 2 wire sensing
                self.instr.write(":SOUR:FUNC CURR")
                print( "The machine has been set to 2-wire (2-probe) sensing, change this by typing myInstrument.SetWire = 'Four'")
                print( "The machine has been set to CURRENT mode, change this by typing myInstrument.SetMode = 'Voltage'")
                print("---------------------------------------------------------------")
                self.instr.write(":SOUR:CURR:MODE FIX") # Fixed current source mode
                self.instr.write(':SENS:FUNC "VOLT" ') #Volts measure function
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
                        print( "4-wire sensing possible only with 'Current' mode. Change mode from 'Voltage' to 'Current'. Now executing 2-wire sensing.")
                elif self.Source == 'Current':
                        self.instr.write(":SYST:RSEN ON")
                        self.__wire__ = 'Four'
                        print( "Sensing set by user as 4-wire. Resetting machine to 4-wire sensing")
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



#ELECTRICAL SPECTRUM ANALYZERS:#
class ESA_RS_FSV30: 

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
        if GPIB_interface>-1: #Set GPIB_interface=0 to use GPIB instead of TCP/IP
            resourceName = 'GPIB'+str(int(GPIB_interface))+'::'+str(channel)+'::INSTR'
        else:
            resourceName ='TCPIP0::'+IP_address+'::inst0::INSTR'
		
        self.instr = rm.open_resource(resourceName)
        alive = self.instr.query('*IDN?')
        self.instr.read_termination = '\n'
        self.instr.write_termination = '\n'
        self.instr.timeout = 10000
        if alive != 0:
            print('ESA_RS_FSV is alive')
            print(alive)

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
        
    def ReadSpectrum(self):
        self.instr.clear()
        self.instr.write('FREQ:CENT '+str(self.centerFreq)+' MHz')   #Center frequency
        self.instr.write('FREQ:SPAN '+str(self.spanFreq)+' MHz')     #Frequency span
        self.instr.write('BAND '+str(self.resolutionBW)+' MHz')      #Resolution bandwidth
        self.instr.write('BAND:VID '+str(self.videoBW*1000)+' kHz')  #Video bandwidth
        self.instr.write('SWE:POIN '+str(int(self.dataPointsInSweep)))                    #Number of data points in sweep
        self.instr.write('SWE:COUN '+str(int(self.sweepCount)))       #Number of sweeps used in a trace.
        

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


    def CloseConnection(self):
        self.instr.close()


# %%
class FILT_WLTF: #developer: Lars Nielsen
    '''
    Class to control narrowband tunable band pass filter.
    '''
    def __init__(self,COMport=8):
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
            
    def SetCenterWavelength(self,lambda0=1550.000,tries=10):
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