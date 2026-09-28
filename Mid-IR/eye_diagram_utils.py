#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared eye-diagram helpers for Eye_diagram_lab.py and reprocess_eye_npz.py.

Binning is chosen to be *truthful* to what the R&S RTO actually records:

Voltage axis
    The RTO stores each sample as an ADC code. From the RTO user manual
    ("Raw (ADC direct)" data conversion, p. 462):

        ConversionFactor = VerticalScale * VerticalDivisionCount / NofQuantisationLevels
        Voltage          = Value_ADC * ConversionFactor + VerticalOffset

    with VerticalDivisionCount = 10 and NofQuantisationLevels = 253 (8-bit),
    or 253*256 in High Definition mode (16-bit words). The HD word is finer
    than the real resolution, which is reported by HDEFinition:RESolution?
    (e.g. ~10-12 bit depending on the HD filter bandwidth).

    -> one voltage bin = one effective ADC level, with bin edges placed
       halfway between levels so every level falls in exactly one bin.

Time axis
    The folded samples sit on a grid set by the sample interval. For
    20 Mbit/s and 10 GSa/s, 2 UI / dt = 1000 exactly, and the AFG and scope
    clocks drift only ~0.1 ppm relative to each other, so the folded sample
    phases barely move. Bins finer than dt would be empty columns.

    -> one time bin = one sample interval, with the fold phase nudged
       (< dt/2) so the sample phases sit in the bin centres.
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter
import h5py

N_VDIV          = 10    # vertical divisions (ADC full-scale = 10 div)
ADC_LEVELS_8BIT = 253   # NofQuantisationLevels for 8-bit data (RTO manual p. 462)
HD_WORD_FACTOR  = 256   # HD mode: 16-bit words, 253*256 levels


# =============================================================================
# Quantisation grid
# =============================================================================

def adc_word_step(volt_scale, hd=False):
    """Voltage spacing between adjacent stored ADC codes [V]."""
    step = volt_scale * N_VDIV / ADC_LEVELS_8BIT
    return step / HD_WORD_FACTOR if hd else step


def infer_grid(v, max_levels=200_000):
    """Infer the quantisation grid (origin, step) directly from the samples.

    Works for any data exported as REAL/float from ADC codes: all samples
    lie on origin + k*step. Returns (origin, step) or (None, None) if the
    data does not look quantised.
    """
    u = np.unique(np.asarray(v, dtype=np.float64))
    if len(u) < 3 or len(u) > max_levels:
        return None, None
    d = np.diff(u)
    if d.min() <= 0:
        return None, None
    # Adjacent-level spacing: median of the smallest gaps (robust to float32
    # rounding, which matters for fine HD steps), then refine by a straight-line
    # fit through all levels.
    step = np.median(d[d < 1.5 * d.min()])
    origin = u[0]
    # Multi-scale refinement: fit over a small span of levels first (where the
    # rough step cannot mis-number levels), then widen. Needed for HD data with
    # tens of thousands of levels.
    span = 64
    while True:
        sel = u <= origin + span * step
        k = np.round((u[sel] - origin) / step)
        if len(np.unique(k)) >= 2:
            step, origin = np.polyfit(k, u[sel], 1)
        if sel.all():
            break
        span *= 8
    k = np.round((u - origin) / step)
    resid = u - (origin + k * step)
    if np.max(np.abs(resid)) > 0.05 * step:
        return None, None
    return origin, step


