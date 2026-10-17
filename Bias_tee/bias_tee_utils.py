#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared helpers for bias_tee_characterization.py (same split as Eye_diagram_lab.py / eye_diagram_utils.py).

bias_tee_characterization.py holds the settings and decides which stages to run; everything that
talks to the instruments, analyses the data and saves it lives here.

Contents
--------
Setup                 instruments (SDG, receiver, Keithley) + the safe-operation logic + one frequency sweep
stage1/2              the two measurement stages (each returns a stage-result dict)
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
    if not any(abs(l) < 1e-12 for l in cfg.PD_DC_LEVELS_V):
        raise ValueError('PD_DC_LEVELS_V must contain 0 (the pure-AC reference of every group), got %r' % (cfg.PD_DC_LEVELS_V,))
    ref = getattr(cfg, 'SCOPE_REFERENCE_H5', None)
    if cfg.MEASUREMENT != 'scope' and ref and not os.path.isfile(ref):
        raise ValueError('SCOPE_REFERENCE_H5 not found: %s' % ref)
    if cfg.MEASUREMENT != 'scope' and getattr(cfg, 'ESA_DC_RAMP_STEP_V', 0.1) > 0.25:
        raise ValueError('ESA_DC_RAMP_STEP_V must be <= 0.25 V (each step reaches the DC-coupled ESA as a transient)')
    if cfg.MEASUREMENT == 'scope' and cfg.SCOPE_COUPLING.get('DC') != 'D50':
        print("WARNING: SCOPE_COUPLING['DC'] is %r - every main measurement is meant to use DC50 ('D50')." % cfg.SCOPE_COUPLING.get('DC'))
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


