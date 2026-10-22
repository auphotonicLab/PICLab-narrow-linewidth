#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frequency-noise / RIN measurement with the HighFinesse LWA-1k (1550 nm), captured and averaged from Python
==========================================================================================================

    lwa_measurement.py   <- this file: settings (edit, then run it)
    lwa_utils.py         <- connection to the HighFinesse GUI, capture, averaging, analysis, saving

How to use
    1. Start LWA_Control.exe, wait until Analyzer and Digitizer are connected, and set the GUI as you want it
       (Noise mode FN/RIN, Cutoff, Power mode, Range, Res, Fitfunction ...). Keep the GUI's Averaging = Off.
       The capture may run continuously (fastest) or be idle (each capture is then started as a single run).
       Do not click in the GUI while the script runs.
    2. Fill in SAVE_FOLDER and PLAN below and run from the VS Code terminal:  python lwa_measurement.py
       A pop-up asks for a label; everything is saved in  SAVE_FOLDER/<label>/ :
           <timestamp>_<name>.h5                 EVERYTHING, gzip-compressed (open it with the VS Code HDF5 viewer):
                                                 noise/x, noise/mean, noise/std, noise/captures (n x N), noise/binned/
                                                 (BINS_PER_DECADE log bins, linear means); lineshape/..., time/...;
                                                 gui_results/<slot> and capture_info/ per capture; Python linewidths,
                                                 settings, timing and state as attributes. FN in Hz^2/Hz, RIN in dB/Hz.
           <timestamp>_<name>_PSD.txt / _RIN.txt the same in the GUI's export format (readable by lwa_lib.LWA)
           <timestamp>_<name>.png / .pdf         plot
           summary.csv                           one row per measurement
           <timestamp>_lwa_log.txt               console log

Averaging
    'n_average' captures are averaged here in LINEAR POWER (FN in Hz^2/Hz, RIN via 10^(x/10)) - unbiased. The GUI's own
    Averaging is biased low (measured 2026-10-21): FN is averaged as AMPLITUDE (Hz/rtHz): x0.807 = -0.93 dB at
    n = 10; RIN is averaged in dB: -2.17 dB at n = 10 (Bias_tee/README.md). AVERAGING = 'gui' reproduces it.
    Measured on the instrument with the GUI in continuous capture: ~0.45 s per capture, n = 10 in ~4.4 s.
    The 10 captures are independent: the bin-to-bin scatter drops from 4.3 dB to 1.35 dB (= 1/sqrt(10)), exactly
    like the GUI's n = 10 export.

GUI settings from Python?
    Not in this GUI version: its remote 'set' command resets every other row of the panel (see SETTINGS_WARNING
    in lwa_utils.py). So the settings are made in the GUI; this script only captures, averages and saves.
