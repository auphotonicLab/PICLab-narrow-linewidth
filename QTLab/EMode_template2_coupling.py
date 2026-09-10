# %% [markdown]
# # Template 2 -- Directional coupler gap sweep
#
# This is the EMode part of Simulations 5-6: characterize how strongly two parallel waveguides
# couple as a function of gap, then use that to predict the coupling of your actual racetrack
# rings.
#
# **What's given:** the EMode code that solves the coupled-waveguide supermodes (symmetric +
# antisymmetric) for one gap and turns that into kappa1. Reuse this pattern (copy, then edit) for
# the sweep.
#
# **What you build:** the gap sweep, the exponential fit kappa1(g) = kappa1(g0) *
# exp(-gamma_gap*(g-g0)), and the effective-coupling-length calculation for your actual ring
# gaps.

# %%
import numpy as np
import matplotlib.pyplot as plt
import emodeconnection as emc

# --- your device -- edit these ---
WIDTH_NM = 1140
HEIGHT_NM = 350
CLAD_NM = 100
BOX_NM = 3000
WAVELENGTH_NM = 1550

R_RING_NM = 75_000
LC_RACETRACK_NM = 20_000

GAP_NM = 700   # centre-to-centre gap for the example solve below

SIDE_MARGIN_NM = 2000
TOP_MARGIN_NM = 2000
BOTTOM_MARGIN_NM = 1500

# %% [markdown]
# Same two things as in Template 1: `position=[x, y]` is each shape's centre, not a corner, and
# there's no explicit Si substrate below the BOX (modelled as more oxide instead -- see Template 1
# for why).

# %%
core_y_bottom = BOTTOM_MARGIN_NM + BOX_NM
core_y_centre = core_y_bottom + HEIGHT_NM / 2
d = (WIDTH_NM + GAP_NM) / 2   # centre-to-centre offset of each core from x=0

half_span = d + WIDTH_NM / 2
window_width = 2 * (half_span + CLAD_NM + SIDE_MARGIN_NM)
window_height = BOTTOM_MARGIN_NM + BOX_NM + HEIGHT_NM + CLAD_NM + TOP_MARGIN_NM
clad_width = 2 * d + WIDTH_NM + 2 * CLAD_NM

em = emc.EMode(simulation_name='coupler', clear='mine')
em.settings(wavelength=WAVELENGTH_NM, x_resolution=10, y_resolution=10,
            window_width=window_width, window_height=window_height,
            num_modes=2, background_material='Air')

em.shape(name='box', material='SiO2', width=window_width, height=BOTTOM_MARGIN_NM + BOX_NM,
          position=[0, (BOTTOM_MARGIN_NM + BOX_NM) / 2])
em.shape(name='clad', material='SiO2', width=clad_width, height=HEIGHT_NM + CLAD_NM,
          position=[0, core_y_bottom + (HEIGHT_NM + CLAD_NM) / 2])
em.shape(name='core1', material='SiN', width=WIDTH_NM, height=HEIGHT_NM, position=[-d, core_y_centre])
em.shape(name='core2', material='SiN', width=WIDTH_NM, height=HEIGHT_NM, position=[d, core_y_centre])

em.plot(component='n', file_name='geometry', file_type='png')

em.FDM()
report = em.report()

em.plot(component='Ex', mode=0, file_name='mode_symmetric', file_type='png')
em.plot(component='Ex', mode=1, file_name='mode_antisymmetric', file_type='png')
em.close()

rows = sorted(report['_default'].values(), key=lambda row: row[1], reverse=True)
n_sym, n_anti = rows[0][1], rows[1][1]
kappa1_per_nm = (np.pi / WAVELENGTH_NM) * (n_sym - n_anti)
print(f"gap = {GAP_NM} nm: n_sym = {n_sym:.6f}, n_anti = {n_anti:.6f}, kappa1 = {kappa1_per_nm:.4e} 1/nm")

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