def confirm_yes(msg):
    """Safety question that needs the typed word 'yes' (ENTER alone is not enough); anything else aborts."""
    PROMPT_LOG.append((datetime.now().isoformat(), msg))
    print('\n' + '=' * 78)
    print(msg)
    ans = input("Type 'yes' + ENTER to confirm (anything else aborts): ").strip().lower()
    PROMPT_LOG.append((datetime.now().isoformat(), 'answer: %r' % ans))
    if ans != 'yes':
        raise RuntimeError('Not confirmed (answer %r) - the ESA stays AC-coupled, aborting.' % ans)


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
        self.rx_dc_coupled = None        # True only for a DC-coupled ESA input => DC only behind a confirmed DC block
        self.dc_block_confirmed = False  # ESA: the EF500 at its input was confirmed (typed 'yes') for the present wiring
        self.rx_text = ('scope CH%d (50 ohm input)' % cfg.SCOPE_CH
                        if self.is_scope else RECEIVER_NAMES[self.kind])
        self.last_vdiv = None
        self.scope_ofst_v = 0.0       # scope channel OFST (V) for DC-present measurements; reset to 0 for AC groups
        self.last_snr = np.nan
        self.run_folder = None
        self.base_name = None
        self.stage_screenshots = []
        self.screenshots_ok = bool(cfg.SAVE_SCREENSHOTS)
        self.used_keys = set()
        self.prior_stage_results = {}          # stage N result stored here after run_stage completes
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
        if self.kind == 'fsw':
            print('FSW input coupling found: %s -> AC until the DC block is confirmed' % self.recv.GetCoupling())
            self.set_rx_coupling('AC')
            w = self.recv.instr.write                      # as the RIN measurement (rin_utils.EsaFSW), no averaging
            w('DISP:TRAC1:MODE WRIT')
            w('DET %s' % getattr(cfg, 'ESA_DETECTOR', 'RMS'))
            att = getattr(cfg, 'ESA_ATTEN_DB', None)
            w('INP:ATT:AUTO ON' if att is None else 'INP:ATT %g' % att)
            w('SWE:TYPE AUTO')
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
                             'BAND:VID?', 'SWE:POIN?', 'SWE:COUN?', 'INP:ATT?', 'DET?', 'DISP:TRAC1:MODE?', 'SWE:TYPE?',
                             'SWE:TYPE:USED?']
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
        if coupling == 'DC' and not self.is_scope and not self.dc_block_confirmed:
            raise RuntimeError('Refusing DC coupling of the ESA: the DC block at its input was not confirmed (esa_rewire)')
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

    def esa_rewire(self, wiring_msg):
        """ESA: AC-coupled (and SDG off) while you re-wire; DC coupling only after typing 'yes' for the DC block.
        The ESA is DC-coupled for every measurement (as in the RIN measurement), so the EF500 at its input is mandatory."""
        self.set_rx_coupling('AC')
        self.dc_block_confirmed = False
        ask(wiring_msg)
        confirm_yes('*** ESA SAFETY CHECK ***\n'
                    '  The %s input will now be switched to DC coupling (needed below ~10 MHz).\n'
                    '  A DC-coupled ESA input must never see DC - it destroys the input.\n'
                    '  Is the EF500 DC block connected DIRECTLY at the ESA RF input?' % self.rx_text)
        self.dc_block_confirmed = True
        self.set_rx_coupling('DC')

    def _ramp_dc(self):
        """DC changes are ramped in ESA_DC_RAMP_STEP_V steps while a DC-coupled ESA sits behind the DC block: a DC step
        passes the coupling capacitors (bias tee, EF500) as a transient of the same size - as when a laser is unblocked."""
        return self.rx_dc_coupled and not self.is_scope

    def ramp_offset(self, freq, vpp, start, stop):
        """SDG output ON: offset start -> stop in steps of ESA_DC_RAMP_STEP_V (each verified by read-back)."""
        step = float(getattr(self.cfg, 'ESA_DC_RAMP_STEP_V', 0.1))
        n = int(np.ceil(abs(stop - start) / step - 1e-9))
        for v in np.linspace(start, stop, n + 1)[1:]:
            self.set_tone(freq, vpp, round(float(v), 3))
            time.sleep(float(getattr(self.cfg, 'ESA_DC_RAMP_SETTLE_S', 0.05)))

    # ---- SDG -------------------------------------------------------------------
    def afg_output_off(self):
        self.afg.output_status(channel=self.cfg.AFG_CH, status='OFF')

    def set_tone(self, freq, vpp, offset):
        """Configure the SDG (offset is verified by read-back before anything is switched on)."""
        cfg = self.cfg
        if self.rx_dc_coupled and abs(offset) > 0 and not self.dc_block_confirmed:
            raise RuntimeError('Refusing DC offset %g V: the ESA is DC-coupled and no DC block was confirmed' % offset)
        self.afg.instr.write('C%d:OUTP LOAD,%s' % (cfg.AFG_CH, cfg.AFG_LOAD))      # load first, then amplitude/offset
        self.afg.setParameters(channel=cfg.AFG_CH, waveform='SINE', frequency=freq, vpp=vpp,
                               offset=offset, load=cfg.AFG_LOAD)
        self.verify_tone(freq, vpp, offset)

    def set_dc(self, offset):
        """SDG in pure DC mode (no AC) at `offset` (50 ohm convention), verified by read-back. Output state unchanged."""
        cfg = self.cfg
        if self.rx_dc_coupled and abs(offset) > 0 and not self.dc_block_confirmed:
            raise RuntimeError('Refusing DC offset %g V: the ESA is DC-coupled and no DC block was confirmed' % offset)
        ch = 'C%d' % cfg.AFG_CH
        self.afg.instr.write('%s:OUTP LOAD,%s' % (ch, cfg.AFG_LOAD))       # load first, then offset
        self.afg.setParameters(channel=cfg.AFG_CH, waveform='DC', offset=offset, load=cfg.AFG_LOAD)
        resp = self.afg.instr.query('%s:BSWV?' % ch)
        outp = self.afg.instr.query('%s:OUTP?' % ch)
        self.last_afg_readback = (resp.strip(), outp.strip())
        m = re.search(r'OFST,([-+0-9.eE]+)', resp)
        if not re.search(r'WVTP,\s*DC\b', resp) or not m or abs(float(m.group(1)) - offset) > 1e-3:
            raise RuntimeError('SDG read-back mismatch: asked DC, offset %g V, got "%s"' % (offset, resp.strip()))
        if not re.search(r'LOAD,\s*%s\b' % cfg.AFG_LOAD, outp):
            raise RuntimeError('SDG load is not %s ohm: "%s"' % (cfg.AFG_LOAD, outp.strip()))

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
        if self.rx_dc_coupled and abs(ofst) > 1e-3 and not self.dc_block_confirmed:
            raise RuntimeError('DC offset present with DC-coupled ESA and no confirmed DC block!')

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
        # SDS2352X-E offset range: ±2 V at ≤100 mV/div, ±20 V at 102 mV–1 V/div (manual p.60).
        # Any vdiv > 100 mV/div (i.e. 200 mV/div) covers offsets up to ±20 V — sufficient for all
        # DC levels used here.  Enforce this floor so the loop never drops back into the narrow range.
        vdiv_floor = 0.2 if abs(self.scope_ofst_v) > 2.0 else 0.0
        vdiv = self.last_vdiv or sc.nearest_vdiv(vpp / 6.0)
        if vdiv < vdiv_floor:
            vdiv = vdiv_floor
        lo, hi = cfg.SCOPE_PP_CODES
        for _ in range(12):                                  # vertical auto-scale (8 bit => keep signal large)
            _vd, _of = sc.SetVertical(cfg.SCOPE_CH, vdiv, self.scope_ofst_v)
            if abs(_of - self.scope_ofst_v) > 1e-3 and vdiv < 0.2:      # offset clamped by the scope (+-2 V at <= 100 mV/div)
                vdiv = 0.2
                _vd, _of = sc.SetVertical(cfg.SCOPE_CH, vdiv, self.scope_ofst_v)
            if abs(_of - self.scope_ofst_v) > 1e-3:
                raise RuntimeError('Scope did not accept the offset %g V (reads back %g V)' % (self.scope_ofst_v, _of))
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
                if new < vdiv_floor:                         # DC offset range is the limit; accept current pp
                    break
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
        codes_avg = np.mean([r.astype(float) for r in records], axis=0)
        dc_from_scope_V = float(np.mean(codes_avg)) * (vdiv_rb / 25.0) - ofst
        return {'p_dbm': p_dbm, 'snr_db': sp['snr_db'], 'records': records, 'vdiv': vdiv_rb, 'ofst': ofst, 'dt': dt,
                'tdiv': info['tdiv'], 'sample_rate': info['sample_rate_Sa_s'], 'pp_codes': pp, 'clipped': clipped,
                'f_peak': sp['f_peak'], 'h2_dbc': sp['h2_dbc'], 'h3_dbc': sp['h3_dbc'],
                'spec_f': sp['f'][band].astype(np.float32),
                'spec_dbm': sp['dbm'][band].astype(np.float32),
                'dc_from_scope_V': dc_from_scope_V}

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
            time.sleep(getattr(self.cfg, 'SCREENSHOT_SETTLE_S', 2.0))
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
        if self._ramp_dc():
            self.ramp_offset(f, vpp, pre, offset)
        else:
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
               'freq': freqs, 'p_dbm': nan.copy(), 'v_dc': nan.copy(), 'v_scope_dc': nan.copy(),
               'snr_db': nan.copy(),
               'h2_dbc': nan.copy(), 'h3_dbc': nan.copy(), 'afg_readback': [None] * len(freqs),
               'points': [None] * len(freqs), 'screenshots': [], 't_start': datetime.now().isoformat()}
        fmin = MIN_FREQ_HZ[self.kind]
        self.afg_output_off()
        ramp = self._ramp_dc() and abs(offset) > 0                  # DC-coupled ESA behind the DC block: no DC steps
        f_on = None                                                 # frequency while the output is on
        try:
            first = True
            for i, f in enumerate(freqs):
                if f < fmin:
                    print('  [%s] %10.0f Hz  skipped (minimum %g Hz)' % (label, f, fmin))
                    continue
                # configure (output still OFF on the first point; with ramp it is switched on at 0 V offset)
                self.set_tone(f, vpp, 0.0 if (first and ramp) else offset)
                if first:
                    res['settings'] = self.settings_snapshot()      # all instrument settings, output still OFF
                    if monitor_dc:
                        self.keithley_guard(offset)                 # never switch the signal on without the Hi-Z monitor
                    if monitor_dc and abs(offset) > cfg.DC_PRECHECK_OFFSET_V:
                        self.dc_precheck(f, vpp, offset)            # low-DC test first; ends with the output ON at `offset`
                    else:
                        self.afg.output_status(channel=cfg.AFG_CH, status='ON')
                        if ramp:
                            self.ramp_offset(f, vpp, 0.0, offset)
                    first = False
                f_on = f
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
                res['v_scope_dc'][i] = pt.get('dc_from_scope_V', np.nan)
                snr = ('  SNR %.0f dB  H2 %.0f dBc  H3 %.0f dBc' % (pt['snr_db'], pt['h2_dbc'], pt['h3_dbc'])) if self.is_scope else ''
                sdc = res['v_scope_dc'][i]
                sdc_str = ('  Vscope_dc = %+.4f V' % sdc) if (self.is_scope and np.isfinite(sdc)) else ''
                print('  [%s] %10.0f Hz  P = %8.2f dBm (exp. %.2f)%s%s%s' % (label, f, pt['p_dbm'], expected_dbm(vpp), snr, msg, sdc_str))
                if self.want_screenshot(f):
                    n_before = len(self.stage_screenshots)
                    self.screenshot('%s_%.0fHz' % (key, f))
                    if len(self.stage_screenshots) > n_before:
                        res['screenshots'].append({'tag': self.stage_screenshots[-1][0],
                                                   'path': self.stage_screenshots[-1][1], 'index': i})
            if ramp and f_on is not None:                           # normal end: DC down gently, then off.
                self.ramp_offset(f_on, vpp, offset, 0.0)            # (after an error: OFF at once - the inductor first)
        finally:
            self.afg_output_off()
            res['t_end'] = datetime.now().isoformat()
            self.stage_sweeps.append(res)
        return res

    def close(self):
        for fn in (lambda: self.afg_output_off(),
                   lambda: self.afg.instr.write('C%d:BSWV OFST,+0' % self.cfg.AFG_CH),
                   lambda: self.kind == 'fsw' and self.recv.SetCoupling('AC'),          # leave the ESA DC-safe
                   lambda: self.kind == 'fsw' and print('FSW input coupling at exit: %s' % self.recv.GetCoupling()),
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


def tee_wiring_text(cfg, rx_text, dc_levels=(0,), cpl='AC-coupled'):
    return ('  SDG CH%d (50 ohm mode)  ->  bias tee  AC+DC input\n' % cfg.AFG_CH +
            '  bias tee  AC output  ->  EF500 DC block  ->  ' + rx_text + ' (' + cpl + ')\n'
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
        levels = list(cfg.PD_DC_LEVELS_V)
        by_level = cfg.MEASUREMENT == 'scope' and len(levels) > 1 and all(r.get('sweep_group') for r in sweeps)
        ramp = _seq_colors(len(levels))
        for i, r in enumerate(sweeps):
            grp = r.get('sweep_group', 'tee_iso' if r.get('isolated') else 'tee_block')
            if by_level:      # same DC level = same colour in every group (stable while the list grows); group = line style/marker
                c = ramp[int(np.argmin([abs(l - r['offset']) for l in levels]))]
                m = _GROUP_MARK.get(grp, 'o')
            else:
                c, m = CATEGORICAL[i % len(CATEGORICAL)], MARKERS[i % len(MARKERS)]
            ls = _GROUP_LS.get(grp, '-')
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
        fig.canvas.draw()
        fig.canvas.flush_events()
        plt.pause(0.3)
    except Exception:
        pass   # never break the measurement for a plot problem


def _levels(S):
    """DC levels of the no-tee reference groups. An ESA never gets DC: it only does the 0 V (pure AC) sweep."""
    return list(S.cfg.PD_DC_LEVELS_V) if S.is_scope else [0]


def _base(sweeps):
    """The 0 V (pure AC) sweep of a group."""
    return next(r for r in sweeps if abs(r['offset']) < 1e-12)


def _rx_main_coupling(S):
    """Coupling of every MAIN measurement: DC. Scope: DC50. ESA: DC-coupled like in the RIN measurement, ALWAYS behind the
    EF500 (esa_rewire: only after typing 'yes'). AC50 on the scope only for the optional extra sweep."""
    return 'DC'


def _cpl_text(S):
    return 'DC-coupled, 50 ohm (DC50)' if S.is_scope else 'DC-coupled, EF500 directly at its input'


def _ref_group(S, name, group, levels, direct, title, done=()):
    """One reference group = one sweep per DC level (the SDG offset).

    direct=True : the receiver sees the DC too, so the scope channel offset is set to -level (taken from the level list,
                  never read from the SDG; the scope clamps it unless V/div is large enough - see read_point_scope).
    direct=False: the EF500 blocks the DC, the scope sees pure AC and its offset stays 0."""
    out = []
    for lvl in levels:
        S.scope_ofst_v = -lvl if direct else 0.0
        try:
            sw = S.sweep('%s %.2f V' % (name, lvl), offset=lvl)
        finally:
            S.scope_ofst_v = 0.0
        sw['sweep_group'] = group
        out.append(sw)
        S.afg_output_off()
        _plot_live(S.cfg, list(done) + out, title)
    return out


def stage1(S):
    """ALL no-tee references, in one wiring pass (no bias tee, no Keithley):
         1-A  SDG -> receiver                 'ref direct DC x V'  (group ref_dc)   pure AC (0 V) + every DC level
         1-B  SDG -> EF500 -> receiver        'ref EF500 DC x V'   (group ref_ac)   pure AC (0 V) + every DC level
       Receiver DC-coupled (scope: DC50) for both.  The EF500 then stays on the receiver for stage 2.
       Optional EXTRA (STAGE1_ALSO_AC_COUPLED): the 0 V EF500 sweep again with the receiver AC-coupled (scope: AC50).
       An ESA only does 1-B at 0 V, DC-coupled as in the RIN measurement: the SDG never reaches its input without the
       EF500 (1-A is skipped). Compared with the scope's 'ref EF500 DC 0.00 V' = the ESA's absolute level (SCOPE_REFERENCE_H5)."""
    cfg = S.cfg
    if not S.is_scope:
        title = 'Stage 1: ESA reference (EF500)'
        S.esa_rewire('STAGE 1 (ESA reference: EF500)\n'
                     '  Bias tee and Keithley NOT connected to anything in this stage.\n'
                     '  SDG CH%d  ->  EF500 DC block  ->  %s RF input\n'
                     '  Same cables / adapters as the scope reference "ref EF500" (only the receiver changes).\n'
                     '  The EF500 stays at the ESA input for stage 2. (The direct reference 1-A is skipped for an ESA.)'
                     % (cfg.AFG_CH, S.rx_text))
        B = _ref_group(S, 'ref EF500 DC', 'ref_ac', [0], False, title)
        return {'stage': 1, 'title': title, 'sweeps': B, 'pairs': [], 'monitor_dc': False, 'color_mode': 'categorical',
                'what': 'ESA reference through the EF500 (compared with the scope reference below)'}
    title = 'Stage 1: references (direct, EF500)'
    levels = _levels(S)
    S.set_rx_coupling('DC')
    if S.is_scope:
        what = ('  The SDG outputs the AC tone + a DC offset of %s V into the scope 50 ohm input (DC50). The scope offset is set\n'
                '  automatically for every level.' % list(levels))
    else:
        what = '  Receiver is DC-coupled: signal is pure AC (offset 0 V, verified by read-back).'
    ask('STAGE 1-A (reference: direct)\n'
        '  Bias tee and Keithley NOT connected to anything in this stage.\n'
        '  SDG CH%d  ->  %s  (direct, SMA/adapters only, NO DC block)\n%s' % (cfg.AFG_CH, S.rx_text, what))
    A = _ref_group(S, 'ref direct DC', 'ref_dc', levels, True, title)
    ask('STAGE 1-B (reference: EF500)\n'
        '  Insert the Thorlabs EF500 DC block:  SDG CH%d  ->  EF500  ->  %s\n'
        '  Keep the EF500 on the receiver side - it stays there for stage 2.%s'
        % (cfg.AFG_CH, S.rx_text, ('\n  Same DC levels again (the EF500 blocks the DC, the scope should see pure AC).' if S.is_scope else '')))
    B = _ref_group(S, 'ref EF500 DC', 'ref_ac', levels, False, title, A)
    sweeps = A + B
    a0, b0 = _base(A), _base(B)
    pairs = [(b0['key'], a0['key'])] + [(r['key'], a0['key']) for r in A if r is not a0] \
        + [(r['key'], b0['key']) for r in B if r is not b0]
    if cfg.STAGE1_ALSO_AC_COUPLED:
        S.set_rx_coupling('AC')
        ask('STAGE 1-X (EXTRA, optional)\n  Keep SDG -> EF500 -> receiver.  Receiver is now AC-coupled (%s), pure AC.'
            % ('scope A50' if S.is_scope else 'ESA AC'))
        X = S.sweep('extra: EF500 AC-coupled', offset=0.0)
        X['sweep_group'] = 'extra_ac'
        sweeps.append(X)
        pairs.append((X['key'], b0['key']))
        _plot_live(cfg, sweeps, title)
        S.set_rx_coupling('DC')
    return {'stage': 1, 'title': 'Stage 1: references (direct, EF500)', 'sweeps': sweeps, 'pairs': pairs,
            'monitor_dc': False, 'color_mode': 'sequential' if (S.is_scope and len(levels) > 1) else 'categorical',
            'what': 'DC block insertion loss (EF500 vs direct) and change vs the 0 V sweep of each group'}


def stage2(S):
    """Bias tee with AC + DC levels.

    Part A (tee_block): SDG -> bias tee -> EF500 -> receiver, all DC levels, Keithley monitored.
    Part B (tee_iso, scope only): SDG -> bias tee -> receiver (no EF500), all DC levels, Keithley monitored.

    Run STAGES_TO_RUN = [1, 2] together so stage 1 references are in memory for per-level comparisons.
    Without stage 1 in memory each group is compared with its own 0 V sweep instead."""
    cfg = S.cfg
    _title2 = 'Stage 2: bias tee, AC + DC'
    coupling = _rx_main_coupling(S)
    s1 = S.prior_stage_results.get(1)
    refs = []
    for sw in (s1['sweeps'] if s1 else []):
        if sw.get('sweep_group') in ('ref_dc', 'ref_ac'):
            c = dict(sw)
            c['points'] = [None] * len(sw['points'])
            c['screenshots'] = []
            c['from_stage1'] = True
            refs.append(c)
    if not refs:
        print('NOTE: stage 1 was not run in this session - tee sweeps compared with their own 0 V sweep only.')
    ref_ac = {r['offset']: r for r in refs if r['sweep_group'] == 'ref_ac'}
    ref_dc = {r['offset']: r for r in refs if r['sweep_group'] == 'ref_dc'}

    def pair_up(group_sweeps, refmap):
        base = _base(group_sweeps)
        out = []
        for r in group_sweeps:
            ref = refmap.get(r['offset'], None if r is base else base)
            if ref is not None and ref is not r:
                out.append((r['key'], ref['key']))
        return out

    # --- Part A: bias tee + EF500 ---
    wiring = ('STAGE 2-A (bias tee + EF500)\n' + tee_wiring_text(cfg, S.rx_text, cfg.PD_DC_LEVELS_V, cpl=_cpl_text(S)) +
              '\n  Levels (PD output into 50 ohm): %s V -> Keithley should read ~%g x these.'
              % (list(cfg.PD_DC_LEVELS_V), cfg.DC_AT_TEE_FACTOR))
    S.keithley.AssertHighZ()
    if S.is_scope:
        S.set_rx_coupling(coupling)
        ask(wiring)
    else:                         # as with the photodetector: sine + DC into the tee, DC port on the Keithley, EF500 at the ESA
        S.esa_rewire(wiring + '\n  The ESA is DC-coupled; DC changes are ramped in %g V steps (transients through the '
                              'capacitors).' % getattr(cfg, 'ESA_DC_RAMP_STEP_V', 0.1))
    tee_block_sweeps = []
    for lvl in cfg.PD_DC_LEVELS_V:
        sw = S.sweep('tee+EF500 DC %.2f V' % lvl, offset=lvl, monitor_dc=True)
        sw['sweep_group'] = 'tee_block'
        tee_block_sweeps.append(sw)
        S.afg_output_off()
        _plot_live(cfg, refs + tee_block_sweeps, _title2)
    sweeps = refs + tee_block_sweeps
    pairs = pair_up(tee_block_sweeps, ref_ac)

    if S.is_scope:
        # --- Part B: bias tee AC port direct to scope, no EF500 ---
        S.set_rx_coupling('DC')
        ask('STAGE 2-B (bias tee, no EF500)\n'
            + tee_isolation_wiring_text(cfg, S.rx_text, cfg.PD_DC_LEVELS_V)
            + '\n  Levels (PD output into 50 ohm): %s V -> Keithley should read ~%g x these.'
            % (list(cfg.PD_DC_LEVELS_V), cfg.DC_AT_TEE_FACTOR))
        iso_sweeps = []
        for lvl in cfg.PD_DC_LEVELS_V:
            sw = S.sweep('tee only DC %.2f V' % lvl, offset=lvl, monitor_dc=True)
            sw['sweep_group'] = 'tee_iso'
            sw['isolated'] = True
            iso_sweeps.append(sw)
            S.afg_output_off()
            _plot_live(cfg, sweeps + iso_sweeps, _title2)
        sweeps = sweeps + iso_sweeps
        pairs += pair_up(iso_sweeps, ref_dc)

    return {'stage': 2, 'title': 'Stage 2: bias tee, AC + DC', 'sweeps': sweeps,
            'pairs': pairs,
            'monitor_dc': True, 'color_mode': 'sequential',
            'what': 'Bias tee loss vs DC level (tee+EF500 vs EF500 ref; tee-only vs direct ref)'}


STAGES = {1: stage1, 2: stage2}


# =============================================================================
# Stage 3: DC calibration - SDG into the Keithley directly vs through the bias tee DC port
# =============================================================================

def _dc_pass(S, part, levels, through_tee):
    """Pure DC (no AC) at every level; the settled Keithley reading followed by STAGE3_NREAD readings per level."""
    cfg = S.cfg
    rows = S.stage3_rows[part]
    S.afg_output_off()
    S.keithley_guard(max(abs(l) for l in levels))         # 0 A / high-Z and a voltage limit above the highest level
    try:
        if through_tee and max(abs(l) for l in levels) > cfg.DC_PRECHECK_OFFSET_V:
            pre = cfg.DC_PRECHECK_OFFSET_V                    # small DC first: <= 4 mA even into a shorted DC port
            S.set_dc(pre)
            S.afg.output_status(channel=cfg.AFG_CH, status='ON')
            time.sleep(cfg.SETTLE_S)
            v, exp = S.read_dc(), cfg.DC_AT_TEE_FACTOR * pre
            if not (cfg.DC_ABORT_LOW_FRAC * exp <= v <= cfg.DC_ABORT_HIGH_FRAC * exp):
                raise RuntimeError('DC pre-check FAILED: Keithley reads %.4f V, expected ~%.4f V at %.2f V SDG offset. Keithley '
                                   'not on the bias tee DC port / wrong terminals / short? Output switched off.' % (v, exp, pre))
            print('  DC pre-check OK: Keithley %.4f V at %.2f V offset (expected %.4f V)' % (v, pre, exp))
        for lvl in levels:
            S.set_dc(lvl)
            S.afg.output_status(channel=cfg.AFG_CH, status='ON')
            time.sleep(cfg.STAGE3_SETTLE_S)
            S.read_dc()                                       # waits until the reading has settled
            vals = np.array([S.keithley.GetMeas() for _ in range(cfg.STAGE3_NREAD)], float)
            exp = cfg.DC_AT_TEE_FACTOR * lvl
            mean = float(vals.mean())
            if abs(exp) > 0 and not (cfg.DC_ABORT_LOW_FRAC * exp <= mean <= cfg.DC_ABORT_HIGH_FRAC * exp):
                raise RuntimeError('Keithley reads %.4f V but ~%.4f V is expected (SDG offset %.2f V): not connected / wrong '
                                   'terminals / SDG load setting? Output switched off.' % (mean, exp, lvl))
            rows.append({'offset': lvl, 'expected': exp, 'mean': mean, 'std': float(vals.std()), 'readings': vals,
                         'afg_readback': ' | '.join(S.last_afg_readback), 't': datetime.now().isoformat()})
            print('  [%-6s] SDG %.2f V -> expected %.4f V   Keithley %.5f V +- %.5f V   (%+.2f mV, %+.3f %%)'
                  % (part, lvl, exp, mean, vals.std(), 1e3 * (mean - exp), 100 * (mean / exp - 1) if exp else np.nan))
    finally:
        S.afg_output_off()


def stage3(S):
    """DC calibration of the DC path: what does the Keithley read for a known DC, directly and through the bias tee?
         3-A  SDG -> Keithley directly                  (no bias tee)
         3-B  SDG -> bias tee AC+DC input, DC port -> Keithley, AC port -> EF500 -> receiver (as stage 2-A)
       Pure DC from the SDG (no AC). Expected reading: DC_AT_TEE_FACTOR (2) x offset. A-B removes the SDG's own offset
       error (the same SDG levels are used in both), so 'tee - direct' is the effect of the bias tee on the DC reading."""
    cfg = S.cfg
    levels = sorted(set(float(l) for l in cfg.PD_DC_LEVELS_V))
    S.stage3_rows = {'direct': [], 'tee': []}
    if not S.is_scope:                     # the receiver is not measured here: keep an ESA AC-coupled (DC-safe)
        S.set_rx_coupling('AC')
        S.dc_block_confirmed = False
    ask('STAGE 3-A (DC calibration: SDG directly into the Keithley)\n'
        '  Bias tee NOT connected.\n'
        '  SDG CH%d (50 ohm mode)  ->  BNC-to-banana cable  ->  Keithley 2450 FRONT  HI (centre) / LO (shield)\n'
        '  Pure DC, levels %s V -> the Keithley should read ~%g x these.' % (cfg.AFG_CH, levels, cfg.DC_AT_TEE_FACTOR))
    _dc_pass(S, 'direct', levels, through_tee=False)
    ask('STAGE 3-B (DC calibration: through the bias tee)\n' + tee_wiring_text(cfg, S.rx_text, levels, cpl=_cpl_text(S)) +
        '  Use the SAME BNC-to-banana cable as in 3-A, now on the bias tee DC output.\n'
        '  The receiver is not measured in this stage (a 50 ohm terminator on the EF500 is fine too).')
    _dc_pass(S, 'tee', levels, through_tee=True)
    return {'stage': 3, 'title': 'Stage 3: DC calibration, SDG -> Keithley direct vs through the bias tee', 'rows': S.stage3_rows}


def dc_table(rows):
    """Both passes side by side per SDG level (NaN where a pass is missing)."""
    levels = sorted({r['offset'] for part in rows.values() for r in part})
    get = lambda part, lvl, key: next((r[key] for r in rows.get(part, []) if r['offset'] == lvl), np.nan)
    t = {'sdg_offset_V': np.array(levels),
         'expected_V': np.array([next(r['expected'] for part in rows.values() for r in part if r['offset'] == l) for l in levels])}
    for part in ('direct', 'tee'):
        t['%s_mean_V' % part] = np.array([get(part, l, 'mean') for l in levels])
        t['%s_std_V' % part] = np.array([get(part, l, 'std') for l in levels])
    with np.errstate(divide='ignore', invalid='ignore'):
        for part in ('direct', 'tee'):
            t['%s_dev_mV' % part] = 1e3 * (t['%s_mean_V' % part] - t['expected_V'])
            t['%s_dev_pct' % part] = np.where(t['expected_V'] != 0, 100 * (t['%s_mean_V' % part] / t['expected_V'] - 1), np.nan)
        t['tee_minus_direct_mV'] = 1e3 * (t['tee_mean_V'] - t['direct_mean_V'])
        ratio = np.where(np.abs(t['direct_mean_V']) > 1e-2, t['tee_mean_V'] / t['direct_mean_V'], np.nan)
        t['tee_minus_direct_pct'] = 100 * (ratio - 1)
        t['rin_error_dB'] = -20 * np.log10(ratio)          # RIN with the tee reading instead of the true DC: + = too high
    return t


def make_dc_report(cfg, res, base_path, show=False):
    t = dc_table(res['rows'])
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 6.6), sharex=True)
        fig.patch.set_facecolor(SURFACE)
        for i, part in enumerate(('direct', 'tee')):
            ax1.errorbar(t['expected_V'], t['%s_dev_mV' % part], yerr=1e3 * t['%s_std_V' % part], fmt='-' + MARKERS[i],
                         color=CATEGORICAL[i], ms=6, lw=1.6, capsize=3,
                         label='SDG -> Keithley %s' % ('directly' if part == 'direct' else 'through the bias tee DC port'))
        ax1.axhline(0, color=AXIS, lw=0.8)
        ax1.set_ylabel('Keithley - %g x SDG offset (mV)' % cfg.DC_AT_TEE_FACTOR)
        ax1.set_title(res['title'], loc='left', color=INK, fontsize=11)
        ax1.legend(fontsize=8, frameon=False, labelcolor=INK2)
        ax2.plot(t['expected_V'], t['tee_minus_direct_pct'], '-' + MARKERS[2], color=CATEGORICAL[2], ms=6, lw=1.6,
                 label='through the tee vs directly (RIN error = -20 log10(tee / direct))')
        ax2.axhline(0, color=AXIS, lw=0.8)
        ax2.set_ylabel('Tee - direct (%)')
        ax2.set_xlabel('Expected DC at the Keithley (V)')
        ax2.legend(fontsize=8, frameon=False, labelcolor=INK2)
        for ax in (ax1, ax2):
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


