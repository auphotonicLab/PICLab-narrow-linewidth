#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AM response test: the same sine intensity modulation seen by the ESA chain, the HighFinesse and (optionally) a scope
=====================================================================================================================

Why
    The RIN of every laser measured with the ESA chain is ~1 dB below the HighFinesse in the middle of the band
    (after the HighFinesse dB-averaging correction), the same for NKT, Agilent and PPCL. A steady tone puts the SAME
    relative modulation on every arm of the splitter, so
        ESA - HighFinesse (tone)   = the difference of the two frequency responses, no noise statistics involved
                                     (a steady tone is not biased by the HighFinesse dB averaging -> no correction)
        ESA - HighFinesse (noise)  = the same comparison on the laser noise next to each tone (HighFinesse corrected
                                     from the Av count of each file) - if both agree, the dB-averaging correction holds
        ESA / HF - scope           = against an independent detector on the scope (SCOPE_ENABLE), see below
        ESA / HF - expected        = from the modulator: m = 2 J1(pi V_pk / V_PI)   (only if V_PI is set)

Wiring (modulator as in Mid-IR/Eye_diagram_lab.py, detection as in rin_measurement.py)
    laser -> amplitude modulator (MZI) -> splitter -> arm 1: PD -> bias tee -> EF500 -> ESA (DC port -> Keithley)
                                                    -> arm 2: HighFinesse
                                                    -> arm 3 (SCOPE_ENABLE): a second photodetector -> scope SCOPE_AC_CH
                                                          (1 Mohm; optionally a BNC T to SCOPE_DC_CH as well)
    modulator bias : SPD3303X (DC_IP) at V_QUAD (quadrature)     modulator RF : SDG6022X (AFG_IP) pure AC sine

HighFinesse: several files per tone (HF_FILES_PER_TONE)
    After the ESA (and scope) measurement of a tone you are asked for up to HF_FILES_PER_TONE HighFinesse files, one
    after the other (each saved after the previous one; 's' = no more files for this tone). Use any Av count and any
    order: everything is read from the files - each is grouped by the 'Av count' in its own header, its noise corrected
    for that Av count (rin_utils.prepare_highfinesse), and its place in the order of saving is recorded. Per tone:
        every file             one row in <timestamp>_am_highfinesse_files.csv
        each Av count group    hf_tone / ESA - HF tone / ESA - HF noise for that Av count (power mean if several files)
        all files combined     power mean of the tones (unbiased for any Av count) and of the CORRECTED noise

Scope (SCOPE_ENABLE): an independent detector, the Siglent SDS2352X-E
    m = V_tone,pk / V_dc  directly (a ratio: the same load for AC and DC cancels): no bias tee, ESA, noise bandwidth
    or TIA gain value is involved. Default 50 ohm inputs (SCOPE_AC_COUPLING / SCOPE_DC_COUPLING): the cable is
    terminated, so no roll-off of the detector's 50 ohm output with the cable capacitance (at 1 Mohm ~0.25 dB at 8 MHz
    for ~1 m of cable). Keep the detector well inside its linear range for both couplings. The tone comes from a flat-top FFT of an AC-coupled
    record at a fine V/div (bias_tee_utils.tone_spectrum, the method that agreed with the FSW within 0.05 dB in the
    bias tee characterization); the DC level from a DC-coupled record. Both are needed: with 8 bits the DC level fills
    ~90 codes, and a 0.7 % tone is then below one code - DC coupling alone cannot resolve it, AC coupling alone has no
    DC level. SCOPE_DC_CH = None (default): the same channel is switched to DC coupling for the DC level after the
    tone records (no BNC T). SCOPE_DC_CH = 2: a BNC T to a second, DC-coupled channel, read from the same acquisition.
    Use a second detector (any
    DC-coupled one with a bandwidth well above 10 MHz) on a third splitter arm; it shows whether the ESA chain or the
    HighFinesse follows the true modulation versus frequency.
    Accuracy: the frequency dependence to ~0.05 dB; the absolute level only to the scope's DC gain accuracy (a few %
    per channel, i.e. a few tenths of a dB in m^2/2) - use the scope result mainly for the SHAPE versus frequency.

Modulator response and drift
    The modulator (LiNbO3 MZI) is before the splitter: whatever m(f) it gives - not flat, polarization dependent -
    is the SAME on every arm and cancels in ESA - HighFinesse / ESA - scope. What does not cancel is a CHANGE of m
    between the ESA and the HighFinesse measurement of one tone (polarization drift into the modulator, bias drift):
    ESA_REMEASURE_AFTER_HF measures the ESA again after the HighFinesse files and reports the drift. The expected level
    from V_PI assumes a flat modulator response and is only approximate.

Background (MEASURE_BACKGROUND)
    Laser blocked once: the same ESA span around every tone + the Keithley dark level. The ESA noise next to each tone is
    then the laser noise above the ESA / detector floor (the HighFinesse floor cannot be measured from here), and spurs
    of the ESA side (seen with the laser blocked) are identified ('floor' columns).

How the tone level is obtained (relative power of the tone, dBc = m^2 / 2, m = modulation depth)
    ESA peak       : highest trace point (= tone power, no noise bandwidth; 10 points per RBW, < 0.05 dB lost). Main ESA value.
    ESA integrated : sum of (trace - noise) over +-TONE_HALF_WIDTH_HZ / (noise_bw_factor x RBW) - as the RIN measurement.
    HighFinesse    : sum of (density - noise) x line spacing over +-HF_TONE_HALF_WIDTH_HZ, as exported.
    ESA power -> open-circuit PD voltage exactly as rin_utils.compute_rin (50 ohm divider, bias tee + DC block loss,
    Keithley V_dc corrected to the reading without the tee). Dark offset of the detectors (~ -5 mV) neglected (< 0.01 dB).

Output in SAVE_FOLDER/<label>/ :
    <timestamp>_am_data.h5                 everything: settings, ESA traces, scope records, HighFinesse files, results, log
    <timestamp>_am_summary.csv             one row per tone (with columns per Av count group)
    <timestamp>_am_highfinesse_files.csv   one row per HighFinesse file
    <timestamp>_am_response.pdf/.svg
    <timestamp>_am_<f>Hz_hf<k>_highfinesse.txt (+ screenshot)   copies of the HighFinesse files

