import numpy as np
from scipy import integrate

#Using the beta separation method to estimate the effective linewidth. 
#Using a kind of heaviside function to get the indices where the FN PSD powers are above the beta sep. line, rather than a specific cut-off.


def beta_sep_condition(freqs,ps):
    
    condition_indices = np.where (ps - 8*np.log(2)*freqs/np.pi**2 > 0)

    return condition_indices


def beta_sep_line(freqs, ps, cutoff):


    condition =  beta_sep_condition(freqs,ps) #(freqs < cutoff) & (freqs > 0)
    new_freqs = freqs[condition]
    new_ps = ps[condition]
    integral = integrate.cumtrapz(new_ps, new_freqs, initial=0)
    A = integral[-1]
    eff_lw = np.sqrt(8 * np.log(2) * A)
    return new_freqs, new_ps, integral, eff_lw
