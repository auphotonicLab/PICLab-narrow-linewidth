import os
import numpy as np
import matplotlib.pyplot as plt

#Functions for loading and plotting raw data

class LoadData(object):
        
    def __init__(self):
        pass

    def get_esa_data(self, path: str ,plot=False,center_about_carrier=False):
        """Returns esa data from a txt file path

        Args:
            path (str): Path of data file
            plot (bool, optional): Plots data if True. Defaults to False.
            center_about_carrier (bool, optional): Centers data about the EOM modulation frequency (80 MHz) if true. Defaults to False.

        Returns:
            freqs: array of ESA frequencies
            powers: array of ESA powers
        """
        data = np.loadtxt(path)
        freqs = data[0,:]*1e-6
        if center_about_carrier:
            freqs = freqs - 80
        powers = data[1,:]
        if plot:
            self.plot_spectrum(freqs,powers)
        return freqs, powers
    
    def get_single_measurement_paths(self, directory: str):
        """Gets all paths within a single measurement folder, sorted into arrays of ESA data.

        Args:
            directory (str): Single measurement folder path

        Returns:
            Tuple: Contains 2 elements: (full ESA spectra, close ESA spectra)
            - Each of these contain paths for: [background (EOM off), signal (EOM on)]
            ( [full background, full signal], [close background, close signal] ) 
        """
        files = os.listdir(directory)
        def path(file):
            return directory + '\\' + file
        return ([path(files[1]), path(files[3])], [path(files[5]), path(files[7])])
    
    def plot_spectrum(self, freqs,powers,label=''):
        """Plots an ESA spectrum from data

        Args:
            freqs (array): ESA frequencies
            powers (array): ESA powers
            label (str, optional): Plot label. Defaults to empty string.
        """
        plt.plot(freqs,powers,label=label)
        plt.xlabel('Fourier frequency [MHz]')
        plt.ylabel('ESA power [dBm]')
    
    def get_all_data(self, directory):
        """Used to get paths for all single measurement in a given lab session

        Args:
            directory (str): directory path for a measurement session

        Returns:
            Array containing paths for all single measurements
        """
        files = os.listdir(directory)
        def path(file):
            return directory + '\\' + file
        return [path(file) for file in files]

    def extract_meas_params(self, directory):

        '''
        A method to extract the measurement parameters used for a given measurement. The information is taken from the dataset where the EOM is turned on and the range is set for the peak.

        Argument: directory
            Type: str
                    A path to a folder from which the measurement information is taken from
                
        Returns: params_dict
            Type: dict
                    A dictionary containing all the information saved in the header of the EOM on, peak range .txt file.
                    The units used are most likely: meters, watts, volts, dB, MHz
        
        '''

        data = open(self.get_data_from_folder(directory)[1][1]) #This corresponds to the measurement taken for the peak range with the EOM on 

        header = data.readline().strip().replace('# ','').replace(', ',',').replace(':','=').replace(' =','=').replace('= ','=') #Making sure that all the information is in the same format
        header2 = data.readline().strip().replace('#  ','').replace('# ','').replace('Parameters: ','').replace(', ',',').replace(':','=').replace(' =','=').replace('= ','=')


        header_final = [i for i in header.split(',') if i] #Making sure that no empty values are included

        header2_final = [i for i in header2.split(',') if i]

        all_params_list = header_final + header2_final


        params_dict = {}

        for parameter_string in all_params_list: #Creating the dictionary
            
            param_list = parameter_string.split('=')

            key = param_list[0]
            value = param_list[1]

            for j in range(len(value)): #Finding the first digit of the float in the value part of the string

                if value[j].isdigit() or value[j]=='-':
                    first_placement = j
                    break

            for j in range(len(value)-1,-1,-1): #Finding the last digit of the float in the value part of the string

                if value[j].isdigit():
                    last_placement = j+1
                    break

            float_value = float(value[first_placement:last_placement]) #Obtaining the full number and turning it into a float

            params_dict[key] = float_value #Saving the key and value in the dictionary

        return params_dict