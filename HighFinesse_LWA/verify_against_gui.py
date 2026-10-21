#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Verification figures: HighFinesse GUI vs Python (lwa_utils), and power- vs dB-averaging
=======================================================================================

    python verify_against_gui.py            (edit the paths below; defaults = the diag_out files of 2026-10-21)

Figure 1  same capture, two routes: GUI 'File > Save > Rawdata' vs the spectrum Python received
          (point-by-point difference, and the GUI's Effective (beta) recomputed in Python)
Figure 2  n = 10 captures averaged in linear power vs in dB (FN and RIN), with the GUI's own n = 1 / n = 10 exports
Figure 3  linewidths from FN spectra: Effective (beta) and Intrinsic, GUI header vs Python estimators

Findings this script reproduces (instrument SN 1006, 2026-10-21):
  * In FN mode the GUI publishes the AMPLITUDE spectrum (Hz/rtHz); its export is the same capture squared
    (Hz^2/Hz) - identical to ~1e-11 (the CSV's printed digits).
  * GUI Effective (beta) = sqrt(8 ln2 * sum(S * df) over bins above the beta line)  - reproduced to 1e-9.
  * Averaging n = 10 in dB reads 2.17 dB below the linear-power average (level of the bin means), in every band and
    in FN and RIN alike; theory Gamma(1+1/n)^n = 0.607 -> 2.17 dB (n = 20: 2.33 dB). All averaging and binning
    in lwa_utils (and in Bias_tee/rin_utils) is linear; dB only ever appears when a final value is displayed.
  * The GUI's own Averaging: RIN (dB/Hz) in dB (its n = 10 export sits on the dB average); FN as AMPLITUDE
    (Hz/rtHz): its n = 10 export = 0.808 x the power average in every band, theory pi/4 + (1-pi/4)/10 = 0.807.
  * GUI Intrinsic 'Mode(stat)' ~ pi * (mode of the amplitude histogram)^2 ~ pi * S0 / 2 for a single capture,
    i.e. about half of the white-noise estimate pi * mean(S) (Rayleigh mode of a single periodogram).
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from scipy.special import gamma as gamma_fn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lwa_utils as lwa  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DIAG = os.path.join(HERE, 'diag_out')
GUI_EXPORT_SAME_CAPTURE = os.path.join(DIAG, 'GUI_FN_last_capture_raw.txt')   # saved right after the probe
# Python data: probe.h5 (run_probe.bat) and a measurement <stem>.h5 (lwa_measurement.py). The .npz/.csv files of
# 2026-10-21 (written before the switch to .h5) are still read.
PY_LAST_CAPTURE = os.path.join(DIAG, 'probe.h5') + '::noise/last'            # FN capture saved by the GUI too
FN_CAPTURES = os.path.join(DIAG, 'probe.h5')                                  # 10 FN captures
RIN_CAPTURES = os.path.join(DIAG, 'test_run', '<stem>.h5')                     # 10 RIN captures (measurement file)
GUI_RIN_N1 = r'C:\Users\Group Login\Downloads\PSD_1.5MHz_n1.txt'               # optional GUI exports
GUI_RIN_N10 = r'C:\Users\Group Login\Downloads\PSD_1.5MHz_n10.txt'
EXTRA_FN_EXPORTS = [r'C:\Users\Group Login\Downloads\PSD_FN_Claude.txt']
GUI_FN_N10 = r'C:\Users\Group Login\Downloads\PSD_FN_Claude_n10.txt'      # GUI Averaging = 10, FN
OUT = os.path.join(DIAG, 'figures')
FLOOR = (1e6, 1e7)

# palette (dataviz reference categorical order) and inks
C_GUI, C_PY, C_3, C_4 = '#2a78d6', '#eb6834', '#1baf7a', '#6250d6'
INK, INK2, GRID = '#0b0b0b', '#52514e', '#e4e3df'
plt.rcParams.update({'font.size': 10, 'axes.edgecolor': INK2, 'axes.labelcolor': INK, 'xtick.color': INK2,
                     'ytick.color': INK2, 'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6,
                     'axes.spines.top': False, 'axes.spines.right': False, 'legend.frameon': False,
                     'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb', 'savefig.facecolor': '#fcfcfb'})


def read_export(path):
    """GUI 'Save' file -> (header dict, x, y)."""
    hdr = {}
    with open(path, encoding='latin-1') as f:
        lines = f.read().splitlines()
    k = 0
    while lines[k].startswith('#'):
        key, _, val = lines[k][1:].partition('=') if '=' in lines[k] else lines[k][1:].partition(':')
        hdr[key.strip()] = val.strip()
        k += 1
    data = np.loadtxt(lines[k + 1:], delimiter=',')
    return hdr, data[:, 0], data[:, 1]


def load_captures(path):
    """(x, captures[n, N]) of the noise spectrum: FN in Hz^2/Hz, RIN in dB/Hz.
    .h5 (probe.h5 or a measurement <stem>.h5): /noise/x and /noise/captures.
    Old .npz of 2026-10-21: probe_captures.npz (x, all, unit) or <stem>_captures.npz (noise_x, noise_all)."""
    if path.lower().endswith(('.h5', '.hdf5')):
        d = lwa.read_h5(path)['noise']
        return d['x'], d['captures']
    z = np.load(path)
    if 'noise_all' in z:
        x, a = z['noise_x'], z['noise_all']
    else:
        x, a = z['x'], z['all']
    if np.nanmax(a) >= 0 and str(z.get('unit', '')) != 'Hz2/Hz':
        a = a ** 2                                            # old FN files: published Hz/rtHz
    return x, a


def hz(s):
    return float(s.replace('Hz', '').replace(',', '.'))


def binned(x, y_lin, bpd=40):
    return lwa.log_bin(x, y_lin, bpd)


def gui_effective(x, S):
    return lwa.beta_separation_linewidth(x, S)


def amp_mode_intrinsic(x, S, rng=FLOOR, bins=500):
    m = (x > rng[0]) & (x < rng[1])
    h, e = np.histogram(np.sqrt(S[m]), bins=bins)
    k = np.argmax(h)
    return float(np.pi * ((e[k] + e[k + 1]) / 2) ** 2), np.sqrt(S[m]), e


def fig_same_capture():
    hdr, xg, Sg = read_export(GUI_EXPORT_SAME_CAPTURE)
    py = lwa.load_xy(PY_LAST_CAPTURE)
    squared = True                                          # .h5 and new .csv files are in Hz^2/Hz
    if PY_LAST_CAPTURE.endswith('.csv'):
        with open(PY_LAST_CAPTURE) as f:
            squared = 'Hz2' in f.readline()                 # old csv of 2026-10-21: published Hz/rtHz
    xp, Sp = py[:, 0], (py[:, 1] if squared else py[:, 1] ** 2)
    rel = (Sp - Sg) / Sg
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6), gridspec_kw=dict(width_ratios=[1.35, 1, 1]))
    a = ax[0]
    a.loglog(xg, Sg, color=C_GUI, lw=2.4, alpha=0.55, label='GUI export (Hz²/Hz)')
    a.loglog(xp, Sp, color=C_PY, lw=0.5, label='Python, published Hz/√Hz squared')
    a.loglog(xg, 8 * np.log(2) * xg / np.pi ** 2, color=INK2, lw=1, ls='--', label='β-separation line')
    a.set_xlabel('Fourier frequency [Hz]'); a.set_ylabel('FN PSD [Hz²/Hz]')
    a.set_title('Same capture: GUI export and Python overlay', loc='left', color=INK)
    a.legend(loc='lower left')
    b = ax[1]
    b.semilogx(xg, rel, '.', ms=1, color=C_PY)
    b.set_ylim(-3e-10, 3e-10)
    b.set_xlabel('Fourier frequency [Hz]'); b.set_ylabel('(Python² − GUI) / GUI')
    b.set_title(f'Point-by-point: max |Δ| = {np.max(np.abs(rel)):.1e}\n(= printed digits of the CSV)', loc='left',
                color=INK)
    c = ax[2]
    c.loglog(Sg, Sp, '.', ms=1, color=C_GUI)
    lim = [Sg.min(), Sg.max()]
    c.loglog(lim, lim, color=INK2, lw=0.8)
    c.set_xlabel('GUI export [Hz²/Hz]'); c.set_ylabel('Python [Hz²/Hz]')
    eff_g, eff_p = hz(hdr['Effective']), gui_effective(xp, Sp)
    c.set_title(f'All {len(Sg):,} points on y = x\nEffective (β) GUI   {eff_g:.6f} Hz\nEffective (β) Python {eff_p:.6f} Hz',
                loc='left', color=INK, fontsize=9.5)
    fig.suptitle(f'GUI vs Python, one FN capture (GUI timestamp {hdr.get("Timestamp")})', x=0.01, ha='left',
                 color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '1_same_capture_gui_vs_python.png'), dpi=150)
    return dict(max_rel=float(np.max(np.abs(rel))), eff_gui=eff_g, eff_py=eff_p)


