# -*- coding: utf-8 -*-
"""
Created on Wed Jul  3 08:34:17 2024

@author: au622616
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

def get_paths(directory):
    
    filenames = os.listdir(directory)
    return [directory + "\\" + e for e in filenames]

def get_header(path):
     lines = []
     with open(path) as file:
         for i in range(2):
             line = file.readline()
             lines.append(line.split()[1:])
     return lines

directory = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\02-7"

paths = get_paths(directory)

path = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\02-7\2024-07-02_14-49-20test.txt"


def get_data(path, plot=False):
    df = pd.read_csv(path,header=2,
                     encoding="ISO-8859-1")
    linewidths = df.values[:,0]
    smsrs = df.values[:,1]
    
    filtered_linewidths = []
    for i in range(len(smsrs)):
        if (i > 0 and i < (len(smsrs) -1)):
            if (smsrs[i-1] > 35 and smsrs[i] > 35):
                filtered_linewidths.append(linewidths[i])
                
    
    header = get_header(path)
    feedback_power = float(header[1][2])

    if plot:
        plt.plot(smsrs,linewidths/1e3,'.')
        plt.title(feedback_power)
        plt.ylabel('Linewidth [kHz]')
        plt.xlabel('SMSR [dB]')
        
    return np.array(filtered_linewidths),np.array([feedback_power] * len(filtered_linewidths))
        
         

for path in paths:
    lws, feedback_power = get_data(path)    
    plt.loglog(feedback_power, lws, '.')
    
plt.xlabel('Feedback power [uW]')
plt.ylabel('Linewidth [kHz]')
