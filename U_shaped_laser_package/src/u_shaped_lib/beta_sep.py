"""
Module for beta separation method in laser linewidth analysis.

This module implements the beta separation method to estimate effective laser linewidth
by analyzing frequency noise power spectral density (PSD) data. It uses a heaviside-like
function to identify regions where the PSD exceeds the beta separation line.
"""

import numpy as np
from scipy import integrate

#Using the beta separation method to estimate the effective linewidth. 
#Using a kind of heaviside function to get the indices where the FN PSD powers are above the beta sep. line, rather than a specific cut-off.


def beta_sep_condition(freqs,ps):
    """
    Find indices where PSD exceeds beta separation line.

    Parameters
    ----------
    freqs : numpy.ndarray
        Array of frequencies
    ps : numpy.ndarray
        Array of power spectral density values

    Returns
    -------
    tuple
        Indices where PSD exceeds beta separation line
    """
    condition_indices = np.where (ps - 8*np.log(2)*freqs/np.pi**2 > 0)
    return condition_indices


def beta_sep_line(freqs, ps, cutoff):
    """
    Calculate effective linewidth using beta separation method.

    Parameters
    ----------
    freqs : numpy.ndarray
        Array of frequencies
    ps : numpy.ndarray
        Array of power spectral density values
    cutoff : float
        Frequency cutoff value

    Returns
    -------
    tuple
        Four values containing:
        - new_freqs : filtered frequency array
        - new_ps : filtered PSD array
        - integral : cumulative integral of PSD
        - eff_lw : effective linewidth estimate
    """
    condition =  beta_sep_condition(freqs,ps) #(freqs < cutoff) & (freqs > 0)
    new_freqs = freqs[condition]
    new_ps = ps[condition]
    integral = integrate.cumtrapz(new_ps, new_freqs, initial=0)
    A = integral[-1]
    eff_lw = np.sqrt(8 * np.log(2) * A)
    return new_freqs, new_ps, integral, eff_lw
