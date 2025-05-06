# -*- coding: utf-8 -*-
"""
Created on Mon Jul 15 14:01:41 2024

@author: au622616
"""

from zeta_fit import get_linewidth
from file_management_lib import get_paths
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from cycler import cycler

plt.rcParams['axes.prop_cycle'] = cycler(color=['r', 'b', 'g', 'y','black','brown'])

dictionary = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_12-05-16\spectra"
dictionary700 = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_14-37-30\spectra"
dictionary100 = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_14-55-02\spectra"
path = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_14-58-12\spectra\2024-07-10_14-58-15spectrum.txt"
path_700 = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_14-37-30\spectra\2024-07-10_14-37-36spectrum.txt"
path_100 = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_14-55-02\spectra\2024-07-10_14-55-19spectrum.txt"
path_30 = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_15-08-23\spectra\2024-07-10_15-08-42spectrum.txt"

lws = []

def plot_linewidth(path,delay=3000):
    df = pd.read_csv(path,header=2)
    
    freqs = df.values[:,0] - 76e6
    powers = df.values[:,1]

    
    linewidth, offset, length = get_linewidth(freqs, powers, delay, plot = True)
    plt.ylim([-100,10])
    plt.xlim([-600,600])
    return linewidth

def plot_all(dictionary,delay):
    lws = []
    for path in get_paths(dictionary):
        linewidth = plot_linewidth(path,delay=delay)
        lws.append(linewidth)
        plt.xlim([-5e3,5e3])
        print(linewidth)
    lws = np.array(lws)
    print(np.mean(lws))

def plot_special():
    plot_linewidth(get_paths(dictionary)[6])
    plt.xlabel('Carrier detuning [kHz]')
    plt.ylabel('Contrast [dB]')
    plt.grid()
    
    #plt.legend(fontsize = 17)
    props = dict(boxstyle='round', facecolor='wheat', alpha=1)
    plt.text(-450, -15, '$\Delta f$ = 375 Hz \n $L = 3$ km', bbox=props, fontsize = 17)
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\zeta_fit_3km.pdf",bbox_inches='tight')

def plot_special_700():
    lw = plot_linewidth(path_700,delay=700)
    plt.xlabel('Carrier detuning [kHz]')
    plt.ylabel('Contrast [dB]')
    plt.grid()
    plt.xlim([-1e3,1e3])
    plt.ylim([-70,5])
    #plt.legend(fontsize = 17)
    props = dict(boxstyle='round', facecolor='wheat', alpha=1)
    plt.text(-700, -15, '$\Delta f$ = 21 kHz \n $L = 700$ m', bbox=props, fontsize = 17)
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\zeta_fit_700m.pdf",bbox_inches='tight')
    print(lw)
    
def plot_special_100():
    lw = plot_linewidth(path_100,delay=100)
    plt.xlabel('Carrier detuning [kHz]')
    plt.ylabel('Contrast [dB]')
    plt.grid()
    plt.xlim([-5e3,5e3])
    plt.ylim([-70,5])
    #plt.legend(fontsize = 17)
    props = dict(boxstyle='round', facecolor='wheat', alpha=1)
    plt.text(-3500, -15, '$\Delta f$ = 81 kHz \n $L = 100$ m', bbox=props, fontsize = 17)
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\zeta_fit_100m.pdf",bbox_inches='tight')
    print(lw)

def plot_special_30():
    lw = plot_linewidth(path_30,delay=30)
    plt.xlabel('Carrier detuning [kHz]')
    plt.ylabel('Contrast [dB]')
    plt.grid()
    plt.xlim([-15e3,15e3])
    plt.ylim([-60,5])
    #plt.legend(fontsize = 17)
    props = dict(boxstyle='round', facecolor='wheat', alpha=1)
    plt.text(-12000, -15, '$\Delta f$ = 1.01 MHz \n $L = 30$ m', bbox=props, fontsize = 17)
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\zeta_fit_30m.pdf",bbox_inches='tight')
    print(lw)

    
#plot_special()

#plot_all(delay=700)
plot_special_700()
plot_special()
plot_special_100()
plot_special_30()