Use the NKT (or another laser with high RIN) for the noise comparison next to the tones. DRIVE_VPP = 20 mV gave
m ~ 0.7 % (-46 dBc), ~60 dB above the noise in a 50 Hz HighFinesse line (2026-10-19).
"""

import os
import math
import time
import json
import hashlib

import numpy as np
import matplotlib.pyplot as plt
import h5py

import rin_measurement as base_settings
import rin_utils as rin

bt = rin.bt
pic = rin.pic

# =============================================================================
# Settings (everything not set here - CHANNELS, calibration folders, Keithley, ESA attenuation, HighFinesse
# dB-averaging correction ... - is taken from rin_measurement.py)
# =============================================================================
SAVE_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\AM_response'
DEFAULT_SAVE_LABEL = ''
SHOW_PLOTS = True

# --- tones ---
TONES_HZ = [10e3, 20e3, 50e3, 100e3, 200e3, 300e3, 500e3, 700e3, 1e6, 1.5e6, 2e6, 3e6, 5e6, 8e6]
# multiples of 100 Hz (on the 50 Hz lines of the HighFinesse and on an ESA point); >= 6 kHz (noise windows)
SETTLE_S = 0.5                    # wait after changing the tone frequency

# --- HighFinesse ---
COMPARE_HIGHFINESSE = True
HIGHFINESSE_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\RIN\HighFinesse'   # where you save the HF files
HF_FILES_PER_TONE = 2             # HighFinesse files asked for per tone (any Av count, any order: read from each file;
                                  # 's' at the prompt = no more files for this tone)

# --- scope: an independent detector (see the docstring) ---
SCOPE_ENABLE = False
SCOPE_IP = '192.168.1.52'         # Siglent SDS2352X-E
SCOPE_AC_CH = 1                   # AC-coupled (SCOPE_AC_COUPLING): the tone
SCOPE_AC_COUPLING = 'A50'         # 'A50' / 'D50' = 50 ohm input (terminates the cable: no 50 ohm x cable-C roll-off,
SCOPE_DC_COUPLING = 'D50'         # ~0.25 dB at 8 MHz at 1 Mohm with ~1 m cable; the path the bias tee characterization
                                  # validated against the FSW). 'A1M' / 'D1M' = 1 Mohm. m = V_tone / V_dc is a ratio,
                                  # so the load does not matter as long as AC and DC see the same one.
SCOPE_DC_CH = None                # None: the same channel, switched to SCOPE_DC_COUPLING for the DC level after the tone
                                  # records. A channel number: a BNC T to that channel, read from the same acquisition
                                  # (with 50 ohm inputs a BNC T would load the detector twice: use None)
SCOPE_SWITCH_SETTLE_S = 1.0       # wait after switching the coupling (AC coupling capacitor recharging)
SCOPE_DETECTOR = 'PD2'            # name of the detector on the scope (saved, in the plot)
SCOPE_MEMORY = '140K'
SCOPE_NCYC = 200                  # record length >= this many tone periods
SCOPE_NACQ = 3                    # records per tone (power-averaged)
SCOPE_PP_CODES = (100, 190)       # wanted peak-peak of the AC channel in ADC codes (25 codes/div, +-127 max)
SCOPE_BWL = False                 # 20 MHz bandwidth limit

# --- modulator drive: SDG6022X, pure AC sine (as Eye_diagram_lab.py) ---
AFG_IP = '192.168.1.101'
AFG_CH = 1
AFG_LOAD = 50                     # SDG load setting (50 or 'HZ'): must match the modulator RF input, else DRIVE_VPP is off
DRIVE_VPP = 0.02                  # [V] peak-to-peak at the modulator

# --- modulator bias: SPD3303X (as Eye_diagram_lab.py) ---
SET_AM_BIAS = True                # False: you set the bias yourself (asked at the start)
DC_IP = '192.168.1.31'
DC_CHANNEL = 1
DC_CURRENT = 0.01                 # [A] current limit
MAX_DC_VOLT = 7.0                 # [V] hard limit (also enforced in DC_Siglent)
V_QUAD = 1.95                     # [V] bias at quadrature (amplitude_modulator_characterization.py: V_quad)
V_PI = None                       # [V] half-wave voltage = V_max - V_min of the AM characterization (eye diagram:
                                  # V_PP_MANUAL = 3.9). None = no expected level. Only right if the RF and DC Vpi are equal
                                  # and the bias is at quadrature; a bias off quadrature lowers m by cos(phase) for ALL
                                  # detectors alike, so the differences between them are not affected.

# --- ESA per tone ---
MEASURE_BACKGROUND = True         # laser blocked once at the start: the same span around every tone (ESA + detector
                                  # floor, spurs) and the Keithley dark level; subtracted from the noise next to the tones
ESA_REMEASURE_AFTER_HF = True     # measure the ESA tone again after the HighFinesse files: the mean of both is compared,
                                  # their difference (drift of the modulation depth during the tone, e.g. polarization
                                  # into the modulator or bias drift) is reported - it does NOT cancel between instruments
DRIFT_WARN_DB = 0.2
TONE_SPAN_HZ = 2000               # span around each tone
TONE_RBW_HZ = 10
TONE_POINTS = 2001                # 1 Hz apart = 10 points per RBW (peak loss < 0.05 dB)
TONE_AVERAGES = 10                # power-averaged sweeps
ESA_REF_LEVEL_DBM = 0             # the tone is much stronger than the RIN: a higher reference level than for RIN
SCREENSHOT_TONES_HZ = [100e3, 1e6]

# --- tone / noise windows ---
TONE_HALF_WIDTH_HZ = 200          # ESA: tone integrated over +-this
ESA_NOISE_HZ = (500.0, 1000.0)    # ESA: noise next to the tone, |f - f_tone| in this range
HF_TONE_HALF_WIDTH_HZ = 1000.0    # HighFinesse: tone integrated over +-this (+-20 lines: window leakage included)
HF_NOISE_HZ = (2000.0, 5000.0)    # HighFinesse: noise next to the tone


# =============================================================================
def build_cfg():
    g = {k: v for k, v in vars(base_settings).items() if k.isupper()}
    g.update({k: v for k, v in globals().items() if k.isupper()})       # the settings of this file win
    g['N_MEASUREMENTS'] = 1
    cfg = bt.config_from_globals(g)
    rin.validate_config(cfg)
    bad = [f for f in cfg.TONES_HZ if abs(f / 100.0 - round(f / 100.0)) > 1e-9 or f < 6e3 or f > 9.9e6]
    if bad:
        raise ValueError('TONES_HZ must be multiples of 100 Hz between 6 kHz and 9.9 MHz, got %s' % bad)
    if not 0 < cfg.DRIVE_VPP <= 1.0:
        raise ValueError('DRIVE_VPP = %r V: expected a small drive (0 ... 1 V)' % cfg.DRIVE_VPP)
    if cfg.SET_AM_BIAS and cfg.V_QUAD + cfg.DRIVE_VPP / 2 > cfg.MAX_DC_VOLT:
        raise ValueError('V_QUAD + DRIVE_VPP/2 = %.2f V exceeds MAX_DC_VOLT = %g V' % (cfg.V_QUAD + cfg.DRIVE_VPP / 2,
                                                                                    cfg.MAX_DC_VOLT))
    if cfg.COMPARE_HIGHFINESSE and not (isinstance(cfg.HF_FILES_PER_TONE, int) and cfg.HF_FILES_PER_TONE >= 1):
        raise ValueError('HF_FILES_PER_TONE must be an integer >= 1, got %r' % (cfg.HF_FILES_PER_TONE,))
    if cfg.SCOPE_ENABLE and cfg.SCOPE_AC_CH == cfg.SCOPE_DC_CH:
        raise ValueError('SCOPE_DC_CH must be another channel than SCOPE_AC_CH, or None (same channel, switched)')
    if cfg.TONE_POINTS < 5 * cfg.TONE_SPAN_HZ / cfg.TONE_RBW_HZ:
        print('NOTE: fewer than 5 points per RBW - the ESA peak can read low (use the integrated value)')
    return cfg


def _j1(x):
    """Bessel function J1 (series; x < 3 here)."""
    return sum((-1) ** k * (x / 2.0) ** (2 * k + 1) / (math.factorial(k) * math.factorial(k + 1)) for k in range(25))


def expected_level_dbc(cfg):
    """Tone level m^2/2 (dBc) from the modulator: P = P0/2 (1 + sin(pi V / V_PI)) at quadrature, V = V_pk sin(wt)
    -> fundamental relative amplitude m = 2 J1(pi V_pk / V_PI). None without V_PI."""
    if not cfg.V_PI:
        return None, None
    m = 2 * _j1(math.pi * (cfg.DRIVE_VPP / 2.0) / cfg.V_PI)
    return 10 * np.log10(m ** 2 / 2), m


def _db(x):
    with np.errstate(divide='ignore', invalid='ignore'):
        return 10 * np.log10(np.where(np.asarray(x, float) > 0, x, np.nan))


def _lin(db):
    return 10 ** (np.asarray(db, float) / 10.0)


def _power_mean_db(values):
    v = [x for x in values if np.isfinite(x)]
    return float(_db(np.mean(_lin(v)))) if v else np.nan


# =============================================================================
# Instruments
# =============================================================================

class Modulator:
    """SDG6022X sine (pure AC) + SPD3303X bias, switched off and to 0 V by close()."""

    def __init__(self, cfg):
        self.cfg, self.afg, self.dc = cfg, None, None
        self.afg = pic.AFG_Siglent(IP_address=cfg.AFG_IP, channel=cfg.AFG_CH, frequency=cfg.TONES_HZ[0],
                                   vpp=cfg.DRIVE_VPP, offset=0, load=cfg.AFG_LOAD)
        self.afg.output_status(channel=cfg.AFG_CH, status='OFF')
        self.check_afg()
        if cfg.SET_AM_BIAS:
            self.dc = pic.DC_Siglent(IP_address=cfg.DC_IP, channel=cfg.DC_CHANNEL, voltage=0.0, current=cfg.DC_CURRENT,
                                     max_voltage=cfg.MAX_DC_VOLT)
            self.dc.outputStatus(channel=cfg.DC_CHANNEL, status='OFF')
            self.dc.setParameters(channel=cfg.DC_CHANNEL, voltage=cfg.V_QUAD, current=cfg.DC_CURRENT)
            time.sleep(0.2)
            self.dc.outputStatus(channel=cfg.DC_CHANNEL, status='ON')
            time.sleep(0.5)
            print('Modulator bias: SPD3303X CH%d ON at %.3f V (limit %.3f A)' % (cfg.DC_CHANNEL, cfg.V_QUAD, cfg.DC_CURRENT))
        else:
            bt.ask('MODULATOR BIAS: set the amplitude modulator to quadrature yourself now (SET_AM_BIAS = False).')

    def check_afg(self):
        """Read back the SDG settings: sine, the drive amplitude and 0 V offset."""
        reply = self.afg.instr.query('C%d:BSWV?' % self.cfg.AFG_CH).strip()
        self.readback = reply
        fields = reply.split(' ', 1)[-1].split(',')
        kv = dict(zip(fields[0::2], fields[1::2]))
        num = lambda s: float(''.join(ch for ch in s if ch in '+-.0123456789eE') or 'nan')
        ofst, amp, wv = num(kv.get('OFST', 'nan')), num(kv.get('AMP', 'nan')), kv.get('WVTP', '?')
        if wv != 'SINE' or not np.isfinite(ofst) or abs(ofst) > 1e-3 or not np.isclose(amp, self.cfg.DRIVE_VPP, rtol=0.02):
            raise RuntimeError('SDG read-back is not a %g Vpp sine with 0 V offset: %s' % (self.cfg.DRIVE_VPP, reply))
        return reply

    def on(self):
        self.afg.output_status(channel=self.cfg.AFG_CH, status='ON')

    def set_frequency(self, f):
        self.afg.instr.write('C%d:BSWV FRQ,%.6f' % (self.cfg.AFG_CH, f))
        time.sleep(self.cfg.SETTLE_S)

    def close(self):
        for fn in (lambda: self.afg and self.afg.output_status(channel=self.cfg.AFG_CH, status='OFF'),
                   lambda: self.dc and self.dc.setParameters(channel=self.cfg.DC_CHANNEL, voltage=0.0, current=0.0),
                   lambda: self.dc and self.dc.outputStatus(channel=self.cfg.DC_CHANNEL, status='OFF'),
                   lambda: self.afg and self.afg.CloseConnection(),
                   lambda: self.dc and self.dc.closeConnection()):
            try:
                fn()
            except Exception as e:
                print('cleanup warning:', e)
        print('Modulator: SDG output OFF, bias 0 V and OFF.')


class ScopeDetector:
    """Second detector on the SDS2352X-E. Tone: AC-coupled records at a fine V/div. DC level: DC-coupled -
    either the same channel switched after the tone records (SCOPE_DC_CH = None) or a second channel on a BNC T, read
    from the same acquisition."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.sc = pic.SCOPE_SIGLENT_SDS(IP_address=cfg.SCOPE_IP)
        self.idn = self.sc.idn
        self.same = cfg.SCOPE_DC_CH is None
        self.ch_ac = cfg.SCOPE_AC_CH
        self.ch_dc = cfg.SCOPE_AC_CH if self.same else cfg.SCOPE_DC_CH
        if not self.same:
            self.sc.SetChannel(self.ch_dc, coupling=cfg.SCOPE_DC_COUPLING, vdiv=2.0, offset=0.0,
                               bandwidth_limit=cfg.SCOPE_BWL)
        self.sc.SetChannel(self.ch_ac, coupling=cfg.SCOPE_AC_COUPLING, vdiv=0.01, offset=0.0,
                           bandwidth_limit=cfg.SCOPE_BWL)
        self.vdiv_ac, self.vdiv_dc = 0.01, None

    def _acquire(self, ch):
        for _ in range(3):
            codes, vdiv, ofst, dt = self.sc.Acquire(ch)
            if len(codes):
                return codes, vdiv, ofst, dt
            print('  warning: scope returned an empty waveform, retrying (%s)' % self.sc.Diagnose(ch))
        raise RuntimeError('Scope returned empty waveforms 3 times')

    @staticmethod
    def _volt(codes, vdiv, ofst):
        return codes.astype(float) * vdiv / 25.0 - ofst

    def _set_coupling(self, coupling, vdiv):
        """Same-channel mode only: switch AC <-> DC coupling and wait for the coupling capacitor."""
        cfg = self.cfg
        self.sc.SetChannel(self.ch_ac, coupling=coupling, vdiv=vdiv, offset=0.0, bandwidth_limit=cfg.SCOPE_BWL)
        time.sleep(cfg.SCOPE_SWITCH_SETTLE_S)

    def _dc_scale(self):
        """V/div that puts the DC level at ~3.5 div with offset 0 (no offset error in the DC value)."""
        sc = self.sc
        if self.vdiv_dc is None:
            if self.same:
                self._set_coupling(self.cfg.SCOPE_DC_COUPLING, 2.0)
            else:
                sc.SetVertical(self.ch_dc, 2.0, 0.0)
            codes, vd, of, _ = self._acquire(self.ch_dc)
            self.vdiv_dc = sc.nearest_vdiv(max(abs(float(np.mean(self._volt(codes, vd, of)))), 0.05) / 3.5)
            if not self.same:
                sc.SetVertical(self.ch_dc, self.vdiv_dc, 0.0)
        return self.vdiv_dc

    def measure(self, f0):
        cfg, sc = self.cfg, self.sc
        sc.SetTimebase(sc.nearest_tdiv(cfg.SCOPE_NCYC / f0 / 14.0), cfg.SCOPE_MEMORY)
        self._dc_scale()
        if self.same:
            self._set_coupling(cfg.SCOPE_AC_COUPLING, self.vdiv_ac)
        lo, hi = cfg.SCOPE_PP_CODES
        vdiv = self.vdiv_ac
        for _ in range(12):                                  # AC vertical auto-scale (8 bit: keep the tone large)
            sc.SetVertical(self.ch_ac, vdiv, 0.0)
            codes, vdiv_rb, _, _ = self._acquire(self.ch_ac)
            pp = int(codes.max()) - int(codes.min())
            if codes.max() >= 126 or codes.min() <= -127:
                new = sc.nearest_vdiv(vdiv_rb * 2.0)
            elif pp > hi or pp < lo:
                new = sc.nearest_vdiv(vdiv_rb * max(pp, 4) / 150.0)
            else:
                break
            if new == vdiv_rb:
                break
            vdiv = new
        self.vdiv_ac = vdiv_rb
        vpk2, vdcs, last = [], [], None
        for _ in range(cfg.SCOPE_NACQ):
            codes, vdiv, ofst, dt = self._acquire(self.ch_ac)
            sp = bt.tone_spectrum(self._volt(codes, vdiv, ofst), dt, f0, load=50.0)
            vpk2.append(sp['vpk'] ** 2)
            if not self.same:                                # DC channel of the SAME acquisition
                dcc, vd, of, _ = sc.ReadStopped(self.ch_dc)
                vdcs.append(float(np.mean(self._volt(dcc, vd, of))))
            last = (codes, vdiv, ofst, dt, sp)
        codes, vdiv, ofst, dt, sp = last
        if self.same:                                        # DC level: the same channel, switched to DC coupling
            self._set_coupling(cfg.SCOPE_DC_COUPLING, self.vdiv_dc)
            for _ in range(cfg.SCOPE_NACQ):
                dcc, vd, of, _ = self._acquire(self.ch_dc)
                vdcs.append(float(np.mean(self._volt(dcc, vd, of))))
            self._set_coupling(cfg.SCOPE_AC_COUPLING, self.vdiv_ac)
        vpk, vdc = float(np.sqrt(np.mean(vpk2))), float(np.mean(vdcs))
        pp = int(codes.max()) - int(codes.min())
        clipped = bool(codes.max() >= 126 or codes.min() <= -127 or dcc.max() >= 126 or dcc.min() <= -127)
        return {'vpk': vpk, 'v_dc': vdc, 'v_dc_spread': float(np.ptp(vdcs)),
                'tone_dbc': float(_db((vpk / vdc) ** 2 / 2)), 'snr_db': sp['snr_db'],
                'f_peak_hz': float(sp['f_peak']), 'h2_dbc': sp['h2_dbc'], 'h3_dbc': sp['h3_dbc'], 'pp_codes': pp,
                'clipped': clipped, 'vdiv_ac': vdiv, 'vdiv_dc': vd, 'offset_dc': of, 'dt': dt,
                'dc_mode': 'same channel, switched' if self.same else 'channel %d (BNC T)' % self.ch_dc,
                'codes_ac': codes, 'codes_dc': dcc}

    def close(self):
        try:
            self.sc.Run()
            self.sc.closeConnection()
        except Exception as e:
            print('cleanup warning:', e)


