#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RIN measurement with photodetector + bias tee (1 kHz - 10 MHz)
==============================================================

Same layout as bias_tee_characterization.py / bias_tee_utils.py:
    rin_measurement.py   <- this file: settings (edit, then run it)
    rin_utils.py         <- all instrument handling, the conversion to optical power / RIN, plotting and saving

Wiring of one channel (CHANNELS: one entry per detector; add a second entry to measure two at the same time)
    PD output  ->  bias tee AC+DC input
    bias tee AC output  ->  DC block  ->  ESA RF input (DC-coupled)
    bias tee DC output  ->  Keithley 2450 HI / LO (0 A source = high-Z voltmeter)

How to use
    1. Fill in CHANNELS (IP addresses) and SAVE_FOLDER.
    2. Run the script. A pop-up asks for a label; everything is saved in  SAVE_FOLDER/<label>/  (the HighFinesse
       files go in SAVE_FOLDER/<label>/HighFinesse/, created right after the label pop-up):
           <timestamp>_rin_data.h5           all data (raw ESA traces, background, DC readings, settings, script sources)
           <timestamp>_rin_<channel>.csv     every ESA point: frequency, ESA noise, optical noise, RIN
           <timestamp>_rin_<channel>_binned.csv   the same averaged in BINS_PER_DECADE logarithmic bins
           <timestamp>_rin.pdf/.svg          RIN + the ESA noise density it was computed from (binned)
           <timestamp>_rin_<channel>_esa.png screenshot of the ESA
           <timestamp>_rin_log.txt           console log
    3. Pick the calibrations in the pop-ups (photodetector *_HiZ.h5, bias tee characterization folder; once per
       session, Cancel = none - see pd_cal / bias_tee_cal in CHANNELS).
       Answer the questions (DC block, block the laser for the background; Keithley unplug / reconnect only if it
       is not in high-Z mode). Then N_MEASUREMENTS are taken in a row without any question; afterwards you can ask
       for more (same or new label, any number) and still nothing is asked again, reset or re-wired.

Session (what is asked when the script is started again)
    A NEW session always asks the DC-block question and measures the background.
    Quit with  k  to KEEP the session open: the next start continues it and skips whatever the switches
    ASK_DC_BLOCK_EVERY_START / BACKGROUND_EVERY_START (False = skip) allow.
    The session is closed - and everything is asked again at the next start, whatever the switches say - by
        * quitting with  q , an error, Ctrl+C or a closed console (it only stays open after a clean  k )
        * SESSION_TIMEOUT_H without a start
        * an instrument that is not exactly as the script left it (somebody used the ESA or the Keithley)
        * a change of CHANNELS.
    The script cannot see cables: do not touch the RF / DC cabling while a session is kept open.

What is computed (rin_utils.compute_rin)
    DC: no current flows in the DC path, so the Keithley reads the OPEN-CIRCUIT (Hi-Z) detector voltage
            P_avg = (V_dc - V_dark) / K          K = V/W of the photodetector characterization (or G x R); V_dc is
                                                 corrected to the reading without the bias tee (its stage 3)
    AC: the ESA (50 ohm) and the 50 ohm output resistor of the detector halve the voltage, the trace is power in the RBW
            S_voc(f) = P_esa(f) / (1.065 RBW) x loss x 50 ohm x 4            V^2/Hz open-circuit detector voltage noise
            S_P(f)   = S_voc / K^2                                          W^2/Hz optical power noise
            RIN(f)   = S_P / P_avg^2                                        1/Hz, single-sided -> dBc/Hz
    K cancels in RIN: it only sets the absolute optical powers (and the TIA gain the shot-noise line). What does
    matter is the factor 4 (Hi-Z DC against 50 ohm AC), the AC path loss of bias tee + DC block (stage 2 of its
    characterization) and the noise bandwidth of the RBW.
    The background (laser blocked) is subtracted in linear power; points less than MIN_ABOVE_BACKGROUND_DB above it are
    dropped from 'rin' (the csv / h5 also hold the RIN as measured and the floor).

What is done with the HighFinesse file (COMPARE_HIGHFINESSE)
    Its FFT lines (50 Hz apart) are averaged in LINEAR units in the same log bins as the ESA RIN, then CORRECTED for
    the HighFinesse's dB averaging (see HIGHFINESSE_DB_AVERAGING_CORRECTION below: +2.33 dB at Av count 20, +2.17 dB
    at 10, 0 at 1), and only then compared: 'ESA - HighFinesse (corrected)'. Every output says which correction was
    added; the csv / h5 keep the HighFinesse bins both as exported and corrected.

