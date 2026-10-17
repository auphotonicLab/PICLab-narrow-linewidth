#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared helpers for rin_measurement.py (same split as bias_tee_characterization.py / bias_tee_utils.py).

rin_measurement.py holds the settings and runs the session; everything that talks to the instruments,
converts the readings to optical power / RIN and saves them lives here.

Contents
--------
EsaFSW / EsaSSA       one averaged noise sweep (RMS detector, power average) of an ESA
DcMonitor             Keithley 2450 as 0 A / high-Z voltmeter - only reset when it is NOT already in that state
RinSetup              the channels (PD + bias tee + ESA + Keithley), the safety prompts and one measurement
compute_rin           ESA trace + Keithley voltage -> optical power, optical noise PSD, RIN
run_measurement       one laser measurement, saved as h5 / csv / pdf / svg / log
load_background       laser-blocked traces of an earlier *_rin_data.h5 (so the laser need not be blocked every time)

Signal chain of one channel
    PD (50 ohm series output) -> bias tee -+- AC out -> DC block -> ESA (50 ohm, DC-coupled)
                                           +- DC out -> Keithley 2450 (0 A source, > 10 Gohm)
    DC: no current flows, the Keithley reads the OPEN-CIRCUIT (Hi-Z) PD voltage     V_dc = G R P_avg
    AC: the PD output resistor and the ESA input form a divider                      v_esa = v_oc r_in / (r_in + r_out)
    (G = transimpedance gain into Hi-Z [V/A], R = responsivity [A/W]; see compute_rin for the formulas.)
