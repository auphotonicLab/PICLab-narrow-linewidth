import numpy as np
import time
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.axes_divider import make_axes_locatable
import os
import shutil
import sys
import multiprocessing
import Moni_Lab_control as pic


from datetime import datetime 
import winsound as ws

import random
import math

from scipy.optimize import curve_fit

#%%

import pyvisa as visa

rm = visa.ResourceManager()

print(rm.list_resources())


#%%

def set_Tosa_params(tosa, m1curr = 7.1, m2curr = 0, lphcurr = 0, lgcurr = 110, soa1curr = 80, soa2curr = 80, ph1curr = 0, ph2curr = 0):

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
    
    return parameter_string



def connect_to_instruments(TOSA_bool = False, OSA_bool =True, ESA_bool = False, EOM_bool = True, Laser_Powermeter_bool = True, Feedback_Powermeter_bool = True, MZI_Powermeter_bool=True, DC_supply_bool = False): 

        
    import Moni_Lab_control as pic
    
    res = []

    
    if TOSA_bool:
        tosa = pic.AimValley_CurrentSource(port=10)
        tosa.openCommunication()
        print('TOSA connected')
        res.append(tosa)
    else:
        res.append(0)


    if OSA_bool:
        #OSA = pic.OSA_YOKOGAWA(GPIB_interface=0,channel=7)
        OSA = pic.OSA_YENISTA_OSA20(GPIB_interface=-1,spanWave=60,centerWave=1535,resolutionBW=0.05,sensitivity=5,ip_address='192.168.1.3',tcp_port=5025)
        res.append(OSA)
    else:
        res.append(0)


    if ESA_bool:
        ESA = pic.ESA_RS_FSV30(channel=15) # GPIB_interface='usb')
        res.append(ESA)
    else:
        res.append(0)


    if EOM_bool:
        EOM = pic.AFG_Siglent(channel=1,frequency=80*10**6,vpp=4.4, load=50)
        res.append(EOM)
    else:
        res.append(0)


    if Laser_Powermeter_bool:
        pm100 = pic.PM100USB(PM_name='P0024530')
        res.append(pm100)
    else:
        res.append(0)


    if Feedback_Powermeter_bool:
        pm101_fb = pic.PM100USB(PM_name='M00905457') #'1904270'
        res.append(pm101_fb)
    else:
        res.append(0)
        
    if MZI_Powermeter_bool:
        pm101_MZI = pic.PM100USB(PM_name='M00608302')
        res.append(pm101_MZI)
    else:
        res.append(0)


    if DC_supply_bool:
        volt_source = pic.DC_Siglent(voltage=2.9)
        res.append(volt_source)
    else:
        res.append(0)

    return res

def close_connections(TOSA, OSA, ESA, EOM, Laser_Powermeter, Feedback_Powermeter, DC_supply): 
    
    try:
        TOSA.closeCommunication()
    except:
        print("TOSA wasn't connected initially")
        
    try:
        OSA.CloseConnection()
    except:
        print("OSA wasn't connected initially")
        
    try:
       ESA.CloseConnection()
    except:
        print("ESA wasn't connected initially")
        
    try:
        EOM.CloseConnection()
    except:
        print("EOM wasn't connected initially")        
        
    try:
        Laser_Powermeter.closeConnection()
    except:
        print("Laser powermeter wasn't connected initially")        
        
    try:
        Feedback_Powermeter.closeConnection()
    except:
        print("Feedback powermeter wasn't connected initially")        
        
    try:
        DC_supply.closeConnection()
    except:
        print("DC supply wasn't connected initially")
        
        
        




#%% Linewidth enhancement measurement


def inj_lock_amp_mod_ESA_monitoring():

    folder = r"C:\Users\Group Login\Documents\Jeppe_Surrow\linewidth_enhancement\30-04\Lower_side_wavelength"
    
    
    [TOSA,OSA,ESA,AM,PM_follower,PM_leader,PM_MZI,DC] = connect_to_instruments(TOSA_bool = False, OSA_bool =True, ESA_bool = True, EOM_bool = True, Laser_Powermeter_bool = True, Feedback_Powermeter_bool = True, MZI_Powermeter_bool=False, DC_supply_bool = False)
    
    DC_voltage_max_power = -2.1
    DC_voltage_min_power = 3.1
    AM.output_status(channel=2,status='OFF')

    AM.setParameters(channel=2, waveform='DC',offset=0,load='HZ')
    
    span= 5000 
    center= 2500
    VBW= 0.1 #0.3 #100,000 datapoints and 5 GHz span means that we get 2 datapoints pr resolution bandwidth if it is 100kHz
    RBW= 0.1 #0.3 #100,000 datapoints and 5 GHz span means that we get 2 datapoints pr resolution bandwidth if it is 100kHz
    Count = 1
     
     
    ESA.SetSpectrumParameters(spanFreq= span, 
                          centerFreq= center,
                          videoBW= VBW,
                          resolutionBW= RBW,
                          sweepCount = Count)
    
    AM.output_status(channel=2,status='ON')
    time.sleep(0.1)
    
    index = 0

 
     
    while True:
        
        
        
        
        ######################## Starting injection and measuring powers, OSA, and ESA (beatnote)
        AM.setParameters(channel=2, waveform='DC',offset=DC_voltage_max_power,load='HZ')
        
        #time.sleep(0.05) #No time sleep needed, as switching happens on timescale of 100ns
        
        
        
        
        injection_follower_PM = PM_follower.GetPower()
           
        injection_leader_PM = PM_leader.GetPower()
        
        
        OSA.StartMeasurement() #Take a measurement
        OSA_injected = OSA.ReadSpectrumSimple()
        
        
        time_injected = pic.datetimestring()

           
        data_injected= ESA.ReadSpectrum()
        
        
        
        ######################## Stopping injection and ESA (beatnote), OSA, and powermeters

        
        AM.setParameters(channel=2, waveform='DC',offset=DC_voltage_min_power,load='HZ')
        
        #time.sleep(0.01) No time sleep needed, as switching happens on scale of 100ns
        
        time_cold_cavity = pic.datetimestring()

        
        
        data_cold_cavity = ESA.ReadSpectrum()
          
        ESA.ContDisplay()


        OSA.StartMeasurement() #Take a measurement
        OSA_cold_cavity = OSA.ReadSpectrumSimple()
        
        
        cold_cavity_follower_PM = PM_follower.GetPower()
           
        cold_cavity_leader_PM = PM_leader.GetPower()


        np.savetxt(folder + '/' + 'no_'+ f'{index}' + '_' + time_injected + '_ESA_injected.txt', data_injected, header = f'rbw={RBW}MHz, counts={Count}')
        np.savetxt(folder + '/' + 'no_'+ f'{index}' + '_' + time_injected + '_OSA_injected.txt', np.transpose([OSA_injected[0], OSA_injected[1]]), delimiter = ',', header = f'{OSA.resolutionBW}')
        np.savetxt(folder + '/' + 'no_'+ f'{index}' + '_' + time_injected + '_powers_injected.txt', [injection_follower_PM, injection_leader_PM], header='[injection_follower, injection_leader] powermeters (directly read off PM [splitting not taken into account])')

                    
        np.savetxt(folder + '/' + 'no_'+ f'{index}' + '_' + time_cold_cavity + '_ESA_cold_cavity.txt', data_cold_cavity, header = f'rbw={RBW}MHz, counts={Count}')
        np.savetxt(folder + '/' + 'no_'+ f'{index}' + '_' + time_cold_cavity+ '_OSA_cold_cavity.txt', np.transpose([OSA_cold_cavity[0], OSA_cold_cavity[1]]), delimiter = ',', header = f'{OSA.resolutionBW}')
        np.savetxt(folder + '/' + 'no_'+ f'{index}' + '_' + time_cold_cavity + '_powers_cold_cavity.txt', [cold_cavity_follower_PM, cold_cavity_leader_PM], header='[cold_cavity_follower, cold_cavity_leader] powermeters (directly read off PM [splitting not taken into account])')
                    
        index += 1
        
        print(f'{index} '+ f'\n Injected leader: {injection_leader_PM*1e6:.3f} µW\n Injected follower: {injection_follower_PM*1e6:.3f} µW\n Cold cavity leader: {cold_cavity_leader_PM*1e6:.3f} µW\n Cold cavity follower: {cold_cavity_follower_PM*1e6:.3f} µW\n')
        
        #if index%10 == 0:
            #time.sleep(5)