def measure_tone_esa(R, cfg, f0):
    """Narrow ESA sweep around f0 on every channel -> {channel: segment dict} (as rin_utils.RinSetup.measure)."""
    out = {}
    for ch in R.channels:
        rb = ch.esa.configure(f0 - cfg.TONE_SPAN_HZ / 2, f0 + cfg.TONE_SPAN_HZ / 2, cfg.TONE_RBW_HZ,
                              10 * cfg.TONE_RBW_HZ, cfg.TONE_POINTS, cfg.TONE_AVERAGES)
        s = dict(rb, settings=ch.esa.snapshot(), errors=ch.esa.errors())
        s['v_before'], s['v_before_std'] = ch.dc.read()
        t0 = time.time()
        s['dbm'] = ch.esa.acquire()
        s['duration_s'] = time.time() - t0
        s['v_after'], s['v_after_std'] = ch.dc.read()
        s['v_dc'] = 0.5 * (s['v_before'] + s['v_after'])
        s['overload'] = ch.esa.overload()
        s['f'] = np.linspace(s['start_hz'], s['stop_hz'], len(s['dbm']))
        for e in s['errors']:
            print('  WARNING: ESA [%s] reports: %s' % (ch.name, e))
        out[ch.name] = s
    return out


def measure_background(R, cfg):
    """Laser blocked: the ESA span around every tone + Keithley dark level -> {f0: {channel: segment dict}}."""
    bt.ask('BACKGROUND: BLOCK the laser (no light on the detector%s), the detector stays powered.\n'
           '  The ESA measures the span around every tone (%d spans).'
           % ('s' if cfg.SCOPE_ENABLE else '', len(cfg.TONES_HZ)))
    out = {}
    for f0 in cfg.TONES_HZ:
        out[f0] = measure_tone_esa(R, cfg, f0)
        for name, s in out[f0].items():
            print('  background %8s [%s]: median %.1f dBm in %g Hz RBW, Vdc %.4f V'
                  % (rin._hz(f0), name, float(np.median(s['dbm'])), s['rbw_hz'], s['v_dc']))
    bt.ask('Background done. UNBLOCK the laser and wait until it is stable.')
    return out


