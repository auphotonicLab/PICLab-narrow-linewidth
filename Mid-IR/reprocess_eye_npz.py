#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reprocess existing _data.npz eye diagram files with updated bin settings.

Loads t, v, t_chip, v_chip, bit_rate from one or more _data.npz files,
recomputes the persistence eye histograms with the current bin settings,
saves new PDF/SVG plots and an HDF5 file matching the Eye_diagram_lab.py format.

Usage:
    python reprocess_eye_npz.py                  # processes all _data.npz in DATA_ROOT
    python reprocess_eye_npz.py path/to/file.npz # processes a single file
"""

import sys
import os
import glob
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter
import h5py

# =============================================================================
# Settings — match or override what was used during measurement
# =============================================================================

DATA_ROOT    = r'C:\Users\shd-photonics-inp\Documents\Jeppe_Surrow\Eye_diagram\Eye_diagram_data'
N_PERIODS    = 10_000       # bit periods used during acquisition
EYE_BINS_V   = 1500         # voltage bins (fixed)
EYE_SMOOTH   = 0            # Gaussian sigma in bins; 0 = off

# =============================================================================
# Helpers
# =============================================================================

def _make_eye(t_arr, v_arr, bit_period, eye_bins, t_offset=None):
    threshold = 0.5 * (v_arr.max() + v_arr.min())
    if t_offset is None:
        crossings_idx = np.where(np.diff((v_arr > threshold).astype(int)) != 0)[0]
        if len(crossings_idx) >= 4:
            cross_times = t_arr[crossings_idx]
            fold_1T = (cross_times - t_arr[0]) % bit_period
            counts, edges = np.histogram(fold_1T * 1e9, bins=200)
            peak = np.argmax(counts)
            cross_phase = 0.5 * (edges[peak] + edges[peak + 1]) * 1e-9
            t_offset = t_arr[0] + cross_phase - bit_period / 2
        else:
            t_offset = t_arr[0]
    t_fold = (t_arr - t_offset) % (2 * bit_period)
    H, t_ed, v_ed = np.histogram2d(t_fold * 1e9, v_arr, bins=eye_bins)
    if EYE_SMOOTH > 0:
        H = gaussian_filter(H, sigma=EYE_SMOOTH)
    return H.T, t_ed, v_ed, t_offset


def _compute_eye_metrics(t_arr, v_arr, bit_period, label):
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

    above       = (v_arr > threshold).astype(int)
    rise_idx    = np.where(np.diff(above) == 1)[0]
    cross_times = []
    for i in rise_idx:
        dv = v_arr[i + 1] - v_arr[i]
        if dv != 0:
            tc = t_arr[i] + (threshold - v_arr[i]) / dv * (t_arr[i + 1] - t_arr[i])
            cross_times.append(tc)

    jitter_rms_ps = jitter_pp_ps = np.nan
    n_cross = len(cross_times)
    if n_cross >= 10:
        ct   = np.array(cross_times)
        fold = (ct - ct[0]) % bit_period
        med  = np.median(fold)
        ok   = np.abs(fold - med) < 0.4 * bit_period
        jitter_rms_ps = fold[ok].std() * 1e12
        jitter_pp_ps  = (fold[ok].max() - fold[ok].min()) * 1e12
        n_cross       = ok.sum()

    return dict(label=label,
                v_high_V=v_hi,       v_high_std_mV=v_hi_std * 1e3,
                v_low_V=v_lo,        v_low_std_mV=v_lo_std * 1e3,
                eye_opening_V=eye_open,
                ER_dB_optical=er_opt, ER_dB_elec=er_elec,
                jitter_rms_ps=jitter_rms_ps,
                jitter_pp_ps=jitter_pp_ps,
                n_crossings=n_cross)


def _plot_eye(H, t_ed, v_ed, title, save_path_base):
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
              cmap='hot', interpolation='nearest')
    ylo, yhi = v_ed[0], v_ed[-1]
    pad = 0.02 * (yhi - ylo)
    ax.set_ylim(ylo - pad, yhi + pad)
    fig.tight_layout()
    for ext in ('pdf', 'svg'):
        p = f'{save_path_base}.{ext}'
        fig.savefig(p, bbox_inches='tight', facecolor='black')
        print(f'  Saved: {p}')
    plt.close(fig)


def reprocess(npz_path):
    print(f'\nProcessing: {npz_path}')
    d = np.load(npz_path)
    t        = d['t']
    v        = d['v']
    t_chip   = d['t_chip']
    v_chip   = d['v_chip']
    bit_rate = float(d['bit_rate'])
    bit_period = 1.0 / bit_rate

    eye_bins_t = len(v) // N_PERIODS
    eye_bins   = (eye_bins_t, EYE_BINS_V)
    print(f'  Bit rate: {bit_rate/1e6:.1f} Mbps,  '
          f'Samples: {len(v):,},  '
          f'Eye bins: {eye_bins[0]} × {eye_bins[1]}  '
          f'({2/bit_rate*1e9/eye_bins[0]*1e3:.2f} ps/bin time, '
          f'{(v.max()-v.min())/eye_bins[1]*1e3:.2f} mV/bin volt approx)')

    folder    = os.path.dirname(npz_path)
    timestamp = os.path.basename(npz_path).replace('_data.npz', '')
    suffix    = f'_reprocessed_{eye_bins[0]}t_{eye_bins[1]}v'

    H_ref, t_ed_ref, v_ed_ref, t_off = _make_eye(t, v, bit_period, eye_bins)
    _plot_eye(H_ref, t_ed_ref, v_ed_ref,
              f'Persistence Eye — Reference CH1 — {bit_rate/1e6:.0f} Mbps',
              os.path.join(folder, f'{timestamp}_persistence_reference_ch1{suffix}'))

    H_chip, t_ed_chip, v_ed_chip, _ = _make_eye(
        t_chip, v_chip, bit_period, eye_bins, t_offset=t_off)
    _plot_eye(H_chip, t_ed_chip, v_ed_chip,
              f'Persistence Eye — Through-chip CH2 — {bit_rate/1e6:.0f} Mbps',
              os.path.join(folder, f'{timestamp}_persistence_through_chip_ch2{suffix}'))

    m_ref  = _compute_eye_metrics(t,      v,      bit_period, 'CH1 reference')
    m_chip = _compute_eye_metrics(t_chip, v_chip, bit_period, 'CH2 through-chip')

    # =========================================================================
    # Save HDF5 — same format as Eye_diagram_lab.py
    # =========================================================================
    h5_path = os.path.join(folder, f'{timestamp}{suffix}_data.h5')
    with h5py.File(h5_path, 'w') as hf:

        hf.attrs['timestamp']               = timestamp
        hf.attrs['label']                   = ''
        hf.attrs['bit_rate_Hz']             = bit_rate
        hf.attrs['sequence']                = str(d['sequence']) if 'sequence' in d else 'unknown'
        hf.attrs['v_quad_V']                = float(d['v_quad'])    if 'v_quad'    in d else np.nan
        hf.attrs['v_pp_V']                  = float(d['v_pp'])      if 'v_pp'      in d else np.nan
        hf.attrs['dc_channel']              = int(d['dc_channel'])  if 'dc_channel' in d else -1
        hf.attrs['dc_current_A']            = float(d['dc_current_A']) if 'dc_current_A' in d else np.nan
        hf.attrs['osc_signal_ch']           = int(d['osc_signal_ch'])  if 'osc_signal_ch'  in d else 1
        hf.attrs['osc_chip_ch']             = int(d['osc_chip_ch'])    if 'osc_chip_ch'    in d else 2
        hf.attrs['osc_clock_ch']            = int(d['osc_clock_ch'])   if 'osc_clock_ch'   in d else 3
        hf.attrs['trigger_source']          = str(d['trigger_source']) if 'trigger_source' in d else 'unknown'
        hf.attrs['trigger_level_V']         = float(d['trigger_level_V'])        if 'trigger_level_V'        in d else np.nan
        hf.attrs['time_scale_s_per_div']    = float(d['time_scale_s_per_div'])   if 'time_scale_s_per_div'   in d else np.nan
        hf.attrs['volt_scale_ch1_V_per_div']= float(d['volt_scale_ch1_V_per_div']) if 'volt_scale_ch1_V_per_div' in d else np.nan
        hf.attrs['signal_offset_ch1_V']     = float(d['signal_offset_ch1_V'])    if 'signal_offset_ch1_V'    in d else np.nan
        hf.attrs['chip_volt_scale_V_per_div']= float(d['chip_volt_scale_V_per_div']) if 'chip_volt_scale_V_per_div' in d else np.nan
        hf.attrs['chip_offset_V']           = float(d['chip_offset_V'])          if 'chip_offset_V'          in d else np.nan
        hf.attrs['clock_volt_scale_V_per_div']= float(d['clock_volt_scale_V_per_div']) if 'clock_volt_scale_V_per_div' in d else np.nan
        hf.attrs['clock_offset_V']          = float(d['clock_offset_V'])         if 'clock_offset_V'         in d else np.nan
        hf.attrs['bw_limit_Hz']             = float(d['bw_limit_Hz'])            if 'bw_limit_Hz'            in d else -1
        hf.attrs['coupling']                = str(d['coupling'])                  if 'coupling'               in d else 'DC'
        hf.attrs['n_ui_persistence']        = int(d['n_ui_persistence'])          if 'n_ui_persistence'       in d else -1
        hf.attrs['record_length_requested'] = int(d['record_length_requested'])   if 'record_length_requested' in d else -1
        hf.attrs['record_length_actual']    = len(v)
        hf.attrs['eye_bins_time']           = eye_bins[0]
        hf.attrs['eye_bins_volt']           = eye_bins[1]
        hf.attrs['eye_smooth_sigma_bins']   = EYE_SMOOTH
        hf.attrs['reprocessed_from_npz']    = os.path.basename(npz_path)

        # Waveforms
        wg = hf.create_group('waveforms')
        for grp_name, t_arr, v_arr, ch, desc in [
            ('reference',    t,      v,      1, 'Reference signal'),
            ('through_chip', t_chip, v_chip, 2, 'Through-chip signal'),
        ]:
            g = wg.create_group(grp_name)
            g.create_dataset('t_s', data=t_arr.astype(np.float64),
                             compression='gzip', compression_opts=4)
            g.create_dataset('v_V', data=v_arr.astype(np.float32),
                             compression='gzip', compression_opts=4)
            g.attrs['channel']     = ch
            g.attrs['description'] = desc
            g.attrs['n_samples']   = len(v_arr)
            g.attrs['v_min_V']     = float(v_arr.min())
            g.attrs['v_max_V']     = float(v_arr.max())
            g.attrs['v_mean_V']    = float(v_arr.mean())

        # Eye diagrams
        eg = hf.create_group('eye_diagrams')
        for grp_name, H, t_ed, v_ed, ch, desc in [
            ('reference',    H_ref,  t_ed_ref,  v_ed_ref,  1, 'Reference CH1'),
            ('through_chip', H_chip, t_ed_chip, v_ed_chip, 2, 'Through-chip CH2'),
        ]:
            g = eg.create_group(grp_name)
            g.create_dataset('H', data=H.astype(np.float32),
                             compression='gzip', compression_opts=4)
            g.create_dataset('t_edges_ns', data=t_ed)
            g.create_dataset('v_edges_V',  data=v_ed)
            g.attrs['channel']         = ch
            g.attrs['description']     = desc
            g.attrs['t_offset_s']      = float(t_off)
            g.attrs['shared_t_offset'] = (grp_name == 'through_chip')
            g.attrs['H_shape']         = f'{H.shape[0]} (volt) × {H.shape[1]} (time)'

        # Metrics
        mg = hf.create_group('metrics')
        for m, grp_name in [(m_ref, 'reference'), (m_chip, 'through_chip')]:
            g = mg.create_group(grp_name)
            g.attrs['label'] = m['label']
            for key, val in m.items():
                if key == 'label':
                    continue
                g.attrs[key] = float(val) if not (isinstance(val, float) and
                                                   np.isnan(val)) else 'NaN'

    print(f'  HDF5 saved: {h5_path}')


# =============================================================================
# Main
# =============================================================================

if len(sys.argv) > 1:
    files = sys.argv[1:]
else:
    files = glob.glob(os.path.join(DATA_ROOT, '**', '*_data.npz'), recursive=True)
    if not files:
        print(f'No _data.npz files found under {DATA_ROOT}')
        sys.exit(1)
    print(f'Found {len(files)} file(s) to reprocess.')

for f in files:
    reprocess(f)

print('\nDone.')
