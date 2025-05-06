import numpy as np
import lwa_lib
from file_management_lib import get_paths

def get_hf_paths(directory):
    hf_paths = [p for p in get_paths(directory) if 'PSD' in p]
    return hf_paths

def load_hf_data(path):
    lwa = lwa_lib.LWA(path)
    return lwa.freqs, lwa.powers

def get_noise_floor_hf(freqs, ps, floor_range):
    condition = (freqs > floor_range[0]) & (freqs < floor_range[1]) 
    return np.mean(ps[condition])

def get_data(directory,floor_range=[5e6,6e6]):

    paths = get_hf_paths(directory)
    number = len(paths)

    freqs_all = [[]]*number
    ps_all =  [[]]*number
    lw_all =  [0]*number


    for i,path in enumerate(paths):
        freqs, ps = load_hf_data(path)

        freqs_all[i] = freqs
        ps_all[i] = ps

        floor = get_noise_floor_hf(freqs,ps,floor_range)

        lw_all[i] = np.pi*floor

    return lw_all,freqs_all,ps_all