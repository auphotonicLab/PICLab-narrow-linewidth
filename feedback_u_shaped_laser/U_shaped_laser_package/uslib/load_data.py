"""Functions for loading and plotting raw data"""

#Third party imports
import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

#First party imports
import uslib.fit_functions as ff

class DshSpectrum:
    """Class representing a DSH spectrum
    """

    def __init__(self, path, path_bg=None, center = 0) -> None:
        """Makes instance of a DSH spectrum.
        It is possible to pass two spectra where the
        second spectrum is treated as a background spectrum
        which is subtracted from the first.

        Parameters
        ----------
        path : str
            Path to DSH spectrum
        path_bg : str, optional
            Path to background spectrum, by default None
        center : int, optional
            Shift of the frequency axis in MHz.
            Set this to the value of the EOM modulation frequency
            (typically 80 MHz) to center the spectrum about 0. 
            Set to 0 by default
        """
        if path_bg is None:
            fs, ps = self.get_data(path)
            params = self.extract_meas_params(path)
            self.freqs = fs - center
            self.powers = ps
            self.powers_lin = 10**(ps/10)
            self.power_max = max(ps)
            self.params = params
            self.center = center
        else:
            signal = DshSpectrum(path,center=center)
            background = DshSpectrum(path_bg,center=center)
            powers_difference_lin = abs(signal.powers_lin - background.powers_lin)
            powers_difference_log = 10*np.log10(powers_difference_lin)
            self.signal = signal
            self.background = background
            self.freqs = signal.freqs
            self.powers = powers_difference_log
            self.powers_lin = powers_difference_lin
            self.power_max = max(self.powers)
            self.params = signal.params
            self.center = center

    def set_center(self, new_center):
        """Change value of center

        Parameters
        ----------
        new_center : float
            New center value 
        """
        self.center = new_center

    def get_data(self, path):
        """Returns esa data from file path. This function works on data from
        O:\\Tech_Photonics\\Projects\\Narrow Linewidth\\MFB Chips\\Chip 3 Feedback measurements
        from 2024-02-18 and onwards

        Example of valid file path:

        O:\\Tech_Photonics\\Projects\\Narrow Linewidth\\MFB Chips\\Chip 3 Feedback measurements
        \\Measurements_2024-02-22\\2024-02-22_12-01-21single_measurement_
        \\2024-02-22_12-01-21_ESA_full_spectrum_, EOM off,feedback_-47.58 dB.txt

        Args:
            path (str): Path of data file
        Returns:
            freqs: array of ESA frequencies
            powers: array of ESA powers in dBm
        """

        data = np.loadtxt(path)
        freqs = data[0,:]*1e-6
        powers = data[1,:]
        return freqs, powers

    def plot(self, label=''):
        """Plot DSH spectrum
        Args:
            label (str, optional): Plot label. Defaults to empty string.
        """
        plt.plot(self.freqs,self.powers,label=label)
        plt.xlabel('Fourier frequency [MHz]')
        plt.ylabel('ESA power [dBm]')

    def fit_profile(self, threshold_close: float,
            threshold_mid: float, threshold_far: float, plot = True):
        """Fits DSH spectrum to a Gaussian about the center and a Lorentzian to the tails 
        and extracts the FWHM from both

        Args:
            fs: Fourier freqencies, assumed to be centered about profile.
            If this is not the case, set center = EOM modulation frequency
            in __init__ or use the set_center() class method.
            ps: ESA powers
            threshold_close (float): Maximum value from the center to make a Gaussian fit
            threshold_mid (float): Minimum value from the center to make a Lorentzian fit
            threshold_far (float): Maximum value from the center to make a Lorentzian fit
            plot (bool, optional): Plots data and fit. Defauls to True

        Returns:
            Gaussian FWHM, Lorentzian FWHM
        """
        fs = self.freqs
        ps = self.powers - self.power_max

        filter_close = abs(fs) < threshold_close
        filter_far = (abs(fs) > threshold_mid) &  (abs(fs) < threshold_far)

        params_close,*_ = curve_fit(ff.gauss_log,fs[filter_close],ps[filter_close])
        params_far,*_ = curve_fit(ff.lor_log,fs[filter_far],ps[filter_far])

        fwhm1 = abs(params_close[0])*2*np.sqrt(2*np.log(2))*np.sqrt(10/np.log(10))
        fwhm2 = 2*abs(params_far[1])

        if plot:
            plt.plot(fs,ps)
            plt.plot(fs,ff.gauss_log(fs,*params_close),label = 'Gaussian fit')
            plt.plot(fs,ff.lor_log(fs,*params_far),label= 'Lorentzian fit')
            plt.xlim([-4,4])
            plt.ylim([-40,5])
            plt.ylabel('DSH power [dBc]')
            plt.xlabel('Carrier detuning [MHz]')
            plt.legend()
        return fwhm1, fwhm2

    def extract_meas_params(self, path):

        '''
        A method to extract the measurement parameters used for a given spectrum.
        Argument: path
            Type: str
                    File path                
        Returns: params_dict
            Type: dict
                    A dictionary containing all the information saved in the header
                    of the EOM on, peak range .txt file.
                    The units used are most likely: meters, watts, volts, dB, MHz
        '''

        with open(path,encoding="utf8") as data:

            #Making sure that all the information is in the same format
            header = data.readline().strip().replace('# ','').replace(', ',',').replace(':','=').replace(' =','=').replace('= ','=')
            header2 = data.readline().strip().replace('#  ','').replace('# ','').replace('Parameters: ','').replace(', ',',').replace(':','=').replace(' =','=').replace('= ','=')

        #Making sure that no empty values are included
        header_final = [i for i in header.split(',') if i]

        header2_final = [i for i in header2.split(',') if i]

        all_params_list = header_final + header2_final


        params_dict = {}
        #Creating the dictionary
        for parameter_string in all_params_list:

            param_list = parameter_string.split('=')

            key = param_list[0]
            value = param_list[1]
            #Finding the first digit of the float in the value part of the string
            for j, val in enumerate(value):
                if val.isdigit() or val=='-':
                    first_placement = j
                    break
            #Finding the last digit of the float in the value part of the string
            for j in range(len(value)-1,-1,-1):

                if value[j].isdigit():
                    last_placement = j+1
                    break
            #Obtaining the full number and turning it into a float
            try:
                float_value = float(value[first_placement:last_placement])

            except ValueError:
                float_value = value
                #print('The value for' + key + 'is not a float')
            #Saving the key and value in the dictionary
            params_dict[key] = float_value

        return params_dict

