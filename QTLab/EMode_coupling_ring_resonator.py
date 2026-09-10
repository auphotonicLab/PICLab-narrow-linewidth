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

## Set simulation parameters -- your device, edit these
wavelength = 1550   # [nm] wavelength
dx, dy = 10, 10      # [nm] resolution
w_core = 1140        # [nm] waveguide core width
h_core = 350         # [nm] waveguide core height (fixed for this platform)
num_modes = 2        # [-] number of modes


gap = 1040

d = (w_core + gap) / 2   # centre-to-centre offset of each core from x=0


# cladding thickness. Just needs to exceed the mode's decay length. 
# Top cladding is thin (only 100 nm of oxide before air); 
# side and bottom just need to be big enough for the mode to have decayed to ~0 by the window edge.

w_clad = 1500 + d    # [nm] side cladding thickness (SiO2), each side
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
em.shape(name='core1', material='SiN', width=w_core, height=h_core, position=[-d, h_clad + h_core / 2])

em.shape(name='core2', material='SiN', width=w_core, height=h_core, position=[d, h_clad + h_core / 2])

em.FDM()
report = em.report()

em.plot()

# em.plot(component='Ex', mode=0, file_name='mode_symmetric', file_type='png')
# em.plot(component='Ex', mode=1, file_name='mode_antisymmetric', file_type='png')
# em.close()

# rows = sorted(report['_default'].values(), key=lambda row: row[1], reverse=True)
# n_sym, n_anti = rows[0][1], rows[1][1]
# kappa1_per_nm = (np.pi / WAVELENGTH_NM) * (n_sym - n_anti)
# print(f"gap = {GAP_NM} nm: n_sym = {n_sym:.6f}, n_anti = {n_anti:.6f}, kappa1 = {kappa1_per_nm:.4e} 1/nm")

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
