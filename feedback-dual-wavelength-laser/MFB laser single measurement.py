# PAULA'S VERSIOOOOOON STILL TRYING TO MAKE IT WORK :(

import numpy as np
import time
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.axes_divider import make_axes_locatable
import os
import shutil
import sys
import multiprocessing



from datetime import datetime 
import winsound as ws

import random

#%%

import pyvisa as visa

rm = visa.ResourceManager()

print(rm.list_resources())

#%%
import Moni_Lab_control as pic

#OSA = pic.OSA_YENISTA_OSA20(GPIB_interface=-1,spanWave=60,centerWave=1535,resolutionBW=0.05,sensitivity=5,ip_address='192.168.1.3',tcp_port=5025)


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

        
    import Moni_Lab_control as pic
    
    res = []

    
    if TOSA_bool:
        tosa = pic.AimValley_CurrentSource(port=4)
        tosa.openCommunication()
        res.append(tosa)
    else:
        res.append(0)


    if OSA_bool:
        #OSA = pic.OSA_YOKOGAWA(GPIB_interface=0,channel=7)
        OSA = pic.OSA_YENISTA_OSA20(GPIB_interface=-1,spanWave=60,centerWave=1535,resolutionBW=5,sensitivity=5,ip_address='192.168.1.3',tcp_port=5025)
        res.append(OSA)
    else:
        res.append(0)


    if ESA_bool:
        ESA = pic.ESA_RS_FSV30(channel=15, GPIB_interface='usb')
        res.append(ESA)
    else:
        res.append(0)


    if EOM_bool:
        EOM = pic.AFG_Siglent(channel=1,frequency=80*10**6,vpp=4.4, load=50)
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

#%% Function for single measurement.
        
''' FOR YENISTA OSA20 '''

def OSA_measurement(OSA):
#OSA = pic.OSA_YENISTA_OSA20(GPIB_interface=-1,spanWave=60,centerWave=1535,resolutionBW=0.05,sensitivity=5,ip_address='192.168.1.3',tcp_port=5025)
    
    #data_full = OSA.ReadSpectrum() #[dataOut,waveAxis] Return x-axis in nm and y-axis in dBm
    data_full = OSA.ReadSpectrumSimple()
    '''
    It is a list so check if it works, if not convert to array :)
    '''
    data_peak = []
    
    return data_full, data_peak, OSA.resolutionBW

def plot_OSA(OSA, measurementname=str, savename=str, save_plots_data=True):
    
    data_full_OSA, data_peak_OSA, resolutionBW = OSA_measurement(OSA)
    
    plt.figure()
    plt.plot(data_full_OSA[0],data_full_OSA[1])
    plt.ylabel('OSA Power [dBm]')
    plt.xlabel('Wavelength [nm]')
    plt.title('OSA spectrum')
    #plt.ylim([-90,-20]) # -80, 10
    if save_plots_data:
        plt.savefig(f'.\\{savename}_OSA_full_spectrum{measurementname}.png' )
        np.savetxt(f'.\\{savename}_OSA_full_spectrum{measurementname}.txt',data_full_OSA, header = f'Parameters: resolutionBW = {resolutionBW}')

    return data_full_OSA, data_peak_OSA

''' FOR YOKOWAGA OSA '''

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




