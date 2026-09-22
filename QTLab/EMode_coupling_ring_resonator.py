# %% [markdown]
# # Template 2 -- Directional coupler gap sweep
#
# This is the EMode part of Simulations 4-5: characterize how strongly two parallel waveguides
# couple as a function of gap, then use that to predict the coupling of your actual racetrack
# rings.


# %%
import numpy as np
import emodeconnection as emc
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

## Set simulation parameters -- your device, edit these
wavelength = 1550   # [nm] wavelength
dx, dy = 10, 10      # [nm] resolution
w_core = 1180        # [nm] waveguide core width
h_core = 350         # [nm] waveguide core height (fixed for this platform)
num_modes = 2        # [-] number of modes


gap = 1040

d = (w_core + gap) / 2   # centre-to-centre offset of each core from x=0


w_clad = 1500 + d    # [nm] side cladding thickness (SiO2), each side
h_clad = 1500        # [nm] bottom cladding thickness (SiO2)
h_clad_top = 100     # [nm] top cladding thickness (SiO2)
h_air = 1500         # [nm] air above the top cladding, up to the window edge

r_ring = 75e-6       # [m] racetrack bend radius
lc_racetrack = 20e-6 # [m] racetrack straight (coupling) section length


# %%

window_width = w_core + 2 * w_clad
clad_height = h_clad + h_core + h_clad_top   # bottom clad + core + thin top clad
window_height = clad_height + h_air

etch_depth = h_core 

em = emc.EMode(simulation_name='modes', clear='mine')
em.settings(wavelength=wavelength, x_resolution=dx, y_resolution=dy,
            window_width=window_width, window_height=window_height,
            num_modes=num_modes, background_material='Air', boundary_condition='TE')

em.shape(name = 'clad', material = 'SiO2', width = window_width, height = clad_height)

em.shape(name='dual core', material='SiN', width=window_width, height=h_core, mask = [w_core, w_core], mask_offset=[-d, d], etch_depth=etch_depth, fill_material='SiO2')

# em.shape(name='core2', material='SiN', width=w_core, height=h_core, position=[d, h_clad + h_core / 2])

# em.shape(name = 'core', material = 'SiN', width = window_width, height = h_core, mask = w_core, etch_depth = etch_depth, fill_material = 'SiO2')

em.shape(name = 'clad_top', material = 'SiO2', width = window_width, height = h_clad_top)

em.FDM()
report = em.report()

em.plot()




# %% 



gap_sweep = np.linspace(800, 1400, 11)  # [nm] range of gaps to sweep


neff_data = []


for g in gap_sweep:
    d = (w_core + g) / 2


    em.shape(name='dual core', material='SiN', width=window_width, height=h_core, mask = [w_core, w_core], mask_offset=[-d, d], etch_depth=etch_depth, fill_material='SiO2')

    em.FDM()
    neff = em.get('effective_index')
    neff_data.append(neff)



# %%

plt.figure()
plt.plot(gap_sweep, neff_data, marker='.')
plt.xlabel('Gap [nm]')
plt.ylabel('Effective index n_eff')
plt.show()

print(neff_data)

neff_sym =  np.array([neff_data[i][0] for i in range(len(neff_data))])
neff_asym = np.array([neff_data[i][1] for i in range(len(neff_data))])
kappa1_data = np.pi * (neff_sym - neff_asym) / wavelength

# plt.figure()
# plt.plot(gap_sweep, kappa1_data, marker='.')
# plt.xlabel('Gap [nm]')
# plt.ylabel(r'Coupling coefficient $\kappa_1$ [1/nm]')
# plt.show()

em.close()

print(gap_sweep)
print(kappa1_data)

# %%

def exp_fit(gap, kappa1_g0, gamma_gap):
    return kappa1_g0 * np.exp(-gamma_gap * (gap - gap_sweep[0]))


fit_params = curve_fit(exp_fit, gap_sweep, kappa1_data, p0=[kappa1_data[0], 0.01])


plt.figure()
plt.plot(gap_sweep, kappa1_data, marker='.')
plt.xlabel('Gap [nm]')
plt.ylabel(r'Coupling coefficient $\kappa_1$ [1/nm]')
plt.plot(gap_sweep, exp_fit(gap_sweep, *fit_params[0]), label='Exponential fit', color='red')
plt.legend()
plt.show()
print('kappa1_g0, gamma_gap:', fit_params[0])  # kappa1_g0, gamma_gap

# %%

path_length = 2 * np.pi * r_ring + 2* lc_racetrack  # total path length of the racetrack
    
print('path length:', path_length)

Lc_eff = lc_racetrack + np.sqrt(2 * np.pi * r_ring*1e9 / fit_params[0][1])*1e-9  # [m]; gamma_gap is the second parameter

kappa_1  = exp_fit(gap_sweep, *fit_params[0])  # [1/nm]

print ('Lc_eff, kappa_1:', Lc_eff, kappa_1)

kappa_squared = np.sin(kappa_1 * Lc_eff*1e9)**2  # kappa_1 [1/nm] * Lc_eff [m -> nm]

alpha_loss = 1 #dB/cm
alpha_loss_np_per_cm = alpha_loss * np.log(10) / 10  # dB/cm -> power attenuation coefficient [1/cm]

a_loss = np.exp(-alpha_loss_np_per_cm *  path_length*1e2 /2)  # amplitude loss over the round trip (path_length converted m -> cm)

print('a_loss:', a_loss)
coupling_comparison = 1-a_loss**2

plt.plot(gap_sweep, kappa_squared, marker='.')
# plt.plot(gap_sweep, 0.997, label='Predicted power coupling', color='red')

plt.hlines(coupling_comparison, gap_sweep[0], gap_sweep[-1], label='1-a^2', color='red')
plt.xlabel('Gap [nm]')
plt.ylabel(r'Power coupling $|\kappa|^2$')
plt.show()






# %% [markdown]
# ## Task 1: Gap sweep and exponential fit
#
# kappa1 falls off exponentially with gap: kappa1(g) = kappa1(g0) * exp(-gamma_gap * (g - g0)).
#
# Sweep a range of gaps (reuse the pattern above in a loop) and fit log(kappa1) vs. gap to get
# gamma_gap and kappa1(g0).
#
# Think about how wide a gap range you need: too narrow, and gamma_gap is poorly constrained by
# the fit (rule of thumb: the swept range should span several 1/gamma_gap decay lengths). The real
# chip's bus-ring gaps only vary ~100-150 nm for a given width -- is that enough on its own?

# %%
gaps_nm = [...]  # TODO: pick a range wide enough to constrain the fit -- see the note above

# TODO: loop over gaps_nm (reusing the pattern above), collect kappa1 at each gap,
# then fit log(kappa1) vs gap to get gamma_gap and kappa1_g0

# %% [markdown]
# ## Task 2: Coupling for your actual ring gaps
#
# A racetrack's bend also contributes to coupling, beyond the straight section Lc: the manual's
# bend correction is
#
# Lc_eff = Lc + sqrt(2*pi*r / gamma_gap)
#
# and the predicted power coupling is |kappa|^2 = sin^2(kappa1(g) * Lc_eff), with kappa1(g)
# evaluated from your fit above (not re-solved in EMode).
#
# Compute Lc_eff and |kappa|^2 for the actual gaps used on your chip.

# %%
onchip_gaps_nm = [...]  # TODO: the actual gaps used on your assigned rings

# TODO: compute Lc_eff (once -- it doesn't depend on gap) and |kappa|^2 for each gap in onchip_gaps_nm