def collect_hf_files(cfg, f0, t_start, base):
    """Ask for up to HF_FILES_PER_TONE HighFinesse files, each saved after the previous one -> list of parsed dicts.
    Nothing is assumed about them: the Av count is read from each file's header, the order from the order of saving."""
    out, t_prev = [], t_start
    for k in range(cfg.HF_FILES_PER_TONE):
        print('  HIGHFINESSE file %d of %d for %s (any Av count - it is read from the file): RESTART its averaging, wait '
              'until it is complete, then save "raw data"' % (k + 1, cfg.HF_FILES_PER_TONE, rin._hz(f0)))
        hf = rin.collect_highfinesse(cfg, t_prev, '%s_%dHz_hf%d' % (base, int(f0), k + 1))
        if hf is None:                                       # 's' = no (more) HighFinesse files for this tone
            break
        hf['save_order'] = k + 1
        t_prev = os.path.getmtime(hf['file'])               # the next file must be saved after this one
        out.append(hf)
    return out


# =============================================================================
# Analysis
# =============================================================================

def esa_gain(cfg, ch, f0):
    """W at the ESA input -> open-circuit PD voltage^2 (as compute_rin)."""
    r_in, r_out = float(cfg.ESA_INPUT_OHM), float(ch.spec['pd_output_ohm'])
    return r_in * ((r_in + r_out) / r_in) ** 2 * 10 ** (float(ch.cal['loss_fn'](np.array([f0]))[0]) / 10.0)


def esa_v_signal(ch, v_dc, v_dark=None):
    dcr = ch.cal['dc_ratio']
    fix = lambda x: x / dcr(x) if dcr else x
    return fix(v_dc) - (fix(v_dark) if v_dark is not None else float(ch.spec['dark_offset_V']))