"""

import datetime
import json
import os
import sys
import time
from pathlib import Path

import lwa_utils as lwa

# =============================================================================
# Settings
# =============================================================================
SAVE_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\HF Python control test\NKT 10mW EDFA 1090mA'
DEFAULT_SAVE_LABEL = 'RIN Python n='          # pre-filled text in the label pop-up
ASK_LABEL = True                 # False = use DEFAULT_SAVE_LABEL without pop-up

DATASETS = ('noise',)            # 'noise', 'lineshape', 'time'. NOTE: requesting 'lineshape' switches the GUI's
                                 # lineshape Autoeval ON, leaving it out switches it OFF (that is how the GUI
                                 # implements the request). Same for 'noise'.

# the measurements, run in order, REPEAT_PLAN times. keys: name, n_average, pause_s
PLAN = [
    dict(name='avg20', n_average=20)]
    #dict(name='single', n_average=1),
#]
REPEAT_PLAN = 1

# --- analysis / saving ---
# Units are automatic: FN is saved in Hz^2/Hz (the GUI publishes Hz/rtHz; capture() squares it - verified equal to the
# GUI's Hz^2/Hz export), RIN in dB/Hz (recognised by its negative values). Just switch the GUI's Noise mode.
NOISE_UNIT = 'Hz2/Hz'          # internal - do not change
AVERAGING = 'power'            # 'power' = unbiased linear-power average (recommended)
                               # 'gui'   = reproduce the GUI's Averaging: FN amplitude average (0.807x = -0.93 dB at
                               #           n = 10), RIN dB average (-2.17 dB at n = 10) - for comparisons with GUI files
FLOOR_RANGE_HZ = (5e6, 6e6)    # white-noise floor for the Python intrinsic linewidth pi*mean(S) (as HighFinesse_FN.get_data)
BINS_PER_DECADE = 20
SAVE_ALL_CAPTURES = True       # every single capture in the .h5 (noise/captures)
CAPTURE_TIMEOUT_S = 180
SHOW_PLOTS = True

# unattended runs (e.g. run_measurement.bat): environment variables override the above
SAVE_FOLDER = os.environ.get('LWA_SAVE_FOLDER', SAVE_FOLDER)
if os.environ.get('LWA_LABEL'):
    DEFAULT_SAVE_LABEL, ASK_LABEL = os.environ['LWA_LABEL'], False
SHOW_PLOTS = os.environ.get('LWA_SHOW_PLOTS', str(SHOW_PLOTS)) not in ('0', 'False', 'false')


# =============================================================================
class _Tee:
    def __init__(self, path):
        self.f = open(path, 'a', encoding='utf-8')
        self.out = sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)

    def flush(self):
        self.out.flush()
        self.f.flush()


def ask_label():
    if not ASK_LABEL:
        return DEFAULT_SAVE_LABEL or 'lwa'
    from tkinter import Tk, simpledialog
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    label = simpledialog.askstring('LWA measurement', 'Label (folder name):', initialvalue=DEFAULT_SAVE_LABEL,
                                   parent=root)
    root.destroy()
    if not label:
        raise SystemExit('No label - stopped.')
    return label.strip()


def main():
    label = ask_label()
    folder = Path(SAVE_FOLDER) / label
    folder.mkdir(parents=True, exist_ok=True)
    stamp0 = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    sys.stdout = _Tee(folder / f'{stamp0}_lwa_log.txt')
    print(f'=== LWA measurement {stamp0}  label={label} ===')

    dev = lwa.LWA1k()
    print(f'Connected to {dev.gui_path} (window 0x{dev.hwnd:X}, {dev.hwnd_source})')
    st = dev.status()
    print('Instrument state:', st['states'], '- nominal' if lwa.states_nominal(st['states']) else '- NOT nominal')
    if not lwa.states_nominal(st['states']):
        print('WARNING: the published state says Digitizer/Analyzer not connected or out of range - check the GUI.\n'
              '         (The GUI only republishes its state when it changes, so this can be stale, e.g. after a\n'
              '         second LWA_Control instance was started and closed; restarting the GUI clears it.)')
    noise_scales = {'noise': 'auto', 'lineshape': 'auto', 'time': 'power'}
    summary_path = folder / 'summary.csv'

    for rep in range(REPEAT_PLAN):
        for p in PLAN:
            n = int(p.get('n_average', 1))
            name = p.get('name', f'n{n}')
            print(f'\n--- {name} (repeat {rep + 1}/{REPEAT_PLAN}): {n} capture(s) ---')

            def progress(k, c):
                res = c.get('results') or {}
                print(f'  capture {k + 1}/{n}: {c["duration_s"]:.2f} s, nominal={c["states_nominal"]}, '
                      f'effective(beta)={res.get("effective_beta_Hz")}')

            t0 = time.time()
            meas = dev.capture_averaged(n, DATASETS, CAPTURE_TIMEOUT_S, on_capture=progress, scales=noise_scales,
                                        mode=AVERAGING)
            print(f'  {n} capture(s) in {time.time() - t0:.1f} s')
            stem = f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{name}"
            meta = lwa.save_measurement(folder, stem, meas, DATASETS, {'states': st['states']},
                                        dict(label=label, plan_entry=p, repeat=rep, gui=dev.gui_path,
                                             scales={d: meas[d]['scale'] for d in DATASETS}),
                                        NOISE_UNIT, BINS_PER_DECADE, SAVE_ALL_CAPTURES, FLOOR_RANGE_HZ)
            print(f"  saved {stem}  | Python analysis: {json.dumps(meta['analysis'])}")
            if not meas['states_nominal']:
                print('  WARNING: instrument state was not nominal during this measurement')
            new = not summary_path.exists()
            with open(summary_path, 'a', encoding='utf-8') as f:
                if new:
                    f.write('stem,n_average,duration_s,states_nominal,intrinsic_python_Hz,intrinsic_GUI_like_Hz,effective_beta_python_Hz,'
                            + ','.join(f'{k}_mean,{k}_std' for k in lwa.RESULT_LABELS) + '\n')
                gr = meas.get('results') or {}
                f.write(','.join('' if v is None else str(v) for v in [
                    stem, n, round(meas['duration_s'], 2), meas['states_nominal'],
                    meta['analysis'].get('intrinsic_linewidth_Hz_python'),
                    meta['analysis'].get('intrinsic_GUI_like_mode_Hz_python'),
                    meta['analysis'].get('effective_linewidth_Hz_python_beta'),
                    *[x for k in lwa.RESULT_LABELS for x in ((gr.get(k) or {}).get('mean'),
                                                             (gr.get(k) or {}).get('std'))]]) + '\n')
            lwa.plot_measurement(meas, DATASETS, NOISE_UNIT, f'{label} / {name} (n={n})', folder / stem, SHOW_PLOTS)
            if p.get('pause_s'):
                time.sleep(p['pause_s'])
    print(f'\nDone. Files in {folder}')
    if SHOW_PLOTS:
        import matplotlib.pyplot as plt
        plt.show()


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
