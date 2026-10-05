#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bias tee characterization (custom bias tee, 1 kHz - 10 MHz)
===========================================================

Same layout as Eye_diagram_lab.py / eye_diagram_utils.py:
    bias_tee_characterization.py   <- this file: settings + which stage(s) to run (edit, then run it)
    bias_tee_utils.py              <- all instrument handling, analysis, plotting and saving

How to use
    1. Set MEASUREMENT (receiver) and the IP addresses below.
    2. Set STAGES_TO_RUN, e.g. [1] today and [2, 3] later.  Each stage tells you how to wire the next step.
    3. Run the script.  A pop-up asks for a label; everything is saved in  SAVE_FOLDER/<label>/ :
           <timestamp>_stage<N>_data.h5          all data (raw scope records / ESA traces, screenshots, settings)
           <timestamp>_stage<N>_summary.csv      power vs frequency of every sweep
           <timestamp>_stage<N>_report.pdf/.svg  plots (power, change vs reference, Keithley DC, scope: harmonics)
           <timestamp>_stage<N>_spectra.pdf/.svg spectra (+ scope time signal) of every sweep at SPECTRA_FREQS_HZ
           <timestamp>_stage<N>_fftcheck.pdf/.svg  scope only: screenshot of the scope's own FFT next to ours
           <timestamp>_stage<N>_log.txt          console log of the stage
           <timestamp>_stage<N>_screenshots/*.png  screenshots of the receiver at SCREENSHOT_FREQS_HZ

Mimics a Thorlabs amplified photodetector (PDA05CF2, PDA10A2, ...) with the Siglent SDG6022X and measures the
AC path of the bias tee on a scope / ESA, while a Keithley 2450 monitors the DC port as a HIGH-IMPEDANCE voltmeter.

Stage 1 - DC block only      (receiver DC-coupled => the signal MUST be pure AC)
    A  SDG CH1 -> receiver                         reference
    B  SDG CH1 -> Thorlabs EF500 -> receiver       DC block
    C  same as B, receiver AC-coupled (optional)
    Result: DC block insertion loss = P(B) - P(A)

Stage 2 - bias tee, pure AC  (receiver AC-coupled, DC block in front of it)
    R  SDG CH1 -> EF500 -> receiver                reference
    T  SDG CH1 -> bias tee (AC+DC in); bias tee AC out -> EF500 -> receiver; bias tee DC out -> Keithley 2450
    Result: bias tee insertion loss = P(T) - P(R)

Stage 3 - bias tee, AC + DC  (same wiring as T)
    One sweep for each level in PD_DC_LEVELS_V (0 V = clean AC repeat).

DC convention
    A Thorlabs PD has a 50 ohm series resistor: 0-10 V into Hi-Z, 0-5 V into 50 ohm.  The SDG is kept in its
    "50 ohm load" mode, so what you type is what a 50 ohm load sees.  In the bias tee the AC path ends in the
    receiver (50 ohm) but the DC path is (almost) open, so the Keithley reads DC_AT_TEE_FACTOR (= 2) x the SDG offset.

Safety
    * The Keithley is ALWAYS a 0 A source / high-Z voltmeter.  Never source voltage on the DC port: the 100 mH
      inductor is only rated for 9 mA.
    * ESA with DC coupling (R&S FSW): the input must be protected against DC by you.  The script forces the SDG
      output OFF while configuring, checks by read-back that the offset is 0 V before switching the output ON, and
      refuses DC offsets while an ESA is DC-coupled.  The SDG output is switched OFF at every re-wiring prompt and at exit.
    * Scope: 1 MOhm input => put a 50 ohm feed-through terminator on it.  Only 8 bit => the vertical scale is
      auto-adjusted so the signal fills ~6 divisions.
    * SSA3021X: starts at 9 kHz (lower points are skipped); no coupling command - check the input DC rating.
    * EF500 is a BNC feed-through: use the same BNC-SMA adapters in the reference and the measurement.
"""

import os
import sys

import numpy as np

import bias_tee_utils as bt

# =============================================================================
# Settings
# =============================================================================
STAGES_TO_RUN = [1]               # any of 1, 2, 3 (run in this order). Stages 2/3 need the Keithley.
MEASUREMENT = 'scope'             # receiver: 'scope' = Siglent SDS2352X-E, 'fsw' = R&S FSW50, 'ssa' = Siglent SSA3021X

# --- instruments ---
AFG_IP = '192.168.1.101'          # Siglent SDG6022X
AFG_CH = 1
AFG_LOAD = 50                     # SDG load setting (see 'DC convention')
SCOPE_IP = ''                     # Siglent SDS2352X-E  <-- set this
FSW_IP = '192.168.1.7'            # R&S FSW50
SSA_IP = '192.168.1.11'           # Siglent SSA3021X
KEITHLEY_IP = '192.168.1.151'     # Keithley 2450

# --- saving ---
SAVE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')     # <-- set to the lab-PC data folder
DEFAULT_SAVE_LABEL = ''           # pre-filled text in the label pop-up
SAVE_SCREENSHOTS = True           # receiver screenshots (PNG, also embedded in the h5)
SCREENSHOT_FREQS_HZ = [1e3, 1e5, 1e7]   # take a screenshot at these tones (set [] for none)
SPECTRA_FREQS_HZ = [1e3, 1e5, 1e7]   # tones shown in the _spectra / _fftcheck figures (must be in FREQUENCIES_HZ)
SHOW_PLOTS = False                # also open the plot windows at the end of each stage

# --- signal ---
FREQUENCIES_HZ = sorted({m * 10 ** e for e in range(3, 7) for m in (1, 2, 3, 5, 7)} | {1e7})   # 1 kHz ... 10 MHz
VPP = 0.5                         # sine amplitude, Vpp into 50 ohm (-2 dBm). Keep small, like a PD AC signal.
# PD output into 50 ohm (PDA05CF2 / PDA10A2: 0-5 V). 0 = clean AC. DC + VPP/2 must stay <= PD_MAX_50OHM_V.
PD_DC_LEVELS_V = [0, 0.5, 1, 2, 3, 4, 4.5]
PD_MAX_50OHM_V = 5.0              # PD / SDG limit into 50 ohm
PD_MAX_HIZ_V = 10.0               # PD saturation into Hi-Z
DC_AT_TEE_FACTOR = 2.0            # DC at bias tee DC port = factor x SDG offset
DC_TOL_FRAC, DC_TOL_ABS_V = 0.05, 0.02    # Keithley vs expected DC: flag deviations beyond this
DC_ABORT_LOW_FRAC, DC_ABORT_HIGH_FRAC = 0.25, 1.5   # ABORT (SDG off) if the Keithley reads outside this fraction of the expected DC
# --- protection of the bias tee DC port (short circuit) ---
INDUCTOR_MAX_A = 9e-3             # rating of the weakest inductor (100 mH: 9 mA)
DC_PORT_SERIES_R_OHM = 0.0        # resistor you put in series with the Keithley input, at the bias tee DC connector. 100e3 is
                                  # recommended: it limits a short to < 0.1 mA and changes the reading by only R/10 GOhm = 1e-5.
                                  # Only recorded/used for the warnings and current estimates - the script cannot see it.
DC_PRECHECK_OFFSET_V = 0.1        # each DC sweep starts with this small SDG offset (2*0.1 V/50 ohm = 4 mA even into a dead short)
                                  # and only goes to the real level if the Keithley reads ~2x of it

STAGE1_ALSO_AC_COUPLED = True     # extra sweep C in stage 1 (receiver AC-coupled, DC block, pure AC)
SETTLE_S = 0.5                    # wait after changing the SDG
PASS_TOL_DB = 1.0                 # flat-response criterion relative to the reference

# --- ESA settings ('fsw' / 'ssa') ---
ESA_REF_LEVEL_DBM = 10
ESA_NREAD = 2                     # sweeps per point (max of the peaks is reported)

# --- scope settings ('scope') ---
SCOPE_CH = 1
SCOPE_COUPLING = {'DC': 'D1M', 'AC': 'A1M'}   # 1 MOhm; use an external 50 ohm feed-through terminator
SCOPE_MEMORY = '140K'             # memory depth (the scope reports what it really used)
SCOPE_NCYC = 100                  # record length >= this many signal periods
SCOPE_NACQ = 3                    # records per point (power-averaged)
SCOPE_PP_CODES = (100, 190)       # wanted peak-peak range in ADC codes (25 codes/div, +-127 max)
SCOPE_BWL = False                 # 20 MHz bandwidth limit

RECEIVER_TIMEOUT_MS = 60000       # slow RBWs at 1 kHz on the ESA


# =============================================================================
def main():
    cfg = bt.config_from_globals(globals())
    bt.validate_config(cfg)
    stages = list(cfg.STAGES_TO_RUN)

    label = bt.ask_label(cfg.SAVE_FOLDER, cfg.DEFAULT_SAVE_LABEL)
    label = bt.safe_name(label) or 'unlabelled'
    run_folder = os.path.join(cfg.SAVE_FOLDER, label)
    os.makedirs(run_folder, exist_ok=True)
    print('Label: %s\nSaving in: %s\nStages: %s   Receiver: %s' % (label, run_folder, stages, bt.RECEIVER_NAMES[cfg.MEASUREMENT]))

    S = bt.Setup(cfg, need_keithley=any(s >= 2 for s in stages))
    try:
        for stage in stages:
            bt.run_stage(S, stage, run_folder, label)
    finally:
        S.close()


if __name__ == '__main__':
    main()
