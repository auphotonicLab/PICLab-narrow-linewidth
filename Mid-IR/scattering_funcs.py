
#Functions used for calculating extinction, scattering, and attenuation coefficients due to Mie scattering. 
#Includes three different Mie models (Kim, Kruse, and full Mie scattering)
#Also includes Beer's law for calculating received power at given distance.

import numpy as np
import miepython as Mie
from scipy.special import erfc
import pandas as pd


def droplet_size_dist_anal_rec(N, sigma, mean_radius, radius):
    """Analytical size distribution for a given number of droplets and radius.
    N total number of droplets pr unit volume
    mean_radius and radius in microns.
    """
    
 

    n = N / (np.sqrt(2 * np.pi) * sigma * radius) * np.exp(- (np.log(radius / mean_radius))**2 / (2 * sigma**2))
    

    return n
 

def DSD_rad_approx(radius):
    """Radiation fog droplet size distribution, reconstructed from looking at plot in Grillot paper
    Input: radius in microns
    Output: droplet size distribution in cm⁻³ µm⁻¹
    """
    
    r_0 = 1 #µm
    N = 2e3 #droplets pr cm³
    sigma  = 0.3

    droplet_size_dist = droplet_size_dist_anal_rec(N, sigma, r_0, radius)

    r_0_2 = 2.8 #µm
    N_2 = 200 #droplets pr cm³
    sigma_2  = 0.4

    droplet_size_dist2 = droplet_size_dist_anal_rec(N_2, sigma_2, r_0_2, radius)


    droplet_size_dist3 = 5e1*np.exp(-0.015*radius**2.5) 

    DSD_rad = droplet_size_dist+droplet_size_dist2+droplet_size_dist3    

    return DSD_rad      


def DSD_adv_approx(radius):
    """Advection fog droplet size distribution, reconstructed from looking at plot in Grillot paper.
    Input: radius in microns
    Output: droplet size distribution in cm⁻³ µm⁻¹
    """

    r_0 = 11 #µm
    N = 13 #droplets pr cm³
    sigma  = 0.49

    droplet_size_dist = droplet_size_dist_anal_rec(N, sigma, r_0, radius)

    droplet_size_dist2 = 5e-1*np.exp(-0.3*(radius-5)**(2))

    DSD_adv = droplet_size_dist + droplet_size_dist2  

    return DSD_adv   


def mie_extinction_coefficient(DSD,Q_k,radius):
    """Calculate the extinction coefficient for a given droplet size distribution and Mie efficiency.
    DSD is the droplet size distribution in cm⁻³ µm⁻¹
    Q_k is the Mie efficiency for k = ext, sca, abs, back
    radius is the radius of the droplets in microns.

    Using the Grillot paper, where sigma_ext(lambda) = 1e-3 * ∫ Q_ext(lambda,r,m) * π * r² * N(r) dr, where N(r) is the droplet size distribution in cm⁻³ µm⁻¹ and r is the radius in microns.
    we get the units km⁻¹ for the extinction coefficient, since Q is unitless we have: µm² * cm⁻³ µm⁻¹ * µm = (1e-4 cm)^2 * cm⁻³ = 1e-8 cm⁻¹ = 1e-6 m⁻¹ = 1e-3 km⁻¹, hence the factor 1e-3 in the Grillot paper.
    So if we just insert the units as above we get per km out.

    Return extinction coefficient in km⁻¹.
    """

    
    # Calculate the geometric cross section in µm²

    geometric_cross_section_µm2 = 1*np.pi * radius**2

    # Calculate the extinction cross section in µm²
    extinction_cross_section_µm2 = Q_k * geometric_cross_section_µm2
    
    # Calculate the extinction coefficient in km⁻¹
    extinction_coefficient_km1 = np.trapezoid(extinction_cross_section_µm2 * DSD, radius)*1e-3

    
    return extinction_coefficient_km1


def Beers_law(power_input,attenuation,distance): 
    """Power at distance due to attenuation
     power_input in W, attenuation in km⁻¹, distance in km
        Return power_out in W and power_dB in dB.
    """

    power_out = power_input*np.exp(-attenuation*distance)

    power_dB = 10 * np.log10(power_out/power_input)
    return power_out, power_dB

def Kim_visibility_model(visibility, wavelength):
    """Calculate the attenuation coefficient using the Kim visibility model.
    visibility in km, wavelength in µm.
    Return attenuation coefficient in 1/km.
    """

    wavelength_0 = 0.55 #µm



    if visibility > 50:
        q = 1.6
    elif visibility > 6:
        q = 1.3
    elif visibility >= 1:
        q = 0.16 * visibility + 0.34
    elif visibility >= 0.5:
        q = visibility - 0.5
    else:   
        q = 0

    front_factor = -np.log(0.02) #Convert from 2% to natural log
    # to_dB = 10 * np.log10(np.exp(1)) #Convert from natural log to dB
    

    
    attenuation_km1 = (front_factor) / visibility * (wavelength_0/wavelength)**(q)


    return attenuation_km1



