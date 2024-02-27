# -*- coding: utf-8 -*-
"""
Created on Tue Jan 16 11:28:49 2024

@author: Group Login
"""

import numpy as np
import time
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.axes_divider import make_axes_locatable
import os
import Moni_Lab_control as pic
import shutil

from datetime import datetime 
import winsound as ws
import pyvisa as visa
import random

#%%

# =============================================================================
# TOSA test
# =============================================================================
tosa = pic.AimValley_CurrentSource(port=4)
tosa.openCommunication()


#%%

#m1curr = 0
#m2curr = 4.45
#lphcurr = 0
#lgcurr = 250
#soa1curr = 160
#soa2curr = 160
#ph1curr = 3.52
#ph2curr = 0

m1curr = 14.1
m2curr = 1.0
lphcurr = 0.2
lgcurr = 114
soa1curr = 87.8
soa2curr = 88.0
ph1curr = 0.91
ph2curr = 0

tosa.setCurrent('M1', m1curr)
tosa.setCurrent('M2', m2curr)
tosa.setCurrent('LPh', lphcurr)
tosa.setCurrent('LG', lgcurr)
tosa.setCurrent('SOA1', soa1curr)
tosa.setCurrent('SOA2', soa2curr)
tosa.setCurrent('Ph1', ph1curr)
tosa.setCurrent('Ph2', ph2curr)


m1_v = tosa.getVoltage('M1')
m2_v = tosa.getVoltage('M2')
lph_v = tosa.getVoltage('LPh')
lg_v = tosa.getVoltage('LG')
soa1_v = tosa.getVoltage('SOA1')
soa2_v = tosa.getVoltage('SOA2')
ph1_v = tosa.getVoltage('Ph1')
ph2_v = tosa.getVoltage('Ph2')

time.sleep(0.5)

parameter_string = ('List of currents: \n'
                    +'M1 = ' + str(m1curr) + ' mA\n'
                    +'M2 = ' + str(m2curr) + ' mA\n'
                    +'LPh = ' + str(lphcurr) + ' mA\n'
                    +'LG = ' + str(lgcurr) + ' mA\n'
                    +'SOA1 = ' + str(soa1curr) + ' mA\n'
                    +'SOA2 = ' + str(soa2curr) + ' mA\n'
                    +'Ph1 = ' + str(ph1curr) + ' mA\n'
                    +'Ph2 = ' + str(ph2curr) + ' mA\n'
                    + '\n \n'
                    'List of Voltages: \n'
                    +'M1 = ' + str(m1_v) + ' V\n'
                    +'M2 = ' + str(m2_v) + ' V\n'
                    +'LPh = ' + str(lph_v) + ' V\n'
                    +'LG = ' + str(lg_v) + ' V\n'
                    +'SOA1 = ' + str(soa1_v) + ' V\n'
                    +'SOA2 = ' + str(soa2_v) + ' V\n'
                    +'Ph1 = ' + str(ph1_v) + ' V\n'
                    +'Ph2 = ' + str(ph2_v) + ' V\n'
                    )



#%%

#VOA = pic.AFG_Siglent(channel=1)

#EOM = pic.AFG_Siglent(channel=2)


#sine_freq = 40*10**6

#EOM.setParameters(frequency=sine_freq)

volt_source = pic.DC_Siglent()


OSA = pic.OSA_YOKOGAWA(GPIB_interface=1,channel=7)


# %%

volt_source.setParameters(voltage=4)

#%%

freq_center = 80 # in MHz
span = 20 # in MHz

power = 10 #mW
resolution_BW= 0.001 # in MHZ
video_BW = resolution_BW

averageNo = 3

esa = pic.ESA_RS_FSV30(
                    channel=29,
                    GPIB_interface=1,
                    spanFreq=span,
                   centerFreq=freq_center,
                   videoBW=resolution_BW,
                   resolutionBW=resolution_BW)

data_points = 2*span/resolution_BW + 1


esa.SetSpectrumParameters(spanFreq=span,
                      centerFreq=freq_center,
                      videoBW=video_BW,
                      resolutionBW=resolution_BW,
                      dataPointsInSweep = data_points)
   
data = esa.ReadSpectrum()

