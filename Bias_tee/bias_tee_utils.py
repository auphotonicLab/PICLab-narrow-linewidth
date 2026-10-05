#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared helpers for bias_tee_characterization.py (same split as Eye_diagram_lab.py / eye_diagram_utils.py).

bias_tee_characterization.py holds the settings and decides which stages to run; everything that
talks to the instruments, analyses the data and saves it lives here.

Contents
--------
Setup                 instruments (SDG, receiver, Keithley) + the safe-operation logic + one frequency sweep
stage1/2/3            the three measurement stages (each returns a stage-result dict)
run_stage             runs one stage and saves everything (h5, csv, pdf, svg, screenshots)
tone_spectrum         flat-top FFT of a scope record -> tone power in dBm (equivalent to the ESA reading)
write_stage_h5        HDF5 writer (data + ALL settings + script sources);  load_scope_record() / extract_script() read back
ask_label             pop-up asking for the save label (as in Eye_diagram_lab.py)

Receiver ("MEASUREMENT" setting)
    'scope'  Siglent SDS2352X-E: raw time data -> flat-top FFT.  1 MOhm input => use a 50 ohm feed-through.
    'fsw'    R&S FSW50 ESA   (class ESA_RS_FSW50)
    'ssa'    Siglent SSA3021X (class ESA_SIGLENT), starts at 9 kHz

DC convention
    A Thorlabs PD has a 50 ohm series resistor: 0-10 V into Hi-Z, 0-5 V into 50 ohm.  The SDG is kept in its
    "50 ohm load" mode, so a value typed in is what a 50 ohm load would see.  In the bias tee the AC path ends in
    the receiver (50 ohm) but the DC path is (almost) open, so the DC voltage at the DC port / Keithley is
    DC_AT_TEE_FACTOR (= 2) x the SDG offset (= what the PD shows into Hi-Z).
