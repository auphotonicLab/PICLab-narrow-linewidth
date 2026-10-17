#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare a saved ESA RIN measurement with a HighFinesse LWA RIN export (no instruments needed)
=============================================================================================

rin_measurement.py with COMPARE_HIGHFINESSE = True does this right after each measurement. This script does it again
later, e.g. with a HighFinesse file that was saved too late or as "binned data" and has been exported again.

    ESA_H5           'newest' = the newest  SAVE_FOLDER/<label>/<timestamp>_rin_data.h5 , or a path
    HIGHFINESSE_TXT  'newest' = the newest .txt in the HighFinesse folder of rin_measurement.py, or a path
                     (must be a "raw data" export: one row per FFT line)

Output in  <label folder>/<timestamp>_vs_<HighFinesse file name>/ :
    <timestamp>_rin.pdf/.svg                     ESA RIN          } the same axes, so they can be laid over each other
    <timestamp>_rin_highfinesse.pdf/.svg         HighFinesse RIN  }
    <timestamp>_rin_vs_highfinesse.pdf/.svg      both + ESA - HighFinesse per bin
    <timestamp>_rin_vs_highfinesse_<channel>.csv the compared bins, and a copy of the HighFinesse .txt

How they are compared (rin_utils.compare_highfinesse): the HighFinesse FFT lines are averaged in linear units in
exactly the logarithmic bins of the ESA RIN (BINS_PER_DECADE of the measurement), over the ESA frequency range.
ESA - HighFinesse is printed per decade and as the median of all bins. A constant offset of about 3 dB would mean
that one of the two is a double-sided spectrum.
"""

import os

import matplotlib.pyplot as plt

import rin_measurement as settings
import rin_utils as rin

# =============================================================================
# Settings
# =============================================================================
ESA_H5 = 'newest'
HIGHFINESSE_TXT = 'newest'
SAVE_FOLDER = settings.SAVE_FOLDER                                        # where 'newest' looks for the ESA file
HIGHFINESSE_DIR = rin.highfinesse_dir(rin.config_from_globals(vars(settings)))   # where 'newest' looks for the .txt
MAX_TIME_GAP_MIN = 30         # warn if the HighFinesse file was not saved within this long after the ESA start
SHOW_PLOTS = True


# =============================================================================
def main():
    esa = ESA_H5 if ESA_H5 != 'newest' else rin._newest(SAVE_FOLDER, os.path.join('*', '*_rin_data.h5'))
    txt = HIGHFINESSE_TXT if HIGHFINESSE_TXT != 'newest' else rin._newest(HIGHFINESSE_DIR, '*.txt')
    if not esa or not os.path.isfile(esa):
        raise SystemExit('No ESA measurement found (%s)' % (esa or os.path.join(SAVE_FOLDER, '*', '*_rin_data.h5')))
    if not txt or not os.path.isfile(txt):
        raise SystemExit('No HighFinesse file found (%s)' % (txt or os.path.join(HIGHFINESSE_DIR, '*.txt')))
    rin.compare_saved(esa, txt, MAX_TIME_GAP_MIN, show=SHOW_PLOTS)
    if SHOW_PLOTS:
        plt.show()


if __name__ == '__main__':
    main()