def averaging_panels(ax_spec, ax_off, x, P, unit_label, to_plot, title, extra=None):
    n = len(P)
    pm = P.mean(0)
    dm = 10 ** (np.mean(10 * np.log10(P), 0) / 10)
    xb, s1 = binned(x, P[0]); _, pmb = binned(x, pm); _, dmb = binned(x, dm)
    ax_spec.plot(xb, to_plot(s1), color=INK2, lw=0.8, alpha=0.6, label='single capture')
    ax_spec.plot(xb, to_plot(pmb), color=C_PY, lw=1.6, label=f'n = {n}, linear-power average (Python)')
    ax_spec.plot(xb, to_plot(dmb), color=C_GUI, lw=1.6, label=f'n = {n}, dB average')
    for lab, (xx, yy, col) in (extra or {}).items():
        xe, ye = binned(xx, yy)
        ax_spec.plot(xe, to_plot(ye), color=col, lw=1.2, ls='--', label=lab)
    ax_spec.set_xscale('log')
    ax_spec.set_xlabel('Fourier frequency [Hz]'); ax_spec.set_ylabel(unit_label)
    ax_spec.set_title(title, loc='left', color=INK)
    ax_spec.legend(fontsize=8.5)
    # LEVEL difference: both averages are first averaged linearly inside each log bin, then compared in dB once.
    # (Averaging per-bin dB differences instead would add the log bias of the scattered power average and give
    # 2.29 dB at n = 10 - a statistic, not a level.)
    xo, pmo = lwa.log_bin(x, pm, 20)
    _, dmo = lwa.log_bin(x, dm, 20)
    off = 10 * np.log10(pmo / dmo)
    ax_off.semilogx(xo, off, color=C_PY, lw=1.6, zorder=3, label='level difference per log bin (linear bin means)')
    # headline: median over the log bins from 10 kHz (each bin compared linearly) - a single wide-band mean would be
    # dominated by the strongest spurs, which barely change with averaging
    level = float(np.median(off[xo > 1e4]))
    return off, level