#inj_lock_amp_mod_ESA_monitoring()



#%% Intensity modulator characterization


def intensity_mod_min_max_finder():
    
    
    [TOSA,OSA,ESA,AM,PM_follower,PM_leader,PM_MZI,DC] = connect_to_instruments(TOSA_bool = False, OSA_bool =False, ESA_bool = False, EOM_bool = True, Laser_Powermeter_bool = False, Feedback_Powermeter_bool = True, MZI_Powermeter_bool=False, DC_supply_bool = False)
    
    
    voltages = np.linspace(-3.0,5.0,161)
    
    meas_no = len(voltages)
    
    power_laser = np.empty(meas_no)

    
    AM.output_status(channel=2,status='OFF')

    AM.setParameters(channel=2, waveform='DC',offset=0,load='HZ')
    
    AM.output_status(channel=2,status='ON')
    time.sleep(0.1)
    
    for i,voltage in enumerate(voltages):
        
        AM.setParameters(channel=2, waveform='DC',offset=voltage,load='HZ')    
        
        time.sleep(0.1)
        
        power_laser[i] = PM_leader.GetPower()
        
    
    
    AM.output_status(channel=2,status='OFF')
    
    max_power = max(power_laser)
    min_power = min(power_laser)
    
    index_max = np.where(power_laser == max_power)
    index_min = np.where(power_laser == min_power)
    
    voltage_max = np.average(voltages[index_max])
    voltage_min = np.average(voltages[index_min])
    
    plt.figure()
    plt.plot(voltages,power_laser)
    plt.vlines([voltage_max,voltage_min],0,max_power*1.1)
    
    print('Voltage max, power',[voltage_max,max_power],'\nVoltage min, power',[voltage_min,min_power])
    
    
    
    return voltages,power_laser


def intensity_mod_charac():
    
    
    [TOSA,OSA,ESA,AM,PM_follower,PM_leader,PM_MZI,DC] = connect_to_instruments(TOSA_bool = False, OSA_bool =False, ESA_bool = False, EOM_bool = True, Laser_Powermeter_bool = False, Feedback_Powermeter_bool = True, MZI_Powermeter_bool=True, DC_supply_bool = False)
    
    
    voltages = np.array([0.0,4.0]*30)
    
    meas_no = len(voltages)
    
    power_laser_fast = np.empty(meas_no)
    
    power_laser_slow = np.empty(meas_no)
    
    power_mod_fast = np.empty(meas_no)

    power_mod_slow = np.empty(meas_no)
    
    time_sleeps = np.empty(meas_no)
    
    AM.output_status(channel=2,status='OFF')

    AM.setParameters(channel=2, waveform='DC',offset=0,load='HZ')
    
    AM.output_status(channel=2,status='ON')
    time.sleep(0.1)
    
    for i,voltage in enumerate(voltages):
        
        AM.setParameters(channel=2, waveform='DC',offset=voltage,load='HZ')    
        
        delta_t = np.random.lognormal(-5,3)
        time.sleep(delta_t)
        
        power_mod_fast[i] = PM_leader.GetPower()
        
        power_laser_fast[i] = PM_MZI.GetPower()
    
        time.sleep(3)
        
        power_mod_slow[i] = PM_leader.GetPower()
        
        power_laser_slow[i] = PM_MZI.GetPower()
        
        time_sleeps[i] = delta_t
        
        time.sleep(0.1)
        
    folder = r"C:\Users\Group Login\Documents\Simon\linewidth_enhancement\Modulator_characterization\Max_min"
    np.savetxt(folder + '/' + 'power_mod_fast.txt', power_mod_fast)
    np.savetxt(folder + '/' + 'power_mod_slow.txt', power_mod_slow)
    np.savetxt(folder + '/' + 'power_laser_fast.txt', power_laser_fast)
    np.savetxt(folder + '/' + 'power_laser_slow.txt', power_laser_slow)
 
    np.savetxt(folder + '/' + 'time_sleeps.txt', time_sleeps)

    AM.output_status(channel=2,status='OFF')





def intensity_mod_oscilloscope():
    
    
    [TOSA,OSA,ESA,AM,PM_follower,PM_leader,PM_MZI,DC] = connect_to_instruments(TOSA_bool = False, OSA_bool =False, ESA_bool = False, EOM_bool = True, Laser_Powermeter_bool = False, Feedback_Powermeter_bool = False, MZI_Powermeter_bool=True, DC_supply_bool = False)
    
    
    voltages = np.array([0.0,4.0]*30)
    
    meas_no = len(voltages)
    
    power_laser_fast = np.empty(meas_no)
    
    power_laser_slow = np.empty(meas_no)
    
    
    time_before_mod = np.empty(meas_no)
    
    time_after_mod = np.empty(meas_no)
    
    
    AM.output_status(channel=2,status='OFF')

    AM.setParameters(channel=2, waveform='DC',offset=0,load='HZ')
    
    AM.output_status(channel=2,status='ON')
    time.sleep(0.1)
    
    start = time.time()
    
    for i,voltage in enumerate(voltages):
        
        
        time_before_mod[i] = time.time()-start
        
        AM.setParameters(channel=2, waveform='DC',offset=voltage,load='HZ')
        
        time_after_mod[i] = time.time()-start
        
        power_laser_fast[i] = PM_MZI.GetPower()
    
        time.sleep(1e-5)
                
        power_laser_slow[i] = PM_MZI.GetPower()
        
        
    folder = r"C:\Users\Group Login\Documents\Simon\linewidth_enhancement\Modulator_characterization\Oscilloscope"

    np.savetxt(folder + '/' + 'power_laser_fast.txt', power_laser_fast)
    np.savetxt(folder + '/' + 'power_laser_slow.txt', power_laser_slow)
 
    np.savetxt(folder + '/' + 'time_before_mod.txt', time_before_mod)
    np.savetxt(folder + '/' + 'time_after_mod.txt', time_after_mod)

    AM.output_status(channel=2,status='OFF')
    
#%%


# import pandas as pd
# filepath = r"D:\SDS00003.csv" # r"D:\CSVMAN_UP.csv"

# data = pd.read_csv(filepath,skiprows=11,delimiter=',',engine='python')

# #%%
# seconds = np.array(data['Second'])
# voltages= np.array(data['Volt'])

# start = 13700# int(13.9995e6)
# stop =14300#int(14.0005e6)


# plt.plot(seconds[start:stop]*1e9,voltages[start:stop])
# plt.xlabel('time [ns]')
# plt.ylabel('voltage [V]')

#%% Function for single measurement.

'''For Yenista OSA'''

def OSA_measurement():
    OSA = pic.OSA_YENISTA_OSA20(GPIB_interface=-1,spanWave=50,centerWave=1535,resolutionBW=0.05,sensitivity=5,ip_address='192.168.1.3',tcp_port=5025)
    
    #data_full = OSA.ReadSpectrum() #[dataOut,waveAxis] Return x-axis in nm and y-axis in dBm
    OSA.StartMeasurement() #Take a measurement
    data_full = OSA.ReadSpectrumSimple()
    '''
    It is a list so check if it works, if not convert to array :)
    '''
    data_peak = []
    
    return data_full, data_peak, OSA.resolutionBW