def save_dc_csv(path, res):
    t = dc_table(res['rows'])
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(list(t))
        for row in zip(*t.values()):
            w.writerow(['%.7g' % x for x in row])
    print('  Saved: %s' % path)


def write_dc_h5(path, cfg, S, label, res):
    with h5py.File(path, 'w') as hf:
        hf.attrs['label'], hf.attrs['stage'], hf.attrs['title'] = label, 3, res['title']
        hf.attrs['afg_idn'], hf.attrs['keithley_idn'] = S.afg_idn, S.keithley_idn
        hf.attrs['created'] = datetime.now().isoformat()
        cg = hf.create_group('config')
        for k, v in vars(cfg).items():
            cg.attrs[k] = _attr(v)
        cg.attrs['config_json'] = json.dumps(vars(cfg), default=str, indent=1, sort_keys=True)
        cg.attrs['keithley_setup'] = json.dumps(S.keithley_setup, default=str)
        _write_settings(hf.create_group('settings'), S.stage_settings)
        _write_provenance(hf)
        lg = hf.create_group('log')
        lg.create_dataset('console_log', data='\n'.join(S.tee.lines[S.log_idx:]), dtype=h5py.string_dtype('utf-8'))
        lg.create_dataset('prompts', data=['[%s] %s' % pr for pr in PROMPT_LOG[S.prompt_idx:]], dtype=h5py.string_dtype('utf-8'))
        tg = hf.create_group('table')
        for k, v in dc_table(res['rows']).items():
            tg.create_dataset(k, data=v)
        for part, rows in res['rows'].items():
            pg = hf.create_group(part)
            for r in rows:
                g = pg.create_group('offset_%+.3fV' % r['offset'])
                g.create_dataset('readings_V', data=r['readings'])
                for k in ('offset', 'expected', 'mean', 'std', 'afg_readback', 't'):
                    g.attrs[k] = _attr(r[k])
    print('  HDF5 saved: %s' % path)