Safety
    * ESA: the input is switched to DC coupling only after 'yes' to the DC-block question (given in this session), and
      back to AC coupling when the script ends (also after an error / Ctrl+C).
    * Keithley: always a 0 A source / high-Z voltmeter. Its state is read at every start and it is only reset (*RST,
      with the question to unplug the bias tee DC port) if it is NOT already in that mode - no switch turns that
      off. The script leaves it running as voltmeter, so later starts (also of a new session) do not reset it and
      the banana cables stay in. RESET_KEITHLEY_EVERY_START = True forces a reset at every start.
      With a 100 kohm resistor in series at the bias tee DC connector (DC_PORT_SERIES_R_OHM = 100e3) even a reset is
      harmless and you are never asked to unplug.
"""

import os
import time

import rin_utils as rin

# =============================================================================
# Settings
# =============================================================================

# --- channels: one detector + bias tee + ESA + Keithley each (all measured at the same time) ---
CHANNELS = [
    dict(name='PD1',
         esa='fsw', esa_ip='192.168.1.7',        # 'fsw' = R&S FSW50, 'ssa' = Siglent SSA3021X (>= 9 kHz, untested here)
         keithley_ip='192.168.1.151',            # Keithley 2450 on this bias tee's DC port
         pd_model='',                            # detector + fibre adapter as in the pd_cal file name, e.g. 'PDA05CF2_SM1FCA2'
                                                 # ('' = no check). The V/mW depends on the adapter: a warning if they differ
         wavelength_nm=None,                     # free, saved with the data
         pd_cal='ask',                           # photodetector characterization (Photodetector/photodetector_characterization.py,
                                                 # *_HiZ.h5): its measured V/W gives the optical power, its TIA gain the shot
                                                 # noise. 'ask' = pop-up once per session (Cancel = none), a path, or None
         pd_cal_preselect=r'C:\Users\Group Login\Documents\Jeppe_Surrow\Photodetector'
                          r'\2026-10-16_16-37-30_PDA05CF2_SM1FCA2_1550nm_HiZ.h5',   # highlighted in the pd_cal pop-up
                                                 # (DET1 + SM1FCA2); '' = the newest *_HiZ.h5
         responsivity_A_W=None,                 # only without pd_cal: responsivity at the laser wavelength (data sheet curve)
         transimpedance_V_A=None,                # only without pd_cal: transimpedance gain into HIGH-Z (PDA05CF2: 10 kV/A)
         pd_output_ohm=50.0,                     # series output resistor of the detector
         pd_max_hiz_V=10.0,                      # saturation into Hi-Z
         dark_offset_V=0.0,                      # only used with BACKGROUND = 'none' (otherwise measured)
         bias_tee_cal='ask',                     # bias tee characterization FOLDER (bias_tee_characterization.py): stage 2 =
                                                 # loss of bias tee + DC block vs frequency, stage 3 = DC reading through the
                                                 # tee vs direct. 'ask' = pop-up once per session (Cancel = none), a folder
                                                 # (or one stage-2 *_data.h5), or None
         bias_tee_cal_preselect=r'C:\Users\Group Login\Documents\Jeppe_Surrow\Bias_tee\Bias_tee_no_1_full_charac_inc_DC',
                                                 # the bias_tee_cal pop-up opens in this folder; '' = the newest run
         ac_path_loss_db=0.0,                   # only without bias_tee_cal: loss in dB, or (freqs_Hz, loss_dB)
         noise_bw_factor=1.065),                 # noise bandwidth of the RBW filter / RBW (Gaussian filter: 1.065)
    # dict(name='PD2', esa='ssa', esa_ip='192.168.1.11', keithley_ip='192.168.1.xxx', ...),
]

# --- saving ---
SAVE_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\RIN'
DEFAULT_SAVE_LABEL = ''           # pre-filled text in the label pop-up
PD_CAL_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\Photodetector'    # where the pd_cal pop-up opens
BIAS_TEE_CAL_FOLDER = r'C:\Users\Group Login\Documents\Jeppe_Surrow\Bias_tee'   # where the bias_tee_cal pop-up opens
                                                                                # (inside its newest characterization)
SAVE_SCREENSHOTS = True           # ESA screenshot after each measurement
SHOW_PLOTS = True                 # show the RIN plot after each measurement

# --- series ---
N_MEASUREMENTS = 1                # measurements taken in a row without any question (each saved separately)
PAUSE_BETWEEN_S = 0.0             # wait between the measurements of a series

# --- session: what is asked again when the script is STARTED again (see 'Session' above) ---
# True = at every start of the script. False = only in a new session; a start that continues a kept session skips it.
# A NEW session always does both, whatever is set here.
ASK_DC_BLOCK_EVERY_START = False      # the DC-block question
BACKGROUND_EVERY_START = False        # the background measurement (block / unblock the laser)
SESSION_TIMEOUT_H = 8                 # a kept session that was not used for this long is closed
# The Keithley does not follow the session: it is reset (with the unplug / reconnect question) only when it is found
# NOT in high-Z voltmeter mode. True here forces the reset at every start.
RESET_KEITHLEY_EVERY_START = False

# --- ESA: (start Hz, stop Hz, RBW Hz, VBW Hz[, points]); RMS detector, power average ---
# Several entries = several sweeps stitched together (each converted with its own RBW, the shared boundary point is
# taken once; the log bins then average across the boundary). Points per segment: the 5th entry, else ESA_POINTS.
# Present choice: one point per RBW in both segments.
#   1 kHz - 100 kHz  RBW 10 Hz , 9901 points (10 Hz apart): 10x more independent points per bin at 1-10 kHz than with
#                    100 Hz, so the low decade scatters ~3x less; RBW = 1/100 of the start keeps the 0 Hz (LO) peak out.
#   100 kHz - 10 MHz RBW 100 Hz, 99001 points (100 Hz apart), as before.
# A change here makes a new background (the session notices that the ESA settings changed).
# The single-sweep setting used until 2026-10-17:  [(1e3, 1e7, 100, 1e3)]  with ESA_POINTS = 100001
ESA_SEGMENTS = [(1e3, 1e5, 10, 100, 9901),
                (1e5, 1e7, 100, 1e3, 99001)]
ESA_POINTS = 100001               # points of a segment that does not give its own (FSW maximum: 100001)
ESA_AVERAGES = 20                 # sweeps averaged (trace scatter at most ~ 4.3 dB / sqrt(averages))
ESA_REF_LEVEL_DBM = -10           # must stay above the TOTAL power at the input; lower = lower noise floor
ESA_ATTEN_DB = 10                 # input attenuation (None = auto). Lower = lower noise floor, less protection.
ESA_SWEEP_TYPE = 'AUTO'           # FSW: AUTO / FFT / SWE  (a classic SWE sweep with 100 Hz RBW over 10 MHz takes very long)
ESA_INPUT_OHM = 50.0
ESA_TIMEOUT_MS = 1800000          # one averaged sweep must finish within this
BINS_PER_DECADE = 50              # plot / *_binned.csv: average in logarithmic frequency bins (0 = every ESA point)
ESA_AC_COUPLED_AT_EXIT = True     # leave the ESA AC-coupled (DC-safe) when the script ends
DC_BLOCK_NAME = 'Thorlabs EF500 DC block'

# --- splitter: power at this detector / power in the other arm (power meter / HighFinesse), from the same splitter ---
# (RIN is normalized to the average power, so the split ratio does not matter - only shot noise differs between the arms)
SPLIT_RATIO = 0.1285              # 2026-10-17: fit of 5 levels (0.1-0.92 mW at the detector arm), +-0.0001, offset-free.
                                  # Only used for the power in the other arm (summary, plot title, h5: p_other_arm_w).
                                  # None = not used. Measure it again whenever the splitter / fibres change.

# --- HighFinesse comparison: a HighFinesse LWA RIN measurement at the same time, on the other arm of the splitter ---
COMPARE_HIGHFINESSE = True       # True: every measurement asks you to start the HighFinesse measurement before the ESA sweep
                                  # and to save its RIN .txt + a screenshot afterwards. Save it as "raw data" ("binned data"
                                  # has only a max / min pair per point above ~60 kHz and is refused). The newest .txt and
                                  # screenshot saved after the ESA start are used and copied to the label folder:
                                  #   <timestamp>_rin_highfinesse.txt / _highfinesse_screenshot.png   the files
                                  #   <timestamp>_rin_highfinesse.pdf/.svg      HighFinesse RIN, same axes as _rin.pdf/.svg
                                  #   <timestamp>_rin_vs_highfinesse.pdf/.svg   both + ESA - HighFinesse in the same bins
                                  #   <timestamp>_rin_vs_highfinesse_<channel>.csv
                                  # Compare again later (other HighFinesse file): rin_compare_highfinesse.py
HIGHFINESSE_FOLDER = 'HighFinesse'   # where you save them: a folder name = a subfolder of the label folder
                                     # (SAVE_FOLDER/<label>/HighFinesse, created as soon as the label is chosen, before
                                     # anything is measured), or an absolute path = one folder for every label
HIGHFINESSE_DB_AVERAGING_CORRECTION = True
# The HighFinesse averages its Av count = N spectra in dB, NOT in power, so its noise reads LOW (tested 2026-10-17 with
# N = 1, 2, 5, 10, 20: exactly as predicted). Every exported FFT line is on average 2.51 dB low; after the linear mean
# in the log bins used here the bias is 10 N log10(Gamma(1 + 1/N)) dB:
#     N = 1: 0   2: -1.05   5: -1.86   10: -2.17   20: -2.33 dB
# N is read from 'Av count' in each HighFinesse file (Averaging = 0 = one spectrum), so any setting on the HighFinesse
# works; more averages (up to its maximum of 20) only reduce the scatter.
# True: that amount is ADDED to the binned HighFinesse RIN before it is plotted as 'corrected' and compared with the ESA
# (the console, the plot titles, the csv column highfinesse_db_averaging_correction_dB and the h5 say so). The
# HighFinesse file and the faint 'every FFT line' curve stay as exported. False = compare as exported (old behaviour).
# Narrow lines (steady tones) are not biased by dB averaging, so there the correction over-corrects.

# --- background (laser blocked): noise floor of detector + ESA and the dark offset ---
BACKGROUND = 'measure'            # 'measure' = once per session; 'none'; or the path of an earlier *_rin_data.h5 (same ESA settings)
MIN_ABOVE_BACKGROUND_DB = 3.0     # points closer to the background than this are dropped from the subtracted RIN

# --- Keithley 2450 (DC port), see 'Safety' ---
KEITHLEY_VLIM_V = 20              # voltage limit of the 0 A source; must be above the highest detector voltage
KEITHLEY_NPLC = 1                 # integration time per reading (power line cycles)
KEITHLEY_NREAD = 10               # readings averaged before and after every ESA segment
KEITHLEY_STORE_POWER_ON = False   # True: after a reset, store the high-Z voltmeter setup as the 2450's power-on state
                                  # (*SAV 0, :SYST:POS SAV0) so a power cycle does not bring back the default state.
                                  # Changes the instrument for every user - hence off by default.
DC_PORT_SERIES_R_OHM = 0.0        # resistor in series with the Keithley HI line at the bias tee DC connector (100e3 recommended)
INDUCTOR_MAX_A = 9e-3             # rating of the weakest bias tee inductor
DC_DRIFT_WARN_FRAC = 0.01         # warn if the DC level changes by more than this during one segment
MIN_SIGNAL_V = 5e-3               # abort if the DC level is less than this above the dark level (no light / not connected)


# =============================================================================
def main():
    cfg = rin.config_from_globals(globals())
    rin.validate_config(cfg)

    label = rin.bt.ask_label(cfg.SAVE_FOLDER, cfg.DEFAULT_SAVE_LABEL, title='RIN measurement')
    label = rin.bt.safe_name(label) or 'unlabelled'
    print('Label: %s\nSaving in: %s\nChannels: %s' % (label, os.path.join(cfg.SAVE_FOLDER, label),
                                                      ', '.join(c['name'] for c in cfg.CHANNELS)))
    rin.prepare_label_folder(cfg, label)  # label folder + its HighFinesse folder, before anything is measured

    R = rin.RinSetup(cfg)
    try:
        R.prepare_dc_monitors()           # Keithley: reset only if it is not already a high-Z voltmeter
        R.confirm_dc_block()              # ESA: DC coupling only after 'yes' (in this session)
        background = R.get_background()
        n = cfg.N_MEASUREMENTS
        while True:
            for i in range(n):                # a series: no questions in between
                if n > 1:
                    print('\n----- measurement %d of %d -----' % (i + 1, n))
                rin.run_measurement(R, label, background)
                if i + 1 < n:
                    time.sleep(cfg.PAUSE_BETWEEN_S)
            nxt = rin.ask_next(cfg, label, n)
            if nxt is None:                   # q: session closed
                break
            if nxt == 'k':                    # quit, but the next start continues this session
                R.keep_session = True
                break
            if nxt == 'b':
                background = R.measure_background()
            else:
                if nxt[0] != label:
                    rin.prepare_label_folder(cfg, nxt[0])   # new label: its folders before the next series starts
                label, n = nxt
    except rin.NotConfirmed as e:
        print('\n%s' % e)
    finally:
        R.close()


if __name__ == '__main__':
    main()
