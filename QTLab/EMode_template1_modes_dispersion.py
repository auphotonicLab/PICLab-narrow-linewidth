# %% [markdown]
# # Template 1 -- Waveguide modes, dispersion, and FSR
#
# This is the EMode part of Simulations 1-4 from the manual: solve the fundamental mode, sweep
# width, get the group index from a wavelength sweep, and use it to predict your racetrack's FSR.
#
# **What's given:** the EMode code that solves for the modes of one waveguide cross-section --
# draw the layers, run `FDM()`, read off `n_eff`. That's the whole pattern; reuse it (copy, then
# edit) for every task below.
#
# **What you build:** the width sweep, the wavelength sweep with its linear fit for the group
# index, and the FSR calculation -- the same way you'd do it from the manual.
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

# cladding thickness, each side -- just needs to be big enough that the mode has decayed to ~0
# before it reaches the window edge (see note below); it does NOT need to match the real chip's
# oxide thickness
w_clad = 1500        # [nm] side cladding thickness (SiO2), each side
h_clad = 1500        # [nm] top/bottom cladding thickness (SiO2), each side

r_ring = 75_000       # [nm] racetrack bend radius
lc_racetrack = 20_000 # [nm] racetrack straight (coupling) section length

# %% [markdown]
# A couple of things about this EMode install worth knowing before you write any more shapes:
#
# - `em.shape(..., position=[x, y])` places a shape's **centre**, not a corner -- handy below
#   since the core just needs to sit in the middle of the window.
# - Don't draw an explicit silicon substrate block. With this solver, a finite Si block sitting
#   against the simulation window's hard wall behaves as its own resonant cavity and returns a
#   wall of spurious high-index modes instead of your waveguide mode. Setting
#   `background_material='SiO2'` sidesteps this entirely -- there's no Si anywhere in the window,
#   so there's no hard wall for it to resonate against.

# %%
window_width = w_core + 2 * w_clad
window_height = h_core + 2 * h_clad

em = emc.EMode(simulation_name='modes', clear='mine')
em.settings(wavelength=wavelength, x_resolution=dx, y_resolution=dy,
            window_width=window_width, window_height=window_height,
            num_modes=num_modes, background_material='SiO2')  # background fills in the cladding on all sides

em.shape(name='core', material='SiN', width=w_core, height=h_core, position=[0, window_height / 2])

# em.plot(component='n')  # drop file_name/file_type for a live popup instead

em.FDM()
report = em.report()

em.plot()
# report['_default'] is a dict of [label, n_eff, TE_fraction, loss] rows, keyed oddly --
# just grab the values and sort by n_eff (mode 0 = fundamental, i.e. highest n_eff)
rows = sorted(report['_default'].values(), key=lambda row: row[1], reverse=True)
for label, n_eff, te_pct, loss in rows:
    print(f"{label}: n_eff = {n_eff:.6f}, TE fraction = {te_pct}")

# em.plot(component='Ex', mode=0, file_name='mode_TE0', file_type='png')  # fundamental TE-like mode
# em.plot(component='Ey', mode=1, file_name='mode_TM0', file_type='png')  # fundamental TM-like mode
em.close()

# %% [markdown]
# ## Task 1: Compare confinement
#
# Look at `mode_TE0.png` and `mode_TM0.png` alongside the printed `n_eff` and TE-fraction for
# each mode.
#
# - Which mode is more tightly confined to the core, and why -- think about the core's aspect
#   ratio (350 nm tall, ~1.1 um wide) and which polarization "sees" the narrower dimension.
# - How does that show up quantitatively, not just visually (n_eff, TE/TM fraction, how far the
#   contours extend into the cladding)?

# %% [markdown]
# ## Task 2: Width sweep
#
# Sweep the core width over the range given in the manual and record the fundamental mode's
# `n_eff` at each width, the same way the cell above did for a single width.
#
# - Reuse the pattern above inside a loop over widths -- you don't need to `em.close()` between
#   iterations, just call `em.settings()` / `em.shape()` / `em.FDM()` again for each width.
# - Plot `n_eff` vs. width, and comment on the trend.

# %%
widths_nm = [...]  # TODO: fill in the range from the manual

# TODO: loop over widths_nm, solve for n_eff at each width, and plot n_eff vs width

# %% [markdown]
# ## Task 3: Group index
#
# n_g = n_eff - lambda * dn_eff/dlambda. Sweep wavelength at your nominal width and fit a line to
# n_eff(lambda) to get dn_eff/dlambda, then n_g.
#
# Two things to watch for on this install:
# - `em.sweep()` intermittently drops the connection mid-sweep here -- looping `FDM()` yourself,
#   once per wavelength, is slower but doesn't have that problem.
# - `em.group_index()` (EMode's built-in route) reproducibly crashes on this install ("not enough
#   memory") even for a single mode -- the manual fit above is the reliable route here.

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