def run_dc_stage(S, run_folder, base, label):
    """Stage 3 (DC only): own csv / h5 / pdf / svg; partial files on an abort."""
    cfg = S.cfg
    S.stage3_rows = {'direct': [], 'tee': []}
    try:
        res = stage3(S)
    except BaseException as e:
        print('\nSTAGE 3 ABORTED (%s: %s)' % (type(e).__name__, e))
        part = {'stage': 3, 'title': 'Stage 3 (ABORTED, partial data)', 'rows': S.stage3_rows}
        if any(S.stage3_rows.values()):
            try:
                S.stage_settings['stage_end'] = S.settings_snapshot()
                save_dc_csv(os.path.join(run_folder, base + '_PARTIAL_dc.csv'), part)
                write_dc_h5(os.path.join(run_folder, base + '_PARTIAL_data.h5'), cfg, S, label, part)
            except Exception as e2:
                print('  (partial data could not be saved: %s)' % e2)
        raise
    S.stage_settings['stage_end'] = S.settings_snapshot()
    S.prior_stage_results[3] = res
    t = dc_table(res['rows'])
    print('\nDC calibration (Keithley - %g x SDG offset; tee - direct):' % cfg.DC_AT_TEE_FACTOR)
    for i, lvl in enumerate(t['sdg_offset_V']):
        print('  SDG %.2f V: direct %+7.2f mV   tee %+7.2f mV   tee - direct %+7.2f mV (%+.3f %%)  -> RIN error %+.4f dB'
              % (lvl, t['direct_dev_mV'][i], t['tee_dev_mV'][i], t['tee_minus_direct_mV'][i], t['tee_minus_direct_pct'][i],
                 t['rin_error_dB'][i]))
    print('\nSaving ...')
    write_dc_h5(os.path.join(run_folder, base + '_data.h5'), cfg, S, label, res)
    save_dc_csv(os.path.join(run_folder, base + '_dc.csv'), res)
    try:
        make_dc_report(cfg, res, os.path.join(run_folder, base + '_report'), show=cfg.SHOW_PLOTS)
    except Exception as e:
        print('  warning: plot failed (%s) - the data are saved in the h5 file' % e)
    with open(os.path.join(run_folder, base + '_log.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(S.tee.lines[S.log_idx:]) + '\n')
    print('\nStage 3 saved in %s' % run_folder)
    return res


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


_GROUP_LS = {'ref_dc': ':', 'ref_ac': '-.', 'tee_block': '-', 'tee_iso': '--', 'extra_ac': '-', '': '-'}
_GROUP_MARK = {'ref_dc': 'o', 'ref_ac': 's', 'tee_block': '^', 'tee_iso': 'D', 'extra_ac': 'x'}


def _series_styles(res):
    """key -> (colour, marker, linestyle).  Categorical = per-sweep identity; sequential = DC level (light -> dark).

    In sequential mode all groups share the same colour ramp keyed by SDG offset (same DC level = same colour).
    Line style distinguishes the group: ref_dc=':', ref_ac='-.', tee_block='-', tee_iso='--'.
    """
    sty = {}
    if res['color_mode'] == 'sequential':
        # Build a colour for every unique DC level in order
        all_offsets = sorted(set(r['offset'] for r in res['sweeps']))
        offset_color = {o: c for o, c in zip(all_offsets, _seq_colors(len(all_offsets)))}
        for i, r in enumerate(res['sweeps']):
            grp = r.get('sweep_group', 'tee_iso' if r.get('isolated') else 'tee_block')
            ls = _GROUP_LS.get(grp, '-')
            c = offset_color[r['offset']]
            sty[r['key']] = (c, _GROUP_MARK.get(grp, 'o'), ls)
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
    has_scope_dc = scope and any(np.isfinite(r.get('v_scope_dc', np.array([np.nan]))).any() for r in res['sweeps'])
    n = (3 if res['monitor_dc'] else 2) + (1 if has_scope_dc else 0) + (2 if scope else 0)
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
        large = len(res['sweeps']) > 8   # too many entries for in-axes legends → use a figure-level legend below
        _lkw = dict(frameon=False, labelcolor=INK2)
        if not large:
            ax1.legend(fontsize=8, ncol=2 if len(res['sweeps']) > 4 else 1, **_lkw)
        ref_labels = set()
        for skey, rkey in res['pairs']:
            s, r = by[skey], by[rkey]
            c, m, ls = sty[skey]
            ax2.plot(s['freq'], s['p_dbm'] - r['p_dbm'], ls, color=c, marker=m, ms=5, lw=1.6,
                     label='%s − %s' % (s['label'], r['label']))
            ref_labels.add(r['label'])
        ax2.axhspan(-cfg.PASS_TOL_DB, cfg.PASS_TOL_DB, color=GRID, alpha=0.7, lw=0)
        ax2.axhline(0, color=AXIS, lw=0.8)
        ax2.set_ylabel('Insertion loss (dB)\n(grey band = ±%.4g dB pass/fail)' % cfg.PASS_TOL_DB)
        if not large:
            ax2.legend(fontsize=8, ncol=1 if len(res['pairs']) <= 4 else 2, **_lkw)
        if res['monitor_dc']:
            ax3 = axes[2]
            for r in res['sweeps']:
                if not np.isfinite(r['v_dc']).any():
                    continue
                c, m, ls = sty[r['key']]
                ax3.plot(r['freq'], r['v_dc'], ls, color=c, marker=m, ms=5, lw=1.6, label=r['label'])
                ax3.axhline(cfg.DC_AT_TEE_FACTOR * r['offset'], color=c, ls=':', lw=0.9)
            ax3.set_ylabel('DC port voltage (V) [Keithley]\n(dotted = expected: %g × SDG offset)' % cfg.DC_AT_TEE_FACTOR)
            if not large:
                ax3.legend(fontsize=8, ncol=2 if len(res['sweeps']) > 4 else 1, **_lkw)
        if has_scope_dc:
            ax_sdc = axes[2 + (1 if res['monitor_dc'] else 0)]
            for r in res['sweeps']:
                sdc = r.get('v_scope_dc', np.full(len(r['freq']), np.nan))
                if not np.isfinite(sdc).any():
                    continue
                c, m, ls = sty[r['key']]
                ax_sdc.plot(r['freq'], sdc, ls, color=c, marker=m, ms=5, lw=1.6, label=r['label'])
                ax_sdc.axhline(0, color=AXIS, lw=0.8)
            ax_sdc.set_ylabel('AC port DC voltage (V) [scope]\n(0 = ideal DC isolation)')
            if not large:
                ax_sdc.legend(fontsize=8, ncol=2 if len(res['sweeps']) > 4 else 1, **_lkw)
        if scope:                                    # harmonic distortion from the scope FFT (floor: 8-bit ADC)
            for ax, key, name in ((axes[-2], 'h2_dbc', 'Second'), (axes[-1], 'h3_dbc', 'Third')):
                for r in res['sweeps']:
                    if not np.isfinite(r[key]).any():
                        continue
                    c, m, ls = sty[r['key']]
                    ax.plot(r['freq'], r[key], ls, color=c, marker=m, ms=5, lw=1.6, label=r['label'])
                ax.set_ylabel('%s harmonic (dBc)\n(floor = scope noise)' % name)
        for ax in axes:
            ax.set_xscale('log')
            _style_axes(ax)
        axes[-1].set_xlabel('Frequency (Hz)')
        if large:
            h, l = ax1.get_legend_handles_labels()
            ncol = min(len(h), 5)
            n_rows = (len(h) + ncol - 1) // ncol
            fig.tight_layout(rect=(0, 0.018 * n_rows + 0.01, 1, 1))
            fig.legend(h, l, loc='lower center', ncol=ncol, fontsize=7, **_lkw)
        else:
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
            no_time_domain = True   # set False once a time-domain trace is plotted
            for r in res['sweeps']:
                pt = r['points'][i]
                if pt is None:
                    continue
                c, m, ls = sty[r['key']]
                if scope:
                    if pt['records']:   # raw codes available (live run); absent when loaded from H5
                        v = pt['records'][0].astype(float) * pt['vdiv'] / 25.0 - pt['ofst']
                        t = np.arange(len(v)) * pt['dt']
                        k = min(len(v), int(round(3.0 / f0 / pt['dt'])))      # first 3 periods
                        axes[ri, 0].plot(t[:k] * 1e6, v[:k], color=c, lw=1.0, label=r['label'])
                        no_time_domain = False
                    axes[ri, 1].plot(pt['spec_f'] / scale, pt['spec_dbm'], color=c, lw=1.0, label=r['label'])
                else:
                    axes[ri, 0].plot((pt['trace_f'] - pt['center_hz']) / 1e3, pt['trace_dbm'], color=c, lw=1.0, label=r['label'])
            ax_t = axes[ri, 0]
            if scope:
                if no_time_domain:
                    ax_t.text(0.5, 0.5, 'time series not stored\n(reprocessed from H5)',
                              transform=ax_t.transAxes, ha='center', va='center', fontsize=8, color=MUTED)
                ax_t.set_xlabel('Time (\u00b5s)')
                ax_t.set_ylabel('Scope voltage (V)\n(f = %g %s)' % (f0 / scale, unit))
                ax_s = axes[ri, 1]
                ax_s.set_xscale('log')
                ax_s.set_xlim(f0 / scale / 20, 20 * f0 / scale)
                ax_s.set_xlabel('Frequency (%s)' % unit)
                ax_s.set_ylabel('Spectrum (dBm into 50 \u03a9)\n[flat-top window, amplitude per bin]')
                # y-axis: cover the full dynamic range of the data, minimum -140 dBm
                all_dbm = [pt['spec_dbm'] for r in res['sweeps']
                           for pt in [r['points'][i]] if pt is not None and 'spec_dbm' in pt]
                ymin = min(-140.0, min(float(d.min()) for d in all_dbm) - 5) if all_dbm else -140.0
                ax_s.set_ylim(ymin, 10)
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
            ymin_fft = min(-110.0, float(pt['spec_dbm'].min()) - 5)
            axs.set_ylim(ymin_fft, 10)
            axs.set_xlabel('Frequency (%s)' % unit)
            axs.set_ylabel('Our FFT (dBm into 50 \u03a9)\n[flat-top window, amplitude per bin]')
            _style_axes(axs)
            dbvrms = pt['p_dbm'] - 10 * np.log10(1e3 / 50.0)             # dBm into 50 ohm -> dBV(rms)
            n_samp = pt.get('n_samples') or (pt['records'][0].size if pt['records'] else 0)
            n_rec  = pt.get('n_records') or len(pt['records'])
            axs.text(0.98, 0.97, 'tone %.3f %s\nP = %.2f dBm  =  %.2f dBVrms\nH2 %.0f dBc, H3 %.0f dBc\n'
                     '%d samples, dt = %.3g s\nflat-top window, mean of %d records' %
                     (pt['f_peak'] / scale, unit, pt['p_dbm'], dbvrms, pt['h2_dbc'], pt['h3_dbc'],
                      n_samp, pt['dt'], n_rec),
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
                         ('isolated', r.get('isolated', False)),
                         ('sweep_group', r.get('sweep_group', ''))):
                g.attrs[k] = _attr(v)
            g.create_dataset('frequency_Hz', data=r['freq'])
            g.create_dataset('p_dbm', data=r['p_dbm'])
            g.create_dataset('v_dc_V', data=r['v_dc'])
            g.create_dataset('v_scope_dc_V', data=r.get('v_scope_dc', np.full(len(r['freq']), np.nan)))
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
                q.attrs['v_scope_dc_V'] = float(pt.get('dc_from_scope_V', np.nan))
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
    entries = []   # (f0, sweep_group, spec_f, spec_dbm)
    for r in res['sweeps']:
        grp = r.get('sweep_group', 'tee_iso' if r.get('isolated') else 'tee_block')
        for i, pt in enumerate(r['points']):
            if pt is None or 'spec_f' not in pt:
                continue
            entries.append((r['freq'][i], grp, pt['spec_f'], pt['spec_dbm']))
    if not entries:
        return
    all_f0 = sorted(set(e[0] for e in entries))
    cmap = plt.cm.plasma
    f_color = {f: cmap(0.1 + 0.8 * i / max(len(all_f0) - 1, 1)) for i, f in enumerate(all_f0)}
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, ax = plt.subplots(figsize=(11, 5))
        fig.patch.set_facecolor(SURFACE)
        seen_f0 = set()
        for f0, grp, sf, sd in entries:
            c = f_color[f0]
            ls = _GROUP_LS.get(grp, '-')
            scale, unit = _hz_unit(f0)
            lbl = '%.4g %s' % (f0 / scale, unit) if f0 not in seen_f0 else None
            seen_f0.add(f0)
            ax.plot(sf, sd, ls, color=c, lw=0.7, alpha=0.65, label=lbl)
        ax.set_xscale('log')
        ax.set_xlim(min(cfg.FREQUENCIES_HZ), max(cfg.FREQUENCIES_HZ))
        ax.set_xlabel('Frequency (Hz)')
        ax.set_ylabel('Power (dBm into 50 \u03a9)')
        ax.set_ylim(-110, 10)
        ax.set_title(res['title'] + ' \u2013 all FFT spectra overlaid\n'
                     'colour = fundamental freq (light\u2192dark = low\u2192high); '
                     'line style: ref_direct=\u00b7\u00b7\u00b7, ref_EF500=-\u00b7-, tee+EF500=\u2014, tee_iso=\u2013\u2013',
                     color=INK, fontsize=10)
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
    """Stage 1 and 2: AC power change vs DC bias level for a selection of frequencies.

    One subplot per group (ref_dc, ref_ac, tee_block, tee_iso) — only present groups are shown.
    X-axis: SDG offset (V into 50 Ω).  Y-axis: ΔP vs 0 V sweep (dB).
    """
    if res.get('stage') not in (1, 2, 3):   # 3 = legacy three-stage data
        return

    # Collect sweeps by group; fall back to isolated flag for old files
    group_map = {}
    for r in res['sweeps']:
        grp = r.get('sweep_group', 'tee_iso' if r.get('isolated') else 'tee_block')
        group_map.setdefault(grp, []).append(r)

    _GROUP_ORDER = [('ref_dc',    'ref: direct (scope DC-coupled, no EF500, no tee)'),
                    ('ref_ac',    'ref: EF500 only (no tee, DC blocked)'),
                    ('tee_block', 'bias tee + EF500 DC block (AC-coupled)'),
                    ('tee_iso',   'bias tee isolation (no EF500, DC-coupled)')]
    groups = [(title, group_map[key]) for key, title in _GROUP_ORDER if len(group_map.get(key, [])) > 1]
    if not groups:
        return

    # Representative frequencies: at most 10, spread across first group's finite points
    first_sweeps = groups[0][1]
    freqs = np.array(cfg.FREQUENCIES_HZ)
    idx_all = np.where(np.isfinite(first_sweeps[0]['p_dbm']))[0]
    if len(idx_all) == 0:
        return
    step = max(1, len(idx_all) // 10)
    plot_idx = idx_all[::step]
    colors = _seq_colors(len(plot_idx))

    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, axes = plt.subplots(len(groups), 1, figsize=(9, 3.8 * len(groups) + 0.8),
                                 sharex=True, squeeze=False)
        fig.patch.set_facecolor(SURFACE)
        for ax, (grp_title, grp_sweeps) in zip(axes[:, 0], groups):
            dc = np.array([r['offset'] for r in grp_sweeps])
            ref_p = grp_sweeps[0]['p_dbm']   # 0 V sweep as reference
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
        if stage == 3:   # legacy 3-stage data: old stage 3 (AC+DC) = new stage 2
            stage = 2
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
                'sweep_group':  str(g.attrs.get('sweep_group', '')),
                'freq':         freq,
                'p_dbm':        g['p_dbm'][()] if 'p_dbm' in g else nan.copy(),
                'v_dc':         g['v_dc_V'][()] if 'v_dc_V' in g else nan.copy(),
                'v_scope_dc':   g['v_scope_dc_V'][()] if 'v_scope_dc_V' in g else nan.copy(),
                'snr_db':       g['snr_dB'][()] if 'snr_dB' in g else nan.copy(),
                'h2_dbc':       g['h2_dBc'][()] if 'h2_dBc' in g else nan.copy(),
                'h3_dbc':       g['h3_dBc'][()] if 'h3_dBc' in g else nan.copy(),
                'afg_readback': [None] * len(freq),
                'screenshots':  [],
                'points':       [None] * len(freq),
            }
            # Infer isolated/sweep_group from label for files written before these flags existed
            if not r['isolated'] and 'no block' in r['label']:
                r['isolated'] = True
            if not r['sweep_group']:
                if 'no block' in r['label']:
                    r['sweep_group'] = 'tee_iso'
                elif r['isolated']:
                    r['sweep_group'] = 'tee_iso'
                else:
                    r['sweep_group'] = 'tee_block'
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
                            'n_samples': int(q.attrs.get('n_samples', 0)),
                            'n_records': int(q.attrs.get('n_records', 0)),
                            'records':  [q['adc_codes_%d' % j][()] for j in range(int(q.attrs.get('n_records', 0)))
                                         if 'adc_codes_%d' % j in q],
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

        color_mode = 'sequential' if any(abs(r['offset']) > 0 for r in sweeps) else 'categorical'
        monitor_dc = stage >= 2
        what_map = {1: 'DC block insertion loss (EF500 vs direct) and change vs the 0 V sweep of each group',
                    2: 'Bias tee loss vs DC level (tee+EF500 vs EF500 ref; tee-only vs direct ref)'}
        res = {'stage': stage, 'title': title, 'sweeps': sweeps, 'pairs': pairs,
               'monitor_dc': monitor_dc, 'color_mode': color_mode,
               'what': what_map.get(stage, '')}

    # Recover on-disk screenshots so make_fft_check_report works when reprocessing.
    # The live run saves PNGs to <base>_screenshots/ next to the H5 file.
    # Tag format: <sweep_key>_<freq_Hz>Hz.png  e.g. direct_1000Hz.png
    h5_dir = os.path.dirname(os.path.abspath(h5_path))
    h5_stem = os.path.splitext(os.path.basename(h5_path))[0]
    for sfx in ('_PARTIAL_data', '_data', ''):
        if h5_stem.endswith(sfx):
            h5_stem = h5_stem[:-len(sfx)] if sfx else h5_stem
            break
    ss_folder = os.path.join(h5_dir, h5_stem + '_screenshots')
    if os.path.isdir(ss_folder):
        by_key = {r['key']: r for r in res['sweeps']}
        for png in sorted(os.listdir(ss_folder)):
            if not png.lower().endswith('.png'):
                continue
            stem = png[:-4]                         # strip .png
            try:
                # strip optional trailing instrument tag e.g. '_scope', '_esa'
                for _tag in ('_scope', '_fsw', '_ssa', '_esa'):
                    if stem.endswith(_tag):
                        stem = stem[:-len(_tag)]
                        break
                if not stem.endswith('Hz'):
                    continue
                skey, freq_str = stem.rsplit('_', 1)
                if not freq_str.endswith('Hz'):
                    continue
                freq_hz = float(freq_str[:-2])      # strip 'Hz'
                if skey not in by_key:
                    continue
                r = by_key[skey]
                idxs = np.where(np.abs(r['freq'] - freq_hz) < 1.0)[0]
                if len(idxs) == 0:
                    continue
                r['screenshots'].append({'index': int(idxs[0]), 'path': os.path.join(ss_folder, png)})
            except Exception:
                pass

    return cfg, res


# =============================================================================
# Run one stage and save everything
# =============================================================================

# =============================================================================
# ESA vs scope: the ESA's absolute level and the bias tee as seen by the ESA (SCOPE_REFERENCE_H5)
# =============================================================================

def load_scope_reference(path, freqs):
    """Scope stage-1/2 file -> ({(sweep_group, DC level): P dBm on freqs}, its VPP). Interpolated in log(f), NaN outside."""
    out = {}
    with h5py.File(path, 'r') as h:
        c = h['config'].attrs
        if str(c['MEASUREMENT']) != 'scope':
            raise ValueError('%s was not measured on the scope' % path)
        vpp = float(c['VPP'])
        for key in h['sweeps']:
            g = h['sweeps'][key]
            grp = str(g.attrs.get('sweep_group', ''))
            if grp in ('ref_ac', 'tee_block'):
                f, p = g['frequency_Hz'][()], g['p_dbm'][()]
                ok = np.isfinite(p)
                out[(grp, round(float(g.attrs.get('offset_V', 0.0)), 6))] = np.interp(
                    np.log10(freqs), np.log10(f[ok]), p[ok], left=np.nan, right=np.nan)
    return out, vpp


def compare_esa_with_scope(cfg, res):
    """ESA sweeps of this stage vs the same sweeps on the scope -> table dict (None if nothing to compare).

        ref_fsw_minus_scope       ref EF500 0 V: the ESA's absolute level (+ = ESA reads high = RIN reads high by as much)
        tee_<L>V_fsw_minus_scope  tee+EF500 at DC level L (sine + DC into the tee, DC port on the Keithley)
        tee_loss_<L>V_fsw / _scope / _diff   loss of the bias tee = ref EF500 0 V - tee+EF500 at L, on each receiver"""
    path = getattr(cfg, 'SCOPE_REFERENCE_H5', None)
    if not path:
        return None
    freqs = np.asarray(cfg.FREQUENCIES_HZ, float)
    scope, vpp = load_scope_reference(path, freqs)
    if abs(vpp - cfg.VPP) > 1e-6:
        print('WARNING: the scope reference was measured with VPP = %g V, this run with %g V - the levels differ by '
              '%.2f dB' % (vpp, cfg.VPP, 20 * np.log10(cfg.VPP / vpp)))
    esa = {(r.get('sweep_group'), round(float(r['offset']), 6)): r['p_dbm'] for r in res['sweeps']
           if r.get('sweep_group') in ('ref_ac', 'tee_block')}
    t = {'frequency_Hz': freqs}
    ref_e, ref_s = esa.get(('ref_ac', 0.0)), scope.get(('ref_ac', 0.0))
    if ref_e is not None and ref_s is not None:
        t['ref_fsw_dBm'], t['ref_scope_dBm'], t['ref_fsw_minus_scope_dB'] = ref_e, ref_s, ref_e - ref_s
    for (grp, lvl), p in sorted(esa.items(), key=lambda kv: kv[0][1]):
        if grp != 'tee_block' or (grp, lvl) not in scope:
            continue
        s, tag = scope[(grp, lvl)], 'tee_%.2fV' % lvl
        t[tag + '_fsw_minus_scope_dB'] = p - s
        if ref_e is not None and ref_s is not None:
            t[tag + '_loss_fsw_dB'], t[tag + '_loss_scope_dB'] = ref_e - p, ref_s - s
            t[tag + '_loss_diff_dB'] = (ref_e - p) - (ref_s - s)
    return t if len(t) > 1 else None


def print_esa_vs_scope(t):
    f = t['frequency_Hz']
    decades = [(a, 10 * a) for a in (1e3, 1e4, 1e5, 1e6)]
    head = ''.join('%14s' % ('%s-%s' % (_hz_text(a), _hz_text(b))) for a, b in decades)
    print('\nESA vs scope (dB, mean per decade)%s\n%-32s%s' % ('' if 'ref_fsw_minus_scope_dB' in t else
                                                           ' - no ESA ref EF500 0 V in this stage', '', head))
    for key in t:
        if key.endswith('_minus_scope_dB') or key.endswith('_loss_diff_dB'):
            vals = ''.join('%+14.2f' % np.nanmean(t[key][(f >= a) & (f <= b)]) for a, b in decades)
            print('%-32s%s' % (key, vals))
    if 'ref_fsw_minus_scope_dB' in t:
        print('  => ref_fsw_minus_scope = the error of the RIN measured with this ESA (+ = RIN too high), if the scope is '
              'right;\n     tee_x_loss_diff = how differently the ESA sees the bias tee at DC level x.')


def _hz_text(x):
    scale, unit = _hz_unit(x)
    return '%g%s' % (x / scale, unit)


def make_esa_vs_scope_report(cfg, t, title, base_path, show=False):
    f = t['frequency_Hz']
    tees = [k[:-len('_fsw_minus_scope_dB')] for k in t if k.startswith('tee_') and k.endswith('_fsw_minus_scope_dB')]
    ramp = _seq_colors(max(len(tees), 1))
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 7.0), sharex=True)
        fig.patch.set_facecolor(SURFACE)
        if 'ref_fsw_minus_scope_dB' in t:
            ax1.plot(f, t['ref_fsw_minus_scope_dB'], '-o', color=CATEGORICAL[1], ms=4, lw=2.0,
                     label='SDG -> EF500 (0 V): ESA absolute level')
        for c, tag in zip(ramp, tees):
            ax1.plot(f, t[tag + '_fsw_minus_scope_dB'], '-^', color=c, ms=3, lw=1.0, label='SDG -> tee -> EF500, %s' % tag[4:])
            if tag + '_loss_diff_dB' in t:
                ax2.plot(f, t[tag + '_loss_diff_dB'], '-^', color=c, ms=3, lw=1.2, label='DC %s' % tag[4:])
        ax1.set_ylabel('ESA - scope (dB)\n(+ = RIN reads high)')
        ax1.set_title(title, loc='left', color=INK, fontsize=10)
        ax2.set_ylabel('Bias tee loss: ESA - scope (dB)')
        ax2.set_xlabel('Frequency (Hz)')
        for ax in (ax1, ax2):
            ax.axhline(0, color=AXIS, lw=0.9)
            ax.set_xscale('log')
            _style_axes(ax)
            if ax.get_legend_handles_labels()[0]:
                ax.legend(fontsize=8, frameon=False, labelcolor=INK2)
        fig.tight_layout()
        for ext in ('pdf', 'svg'):
            fig.savefig('%s.%s' % (base_path, ext), bbox_inches='tight', facecolor=fig.get_facecolor())
            print('  Saved: %s.%s' % (base_path, ext))
        if show:
            plt.show()
        else:
            plt.close(fig)


