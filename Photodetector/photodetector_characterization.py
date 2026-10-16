#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Photodetector DC characterization with a hand-turned VOA
========================================================
developer: Jeppe Surrow

Laser -> VOA -> splitter -+-> monitor arm -> PM100USB (photodiode sensor)
                          +-> DUT arm     -> photodetector -> Keithley 2450 (high-Z voltmeter)

Turn the VOA SLOWLY and smoothly (e.g. full range in ~1 min, down and back up).
A live plot shows the curve while you turn (close it or press Ctrl+C to stop).
The power meter is read before and after every voltage reading and the two are
averaged, so the power and voltage belong to the same moment. Stop with Ctrl+C.

SPLIT_RATIO = P(DUT arm) / P(monitor arm). Set MEASURE_SPLIT_RATIO = True to
measure it with the power meter (it prints the value; put it in SPLIT_RATIO).

Output (in SAVE_FOLDER): <timestamp>_<DUT>.csv  and  <timestamp>_<DUT>.png
"""

import os
import sys
import time
from ctypes import c_double, c_int16, byref

import numpy as np
import matplotlib.pyplot as plt

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lab-control'))
import Lab_control as pic

# =============================================================================
# Settings
# =============================================================================
DUT_NAME        = 'PDA05CF2'
WAVELENGTH_NM   = 1550
LOAD            = 'HiZ'          # 'HiZ' or '50ohm' (50 ohm feed-through at the Keithley input)
TIA_GAIN        = 10e3           # V/A for this load (PDA05CF2: 10 kV/A Hi-Z, 5 kV/A 50 ohm), None to skip

SPLIT_RATIO         = 1.0        # P(DUT arm) / P(monitor arm)
MEASURE_SPLIT_RATIO = False

PM_SERIAL       = 'P0024530'
KEITHLEY_IP     = '192.168.1.151'
NPLC            = 1              # Keithley integration, 1 PLC = 20 ms
PM_AVG_TIME     = 0.02           # s, same window as the Keithley

N_DARK          = 30             # readings for the dark offset
MAX_DURATION    = 300            # s, the sweep also stops with Ctrl+C
LIVE_PLOT       = True           # run in the VS Code terminal (python photodetector_characterization.py), not the Interactive Window
LIVE_PLOT_INTERVAL = 1.0         # s between redraws (each costs ~0.05-0.1 s of measuring time)
FIT_V_RANGE     = (0.01, 0.5)    # linear fit uses V_net between these fractions of the max V_net

SAVE_FOLDER = r'C:\Users\shd-photonics-inp\Documents\Jeppe_Surrow\Photodetector'


# =============================================================================
# Instruments
# =============================================================================
def connect():
    pm = pic.PM100USB(lambda0=WAVELENGTH_NM, PM_name=PM_SERIAL)
    pm.PDinstr.setPowerUnit(c_int16(0))              # W
    pm.PDinstr.setAvgTime(c_double(PM_AVG_TIME))     # set once (GetPower() re-sets it every call)

    k = pic.DC_KEITHLEY_2450(GPIB_interface=-1, IP_address=KEITHLEY_IP)
    k.SetHighZVoltmeter(vlim=20, nplc=NPLC)          # source 0 A, measure V, autorange
    k.SwitchOn()
    return pm, k


def read_power(pm):
    p = c_double()
    pm.PDinstr.measPower(byref(p))
    return p.value


def read_voltage(k):
    return float(k.instr.query('READ?'))


def average(fn, n):
    x = np.array([fn() for _ in range(n)])
    return x.mean(), x.std()


# =============================================================================
# Measurement
# =============================================================================
def measure_split_ratio(pm, n=30):
    input('Power meter on the MONITOR arm, VOA fixed. Enter...')
    p_mon, _ = average(lambda: read_power(pm), n)
    input('Power meter on the DUT arm fiber end. Enter...')
    p_dut, _ = average(lambda: read_power(pm), n)
    ratio = p_dut / p_mon
    print('SPLIT_RATIO = %.4f  (%.3f dB)  <- put this in the settings' % (ratio, 10 * np.log10(ratio)))
    input('Power meter back on the MONITOR arm, detector on the DUT arm. Enter...')
    return ratio


def measure_dark(pm, k):
    input('\nLaser OFF / output blocked. Enter to measure the dark offset...')
    v0, v_noise = average(lambda: read_voltage(k), N_DARK)
    p0, _ = average(lambda: read_power(pm), N_DARK)
    print('Dark: V = %.3f mV (noise %.1f uV rms),  P_pm = %.3g W' % (v0 * 1e3, v_noise * 1e6, p0))
    input('Laser ON. Enter...')
    return v0, v_noise, p0


class LivePlot:
    """V vs P on the detector, linear and log-log, redrawn every LIVE_PLOT_INTERVAL seconds."""

    def __init__(self, dark, ratio):
        self.v0, self.p0, self.ratio = dark[0], dark[2], ratio
        plt.ion()
        self.fig, self.ax = plt.subplots(1, 2, figsize=(11, 4.5))
        self.lin, = self.ax[0].plot([], [], '.', ms=3)
        self.ax[1].set_xlim(1e-7, 1e-2); self.ax[1].set_ylim(1e-4, 10)
        self.ax[1].set_xscale('log'); self.ax[1].set_yscale('log')
        self.log, = self.ax[1].plot([], [], '.', ms=3)
        self.ax[0].set_xlabel('P on detector [mW]'); self.ax[0].set_ylabel('V - V_dark [V]')
        self.ax[1].set_xlabel('P on detector [W]'); self.ax[1].set_ylabel('V - V_dark [V]')
        for a in self.ax:
            a.grid(True, which='both', alpha=0.3)
        self.closed = False
        self.fig.canvas.mpl_connect('close_event', lambda e: setattr(self, 'closed', True))
        self.last = 0.0
        plt.show(block=False)
        plt.pause(0.1)

    def update(self, P_pm, V, force=False):
        """Returns True if it redrew (the caller then re-reads the power meter)."""
        if self.closed or (not force and time.time() - self.last < LIVE_PLOT_INTERVAL):
            return False
        self.last = time.time()
        P = self.ratio * (np.asarray(P_pm) - self.p0)
        Vn = np.asarray(V) - self.v0
        self.lin.set_data(P * 1e3, Vn)
        pos = (P > 0) & (Vn > 0)
        self.log.set_data(P[pos], Vn[pos])
        self.ax[0].relim(); self.ax[0].autoscale_view()
        if pos.sum() > 1:
            self.ax[1].set_xlim(P[pos].min() / 1.5, P[pos].max() * 1.5)
            self.ax[1].set_ylim(Vn[pos].min() / 1.5, Vn[pos].max() * 1.5)
        self.fig.suptitle('%d points   now: P = %.3g mW, V = %.3f V   (close window or Ctrl+C to stop)'
                          % (len(V), P[-1] * 1e3, Vn[-1]))
        self.fig.canvas.draw_idle()
        plt.pause(0.001)
        return True


def sweep(pm, k, dark, ratio):
    live = LivePlot(dark, ratio) if LIVE_PLOT else None
    input('\nStart turning the VOA slowly, then press Enter. Ctrl+C (or close the live plot) to stop.')
    t, P, V = [], [], []
    t0 = time.time()
    p_before = read_power(pm)
    try:
        while time.time() - t0 < MAX_DURATION:
            v = read_voltage(k)
            p_after = read_power(pm)
            t.append(time.time() - t0)
            V.append(v)
            P.append(0.5 * (p_before + p_after))     # power at the time of the voltage reading
            p_before = p_after
            if live is not None:
                if live.closed:
                    break
                if live.update(P, V):
                    p_before = read_power(pm)        # the redraw took time: start a fresh pair
            elif len(V) % 20 == 0:
                print('  %5.1f s   P_pm = %.3e W   V = %.4f V' % (t[-1], P[-1], v))
    except KeyboardInterrupt:
        print('Stopped.')
        try:
            k.instr.clear()                          # flush a reply interrupted by Ctrl+C
        except Exception:
            pass
    if live is not None and not live.closed:
        plt.close(live.fig)
    plt.ioff()
    print('%d points in %.0f s' % (len(V), t[-1]))
    return np.array(t), np.array(P), np.array(V)


# =============================================================================
# Analysis
# =============================================================================
def analyze(t, P_pm, V, dark, ratio):
    v0, v_noise, p0 = dark
    P = ratio * (P_pm - p0)                           # power on the detector
    Vn = V - v0                                       # output above dark

    lo, hi = FIT_V_RANGE[0] * Vn.max(), FIT_V_RANGE[1] * Vn.max()
    m = (Vn > lo) & (Vn < hi)
    slope, intercept = np.polyfit(P[m], Vn[m], 1)
    dev = 100 * (Vn / (slope * P + intercept) - 1)    # % deviation from linear

    # 1 % compression: first power above which the running median deviation stays below -1 %
    order = np.argsort(P)
    run_med = np.array([np.median(dev[order][max(0, i - 7):i + 8]) for i in range(len(order))])
    below = (run_med < -1) & (Vn[order] > hi * 0.5)
    P_comp = P[order][np.argmax(below)] if below.any() else None

    r = {'gain_V_per_W': slope, 'intercept_V': intercept, 'dark_V': v0, 'dark_noise_V': v_noise,
         'P_comp_W': P_comp, 'V_max': Vn.max(), 'P_max_W': P.max()}
    if TIA_GAIN:
        r['responsivity_A_per_W'] = slope / TIA_GAIN

    print('\n--- %s @ %g nm, %s ---' % (DUT_NAME, WAVELENGTH_NM, LOAD))
    print('Gain dV/dP       : %.4g V/W  (%.4g V/mW)' % (slope, slope / 1e3))
    if TIA_GAIN:
        print('Responsivity     : %.3f A/W  (with TIA gain %g V/A)' % (r['responsivity_A_per_W'], TIA_GAIN))
    print('Fit intercept    : %.3f mV' % (intercept * 1e3))
    print('Dark offset      : %.3f mV, noise %.1f uV rms -> noise-equivalent power %.2g W'
          % (v0 * 1e3, v_noise * 1e6, v_noise / slope))
    if P_comp is not None:
        print('1 %% compression  : %.3g W (%.1f dBm)' % (P_comp, 10 * np.log10(P_comp / 1e-3)))
    else:
        print('1 %% compression  : not reached (max %.3g W, %.3f V)' % (P.max(), Vn.max()))
    return P, Vn, dev, m, r


def plot(t, P, Vn, dev, m, r, path):
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.suptitle('%s @ %g nm, %s:  %.4g V/mW%s' % (DUT_NAME, WAVELENGTH_NM, LOAD, r['gain_V_per_W'] / 1e3,
                 '  (%.3f A/W)' % r['responsivity_A_per_W'] if TIA_GAIN else ''))
    pp = np.linspace(0, P.max(), 2)
    # colour = time, so the down and up sweeps can be compared by eye
    ax[0].scatter(P * 1e3, Vn, c=t, s=4, cmap='viridis')
    ax[0].plot(pp * 1e3, r['gain_V_per_W'] * pp + r['intercept_V'], 'k-', lw=1, label='linear fit')
    ax[0].set_ylim(-0.05 * Vn.max(), 1.15 * Vn.max())
    ax[0].set_xlabel('P on detector [mW]'); ax[0].set_ylabel('V - V_dark [V]'); ax[0].legend()

    pos = (P > 0) & (Vn > 0)
    ax[1].scatter(P[pos], Vn[pos], c=t[pos], s=4, cmap='viridis')
    ax[1].plot(P[pos], r['gain_V_per_W'] * P[pos], 'k-', lw=1)
    ax[1].axhline(r['dark_noise_V'], color='r', ls=':', label='dark noise')
    ax[1].set_xscale('log'); ax[1].set_yscale('log')
    ax[1].set_xlabel('P on detector [W]'); ax[1].set_ylabel('V - V_dark [V]'); ax[1].legend()

    sc = ax[2].scatter(P[pos], dev[pos], c=t[pos], s=4, cmap='viridis')
    ax[2].axhspan(-1, 1, color='g', alpha=0.1)
    ax[2].axvspan(P[m].min(), P[m].max(), color='0.5', alpha=0.1, label='fit range')
    if r['P_comp_W']:
        ax[2].axvline(r['P_comp_W'], color='tab:orange', ls='--', label='1 % compression')
    ax[2].set_xscale('log'); ax[2].set_ylim(-5, 5)
    ax[2].set_xlabel('P on detector [W]'); ax[2].set_ylabel('deviation from linear [%]'); ax[2].legend()
    fig.colorbar(sc, ax=ax[2], label='time [s]')
    for a in ax:
        a.grid(True, which='both', alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


# =============================================================================
# Run
# =============================================================================
if __name__ == '__main__':
    pm, k = connect()
    try:
        ratio = measure_split_ratio(pm) if MEASURE_SPLIT_RATIO else SPLIT_RATIO
        dark = measure_dark(pm, k)
        t, P_pm, V = sweep(pm, k, dark, ratio)
    finally:
        k.SwitchOff(); k.CloseConnection(); pm.closeConnection()

    os.makedirs(SAVE_FOLDER, exist_ok=True)
    base = os.path.join(SAVE_FOLDER, '%s_%s_%gnm_%s' % (pic.datetimestring(), DUT_NAME, WAVELENGTH_NM, LOAD))
    np.savetxt(base + '.csv', np.column_stack([t, P_pm, V]), delimiter=',',
               header='split_ratio=%g, dark_V=%g, dark_noise_V=%g, dark_P_pm=%g\nt_s,P_pm_W,V_V' % (ratio, *dark))

    P, Vn, dev, m, r = analyze(t, P_pm, V, dark, ratio)
    plot(t, P, Vn, dev, m, r, base + '.png')
    print('Saved', base + '.csv/.png')
    plt.show()
