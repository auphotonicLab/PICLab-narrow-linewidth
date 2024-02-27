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


def set_Tosa_params(tosa, m1curr = 1.5, m2curr = 0, lphcurr = 0, lgcurr = 60, soa1curr = 40, soa2curr = 40, ph1curr = 0, ph2curr = 0):

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



def connect_to_instruments(TOSA_bool = False, OSA_bool =True, ESA_bool = True, EOM_bool = True, Laser_Powermeter_bool = True, Feedback_Powermeter_bool = True, DC_supply_bool = False): 

    res = []

    
    if TOSA_bool:
        tosa = pic.AimValley_CurrentSource(port=4)
        tosa.openCommunication()
        res.append(tosa)
    else:
        res.append(0)


    if OSA_bool:
        OSA = pic.OSA_YOKOGAWA(GPIB_interface=1,channel=7)
        res.append(OSA)
    else:
        res.append(0)


    if ESA_bool:
        ESA = pic.ESA_RS_FSV30(channel=29, GPIB_interface=1)
        res.append(ESA)
    else:
        res.append(0)


    if EOM_bool:
        EOM = pic.AFG_Siglent(channel=1,frequency=80*10**6,vpp=4.4)
        res.append(EOM)
    else:
        res.append(0)


    if Laser_Powermeter_bool:
        pm100 = pic.PM100USB(PM_index=1)
        res.append(pm100)
    else:
        res.append(0)


    if Feedback_Powermeter_bool:
        pm101_fb = pic.PM100USB(PM_index=0)
        res.append(pm101_fb)
    else:
        res.append(0)


    if DC_supply_bool:
        volt_source = pic.DC_Siglent(voltage=4.9)
        res.append(volt_source)
    else:
        res.append(0)

    return res




#%% Function for single measurement.

def OSA_measurement(OSA):


    spanwav_full = 50
    spanwav_peak = 20
    resolution_full = 0.05
    resolution_peak = 0.02
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
    '''
    OSA.SetParameters(centerWave=center_wav_osa,
                      spanWave=spanwav_peak,
                      resolutionBW=resolution_peak,
                      dbres=dbres,
                      reflev=reflev,
                      sensitivity='normal')
    '''
    data_peak = [] #OSA.ReadSpectrum()
    
    return data_full, data_peak, dbres, reflev, resolution_full, resolution_peak


def plot_OSA(OSA, measurementname=str, savename=str, save_plots_data=True):
    
    data_full_OSA, data_peak_OSA, dbres, reflev, resolution_full, resolution_peak = OSA_measurement(OSA)
    
    plt.figure()
    plt.plot(data_full_OSA[0]*1e9,data_full_OSA[1])
    plt.ylabel('OSA Power [dBm]')
    plt.xlabel('Wavelength [nm]')
    plt.title('OSA spectrum')
    plt.ylim([-80,10])
    if save_plots_data:
        plt.savefig(f'.\\{savename}_OSA_full_spectrum{measurementname}.png' )
        np.savetxt(f'.\\{savename}_OSA_full_spectrum{measurementname}',data_full_OSA, header = f'Parameters: dbres={dbres}, reflev = {reflev}, resolutionBW = {resolution_full}.txt')

    '''
    plt.figure()
    plt.plot(data_peak_OSA[0]*1e9,data_peak_OSA[1])
    plt.ylabel('OSA Power [dBm]')
    plt.xlabel('Wavelength [nm]')
    plt.title('OSA spectrum ' + measurementname)
    plt.ylim([-80,10])

    if save_plots_data:
        plt.savefig('.\\OSA_peak_spectrum_' + measurementname)
        np.savetxt('.\\OSA_peak_spectrum_' + measurementname,data_peak_OSA, header = f'Parameters: dbres={dbres}, reflev = {reflev}, resolutionBW = {resolution_peak}.txt')
    '''
    return data_full_OSA, data_peak_OSA



def ESA_measurement(ESA, resolution_BW_dsh=0.001, freqcenter_dsh = 80, span_ESA_dsh = 20, resolution_BW_full=0.05, freqcenter_full = 80, span_ESA_full = 100, sweepcount = 100):
    
    ESA.SetSpectrumParameters(spanFreq=span_ESA_full,
                              centerFreq=freqcenter_full,
                              videoBW=resolution_BW_full,
                              resolutionBW=resolution_BW_full,
                              sweepCount = int(sweepcount/2))
        
    data_full = ESA.ReadSpectrum()


    ESA.SetSpectrumParameters(spanFreq=span_ESA_dsh,
                              centerFreq=freqcenter_dsh,
                              videoBW=resolution_BW_dsh,
                              resolutionBW=resolution_BW_dsh,
                              sweepCount=sweepcount)
    
    data_peak = ESA.ReadSpectrum()
        
        
    return  data_full, data_peak




