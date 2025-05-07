import os
from typing import List, Tuple, Union, Optional
import numpy as np
from scipy.optimize import curve_fit

# --- Constants ---
MIN_FEEDBACK_POWER = 0.000003  # 0.003 nW (minimum for feedback PM)
DEFAULT_IMPEDANCE = 50  # Ohms
DEFAULT_CONVERSION = 371.7 * 1e-3 / 208  # Default conversion factor for optical to electrical

# --- Calibration and conversion ---
def lin_func(x: np.ndarray, a: float) -> np.ndarray:
    """Linear function for curve fitting."""
    return x * a

# Calibration data from: ".\\Data\\RIN_MHz\\RIN measurements using HP detector.txt"
power_uW = np.array([581, 580, 578])
voltage_mV = np.array([161.89, 161.61, 161.13])
popt, pcov = curve_fit(lin_func, power_uW, voltage_mV)
conversion_factor = popt[0]
conversion_offset = 0

# --- File and data utilities ---
def get_paths_homodyne(directory: str) -> List[str]:
    """Get paths to all homodyne files in directory."""
    filenames = os.listdir(directory)
    return [os.path.join(directory, e) for e in filenames if "homodyne" in e]

def get_paths_intensity(directory: str) -> List[str]:
    """Get paths to all ESA files in directory."""
    filenames = os.listdir(directory)
    return [os.path.join(directory, e) for e in filenames if e.endswith("esa.txt")]

def get_OSA_paths(directory: str) -> List[str]:
    """Get paths to all OSA files in directory, excluding last 10."""
    filenames = os.listdir(directory)
    return [os.path.join(directory, e) for e in filenames if "OSA" in e][:-10]

def get_data(path: str, length: int = 1) -> Tuple[np.ndarray, np.ndarray]:
    """Load data from file, skipping header rows."""
    return np.loadtxt(path, encoding="unicode_escape", skiprows=1, delimiter=' ')

def get_header(path: str, length: int = 1) -> List[List[str]]:
    """Read header lines from file."""
    lines = []
    with open(path, encoding="ISO-8859-1") as file:
        for _ in range(length):
            line = file.readline()
            lines.append(line[1:].split(','))
    return lines

def parse_rbw(rbw_str: str) -> float:
    """Parse RBW string to float value in Hz."""
    if 'MHz' in rbw_str:
        return float(rbw_str[4:-3]) * 1e6
    elif 'kHz' in rbw_str:
        return float(rbw_str[4:-3]) * 1e3
    return float(rbw_str[4:-2])

def esa_header_data(header: List[List[str]]) -> Tuple[float, float, str, str, float]:
    """Extract data from ESA header."""
    header_line = header[0]
    output_power = float(header_line[0].split(" ")[1][:-2])
    fb_level = float(header_line[1].split(" ")[3][:-2])
    
    # Handle different header formats
    if len(header_line) == 6:
        gain = header_line[2][1:]
        pol = header_line[3].split(" ")[2]
        rbw = parse_rbw(header_line[4].split(" ")[1])
    else:  # len == 5
        pol = header_line[2].split(" ")[2]
        rbw = parse_rbw(header_line[3].split(" ")[1])
        gain = 'None'
    
    # Normalize polarization values
    pol = pol.lower() if pol in ['Misaligned', 'Aligned', 'None'] else pol
    
    return output_power, fb_level, gain, pol, rbw

# --- Math and conversion utilities ---
def ratio_to_db(feedback_power: float, output_power: float) -> float:
    """Convert power ratio to dB."""
    feedback_power = max(feedback_power, MIN_FEEDBACK_POWER)
    output_power = max(output_power, MIN_FEEDBACK_POWER)
    return 10 * np.log10(feedback_power / output_power)

def linear_to_dB(datapoint_linear: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Convert linear power to dB."""
    return 10 * np.log10(datapoint_linear)

def dB_to_linear(power: Union[float, np.ndarray]) -> Union[float, np.ndarray]:
    """Convert dB to linear power."""
    return 10 ** (power / 10)

def OSA_fb_dB(feedback_power: float, peak_power: float) -> float:
    """Calculate feedback power in dB for OSA measurements."""
    peak_power_uW = 10 ** (peak_power / 10) * 1000 * 40  # Convert to µW
    feedback_power = max(feedback_power, MIN_FEEDBACK_POWER)
    return ratio_to_db(feedback_power, peak_power_uW)

def convert_optical_to_electrical(
    power: float,
    ret_V: bool = False,
    conversion: Optional[float] = None
) -> float:
    """
    Convert optical power to electrical power or voltage.
    
    Args:
        power: Optical power in µW
        ret_V: If True, return voltage instead of power
        conversion: Conversion factor (V/µW). If None, uses default.
    
    Returns:
        Electrical power in dBm or voltage in V
    """
    conversion = conversion or DEFAULT_CONVERSION
    volts = conversion * power  # V
    
    if ret_V:
        return volts
    
    elec_power = volts ** 2 / DEFAULT_IMPEDANCE  # W/Hz
    elec_power_mW = 1e3 * elec_power  # mW/Hz
    return 10 * np.log10(elec_power_mW)  # dBm

def convert_optical_to_electrical2(power, ret_V=False, conversion=1.9 / 1950):
    volts = conversion * power  # V
    if ret_V:
        return volts
    else:
        elec_power = volts ** 2 / 50  # V^2/Ohm = W/Hz
        elec_power_mW = 1e3 * elec_power  # mW/Hz
        power_sq_dBm = 10 * np.log10(elec_power_mW / 1)  # dBm
        return power_sq_dBm

def scientific(x: float, pos: int) -> str:
    """Format number in scientific notation for plotting."""
    if x == 1e5:
        return r'$10^5$'
    elif x == 1e6:
        return r'$10^6$'
    elif x == 1e7:
        return r'$10^7$'
    else:
        return r'$%d \\times 10^{%d}$' % (
            int(x / (10 ** int(np.log10(x)))),
            int(np.log10(x))
        ) 