#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AM response test: the same sine intensity modulation seen by the ESA chain and by the HighFinesse
==================================================================================================

Why
    The RIN of every laser measured with the ESA chain is ~1 dB below the HighFinesse in the middle of the band
    (after the HighFinesse dB-averaging correction), the same for NKT, Agilent and PPCL. A steady tone puts a KNOWN,
    identical relative modulation on both arms of the splitter, so
        ESA - HighFinesse (tone)   = the difference of the two frequency responses, no noise statistics involved
                                     (a steady tone is not biased by the HighFinesse dB averaging -> no correction)
        ESA - HighFinesse (noise)  = the same comparison on the laser noise next to each tone (HighFinesse corrected),
                                     measured in the same run - if both agree, the dB-averaging correction holds
        ESA / HF - expected        = absolute check, from the modulator: m = 2 J1(pi V_pk / V_PI)   (only if V_PI is set)

Wiring (as in Mid-IR/Eye_diagram_lab.py for the modulator, as in rin_measurement.py for the detection)
    laser -> amplitude modulator (MZI) -> splitter -> arm 1: PD -> bias tee -> EF500 -> ESA (DC port -> Keithley)
                                                    -> arm 2: HighFinesse
    modulator bias : SPD3303X (DC_IP) at V_QUAD (quadrature)     modulator RF : SDG6022X (AFG_IP) pure AC sine
    The SDG output is a pure sine with 0 V offset, the bias comes from the DC supply only (as in the eye diagram).

What happens per tone
    1. the SDG is set to the tone frequency (output stays on, DRIVE_VPP)
    2. ESA: narrow span around the tone (TONE_SPAN_HZ, TONE_RBW_HZ, TONE_POINTS, TONE_AVERAGES; RMS detector, power
       average - the same ESA, DC coupling, attenuation and safety logic as rin_measurement.py), Keithley before/after
    3. HighFinesse (COMPARE_HIGHFINESSE): you restart its averaging, wait for the Av count and save "raw data" (as in
       rin_measurement.py; a screenshot is optional - answer 'n')

How the tone level is obtained (all as relative power of the tone, dBc = m^2 / 2, m = modulation depth)
    ESA peak       : highest trace point (power in the RBW = tone power, no noise bandwidth needed; ~10 points per RBW,
                     so < 0.05 dB lost to the point spacing). This is the main ESA number.
    ESA integrated : sum of (trace - noise) over +-TONE_HALF_WIDTH_HZ / (noise_bw_factor x RBW) - the way the RIN
                     measurement treats every point, i.e. it also tests the noise-bandwidth factor.
    HighFinesse    : sum of (density - noise) x line spacing over +-HF_TONE_HALF_WIDTH_HZ of its RIN export, as
                     exported (no dB-averaging correction for a steady tone; its noise baseline IS corrected).
    Both are converted exactly as in rin_utils.compute_rin: ESA power -> open-circuit PD voltage (50 ohm divider,
    bias tee + DC block loss of the calibration) / V_dc^2 (Keithley, corrected to the reading without the tee).
    Noise next to each tone: ESA mean of +-ESA_NOISE_HZ, HighFinesse mean of +-HF_NOISE_HZ (corrected), in dBc/Hz.

Output in SAVE_FOLDER/<label>/ :
    <timestamp>_am_data.h5        everything: settings, every ESA trace, every HighFinesse file, results, log, sources
    <timestamp>_am_summary.csv    one row per tone
    <timestamp>_am_response.pdf/.svg
    <timestamp>_am_<f>Hz_highfinesse.txt (+ screenshot)   copies of the HighFinesse files

Use the NKT (or another laser with high RIN): the noise comparison next to the tones needs RIN well above the
HighFinesse floor. Keep the tone well below saturation: DRIVE_VPP = 20 mV with V_PI ~ 3.9 V gives m ~ 0.8 % (-45 dBc).
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
HIGHFINESSE_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\RIN\HighFinesse'   # where you save the HF files
COMPARE_HIGHFINESSE = True
SHOW_PLOTS = True

# --- tones ---
TONES_HZ = [10e3, 20e3, 50e3, 100e3, 200e3, 300e3, 500e3, 700e3, 1e6, 1.5e6, 2e6, 3e6, 5e6, 8e6]
# multiples of 100 Hz (on the 50 Hz lines of the HighFinesse and on an ESA point); >= 6 kHz (noise windows)
SETTLE_S = 0.5                    # wait after changing the tone frequency