class laser_powers:
    '''
    Class extracting laser and feedback powers from separate .txt files
    Calculates variance and mean
    '''

    def __init__(self, directory):
        
        files = os.listdir(directory)

        measurements = files.copy()

        laser_path = None
        feedback_path = None


        def path(file):
            return directory + '\\' + file

        for file in files:

            if file.endswith('Laser_power_readings.txt'):
                laser_path = path(file)

            if file.endswith('Feedback_power_readings.txt'):
                feedback_path = path(file)

            if file.endswith('.txt'):
                measurements.remove(file)

        no_of_meas = len(measurements)

        self.laser_powers = [[] for _ in range(no_of_meas)] #Powers
        self.las_avg = [None for _ in range(no_of_meas)] #Average
        self.las_var = [None for _ in range(no_of_meas)] #Variance

        self.fb_powers = [[] for _ in range(no_of_meas)]
        self.fb_avg = [None for _ in range(no_of_meas)]
        self.fb_var = [None for _ in range(no_of_meas)]

        if laser_path != None:

            with open(laser_path) as laser_file:

                laser_lists = laser_file.readlines()
            
                for i in range(no_of_meas): 

                    self.laser_powers[i] = eval(laser_lists[i+1]) #First line is header
                    self.las_avg[i] = np.average(eval(laser_lists[i+1]))
                    self.las_var[i] = np.var(eval(laser_lists[i+1]))
                    

        if feedback_path !=None:

            with open(feedback_path) as feedback_file: 
                
                feedback_lists = feedback_file.readlines()

                for i in range(no_of_meas):
                    
                    self.fb_powers[i] = eval(feedback_lists[i+1]) #First line is header
                    self.fb_avg[i] = np.average(eval(feedback_lists[i+1]))
                    self.fb_var[i] = np.var(eval(feedback_lists[i+1]))