def resolve_voltage_grid(v, volt_scale=None, offset=None, hd=False,
                         eff_bits=None, levels_per_bin=1, label=''):
    """Decide the voltage bin step and grid origin for one channel.

    The grid measured from the data is used when available (it is what the
    scope really recorded); scope settings are used as a cross-check and as
    a fallback.

    Returns dict with origin_V, word_step_V, bin_step_V, n_levels_per_bin,
    source, eff_bits, n_levels_used.
    """
    origin, word_step = infer_grid(v)
    expected = adc_word_step(volt_scale, hd) if volt_scale and np.isfinite(volt_scale) else None
    source = 'data'

    if word_step is None:
        if expected is None:
            raise ValueError(f'{label}: data is not quantised and no volt_scale '
                             f'is known - cannot determine ADC levels.')
        word_step = expected
        origin = offset if (offset is not None and np.isfinite(offset)) else 0.0
        source = 'scope settings'
    elif expected is not None:
        rel = abs(word_step / expected - 1)
        if rel > 0.01:
            print(f'  NOTE {label}: level spacing in data {word_step*1e3:.4f} mV '
                  f'differs from scope settings {expected*1e3:.4f} mV '
                  f'({volt_scale} V/div{", HD" if hd else ""}) - using the data.')

    # Implied vertical scale from 8-bit word step (useful for old files)
    implied_scale = word_step * ADC_LEVELS_8BIT / N_VDIV * (HD_WORD_FACTOR if hd else 1)

    # HD: words are 16 bit but the true resolution is eff_bits
    m = 1
    if hd and eff_bits and np.isfinite(eff_bits) and eff_bits < 16:
        m = max(1, int(round(2 ** (16 - eff_bits))))
    elif not hd:
        eff_bits = 8.0
    m *= max(1, int(levels_per_bin))

    return dict(origin_V=float(origin), word_step_V=float(word_step),
                bin_step_V=float(word_step * m), n_words_per_bin=int(m),
                source=source, eff_bits=float(eff_bits) if eff_bits else np.nan,
                implied_volt_scale_V_per_div=float(implied_scale),
                n_levels_used=int(len(np.unique(v))) if source == 'data' else -1)


def voltage_edges(v, grid):
    """Bin edges half a word below each group of levels -> one level set per bin."""
    o, w, s = grid['origin_V'], grid['word_step_V'], grid['bin_step_V']
    lo = o - 0.5 * w
    j_min = int(np.floor((v.min() - lo) / s))
    j_max = int(np.floor((v.max() - lo) / s))
    return lo + np.arange(j_min, j_max + 2) * s


def check_clipping(v, volt_scale, offset, label=''):
    """Warn if the waveform touches the ADC limits (offset ± 5 div)."""
    if not (volt_scale and offset is not None and np.isfinite(volt_scale) and np.isfinite(offset)):
        return
    top = offset + 0.5 * N_VDIV * volt_scale
    bot = offset - 0.5 * N_VDIV * volt_scale
    step = adc_word_step(volt_scale)
    n_hi = int(np.sum(v >= top - 1.5 * step))
    n_lo = int(np.sum(v <= bot + 1.5 * step))
    if n_hi or n_lo:
        print(f'  WARNING {label}: {n_hi} samples at the top / {n_lo} at the bottom '
              f'of the ADC range [{bot:.3f}, {top:.3f}] V - signal is clipped. '
              f'Increase V/div or adjust the offset.')


# =============================================================================
# Time grid
# =============================================================================

def regularise_time_axis(t):
    """Return an evenly spaced time axis with the true sample interval.

    Older data was built with np.linspace(start, stop, N), which stretches
    the interval by N/(N-1). Pick whichever of span/N or span/(N-1) gives
    the rounder sample rate (scope sample rates are whole MSa/s).
    """
    t = np.asarray(t, dtype=np.float64)
    n = len(t)
    span = t[-1] - t[0]
    cands = [span / (n - 1), span / n]
    def _roundness(dt):
        sr = 1.0 / dt
        return abs(sr / 1e6 - round(sr / 1e6)) / (sr / 1e6)
    dt = min(cands, key=_roundness)
    return t[0] + np.arange(n) * dt, dt


def find_t_offset(t_arr, v_arr, bit_period):
    """Fold phase that puts the most common crossing in the middle of the 2-UI window."""
    threshold = 0.5 * (v_arr.max() + v_arr.min())
    idx = np.where(np.diff((v_arr > threshold).astype(int)) != 0)[0]
    if len(idx) < 4:
        return t_arr[0]
    fold_1T = (t_arr[idx] - t_arr[0]) % bit_period
    counts, edges = np.histogram(fold_1T * 1e9, bins=200)
    peak = np.argmax(counts)
    cross_phase = 0.5 * (edges[peak] + edges[peak + 1]) * 1e-9
    return t_arr[0] + cross_phase - bit_period / 2


