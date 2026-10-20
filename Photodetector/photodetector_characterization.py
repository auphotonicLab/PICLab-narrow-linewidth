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

Output (in SAVE_FOLDER): <timestamp>_<DUT>_<wavelength>_<load>.h5 / .png / .csv
    .h5   everything: raw data, dark readings, every setting, instrument read-backs, results,
          console log, script sources and the figure (layout in write_h5; read back with load_h5)
    .csv  plain-text copy of the raw sweep (written before the analysis, in case it fails)
"""

import os
import re
import sys
import json
import time
from datetime import datetime
from ctypes import c_double, c_int, c_int16, c_uint32, byref, create_string_buffer

import numpy as np
import matplotlib.pyplot as plt
import h5py

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lab-control'))
import Lab_control as pic
from TLPM import TLPM

# =============================================================================
# Settings
# =============================================================================
DUT_NAME        = 'HP11982A' #PDA05CF2_SM1FCA2_DET2_no_splitting'     # default only: the script asks for the DUT (and TIA gain) every run
WAVELENGTH_NM   = 1550
LOAD            = 'HiZ'          # 'HiZ' or '50ohm' (50 ohm feed-through/T-splitter + 50 Ohm terminator at the Keithley input)
TIA_GAIN        = 10e3           # default V/A for this load (PDA05CF2: 10 kV/A Hi-Z, 5 kV/A 50 ohm), None to skip
 
SPLIT_RATIO         = 0.9598#2653 #289 #955 #1.0        # P(DUT arm) / P(monitor arm) #Measured from handheld powermeter: Photodetector arm: 1.214, 0.8706, 0.4007, 0.1881, 0.0982 powermeter arm: 4.187, 3.015, 1.372, 0.6488, 0.3442  # Measured from M01246265 Photodetector arm: 1.537 mW, 1.126mW, 0.805 mW, 0.3827, 0.2011. Powermeter arm: 1.607 mW, 1.186mW, 0.842mW, 0.4001, 0.2103
MEASURE_SPLIT_RATIO = False

PM_SERIAL       = 'M01246265' #'P0024530'
KEITHLEY_IP     = '192.168.1.151'
NPLC            = 1              # Keithley integration, 1 PLC = 20 ms
PM_AVG_TIME     = 0.02           # s, same window as the Keithley

N_DARK          = 30             # readings for the dark offset
MAX_DURATION    = 300            # s, the sweep also stops with Ctrl+C
LIVE_PLOT       = True           # run in the VS Code terminal (python photodetector_characterization.py), not the Interactive Window
LIVE_PLOT_INTERVAL = 1.0         # s between redraws (each costs ~0.05-0.1 s of measuring time)
FIT_V_RANGE     = (0.01, 0.5)    # linear fit uses V_net between these fractions of the max V_net

SAVE_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\Photodetector' #r'C:\Users\shd-photonics-inp\Documents\Jeppe_Surrow\Photodetector'


run_record = {'prompts': []}     # everything recorded during the run that goes into the h5 file besides the sweep


def settings():
    """Every UPPER_CASE setting of this script (DUT_NAME / TIA_GAIN as answered in the pop-ups)."""
    return {k: v for k, v in globals().items() if k.isupper() and not k.startswith('_')}


class Tee:
    """Copies everything printed to the console into a list of lines (saved in the h5 file)."""

    def __init__(self):
        self.lines, self._buf, self._orig = [], '', sys.stdout
        sys.stdout = self

    def write(self, text):
        self._orig.write(text)
        self._buf += text
        while '\n' in self._buf:
            line, self._buf = self._buf.split('\n', 1)
            self.lines.append(line)
        return len(text)

    def flush(self):
        self._orig.flush()

    def __getattr__(self, name):                     # encoding, isatty, ... of the real stdout
        return getattr(self._orig, name)


# =============================================================================
# Run inputs
# =============================================================================
def popup(title, prompt, initial):
    """Pop-up text box (as ask_label in the bias tee scripts). Returns None on Cancel.
    Falls back to a console prompt if no display is available."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)              # don't hide behind VS Code
        root.after(200, lambda: _focus_entry(root))    # take the keyboard, or typing lands in the terminal
        s = simpledialog.askstring(title, prompt, initialvalue=initial, parent=root)
        root.destroy()
    except Exception as e:
        print('(pop-up not available: %s)' % e)
        s = input('%s [%s]: ' % (prompt, initial)).strip() or initial
    return None if s is None else s.strip()