def plot_OSA(savename=str, save=True,fb_power=0,plot=True):
    
    #res = connect_to_instruments(TOSA_bool = False, OSA_bool =True, ESA_bool = False, EOM_bool = False, Laser_Powermeter_bool = False, Feedback_Powermeter_bool = False, DC_supply_bool = False)
    #OSA = res[1]
    
    data_full_OSA, data_peak_OSA, resolutionBW = OSA_measurement()
    wav = data_full_OSA[0]
    #ps = 10*np.log10(data_full_OSA[1])
    ps = data_full_OSA[1]
    
    if plot:
        plt.figure()
        plt.plot(wav,ps)
        plt.ylabel('OSA Power [dBm]')
        plt.xlabel('Wavelength [nm]')
        plt.title('OSA spectrum')
        plt.yscale('log')
        #plt.ylim([-90,-20]) # -80, 10
    txt_header = '\n'.join(["Center wavelength: %f [nm]" %wav[np.where(ps == max(ps))],
                            "Peak power: %f [dBm]" %max(ps),
                            "Feedback_power: %f [arb.]" %fb_power,
                            'Wavelength [nm], Optical power [dBm]', f'{savename}'])
    

    folder = r"C:\Users\Group Login\Documents\Jeppe_Surrow\Weird_data_new_lensed_fiber\OSA/"
    if save:
        np.savetxt(folder + pic.datetimestring() + "OSA_spectrum.txt", np.transpose([wav, ps]), delimiter = ',', header = txt_header)
        plt.savefig(folder + pic.datetimestring() + "OSA_spectrum.png")
    #if save_plots_data:
    #    plt.savefig(f'.\\{savename}_OSA_full_spectrum{measurementname}.png' )
    #    np.savetxt(f'.\\{savename}_OSA_full_spectrum{measurementname}.txt',data_full_OSA, header = f'Parameters: resolutionBW = {resolutionBW}')

    return data_full_OSA, data_peak_OSA, wav[np.where(ps == max(ps))]

def plot_OSA_fast(save=True,plot=True):
    #res = connect_to_instruments(TOSA_bool = False, OSA_bool =True, ESA_bool = False, EOM_bool = False, Laser_Powermeter_bool = False, Feedback_Powermeter_bool = False, DC_supply_bool = False)
    #OSA = res[1]
    _,_,wav = plot_OSA(save=save,plot=plot)
    return wav

'''For Yokogawa OSA'''
# def OSA_measurement(OSA):


#     spanwav_full = 500 #50
#     spanwav_peak = 20
#     resolution_full = 0.5 # 0.2 dual WL
#     resolution_peak = 0.02
#     dbres = 107
#     reflev = -5
#     OSA.SetParameters(centerWave=1550, #1530
#                       spanWave=spanwav_full,
#                       resolutionBW=resolution_full,
#                       dbres=dbres,
#                       reflev=reflev,
#                       sensitivity='normal')
#     data_full = OSA.ReadSpectrum()


#     prelim_wav = data_full[0,:]
#     prelim_pow = data_full[1,:]
#     center_wav_osa_aux = prelim_wav[prelim_pow == max(prelim_pow )]
      
#     center_wav_osa = center_wav_osa_aux[0]*1e9
#     '''
#     OSA.SetParameters(centerWave=center_wav_osa,
#                       spanWave=spanwav_peak,
#                       resolutionBW=resolution_peak,
#                       dbres=dbres,
#                       reflev=reflev,
#                       sensitivity='normal')
#     '''
#     data_peak = [] #OSA.ReadSpectrum()
    
#     return data_full, data_peak, dbres, reflev, resolution_full, resolution_peak


# def plot_OSA(OSA, measurementname=str, savename=str, save_plots_data=True):
    
#     data_full_OSA, data_peak_OSA, dbres, reflev, resolution_full, resolution_peak = OSA_measurement(OSA)
    
#     plt.figure()
#     plt.plot(data_full_OSA[0]*1e9,data_full_OSA[1])
#     plt.ylabel('OSA Power [dBm]')
#     plt.xlabel('Wavelength [nm]')
#     plt.title('OSA spectrum')
#     plt.ylim([-80,-20]) # -80, 10
#     if save_plots_data:
#         plt.savefig(f'.\\{savename}_OSA_full_spectrum{measurementname}.png' )
#         np.savetxt(f'.\\{savename}_OSA_full_spectrum{measurementname}.txt',data_full_OSA, header = f'Parameters: dbres={dbres}, reflev = {reflev}, resolutionBW = {resolution_full}')

#     '''
#     plt.figure()
#     plt.plot(data_peak_OSA[0]*1e9,data_peak_OSA[1])
#     plt.ylabel('OSA Power [dBm]')
#     plt.xlabel('Wavelength [nm]')
#     plt.title('OSA spectrum ' + measurementname)
#     plt.ylim([-80,10])

#     if save_plots_data:
#         plt.savefig('.\\OSA_peak_spectrum_' + measurementname)
#         np.savetxt(f'.\\OSA_peak_spectrum_' + {measurementname}.txt,data_peak_OSA, header = f'Parameters: dbres={dbres}, reflev = {reflev}, resolutionBW = {resolution_peak}')
#     '''
#     return data_full_OSA, data_peak_OSA



def ESA_measurement(ESA, resolution_BW_dsh=0.001, freqcenter_dsh = 80, span_ESA_dsh = 20, resolution_BW_full=0.05, freqcenter_full = 80, span_ESA_full = 100, sweepcount = 100):
    
    
   
    
    ESA.SetSpectrumParameters(spanFreq=span_ESA_dsh,
                              centerFreq=freqcenter_dsh,
                              videoBW=resolution_BW_dsh,
                              resolutionBW=resolution_BW_dsh,
                              sweepCount=sweepcount)
    
    
    data_peak = ESA.ReadSpectrum()
        
    
    ESA.SetSpectrumParameters(spanFreq=span_ESA_full,
                              centerFreq=freqcenter_full,
                              videoBW=resolution_BW_full,
                              resolutionBW=resolution_BW_full,
                              sweepCount = int(sweepcount/2))
        
    data_full = ESA.ReadSpectrum()

        
    return  data_full, data_peak