# --- modulator drive: SDG6022X, pure AC sine (as Eye_diagram_lab.py) ---
AFG_IP = '192.168.1.101'
AFG_CH = 1
AFG_LOAD = 50                     # SDG load setting (50 or 'HZ'): must match the modulator RF input, else DRIVE_VPP is off
DRIVE_VPP = 0.02                  # [V] peak-to-peak at the modulator. 20 mV ~ m = 0.8 % for V_PI = 3.9 V

# --- modulator bias: SPD3303X (as Eye_diagram_lab.py) ---
SET_AM_BIAS = True                # False: you set the bias yourself (asked at the start)
DC_IP = '192.168.1.31'
DC_CHANNEL = 1
DC_CURRENT = 0.01                 # [A] current limit
MAX_DC_VOLT = 7.0                 # [V] hard limit (also enforced in DC_Siglent)
V_QUAD = 1.95                     # [V] bias at quadrature (amplitude_modulator_characterization.py: V_quad)
V_PI = None                       # [V] half-wave voltage = V_max - V_min of the AM characterization (eye diagram:
                                  # V_PP_MANUAL = 3.9). None = no expected level. Only right if the RF and DC Vpi are equal
                                  # and the bias is at quadrature; a bias off quadrature lowers m by cos(phase) for BOTH
                                  # instruments alike, so ESA - HighFinesse is not affected.

# --- ESA per tone ---
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
    if not TONE_POINTS >= 5 * TONE_SPAN_HZ / TONE_RBW_HZ:
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


# =============================================================================
# Analysis
# =============================================================================

def esa_gain(cfg, ch, f0):
    """W at the ESA input -> open-circuit PD voltage^2 (as compute_rin)."""
    r_in, r_out = float(cfg.ESA_INPUT_OHM), float(ch.spec['pd_output_ohm'])
    return r_in * ((r_in + r_out) / r_in) ** 2 * 10 ** (float(ch.cal['loss_fn'](np.array([f0]))[0]) / 10.0)


def esa_v_signal(ch, v_dc):
    dcr = ch.cal['dc_ratio']
    return (v_dc / dcr(v_dc) if dcr else v_dc) - float(ch.spec['dark_offset_V'])


def analyse_esa(cfg, ch, s, f0):
    f, p = s['f'], 1e-3 * 10 ** (np.asarray(s['dbm'], float) / 10.0)        # W in the RBW
    enbw = ch.spec['noise_bw_factor'] * s['rbw_hz']
    df = float(np.median(np.diff(f)))
    d = np.abs(f - f0)
    near, side = d <= cfg.TONE_HALF_WIDTH_HZ, (d >= cfg.ESA_NOISE_HZ[0]) & (d <= cfg.ESA_NOISE_HZ[1])
    noise = float(np.mean(p[side]))
    k = int(np.argmax(np.where(near, p, -np.inf)))
    g, v = esa_gain(cfg, ch, f0), esa_v_signal(ch, s['v_dc'])
    peak, integ = p[k], float(np.sum(p[near] - noise) * df / enbw)
    return {'v_dc': s['v_dc'], 'v_signal': v, 'peak_dbm': float(10 * np.log10(peak * 1e3)), 'f_peak_hz': float(f[k]),
            'tone_peak_dbc': float(_db(peak * g / v ** 2)), 'tone_int_dbc': float(_db(integ * g / v ** 2)),
            'noise_dbc_hz': float(_db(noise / enbw * g / v ** 2)), 'snr_db': float(_db(peak / noise)),
            'loss_db': float(ch.cal['loss_fn'](np.array([f0]))[0]),
            'overload': s['overload'] if s['overload'] is not None else -1}


def analyse_hf(cfg, hf, f0):
    """Tone level (as exported) and the corrected noise next to it, from a HighFinesse RIN export."""
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
            'av_count': hf.get('av_count'), 'correction_db': hf.get('correction_db', 0.0),
            'file': hf['file'], 'timestamp': hf['header'].get('Timestamp', '?')}