def analyse_esa(cfg, ch, s, f0, bg=None):
    """One ESA span around f0 -> tone (peak, integrated) and the noise next to it, all relative to V_dc^2.
    bg = the same span with the laser blocked (MEASURE_BACKGROUND): its power is subtracted from the noise next to the
    tone ('noise' = laser noise above the floor, 'floor' = the blocked level), its Keithley reading is the dark level."""
    f, p = s['f'], 1e-3 * 10 ** (np.asarray(s['dbm'], float) / 10.0)        # W in the RBW
    enbw = ch.spec['noise_bw_factor'] * s['rbw_hz']
    df = float(np.median(np.diff(f)))
    d = np.abs(f - f0)
    near, side = d <= cfg.TONE_HALF_WIDTH_HZ, (d >= cfg.ESA_NOISE_HZ[0]) & (d <= cfg.ESA_NOISE_HZ[1])
    noise_raw = float(np.mean(p[side]))
    floor = np.nan
    if bg is not None:
        if len(bg['f']) != len(f) or not np.allclose(bg['f'], f):
            raise ValueError('background span at %s does not match the measurement' % rin._hz(f0))
        floor = float(np.mean(1e-3 * 10 ** (np.asarray(bg['dbm'], float)[side] / 10.0)))
    noise = noise_raw - floor if np.isfinite(floor) else noise_raw
    k = int(np.argmax(np.where(near, p, -np.inf)))
    g = esa_gain(cfg, ch, f0)
    v = esa_v_signal(ch, s['v_dc'], bg['v_dc'] if bg is not None else None)
    if v < cfg.MIN_SIGNAL_V:
        raise RuntimeError('[%s] only %.4f V above the dark level at %s - no light on the detector (laser still blocked?)'
                           % (ch.name, v, rin._hz(f0)))
    peak, integ = p[k], float(np.sum(p[near] - noise_raw) * df / enbw)
    rel = lambda w: float(_db(w * g / v ** 2))
    return {'v_dc': s['v_dc'], 'v_signal': v, 'v_dark': bg['v_dc'] if bg is not None else float(ch.spec['dark_offset_V']),
            'peak_dbm': float(10 * np.log10(peak * 1e3)), 'f_peak_hz': float(f[k]),
            'tone_peak_dbc': rel(peak), 'tone_int_dbc': rel(integ),
            'noise_dbc_hz': rel(noise / enbw), 'noise_as_measured_dbc_hz': rel(noise_raw / enbw),
            'floor_dbc_hz': rel(floor / enbw) if np.isfinite(floor) else np.nan,
            'snr_db': float(_db(peak / noise_raw)), 'loss_db': float(ch.cal['loss_fn'](np.array([f0]))[0]),
            'overload': s['overload'] if s['overload'] is not None else -1}


def combine_esa(e1, e2):
    """ESA before and after the HighFinesse files -> power mean of the levels + drift (after - before, dB)."""
    if e2 is None:
        return dict(e1, drift_db=np.nan)
    out = dict(e1)
    for k in ('tone_peak_dbc', 'tone_int_dbc', 'noise_dbc_hz', 'noise_as_measured_dbc_hz', 'floor_dbc_hz'):
        out[k] = _power_mean_db([e1[k], e2[k]])
    out['v_dc'] = 0.5 * (e1['v_dc'] + e2['v_dc'])
    out['snr_db'] = min(e1['snr_db'], e2['snr_db'])
    out['overload'] = max(e1['overload'], e2['overload'])
    out['drift_db'] = e2['tone_peak_dbc'] - e1['tone_peak_dbc']
    return out


def analyse_hf(cfg, hf, f0):
    """Tone level (as exported) and the corrected noise next to it, from one HighFinesse RIN export."""
    f, lin = hf['f'], 10 ** (hf['db'] / 10.0)
    df = float(np.median(np.diff(f)))
    d = np.abs(f - f0)
    near, side = d <= cfg.HF_TONE_HALF_WIDTH_HZ, (d >= cfg.HF_NOISE_HZ[0]) & (d <= cfg.HF_NOISE_HZ[1])
    noise_raw = float(np.mean(lin[side]))
    noise = noise_raw * 10 ** (hf.get('correction_db', 0.0) / 10.0)          # corrected for the dB averaging
    tone = float(np.sum(lin[near] - noise) * df)
    k = int(np.argmax(np.where(near, lin, -np.inf)))
    return {'tone_dbc': float(_db(tone)), 'f_peak_hz': float(f[k]), 'noise_dbc_hz': float(_db(noise)),
            'noise_as_exported_dbc_hz': float(_db(noise_raw)), 'snr_db': float(_db(lin[k] / noise_raw)),
            'av_count': hf.get('av_count') if hf.get('av_count') is not None else -1,
            'correction_db': hf.get('correction_db', 0.0), 'save_order': hf.get('save_order', -1),
            'file': os.path.basename(hf['file']), 'timestamp': hf['header'].get('Timestamp', '?')}


def tone_summary(f0, e, hfs, sc, exp_dbc):
    """One tone of one ESA channel: ESA, every HighFinesse file, per-Av-count groups, all combined, scope, expected."""
    nan = np.nan
    row = {'f': f0, 'v_dc': e['v_dc'], 'esa_peak': e['tone_peak_dbc'], 'esa_int': e['tone_int_dbc'],
           'esa_snr': e['snr_db'], 'esa_noise': e['noise_dbc_hz'], 'esa_floor': e['floor_dbc_hz'],
           'esa_drift': e['drift_db'],
           'm_esa': 100 * np.sqrt(2 * 10 ** (e['tone_peak_dbc'] / 10.0)),
           'exp': exp_dbc if exp_dbc is not None else nan, 'groups': {}}
    files = []
    for h in hfs:
        files.append(dict(h, f=f0, esa_peak=e['tone_peak_dbc'], esa_noise=e['noise_dbc_hz'],
                          d_tone=e['tone_peak_dbc'] - h['tone_dbc'], d_noise=e['noise_dbc_hz'] - h['noise_dbc_hz']))
    for n in sorted({h['av_count'] for h in hfs}):
        grp = [h for h in hfs if h['av_count'] == n]
        tone, noise = _power_mean_db([h['tone_dbc'] for h in grp]), _power_mean_db([h['noise_dbc_hz'] for h in grp])
        row['groups'][n] = {'n_files': len(grp), 'hf_tone': tone, 'hf_noise': noise,
                            'd_tone': row['esa_peak'] - tone, 'd_noise': row['esa_noise'] - noise}
    row['hf_tone'] = _power_mean_db([h['tone_dbc'] for h in hfs])
    row['hf_noise'] = _power_mean_db([h['noise_dbc_hz'] for h in hfs])
    row['n_hf_files'] = len(hfs)
    row['d_tone'] = row['esa_peak'] - row['hf_tone']
    row['d_tone_int'] = row['esa_int'] - row['hf_tone']
    row['d_noise'] = row['esa_noise'] - row['hf_noise']
    row['scope_tone'] = sc['tone_dbc'] if sc else nan
    row['scope_snr'] = sc['snr_db'] if sc else nan
    row['d_esa_scope'] = row['esa_peak'] - row['scope_tone']
    row['d_hf_scope'] = row['hf_tone'] - row['scope_tone']
    row['d_esa_exp'] = row['esa_peak'] - row['exp']
    row['d_hf_exp'] = row['hf_tone'] - row['exp']
    row['d_scope_exp'] = row['scope_tone'] - row['exp']
    return row, files