def fig_averaging():
    n = 10
    theory = -10 * n * np.log10(gamma_fn(1 + 1 / n))          # level of a dB average: Gamma(1+1/n)^n -> 2.17 dB
    xf, Pf = load_captures(FN_CAPTURES)
    xr, Rdb = load_captures(RIN_CAPTURES)
    Pr = 10 ** (Rdb / 10)
    extra = {}
    if os.path.isfile(GUI_RIN_N10):
        h10, x10, y10 = read_export(GUI_RIN_N10)
        extra['GUI export n = 10 (other day)'] = (x10, 10 ** (y10 / 10), C_3)
    if os.path.isfile(GUI_RIN_N1):
        h1, x1, y1 = read_export(GUI_RIN_N1)
        extra['GUI export n = 1 (other day)'] = (x1, 10 ** (y1 / 10), C_4)
    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    (off_f, lev_f) = averaging_panels(ax[0, 0], ax[1, 0], xf, Pf, 'FN PSD [Hz²/Hz]', lambda v: v,
                             'FN, 10 captures of 2026-10-21 11:46')
    ax[0, 0].set_yscale('log')
    (off_r, lev_r) = averaging_panels(ax[0, 1], ax[1, 1], xr, Pr, 'RIN [dB/Hz]', lambda v: 10 * np.log10(v),
                             'RIN, 10 captures of 2026-10-21 11:29', extra)
    for a, off, lev, name in ((ax[1, 0], off_f, lev_f, 'FN'), (ax[1, 1], off_r, lev_r, 'RIN')):
        a.axhline(theory, color=INK, lw=1, ls='--', label=f'theory Γ(1+1/n)^n, n = 10: {theory:.2f} dB')
        a.set_ylim(-1, 7)
        a.set_xlabel('Fourier frequency [Hz]'); a.set_ylabel('level: power average / dB average [dB]')
        a.set_title(f'{name}: level difference, median of log bins > 10 kHz = {lev:.2f} dB (theory {theory:.2f} dB)', loc='left',
                    color=INK)
        a.legend(fontsize=8.5, loc='upper left')
    fig.suptitle('Averaging n = 10: linear power vs dB (the same 10 captures)', x=0.01, ha='left', color=INK,
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '2_averaging_power_vs_dB.png'), dpi=150)
    return dict(theory_dB=float(theory), fn_level_dB=float(lev_f), rin_level_dB=float(lev_r))