def plot_ESA(ESA, measurementname = str, save_name=str, delay_length = float, modulation_frequency = any, V_pp = float, feedback_ratio = str, laserPower = any, laser_ref = any, feedbackPower = any, save_plots_data=True, resolution_BW_dsh=0.001, freqcenter_dsh = 80, span_ESA_dsh = 20, resolution_BW_full=0.05, freqcenter_full = 80,span_ESA_full = 100, sweepcount = 100, voltage_DC = float, temperature = float):
    
        
    
    data_full_ESA, data_peak_ESA = ESA_measurement(ESA, resolution_BW_dsh, freqcenter_dsh, span_ESA_dsh, resolution_BW_full, freqcenter_full, span_ESA_full, sweepcount)
    print(span_ESA_dsh, resolution_BW_full, freqcenter_full, span_ESA_full)
    
    plt.figure()
    plt.plot(data_full_ESA[0]*1e-6,data_full_ESA[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier Frequency [MHz]')
    plt.title('ESA spectrum' + measurementname + ' feedback: ' + feedback_ratio)
    if save_plots_data:
        plt.savefig(f'.\\{save_name}_ESA_full_spectrum_{measurementname},feedback_{feedback_ratio}.png')
        np.savetxt(f'.\\{save_name}_ESA_full_spectrum_{measurementname},feedback_{feedback_ratio}.txt', data_full_ESA, header = f'Delay: {delay_length} m, Modulation frequency: {modulation_frequency} MHz, V_pp = {V_pp}, Reference laser power = {laser_ref}, Laser power = {laserPower}, Feedback power = {feedbackPower}, Feedback ratio: ' + feedback_ratio + f', \n Parameters: resolutionBW = {resolution_BW_full}, freqcenter = {freqcenter_full}, span = {span_ESA_full}, sweepcount = {int(sweepcount/2)}, DC voltage = {voltage_DC}, temperature = {temperature}')


    plt.figure()
    plt.plot(data_peak_ESA[0]*1e-6,data_peak_ESA[1])
    plt.ylabel('ESA Power [dBm]')
    plt.xlabel('Fourier frequency [MHz]')
    plt.title('ESA spectrum' + measurementname + ' feedback: ' + feedback_ratio)
    if save_plots_data:
        plt.savefig(f'.\\{save_name}_ESA_peak_spectrum_{measurementname},feedback_{feedback_ratio}.png')
        np.savetxt(f'.\\{save_name}_ESA_peak_spectrum_{measurementname},feedback_{feedback_ratio}.txt', data_peak_ESA, header = f'Delay: {delay_length} m, Modulation frequency: {modulation_frequency} MHz, V_pp = {V_pp}, Reference laser power = {laser_ref}, Laser power = {laserPower}, Feedback power = {feedbackPower}, Feedback ratio: ' + feedback_ratio + f', \n Parameters: resolutionBW = {resolution_BW_dsh}, freqcenter = {freqcenter_dsh}, span = {span_ESA_dsh}, sweepcount = {sweepcount}, DC voltage = {voltage_DC}, temperature = {temperature}')
    
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




def single_measurement(measurementname = str, measure_OSA = True, save_plots_data = True, feedback_on = True, delay_length = 3000, modulation_frequency=80, V_pp = 4.4, ESA=any, OSA=any, EOM = any, laser_powermeter = any, laser_coef = 1/40, laser_ref = 6.1e-5, feedback_powermeter=any, resolution_BW_dsh = 0.001, span_ESA_dsh = 20, resolution_BW_full=0.05, span_ESA_full=100, sweepcount=100, voltage_DC=float, temperature = float):
    
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
        data_full_OSA, data_peak_OSA = plot_OSA(OSA, f', EOM on at {modulation_frequency} MHz,feedback_{feedbackRatio} ', measurementname, save_plots_data)
    else:
        data_full_OSA = []
        data_peak_OSA = []

    EOM.setParameters(channel=1, frequency = modulation_frequency*1e6, vpp = V_pp, )
        
    EOM.output_status(channel=1,status='ON')
    time.sleep(1)

    
    
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
    


    data_full_ESA_EOM, data_peak_ESA_EOM = plot_ESA(ESA, f', EOM on at {modulation_frequency} MHz, ', measurementname, delay_length, modulation_frequency, V_pp, feedbackRatio, laserPower, laser_ref, feedbackPower, save_plots_data, resolution_BW_dsh, modulation_frequency, span_ESA_dsh, resolution_BW_full, modulation_frequency, span_ESA_full, sweepcount, voltage_DC, temperature)

        
    
    EOM.output_status(channel=1,status='OFF')
    time.sleep(1)
    
    
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

    data_full_ESA_off, data_peak_ESA_off = plot_ESA(ESA, ', EOM off', measurementname, delay_length, modulation_off, V_pp, feedbackRatio, laserPower, laser_ref, feedbackPower, save_plots_data, resolution_BW_dsh, modulation_frequency, span_ESA_dsh, resolution_BW_full, modulation_frequency, span_ESA_full, sweepcount, voltage_DC, temperature)
    
    
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

import Moni_Lab_control as pic


TOSA_bool = False
OSA_bool = True
ESA_bool = False
EOM_bool = False
Laser_Powermeter_bool = False
Feedback_Powermeter_bool = False
DC_supply_bool = False

[TOSA, OSA, ESA, EOM, pm100, pm101_fb, volt_source]  = connect_to_instruments(TOSA_bool, OSA_bool, ESA_bool, EOM_bool, Laser_Powermeter_bool, Feedback_Powermeter_bool, DC_supply_bool)

if TOSA_bool:
    parameter_string = set_Tosa_params(TOSA, m1curr = 1.5, m2curr = 0, lphcurr = 0, lgcurr = 60, soa1curr = 60, soa2curr = 60, ph1curr = 0, ph2curr = 0)



#%%

'''

coupling_treshold = 0e-5

if pm100.GetPower() < coupling_treshold:
    print(f'Laser power below coupling threshold: {coupling_treshold*1e6} µW')
    raise SystemExit(0)

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

save_plots_data = False 
feedback_on = True
measure_OSA = False

voltage_DC = 0 #volts


#volt_source.setParameters(channel=1,voltage=voltage_DC)

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

#%%

'''
# COUPLING OPTIMIZATION

def measurement_process(result_queue, list_of_meas_events, finish_event, finished_optimizing):
    
    
    import Moni_Lab_control as pic
    import pyvisa as visa
    
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
    
    laser_ref = 3.73e-5  # The reference laser value used in feedback ratio calculation. This is assumed to be the best coupling obtainable.
    
    save_plots_data = True# The
    feedback_on = True
    measure_OSA = False
    
    
    voltage_DC = np.append(np.linspace(0,5,26),np.linspace(5,0,26))  #volts
    
    #voltage_DC = np.linspace(0,1,2)                      
         
    for i, voltage in enumerate(voltage_DC):
        

        
        if save_plots_data:
            plt.close('all')
        
        volt_source.setParameters(channel=1,voltage=voltage)
    
        time.sleep(1)
        
        measurement_name = pic.datetimestring()
        if save_plots_data:   
            os.chdir('C:\\Users\\Group Login\\Documents\\Simon\\measurementData3')
            data_folder = os.getcwd()
            sweep_name = pic.datetimestring() + 'single_measurement'
            old_dir, save_dir = pic.change_folder(data_folder, sweep_name)
            
        
        finished_optimizing.wait() #Waits until finished_optimizing is set to True

        
        # Perform measurements
        measurement_result = single_measurement(measurement_name, measure_OSA, save_plots_data, feedback_on, delay_length, modulation_frequency, V_pp, ESA, OSA, EOM, pm100,laser_coef, laser_ref, pm101_fb, resolution_BW_dsh, span_ESA_dsh,resolution_BW_full ,span_ESA_full, sweepcount, voltage, temperature)
        
        #Notifies the other process that a measurements has been taken and it should save the power readings
        list_of_meas_events[i].set()
        
        
        # Put the measurement result into the queue for the main process
        result_queue.put(measurement_result)
        
    print("Measurement process finished.")
    finish_event.set()  # Set the finish event after completing all measurements
    
    
    close_connections(TOSA, OSA, ESA, EOM, pm100, pm101_fb, volt_source)

    
def lab_setup(start_event, list_of_meas_events, finish_event):
    
    sys.path.append("C:/Users/Group Login/Documents/Simon/AU/PICLAB-main/Projects/QVersion/Python_lib")

    import MDT_Example as mdt
    
    mdt.open_instruments()
    
    mdt.optimize_piezo.optimize(start_event, list_of_meas_events, finish_event, finished_optimizing)
    


if __name__ == '__main__':
    # Create a queue to communicate measurement results back to the main process
    result_queue = multiprocessing.Queue()

    # Create an event to signal the processes to finish
    
    list_of_meas_events = [multiprocessing.Event() for _ in range(52)]
    
    start_event =  multiprocessing.Event()
    
    finish_event = multiprocessing.Event()
    
    finished_optimizing = multiprocessing.Event() #Is False when advanced optimization is running in between measurements

    # Define the number of measurements to take
    #num_measurements = 5
    
    
    # Create and start the lab setup process
    
   
    lab_setup_proc = multiprocessing.Process(target=lab_setup, args=(start_event, list_of_meas_events, finish_event, finished_optimizing))
    lab_setup_proc.start()

    time.sleep(10) #Allow time for the optimizer to work
    start_event.set() #Let the optimizer know, that it should start saving power readings
    
    # Create and start the measurement process
    measurement_proc = multiprocessing.Process(target=measurement_process, args=(result_queue, list_of_meas_events, finish_event, finished_optimizing))
    measurement_proc.start()

    
    # Wait for the measurement process to finish
    measurement_proc.join()

    # Wait for the lab setup process to finish
    lab_setup_proc.join()

    print("All processes finished.")


print("All processes finished.")




#Change the OSA we use to ANDO AQ4321, should represent the ANDO AQ6315A OSA



'''

#%%



pm100.closeConnection()
pm101_fb.closeConnection()

#TOSA.closeCommunication()
OSA.CloseConnection()
ESA.CloseConnection()
EOM.CloseConnection()
volt_source.closeConnection()

#%%


#os.chdir('C:\\Users\\Group Login\\Documents\\Simon\\measurementData3')
#data_ESA2 = plot_ESA_fast()
#np.savetxt('..\\Paula_data_ESA_spectrum', data_ESA)
#plt.savefig('..\\Paula_plot_ESA')

#%%

#save_ESA_plot_file(data_ESA2,10,'nice_spectrum')

#%%

#tosa.closeCommunication()
#OSA.closeConnection()
#esa.CloseConnection()
#gen.CloseConnection()
#pm100.closeConnection()
#pm101_fb.closeConnection()
#volt_source.closeConnection()

