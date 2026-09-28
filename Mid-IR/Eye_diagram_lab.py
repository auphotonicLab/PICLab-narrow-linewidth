#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eye diagram measurement.

1. Optionally runs AM characterization to find V_quad and V_pp.
   Set RUN_CHARAC = False and fill in the manual values to skip.
2. Sets SPD3303X DC supply to quadrature bias (V_quad).
3. Configures SDG6022X: PRBS7 on ch1, clock on ch2.
4. Asks the RTO1024 whether High Definition mode (option K17) is installed
   and, if so, enables it (up to 16-bit vertical resolution).
5. Configures RTO1024 with persistence — the scope builds the eye diagram.
6. Acquires a long real-time record at the maximum real sample rate and
   saves screenshots and software-rendered eye diagrams for both signal
   channels, binned at one ADC level × one sample interval
   (see eye_diagram_utils.py).
"""

import sys
import os
import time
import tkinter as tk
from tkinter import simpledialog
import numpy as np
import matplotlib.pyplot as plt

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.append(os.path.join(_here, '..', 'lab-control'))
import Lab_control as pic
from amplitude_modulator_characterization import find_am_operating_points
import eye_diagram_utils as eu

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

USE_HD          = 'auto'       # 'auto': use High Definition if option K17 is installed; False: never
HD_BANDWIDTH    = OSC_BW_LIMIT or 1e9  # [Hz] HD filter bandwidth (lower → more bits; max 1 GHz)

N_UI            = 1_000_000    # unit intervals for oscilloscope persistence display
N_PERIODS       = 10_000       # bit periods to acquire for software eye diagram
RECORD_LENGTH   = None         # None = max real-time rate (10 GSa/s, 5 GSa/s in HD) over N_PERIODS

# Eye binning is ADC-truthful (see eye_diagram_utils.py):
#   voltage bin = one ADC level  (8 bit: V/div·10/253, HD: from HDEFinition:RESolution?)
#   time bin    = one sample interval (100 ps at 10 GSa/s → 1000 bins over 2 UI at 20 Mbps)
EYE_V_LEVELS_PER_BIN  = 1      # integer; >1 merges ADC levels (coarser, still alias-free)
EYE_T_SAMPLES_PER_BIN = 1      # integer; >1 merges sample intervals
EYE_SMOOTH      = 0            # Gaussian sigma (bins); 0 = off
PLOT_DPI        = 600          # only matters for raster output; PDF/SVG embed the histogram at native size

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

    # Step 5 — Scope resolution: High Definition if available
    hd_on, hd_bits = osc.setHighDefinition(
        state=(USE_HD == 'auto' or USE_HD is True), bandwidth=HD_BANDWIDTH)

    # Step 6 — Scope eye diagram
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

    # Bandwidth limit (in HD mode the HD filter sets the bandwidth instead)
    if OSC_BW_LIMIT and not hd_on:
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
    acq = osc.last_acquisition
    bit_period = 1.0 / BIT_RATE
    dt = acq['sample_interval_s']
    print(f'Sample interval {dt*1e12:.1f} ps ({acq["sample_rate_Sa_s"]/1e9:.3g} GSa/s), '
          f'HD mode: {acq["hd_mode"]}'
          + (f' ({acq["hd_resolution_bits"]} bit)' if acq['hd_mode'] else ' (8 bit)'))
    print(f'CH{OSC_SIGNAL_CH} (ref):  {len(v):,} pts, '
          f'V=[{v.min():.3f}, {v.max():.3f}] V, mean={v.mean():.3f} V')
    print(f'CH{OSC_CHIP_CH} (chip): {len(v_chip):,} pts, '
          f'V=[{v_chip.min():.3f}, {v_chip.max():.3f}] V, mean={v_chip.mean():.3f} V')

    # Eye metrics
    m_ref  = eu.compute_eye_metrics(t,      v,      bit_period, f'CH{OSC_SIGNAL_CH} reference')
    m_chip = eu.compute_eye_metrics(t_chip, v_chip, bit_period, f'CH{OSC_CHIP_CH} through-chip')
    eu.print_metrics(m_ref,  bit_period)
    eu.print_metrics(m_chip, bit_period)

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
    # Eye diagrams — one bin per ADC level × one bin per sample interval
    # =========================================================================
    chans = []
    _t_off = None
    for name, ch, desc, t_arr, v_arr, prefix in [
            ('reference',    OSC_SIGNAL_CH, 'Reference signal',    t,      v,      _ref_prefix),
            ('through_chip', OSC_CHIP_CH,   'Through-chip signal', t_chip, v_chip, _chip_prefix)]:
        vi = acq['vertical'][ch]
        label = f'CH{ch} {name.replace("_", "-")}'
        vgrid = eu.resolve_voltage_grid(
            v_arr, volt_scale=vi['volt_scale_V_per_div'], offset=vi['offset_V'],
            hd=vi['hd_mode'], eff_bits=vi['adc_bits_effective'],
            levels_per_bin=EYE_V_LEVELS_PER_BIN, label=label)
        eu.check_clipping(v_arr, vi['volt_scale_V_per_div'], vi['offset_V'], label)
        H, t_ed, v_ed, t_off_ch = eu.make_eye(
            t_arr, v_arr, bit_period, dt, vgrid, t_offset=_t_off,
            samples_per_bin=EYE_T_SAMPLES_PER_BIN, smooth=EYE_SMOOTH)
        if _t_off is None:
            _t_off = t_off_ch            # reuse phase so both eyes are time-aligned
        eu.describe_bins(label, vgrid, t_ed, v_ed, dt)
        eu.plot_eye(H, t_ed, v_ed,
                    f'Persistence Eye — {label} — {BIT_RATE/1e6:.0f} Mbps {SEQUENCE}',
                    os.path.join(_run_folder, prefix), dpi=PLOT_DPI, show=True)
        chans.append(dict(name=name, channel=ch, description=desc,
                          t=t_arr, v=v_arr, H=H, t_ed=t_ed, v_ed=v_ed,
                          vgrid=vgrid, dt=dt, wf_attrs=vi,
                          metrics=m_ref if name == 'reference' else m_chip))

    # =========================================================================
    # Save everything to a single HDF5 file
    # =========================================================================
    root_attrs = dict(
        timestamp=_timestamp, label=SAVE_LABEL,
        bit_rate_Hz=BIT_RATE, sequence=SEQUENCE,
        v_quad_V=v_quad, v_pp_V=v_pp,
        dc_channel=DC_CHANNEL, dc_current_A=DC_CURRENT,
        osc_signal_ch=OSC_SIGNAL_CH, osc_chip_ch=OSC_CHIP_CH, osc_clock_ch=OSC_CLOCK_CH,
        trigger_source=OSC_TRIGGER_SRC, trigger_level_V=TRIGGER_LEVEL,
        time_scale_s_per_div=TIME_SCALE,
        volt_scale_ch1_V_per_div=acq['vertical'][OSC_SIGNAL_CH]['volt_scale_V_per_div'],
        signal_offset_ch1_V=acq['vertical'][OSC_SIGNAL_CH]['offset_V'],
        chip_volt_scale_V_per_div=acq['vertical'][OSC_CHIP_CH]['volt_scale_V_per_div'],
        chip_offset_V=acq['vertical'][OSC_CHIP_CH]['offset_V'],
        clock_volt_scale_V_per_div=CLOCK_VOLT_SCALE, clock_offset_V=CLOCK_OFFSET,
        bw_limit_Hz=OSC_BW_LIMIT if (OSC_BW_LIMIT and not acq['hd_mode']) else -1,
        coupling='DC',
        n_ui_persistence=N_UI,
        record_length_requested=RECORD_LENGTH if RECORD_LENGTH else -1,
        record_length_actual=len(v),
        sample_interval_s=dt,
        sample_rate_Sa_s=acq['sample_rate_Sa_s'],
        acquire_mode=acq['acquire_mode'],
        hd_mode=acq['hd_mode'],
        hd_resolution_bits=acq['hd_resolution_bits'],
        hd_bandwidth_Hz=acq['hd_bandwidth_Hz'] if acq['hd_bandwidth_Hz'] else -1,
        eye_binning='adc_truthful',
        eye_v_levels_per_bin=EYE_V_LEVELS_PER_BIN,
        eye_t_samples_per_bin=EYE_T_SAMPLES_PER_BIN,
        eye_smooth_sigma_bins=EYE_SMOOTH)

    eu.write_eye_h5(_h5_path, root_attrs, chans, _t_off, screenshots=[
        ('all_channels',     os.path.join(_run_folder, f'{_base_name}_scope_all.png')),
        ('reference_ch1',    os.path.join(_run_folder, f'{_base_name}_scope_reference_ch1.png')),
        ('through_chip_ch2', os.path.join(_run_folder, f'{_base_name}_scope_through_chip_ch2.png')),
    ])

finally:
    afg.output_status(channel=AFG_DATA_CH,  status='OFF')
    afg.output_status(channel=AFG_CLOCK_CH, status='OFF')
    dc.setParameters(channel=DC_CHANNEL, voltage=0.0, current=0.0)
    dc.outputStatus(channel=DC_CHANNEL, status='OFF')
    afg.CloseConnection()
    dc.closeConnection()
    osc.closeConnection()
    print('Outputs off, connections closed.')