"""

import io
import os
import re
import sys
import csv
import json
import time
from datetime import datetime
from types import SimpleNamespace

import numpy as np
import matplotlib.pyplot as plt
import h5py
import pyvisa

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(_here, '..', 'lab-control'))
import Lab_control as pic

MIN_FREQ_HZ = {'fsw': 10.0, 'ssa': 9e3, 'scope': 0.0}      # lowest tone each receiver can measure
RECEIVER_NAMES = {'scope': 'SDS2352X-E scope', 'fsw': 'FSW50 ESA', 'ssa': 'SSA3021X ESA'}

# Plot colours (dataviz reference palette; categorical slots 1-3 validated all-pairs, sequential blue ramp for DC level)
SURFACE, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
CATEGORICAL = ['#2a78d6', '#eb6834', '#1baf7a']
MARKERS = ['o', 's', '^', 'D', 'v', 'P', 'X', '*']
SEQ_LIGHT, SEQ_DARK = '#86b6ef', '#0d366b'


# =============================================================================
# Config / small helpers
# =============================================================================

def config_from_globals(g):
    """All UPPER_CASE names of the runner module -> one config object."""
    return SimpleNamespace(**{k: v for k, v in g.items() if k.isupper()})


def validate_config(cfg):
    if cfg.MEASUREMENT not in RECEIVER_NAMES:
        raise ValueError("MEASUREMENT must be one of %s, got %r" % (list(RECEIVER_NAMES), cfg.MEASUREMENT))
    stages = list(cfg.STAGES_TO_RUN)
    if not stages or any(s not in (1, 2, 3) for s in stages):
        raise ValueError('STAGES_TO_RUN must be a non-empty list drawn from 1, 2, 3, got %r' % (cfg.STAGES_TO_RUN,))
    if cfg.MEASUREMENT == 'scope' and not cfg.SCOPE_IP:
        raise ValueError('Set SCOPE_IP (IP address of the SDS2352X-E) in bias_tee_characterization.py')
    if not len(cfg.FREQUENCIES_HZ):
        raise ValueError('FREQUENCIES_HZ is empty')
    pre_mA = short_current_mA(cfg, cfg.DC_PRECHECK_OFFSET_V)
    if pre_mA > 0.5 * 1e3 * cfg.INDUCTOR_MAX_A:
        raise ValueError('DC_PRECHECK_OFFSET_V = %g V would draw %.1f mA into a short (> half of the %.0f mA inductor rating); '
                         'use a smaller value' % (cfg.DC_PRECHECK_OFFSET_V, pre_mA, 1e3 * cfg.INDUCTOR_MAX_A))
    for lvl in cfg.PD_DC_LEVELS_V:
        if lvl + cfg.VPP / 2 > cfg.PD_MAX_50OHM_V:
            print('WARNING: DC level %.2f V + %.2f V peak AC exceeds %.1f V - a real PD would saturate and the '
                  'SDG may refuse it.' % (lvl, cfg.VPP / 2, cfg.PD_MAX_50OHM_V))


def expected_dbm(vpp, load=50.0):
    return 10 * np.log10((vpp / (2 * np.sqrt(2))) ** 2 / load * 1e3)


def esa_settings(freq):
    """Span / RBW (in MHz, as the Lab_control ESA classes want them) for a tone at freq."""
    span = max(0.2 * freq, 200.0)          # Hz
    rbw = max(0.01 * freq, 10.0)           # Hz (SSA min RBW = 10 Hz)
    return span / 1e6, rbw / 1e6


PROMPT_LOG = []        # every re-wiring prompt shown to the user (saved in the h5 file)


def ask(msg):
    PROMPT_LOG.append((datetime.now().isoformat(), msg))
    print('\n' + '=' * 78)
    print(msg)
    input('Press ENTER when done (Ctrl+C aborts)... ')


class Tee:
    """Copies everything printed to the console into a list of lines (saved as _log.txt and in the h5 file)."""

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

    def __getattr__(self, name):               # encoding, isatty, ... of the real stdout
        return getattr(self._orig, name)

    def close(self):
        if sys.stdout is self:
            sys.stdout = self._orig


def safe_name(text):
    """Folder / file name safe on Windows."""
    return re.sub(r'[^A-Za-z0-9._+-]+', '_', str(text)).strip('_.')


def ask_label(save_folder, default_label, title='Bias tee characterization'):
    """Pop-up asking for the label of this measurement (as in Eye_diagram_lab.py).

    Files are saved in <save_folder>/<label>/.  Cancelling the pop-up gives the label 'unlabelled'.
    Falls back to a console prompt if no display is available.
    """
    prompt = ('Enter a label for this measurement.\n'
              'Files will be saved in:  %s\\<label>\\<timestamp>_stage<N>_*.h5 / .pdf / .svg / .png' % save_folder)
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        label = simpledialog.askstring(title, prompt, initialvalue=default_label, parent=root) or ''
        root.destroy()
    except Exception as e:
        print('(pop-up not available: %s)' % e)
        print(prompt)
        label = input('Label [%s]: ' % default_label).strip() or default_label
    return label


# =============================================================================
# Analysis: scope record -> tone power
# =============================================================================

def flattop(n):
    """5-term flat-top window, amplitude-accurate to <0.01 dB."""
    k = np.arange(n) * 2 * np.pi / (n - 1)
    a = (0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368)
    return a[0] - a[1] * np.cos(k) + a[2] * np.cos(2 * k) - a[3] * np.cos(3 * k) + a[4] * np.cos(4 * k)


def tone_spectrum(volt, dt, f0, load=50.0):
    """Single-sided amplitude spectrum of a record and the tone near f0.

    Returns dict: f (Hz), dbm (per-bin tone power into `load`), f_peak, vpk, p_dbm, snr_db, df.
    Power of a sine of peak amplitude A across `load`: A^2 / (2*load).
    """
    v = volt - np.mean(volt)
    n = len(v)
    w = flattop(n)
    amp = 2.0 * np.abs(np.fft.rfft(v * w)) / np.sum(w)          # volt peak per bin
    f = np.fft.rfftfreq(n, dt)
    df = f[1] - f[0]
    sel = np.where(np.abs(f - f0) <= max(0.05 * f0, 8 * df))[0]
    k = sel[np.argmax(amp[sel])]
    vpk = amp[k]
    away = np.abs(f - f[k]) > 12 * df
    noise = np.median(amp[away & (f > 0)]) if np.any(away & (f > 0)) else np.nan
    to_dbm = lambda a: 10 * np.log10(np.maximum(a, 1e-30) ** 2 / (2 * load) * 1e3)
    harm = {}
    for n in (2, 3):                                     # harmonic level relative to the carrier (dBc)
        fn = n * f[k]
        if fn < f[-1] - 6 * df:
            w = np.where(np.abs(f - fn) <= max(0.01 * fn, 6 * df))[0]
            harm[n] = float(to_dbm(amp[w].max()) - to_dbm(vpk))
        else:
            harm[n] = np.nan
    return {'f': f, 'dbm': to_dbm(amp), 'f_peak': f[k], 'vpk': vpk, 'p_dbm': float(to_dbm(vpk)),
            'snr_db': float(to_dbm(vpk) - to_dbm(noise)) if np.isfinite(noise) else np.nan, 'df': df,
            'h2_dbc': harm[2], 'h3_dbc': harm[3]}


def save_screenshot_png(recv, png_path):
    """Screenshot of the receiver saved as PNG (the scope and SSA deliver BMP, the FSW delivers PNG)."""
    tmp = png_path + '.tmp'
    recv.saveScreenshotToPC(tmp)
    with open(tmp, 'rb') as f:
        data = f.read()
    os.remove(tmp)
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        with open(png_path, 'wb') as f:
            f.write(data)
    else:
        from PIL import Image
        Image.open(io.BytesIO(data)).convert('RGB').save(png_path)


# =============================================================================
# Instruments + one frequency sweep
# =============================================================================

class Setup:
    """Holds the instruments and the safe-operation logic."""

    def __init__(self, cfg, need_keithley):
        self.cfg = cfg
        self.kind = cfg.MEASUREMENT
        self.is_scope = (self.kind == 'scope')
        self.rx_coupling = None
        self.rx_dc_coupled = None        # True only for a DC-coupled ESA input => no DC allowed
        self.rx_text = ('scope CH%d (50 ohm input)' % cfg.SCOPE_CH
                        if self.is_scope else RECEIVER_NAMES[self.kind])
        self.last_vdiv = None
        self.last_snr = np.nan
        self.run_folder = None
        self.base_name = None
        self.stage_screenshots = []
        self.screenshots_ok = bool(cfg.SAVE_SCREENSHOTS)
        self.used_keys = set()
        self.tee = Tee()                       # console log -> _log.txt and h5
        self.log_idx = self.prompt_idx = 0
        self.stage_settings = {}
        self.last_afg_readback = ('', '')
        self.keithley_setup = None

        print('Connecting to instruments...')
        # 1) make sure the SDG output is OFF before anything else touches it
        rm = pyvisa.ResourceManager()
        r = rm.open_resource('TCPIP0::' + cfg.AFG_IP + '::inst0::INSTR')
        r.write('C%d:OUTP OFF' % cfg.AFG_CH)
        r.close()
        self.afg = pic.AFG_Siglent(IP_address=cfg.AFG_IP, channel=cfg.AFG_CH, frequency=cfg.FREQUENCIES_HZ[0],
                                   waveform='SINE', vpp=cfg.VPP, offset=0, load=cfg.AFG_LOAD)
        self.afg.output_status(channel=cfg.AFG_CH, status='OFF')

        # 2) receiver: scope or ESA
        if self.is_scope:
            self.recv = pic.SCOPE_SIGLENT_SDS(IP_address=cfg.SCOPE_IP)
        elif self.kind == 'fsw':
            self.recv = pic.ESA_RS_FSW50(IP_address=cfg.FSW_IP)
        else:
            self.recv = pic.ESA_SIGLENT(IP_address=cfg.SSA_IP, USB_interface=-1)
        self.recv.instr.timeout = cfg.RECEIVER_TIMEOUT_MS
        self.recv_idn = self.recv.instr.query('*IDN?').strip()
        if not self.is_scope:
            print('ESA:', self.recv_idn)
            rl_cmd = 'DISP:TRAC:Y:RLEV ' if self.kind == 'fsw' else ':DISP:WIND:TRAC:Y:SCAL:RLEV '
            self.recv.instr.write(rl_cmd + str(cfg.ESA_REF_LEVEL_DBM))
        self.afg_idn = self.afg.instr.query('*IDN?').strip()

        # 3) Keithley as high-Z DC monitor
        self.keithley = None
        self.keithley_idn = ''
        if need_keithley:
            ask('The Keithley will now be reset (*RST) and put in 0 A / HIGH-Z voltmeter mode.\n'
                '  During the reset its output-off state is briefly NORMAL (= near short), so make sure the\n'
                '  Keithley is NOT connected to the bias tee DC port yet. You connect it later, when asked.')
            self.keithley = pic.DC_KEITHLEY_2450(channel=21, GPIB_interface=-1, IP_address=cfg.KEITHLEY_IP)
            self.keithley_setup = {'vlim_V': 20, 'nplc': 1, 'mode': 'current source 0 A / voltage measure, high-Z'}
            self.keithley.SetHighZVoltmeter(vlim=20, nplc=1)
            self.keithley.SwitchOn()
            self.keithley_idn = self.keithley.instr.query('*IDN?').strip()
            try:
                print('Keithley terminals in use (reset selects FRONT):', self.keithley.instr.query(':ROUT:TERM?').strip())
            except Exception as e:
                print('  (could not read Keithley terminal selection: %s)' % e)

    # ---- output location -------------------------------------------------------
    def begin_stage(self, run_folder, base_name):
        self.run_folder, self.base_name = run_folder, base_name
        self.stage_screenshots = []
        self.used_keys = set()
        self.log_idx, self.prompt_idx = len(self.tee.lines), len(PROMPT_LOG)
        self.stage_sweeps = []              # every sweep of this stage, also an aborted one (for the partial save)
        self.stage_settings = {}
        if self.is_scope and self.screenshots_ok and self.cfg.SCREENSHOT_FREQS_HZ:
            print('NOTE: to compare with the scope\'s own FFT, enable Math -> FFT (source C%d, window Flat Top, unit dBm) '
                  'on the scope screen now;\n      the screenshots then show it next to the time signal (see the _fftcheck figure).'
                  % self.cfg.SCOPE_CH)
        self.stage_settings['stage_start'] = self.settings_snapshot()

    # ---- read back every instrument setting (queries only; never changes anything) ----------------------
    def _queries(self):
        cfg, ch = self.cfg, 'C%d' % self.cfg.AFG_CH
        q = {'sdg': ['*IDN?', ch + ':BSWV?', ch + ':OUTP?']}
        if self.keithley is not None:
            q['keithley'] = ['*IDN?', ':ROUT:TERM?', ':OUTP?', ':SOUR:FUNC?', ':SOUR:CURR?', ':SOUR:CURR:VLIM?', ':OUTP:CURR:SMOD?',
                             ':SENS:VOLT:NPLC?', ':SENS:VOLT:RANG:AUTO?', ':SENS:VOLT:RANG?', ':SENS:VOLT:RSEN?']
        sc = 'C%d' % cfg.SCOPE_CH
        if self.is_scope:
            q['receiver'] = ['*IDN?', sc + ':CPL?', sc + ':VDIV?', sc + ':OFST?', sc + ':ATTN?', 'BWL?', 'TDIV?',
                             'TRDL?', 'SARA?', 'MSIZ?', 'TRMD?', 'ACQW?', 'SANU? ' + sc]
        elif self.kind == 'fsw':
            q['receiver'] = ['*IDN?', 'INP:COUP?', 'DISP:TRAC:Y:RLEV?', 'FREQ:CENT?', 'FREQ:SPAN?', 'BAND?',
                             'BAND:VID?', 'SWE:POIN?', 'SWE:COUN?', 'INP:ATT?']
        else:
            q['receiver'] = ['*IDN?', ':FREQ:CENT?', ':FREQ:SPAN?', ':DISP:WIND:TRAC:Y:SCAL:RLEV?', ':POW:ATT?',
                             ':BWID?', ':BWID:VID?', ':UNIT:POW?', ':SWE:COUN?', ':SWE:TIME?', ':DET:TRAC1:FUNC?']
        return q

    def settings_snapshot(self):
        instr = {'sdg': self.afg.instr, 'receiver': self.recv.instr}
        if self.keithley is not None:
            instr['keithley'] = self.keithley.instr
        snap = {'time': datetime.now().isoformat()}
        for name, cmds in self._queries().items():
            d = {}
            for c in cmds:
                try:
                    d[c] = str(instr[name].query(c)).strip()
                except Exception as e:
                    d[c] = '<query failed: %s>' % str(e).splitlines()[0][:80]
                    try:
                        instr[name].clear()
                    except Exception:
                        pass
            snap[name] = d
        return snap

    # ---- receiver coupling -----------------------------------------------------
    def set_rx_coupling(self, coupling):
        cfg = self.cfg
        assert coupling in ('AC', 'DC')
        self.afg_output_off()                       # never change coupling with signal/DC present
        if self.is_scope:
            self.recv.SetChannel(cfg.SCOPE_CH, coupling=cfg.SCOPE_COUPLING[coupling], vdiv=self.last_vdiv or 0.1,
                                 offset=0.0, bandwidth_limit=cfg.SCOPE_BWL)
            print('Scope coupling:', cfg.SCOPE_COUPLING[coupling])
            self.rx_dc_coupled = False     # scope handles DC on its 50 ohm input; flag only guards ESA inputs
        elif self.kind == 'fsw':
            self.recv.SetCoupling(coupling)
            got = self.recv.GetCoupling()
            if got != coupling:
                raise RuntimeError('ESA coupling is %s, wanted %s' % (got, coupling))
            print('ESA input coupling:', got)
            self.rx_dc_coupled = (coupling == 'DC')
        else:
            print('SSA3021X: no coupling command used - check the instrument input.')
            self.rx_dc_coupled = (coupling == 'DC')
        self.rx_coupling = coupling

    # ---- SDG -------------------------------------------------------------------
    def afg_output_off(self):
        self.afg.output_status(channel=self.cfg.AFG_CH, status='OFF')

    def set_tone(self, freq, vpp, offset):
        """Configure the SDG (offset is verified by read-back before anything is switched on)."""
        cfg = self.cfg
        if self.rx_dc_coupled and abs(offset) > 0:
            raise RuntimeError('Refusing DC offset %g V while the ESA is DC-coupled' % offset)
        self.afg.instr.write('C%d:OUTP LOAD,%s' % (cfg.AFG_CH, cfg.AFG_LOAD))      # load first, then amplitude/offset
        self.afg.setParameters(channel=cfg.AFG_CH, waveform='SINE', frequency=freq, vpp=vpp,
                               offset=offset, load=cfg.AFG_LOAD)
        self.verify_tone(freq, vpp, offset)

    def verify_tone(self, freq, vpp, offset):
        cfg = self.cfg
        resp = self.afg.instr.query('C%d:BSWV?' % cfg.AFG_CH)
        outp = self.afg.instr.query('C%d:OUTP?' % cfg.AFG_CH)

        def grab(key):
            m = re.search(key + r',([-+0-9.eE]+)', resp)
            return float(m.group(1)) if m else float('nan')
        self.last_afg_readback = (resp.strip(), outp.strip())
        amp, ofst, frq = grab('AMP'), grab('OFST'), grab('FRQ')
        if not (abs(ofst - offset) < 1e-3 and abs(amp - vpp) < 1e-3 * max(1, vpp) + 1e-3
                and abs(frq - freq) < 1e-6 * freq + 1e-3):
            raise RuntimeError('SDG read-back mismatch: asked f=%g amp=%g ofst=%g, got "%s"' % (freq, vpp, offset, resp.strip()))
        if not re.search(r'LOAD,\s*%s\b' % cfg.AFG_LOAD, outp):
            raise RuntimeError('SDG load is not %s ohm: "%s"' % (cfg.AFG_LOAD, outp.strip()))
        if self.rx_dc_coupled and abs(ofst) > 1e-3:
            raise RuntimeError('DC offset present with DC-coupled ESA!')

    # ---- DC monitor ------------------------------------------------------------
    def read_dc(self):
        """Settled Keithley voltage (V)."""
        self.keithley.AssertHighZ()
        prev, v = None, None
        for _ in range(20):
            v = self.keithley.GetMeas()
            if prev is not None and abs(v - prev) < max(2e-3, 5e-3 * abs(v)):
                break
            prev = v
            time.sleep(0.3)
        if abs(v) > self.cfg.PD_MAX_HIZ_V + 1:
            raise RuntimeError('DC monitor reads %.2f V - above any PD level, aborting' % v)
        return v

    # ---- receiver readings -------------------------------------------------------
    def read_point_scope(self, freq, vpp):
        """Acquire time records, FFT with a flat-top window, return the point dict (tone power in dBm into 50 ohm)."""
        cfg, sc = self.cfg, self.recv
        tdiv = sc.nearest_tdiv(cfg.SCOPE_NCYC / freq / 14.0)
        sc.SetTimebase(tdiv, cfg.SCOPE_MEMORY)
        vdiv = self.last_vdiv or sc.nearest_vdiv(vpp / 6.0)
        lo, hi = cfg.SCOPE_PP_CODES
        for _ in range(12):                                  # vertical auto-scale (8 bit => keep signal large)
            sc.SetVertical(cfg.SCOPE_CH, vdiv, 0.0)
            for _retry in range(3):
                codes, vdiv_rb, ofst, dt = sc.Acquire(cfg.SCOPE_CH)
                if len(codes) > 0:
                    break
                print('  warning: scope returned empty waveform, retrying...  scope state: %s  (INR new-acquisition flag seen: %s)'
                      % (sc.Diagnose(cfg.SCOPE_CH), getattr(sc, 'acq_done', '?')))
            if len(codes) == 0:
                raise RuntimeError('Scope returned empty waveform after 3 retries at %.0f Hz  scope state: %s' % (freq, sc.Diagnose(cfg.SCOPE_CH)))
            pp = int(codes.max()) - int(codes.min())
            clipped = bool(codes.max() >= 126 or codes.min() <= -127)
            if clipped:
                new = sc.nearest_vdiv(vdiv_rb * 2.0)
            elif pp > hi or pp < lo:
                if pp < 4:
                    new = sc.nearest_vdiv(vpp / 6.0)        # near-zero pp: reset to vpp-based estimate
                else:
                    new = sc.nearest_vdiv(vdiv_rb * pp / 150.0)   # aim at ~6 div pk-pk
            else:
                break
            if new == vdiv_rb:
                break
            vdiv = new
        self.last_vdiv = vdiv_rb
        info = sc.GetAcquisitionInfo(cfg.SCOPE_CH)
        if abs(len(codes) * dt - 14 * info['tdiv']) > 0.2 * 14 * info['tdiv']:
            print('  warning: record length %.3g s differs from 14 x tdiv (%.3g s)' % (len(codes) * dt, 14 * info['tdiv']))
        if pp < 40:
            print('  warning: only %d ADC codes peak-peak - amplitude accuracy is poor (signal very small?)' % pp)
        if clipped:
            print('  warning: scope input clipped - result invalid')
        records, v2 = [codes], []
        for i in range(cfg.SCOPE_NACQ):
            if i:
                for _retry in range(3):
                    codes, vdiv_rb, ofst, dt = sc.Acquire(cfg.SCOPE_CH)
                    if len(codes) > 0:
                        break
                    print('  warning: scope returned empty waveform, retrying...  scope state: %s' % sc.Diagnose(cfg.SCOPE_CH))
                if len(codes) == 0:
                    raise RuntimeError('Scope returned empty waveform on record %d at %.0f Hz' % (i, freq))
                records.append(codes)
            volt = codes.astype(float) * vdiv_rb / 25.0 - ofst
            sp = tone_spectrum(volt, dt, freq)
            v2.append(sp['vpk'] ** 2)
        p_dbm = float(10 * np.log10(np.mean(v2) / (2 * 50.0) * 1e3))
        if abs(sp['f_peak'] - freq) > max(3 * sp['df'], 0.02 * freq):
            print('  warning: spectral peak at %.1f Hz, expected %.1f Hz' % (sp['f_peak'], freq))
        band = sp['f'] <= 20 * freq                          # spectrum of the last record up to 20 x f0
        self.last_snr = sp['snr_db']
        return {'p_dbm': p_dbm, 'snr_db': sp['snr_db'], 'records': records, 'vdiv': vdiv_rb, 'ofst': ofst, 'dt': dt,
                'tdiv': info['tdiv'], 'sample_rate': info['sample_rate_Sa_s'], 'pp_codes': pp, 'clipped': clipped,
                'f_peak': sp['f_peak'], 'h2_dbc': sp['h2_dbc'], 'h3_dbc': sp['h3_dbc'],
                'spec_f': sp['f'][band].astype(np.float32),
                'spec_dbm': sp['dbm'][band].astype(np.float32)}

    def read_point_esa(self, freq):
        span, rbw = esa_settings(freq)
        self.recv.SetSpectrumParameters(spanFreq=span, centerFreq=freq / 1e6, videoBW=rbw,
                                        resolutionBW=rbw, dataPointsInSweep=1001)
        p = self.recv.ReadPeakPower(Nread=self.cfg.ESA_NREAD)
        trace = np.asarray(getattr(self.recv, 'last_trace', []), float)
        span_hz, rbw_hz = span * 1e6, rbw * 1e6
        self.last_snr = np.nan
        return {'p_dbm': float(p), 'snr_db': np.nan, 'trace_dbm': trace,
                'trace_f': np.linspace(freq - span_hz / 2, freq + span_hz / 2, len(trace)) if len(trace) else trace,
                'center_hz': freq, 'span_hz': span_hz, 'rbw_hz': rbw_hz}

    def read_point(self, freq, vpp):
        return self.read_point_scope(freq, vpp) if self.is_scope else self.read_point_esa(freq)

    # ---- screenshots ------------------------------------------------------------
    def screenshot(self, tag):
        """PNG screenshot of the receiver in the run folder. Never aborts the measurement."""
        if not (self.screenshots_ok and self.run_folder):
            return None
        shot_dir = os.path.join(self.run_folder, self.base_name + '_screenshots')
        os.makedirs(shot_dir, exist_ok=True)
        path = os.path.join(shot_dir, '%s_%s.png' % (safe_name(tag), self.kind))
        try:
            save_screenshot_png(self.recv, path)
        except Exception as e:
            print('  warning: screenshot failed (%s) - no more screenshots in this run.' % e)
            self.screenshots_ok = False
            try:
                self.recv.instr.clear()
            except Exception:
                pass
            return None
        self.stage_screenshots.append((tag, path))
        return path

    def want_screenshot(self, freq):
        return any(abs(freq - f) <= 1e-6 * f for f in self.cfg.SCREENSHOT_FREQS_HZ)

    # ---- short-circuit protection of the bias tee DC port ----------------------------
    def keithley_guard(self, offset):
        """Before any signal is switched on: Keithley must be 0 A / Hi-Z, and its voltage limit must be above the DC at the tee
        (the 2450 manual: an external voltage above the limit makes the 2450 draw excessive current)."""
        self.keithley.AssertHighZ()
        vlim = float(self.keithley.instr.query(':SOUR:CURR:VLIM?'))
        need = 1.2 * abs(self.cfg.DC_AT_TEE_FACTOR * offset) + 1.0
        if vlim < need:
            raise RuntimeError('Keithley voltage limit is %.1f V but the DC at the bias tee will be %.1f V (need > %.1f V).'
                               % (vlim, self.cfg.DC_AT_TEE_FACTOR * offset, need))

    def dc_precheck(self, f, vpp, offset):
        """Apply only DC_PRECHECK_OFFSET_V first and check that the Keithley sees 2x that. Even into a dead short this draws at
        most 2*offset/50 ohm (= 4 mA for 0.1 V, below the 9 mA inductor rating) - then the real DC level is applied."""
        cfg = self.cfg
        pre = float(np.copysign(min(cfg.DC_PRECHECK_OFFSET_V, abs(offset)), offset))
        self.set_tone(f, vpp, pre)
        self.afg.output_status(channel=cfg.AFG_CH, status='ON')
        time.sleep(cfg.SETTLE_S)
        v = self.read_dc()
        exp = cfg.DC_AT_TEE_FACTOR * pre
        if not (cfg.DC_ABORT_LOW_FRAC * abs(exp) <= v * np.sign(exp) <= cfg.DC_ABORT_HIGH_FRAC * abs(exp)):
            raise RuntimeError(
                'DC pre-check FAILED: Keithley reads %.3f V, expected ~%.3f V at only %.2f V SDG offset (short-circuit current '
                'would be <= %.1f mA). Keithley not connected / wrong terminals / short or wrong load on the DC port? '
                'Output switched off, the real DC level was NOT applied.'
                % (v, exp, pre, 1e3 * cfg.DC_AT_TEE_FACTOR * abs(pre) / (50.0 + cfg.DC_PORT_SERIES_R_OHM)))
        print('  DC pre-check OK: Keithley %.3f V at %.2f V offset (expected %.3f V) -> applying %.2f V' % (v, pre, exp, offset))
        self.set_tone(f, vpp, offset)

    # ---- one sweep ---------------------------------------------------------------
    def sweep(self, label, offset=0.0, vpp=None, monitor_dc=False):
        cfg = self.cfg
        vpp = cfg.VPP if vpp is None else vpp
        key = safe_name(label)
        while key in self.used_keys:
            key += '_'
        self.used_keys.add(key)
        freqs = np.array(cfg.FREQUENCIES_HZ, float)
        nan = np.full(len(freqs), np.nan)
        res = {'label': label, 'key': key, 'offset': offset, 'vpp': vpp, 'coupling': self.rx_coupling,
               'freq': freqs, 'p_dbm': nan.copy(), 'v_dc': nan.copy(), 'snr_db': nan.copy(),
               'h2_dbc': nan.copy(), 'h3_dbc': nan.copy(), 'afg_readback': [None] * len(freqs),
               'points': [None] * len(freqs), 'screenshots': [], 't_start': datetime.now().isoformat()}
        fmin = MIN_FREQ_HZ[self.kind]
        self.afg_output_off()
        try:
            first = True
            for i, f in enumerate(freqs):
                if f < fmin:
                    print('  [%s] %10.0f Hz  skipped (minimum %g Hz)' % (label, f, fmin))
                    continue
                self.set_tone(f, vpp, offset)                        # configure (output still OFF on the first point)
                if first:
                    res['settings'] = self.settings_snapshot()      # all instrument settings, output still OFF
                    if monitor_dc:
                        self.keithley_guard(offset)                 # never switch the signal on without the Hi-Z monitor
                    if monitor_dc and abs(offset) > cfg.DC_PRECHECK_OFFSET_V:
                        self.dc_precheck(f, vpp, offset)            # low-DC test first; ends with the output ON at `offset`
                    else:
                        self.afg.output_status(channel=cfg.AFG_CH, status='ON')
                    first = False
                res['afg_readback'][i] = self.last_afg_readback
                time.sleep(cfg.SETTLE_S)
                msg = ''
                if monitor_dc:
                    v = self.read_dc()
                    res['v_dc'][i] = v
                    exp = cfg.DC_AT_TEE_FACTOR * offset
                    if abs(exp) > 0 and not (cfg.DC_ABORT_LOW_FRAC * abs(exp) <= v * np.sign(exp) <= cfg.DC_ABORT_HIGH_FRAC * abs(exp)):
                        raise RuntimeError(
                            'DC monitor reads %.3f V but ~%.3f V is expected (offset %.2f V). Keithley not connected to the '
                            'bias tee DC port / wrong (front vs rear) terminals / wrong SDG load setting? Output switched off.'
                            % (v, exp, offset))
                    flag = ''
                    if abs(v - exp) > max(cfg.DC_TOL_ABS_V, cfg.DC_TOL_FRAC * abs(exp)):
                        flag = '  <-- differs from expected %.3f V' % exp
                    msg = '  Vdc = %8.4f V%s' % (v, flag)
                pt = self.read_point(f, vpp)
                pt['v_dc'] = res['v_dc'][i]
                res['points'][i] = pt
                res['p_dbm'][i] = pt['p_dbm']
                res['snr_db'][i] = pt['snr_db']
                res['h2_dbc'][i] = pt.get('h2_dbc', np.nan)
                res['h3_dbc'][i] = pt.get('h3_dbc', np.nan)
                snr = ('  SNR %.0f dB  H2 %.0f dBc  H3 %.0f dBc' % (pt['snr_db'], pt['h2_dbc'], pt['h3_dbc'])) if self.is_scope else ''
                print('  [%s] %10.0f Hz  P = %8.2f dBm (exp. %.2f)%s%s' % (label, f, pt['p_dbm'], expected_dbm(vpp), snr, msg))
                if self.want_screenshot(f):
                    n_before = len(self.stage_screenshots)
                    self.screenshot('%s_%.0fHz' % (key, f))
                    if len(self.stage_screenshots) > n_before:
                        res['screenshots'].append({'tag': self.stage_screenshots[-1][0],
                                                   'path': self.stage_screenshots[-1][1], 'index': i})
        finally:
            self.afg_output_off()
            res['t_end'] = datetime.now().isoformat()
            self.stage_sweeps.append(res)
        return res

    def close(self):
        for fn in (lambda: self.afg_output_off(),
                   lambda: self.afg.instr.write('C%d:BSWV OFST,+0' % self.cfg.AFG_CH),
                   lambda: self.keithley and self.keithley.SwitchOff(),
                   lambda: self.keithley and self.keithley.CloseConnection(),
                   lambda: self.afg.CloseConnection(),
                   lambda: (self.recv.closeConnection() if self.is_scope else self.recv.CloseConnection())):
            try:
                fn()
            except Exception as e:      # keep cleaning up
                print('cleanup warning:', e)
        self.tee.close()


# =============================================================================
# Stages
# =============================================================================

def short_current_mA(cfg, offset):
    """Worst case current into a dead short on the DC port: 2*offset (open-circuit) behind 50 ohm (+ series resistor)."""
    return 1e3 * cfg.DC_AT_TEE_FACTOR * abs(offset) / (50.0 + cfg.DC_PORT_SERIES_R_OHM)


def short_warning(cfg, levels):
    worst = max(short_current_mA(cfg, lvl) for lvl in list(levels) + [0])
    if worst > 1e3 * cfg.INDUCTOR_MAX_A:
        return ('  WARNING: a short on the DC port would draw up to %.0f mA at the highest DC level (inductor rating %.0f mA, '
                'series resistor %g ohm).\n  A 100 kohm resistor in series with the Keithley input removes this risk '
                '(see README). The script applies a low-DC pre-check first.\n' % (worst, 1e3 * cfg.INDUCTOR_MAX_A,
                                                                                   cfg.DC_PORT_SERIES_R_OHM))
    return ''


def tee_wiring_text(cfg, rx_text, dc_levels=(0,)):
    return ('  SDG CH%d (50 ohm mode)  ->  bias tee  AC+DC input\n' % cfg.AFG_CH +
            '  bias tee  AC output  ->  EF500 DC block  ->  ' + rx_text + ' (AC-coupled)\n'
            '  bias tee  DC output  ->  Keithley 2450 FRONT-panel HI / LO terminals  (HIGH-Z voltmeter, 0 A source, 2-wire;\n'
            '                           the script resets the 2450 to the FRONT terminals - use those)\n'
            + ('  (series resistor in the DC line: %g ohm, close to the bias tee connector)\n' % cfg.DC_PORT_SERIES_R_OHM
               if cfg.DC_PORT_SERIES_R_OHM > 0 else '') +
            '  Do NOT connect anything else to the DC port.\n' + short_warning(cfg, dc_levels))


def tee_isolation_wiring_text(cfg, rx_text, dc_levels=(0,)):
    """Wiring text for scope-only bias tee isolation sweeps (no EF500, scope DC-coupled)."""
    return ('  Remove the EF500 DC block.\n'
            '  SDG CH%d (50 ohm mode)  ->  bias tee  AC+DC input\n' % cfg.AFG_CH +
            '  bias tee  AC output  ->  ' + rx_text + ' (DC-coupled, NO EF500)\n'
            '  bias tee  DC output  ->  Keithley 2450  (unchanged)\n'
            + ('  (series resistor in the DC line: %g ohm, close to the bias tee connector)\n' % cfg.DC_PORT_SERIES_R_OHM
               if cfg.DC_PORT_SERIES_R_OHM > 0 else '') +
            '  Do NOT connect anything else to the DC port.\n'
            '  NOTE: the scope will see any DC leakage through the bias tee AC path; this is what we are measuring.\n'
            + short_warning(cfg, dc_levels))


_live_figs = {}   # stage title -> figure number


def _plot_live(cfg, sweeps, title):
    """Non-blocking power-vs-frequency window that updates after each sweep completes."""
    try:
        fig_num = abs(hash(title)) % 9000 + 1000   # stable figure number per stage title
        if fig_num not in _live_figs or not plt.fignum_exists(fig_num):
            fig = plt.figure(fig_num, figsize=(9, 4))
            _live_figs[fig_num] = fig
        else:
            fig = _live_figs[fig_num]
            fig.clf()
        ax = fig.add_subplot(1, 1, 1)
        ax.set_facecolor(SURFACE)
        for i, r in enumerate(sweeps):
            c = CATEGORICAL[i % len(CATEGORICAL)]
            m = MARKERS[i % len(MARKERS)]
            ls = '--' if r.get('isolated') else '-'
            ax.plot(r['freq'], r['p_dbm'], ls, color=c, marker=m, ms=4, lw=1.4, label=r['label'])
        ax.axhline(expected_dbm(cfg.VPP), color=MUTED, ls=':', lw=1.0,
                   label='ideal (%.2f dBm)' % expected_dbm(cfg.VPP))
        ax.set_xscale('log')
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Tone power (dBm)')
        ax.set_title(title + '  [live — updates after each sweep]', color=INK, fontsize=10)
        ax.legend(fontsize=8, frameon=False, labelcolor=INK2)
        _style_axes(ax)
        fig.tight_layout()
        fig.canvas.draw_idle()
        plt.pause(0.05)
    except Exception:
        pass   # never break the measurement for a plot problem


def stage1(S):
    """DC block only: direct, with EF500, with EF500 and AC-coupled receiver.

    Sweep C (AC-coupled) always runs for the scope (needed as the stage 2 receiver baseline).
    For ESA receivers it runs only when STAGE1_ALSO_AC_COUPLED is True.
    """
    cfg = S.cfg
    S.set_rx_coupling('DC')
    _title1 = 'Stage 1: DC block (EF500)'
    ask('STAGE 1-A (reference)\n  SDG CH%d  ->  %s  (direct, SMA/adapters only, NO DC block)\n'
        '  Receiver is DC-coupled: signal is pure AC (offset 0 V, verified by read-back).' % (cfg.AFG_CH, S.rx_text))
    A = S.sweep('direct')
    _plot_live(cfg, [A], _title1)
    ask('STAGE 1-B\n  SDG CH%d  ->  Thorlabs EF500 DC block  ->  %s' % (cfg.AFG_CH, S.rx_text))
    B = S.sweep('with DC block')
    sweeps, pairs = [A, B], [(B['key'], A['key'])]
    _plot_live(cfg, sweeps, _title1)
    if S.is_scope or cfg.STAGE1_ALSO_AC_COUPLED:
        S.set_rx_coupling('AC')
        ask('STAGE 1-C%s\n  Keep SDG -> EF500 -> receiver.  Receiver is now AC-coupled (pure AC, still safe).'
            % ('' if S.is_scope else ' (optional)'))
        C = S.sweep('block, AC-coupled')
        sweeps.append(C)
        pairs.append((C['key'], A['key']))
        _plot_live(cfg, sweeps, _title1)
    return {'stage': 1, 'title': 'Stage 1: DC block (EF500)', 'sweeps': sweeps, 'pairs': pairs,
            'monitor_dc': False, 'color_mode': 'categorical',
            'what': 'DC block insertion loss (relative to direct)'}


def stage2(S):
    """Bias tee with pure AC; reference = DC block only."""
    cfg = S.cfg
    S.set_rx_coupling('AC')
    _title2 = 'Stage 2: bias tee, pure AC'
    ask('STAGE 2-R (reference, no bias tee)\n  SDG CH%d  ->  EF500  ->  %s (AC-coupled)' % (cfg.AFG_CH, S.rx_text))
    R = S.sweep('ref: block only')
    _plot_live(cfg, [R], _title2)
    S.keithley.AssertHighZ()
    ask('STAGE 2-T (bias tee, pure AC)\n' + tee_wiring_text(cfg, S.rx_text))
    T = S.sweep('bias tee, AC only', monitor_dc=True)
    _plot_live(cfg, [R, T], _title2)
    return {'stage': 2, 'title': 'Stage 2: bias tee, pure AC', 'sweeps': [R, T], 'pairs': [(T['key'], R['key'])],
            'monitor_dc': True, 'color_mode': 'categorical',
            'what': 'Bias tee insertion loss (relative to block-only reference)'}


def stage3(S):
    """Bias tee with AC + PD-like DC levels; reference = the 0 V sweep.

    For scope only: also runs isolation sweeps (bias tee AC port direct to scope, no EF500),
    so the bias tee AC-path behaviour is tested both with and without the DC block.
    """
    cfg = S.cfg
    S.set_rx_coupling('AC')
    if S.kind == 'ssa':
        print('NOTE: SSA3021X - make sure its input is AC coupled / rated for the DC block output.')
    ask('STAGE 3 (bias tee, AC + PD-like DC)\n' + tee_wiring_text(cfg, S.rx_text, cfg.PD_DC_LEVELS_V) +
        '\n  Levels (PD output into 50 ohm): %s V -> Keithley should read ~%g x these.'
        % (list(cfg.PD_DC_LEVELS_V), cfg.DC_AT_TEE_FACTOR))
    _title3 = 'Stage 3: bias tee, AC + DC'
    sweeps = []
    for lvl in cfg.PD_DC_LEVELS_V:
        sweeps.append(S.sweep('DC %.2f V (tee %.2f V)' % (lvl, cfg.DC_AT_TEE_FACTOR * lvl),
                              offset=lvl, monitor_dc=True))
        S.afg_output_off()
        _plot_live(cfg, sweeps, _title3)
    base = sweeps[0]
    pairs = [(r['key'], base['key']) for r in sweeps[1:]]

    if S.is_scope:
        # Scope-only: remove EF500, connect bias tee AC out directly to scope (DC-coupled).
        # Measures the true AC-path insertion loss of the bias tee alone.
        S.set_rx_coupling('DC')
        ask('STAGE 3 (bias tee isolation, no EF500)\n'
            + tee_isolation_wiring_text(cfg, S.rx_text, cfg.PD_DC_LEVELS_V)
            + '\n  Levels (PD output into 50 ohm): %s V -> Keithley should read ~%g x these.'
            % (list(cfg.PD_DC_LEVELS_V), cfg.DC_AT_TEE_FACTOR))
        iso_sweeps = []
        for lvl in cfg.PD_DC_LEVELS_V:
            sw = S.sweep('no block, DC %.2f V' % lvl, offset=lvl, monitor_dc=True)
            sw['isolated'] = True
            iso_sweeps.append(sw)
            S.afg_output_off()
            _plot_live(cfg, sweeps + iso_sweeps, _title3)
        iso_base = iso_sweeps[0]
        sweeps.extend(iso_sweeps)
        pairs.extend([(r['key'], iso_base['key']) for r in iso_sweeps[1:]])

    return {'stage': 3, 'title': 'Stage 3: bias tee, AC + DC', 'sweeps': sweeps,
            'pairs': pairs,
            'monitor_dc': True, 'color_mode': 'sequential',
            'what': 'Change of AC response vs the 0 V sweep'}


STAGES = {1: stage1, 2: stage2, 3: stage3}


# =============================================================================
# Summary, csv, plots
# =============================================================================

def sweep_by_key(res):
    return {r['key']: r for r in res['sweeps']}


def summarise(cfg, res):
    """Print + return pass/fail of every (sample - reference) pair."""
    by = sweep_by_key(res)
    out = []
    print('\n' + res['what'] + ':')
    for skey, rkey in res['pairs']:
        s, r = by[skey], by[rkey]
        d = s['p_dbm'] - r['p_dbm']
        fin = np.isfinite(d)
        worst = float(np.nanmax(np.abs(d))) if fin.any() else float('nan')
        ok = bool(fin.any() and worst <= cfg.PASS_TOL_DB)
        below3 = s['freq'][np.where(fin & (d < -3))[0]]
        print('  %-28s worst |dev| = %.2f dB -> %s%s' % (
            s['label'], worst, 'PASS' if ok else 'CHECK',
            ('   (< -3 dB at %s Hz)' % ', '.join('%g' % f for f in below3)) if len(below3) else ''))
        out.append({'sample': skey, 'reference': rkey, 'delta_db': d, 'worst_abs_db': worst, 'passed': ok})
    if res['monitor_dc']:
        print('\nDC level  expected   Keithley (mean over sweep)')
        for r in res['sweeps']:
            if np.isfinite(r['v_dc']).any():
                print('  %5.2f V   %6.2f V   %8.4f V' % (r['offset'], cfg.DC_AT_TEE_FACTOR * r['offset'], np.nanmean(r['v_dc'])))
    return out


def save_csv(cfg, path, res):
    cols = ['freq_Hz']
    for r in res['sweeps']:
        cols += [r['label'] + '_dBm', r['label'] + '_Vdc']
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i, f in enumerate(cfg.FREQUENCIES_HZ):
            row = [f]
            for r in res['sweeps']:
                row += [r['p_dbm'][i], r['v_dc'][i]]
            w.writerow(row)


def _seq_colors(n):
    a = np.array([int(SEQ_LIGHT[i:i + 2], 16) for i in (1, 3, 5)], float)
    b = np.array([int(SEQ_DARK[i:i + 2], 16) for i in (1, 3, 5)], float)
    t = np.linspace(0, 1, max(n, 1))
    return ['#%02x%02x%02x' % tuple(int(round(v)) for v in (a + (b - a) * x)) for x in t]


def _series_styles(res):
    """key -> (colour, marker, linestyle).  Categorical = identity; sequential = DC level (light -> dark).

    In sequential mode, isolation sweeps (sw['isolated'] = True) use the same colour ramp as the
    corresponding EF500 sweeps but with dashed lines so the two groups are visually distinct.
    """
    sty = {}
    if res['color_mode'] == 'sequential':
        refs = {rk for _, rk in res['pairs']}
        samples_block = [r for r in res['sweeps'] if r['key'] not in refs and not r.get('isolated')]
        samples_iso   = [r for r in res['sweeps'] if r['key'] not in refs and r.get('isolated')]
        for r in res['sweeps']:
            if r['key'] in refs:
                sty[r['key']] = (INK2, 'o', ':' if r.get('isolated') else '--')
        for r, c, m in zip(samples_block, _seq_colors(len(samples_block)), MARKERS * 2):
            sty[r['key']] = (c, m, '-')
        for r, c, m in zip(samples_iso, _seq_colors(len(samples_iso)), MARKERS * 2):
            sty[r['key']] = (c, m, '--')
    else:
        for i, r in enumerate(res['sweeps']):
            sty[r['key']] = (CATEGORICAL[i % len(CATEGORICAL)], MARKERS[i % len(MARKERS)], '-')
    return sty


def _style_axes(ax):
    ax.set_facecolor(SURFACE)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    for sp in ('left', 'bottom'):
        ax.spines[sp].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelcolor=INK2, labelsize=9)
    ax.grid(True, which='both', color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK2)
    ax.yaxis.label.set_color(INK2)


def make_report(cfg, res, base_path, show=False):
    """Absolute power, change vs reference and (stages 2/3) the Keithley DC reading. Saved as PDF and SVG."""
    by = sweep_by_key(res)
    sty = _series_styles(res)
    scope = cfg.MEASUREMENT == 'scope'
    n = (3 if res['monitor_dc'] else 2) + (2 if scope else 0)
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, axes = plt.subplots(n, 1, figsize=(8.5, (2.9 if n > 3 else 3.3) * n + 0.6), sharex=True)
        fig.patch.set_facecolor(SURFACE)
        ax1, ax2 = axes[0], axes[1]
        for r in res['sweeps']:
            c, m, ls = sty[r['key']]
            ax1.plot(r['freq'], r['p_dbm'], ls, color=c, marker=m, ms=5, lw=1.6, label=r['label'])
        ax1.axhline(expected_dbm(cfg.VPP), color=MUTED, ls=':', lw=1.0, label='ideal (%.2f dBm)' % expected_dbm(cfg.VPP))
        ax1.set_ylabel('Tone power at receiver (dBm)')
        ax1.set_title(res['title'] + '   [' + RECEIVER_NAMES[cfg.MEASUREMENT] + ']', loc='left', color=INK, fontsize=11)
        ax1.legend(fontsize=8, frameon=False, labelcolor=INK2, ncol=2 if len(res['sweeps']) > 4 else 1)
        ref_labels = set()
        for skey, rkey in res['pairs']:
            s, r = by[skey], by[rkey]
            c, m, ls = sty[skey]
            ax2.plot(s['freq'], s['p_dbm'] - r['p_dbm'], ls, color=c, marker=m, ms=5, lw=1.6,
                     label='%s - %s' % (s['label'], r['label']))
            ref_labels.add(r['label'])
        ax2.axhspan(-cfg.PASS_TOL_DB, cfg.PASS_TOL_DB, color=GRID, alpha=0.7, lw=0)
        ax2.axhline(0, color=AXIS, lw=0.8)
        ax2.set_ylabel('Change vs reference (dB)\n(reference: %s)' % ' / '.join(sorted(ref_labels)))
        ax2.legend(fontsize=8, frameon=False, labelcolor=INK2, ncol=1 if len(res['pairs']) <= 4 else 2)
        if res['monitor_dc']:
            ax3 = axes[2]
            for r in res['sweeps']:
                if not np.isfinite(r['v_dc']).any():
                    continue
                c, m, ls = sty[r['key']]
                ax3.plot(r['freq'], r['v_dc'], ls, color=c, marker=m, ms=5, lw=1.6, label=r['label'])
                ax3.axhline(cfg.DC_AT_TEE_FACTOR * r['offset'], color=c, ls=':', lw=0.9)
            ax3.set_ylabel('Keithley DC voltage (V)\n(dotted: %g x SDG offset)' % cfg.DC_AT_TEE_FACTOR)
            ax3.legend(fontsize=8, frameon=False, labelcolor=INK2, ncol=2 if len(res['sweeps']) > 4 else 1)
        if scope:                                    # harmonic distortion from the scope FFT (floor: 8-bit ADC)
            for ax, key, name in ((axes[-2], 'h2_dbc', 'Second'), (axes[-1], 'h3_dbc', 'Third')):
                for r in res['sweeps']:
                    if not np.isfinite(r[key]).any():
                        continue
                    c, m, ls = sty[r['key']]
                    ax.plot(r['freq'], r[key], ls, color=c, marker=m, ms=5, lw=1.6, label=r['label'])
                ax.set_ylabel('%s harmonic (dBc)\n(floor = scope noise)' % name)      # same colours as the legend above
        for ax in axes:
            ax.set_xscale('log')
            _style_axes(ax)
        axes[-1].set_xlabel('Frequency (Hz)')
        fig.tight_layout()
        for ext in ('pdf', 'svg'):
            p = '%s.%s' % (base_path, ext)
            fig.savefig(p, bbox_inches='tight', facecolor=fig.get_facecolor())
            print('  Saved: %s' % p)
        if show:
            plt.show()
        else:
            plt.close(fig)


def _spectra_freqs(cfg, res):
    want = getattr(cfg, 'SPECTRA_FREQS_HZ', cfg.SCREENSHOT_FREQS_HZ)
    out = []
    for f in want:
        idx = [i for i, ff in enumerate(cfg.FREQUENCIES_HZ) if abs(ff - f) <= 1e-6 * f and any(r['points'][i] is not None for r in res['sweeps'])]
        if idx:
            out.append(idx[0])
    return out


def _hz_unit(x):
    x = abs(x)
    return (1e6, 'MHz') if x >= 1e6 else (1e3, 'kHz') if x >= 1e3 else (1.0, 'Hz')


def make_spectra_report(cfg, res, base_path, show=False):
    """Spectrum of every sweep at SPECTRA_FREQS_HZ (scope: also the time-domain signal). Saved as PDF and SVG."""
    rows = _spectra_freqs(cfg, res)
    if not rows:
        return
    scope = cfg.MEASUREMENT == 'scope'
    sty = _series_styles(res)
    ncol = 2 if scope else 1
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, axes = plt.subplots(len(rows), ncol, figsize=(5.2 * ncol + 1.2, 3.0 * len(rows) + 0.7), squeeze=False)
        fig.patch.set_facecolor(SURFACE)
        for ri, i in enumerate(rows):
            f0 = float(cfg.FREQUENCIES_HZ[i])
            scale, unit = _hz_unit(f0)
            for r in res['sweeps']:
                pt = r['points'][i]
                if pt is None:
                    continue
                c, m, ls = sty[r['key']]
                if scope:
                    v = pt['records'][0].astype(float) * pt['vdiv'] / 25.0 - pt['ofst']
                    t = np.arange(len(v)) * pt['dt']
                    k = min(len(v), int(round(3.0 / f0 / pt['dt'])))      # first 3 periods
                    axes[ri, 0].plot(t[:k] * 1e6, v[:k], color=c, lw=1.0, label=r['label'])
                    axes[ri, 1].plot(pt['spec_f'] / scale, pt['spec_dbm'], color=c, lw=1.0, label=r['label'])
                else:
                    axes[ri, 0].plot((pt['trace_f'] - pt['center_hz']) / 1e3, pt['trace_dbm'], color=c, lw=1.0, label=r['label'])
            ax_t = axes[ri, 0]
            if scope:
                ax_t.set_xlabel('Time (\u00b5s)')
                ax_t.set_ylabel('Scope voltage (V)\n(f = %g %s)' % (f0 / scale, unit))
                ax_s = axes[ri, 1]
                ax_s.set_xscale('log')
                ax_s.set_xlim(f0 / scale / 20, 20 * f0 / scale)
                ax_s.set_xlabel('Frequency (%s)' % unit)
                ax_s.set_ylabel('Spectrum (dBm into 50 \u03a9)')
                ax_s.set_ylim(-120, 10)
                _style_axes(ax_s)
            else:
                ax_t.set_xlabel('Offset from %g %s (kHz)' % (f0 / scale, unit))
                ax_t.set_ylabel('ESA trace (dBm)\n(f = %g %s)' % (f0 / scale, unit))
            _style_axes(ax_t)
        h, l = axes[0, ncol - 1].get_legend_handles_labels()
        fig.suptitle(res['title'] + ' \u2013 spectra   [' + RECEIVER_NAMES[cfg.MEASUREMENT] + ']', x=0.01, ha='left', color=INK, fontsize=11)
        fig.tight_layout(rect=(0, 0.05, 1, 0.97))
        fig.legend(h, l, loc='lower center', ncol=min(len(l), 3), fontsize=8, frameon=False, labelcolor=INK2)
        for ext in ('pdf', 'svg'):
            pth = '%s.%s' % (base_path, ext)
            fig.savefig(pth, bbox_inches='tight', facecolor=fig.get_facecolor())
            print('  Saved: %s' % pth)
        if show:
            plt.show()
        else:
            plt.close(fig)


def make_fft_check_report(cfg, res, base_path, show=False, max_rows=6):
    """Scope screenshot (with the scope's own on-screen FFT, if enabled) next to our FFT of the same record."""
    if cfg.MEASUREMENT != 'scope':
        return
    from PIL import Image
    entries = []
    for r in res['sweeps']:
        for sh in r['screenshots']:
            if r['points'][sh['index']] is not None and os.path.exists(sh['path']):
                entries.append((r, sh))
    if not entries:
        return
    if len(entries) > max_rows:
        entries = [entries[j] for j in np.unique(np.linspace(0, len(entries) - 1, max_rows).round().astype(int))]
    sty = _series_styles(res)
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, axes = plt.subplots(len(entries), 2, figsize=(11.5, 3.4 * len(entries) + 0.8), squeeze=False,
                                 gridspec_kw={'width_ratios': [1.15, 1]})
        fig.patch.set_facecolor(SURFACE)
        for ri, (r, sh) in enumerate(entries):
            i = sh['index']
            pt, f0 = r['points'][i], r['freq'][i]
            scale, unit = _hz_unit(f0)
            axi, axs = axes[ri, 0], axes[ri, 1]
            axi.imshow(np.asarray(Image.open(sh['path']).convert('RGB')))
            axi.axis('off')
            axi.set_title('Scope screenshot: %s, %g %s' % (r['label'], f0 / scale, unit), loc='left', color=INK, fontsize=9)
            c, m, ls = sty[r['key']]
            axs.plot(pt['spec_f'] / scale, pt['spec_dbm'], color=c, lw=1.1)
            axs.set_xlim(0, 4.5 * f0 / scale)
            axs.set_ylim(-110, 10)
            axs.set_xlabel('Frequency (%s)' % unit)
            axs.set_ylabel('Our FFT (dBm into 50 \u03a9)')
            _style_axes(axs)
            dbvrms = pt['p_dbm'] - 10 * np.log10(1e3 / 50.0)             # dBm into 50 ohm -> dBV(rms)
            axs.text(0.98, 0.97, 'tone %.3f %s\nP = %.2f dBm  =  %.2f dBVrms\nH2 %.0f dBc, H3 %.0f dBc\n'
                     '%d samples, dt = %.3g s\nflat-top window, mean of %d records' %
                     (pt['f_peak'] / scale, unit, pt['p_dbm'], dbvrms, pt['h2_dbc'], pt['h3_dbc'],
                      pt['records'][0].size, pt['dt'], len(pt['records'])),
                     transform=axs.transAxes, ha='right', va='top', fontsize=8, color=INK2,
                     bbox=dict(boxstyle='round,pad=0.4', fc=SURFACE, ec=AXIS, lw=0.6))
        fig.suptitle(res['title'] + ' \u2013 scope FFT screenshot vs our FFT of the same record\n'
                     '(enable Math \u2192 FFT, Flat Top window, on the scope screen to see its own FFT in the screenshot)',
                     x=0.01, ha='left', color=INK, fontsize=10)
        fig.tight_layout()
        for ext in ('pdf', 'svg'):
            pth = '%s.%s' % (base_path, ext)
            fig.savefig(pth, bbox_inches='tight', facecolor=fig.get_facecolor())
            print('  Saved: %s' % pth)
        if show:
            plt.show()
        else:
            plt.close(fig)


# =============================================================================
# HDF5
# =============================================================================

def _attr(val):
    """h5py-safe attribute value (None -> 'None', dict/other -> json)."""
    if val is None:
        return 'None'
    if isinstance(val, np.generic):
        return val.item()
    if isinstance(val, (bool, int, float, str, np.ndarray)):
        return val
    if isinstance(val, (list, tuple)) and all(isinstance(x, (int, float)) for x in val):
        return np.asarray(val, float)
    return json.dumps(val, default=str)


def _write_settings(group, snaps, flat=False):
    """{phase: {instrument: {query: reply}}} -> group/<phase>/<instrument> with one attribute per query."""
    for phase, snap in snaps.items():
        base = group if flat else group.create_group(phase)
        base.attrs['time'] = snap.get('time', '')
        for inst, d in snap.items():
            if isinstance(d, dict):
                g = base.create_group(inst)
                for cmd, reply in d.items():
                    g.attrs[cmd] = reply


def _write_analysis(g, cfg):
    g.attrs['tone_power'] = ('P[dBm] = 10 log10( Vpk^2 / (2 * 50 ohm) * 1e3 ), Vpk = flat-top-windowed single-sided FFT peak '
                             'of the mean-removed record (window amplitude-normalised by sum(w))')
    g.attrs['scope_volt'] = 'volt = adc_code * vdiv / 25 - offset   (int8 codes, 25 codes per division)'
    g.attrs['window'] = '5-term flat-top, coefficients 0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368'
    g.attrs['load_ohm'] = 50.0
    g.attrs['averaging'] = 'power average over SCOPE_NACQ records (mean of Vpk^2)'
    g.attrs['snr'] = 'tone power minus median spectral amplitude more than 12 bins away (last record)'
    g.attrs['harmonics'] = 'H2/H3: largest bin within +-1% (>= 6 bins) of 2*f_peak / 3*f_peak, relative to the tone, last record'
    g.attrs['peak_search'] = 'bin of maximum amplitude within +-max(5% of f_set, 8 bins) of the set frequency'
    g.attrs['dBVrms'] = 'dBVrms = dBm(50 ohm) - 10 log10(1e3/50) = dBm - 13.01'
    g.attrs['esa_span_rule'] = 'span = max(0.2 f, 200 Hz); RBW = VBW = max(0.01 f, 10 Hz); 1001 points'
    g.attrs['scope_timebase_rule'] = 'tdiv = nearest(SCOPE_NCYC / f / 14); vertical auto-scaled to SCOPE_PP_CODES'
    g.attrs['expected_dbm_ideal'] = float(expected_dbm(cfg.VPP))
    g.attrs['load_model'] = (
        'SDG: output impedance 50 ohm, load setting forced to 50 (read back every point) -> typed Vpp/offset = what a 50 ohm load '
        'sees. AC path: SDG(50) -> [tee] -> EF500 -> receiver (50 ohm ESA, or scope 1 Mohm + 50 ohm feed-through) -> '
        'amplitude at the receiver = typed Vpp. DC path: bias tee DC port -> Keithley 2450 as 0 A source / voltmeter (>10 Gohm, '
        'datasheet), output-off state HIGH-Z, Vlim 20 V -> no DC current, DC at the tee = open-circuit voltage = '
        'DC_AT_TEE_FACTOR (2) x typed offset (the DC block in front of the receiver must stop DC; a PD has the same 50 ohm series '
        'resistor: 0-5 V into 50 ohm = 0-10 V into Hi-Z). Receiver load errors cancel in the sample-minus-reference plots. '
        'See Bias_tee/README.md.')


def _write_provenance(hf):
    import platform
    import hashlib
    import subprocess
    env = hf.create_group('environment')
    env.attrs['python'] = sys.version
    env.attrs['platform'] = platform.platform()
    env.attrs['hostname'] = platform.node()
    for mod in ('numpy', 'h5py', 'matplotlib', 'pyvisa'):
        try:
            env.attrs[mod] = sys.modules[mod].__version__
        except Exception:
            pass
    try:
        from PIL import Image          # noqa: F401
        import PIL
        env.attrs['pillow'] = PIL.__version__
    except Exception:
        pass
    try:
        kw = dict(cwd=_here, capture_output=True, text=True, timeout=5)
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], **kw)
        dirty = subprocess.run(['git', 'status', '--porcelain'], **kw)
        if head.returncode == 0:
            env.attrs['git_commit'] = head.stdout.strip()
            env.attrs['git_dirty'] = bool(dirty.stdout.strip())
    except Exception:
        pass
    sg = hf.create_group('script')
    for name, path in (('bias_tee_characterization.py', os.path.join(_here, 'bias_tee_characterization.py')),
                       ('bias_tee_utils.py', os.path.abspath(__file__)),
                       ('Lab_control.py', os.path.abspath(pic.__file__))):
        try:
            data = open(path, 'rb').read()
        except Exception as e:
            sg.attrs[name + '_error'] = str(e)
            continue
        ds = sg.create_dataset(name, data=np.frombuffer(data, np.uint8), compression='gzip', compression_opts=9)
        ds.attrs['sha256'] = hashlib.sha256(data).hexdigest()
        ds.attrs['bytes'] = len(data)
        ds.attrs['path'] = path


