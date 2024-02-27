#Creating a class with fitting functions:


#Defining functions from the booklets, that can be used for fitting purposes


import math
import numpy as np


class FitFunctions(object):
        
    def __init__(self):
        pass
        
    def gauss_log(self, x,a,b):
        return -0.5*(x/a)**2 + b
    
    def lor_log(self, x,a,df):
        return a + 10*np.log10(df/(df**2 + x**2))
    
    def del_o(self, del_f):
        return 2*np.pi*del_f
    
    def time_delay(self, fiber_length): #Booklet definition of time delay
        c = 299792458 #m/s speed of light
        L = fiber_length
        n_g = 1.468 #group index at 1550nm for silica
        return n_g * L / c
    
    def Lorentzian_dB(self, omega, A, del_f,freq_center):
        return 10*np.log10(A**2 * np.pi *del_f / ((freq_center-omega)**2 + (np.pi*del_f)**2) )
    
    def Lor_dB(self, x,a,df):
        return a + 10*np.log10(df/(df**2 + x**2))
    
    #Below timelags of 10µs
    
    def PSD_real_laser_dB(self, omega, A, del_f, freq_center, a1):
    
        return 10*np.log10(A * math.exp(- (freq_center-omega)**2/(4*a1)) * np.real(math.exp(1j*np.pi* (freq_center-omega)*del_f/(2*a1))*math.erfc( (np.pi*del_f + 1j*(freq_center-omega))/ (2*np.sqrt(a1)) ) ) )
    
    def del_o(self, del_f):
        return 2*np.pi*del_f
    
    
    def zeta_func(self, f,del_f,t_d):
        
        Omega = 2*np.pi*f
        
        
        return self.del_o(del_f) * ( 1-math.exp(-t_d*self.del_o(del_f)) * (np.cos(Omega*t_d) + self.del_o(del_f)/Omega * np.sin(Omega*t_d)) ) / ( self.del_o(del_f)**2 + Omega**2)

def zeta_zero(self, del_f,t_d):
    return ( 1-math.exp(-t_d*self.del_o(del_f)) * (1 + self.del_o(del_f)*t_d ) ) / self.del_o(del_f)


def f_minus(self, f,freq_shift):
    return f - freq_shift

def q_func(self, A_1,A_2):
    return (1+(A_2/A_1)**2)/(2*A_2/A_1) #A_1 amplitude of field going through time delay, A_2 amplitude of field going through EOM

def dirac_delta(self, x,limit):
    
    return np.piecewise(x,[np.abs(x) <= limit/2, np.abs(x) > limit/2],[1/limit,0] )


def DSH_ideal_PSD(self, f,freq_shift,del_f,t_d,limit):

    return 2*(self.zeta_func(f_minus(f,freq_shift),del_f,t_d) + np.pi*math.exp(-t_d*self.del_o(del_f))*dirac_delta(2*np.pi*f_minus(f,freq_shift),limit) + 4*np.pi*q_func(1,1)*dirac_delta(2*np.pi*f,limit) )

def Gaussian_dB(self, x,A,freq_center,var):
    return 10*np.log10 (A/np.sqrt(2*np.pi*var) * math.exp(- (x-freq_center)**2 /(2*var) ) ) #var is the square of the standard deviation

def Gauss_dB(self, x,a,b):
    return a - b*x**2
