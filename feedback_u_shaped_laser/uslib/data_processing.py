#Functions that has to do with post processing of data

import os
import numpy as np
import matplotlib.pyplot as plt
from .load_data import LoadData
from .fit_functions import fit_functions
from scipy.optimize import curve_fit

class data_processing(object):
        
    def __init__(self):
        
        self.ld = LoadData()
        self.ff = fit_functions()

    
    def get_full_spectrum_from_folder(self, directory,k=1,plot=False,center_about_carrier=False):
        esa_full, esa_close = self.ld.get_data_from_folder(directory)
        fs, ps = self.get_subtracted_background(esa_full[1], esa_full[0],k,plot,center_about_carrier)
        return fs, ps
    
    def get_close_spectrum_from_folder(self, directory,k=1,plot=False,center_about_carrier=False):
        esa_full, esa_close = self.ld.get_data_from_folder(directory)
        fs, ps = self.get_subtracted_background(esa_close[1], esa_close[0],k,plot,center_about_carrier)
        return fs, ps
    
    def get_full_background(self, directory,k=1,plot=False):
        esa_full, esa_close = self.ld.get_data_from_folder(directory)
        fs, ps = self.ld.get_esa_data(esa_full[0])
        if plot:
            self.ld.plot_spectrum(fs,ps)
        return fs, ps
    
    def fit_profile(self, fs, ps, threshold_close, threshold_mid, threshold_far):
        
        filter_close = abs(fs) < threshold_close
        filter_far = (abs(fs) > threshold_mid) &  (abs(fs) < threshold_far)
    
        fs_close = fs[filter_close]
        ps_close = ps[filter_close]
        fs_far = fs[filter_far]
        ps_far = ps[filter_far]
    
        plt.plot(self, fs,ps)
        params_close,_ = curve_fit(self.ff.gauss_log,fs_close,ps_close)
        params_far,_ = curve_fit(self.ff.lor_log,fs_far,ps_far)
        self.fwhm1 = abs(params_close[0])*2*np.sqrt(2*np.log(2))*np.sqrt(10/np.log(10))
        self.fwhm2 = 2*abs(params_far[1])
    
        plt.plot(fs,self.ff.gauss_log(fs,*params_close),label = 'Gaussian fit')
        plt.plot(fs,self.ff.lor_log(fs,*params_far),label= 'Lorentzian fit')
        
    
        plt.xlim([-4,4])
        plt.ylim([-40,5])
        plt.ylabel('DSH power [dBc]')
        plt.xlabel('Carrier detuning [MHz]')
        plt.legend()
        return self.fwhm1, self.fwhm2
    
    def fit_profile_from_folder(self, directory, threshold_close, threshold_mid, threshold_far):
        esa_full, esa_close = self.ld.get_data_from_folder(directory)
        fs, ps = self.get_subtracted_background(esa_close[1], esa_close[0],plot=False, center_about_carrier=True)
        fwhm1, fwhm2 = self.fit_profile(fs, ps, threshold_close, threshold_mid, threshold_far)
        return fwhm1, fwhm2 
    
    def subtract_background(self, path_spectrum,path_bg,k=1):
        freqs, powers = self.ld.get_esa_data(path_spectrum)
        freqs_bg, powers_bg = self.ld.get_esa_data(path_bg)
    
        powers_lin = 10**(powers/10)
        powers_bg_lin = 10**(powers_bg/10)
    
        powers_difference_lin = abs(powers_lin - k*powers_bg_lin)
        powers_difference = 10*np.log10(powers_difference_lin)
        return freqs, powers_difference
    
    def get_subtracted_background(self, signal,background,k=1, plot=True, center_about_carrier = False):
        freqs, powers = self.ld.get_esa_data(signal)
        freqs_new, powers_new = self.subtract_background(signal,background,k)
        if plot:
            self.ld.plot_spectrum(freqs,powers,label='Raw')
            self.ld.plot_spectrum(freqs_new,powers_new,label='Background subtracted')
            plt.legend()
        if center_about_carrier:
            freqs_new = freqs_new - 80
            powers_new = powers_new - max(powers_new)
        return freqs_new, powers_new