def extract_script(h5_path, name, out_path=None):
    """Source file stored in the h5 file (name: 'bias_tee_utils.py', ...) -> text (and written to out_path if given)."""
    with h5py.File(h5_path, 'r') as hf:
        data = bytes(hf['script'][name][()])
    if out_path:
        with open(out_path, 'wb') as f:
            f.write(data)
    return data.decode('utf-8')


def write_stage_h5(path, cfg, S, label, res, comparisons):
    """One HDF5 file per stage run.

    /                      attrs: timestamp, label, stage, receiver, instrument IDNs
    /config                attrs: every UPPER_CASE setting of the runner (+ attr config_json: all of them as one json text)
    /settings/<phase>/<instrument>   what the instruments reported back (queries) at stage start and stage end
    /sweeps/<key>/settings/<instrument>   same, read just before that sweep's output was switched on
    /analysis              attrs: how tone power / SNR / harmonics are computed (window, load, formulas)
    /environment           attrs: python / package versions, platform, git commit (if any)
    /script/<file>         the exact source of bias_tee_characterization.py, bias_tee_utils.py and Lab_control.py
                           (uint8, gzip; read back with extract_script())
    /log                   datasets console_log (everything printed during this stage) and prompts (re-wiring steps)
    /sweeps/<key>          attrs (label, offset, vpp, receiver coupling, ...), datasets frequency_Hz, p_dbm, v_dc_V, snr_dB,
                           h2_dBc, h3_dBc (scope only), afg_readback (SDG BSWV?/OUTP? reply of every point)
    /sweeps/<key>/points/fNN   scope: adc_codes_<j> (int8 records), spectrum_f_Hz, spectrum_dBm
                               ESA:   trace_f_Hz, trace_dBm
    /comparisons/<key>     delta_dB of that sweep vs its reference (attrs: reference, worst_abs_dB, passed)
    /screenshots/<tag>     RGB image (uint8), attrs: filename
    A scope record is converted back with  volt = code * volt_per_code_V - volt_offset_V   (see load_scope_record).
    """
    ckw = dict(compression='gzip', compression_opts=6, shuffle=True)
    with h5py.File(path, 'w') as hf:
        hf.attrs['label'] = label
        hf.attrs['stage'] = res['stage']
        hf.attrs['title'] = res['title']
        hf.attrs['receiver'] = cfg.MEASUREMENT
        hf.attrs['receiver_idn'] = S.recv_idn
        hf.attrs['afg_idn'] = S.afg_idn
        hf.attrs['keithley_idn'] = S.keithley_idn
        hf.attrs['created'] = datetime.now().isoformat()
        hf.attrs['script'] = 'bias_tee_characterization.py / bias_tee_utils.py'
        cg = hf.create_group('config')
        for k, v in vars(cfg).items():
            cg.attrs[k] = _attr(v)
        cg.attrs['config_json'] = json.dumps(vars(cfg), default=str, indent=1, sort_keys=True)
        cg.attrs['keithley_setup'] = json.dumps(S.keithley_setup, default=str)
        cg.attrs['dc_convention'] = ('Keithley DC at the bias tee = DC_AT_TEE_FACTOR x SDG offset (SDG in 50 ohm load mode, '
                                     'DC path unterminated)')
        _write_settings(hf.create_group('settings'), S.stage_settings)
        _write_analysis(hf.create_group('analysis'), cfg)
        _write_provenance(hf)
        lg = hf.create_group('log')
        lg.create_dataset('console_log', data='\n'.join(S.tee.lines[S.log_idx:]), dtype=h5py.string_dtype('utf-8'))
        lg.create_dataset('prompts', data=['[%s] %s' % pr for pr in PROMPT_LOG[S.prompt_idx:]], dtype=h5py.string_dtype('utf-8'))

        sg = hf.create_group('sweeps')
        for r in res['sweeps']:
            g = sg.create_group(r['key'])
            for k, v in (('label', r['label']), ('offset_V', r['offset']), ('vpp_V', r['vpp']),
                         ('expected_tee_dc_V', cfg.DC_AT_TEE_FACTOR * r['offset']),
                         ('receiver_coupling', r['coupling']), ('t_start', r['t_start']), ('t_end', r['t_end']),
                         ('isolated', r.get('isolated', False))):
                g.attrs[k] = _attr(v)
            g.create_dataset('frequency_Hz', data=r['freq'])
            g.create_dataset('p_dbm', data=r['p_dbm'])
            g.create_dataset('v_dc_V', data=r['v_dc'])
            g.create_dataset('snr_dB', data=r['snr_db'])
            if cfg.MEASUREMENT == 'scope':
                g.create_dataset('h2_dBc', data=r['h2_dbc'])
                g.create_dataset('h3_dBc', data=r['h3_dbc'])
            g.create_dataset('afg_readback', data=['%s | %s' % rb if rb else '' for rb in r['afg_readback']],
                             dtype=h5py.string_dtype('utf-8'))
            if 'settings' in r:
                _write_settings(g.create_group('settings'), {'before_sweep': r['settings']}, flat=True)
            pg = g.create_group('points')
            for i, pt in enumerate(r['points']):
                if pt is None:
                    continue
                q = pg.create_group('f%02d' % i)
                q.attrs['f_set_Hz'] = float(r['freq'][i])
                q.attrs['p_dbm'] = pt['p_dbm']
                q.attrs['snr_dB'] = pt['snr_db']
                q.attrs['v_dc_V'] = float(pt['v_dc'])
                if 'records' in pt:                                   # scope
                    for j, rec in enumerate(pt['records']):
                        q.create_dataset('adc_codes_%d' % j, data=np.asarray(rec, np.int8), **ckw)
                    q.attrs['n_records'] = len(pt['records'])
                    q.attrs['n_samples'] = len(pt['records'][0])
                    q.attrs['volt_per_code_V'] = pt['vdiv'] / 25.0
                    q.attrs['volt_offset_V'] = pt['ofst']
                    q.attrs['vdiv_V_per_div'] = pt['vdiv']
                    q.attrs['dt_s'] = pt['dt']
                    q.attrs['sample_rate_Sa_s'] = pt['sample_rate']
                    q.attrs['tdiv_s'] = pt['tdiv']
                    q.attrs['pp_codes'] = pt['pp_codes']
                    q.attrs['clipped'] = pt['clipped']
                    q.attrs['f_peak_Hz'] = pt['f_peak']
                    q.attrs['h2_dBc'] = pt['h2_dbc']
                    q.attrs['h3_dBc'] = pt['h3_dbc']
                    q.create_dataset('spectrum_f_Hz', data=pt['spec_f'], **ckw)
                    q.create_dataset('spectrum_dBm', data=pt['spec_dbm'], **ckw)
                else:                                                 # ESA
                    q.create_dataset('trace_f_Hz', data=pt['trace_f'], **ckw)
                    q.create_dataset('trace_dBm', data=pt['trace_dbm'], **ckw)
                    q.attrs['center_Hz'] = pt['center_hz']
                    q.attrs['span_Hz'] = pt['span_hz']
                    q.attrs['rbw_Hz'] = pt['rbw_hz']

        cg2 = hf.create_group('comparisons')
        for c in comparisons:
            g = cg2.create_group(c['sample'])
            g.create_dataset('delta_dB', data=c['delta_db'])
            g.attrs['reference'] = c['reference']
            g.attrs['worst_abs_dB'] = c['worst_abs_db']
            g.attrs['passed'] = c['passed']
            g.attrs['pass_tolerance_dB'] = cfg.PASS_TOL_DB

        if S.stage_screenshots:
            from PIL import Image
            shg = hf.create_group('screenshots')
            for tag, png in S.stage_screenshots:
                if os.path.exists(png):
                    ds = shg.create_dataset(tag, data=np.asarray(Image.open(png).convert('RGB')),
                                            compression='gzip', compression_opts=4)
                    ds.attrs['filename'] = os.path.basename(png)
                    ds.attrs['CLASS'] = 'IMAGE'
    print('  HDF5 saved: %s' % path)