resolution_BW_dsh=0.001 # in MHZ
freqcenter_dsh = 80
span_ESA_dsh = 20


resolution_BW_full=0.05 # in MHZ
freqcenter_full = 80
span_ESA_full = 100
#%%
 #np.savetxt('ESA_voa-voltage_' + str(4),data)
#%%

pm100 = pic.PM100USB(PM_index=0)
print('')
pm101_fb = pic.PM100USB(PM_index=1)


#%%
print(pm100.GetPower())
print(pm101_fb.GetPower())


# %%


power_no_feedback = input('Power free running laser? (mW)\n')


gen = pic.AFG_Siglent(channel=1,frequency=80*10**6,vpp=4.4)


#%% Function for single measurement.

def OSA_measurement(OSA):


    
    spanwav_full = 50
    spanwav_peak = 10
    resolution_full = 0.5
    resolution_peak = 0.05
    dbres = 107
    reflev = -5
    OSA.SetParameters(centerWave=1535,
                      spanWave=spanwav_full,
                      resolutionBW=resolution_full,
                      dbres=dbres,
                      reflev=reflev,
                      sensitivity='normal')
    data_full = OSA.ReadSpectrum()


    prelim_wav = data_full[0,:]
    prelim_pow = data_full[1,:]
    center_wav_osa_aux = prelim_wav[prelim_pow == max(prelim_pow )]
      
    center_wav_osa = center_wav_osa_aux[0]*1e9
    
    OSA.SetParameters(centerWave=center_wav_osa,
                      spanWave=spanwav_peak,
                      resolutionBW=resolution_peak,
                      dbres=dbres,
                      reflev=reflev,
                      sensitivity='normal')
    data_peak = OSA.ReadSpectrum()
    
    return data_full, data_peak


def ESA_measurement(ESA=esa, EOM=gen, DSH_on = True, resolution_BW_dsh=0.001, freqcenter_dsh = 80, span_ESA_dsh = 20,resolution_BW_full=0.05,    freqcenter_full = 80,span_ESA_full = 100, sweepcount = 100):
    
   
    if DSH_on:
        #EOM.output_status(channel=1,status='ON')
        
        #time.sleep(0.5)
        
        esa.SetSpectrumParameters(spanFreq=span_ESA_dsh,
                              centerFreq=freqcenter_dsh,
                              videoBW=resolution_BW_dsh,
                              resolutionBW=resolution_BW_dsh,
                              sweepcount=sweepcount)
        data_esa_dsh_on = esa.ReadSpectrum()
        
        esa.SetSpectrumParameters(spanFreq=span_ESA_full,
                              centerFreq=freqcenter_full,
                              videoBW=resolution_BW_full,
                              resolutionBW=resolution_BW_full,
                              sweepcount = sweepcount)
        
        data_esa_full_on = esa.ReadSpectrum()
        
        
        return  data_esa_full_on, data_esa_dsh_on
    
    else:
        
        EOM.output_status(channel=1,status='OFF')
        
        time.sleep(0.5)
        
        esa.SetSpectrumParameters(spanFreq=span_ESA_dsh,
                              centerFreq=freqcenter_dsh,
                              videoBW=resolution_BW_dsh,
                              resolutionBW=resolution_BW_dsh,
                              sweepcount=sweepcount)
        data_esa_dsh_off = esa.ReadSpectrum()
        
        esa.SetSpectrumParameters(spanFreq=span_ESA_full,
                              centerFreq=freqcenter_full,
                              videoBW=resolution_BW_full,
                              resolutionBW=resolution_BW_full,
                              sweepcount = sweepcount)
        
        data_esa_full_off = esa.ReadSpectrum()
    
        return  data_esa_full_off, data_esa_dsh_off


def plot_OSA():
    
    data_full_OSA, data_peak_OSA = OSA_measurement(OSA)
    
    plt.figure()
    plt.figure(data_full_OSA[0,:]*1e9,data_full_OSA[1,:])
    plt.ylabel('OSA Power [dBm]')
    plt.xlabel('Wavelength [nm]')
    plt.title('OSA spectrum')
    
    
def plot_ESA():
    



