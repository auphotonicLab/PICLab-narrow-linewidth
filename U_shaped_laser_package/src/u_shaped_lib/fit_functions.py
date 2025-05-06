"""
Module containing mathematical functions for fitting laser measurement data.

This module provides various mathematical functions used for fitting and analyzing
laser measurement data, including Gaussian and Lorentzian functions, time delay
calculations, and power spectral density (PSD) functions.
"""

import math
import numpy as np

def gauss_log(x, a, b):
    """
    Gaussian function in logarithmic scale (base e).

    Parameters
    ----------
    x : numpy.ndarray
        Input values
    a : float
        Width parameter
    b : float
        Offset parameter

    Returns
    -------
    numpy.ndarray
        Gaussian function values in log scale
    """
    return -0.5*(x/a)**2 + b

def lor_log(x, a, df):
    """
    Lorentzian function in logarithmic scale (base 10).

    Parameters
    ----------
    x : numpy.ndarray
        Input values
    a : float
        Amplitude parameter
    df : float
        Linewidth parameter

    Returns
    -------
    numpy.ndarray
        Lorentzian function values in log scale
    """
    return a + 10*np.log10(df/(df**2 + x**2))

def del_o(del_f):
    """
    Transform frequency to angular frequency.

    Parameters
    ----------
    del_f : float
        Frequency in Hz

    Returns
    -------
    float
        Angular frequency in rad/s
    """
    return 2*np.pi*del_f

def time_delay(fiber_length):
    """
    Calculate time delay in an optical fiber.

    Parameters
    ----------
    fiber_length : float
        Length of the fiber in meters

    Returns
    -------
    float
        Time delay in seconds
    """
    c = 299792458 #m/s speed of light
    L = fiber_length
    n_g = 1.468 #group index at 1550nm for silica
    return n_g * L / c

def Lorentzian_dB(omega, A, del_f, freq_center):
    """
    Lorentzian function in dB scale.

    Parameters
    ----------
    omega : numpy.ndarray
        Angular frequencies
    A : float
        Amplitude parameter
    del_f : float
        Linewidth parameter
    freq_center : float
        Center frequency

    Returns
    -------
    numpy.ndarray
        Lorentzian function values in dB scale
    """
    return 10*np.log10(A**2 * np.pi *del_f / ((freq_center-omega)**2 + (np.pi*del_f)**2) )

def Lor_dB(x, a, df):
    """
    Alternative Lorentzian function in dB scale.

    Parameters
    ----------
    x : numpy.ndarray
        Input values
    a : float
        Amplitude parameter
    df : float
        Linewidth parameter

    Returns
    -------
    numpy.ndarray
        Lorentzian function values in dB scale
    """
    return a + 10*np.log10(df/(df**2 + x**2))

#Below timelags of 10µs

def PSD_real_laser_dB(omega, A, del_f, freq_center, a1):
    """
    Real part of laser power spectral density in dB scale.

    Parameters
    ----------
    omega : numpy.ndarray
        Angular frequencies
    A : float
        Amplitude parameter
    del_f : float
        Linewidth parameter
    freq_center : float
        Center frequency
    a1 : float
        Gaussian width parameter

    Returns
    -------
    numpy.ndarray
        PSD values in dB scale
    """
    return 10*np.log10(A * math.exp(- (freq_center-omega)**2/(4*a1))
                        * np.real(math.exp(1j*np.pi* (freq_center-omega)*del_f/(2*a1))
                                  *math.erfc( (np.pi*del_f + 1j*(freq_center-omega))/ (2*np.sqrt(a1)) ) ) )


def zeta_func(f, del_f, t_d):
    """
    Zeta function for laser linewidth calculations.

    Parameters
    ----------
    f : numpy.ndarray
        Frequencies
    del_f : float
        Linewidth parameter
    t_d : float
        Time delay

    Returns
    -------
    numpy.ndarray
        Zeta function values
    """
    Omega = 2*np.pi*f
    return del_o(del_f) * ( 1-math.exp(-t_d*del_o(del_f)) * (np.cos(Omega*t_d) + del_o(del_f)/Omega * np.sin(Omega*t_d)) ) / ( del_o(del_f)**2 + Omega**2)

