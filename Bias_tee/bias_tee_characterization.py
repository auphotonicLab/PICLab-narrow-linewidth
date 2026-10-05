#!/usr/bin/env python3
"""
Bias tee characterization (custom bias tee, 1 kHz - 10 MHz)
===========================================================

Mimics a Thorlabs amplified photodetector (PDA05CF2, PDA10A2, ...) with the
Siglent SDG6022X and measures the AC path of the bias tee on an ESA, while a
Keithley 2450 monitors the DC port as a HIGH-IMPEDANCE voltmeter.

Run one stage at a time (each stage tells you how to wire the next step):

    python bias_tee_characterization.py --stage 1 --meas scope --scope-ip 192.168.1.xx
    python bias_tee_characterization.py --stage 2 --meas scope --scope-ip 192.168.1.xx
    python bias_tee_characterization.py --stage 3 --meas scope --scope-ip 192.168.1.xx

    --meas scope   Siglent SDS2352X-E: raw time data -> flat-top FFT -> tone power in dBm (like the ESA)
    --meas fsw     R&S FSW50 ESA      (DC-coupled in stage 1: pure AC only!)
    --meas ssa     Siglent SSA3021X   (starts at 9 kHz)

Stage 1 - DC block only      (ESA DC-coupled => the signal MUST be pure AC)
    A  SDG CH1 -> receiver                         reference
    B  SDG CH1 -> Thorlabs EF500 -> receiver       DC block
    C  same as B, receiver AC-coupled (optional)   isolates the receiver's AC-coupling response
    receiver = ESA, or the scope (1 MOhm input) behind a 50 ohm feed-through terminator
    Result: DC block insertion loss = P(B) - P(A)

Stage 2 - bias tee, pure AC  (ESA AC-coupled, DC block in front of the ESA)
    R  SDG CH1 -> EF500 -> ESA                     reference
    T  SDG CH1 -> bias tee (AC+DC in) ; bias tee AC out -> EF500 -> ESA ;
       bias tee DC out -> Keithley 2450 (HIGH-Z voltmeter)
    Result: bias tee insertion loss = P(T) - P(R)

Stage 3 - bias tee, AC + DC  (same wiring as T)
    Sweep for each DC level in PD_DC_LEVELS_V (0 V = clean AC repeat).
    Result: change in AC response vs DC level, and Keithley DC reading.

DC convention (important)
-------------------------
A Thorlabs PD has a 50 ohm series resistor: 0-10 V into Hi-Z, 0-5 V into 50 ohm.
The SDG is kept in its "50 ohm load" mode, so everything you type is the value
a 50 ohm load would see.  In the bias tee the AC path is terminated by the ESA
(50 ohm) but the DC path is (almost) open, so the DC voltage at the bias tee /
Keithley is 2 x the SDG offset (= what the PD shows in Hi-Z).
PD_DC_LEVELS_V are therefore "PD output into 50 ohm" values and the Keithley
should read about 2 x that value.

Safety
------
* Keithley is ALWAYS a 0 A source / voltmeter (>10 GOhm).  Never use it as a
  voltage source on the DC port: the 100 mH inductor is only rated for 9 mA.
* R&S FSW: "you must protect the instrument from damaging DC input voltages manually" with DC coupling.
  The script therefore forces the SDG output OFF before configuring it,
  verifies by read-back that the offset is 0 V before the output is switched
  ON, and refuses DC offsets whenever the ESA is DC-coupled.
* Output of the SDG is switched OFF at every re-wiring prompt and at exit.

Notes
-----
* Oscilloscope: the SDS2000X-E has a 1 MOhm input.  Put a 50 ohm feed-through terminator on the
  scope input so the bias tee AC path sees 50 ohm like with the ESA.  The scope is only 8 bit:
  the vertical scale is auto-adjusted (signal ~6 div pk-pk) and several records are averaged.
  Raw 8-bit records + the tone spectrum of every point are saved in <run folder>/raw/*.npz.
* Siglent SSA3021X starts at 9 kHz: points below ESA_MIN_FREQ_HZ are skipped.
  The SSA has no input coupling command; check the DC rating of its input.
* EF500 is a BNC feed-through: use BNC-SMA adapters (their loss is part of
  the 'direct' reference only if you also use them there - use the same adapters).
* Optionally lock the SDG and ESA to a common 10 MHz reference.
"""