"""

import os
import csv
import glob
import json
import time
import shutil
import hashlib
from datetime import datetime
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import matplotlib.pyplot as plt
import h5py

import bias_tee_utils as bt

pic = bt.pic
config_from_globals = bt.config_from_globals

Q_E = 1.602176634e-19             # elementary charge (C)
_trapz = getattr(np, 'trapezoid', None) or np.trapz

CHANNEL_DEFAULTS = dict(name='PD1', esa='fsw', esa_ip='', keithley_ip='', pd_model='', wavelength_nm=None,
                        responsivity_A_W=None, transimpedance_V_A=None, pd_output_ohm=50.0, pd_max_hiz_V=10.0,
                        dark_offset_V=0.0, ac_path_loss_db=0.0, noise_bw_factor=1.065, pd_cal='ask', bias_tee_cal='ask')


class NotConfirmed(Exception):
    """A safety question was not answered with the confirmation word."""


# =============================================================================
# Config / prompts
# =============================================================================

def _protected_by_series_r(cfg, spec):
    """True if the declared series resistor keeps a shorted DC port below half the inductor rating."""
    r = float(cfg.DC_PORT_SERIES_R_OHM)
    return r > 0 and spec['pd_max_hiz_V'] / (r + spec['pd_output_ohm']) < 0.5 * cfg.INDUCTOR_MAX_A


def validate_config(cfg):
    if not cfg.CHANNELS:
        raise ValueError('CHANNELS is empty')
    if len(cfg.CHANNELS) > len(bt.CATEGORICAL):
        raise ValueError('At most %d channels (one plot colour each)' % len(bt.CATEGORICAL))
    chans = []
    for spec in cfg.CHANNELS:
        unknown = set(spec) - set(CHANNEL_DEFAULTS)
        if unknown:
            raise ValueError('Unknown channel setting(s) %s; allowed: %s' % (sorted(unknown), sorted(CHANNEL_DEFAULTS)))
        full = dict(CHANNEL_DEFAULTS, **spec)
        if full['esa'] not in ESA_CLASSES:
            raise ValueError("Channel %s: esa must be one of %s, got %r" % (full['name'], list(ESA_CLASSES), full['esa']))
        if not full['esa_ip'] or not full['keithley_ip']:
            raise ValueError('Channel %s: set esa_ip and keithley_ip' % full['name'])
        if bt.safe_name(full['name']) != full['name']:
            raise ValueError('Channel name %r must only contain letters, digits and . _ + -' % full['name'])
        chans.append(full)
    cfg.CHANNELS = chans                                   # with all defaults filled in (this is what gets saved)
    for key in ('name', 'esa_ip', 'keithley_ip'):
        vals = [c[key] for c in chans]
        if len(set(vals)) != len(vals):
            raise ValueError('Every channel needs its own %s, got %s' % (key, vals))

    segs = []
    for s in cfg.ESA_SEGMENTS:
        s = tuple(float(x) for x in s)
        if len(s) == 3:
            s += (10 * s[2],)                              # VBW default: 10 x RBW
        if len(s) != 4:
            raise ValueError('ESA_SEGMENTS entries are (start Hz, stop Hz, RBW Hz[, VBW Hz]), got %r' % (s,))
        segs.append(s)
    if not segs:
        raise ValueError('ESA_SEGMENTS is empty')
    if not 101 <= cfg.ESA_POINTS <= 100001:
        raise ValueError('ESA_POINTS must be 101 ... 100001 (FSW limit), got %r' % (cfg.ESA_POINTS,))
    if cfg.N_MEASUREMENTS < 1:
        raise ValueError('N_MEASUREMENTS must be >= 1')
    for key in ('ASK_DC_BLOCK_EVERY_START', 'RESET_KEITHLEY_EVERY_START', 'BACKGROUND_EVERY_START', 'COMPARE_HIGHFINESSE'):
        if not isinstance(getattr(cfg, key), bool):
            raise ValueError('%s must be True or False, got %r' % (key, getattr(cfg, key)))
    for i, (f0, f1, rbw, vbw) in enumerate(segs):
        if not (0 < f0 < f1 and rbw > 0 and vbw > 0):
            raise ValueError('ESA_SEGMENTS[%d] = %r: need 0 < start < stop and RBW, VBW > 0' % (i, segs[i]))
        if i and f0 < segs[i - 1][1]:
            raise ValueError('ESA_SEGMENTS must be sorted and must not overlap (segment %d starts below the stop of %d)' % (i, i - 1))
        if rbw > f0 / 10.0:
            print('WARNING: segment %d: RBW %g Hz is more than 1/10 of the start frequency %g Hz - the 0 Hz (LO) peak and '
                  'the poor resolution will distort the low end.' % (i, rbw, f0))
    cfg.ESA_SEGMENTS = segs
    if cfg.COMPARE_HIGHFINESSE and not cfg.BINS_PER_DECADE:
        raise ValueError('COMPARE_HIGHFINESSE needs BINS_PER_DECADE > 0 (both RIN spectra are compared in the same bins)')

    need = 1.2 * max(c['pd_max_hiz_V'] for c in chans) + 1.0
    if cfg.KEITHLEY_VLIM_V < need:
        raise ValueError('KEITHLEY_VLIM_V = %g V must be above %.1f V (1.2 x PD maximum + 1 V): an external voltage above '
                         'the limit makes the 2450 draw current.' % (cfg.KEITHLEY_VLIM_V, need))
    if cfg.BACKGROUND not in ('measure', 'none') and not os.path.isfile(cfg.BACKGROUND):
        raise ValueError("BACKGROUND must be 'measure', 'none' or the path of an earlier *_rin_data.h5, got %r" % (cfg.BACKGROUND,))
    for c in chans:
        if c['pd_cal'] is None and (c['responsivity_A_W'] is None or c['transimpedance_V_A'] is None):
            print('NOTE: channel %s: responsivity_A_W / transimpedance_V_A not set - RIN is still correct (both cancel), but '
                  'the optical powers%s cannot be given.'
                  % (c['name'], '' if c['transimpedance_V_A'] else ' and the shot-noise limit'))


def confirm(msg, word='yes'):
    """Safety question that needs the typed word (ENTER alone is not enough). Anything else raises NotConfirmed."""
    bt.PROMPT_LOG.append((datetime.now().isoformat(), msg))
    print('\n' + '=' * 78)
    print(msg)
    ans = input("Type '%s' + ENTER to confirm (anything else aborts): " % word).strip().lower()
    bt.PROMPT_LOG.append((datetime.now().isoformat(), 'answer: %r' % ans))
    if ans != word:
        raise NotConfirmed('Not confirmed (answer %r) - nothing was switched, aborting.' % ans)


def ask_next(cfg, label, n):
    """After a series: None = quit and close the session, 'k' = quit and keep it, 'b' = new background,
    else (label, number of measurements) of the next series."""
    print('\n' + '=' * 78)
    print("Next (electrical wiring UNCHANGED - if you touch the RF / DC cabling, quit with q):\n"
          "    ENTER      %d more with label '%s'\n"
          "    <number>   that many more              <text>   new label\n"
          "    b          re-measure the background\n"
          "    k          quit, KEEP the session open: the next start (within %g h) does not ask again\n"
          "    q          quit and CLOSE the session: the next start asks everything again"
          % (n, label, cfg.SESSION_TIMEOUT_H))
    ans = input('  > ').strip()
    if ans.lower() in ('q', 'quit', 'exit'):
        return None
    if ans.lower() in ('k', 'b'):
        return ans.lower()
    if ans.isdigit():
        return label, max(int(ans), 1)
    return bt.safe_name(ans) or label, n


def _snapshot(instr, cmds):
    """Read back instrument settings (queries only; never changes anything)."""
    d = {}
    for c in cmds:
        try:
            d[c] = str(instr.query(c)).strip()
        except Exception as e:
            d[c] = '<query failed: %s>' % str(e).splitlines()[0][:80]
            try:
                instr.clear()
            except Exception:
                pass
    return d


def _hz(x):
    for lim, unit in ((1e6, 'MHz'), (1e3, 'kHz')):
        if x >= lim:
            return '%g %s' % (x / lim, unit)
    return '%g Hz' % x


# =============================================================================
# ESAs: one averaged noise sweep
# =============================================================================

class _Esa:
    """What the RIN measurement needs from an ESA. Detector RMS + POWER averaging, so the trace is true mean power
    in the RBW filter and no log-averaging correction is needed."""
    kind, min_freq_hz, has_coupling = '', 0.0, False
    queries = []

    def __init__(self, drv, timeout_ms):
        self.drv, self.instr = drv, drv.instr
        self.instr.timeout = timeout_ms
        self.idn = self.instr.query('*IDN?').strip()
        self.navg = 1

    def errors(self):
        """Empty the SCPI error queue -> list of messages (a rejected command shows up here)."""
        out = []
        for _ in range(20):
            try:
                e = self.instr.query('SYST:ERR?').strip()
            except Exception as ex:
                out.append('<SYST:ERR? failed: %s>' % str(ex).splitlines()[0][:80])
                break
            if e.split(',')[0].strip().lstrip('+-') in ('0', ''):
                break
            out.append(e)
        return out

    def snapshot(self):
        return _snapshot(self.instr, self.queries)

    def overload(self):
        return None


class EsaFSW(_Esa):
    """R&S FSW (spectrum mode). DC coupling is needed below ~10 MHz - the input must then be protected from DC."""
    kind, min_freq_hz, has_coupling = 'fsw', 10.0, True
    queries = ['*IDN?', 'INP:COUP?', 'INP:ATT?', 'INP:ATT:AUTO?', 'DISP:TRAC:Y:RLEV?', 'FREQ:STAR?', 'FREQ:STOP?', 'BAND?',
               'BAND:VID?', 'SWE:POIN?', 'SWE:COUN?', 'SWE:TIME?', 'SWE:TYPE?', 'DET?', 'DISP:TRAC1:MODE?', 'AVER:TYPE?',
               'CALC:UNIT:POW?']
    session_queries = ['INP:COUP?', 'INP:ATT?', 'DISP:TRAC:Y:RLEV?', 'FREQ:STAR?', 'FREQ:STOP?', 'BAND?', 'BAND:VID?',
                       'SWE:POIN?', 'SWE:COUN?', 'DET?', 'DISP:TRAC1:MODE?', 'AVER:TYPE?']

    def __init__(self, ip, timeout_ms):
        super().__init__(pic.ESA_RS_FSW50(IP_address=ip), timeout_ms)       # no reset, coupling untouched

    def get_coupling(self):
        return self.drv.GetCoupling()

    def set_coupling(self, coupling):
        self.drv.SetCoupling(coupling)
        got = self.get_coupling()
        if got != coupling:
            raise RuntimeError('ESA coupling is %s, wanted %s' % (got, coupling))

    def setup(self, cfg):
        """Everything that is the same for all segments."""
        w = self.instr.write
        w('INIT:CONT OFF')
        w('CALC:UNIT:POW DBM')
        w('DISP:TRAC:Y:RLEV %g' % cfg.ESA_REF_LEVEL_DBM)
        w('DISP:TRAC:Y 150DB')                              # display only: the noise trace is ~100 dB below the reference
        w('DISP:TRAC:Y:RPOS 100PCT')                        # level, without this the screenshot shows an empty grid
        w('INP:ATT:AUTO ON' if cfg.ESA_ATTEN_DB is None else 'INP:ATT %g' % cfg.ESA_ATTEN_DB)
        w('SWE:TYPE %s' % cfg.ESA_SWEEP_TYPE)
        w('SWE:TIME:AUTO ON')
        w('DET RMS')
        w('DISP:TRAC1:MODE AVER')
        w('AVER:TYPE POW')

    def configure(self, f0, f1, rbw, vbw, npts, navg):
        w, q = self.instr.write, self.instr.query
        self.navg = navg
        w('FREQ:STAR %.3f HZ' % f0)
        w('FREQ:STOP %.3f HZ' % f1)
        w('BAND %.3f HZ' % rbw)
        w('BAND:VID %.3f HZ' % vbw)
        w('SWE:POIN %d' % npts)
        w('SWE:COUN %d' % navg)                             # single sweep = navg sweeps, power-averaged
        return {'start_hz': float(q('FREQ:STAR?')), 'stop_hz': float(q('FREQ:STOP?')), 'rbw_hz': float(q('BAND?')),
                'vbw_hz': float(q('BAND:VID?')), 'sweep_time_s': float(q('SWE:TIME?'))}

    def acquire(self):
        self.instr.write('INIT')
        self.instr.query('*OPC?')                            # returns when all navg sweeps are done
        return np.array(self.instr.query_binary_values('FORM REAL,32;:TRAC? TRACE1'), float)

    def overload(self):
        """STATus:QUEStionable:POWer condition register (non-zero = RF / IF overload); None if it cannot be read."""
        try:
            return int(float(self.instr.query('STAT:QUES:POW:COND?')))
        except Exception:
            return None


class EsaSSA(_Esa):
    """Siglent SSA3021X (starts at 9 kHz, no coupling command).  NOT TESTED on the instrument: the commands are from the
    SSA3000X programming guide; check the error messages printed at the first run."""
    kind, min_freq_hz, has_coupling = 'ssa', 9e3, False
    queries = ['*IDN?', ':FREQ:STAR?', ':FREQ:STOP?', ':DISP:WIND:TRAC:Y:SCAL:RLEV?', ':POW:ATT?', ':BWID?', ':BWID:VID?',
               ':UNIT:POW?', ':SWE:TIME?', ':DET:TRAC1:FUNC?', ':TRAC1:MODE?', ':AVER:TYPE?', ':AVER:TRAC1:COUN?']
    session_queries = [':FREQ:STAR?', ':FREQ:STOP?', ':DISP:WIND:TRAC:Y:SCAL:RLEV?', ':POW:ATT?', ':BWID?',
                       ':DET:TRAC1:FUNC?', ':TRAC1:MODE?', ':AVER:TYPE?', ':AVER:TRAC1:COUN?']

    def __init__(self, ip, timeout_ms):
        super().__init__(pic.ESA_SIGLENT(IP_address=ip, USB_interface=-1), timeout_ms)

    def setup(self, cfg):
        w = self.instr.write
        w(':INIT:CONT OFF')
        w(':UNIT:POW DBM')
        w(':DISP:WIND:TRAC:Y:SCAL:RLEV %g' % cfg.ESA_REF_LEVEL_DBM)
        w(':POW:ATT:AUTO ON' if cfg.ESA_ATTEN_DB is None else ':POW:ATT %g' % cfg.ESA_ATTEN_DB)
        w(':DET:TRAC1:FUNC AVER')                           # 'average' detector = RMS
        w(':TRAC1:MODE AVER')
        w(':AVER:TYPE POW')

    def configure(self, f0, f1, rbw, vbw, npts, navg):
        w, q = self.instr.write, self.instr.query
        self.navg = navg
        w(':FREQ:STAR %.3f Hz' % f0)
        w(':FREQ:STOP %.3f Hz' % f1)
        w(':BWID %.3f Hz' % rbw)
        w(':BWID:VID %.3f Hz' % vbw)
        w(':AVER:TRAC1:COUN %d' % navg)
        return {'start_hz': float(q(':FREQ:STAR?')), 'stop_hz': float(q(':FREQ:STOP?')), 'rbw_hz': float(q(':BWID?')),
                'vbw_hz': float(q(':BWID:VID?')), 'sweep_time_s': float(q(':SWE:TIME?'))}

    def acquire(self):
        self.instr.write(':AVER:TRAC1:CLE')
        for _ in range(self.navg):
            self.instr.write(':INIT:IMM')
            self.instr.query('*OPC?')
        return np.array([v for v in self.instr.query(':TRAC:DATA? 1').split(',') if v.strip() != ''], float)


ESA_CLASSES = {'fsw': EsaFSW, 'ssa': EsaSSA}


# =============================================================================
# Keithley 2450 as DC monitor - without a reset whenever possible
# =============================================================================

class DcMonitor:
    """Keithley 2450 on the bias tee DC port: 0 A source = > 10 Gohm voltmeter.

    The only dangerous moment is the *RST (the default output-off state is a 0 V source = near short on the 9 mA
    inductor).  So the state is READ at every start and the reset (with its unplug question) is skipped when the 2450
    already is a 0 A / high-Z voltmeter: the banana cables then stay plugged in.  The script never switches the output
    off and never resets at exit, so every start after the first one finds the 2450 ready - also in a new session."""
    queries = ['*IDN?', ':ROUT:TERM?', ':OUTP?', ':SOUR:FUNC?', ':SOUR:CURR?', ':SOUR:CURR:VLIM?', ':OUTP:CURR:SMOD?',
               ':SENS:FUNC?', ':SENS:VOLT:NPLC?', ':SENS:VOLT:RANG:AUTO?', ':SENS:VOLT:RANG?', ':SENS:VOLT:RSEN?']
    session_queries = [':ROUT:TERM?', ':OUTP?', ':SOUR:FUNC?', ':SOUR:CURR?', ':SOUR:CURR:VLIM?', ':OUTP:CURR:SMOD?',
                       ':SENS:FUNC?', ':SENS:VOLT:NPLC?', ':SENS:VOLT:RANG:AUTO?', ':SENS:VOLT:RSEN?']

    def __init__(self, cfg, spec):
        self.cfg, self.name, self.spec = cfg, spec['name'], spec
        self.k = pic.DC_KEITHLEY_2450(channel=21, GPIB_interface=-1, IP_address=spec['keithley_ip'])   # *IDN? / :OUTP? only
        self.instr = self.k.instr
        self.idn = self.instr.query('*IDN?').strip()
        self.state_at_start = _snapshot(self.instr, self.session_queries)     # as found, for the session check
        self.was_reset = False

    def highz_problems(self):
        """Everything that is not '0 A source, high-Z output-off state, 2-wire voltage measurement' (queries only)."""
        bad = []

        def check(cmd, ok, text):
            try:
                reply = self.instr.query(cmd).strip().upper()
                if not ok(reply):
                    bad.append('%s (%s -> %s)' % (text, cmd, reply))
            except Exception as e:
                bad.append('%s (%s failed: %s)' % (text, cmd, str(e).splitlines()[0][:60]))
                try:
                    self.instr.clear()
                except Exception:
                    pass
        check(':SOUR:FUNC?', lambda r: r.startswith('CURR'), 'source function is not CURRENT')
        check(':SOUR:CURR?', lambda r: float(r) == 0.0, 'source current is not 0 A')
        check(':SOUR:CURR:VLIM?', lambda r: float(r) >= self.cfg.KEITHLEY_VLIM_V - 1e-3,
              'voltage limit is below %g V' % self.cfg.KEITHLEY_VLIM_V)
        check(':OUTP:CURR:SMOD?', lambda r: r.startswith('HIMP'), 'output-off state is not HIGH-Z')
        check(':SENS:FUNC?', lambda r: 'VOLT' in r, 'measure function is not VOLTAGE')
        check(':SENS:VOLT:RSEN?', lambda r: r in ('0', 'OFF'), '4-wire sense is on')
        return bad

    def prepare(self, force_reset=False, why_forced=''):
        """force_reset: reset even if the 2450 is in high-Z mode (RESET_KEITHLEY_EVERY_START).
        Without it the reset (and its unplug question) only happens when the 2450 is NOT in high-Z mode - and then
        ALWAYS: that is the one case in which the question protects the bias tee."""
        cfg = self.cfg
        bad = self.highz_problems()
        if not bad and not force_reset:
            print('Keithley [%s]: already a 0 A / high-Z voltmeter -> NOT reset, the cables stay connected.' % self.name)
        else:
            if bad:
                why = 'is NOT in high-Z voltmeter mode:\n' + '\n'.join('      - ' + b for b in bad)
            else:
                why = 'is reset to a known state (%s).' % why_forced
            if _protected_by_series_r(cfg, self.spec):
                print('Keithley [%s] %s\n  -> reset now. The %g ohm series resistor (DC_PORT_SERIES_R_OHM) keeps this '
                      'harmless, the cables stay connected.' % (self.name, why, cfg.DC_PORT_SERIES_R_OHM))
            else:
                bt.ask('Keithley [%s] %s\n'
                       '  During the reset (*RST) its output-off state is briefly NORMAL (= near short), so UNPLUG the\n'
                       '  banana cables from the bias tee DC port now.' % (self.name, why))
            self.k.SetHighZVoltmeter(vlim=cfg.KEITHLEY_VLIM_V, nplc=cfg.KEITHLEY_NPLC)        # *RST + configure + AssertHighZ
            self.was_reset = True
            if cfg.KEITHLEY_STORE_POWER_ON:
                self.instr.write('*SAV 0')
                self.instr.write(':SYST:POS SAV0')
                print('Keithley [%s]: high-Z voltmeter setup stored as power-on state (*SAV 0, :SYST:POS SAV0).' % self.name)
        self.instr.write(':SENS:VOLT:RANG:AUTO ON')        # measurement-only settings: no effect on the impedance
        self.instr.write(':SENS:VOLT:REL:STAT OFF')        # no reset = clear what would falsify the DC reading:
        self.instr.write(':SENS:VOLT:AVER:STAT OFF')       # a relative offset or filter left on by somebody else
        self.instr.write(':SENS:VOLT:NPLC %g' % cfg.KEITHLEY_NPLC)
        self.k.AssertHighZ()
        self.k.SwitchOn()                                  # 0 A source ON = voltmeter; stays on from now on
        err = _snapshot(self.instr, [':SYST:ERR?'])[':SYST:ERR?']
        if not err.lstrip('+-').startswith('0'):
            print('  WARNING: Keithley [%s] reports: %s' % (self.name, err))
        try:
            print('Keithley [%s] terminals in use: %s' % (self.name, self.instr.query(':ROUT:TERM?').strip()))
        except Exception:
            pass
        if self.was_reset and not _protected_by_series_r(cfg, self.spec):
            bt.ask('Keithley [%s] is now a 0 A / high-Z voltmeter.\n'
                   '  Reconnect:  bias tee DC output  ->  Keithley HI / LO (the terminals printed above).' % self.name)

    def read(self, n=None):
        """Mean and standard deviation of n readings (V). High-Z state is asserted first."""
        self.k.AssertHighZ()
        if int(self.instr.query(':OUTP?')) != 1:           # somebody pressed OUTPUT: 0 A source back on (still high-Z)
            self.k.SwitchOn()
        vals = np.array([self.k.GetMeas() for _ in range(n or self.cfg.KEITHLEY_NREAD)], float)
        v = float(np.mean(vals))
        if abs(v) > self.spec['pd_max_hiz_V'] + 1.0:
            raise RuntimeError('Keithley [%s] reads %.2f V - above any PD level. Cables not connected to the bias tee DC '
                               'port (an open input drifts to the voltage limit) or wrong terminals?' % (self.name, v))
        return v, float(np.std(vals))

    def snapshot(self):
        return _snapshot(self.instr, self.queries)


# =============================================================================
# AC path calibration (bias tee + DC block)
# =============================================================================

def load_tee_loss_h5(path):
    """AC path loss of bias tee + DC block from a stage-2 file of bias_tee_characterization.py.

    loss(f) [dB, positive] = P('ref direct', 0 V) - mean over the DC levels of P('tee+EF500')  -> (f_Hz, loss_dB)"""
    ref, tees = None, []
    with h5py.File(path, 'r') as hf:
        for key in hf['sweeps']:
            g = hf['sweeps'][key]
            group = str(g.attrs.get('sweep_group', ''))
            if group == 'ref_dc' and abs(float(g.attrs.get('offset_V', 0.0))) < 1e-12:
                ref = (g['frequency_Hz'][()], g['p_dbm'][()])
            elif group == 'tee_block':
                tees.append(g['p_dbm'][()])
    if ref is None or not tees:
        raise ValueError("%s: need the sweep groups 'ref_dc' (0 V) and 'tee_block' - use the stage 2 file of a "
                         "STAGES_TO_RUN = [1, 2] run" % path)
    tees = np.array(tees, float)
    ok = np.isfinite(ref[1]) & np.isfinite(tees).any(axis=0)
    loss = ref[1][ok] - np.nanmean(tees[:, ok], axis=0)
    return ref[0][ok], loss


def ac_path_loss(spec):
    """Channel setting ac_path_loss_db -> (function f_Hz -> loss in dB (positive = AC path attenuates), description).

    Allowed: a number (dB, same at all frequencies), (frequencies_Hz, loss_dB) or the path of a stage-2 h5 file.
    Tables are interpolated in log(f) and held constant outside their range."""
    if spec is None or isinstance(spec, (int, float)):
        val = float(spec or 0.0)
        return (lambda f: np.full(np.shape(f), val)), 'constant %g dB' % val
    if isinstance(spec, str):
        ft, lt = load_tee_loss_h5(spec)
        text = 'bias tee characterization %s (%.2f ... %.2f dB)' % (os.path.basename(spec), lt.min(), lt.max())
    else:
        ft, lt = np.asarray(spec[0], float), np.asarray(spec[1], float)
        text = 'table, %d points (%.2f ... %.2f dB)' % (len(ft), lt.min(), lt.max())
    order = np.argsort(ft)
    lf, lt = np.log10(ft[order]), lt[order]
    return (lambda f: np.interp(np.log10(f), lf, lt)), text


# =============================================================================
# Calibrations: photodetector (V per W) and bias tee (AC loss, DC reading)
# =============================================================================

def _newest(folder, pattern):
    files = glob.glob(os.path.join(folder, pattern)) if folder and os.path.isdir(folder) else []
    return max(files, key=os.path.getmtime) if files else ''


def _ask_path(title, initialdir, pattern=None):
    """File pop-up (pattern given, the newest match pre-selected) or folder pop-up (pattern None). '' = cancelled.
    Falls back to a console prompt if no display is available."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        if pattern:
            newest = _newest(initialdir, pattern)
            path = filedialog.askopenfilename(title=title, initialdir=initialdir or None, parent=root,
                                              initialfile=os.path.basename(newest),
                                              filetypes=[(pattern, pattern), ('all files', '*.*')])
        else:
            path = filedialog.askdirectory(title=title, initialdir=initialdir or None, mustexist=True, parent=root)
        root.destroy()
        return os.path.normpath(path) if path else ''
    except Exception as e:
        print('(pop-up not available: %s)' % e)
        return input('%s\n  path (empty = none): ' % title).strip().strip('"')


