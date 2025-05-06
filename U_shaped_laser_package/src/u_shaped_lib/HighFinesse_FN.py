"""
Module for analyzing frequency noise measurements from High Finesse equipment.

This module provides functionality to load and process frequency noise (FN) data
from High Finesse measurement equipment, including noise floor analysis and
linewidth calculations.
"""

import numpy as np
import lwa_lib
from file_management_lib import get_paths

def get_hf_paths(directory):
    """
    Get paths to all High Finesse PSD measurement files in a directory.

    Parameters
    ----------
    directory : str
        Path to the directory containing measurement files

    Returns
    -------
    list
        List of paths to PSD measurement files
    """
    hf_paths = [p for p in get_paths(directory) if 'PSD' in p]
    return hf_paths

def load_hf_data(path):
    """
    Load frequency noise data from a High Finesse measurement file.

    Parameters
    ----------
    path : str
        Path to the measurement file

    Returns
    -------
    tuple
        Two numpy arrays containing:
        - freqs : array of frequencies
        - ps : array of power values
    """
    lwa = lwa_lib.LWA(path)
    return lwa.freqs, lwa.powers

def get_noise_floor_hf(freqs, ps, floor_range):
    """
    Calculate the noise floor from frequency noise data in a specified range.

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

def get_data(directory, floor_range=[5e6,6e6]):
    """
    Load and process all High Finesse frequency noise measurements in a directory.

    Parameters
    ----------
    directory : str
        Path to the directory containing measurement files
    floor_range : list, optional
        Range for noise floor calculation [lower_freq, upper_freq], by default [5e6,6e6]

    Returns
    -------
    tuple
        Three lists containing:
        - lw_all : list of calculated linewidths
        - freqs_all : list of frequency arrays
        - ps_all : list of power arrays
    """
    paths = get_hf_paths(directory)
    number = len(paths)

    freqs_all = [[]]*number
    ps_all =  [[]]*number
    lw_all =  [0]*number

    for i,path in enumerate(paths):
        freqs, ps = load_hf_data(path)

        freqs_all[i] = freqs
        ps_all[i] = ps

        floor = get_noise_floor_hf(freqs,ps,floor_range)

        lw_all[i] = np.pi*floor

    return lw_all,freqs_all,ps_all