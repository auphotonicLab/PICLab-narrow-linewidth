#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reprocess saved eye-diagram measurements (_data.npz or _data.h5) with
ADC-truthful binning.

Voltage bins = one effective ADC level (8-bit: V/div*10/253; HD: from the
stored HD resolution). Time bins = one sample interval. See
eye_diagram_utils.py for details. The level spacing is measured from the
data itself, so this also works for old files without scope metadata.

Accepted inputs:
    <timestamp>_data.npz   (older Eye_diagram_lab.py versions)
    <timestamp>_data.h5    (current Eye_diagram_lab.py)
Files produced by this script (*_reprocessed_*) are skipped. If both an .npz
and an .h5 exist for the same timestamp, the .h5 is used.

Usage:
    python reprocess_eye_npz.py                    # everything under DATA_ROOT
    python reprocess_eye_npz.py file1.h5 file2.npz # specific files
"""

import sys
import os
import glob
import numpy as np
import h5py

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eye_diagram_utils as eu

# =============================================================================
# Settings
# =============================================================================

DATA_ROOT            = r'C:\Users\shd-photonics-inp\Documents\Jeppe_Surrow\Eye_diagram\Eye_diagram_data'
EYE_V_LEVELS_PER_BIN = 1     # ADC levels per voltage bin (1 = full ADC resolution)
EYE_T_SAMPLES_PER_BIN = 1    # sample intervals per time bin (1 = full sample resolution)
EYE_SMOOTH           = 0     # Gaussian sigma in bins; 0 = off
PLOT_DPI             = 600
# The raw waveforms stay in the source _data file; copying them into every
# reprocessed .h5 would duplicate ~60 MB per measurement. Set True to include.
INCLUDE_WAVEFORMS    = False

# Per-folder notes: folder name -> (filename tag, short title note, h5 note).
# Only applied to files inside a folder with exactly this name.
FOLDER_NOTES = {
    'Eye_diagram_1550nm_ref(ch2)+chip(ch1)': (
        'detswap', 'det. swapped',
        'Detectors swapped: the reference-detector channel measures the chip '
        'output and the chip-detector channel measures the reference tap '
        '(fibers/adapters exchanged, see Eye_diagram_data/Readme.txt).'),
}

# =============================================================================
# Loading
# =============================================================================

# Second channel: (h5 group name, scope channel, description, file tag)
SECOND_CHIP  = ('through_chip', 2, 'Through-chip CH2', 'through_chip_ch2')
SECOND_CLOCK = ('clock',        2, 'Clock CH2',        'clock_ch2')

def _scalar(x):
    x = np.asarray(x)
    if x.dtype.kind in 'SUO':
        v = x.item()
        return v.decode() if isinstance(v, bytes) else str(v)
    return x.item()


def load_measurement(path):
    """Return dict(t, v, t_chip, v_chip, bit_rate, meta, ch_meta) from npz or h5."""
    if path.lower().endswith('.npz'):
        d = np.load(path)
        meta = {k: _scalar(d[k]) for k in d.files
                if k not in ('t', 'v', 't_chip', 'v_chip', 't_clk', 'v_clk') and d[k].ndim == 0}
        if 't_chip' in d.files:
            t2, v2 = d['t_chip'], d['v_chip']
        elif 't_clk' in d.files:
            # Oldest format (2026-09-23): CH1 signal + CH2 clock, no chip channel
            t2, v2 = d['t_clk'], d['v_clk']
            meta.pop('t_clk', None)
        else:
            raise KeyError(f'{path}: no second channel (t_chip/v_chip or t_clk/v_clk)')
        out = dict(t=d['t'], v=d['v'], t_chip=t2, v_chip=v2,
                   bit_rate=float(d['bit_rate']), meta=meta,
                   ch_meta={'reference': {}, 'through_chip': {}},
                   second=SECOND_CLOCK if 't_clk' in d.files else SECOND_CHIP)
        # Map legacy flat keys to per-channel scope settings (cross-check only)
        out['ch_meta']['reference'] = dict(
            volt_scale_V_per_div=meta.get('volt_scale_ch1_V_per_div'),
            offset_V=meta.get('signal_offset_ch1_V'))
        out['ch_meta']['through_chip'] = dict(
            volt_scale_V_per_div=meta.get('chip_volt_scale_V_per_div'),
            offset_V=meta.get('chip_offset_V'))
        return out

    with h5py.File(path, 'r') as hf:
        meta = {k: _scalar(hf.attrs[k]) for k in hf.attrs}
        wf = hf['waveforms']
        out = dict(second=SECOND_CHIP,
                   t=wf['reference/t_s'][()], v=wf['reference/v_V'][()],
                   t_chip=wf['through_chip/t_s'][()], v_chip=wf['through_chip/v_V'][()],
                   bit_rate=float(meta['bit_rate_Hz']), meta=meta, ch_meta={})
        for name in ('reference', 'through_chip'):
            out['ch_meta'][name] = {k: _scalar(wf[name].attrs[k]) for k in wf[name].attrs}
    # Older h5 files only have the flat root attributes
    legacy = {'reference':   ('volt_scale_ch1_V_per_div', 'signal_offset_ch1_V'),
              'through_chip': ('chip_volt_scale_V_per_div', 'chip_offset_V')}
    for name, (ks, ko) in legacy.items():
        cm = out['ch_meta'][name]
        cm.setdefault('volt_scale_V_per_div', meta.get(ks))
        cm.setdefault('offset_V', meta.get(ko))
    return out


def _num(x):
    try:
        x = float(x)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _bool(x):
    if isinstance(x, str):
        return x.strip().lower() in ('1', 'true', 'on', 'yes')
    return bool(x) if x is not None else False

# =============================================================================
# Reprocessing
# =============================================================================

def reprocess(path):
    print(f'\nProcessing: {path}')
    d = load_measurement(path)
    meta, bit_rate = d['meta'], d['bit_rate']
    bit_period = 1.0 / bit_rate
    hd = _bool(meta.get('hd_mode', False))
    eff_bits = _num(meta.get('hd_resolution_bits'))

    folder = os.path.dirname(os.path.abspath(path))
    base = os.path.basename(path)
    timestamp = base.rsplit('_data.', 1)[0]
    note = FOLDER_NOTES.get(os.path.basename(folder))
    ftag = f'_{note[0]}' if note else ''
    tnote = f' ({note[1]})' if note else ''
    if note:
        print(f'  Folder note: {note[1]}')

    t, dt = eu.regularise_time_axis(d['t'])
    t_chip, _ = eu.regularise_time_axis(d['t_chip'])
    print(f'  Bit rate {bit_rate/1e6:.1f} Mbps, {len(t):,} samples, '
          f'dt = {dt*1e12:.2f} ps ({1/dt/1e9:.3g} GSa/s), HD mode: {hd}'
          + (f' ({eff_bits:.1f} bit)' if hd and eff_bits else ''))

    chans = []
    t_off = None
    for name, ch, desc, t_arr, v_arr in [
            ('reference', 1, 'Reference CH1', t, np.asarray(d['v'], np.float64)),
            (*d['second'][:3], t_chip, np.asarray(d['v_chip'], np.float64))]:
        cm = d['ch_meta'].get(name, {})   # no stored settings for the clock channel
        scale, offset = _num(cm.get('volt_scale_V_per_div')), _num(cm.get('offset_V'))
        vgrid = eu.resolve_voltage_grid(v_arr, volt_scale=scale, offset=offset,
                                        hd=hd, eff_bits=eff_bits,
                                        levels_per_bin=EYE_V_LEVELS_PER_BIN, label=desc)
        eu.check_clipping(v_arr, scale, offset, desc)
        H, t_ed, v_ed, t_off_ch = eu.make_eye(t_arr, v_arr, bit_period, dt, vgrid,
                                              t_offset=t_off,
                                              samples_per_bin=EYE_T_SAMPLES_PER_BIN,
                                              smooth=EYE_SMOOTH)
        if t_off is None:
            t_off = t_off_ch
        eu.describe_bins(desc, vgrid, t_ed, v_ed, dt)
        chans.append(dict(name=name, channel=ch, description=desc, t=t_arr, v=v_arr,
                          H=H, t_ed=t_ed, v_ed=v_ed, vgrid=vgrid, dt=dt,
                          wf_attrs={k: v for k, v in cm.items()
                                    if k not in ('channel', 'description', 'n_samples',
                                                 'v_min_V', 'v_max_V', 'v_mean_V',
                                                 'sample_interval_s')},
                          metrics=eu.compute_eye_metrics(t_arr, v_arr, bit_period, desc)))

    suffix = '_reprocessed_adc'
    for c, tag in zip(chans, ('reference_ch1', d['second'][3])):
        nt, nv = len(c['t_ed']) - 1, len(c['v_ed']) - 1
        eu.plot_eye(c['H'], c['t_ed'], c['v_ed'],
                    f'Persistence Eye — {c["description"]} — {bit_rate/1e6:.0f} Mbps{tnote}',
                    os.path.join(folder, f'{timestamp}_persistence_{tag}{suffix}{ftag}_{nt}t_{nv}v'),
                    dpi=PLOT_DPI)
        eu.print_metrics(c['metrics'], bit_period)

    root = dict(meta)
    root.update(timestamp=timestamp,
                bit_rate_Hz=bit_rate,
                record_length_actual=len(t),
                sample_interval_s=dt,
                eye_v_levels_per_bin=EYE_V_LEVELS_PER_BIN,
                eye_t_samples_per_bin=EYE_T_SAMPLES_PER_BIN,
                eye_smooth_sigma_bins=EYE_SMOOTH,
                eye_binning='adc_truthful',
                reprocessed_from=base,
                waveforms_source=base if not INCLUDE_WAVEFORMS else 'this file')
    if note:
        root['note'] = note[2]
    for k in ('eye_bins_time', 'eye_bins_volt', 'reprocessed_from_npz'):
        root.pop(k, None)   # now stored per channel under eye_diagrams/
    eu.write_eye_h5(os.path.join(folder, f'{timestamp}{suffix}{ftag}_data.h5'),
                    root, chans, t_off, include_waveforms=INCLUDE_WAVEFORMS)


def find_inputs(root):
    files = (glob.glob(os.path.join(root, '**', '*_data.npz'), recursive=True) +
             glob.glob(os.path.join(root, '**', '*_data.h5'),  recursive=True))
    files = [f for f in files if '_reprocessed' not in os.path.basename(f)]
    chosen = {}
    for f in sorted(files):
        key = (os.path.dirname(f), os.path.basename(f).rsplit('_data.', 1)[0])
        if key not in chosen or f.lower().endswith('.h5'):
            chosen[key] = f     # prefer .h5 when both exist
    return sorted(chosen.values())

# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        files = find_inputs(DATA_ROOT)
        if not files:
            print(f'No _data.npz / _data.h5 files found under {DATA_ROOT}')
            sys.exit(1)
        print(f'Found {len(files)} file(s) to reprocess.')
    for f in files:
        reprocess(f)
    print('\nDone.')
