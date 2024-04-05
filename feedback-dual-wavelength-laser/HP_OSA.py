"""
Created on Tue Sep 25 12:24:11 2018

@author: Dan Hickstein (danhickstein@gmail.com)

Modified by Maria Paula Montes

This script grabs a spectrum from an HP 70950A optical spectrum analyzer (OSA)
You'll need to manually change the "osa_address" variable to match the actual
GPIB address of your OSA.

Requirements:
 - National instruments VISA:
       https://www.ni.com/en-us/support/downloads/drivers/download.ni-visa.html#329456
 - pyvisa:
       use the Anaconda Prompt and type "pip install pyvisa"
       https://pypi.org/project/PyVISA/
 - For the GPIB-to-USB converter, you need NI 488.2 driver
       https://www.ni.com/en-us/support/downloads/drivers/download.ni-488-2.html#329025

"""

import numpy as np
import matplotlib.pyplot as plt
import os
import pyvisa as visa
rm = visa.ResourceManager()

print('Devices found:')
print(rm.list_resources())  # use this to figure out the address of the OSA
print('Connecting to OSA...')

# %%

# --- CHANGE THIS TO MATCH YOUR OSA:
osa_address = "GPIB0::23::INSTR"
# ----------------------------------

print('Trying to connect to %s' % osa_address)
osa = rm.open_resource(osa_address)

startWL = float(osa.query("STARTWL?"))
stopWL = float(osa.query("STOPWL?"))
print('Wavelength range: %.1f to %.1f nm' % (startWL*1e9, stopWL*1e9))
osa.timeout = 4000

print('Grabbing data from OSA...')
data = osa.query("TRDEF TRA, 2048; TRA?;").rstrip().split(',')
data = np.array([float(num) for num in data])

wls = np.linspace(startWL, stopWL, data.shape[0])

plt.plot(wls*1e9, data)

prefix = 'spec'
fileformat = prefix+'%04i.txt'

filenum = 1
while True:
    if os.path.exists(fileformat % filenum):
        filenum += 1
    else:
        break

print('Saving ' + fileformat % filenum + '...')

with open(fileformat % filenum, 'w') as outfile:
    for wl, d in zip(wls, data):
        outfile.write('%f, %f\n' % (wl*1e9, d))

print('================== Finished! ================')

# %%

# Now define class to implement with the lab control and single measurement

'''

class HP_OSA:  # developer: Maria Paula Montes
    """
    - DESCRIPTION:
        This class is for controlling the HP 70951A OSA
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
        
        '''