def zeta_zero(del_f, t_d):
    """
    Zero-frequency value of zeta function.

    Parameters
    ----------
    del_f : float
        Linewidth parameter
    t_d : float
        Time delay

    Returns
    -------
    float
        Zero-frequency zeta value
    """
    return ( 1-math.exp(-t_d*del_o(del_f)) * (1 + del_o(del_f)*t_d ) ) / del_o(del_f)

def f_minus(f, freq_shift):
    """
    Frequency shift function.

    Parameters
    ----------
    f : numpy.ndarray
        Input frequencies
    freq_shift : float
        Frequency shift value

    Returns
    -------
    numpy.ndarray
        Shifted frequencies
    """
    return f - freq_shift

def q_func(A_1, A_2):
    """
    Q-function for amplitude ratio calculations.

    Parameters
    ----------
    A_1 : float
        First amplitude
    A_2 : float
        Second amplitude

    Returns
    -------
    float
        Q-function value
    """
    return (1+(A_2/A_1)**2)/(2*A_2/A_1) 

def dirac_delta(x, limit):
    """
    Approximate Dirac delta function.

    Parameters
    ----------
    x : numpy.ndarray
        Input values
    limit : float
        Width of the approximation

    Returns
    -------
    numpy.ndarray
        Approximate delta function values
    """
    return np.piecewise(x,[np.abs(x) <= limit/2, np.abs(x) > limit/2],[1/limit,0] )

def DSH_ideal_PSD(f, freq_shift, del_f, t_d, limit):
    """
    Ideal power spectral density for delayed self-heterodyne measurements.

    Parameters
    ----------
    f : numpy.ndarray
        Frequencies
    freq_shift : float
        Frequency shift
    del_f : float
        Linewidth parameter
    t_d : float
        Time delay
    limit : float
        Delta function limit

    Returns
    -------
    numpy.ndarray
        PSD values
    """
    return 2*(zeta_func(f_minus(f,freq_shift),del_f,t_d) + np.pi*math.exp(-t_d*del_o(del_f))*dirac_delta(2*np.pi*f_minus(f,freq_shift),limit) + 4*np.pi*q_func(1,1)*dirac_delta(2*np.pi*f,limit) )

def Gaussian_dB(x, A, freq_center, var):
    """
    Gaussian function in dB scale.

    Parameters
    ----------
    x : numpy.ndarray
        Input values
    A : float
        Amplitude parameter
    freq_center : float
        Center frequency
    var : float
        Variance parameter

    Returns
    -------
    numpy.ndarray
        Gaussian function values in dB scale
    """
    return 10*np.log10 (A/np.sqrt(2*np.pi*var) * math.exp(- (x-freq_center)**2 /(2*var) ) )

def Gauss_dB(x, a, b):
    """
    Simplified Gaussian function in dB scale.

    Parameters
    ----------
    x : numpy.ndarray
        Input values
    a : float
        Amplitude parameter
    b : float
        Width parameter

    Returns
    -------
    numpy.ndarray
        Gaussian function values in dB scale
    """
    return a - b*x**2

def zeta_fit(freq, linewidth, offset, length):
    """
    Zeta function for fitting laser linewidth data.

    Parameters
    ----------
    freq : numpy.ndarray
        Frequencies
    linewidth : float
        Linewidth parameter
    offset : float
        Offset parameter
    length : float
        Fiber length

    Returns
    -------
    numpy.ndarray
        Fitted zeta function values
    """
    return 10*np.log10(zeta_func(freq,linewidth,time_delay(length)))+offset

def R_squared(data, fitfunc_evaluated):
    """
    Calculate R-squared value for fit quality assessment.

    Parameters
    ----------
    data : numpy.ndarray
        Original data
    fitfunc_evaluated : numpy.ndarray
        Evaluated fit function

    Returns
    -------
    float
        R-squared value
    """
    return 1-(((data-fitfunc_evaluated))**2).sum() / ((data-data.mean())**2).sum()