BASE_COLUMNS = [
    ('frequency_Hz', 'f'), ('v_dc_V', 'v_dc'),
    ('esa_tone_peak_dBc', 'esa_peak'), ('esa_tone_integrated_dBc', 'esa_int'), ('esa_snr_dB', 'esa_snr'),
    ('esa_noise_above_floor_dBc_Hz', 'esa_noise'), ('esa_floor_laser_blocked_dBc_Hz', 'esa_floor'),
    ('esa_drift_after_minus_before_dB', 'esa_drift'), ('esa_modulation_depth_pct', 'm_esa'),
    ('hf_n_files', 'n_hf_files'), ('hf_tone_all_files_dBc', 'hf_tone'), ('hf_noise_all_files_corrected_dBc_Hz', 'hf_noise'),
    ('esa_minus_hf_tone_dB', 'd_tone'), ('esa_integrated_minus_hf_tone_dB', 'd_tone_int'),
    ('esa_minus_hf_noise_dB', 'd_noise'),
    ('scope_tone_dBc', 'scope_tone'), ('scope_snr_dB', 'scope_snr'),
    ('esa_minus_scope_dB', 'd_esa_scope'), ('hf_minus_scope_dB', 'd_hf_scope'),
    ('expected_tone_dBc', 'exp'), ('esa_minus_expected_dB', 'd_esa_exp'), ('hf_minus_expected_dB', 'd_hf_exp'),
    ('scope_minus_expected_dB', 'd_scope_exp')]
GROUP_COLUMNS = [('hf_files_av%s', 'n_files'), ('hf_tone_av%s_dBc', 'hf_tone'),
                 ('hf_noise_av%s_corrected_dBc_Hz', 'hf_noise'), ('esa_minus_hf_tone_av%s_dB', 'd_tone'),
                 ('esa_minus_hf_noise_av%s_dB', 'd_noise')]
FILE_COLUMNS = [('frequency_Hz', 'f'), ('file', 'file'), ('hf_timestamp', 'timestamp'), ('av_count', 'av_count'),
                ('save_order', 'save_order'), ('db_averaging_correction_dB', 'correction_db'),
                ('hf_tone_dBc', 'tone_dbc'), ('hf_snr_dB', 'snr_db'), ('hf_noise_corrected_dBc_Hz', 'noise_dbc_hz'),
                ('hf_noise_as_exported_dBc_Hz', 'noise_as_exported_dbc_hz'), ('esa_tone_peak_dBc', 'esa_peak'),
                ('esa_noise_dBc_Hz', 'esa_noise'), ('esa_minus_hf_tone_dB', 'd_tone'), ('esa_minus_hf_noise_dB', 'd_noise')]


def av_groups(rows):
    return sorted({n for r in rows for n in r['groups']})


def flat_row(r, groups):
    out = {c: r[k] for c, k in BASE_COLUMNS}
    for n in groups:
        g = r['groups'].get(n)
        for c, k in GROUP_COLUMNS:
            out[c % n] = g[k] if g else (0 if k == 'n_files' else np.nan)
    return out


# =============================================================================
# Saving
# =============================================================================

def _fmt(x):
    return x if isinstance(x, str) else '%.6g' % x


def save_csv(path, rows):
    if not rows:
        return
    cols = list(rows[0])
    with open(path, 'w', newline='') as fh:
        fh.write(','.join(cols) + '\n')
        for r in rows:
            fh.write(','.join(_fmt(r[c]) for c in cols) + '\n')
    print('  Saved: %s' % path)


_GROUP_MARK = ['s', 'D', 'v', 'P', '*']


def make_plot(cfg, label, stamp, rows_by_ch, base_path, show):
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 8.6), sharex=True, gridspec_kw={'height_ratios': [1.3, 1.9]})
        fig.patch.set_facecolor(bt.SURFACE)
        n_ch = len(rows_by_ch)
        hf_col = bt.CATEGORICAL[min(n_ch, len(bt.CATEGORICAL) - 1)]
        for i, (name, rows) in enumerate(rows_by_ch.items()):
            c = bt.CATEGORICAL[i]
            f = np.array([r['f'] for r in rows])
            get = lambda k: np.array([r[k] for r in rows], float)
            ax1.plot(f, get('esa_peak'), 'o-', color=c, ms=4, lw=1.4, label='%s ESA (peak)' % name)
            ax1.plot(f, get('esa_int'), 'x', color=c, ms=5, label='%s ESA (integrated, as the RIN)' % name)
            for j, n in enumerate(av_groups(rows)):
                gv = lambda k: np.array([r['groups'][n][k] if n in r['groups'] else np.nan for r in rows], float)
                mk = _GROUP_MARK[j % len(_GROUP_MARK)]
                if i == 0:
                    ax1.plot(f, gv('hf_tone'), mk, color=hf_col, ms=5, mfc='none',
                             label='HighFinesse, Av count %s (as exported)' % n)
                ax2.plot(f, gv('d_tone'), mk + '-', color=c, ms=5, lw=1.4, mfc='none' if j else c,
                         label='%s - HighFinesse, TONE, Av count %s' % (name, n))
                ax2.plot(f, gv('d_noise'), mk + ':', color=c, ms=4, lw=0.9, alpha=0.7,
                         label='%s - HighFinesse, NOISE next to the tone, Av count %s (corrected)' % (name, n))
            if np.isfinite(get('scope_tone')).any():
                if i == 0:
                    ax1.plot(f, get('scope_tone'), '^-', color=bt.INK2, ms=4, lw=1.2,
                             label='scope, %s (1 Mohm, AC / DC)' % cfg.SCOPE_DETECTOR)
                    ax2.plot(f, get('d_hf_scope'), 'v--', color=hf_col, ms=5, lw=1.2,
                             label='HighFinesse - scope (TONE, all files)')
                ax2.plot(f, get('d_esa_scope'), '^--', color=c, ms=5, lw=1.2, label='%s ESA - scope (TONE)' % name)
            if np.isfinite(get('exp')).any():
                ax2.plot(f, get('d_esa_exp'), '^:', color=c, ms=4, lw=1.0, label='%s ESA - expected (V_PI)' % name)
        rows = next(iter(rows_by_ch.values()))
        if rows and np.isfinite(rows[0]['exp']):
            ax1.axhline(rows[0]['exp'], color=bt.MUTED, ls='--', lw=1.0,
                        label='expected from V_PI = %g V, %g Vpp' % (cfg.V_PI, cfg.DRIVE_VPP))
        ax1.set_ylabel('Tone level m^2/2 (dBc)')
        ax1.set_title('AM response   %s   %s\nsame sine intensity modulation on every arm, %g Vpp drive'
                      % (label, stamp, cfg.DRIVE_VPP), loc='left', color=bt.INK, fontsize=10)
        ax2.axhline(0, color=bt.AXIS, lw=0.9)
        ax2.set_ylabel('Difference (dB)\n(tone: no dB-averaging correction;\nnoise: HighFinesse corrected)')
        ax2.set_xlabel('Frequency (Hz)')
        for ax in (ax1, ax2):
            ax.set_xscale('log')
            bt._style_axes(ax)
            ax.legend(fontsize=7, frameon=False, labelcolor=bt.INK2)
        fig.tight_layout()
        rin._finish(fig, base_path, show)


