# -*- coding: utf-8 -*-
"""
Created on Mon Jul 15 13:59:10 2024

@author: au622616
"""
import math
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

def del_o(del_f):
    return 2*np.pi*del_f

def time_delay(fiber_length):
    c = 299792458 #m/s speed of light
    L = fiber_length #m 
    n_g = 1.468 #group index at 1550nm for silica
    return n_g * L / c

def zeta_func(f,del_f,t_d):
    Omega = 2*np.pi*f    
    return del_o(del_f) * ( 1-math.exp(-t_d*del_o(del_f)) * (np.cos(Omega*t_d) + del_o(del_f)/Omega * np.sin(Omega*t_d)) ) / ( del_o(del_f)**2 + Omega**2)

def zeta_fit(freq, linewidth, offset, length):
    return 10*np.log10(zeta_func(freq,linewidth,time_delay(length)))+offset

delay_dict = {
    3000 : [2, 0.0005, 400e3,3e3,1e1],
    100 : [10, 0.001, 3e6,1e2,1e5],
    30 : [30, 0.003, 10e6,30,3e5],
    700 : [2, 0.0005, 1e6, 7e2, 30e3]}



center = 0
def get_linewidth(freqs, powers, delay, plot = False):
    settings = delay_dict[delay] 
    freqs = freqs - center
    powers = powers - max(powers)
    filt = (abs(freqs) > 200e3) & (abs(freqs) < settings[2])
    p_opt, _ = curve_fit(zeta_fit, freqs[filt], powers[filt], p0 = [settings[4], 11, settings[3]])
    
    if plot:
        plt.figure(figsize=[8,5])
        plt.plot(freqs/1e3, powers, label = 'ESA spectrum')
        plt.plot(freqs/1e3, zeta_fit(freqs,*p_opt), label = 'Fit')
        
    return p_opt