SUMMARY_COLUMNS = [
    ('frequency_Hz', 'f'), ('v_dc_V', 'v_dc'),
    ('esa_tone_peak_dBc', 'esa_peak'), ('esa_tone_integrated_dBc', 'esa_int'), ('esa_snr_dB', 'esa_snr'),
    ('hf_tone_dBc', 'hf_tone'), ('hf_snr_dB', 'hf_snr'),
    ('esa_minus_hf_tone_dB', 'd_tone'), ('esa_integrated_minus_hf_tone_dB', 'd_tone_int'),
    ('esa_noise_dBc_Hz', 'esa_noise'), ('hf_noise_corrected_dBc_Hz', 'hf_noise'), ('esa_minus_hf_noise_dB', 'd_noise'),
    ('expected_tone_dBc', 'exp'), ('esa_minus_expected_dB', 'd_esa_exp'), ('hf_minus_expected_dB', 'd_hf_exp'),
    ('esa_modulation_depth_pct', 'm_esa')]


def summary_row(f0, e, h, exp_dbc):
    nan = np.nan
    row = {'f': f0, 'v_dc': e['v_dc'], 'esa_peak': e['tone_peak_dbc'], 'esa_int': e['tone_int_dbc'],
           'esa_snr': e['snr_db'], 'esa_noise': e['noise_dbc_hz'],
           'm_esa': 100 * np.sqrt(2 * 10 ** (e['tone_peak_dbc'] / 10.0)),
           'hf_tone': h['tone_dbc'] if h else nan, 'hf_snr': h['snr_db'] if h else nan,
           'hf_noise': h['noise_dbc_hz'] if h else nan, 'exp': exp_dbc if exp_dbc is not None else nan}
    row['d_tone'] = row['esa_peak'] - row['hf_tone']
    row['d_tone_int'] = row['esa_int'] - row['hf_tone']
    row['d_noise'] = row['esa_noise'] - row['hf_noise']
    row['d_esa_exp'] = row['esa_peak'] - row['exp']
    row['d_hf_exp'] = row['hf_tone'] - row['exp']
    return row


# =============================================================================
# Saving
# =============================================================================

def save_csv(path, rows):
    with open(path, 'w', newline='') as fh:
        fh.write(','.join(c for c, _ in SUMMARY_COLUMNS) + '\n')
        for r in rows:
            fh.write(','.join('%.6g' % r[k] for _, k in SUMMARY_COLUMNS) + '\n')
    print('  Saved: %s' % path)


def make_plot(cfg, label, stamp, rows_by_ch, hf_used, base_path, show):
    with plt.rc_context({'pdf.fonttype': 42, 'font.family': 'sans-serif', 'font.size': 9}):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 8.0), sharex=True, gridspec_kw={'height_ratios': [1.3, 1.7]})
        fig.patch.set_facecolor(bt.SURFACE)
        hf_col = bt.CATEGORICAL[min(len(rows_by_ch), len(bt.CATEGORICAL) - 1)]
        for i, (name, rows) in enumerate(rows_by_ch.items()):
            c = bt.CATEGORICAL[i]
            f = np.array([r['f'] for r in rows])
            get = lambda k: np.array([r[k] for r in rows])
            ax1.plot(f, get('esa_peak'), 'o-', color=c, ms=4, lw=1.2, label='%s ESA (peak)' % name)
            ax1.plot(f, get('esa_int'), 'x', color=c, ms=5, label='%s ESA (integrated, as the RIN)' % name)
            if hf_used:
                if i == 0:
                    ax1.plot(f, get('hf_tone'), 's-', color=hf_col, ms=4, lw=1.2, label='HighFinesse (as exported)')
                ax2.plot(f, get('d_tone'), 'o-', color=c, ms=5, lw=1.6, label='%s - HighFinesse, TONE' % name)
                ax2.plot(f, get('d_noise'), 'd--', color=c, ms=4, lw=1.0,
                         label='%s - HighFinesse, NOISE next to the tone (HF corrected)' % name)
            if np.isfinite(get('exp')).any():
                ax2.plot(f, get('d_esa_exp'), '^:', color=c, ms=4, lw=1.0, label='%s ESA - expected (V_PI)' % name)
        if rows_by_ch and np.isfinite([r['exp'] for r in next(iter(rows_by_ch.values()))]).any():
            rows = next(iter(rows_by_ch.values()))
            ax1.axhline(rows[0]['exp'], color=bt.MUTED, ls='--', lw=1.0,
                        label='expected from V_PI = %g V, %g Vpp' % (cfg.V_PI, cfg.DRIVE_VPP))
            if hf_used:
                ax2.plot([r['f'] for r in rows], [r['d_hf_exp'] for r in rows], 'v:', color=hf_col, ms=4, lw=1.0,
                         label='HighFinesse - expected (V_PI)')
        ax1.set_ylabel('Tone level m^2/2 (dBc)')
        ax1.set_title('AM response   %s   %s\nsame sine intensity modulation on both arms, %g Vpp drive'
                      % (label, stamp, cfg.DRIVE_VPP), loc='left', color=bt.INK, fontsize=10)
        ax2.axhline(0, color=bt.AXIS, lw=0.9)
        ax2.set_ylabel('Difference (dB)\n(tone: no dB-averaging correction;\nnoise: HighFinesse corrected)')
        ax2.set_xlabel('Frequency (Hz)')
        for ax in (ax1, ax2):
            ax.set_xscale('log')
            bt._style_axes(ax)
            ax.legend(fontsize=7.5, frameon=False, labelcolor=bt.INK2)
        fig.tight_layout()
        rin._finish(fig, base_path, show)