def fig_linewidths():
    files = [GUI_EXPORT_SAME_CAPTURE] + [f for f in EXTRA_FN_EXPORTS if os.path.isfile(f)]
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.8), gridspec_kw=dict(width_ratios=[1.4, 1]))
    rows = []
    cols = [C_GUI, C_3, C_4]
    for k, f in enumerate(files):
        hdr, x, S = read_export(f)
        if 'FN' not in hdr.get('Outputmode', 'FN'):
            continue
        eff_g, int_g = hz(hdr['Effective']), hz(hdr['Intrinsic'])
        m = (x > FLOOR[0]) & (x < FLOOR[1])
        int_mean = float(np.pi * S[m].mean())
        int_mode, amp, edges = amp_mode_intrinsic(x, S)
        rows.append((hdr.get('Timestamp'), eff_g, gui_effective(x, S), int_g, int_mode, int_mean))
        xb, sb = binned(x, S)
        ax[0].loglog(xb, sb, color=cols[k % 3], lw=1.3, label=f'GUI export {hdr.get("Timestamp")} (40 bins/decade)')
        if k == 0:
            ax[1].hist(amp, bins=edges, color=cols[k % 3], alpha=0.85)
            s0 = S[m].mean()
            ax[1].axvline(np.sqrt(s0 / 2), color=C_PY, lw=1.5, label=f'Rayleigh mode √(S₀/2) → π·S₀/2 = {np.pi*s0/2:.1f} Hz')
            ax[1].axvline(np.sqrt(s0), color=INK, lw=1.2, ls='--', label=f'√S₀ (mean power) → π·S₀ = {np.pi*s0:.1f} Hz')
            ax[1].axvline(np.sqrt(int_g / np.pi), color=C_GUI, lw=1.5, ls=':',
                          label=f'GUI Intrinsic {int_g:.1f} Hz ↔ √(I/π)')
    xx = np.logspace(1.7, 7, 100)
    ax[0].loglog(xx, 8 * np.log(2) * xx / np.pi ** 2, color=INK2, lw=1, ls='--', label='β-separation line')
    ax[0].set_xlabel('Fourier frequency [Hz]'); ax[0].set_ylabel('FN PSD [Hz²/Hz]')
    ax[0].set_title('Your FN exports', loc='left', color=INK)
    ax[0].legend(fontsize=8.5)
    ax[1].set_xlabel(f'amplitude √S [Hz/√Hz], {FLOOR[0]/1e6:g}–{FLOOR[1]/1e6:g} MHz')
    ax[1].set_ylabel('bins per histogram cell')
    ax[1].set_title('Why "Intrinsic (Mode(stat))" ≈ half of π·S₀', loc='left', color=INK)
    ax[1].legend(fontsize=8.5)
    txt = 'export        Effective GUI | Python      Intrinsic GUI | π·mode(amp)² | π·mean(S)\n' + '\n'.join(
        f'{r[0]:>8}   {r[1]:9.2f} | {r[2]:9.2f} Hz     {r[3]:6.1f} | {r[4]:6.1f} | {r[5]:6.1f} Hz' for r in rows)
    fig.text(0.01, -0.02, txt, family='monospace', fontsize=9, color=INK, va='top')
    fig.suptitle('Linewidths: GUI header vs Python on the same spectra', x=0.01, ha='left', color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '3_linewidths_gui_vs_python.png'), dpi=150, bbox_inches='tight')
    return rows