def time_grid(t_arr, dt, bit_period, t_offset, samples_per_bin=1):
    """Time edges [ns] of width ≈ samples_per_bin*dt over 2 UI, plus a
    phase-adjusted t_offset that centres the sample phases in the bins."""
    window = 2 * bit_period
    n_bins = max(1, int(round(window / (dt * samples_per_bin))))
    bin_w = window / n_bins
    # Shift fold phase so (t0 - t_offset) mod dt = dt/2  (shift < dt/2)
    phi = (t_arr[0] - t_offset) % dt
    t_offset_c = t_offset + (phi - 0.5 * dt)
    edges_ns = np.arange(n_bins + 1) * bin_w * 1e9
    return edges_ns, t_offset_c


# =============================================================================
# Eye histogram
# =============================================================================

def make_eye(t_arr, v_arr, bit_period, dt, vgrid, t_offset=None,
             samples_per_bin=1, smooth=0):
    """Fold into a 2-UI persistence histogram on the truthful grid.

    Returns (H[volt, time], t_edges_ns, v_edges_V, t_offset_s).
    Pass t_offset to reuse the same phase alignment across channels.
    """
    if t_offset is None:
        t_offset = find_t_offset(t_arr, v_arr, bit_period)
        t_ed, t_offset = time_grid(t_arr, dt, bit_period, t_offset, samples_per_bin)
    else:
        t_ed, _ = time_grid(t_arr, dt, bit_period, t_offset, samples_per_bin)
    v_ed = voltage_edges(v_arr, vgrid)
    t_fold = (t_arr - t_offset) % (2 * bit_period)
    H, _, _ = np.histogram2d(t_fold * 1e9, v_arr, bins=[t_ed, v_ed])
    if smooth > 0:
        H = gaussian_filter(H, sigma=smooth)
    return H.T, t_ed, v_ed, t_offset