def write_h5(path, cfg, R, scope, label, stamp, tones, rows_by_ch, files_by_ch, mod, log_idx, prompt_idx):
    ckw = dict(compression='gzip', compression_opts=6, shuffle=True)
    with h5py.File(path, 'w') as h:
        h.attrs['label'], h.attrs['created'] = label, stamp
        h.attrs['script'] = 'am_response_test.py (+ rin_utils.py, rin_measurement.py)'
        h.attrs['doc'] = __doc__
        h.attrs['afg_readback'] = getattr(mod, 'readback', '')
        h.attrs['scope_idn'] = scope.idn if scope else 'None'
        cg = h.create_group('config')
        for k, v in vars(cfg).items():
            cg.attrs[k] = bt._attr(v)
        cg.attrs['config_json'] = json.dumps(vars(cfg), default=str, indent=1, sort_keys=True)
        bt._write_provenance(h)
        for name in ('am_response_test.py', 'rin_utils.py', 'rin_measurement.py'):
            data = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), 'rb').read()
            ds = h['script'].create_dataset(name, data=np.frombuffer(data, np.uint8), compression='gzip')
            ds.attrs['sha256'] = hashlib.sha256(data).hexdigest()
        lg = h.create_group('log')
        lg.create_dataset('console_log', data='\n'.join(R.tee.lines[log_idx:]), dtype=h5py.string_dtype('utf-8'))
        lg.create_dataset('prompts', data=['[%s] %s' % pr for pr in bt.PROMPT_LOG[prompt_idx:]],
                          dtype=h5py.string_dtype('utf-8'))
        for ch in R.channels:
            g = h.create_group('channels/%s' % ch.name)
            g.attrs['esa_idn'], g.attrs['keithley_idn'] = ch.esa.idn, ch.dc.idn
            for k, v in ch.cal.items():
                if not callable(v):
                    g.attrs['cal_' + k] = bt._attr(v)
            for k, v in ch.spec.items():
                g.attrs['setting_' + k] = bt._attr(v)
            rows = rows_by_ch[ch.name]
            flat = [flat_row(r, av_groups(rows)) for r in rows]
            for col in (flat[0] if flat else {}):
                g.create_dataset('summary/' + col, data=[r[col] for r in flat])
            for col, key in FILE_COLUMNS:
                vals = [r[key] for r in files_by_ch[ch.name]]
                g.create_dataset('highfinesse_files/' + col,
                                 data=vals if not vals or not isinstance(vals[0], str) else np.array(vals, dtype=object),
                                 dtype=h5py.string_dtype('utf-8') if vals and isinstance(vals[0], str) else None)
        for i, t in enumerate(tones):
            tg = h.create_group('tones/%02d_%dHz' % (i, int(round(t['f']))))
            tg.attrs['frequency_Hz'] = t['f']
            groups = [('esa/', t['esa'], t['esa_result'])]
            if t.get('esa_after'):
                groups.append(('esa_after_hf/', t['esa_after'], t.get('esa_result_after') or {}))
            if t.get('background'):
                groups.append(('background_laser_blocked/', t['background'], {}))
            for prefix, segs, results in groups:
                for name, s in segs.items():
                    eg = tg.create_group(prefix + name)
                    eg.create_dataset('frequency_Hz', data=s['f'], **ckw)
                    eg.create_dataset('trace_dBm', data=np.asarray(s['dbm'], np.float32), **ckw)
                    for k, v in s.items():
                        if k not in ('f', 'dbm', 'settings', 'errors'):
                            eg.attrs[k] = bt._attr(v)
                    sg = eg.create_group('esa_settings')
                    for cmd, reply in s['settings'].items():
                        sg.attrs[cmd] = reply
                    for k, v in (results.get(name) or {}).items():
                        eg.attrs['result_' + k] = bt._attr(v)
            for k, (hf, res) in enumerate(zip(t['hf'], t['hf_result'])):
                hg = tg.create_group('highfinesse/hf%d' % (k + 1))
                hg.create_dataset('frequency_Hz', data=hf['f'], **ckw)
                hg.create_dataset('rin_dB_Hz', data=hf['db'], **ckw)              # as exported
                hg.attrs['header_json'] = json.dumps(hf['header'])
                hg.attrs['file'] = hf['file']
                hg.attrs['correction_text'] = hf.get('correction_text', '')
                for kk, v in res.items():
                    hg.attrs['result_' + kk] = bt._attr(v)
                if os.path.isfile(hf['file']):
                    hg.create_dataset('file_bytes', data=np.frombuffer(open(hf['file'], 'rb').read(), np.uint8),
                                      compression='gzip')
            if t.get('scope'):
                s = t['scope']
                sg = tg.create_group('scope')
                sg.create_dataset('codes_ac_last_record', data=s['codes_ac'], **ckw)
                sg.create_dataset('codes_dc_last_record', data=s['codes_dc'], **ckw)
                sg.attrs['volt'] = 'code * vdiv / 25 - offset'
                for k, v in s.items():
                    if not k.startswith('codes'):
                        sg.attrs[k] = bt._attr(v)
    print('  HDF5 saved: %s' % path)


