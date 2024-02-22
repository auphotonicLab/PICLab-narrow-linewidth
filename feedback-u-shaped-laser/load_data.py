import os
import numpy as np
import matplotlib.pyplot as plt

#Functions for loading and plotting raw data

def get_esa_data(path,plot=False,center_about_carrier=False):
    #Returns:
    #freqs: frequency axis in MHz
    #powers: ESA power in dBm 
    data = np.loadtxt(path)
    freqs = data[0,:]*1e-6
    if center_about_carrier:
        freqs = freqs - 80
    powers = data[1,:]
    if plot:
        plot_spectrum(freqs,powers)
    return freqs, powers

def get_data_from_folder(directory):
    files = os.listdir(directory)
    def path(file):
        return directory + '\\' + file
    return ([path(files[1]), path(files[3])], [path(files[5]), path(files[7])])

def plot_spectrum(freqs,powers,label=''):
    plt.plot(freqs,powers,label=label)
    plt.xlabel('Fourier frequency [MHz]')
    plt.ylabel('ESA power [dBm]')

def get_all_data(directory):
    files = os.listdir(directory)
    def path(file):
        return directory + '\\' + file
    return [path(file) for file in files]