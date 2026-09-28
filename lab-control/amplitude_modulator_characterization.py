#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Amplitude modulator (MZI) DC characterization.

Sweeps the DC bias voltage from the SPD3303X supply across the modulator
and records the transmitted optical power to find:
  - V_max : bias voltage giving maximum optical transmission  ('1' level)
  - V_min : bias voltage giving minimum transmission / null  ('0' level)
  - V_quad: quadrature point = (V_max + V_min) / 2  (optimal DC bias)
  - V_pp  : required peak-to-peak AC swing = V_max - V_min

During eye-diagram measurements the DC supply is set to V_quad and the
SDG6022X (AFG_Siglent) outputs a pure-AC PRBS signal with amplitude V_pp.
The two voltages add linearly across the AM, so:
  total_max = V_quad + V_pp/2  ≈ V_max
  total_min = V_quad - V_pp/2  ≈ V_min

Safety: the script enforces that no voltage step exceeds max_dc_voltage (7 V
by default), which is also enforced inside DC_Siglent. The AM absolute
maximum rating is ±20 V; the 7 V cap keeps well within that.

Instruments
-----------
- Siglent SPD3303X DC supply  (192.168.1.31) : sweeps bias voltage
- Thorlabs PM100USB power meter               : reads transmitted power
"""

import numpy as np
import time
import matplotlib.pyplot as plt
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import Lab_control as pic


def find_am_operating_points(
        dc_ip='192.168.1.31',
        dc_channel=1,
        pm_serial='P0024530',
        v_start=0.0,
        v_stop=7.0,
        n_points=141,
        settling_time=0.15,
        max_dc_voltage=7.0,
        save=False,
        save_folder=None):
    """Sweep DC bias on the amplitude modulator and return operating voltages.

    Parameters
    ----------
    dc_ip : str
        IP address of Siglent SPD3303X DC supply.
    dc_channel : int
        Supply channel wired to the AM bias input.
    pm_serial : str
        Thorlabs PM100USB serial number.
    v_start : float
        Sweep start voltage [V] (≥ 0, SPD3303X is unipolar).
    v_stop : float
        Sweep stop voltage [V] (≤ max_dc_voltage).
    n_points : int
        Number of voltage steps.
    settling_time : float
        Wait time after each voltage step [s].
    max_dc_voltage : float
        Hard upper limit on output voltage [V].  Passed to DC_Siglent so
        both the sweep and any later setParameters calls are protected.
    save : bool
        Save data and figure to disk.
    save_folder : str or None
        Destination directory when save=True.

    Returns
    -------
    voltages : np.ndarray   Swept bias voltages [V]
    power    : np.ndarray   Optical power at each step [W]
    v_max    : float        Voltage at maximum transmission [V]
    v_min    : float        Voltage at minimum transmission [V]
    v_quad   : float        Quadrature (optimal DC bias) [V]
    v_pp     : float        Required AC peak-to-peak swing [V]
    """
    v_stop = min(v_stop, max_dc_voltage)

    dc = pic.DC_Siglent(IP_address=dc_ip, channel=dc_channel,
                        voltage=v_start, current=0.1,
                        max_voltage=max_dc_voltage)
    pm = pic.PM100USB(PM_name=pm_serial)

    voltages = np.linspace(v_start, v_stop, n_points)
    power = np.empty(n_points)

    dc.outputStatus(channel=dc_channel, status='ON')
    time.sleep(0.2)

    for i, v in enumerate(voltages):
        dc.setParameters(channel=dc_channel, voltage=v, current=0.1)
        time.sleep(settling_time)
        power[i] = pm.GetPower()

    # Return to zero after sweep
    dc.setParameters(channel=dc_channel, voltage=0.0, current=0.1)

    v_max  = voltages[np.argmax(power)]
    v_min  = voltages[np.argmin(power)]
    v_quad = (v_max + v_min) / 2.0
    v_pp   = np.abs(v_max - v_min)
    er_db  = 10 * np.log10(max(power) / min(power))

    print(f'\nAmplitude modulator characterization')
    print(f'  Max transmission : {v_max:.3f} V  ({max(power)*1e6:.2f} µW)')
    print(f'  Min transmission : {v_min:.3f} V  ({min(power)*1e6:.2f} µW)')
    print(f'  Extinction ratio : {er_db:.1f} dB')
    print(f'\n  --- Eye diagram settings ---')
    print(f'  DC supply (SPD3303X) bias : {v_quad:.3f} V   (quadrature)')
    print(f'  AFG (SDG6022X) PRBS Vpp  : {v_pp:.3f} V   (pure AC, zero offset)')
    print(f'  Total max voltage         : {v_quad + v_pp/2:.3f} V')
    print(f'  Total min voltage         : {v_quad - v_pp/2:.3f} V')

    if v_quad + v_pp / 2 > max_dc_voltage:
        print(f'\n  WARNING: total max voltage exceeds {max_dc_voltage} V limit!')

    fig, ax = plt.subplots()
    ax.plot(voltages, power * 1e6, 'b')
    ax.axvline(v_max,  color='g', linestyle='--', label=f'V_max  = {v_max:.2f} V')
    ax.axvline(v_min,  color='r', linestyle='--', label=f'V_min  = {v_min:.2f} V')
    ax.axvline(v_quad, color='k', linestyle=':',  label=f'V_quad = {v_quad:.2f} V')
    ax.set_xlabel('DC Bias Voltage [V]')
    ax.set_ylabel('Optical Power [µW]')
    ax.set_title('Amplitude Modulator Transfer Function')
    ax.legend()
    ax.grid(True)
    plt.tight_layout()

    if save:
        if save_folder is None:
            raise ValueError('save_folder must be specified when save=True')
        timestamp = pic.datetimestring()
        np.savetxt(
            os.path.join(save_folder, timestamp + '_AM_characterization.txt'),
            np.column_stack([voltages, power]),
            header=(f'V_max={v_max:.3f} V, V_min={v_min:.3f} V, '
                    f'V_quad={v_quad:.3f} V, V_pp={v_pp:.3f} V, '
                    f'ER={er_db:.1f} dB\n'
                    'Voltage [V], Power [W]'))
        plt.savefig(os.path.join(save_folder, timestamp + '_AM_characterization.png'),
                    bbox_inches='tight')

    plt.show()

    pm.closeConnection()
    dc.closeConnection()

    return voltages, power, v_max, v_min, v_quad, v_pp


# =============================================================================
# Run
# =============================================================================

if __name__ == '__main__':
    # --- Configure before running ---
    DC_IP         = '192.168.1.31'   # Siglent SPD3303X
    DC_CHANNEL    = 1
    PM_SERIAL     = 'P0024530'       # Thorlabs PM100USB serial number
    MAX_DC_VOLT   = 7.0              # Hard voltage cap [V]
    SAVE          = False
    SAVE_FOLDER   = r'C:\Users\Group Login\Documents\Measurements\AM_characterization'

    voltages, power, v_max, v_min, v_quad, v_pp = find_am_operating_points(
        dc_ip=DC_IP,
        dc_channel=DC_CHANNEL,
        pm_serial=PM_SERIAL,
        v_start=0.0,
        v_stop=MAX_DC_VOLT,
        n_points=141,
        settling_time=0.15,
        max_dc_voltage=MAX_DC_VOLT,
        save=SAVE,
        save_folder=SAVE_FOLDER if SAVE else None,
    )