def fig_fn_gui_averaging():
    """The GUI's FN Averaging vs the three ways of averaging the 10 Python captures."""
    if not os.path.isfile(GUI_FN_N10):
        return None
    x, P = load_captures(FN_CAPTURES)
    hdr, xg, Sg = read_export(GUI_FN_N10)
    singles = [read_export(f) for f in [GUI_EXPORT_SAME_CAPTURE] + EXTRA_FN_EXPORTS if os.path.isfile(f)]
    avgs = {'power average (Python default, unbiased)': (P.mean(0), C_PY, '-'),
            'amplitude average (Hz/√Hz)': (np.sqrt(P).mean(0) ** 2, C_3, '-'),
            'dB average': (np.exp(np.log(P).mean(0)), C_4, '-')}
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.8), gridspec_kw=dict(width_ratios=[1.4, 1]))
    for lab, (y, c, ls) in avgs.items():
        xb, yb = binned(x, y)
        ax[0].loglog(xb, yb, color=c, lw=1.5, ls=ls, label=f'Python 10 captures: {lab}')
    xb, yb = binned(xg, Sg)
    ax[0].loglog(xb, yb, color=C_GUI, lw=2.2, ls='--', label=f'GUI export, Averaging n = {hdr.get("Av count")}')
    ax[0].set_xlabel('Fourier frequency [Hz]'); ax[0].set_ylabel('FN PSD [Hz²/Hz] (40 bins/decade, linear mean)')
    ax[0].set_title('FN: which averaging does the GUI use?', loc='left', color=INK)
    ax[0].legend(fontsize=8.5)
    bands = [(1e5, 1e6), (1e6, 9e6), (2e6, 8e6), (5e6, 6e6)]
    labels = [f'{lo/1e6:g}–{hi/1e6:g} MHz' for lo, hi in bands]
    w = 0.16
    series = [('power avg', P.mean(0), x, C_PY), ('amplitude avg', np.sqrt(P).mean(0) ** 2, x, C_3),
              ('dB avg', np.exp(np.log(P).mean(0)), x, C_4), ('GUI n = 10', Sg, xg, C_GUI)]
    for k, (lab, y, xx, c) in enumerate(series):
        vals = [y[(xx > lo) & (xx < hi)].mean() for lo, hi in bands]
        ax[1].bar(np.arange(len(bands)) + (k - 1.5) * w, vals, w * 0.92, color=c, label=lab)
    for xs, Ss in [(s[1], s[2]) for s in singles]:
        vals = [Ss[(xs > lo) & (xs < hi)].mean() for lo, hi in bands]
        ax[1].plot(np.arange(len(bands)) + 0.42, vals, 'o', color=INK, ms=4)
    ax[1].plot([], [], 'o', color=INK, ms=4, label='GUI single exports')
    ax[1].set_xticks(np.arange(len(bands)), labels)
    ax[1].set_ylabel('mean S [Hz²/Hz]')
    ax[1].set_title('GUI n = 10 = amplitude average (0.81× power)', loc='left', color=INK)
    ax[1].legend(fontsize=8.5, ncol=2)
    fig.suptitle('FN averaging: GUI Averaging = 10 vs Python', x=0.01, ha='left', color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, '4_fn_gui_averaging.png'), dpi=150)
    m = (x > 1e6) & (x < 9e6); mg = (xg > 1e6) & (xg < 9e6)
    return dict(gui_over_power=float(Sg[mg].mean() / P.mean(0)[m].mean()), theory=np.pi / 4 + (1 - np.pi / 4) / 10)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    print('1:', fig_same_capture())
    print('2:', fig_averaging())
    print('3:', fig_linewidths())
    print('4:', fig_fn_gui_averaging())
    print('figures in', OUT)
