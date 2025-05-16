# -*- coding: utf-8 -*-
"""
Created on Tue Jul 30 11:28:52 2024

@author: au622616
"""

import matplotlib.pyplot as plt 
import numpy as np
from .file_management_lib import get_paths, get_header
from scipy.signal import find_peaks
import pandas as pd
import re

path = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\25-07\Mirror1_7.1_8mW\0_SOA1_0_PhS_one_7.1_mirror_one.csv"
directory_8mW_mirror = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\25-07\Mirror1_7.1_8mW"
directory3 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\25-07\4mW_mirror1_7.1"
directory_4mW_soa1 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\25-07\4mW_mirror1_7.1\SOA1"
directory_4mW_soa2 = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\25-07\4mW_mirror1_7.1\SOA2"
directory_4mW_both = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\25-07\4mW_mirror1_7.1\SOAs_PhS"
directory_8mW = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\25-07\8mW"

def get_mean(path):
    name = path.split('\\')[-1]
    soa_curr = float(name.split('_')[0])
    df = pd.read_csv(path,delimiter=',')
    tail = df.tail(n=5).values[0][0]
    power = float(tail.split()[1])*1e6
    return soa_curr, power

fig, ax = plt.subplots()

def plot_rel_loss(directory,input_power,color):
    for path in get_paths(directory):
        if 'SOA' in path:
            current, power  = get_mean(path)
            ax.plot(current,10*np.log10(power/input_power),'.',color=color)

plot_rel_loss(directory_8mW_mirror,8000,'blue')
plot_rel_loss(directory_8mW,8000,'red')
plot_rel_loss(directory_4mW_soa1,4000,'green')
plot_rel_loss(directory_4mW_soa2,4000,'orange')
plot_rel_loss(directory_4mW_both,4000,'black')

ax.set(xlabel='SOA1 current [mA]',
       ylabel='Total loss [dB]')