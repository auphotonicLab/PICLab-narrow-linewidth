# -*- coding: utf-8 -*-
"""
Created on Fri Jul 19 11:33:20 2024

@author: au622616
"""


import matplotlib.pyplot as plt 
import numpy as np
from file_management_lib import get_paths
from scipy.signal import find_peaks
import pandas as pd
from matplotlib.patches import Rectangle

path = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\2024-07-18_15-34-28\result.txt"
path_no = r"C:\Users\au622616\OneDrive - Aarhus universitet\U shaped measurements\18-7\2024-07-18_14-53-44\result.txt"
    
def get_data(path):
    df = pd.read_csv(path,header=3,
                     encoding="ISO-8859-1")
    lw = df.values[:,0]
    smsr = df.values[:,1]
    return lw, smsr

lw, smsr = get_data(path)

fig, ax = plt.subplots(figsize=[8,5])



props = dict(boxstyle='round', facecolor='wheat', alpha=1)
#ax.text(30, 8, '$<\Delta f$ = 21 kHz \n $L = 700$ m', bbox=props, fontsize = 17)

ax.add_patch(Rectangle((0, 0), 30, 30,alpha=.12,color='red'))
ax.add_patch(Rectangle((30, 0), 30, 30,alpha=.12,color='green'))

ax.set(xlabel='SMSR [dB]',
       ylabel='Linewidth [kHz]',
       xlim=[0,40],
       ylim=[0,10])

ax.axvline(30,linestyle='--',color='grey')

ax.plot(smsr,lw/1e3,'.', color = 'black')

plt.savefig(r"C:\Users\au622616\OneDrive - Aarhus universitet\Documents\Dual feedback figures\smsr_vs_linewidth.pdf",bbox_inches='tight')

lw2, smsr2 = get_data(path_no)

mean = np.mean(lw2)
std = np.std(lw2)