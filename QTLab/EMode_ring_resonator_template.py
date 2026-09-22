
# Ring resonator coupling template

# Edit the parameters below for your assigned device before you start.

import emodeconnection as emc

## Set simulation parameters -- your device, edit these
wavelength = 1550    # [nm] wavelength
dx, dy = 10, 10       # [nm] resolution
w_core = 1180         # [nm] waveguide core width
h_core = 350          # [nm] waveguide core height (fixed for this platform)
num_modes = 2         # [-] number of supermodes (symmetric + antisymmetric)
symmetry = 'TE'        # [-] mode symmetry: 'TE' or 'TM'

gap = 1040            # [nm] edge-to-edge gap between the two waveguide cores
d = (w_core + gap) / 2   # centre-to-centre offset of each core from x=0

w_clad = 1500 + d     # [nm] side cladding thickness (SiO2), each side
h_clad = 1500         # [nm] bottom cladding thickness (SiO2)
h_clad_top = 100      # [nm] top cladding thickness (SiO2)
h_air = 1500          # [nm] air above the top cladding, up to the window edge

r_ring = 75_000       # [nm] racetrack bend radius
lc_racetrack = 20_000 # [nm] racetrack straight (coupling) section length

# %%
window_width = w_core + 2 * w_clad
clad_height = h_clad + h_core + h_clad_top
window_height = clad_height + h_air
etch_depth = h_core

em = emc.EMode(simulation_name='modes', clear='mine')
em.settings(wavelength=wavelength, x_resolution=dx, y_resolution=dy,
            window_width=window_width, window_height=window_height,
            num_modes=num_modes, background_material='Air', boundary_condition=symmetry)

em.shape(name='clad', material='SiO2', width=window_width, height=clad_height)
em.shape(name='dual core', material='SiN', width=window_width, height=h_core,
         mask=[w_core, w_core], mask_offset=[-d, d], etch_depth=etch_depth, fill_material='SiO2')
em.shape(name='clad_top', material='SiO2', width=window_width, height=h_clad_top)

em.FDM()
report = em.report()

em.plot()

em.close()
