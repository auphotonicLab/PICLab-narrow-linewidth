

# %%
import emodeconnection as emc



## Set simulation parameters
wavelength = 1550 # [nm] wavelength
dx, dy = 10, 10 # [nm] resolution
w_core = 1140 # [nm] waveguide core width
h_core = 350 # [nm] waveguide core height
h_clad = 100 # [nm] top/bottom cladding thickness (SiO2), each side
num_modes = 1 # [-] number of modes

BOX_nm = 3000 # [nm] buried oxide (BOX)

R_ring_nm = 75_000 # [nm] racetrack bend radius
Lc_racetrack_nm = 20_000 # [nm] racetrack straight (coupling) section length



# --- your device ---
WIDTH_NM = 1140          # [nm] core width
HEIGHT_NM = 350          # [nm] core height (fixed for this platform)
CLAD_NM = 100            # [nm] top oxide cladding
BOX_NM = 3000            # [nm] buried oxide (BOX)

# window padding -- just needs to be big enough that the field has decayed to ~0 at the edges
SIDE_MARGIN_NM = 2000
TOP_MARGIN_NM = 2000
BOTTOM_MARGIN_NM = 1500

# %%
core_y_bottom = BOTTOM_MARGIN_NM + BOX_NM
core_y_centre = core_y_bottom + HEIGHT_NM / 2

window_width = 2 * (WIDTH_NM / 2 + CLAD_NM + SIDE_MARGIN_NM)
window_height = BOTTOM_MARGIN_NM + BOX_NM + HEIGHT_NM + CLAD_NM + TOP_MARGIN_NM

em = emc.EMode(simulation_name='modes', clear='mine')
em.settings(wavelength=wavelength, x_resolution=dx, y_resolution=dy,
            window_width=window_width, window_height=window_height,
            num_modes=2, background_material='Air')

em.shape(name='box', material='SiO2', width=window_width, height=BOTTOM_MARGIN_NM + BOX_NM,
          position=[0, (BOTTOM_MARGIN_NM + BOX_NM) / 2])
em.shape(name='clad', material='SiO2', width=WIDTH_NM + 2 * CLAD_NM, height=HEIGHT_NM + CLAD_NM,
          position=[0, core_y_bottom + (HEIGHT_NM + CLAD_NM) / 2])
em.shape(name='core', material='SiN', width=WIDTH_NM, height=HEIGHT_NM, position=[0, core_y_centre])

# em.plot(component='n', file_name='geometry', file_type='png')  # drop file_name/file_type for a live popup instead

em.FDM()
report = em.report()

# report['_default'] is a dict of [label, n_eff, TE_fraction, loss] rows, keyed oddly --
# just grab the values and sort by n_eff (mode 0 = fundamental, i.e. highest n_eff)
rows = sorted(report['_default'].values(), key=lambda row: row[1], reverse=True)
for label, n_eff, te_pct, loss in rows:
    print(f"{label}: n_eff = {n_eff:.6f}, TE fraction = {te_pct}")

em.plot(component='Ex', mode=0, file_name='mode_TE0', file_type='png')  # fundamental TE-like mode
em.plot(component='Ey', mode=1, file_name='mode_TM0', file_type='png')  # fundamental TM-like mode
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
# Round-trip length: L = 2*pi*r + 2*Lc (r = `R_RING_NM`, Lc = `LC_RACETRACK_NM`, defined above).
#
# FSR_lambda = lambda^2 / (n_g * L);  FSR_f = c / (n_g * L)

# %%
# TODO: compute L, FSR_lambda [nm], and FSR_f [GHz] from your n_g above
