# -*- coding: utf-8 -*-
"""
Created on Wed Jul  3 08:34:17 2024

@author: au622616
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
from collections import defaultdict
from scipy.stats import iqr
from file_management_lib import get_paths, get_header
from lwa_lib import LWA

fontsize=20
plt.rcParams['axes.labelsize'] = fontsize

directory = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\02-7"
directory2 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\05-7"
directory3 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\09-7"
directory4 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\10-7"
directory5 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\16-07"
directory6 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\23-7"

paths = get_paths(directory)
paths2 = get_paths(directory2)

lwa_path  = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\10-7\2024-07-10_15-14-11\PSD_1e-05.txt"
rin_path = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\16-07\RINvsFB.txt"

psd  =LWA(lwa_path)

paths3 = []
paths4 = []
paths5 = []
paths6 = []

for dataset in get_paths(directory4):
    for path in get_paths(dataset):
        if 'result' in path:
            result = path
        if 'PSD' in path:
            lwa = path
    paths4.append([result,LWA(lwa)])
    
for dataset in get_paths(directory5):
    if ('fb' not in dataset) and ('.txt' not in dataset) and ('.csv' not in dataset) and ('.png' not in dataset) and ('Thumbs' not in dataset) and ('bad' not in dataset) and ('pdf' not in dataset):
        for path in get_paths(dataset):
            if 'result' in path:
                result = path
            if 'PSD' in path:
                lwa = path
            paths5.append([result,LWA(lwa)])
            
for dataset in get_paths(directory6):
    if ('fb' not in dataset) and ('.txt' not in dataset) and ('.csv' not in dataset) and ('.png' not in dataset) and ('Thumbs' not in dataset) and ('bad' not in dataset) and ('pdf' not in dataset):
        for path in get_paths(dataset):
            if 'result' in path:
                result = path
            if 'OSA' in path:
                osa = path
        paths6.append([result,osa])


def get_rin():
    df = pd.read_csv(rin_path,header=3,
                     encoding="ISO-8859-1",delim_whitespace=True)
    fb = df.values[:,0]
    rin = df.values[:,1]
    return fb, rin

def get_data(path, plot=False):
    df = pd.read_csv(path,header=3,
                     encoding="ISO-8859-1")
    linewidths = df.values[:,0]
    smsrs = df.values[:,1]
    
    filtered_linewidths = []
    for i in range(len(smsrs)):
        threshold = 30
        if (i > 0 and i < (len(smsrs) -1)):
            if (smsrs[i-1] > threshold and smsrs[i] > threshold):
                filtered_linewidths.append(linewidths[i])
                
    
    header = get_header(path,length=3)
    feedback_power = float(header[2][2])
    delay = float(header[1][2])

    if plot:
        plt.plot(smsrs,linewidths/1e3,'.')
        plt.title(feedback_power)
        plt.ylabel('Linewidth [kHz]')
        plt.xlabel('SMSR [dB]')
        
    return np.array(filtered_linewidths), feedback_power

def get_data2(path):
    df = pd.read_csv(path,header=3,
                     encoding="ISO-8859-1")
    linewidths = df.values[:,0]
    smsrs = df.values[:,1]
    
    header = get_header(path,length=3)
    feedback_power = float(header[2][2])
    delay = int(float(header[0][1]))
    
    return linewidths, feedback_power, delay

def get_data3(path):
    df = pd.read_csv(path,header=4,
                     encoding="ISO-8859-1",delimiter=',')
    linewidths = df.values[:,0]
    smsrs = df.values[:,1]
    
    header = get_header(path,length=4)
    output_power = float(header[1][2])
    feedback_power = float(header[2][2])
    delay = int(float(header[0][1]))
    wavelength = float(header[3][1])
    
    return linewidths, wavelength, output_power

def get_osa_data(path):
    df = pd.read_csv(path,header=3,
                     encoding="ISO-8859-1",delimiter=',')
    wavelengths = df.values[:,0]
    ps = df.values[:,1]
    ps_max = max(ps)
    if np.isnan(ps_max):
        ps_max = -9.53
    
    return wavelengths, ps - ps_max 

def plot_data():
    result = defaultdict(list)     
    
    for path in paths:
        linewidths = []
        fb_power = []
        lws, feedback_power = get_data(path)    
        plt.loglog(np.array([feedback_power] * len(lws)), lws, '.')
        key = feedback_power
        result[key].append(lws)
        
    data = []
    for key in result:
        result[key] = np.concatenate(result[key]) 
        data.append([key, np.mean(result[key]), np.std(result[key])])
        #plt.errorbar(key, np.mean(result[key]), yerr = np.std(result[key]), fmt= '.')
        plt.xscale('log')
        plt.yscale('log')
    data = np.array(data)
    
    powers = np.linspace(0.1, 500)
    
    def f(x,a):
        return a/x
        
    
    plt.plot(powers,f(powers,4e3),label='Theory')
    #plt.errorbar(data[:,0], data[:,1], data[:,2], fmt= '.',label = 'data')
    plt.xlabel('Feedback power [uW]')
    plt.ylabel('Linewidth [kHz]')
    plt.legend()
    plt.ylim(3e2,2e4)
    
#plot_data()
def f(x,a):
    return a/x

def linewidth_theory(feedback_power, nu_0, beta):
    tau = 1/(11e6)
    return nu_0 / (1 + tau*beta*np.sqrt(feedback_power))**2

powers = np.logspace(-7, 2, 1000)

#plt.plot(powers,f(powers,1.5e3),'--',label='Theory')

#plt.axhline(300,color='grey',linestyle='--', label = 'Linewidth floor')

#fig2, ax2 = plt.subplots()

def IQR_filter(linewidths):
    Q1 = np.percentile(linewidths,25,method='midpoint')
    Q3 = np.percentile(linewidths,75,method='midpoint')
    iqr_number = iqr(linewidths, interpolation='midpoint')
    linewidths_filtered = []
    for linewidth in linewidths:
        if (linewidth < Q3+1.5*iqr_number and linewidth > Q1-1.5*iqr_number):
            linewidths_filtered.append(linewidth)
    return linewidths_filtered

def plot_dataset(paths):
    output_power = 4200
    fig, ax = plt.subplots(figsize=(10,7))
    ax.plot(10*np.log10(powers/output_power),linewidth_theory(powers,1e6,2.5e8),'--',label='Theory',color='grey')
    lw_floor= []
    for path, lwa in paths:
        linewidths, feedback_power, delay = get_data2(path)    
        color_dict = {30: 'blue',
                      100: 'red',
                      700: 'green',
                      3000: 'black'}
        
        linewidths_filtered = IQR_filter(linewidths)
        ax.errorbar(10*np.log10(feedback_power/output_power), np.mean(linewidths_filtered), yerr = np.std(linewidths_filtered), fmt= '.', color = 'blue')
        if feedback_power > 10:
            lw_floor.append(np.mean(linewidths_filtered))
        ax.set(xscale='linear',
               yscale='log',
               xlabel='Feedback ratio [dB]',
               ylabel='Linewidth [Hz]',
               xlim=[-77,-5],
               ylim=[3e2,2e6],
               yticks=[1e3,1e4,1e5,1e6],
               yticklabels=['1k','10k','100k','1M'])
        ax.set_ylabel('Linewidth [Hz]',color='blue')
        ax.tick_params(axis='y', labelcolor='blue')
        labels = [item.get_text() for item in ax.get_yticklabels()]

        #ax2.set(xscale='log',
        #        yscale='log')

        #plt.plot(feedback_power, lwa.get_linewidth(),'b.')
        #plt.plot(feedback_power, lwa.fit_linewidth(lower=2e6,upper=8e6),'g.')
        #ax2.plot(lwa.freqs, lwa.powers)
        
    
    ax2 = ax.twinx()  # instantiate a second Axes that shares the same x-axis
    
    color = 'red'
    ax2.set_ylabel('RIN [dB]', color=color)  # we already handled the x-label with ax1
    
    fb, rin = get_rin()
    
    #ax.legend(fontsize = 20)
    ax.grid()
    
    ax2.plot(10*np.log10(fb/output_power), rin, '.', color=color)
    ax2.set(ylim=[-55,-30])
    ax2.tick_params(axis='y', labelcolor=color)
    
    fig.tight_layout()  # otherwise the right y-label is slightly clipped
    
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\linewidth_vs_feedback.pdf", bbox_inches = 'tight')   
    
def plot_wavelengths(paths):
    fig, (ax,ax2) = plt.subplots(2,1,figsize=(10,7),sharex='all')
    for path, osa in paths:
        linewidths, wavelength, output_power = get_data3(path)    
        
        linewidths_filtered = IQR_filter(linewidths)
        #ax.errorbar(wavelength, np.mean(linewidths_filtered), yerr = np.std(linewidths_filtered), fmt= '.', color = 'black')
        ax.plot(wavelength,min(linewidths_filtered),'.',color='black')
        
        wavelengths, powers = get_osa_data(osa)
        
        ax2.plot(wavelengths,powers)
        
        ax.set(xscale='linear',
               yscale='linear',
               xlabel='Wavelength [nm]',
               ylabel='Min. linewidth [Hz]',
               ylim=[0,2000],
               xlim=[1510,1560],)
        ax2.set(ylim=[-60,10],
                ylabel='Relative power [dB]')
    plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\linewidth_vs_wavelength.pdf", bbox_inches = 'tight')   
#plot_dataset(paths5)
#plot_dataset(paths4)

plot_wavelengths(paths6)

 
