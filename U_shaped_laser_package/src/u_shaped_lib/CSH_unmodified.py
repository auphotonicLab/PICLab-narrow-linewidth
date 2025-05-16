"""
Module for analyzing unmodified Coherent Self-Heterodyne (CSH) measurements.

This module provides functionality to load and process raw CSH measurement data,
including noise floor analysis and linewidth calculations. The data needs to be
divided by the propagation factor for proper analysis.
"""

import numpy as np
from .file_management_lib import get_paths

#For unmodified data. Needs to be divided by prop factor

""""
    data_ESA = plot_ESA_fast(plot=False)
    freqs = data_ESA[0,:] - center 
    ps_raw = 10**(data_ESA[1,:]/10)
    k=1.06
    n=1.5
    c = 3e8
    carrier_power = max(ps_raw)
    time_delay = abs(delay - 3)*n/c
    prop_factor = 2*np.pi**2 * time_delay**2 * k * rbw *carrier_power
    ps = ps_raw / prop_factor
"""


def get_csh_paths(directory):
    """
    Get paths to all CSH measurement files in a directory.

    Parameters
    ----------
    directory : str
        Path to the directory containing measurement files

    Returns
    -------
    list
        List of paths to CSH measurement files
    """
    csh_paths = [p for p in get_paths(directory) if 'esa' in p]
    return csh_paths


def load_csh_data(path,center,delay,rbw):
    """
    Load and process raw CSH measurement data.

    Parameters
    ----------
    path : str
        Path to the measurement file
    center : float
        Center frequency for data processing
    delay : float
        Time delay value
    rbw : float
        Resolution bandwidth

    Returns
    -------
    tuple
        Two numpy arrays containing:
        - freqs : array of frequencies
        - ps : array of power values divided by propagation factor
    """
    data_ESA = np.loadtxt(path, skiprows=1)
    freqs = data_ESA[0,:] - center 
    ps_raw = 10**(data_ESA[1,:]/10)

    k=1.06
    n=1.5
    c = 3e8
    carrier_power = max(ps_raw)
    time_delay = abs(delay - 3)*n/c
    prop_factor = 2*np.pi**2 * time_delay**2 * k * rbw *carrier_power
    
    ps = ps_raw/prop_factor

    return freqs, ps


def get_noise_floor_csh(freqs, ps, floor_range):#Floor range chosen to be outside the range of the sidemodes from DC
    """
    Calculate the noise floor from CSH data in a specified range.

    Parameters
    ----------
    freqs : numpy.ndarray
        Array of frequencies
    ps : numpy.ndarray
        Array of power values
    floor_range : tuple
        Tuple of (lower_freq, upper_freq) defining the range for noise floor calculation

    Returns
    -------
    float
        Mean power value in the specified range
    """
    condition = (freqs > floor_range[0]) & (freqs < floor_range[1]) 
    return np.mean(ps[condition])


def get_data(directory,center,delay,rbw,floor_range=[9e5,1e6]):
    """
    Load and process all unmodified CSH measurements in a directory.

    Parameters
    ----------
    directory : str
        Path to the directory containing measurement files
    center : float
        Center frequency for data processing
    delay : float
        Time delay value
    rbw : float
        Resolution bandwidth
    floor_range : list, optional
        Range for noise floor calculation [lower_freq, upper_freq], by default [9e5,1e6]

    Returns
    -------
    tuple
        Three lists containing:
        - lw_all : list of calculated linewidths
        - freqs_all : list of frequency arrays
        - ps_all : list of power arrays
    """
    paths = get_csh_paths(directory)
    number = len(paths)

    freqs_all = [[]]*number
    ps_all =  [[]]*number
    lw_all =  [0]*number
    
    print('Linewidths found from average between',floor_range[0]*1e-3,'kHz and',floor_range[1]*1e-3,'kHz')


    for i,path in enumerate(paths):
        freqs, ps = load_csh_data(path,center,delay,rbw)

        freqs_all[i] = freqs
        ps_all[i] = ps

        floor = get_noise_floor_csh(freqs,ps,floor_range)

        lw_all[i] = np.pi*floor

    return lw_all,freqs_all,ps_all