def load_pd_cal(path):
    """Photodetector characterization (Photodetector/photodetector_characterization.py, *.h5) -> dict.

    Uses its measured gain V_net / P_detector [V/W] (P = power out of the fibre onto the detector, incl. any coupling
    loss) and its TIA gain [V/A] (for the photocurrent / shot noise). It must have been measured into Hi-Z, like the
    Keithley reads the DC port here."""
    with h5py.File(path, 'r') as h:
        r = h['results'].attrs if 'results' in h else {}
        if 'gain_V_per_W' not in r:
            raise ValueError('%s has no fit result (%s) - choose another run' % (os.path.basename(path),
                                                                                h.attrs.get('analysis_error', 'no results')))
        load = str(h.attrs.get('load', '?'))
        if load.replace(' ', '').lower() != 'hiz':
            raise ValueError('%s was measured into %s; the Keithley reads Hi-Z - choose a HiZ characterization'
                             % (os.path.basename(path), load))
        num = lambda x: float(x) if x is not None and str(x) not in ('None', 'nan', '') else np.nan
        v_per_w, tia = num(r['gain_V_per_W']), num(h.attrs.get('tia_gain_V_per_A'))
        p_comp = num(r.get('P_comp_W'))
        cal = {'pd_file': os.path.normpath(path), 'v_per_w': v_per_w, 'tia_v_per_a': tia if np.isfinite(tia) else None,
               'pd_wavelength_nm': num(h.attrs.get('wavelength_nm')), 'pd_dut': str(h.attrs.get('dut', '')),
               # highest voltage known to be linear: the 1 % compression point if one was found, else the largest one measured
               'v_linear_max': p_comp * v_per_w if np.isfinite(p_comp) else num(r.get('V_max'))}
    cal['pd_text'] = ('%s: %.4g V/mW%s, linear to %.2f V (%s)'
                      % (cal['pd_dut'] or 'detector', v_per_w / 1e3,
                         ', TIA %g V/A -> %.3f A/W' % (tia, v_per_w / tia) if cal['tia_v_per_a'] else '',
                         cal['v_linear_max'], os.path.basename(path)))
    return cal


def load_dc_cal_h5(path):
    """Stage 3 of the bias tee characterization -> (function V_through_tee -> tee / direct ratio, description)."""
    with h5py.File(path, 'r') as h:
        t = {k: h['table'][k][()] for k in h['table']}
    ok = np.isfinite(t['tee_mean_V']) & np.isfinite(t['direct_mean_V']) & (np.abs(t['direct_mean_V']) > 0.1)
    if not ok.any():
        raise ValueError('%s: no level with both a direct and a through-the-tee reading' % os.path.basename(path))
    vt, ratio = t['tee_mean_V'][ok], t['tee_mean_V'][ok] / t['direct_mean_V'][ok]
    order = np.argsort(vt)
    vt, ratio = vt[order], ratio[order]
    return (lambda v: np.interp(v, vt, ratio)), ('reading through the tee / direct = %.5f ... %.5f (%s)'
                                                 % (ratio.min(), ratio.max(), os.path.basename(path)))


def load_bias_tee_cal(path):
    """Bias tee characterization folder (newest *_stage2_data.h5 = AC loss, newest *_stage3_data.h5 = DC reading) or
    one stage-2 file -> dict."""
    if os.path.isdir(path):
        s2, s3 = _newest(path, '*_stage2_data.h5'), _newest(path, '*_stage3_data.h5')
        if not s2:
            raise ValueError('no *_stage2_data.h5 in %s' % path)
    else:
        s2, s3 = path, ''
    loss_fn, loss_text = ac_path_loss(s2)
    dc_ratio, dc_text = load_dc_cal_h5(s3) if s3 else (None, 'not corrected (no stage 3 in %s)' % os.path.basename(path))
    return {'bias_tee_source': os.path.normpath(path), 'stage2_file': s2, 'stage3_file': s3 or None,
            'loss_fn': loss_fn, 'loss_text': loss_text, 'dc_ratio': dc_ratio, 'dc_text': dc_text}


def resolve_calibrations(cfg, spec, kept=None):
    """Channel settings pd_cal / bias_tee_cal -> one calibration dict for compute_rin.

        'ask'  pop-up (Cancel = none). In a continued session the choice made when it was opened (`kept`) is reused.
        path   used as it is (errors stop the script)
        None   manual settings: responsivity_A_W x transimpedance_V_A, ac_path_loss_db, no DC correction"""
    name = spec['name']
    kept = kept or {}
    cal = {}

    def choose(key, title, folder, pattern, loader):
        setting = spec[key]
        if setting != 'ask':
            return loader(setting) if setting else None
        if key in kept and (kept[key] == '' or os.path.exists(kept[key])):
            print('[%s] %s: the choice of this session is used (%s)' % (name, key, kept[key] or 'none'))
            return loader(kept[key]) if kept[key] else None
        for _ in range(3):
            path = _ask_path(title, folder, pattern)
            if not path:
                print('[%s] %s: none chosen' % (name, key))
                return None
            try:
                return loader(path)
            except Exception as e:
                print('[%s] %s: %s' % (name, key, e))
        return None

    pd = choose('pd_cal', 'RIN [%s]: photodetector characterization (*_HiZ.h5) - Cancel = use responsivity_A_W x '
                          'transimpedance_V_A' % name, getattr(cfg, 'PD_CAL_FOLDER', ''), '*_HiZ.h5', load_pd_cal)
    if pd is None:
        G, R = spec['transimpedance_V_A'], spec['responsivity_A_W']
        pd = {'pd_file': None, 'v_per_w': float(G) * float(R) if (G and R) else np.nan, 'tia_v_per_a': G or None,
              'pd_wavelength_nm': np.nan, 'pd_dut': spec['pd_model'], 'v_linear_max': np.inf,
              'pd_text': ('settings: %g A/W x %g V/A' % (R, G)) if (G and R) else
                         'none - RIN is still right (K cancels), but no optical power%s' % ('' if G else ' / shot noise')}
    cal.update(pd)
    if pd['pd_file'] and spec['pd_model'] and spec['pd_model'] != pd['pd_dut']:
        print('WARNING [%s]: the detector calibration is for %s, pd_model is %s - the V/mW depends on the fibre adapter, '
              'so the optical power is only right for the same adapter (RIN is not affected)' % (name, pd['pd_dut'], spec['pd_model']))
    wl = spec['wavelength_nm']
    if wl and np.isfinite(cal['pd_wavelength_nm']) and abs(wl - cal['pd_wavelength_nm']) > 1:
        print('WARNING [%s]: the detector was characterized at %g nm, the laser is at %g nm' % (name, cal['pd_wavelength_nm'], wl))

    folder = getattr(cfg, 'BIAS_TEE_CAL_FOLDER', '')
    newest_run = os.path.dirname(_newest(folder, os.path.join('*', '*_stage2_data.h5'))) or folder   # dialog opens there
    tee = choose('bias_tee_cal', 'RIN [%s]: bias tee characterization FOLDER (stage 2 = AC loss, stage 3 = DC) - '
                                 'Cancel = ac_path_loss_db' % name, newest_run, None, load_bias_tee_cal)
    if tee is None:
        fn, text = ac_path_loss(spec['ac_path_loss_db'])
        tee = {'bias_tee_source': None, 'stage2_file': None, 'stage3_file': None, 'loss_fn': fn,
               'loss_text': 'ac_path_loss_db: ' + text, 'dc_ratio': None, 'dc_text': 'not corrected'}
    cal.update(tee)
    return cal


# =============================================================================
# Channels, safety prompts, one measurement
# =============================================================================

class Channel:
    def __init__(self, cfg, spec):
        self.spec, self.name = spec, spec['name']
        self.cal = None                                    # calibrations, filled by RinSetup._resolve_calibrations
        self.esa = ESA_CLASSES[spec['esa']](spec['esa_ip'], cfg.ESA_TIMEOUT_MS)
        print('ESA [%s]: %s' % (self.name, self.esa.idn))
        self.esa_state_at_start = _snapshot(self.esa.instr, self.esa.session_queries)   # as found, for the session check
        self.coupling_at_start = None
        if self.esa.has_coupling:                          # safe state until the DC block is confirmed
            self.coupling_at_start = self.esa.get_coupling()
            self.esa.set_coupling('AC')
            print('ESA [%s]: input found %s-coupled; kept AC-coupled until the DC block is confirmed.'
                  % (self.name, self.coupling_at_start))
        self.dc = DcMonitor(cfg, spec)

    def segments(self, cfg):
        """ESA_SEGMENTS clipped to what this ESA can do -> [(index, start, stop, rbw, vbw)]."""
        out = []
        for i, (f0, f1, rbw, vbw) in enumerate(cfg.ESA_SEGMENTS):
            if f1 <= self.esa.min_freq_hz:
                continue
            out.append((i, max(f0, self.esa.min_freq_hz), f1, rbw, vbw))
        return out