def _focus_entry(widget):
    for w in widget.winfo_children():
        if w.winfo_class() == 'Entry':
            w.focus_force(); w.select_range(0, 'end')
            return True
        if _focus_entry(w):
            return True
    return False


def wait_enter(msg):
    """input() that ignores keys pressed before the prompt appeared (e.g. an Enter hit while connecting)."""
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
    except ImportError:
        pass
    input(msg)
    run_record['prompts'].append('[%s] %s' % (datetime.now().isoformat(timespec='seconds'), msg.strip()))


def ask_dut():
    """Pop-ups for the DUT name and TIA gain. Cancel aborts the run (nothing is connected yet)."""
    title = 'Photodetector characterization'
    name = popup(title, 'Device under test (DUT):\n(goes into the file names in %s)' % SAVE_FOLDER, DUT_NAME)
    if not name:
        sys.exit('No DUT name given, aborted.')
    name = re.sub(r'[\\/:*?"<>|\s]+', '_', name)     # it goes into the file name
    s, error = '%g' % TIA_GAIN if TIA_GAIN else 'none', ''
    while True:
        s = popup(title, '%sTIA gain of %s with %s load [V/A]:\n("none" to skip the responsivity)'
                  % (error, name, LOAD), s)
        if s is None:
            sys.exit('Aborted.')
        if s.lower() == 'none':
            return name, None
        try:
            return name, float(s)
        except ValueError:
            error = '"%s" is not a number.\n\n' % s


# =============================================================================
# Instruments
# =============================================================================
def find_power_meters():
    """Serial numbers of the Thorlabs power meters the TLPM driver can see."""
    tl = TLPM()
    n = c_uint32()
    tl.findRsrc(byref(n))
    serials = []
    for i in range(n.value):
        model, serial, maker = (create_string_buffer(1024) for _ in range(3))
        tl.getRsrcInfo(c_int(i), model, serial, maker, byref(c_int16()))
        serials.append((serial.value.decode(), model.value.decode()))
    tl.close()
    return serials


def connect():
    pm_serial = PM_SERIAL
    found = find_power_meters()
    if pm_serial not in [s for s, _ in found]:
        if not found:
            raise RuntimeError('No Thorlabs power meter found (is it plugged in / open in another program?)')
        listing = ', '.join('%s (%s)' % f for f in found)
        print('Power meter %s not found. Connected: %s' % (pm_serial, listing))
        pm_serial = popup('Power meter', 'Power meter %s not found.\nConnected: %s\n\nSerial to use (monitor arm):'
                          % (pm_serial, listing), found[0][0])
        if not pm_serial:
            sys.exit('No power meter chosen, aborted.')
    pm = pic.PM100USB(lambda0=WAVELENGTH_NM, PM_name=pm_serial)
    pm.PDinstr.setPowerUnit(c_int16(0))              # W
    pm.PDinstr.setAvgTime(c_double(PM_AVG_TIME))     # set once (GetPower() re-sets it every call)
    run_record['power_meter'] = power_meter_info(pm, pm_serial, dict(found).get(pm_serial, ''))

    k = pic.DC_KEITHLEY_2450(GPIB_interface=-1, IP_address=KEITHLEY_IP)
    k.SetHighZVoltmeter(vlim=20, nplc=NPLC)          # source 0 A, measure V, autorange
    k.SwitchOn()
    run_record['keithley'] = keithley_info(k)
    return pm, k