def make_all_spectra_report(cfg, res, base_path, show=False):
    """All FFT spectra from every scope sweep overlaid on one log-frequency axis.

    Each line is one frequency point from one sweep.  Colour = fundamental frequency (low=light, high=dark).
    Useful for spotting harmonics across all frequencies and sweeps at a glance.
    """
    if cfg.MEASUREMENT != 'scope':
        return
    entries = []   # (f0, sweep_label, spec_f, spec_dbm, isolated)
    for r in res['sweeps']:
        for i, pt in enumerate(r['points']):
            if pt is None or 'spec_f' not in pt:
                continue
            entries.append((r['freq'][i], r['label'], pt['spec_f'], pt['spec_dbm'], r.get('isolated', False)))
    if not entries:
        return
    all_f0 = sorted(set(e[0] for e in entries))
    cmap = plt.cm.plasma
    f_color = {f: cmap(0.1 + 0.8 * i / max(len(all_f0) - 1, 1)) for i, f in enumerate(all_f0)}
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, ax = plt.subplots(figsize=(11, 5))
        fig.patch.set_facecolor(SURFACE)
        seen_f0 = set()
        for f0, sweep_lbl, sf, sd, iso in entries:
            c = f_color[f0]
            ls = '--' if iso else '-'
            scale, unit = _hz_unit(f0)
            lbl = '%.4g %s' % (f0 / scale, unit) if f0 not in seen_f0 else None
            seen_f0.add(f0)
            ax.plot(sf, sd, ls, color=c, lw=0.7, alpha=0.65, label=lbl)
        ax.set_xscale('log')
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Power (dBm into 50 \u03a9)')
        ax.set_ylim(-110, 10)
        ax.set_title(res['title'] + ' \u2013 all FFT spectra overlaid\n'
                     'colour = fundamental frequency (light \u2192 dark = low \u2192 high); '
                     'solid = with EF500, dashed = no EF500', color=INK, fontsize=10)
        ax.legend(fontsize=7, frameon=False, labelcolor=INK2, ncol=4)
        _style_axes(ax)
        fig.tight_layout()
        for ext in ('pdf', 'svg'):
            p = '%s.%s' % (base_path, ext)
            fig.savefig(p, bbox_inches='tight', facecolor=fig.get_facecolor())
            print('  Saved: %s' % p)
        if show:
            plt.show()
        else:
            plt.close(fig)


