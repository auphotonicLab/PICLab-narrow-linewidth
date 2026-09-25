#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eye diagram measurement.

1. Optionally runs AM characterization to find V_quad and V_pp.
   Set RUN_CHARAC = False and fill in the manual values to skip.
2. Sets SPD3303X DC supply to quadrature bias (V_quad).
3. Configures SDG6022X: PRBS7 on ch1, clock on ch2.
4. Configures RTO1024 with persistence — the scope builds the eye diagram.
5. Saves screenshots and software-rendered eye diagrams for both signal channels.
"""

import sys
import os
import time
import tkinter as tk
from tkinter import simpledialog
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import gaussian_filter
import h5py

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             '..', 'lab-control'))
import Lab_control as pic
from amplitude_modulator_characterization import find_am_operating_points

# =============================================================================
# Settings
# =============================================================================

AFG_IP = '192.168.1.101'
DC_IP  = '192.168.1.31'
OSC_IP = '192.168.1.87'

V_QUAD_MANUAL = 1.95      # [V] DC bias at quadrature
V_PP_MANUAL   = 3.9       # [V] PRBS peak-to-peak amplitude
RUN_CHARAC    = False      # False: use manual values below

DC_CHANNEL    = 1
DC_CURRENT    = 0.01 # [A]
MAX_DC_VOLT   = 7.0        # [V] hard limit

BIT_RATE      = 20e6       # [bps]
SEQUENCE      = 'PRBS7'
AFG_DATA_CH   = 1
AFG_CLOCK_CH  = 2

OSC_SIGNAL_CH    = 1           # CH1 — reference signal
OSC_CHIP_CH      = 2           # CH2 — through-chip signal
OSC_CLOCK_CH     = 3           # CH3 — clock / trigger
OSC_TRIGGER_SRC  = 'CH3'
# 2 bit periods across 10 divisions → TIME_SCALE = 2/(BIT_RATE*10) = 1/(BIT_RATE*5)
TIME_SCALE       = 1 / (BIT_RATE * 5)   # [s/div]
VOLT_SCALE       = 0.2         # [V/div] — CH1 reference signal
SIGNAL_OFFSET    = 0.67         # [V] — CH1 display centre
CHIP_VOLT_SCALE  = 0.002         # [V/div] — CH2 through-chip signal
CHIP_OFFSET      = 0.0         # [V] — CH2 display centre
CLOCK_VOLT_SCALE = 0.5         # [V/div] — CH3 clock
CLOCK_OFFSET     = 0.0         # [V] — CH3 display centre
TRIGGER_LEVEL    = 1.65         # [V] — rising edge of 0–3.3 V clock
OSC_BW_LIMIT     = 200e6       # [Hz] per-channel bandwidth limit; None = full bandwidth

N_UI            = 1_000_000    # unit intervals for oscilloscope persistence display
N_PERIODS       = 10_000       # bit periods to acquire for software eye diagram
RECORD_LENGTH   = 5_000_000    # requested waveform samples (scope caps at hw limit)
EYE_BINS_V      = 1500         # voltage bins (fixed; ~2.6 mV/bin at 0.4 V/div × 10 div)
EYE_SMOOTH      = 0            # Gaussian sigma (bins) to fill gaps between samples; 0 = off
# Time bins are computed after acquisition: actual_samples // N_PERIODS → ~2 samples/bin

PM_SERIAL         = 'P0024530'
SAVE_FOLDER       = r'C:\Users\shd-photonics-inp\Documents\Jeppe_Surrow\Eye_diagram\Eye_diagram_data'
DEFAULT_SAVE_LABEL = 'Eye_diagram_1550nm_ref(ch1)+775nm_chip(ch2)'

# =============================================================================
# Measurement
# =============================================================================

os.makedirs(SAVE_FOLDER, exist_ok=True)

_timestamp = pic.datetimestring()

_root = tk.Tk()
_root.withdraw()
SAVE_LABEL = simpledialog.askstring(
    'Eye Diagram',
    f'Enter a label for this measurement.\n'
    f'Files will be saved in:  {SAVE_FOLDER}\\<label>\\{_timestamp}_*.pdf …',
    initialvalue=DEFAULT_SAVE_LABEL,
    parent=_root) or ''
_root.destroy()

_label_dir   = SAVE_LABEL.replace(' ', '_') if SAVE_LABEL else 'unlabelled'
_run_folder  = os.path.join(SAVE_FOLDER, _label_dir)
os.makedirs(_run_folder, exist_ok=True)

_base_name   = _timestamp
_ref_prefix  = f'{_timestamp}_persistence_reference_ch1'
_chip_prefix = f'{_timestamp}_persistence_through_chip_ch2'

# Step 1 — AM operating point
if RUN_CHARAC:
    _, _, _, _, v_quad, v_pp = find_am_operating_points(
        dc_ip=DC_IP, dc_channel=DC_CHANNEL, pm_serial=PM_SERIAL,
        v_start=0.0, v_stop=MAX_DC_VOLT, max_dc_voltage=MAX_DC_VOLT)
else:
    v_quad, v_pp = V_QUAD_MANUAL, V_PP_MANUAL

if v_quad + v_pp / 2 > MAX_DC_VOLT:
    raise ValueError(
        f'Total max voltage {v_quad + v_pp/2:.2f} V would exceed '
        f'MAX_DC_VOLT = {MAX_DC_VOLT} V. Adjust V_quad or V_pp.')

print(f'V_quad = {v_quad:.3f} V,  V_pp = {v_pp:.3f} V')

_h5_path = os.path.join(_run_folder, f'{_timestamp}_data.h5')

# Step 2 — Connect
dc  = pic.DC_Siglent(IP_address=DC_IP, channel=DC_CHANNEL,
                     voltage=0.0, current=DC_CURRENT, max_voltage=MAX_DC_VOLT)
afg = pic.AFG_Siglent(IP_address=AFG_IP, frequency=int(BIT_RATE))
osc = pic.RTO1024(IP_address=OSC_IP)

try:
    # Step 3 — DC bias
    dc.outputStatus(channel=DC_CHANNEL, status='OFF')
    dc.setParameters(channel=DC_CHANNEL, voltage=v_quad, current=DC_CURRENT)
    time.sleep(0.2)
    dc.outputStatus(channel=DC_CHANNEL, status='ON')
    time.sleep(0.5)
    print(f'DC CH{DC_CHANNEL} ON: {v_quad:.3f} V, {DC_CURRENT:.3f} A')

    # Step 4 — PRBS + clock
    afg.output_status(channel=AFG_DATA_CH,  status='OFF')
    afg.output_status(channel=AFG_CLOCK_CH, status='OFF')
    afg.setPRBS(channel=AFG_DATA_CH, bit_rate=BIT_RATE,
                sequence=SEQUENCE, amplitude=v_pp, load=50)
    afg.setClock(channel=AFG_CLOCK_CH, bit_rate=BIT_RATE)
    afg.output_status(channel=AFG_CLOCK_CH, status='ON')
    time.sleep(0.2)
    afg.output_status(channel=AFG_DATA_CH,  status='ON')
    time.sleep(0.5)

    # Step 5 — Scope eye diagram
    osc.setupEyeDiagram(signal_channel=OSC_SIGNAL_CH,
                        trigger_source=OSC_TRIGGER_SRC,
                        time_scale=TIME_SCALE,
                        volt_scale=VOLT_SCALE,
                        signal_offset=SIGNAL_OFFSET,
                        clock_offset=CLOCK_OFFSET,
                        trigger_level=TRIGGER_LEVEL,
                        clock_volt_scale=CLOCK_VOLT_SCALE)
    osc.instr.write(f'CHANnel{OSC_CHIP_CH}:STATe ON')
    osc.instr.write(f'CHANnel{OSC_CHIP_CH}:SCALe {CHIP_VOLT_SCALE}')
    osc.instr.write(f'CHANnel{OSC_CHIP_CH}:OFFSet {CHIP_OFFSET}')

    # Bandwidth limit
    if OSC_BW_LIMIT:
        _bw_str = f'{OSC_BW_LIMIT:.0f}'
        for _ch in [OSC_SIGNAL_CH, OSC_CHIP_CH, OSC_CLOCK_CH]:
            osc.instr.write(f'CHANnel{_ch}:BANDwidth {_bw_str}')
        print(f'BW limit set to {OSC_BW_LIMIT/1e6:.0f} MHz on CH'
              f'{OSC_SIGNAL_CH}, CH{OSC_CHIP_CH}, CH{OSC_CLOCK_CH}.')

    # Accumulate persistence
    t_acq = max(N_UI / BIT_RATE, 10.0)
    print(f'Accumulating {N_UI:,} UIs at {BIT_RATE/1e9:.3g} Gbps '
          f'— waiting {t_acq:.1f} s …')
    for remaining in range(int(t_acq), 0, -1):
        print(f'  {remaining} s remaining …', end='\r')
        time.sleep(1)
    print()

    # Screenshots
    osc.saveScreenshotToPC(local_path=os.path.join(_run_folder, f'{_base_name}_scope_all.png'))
    print(f'Scope screenshot (all) saved.')

    osc.instr.write(f'CHANnel{OSC_CHIP_CH}:STATe OFF')
    osc.instr.write(f'CHANnel{OSC_CLOCK_CH}:STATe OFF')
    time.sleep(0.3)
    osc.saveScreenshotToPC(local_path=os.path.join(_run_folder, f'{_base_name}_scope_reference_ch1.png'))
    print('Scope screenshot (reference CH1) saved.')

    osc.instr.write(f'CHANnel{OSC_SIGNAL_CH}:STATe OFF')
    osc.instr.write(f'CHANnel{OSC_CHIP_CH}:STATe ON')
    time.sleep(0.3)
    osc.saveScreenshotToPC(local_path=os.path.join(_run_folder, f'{_base_name}_scope_through_chip_ch2.png'))
    print('Scope screenshot (through-chip CH2) saved.')

    osc.instr.write(f'CHANnel{OSC_SIGNAL_CH}:STATe ON')
    osc.instr.write(f'CHANnel{OSC_CLOCK_CH}:STATe ON')
    time.sleep(0.1)

    # Acquire long waveform for both signal channels
    osc.stop()
    print('Acquiring long waveform …')
    t, v, extra = osc.acquireLongWaveform(channel=OSC_SIGNAL_CH,
                                          n_periods=N_PERIODS,
                                          bit_rate=BIT_RATE,
                                          volt_scale=VOLT_SCALE,
                                          record_length=RECORD_LENGTH,
                                          extra_channels=[OSC_CHIP_CH])
    t_chip, v_chip = extra[OSC_CHIP_CH]
    bit_period = 1.0 / BIT_RATE
    _eye_bins_t = len(v) // N_PERIODS   # ~2 samples/bin, adapts to any bit rate/sample rate
    EYE_BINS    = (_eye_bins_t, EYE_BINS_V)
    print(f'Eye bins: {EYE_BINS[0]} time ({2/BIT_RATE*1e9/EYE_BINS[0]*1e3:.2f} ps/bin), '
          f'{EYE_BINS[1]} voltage')
    print(f'CH{OSC_SIGNAL_CH} (ref):  {len(v):,} pts, '
          f'V=[{v.min():.3f}, {v.max():.3f}] V, mean={v.mean():.3f} V')
    print(f'CH{OSC_CHIP_CH} (chip): {len(v_chip):,} pts, '
          f'V=[{v_chip.min():.3f}, {v_chip.max():.3f}] V, mean={v_chip.mean():.3f} V')

    # =========================================================================
    # Eye diagram helpers
    # =========================================================================

    def _make_eye(t_arr, v_arr, t_offset=None):
        """Fold waveform into a 2-UI persistence histogram, centered on crossings.

        Returns (H, t_edges_ns, v_edges_V, t_offset_s).
        Pass t_offset to reuse the same phase alignment across channels.
        """
        if t_offset is None:
            threshold = 0.5 * (v_arr.max() + v_arr.min())
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
        H, t_ed, v_ed = np.histogram2d(t_fold * 1e9, v_arr, bins=EYE_BINS)
        if EYE_SMOOTH > 0:
            H = gaussian_filter(H, sigma=EYE_SMOOTH)
        return H.T, t_ed, v_ed, t_offset

    def _black_axes(fig, ax, title):
        ax.set_facecolor('black')
        fig.patch.set_facecolor('black')
        ax.set_xlabel('Time [ns]', color='white')
        ax.set_ylabel('Voltage [V]', color='white')
        ax.set_title(title, color='white')
        ax.tick_params(colors='white')
        for spine in ax.spines.values():
            spine.set_edgecolor('white')

    def _plot_eye(H, t_ed, v_ed, title, prefix,
                  cmap='hot',
                  H_overlay=None, t_ed_overlay=None, v_ed_overlay=None,
                  cmap_overlay='winter', alpha_overlay=0.6):
        """Render a persistence eye diagram and save as PDF + SVG.

        Supply H_overlay / t_ed_overlay / v_ed_overlay to overlay a second
        channel (e.g. clock or comparison signal) in a different colormap.
        """
        fig, ax = plt.subplots(figsize=(8, 5))
        _black_axes(fig, ax, title)
        ax.imshow(np.ma.masked_where(H == 0, np.log1p(H)),
                  origin='lower', aspect='auto',
                  extent=[t_ed[0], t_ed[-1], v_ed[0], v_ed[-1]],
                  cmap=cmap, interpolation='nearest')
        ylo, yhi = v_ed[0], v_ed[-1]
        if H_overlay is not None:
            ax.imshow(np.ma.masked_where(H_overlay == 0, np.log1p(H_overlay)),
                      origin='lower', aspect='auto',
                      extent=[t_ed_overlay[0], t_ed_overlay[-1],
                              v_ed_overlay[0], v_ed_overlay[-1]],
                      cmap=cmap_overlay, interpolation='nearest',
                      alpha=alpha_overlay)
            ylo = min(ylo, v_ed_overlay[0])
            yhi = max(yhi, v_ed_overlay[-1])
        pad = 0.02 * (yhi - ylo)
        ax.set_ylim(ylo - pad, yhi + pad)
        fig.tight_layout()
        for ext in ('pdf', 'svg'):
            p = os.path.join(_run_folder, f'{prefix}.{ext}')
            fig.savefig(p, bbox_inches='tight', facecolor='black')
            print(f'Persistence eye saved: {p}')
        plt.show()
        return fig, ax

    def _eye(t_arr, v_arr, title, prefix, t_offset=None, cmap='hot'):
        """Build histogram, save .npz, render and save PDF/SVG for one eye diagram.

        Returns (H, t_edges, v_edges, t_offset) so the offset can be reused
        for a time-aligned overlay on another channel.
        """
        H, t_ed, v_ed, t_off = _make_eye(t_arr, v_arr, t_offset=t_offset)
        _plot_eye(H, t_ed, v_ed, title, prefix, cmap=cmap)
        return H, t_ed, v_ed, t_off

    def _compute_eye_metrics(t_arr, v_arr, label):
        """Compute key eye diagram metrics from a raw waveform.

        Returns a dict with rail voltages, extinction ratio, and jitter.
        ER_dB_optical  uses 10·log10 (V_high/V_low) — correct when voltage is
                       proportional to optical power (photodetector output).
        ER_dB_elec     uses 20·log10 — correct for purely electrical amplitude.
        Jitter is extracted from interpolated rising-edge crossing times folded
        modulo one bit period.
        """
        threshold = 0.5 * (v_arr.max() + v_arr.min())
        margin    = 0.25 * (v_arr.max() - v_arr.min())

        upper = v_arr[v_arr > threshold + margin]
        lower = v_arr[v_arr < threshold - margin]

        v_hi      = upper.mean() if len(upper) else np.nan
        v_hi_std  = upper.std()  if len(upper) else np.nan
        v_lo      = lower.mean() if len(lower) else np.nan
        v_lo_std  = lower.std()  if len(lower) else np.nan

        eye_open = v_hi - v_lo
        er_opt   = 10 * np.log10(v_hi / v_lo) if v_lo > 0 else np.nan
        er_elec  = 20 * np.log10(v_hi / v_lo) if v_lo > 0 else np.nan

        # Interpolated rising-edge crossing times → jitter
        above      = (v_arr > threshold).astype(int)
        rise_idx   = np.where(np.diff(above) == 1)[0]
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

    def _print_metrics(m):
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

    # Eye metrics
    m_ref  = _compute_eye_metrics(t,      v,      f'CH{OSC_SIGNAL_CH} reference')
    m_chip = _compute_eye_metrics(t_chip, v_chip, f'CH{OSC_CHIP_CH} through-chip')
    _print_metrics(m_ref)
    _print_metrics(m_chip)

    # Raw waveform plot
    fig_raw, ax_raw = plt.subplots(figsize=(10, 4))
    ax_raw.plot((t - t[0]) * 1e6, v, lw=0.3, color='C0',
                label=f'CH{OSC_SIGNAL_CH} reference')
    ax_raw.plot((t_chip - t_chip[0]) * 1e6, v_chip, lw=0.3, color='C1',
                label=f'CH{OSC_CHIP_CH} through-chip')
    ax_raw.set_xlabel('Time [µs]')
    ax_raw.set_ylabel('Voltage [V]')
    ax_raw.set_title(f'Raw waveform — {BIT_RATE/1e6:.0f} Mbps {SEQUENCE}')
    ax_raw.legend(loc='upper right')
    ax_raw.grid(True, alpha=0.3)
    fig_raw.tight_layout()
    for ext in ('pdf', 'svg'):
        fig_raw.savefig(os.path.join(_run_folder, f'{_base_name}_raw.{ext}'),
                        bbox_inches='tight')
    print('Raw waveform saved.')
    plt.show()

    # =========================================================================
    # Eye diagram plots
    # =========================================================================

    H_ref, t_ed_ref, v_ed_ref, _t_off = _eye(
        t, v,
        f'Persistence Eye — Reference CH{OSC_SIGNAL_CH} — {BIT_RATE/1e6:.0f} Mbps {SEQUENCE}',
        _ref_prefix)

    H_chip, t_ed_chip, v_ed_chip, _ = _eye(
        t_chip, v_chip,
        f'Persistence Eye — Through-chip CH{OSC_CHIP_CH} — {BIT_RATE/1e6:.0f} Mbps {SEQUENCE}',
        _chip_prefix, t_offset=_t_off)

    # =========================================================================
    # Save everything to a single HDF5 file
    # =========================================================================
    with h5py.File(_h5_path, 'w') as hf:

        # Root attributes — all measurement settings
        hf.attrs['timestamp']                  = _timestamp
        hf.attrs['label']                      = SAVE_LABEL
        hf.attrs['bit_rate_Hz']                = BIT_RATE
        hf.attrs['sequence']                   = SEQUENCE
        hf.attrs['v_quad_V']                   = v_quad
        hf.attrs['v_pp_V']                     = v_pp
        hf.attrs['dc_channel']                 = DC_CHANNEL
        hf.attrs['dc_current_A']               = DC_CURRENT
        hf.attrs['osc_signal_ch']              = OSC_SIGNAL_CH
        hf.attrs['osc_chip_ch']                = OSC_CHIP_CH
        hf.attrs['osc_clock_ch']               = OSC_CLOCK_CH
        hf.attrs['trigger_source']             = OSC_TRIGGER_SRC
        hf.attrs['trigger_level_V']            = TRIGGER_LEVEL
        hf.attrs['time_scale_s_per_div']       = TIME_SCALE
        hf.attrs['volt_scale_ch1_V_per_div']   = VOLT_SCALE
        hf.attrs['signal_offset_ch1_V']        = SIGNAL_OFFSET
        hf.attrs['chip_volt_scale_V_per_div']  = CHIP_VOLT_SCALE
        hf.attrs['chip_offset_V']              = CHIP_OFFSET
        hf.attrs['clock_volt_scale_V_per_div'] = CLOCK_VOLT_SCALE
        hf.attrs['clock_offset_V']             = CLOCK_OFFSET
        hf.attrs['bw_limit_Hz']                = OSC_BW_LIMIT if OSC_BW_LIMIT else -1
        hf.attrs['coupling']                   = 'DC'
        hf.attrs['n_ui_persistence']           = N_UI
        hf.attrs['record_length_requested']    = RECORD_LENGTH
        hf.attrs['record_length_actual']       = len(v)
        hf.attrs['eye_bins_time']              = EYE_BINS[0]
        hf.attrs['eye_bins_volt']              = EYE_BINS[1]
        hf.attrs['eye_smooth_sigma_bins']      = EYE_SMOOTH

        # Waveforms
        wg = hf.create_group('waveforms')
        for grp_name, t_arr, v_arr, ch, desc in [
            ('reference',   t,      v,      OSC_SIGNAL_CH, 'Reference signal'),
            ('through_chip', t_chip, v_chip, OSC_CHIP_CH,  'Through-chip signal'),
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
            ('reference',    H_ref,  t_ed_ref,  v_ed_ref,  OSC_SIGNAL_CH, 'Reference CH1'),
            ('through_chip', H_chip, t_ed_chip, v_ed_chip, OSC_CHIP_CH,   'Through-chip CH2'),
        ]:
            g = eg.create_group(grp_name)
            g.create_dataset('H', data=H.astype(np.float32),
                             compression='gzip', compression_opts=4)
            g.create_dataset('t_edges_ns', data=t_ed)
            g.create_dataset('v_edges_V',  data=v_ed)
            g.attrs['channel']          = ch
            g.attrs['description']      = desc
            g.attrs['t_offset_s']       = float(_t_off)
            g.attrs['shared_t_offset']  = (grp_name == 'through_chip')
            g.attrs['H_shape']          = f'{H.shape[0]} (volt) × {H.shape[1]} (time)'

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

        # Scope screenshots (embedded as image arrays)
        sg = hf.create_group('screenshots')
        for tag, png_path in [
            ('all_channels',     os.path.join(_run_folder, f'{_base_name}_scope_all.png')),
            ('reference_ch1',    os.path.join(_run_folder, f'{_base_name}_scope_reference_ch1.png')),
            ('through_chip_ch2', os.path.join(_run_folder, f'{_base_name}_scope_through_chip_ch2.png')),
        ]:
            if os.path.exists(png_path):
                img = plt.imread(png_path)
                ds = sg.create_dataset(tag, data=img,
                                       compression='gzip', compression_opts=4)
                ds.attrs['filename'] = os.path.basename(png_path)
                ds.attrs['CLASS']    = 'IMAGE'

    print(f'HDF5 saved: {_h5_path}')

finally:
    afg.output_status(channel=AFG_DATA_CH,  status='OFF')
    afg.output_status(channel=AFG_CLOCK_CH, status='OFF')
    dc.setParameters(channel=DC_CHANNEL, voltage=0.0, current=0.0)
    dc.outputStatus(channel=DC_CHANNEL, status='OFF')
    afg.CloseConnection()
    dc.closeConnection()
    osc.closeConnection()
    print('Outputs off, connections closed.')
