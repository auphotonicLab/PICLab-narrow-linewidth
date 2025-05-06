"""
Module for analyzing laser linewidth measurements.

This module provides a class for loading, processing and analyzing laser linewidth
measurements, including frequency noise (FN) and relative intensity noise (RIN) data.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

class LWA:
    """
    Class for analyzing laser linewidth measurements.
    
    This class provides methods to load and process laser linewidth data from various
    measurement files, including frequency noise (FN) and relative intensity noise (RIN)
    measurements.
    
    Attributes
    ----------
    path : str
        Path to the measurement file
    header_lines : int
        Number of header lines in the file
    type : str
        Type of measurement ('PSD', 'RIN', or 'Power')
    freqs : numpy.ndarray
        Array of frequency values
    powers : numpy.ndarray
        Array of power values
    df : float
        Frequency step size
    """
    
    def __init__(self, path, header_lines=13):
        """
        Initialize LWA object.

        Parameters
        ----------
        path : str
            Path to the measurement file
        header_lines : int, optional
            Number of header lines in the file, by default 13
        """
        self.path = path
        self.header_lines = header_lines
        self.type = self.get_type()
        df = pd.read_csv(self.path,header=self.header_lines,
                         encoding="ISO-8859-1")
        self.freqs = df.values[:,0]
        self.powers = df.values[:,1]
        self.df = self.freqs[1] - self.freqs[0]
    
    def get_header(self):
        """
        Extract header information from the measurement file.

        Returns
        -------
        list
            List of header lines split into components
        """
        lines = []
        try:
            with open(self.path) as file:
                for _ in range(self.header_lines):
                    line = file.readline()
                    lines.append(line.split()[1:])
            return lines
        
        except UnicodeDecodeError:
            with open(self.path,'rb') as file:
                for _ in range(self.header_lines):
                    line = file.readline().decode("unicode_escape")
                    lines.append(line.split()[1:])
            return lines
    
    def get_type(self):
        """
        Determine the type of measurement from the header.

        Returns
        -------
        str
            Type of measurement ('PSD', 'RIN', or 'Power')
        """
        lines = self.get_header()
        try:
            y_label = lines[self.header_lines-1][0]
        except IndexError:
            y_label = lines[0][0]

        if 'Frequency' in y_label:
            return 'PSD'
        if 'Intensity' in y_label:
            return 'RIN'
        if 'Powermeter' in y_label:
            return 'Power'
        
        else:
            print('No type found')
    
    def get_linewidth(self):
        """
        Extract linewidth value from the header.

        Returns
        -------
        float
            Linewidth value in Hz
        """
        lines = self.get_header()
        
        return float(lines[11][0][:-2].replace(',','.'))
        
    def fit_linewidth(self, lower = 1e6, upper = 10e6):
        """
        Fit linewidth using data in specified frequency range.

        Parameters
        ----------
        lower : float, optional
            Lower frequency bound for fitting, by default 1e6
        upper : float, optional
            Upper frequency bound for fitting, by default 10e6

        Returns
        -------
        float
            Fitted linewidth value in Hz
        """
        sort = (self.freqs > lower) & (self.freqs < upper)
        freqs_filtered = self.freqs[sort]
        powers_filtered = self.powers[sort]
        
        def const(x,df):
            return df
        
        p_opt,_ = curve_fit(const,freqs_filtered,powers_filtered)
        
        return p_opt[0]*np.pi
        
    def plot(self,scale='log',factor=1,label='',title=''):
        """
        Plot the measurement data.

        Parameters
        ----------
        scale : str, optional
            Scale type ('log' or 'lin'), by default 'log'
        factor : float, optional
            Scaling factor for the power values, by default 1
        label : str, optional
            Plot label, by default ''
        title : str, optional
            Plot title, by default ''
        """
        plt.xlabel('Fourier frequency [Hz]')
        
        if self.type == 'PSD':
            plt.ylabel('FN PSD [Hz$^2$/Hz]')
            plt.loglog(self.freqs, self.powers*factor,label=label)
            if title:
                plt.title(title)
        if self.type == 'RIN':
            plt.ylabel('RIN [dBc/Hz]')
            if scale == 'log':
                plt.semilogx(self.freqs, self.powers,label=label)
            if scale == 'lin':
                lin_powers = 10**(self.powers/10)
                plt.loglog(self.freqs,lin_powers*factor,label=label)