def make_dc_response_report(cfg, res, base_path, show=False):
    """Stage 3 only: AC power change vs DC bias level for a selection of frequencies.

    Two subplots when isolation sweeps are present (with EF500 / without EF500).
    X-axis: SDG offset (V into 50 Ω).  Y-axis: ΔP vs 0 V sweep (dB).
    """
    if res.get('stage') != 3:
        return
    block_sweeps = [r for r in res['sweeps'] if not r.get('isolated')]
    iso_sweeps   = [r for r in res['sweeps'] if r.get('isolated')]
    if not block_sweeps:
        return

    freqs = np.array(cfg.FREQUENCIES_HZ)
    # Pick a representative subset of frequencies (at most 10, spread across range)
    idx_all = np.where(np.isfinite(block_sweeps[0]['p_dbm']))[0]
    if len(idx_all) == 0:
        return
    step = max(1, len(idx_all) // 10)
    plot_idx = idx_all[::step]
    colors = _seq_colors(len(plot_idx))

    groups = [('with EF500 DC block', block_sweeps)]
    if iso_sweeps:
        groups.append(('no EF500 (isolation)', iso_sweeps))

    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, axes = plt.subplots(len(groups), 1, figsize=(9, 3.8 * len(groups) + 0.8),
                                 sharex=True, squeeze=False)
        fig.patch.set_facecolor(SURFACE)
        for ax, (grp_title, grp_sweeps) in zip(axes[:, 0], groups):
            dc = np.array([r['offset'] for r in grp_sweeps])
            ref_p = grp_sweeps[0]['p_dbm']   # 0 V reference
            for fi, c in zip(plot_idx, colors):
                f0 = freqs[fi]
                scale, unit = _hz_unit(f0)
                delta = np.array([r['p_dbm'][fi] for r in grp_sweeps]) - ref_p[fi]
                ax.plot(dc, delta, '-o', color=c, ms=4, lw=1.4,
                        label='%.4g %s' % (f0 / scale, unit))
            ax.axhline(0, color=AXIS, lw=0.8)
            ax.set_ylabel('\u0394P vs 0 V (dB)\n' + grp_title)
            ax.legend(fontsize=7, frameon=False, labelcolor=INK2, ncol=2)
            _style_axes(ax)
        axes[-1, 0].set_xlabel('SDG DC offset (V into 50 \u03a9)  \u2014  bias tee DC port \u2248 %g\u00d7 (V)'
                               % cfg.DC_AT_TEE_FACTOR)
        fig.suptitle(res['title'] + ' \u2013 AC response vs DC bias level', color=INK, fontsize=11)
        fig.tight_layout()
        for ext in ('pdf', 'svg'):
            p = '%s.%s' % (base_path, ext)
            fig.savefig(p, bbox_inches='tight', facecolor=fig.get_facecolor())
            print('  Saved: %s' % p)
        if show:
            plt.show()
        else:
            plt.close(fig)


def load_scope_record(h5_path, sweep_key, point_index, record=0):
    """Raw scope record of one point -> (time [s], voltage [V])."""
    with h5py.File(h5_path, 'r') as hf:
        q = hf['sweeps/%s/points/f%02d' % (sweep_key, point_index)]
        codes = q['adc_codes_%d' % record][:]
        v = codes.astype(float) * q.attrs['volt_per_code_V'] - q.attrs['volt_offset_V']
        return np.arange(len(v)) * q.attrs['dt_s'], v


def load_stage_result(h5_path):
    """Load a stage HDF5 file and return (cfg, res) compatible with all make_*_report functions.

    Both completed (*_data.h5) and aborted (*_PARTIAL_data.h5) files are supported.
    Scope spectra and ESA traces are loaded; raw ADC codes are NOT loaded (not needed for plots).
    """
    import types, json as _json
    with h5py.File(h5_path, 'r') as hf:
        cfg_dict = _json.loads(hf['config'].attrs['config_json'])
        cfg = types.SimpleNamespace(**cfg_dict)
        cfg.MEASUREMENT = str(hf.attrs.get('receiver', cfg_dict.get('MEASUREMENT', 'scope')))

        stage    = int(hf.attrs.get('stage', 1))
        title    = str(hf.attrs.get('title', 'Stage %d' % stage))
        is_scope = cfg.MEASUREMENT == 'scope'

        sweeps = []
        sg = hf['sweeps']
        n_freq = None
        for key in sg:
            g = sg[key]
            freq = g['frequency_Hz'][()]
            if n_freq is None:
                n_freq = len(freq)
            nan = np.full(len(freq), np.nan)
            r = {
                'label':        str(g.attrs['label']),
                'key':          key,
                'offset':       float(g.attrs.get('offset_V', 0.0)),
                'vpp':          float(g.attrs.get('vpp_V', 0.5)),
                'coupling':     str(g.attrs.get('receiver_coupling', 'DC')),
                'isolated':     bool(g.attrs.get('isolated', False)),
                'freq':         freq,
                'p_dbm':        g['p_dbm'][()] if 'p_dbm' in g else nan.copy(),
                'v_dc':         g['v_dc_V'][()] if 'v_dc_V' in g else nan.copy(),
                'snr_db':       g['snr_dB'][()] if 'snr_dB' in g else nan.copy(),
                'h2_dbc':       g['h2_dBc'][()] if 'h2_dBc' in g else nan.copy(),
                'h3_dbc':       g['h3_dBc'][()] if 'h3_dBc' in g else nan.copy(),
                'afg_readback': [None] * len(freq),
                'screenshots':  [],
                'points':       [None] * len(freq),
            }
            # Infer isolated from label for files written before the isolated flag was added
            if not r['isolated'] and 'no block' in r['label']:
                r['isolated'] = True
            if 'points' in g:
                for pt_key in sorted(g['points'].keys()):
                    idx = int(pt_key[1:])   # 'f07' -> 7
                    q = g['points'][pt_key]
                    pt = {'p_dbm': float(q.attrs.get('p_dbm', np.nan)),
                          'snr_db': float(q.attrs.get('snr_dB', np.nan)),
                          'v_dc':   float(q.attrs.get('v_dc_V', np.nan))}
                    if 'spectrum_f_Hz' in q:       # scope
                        pt.update({
                            'spec_f':   q['spectrum_f_Hz'][()],
                            'spec_dbm': q['spectrum_dBm'][()],
                            'f_peak':   float(q.attrs.get('f_peak_Hz', 0)),
                            'h2_dbc':   float(q.attrs.get('h2_dBc', np.nan)),
                            'h3_dbc':   float(q.attrs.get('h3_dBc', np.nan)),
                            'vdiv':     float(q.attrs.get('vdiv_V_per_div', 0.1)),
                            'ofst':     float(q.attrs.get('volt_offset_V', 0.0)),
                            'dt':       float(q.attrs.get('dt_s', 1e-7)),
                            'sample_rate': float(q.attrs.get('sample_rate_Sa_s', 1e7)),
                            'tdiv':     float(q.attrs.get('tdiv_s', 2e-3)),
                            'pp_codes': int(q.attrs.get('pp_codes', 0)),
                            'clipped':  bool(q.attrs.get('clipped', False)),
                            'records':  [],   # raw codes not loaded — not needed for plots
                        })
                    elif 'trace_f_Hz' in q:        # ESA
                        pt.update({
                            'trace_f':    q['trace_f_Hz'][()],
                            'trace_dbm':  q['trace_dBm'][()],
                            'center_hz':  float(q.attrs.get('center_Hz', 0)),
                            'span_hz':    float(q.attrs.get('span_Hz', 0)),
                            'rbw_hz':     float(q.attrs.get('rbw_Hz', 0)),
                        })
                    r['points'][idx] = pt
            sweeps.append(r)

        # Reconstruct comparison pairs in insertion order
        pairs = []
        if 'comparisons' in hf:
            for skey in hf['comparisons']:
                rkey = str(hf['comparisons'][skey].attrs['reference'])
                pairs.append((skey, rkey))

        color_mode = 'sequential' if stage == 3 else 'categorical'
        monitor_dc = stage >= 2
        what_map = {1: 'DC block insertion loss (relative to direct)',
                    2: 'Bias tee insertion loss (relative to block-only reference)',
                    3: 'Change of AC response vs the 0 V sweep'}
        res = {'stage': stage, 'title': title, 'sweeps': sweeps, 'pairs': pairs,
               'monitor_dc': monitor_dc, 'color_mode': color_mode,
               'what': what_map.get(stage, '')}
    return cfg, res


# =============================================================================
# Run one stage and save everything
# =============================================================================

def run_stage(S, stage, run_folder, label):
    """Run `stage`, then write  <timestamp>_stage<N>_data.h5 / .csv / _report.pdf / _report.svg / screenshots  to run_folder."""
    cfg = S.cfg
    base = '%s_stage%d' % (pic.datetimestring(), stage)
    S.begin_stage(run_folder, base)
    try:
        res = STAGES[stage](S)
    except BaseException as e:                       # abort (error / Ctrl+C): keep what was measured so far
        print('\nSTAGE %d ABORTED (%s: %s)' % (stage, type(e).__name__, e))
        try:
            if any(r['points'].count(None) < len(r['points']) for r in S.stage_sweeps):
                part = {'stage': stage, 'title': 'Stage %d (ABORTED, partial data)' % stage, 'sweeps': S.stage_sweeps,
                        'pairs': [], 'monitor_dc': stage >= 2, 'color_mode': 'categorical', 'what': 'aborted'}
                S.stage_settings['stage_end'] = S.settings_snapshot()
                save_csv(cfg, os.path.join(run_folder, base + '_PARTIAL_summary.csv'), part)
                write_stage_h5(os.path.join(run_folder, base + '_PARTIAL_data.h5'), cfg, S, label, part, [])
        except Exception as e2:
            print('  (partial data could not be saved: %s)' % e2)
        raise
    S.stage_settings['stage_end'] = S.settings_snapshot()
    comparisons = summarise(cfg, res)
    print('\nSaving ...')
    save_csv(cfg, os.path.join(run_folder, base + '_summary.csv'), res)
    write_stage_h5(os.path.join(run_folder, base + '_data.h5'), cfg, S, label, res, comparisons)    # data first
    for fn, suffix in ((make_report, '_report'), (make_spectra_report, '_spectra'),
                       (make_fft_check_report, '_fftcheck'),
                       (make_all_spectra_report, '_allspectra'),
                       (make_dc_response_report, '_dcresponse')):
        try:
            fn(cfg, res, os.path.join(run_folder, base + suffix), show=cfg.SHOW_PLOTS)
        except Exception as e:                       # a plotting problem must never lose the measurement
            print('  warning: %s failed (%s) - the data are saved in the h5 file' % (fn.__name__, e))
    print('\nStage %d saved in %s' % (stage, run_folder))
    with open(os.path.join(run_folder, base + '_log.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(S.tee.lines[S.log_idx:]) + '\n')
    return res
