
# Dispersion template

# Edit the parameters below for your assigned device before you start.

import emodeconnection as emc

## Set simulation parameters -- your device, edit these
wavelength = 1550    # [nm] wavelength
dx, dy = 10, 10       # [nm] resolution
w_core = 1140         # [nm] waveguide core width
h_core = 350          # [nm] waveguide core height (fixed for this platform)
num_modes = 2         # [-] number of modes


w_clad = 1500         # [nm] side cladding thickness (SiO2), each side
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
            num_modes=num_modes, background_material='Air')

em.shape(name='clad', material='SiO2', width=window_width, height=clad_height)
em.shape(name='core', material='SiN', width=window_width, height=h_core,
         mask=w_core, etch_depth=etch_depth, fill_material='SiO2')
em.shape(name='clad_top', material='SiO2', width=window_width, height=h_clad_top)

em.FDM()
report = em.report()

em.plot()

## Core confinement factor (fraction of mode power in the core) for each mode
core_confinement = em.confinement(shape_list='core', mode_list='all')[0]['core']
for mode in range(num_modes):
    print(f"Mode {mode}: core confinement = {core_confinement[str(mode)]*100:.1f} %")

em.close()