def save_esa_vs_scope(cfg, t, run_folder, base, label, stage):
    """Print, <base>_vs_scope.csv / .pdf / .svg and the group 'esa_vs_scope' in <base>_data.h5."""
    print_esa_vs_scope(t)
    with open(os.path.join(run_folder, base + '_vs_scope.csv'), 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(list(t))
        for row in zip(*t.values()):
            w.writerow(['%.6g' % x for x in row])
    with h5py.File(os.path.join(run_folder, base + '_data.h5'), 'a') as hf:
        g = hf.create_group('esa_vs_scope')
        g.attrs['scope_reference'] = cfg.SCOPE_REFERENCE_H5
        g.attrs['doc'] = compare_esa_with_scope.__doc__
        for k, v in t.items():
            g.create_dataset(k, data=v)
    make_esa_vs_scope_report(cfg, t, 'Stage %d: %s vs scope   %s   %s\nscope reference: %s'
                             % (stage, RECEIVER_NAMES[cfg.MEASUREMENT], label, base[:19],
                                os.path.basename(cfg.SCOPE_REFERENCE_H5)),
                             os.path.join(run_folder, base + '_vs_scope'), show=cfg.SHOW_PLOTS)


def run_stage(S, stage, run_folder, label):
    """Run `stage`, then write  <timestamp>_stage<N>_data.h5 / .csv / _report.pdf / _report.svg / screenshots  to run_folder."""
    cfg = S.cfg
    base = '%s_stage%d' % (pic.datetimestring(), stage)
    S.begin_stage(run_folder, base)
    if stage == 3:                                   # DC only: no sweeps, own files
        return run_dc_stage(S, run_folder, base, label)
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
    S.prior_stage_results[stage] = res
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
    if not S.is_scope:
        try:
            t = compare_esa_with_scope(cfg, res)
            if t is not None:
                save_esa_vs_scope(cfg, t, run_folder, base, label, stage)
        except Exception as e:
            print('  warning: comparison with the scope reference failed (%s)' % e)
    print('\nStage %d saved in %s' % (stage, run_folder))
    with open(os.path.join(run_folder, base + '_log.txt'), 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(S.tee.lines[S.log_idx:]) + '\n')
    return res