def power_meter_info(pm, serial, model):
    """Identity and read-back settings of the power meter and its sensor (for the h5 file)."""
    d = {'serial': serial, 'model': model}
    tl = pm.PDinstr
    try:
        msg = create_string_buffer(1024)
        tl.getCalibrationMsg(msg)
        d['calibration'] = msg.value.decode()
    except Exception as e:
        d['calibration_error'] = str(e)
    try:
        name, snr, msg = (create_string_buffer(1024) for _ in range(3))
        tl.getSensorInfo(name, snr, msg, byref(c_int16()), byref(c_int16()), byref(c_int16()))
        d['sensor'], d['sensor_serial'], d['sensor_calibration'] = (b.value.decode() for b in (name, snr, msg))
    except Exception as e:
        d['sensor_error'] = str(e)
    for key, fn in (('wavelength_nm', tl.getWavelength), ('avg_time_s', tl.getAvgTime)):
        try:
            x = c_double()
            fn(c_int16(0), byref(x))
            d[key] = x.value
        except Exception as e:
            d[key + '_error'] = str(e)
    return d


def keithley_info(k):
    """Identity and read-back settings of the Keithley 2450 (for the h5 file)."""
    d = {}
    for q in ('*IDN?', ':SOUR:FUNC?', ':SOUR:CURR?', ':SOUR:CURR:VLIM?', ':SENS:FUNC?', ':SENS:VOLT:NPLC?',
              ':SENS:VOLT:RANG:AUTO?', ':SENS:VOLT:RANG?', ':SENS:VOLT:RSEN?', ':OUTP:CURR:SMOD?', ':OUTP?'):
        try:
            d[q] = k.instr.query(q).strip()
        except Exception as e:
            d[q] = 'error: %s' % e
    return d


def read_power(pm):
    p = c_double()
    pm.PDinstr.measPower(byref(p))
    return p.value


def read_voltage(k):
    return float(k.instr.query('READ?'))


def readings(fn, n):
    return np.array([fn() for _ in range(n)])


# =============================================================================
# Measurement
# =============================================================================
def measure_split_ratio(pm, n=30):
    wait_enter('Power meter on the MONITOR arm, VOA fixed. Enter...')
    p_mon = readings(lambda: read_power(pm), n)
    wait_enter('Power meter on the DUT arm fiber end. Enter...')
    p_dut = readings(lambda: read_power(pm), n)
    ratio = p_dut.mean() / p_mon.mean()
    run_record['split_P_monitor_W'], run_record['split_P_dut_W'] = p_mon, p_dut
    print('SPLIT_RATIO = %.4f  (%.3f dB)  <- put this in the settings' % (ratio, 10 * np.log10(ratio)))
    wait_enter('Power meter back on the MONITOR arm, detector on the DUT arm. Enter...')
    return ratio