def plot_eye(H, t_ed, v_ed, title, save_path_base, cmap='hot', dpi=600, show=False):
    """Render and save PDF + SVG. interpolation='none' embeds the histogram
    at native resolution in vector output, so no bins are dropped."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_facecolor('black')
    fig.patch.set_facecolor('black')
    ax.set_xlabel('Time [ns]', color='white')
    ax.set_ylabel('Voltage [V]', color='white')
    ax.set_title(title, color='white')
    ax.tick_params(colors='white')
    for spine in ax.spines.values():
        spine.set_edgecolor('white')
    ax.imshow(np.ma.masked_where(H == 0, np.log1p(H)),
              origin='lower', aspect='auto',
              extent=[t_ed[0], t_ed[-1], v_ed[0], v_ed[-1]],
              cmap=cmap, interpolation='none')
    ylo, yhi = v_ed[0], v_ed[-1]
    pad = 0.02 * (yhi - ylo)
    ax.set_ylim(ylo - pad, yhi + pad)
    fig.tight_layout()
    for ext in ('pdf', 'svg'):
        p = f'{save_path_base}.{ext}'
        fig.savefig(p, bbox_inches='tight', facecolor='black', dpi=dpi)
        print(f'  Saved: {p}')
    if show:
        plt.show()
    else:
        plt.close(fig)


def describe_bins(label, vgrid, t_ed, v_ed, dt):
    nt, nv = len(t_ed) - 1, len(v_ed) - 1
    print(f'  {label}: {nt} time bins × {nv} voltage bins | '
          f'{(t_ed[1]-t_ed[0])*1e3:.1f} ps/bin (dt = {dt*1e12:.1f} ps), '
          f'{vgrid["bin_step_V"]*1e3:.4f} mV/bin '
          f'(ADC step {vgrid["word_step_V"]*1e3:.4f} mV, '
          f'{vgrid["eff_bits"]:.1f} bit, grid from {vgrid["source"]}, '
          f'≈{vgrid["implied_volt_scale_V_per_div"]:.4g} V/div)')


# =============================================================================
# Metrics
# =============================================================================

def compute_eye_metrics(t_arr, v_arr, bit_period, label):
    """Rail levels, extinction ratio and crossing jitter from a raw waveform.

    ER_dB_optical uses 10·log10(V_high/V_low) (photodetector voltage ∝ power);
    ER_dB_elec uses 20·log10. Jitter from interpolated rising-edge crossings
    folded modulo one bit period.
    """
    threshold = 0.5 * (v_arr.max() + v_arr.min())
    margin    = 0.25 * (v_arr.max() - v_arr.min())
    upper = v_arr[v_arr > threshold + margin]
    lower = v_arr[v_arr < threshold - margin]
    v_hi     = upper.mean() if len(upper) else np.nan
    v_hi_std = upper.std()  if len(upper) else np.nan
    v_lo     = lower.mean() if len(lower) else np.nan
    v_lo_std = lower.std()  if len(lower) else np.nan
    eye_open = v_hi - v_lo
    er_opt   = 10 * np.log10(v_hi / v_lo) if v_lo > 0 else np.nan
    er_elec  = 20 * np.log10(v_hi / v_lo) if v_lo > 0 else np.nan

    above = (v_arr > threshold).astype(int)
    i = np.where(np.diff(above) == 1)[0]
    dv = v_arr[i + 1] - v_arr[i]
    ok_dv = dv != 0
    i, dv = i[ok_dv], dv[ok_dv]
    cross_times = t_arr[i] + (threshold - v_arr[i]) / dv * (t_arr[i + 1] - t_arr[i])

    jitter_rms_ps = jitter_pp_ps = np.nan
    n_cross = len(cross_times)
    if n_cross >= 10:
        fold = (cross_times - cross_times[0]) % bit_period
        med  = np.median(fold)
        ok   = np.abs(fold - med) < 0.4 * bit_period
        jitter_rms_ps = fold[ok].std() * 1e12
        jitter_pp_ps  = (fold[ok].max() - fold[ok].min()) * 1e12
        n_cross       = int(ok.sum())

    return dict(label=label,
                v_high_V=v_hi,       v_high_std_mV=v_hi_std * 1e3,
                v_low_V=v_lo,        v_low_std_mV=v_lo_std * 1e3,
                eye_opening_V=eye_open,
                ER_dB_optical=er_opt, ER_dB_elec=er_elec,
                jitter_rms_ps=jitter_rms_ps,
                jitter_pp_ps=jitter_pp_ps,
                n_crossings=n_cross)


def print_metrics(m, bit_period):
    print(f"\n  Eye metrics — {m['label']}")
    print(f"    V_high = {m['v_high_V']:.4f} V  (σ = {m['v_high_std_mV']:.2f} mV)")
    print(f"    V_low  = {m['v_low_V']:.4f} V  (σ = {m['v_low_std_mV']:.2f} mV)")
    print(f"    Eye opening        = {m['eye_opening_V']*1e3:.2f} mV")
    print(f"    ER (10·log, opt.)  = {m['ER_dB_optical']:.2f} dB")
    print(f"    ER (20·log, elec.) = {m['ER_dB_elec']:.2f} dB")
    print(f"    Jitter RMS  = {m['jitter_rms_ps']:.2f} ps  "
          f"({m['jitter_rms_ps']*1e-12/bit_period:.4f} UI)")
    print(f"    Jitter p-p  = {m['jitter_pp_ps']:.2f} ps  "
          f"({m['jitter_pp_ps']*1e-12/bit_period:.4f} UI)")
    print(f"    N rising crossings = {m['n_crossings']}")


# =============================================================================
# HDF5
# =============================================================================

def _attr(val):
    """h5py-safe attribute value (None -> 'None', NaN kept)."""
    if val is None:
        return 'None'
    if isinstance(val, (np.generic,)):
        return val.item()
    return val


def write_eye_h5(h5_path, root_attrs, channels, t_offset, screenshots=None,
                 include_waveforms=True):
    """Write the standard eye-diagram HDF5 file.

    channels: list of dicts with keys
        name ('reference'/'through_chip'), channel, description,
        t, v, H, t_ed, v_ed, vgrid, dt, metrics, wf_attrs (dict, optional)
    include_waveforms=False skips the raw t/v arrays (e.g. for reprocessed
    files whose raw data already lives in the source file); per-channel
    scope metadata is then stored on the eye_diagrams groups instead.
    """
    with h5py.File(h5_path, 'w') as hf:
        for k, val in root_attrs.items():
            hf.attrs[k] = _attr(val)

        wg = hf.create_group('waveforms') if include_waveforms else None
        eg = hf.create_group('eye_diagrams')
        mg = hf.create_group('metrics')
        # Byte-shuffle + gzip-9 compresses the quantised waveforms ~3x better
        # than plain gzip; lossless.
        ckw = dict(compression='gzip', compression_opts=9, shuffle=True)
        t_written = []          # (array, dataset) already stored
        for i, c in enumerate(channels):
            if include_waveforms:
                g = wg.create_group(c['name'])
                t_arr = np.asarray(c['t'], np.float64)
                shared = next((ds for a, ds in t_written if np.array_equal(a, t_arr)), None)
                if shared is not None:
                    g['t_s'] = shared   # hard link: identical time axis stored once
                else:
                    ds = g.create_dataset('t_s', data=t_arr, **ckw)
                    t_written.append((t_arr, ds))
                g.create_dataset('v_V', data=np.asarray(c['v'], np.float32), **ckw)
                g.attrs['channel']           = c['channel']
                g.attrs['description']       = c['description']
                g.attrs['n_samples']         = len(c['v'])
                g.attrs['v_min_V']           = float(np.min(c['v']))
                g.attrs['v_max_V']           = float(np.max(c['v']))
                g.attrs['v_mean_V']          = float(np.mean(c['v']))
                g.attrs['sample_interval_s'] = float(c['dt'])
                for k, val in (c.get('wf_attrs') or {}).items():
                    g.attrs[k] = _attr(val)

            e = eg.create_group(c['name'])
            if not include_waveforms:
                e.attrs['sample_interval_s'] = float(c['dt'])
                e.attrs['n_samples']         = len(c['v'])
                for k, val in (c.get('wf_attrs') or {}).items():
                    e.attrs['scope_' + k] = _attr(val)
            e.create_dataset('H', data=c['H'].astype(np.float32), **ckw)
            e.create_dataset('t_edges_ns', data=c['t_ed'])
            e.create_dataset('v_edges_V',  data=c['v_ed'])
            e.attrs['channel']            = c['channel']
            e.attrs['description']        = c['description']
            e.attrs['t_offset_s']         = float(t_offset)
            e.attrs['shared_t_offset']    = i > 0
            e.attrs['H_shape']            = f'{c["H"].shape[0]} (volt) × {c["H"].shape[1]} (time)'
            e.attrs['eye_bins_time']      = len(c['t_ed']) - 1
            e.attrs['eye_bins_volt']      = len(c['v_ed']) - 1
            e.attrs['time_bin_s']         = float((c['t_ed'][1] - c['t_ed'][0]) * 1e-9)
            for k, val in c['vgrid'].items():
                e.attrs['vgrid_' + k] = _attr(val)

            m = mg.create_group(c['name'])
            m.attrs['label'] = c['metrics']['label']
            for k, val in c['metrics'].items():
                if k == 'label':
                    continue
                m.attrs[k] = 'NaN' if (isinstance(val, float) and np.isnan(val)) else float(val)

        if screenshots:
            sg = hf.create_group('screenshots')
            for tag, png_path in screenshots:
                if os.path.exists(png_path):
                    img = plt.imread(png_path)
                    ds = sg.create_dataset(tag, data=img,
                                           compression='gzip', compression_opts=4)
                    ds.attrs['filename'] = os.path.basename(png_path)
                    ds.attrs['CLASS']    = 'IMAGE'
    print(f'  HDF5 saved: {h5_path}')
