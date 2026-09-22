#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eye diagram measurement.

1. Optionally runs AM characterization to find V_quad and V_pp.
   Set RUN_CHARAC = False and fill in the manual values to skip.
2. Sets SPD3303X DC supply to quadrature bias (V_quad).
3. Configures SDG6022X: PRBS7 on ch1, clock on ch2.
4. Configures RTO1024 with persistence — the scope builds the eye diagram.
5. Saves a screenshot from the scope.
"""

import sys
import os
import time
import tkinter as tk
from tkinter import simpledialog
import numpy as np
import matplotlib.pyplot as plt

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
V_PP_MANUAL   = 3.9      # [V] PRBS peak-to-peak amplitude
RUN_CHARAC    = False     # False: use manual values below

DC_CHANNEL    = 1
MAX_DC_VOLT   = 7.0      # [V] hard limit — DC_Siglent will raise an error if exceeded

BIT_RATE      = 20e6       # [bps]
SEQUENCE      = 'PRBS7'
AFG_DATA_CH   = 1
AFG_CLOCK_CH  = 2

OSC_SIGNAL_CH   = 1
OSC_TRIGGER_SRC = 'CH2'       # clock from SDG6022X
# 2 bit periods across 10 divisions → TIME_SCALE = 2/(BIT_RATE*10) = 1/(BIT_RATE*5)
TIME_SCALE      = 1 / (BIT_RATE * 5)   # [s/div] — exactly 2 bit periods on screen
VOLT_SCALE      = 0.4          # [V/div] — photodetector output
SIGNAL_OFFSET   = 1.65         # [V] — centre CH1 display on detector operating point
CLOCK_VOLT_SCALE = 0.5         # [V/div] — for clock on CH2
CLOCK_OFFSET    = 0.0          # [V] — CH2 centred at 0 V
TRIGGER_LEVEL   = 2.0          # [V] — rising edge of 0–3.3 V clock

N_UI            = 1_000_000  # unit intervals to accumulate (compliance standard)

PM_SERIAL   = 'P0024530'
SAVE_FOLDER = r'C:\Users\shd-photonics-inp\Documents\Jeppe_Surrow\Eye_diagram\Eye_diagram_data' #r'C:\Users\Group Login\Documents\Measurements\Eye_diagram'

# =============================================================================
# Measurement
# =============================================================================

os.makedirs(SAVE_FOLDER, exist_ok=True)

# Generate timestamp now so the user can see it in the save-name prompt
_timestamp = pic.datetimestring()

_root = tk.Tk()
_root.withdraw()
SAVE_LABEL = simpledialog.askstring(
    'Eye Diagram',
    f'Enter a label for this measurement.\n'
    f'Files will be saved as:  <label>_{_timestamp}_*.pdf/svg/npz/png\n'
    f'(Leave blank to use only the timestamp as prefix.)',
    parent=_root) or ''
_root.destroy()

# Build the base filename: label first, then datetime
if SAVE_LABEL:
    _base_name = SAVE_LABEL.replace(' ', '_') + '_' + _timestamp
else:
    _base_name = _timestamp

# Step 1 — AM operating point
if RUN_CHARAC:
    _, _, _, _, v_quad, v_pp = find_am_operating_points(
        dc_ip=DC_IP, dc_channel=DC_CHANNEL, pm_serial=PM_SERIAL,
        v_start=0.0, v_stop=MAX_DC_VOLT, max_dc_voltage=MAX_DC_VOLT)
else:
    v_quad, v_pp = V_QUAD_MANUAL, V_PP_MANUAL

# Sanity check before touching instruments
if v_quad + v_pp / 2 > MAX_DC_VOLT:
    raise ValueError(
        f'Total max voltage {v_quad + v_pp/2:.2f} V would exceed '
        f'MAX_DC_VOLT = {MAX_DC_VOLT} V. Adjust V_quad or V_pp.')

print(f'V_quad = {v_quad:.3f} V,  V_pp = {v_pp:.3f} V')

# Step 2 — Connect
dc  = pic.DC_Siglent(IP_address=DC_IP, channel=DC_CHANNEL,
                     voltage=0.0, current=0.02, max_voltage=MAX_DC_VOLT)
afg = pic.AFG_Siglent(IP_address=AFG_IP, frequency=int(BIT_RATE))
osc = pic.RTO1024(IP_address=OSC_IP)

try:
    # Step 3 — DC bias
    dc.outputStatus(channel=DC_CHANNEL, status='ON')
    dc.setParameters(channel=DC_CHANNEL, voltage=v_quad, current=0.02)
    time.sleep(0.5)

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

    # Wait long enough to accumulate N_UI unit intervals.
    # Physical minimum = N_UI / BIT_RATE, but allow at least 10 s so
    # the persistence heat map fills in visually.
    t_acq = max(N_UI / BIT_RATE, 10.0)
    print(f'Accumulating {N_UI:,} UIs at {BIT_RATE/1e9:.3g} Gbps '
          f'— waiting {t_acq:.1f} s …')
    for remaining in range(int(t_acq), 0, -1):
        print(f'  {remaining} s remaining …', end='\r')
        time.sleep(1)
    print()

    # Screenshot FIRST — while persistence trace is still on screen
    scope_path = os.path.join(SAVE_FOLDER, f'{_base_name}_scope.png')
    print('Saving scope screenshot (persistence still active) …')
    osc.saveScreenshotToPC(local_path=scope_path)
    print(f'Scope screenshot saved: {scope_path}')

    # Stop scope, then acquire long waveform for both raw trace and eye diagram
    osc.stop()
    print('Acquiring long waveform …')
    t, v = osc.acquireLongWaveform(channel=OSC_SIGNAL_CH,
                                   n_periods=10000,
                                   bit_rate=BIT_RATE,
                                   volt_scale=VOLT_SCALE)
    bit_period = 1.0 / BIT_RATE

    # Save raw data
    data_path = os.path.join(SAVE_FOLDER, f'{_base_name}_data.npz')
    np.savez(data_path, t=t, v=v, bit_rate=BIT_RATE)
    print(f'Raw data saved: {data_path}')

    # Raw waveform plot
    fig_raw, ax_raw = plt.subplots(figsize=(10, 4))
    ax_raw.plot((t - t[0]) * 1e6, v, lw=0.3, color='C0')
    ax_raw.set_xlabel('Time [µs]')
    ax_raw.set_ylabel('Voltage [V]')
    ax_raw.set_title(f'Raw waveform — {BIT_RATE/1e6:.0f} Mbps {SEQUENCE}')
    ax_raw.grid(True, alpha=0.3)
    fig_raw.tight_layout()
    for ext in ('pdf', 'svg'):
        p = os.path.join(SAVE_FOLDER, f'{_base_name}_raw.{ext}')
        fig_raw.savefig(p, bbox_inches='tight')
        print(f'Raw waveform saved: {p}')
    plt.show()

    # Eye diagram — fold waveform onto 2 UI window
    t_folded = (t - t[0]) % (2 * bit_period)

    # 2D histogram (persistence heatmap)
    H, t_edges, v_edges = np.histogram2d(t_folded * 1e9, v, bins=[500, 300])
    H = H.T  # rows = voltage, columns = time
    np.savez(os.path.join(SAVE_FOLDER, f'{_base_name}_persistence.npz'),
             H=H, t_edges=t_edges, v_edges=v_edges, bit_rate=BIT_RATE)
    print(f'Persistence data saved: {_base_name}_persistence.npz')

    fig_pers, ax_pers = plt.subplots(figsize=(8, 5))
    ax_pers.set_facecolor('black')
    fig_pers.patch.set_facecolor('black')
    ax_pers.imshow(np.log1p(H), origin='lower', aspect='auto',
                   extent=[t_edges[0], t_edges[-1], v_edges[0], v_edges[-1]],
                   cmap='hot', interpolation='nearest')
    ax_pers.set_xlabel('Time [ns]', color='white')
    ax_pers.set_ylabel('Voltage [V]', color='white')
    ax_pers.set_title(f'Persistence Eye — {BIT_RATE/1e6:.0f} Mbps {SEQUENCE}', color='white')
    ax_pers.tick_params(colors='white')
    for spine in ax_pers.spines.values():
        spine.set_edgecolor('white')
    fig_pers.tight_layout()
    for ext in ('pdf', 'svg'):
        p = os.path.join(SAVE_FOLDER, f'{_base_name}_persistence.{ext}')
        fig_pers.savefig(p, bbox_inches='tight', facecolor='black')
        print(f'Persistence eye saved: {p}')
    plt.show()

finally:
    afg.output_status(channel=AFG_DATA_CH,  status='OFF')
    afg.output_status(channel=AFG_CLOCK_CH, status='OFF')
    dc.setParameters(channel=DC_CHANNEL, voltage=0.0, current=0.0)
    dc.outputStatus(channel=DC_CHANNEL, status='OFF')
    afg.CloseConnection()
    dc.closeConnection()
    osc.closeConnection()
    print('Outputs off, connections closed.')