import sys
import os
import re
import csv
import json
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lab-control'))

import numpy as np
import matplotlib.pyplot as plt
import pyvisa
from Lab_control import AFG_Siglent, DC_KEITHLEY_2450, ESA_RS_FSW50, ESA_SIGLENT, SCOPE_SIGLENT_SDS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FREQUENCIES_HZ = sorted({m * 10 ** e for e in range(3, 7) for m in (1, 2, 3, 5, 7)} | {1e7})  # 1 kHz ... 10 MHz

VPP        = 0.5     # sine amplitude, Vpp into 50 ohm (-2 dBm).  Keep small, like a PD AC signal.
AFG_LOAD   = 50      # SDG load setting (see 'DC convention')
AFG_CH     = 1

PD_DC_LEVELS_V = [0, 0.5, 1, 2, 3, 4, 5]   # PD output into 50 ohm (PDA05CF2 / PDA10A2: 0-5 V). 0 = clean AC.
DC_AT_TEE_FACTOR = 2.0                      # DC at bias tee DC port = factor x SDG offset (SDG 50 ohm mode, DC path unterminated)
PD_MAX_HIZ_V = 10.0                         # PD saturation into Hi-Z

STAGE1_ALSO_AC_COUPLED = True   # extra sweep C in stage 1 (ESA AC-coupled, DC block, pure AC)

ESA_KIND   = 'fsw'              # measurement instrument: 'fsw' = R&S FSW50 (ESA_RS_FSW50 class), 'ssa' = Siglent SSA3021X, 'scope' = SDS2352X-E
AFG_IP     = '192.168.1.101'
ESA_IPS    = {'fsw': '192.168.1.7', 'ssa': '192.168.1.11', 'scope': None}   # scope IP: set here or use --scope-ip
KEITHLEY_IP = '192.168.1.151'
ESA_MIN_FREQ_HZ = {'fsw': 10.0, 'ssa': 9e3, 'scope': 0.0}
ESA_REF_LEVEL_DBM = 10          # ESA reference level
ESA_NREAD  = 2                  # sweeps per point (max of peaks is reported)
ESA_TIMEOUT_MS = 60000          # slow RBWs at 1 kHz

# Oscilloscope (SDS2352X-E) settings
SCOPE_CH         = 1
SCOPE_COUPLING   = {'DC': 'D1M', 'AC': 'A1M'}   # 1 MOhm; use an external 50 ohm feed-through terminator
SCOPE_MEMORY     = '140K'    # memory depth; the scope reports what it really used (SANU?)
SCOPE_NCYC       = 100       # record length >= this many signal periods
SCOPE_NACQ       = 3         # records averaged per point (power average)
SCOPE_PP_CODES   = (100, 190)  # wanted peak-peak range in ADC codes (25 codes/div, +-127 max)
SCOPE_BWL        = False     # 20 MHz bandwidth limit off

SETTLE_S   = 0.5                # after changing the SDG
PASS_TOL_DB = 1.0               # flat-response criterion relative to the reference
DC_TOL_FRAC, DC_TOL_ABS_V = 0.05, 0.02   # Keithley vs expected DC check

DATA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def expected_dbm(vpp, load=50.0):
    return 10 * np.log10((vpp / (2 * np.sqrt(2))) ** 2 / load * 1e3)


def esa_settings(freq):
    """Span / RBW (in MHz, as the Lab_control ESA classes want them) for a tone at freq."""
    span = max(0.2 * freq, 200.0)          # Hz
    rbw = max(0.01 * freq, 10.0)           # Hz (SSA min RBW = 10 Hz)
    return span / 1e6, rbw / 1e6


def flattop(n):
    """Flat-top window (a0..a4 of the standard 5-term flat-top), amplitude-accurate to <0.01 dB."""
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
    return {'f': f, 'dbm': to_dbm(amp), 'f_peak': f[k], 'vpk': vpk, 'p_dbm': float(to_dbm(vpk)),
            'snr_db': float(to_dbm(vpk) - to_dbm(noise)) if np.isfinite(noise) else np.nan, 'df': df}