# =============================================================================
def main():
    cfg = build_cfg()
    exp_dbc, exp_m = expected_level_dbc(cfg)
    label = bt.safe_name(bt.ask_label(cfg.SAVE_FOLDER, cfg.DEFAULT_SAVE_LABEL, title='AM response test')) or 'unlabelled'
    folder = os.path.join(cfg.SAVE_FOLDER, label)
    os.makedirs(folder, exist_ok=True)
    if cfg.COMPARE_HIGHFINESSE:
        os.makedirs(rin.highfinesse_dir(cfg), exist_ok=True)
    stamp = pic.datetimestring()
    base = os.path.join(folder, stamp + '_am')
    print('Label: %s\nSaving in: %s\nTones: %s' % (label, folder, ', '.join(rin._hz(f) for f in cfg.TONES_HZ)))
    if cfg.COMPARE_HIGHFINESSE:
        print('HighFinesse: up to %d file(s) per tone (Av count read from each file)' % cfg.HF_FILES_PER_TONE)
    if exp_dbc is not None:
        print('Expected from the modulator: m = %.3f %% -> %.2f dBc (V_PI %g V, %g Vpp)' % (100 * exp_m, exp_dbc,
                                                                                         cfg.V_PI, cfg.DRIVE_VPP))
    R = rin.RinSetup(cfg)
    log_idx, prompt_idx = 0, len(bt.PROMPT_LOG)
    mod = scope = None
    tones = []
    rows_by_ch = {ch.name: [] for ch in R.channels}
    files_by_ch = {ch.name: [] for ch in R.channels}
    try:
        R.prepare_dc_monitors()
        R.confirm_dc_block()                       # ESA DC-coupled only after 'yes' (EF500 at the ESA input)
        if cfg.SCOPE_ENABLE:
            scope = ScopeDetector(cfg)
            print('Scope: %s  CH%d %s = tone, DC level of %s: %s'
                  % (scope.idn, cfg.SCOPE_AC_CH, cfg.SCOPE_AC_COUPLING, cfg.SCOPE_DETECTOR,
                     ('the same channel switched to %s' % cfg.SCOPE_DC_COUPLING) if scope.same else
                     'CH%d %s (BNC T)' % (cfg.SCOPE_DC_CH, cfg.SCOPE_DC_COUPLING)))
        background = measure_background(R, cfg) if cfg.MEASURE_BACKGROUND else {}
        mod = Modulator(cfg)
        mod.set_frequency(cfg.TONES_HZ[0])
        mod.on()
        print('SDG CH%d ON: %g Vpp sine, 0 V offset (read back: %s)' % (cfg.AFG_CH, cfg.DRIVE_VPP, mod.readback))
        for i, f0 in enumerate(cfg.TONES_HZ):
            print('\n----- tone %d of %d: %s -----' % (i + 1, len(cfg.TONES_HZ), rin._hz(f0)))
            mod.set_frequency(f0)
            t_start = time.time()
            t = {'f': f0, 'esa': measure_tone_esa(R, cfg, f0), 'esa_after': None, 'esa_result': {}, 'hf': [],
                 'hf_result': [], 'scope': None, 'background': background.get(f0)}
            bg_of = lambda name: (t['background'] or {}).get(name)
            for ch in R.channels:
                e = analyse_esa(cfg, ch, t['esa'][ch.name], f0, bg_of(ch.name))
                t['esa_result'][ch.name] = e
                flag = ''
                if e['overload'] > 0:
                    flag += '  <-- ESA OVERLOAD: lower DRIVE_VPP or raise ESA_REF_LEVEL_DBM'
                if e['peak_dbm'] > cfg.ESA_REF_LEVEL_DBM - 6:
                    flag += '  <-- tone within 6 dB of the reference level'
                if abs(e['f_peak_hz'] - f0) > 2 * cfg.TONE_RBW_HZ:
                    flag += '  <-- peak not at the tone frequency'
                print('  [%s] ESA: tone %.2f dBm  ->  %.2f dBc (peak), %.2f dBc (integrated), m = %.3f %%, '
                      'SNR %.0f dB, noise %.1f dBc/Hz%s, Vdc %.4f V%s'
                      % (ch.name, e['peak_dbm'], e['tone_peak_dbc'], e['tone_int_dbc'],
                         100 * np.sqrt(2 * 10 ** (e['tone_peak_dbc'] / 10)), e['snr_db'], e['noise_dbc_hz'],
                         (' (floor %.1f)' % e['floor_dbc_hz']) if np.isfinite(e['floor_dbc_hz']) else '', e['v_dc'], flag))
                if cfg.SAVE_SCREENSHOTS and any(abs(f0 - s) < 1 for s in cfg.SCREENSHOT_TONES_HZ):
                    try:
                        bt.save_screenshot_png(ch.esa.drv, '%s_%dHz_%s_esa.png' % (base, int(f0), ch.name))
                    except Exception as ex:
                        print('  warning: screenshot failed (%s)' % ex)
            if scope:
                s = scope.measure(f0)
                t['scope'] = s
                print('  scope (%s): Vdc %.4f V, tone %.3f mV pk -> %.2f dBc, m = %.3f %%, SNR %.0f dB, %d codes pk-pk%s'
                      % (cfg.SCOPE_DETECTOR, s['v_dc'], 1e3 * s['vpk'], s['tone_dbc'], 100 * s['vpk'] / s['v_dc'],
                         s['snr_db'], s['pp_codes'], '  <-- CLIPPED' if s['clipped'] else ''))
            if cfg.COMPARE_HIGHFINESSE:
                for hf in collect_hf_files(cfg, f0, t_start, base):
                    h = analyse_hf(cfg, hf, f0)
                    t['hf'].append(hf)
                    t['hf_result'].append(h)
                    print('  HighFinesse %s: Av count %s -> tone %.2f dBc (as exported, SNR %.0f dB), noise %.1f dBc/Hz '
                          '(corrected %+.2f dB)' % (h['file'], h['av_count'], h['tone_dbc'], h['snr_db'],
                                                    h['noise_dbc_hz'], h['correction_db']))
                    if abs(h['f_peak_hz'] - f0) > 100:
                        print('  WARNING: the HighFinesse peak is at %s, not at the tone' % rin._hz(h['f_peak_hz']))
            if cfg.ESA_REMEASURE_AFTER_HF and t['hf']:
                t['esa_after'] = measure_tone_esa(R, cfg, f0)
            for ch in R.channels:
                e2 = analyse_esa(cfg, ch, t['esa_after'][ch.name], f0, bg_of(ch.name)) if t['esa_after'] else None
                t['esa_result_after'] = dict(t.get('esa_result_after') or {}, **({ch.name: e2} if e2 else {}))
                e = combine_esa(t['esa_result'][ch.name], e2)
                if e2:
                    print('  [%s] ESA again after the HighFinesse: tone %.2f dBc -> drift %+.2f dB%s'
                          % (ch.name, e2['tone_peak_dbc'], e['drift_db'],
                             '  <-- the modulation depth changed during this tone' if abs(e['drift_db']) > cfg.DRIFT_WARN_DB
                             else ''))
                r, files = tone_summary(f0, e, t['hf_result'], t['scope'], exp_dbc)
                rows_by_ch[ch.name].append(r)
                files_by_ch[ch.name].extend(files)
                parts = ['Av %s: tone %+.2f, noise %+.2f' % (n, g['d_tone'], g['d_noise']) for n, g in r['groups'].items()]
                print('  [%s] ESA - HighFinesse (dB): %s%s%s'
                      % (ch.name, '   '.join(parts) or 'no HighFinesse file',
                         ('   | ESA - scope %+.2f, HF - scope %+.2f' % (r['d_esa_scope'], r['d_hf_scope']))
                         if scope else '',
                         ('   | ESA - expected %+.2f' % r['d_esa_exp']) if exp_dbc is not None else ''))
            tones.append(t)
    except rin.NotConfirmed as e:
        print('\n%s' % e)
    finally:
        if mod:
            mod.close()
        if scope:
            scope.close()
        if tones:
            print('\nSaving ...')
            try:
                write_h5(base + '_data.h5', cfg, R, scope, label, stamp, tones, rows_by_ch, files_by_ch, mod,
                         log_idx, prompt_idx)
                for name in rows_by_ch:
                    suffix = ('_' + name) if len(rows_by_ch) > 1 else ''
                    rows = rows_by_ch[name]
                    save_csv(base + '_summary%s.csv' % suffix, [flat_row(r, av_groups(rows)) for r in rows])
                    save_csv(base + '_highfinesse_files%s.csv' % suffix,
                             [{c: r[k] for c, k in FILE_COLUMNS} for r in files_by_ch[name]])
                make_plot(cfg, label, stamp, rows_by_ch, base + '_response', cfg.SHOW_PLOTS)
            except Exception as e:
                print('  warning: saving failed partly (%s)' % e)
            with open(base + '_log.txt', 'w', encoding='utf-8') as fh:
                fh.write('\n'.join(R.tee.lines[log_idx:]) + '\n')
        R.close()
        if cfg.SHOW_PLOTS and tones:
            plt.show()


if __name__ == '__main__':
    main()
