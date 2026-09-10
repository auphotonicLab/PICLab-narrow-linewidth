# %% [markdown]
# # Template 1 -- Waveguide modes, dispersion, and FSR
#
# EMode part of Simulations 1-4: solve the fundamental mode, sweep width, get the group index
# from a wavelength sweep, and predict your racetrack's FSR.
#
# Edit the parameters below for your assigned device before you start.

# %%
import emodeconnection as emc

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

r_ring = 75_000       # [nm] racetrack bend radius
lc_racetrack = 20_000 # [nm] racetrack straight (coupling) section length


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


em.close()

# %% [markdown]
# ## Task 1: Compare confinement
#
# Compare `mode_TE0.png` / `mode_TM0.png` against the printed `n_eff` and TE-fraction.
#
# - Which mode is more tightly confined, and why -- consider the core's aspect ratio (350 nm
#   tall, ~1.1 um wide) and which polarization "sees" the narrower dimension.
# - How does that show up quantitatively (n_eff, TE/TM fraction, contour extent into cladding)?

# %% [markdown]
# ## Task 2: Width sweep
#
# Sweep the core width over the range given in the manual and record the fundamental mode's
# `n_eff` at each width (reuse the pattern above in a loop; no need to `em.close()` between
# iterations). Plot `n_eff` vs. width and comment on the trend.

# %%
widths_nm = [...]  # TODO: fill in the range from the manual

# TODO: loop over widths_nm, solve for n_eff at each width, and plot n_eff vs width

# %% [markdown]
# ## Task 3: Group index
#
# n_g = n_eff - lambda * dn_eff/dlambda. Sweep wavelength at your nominal width and fit a line to
# n_eff(lambda) to get dn_eff/dlambda, then n_g.
#
# On this install: loop `FDM()` yourself once per wavelength rather than `em.sweep()` (drops
# connection mid-sweep) or `em.group_index()` (crashes with "not enough memory").

# %%
wavelengths_nm = [...]  # TODO: a handful of points around your operating wavelength

# TODO: solve n_eff at each wavelength (one FDM() call per point), fit a line, get n_g

# %% [markdown]
# ## Task 4: Predict the racetrack's FSR
#
# Round-trip length: L = 2*pi*r + 2*Lc (r = `r_ring`, Lc = `lc_racetrack`, defined above).
#
# FSR_lambda = lambda^2 / (n_g * L);  FSR_f = c / (n_g * L)

# %%
# TODO: compute L, FSR_lambda [nm], and FSR_f [GHz] from your n_g above
