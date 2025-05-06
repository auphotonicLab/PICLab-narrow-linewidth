import numpy as np
from file_management_lib import get_paths

#For modified data. Having been divided by prop factor in main script
""""
    data_ESA = plot_ESA_fast(plot=False)
    freqs = data_ESA[0,:] - center 
    ps_raw = 10**(data_ESA[1,:]/10)
    k=1.06
    n=1.5
    c = 3e8
    carrier_power = max(ps_raw)
    time_delay = abs(delay - 3)*n/c
    prop_factor = 2*np.pi**2 * time_delay**2 * k * rbw *carrier_power
    ps = ps_raw / prop_factor
"""

def get_csh_paths(directory):
    csh_paths = [p for p in get_paths(directory) if 'esa' in p]
    return csh_paths

def load_csh_data(path):
    data = np.loadtxt(path, skiprows=1)
    freqs = data[:, 0]
    ps = data[:, 1]
    lw = np.min(ps)
    return freqs, ps, lw

def get_noise_floor_csh(freqs, ps):
    condition = (freqs > 9e5) & (freqs < 1e6)
    return np.mean(ps[condition])


def get_data(directory,floor_range=[9e5,1e6]):

    paths = get_csh_paths(directory)
    number = len(paths)

    freqs_all = [[]]*number
    ps_all =  [[]]*number
    lw_all =  [0]*number


    for i,path in enumerate(paths):
        freqs, ps = load_csh_data(path)

        freqs_all[i] = freqs
        ps_all[i] = ps

        floor = get_noise_floor_csh(freqs,ps,floor_range)

        lw_all[i] = np.pi*floor

    return lw_all,freqs_all,ps_all