def single_measurement(measurementname = str, DSH_on = True, ESA=esa, OSA=OSA, EOM = gen, DC_supply = volt_source, laser_powermeter = pm100, feedback_powermeter=pm101_fb, resolution_BW_dsh=0.001, freqcenter_dsh = 80, span_ESA_dsh = 20,resolution_BW_full=0.05, freqcenter_full = 80,span_ESA_full = 100, sweepcount = 100):
    
    os.chdir('C:\\Users\\Group Login\\Documents\\Simon\\measurementData2')
    data_folder = os.getcwd()
    sweep_name = pic.timestring() + 'single_measurement_' + measurementname
    old_dir, save_dir = pic.change_folder(data_folder, sweep_name)

    data_full_OSA, data_peak_OSA = OSA_measurement(OSA)
    
    plt.figure()
    plt.figure(data_full_OSA[0,:]*1e9,data_full_OSA[1,:])
    plt.ylabel('OSA Power [dBm]')
    plt.xlabel('Wavelength [nm]')
    plt.title('OSA spectrum')
    
    
    if DSH_on:
        data_esa_full_on, data_esa_dsh_on =  ESA_measurement(ESA=ESA, EOM=EOM, DSH_on = DSH_on, resolution_BW_dsh=resolution_BW_dsh, freqcenter_dsh = freqcenter_dsh, span_ESA_dsh =span_ESA_dsh, resolution_BW_full=resolution_BW_full, freqcenter_full = freqcenter_full, span_ESA_full = span_ESA_full)# sweepcount = sweepcount )
        plt.figure()
        plt.figure(data_esa_full_on[0]*1e-6,data_esa_full_on[1])
        plt.ylabel('ESA Power [dBm]')
        plt.xlabel('Fourier frequency [MHz]')
        plt.title('Esa spectrum DSH on')
        
        plt.figure()
        plt.figure(data_esa_dsh_on[0]*1e-6,data_esa_dsh_on[1])
        plt.ylabel('ESA Power [dBm]')
        plt.xlabel('Fourier frequency [MHz]')
        plt.title('Esa spectrum DSH on')
    
    
        
        
    else:
        data_esa_full_off, data_esa_dsh_off = ESA_measurement(ESA=ESA, EOM=EOM, DSH_on = DSH_on, resolution_BW_dsh=resolution_BW_dsh, freqcenter_dsh = freqcenter_dsh, span_ESA_dsh =span_ESA_dsh, resolution_BW_full=resolution_BW_full, freqcenter_full = freqcenter_full, span_ESA_full = span_ESA_full)# sweepcount = sweepcount )

    laserPower = laser_powermeter.GetPower()
    feedbackPower = feedback_powermeter.GetPower()
    
    
    #np.save(pic.datetimestring() + 'result_nested_dict_feedback_test', osa_dict_feedback)
    np.savetxt(pic.datetimestring() + 'osa_matrix_full', data_osa_full)
    np.savetxt(pic.datetimestring() + 'osa_matrix_peak', data_osa_peak)

    if DSH_on:
        np.savetxt(pic.datetimestring() + 'esa_matrix_full_on', data_esa_full_on)
        np.savetxt(pic.datetimestring() + 'esa_matrix_dsh_on', data_esa_dsh_on)
        
    else:
        np.savetxt(pic.datetimestring() + 'esa_matrix_full_off', data_esa_full_off)
        np.savetxt(pic.datetimestring() + 'esa_matrix_dsh_off', data_esa_dsh_off)

    voa_voltage = DC_supply.voltage

    np.savetxt(pic.datetimestring() + '_voa_voltages.txt', np.array([voa_voltage,feedbackPower,laserPower]), header=('Voa_voltages \t Feedback powers \t Laser powers \t' + parameter_string))  


#%%

plt.figure(2)
plt.plot(data[0]*10**9,data[1])
plt.ylim([-70,0])
plt.xlabel('Wavelength [nm] ')
plt.ylabel('OSA power [dBm] ')
plt.savefig('OSA_power_spectrum_2.png')

# %%
LaserPWR = pm100
FeedbackPWR = pm101_fb
#volt_source.SetMeasCurr()
#volt_source.SetSourceVolt()
#olt_source.SetCompliance(0.250)