def write_h5(path, cfg, R, label, stamp, tones, rows_by_ch, mod, log_idx, prompt_idx):
    ckw = dict(compression='gzip', compression_opts=6, shuffle=True)
    with h5py.File(path, 'w') as h:
        h.attrs['label'], h.attrs['created'] = label, stamp
        h.attrs['script'] = 'am_response_test.py (+ rin_utils.py, rin_measurement.py)'
        h.attrs['doc'] = __doc__
        h.attrs['afg_readback'] = getattr(mod, 'readback', '')
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
            for col, key in SUMMARY_COLUMNS:
                g.create_dataset('summary/' + col, data=[r[key] for r in rows_by_ch[ch.name]])
        for i, t in enumerate(tones):
            tg = h.create_group('tones/%02d_%dHz' % (i, int(round(t['f']))))
            tg.attrs['frequency_Hz'] = t['f']
            for name, s in t['esa'].items():
                eg = tg.create_group('esa/' + name)
                eg.create_dataset('frequency_Hz', data=s['f'], **ckw)
                eg.create_dataset('trace_dBm', data=np.asarray(s['dbm'], np.float32), **ckw)
                for k, v in s.items():
                    if k not in ('f', 'dbm', 'settings', 'errors'):
                        eg.attrs[k] = bt._attr(v)
                sg = eg.create_group('esa_settings')
                for cmd, reply in s['settings'].items():
                    sg.attrs[cmd] = reply
                for k, v in t['esa_result'][name].items():
                    eg.attrs['result_' + k] = bt._attr(v)
            hf = t.get('hf')
            if hf:
                hg = tg.create_group('highfinesse')
                hg.create_dataset('frequency_Hz', data=hf['f'], **ckw)
                hg.create_dataset('rin_dB_Hz', data=hf['db'], **ckw)              # as exported
                hg.attrs['header_json'] = json.dumps(hf['header'])
                hg.attrs['file'] = hf['file']
                hg.attrs['correction_text'] = hf.get('correction_text', '')
                for k, v in t['hf_result'].items():
                    hg.attrs['result_' + k] = bt._attr(v)
                if os.path.isfile(hf['file']):
                    hg.create_dataset('file_bytes', data=np.frombuffer(open(hf['file'], 'rb').read(), np.uint8),
                                      compression='gzip')
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
    if exp_dbc is not None:
        print('Expected from the modulator: m = %.3f %% -> %.2f dBc (V_PI %g V, %g Vpp)' % (100 * exp_m, exp_dbc,
                                                                                         cfg.V_PI, cfg.DRIVE_VPP))
    R = rin.RinSetup(cfg)
    log_idx, prompt_idx = 0, len(bt.PROMPT_LOG)
    mod = None
    tones, rows_by_ch = [], {ch.name: [] for ch in R.channels}
    try:
        R.prepare_dc_monitors()
        R.confirm_dc_block()                       # ESA DC-coupled only after 'yes' (EF500 at the ESA input)
        mod = Modulator(cfg)
        mod.set_frequency(cfg.TONES_HZ[0])
        mod.on()
        print('SDG CH%d ON: %g Vpp sine, 0 V offset (read back: %s)' % (cfg.AFG_CH, cfg.DRIVE_VPP, mod.readback))
        for i, f0 in enumerate(cfg.TONES_HZ):
            print('\n----- tone %d of %d: %s -----' % (i + 1, len(cfg.TONES_HZ), rin._hz(f0)))
            mod.set_frequency(f0)
            t_start = time.time()
            esa = measure_tone_esa(R, cfg, f0)
            t = {'f': f0, 'esa': esa, 'esa_result': {}}
            for ch in R.channels:
                e = analyse_esa(cfg, ch, esa[ch.name], f0)
                t['esa_result'][ch.name] = e
                flag = ''
                if e['overload'] > 0:
                    flag += '  <-- ESA OVERLOAD: lower DRIVE_VPP or raise ESA_REF_LEVEL_DBM'
                if e['peak_dbm'] > cfg.ESA_REF_LEVEL_DBM - 6:
                    flag += '  <-- tone within 6 dB of the reference level'
                if abs(e['f_peak_hz'] - f0) > 2 * cfg.TONE_RBW_HZ:
                    flag += '  <-- peak not at the tone frequency'
                print('  [%s] ESA: tone %.2f dBm  ->  %.2f dBc (peak), %.2f dBc (integrated), m = %.3f %%, '
                      'SNR %.0f dB, noise %.1f dBc/Hz, Vdc %.4f V%s'
                      % (ch.name, e['peak_dbm'], e['tone_peak_dbc'], e['tone_int_dbc'],
                         100 * np.sqrt(2 * 10 ** (e['tone_peak_dbc'] / 10)), e['snr_db'], e['noise_dbc_hz'], e['v_dc'], flag))
                if cfg.SAVE_SCREENSHOTS and any(abs(f0 - s) < 1 for s in cfg.SCREENSHOT_TONES_HZ):
                    try:
                        bt.save_screenshot_png(ch.esa.drv, '%s_%dHz_%s_esa.png' % (base, int(f0), ch.name))
                    except Exception as ex:
                        print('  warning: screenshot failed (%s)' % ex)
            hf = h = None
            if cfg.COMPARE_HIGHFINESSE:
                print('  HIGHFINESSE: the tone is now at %s - RESTART its averaging, wait until the Av count is reached,\n'
                      '  then save "raw data" (screenshot optional: answer n).' % rin._hz(f0))
                hf = rin.collect_highfinesse(cfg, t_start, '%s_%dHz' % (base, int(f0)))
                if hf:
                    h = analyse_hf(cfg, hf, f0)
                    t['hf'], t['hf_result'] = hf, h
                    print('  HighFinesse: tone %.2f dBc (as exported, SNR %.0f dB), noise %.1f dBc/Hz (corrected %+.2f dB)'
                          % (h['tone_dbc'], h['snr_db'], h['noise_dbc_hz'], h['correction_db']))
                    if abs(h['f_peak_hz'] - f0) > 100:
                        print('  WARNING: the HighFinesse peak is at %s, not at the tone' % rin._hz(h['f_peak_hz']))
            for ch in R.channels:
                r = summary_row(f0, t['esa_result'][ch.name], h, exp_dbc)
                rows_by_ch[ch.name].append(r)
                print('  [%s] ESA - HighFinesse: tone %+.2f dB (integrated %+.2f), noise %+.2f dB%s'
                      % (ch.name, r['d_tone'], r['d_tone_int'], r['d_noise'],
                         ('   | ESA - expected %+.2f, HF - expected %+.2f' % (r['d_esa_exp'], r['d_hf_exp']))
                         if exp_dbc is not None else ''))
            tones.append(t)
    except rin.NotConfirmed as e:
        print('\n%s' % e)
    finally:
        if mod:
            mod.close()
        if tones:
            print('\nSaving ...')
            try:
                write_h5(base + '_data.h5', cfg, R, label, stamp, tones, rows_by_ch, mod, log_idx, prompt_idx)
                for name, rows in rows_by_ch.items():
                    save_csv('%s_summary_%s.csv' % (base, name) if len(rows_by_ch) > 1 else base + '_summary.csv', rows)
                make_plot(cfg, label, stamp, rows_by_ch, cfg.COMPARE_HIGHFINESSE, base + '_response', cfg.SHOW_PLOTS)
            except Exception as e:
                print('  warning: saving failed partly (%s)' % e)
            with open(base + '_log.txt', 'w', encoding='utf-8') as fh:
                fh.write('\n'.join(R.tee.lines[log_idx:]) + '\n')
        R.close()
        if cfg.SHOW_PLOTS and tones:
            plt.show()


if __name__ == '__main__':
    main()
