#Functions that has to do with post processing of data

import numpy as np
import matplotlib.pyplot as plt
from .load_data import LoadData
from .fit_functions import FitFunctions
from scipy.optimize import curve_fit

class DataProcessing(object):
    """Class containing functions for processing data

    Args:
        object (_type_): _description_
    """
    def __init__(self):
        """Initialize other modules from the package
        """
        self.ld = LoadData()
        self.ff = FitFunctions()

    def subtract_background(self, path_signal: str,path_bg: str,k: float =1):
        """Subtracts background (EOM off) spectrum from the signal (EOM on) spectrum 

        Args:
            path_signal (str): Path for signal
            path_bg (str): Path for background 
            k (float, optional): Multiplication factor for background subtraction. Defaults to 1.

        Returns:
            freqs, powers_difference
            - freqs: ESA frequencies
            - power_difference: Background subtracted signal
        """
        freqs, powers = self.ld.get_esa_data(path_signal)
        freqs_bg, powers_bg = self.ld.get_esa_data(path_bg)
    
        powers_lin = 10**(powers/10)
        powers_bg_lin = 10**(powers_bg/10)
    
        powers_difference_lin = abs(powers_lin - k*powers_bg_lin)
        powers_difference = 10*np.log10(powers_difference_lin)
        return freqs, powers_difference

    def get_subtracted_background(self, signal: str,background: str,k: float = 1, plot=True, center_about_carrier = False):
        """Subtracts background (EOM off) spectrum from the signal (EOM on) spectrum
            Extension of the 'subtract_background' method

        Args:
            signal (str): Path for signal
            background (str): Path for background
            k (float, optional): Multiplication factor for background subtraction. Defaults to 1.
            plot (bool, optional): Plot resultant spectrum. Defaults to True.
            center_about_carrier (bool, optional): Centers data about the EOM modulation frequency (80 MHz) if true. Defaults to False.

        Returns:
            freqs_new, powers_new
            - freqs_new: ESA frequencies
            - powers_new: Background subtracted signal
        """
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

    
    def get_full_spectrum_from_folder(self, directory: str,k: float = 1,plot = False,center_about_carrier = False):
        """Subtracts background from full spectrum (160 MHz span)

        Args:
            directory (str): Path for single measurement folder
            k (float, optional): Multiplication factor for background subtraction. Defaults to 1.
            plot (bool, optional): Plot resultant spectrum. Defaults to False.
            center_about_carrier (bool, optional): Centers data about the EOM modulation frequency (80 MHz) if true. Defaults to False.
        Returns:
            fs, ps
            - fs: ESA frequencies
            - ps: Background subtracted signal
        """
        esa_full, esa_close = self.ld.get_single_measurement_paths(directory)
        fs, ps = self.get_subtracted_background(esa_full[1], esa_full[0],k,plot,center_about_carrier)
        return fs, ps
    
    def get_close_spectrum_from_folder(self, directory,k=1,plot=False,center_about_carrier=False):
        """Subtracts background from close spectrum
        Args:
            directory (str): Path for single measurement folder
            k (float, optional): Multiplication factor for background subtraction. Defaults to 1.
            plot (bool, optional): Plot resultant spectrum. Defaults to False.
            center_about_carrier (bool, optional): Centers data about the EOM modulation frequency (80 MHz) if true. Defaults to False.
        Returns:
            fs, ps
            - fs: ESA frequencies
            - ps: Background subtracted signal
        """
        esa_full, esa_close = self.ld.get_single_measurement_paths(directory)
        fs, ps = self.get_subtracted_background(esa_close[1], esa_close[0],k,plot,center_about_carrier)
        return fs, ps
    
    def fit_profile(self, fs, ps, threshold_close: float, threshold_mid: float, threshold_far: float, plot = True):
        """Fits DSH spectrum to a Gaussian about the center and a Lorentzian to the tails 
        and extracts the FWHM from both

        Args:
            fs: ESA frequencies
            ps: ESA powers
            threshold_close (float): Maximum value from the center to make a Gaussian fit
            threshold_mid (float): Minimum value from the center to make a Lorentzian fit
            threshold_far (float): Maximum value from the center to make a Lorentzian fit
            plot (bool, optional): Plots data and fit. Defauls to True

        Returns:
            Gaussian FWHM, Lorentzian FWHM
        """
        filter_close = abs(fs) < threshold_close
        filter_far = (abs(fs) > threshold_mid) &  (abs(fs) < threshold_far)
    
        fs_close = fs[filter_close]
        ps_close = ps[filter_close]
        fs_far = fs[filter_far]
        ps_far = ps[filter_far]
    
        params_close,_ = curve_fit(self.ff.gauss_log,fs_close,ps_close)
        params_far,_ = curve_fit(self.ff.lor_log,fs_far,ps_far)
        self.fwhm1 = abs(params_close[0])*2*np.sqrt(2*np.log(2))*np.sqrt(10/np.log(10))
        self.fwhm2 = 2*abs(params_far[1])

        if plot:
            plt.plot(self, fs,ps)
            plt.plot(fs,self.ff.gauss_log(fs,*params_close),label = 'Gaussian fit')
            plt.plot(fs,self.ff.lor_log(fs,*params_far),label= 'Lorentzian fit')
            plt.xlim([-4,4])
            plt.ylim([-40,5])
            plt.ylabel('DSH power [dBc]')
            plt.xlabel('Carrier detuning [MHz]')
            plt.legend()
        return self.fwhm1, self.fwhm2
    
    def fit_profile_from_folder(self, directory: str, threshold_close: float, threshold_mid: float, threshold_far: float, plot = True):
        """Fits close spectrum from a single measurement folder 

        Args:
            directory (str): Path for single measurement folder
            threshold_close (float): Maximum value from the center to make a Gaussian fit
            threshold_mid (float): Minimum value from the center to make a Lorentzian fit
            threshold_far (float): Maximum value from the center to make a Lorentzian fit
            plot (bool, optional): Plots data and fit. Defauls to True

        Returns:
            Gaussian FWHM, Lorentzian FWHM
        """
        esa_full, esa_close = self.ld.get_single_measurement_paths(directory)
        fs, ps = self.get_subtracted_background(esa_close[1], esa_close[0],plot=False, center_about_carrier=True)
        fwhm1, fwhm2 = self.fit_profile(fs, ps, threshold_close, threshold_mid, threshold_far)
        return fwhm1, fwhm2 
    


    def feedback_ratio(self,LaserPWR,FeedbackPWR,Laser_ref, Laser_power_coef = 1/40, coupling_ref = 0.4, Feedback_coef = 1): 
        '''The calculation of the feedback ratio using Simon's derivation. 
        It assumes initially an coupling of 0.4 between the laser and the fiber. 
        The arguments could be taken from the header of each measurement (see ld.extract_meas_params method)
        Laser_power_coef and Feedback_coef depends on the setup, as it is the amount of splitting done before the power meters. 
        '''
        return 10*np.log10(coupling_ref**2 * LaserPWR*FeedbackPWR*Laser_power_coef*Feedback_coef/Laser_ref**2)