def plot_ESA(ESA, measurementname = str, save_name=str, delay_length = float, modulation_frequency = any, V_pp = float, feedback_ratio = str, laserPower = any, laser_ref = any, feedbackPower = any, save_plots_data=True, resolution_BW_dsh=0.001, freqcenter_dsh = 80, span_ESA_dsh = 20, resolution_BW_full=0.05, freqcenter_full = 80,span_ESA_full = 100, sweepcount = 100):
    
        
    data_full_ESA, data_peak_ESA = ESA_measurement(ESA, resolution_BW_dsh, freqcenter_dsh, span_ESA_dsh, resolution_BW_full, freqcenter_full, span_ESA_full, sweepcount)

    
    plt.figure()
    plt.plot(data_full_ESA[0]*1e-6,data_full_ESA[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier Frequency [MHz]')
    plt.title('ESA spectrum' + measurementname + ' feedback: ' + feedback_ratio)
    if save_plots_data:
        plt.savefig(f'.\\{save_name}_ESA_full_spectrum_{measurementname},feedback_{feedback_ratio}.png')
        np.savetxt(f'.\\{save_name}_ESA_full_spectrum_{measurementname},feedback_{feedback_ratio}.txt', data_full_ESA, header = f'Delay: {delay_length} m, Modulation frequency: {modulation_frequency} MHz, V_pp = {V_pp}, Reference laser power = {laser_ref}, Laser power = {laserPower}, Feedback power = {feedbackPower}, Feedback ratio: ' + feedback_ratio + f', \n Parameters: resolutionBW = {resolution_BW_full}, freqcenter = {freqcenter_full}, span = {span_ESA_full}, sweepcount = {int(sweepcount/2)}')


    plt.figure()
    plt.plot(data_peak_ESA[0]*1e-6,data_peak_ESA[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier frequency [MHz]')
    plt.title('ESA spectrum' + measurementname + ' feedback: ' + feedback_ratio)
    if save_plots_data:
        plt.savefig(f'.\\{save_name}_ESA_peak_spectrum_{measurementname},feedback_{feedback_ratio}.png')
        np.savetxt(f'.\\{save_name}_ESA_peak_spectrum_{measurementname},feedback_{feedback_ratio}.txt', data_peak_ESA, header = f'Delay: {delay_length} m, Modulation frequency: {modulation_frequency} MHz, V_pp = {V_pp}, Reference laser power = {laser_ref}, Laser power = {laserPower}, Feedback power = {feedbackPower}, Feedback ratio: ' + feedback_ratio + f', \n Parameters: resolutionBW = {resolution_BW_dsh}, freqcenter = {freqcenter_dsh}, span = {span_ESA_dsh}, sweepcount = {sweepcount}')
    
    return data_full_ESA, data_peak_ESA


def plot_ESA_fast(tracenumber = 1):
    
    ESA = connect_to_instruments(False, False, True, False, False, False, False)[2]
    
    data_ESA = ESA.ReadDisplay(tracenumber)

    
    plt.figure()
    plt.plot(data_ESA[0]*1e-6,data_ESA[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier frequency [MHz]')
    plt.title('ESA spectrum')

    return data_ESA



def feedback_ratio(LaserPWR,FeedbackPWR, Laser_ref, Laser_coef, Feedback_coef=1, coupling_ref=1):

    return 10*np.log10(coupling_ref**2 * LaserPWR*FeedbackPWR*Laser_coef*Feedback_coef/Laser_ref**2)




def single_measurement(measurementname = str, measure_OSA = True, save_plots_data = True, feedback_on = True, delay_length = 3000, modulation_frequency=80, V_pp = 4.4, ESA=any, OSA=any, EOM = any, laser_powermeter = any, laser_coef = 1/40, laser_ref = 6.1e-5, feedback_powermeter=any, resolution_BW_dsh = 0.001, span_ESA_dsh = 20, resolution_BW_full=0.05, span_ESA_full=100, sweepcount=100):
    
    time.sleep(.1)
    laserPower = laser_powermeter.GetPower()
    print(laserPower)
    feedbackPower = feedback_powermeter.GetPower()
    print(feedbackPower)

    if feedback_on:
        feedbackRatio = f'{feedback_ratio(laserPower,feedbackPower,laser_ref,laser_coef):.2f} dB' # Setting the laser_reference power equal to the laserpower, as we assume the coupling is as good as it gets (thus making it difficult to know what the relative coupling is)

        
    else: 
        feedbackRatio = 'None'
    

    if measure_OSA:
        data_full_OSA, data_peak_OSA = plot_OSA(OSA, f', EOM on at {modulation_frequency} MHz,feedback_{feedbackRatio} ', measurementname, save_plots_data)
    else:
        data_full_OSA = []
        data_peak_OSA = []

    EOM.setParameters(channel=1, frequency = modulation_frequency*1e6, vpp = V_pp, )
        
    EOM.output_status(channel=1,status='ON')
    time.sleep(1)


    data_full_ESA_EOM, data_peak_ESA_EOM = plot_ESA(ESA, f', EOM on at {modulation_frequency} MHz, ', measurementname, delay_length, modulation_frequency, V_pp, feedbackRatio, laserPower, laser_ref, feedbackPower, save_plots_data, resolution_BW_dsh, modulation_frequency, span_ESA_dsh, resolution_BW_full, modulation_frequency, span_ESA_full, sweepcount)

        
    
    EOM.output_status(channel=1,status='OFF')
    time.sleep(1)
        
    modulation_off = np.nan

    data_full_ESA_off, data_peak_ESA_off = plot_ESA(ESA, ', EOM off', measurementname, delay_length, modulation_off, V_pp, feedbackRatio, laserPower, laser_ref, feedbackPower, save_plots_data, resolution_BW_dsh, modulation_frequency, span_ESA_dsh, resolution_BW_full, modulation_frequency, span_ESA_full, sweepcount)
    
    
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
        
#Taking single measurement:




TOSA_bool = False
OSA_bool = True
ESA_bool =True
EOM_bool = True
Laser_Powermeter_bool = True
Feedback_Powermeter_bool = True
DC_supply_bool = True

[TOSA, OSA, ESA, EOM, pm100, pm101_fb, volt_source]  = connect_to_instruments(TOSA_bool, OSA_bool, ESA_bool, EOM_bool, Laser_Powermeter_bool, Feedback_Powermeter_bool, DC_supply_bool)

if TOSA_bool:
    parameter_string = set_Tosa_params(TOSA, m1curr = 1.5, m2curr = 0, lphcurr = 0, lgcurr = 60, soa1curr = 40, soa2curr = 40, ph1curr = 0, ph2curr = 0)

#%%

coupling_treshold = 5.75e-5

if pm100.GetPower() < coupling_treshold:
    print(f'Laser power below coupling threshold: {coupling_treshold*1e6} µW')
    raise SystemExit(0)



laser_coef = 1/40 #The ratio of laser power sent into the powermeter 


delay_length = 3000 # m
modulation_frequency = 80 # MHz
V_pp = 4.4 # V

span_ESA_dsh = 10
span_ESA_full = 160
sweepcount = 100


resolution_BW_dsh= span_ESA_dsh/20000

resolution_BW_full = span_ESA_full/20000

laser_ref = 5.86e-5  # The reference laser value used in feedback ratio calculation. This is assumed to be the best coupling obtainable.

save_plots_data = False
feedback_on = True
measure_OSA = True


volt_source.setParameters(channel=1,voltage=3.2)

time.sleep(1)

if save_plots_data:
    plt.close('all')



measurement_name = pic.datetimestring()




if save_plots_data:   
    os.chdir('C:\\Users\\Group Login\\Documents\\Simon\\measurementData3')
    data_folder = os.getcwd()
    sweep_name = pic.datetimestring() + 'single_measurement_'
    old_dir, save_dir = pic.change_folder(data_folder, sweep_name)        




[laserPower, feedbackPower, data_full_OSA, data_peak_OSA, data_full_ESA_EOM, data_peak_ESA_EOM, data_full_ESA_off, data_peak_ESA_off] = single_measurement(measurement_name, measure_OSA, save_plots_data, feedback_on, delay_length, modulation_frequency, V_pp, ESA, OSA, EOM, pm100, laser_coef, laser_ref, pm101_fb, resolution_BW_dsh, span_ESA_dsh,resolution_BW_full ,span_ESA_full, sweepcount)

if save_plots_data:
    if TOSA_bool:
        np.savetxt('Laser params, power, and feedback power.txt', header = f'Laser power: {laserPower}, \t feedback power: {feedbackPower}, \tLaser params: \n {parameter_string}')

#%%

pm100.closeConnection()
pm101_fb.closeConnection()

#TOSA.closeCommunication()
OSA.closeConnection()
ESA.CloseConnection()
EOM.CloseConnection()
volt_source.closeConnection()

#%%


data_ESA2 = plot_ESA_fast()
#np.savetxt('..\\Paula_data_ESA_spectrum', data_ESA)
#plt.savefig('..\\Paula_plot_ESA')

#%%

save_ESA_plot_file(data_ESA2,50,'PD background')

#%%

#tosa.closeCommunication()
#OSA.closeConnection()
#esa.CloseConnection()
#gen.CloseConnection()
pm100.closeConnection()
pm101_fb.closeConnection()
#volt_source.closeConnection()