def measure_dark(pm, k):
    wait_enter('\nLaser OFF / output blocked. Enter to measure the dark offset...')
    v = readings(lambda: read_voltage(k), N_DARK)
    p = readings(lambda: read_power(pm), N_DARK)
    run_record['dark_V_readings'], run_record['dark_P_pm_readings'] = v, p
    v0, v_noise, p0 = v.mean(), v.std(), p.mean()
    print('Dark: V = %.3f mV (noise %.1f uV rms),  P_pm = %.3g W' % (v0 * 1e3, v_noise * 1e6, p0))
    wait_enter('Laser ON. Enter...')
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
    wait_enter('\nStart turning the VOA slowly, then press Enter. Ctrl+C (or close the live plot) to stop.')
    t, P, V, Pb, Pa = [], [], [], [], []
    run_record['sweep_start'] = datetime.now().isoformat()
    run_record['stop_reason'] = 'MAX_DURATION reached'
    t0 = time.time()
    p_before = read_power(pm)
    try:
        while time.time() - t0 < MAX_DURATION:
            v = read_voltage(k)
            p_after = read_power(pm)
            t.append(time.time() - t0)
            V.append(v)
            P.append(0.5 * (p_before + p_after))     # power at the time of the voltage reading
            Pb.append(p_before); Pa.append(p_after)
            p_before = p_after
            if live is not None:
                if live.closed:
                    run_record['stop_reason'] = 'live plot closed'
                    break
                if live.update(P, V):
                    p_before = read_power(pm)        # the redraw took time: start a fresh pair
            elif len(V) % 20 == 0:
                print('  %5.1f s   P_pm = %.3e W   V = %.4f V' % (t[-1], P[-1], v))
    except KeyboardInterrupt:
        print('Stopped.')
        run_record['stop_reason'] = 'Ctrl+C'
        try:
            k.instr.clear()                          # flush a reply interrupted by Ctrl+C
        except Exception:
            pass
    run_record['sweep_end'] = datetime.now().isoformat()
    n = min(len(t), len(V), len(P), len(Pb), len(Pa))  # Ctrl+C can land between the appends
    t, P, V, Pb, Pa = t[:n], P[:n], V[:n], Pb[:n], Pa[:n]
    run_record['P_pm_before_W'], run_record['P_pm_after_W'] = np.array(Pb), np.array(Pa)
    if live is not None and not live.closed:
        plt.close(live.fig)
    plt.ioff()
    print('%d points in %.0f s' % (len(V), t[-1] if t else 0))
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
    shown = pos & (np.abs(dev) <= 5)                  # x-axis spans only the points inside the y-range
    if shown.sum() > 1:
        ax[2].set_xlim(P[shown].min() / 1.5, P[shown].max() * 1.5)
    ax[2].set_xlabel('P on detector [W]'); ax[2].set_ylabel('deviation from linear [%]'); ax[2].legend()
    fig.colorbar(sc, ax=ax[2], label='time [s]')
    for a in ax:
        a.grid(True, which='both', alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


# =============================================================================
# HDF5
# =============================================================================
def _attr(val):
    """h5py-safe attribute value (None -> 'None', dict/other -> json), as in bias_tee_utils."""
    if val is None:
        return 'None'
    if isinstance(val, np.generic):
        return val.item()
    if isinstance(val, (bool, int, float, str, np.ndarray)):
        return val
    if isinstance(val, (list, tuple)) and all(isinstance(x, (int, float)) for x in val):
        return np.asarray(val, float)
    return json.dumps(val, default=str)


def _store_file(group, name, path):
    """A file (script source, figure, original csv) as gzip-compressed bytes with its sha256."""
    import hashlib
    try:
        data = open(path, 'rb').read()
    except Exception as e:
        group.attrs[name + '_error'] = str(e)
        return
    ds = group.create_dataset(name, data=np.frombuffer(data, np.uint8), compression='gzip', compression_opts=9)
    ds.attrs['sha256'] = hashlib.sha256(data).hexdigest()
    ds.attrs['bytes'] = len(data)
    ds.attrs['path'] = path


def write_h5(path, cfg, t, P_pm, V, dark, ratio, run, analysis=None, png=None, log_lines=(),
             sources=None, extra=None):
    """One HDF5 file per run.

    /              attrs: dut, wavelength, load, TIA gain, split ratio (+ source), times, stop reason, notes
    /data          raw sweep: t_s, P_pm_W (mean of the readings before and after each voltage reading),
                   P_pm_before_W, P_pm_after_W, V_V
    /dark          attrs V_dark_V, V_noise_V (rms), P_pm_dark_W + the raw readings
    /split_ratio   attrs value, source (+ the raw readings when MEASURE_SPLIT_RATIO)
    /results       fit results (attrs) + P_detector_W, V_net_V, deviation_percent, fit_mask
    /settings      every UPPER_CASE setting as an attribute (+ settings_json)
    /instruments   power_meter / keithley: identity and read-back settings
    /analysis      the formulas used
    /log           console_log, prompts (time-stamped terminal steps)
    /environment   Python / package versions, git commit
    /files         script sources (gzip bytes + sha256), the figure, and originals of converted files
    Read back with load_h5(); a stored file: bytes(h5['files'][name][()]).
    """
    import platform
    import subprocess
    run = dict(run)
    with h5py.File(path, 'w') as hf:
        hf.attrs['format'] = 'photodetector_characterization h5 v1'
        hf.attrs['created'] = datetime.now().isoformat()
        hf.attrs['dut'] = str(cfg['DUT_NAME'])
        hf.attrs['wavelength_nm'] = float(cfg['WAVELENGTH_NM'])
        hf.attrs['load'] = str(cfg['LOAD'])
        hf.attrs['tia_gain_V_per_A'] = _attr(cfg['TIA_GAIN'])
        hf.attrs['split_ratio'] = float(ratio)
        for key in ('start', 'sweep_start', 'sweep_end', 'stop_reason', 'analysis_error'):
            if key in run:
                hf.attrs[key] = str(run[key])
        for k, v in (extra or {}).items():
            hf.attrs[k] = _attr(v)

        g = hf.create_group('data')
        for name, arr, unit in (('t_s', t, 's since the sweep start'), ('P_pm_W', P_pm, 'W, monitor arm, mean of before/after'),
                                ('P_pm_before_W', run.get('P_pm_before_W'), 'W, monitor arm, read just before V'),
                                ('P_pm_after_W', run.get('P_pm_after_W'), 'W, monitor arm, read just after V'),
                                ('V_V', V, 'V, Keithley 2450 reading of the detector output (dark not subtracted)')):
            if arr is not None and len(arr):
                g.create_dataset(name, data=np.asarray(arr, float)).attrs['unit'] = unit

        g = hf.create_group('dark')
        g.attrs['V_dark_V'], g.attrs['V_noise_V'], g.attrs['P_pm_dark_W'] = (float(x) for x in dark)
        for name, key in (('V_readings_V', 'dark_V_readings'), ('P_pm_readings_W', 'dark_P_pm_readings')):
            if run.get(key) is not None:
                g.create_dataset(name, data=np.asarray(run[key], float))
        if 'dark_note' in run:
            g.attrs['note'] = run['dark_note']

        g = hf.create_group('split_ratio')
        g.attrs['value'] = float(ratio)
        g.attrs['definition'] = 'P(DUT arm) / P(monitor arm)'
        if run.get('split_P_monitor_W') is not None:
            g.attrs['source'] = 'measured in this run (MEASURE_SPLIT_RATIO = True)'
            g.create_dataset('P_monitor_W', data=np.asarray(run['split_P_monitor_W'], float))
            g.create_dataset('P_dut_W', data=np.asarray(run['split_P_dut_W'], float))
        else:
            g.attrs['source'] = run.get('split_source', 'SPLIT_RATIO setting')

        if analysis is not None:
            P, Vn, dev, m, r = analysis
            g = hf.create_group('results')
            for k, v in r.items():
                g.attrs[k] = _attr(v)
            g.attrs['NEP_W'] = float(r['dark_noise_V'] / r['gain_V_per_W'])
            if r['P_comp_W']:
                g.attrs['P_comp_dBm'] = float(10 * np.log10(r['P_comp_W'] / 1e-3))
            g.create_dataset('P_detector_W', data=P)
            g.create_dataset('V_net_V', data=Vn)
            g.create_dataset('deviation_percent', data=dev)
            g.create_dataset('fit_mask', data=m)

        g = hf.create_group('settings')
        for k, v in sorted(cfg.items()):
            g.attrs[k] = _attr(v)
        g.attrs['settings_json'] = json.dumps(cfg, default=str, indent=1, sort_keys=True)

        g = hf.create_group('instruments')
        for inst in ('power_meter', 'keithley'):
            sub = g.create_group(inst)
            for k, v in run.get(inst, {}).items():
                sub.attrs[k] = _attr(v)

        g = hf.create_group('analysis')
        g.attrs['P_detector'] = 'P_detector = split_ratio * (P_pm - P_pm_dark)'
        g.attrs['V_net'] = 'V_net = V - V_dark'
        g.attrs['fit'] = ('linear least squares V_net = gain * P_detector + intercept, using points with '
                          'FIT_V_RANGE[0] < V_net / max(V_net) < FIT_V_RANGE[1]')
        g.attrs['responsivity'] = 'responsivity = gain / TIA_GAIN'
        g.attrs['deviation'] = 'deviation_percent = 100 * (V_net / (gain * P_detector + intercept) - 1)'
        g.attrs['compression'] = ('1 % compression: lowest P_detector where the running median (15 points, sorted by P) '
                                  'of the deviation is below -1 % and V_net > FIT_V_RANGE[1] / 2 * max(V_net)')
        g.attrs['NEP'] = 'NEP = V_noise (rms of the dark readings) / gain'

        g = hf.create_group('log')
        str_dt = h5py.string_dtype('utf-8')
        g.create_dataset('console_log', data='\n'.join(log_lines), dtype=str_dt)
        g.create_dataset('prompts', data=list(run.get('prompts', [])) or [''], dtype=str_dt)

        g = hf.create_group('environment')
        g.attrs['python'] = sys.version
        g.attrs['platform'] = platform.platform()
        g.attrs['hostname'] = platform.node()
        for mod in ('numpy', 'h5py', 'matplotlib', 'pyvisa'):
            if mod in sys.modules and hasattr(sys.modules[mod], '__version__'):
                g.attrs[mod] = sys.modules[mod].__version__
        try:
            kw = dict(cwd=os.path.dirname(os.path.abspath(__file__)), capture_output=True, text=True, timeout=5)
            head = subprocess.run(['git', 'rev-parse', 'HEAD'], **kw)
            if head.returncode == 0:
                g.attrs['git_commit'] = head.stdout.strip()
                g.attrs['git_dirty'] = bool(subprocess.run(['git', 'status', '--porcelain'], **kw).stdout.strip())
        except Exception:
            pass

        g = hf.create_group('files')
        if sources is None:
            sources = {os.path.basename(__file__): os.path.abspath(__file__),
                       'Lab_control.py': os.path.abspath(pic.__file__)}
        for name, p in sources.items():
            _store_file(g, name, p)
        if png and os.path.exists(png):
            _store_file(g, 'figure.png', png)


def load_h5(path):
    """Raw data, dark, split ratio and settings of a run -> dict (enough to redo the analysis)."""
    with h5py.File(path, 'r') as hf:
        d = {k: hf['data'][k][()] for k in hf['data']}
        d['dark'] = tuple(float(hf['dark'].attrs[k]) for k in ('V_dark_V', 'V_noise_V', 'P_pm_dark_W'))
        d['split_ratio'] = float(hf['split_ratio'].attrs['value'])
        d['settings'] = json.loads(hf['settings'].attrs['settings_json'])
        d['attrs'] = dict(hf.attrs)
        if 'results' in hf:
            d['results'] = dict(hf['results'].attrs)
    return d


# =============================================================================
# Run
# =============================================================================
if __name__ == '__main__':
    tee = Tee()
    DUT_NAME, TIA_GAIN = ask_dut()
    run_record['start'] = datetime.now().isoformat()
    pm, k = connect()
    try:
        ratio = measure_split_ratio(pm) if MEASURE_SPLIT_RATIO else SPLIT_RATIO
        dark = measure_dark(pm, k)
        t, P_pm, V = sweep(pm, k, dark, ratio)
    finally:
        k.SwitchOff(); k.CloseConnection(); pm.closeConnection()
    if len(V) < 10:
        sys.exit('Only %d points measured, nothing saved.' % len(V))

    os.makedirs(SAVE_FOLDER, exist_ok=True)
    base = os.path.join(SAVE_FOLDER, '%s_%s_%gnm_%s' % (pic.datetimestring(), DUT_NAME, WAVELENGTH_NM, LOAD))
    np.savetxt(base + '.csv', np.column_stack([t, P_pm, V]), delimiter=',',
               header='split_ratio=%g, dark_V=%g, dark_noise_V=%g, dark_P_pm=%g\nt_s,P_pm_W,V_V' % (ratio, *dark))

    analysis = None
    try:
        analysis = analyze(t, P_pm, V, dark, ratio)
        plot(t, *analysis, base + '.png')
    except Exception as e:                           # e.g. no points in FIT_V_RANGE: the raw data is still saved
        print('Analysis failed: %r' % e)
        run_record['analysis_error'] = repr(e)
    write_h5(base + '.h5', settings(), t, P_pm, V, dark, ratio, run_record, analysis,
             base + '.png' if analysis else None, tee.lines)
    print('Saved', base + '.h5 / .png / .csv')
    plt.show()
