# -*- coding: utf-8 -*-
"""
Created on Wed Mar 22 19:27:17 2023

@author: 45242
"""

"""
Module for file management and path handling.

This module provides utility functions for managing file paths and reading file headers
in the context of laser measurement data.
"""

import os

def get_paths(directory):
    """
    Get full paths for all files in a directory.

    Parameters
    ----------
    directory : str
        Path to the directory

    Returns
    -------
    list
        List of full paths to all files in the directory
    """
    filenames = os.listdir(directory)
    return [directory + "\\" + e for e in filenames]

def get_header(path, length=2):
    """
    Read header lines from a file.

    Parameters
    ----------
    path : str
        Path to the file
    length : int, optional
        Number of header lines to read, by default 2

    Returns
    -------
    list
        List of header lines split into components
    """
    lines = []
    with open(path) as file:
        for i in range(length):
            line = file.readline()
            lines.append(line.split()[1:])
    return lines