def ask(msg):
    print('\n' + '=' * 78)
    print(msg)
    input('Press ENTER when done (Ctrl+C aborts)... ')


class Setup:
    """Holds the instruments and the safe-operation logic."""

    def __init__(self, esa_kind, need_keithley):
        self.esa_kind = esa_kind
        self.is_scope = (esa_kind == 'scope')
        self.esa_dc_coupled = None   # DC-coupled ESA => no DC allowed (not applied to the scope)
        self.esa_ip = ESA_IPS[esa_kind]
        self.rx = ('scope CH%d (1 MOhm input, with a 50 ohm feed-through terminator)' % SCOPE_CH
                   if self.is_scope else 'ESA')
        self.raw_dir = None
        self.last_vdiv = None

        print('Connecting to instruments...')
        # 1) make sure the SDG output is OFF before anything else touches it
        rm = pyvisa.ResourceManager()
        r = rm.open_resource('TCPIP0::' + AFG_IP + '::inst0::INSTR')
        r.write('C%d:OUTP OFF' % AFG_CH)
        r.close()
        self.afg = AFG_Siglent(IP_address=AFG_IP, channel=AFG_CH, frequency=FREQUENCIES_HZ[0],
                               waveform='SINE', vpp=VPP, offset=0, load=AFG_LOAD)
        self.afg.output_status(channel=AFG_CH, status='OFF')

        # 2) receiver: scope or ESA
        if self.is_scope:
            if not self.esa_ip:
                raise SystemExit('Scope IP not set: use --scope-ip or edit ESA_IPS["scope"]')
            self.esa = SCOPE_SIGLENT_SDS(IP_address=self.esa_ip)
            self.esa.instr.timeout = ESA_TIMEOUT_MS
        else:
            if esa_kind == 'fsw':
                self.esa = ESA_RS_FSW50(IP_address=self.esa_ip)      
            else:
                self.esa = ESA_SIGLENT(IP_address=self.esa_ip, USB_interface=-1)
            self.esa.instr.timeout = ESA_TIMEOUT_MS
            print('ESA:', self.esa.instr.query('*IDN?').strip())
            rl_cmd = ('DISP:TRAC:Y:RLEV ' if esa_kind == 'fsw' else ':DISP:WIND:TRAC:Y:SCAL:RLEV ') + str(ESA_REF_LEVEL_DBM)
            self.esa.instr.write(rl_cmd)

        # 3) Keithley as high-Z DC monitor
        self.keithley = None
        if need_keithley:
            self.keithley = DC_KEITHLEY_2450(channel=21, GPIB_interface=-1, IP_address=KEITHLEY_IP)
            self.keithley.SetHighZVoltmeter(vlim=20, nplc=1)
            self.keithley.SwitchOn()

    # ---- ESA coupling --------------------------------------------------
    def set_esa_coupling(self, coupling):
        assert coupling in ('AC', 'DC')
        if self.is_scope:
            self.afg_output_off()
            self.esa.SetChannel(SCOPE_CH, coupling=SCOPE_COUPLING[coupling], vdiv=self.last_vdiv or 0.1,
                                offset=0.0, bandwidth_limit=SCOPE_BWL)
            print('Scope coupling:', SCOPE_COUPLING[coupling])
            self.esa_dc_coupled = False     # 1 MOhm scope input tolerates DC (and the tee/DC block sit in front)
            return
        if self.esa_kind == 'fsw':
            self.afg_output_off()                       # never change coupling with signal/DC present
            self.esa.SetCoupling(coupling)
            got = self.esa.GetCoupling()
            if got != coupling:
                raise RuntimeError('ESA coupling is %s, wanted %s' % (got, coupling))
            print('ESA input coupling:', got)
        else:
            print('SSA3021X: no coupling command used - check the instrument input.')
        self.esa_dc_coupled = (coupling == 'DC')

    # ---- SDG -------------------------------------------------------------
    def afg_output_off(self):
        self.afg.output_status(channel=AFG_CH, status='OFF')

    def set_tone(self, freq, vpp, offset):
        """Configure the SDG (output must already be ON or OFF - offset is verified by read-back)."""
        if self.esa_dc_coupled and abs(offset) > 0:
            raise RuntimeError('Refusing DC offset %g V while the ESA is DC-coupled' % offset)
        self.afg.instr.write('C%d:OUTP LOAD,%s' % (AFG_CH, AFG_LOAD))      # load first, then amplitude/offset
        self.afg.setParameters(channel=AFG_CH, waveform='SINE', frequency=freq, vpp=vpp,
                               offset=offset, load=AFG_LOAD)
        self.verify_tone(freq, vpp, offset)

    def verify_tone(self, freq, vpp, offset):
        resp = self.afg.instr.query('C%d:BSWV?' % AFG_CH)
        outp = self.afg.instr.query('C%d:OUTP?' % AFG_CH)
        def grab(key):
            m = re.search(key + r',([-+0-9.eE]+)', resp)
            return float(m.group(1)) if m else float('nan')
        amp, ofst, frq = grab('AMP'), grab('OFST'), grab('FRQ')
        if not (abs(ofst - offset) < 1e-3 and abs(amp - vpp) < 1e-3 * max(1, vpp) + 1e-3
                and abs(frq - freq) < 1e-6 * freq + 1e-3):
            raise RuntimeError('SDG read-back mismatch: asked f=%g amp=%g ofst=%g, got "%s"' % (freq, vpp, offset, resp.strip()))
        if not re.search(r'LOAD,\s*%s\b' % AFG_LOAD, outp):
            raise RuntimeError('SDG load is not %s ohm: "%s"' % (AFG_LOAD, outp.strip()))
        if self.esa_dc_coupled and abs(ofst) > 1e-3:
            raise RuntimeError('DC offset present with DC-coupled ESA!')

    # ---- DC monitor ------------------------------------------------------
    def read_dc(self, expected=None):
        """Settled Keithley voltage (V)."""
        self.keithley.AssertHighZ()
        prev, v = None, None
        for _ in range(20):
            v = self.keithley.GetMeas()
            if prev is not None and abs(v - prev) < max(2e-3, 5e-3 * abs(v)):
                break
            prev = v
            time.sleep(0.3)
        if abs(v) > PD_MAX_HIZ_V + 1:
            raise RuntimeError('DC monitor reads %.2f V - above any PD level, aborting' % v)
        return v

    # ---- ESA -------------------------------------------------------------
    def read_power_scope(self, freq, vpp, label):
        """Acquire time records, FFT with a flat-top window, return tone power (dBm into 50 ohm)."""
        sc = self.esa
        tdiv = sc.nearest_tdiv(SCOPE_NCYC / freq / 14.0)
        sc.SetTimebase(tdiv, SCOPE_MEMORY)
        vdiv = self.last_vdiv or sc.nearest_vdiv(vpp / 6.0)
        lo, hi = SCOPE_PP_CODES
        for _ in range(8):                                   # vertical auto-scale (8 bit => keep signal large)
            sc.SetVertical(SCOPE_CH, vdiv, 0.0)
            codes, vdiv_rb, _o, dt = sc.Acquire(SCOPE_CH)
            pp = int(codes.max()) - int(codes.min())
            clipped = codes.max() >= 126 or codes.min() <= -127
            if clipped:
                new = sc.nearest_vdiv(vdiv_rb * 2.0)
            elif pp > hi or pp < lo:
                new = sc.nearest_vdiv(vdiv_rb * max(pp, 1) / 150.0)      # aim at ~6 div pk-pk
            else:
                break
            if new == vdiv_rb:
                break
            vdiv = new
        self.last_vdiv = vdiv_rb
        info = sc.GetAcquisitionInfo(SCOPE_CH)
        if abs(len(codes) * dt - 14 * info['tdiv']) > 0.2 * 14 * info['tdiv']:
            print('  warning: record length %.3g s differs from 14 x tdiv (%.3g s)' % (len(codes) * dt, 14 * info['tdiv']))
        if pp < 40:
            print('  warning: only %d ADC codes peak-peak - amplitude accuracy is poor (signal very small?)' % pp)
        if clipped:
            print('  warning: scope input clipped - result invalid')
        v2 = []
        for i in range(SCOPE_NACQ):
            if i:
                codes, vdiv_rb, _o, dt = sc.Acquire(SCOPE_CH)
            volt = codes.astype(float) * vdiv_rb / 25.0
            sp = tone_spectrum(volt, dt, freq)
            v2.append(sp['vpk'] ** 2)
        p_dbm = float(10 * np.log10(np.mean(v2) / (2 * 50.0) * 1e3))
        if abs(sp['f_peak'] - freq) > max(3 * sp['df'], 0.02 * freq):
            print('  warning: spectral peak at %.1f Hz, expected %.1f Hz' % (sp['f_peak'], freq))
        if self.raw_dir:                                     # keep time data + spectrum around the tone (<= 20 x f0)
            band = sp['f'] <= 20 * freq
            name = re.sub(r'[^A-Za-z0-9_.-]+', '_', label) + '_f%.0fHz.npz' % freq
            np.savez_compressed(os.path.join(self.raw_dir, name), codes=codes, vdiv=vdiv_rb, dt=dt,
                                f0=freq, vpp_set=vpp, spec_f=sp['f'][band].astype(np.float32),
                                spec_dbm=sp['dbm'][band].astype(np.float32), p_dbm=p_dbm,
                                snr_db=sp['snr_db'], tdiv=info['tdiv'], sample_rate=info['sample_rate_Sa_s'])
        self.last_snr = sp['snr_db']
        return p_dbm

    def read_power(self, freq, vpp=VPP, label='sweep'):
        if self.is_scope:
            return self.read_power_scope(freq, vpp, label)
        span, rbw = esa_settings(freq)
        self.esa.SetSpectrumParameters(spanFreq=span, centerFreq=freq / 1e6, videoBW=rbw,
                                       resolutionBW=rbw, dataPointsInSweep=1001)
        return self.esa.ReadPeakPower(Nread=ESA_NREAD)

    # ---- one sweep -------------------------------------------------------
    def sweep(self, label, offset=0.0, vpp=VPP, monitor_dc=False):
        fmin = ESA_MIN_FREQ_HZ[self.esa_kind]
        res = {'label': label, 'offset': offset, 'vpp': vpp,
               'freq': np.array(FREQUENCIES_HZ, float),
               'p_dbm': np.full(len(FREQUENCIES_HZ), np.nan),
               'v_dc': np.full(len(FREQUENCIES_HZ), np.nan)}
        self.afg_output_off()
        try:
            first = True
            for i, f in enumerate(FREQUENCIES_HZ):
                if f < fmin:
                    print('  [%s] %10.0f Hz  skipped (minimum %g Hz)' % (label, f, fmin))
                    continue
                self.set_tone(f, vpp, offset)
                if first:
                    self.afg.output_status(channel=AFG_CH, status='ON')
                    first = False
                time.sleep(SETTLE_S)
                msg = ''
                if monitor_dc:
                    v = self.read_dc()
                    res['v_dc'][i] = v
                    exp = DC_AT_TEE_FACTOR * offset
                    flag = ''
                    if abs(v - exp) > max(DC_TOL_ABS_V, DC_TOL_FRAC * abs(exp)):
                        flag = '  <-- differs from expected %.3f V' % exp
                    msg = '  Vdc = %8.4f V%s' % (v, flag)
                p = self.read_power(f, vpp, label)
                res['p_dbm'][i] = p
                snr = ('  SNR %.0f dB' % self.last_snr) if self.is_scope else ''
                print('  [%s] %10.0f Hz  P = %8.2f dBm (exp. %.2f)%s%s' % (label, f, p, expected_dbm(vpp), snr, msg))
        finally:
            self.afg_output_off()
        return res

    def close(self):
        for fn in (lambda: self.afg_output_off(),
                   lambda: self.afg.instr.write('C%d:BSWV OFST,+0' % AFG_CH),
                   lambda: self.keithley and self.keithley.SwitchOff(),
                   lambda: self.keithley and self.keithley.CloseConnection(),
                   lambda: self.afg.CloseConnection(),
                   lambda: (self.esa.closeConnection() if self.is_scope else self.esa.CloseConnection())):
            try:
                fn()
            except Exception as e:      # keep cleaning up
                print('cleanup warning:', e)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def make_outdir(stage):
    d = os.path.join(DATA_ROOT, datetime.now().strftime('%Y%m%d_%H%M%S') + '_stage%d_%s' % (stage, ESA_KIND))
    os.makedirs(d, exist_ok=True)
    return d


