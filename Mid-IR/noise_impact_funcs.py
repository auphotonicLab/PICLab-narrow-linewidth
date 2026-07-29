import numpy as np
from scipy.special import erfc


def detector_noise(NEP,bw):
    """Calculate the noise power for a given noise equivalent power and bandwidth.
    NEP in W/Hz^0.5, bw in Hz.
    Returns noise power in W.
    """

    noise_det = NEP * np.sqrt(bw)

    return noise_det

def signal_to_noise_ratio(power_in,attenuation,noise_detector):
    """Calculate the signal to noise ratio for a given power.
    Power_in in W, attenuation in linear scale, noise_detector in W.
    Assuming a simple binary modulation scheme.
    """

    SNR = power_in * attenuation / noise_detector

    return SNR


def bit_error_rate_OOK(signal_to_noise_ratio):
    """Calculate the bit error rate for a SNR.
    Assuming a simple binary modulation scheme. Power used in SNR is peak optical power, with off key at 0 power and on key at peak optical power.
    """

    BER = 0.5 * erfc(np.sqrt(signal_to_noise_ratio/8) )


    return BER




def bit_error_rate_PAM4(signal_to_noise_ratio):
    """Calculate the bit error rate for a SNR.
    Assuming a simple binary modulation scheme.
    Power levels for bits {0,1,2,3}: {0,P_peak/3,2P_peak/3,P_peak}
    Since we have optical power P_peak/3 as the distance between each level, the SNR gets a factor 1/3 in the square root.
    """

    BER = 3/8 * erfc(np.sqrt(signal_to_noise_ratio/24) )


    return BER
