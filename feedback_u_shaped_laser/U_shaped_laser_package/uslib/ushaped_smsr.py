# -*- coding: utf-8 -*-
"""
Created on Thu Jul 18 08:38:11 2024

@author: au622616
"""

import matplotlib.pyplot as plt 
import numpy as np
from file_management_lib import get_paths
from scipy.signal import find_peaks

directory = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\16-07\2024-07-16_16-51-37_fb_300µW"
path = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\16-07\2024-07-17_10-09-20_fb_15.2µW\no 20full.txt"
from cycler import cycler

fontsize = 17
plt.style.use('default')
plt.rcParams['lines.linewidth'] = 2.5
plt.rcParams['axes.labelsize'] = fontsize
plt.rcParams['axes.prop_cycle'] = cycler(color=['r', 'b', 'g', 'y','black','brown'])

plt.rcParams['legend.fontsize'] = fontsize
plt.rcParams['legend.loc'] = 'upper right'
plt.rcParams['xtick.labelsize'] = fontsize
plt.rcParams['ytick.labelsize'] = fontsize
plt.rcParams['xtick.direction'] = 'out'
plt.rcParams['xtick.minor.size'] = 4
plt.rcParams['xtick.minor.width'] = 1.5
plt.rcParams['xtick.major.width'] = 1.5
plt.rcParams['ytick.minor.width'] = 1.5
plt.rcParams['ytick.major.width'] = 1.5
plt.rcParams['xtick.major.size'] = 7
plt.rcParams['ytick.direction'] = 'out'
plt.rcParams['ytick.minor.size'] = 4

plt.rcParams['ytick.major.size'] = 7

plt.rcParams["legend.framealpha"] = 1

def get_data(path,plot=False):
    df = np.loadtxt(path,skiprows=1,delimiter=',')
    freqs = df[0,:]/1e6 - 76
    ps = df[1,:]
    ps = ps - max(ps)
    if plot:
        plt.plot(freqs, ps)
    return freqs, ps

def plot_all(directory):
    for path in get_paths(directory):
        if 'full' in path:
            plt.figure()
            get_data(path)
            plt.title(path)

def plot_single(path,plot=False):
    freqs, ps = get_data(path)
    peaks, _ = find_peaks(ps,distance = 15000,threshold=-50)
    
    filt = (abs(freqs) > 3.5) & (abs(freqs) < 8)
    filt2 = (abs(freqs) < 3.5) ^ (abs(freqs) > 8)
    
    if plot:
        fig, ax = plt.subplots(figsize=(11,6))
        ax.set(xlabel='Carrier detuning, f [MHz]',
               ylabel='Contrast [dB]',
               xlim=[-14, 14],
               yticks=[0, -10, -20, -30, -40, -50, -60, -70],
               xticks=[-10,-5,0,5,10])
        ax.grid()
        ax.plot(freqs[filt2],ps[filt2],'.',color='black',label = '1st sideband',markersize=2)
        fsr = 11.7
        ax.annotate('', xy=(-fsr,-37), xytext=(-fsr,1), arrowprops=dict(arrowstyle='<->',linewidth=2),fontsize=fontsize)
        ax.text(-11,-20,'SMSR = 37 dB',fontsize=15)
        ax.annotate('', xy=(fsr,-37), xytext=(0,-37), arrowprops=dict(arrowstyle='<->',linewidth=2,linestyle='--'),fontsize=fontsize)
        ax.annotate('', xy=(-fsr/2 +.3,-41), xytext=(fsr/2 +.3,-41), arrowprops=dict(arrowstyle='<->',linewidth=2,color='black',linestyle='--',alpha=.5),fontsize=fontsize)
        ax.text(-2,-45,'$1/\\tau_e$',fontsize=15,color='grey')
        ax.text(fsr/2 - 2,-35,'$1/\\tau_e$ = ' + str(fsr) + ' MHz',fontsize=15)
        ax.plot(freqs[filt],ps[filt],'.', color='grey',label='From DC',markersize=2)
        black_line, = ax.plot([],[],color='black')
        grey_line, = ax.plot([],[],color='grey')
        ax.legend()
        ax.legend([black_line, grey_line], ['1st sideband', 'DC'])
        #ax.plot(freqs[peaks],ps[peaks],'b.')
        plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\SMSR.png")
    return freqs[peaks]

#for path in get_paths(directory):   
#    peaks = plot_single(path)
#    print(peaks[4])

plot_single(path,plot=True)