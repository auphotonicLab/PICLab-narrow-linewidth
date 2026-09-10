import emodeconnection as emc

print("EMode connection established.")

## Set simulation parameters
wavelength = 1550 # [nm] wavelength
dx, dy = 10, 10 # [nm] resolution
w_core = 1400 # [nm] waveguide core width
h_core = 600 # [nm] waveguide core height
w_clad = 1000 # [nm] side cladding thickness (SiO2), each side
h_clad = 800 # [nm] top/bottom cladding thickness (SiO2), each side
num_modes = 3 # [-] number of modes

## Connect and initialize EMode, clearing out any sessions
em = emc.EMode(clear='mine')

## Settings -- Set background to SiO2 so the core is automatically embedded on all sides
window_width = w_core + w_clad*2
window_height = h_core + h_clad*2
em.settings(
    wavelength = wavelength, x_resolution = dx, y_resolution = dy,
    window_width = window_width, window_height = window_height,
    num_modes = num_modes, background_material = 'SiO2') # Changed to SiO2

## Draw shapes -- Only need to draw the core since the background handles the cladding
em.shape(name = 'core', material = 'SiN', width = w_core, height = h_core, position = [0, window_height/2])

## Launch FDM solver
em.FDM()

## Display the effective indices, TE fractions, and core confinement
em.report()

## Core confinement factor (fraction of mode power in the core) for each mode
core_confinement = em.confinement(shape_list='core', mode_list='all')[0]['core']
for mode in range(num_modes):
    print(f"Mode {mode}: core confinement = {core_confinement[str(mode)]*100:.1f} %")

## Plot the field and refractive index profiles
em.plot()

## Close EMode
em.close()