def _session_path(cfg):
    return os.path.join(cfg.SAVE_FOLDER, 'rin_session.json')


def _esa_signature(cfg):
    return json.dumps([cfg.ESA_SEGMENTS, cfg.ESA_POINTS, cfg.ESA_AVERAGES, cfg.ESA_REF_LEVEL_DBM, cfg.ESA_ATTEN_DB,
                       cfg.ESA_SWEEP_TYPE], default=str)


def _channels_signature(cfg):
    return json.dumps(cfg.CHANNELS, sort_keys=True, default=str)


def take_session(cfg):
    """The open session left by the previous start -> dict, or None (= new session: everything is asked).

    The file is REMOVED here and only written again by a clean exit with 'k' (RinSetup.close). So an error, Ctrl+C or a
    killed console always ends the session, and the questions are back at the next start."""
    path = _session_path(cfg)
    if not os.path.isfile(path):
        print('NEW SESSION (no session was kept open).')
        return None
    s, why = None, ''
    try:
        with open(path, encoding='utf-8') as fh:
            s = json.load(fh)
        age_h = (datetime.now() - datetime.fromisoformat(s['last_used'])).total_seconds() / 3600.0
        if age_h > cfg.SESSION_TIMEOUT_H:
            why = 'the kept session was last used %.1f h ago (SESSION_TIMEOUT_H = %g)' % (age_h, cfg.SESSION_TIMEOUT_H)
        elif s['channels_signature'] != _channels_signature(cfg):
            why = 'CHANNELS changed since the kept session'
    except Exception as e:
        why = 'the session file is not readable (%s)' % e
    try:
        os.remove(path)
    except OSError as e:
        why = why or 'the session file cannot be removed (%s)' % e
    if why:
        print('NEW SESSION: %s.' % why)
        return None
    return s


