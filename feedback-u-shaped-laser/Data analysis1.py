#%%
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import fit_functions as ff
import load_data as ld
import data_processing as dp
import matplotlib.animation as animation

#%%
data_dir = r"O:\Tech_Photonics\Projects\Narrow Linewidth\MFB Chips\Chip 3 Feedback measurements\Measurements_2024-02-18"
dirs = ld.get_all_data(data_dir)

# %%
fig, ax = plt.subplots()
artists = []
for directory in dirs:
    if ('Read' not in directory) and ('PD' not in directory):
        print(directory)
        plt.xlim([-1,1])
        plt.ylim([-60,5])
        plt.xlabel('Frequency detuning [MHz]')
        plt.ylabel('Spectrum power [dBc]')
        fs, ps = dp.get_close_spectrum_from_folder(directory,plot=False,center_about_carrier=True)
        container = ax.plot(fs,ps,color='black')
        artists.append(container)
# %%
ani = animation.ArtistAnimation(fig=fig, artists=artists, interval=400)
plt.show()
from IPython.display import HTML
HTML(ani.to_jshtml())
# %%
writer = animation.PillowWriter(fps=5, metadata=dict(artist='Me'), bitrate=1800)
ani.save('scatter.gif', writer=writer)
# %%
_,_ = dp.get_full_background(dirs[25],plot=True)
# %%
