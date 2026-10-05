#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reprocess bias tee HDF5 data files
====================================
Regenerates all plots from existing *_data.h5 (or *_PARTIAL_data.h5) files without
needing any instruments connected.

Usage
-----
  python bias_tee_reprocess.py                          # file dialog
  python bias_tee_reprocess.py path/to/file.h5          # one file
  python bias_tee_reprocess.py path/to/folder/          # all *_data.h5 in folder

Plots generated (same base name as the h5, overwriting any existing files):
  _report.pdf/.svg        power vs frequency, delta, DC, harmonics
  _spectra.pdf/.svg       FFT spectra at SPECTRA_FREQS_HZ
  _fftcheck.pdf/.svg      scope screenshots vs our FFT (scope only, needs screenshots in h5)
  _allspectra.pdf/.svg    all FFT spectra overlaid (scope only)
  _dcresponse.pdf/.svg    AC response vs DC bias level (stage 3 only)
"""

import os
import sys
import glob

import bias_tee_utils as bt


def _strip_data_suffix(path):
    """'foo_data.h5' -> 'foo',  'foo_PARTIAL_data.h5' -> 'foo_PARTIAL'."""
    name = os.path.splitext(os.path.basename(path))[0]   # strip .h5
    for sfx in ('_data', '_PARTIAL_data'):
        if name.endswith(sfx):
            name = name[:-len(sfx)]
            break
    return os.path.join(os.path.dirname(path), name)


def reprocess(h5_path, show=False):
    print('\nLoading: %s' % h5_path)
    try:
        cfg, res = bt.load_stage_result(h5_path)
    except Exception as e:
        print('  ERROR loading h5: %s' % e)
        return
    base = _strip_data_suffix(h5_path)
    print('  Stage %d: %s  (%d sweeps)' % (res['stage'], res['title'], len(res['sweeps'])))
    for fn, suffix in ((bt.make_report,            '_report'),
                       (bt.make_spectra_report,    '_spectra'),
                       (bt.make_fft_check_report,  '_fftcheck'),
                       (bt.make_all_spectra_report,'_allspectra'),
                       (bt.make_dc_response_report,'_dcresponse')):
        try:
            fn(cfg, res, base + suffix, show=show)
        except Exception as e:
            print('  warning: %s failed: %s' % (fn.__name__, e))
    print('  Done.')


def _pick_files():
    """Return a list of h5 paths from argv or a file dialog."""
    if len(sys.argv) > 1:
        paths = []
        for arg in sys.argv[1:]:
            if os.path.isdir(arg):
                paths += sorted(glob.glob(os.path.join(arg, '*_data.h5')))
            else:
                paths.append(arg)
        return paths
    # No arguments: try a file dialog
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        paths = filedialog.askopenfilenames(
            title='Select bias tee HDF5 file(s)',
            filetypes=[('HDF5 files', '*_data.h5'), ('All HDF5', '*.h5'), ('All files', '*')],
        )
        root.destroy()
        return list(paths)
    except Exception:
        print('No file given and no GUI available.  Pass file path(s) as arguments.')
        sys.exit(1)


if __name__ == '__main__':
    import matplotlib
    matplotlib.use('TkAgg')   # interactive backend for show=True
    import matplotlib.pyplot as plt

    files = _pick_files()
    if not files:
        print('No files selected.')
        sys.exit(0)

    for p in files:
        reprocess(p, show=True)
    plt.show()