class RinSetup:
    """Holds the channels and the safe-operation logic.

    Session = from the first start of the script until it is quit with 'q', an error / Ctrl+C, SESSION_TIMEOUT_H without
    use, or somebody else using an instrument. Quitting with 'k' keeps it open: the next start then skips what the
    switches ASK_DC_BLOCK_EVERY_START / BACKGROUND_EVERY_START allow to skip.
    A NEW session always asks the DC-block question and measures the background.
    The Keithley does not depend on the session: it is reset only when it is not in high-Z mode (DcMonitor)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.tee = bt.Tee()                                # console log -> _log.txt and h5
        self.channels = []
        self.dc_block_confirmed = False
        self.dc_block_time = None
        self.keep_session = False
        self.last_h5 = None
        self.timing_shown = set()
        kept = take_session(cfg)                           # before anything can fail: a failed start ends the session
        print('Connecting to instruments...')
        try:
            for spec in cfg.CHANNELS:
                self.channels.append(Channel(cfg, spec))
        except BaseException:
            self.close()
            raise
        self.session = self._check_session(kept)
        self.session_opened = self.session['opened'] if self.session else datetime.now().isoformat(timespec='seconds')
        try:
            self._resolve_calibrations()
        except BaseException:
            self.close()
            raise
        for ch in self.channels:
            skipped = [s for s in cfg.ESA_SEGMENTS if s[0] < ch.esa.min_freq_hz]
            if skipped:
                print('NOTE [%s]: this ESA starts at %s - the range below is not measured.' % (ch.name, _hz(ch.esa.min_freq_hz)))

    def _resolve_calibrations(self):
        """Photodetector and bias tee calibration per channel. 'ask' = pop-up in a new session; a kept session reuses
        the choice made when it was opened (also 'none')."""
        for ch in self.channels:
            kept = ((self.session or {}).get('calibrations') or {}).get(ch.name)
            ch.cal = resolve_calibrations(self.cfg, ch.spec, kept)
            c = ch.cal
            print('Calibration [%s]:\n   detector : %s\n   AC path  : %s\n   DC path  : %s'
                  % (ch.name, c['pd_text'], c['loss_text'], c['dc_text']))

    def _check_session(self, s):
        """A kept session only continues if every instrument is exactly as this script left it."""
        if s is None:
            return None
        for ch in self.channels:
            old = s['channels'].get(ch.name, {})
            diff = [what for what, a, b in (('ESA', old.get('esa_idn'), ch.esa.idn), ('Keithley', old.get('keithley_idn'), ch.dc.idn))
                    if a != b]
            for inst, now in (('ESA', ch.esa_state_at_start), ('Keithley', ch.dc.state_at_start)):
                was = old.get(inst, {})
                diff += ['%s %s %s -> %s' % (inst, q, was.get(q), now[q]) for q in now if was.get(q) != now[q]]
            if diff:
                print('NEW SESSION: [%s] is not as this script left it - somebody used the instrument since then:\n      %s'
                      % (ch.name, '\n      '.join(diff[:6])))
                return None
        print('SESSION CONTINUES (opened %s, DC block confirmed %s, last used %s).'
              % (s['opened'], s['dc_block_confirmed'], s['last_used']))
        return s

    def _session_state(self):
        """What the next start needs to continue this session (instrument states = as they are left now)."""
        cfg = self.cfg
        return {'opened': self.session_opened, 'last_used': datetime.now().isoformat(timespec='seconds'),
                'dc_block_confirmed': self.dc_block_time, 'background_h5': self.last_h5,
                'esa_signature': _esa_signature(cfg), 'channels_signature': _channels_signature(cfg),
                'calibrations': {ch.name: {'pd_cal': ch.cal['pd_file'] or '', 'bias_tee_cal': ch.cal['bias_tee_source'] or ''}
                                 for ch in self.channels},
                'channels': {ch.name: {'esa_idn': ch.esa.idn, 'keithley_idn': ch.dc.idn,
                                       'ESA': _snapshot(ch.esa.instr, ch.esa.session_queries),
                                       'Keithley': _snapshot(ch.dc.instr, ch.dc.session_queries)} for ch in self.channels}}

    def prepare_dc_monitors(self):
        """Keithley reset (+ unplug question) only if the 2450 is found NOT in high-Z mode (see DcMonitor.prepare) -
        in a new session too. RESET_KEITHLEY_EVERY_START forces it at every start."""
        for ch in self.channels:
            ch.dc.prepare(force_reset=self.cfg.RESET_KEITHLEY_EVERY_START, why_forced='RESET_KEITHLEY_EVERY_START = True')

    def wiring_text(self, ch):
        cfg = self.cfg
        return ('  PD %s output  ->  bias tee AC+DC input\n' % (ch.spec['pd_model'] or ch.name) +
                '  bias tee AC output  ->  %s  ->  %s RF input\n' % (cfg.DC_BLOCK_NAME, bt.RECEIVER_NAMES[ch.esa.kind]) +
                '  bias tee DC output  ->  Keithley 2450 HI / LO  (0 A source, high-Z)\n' +
                ('  (series resistor in the DC line: %g ohm, at the bias tee connector)\n' % cfg.DC_PORT_SERIES_R_OHM
                 if cfg.DC_PORT_SERIES_R_OHM > 0 else ''))

    def confirm_dc_block(self):
        """The ESA is only DC-coupled after the DC block was confirmed by typing 'yes' - in a new session always, at the
        later starts of a kept session only with ASK_DC_BLOCK_EVERY_START."""
        ask = self.session is None or self.cfg.ASK_DC_BLOCK_EVERY_START
        self.dc_block_time = datetime.now().isoformat(timespec='seconds') if ask else self.session['dc_block_confirmed']
        for ch in self.channels:
            action = ('The ESA input will be switched to DC coupling (needed for 1 kHz - 10 MHz).' if ch.esa.has_coupling
                      else 'Check the maximum DC input rating of this ESA.')
            if ask:
                confirm('*** ESA SAFETY CHECK [%s] ***\n' % ch.name + self.wiring_text(ch) +
                        '  %s\n  A DC-coupled ESA input must never see the DC level of the detector - it destroys the input.\n'
                        '  Is the DC block (%s) connected between the bias tee AC output and the ESA RF input?'
                        % (action, self.cfg.DC_BLOCK_NAME))
            else:
                print('ESA [%s]: DC-block question NOT asked - it was confirmed at %s in this session and the wiring is '
                      'taken to be unchanged:\n%s' % (ch.name, self.dc_block_time, self.wiring_text(ch)), end='')
            if ch.esa.has_coupling:
                ch.esa.set_coupling('DC')
                print('ESA [%s] input coupling: DC' % ch.name)
            ch.esa.setup(self.cfg)
            for e in ch.esa.errors():
                print('  WARNING: ESA [%s] reports: %s' % (ch.name, e))
        self.dc_block_confirmed = True

    def measure(self, what):
        """One pass over all segments, all channels in parallel. what = 'laser' or 'background'.

        -> {'what', 't_start', 't_end', 'channels': {name: [segment dict, ...]}}"""
        cfg = self.cfg
        if not self.dc_block_confirmed:
            raise RuntimeError('DC block not confirmed - refusing to measure')
        out = {'what': what, 't_start': datetime.now().isoformat(), 'channels': {ch.name: [] for ch in self.channels}}
        plan = {ch.name: {s[0]: s for s in ch.segments(cfg)} for ch in self.channels}
        with ThreadPoolExecutor(max_workers=len(self.channels)) as pool:
            for i in range(len(cfg.ESA_SEGMENTS)):
                active = [ch for ch in self.channels if i in plan[ch.name]]
                segs = {}
                for ch in active:
                    _, f0, f1, rbw, vbw = plan[ch.name][i]
                    rb = ch.esa.configure(f0, f1, rbw, vbw, cfg.ESA_POINTS, cfg.ESA_AVERAGES)
                    segs[ch.name] = dict(rb, index=i, rbw_set_hz=rbw, vbw_set_hz=vbw, averages=cfg.ESA_AVERAGES,
                                         settings=ch.esa.snapshot(), errors=ch.esa.errors())
                    for e in segs[ch.name]['errors']:
                        print('  WARNING: ESA [%s] reports: %s' % (ch.name, e))
                    est = rb['sweep_time_s'] * cfg.ESA_AVERAGES
                    if (ch.name, i) not in self.timing_shown:                     # once per session
                        self.timing_shown.add((ch.name, i))
                        print('  [%s] %s - %s: %d sweeps of %.2f s (as reported by the ESA) = about %.0f s per measurement'
                              % (ch.name, _hz(f0), _hz(f1), cfg.ESA_AVERAGES, rb['sweep_time_s'], est))
                        if 1e3 * est > 0.8 * cfg.ESA_TIMEOUT_MS:
                            print('  WARNING [%s]: ESA_TIMEOUT_MS is only %.0f s - raise it, or use fewer averages / a '
                                  'wider RBW.' % (ch.name, cfg.ESA_TIMEOUT_MS / 1e3))
                for ch in active:
                    segs[ch.name]['v_before'], segs[ch.name]['v_before_std'] = ch.dc.read()
                t0 = time.time()
                futures = {ch.name: pool.submit(ch.esa.acquire) for ch in active}       # all ESAs sweep at the same time
                traces = {name: fut.result() for name, fut in futures.items()}
                dur = time.time() - t0
                for ch in active:
                    s = segs[ch.name]
                    s['v_after'], s['v_after_std'] = ch.dc.read()
                    s['v_dc'] = 0.5 * (s['v_before'] + s['v_after'])
                    s['dbm'] = traces[ch.name]
                    s['f'] = np.linspace(s['start_hz'], s['stop_hz'], len(s['dbm']))
                    s['duration_s'] = dur
                    s['overload'] = ch.esa.overload()
                    drift = s['v_after'] - s['v_before']
                    enbw = ch.spec['noise_bw_factor'] * s['rbw_hz']
                    flags = ''
                    if s['overload']:
                        flags += '  <-- ESA OVERLOAD (status %d): raise ESA_REF_LEVEL_DBM / ESA_ATTEN_DB' % s['overload']
                    if what == 'laser' and abs(drift) > cfg.DC_DRIFT_WARN_FRAC * abs(s['v_dc']):
                        flags += '  <-- DC level drifted during the sweep'
                    print('  [%s] %-10s %8s - %-8s RBW %-7s median %7.1f dBm/Hz   Vdc %8.4f V (%+.4f V)   %5.1f s%s'
                          % (ch.name, what, _hz(s['start_hz']), _hz(s['stop_hz']), _hz(s['rbw_hz']),
                             float(np.median(s['dbm'])) - 10 * np.log10(enbw), s['v_dc'], drift, dur, flags))
                    out['channels'][ch.name].append(s)
        out['t_end'] = datetime.now().isoformat()
        return out

    def measure_background(self):
        bt.ask('BACKGROUND (noise floor of detector + bias tee + ESA, dark offset of the detector)\n'
               '  BLOCK the laser beam / switch the laser off: NO light on the detector(s). Detector stays powered.')
        bg = self.measure('background')
        bt.ask('Background done.  UNBLOCK the laser / switch it on and wait until it is stable.')
        return bg

    def get_background(self):
        """Per cfg.BACKGROUND: measure with the laser blocked, load from an earlier file, or None."""
        cfg = self.cfg
        if cfg.BACKGROUND == 'none':
            print('BACKGROUND = none: no noise-floor subtraction; dark offset from the channel settings.')
            return None
        if cfg.BACKGROUND != 'measure':
            return self._load_background(cfg.BACKGROUND)
        if self.session is not None and not cfg.BACKGROUND_EVERY_START:      # kept session: use its background again
            source = self.session.get('background_h5')
            if self.session['esa_signature'] != _esa_signature(cfg):
                print('ESA settings changed since the background of this session -> new background.')
            elif source and os.path.isfile(source):
                try:
                    bg = self._load_background(source)
                    print('Background NOT measured again: the one of this session is used (BACKGROUND_EVERY_START = False).')
                    return bg
                except Exception as e:
                    print('Background of this session cannot be used (%s) -> new background.' % e)
        return self.measure_background()

    def _load_background(self, source):
        bg = {'what': 'background', 'source': source, 'channels': {}}
        for ch in self.channels:
            bg['channels'][ch.name] = load_background(source, ch.name)
        print('Background loaded from %s' % source)
        return bg

    def close(self):
        """ESA back to AC coupling (safe). The Keithley is left as it is: 0 A source ON = high-Z voltmeter, ready for the
        next start. The session file is only written here, and only after quitting with 'k'."""
        ok = True
        for ch in self.channels:
            if ch.esa.has_coupling and self.cfg.ESA_AC_COUPLED_AT_EXIT:
                try:
                    ch.esa.set_coupling('AC')
                except Exception as e:
                    ok = False
                    print('cleanup warning:', e)
        if self.keep_session and self.dc_block_confirmed and ok:
            try:
                state = self._session_state()
                os.makedirs(self.cfg.SAVE_FOLDER, exist_ok=True)
                with open(_session_path(self.cfg), 'w', encoding='utf-8') as fh:
                    json.dump(state, fh, indent=1)
                print('\nSESSION KEPT OPEN: a start within %g h asks nothing that is switched off - unless an instrument was '
                      'used in between.\n  Do NOT change the RF / DC cabling. (Deleting %s closes the session.)'
                      % (self.cfg.SESSION_TIMEOUT_H, _session_path(self.cfg)))
            except Exception as e:
                print('\nSESSION CLOSED (could not be kept: %s).' % e)
        else:
            print('\nSESSION CLOSED: the next start asks the DC-block question and measures the background again.')
        for ch in self.channels:
            for fn in (lambda ch=ch: ch.esa.drv.CloseConnection(), lambda ch=ch: ch.dc.k.CloseConnection()):
                try:
                    fn()
                except Exception as e:                     # keep cleaning up
                    print('cleanup warning:', e)
        self.tee.close()


# =============================================================================
# Analysis: ESA trace + DC voltage -> optical power, optical noise, RIN
# =============================================================================

def _dbm_to_w(dbm):
    return 1e-3 * 10 ** (np.asarray(dbm, float) / 10.0)


def _db(x):
    with np.errstate(divide='ignore', invalid='ignore'):
        return 10 * np.log10(np.where(np.asarray(x, float) > 0, x, np.nan))


def log_bin(f, y, per_decade):
    """Mean of y (linear power quantities) in logarithmically spaced frequency bins -> (f_bin, y_bin).

    A sweep with one RBW has linearly spaced points: 90 in the first decade and 90 000 in the last. Binning gives the
    same number of points per decade and averages the trace scatter away where the points are dense. Bins without a
    point do not exist; NaNs are ignored (a bin of only NaNs is NaN). f_bin is the geometric mean of the members."""
    lf = np.log10(f) * per_decade
    idx = np.minimum(np.floor(lf + 1e-9), np.floor(lf.max() - 1e-9)).astype(int)     # a stop frequency on a bin edge
    _, inv = np.unique(idx, return_inverse=True)                                     # joins the bin below it
    ok = np.isfinite(y)
    n_ok = np.bincount(inv, weights=ok.astype(float))
    with np.errstate(divide='ignore', invalid='ignore'):
        yb = np.bincount(inv, weights=np.where(ok, y, 0.0)) / np.where(n_ok > 0, n_ok, np.nan)
    return 10 ** (np.bincount(inv, weights=np.log10(f)) / np.bincount(inv)), yb


def compute_rin(cfg, spec, cal, laser, background=None):
    """Segments of one channel -> merged spectra and RIN.

        S_esa(f)  = P_trace / (noise_bw_factor x RBW)               W/Hz    at the ESA input (single-sided)
        S_pd(f)   = S_esa x 10^(loss/10)                            W/Hz    in front of bias tee + DC block
        S_voc(f)  = S_pd x r_in x ((r_in + r_out) / r_in)^2         V^2/Hz  open-circuit (Hi-Z) PD voltage noise
        V         = V_dc / dc_ratio(V_dc) - V_dark                  V       Keithley (Hi-Z), corrected to the reading WITHOUT
                                                                            the bias tee (stage 3), dark offset removed
        P_avg     = V / K                                           W       average optical power out of the fibre
        S_P(f)    = S_voc / K^2                                     W^2/Hz  optical power noise
        RIN(f)    = S_P / P_avg^2  ( = S_voc / V^2 : K cancels )    1/Hz, single-sided
        shot      = 2 q / I_pd,  I_pd = V / G
    K [V/W] = measured gain of the photodetector characterization (Hi-Z), or responsivity_A_W x transimpedance_V_A;
    G [V/A] = its transimpedance (TIA) gain; loss and dc_ratio from the bias tee characterization (see resolve_calibrations).

    'rin_raw' uses the laser trace as measured; 'rin' has the background (laser blocked) subtracted in linear power and
    is NaN where the laser trace is less than MIN_ABOVE_BACKGROUND_DB above it; 'floor' is the background as RIN.
    'binned' holds the same in BINS_PER_DECADE logarithmic bins: laser and background are averaged in each bin FIRST and
    subtracted afterwards, so far fewer points are lost to the background criterion. This is what the plot shows.
    """
    r_in, r_out = float(cfg.ESA_INPUT_OHM), float(spec['pd_output_ohm'])
    to_voc2 = r_in * ((r_in + r_out) / r_in) ** 2          # W/Hz at the ESA -> V^2/Hz open circuit
    k, G, loss_fn = cal['v_per_w'], cal['tia_v_per_a'], cal['loss_fn']
    dcr = cal['dc_ratio']
    vfix = (lambda x: x / dcr(x)) if dcr else (lambda x: x)   # Keithley reading through the tee -> reading without it
    bg_by_index = {s['index']: s for s in (background or [])}
    if background:
        v_dark = float(np.mean([vfix(s['v_dc']) for s in background]))
    else:
        v_dark = float(spec['dark_offset_V'])

    cols = {key: [] for key in ('f', 'rbw', 'esa_dbm', 'bg_dbm', 'psd', 'bg_psd', 'loss_db', 'v_dc')}
    for n, s in enumerate(laser):
        f, enbw = s['f'], spec['noise_bw_factor'] * s['rbw_hz']
        keep = np.ones(len(f), bool)
        if n + 1 < len(laser) and np.isclose(f[-1], laser[n + 1]['f'][0], rtol=1e-9):
            keep[-1] = False                               # shared boundary point: take it from the next segment
        b = bg_by_index.get(s['index'])
        if b is not None:
            if len(b['f']) != len(f) or not np.allclose(b['f'], f, rtol=1e-6) or not np.isclose(b['rbw_hz'], s['rbw_hz'], rtol=1e-3):
                raise ValueError('Background segment %d (%s - %s, RBW %s) does not match the measurement (%s - %s, RBW %s): '
                                 're-measure the background with the present ESA_SEGMENTS / ESA_POINTS.'
                                 % (s['index'], _hz(b['f'][0]), _hz(b['f'][-1]), _hz(b['rbw_hz']),
                                    _hz(f[0]), _hz(f[-1]), _hz(s['rbw_hz'])))
            bg_dbm = np.asarray(b['dbm'], float)
        else:
            bg_dbm = np.full(len(f), np.nan)
        cols['f'].append(f[keep])
        cols['rbw'].append(np.full(keep.sum(), s['rbw_hz']))
        cols['esa_dbm'].append(np.asarray(s['dbm'], float)[keep])
        cols['bg_dbm'].append(bg_dbm[keep])
        cols['psd'].append(_dbm_to_w(s['dbm'])[keep] / enbw)
        cols['bg_psd'].append(_dbm_to_w(bg_dbm)[keep] / enbw)
        cols['loss_db'].append(np.asarray(loss_fn(f), float)[keep])
        cols['v_dc'].append(np.full(keep.sum(), vfix(s['v_dc'])))
    c = {key: np.concatenate(v) for key, v in cols.items()}

    v = c['v_dc'] - v_dark                                  # Hi-Z voltage caused by the light, per point
    v_mean = float(np.mean([vfix(s['v_dc']) for s in laser])) - v_dark
    if v_mean < cfg.MIN_SIGNAL_V:
        raise RuntimeError('Channel %s: DC signal is only %.4f V above the dark level (%.4f V) - no light on the detector, '
                           'or the Keithley is not connected to the bias tee DC port?' % (spec['name'], v_mean, v_dark))
    gain = 10 ** (c['loss_db'] / 10.0) * to_voc2
    voc_raw = c['psd'] * gain                              # V^2/Hz, as measured
    voc_bg = c['bg_psd'] * gain
    have_bg = np.isfinite(voc_bg)
    above = c['psd'] >= c['bg_psd'] * 10 ** (cfg.MIN_ABOVE_BACKGROUND_DB / 10.0)
    voc = np.where(have_bg, np.where(above, voc_raw - voc_bg, np.nan), voc_raw)

    rin_raw, rin, floor = voc_raw / v ** 2, voc / v ** 2, voc_bg / v ** 2
    i_pd = v_mean / float(G) if G else np.nan
    res = {'f': c['f'], 'rbw': c['rbw'], 'esa_dbm': c['esa_dbm'], 'bg_dbm': c['bg_dbm'], 'loss_db': c['loss_db'],
           'v_dc': c['v_dc'], 'psd_dbm_hz': _db(c['psd'] * 1e3), 'bg_psd_dbm_hz': _db(c['bg_psd'] * 1e3),
           'opt_psd_w2_hz': voc / k ** 2, 'opt_psd_raw_w2_hz': voc_raw / k ** 2,
           'rin_raw_db': _db(rin_raw), 'rin_db': _db(rin), 'floor_db': _db(floor),
           'v_dc_mean': v_mean + v_dark, 'v_dark': v_dark, 'v_signal': v_mean, 'p_avg_w': v_mean / k, 'i_pd_a': i_pd,
           'rin_shot_db': float(_db(2 * Q_E / i_pd)) if G else np.nan,
           'rin_rms_raw': float(np.sqrt(_trapz(rin_raw, c['f']))),
           'rin_rms': float(np.sqrt(_trapz(np.nan_to_num(rin, nan=0.0), c['f']))),
           'valid_fraction': float(np.mean(np.isfinite(rin))), 'background': bool(have_bg.any()),
           'v_linear_max': cal['v_linear_max']}

    if cfg.BINS_PER_DECADE:
        fb, raw_b = log_bin(c['f'], rin_raw, cfg.BINS_PER_DECADE)
        floor_b = log_bin(c['f'], floor, cfg.BINS_PER_DECADE)[1]
        psd_b = log_bin(c['f'], c['psd'], cfg.BINS_PER_DECADE)[1]
        bg_psd_b = log_bin(c['f'], c['bg_psd'], cfg.BINS_PER_DECADE)[1]
    else:
        fb, raw_b, floor_b, psd_b, bg_psd_b = c['f'], rin_raw, floor, c['psd'], c['bg_psd']
    with np.errstate(invalid='ignore'):
        above_b = raw_b >= floor_b * 10 ** (cfg.MIN_ABOVE_BACKGROUND_DB / 10.0)
    rin_b = np.where(np.isfinite(floor_b), np.where(above_b, raw_b - floor_b, np.nan), raw_b)
    res['binned'] = {'f': fb, 'rin_raw_db': _db(raw_b), 'rin_db': _db(rin_b), 'floor_db': _db(floor_b),
                     'psd_dbm_hz': _db(psd_b * 1e3), 'bg_psd_dbm_hz': _db(bg_psd_b * 1e3)}
    return res


def rin_at(res, freq, key='rin_db'):
    """Median RIN (dBc/Hz) within +-10 % of freq (NaN if nothing valid there)."""
    sel = (res['f'] >= freq / 1.1) & (res['f'] <= freq * 1.1) & np.isfinite(res[key])
    return float(np.median(res[key][sel])) if sel.any() else np.nan


def print_summary(cfg, name, spec, res):
    sat = '  <-- CLOSE TO SATURATION' if res['v_dc_mean'] > 0.9 * spec['pd_max_hiz_V'] else ''
    if not sat and res['v_dc_mean'] > res['v_linear_max']:
        sat = '  <-- above %.2f V, where the detector characterization showed it linear' % res['v_linear_max']
    print('\n[%s] Vdc = %.4f V (dark %.4f V)%s  ->  P_avg = %.4g mW,  I_pd = %.4g mA,  shot-noise RIN = %.1f dBc/Hz'
          % (name, res['v_dc_mean'], res['v_dark'], sat, 1e3 * res['p_avg_w'], 1e3 * res['i_pd_a'], res['rin_shot_db']))
    decades = [f for f in 10.0 ** np.arange(0, 12) if res['f'][0] <= f <= res['f'][-1]]
    print('[%s] RIN (dBc/Hz): %s' % (name, '   '.join('%s: %.1f' % (_hz(f), rin_at(res, f)) for f in decades)))
    print('[%s] integrated %s - %s: %.4g %% rms as measured, %.4g %% rms after background subtraction (%.0f %% of the '
          'points are > %g dB above the background)'
          % (name, _hz(res['f'][0]), _hz(res['f'][-1]), 100 * res['rin_rms_raw'], 100 * res['rin_rms'],
             100 * res['valid_fraction'], cfg.MIN_ABOVE_BACKGROUND_DB))
    if res['background'] and res['valid_fraction'] < 0.5:
        print('[%s] WARNING: most of the spectrum is at the measurement floor - more optical power, less ESA attenuation '
              '(ESA_ATTEN_DB) or a lower ESA_REF_LEVEL_DBM is needed.' % name)


# =============================================================================
# Saving: csv, plot, h5
# =============================================================================

# =============================================================================
# HighFinesse comparison: a HighFinesse LWA RIN measurement taken at the same time (other arm of a splitter)
# =============================================================================

HF_IMAGES = ('*.png', '*.jpg', '*.jpeg', '*.bmp')

COMPARE_COLUMNS = [('frequency_Hz', 'f'), ('esa_rin_dBc_Hz', 'esa_db'), ('esa_measurement_floor_dBc_Hz', 'floor_db'),
                   ('highfinesse_rin_dB_Hz', 'hf_db'), ('esa_minus_highfinesse_dB', 'diff_db')]


def highfinesse_dir(cfg):
    """HIGHFINESSE_FOLDER: a name = a folder next to the label folders (in SAVE_FOLDER), or an absolute path."""
    d = cfg.HIGHFINESSE_FOLDER
    return d if os.path.isabs(d) else os.path.join(cfg.SAVE_FOLDER, d)


def parse_highfinesse(path):
    """HighFinesse LWA text export (RIN mode) -> dict(file, header, f, db, binned_export, image) in dB/Hz.

    Save it as 'raw data': one row per FFT line (50 Hz apart up to 10 MHz) of the spectrum averaged 'Av count' times.
    'Binned data' is a 2048-point display buffer with two rows per point - equal where the point is one FFT line
    (below ~60 kHz), the MAX and MIN of the lines in it above. It holds no average, so it is not compared
    (binned_export = True; 'db' is then the max of each point)."""
    header, rows = {}, []
    with open(path, encoding='utf-8', errors='replace') as fh:
        for line in fh:
            line = line.strip()
            if line.startswith('#'):
                key, _, val = line[1:].partition('=')
                header[key.strip()] = val.strip()
                continue
            parts = line.split(',')
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except (ValueError, IndexError):
                continue                                   # column title line
    if not rows:
        raise ValueError('%s: no data rows' % os.path.basename(path))
    if 'RIN' not in header.get('Outputmode', 'RIN').upper():
        print('  WARNING: %s is not a RIN export (Outputmode = %s)' % (os.path.basename(path), header.get('Outputmode')))
    f_all, y_all = np.array(rows).T
    f, inv, count = np.unique(f_all, return_inverse=True, return_counts=True)
    db = np.full(len(f), -np.inf)
    np.maximum.at(db, inv, y_all)
    return {'file': os.path.normpath(path), 'header': header, 'f': f, 'db': db,
            'binned_export': bool((count > 1).any()), 'image': None}


def bin_highfinesse(hf, per_decade, f_lo=0.0, f_hi=np.inf):
    """HighFinesse RIN between f_lo and f_hi, averaged in LINEAR units in the same logarithmic bins as the ESA RIN
    -> (f, dB/Hz)."""
    sel = (hf['f'] >= f_lo) & (hf['f'] <= f_hi)
    if not sel.any():
        return np.array([]), np.array([])
    fb, yb = log_bin(hf['f'][sel], 10 ** (hf['db'][sel] / 10.0), per_decade)
    return fb, _db(yb)


def _bin_id(f_bin, per_decade):
    """Number of the log_bin bin a bin frequency (geometric mean of its members) lies in."""
    return np.floor(np.log10(f_bin) * per_decade + 1e-9).astype(int)


def compare_highfinesse(cfg, res, hf):
    """ESA RIN of one channel (binned, background subtracted) vs the HighFinesse RIN averaged in the SAME bins, over
    the ESA frequency range only -> dict(f, esa_db, floor_db, hf_db, diff_db, median_db, n_compared, bands).

    Both are linear means of the points in each bin, so ESA - HighFinesse compares the same frequencies with the same
    weight. 'bands' = difference of the linear means per decade. Bins where the ESA RIN is at its measurement floor
    (NaN) are not compared."""
    nb = cfg.BINS_PER_DECADE
    b = res['binned']
    fh, hdb = bin_highfinesse(hf, nb, res['f'][0], res['f'][-1])
    _, ie, ih = np.intersect1d(_bin_id(b['f'], nb), _bin_id(fh, nb), return_indices=True)
    f, esa, hfv = b['f'][ie], b['rin_db'][ie], hdb[ih]
    diff = esa - hfv
    ok = np.isfinite(diff)
    lin = lambda x: 10 ** (np.asarray(x) / 10.0)
    bands = {}
    for a in 10.0 ** np.arange(0, 11):
        dec = ok & (f >= a) & (f < 10 * a)
        if dec.sum() >= 3:
            bands['%s-%s' % (_hz(a), _hz(10 * a))] = float(_db(lin(esa[dec]).mean()) - _db(lin(hfv[dec]).mean()))
    return {'f': f, 'esa_db': esa, 'floor_db': b['floor_db'][ie], 'hf_db': hfv, 'diff_db': diff,
            'median_db': float(np.median(diff[ok])) if ok.any() else np.nan, 'n_compared': int(ok.sum()), 'bands': bands}


def format_bands(c):
    return '   '.join('%s: %+.2f' % kv for kv in c['bands'].items()) + \
        '   | median of %d bins: %+.2f' % (c['n_compared'], c['median_db'])


def collect_highfinesse(cfg, t_start, base):
    """After the ESA measurement: wait until the HighFinesse RIN file ('raw data' export) and a screenshot, saved
    after t_start, are there. The newest of each is used and copied next to the ESA data as <base>_highfinesse.txt /
    <base>_highfinesse_screenshot.<ext>. -> parsed dict, or None if skipped."""
    d = highfinesse_dir(cfg)
    since = datetime.fromtimestamp(t_start).strftime('%H:%M:%S')
    new = lambda patterns: sorted((p for pat in patterns for p in glob.glob(os.path.join(d, pat))
                                   if os.path.getmtime(p) > t_start), key=os.path.getmtime)
    msg = ('HIGHFINESSE: stop its measurement and SAVE in\n  %s\n'
           '    - the RIN spectrum as "raw data" (.txt) - NOT "binned data" (only max / min per display point)\n'
           '    - a screenshot of the HighFinesse window (.png / .jpg / .bmp)\n'
           '  ENTER when saved   s = continue without the HighFinesse comparison : ' % d)
    while True:
        bt.PROMPT_LOG.append((datetime.now().isoformat(), 'HighFinesse: save'))
        ans = input('\n' + '=' * 78 + '\n' + msg).strip().lower()
        if ans == 's':
            print('  no HighFinesse comparison for this measurement')
            return None
        txt = new(['*.txt'])
        if not txt:
            print('  no .txt saved in %s since %s - try again' % (d, since))
            continue
        try:
            hf = parse_highfinesse(txt[-1])
        except Exception as e:
            print('  %s cannot be read (%s) - try again' % (os.path.basename(txt[-1]), e))
            continue
        if hf['binned_export']:
            print('  %s is a "binned data" export (max / min per display point, no average): export it again as '
                  '"raw data"' % os.path.basename(txt[-1]))
            continue
        imgs = new(HF_IMAGES)
        if imgs or ans == 'n':
            break
        msg = ('  no screenshot saved in %s since %s.\n  ENTER after saving one   n = continue without a screenshot   '
               's = continue without the HighFinesse comparison : ' % (d, since))
    hf['image'] = os.path.normpath(imgs[-1]) if imgs else None
    shutil.copy2(hf['file'], base + '_highfinesse.txt')
    if hf['image']:
        shutil.copy2(hf['image'], base + '_highfinesse_screenshot' + os.path.splitext(hf['image'])[1].lower())
    h = hf['header']
    print('  HighFinesse: %s (its timestamp %s, Av count %s, optical power %s; ESA measurement started %s)%s'
          % (os.path.basename(hf['file']), h.get('Timestamp', '?'), h.get('Av count', '?'), h.get('OpticalPower', '?'),
             since, '' if hf['image'] else ' - no screenshot'))
    return hf


def _hf_colour(n_channels):
    return bt.CATEGORICAL[n_channels] if n_channels < len(bt.CATEGORICAL) else bt.INK2


def rin_plot_limits(results, hf, per_decade):
    """Axis limits shared by the ESA, HighFinesse and comparison plots, so they can be laid over each other."""
    xs = [hf['f'][0], hf['f'][-1]]
    ys = [bin_highfinesse(hf, per_decade)[1], np.percentile(hf['db'], [0.5, 99.5])]
    for res in results.values():
        b = res['binned']
        xs += [res['f'][0], res['f'][-1]]
        ys += [b['rin_db'], b['floor_db'], [res['rin_shot_db']]]
    y = np.concatenate([np.ravel(v) for v in ys])
    y = y[np.isfinite(y)]
    return (min(xs) / 1.2, max(xs) * 1.2), (5 * np.floor(y.min() / 5) - 2, 5 * np.ceil(y.max() / 5) + 2)


def make_highfinesse_rin_report(cfg, label, stamp, hf, n_channels, base_path, lims=None):
    """The HighFinesse RIN on its own: every FFT line of the raw export (faint) and the same logarithmic bins as the
    ESA RIN (linear mean). Saved as PDF and SVG, with the axes of the ESA plot when lims is given."""
    nb = cfg.BINS_PER_DECADE
    fb, db = bin_highfinesse(hf, nb)
    h, colour = hf['header'], _hf_colour(n_channels)
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, ax = plt.subplots(figsize=(8.5, 5.0))
        fig.patch.set_facecolor(bt.SURFACE)
        ax.plot(hf['f'], hf['db'], color=colour, lw=0.5, alpha=0.3, rasterized=True,
                label='every FFT line (%d, %s apart)' % (len(hf['f']), _hz(float(np.median(np.diff(hf['f']))))))
        ax.plot(fb, db, color=colour, lw=1.6, label='%d bins per decade (linear mean)' % nb)
        ax.set_xscale('log')
        if lims:
            ax.set_xlim(lims[0])
            ax.set_ylim(lims[1])
        info = ',  '.join('%s %s' % (k, h[k]) for k in ('Timestamp', 'OpticalPower', 'Av count', 'Range[V]') if k in h)
        ax.set_title('HighFinesse RIN   %s   %s\n%s\n%s' % (label, stamp, os.path.basename(hf['file']), info),
                     loc='left', color=bt.INK, fontsize=10)
        ax.set_ylabel('RIN (dB/Hz), as exported by the HighFinesse')
        ax.set_xlabel('Frequency (Hz)')
        bt._style_axes(ax)
        ax.legend(fontsize=8, frameon=False, labelcolor=bt.INK2)
        fig.tight_layout()
        _finish(fig, base_path, show=False)


def make_compare_report(cfg, label, stamp, results, hf, cmp, base_path, lims=None, show=False):
    """ESA RIN of every channel and the HighFinesse RIN in the same bins (top), ESA - HighFinesse per bin (bottom)."""
    fb, db = bin_highfinesse(hf, cfg.BINS_PER_DECADE)
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 7.6), sharex=True, gridspec_kw={'height_ratios': [3, 1.5]})
        fig.patch.set_facecolor(bt.SURFACE)
        ax1.plot(fb, db, color=_hf_colour(len(results)), lw=1.6, label='HighFinesse LWA (%s, %s)'
                 % (os.path.basename(hf['file']), hf['header'].get('Timestamp', '?')))
        spread = [3.0]
        for i, (name, res) in enumerate(results.items()):
            c, b, d = bt.CATEGORICAL[i], res['binned'], cmp[name]
            ax1.plot(b['f'], b['rin_db'], color=c, lw=1.4, label='%s  RIN (ESA, background subtracted)' % name)
            if np.isfinite(b['floor_db']).any():
                ax1.plot(b['f'], b['floor_db'], ':', color=c, lw=1.0, label='%s  ESA measurement floor' % name)
            ax2.plot(d['f'], d['diff_db'], color=c, lw=1.4,
                     label='%s - HighFinesse  (median %+.2f dB)' % (name, d['median_db']))
            if np.isfinite(d['diff_db']).any():
                spread.append(np.nanpercentile(np.abs(d['diff_db']), 98))
        ax1.set_ylabel('RIN (dBc/Hz), single-sided\n(%d bins per decade)' % cfg.BINS_PER_DECADE)
        ax1.set_title('RIN   %s   %s   ESA vs HighFinesse, measured at the same time' % (label, stamp),
                      loc='left', color=bt.INK, fontsize=10)
        ax2.axhline(0, color=bt.AXIS, lw=0.9)
        for y in (-3, 3):                                  # a factor 2 = single- against double-sided spectrum
            ax2.axhline(y, color=bt.MUTED, ls='--', lw=0.8)
        lim = np.ceil(max(spread)) + 1
        ax2.set_ylim(-lim, lim)
        ax2.set_ylabel('ESA - HighFinesse (dB)\n(dashed: +-3 dB = factor 2)')
        ax2.set_xlabel('Frequency (Hz)')
        for ax in (ax1, ax2):
            ax.set_xscale('log')
            bt._style_axes(ax)
            ax.legend(fontsize=8, frameon=False, labelcolor=bt.INK2)
        if lims:
            ax1.set_xlim(lims[0])
            ax1.set_ylim(lims[1])
        fig.tight_layout()
        _finish(fig, base_path, show)


def save_highfinesse_outputs(cfg, label, stamp, results, hf, cmp, base, show=False):
    """Plots and tables of one ESA measurement + one HighFinesse file, all RIN plots on the same axes:
        <base>.pdf/.svg                   ESA RIN (make_rin_report)
        <base>_highfinesse.pdf/.svg       HighFinesse RIN
        <base>_vs_highfinesse.pdf/.svg    both + ESA - HighFinesse (shown if show)
        <base>_vs_highfinesse_<ch>.csv    the compared bins"""
    for name, c in cmp.items():
        save_csv('%s_vs_highfinesse_%s.csv' % (base, name), c, COMPARE_COLUMNS)
    lims = rin_plot_limits(results, hf, cfg.BINS_PER_DECADE)
    make_rin_report(cfg, label, stamp, results, base, lims=lims)
    make_highfinesse_rin_report(cfg, label, stamp, hf, len(results), base + '_highfinesse', lims)
    make_compare_report(cfg, label, stamp, results, hf, cmp, base + '_vs_highfinesse', lims, show)


def _write_highfinesse(hf_group, cfg, hf, cmp):
    ckw = dict(compression='gzip', compression_opts=6, shuffle=True)
    hf_group.attrs['file'] = hf['file']
    hf_group.attrs['image'] = hf['image'] or 'None'
    hf_group.attrs['header_json'] = json.dumps(hf['header'])
    hf_group.attrs['compared'] = ('ESA rin_dBc_Hz (binned) - HighFinesse averaged in linear units in the same '
                                  'logarithmic bins, over the ESA frequency range')
    hf_group.create_dataset('frequency_Hz', data=hf['f'], **ckw)
    hf_group.create_dataset('rin_dB_Hz', data=hf['db'], **ckw)
    fb, db = bin_highfinesse(hf, cfg.BINS_PER_DECADE)
    bg = hf_group.create_group('binned')
    bg.create_dataset('frequency_Hz', data=fb, **ckw)
    bg.create_dataset('rin_dB_Hz', data=db, **ckw)
    for name, path in (('file_bytes', hf['file']), ('image_bytes', hf['image'])):
        if path and os.path.isfile(path):
            hf_group.create_dataset(name, data=np.frombuffer(open(path, 'rb').read(), np.uint8), compression='gzip')
    for ch, c in cmp.items():
        g = hf_group.create_group('compared_' + ch)
        for col, key in COMPARE_COLUMNS:
            g.create_dataset(col, data=c[key], **ckw)
        g.attrs['median_dB'] = c['median_db']
        g.attrs['bands_json'] = json.dumps(c['bands'])


def load_rin_h5(path):
    """Saved measurement (*_rin_data.h5) -> (cfg with the settings the plots need, label, stamp, laser start time,
    {channel: results as compute_rin returns them, without the per-segment data}), to compare it again later."""
    with h5py.File(path, 'r') as h:
        c = h['config'].attrs
        cfg = SimpleNamespace(BINS_PER_DECADE=int(c['BINS_PER_DECADE']),
                              MIN_ABOVE_BACKGROUND_DB=float(c['MIN_ABOVE_BACKGROUND_DB']))
        label, t_start = str(h.attrs['label']), str(h.attrs['laser_t_start'])
        results = {}
        for name, g in h['channels'].items():
            res = {k: float(v) for k, v in g.attrs.items() if isinstance(v, (float, int, np.floating, np.integer))}
            for col, key in CSV_COLUMNS:
                res[key] = g[col][()]
            res['binned'] = {key: g['binned'][col][()] for col, key in BINNED_COLUMNS}
            results[name] = res
    stamp = os.path.basename(path).split('_rin_data')[0]
    return cfg, label, stamp, t_start, results


def compare_saved(esa_h5, hf_txt, max_gap_min=30.0, show=False):
    """Compare a saved ESA RIN measurement with a HighFinesse 'raw data' export (rin_compare_highfinesse.py).
    Output in <folder of esa_h5>/<stamp>_vs_<HighFinesse file name>/ (see save_highfinesse_outputs). -> comparisons"""
    cfg, label, stamp, t_start, results = load_rin_h5(esa_h5)
    if not cfg.BINS_PER_DECADE:
        raise ValueError('%s was saved with BINS_PER_DECADE = 0; the comparison needs logarithmic bins' % esa_h5)
    hf = parse_highfinesse(hf_txt)
    if hf['binned_export']:
        raise ValueError('%s is a "binned data" export (max / min per display point, no average): export the '
                         'HighFinesse spectrum as "raw data"' % hf_txt)
    gap = (os.path.getmtime(hf_txt) - datetime.fromisoformat(t_start).timestamp()) / 60.0
    print('ESA        : %s  (label %s, started %s)' % (esa_h5, label, t_start[:19]))
    print('HighFinesse: %s  (saved %.1f min after the ESA start, its timestamp %s, Av count %s)'
          % (hf_txt, gap, hf['header'].get('Timestamp', '?'), hf['header'].get('Av count', '?')))
    if not 0 <= gap <= max_gap_min:
        print('WARNING: the HighFinesse file was saved %.1f min %s the ESA measurement started - probably not the '
              'same measurement' % (abs(gap), 'before' if gap < 0 else 'after'))
    out = os.path.join(os.path.dirname(os.path.abspath(esa_h5)),
                       '%s_vs_%s' % (stamp, bt.safe_name(os.path.splitext(os.path.basename(hf_txt))[0])))
    os.makedirs(out, exist_ok=True)
    shutil.copy2(hf_txt, out)
    cmp = {name: compare_highfinesse(cfg, res, hf) for name, res in results.items()}
    for name, c in cmp.items():
        print('[%s] ESA - HighFinesse (dB): %s' % (name, format_bands(c)))
    save_highfinesse_outputs(cfg, label, stamp, results, hf, cmp, os.path.join(out, stamp + '_rin'), show)
    return cmp


CSV_COLUMNS = [('frequency_Hz', 'f'), ('rbw_Hz', 'rbw'), ('esa_dBm', 'esa_dbm'), ('background_dBm', 'bg_dbm'),
               ('esa_psd_dBm_Hz', 'psd_dbm_hz'), ('background_psd_dBm_Hz', 'bg_psd_dbm_hz'), ('ac_path_loss_dB', 'loss_db'),
               ('v_dc_V', 'v_dc'), ('optical_noise_W2_Hz', 'opt_psd_w2_hz'), ('rin_as_measured_dBc_Hz', 'rin_raw_db'),
               ('rin_dBc_Hz', 'rin_db'), ('measurement_floor_dBc_Hz', 'floor_db')]


BINNED_COLUMNS = [('frequency_Hz', 'f'), ('esa_psd_dBm_Hz', 'psd_dbm_hz'), ('background_psd_dBm_Hz', 'bg_psd_dbm_hz'),
                  ('rin_as_measured_dBc_Hz', 'rin_raw_db'), ('rin_dBc_Hz', 'rin_db'), ('measurement_floor_dBc_Hz', 'floor_db')]


def save_csv(path, res, columns=CSV_COLUMNS):
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow([name for name, _ in columns])
        for row in zip(*[res[key] for _, key in columns]):
            w.writerow(['%.9g' % x for x in row])
    print('  Saved: %s' % path)


_shown_fig = []        # the plot window of the previous measurement (closed when the next one is shown)


def close_shown_plots():
    while _shown_fig:
        plt.close(_shown_fig.pop())


def _finish(fig, base_path, show):
    """Save as PDF and SVG; then show the window (closed by the next close_shown_plots) or close the figure."""
    for ext in ('pdf', 'svg'):
        p = '%s.%s' % (base_path, ext)
        fig.savefig(p, bbox_inches='tight', facecolor=fig.get_facecolor())
        print('  Saved: %s' % p)
    if show:
        _shown_fig.append(fig)
        fig.show()
        plt.pause(0.5)
    else:
        plt.close(fig)


def make_rin_report(cfg, label, stamp, results, base_path, show=False, lims=None):
    """RIN (top) and the ESA noise density it was computed from (bottom), log-binned. Saved as PDF and SVG.
    lims = ((f_min, f_max), (rin_min, rin_max)): the axes of the HighFinesse plots (rin_plot_limits)."""
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 7.8), sharex=True, gridspec_kw={'height_ratios': [3, 2]})
        fig.patch.set_facecolor(bt.SURFACE)
        info = []
        for i, (name, res) in enumerate(results.items()):
            c, r = bt.CATEGORICAL[i], res['binned']
            ax1.plot(r['f'], r['rin_db'], '-', color=c, lw=1.4, label='%s  RIN' % name)
            if np.isfinite(r['floor_db']).any():
                ax1.plot(r['f'], r['floor_db'], ':', color=c, lw=1.2, label='%s  measurement floor (laser blocked)' % name)
            if np.isfinite(res['rin_shot_db']):
                ax1.axhline(res['rin_shot_db'], color=c, ls='--', lw=1.0,
                            label='%s  shot-noise limit (%.1f dBc/Hz)' % (name, res['rin_shot_db']))
            ax2.plot(r['f'], r['psd_dbm_hz'], '-', color=c, lw=1.2, label='%s  laser on' % name)
            if np.isfinite(r['bg_psd_dbm_hz']).any():
                ax2.plot(r['f'], r['bg_psd_dbm_hz'], ':', color=c, lw=1.2, label='%s  laser blocked' % name)
            power = ('P = %.3g mW,  ' % (1e3 * res['p_avg_w'])) if np.isfinite(res['p_avg_w']) else ''
            info.append('%s:  Vdc = %.3f V,  %s%.3g %% rms (%s - %s)'
                        % (name, res['v_dc_mean'], power, 100 * res['rin_rms'], _hz(res['f'][0]), _hz(res['f'][-1])))
        binning = ('%d bins per decade' % cfg.BINS_PER_DECADE) if cfg.BINS_PER_DECADE else 'every ESA point'
        ax1.set_ylabel('RIN (dBc/Hz), single-sided\n(%s)' % binning)
        ax1.set_title('RIN   %s   %s\n%s' % (label, stamp, '\n'.join(info)), loc='left', color=bt.INK, fontsize=10)
        ax2.set_ylabel('Noise at the ESA input (dBm/Hz)')
        ax2.set_xlabel('Frequency (Hz)')
        for ax in (ax1, ax2):
            ax.set_xscale('log')
            bt._style_axes(ax)
            ax.legend(fontsize=8, frameon=False, labelcolor=bt.INK2)
        if lims:
            ax1.set_xlim(lims[0])
            ax1.set_ylim(lims[1])
        fig.tight_layout()
        _finish(fig, base_path, show)


def _write_segments(group, segs, with_settings=True):
    ckw = dict(compression='gzip', compression_opts=6, shuffle=True)
    for s in segs:
        g = group.create_group('s%02d' % s['index'])
        g.create_dataset('frequency_Hz', data=s['f'], **ckw)
        g.create_dataset('trace_dBm', data=np.asarray(s['dbm'], np.float32), **ckw)
        for key, val in s.items():
            if key in ('f', 'dbm', 'settings', 'errors'):
                continue
            g.attrs[key] = bt._attr(val)
        if s.get('errors'):
            g.attrs['esa_errors'] = json.dumps(s['errors'])
        if with_settings and 'settings' in s:
            sg = g.create_group('esa_settings')
            for cmd, reply in s['settings'].items():
                sg.attrs[cmd] = reply


def write_rin_h5(path, cfg, R, label, laser, background, results, log_idx, prompt_idx, hfm=None, cmp=None):
    """One HDF5 file per measurement.

    /                              attrs: label, created
    /config                        attrs: every UPPER_CASE setting of the runner (+ config_json; CHANNELS with defaults)
    /analysis                      attrs: the formulas of compute_rin
    /environment, /script          versions, git commit, the exact source files (read back with bt.extract_script)
    /log                           console_log, prompts
    /channels/<name>               attrs: instrument IDNs, setting_* (the CHANNELS entry), v_dc, P_avg, I_pd, shot-noise RIN, ...
        frequency_Hz, rin_dBc_Hz, rin_as_measured_dBc_Hz, ...   every ESA point (same columns as the csv)
        binned/...                 the same in BINS_PER_DECADE logarithmic bins (what the plot shows)
        keithley_settings          attrs: what the Keithley reported back
        laser/sNN                  frequency_Hz, trace_dBm (as read from the ESA) + attrs (RBW, sweep time, v_dc before/after)
        background/sNN             the same with the laser blocked (what load_background() reads)
    /highfinesse                   (COMPARE_HIGHFINESSE) the simultaneous HighFinesse file: frequency_Hz, rin_dB_Hz,
                                   binned/..., header, the file and screenshot bytes, compared_<channel>/ (COMPARE_COLUMNS)
    """
    ckw = dict(compression='gzip', compression_opts=6, shuffle=True)
    with h5py.File(path, 'w') as hf:
        hf.attrs['label'] = label
        hf.attrs['created'] = datetime.now().isoformat()
        hf.attrs['script'] = 'rin_measurement.py / rin_utils.py'
        hf.attrs['session_opened'], hf.attrs['dc_block_confirmed'] = R.session_opened, R.dc_block_time
        hf.attrs['session_continued_from_earlier_start'] = R.session is not None
        hf.attrs['laser_t_start'], hf.attrs['laser_t_end'] = laser['t_start'], laser['t_end']
        if background:
            hf.attrs['background_source'] = background.get('source', 'measured in this session')
            hf.attrs['background_t_start'] = background.get('t_start', '')
        cg = hf.create_group('config')
        for k, v in vars(cfg).items():
            cg.attrs[k] = bt._attr(v)
        cg.attrs['config_json'] = json.dumps(vars(cfg), default=str, indent=1, sort_keys=True)
        hf.create_group('analysis').attrs['formulas'] = compute_rin.__doc__
        bt._write_provenance(hf)
        for name in ('rin_measurement.py', 'rin_utils.py'):
            data = open(os.path.join(bt._here, name), 'rb').read()
            ds = hf['script'].create_dataset(name, data=np.frombuffer(data, np.uint8), compression='gzip', compression_opts=9)
            ds.attrs['sha256'] = hashlib.sha256(data).hexdigest()
        lg = hf.create_group('log')
        lg.create_dataset('console_log', data='\n'.join(R.tee.lines[log_idx:]), dtype=h5py.string_dtype('utf-8'))
        lg.create_dataset('prompts', data=['[%s] %s' % pr for pr in bt.PROMPT_LOG[prompt_idx:]], dtype=h5py.string_dtype('utf-8'))

        chg = hf.create_group('channels')
        for ch in R.channels:
            res = results[ch.name]
            g = chg.create_group(ch.name)
            g.attrs['esa_idn'], g.attrs['keithley_idn'] = ch.esa.idn, ch.dc.idn
            g.attrs['esa_coupling_at_start'] = bt._attr(ch.coupling_at_start)
            for k, v in ch.cal.items():
                if not callable(v):
                    g.attrs['cal_' + k] = bt._attr(v)
            g.attrs['keithley_was_reset_this_session'] = ch.dc.was_reset
            for k, v in ch.spec.items():
                g.attrs['setting_' + k] = bt._attr(v)
            for k, v in res.items():
                if not isinstance(v, dict) and np.ndim(v) == 0:
                    g.attrs[k] = bt._attr(v)
            for col, key in CSV_COLUMNS + [('optical_noise_as_measured_W2_Hz', 'opt_psd_raw_w2_hz')]:
                g.create_dataset(col, data=res[key], **ckw)
            bg_ = g.create_group('binned')
            bg_.attrs['bins_per_decade'] = cfg.BINS_PER_DECADE
            for col, key in BINNED_COLUMNS:
                bg_.create_dataset(col, data=res['binned'][key], **ckw)
            kg = g.create_group('keithley_settings')
            for cmd, reply in ch.dc.snapshot().items():
                kg.attrs[cmd] = reply
            _write_segments(g.create_group('laser'), laser['channels'][ch.name])
            if background and background['channels'].get(ch.name):
                _write_segments(g.create_group('background'), background['channels'][ch.name])
        if hfm:
            _write_highfinesse(hf.create_group('highfinesse'), cfg, hfm, cmp)
    print('  HDF5 saved: %s' % path)


def load_background(h5_path, channel):
    """Laser-blocked segments of one channel from an earlier *_rin_data.h5 -> list of segment dicts."""
    with h5py.File(h5_path, 'r') as hf:
        if 'channels/%s/background' % channel not in hf:
            raise ValueError('%s has no background for channel %s' % (h5_path, channel))
        g = hf['channels/%s/background' % channel]
        return [{'index': int(g[key].attrs['index']), 'f': g[key]['frequency_Hz'][()],
                 'dbm': g[key]['trace_dBm'][()].astype(float), 'rbw_hz': float(g[key].attrs['rbw_hz']),
                 'v_dc': float(g[key].attrs['v_dc'])} for key in sorted(g)]


# =============================================================================
# One measurement, saved
# =============================================================================

def run_measurement(R, label, background):
    """Measure the laser on all channels, compute RIN and write  <timestamp>_rin_data.h5 / _<channel>.csv / .pdf / .svg / _log.txt
    to SAVE_FOLDER/<label>/."""
    cfg = R.cfg
    stamp = pic.datetimestring()
    folder = os.path.join(cfg.SAVE_FOLDER, label)
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, stamp + '_rin')
    log_idx, prompt_idx = len(R.tee.lines), len(bt.PROMPT_LOG)
    print('\nMeasuring RIN  [%s]  ->  %s' % (label, folder))
    hfm = cmp = None
    if cfg.COMPARE_HIGHFINESSE:
        os.makedirs(highfinesse_dir(cfg), exist_ok=True)
        bt.ask('HIGHFINESSE: START its RIN measurement now (same laser, other arm of the splitter), with averaging on.\n'
               '  The ESA measurement starts when you press ENTER; save the HighFinesse file ("raw data") and a\n'
               '  screenshot AFTER it, in  %s' % highfinesse_dir(cfg))
    t_start = time.time()
    laser = R.measure('laser')
    if cfg.COMPARE_HIGHFINESSE:
        hfm = collect_highfinesse(cfg, t_start, base)
    results = {}
    for ch in R.channels:
        bg = background['channels'].get(ch.name) if background else None
        results[ch.name] = compute_rin(cfg, ch.spec, ch.cal, laser['channels'][ch.name], bg)
        print_summary(cfg, ch.name, ch.spec, results[ch.name])
    if hfm:
        cmp = {name: compare_highfinesse(cfg, res, hfm) for name, res in results.items()}
        for name, c in cmp.items():
            print('[%s] ESA - HighFinesse (dB): %s' % (name, format_bands(c)))
    print('\nSaving ...')
    write_rin_h5(base + '_data.h5', cfg, R, label, laser, background, results, log_idx, prompt_idx, hfm, cmp)  # data first
    R.last_h5 = base + '_data.h5'                          # holds the background: a kept session reuses it
    for ch in R.channels:
        save_csv('%s_%s.csv' % (base, ch.name), results[ch.name])
        save_csv('%s_%s_binned.csv' % (base, ch.name), results[ch.name]['binned'], BINNED_COLUMNS)
        if cfg.SAVE_SCREENSHOTS:
            try:
                bt.save_screenshot_png(ch.esa.drv, '%s_%s_esa.png' % (base, ch.name))
            except Exception as e:                         # a screenshot must never lose the measurement
                print('  warning: screenshot failed (%s)' % e)
    try:
        close_shown_plots()
        if hfm:
            save_highfinesse_outputs(cfg, label, stamp, results, hfm, cmp, base, show=cfg.SHOW_PLOTS)
        else:
            make_rin_report(cfg, label, stamp, results, base, show=cfg.SHOW_PLOTS)
    except Exception as e:
        print('  warning: plot failed (%s) - the data are saved in the h5 file' % e)
    with open(base + '_log.txt', 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(R.tee.lines[log_idx:]) + '\n')
    return results