def Kruse_visibility_model(visibility, wavelength):
    """Calculate the attenuation coefficient using the Kruse visibility model.
    visibility in km, wavelength in µm.
    Return attenuation coefficient in 1/km.
    """

    wavelength_0 = 0.550 #in µm. reference wavelength 0.550µm, optimal eye performance

    if visibility < 6: #km
        q=0.585 * visibility**(1/3)
    elif (visibility >= 6) and (visibility < 50):
        q=1.3

    else:
        q=1.6

    att_Mie_km1 = -np.log(0.02)/visibility * (wavelength/wavelength_0)**(-q)

    return att_Mie_km1




def log_normal_modes(N_k,sigma_k,radius_k,radius):
    """Function used to reconstruct fog droplet size distribution. 
    N_k: list of total particles per cm^(-3) for each k, \n
    sigma_k: sets the width of each mode k, \n
    r_k: is the modal radius in µm, i.e. center of the mode or peak,\n
    k: mode number,\n
    radius: in µm, list of all radii that the particle has in the measurement, which we try to replicate

    Return: n, particle distribution cm^(-3) µm^(-1) 
    """


    M = len(N_k) #Total number of modes

    
    
    sum = np.zeros_like(radius,dtype=float)

    for k in range(M):

        ln_sigma= np.log(sigma_k[k])        

        ln_r_over_r_k = np.log( radius/radius_k[k])

        mode = N_k[k]/ln_sigma * np.exp( - ln_r_over_r_k**2 / (2*ln_sigma**2) )

        sum += mode

    n_cm3_µm = sum / (np.sqrt(2*np.pi) * radius) #particles per µm and cm^3

    
    return n_cm3_µm


def mod_gamma_dist(a,b, alpha,radius):
    """Function used to reconstruct fog droplet size distribution. 
    a, b, alpha : parameters for the fog distribution
    radius: in µm, list of all radii that the particle has in the measurement, which we try to replicate

    Return: n, particle distribution per unit volume and radius increment (µm)
    """

    n_vol_dr = a * radius**alpha * np.exp(-b*radius)

    return n_vol_dr



def load_fog_data(file_path: str) -> list[dict]:
    df = pd.read_excel(file_path)

    # Expected columns (matching the CSV header from the table):
    # #, Date, Time (UTC), Mode, Nk (part/cc), sigma_k, Dk (um),
    # LWC (g/m3), alpha_ext_11um (1/m), alpha_abs_11um (1/m),
    # alpha_ext_4um (1/m), alpha_abs_4um (1/m)

    fog_cases = []

    for case_num, group in df.groupby("#", sort=False):
        # Per-case scalars sit on the first mode row; grab from there
        first = group.iloc[0]

        case = {
            "n":        int(case_num),
            "date":     first["Date"],
            "time":     first["Time (UTC)"],
            # Mode parameters as lists
            "N_k":      group["Nk (part/cc)"].tolist(),
            "sigma_k":  group["sigma_k"].tolist(),
            "r_k":      (group["Dk (um)"] / 2).tolist(),   # convert diameter → radius
            # Per-case optical / LWC values
            "LWC":      first["LWC (g/m3)"],
            "alpha_ext_11um": first["alpha_ext_11um (1/m)"],
            "alpha_abs_11um": first["alpha_abs_11um (1/m)"],
            "alpha_ext_4um":  first["alpha_ext_4um (1/m)"],
            "alpha_abs_4um":  first["alpha_abs_4um (1/m)"],
        }
        fog_cases.append(case)

    return fog_cases




def load_adv_fog_data(file_path: str) -> list[dict]:
    df = pd.read_excel(file_path)

    # Expected columns (matching the CSV header from the table):
    # #, Date, Time (UTC), Mode, Nk (part/cc), sigma_k, Dk (um),
    # LWC (g/m3), alpha_ext_11um (1/m), alpha_abs_11um (1/m),
    # alpha_ext_4um (1/m), alpha_abs_4um (1/m)

    fog_cases = []

    for case_num, group in df.groupby("#", sort=False):
        # Per-case scalars sit on the first mode row; grab from there
        first = group.iloc[0]

        case = {
            "n":        case_num,
            "Type":     first["Type"],
            "alpha":     first["alpha"],
            "a":     first["a"],
            "B":     first["B"],
            "N":     first["N (nb/cm^3)"],
            "W":     first["W (g/m^3)"],
            "r_m":  first["r_m (µm)"],    
            "V":    first["V (m)"]}
        fog_cases.append(case)

    return fog_cases