def save_csv(path, results):
    cols = ['freq_Hz']
    for r in results:
        cols += [r['label'] + '_dBm', r['label'] + '_Vdc']
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for i, f in enumerate(FREQUENCIES_HZ):
            row = [f]
            for r in results:
                row += [r['p_dbm'][i], r['v_dc'][i]]
            w.writerow(row)


def rel_db(res, ref):
    return res['p_dbm'] - ref['p_dbm']


def report(res_list, ref, title, outdir, fname):
    """Plot absolute power and change relative to ref; print pass/fail."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 8), sharex=True)
    for r in res_list + [ref]:
        ax1.semilogx(r['freq'], r['p_dbm'], 'o-', ms=4, label=r['label'])
    ax1.axhline(expected_dbm(VPP), color='gray', ls=':', label='ideal (%.2f dBm)' % expected_dbm(VPP))
    ax1.set_ylabel('Tone power at receiver (dBm)')
    ax1.set_title(title)
    ax1.grid(True, which='both')
    ax1.legend(fontsize=8)
    for r in res_list:
        d = rel_db(r, ref)
        ax2.semilogx(r['freq'], d, 's-', ms=4, label='%s - %s' % (r['label'], ref['label']))
        ok = np.nanmax(np.abs(d)) <= PASS_TOL_DB if np.any(np.isfinite(d)) else False
        worst = np.nanmax(np.abs(d)) if np.any(np.isfinite(d)) else float('nan')
        below3 = r['freq'][np.where(np.isfinite(d) & (d < -3))[0]]
        print('  %-28s worst |dev| = %.2f dB -> %s%s' % (
            r['label'], worst, 'PASS' if ok else 'CHECK',
            ('   (< -3 dB at %s Hz)' % ', '.join('%g' % f for f in below3)) if len(below3) else ''))
    ax2.axhspan(-PASS_TOL_DB, PASS_TOL_DB, color='g', alpha=0.1)
    ax2.set_xlabel('Frequency (Hz)')
    ax2.set_ylabel('Change relative to %s (dB)' % ref['label'])
    ax2.grid(True, which='both')
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, fname), dpi=150)
    return fig


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def stage1(S, outdir):
    S.set_esa_coupling('DC')
    ask('STAGE 1-A (reference)\n  SDG CH%d  ->  %s  (direct, SMA/adapters only, NO DC block)\n'
        '  Receiver is DC-coupled: signal is pure AC (offset 0 V, verified by read-back).' % (AFG_CH, S.rx))
    A = S.sweep('direct')
    ask('STAGE 1-B\n  SDG CH%d  ->  Thorlabs EF500 DC block  ->  %s' % (AFG_CH, S.rx))
    B = S.sweep('with DC block')
    results = [A, B]
    if STAGE1_ALSO_AC_COUPLED:
        S.set_esa_coupling('AC')
        ask('STAGE 1-C (optional)\n  Keep SDG -> EF500 -> receiver.  Receiver is now AC-coupled (pure AC, still safe).')
        C = S.sweep('block, AC-coupled')
        results.append(C)
    save_csv(os.path.join(outdir, 'stage1.csv'), results)
    print('\nDC block insertion loss (relative to direct):')
    fig = report(results[1:], A, 'Stage 1: DC block (EF500)', outdir, 'stage1.png')
    return fig


def tee_wiring_text(rx):
    return ('  SDG CH%d (50 ohm mode)  ->  bias tee  AC+DC input\n' % AFG_CH +
            '  bias tee  AC output  ->  EF500 DC block  ->  ' + rx + ' (AC-coupled)\n'
            '  bias tee  DC output  ->  Keithley 2450 INPUT HI/LO  (HIGH-Z voltmeter, 0 A source, 2-wire)\n'
            '  Do NOT connect anything else to the DC port.')


def stage2(S, outdir):
    S.set_esa_coupling('AC')
    ask('STAGE 2-R (reference, no bias tee)\n  SDG CH%d  ->  EF500  ->  %s (AC-coupled)' % (AFG_CH, S.rx))
    R = S.sweep('ref: block only')
    S.keithley.AssertHighZ()
    ask('STAGE 2-T (bias tee, pure AC)\n' + tee_wiring_text(S.rx))
    T = S.sweep('bias tee, AC only', monitor_dc=True)
    results = [R, T]
    save_csv(os.path.join(outdir, 'stage2.csv'), results)
    print('\nBias tee insertion loss (relative to block-only reference):')
    return report([T], R, 'Stage 2: bias tee, pure AC', outdir, 'stage2.png')


def stage3(S, outdir):
    S.set_esa_coupling('AC')
    if S.esa_kind == 'ssa':
        print('NOTE: SSA3021X - make sure its input is AC coupled / rated for the DC block output.')
    ask('STAGE 3 (bias tee, AC + PD-like DC)\n' + tee_wiring_text(S.rx) +
        '\n  Levels (PD output into 50 ohm): %s V -> Keithley should read ~%g x these.'
        % (PD_DC_LEVELS_V, DC_AT_TEE_FACTOR))
    results = []
    for lvl in PD_DC_LEVELS_V:
        if lvl + VPP / 2 > 5.0:
            print('  note: %.2f V + %.2f V peak exceeds 5 V - the real PD would saturate.' % (lvl, VPP / 2))
        results.append(S.sweep('DC %.2f V (tee %.2f V)' % (lvl, DC_AT_TEE_FACTOR * lvl),
                               offset=lvl, monitor_dc=True))
        S.afg_output_off()
    save_csv(os.path.join(outdir, 'stage3.csv'), results)
    print('\nChange of AC response vs the 0 V sweep:')
    base = results[0]
    fig = report(results[1:], base, 'Stage 3: bias tee, AC + DC', outdir, 'stage3.png')
    # Keithley vs DC level summary
    print('\nDC level  expected   Keithley (mean over sweep)')
    for r, lvl in zip(results, PD_DC_LEVELS_V):
        print('  %5.2f V   %6.2f V   %8.4f V' % (lvl, DC_AT_TEE_FACTOR * lvl, np.nanmean(r['v_dc'])))
    return fig


def main():
    global ESA_KIND
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stage', type=int, choices=(1, 2, 3), required=True)
    ap.add_argument('--meas', choices=('fsw', 'ssa', 'scope'), default=ESA_KIND,
                    help='measurement instrument (default %s)' % ESA_KIND)
    ap.add_argument('--scope-ip', default=None, help='IP address of the SDS2352X-E')
    ap.add_argument('--no-show', action='store_true', help='do not open the plot window')
    args = ap.parse_args()

    ESA_KIND = args.meas
    if args.scope_ip:
        ESA_IPS['scope'] = args.scope_ip
    outdir = make_outdir(args.stage)
    S = Setup(ESA_KIND, need_keithley=(args.stage >= 2))
    S.raw_dir = os.path.join(outdir, 'raw')
    os.makedirs(S.raw_dir, exist_ok=True)
    try:
        with open(os.path.join(outdir, 'config.json'), 'w') as fh:
            json.dump({'stage': args.stage, 'meas': ESA_KIND, 'scope_memory': SCOPE_MEMORY, 'scope_ncyc': SCOPE_NCYC, 'scope_nacq': SCOPE_NACQ, 'vpp': VPP, 'load': AFG_LOAD,
                       'pd_dc_levels_v': PD_DC_LEVELS_V, 'dc_at_tee_factor': DC_AT_TEE_FACTOR,
                       'freqs_hz': FREQUENCIES_HZ}, fh, indent=1)
        fig = {1: stage1, 2: stage2, 3: stage3}[args.stage](S, outdir)
        print('\nSaved to', outdir)
        if not args.no_show:
            plt.show()
    except KeyboardInterrupt:
        print('\nAborted by user.')
    finally:
        S.close()


if __name__ == '__main__':
    main()
