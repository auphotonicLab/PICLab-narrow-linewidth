
# %%
import numpy as np
import emodeconnection as emc
import matplotlib.pyplot as plt

## Set simulation parameters -- your device, edit these
wavelength = 1550   # [nm] wavelength
dx, dy = 10, 10      # [nm] resolution
w_core = 1140        # [nm] waveguide core width
h_core = 350         # [nm] waveguide core height (fixed for this platform)
num_modes = 2        # [-] number of modes

# cladding thickness. Just needs to exceed the mode's decay length. 
# Top cladding is thin (only 100 nm of oxide before air); 
# side and bottom just need to be big enough for the mode to have decayed to ~0 by the window edge.

w_clad = 1500        # [nm] side cladding thickness (SiO2), each side
h_clad = 1500        # [nm] bottom cladding thickness (SiO2)
h_clad_top = 100     # [nm] top cladding thickness (SiO2)
h_air = 1500         # [nm] air above the top cladding, up to the window edge

r_ring = 75e-6       # [µm] racetrack bend radius
lc_racetrack = 20e-6 # [µm] racetrack straight (coupling) section length


# %%
window_width = w_core + 2 * w_clad
clad_height = h_clad + h_core + h_clad_top   # bottom clad + core + thin top clad
window_height = clad_height + h_air


em = emc.EMode(simulation_name='modes', clear='mine')
em.settings(wavelength=wavelength, x_resolution=dx, y_resolution=dy,
            window_width=window_width, window_height=window_height,
            num_modes=num_modes, background_material='Air')

em.shape(name='clad', material='SiO2', width=window_width, height=clad_height, position=[0, clad_height / 2])
em.shape(name='core', material='SiN', width=w_core, height=h_core, position=[0, h_clad + h_core / 2])

em.FDM()
report = em.report()

em.plot()

## Core confinement factor (fraction of mode power in the core) for each mode
core_confinement = em.confinement(shape_list='core', mode_list='all')[0]['core']
for mode in range(num_modes):
    print(f"Mode {mode}: core confinement = {core_confinement[str(mode)]*100:.1f} %")



# %% [markdown]
# ## Task 2: Width sweep
#
# Sweep the core width over the range given in the manual and record the fundamental mode's
# `n_eff` at each width (reuse the pattern above in a loop; no need to `em.close()` between
# iterations). Plot `n_eff` vs. width and comment on the trend.

em.settings(wavelength=wavelength, x_resolution=dx, y_resolution=dy,
            window_width=window_width, window_height=window_height,
            num_modes=1, background_material='Air')


width_sweep = np.linspace(700,1300,7)

# data_width = em.sweep(key='shape, core, width', values=width_sweep, result=['effective_index'])
# neff_data = data_width['effective_index']

core_confinement_sweep = []
neff_data = []
for w in width_sweep:
    em.shape(name='core', material='SiN', width=w, height=h_core,
              position=[0, h_clad + h_core / 2])
    em.FDM()
    conf = em.confinement(shape_list='core', mode_list='all')[0]['core']['0']
    core_confinement_sweep.append(conf)
    neff = em.get('effective_index')
    neff_data.append(neff)


plt.figure()
plt.plot(width_sweep, neff_data, marker='o')
plt.xlabel('Core Width [nm]')   
plt.ylabel('Effective Index (n_eff)')
plt.show() 


plt.figure()
plt.plot(width_sweep, core_confinement_sweep, marker='o')
plt.xlabel('Core Width [nm]')   
plt.ylabel('Core Confinement Factor')
plt.show() 

# %% [markdown]
# ## Task 3: Group index
#
# n_g = n_eff - lambda * dn_eff/dlambda. Sweep wavelength at your nominal width and fit a line to
# n_eff(lambda) to get dn_eff/dlambda, then n_g.


em.shape(name='core', material='SiN', width=w_core, height=h_core, position=[0, h_clad + h_core / 2])
# em.group_index()

wavelength_sweep = np.linspace(1540,1560,5)

data_wavelength = em.sweep(key = 'wavelength', values = wavelength_sweep, result = 'effective_index')

neff_data_wavelength = data_wavelength['effective_index']



em.close()

plt.figure()
plt.plot(wavelength_sweep, neff_data_wavelength, marker='o')
plt.xlabel('Wavelength [nm]')   
plt.ylabel('Effective Index (n_eff)')
plt.show() 

print("n_eff data:", neff_data_wavelength, "at wavelengths:", wavelength_sweep)
central_difference_5_point = (- neff_data_wavelength[4] + 8*neff_data_wavelength[3]  - 8*neff_data_wavelength[1] + neff_data_wavelength[0]) / (12 * (wavelength_sweep[1] - wavelength_sweep[0]))

print("dn/dlambda (Central difference 5-point):", central_difference_5_point)
n_group = neff_data_wavelength[2] - wavelength_sweep[2] * central_difference_5_point

print("Group index n_g = n_eff - lambda * dn_eff/dlambda:", n_group)

# %% [markdown]
# ## Task 4: Predict the racetrack's FSR
#
# Round-trip length: 
L = 2*np.pi*r_ring + 2*lc_racetrack
c=3e8 

lambda_0 = wavelength_sweep[2] * 1e-9 # convert to meters


FSR_lambda = lambda_0**2 / (n_group * L) 
FSR_f = c / (n_group * L)

print(FSR_lambda*1e9, "nm")
print(FSR_f*1e-9, "GHz")




# %%