def single_laser_powers(path: str):
    '''
    Works regardsless of using comma as delimiter or not.

    Returns: laser power, time
    
    '''

    with open(path) as powers_file: 

        powers_lists = powers_file.readlines()

        try:
            powers = list(eval(powers_lists[0+1])) #In watts

            time = list(eval(powers_lists[1+1])) #In seconds

        except SyntaxError:

            powers_lists[0+1]=powers_lists[1].replace(' ', ', ')
            powers_lists[1+1] = powers_lists[2].replace(' ', ', ')

            #First line is header

            powers = list(eval(powers_lists[0+1])) #In watts

            time = list(eval(powers_lists[1+1])) #In seconds

    return powers, time
            



#UPDATED VERSION OF GET_SINGLE_MEASUREMENT_PATHS
def get_single_measurement(directory: str):
    """Updated version of get_single_measurement_paths
    Gets background subtracted DshSpectrum classes
    in full (160 MHz typ.) span and close (10/20 MHz tpy.) span
    as well as OSA spectrum if present

    Args:
        directory (str): Single measurement folder path.
        Example directory:
        "O:\\Tech_Photonics\\Projects\\Narrow Linewidth\\MFB Chips
        \\Chip 3 Feedback measurements\\Measurements_2024-02-22
        \\2024-02-22_12-01-21single_measurement_"


    Returns:
        dsh_full: instance of DshSpectrum
            DSH spectrum of the full span
        dsh_close: instance of DshSpectrum
            DSH spectrum of the close span
        osa : instance of OsaSpectrum
            Full span OSA spectrum
    """
    #THERE SHOULD BE A SIMPLER IMPLEMENTATION OF THIS METHOD
    files = os.listdir(directory)

    def path(file):
        return directory + '\\' + file
    
    #Sort out png files
    txt_files = [file for file in files if file.endswith('.txt')]
    
    #Placeholders for the different paths
    path_full_bg = None
    path_full_signal = None
    path_close_bg = None
    path_close_signal = None
    path_osa = None

    path_laser = None
    path_feedback = None
    path_opt = None

    laser_power_time_dict = {}

    for txt_file in txt_files:
        if "ESA_full_spectrum_, EOM off" in txt_file:
            path_full_bg = path(txt_file)
        if "ESA_full_spectrum_, EOM on" in txt_file:
            path_full_signal = path(txt_file)
        if "ESA_peak_spectrum_, EOM off" in txt_file:
            path_close_bg = path(txt_file)
        if "ESA_peak_spectrum_, EOM on" in txt_file:
            path_close_signal = path(txt_file)
        if "OSA_full_spectrum" in txt_file:
            path_osa = path(txt_file)

        if txt_file.endswith('Laser_power_readings.txt'):
            path_laser = path(txt_file)

        if txt_file.endswith('Feedback_power_readings.txt'):
            path_feedback = path(txt_file)

        if txt_file.endswith('Adv_laser_power_readings.txt'):
            path_opt = path(txt_file)

    if path_full_signal != None:
        dsh_full = DshSpectrum(path_full_signal,path_full_bg)
    else:
        dsh_full = None

    if path_close_signal != None:
        #Centering these spectra about the modulation frequency
        dsh_close = DshSpectrum(path_close_signal,path_close_bg,center=80)
    else:
        dsh_close = None

    if path_osa == None:
        osa = None
    else:
        osa = OsaSpectrum(path_osa)

    if path_laser != None:
        laser_power, laser_time = single_laser_powers(path_laser)

        laser_power_time_dict ['laser_power'] = laser_power
        laser_power_time_dict ['laser_time'] = laser_time

    if path_feedback != None:
        feedback_power, feedback_time = single_laser_powers(path_feedback)

        laser_power_time_dict ['feedback_power'] = feedback_power
        laser_power_time_dict ['feedback_time'] = feedback_time

    if path_opt != None:
        opt_power, opt_time = single_laser_powers(path_opt)

        laser_power_time_dict ['optimization_power'] = opt_power
        laser_power_time_dict ['optimization_time'] = opt_time

    return dsh_full, dsh_close, osa, laser_power_time_dict