def plot_ESA(ESA, measurementname = str, save_name=str, delay_length = float, modulation_frequency = any, V_pp = float, feedback_ratio = str, laserPower = any, laser_ref = any, feedbackPower = any, save_plots_data=True, resolution_BW_dsh=0.001, freqcenter_dsh = 80, span_ESA_dsh = 20, resolution_BW_full=0.05, freqcenter_full = 80,span_ESA_full = 100, sweepcount = 100, voltage_DC = float, temperature = float):
    
        
    
    data_full_ESA, data_peak_ESA = ESA_measurement(ESA, resolution_BW_dsh, freqcenter_dsh, span_ESA_dsh, resolution_BW_full, freqcenter_full, span_ESA_full, sweepcount)
    print(span_ESA_dsh, resolution_BW_full, freqcenter_full, span_ESA_full)
    
    plt.figure()
    plt.plot(data_full_ESA[0]*1e-6,data_full_ESA[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier Frequency [MHz]')
    plt.title('ESA spectrum' + measurementname)
    if save_plots_data:
        plt.savefig(f'.\\{save_name}_ESA_full_spectrum_{measurementname}.png')
        np.savetxt(f'.\\{save_name}_ESA_full_spectrum_{measurementname}.txt', data_full_ESA, header = f'Delay: {delay_length} m, Modulation frequency: {modulation_frequency} MHz, V_pp = {V_pp}, Reference laser power = {laser_ref}, Laser power = {laserPower}, Feedback power = {feedbackPower}, Feedback ratio: ' + feedback_ratio + f', \n Parameters: resolutionBW = {resolution_BW_full}, freqcenter = {freqcenter_full}, span = {span_ESA_full}, sweepcount = {int(sweepcount/2)}, DC voltage = {voltage_DC}, temperature = {temperature}')


    plt.figure()
    plt.plot(data_peak_ESA[0]*1e-6,data_peak_ESA[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier frequency [MHz]')
    plt.title('ESA spectrum' + measurementname)
    if save_plots_data:
        plt.savefig(f'.\\{save_name}_ESA_peak_spectrum_{measurementname}.png')
        np.savetxt(f'.\\{save_name}_ESA_peak_spectrum_{measurementname}.txt', data_peak_ESA, header = f'Delay: {delay_length} m, Modulation frequency: {modulation_frequency} MHz, V_pp = {V_pp}, Reference laser power = {laser_ref}, Laser power = {laserPower}, Feedback power = {feedbackPower}, Feedback ratio: ' + feedback_ratio + f', \n Parameters: resolutionBW = {resolution_BW_dsh}, freqcenter = {freqcenter_dsh}, span = {span_ESA_dsh}, sweepcount = {sweepcount}, DC voltage = {voltage_DC}, temperature = {temperature}')
    
    plt.figure()
    
    peakfilter = abs(data_peak_ESA[0]*1e-6-80) < 0.6
    
    plt.plot(data_peak_ESA[0][peakfilter]*1e-6,data_peak_ESA[1][peakfilter])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier frequency [MHz]')
    plt.title('ESA peak spectrum' + measurementname)
    if save_plots_data:
        plt.savefig(f'.\\{save_name}_ESA_peak_zoom_spectrum_{measurementname}.png')
    
    
    return data_full_ESA, data_peak_ESA


def plot_ESA_fast(tracenumber = 1, powermeter_power=104, fb_power=1, gain = 110, pol='None',rbw=5e3,plot=True):
    
    ESA = connect_to_instruments(False, False, True, False, False, False, False)[2]
    
    data_ESA = ESA.ReadDisplay(tracenumber)
    
    

    if plot:    
        plt.figure()
        plt.plot(data_ESA[0]*1e-6,data_ESA[1])
        plt.ylabel('ESA Power [dBm]')
        plt.xlabel('Fourier frequency [MHz]')
        plt.title('ESA spectrum')
    folder = r"C:\Users\Group Login\Documents\Jeppe_Surrow\Weird_data\RIN/"
    #plot_OSA(savename = f'gain: {gain}', save=True,fb_power=fb_power)

    np.savetxt(folder + pic.datetimestring(microsecond=True) + 'esa.txt', data_ESA, header = f'{powermeter_power}uW output, fb = {fb_power}uW, Pol: {pol}, rbw={rbw}Hz, counts=50')
    ESA.ContDisplay()


    
    return data_ESA

def plot_psd(delay=30,rbw=1e2,center=78.5e6):
    
    data_ESA = plot_ESA_fast(plot=False)
    freqs = data_ESA[0,:] - center 
    ps_raw = 10**(data_ESA[1,:]/10)
    k=1.06
    n=1.5
    c = 3e8
    carrier_power = max(ps_raw)
    time_delay = abs(delay - 3)*n/c
    prop_factor = 2*np.pi**2 * time_delay**2 * k * rbw *carrier_power
    ps = ps_raw / prop_factor
    linewidth = min(ps) * np.pi
    print(linewidth)
    plt.loglog(freqs,ps)
    plt.grid()
    plt.ylim([1e0,1e10])
    folder = r"C:\Users\Group Login\Documents\Jeppe_Surrow\Weird_data_new_lensed_fiber\200 counts/"
    np.savetxt(folder + pic.datetimestring(microsecond=True) + 'esa_kHz.txt', np.transpose([freqs,ps]), header = 'Fourier frequencies [Hz], FN PSD [Hz$^2$/Hz], 200 counts')
    return data_ESA


def mult_PSD(number):
    
    for i in range(number):
        plot_psd()
        
        time.sleep(15)
        

def get_ESA_peak(tracenumber = 1):
    
    ESA = connect_to_instruments(False, False, True, False, False, False, False)[2]

    data_ESA = ESA.ReadDisplay(tracenumber)
    ESA.ContDisplay()
    freqs = data_ESA[0,:]
    powers = data_ESA[1,:]
    
    if max(powers) > -90:
        peak = freqs[np.where(powers == max(powers))]
    
    return peak[0]

def sample_ESA_peak(tracenumber=1,time_seconds = 3600):
    pm100 = connect_to_instruments(False, False, False, False, True, False, False)[4]
    time.sleep(1)
    start_time = time.time()
    peaks = []
    time_stamps =[]
    ps = []
    while (time.time() - start_time) < time_seconds:
        time_stamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        peaks.append(get_ESA_peak())
        ps.append(pm100.GetPower()*1e6)
        time_stamps.append(time_stamp)
        
        time.sleep(0.5)
    folder = r"C:\Users\Group Login\Documents\Jeppe_Surrow\Weird_data\Beatnote/"
    data = np.array([time_stamps, peaks,ps])
    np.savetxt(folder + pic.datetimestring(microsecond=True) + 'esa.txt', np.transpose(data), header = 'Time[s] Frequency[Hz] Power[uW]',fmt='%s')
    pm100.closeConnection()
    return data



def sample_ESA_fast(samples=1000):
    pm100 = pic.PM100USB(PM_index=1)
    #pm101 = pic.PM100USB(PM_index=0)
    for i in range(samples):
        print(i)
        power_out = pm100.GetPower()
        #power_fb = pm101.GetPower()
        #wav = plot_OSA_fast(save=False,plot=False)
        #plot_ESA_fast(powermeter_power = power_out*1e6*40, fb_power = power_fb*1e6*2,wavelength = 0,plot=False)
        plot_ESA_fast(powermeter_power = power_out*1e6*40, fb_power = 'NA' ,plot=False)
        time.sleep(2)
    pm100.closeConnection()
    #pm101.closeConnection()

def fit_ESA_fast(tracenumber = 1, plot = False, delay = 3000,save=True,folder ="C:/Users/Group Login/Documents/Simon/fast_esa_measurements/11-9/coh_collapse/" ):
    
    "[0]: span (MHz), [1]: rbw (MHz), [2]: fit cutoff (Hz), [3] delay (m), [4] linewidth guess, [5] sweep count"
    delay_dict = {
        3000 : [2, 0.0005, 500e3,3e3,1e3,20],
        100 : [10, 0.001, 3e6,1e2,1e5,20],
        30 : [30, 0.003, 9e6,30,3e5,80],
        700 : [3, 0.0005, 1e6, 7e2, 30e3,20],
        1000 : [2, 0.0005, 800e3, 1e3, 10e3,20],
        12500 : [0.5, 0.0001, 250e3, 12.5e3,1e3,20],
        40 : [20, 0.003, 9e6, 40, 10e3,40]}
    settings = delay_dict[delay] 
    
    ESA = connect_to_instruments(False, False, True, False, False, False, False)[2]
    
    ESA.SetSpectrumParameters(spanFreq=settings[0],
                              centerFreq=76,
                              videoBW=settings[1],
                              resolutionBW=settings[1],
                              sweepCount = settings[5])
    
        
    data_ESA_zoom = ESA.ReadSpectrum()
    
    freqs = data_ESA_zoom[0]
    powers = data_ESA_zoom[1]

    if plot:
        plt.figure()
        plt.plot(freqs,powers)
        plt.ylabel('ESA Power [dBm]')
        plt.xlabel('Fourier frequency [Hz]')
        plt.title('ESA spectrum')
    txt_header = '\n'.join(["Delay: %f [m]" %int(delay),
                            'Fourier frequency [Hz], Power [dBm]'])
    if save:
        np.savetxt(folder + pic.datetimestring() + "spectrum.txt", np.transpose([freqs, powers]), delimiter = ',', header = txt_header)
        
    
    def del_o(del_f):
        return 2*np.pi*del_f

    def time_delay(fiber_length):
        c = 299792458 #m/s speed of light
        L = fiber_length #m 
        n_g = 1.468 #group index at 1550nm for silica
        return n_g * L / c
    
    def zeta_func(f,del_f,t_d):
        Omega = 2*np.pi*f    
        return del_o(del_f) * ( 1-math.exp(-t_d*del_o(del_f)) * (np.cos(Omega*t_d) + del_o(del_f)/Omega * np.sin(Omega*t_d)) ) / ( del_o(del_f)**2 + Omega**2)
    
    def zeta_fit(freq, linewidth, offset, length):
        return 10*np.log10(zeta_func(freq,linewidth,time_delay(length)))+offset
    
    
    center = 76e6
    def get_linewidth(freqs, powers):
        freqs = freqs - center
        filt = (abs(freqs) > 200e3) & (abs(freqs) < settings[2])
        try:
            p_opt, _ = curve_fit(zeta_fit, freqs[filt], powers[filt], p0 = [settings[4], 11, settings[3]])
        except RuntimeError:
            p_opt = [1e9,0]
                
        if plot:
            plt.figure()
            plt.plot(freqs, powers)
            plt.plot(freqs[filt], zeta_fit(freqs[filt],*p_opt))
            
        return p_opt[0]
    
    def get_smsr(freqs, powers):
        freqs = freqs - center
        fsr = 11.5e6
        filt1 = abs(freqs - fsr) < 1e6
        filt2 = abs(freqs + fsr) < 1e6
        return max(powers) -  max( max(powers[filt1]), max(powers[filt2]))
        

    linewidth = get_linewidth(freqs, powers)
    #np.savetxt(folder + pic.datetimestring() + 'test.txt', data_ESA)
    
    lim = 600e3
    lower_lim = settings[2]
    upper_lim = 0

    if plot:
        plt.xlim([-lower_lim,-upper_lim])
        plt.ylim( [-100,-40])
        if save:
            plt.savefig(folder + pic.datetimestring() + 'test.png', bbox_inches = 'tight')
        plt.title(linewidth)
    
    ESA.SetSpectrumParameters(spanFreq=30,
                              centerFreq=76,
                              videoBW=0.01,
                              resolutionBW=0.01,
                              sweepCount = int(settings[5]/2))
        
    data_ESA_full = ESA.ReadSpectrum()
    smsr = get_smsr(data_ESA_full[0],data_ESA_full[1])
    
    ESA.SetSpectrumParameters(spanFreq=settings[0],
                              centerFreq=76,
                              videoBW=settings[1],
                              resolutionBW=settings[1],
                              sweepCount = 2)
    ESA.SetSpectrum()
    ESA.ContDisplay()
    
    return [linewidth, smsr,data_ESA_zoom,data_ESA_full]

def monitor_spectrum(plot=False,delay=3000):
    while True:
        linewidth, smsr, _,_ = fit_ESA_fast(plot=plot,delay=delay,save=False)
        print(linewidth,smsr)
        
def monitor_filter_data(output_power:float, feedback_power:float,plot=False,threshold=30, save = True,delay=3000, counts = 20,get_OSA=False):
    folder = "C:/Users/Group Login/Documents/Simon/fast_esa_measurements/13-9/"
    directory = folder + pic.datetimestring()
    os.mkdir(directory)
    os.mkdir(directory + "_fb_" + str(feedback_power) + 'µW')
    linewidths = []
    smsrs_prev = []
    smsrs = []
    prev_smsr = 0
    prev_ESA_full = []
    counter = 0
    
    wavelength = 1550
    if get_OSA: 
        wavelength = plot_OSA_fast()
    
    while True:
        linewidth, smsr, data_ESA_zoom, data_ESA_full = fit_ESA_fast(plot=plot,save=False,folder=directory+'/spectra/',delay=delay)
        if (prev_smsr> threshold and smsr> threshold):
            counter = counter + 1
            linewidths.append(linewidth)
            
            smsrs.append(smsr)
            smsrs_prev.append(prev_smsr)
            
            txt_header = '\n'.join(['Fourier frequency [Hz], Power [dBm]'])
            print('Good measurement: ' + str(counter) + '  Prev SMSR:' + str(prev_smsr) + '  SMSR: ' + str(smsr))

            np.savetxt(directory + "_fb_" + str(feedback_power) + 'µW' + "/no " + str(counter-1) + "full_prev.txt", prev_ESA_full , delimiter = ',', header = "Previous ESA spectrum_full")
            np.savetxt(directory + "_fb_" + str(feedback_power) + 'µW' + "/no " + str(counter-1) + "zoom.txt", data_ESA_zoom, delimiter = ',', header = "ESA spectrum_zoom")
            np.savetxt(directory + "_fb_" + str(feedback_power) + 'µW' + "/no " + str(counter-1) + "full_after.txt", data_ESA_full , delimiter = ',', header = "ESA spectrum_full")

        
        prev_smsr = smsr
        prev_ESA_full = data_ESA_full
        
        print(linewidth,smsr)
        if len(linewidths) == counts:
            break
    
    plt.plot(smsrs, np.array(linewidths),'.')
    plt.ylabel('Linewidth [Hz]')
    plt.xlabel('SMSR [dB]')
    plt.yscale('log')
    
    
    txt_header = '\n'.join(["Delay: %f [m]" %int(delay),
        "Output power: %f [uW]" %int(output_power*40),
                    'Feedback power: %f [uW]' %feedback_power,
                    'Wavelength: %f [nm]' %wavelength,
                    'Linewidth [kHz], SMSR [dB], Previous SMSR [dB]'])
    np.savetxt(directory + "/result_" + str(feedback_power) + ".txt", np.transpose([linewidths, smsrs, smsrs_prev]), delimiter = ',', header = txt_header)
    
        
def repeat_fit(number_of_repeats, plot = False, output_power = 0, feedback_power = 0, delay = 3000):
    folder = "C:/Users/Group Login/Documents/Simon/fast_esa_measurements/11-9/coh_collapse/"
    linewidths = []
    smsrs = []
    for i in range(number_of_repeats):
        linewidth, smsr,_,_ = fit_ESA_fast(plot=plot, delay = delay, save = True)
        print(linewidth,smsr)
        linewidths.append(linewidth)
        smsrs.append(smsr)
    plt.plot(smsrs, np.array(linewidths),'.')
    plt.ylabel('Linewidth [Hz]')
    plt.xlabel('SMSR [dB]')
    plt.yscale('log')
    directory = folder + pic.datetimestring()
    os.mkdir(directory)
    plt.savefig(directory + '/result.png', bbox_inches = 'tight')
    
    txt_header = '\n'.join(["Output power: %f [uW]" %int(output_power*40),
                    'Feedback power: %f [uW]' %feedback_power,
                    'Linewidth [kHz], SMSR [dB]'])
    np.savetxt(directory + "/result.txt", np.transpose([linewidths, smsrs]), delimiter = ',', header = txt_header)

def feedback_ratio(LaserPWR,FeedbackPWR, Laser_ref, Laser_coef, Feedback_coef=1, coupling_ref=1):

    return 10*np.log10(coupling_ref**2 * LaserPWR*FeedbackPWR*Laser_coef*Feedback_coef/Laser_ref**2)




def single_measurement(measurementname = str, measure_OSA = True, measure_background =True, measure_EOM_on =True, save_plots_data = True, feedback_on = True, delay_length = 3000, modulation_frequency=80, V_pp = 4.4, ESA=any, OSA=any, EOM = any, laser_powermeter = any, laser_coef = 1/40, laser_ref = 6.1e-5, feedback_powermeter=any, resolution_BW_dsh = 0.001, span_ESA_dsh = 20, resolution_BW_full=0.05, span_ESA_full=100, sweepcount=100, voltage_DC=float, temperature = float):
    
    time.sleep(.1)
    #laserPower = laser_powermeter.GetPower()
    #print(laserPower)
    #feedbackPower = feedback_powermeter.GetPower()
    #print(feedbackPower)
    
    '''
    if feedback_on:
        #feedbackRatio = f'{feedback_ratio(laserPower,feedbackPower,laser_ref,laser_coef):.2f} dB' # Setting the laser_reference power equal to the laserpower, as we assume the coupling is as good as it gets (thus making it difficult to know what the relative coupling is)

        
    #else: 
        #feedbackRatio = 'None'    
    '''
    
    feedbackRatio = 'None' #Calculating this after
    laserPower = 'None'   #Getting the laser power from the other process
    feedbackPower = 'None'
    
    if measure_OSA:
        data_full_OSA, data_peak_OSA = plot_OSA(OSA, '', measurementname, save_plots_data)
    else:
        data_full_OSA = []
        data_peak_OSA = []

    EOM.setParameters(channel=1, frequency = modulation_frequency*1e6, vpp = V_pp, )
        

    
    
    #laserPower = laser_powermeter.GetPower()
    #print(laserPower)
    #feedbackPower = feedback_powermeter.GetPower()
    #print(feedbackPower)
    
    '''
    if feedback_on:
        feedbackRatio = f'{feedback_ratio(laserPower,feedbackPower,laser_ref,laser_coef):.2f} dB' # Setting the laser_reference power equal to the laserpower, as we assume the coupling is as good as it gets (thus making it difficult to know what the relative coupling is)

        
    else: 
        feedbackRatio = 'None'    
    '''
    
    if measure_EOM_on:
        EOM.output_status(channel=1,status='ON')
        time.sleep(1)

        data_full_ESA_EOM, data_peak_ESA_EOM = plot_ESA(ESA, f', EOM on at {modulation_frequency} MHz, ', measurementname, delay_length, modulation_frequency, V_pp, feedbackRatio, laserPower, laser_ref, feedbackPower, save_plots_data, resolution_BW_dsh, modulation_frequency, span_ESA_dsh, resolution_BW_full, modulation_frequency, span_ESA_full, sweepcount, voltage_DC, temperature)
    
    else:
        data_full_ESA_EOM = None
        data_peak_ESA_EOM = None
    

    
    
    #laserPower = laser_powermeter.GetPower()
    #print(laserPower)
    #feedbackPower = feedback_powermeter.GetPower()
    #print(feedbackPower)
    
    '''
    if feedback_on:
        feedbackRatio = f'{feedback_ratio(laserPower,feedbackPower,laser_ref,laser_coef):.2f} dB' # Setting the laser_reference power equal to the laserpower, as we assume the coupling is as good as it gets (thus making it difficult to know what the relative coupling is)

        
    else: 
        feedbackRatio = 'None'    
    '''
    
    modulation_off = np.nan
    
    if measure_background:
        EOM.output_status(channel=1,status='OFF')
        time.sleep(1)
        data_full_ESA_off, data_peak_ESA_off = plot_ESA(ESA, ', EOM off', measurementname, delay_length, modulation_off, V_pp, feedbackRatio, laserPower, laser_ref, feedbackPower, save_plots_data, resolution_BW_dsh, modulation_frequency, span_ESA_dsh, resolution_BW_full, modulation_frequency, span_ESA_full, sweepcount, voltage_DC, temperature)
        
    else:
        data_full_ESA_off = None
        data_peak_ESA_off = None

    if measure_EOM_on and measure_background:
        plt.figure()
        plt.plot(data_full_ESA_EOM[0],data_full_ESA_EOM[1]-data_full_ESA_off[1])
    
    
    return [laserPower, feedbackPower, data_full_OSA, data_peak_OSA, data_full_ESA_EOM, data_peak_ESA_EOM, data_full_ESA_off, data_peak_ESA_off]


def save_ESA_plot_file(data=list, sweepcount = int, measurementname=str):
    
    plt.figure()
    plt.plot(data[0]*1e-6,data[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier frequency [MHz]')
    plt.title(f'ESA spectrum, {measurementname}, {sweepcount} sweeps')
    
    plt.savefig(f'.\\ESA_spectrum_{measurementname}')
    np.savetxt(f'.\\ESA_spectrum_{measurementname}.txt', data, header = f'{measurementname}, sweepcount = {sweepcount}')
    
    
#%% 

def create_folder(OSA_peak,date_time):
    
    path = r'C:\Users\Group Login\Documents\Jeppe_Surrow\Laser_sweep_50_50_SIL'
    
    new_path = f'{path}\\{OSA_peak*1e9}_{date_time}'
    
    
    os.mkdir(new_path)
    
    return new_path
    

def OSA_SMSR(OSA):
    
    OSA.StartMeasurement() #Take a measurement

    OSA_dict = OSA.ReadPeakData()
    
    return OSA_dict


def FN_psd(ESA,delay=30,rbw=1e3,center=101.3e6):
    
    time.sleep(0.2)
    data_ESA = ESA.ReadDisplay(tracenumber=1)

    freqs = data_ESA[0,:] - center 
    ps_raw = 10**(data_ESA[1,:]/10)
    k=1.06
    n=1.5
    c = 3e8
    carrier_power = max(ps_raw)
    time_delay = abs(delay - 3)*n/c
    prop_factor = 2*np.pi**2 * time_delay**2 * k * rbw *carrier_power
    ps = ps_raw / prop_factor
    linewidth = min(ps) * np.pi
    print(linewidth)
    #plt.loglog(freqs,ps)
    #plt.grid()
    #plt.ylim([1e0,1e10])
    
    ESA.ContDisplay()

    return data_ESA,linewidth,rbw,center
    



def good_SMSR(OSA,OSA_dict,ESA,PM_laser,PM_feedback,TOSA_params):
    
    date_time = pic.datetimestring()
    
    OSA_data = OSA.ReadSpectrumSimple()

    OSA_peak = OSA_dict['Peak_WL']
    
    OSA_bw = OSA.resolutionBW
    
    save_path = create_folder(OSA_peak,date_time)
    
    np.savetxt(f'{save_path}\\OSA_data_{date_time}.txt',OSA_data,header=f'OSA_peak:{OSA_peak}, OSA_bw:{OSA_bw}')
    
    ESA_data, linewidth, ESA_bw, center_freq = FN_psd(ESA)
    
    np.savetxt(f'{save_path}\\ESA_data_{date_time}.txt', np.transpose([ESA_data[0,:],ESA_data[1,:]]), header = f'rbw:{ESA_bw}, center frequency:{center_freq}, linewidth={linewidth}, Fourier frequencies [Hz], FN PSD [Hz$^2$/Hz]')

    power_laser = PM_laser.GetPower()*40
    time.sleep(0.1)
    power_feedback = PM_feedback.GetPower()
    
    np.savetxt(f'{save_path}\\TOSA_params_{date_time}.txt',[0],header=TOSA_params)
    
    np.savetxt(f'{save_path}\\powers_{date_time}.txt',[power_laser,power_feedback],header='Power laser *40 [W], Power_feedback [W]')
    
    
 

#%%% U-shaped packaged laser sweep with self-injection locking


mirror_sweep = np.linspace(0,20,int(2e2+1))

def sweep_laser_settings(mirror_sweep=mirror_sweep):
    
    
    [TOSA,OSA,ESA,_,_,PM_laser,PM_feedback,_] = connect_to_instruments(TOSA_bool = True, OSA_bool =True, ESA_bool = True, EOM_bool = False, Laser_Powermeter_bool = False, Feedback_Powermeter_bool = True, MZI_Powermeter_bool=True, DC_supply_bool = False)
    
    ESA.ContDisplay()

    for mirror_voltage in mirror_sweep:
        
        print(mirror_voltage)
    
        for laser_phase in np.linspace(0,10,51):
            
            
            
            TOSA_params = set_Tosa_params(TOSA, m1curr = mirror_voltage, m2curr = 0, lphcurr = laser_phase, lgcurr = 110, soa1curr = 80, soa2curr = 80, ph1curr = 0, ph2curr = 0)
            
            time.sleep(0.01)

            OSA_dict = OSA_SMSR(OSA)
    
            if (OSA_dict['SideMode1_SMSR']>=35) and (OSA_dict['SideMode2_SMSR']>=35):
        

                good_SMSR(OSA,OSA_dict,ESA,PM_laser,PM_feedback,TOSA_params)
            
                break


sweep_laser_settings()


'''

#Taking single measurement:

import Moni_Lab_control as pic


TOSA_bool = False
OSA_bool = False
ESA_bool = True
EOM_bool = True
Laser_Powermeter_bool = False
Feedback_Powermeter_bool = False
DC_supply_bool = True

[TOSA, OSA, ESA, EOM, pm100, pm101_fb, volt_source]  = connect_to_instruments(TOSA_bool, OSA_bool, ESA_bool, EOM_bool, Laser_Powermeter_bool, Feedback_Powermeter_bool, DC_supply_bool)

if TOSA_bool:
    parameter_string = set_Tosa_params(TOSA, m1curr = 1.5, m2curr = 0, lphcurr = 0, lgcurr = 60, soa1curr = 60, soa2curr = 60, ph1curr = 0, ph2curr = 0)

'''

#%%

'''

coupling_treshold = 0e-5

if pm100.GetPower() < coupling_treshold:
    print(f'Laser power below coupling threshold: {coupling_treshold*1e6} µW')
    raise SystemExit(0)

'''
'''
laser_coef = 1/40 #The ratio of laser power sent into the powermeter 

temperature = 30 #Celcius


delay_length = 3000 # m
modulation_frequency = 80 # MHz
V_pp = 4.4 # V

span_ESA_dsh = 10
span_ESA_full = 160
sweepcount = 100


resolution_BW_dsh= span_ESA_dsh/20000

resolution_BW_full = span_ESA_full/20000

laser_ref = 1.4e-5  # The reference laser value used in feedback ratio calculation. This is assumed to be the best coupling obtainable.

save_plots_data = False# The
feedback_on = True
measure_OSA = False

voltage_DC = 0 #volts


volt_source.setParameters(channel=1,voltage=voltage_DC)

time.sleep(1)

if save_plots_data:
    plt.close('all')


measurement_name = pic.datetimestring()




if save_plots_data:   
    os.chdir('C:\\Users\\Group Login\\Documents\\Simon\\measurementData3')
    data_folder = os.getcwd()
    sweep_name = pic.datetimestring() + 'single_measurement'
    old_dir, save_dir = pic.change_folder(data_folder, sweep_name)        




[laserPower, feedbackPower, data_full_OSA, data_peak_OSA, data_full_ESA_EOM, data_peak_ESA_EOM, data_full_ESA_off, data_peak_ESA_off] = single_measurement(measurement_name, measure_OSA, save_plots_data, feedback_on, delay_length, modulation_frequency, V_pp, ESA, OSA, EOM, pm100, laser_coef, laser_ref, pm101_fb, resolution_BW_dsh, span_ESA_dsh,resolution_BW_full ,span_ESA_full, sweepcount, voltage_DC, temperature)

if save_plots_data:
    if TOSA_bool:
        np.savetxt('Laser params, power, and feedback power.txt', header = f'Laser power: {laserPower}, \t feedback power: {feedbackPower}, \tLaser params: \n {parameter_string}')
'''
#%%


def measurement_process(result_queue, list_of_meas_events, finished_optimizing, pipe_sender, saved_the_data, meas_type,VOA_voltage):
    
    
    import Moni_Lab_control as pic
    import pyvisa as visa
    
    simulate_meas = False
    
    
    if not simulate_meas:
        TOSA_bool = False
        OSA_bool = True
        ESA_bool = True
        EOM_bool = True
        Laser_Powermeter_bool = False
        Feedback_Powermeter_bool = False
        DC_supply_bool = True
        
        [TOSA, OSA, ESA, EOM, pm100, pm101_fb, volt_source]  = connect_to_instruments(TOSA_bool, OSA_bool, ESA_bool, EOM_bool, Laser_Powermeter_bool, Feedback_Powermeter_bool, DC_supply_bool)
        
        if TOSA_bool:
            parameter_string = set_Tosa_params(TOSA, m1curr = 7.1, m2curr = 0, lphcurr = 0, lgcurr = 120, soa1curr = 100, soa2curr = 100, ph1curr = 0, ph2curr = 0)
        
    
    
    half_no_of_meas = int(len(list_of_meas_events)/2)
    
    laser_coef = 1/40 #The ratio of laser power sent into the powermeter 

    temperature = 23.5 #Celcius
    
    
    delay_length = 3000 # m
    modulation_frequency = 80 # MHz
    V_pp = 4.4 # V
    
    span_ESA_dsh = 10
    span_ESA_full = 160
    sweepcount = 20
    
    
    resolution_BW_dsh= span_ESA_dsh/20000
    
    resolution_BW_full = span_ESA_full/20000
    
    laser_ref = 217e-6  # The reference laser value used in feedback ratio calculation. This is assumed to be the best coupling obtainable.
    

    save_plots_data = True
    feedback_on = True
    measure_OSA = True
    
    
    
    if not simulate_meas:
            volt_source.setParameters(channel=1,voltage=VOA_voltage)
    
            time.sleep(0.3)
            pass
        
    
    
    
    no_of_meas = len(list_of_meas_events) #np.append(np.linspace(0,5,half_no_of_meas),np.linspace(5,0,half_no_of_meas))  #volts
    
    #voltage_DC = np.linspace(0,1,2)                      
         
    for i in range(no_of_meas):
        

        
        plt.close('all')
        
        
        if i <10:
            measure_background = True
            measure_EOM_on = not measure_background
        else:
            measure_background = False
            measure_EOM_on = not measure_background
            
        
        
        measurement_name = pic.datetimestring()  #Using the meas_type name in the overall folder name, and sending the sweep folder name to the other process to save power   
        os.chdir('C:\\Users\\Group Login\\Documents\\Simon\\measurementPolControl')
        data_folder = os.getcwd()
        
        if not measure_background:
            sweep_name = pic.datetimestring() + 'single_measurement'
        
        if measure_background:
            sweep_name = pic.datetimestring() + 'single_measurement' + '_background'
        
       
        old_dir, save_dir = pic.change_folder(data_folder, sweep_name, meas_type)


        pipe_sender.send((i, save_dir)) #Sending both the index and the save directory to ensure the data is saved in the correct place.
    
                
        #Waits until finished_optimizing is set to True. When set to True the power readings will be saved. 
        finished_optimizing.wait()
        
        if i ==9:
            measure_OSA = True
        else:
            measure_OSA = False
        
        if simulate_meas:
            time.sleep(1800)
            
        else:
            # Perform measurements
            measurement_result = single_measurement(measurement_name, measure_OSA, measure_background, measure_EOM_on, save_plots_data, feedback_on, delay_length, modulation_frequency, V_pp, ESA, OSA, EOM, pm100,laser_coef, laser_ref, pm101_fb, resolution_BW_dsh, span_ESA_dsh,resolution_BW_full ,span_ESA_full, sweepcount, VOA_voltage, temperature)
        
        #Starts the gradient descent optimization in between the measurements. Also stops the power meter readings from being saved.
        finished_optimizing.clear()
        
        if not simulate_meas:
            # Put the measurement result into the queue for the main process
            result_queue.put(measurement_result)

        #Waits for the data to be saved before continuing (to not clog the pipe with multiple messages)
        saved_the_data.wait()

        #Notifies the other process that a measurement has been taken and it should save the power readings
        list_of_meas_events[i].set()

        #Clears the saved_data so it can be used next iteration.
        saved_the_data.clear()
        
        
    print("Measurement process finished.")    
    
    if not simulate_meas:
        close_connections(TOSA, OSA, ESA, EOM, pm100, pm101_fb, volt_source)


    
def lab_setup(list_of_meas_events, finished_optimizing, pipe_receiver, saved_the_data, add_simple_opt=True, simple_pow_avg_time=0.2):
    
    '''
    Function that starts the optimization process of the coupling
    Initially it will optimize the coupling using gradient descent (only y- and z-direction).
    Then a measurement will begin. During the measurement a simple optimization algorithm will be used if add_simple_opt=True.
    
    '''
    
    sys.path.append("C:/Users/Group Login/Documents/Simon/AU/PICLAB-main/Projects/QVersion/Python_lib")

    import MDT_Example as mdt
    
    mdt.open_instruments()
    
    if add_simple_opt:
        mdt.optimize_piezo.optimize_simple(list_of_meas_events, finished_optimizing, pipe_receiver, saved_the_data, simple_pow_avg_time)
    
    else: 
        mdt.optimize_piezo.optimize_none(list_of_meas_events, finished_optimizing, pipe_receiver, saved_the_data, simple_pow_avg_time)
    


if __name__ == '__main__':
    # Create a queue to communicate measurement results back to the main process
    for VOA_voltage in [0]:
        for simple_pow_avg_time in [0.1]:
            for add_simple_opt in [False]:
                    
                result_queue = multiprocessing.Queue()
            
                # Create an event to signal the processes to finish
                
                list_of_meas_events = [multiprocessing.Event() for _ in range(40)] #Remember to edit voltage_DC in meas_process
                
                finished_optimizing = multiprocessing.Event() #Is False when advanced optimization is running in between measurements
            
                pipe_sender, pipe_receiver = multiprocessing.Pipe()
            
                saved_the_data = multiprocessing.Event()
            
                # Create and start the lab setup process
                
                if add_simple_opt == True: #True: Allow for simple optimization during measurements, False: No optimization during measurements
                    meas_type = f'Agilent_simple_opt_0.075V_{simple_pow_avg_time}s_30min_' #Add name for the save folder for this run of measurements
                else:
                    meas_type = f'Linewidth_pol_control_{VOA_voltage:.1f}V_1550nm_3km'
                    
                lab_setup_proc = multiprocessing.Process(target=lab_setup, args=(list_of_meas_events, finished_optimizing, pipe_receiver, saved_the_data, add_simple_opt, simple_pow_avg_time))
                lab_setup_proc.start()
            
            
                # Create and start the measurement process
                measurement_proc = multiprocessing.Process(target=measurement_process, args=(result_queue, list_of_meas_events, finished_optimizing, pipe_sender, saved_the_data, meas_type,VOA_voltage))
                measurement_proc.start()
            
                
                # Wait for the lab setup process to finish
                lab_setup_proc.join()
                
                # Wait for the measurement process to finish
                #measurement_proc.join()
            
                print("All processes finished. Except measurement process for some reason")


#print("All processes finished.")

    

#%%

def test_tosa():
    tosa = pic.AimValley_CurrentSource(port=10)
    tosa.openCommunication()
    increment = 0.01
    start = 80
    for i in range(10):
        tosa.setCurrent('SOA1', start + i * increment)
        print(i)
    tosa.closeCommunication()



def test_power_meter(scale_factor=.5,threshold=5):
    
    pm100 = pic.PM100USB(PM_index=0)
    
    tosa = pic.AimValley_CurrentSource(port=10)
    tosa.openCommunication()
    set_Tosa_params(tosa,m1curr = 28.6, m2curr = 19.15, lphcurr = 0, lgcurr = 110, soa1curr = 80, soa2curr = 80, ph1curr = 9.5, ph2curr = 9.5)
    #plt.ion()  # turning interactive mode on
     
    # preparing the data
    time_data = []
    power_data = []
    channel = 'Ph1'
    channel2= 'Ph2'
    start = 9.5
    start0 = 9.5
    increment = 0.03
    # plotting the first frame
    #graph = plt.plot(time_data,power_data)[0]
    #plt.pause(1)
    time0 = time.time()
    
    # the update loop
    while(True):
        # updating the data
        if abs(start - start0) > 10:
            start = start0
        print(start)
        time1 = time.time()
        res1 = pm100.GetPower() * 1e6
        if res1 > threshold:
            tosa.setCurrent(channel, start -  increment)
            res3 = pm100.GetPower() * 1e6
            error = (res3 - res1)
            print(error)
            if abs(error) < .4:
                start = start - error * scale_factor
                start2 = start + error * scale_factor * 1
                tosa.setCurrent(channel, start)
                tosa.setCurrent(channel2, start2)
                    
        power_data.append(res1)
        time_data.append( time.time() - time0 ) 
        # removing the older graph
        #graph.remove()
         
        # plotting newer graph
        #graph = plt.plot(time_data,power_data,color = 'g')[0]
        
        if len(time_data) > 200: 
            plt.xlim(time_data[-200], time_data[-1])
         
        # calling pause function for 0.25 seconds
        #plt.pause(0.1)
        if abs(time0 - time.time()) > 20: 
            break
    pm100.closeConnection()
    tosa.closeCommunication()
    plt.figure()
    plt.plot(time_data,power_data)
    return time_data, power_data

def laser_scan(scale_factor = 1):
    tosa = pic.AimValley_CurrentSource(port=10)
    tosa.openCommunication()
    set_Tosa_params(tosa,m1curr = 28.6, m2curr = 19.15, lphcurr = 0, lgcurr = 110, soa1curr = 80, soa2curr = 80, ph1curr = 9.5, ph2curr = 9.5)
    pm100 = pic.PM100USB(PM_index=1)
    time.sleep(1)
    time0 = time.time()
    channel = 'SOA2'
    start0 = 80
    start = 80 
    increment = 0.05
    powers = []
    times = []
    while(True):
        power1 = pm100.GetPower() * 1e6
        power2 = pm100.GetPower() * 1e6
        power_change = abs(power1 - power2) / power1
        print(power_change)
        if power_change > .02:
            print("Resonance detected")
            time1 = time.time()
            while(True):
                if abs(start - start0) > 10:
                    start = start0
                print(start)
                power3 =  pm100.GetPower() * 1e6
                tosa.setCurrent(channel, start +  increment)
                power4 = pm100.GetPower() * 1e6
                powers.append(power4)
                times.append(time.time() - time1)
                error = power4 - power3
                print(error)
                if abs(error) < 1:
                    start = start + error * scale_factor
                    tosa.setCurrent(channel,start - error)
                if abs(time1 - time.time() ) > 10:
                    break
                
        if abs(time0 - time.time() ) > 10:
            break
    pm100.closeConnection()
    tosa.closeCommunication()
    plt.plot(times,powers)
            