osa_dict_feedback = {}
laserPower = []
feedbackPower = []
data_full_osa = []
data_peak_osa = []

data_full_on_esa = []
data_full_off_esa = []
data_dsh_on_esa = []
data_dsh_off_esa = []


spanwav_full = 50
spanwav_peak = 10
resolutionosa = 0.05
dbres = 107
reflev = -5
OSA.SetParameters(centerWave=1535,
                  spanWave=spanwav_full,
                  resolutionBW=resolutionosa,
                  dbres=dbres,
                  reflev=reflev,
                  sensitivity='normal')
data = OSA.ReadSpectrum()
# %%
prelim_wav = data[0,:]
prelim_pow = data[1,:]
center_wav_osa_aux = prelim_wav[prelim_pow == max(prelim_pow )]
center_wav_osa = center_wav_osa_aux[0]*1e9
OSA.SetParameters(centerWave=center_wav_osa,
                  spanWave=spanwav_full,
                  resolutionBW=resolutionosa,
                  dbres=dbres,
                  reflev=reflev,
                  sensitivity='normal')
#data = OSA.ReadSpectrum()
# %%
voltage_0 = np.arange(0,1,0.25)
voltage_1 = np.arange(1,2.5,0.1)
voltage_2 = np.arange(2.5,4,0.025)
voltage_3 = np.arange(4,5.1,0.05)

#voltage_3 = np.logspace(np.log10(4),np.log10(5),)

voltage_all = np.hstack([voltage_0,voltage_1,voltage_2,voltage_3])
voa_voltages = np.flip(np.round(voltage_all,4))
# %%
os.chdir('..')
data_folder = os.path.join(os.getcwd(),'measurementData2')
sweep_name = pic.timestring() + '_feedback_test_free-running-laser_' + power_no_feedback 
old_dir, save_dir = pic.change_folder(data_folder, sweep_name)


for i, v in enumerate(voa_voltages):
    volt_source.setParameters(voltage=v)
    time.sleep(0.25)
    p_laser = LaserPWR.GetPower()
    p_feedback = FeedbackPWR.GetPower()
    laserPower.append(p_laser)
    feedbackPower.append(p_feedback)
    print('Voltage:')
    print(v)
    print('Laser power:')
    print(p_laser)
    
    print('Feedback power:')
    print(p_feedback)
    
    
    OSA.SetParameters(centerWave=center_wav_osa_aux,
                      spanWave=spanwav_full,
                      resolutionBW=resolutionosa,
                      dbres=dbres,
                      reflev=reflev,
                      sensitivity='normal')
    data_osa_full = OSA.ReadSpectrum()
    try:
        data_full_osa = np.vstack([data_full_osa,data_osa_full[1,:]])
    except ValueError:
        data_full_osa = data_osa_full

    OSA.SetParameters(centerWave=center_wav_osa_aux,
                      spanWave=spanwav_peak,
                      resolutionBW=resolutionosa,
                      dbres=dbres,
                      reflev=reflev,
                      sensitivity='normal')
    data_osa_peak = OSA.ReadSpectrum()
    try:
        data_peak_osa = np.vstack([data_peak_osa,data_osa_peak[1,:]])
    except ValueError:
        data_peak_osa = data_osa_peak



    gen.output_status(channel=1,status='ON')
    time.sleep(0.3)

    esa.SetSpectrumParameters(spanFreq=span_ESA_dsh,
                              centerFreq=freqcenter_dsh,
                              videoBW=resolution_BW_dsh,
                              resolutionBW=resolution_BW_dsh)
    data_esa_dsh_on = esa.ReadSpectrum()


    try:
        data_dsh_on_esa = np.vstack([data_dsh_on_esa,data_esa_dsh_on[1,:]])
    except ValueError:
        data_dsh_on_esa = data_esa_dsh_on

    gen.output_status(channel=1,status='OFF')
    time.sleep(0.3)

    data_esa_dsh_off = esa.ReadSpectrum()  

    try:
        data_dsh_off_esa = np.vstack([data_dsh_off_esa,data_esa_dsh_off[1,:]])
    except ValueError:
        data_dsh_off_esa = data_esa_dsh_off


    gen.output_status(channel=1,status='ON')
    time.sleep(0.3)

    esa.SetSpectrumParameters(spanFreq=span_ESA_full,
                              centerFreq=freqcenter_full,
                              videoBW=resolution_BW_full,
                              resolutionBW=resolution_BW_full)
    data_esa_full_on = esa.ReadSpectrum()  


    try:
        data_full_on_esa = np.vstack([data_full_on_esa,data_esa_full_on[1,:]])
    except ValueError:
        data_full_on_esa = data_esa_full_on

    gen.output_status(channel=1,status='OFF')
    time.sleep(0.3)

    data_esa_full_off = esa.ReadSpectrum()  

    try:
        data_full_off_esa = np.vstack([data_full_off_esa,data_esa_full_off[1,:]])
    except ValueError:
        data_full_off_esa = data_esa_full_off

    osa_dict_feedback[str(v)] = np.array(data)
    #np.savetxt('OSA_voa-voltage_' + str(v),data_osa_full,
               #header='Feedback power: ' + str(p_feedback) + ', Laser power: ' + str(p_laser))
    #np.savetxt('ESA_voa-voltage_' + str(v),data_esa_dsh_on,
               #header='Feedback power: ' + str(p_feedback) + ', Laser power: ' + str(p_laser))
