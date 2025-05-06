# -*- coding: utf-8 -*-
"""
Created on Mon Sep 30 12:07:50 2024

@author: au622616
"""

import lwa_lib
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

path = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\30-9\RIN_highfinesse.txt"
esa_path1 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\30-9\150MHzesa.txt"
esa_path2 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\30-9\HPesa.txt"

lwa = lwa_lib.LWA(path)
plt.figure(figsize=(12,5))
lwa.plot(label='HF')

#plt.figure()


def plot_rin(path, V0,label):
    df = np.loadtxt(esa_path1, skiprows=1)
    
    rbw = 500
    
    freqs = df[0,:]
    powers = df[1,:] #dBm
    psd = powers - 10*np.log10(rbw) #dBm/Hz
    dc_power = (V0)**2 / 50 * 1e3 #mW
    rin = psd - 20*np.log10(dc_power)
    
    plt.plot(freqs,rin,label=label)

V1 = 787e-3
V2 = 114e-3
gain1 = 2e3*0.67e-3*.5
gain2 = 300e-3*0.67

plot_rin(esa_path1,V1,'Thorlabs')
plot_rin(esa_path2,V2,'HP')
plt.legend(loc='upper left')
plt.title('Agilent laser RIN (10 mW output power)',fontsize=25)