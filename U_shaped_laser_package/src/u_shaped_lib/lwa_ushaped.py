# -*- coding: utf-8 -*-
"""
Created on Wed Mar  6 11:13:00 2024

@author: au622616
"""

from . import lwa_lib
import os
import matplotlib.pyplot as plt
from .file_management_lib import get_paths
import numpy as np
from cycler import cycler

import matplotlib.ticker
from matplotlib import pyplot as plt, ticker as mticker

fontsize = 20
plt.style.use('default')
plt.rcParams['lines.linewidth'] = 2.5
plt.rcParams['axes.labelsize'] = fontsize
#plt.rcParams['axes.prop_cycle'] = cycler(color=['r', 'b', 'g', 'y','black','brown'])

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

lwa_dir = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\LWA_2024-03-06"
path_no = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\LWA_2024-03-06\PSD_no_feedback.txt"
path_2 = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped\FN_490uW_p2uW_FB.txt"
path_3 = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped\FN_490uW_25uW_FB.txt"
path_4 = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped\FN_490uW_p05uW_FB.txt"
path_rin = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped\RIN_493uW_400uW_FB.txt"
path_rin2 = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped\RIN_490uW_p05uW_FB.txt"
path_rin3 = r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped\RIN_490uW_12uW_FB.txt"

def plot_fn():
    """
    Plot frequency noise measurements from all FN files in the U-shaped measurements directory.
    """
    paths = get_paths(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped")
    for path in paths:
        if 'FN' in path:
            lwa = lwa_lib.LWA(path)
            fs = lwa.freqs
            ps = lwa.powers**2
            if ('p2' or '400') in path:
                ps = ps**(1/2)
            plt.loglog(fs,ps,label=path)
            #plt.legend()
def plot_rin():
    """
    Plot relative intensity noise measurements from all RIN files in the U-shaped measurements directory.
    """
    paths = get_paths(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Simon\20-6-ushaped")
    for path in paths:
        if 'RIN' in path:
            lwa = lwa_lib.LWA(path)
            plt.loglog(lwa.freqs,lwa.powers,label=path)
            plt.legend()

def plot_other():
    """
    Plot various laser measurements including linewidth, frequency noise, and RIN data
    with different feedback conditions.
    """
    lwa = lwa_lib.LWA(path_no)
    lwa2 = lwa_lib.LWA(path_2)
    lwa3 = lwa_lib.LWA(path_3)
    lwa4 = lwa_lib.LWA(path_4)
    lwa.plot()
    
    rin = lwa_lib.LWA(path_rin)
    rin2 = lwa_lib.LWA(path_rin2)
    rin3 = lwa_lib.LWA(path_rin3)
    
    
    
    feedbacks = np.array([400, 200, 100, 50, 25, 12, 6, 3, 1, .5, .2, .1])
    feedbacks = 10 * np.log10( feedbacks / (490 * 40 ) )
    
    
    linewidths = [680, 823, 1661, 685, 908, 1731, 1180, 1747, 1272, 2285, 6278, 90943]
    
    plt.figure()
    plt.semilogy(feedbacks,linewidths,'.')
    
    fig, ax = plt.subplots(figsize=[10,6])
    
    #lwa.plot(label='No feedback')
    #lwa2.plot()
    lw = 1.5
    
    ax.yaxis.set_major_locator(mticker.LogLocator(numticks=999))
    ax.yaxis.set_minor_locator(mticker.LogLocator(numticks=999, subs=(.2, .4, .6, .8)))
    
    ax.plot(lwa.freqs,lwa.powers,linewidth=lw)
    ax.plot(lwa3.freqs,lwa3.powers**2,linewidth=lw)
    #ax.plot(lwa4.freqs,lwa4.powers**2,linewidth=lw)
    ax.grid()
    ax.set_xscale("log")
    ax.set_yscale("log")
    
    ax.annotate('', xy=(1e6,2e2), xytext=(1e6,1e7), arrowprops=dict(arrowstyle='<->',linewidth=2),fontsize=fontsize)
    
    ax.text(1.2e6,2e4,'~40 dB',fontsize=fontsize)
    
    ax.set(xlim=[1e3,1e7], xlabel = 'Fourier frequency [Hz]', ylabel = 'FN PSD [Hz$^2$/Hz]')
    #plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\fn_psd.pdf")
    
    plt.figure(figsize=[10,6])
    
    plt.semilogx(rin2.freqs, rin2.powers, label = 'No feedback',color='grey')
    plt.semilogx(rin.freqs, rin.powers, label = 'High feedback \n (-15 dB)',color='black')
    
    plt.xlabel('Fourier frequency [Hz]')
    plt.ylabel('RIN [dBc/Hz]')
    plt.xlim([100,4e6])
    plt.ylim([-160,-80])
    plt.legend(loc='upper right',fontsize=17)
    plt.grid()
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\rin.pdf",bbox_inches='tight')

def plot_new():
    """
    Plot new linewidth measurements comparing no feedback and high feedback conditions.
    """
    path_no_fb = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_15-14-11\PSD_1e-05.txt"
    path_high_fb  = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\10-7\2024-07-10_14-10-06\PSD_2.txt"
    lw = 1.5
    lwa = lwa_lib.LWA(path_no_fb)
    lwa2 = lwa_lib.LWA(path_high_fb)
    fig, ax = plt.subplots(figsize=[10,6])
    color1 = 'royalblue'
    ax.annotate('', xy=(1e6,1.5e3), xytext=(1e6,4e6), arrowprops=dict(arrowstyle='<->',linewidth=2, color=color1),fontsize=17)
    ax.text(1.2e6,2e4,'~35 dB',fontsize=fontsize,color=color1)
    
    ax.plot(lwa.freqs,lwa.powers,linewidth=lw,color='grey', label='No feedback')
    ax.plot(lwa2.freqs,lwa2.powers,linewidth=lw,color='black', label='High feedback \n (-15 dB)')
    ax.set(xlim=[1e3,4e6],
           ylim=[1e2,1e9],
           xscale='log',
           yscale='log',
           xlabel='Fourier frequency [Hz]',
           ylabel='FN PSD [Hz$^2$/Hz]')
    ax.grid()
    
    plt.legend(fontsize=15)
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\fn_psd.pdf",bbox_inches='tight')
    
#plot_new()
plot_other()