#UPDATED VERSION OF GET_ALL_DATA
def get_lab_session_data(directory):
    """Used to get data for all single measurements in a given lab session

    Args:
        directory (str): directory path for a measurement session.
        Example directory:
        "O:\\Tech_Photonics\\Projects\\Narrow Linewidth\\MFB Chips
        \\Chip 3 Feedback measurements\\Measurements_2024-02-22"

    Returns:
        Array containing data for all single measurements
    """
    files = os.listdir(directory)


    def path(file):
        return directory + '\\' + file
    
    #Get subfolders in directory
    paths_dir = [path(file) for file in files if os.path.isdir(path(file))]
    
    data = [get_single_measurement(e) for e in paths_dir]

    dsh_full = [tuple[0] for tuple in data]
    dsh_close = [tuple[1] for tuple in data]
    osa = [tuple[2] for tuple in data]
    laser_readings = [tuple[3] for tuple in data]
    
    if not laser_readings[0]: #If the first measurement has an empty dictionary
        laser_readings = laser_powers(directory)

    return dsh_full, dsh_close, osa, laser_readings






#MOVED FROM DATA_PROCESSING MODULE
def feedback_ratio(laser_power,feedback_power,laser_ref,
                    laser_power_coef = 1/40, coupling_ref = 0.4, feedback_coef = 1.0):
    '''The calculation of the feedback ratio using Simon's derivation.
    It assumes initially a coupling of 0.4 between the laser and the fiber.
    The arguments could be taken from the header of each measurement
    (see ld.extract_meas_params method)
    laser_power_coef and feedback_coef depends on the setup,
    as it is the amount of splitting done before the power meters.
    '''
    return 10*np.log10(coupling_ref**2
                        * laser_power*feedback_power*laser_power_coef*
                        feedback_coef/laser_ref**2)

class OsaSpectrum:
    """Class representing an OSA spectrum
    """

    def __init__(self, path) -> None:
        """Makes instance of an OSA spectrum.

        Parameters
        ----------
        path : str
            Path to the OSA spectrum 
        """
        wav, ps = self.get_data(path)
        
        self.wavelengths = wav
        self.powers = ps
        self.peak_power = max(ps)
        
        #THERE SHOULD BE A SIMPLER IMPLEMENTATION OF THIS
        self.peak_wavelength = wav[np.where(ps == max(ps))[0][0]]

    def get_data(self, path):
        """Returns OSA data from file path

        Parameters
        ----------
        path : str
            path to OSA spectrum

        Returns
        -------
        wav : numpy.ndarray
            array of wavelengths
        ps : numpy.ndarray
            array of powers
        """
        df = np.loadtxt(path)

        wav = df[0,:]*1e9
        ps = df[1,:]

        return wav, ps
    
    def plot(self):
        """Plots OSA spectrum
        """
        plt.plot(self.wavelengths,self.powers)
        plt.ylim(-80,0)
        plt.xlabel('Wavelength [nm]')
        plt.ylabel('Power [dBm]')
