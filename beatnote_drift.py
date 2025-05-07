#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Beatnote Drift Analysis Tool

This script provides functionality for analyzing and plotting beatnote drift measurements.
"""

import matplotlib.pyplot as plt
import numpy as np
from file_management_lib import get_paths

def analyze_beatnote_drift(directory, xaxis_label, skip_points=100, freq_threshold=None):
    """
    Analyze beatnote drift from a directory of measurement files.
    
    Parameters:
    -----------
    directory : str
        Path to directory containing beatnote measurement files
    xaxis_label : str
        Label for x-axis in plot
    skip_points : int, optional
        Number of points to skip at start of each measurement (default: 100)
    freq_threshold : float, optional
        If provided, only include measurements below this frequency threshold
        
    Returns:
    --------
    centers : ndarray
        Array of measured beatnote center frequencies
    std : float
        Standard deviation of the center frequencies
    """
    centers = []
    
    # Process each measurement file
    for path in get_paths(directory):
        # Load and process data
        data = np.loadtxt(path, skiprows=1)
        freqs = data[0, skip_points:] / 1e6  # Convert to MHz
        powers = data[1, skip_points:]
        
        # Find peak frequency
        center_freq = freqs[np.argmax(powers)]
        
        # Apply frequency threshold if specified
        if freq_threshold is None or center_freq < freq_threshold:
            centers.append(center_freq)
    
    centers = np.array(centers)
    std = np.std(centers)
    
    return centers, std

def plot_beatnote_drift(centers, xaxis_label, figsize=(12,5), ylim=None, xlim=None):
    """
    Plot beatnote drift data.
    
    Parameters:
    -----------
    centers : ndarray
        Array of measured beatnote center frequencies
    xaxis_label : str
        Label for x-axis
    figsize : tuple, optional
        Figure size (width, height) in inches
    ylim : tuple, optional
        Y-axis limits (ymin, ymax)
    xlim : tuple, optional
        X-axis limits (xmin, xmax)
    """
    plt.figure(figsize=figsize)
    plt.plot(centers, '.')
    plt.xlabel(xaxis_label)
    plt.ylabel('Beat note drift [MHz]')
    
    if ylim is not None:
        plt.ylim(ylim)
    if xlim is not None:
        plt.xlim(xlim)

def plot_beatnote_spectrum(path, skip_points=1):
    """
    Plot a single beatnote spectrum.
    
    Parameters:
    -----------
    path : str
        Path to beatnote spectrum file
    skip_points : int, optional
        Number of points to skip at start of measurement (default: 1)
    """
    data = np.loadtxt(path, skiprows=1)
    freqs = data[0, skip_points:] / 1e6  # Convert to MHz
    powers = data[1, skip_points:]
    plt.plot(freqs, powers)
    plt.xlabel('Frequency [MHz]')
    plt.ylabel('Power [dBm]')

if __name__ == "__main__":
    # Example usage
    directory = "path/to/measurements"
    
    # Analyze drift
    centers, std = analyze_beatnote_drift(
        directory, 
        xaxis_label='Time [min.]',
        freq_threshold=35000
    )
    
    # Plot results
    plot_beatnote_drift(
        centers,
        xaxis_label='Time [min.]',
        ylim=[2800, 3000],
        xlim=[100, 120]
    )
    
    plt.show() 