# %%
tosa.setCurrent('M1',0)
tosa.setCurrent('M2',0)
tosa.setCurrent('LPh',0)
tosa.setCurrent('LG',0)
tosa.setCurrent('SOA1',0)
tosa.setCurrent('SOA2',0)
tosa.setCurrent('Ph1',0)
tosa.setCurrent('Ph2',0)
# %%
#tosa.closeCommunication()
#OSA.closeConnection()
#esa.CloseConnection()
#gen.CloseConnection()
LaserPWR.closeConnection()
FeedbackPWR.closeConnection()
#volt_source.closeConnection()


#copied_script_name = pic.datetimestring() + '_' + os.path.basename(__file__)
#shutil.copy(__file__, os.getcwd() + os.sep + copied_script_name) 
# %%
np.save(pic.datetimestring() + 'result_nested_dict_feedback_test', osa_dict_feedback)
np.savetxt(pic.datetimestring() + 'osa_matrix_full', data_full_osa)
np.savetxt(pic.datetimestring() + 'osa_matrix_peak', data_peak_osa)

np.savetxt(pic.datetimestring() + 'esa_matrix_full_on', data_full_on_esa)
np.savetxt(pic.datetimestring() + 'esa_matrix_full_off', data_full_off_esa)
np.savetxt(pic.datetimestring() + 'esa_matrix_dsh_on', data_dsh_on_esa)
np.savetxt(pic.datetimestring() + 'esa_matrix_dsh_off', data_dsh_off_esa)

np.savetxt(pic.datetimestring() + '_voa_voltages.txt', np.array([voa_voltages,feedbackPower[2:],laserPower[2:]]), header=('Voa_voltages \t Feedback powers \t Laser powers \t' + parameter_string))  


# %%
# a = mirror2_currents * 1
# new_mirror2_currents = np.hstack([a, np.zeros(len(mirror1_currents)-len(a))])




#This is where the feedback test script cuts off










print(f'The data is saved in {save_dir}')



#%%
'''
copied_script_name = pic.datetimestring() + '_' + os.path.basename(__file__)
shutil.copy(__file__, os.getcwd() + os.sep + copied_script_name) 

# %%
#np.save(pic.datetimestring() + 'result_nested_dict_feedback_test', osa_dict_feedback)
np.savetxt(pic.datetimestring() + 'osa_matrix_full', data_full_osa)
np.savetxt(pic.datetimestring() + 'osa_matrix_peak', data_peak_osa)

# %%
# a = mirror2_currents * 1
# new_mirror2_currents = np.hstack([a, np.zeros(len(mirror1_currents)-len(a))])

#np.savetxt(pic.datetimestring() + '_laser-gain-currents_osa-to-laser.txt',
           np.array([LG_currents]),
           header=('Laser gain currents. Osa Directly to laser.'
                   + parameter_string))  
'''