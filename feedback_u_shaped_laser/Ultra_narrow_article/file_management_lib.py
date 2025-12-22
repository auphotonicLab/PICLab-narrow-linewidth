# -*- coding: utf-8 -*-
"""
Created on Wed Mar 22 19:27:17 2023

@author: 45242
"""

import os

def get_paths(directory):
    
    filenames = os.listdir(directory)
    return [directory + "\\" + e for e in filenames]

def get_header(path,length=2):
     lines = []
     with open(path) as file:
         for i in range(length):
             line = file.readline()
             lines.append(line.split()[1:])
     return lines