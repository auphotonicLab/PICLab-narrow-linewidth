#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HighFinesse LWA-1k (1550) remote control - everything except the settings
==========================================================================

    lwa_measurement.py   <- settings (edit, then run it)
    lwa_utils.py         <- this file: connection, commands, data, averaging, analysis, saving, diagnostics

HOW THE CONNECTION WORKS
    HighFinesse ships no documented API for the LWA-1k. This module talks to the running GUI (LWA_Control.exe)
    the same way HighFinesse's own lwaData.dll does; everything below was reverse-engineered from lwaData.dll and
    LWA_Control.exe (versions in 'HighFinesse LWA-1k installation file and manual\\src', see README.md):

      * COMMANDS  are window messages WM_USER+1 (0x401) to the GUI main window:
                      wParam = (group << 16) | panel      lParam = (row << 16) | value
                  group 2 = "set panel row to option number <value>" (the GUI then clicks that option itself),
                  group 1 = requests (start capture + publish data, publish settings / results, output binning).
      * RESULTS   come back through four named shared-memory blocks the GUI writes:
                      LWA_Status_Rec_map (settings, instrument state, linewidths, 'new data' flags)
                      LWA_TimeData_map / LWA_NoiseData_map / LWA_LineshapeData_map  (up to 8 388 608 doubles)
    => LWA_Control.exe must be running and initialised. It still does the hardware I/O and HighFinesse's
       calibrated evaluation; Python sets it up, triggers it and collects the results.

WHAT CAN BE SET FROM PYTHON (the GUI's remote interface handles exactly these)
    Analyzer   : Noise mode (FN/RIN), Cutoff (10Hz/1kHz/10kHz/100kHz), Power mode (Fixed/Auto/Reset), Pol control
    Digitizer  : Range [V] (10mV ... 20V, auto), Range [Hz] (60kHz ... 30MHz)
    Evaluation : noise Autoeval, lineshape Autoeval, Fitmode (Off/Full/Guess), Fitfunction (Lorentzian/Gaussian/
                 Voigt), Intrinsic (1/f fit / Mode(stat)), lineshape Time int [s]
    Capture    : single capture, continuous start, stop; which datasets are published; raw or binned output
    NOT settable (the GUI ignores them remotely): Digitizer Res [Hz], Coupling, Continuous, Averaging, the whole
    Display panel and the wavelength. Res / Coupling / Continuous / Averaging can be READ back, so the script checks
    them. Averaging is done here instead (capture_averaged: n single captures averaged in LINEAR units - unlike the
    GUI, which averages in dB, see Bias_tee/README.md).

Requires Windows, 64-bit Python >= 3.8, numpy (matplotlib for plots). No HighFinesse DLL is needed; lwaData.dll is
only loaded by `check` to cross-check the decoding when it is found.

Diagnostics from the VS Code terminal (python lwa_utils.py -h):
    python lwa_utils.py check            staged connection test (read-only, nothing is changed)
    python lwa_utils.py settings         print the GUI settings as Python reads them
    python lwa_utils.py set analyzer.cutoff=1kHz evaluation.fit_function=Voigt
    python lwa_utils.py probe            one capture, logs everything to probe_log.json
    python lwa_utils.py compare GUI_export.txt <file>_noise.csv
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import datetime as _dt
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

IS_WINDOWS = sys.platform == "win32"

# =============================================================================
# Protocol constants (from the disassembly - see README.md 'How it was found')
# =============================================================================
WM_LWA = 0x0401                        # WM_USER + 1, handled by the GUI main form

# group 1: requests
REQ_PUBLISH_DIGITIZER = 1              # GUI writes its Digitizer settings table into status group 0
REQ_PUBLISH_ANALYZER = 2               # ... Analyzer settings table into status group 1
REQ_PUBLISH_RESULTS = 5                # DO NOT USE: publishes the module's never-synced (zero) result table
REQ_DATA = 7                           # value = dataset mask; row 0 = single capture, row != 0 = continuous
REQ_BINNING = 8                        # value = mask of datasets published BINNED (0 = all raw)
# (group 1 panel 3/4/6 exist but overwrite the instrument-state group or are lost - never sent)

# group 2: settings ("panel row := option index"), then the GUI applies them
PANEL_DIGITIZER = 1
PANEL_ANALYZER = 2
PANEL_EVALUATION = 4
PANEL_CAPTURE = 6                      # row 0: value 0 = stop, 2 = start (clicks Capture if the state differs)

DATASET_BITS = {"time": 1, "noise": 2, "lineshape": 4}

# Option lists = the GUI's drop-down menus, in order (value sent = index in this list).
DIGITIZER_ROWS = {   # name: (row, options or None if read-only)
    "range_V":    (0, ["10mV", "20mV", "50mV", "100mV", "200mV", "500mV", "1V", "2V", "5V", "10V", "20V", "auto"]),
    "coupling":   (1, ["AC", "DC"]),
    "range_Hz":   (2, ["60kHz", "125kHz", "250kHz", "500kHz", "1MHz", "2MHz", "4MHz", "8MHz", "15MHz", "30MHz"]),
    "res_Hz":     (3, None),
    "continuous": (4, ["Off", "On"]),
    "averaging":  (5, ["Off", "Complete BW", "Binned"]),
}
DIGITIZER_SETTABLE = {"range_V", "range_Hz"}          # the GUI applies only rows 0 and 2 remotely
ANALYZER_ROWS = {
    "noise_mode":  (0, ["FN", "RIN"]),
    "cutoff":      (1, ["10Hz", "1kHz", "10kHz", "100kHz"]),
    "power_mode":  (2, ["Fixed", "Auto", "Reset"]),
    "pol_control": (3, None),                         # option order not confirmed: integer only
}
EVALUATION_ROWS = {  # internal GUI keys in brackets
    "noise_autoeval":     (0, ["Inactive", "Active"]),            # _psd_autoeval
    "lineshape_autoeval": (4, ["Inactive", "Active"]),            # _line_autoeval
    "fit_mode":           (5, ["Off", "Full", "Guess"]),          # _line_autofit
    "fit_function":       (8, ["Lorentzian", "Gaussian", "Voigt"]),  # _line_fitfun
    "intrinsic":          (13, ["1/f fit", "Mode(stat)"]),        # _psd_intrinsic
    "lineshape_time_int_s": (7, "float"),                         # _line_timelength (double via shared memory)
}
# Rows NOT exposed on purpose: numeric fields (Start [Hz] = row 1, Division = row 14) and Recalc buttons -
# sending an option index to a numeric field makes the GUI look up a non-existing menu item.

# =============================================================================
# Shared-memory layout
# =============================================================================
STATUS_MAP = "LWA_Status_Rec_map"
DATA_MAPS = {"time": "LWA_TimeData_map", "noise": "LWA_NoiseData_map", "lineshape": "LWA_LineshapeData_map"}
STATUS_SIZE = 0x648
DATA_HDR = 0x28
DATA_MAX_POINTS = 0x800000

OFF_HWND, OFF_READY, OFF_COUNT, OFF_TABLE = 0x08, 0x12, 0x18, 0x30
GROUP_STRIDE, ITEM_STRIDE = 312, 24                    # 5 groups x 13 cells {int32; pad; double; u8 new}
G_DIGITIZER, G_ANALYZER, G_STATES, G_MISC, G_RESULTS = 0, 1, 2, 3, 4
STATE_ITEMS = ["digitizer", "analyzer", "noise", "range", "power", "power_state", "pol_control"]
STATE_NOMINAL = {"digitizer": 1, "analyzer": 1, "range": 1}     # connected + in range. Published: items 0-4;
# on the instrument: noise = 1 and power = 97..98 (power level in %) during normal operation.
# Result slots, identified on the instrument (2026-10-21, FN mode): slot1 = Effective (beta), identical to the
# export header; slots 2-4 = lineshape fit: Voigt FWHM, Lorentzian width, Gaussian width (they satisfy the Voigt
# FWHM formula exactly); slot0 = 100.0 = the GUI's "<0.1 kHz" display limit. The intrinsic value of the export
# header is NOT published - Python computes it from the spectrum.
RESULT_LABELS = ["intrinsic_display_Hz", "effective_beta_Hz", "voigt_fwhm_Hz", "lorentz_width_Hz", "gauss_width_Hz"]


def cell(group: int, item: int) -> int:
    return OFF_TABLE + group * GROUP_STRIDE + item * ITEM_STRIDE


def parse_status(buf: bytes) -> dict:
    """Decode the 1608-byte status record."""
    if len(buf) < STATUS_SIZE:
        raise ValueError("status record too short")
    i32 = lambda off: struct.unpack_from("<i", buf, off)[0]          # noqa: E731
    f64 = lambda off: struct.unpack_from("<d", buf, off)[0]          # noqa: E731
    return {
        "record_size": i32(0),
        "gui_hwnd": struct.unpack_from("<Q", buf, OFF_HWND)[0],
        "ready": {d: bool(buf[OFF_READY + i]) for i, d in enumerate(DATA_MAPS)},
        "counts": {d: i32(OFF_COUNT + 4 * i) for i, d in enumerate(DATA_MAPS)},
        "digitizer_raw": [i32(cell(G_DIGITIZER, i)) for i in range(6)],
        "digitizer_new": [bool(buf[cell(G_DIGITIZER, i) + 16]) for i in range(6)],
        "analyzer_raw": [i32(cell(G_ANALYZER, i)) for i in range(4)],
        "analyzer_new": [bool(buf[cell(G_ANALYZER, i) + 16]) for i in range(4)],
        "states": {n: i32(cell(G_STATES, i)) for i, n in enumerate(STATE_ITEMS)},
        "results": [f64(cell(G_RESULTS, i) + 8) for i in range(5)],
        "results_new": [bool(buf[cell(G_RESULTS, i) + 16]) for i in range(5)],
        "time_int_s": f64(cell(G_MISC, 7) + 8),
    }


def states_nominal(states: dict) -> bool:
    return all(states.get(k) == v for k, v in STATE_NOMINAL.items())


def parse_data_header(buf: bytes) -> dict:
    """40-byte data header: n @0x14, first x @0x20, last x @0x18, flag @0x10."""
    return {"valid": bool(buf[0x10]), "n": struct.unpack_from("<i", buf, 0x14)[0],
            "x_first": struct.unpack_from("<d", buf, 0x20)[0],
            "x_last": struct.unpack_from("<d", buf, 0x18)[0]}


def decode_table(raw: list, rows: dict) -> dict:
    out = {}
    for name, (row, opts) in rows.items():
        if row >= len(raw):
            continue
        v = raw[row]
        out[name] = opts[v] if isinstance(opts, list) and 0 <= v < len(opts) else v
    return out


def option_index(name: str, value, options) -> int:
    """'1 kHz', '1kHz', 1 -> index. Case/space-insensitive."""
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, int):
        if isinstance(options, list) and not 0 <= value < len(options):
            raise ValueError(f"{name}: index {value} out of range {options}")
        return value
    norm = lambda s: str(s).lower().replace(" ", "").replace("_", "")  # noqa: E731
    if not isinstance(options, list):
        raise ValueError(f"{name} takes an integer")
    for i, o in enumerate(options):
        if norm(o) == norm(value):
            return i
    raise ValueError(f"{name}: '{value}' is not one of {options}")


def lparam(row: int, value: int) -> int:
    return ((row & 0xFFFF) << 16) | (value & 0xFFFF)


# =============================================================================
# Windows plumbing
# =============================================================================
if IS_WINDOWS:
    from ctypes import wintypes as wt
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _k32.OpenFileMappingW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
    _k32.OpenFileMappingW.restype = wt.HANDLE
    _k32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
    _k32.MapViewOfFile.restype = ctypes.c_void_p
    _k32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.OpenProcess.restype = wt.HANDLE
    _k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
    _u32.IsWindow.argtypes = [wt.HWND]
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    _u32.EnumWindows.argtypes = [_WNDENUMPROC, wt.LPARAM]
    _u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _u32.IsWindowVisible.argtypes = [wt.HWND]
    _u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    _u32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT,
                                         ctypes.POINTER(ctypes.c_size_t)]
    _u32.SendMessageTimeoutW.restype = ctypes.c_size_t
    FILE_MAP_WRITE, FILE_MAP_READ = 0x0002, 0x0004


class LWAError(RuntimeError):
    pass


SETTINGS_WARNING = (
    "Remote settings are disabled. Found on the instrument (2026-10-21): the GUI's remote module keeps its own copy "
    "of the Digitizer/Analyzer/Evaluation tables and never synchronises it with the panels (it publishes all "
    "zeros). A set command writes one row into that copy and the GUI then applies the WHOLE copy - every other "
    "row of the panel jumps to its first option (e.g. setting the cutoff switches RIN -> FN and Auto -> Fixed). "
    "Set the GUI by hand. LWA1k(allow_settings=True) re-enables it for experiments - give ALL rows of a panel.")


def _need_windows():
    if not IS_WINDOWS:
        raise LWAError("The LWA software runs on Windows only.")


def _map(name: str, write: bool = False):
    _need_windows()
    acc = FILE_MAP_WRITE if write else FILE_MAP_READ
    h = _k32.OpenFileMappingW(acc, False, name)
    if not h:
        return None, None
    p = _k32.MapViewOfFile(h, acc, 0, 0, 0)
    if not p:
        _k32.CloseHandle(h)
        raise OSError(ctypes.get_last_error(), f"MapViewOfFile({name})")
    return h, p


def read_shared(name: str, nbytes: int) -> bytes | None:
    """Read-only copy of a shared-memory block (None = does not exist = GUI not running)."""
    h, p = _map(name)
    if h is None:
        return None
    try:
        return ctypes.string_at(p, nbytes)
    finally:
        _k32.UnmapViewOfFile(p)
        _k32.CloseHandle(h)


def write_shared(name: str, offset: int, data: bytes):
    """Write a few bytes (a flag or one double) - never the whole record, so GUI updates are not overwritten."""
    h, p = _map(name, write=True)
    if h is None:
        raise LWAError(f"{name} not found - GUI not running")
    try:
        ctypes.memmove(p + offset, data, len(data))
    finally:
        _k32.UnmapViewOfFile(p)
        _k32.CloseHandle(h)


def read_status() -> dict | None:
    buf = read_shared(STATUS_MAP, STATUS_SIZE)
    return None if buf is None else parse_status(buf)


def read_dataset(dataset: str) -> dict | None:
    name = DATA_MAPS[dataset]
    hdr_buf = read_shared(name, DATA_HDR)
    if hdr_buf is None:
        return None
    hdr = parse_data_header(hdr_buf)
    n = max(0, min(hdr["n"], DATA_MAX_POINTS))
    buf = read_shared(name, DATA_HDR + 8 * n)
    hdr["y"] = np.frombuffer(buf, dtype="<f8", count=n, offset=DATA_HDR).copy()
    hdr["n"] = n
    return hdr


def find_gui_processes() -> list[dict]:
    _need_windows()
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq LWA_Control.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    procs = []
    for row in csv.reader(out.splitlines()):
        if len(row) >= 2 and row[0].lower() == "lwa_control.exe":
            procs.append({"pid": int(row[1]), "path": _process_path(int(row[1]))})
    return procs


def _process_path(pid: int) -> str | None:
    h = _k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        size = wt.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        return buf.value if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) else None
    finally:
        _k32.CloseHandle(h)


def list_windows(pid: int) -> list[dict]:
    """Top-level windows of a process: handle, class, title, visible."""
    _need_windows()
    out = []

    def cb(hwnd, _):
        p = wt.DWORD()
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid:
            t = ctypes.create_unicode_buffer(256)
            c = ctypes.create_unicode_buffer(256)
            _u32.GetWindowTextW(hwnd, t, 256)
            _u32.GetClassNameW(hwnd, c, 256)
            out.append({"hwnd": int(hwnd or 0), "class": c.value, "title": t.value,
                        "visible": bool(_u32.IsWindowVisible(hwnd))})
        return True

    _u32.EnumWindows(_WNDENUMPROC(cb), 0)
    return out


def window_pid(hwnd: int) -> int | None:
    if not hwnd or not _u32.IsWindow(hwnd):
        return None
    p = wt.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    return p.value


def find_gui_window(stored_hwnd: int) -> tuple[int, int, str]:
    """(hwnd, pid, how). Uses the handle the GUI stored in shared memory when it is still valid; otherwise the
    GUI's visible main window. (Seen on the lab PC: the stored handle was stale - the GUI recreates its main
    window after it has registered it - so HighFinesse's own lwaData.dll could not reach the GUI either.)"""
    procs = find_gui_processes()
    if not procs:
        raise LWAError("LWA_Control.exe is not running.")
    if len(procs) > 1:
        raise LWAError(f"{len(procs)} LWA_Control.exe instances running - close all but one.")
    pid = procs[0]["pid"]
    if window_pid(stored_hwnd) == pid:
        return stored_hwnd, pid, "stored handle"
    mains = [w for w in list_windows(pid) if w["visible"] and "Linewidth Analyzer" in w["title"]]
    if len(mains) != 1:
        raise LWAError(f"Cannot identify the GUI main window (stored handle 0x{stored_hwnd:X} is stale); "
                       f"windows of the GUI: {list_windows(pid)}")
    return mains[0]["hwnd"], pid, f"main window found by title (stored handle 0x{stored_hwnd:X} is stale)"


# =============================================================================
# The client
# =============================================================================
class LWA1k:
    """Remote control of a running LWA_Control.exe.

        lwa = LWA1k()                                   # connects (raises LWAError with a reason if it cannot)
        lwa.set_analyzer(cutoff='1kHz', power_mode='Fixed')
        lwa.set_evaluation(fit_function='Voigt')
        cap = lwa.capture(('noise', 'lineshape'))       # one single capture
        avg = lwa.capture_averaged(10, ('noise',))      # 10 captures averaged in Python
        print(lwa.read_settings())
    """

    def __init__(self, cmd_timeout_ms: int = 5000, raw_output: bool = True, verbose: bool = True,
                 allow_settings: bool = False):
        _need_windows()
        self.cmd_timeout_ms = cmd_timeout_ms
        self.verbose = verbose
        st = read_status()
        if st is None:
            raise LWAError("LWA_Control.exe is not running (no LWA_Status_Rec_map). Start it and wait until "
                           "Analyzer and Digitizer are connected.")
        if st["record_size"] != STATUS_SIZE:
            raise LWAError(f"Unexpected status record size {st['record_size']} - different GUI version?")
        self.hwnd, self.gui_pid, self.hwnd_source = find_gui_window(st["gui_hwnd"])
        self.gui_path = _process_path(self.gui_pid)
        if self.hwnd_source != "stored handle":
            self._log(f"GUI window 0x{self.hwnd:X}: {self.hwnd_source}")
        self.allow_settings = allow_settings
        self.binned = {}
        if raw_output:
            self.set_output_binning()           # full-resolution data, independent of the Display panel

    # ---- low level -----------------------------------------------------------
    def send(self, group: int, panel: int, row: int = 0, value: int = 0) -> int:
        res = ctypes.c_size_t(0)
        ok = _u32.SendMessageTimeoutW(self.hwnd, WM_LWA, (group << 16) | panel, lparam(row, value),
                                      0x0002, self.cmd_timeout_ms, ctypes.byref(res))   # SMTO_ABORTIFHUNG
        if not ok:
            raise LWAError(f"GUI did not answer command ({group},{panel},{row},{value}) within "
                           f"{self.cmd_timeout_ms} ms - busy or frozen?")
        return res.value

    def status(self) -> dict:
        st = read_status()
        if st is None:
            raise LWAError("GUI closed")
        return st

    def _log(self, *a):
        if self.verbose:
            print("[LWA]", *a)

    # ---- settings ------------------------------------------------------------
    def read_settings(self, refresh: bool = True) -> dict:
        """Instrument state, plus the remote module's copy of the Digitizer/Analyzer tables.
        CAUTION: in the GUI version on the lab PC that copy is never synchronised with the panels (all zeros),
        so 'digitizer'/'analyzer' do NOT show the real GUI settings - only 'states' is reliable."""
        st = self._refreshed_status() if refresh else self.status()
        return {"digitizer": decode_table(st["digitizer_raw"], DIGITIZER_ROWS),
                "analyzer": decode_table(st["analyzer_raw"], ANALYZER_ROWS),
                "states": st["states"], "states_nominal": states_nominal(st["states"]),
                "lineshape_time_int_s": st["time_int_s"]}

    def _refreshed_status(self) -> dict:
        for g in (G_DIGITIZER, G_ANALYZER):
            write_shared(STATUS_MAP, cell(g, 0) + 16, b"\x00")
        self.send(1, REQ_PUBLISH_DIGITIZER)
        self.send(1, REQ_PUBLISH_ANALYZER)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 2.0:
            st = self.status()
            if st["digitizer_new"][0] and st["analyzer_new"][0]:
                break
            time.sleep(0.05)
        return st

    def _set_rows(self, panel: int, rows: dict, settable: set | None, readback_group: int | None, **kw):
        if not self.allow_settings and any(v is not None for v in kw.values()):
            raise LWAError(SETTINGS_WARNING)
        changes = {}
        for name, val in kw.items():
            if val is None:
                continue
            if name not in rows:
                raise ValueError(f"unknown setting '{name}', choose from {list(rows)}")
            if settable is not None and name not in settable:
                raise LWAError(f"'{name}' cannot be changed remotely (the GUI ignores it) - set it in the GUI")
            row, opts = rows[name]
            changes[name] = (row, option_index(name, val, opts), val)
        for name, (row, idx, val) in changes.items():
            self.send(2, panel, row, idx)
            self._log(f"set {name} = {val}")
        if readback_group is None or not changes:
            return
        # Read back the table the GUI publishes. This confirms the GUI received and stored the value; that the
        # unit itself switched is visible in the GUI panel / front-panel LEDs (README verification step 5).
        t0 = time.monotonic()
        while True:
            raw = self._refreshed_status()["digitizer_raw" if readback_group == G_DIGITIZER else "analyzer_raw"]
            bad = {n: raw[r] for n, (r, i, _) in changes.items() if raw[r] != i}
            if not bad:
                return
            if time.monotonic() - t0 > 5:
                raise LWAError(f"GUI did not take over {bad} (read back as index). Is the unit connected?")
            time.sleep(0.3)

    def set_digitizer(self, range_V=None, range_Hz=None):
        """range_V: '10mV' ... '20V' or 'auto'; range_Hz: '60kHz' ... '30MHz'. Verified by read-back."""
        self._set_rows(PANEL_DIGITIZER, DIGITIZER_ROWS, DIGITIZER_SETTABLE, G_DIGITIZER,
                       range_V=range_V, range_Hz=range_Hz)

    def set_analyzer(self, noise_mode=None, cutoff=None, power_mode=None, pol_control=None):
        """noise_mode 'FN'/'RIN', cutoff '10Hz'/'1kHz'/'10kHz'/'100kHz', power_mode 'Fixed'/'Auto'/'Reset'.
        Only applied while the Analyzer is connected. Verified by read-back."""
        if any(v is not None for v in (noise_mode, cutoff, power_mode, pol_control)) and \
                self.status()["states"]["analyzer"] != 1:
            raise LWAError("Analyzer not connected (state != 1): the GUI would store but not apply the setting")
        if power_mode is not None and option_index("power_mode", power_mode, ANALYZER_ROWS["power_mode"][1]) == 2:
            readback = None             # 'Reset' is an action: the GUI may switch back to Fixed
        else:
            readback = G_ANALYZER
        self._set_rows(PANEL_ANALYZER, ANALYZER_ROWS, None, readback, noise_mode=noise_mode, cutoff=cutoff,
                       power_mode=power_mode, pol_control=pol_control)

    def set_evaluation(self, noise_autoeval=None, lineshape_autoeval=None, fit_mode=None, fit_function=None,
                       intrinsic=None, lineshape_time_int_s=None):
        """Evaluation panel. Cannot be read back - check the GUI once (README step 5).
        Note: capture() switches noise/lineshape Autoeval to match the requested datasets."""
        if lineshape_time_int_s is not None:
            if not self.allow_settings:
                raise LWAError(SETTINGS_WARNING)
            write_shared(STATUS_MAP, cell(G_MISC, 7) + 8, struct.pack("<d", float(lineshape_time_int_s)))
            self.send(2, PANEL_EVALUATION, 7, 3)
            self._log(f"set lineshape_time_int_s = {lineshape_time_int_s}")
        self._set_rows(PANEL_EVALUATION, {k: v for k, v in EVALUATION_ROWS.items() if v[1] != "float"},
                       None, None, noise_autoeval=noise_autoeval, lineshape_autoeval=lineshape_autoeval,
                       fit_mode=fit_mode, fit_function=fit_function, intrinsic=intrinsic)

    def set_output_binning(self, time_binned=False, noise_binned=False, lineshape_binned=False):
        """False = the full-resolution arrays (one point per FFT line), independent of the Display panel."""
        self.send(1, REQ_BINNING, 0, int(time_binned) | int(noise_binned) << 1 | int(lineshape_binned) << 2)
        self.binned = {"time": time_binned, "noise": noise_binned, "lineshape": lineshape_binned}

    def stop(self):
        self.send(2, PANEL_CAPTURE, 0, 0)

    # ---- acquisition ---------------------------------------------------------
    def capture(self, datasets=("noise",), timeout_s: float = 120.0, results: bool = True,
                continuous: bool = False) -> dict:
        """One capture. Requests `datasets`, starts a SINGLE run (even if the GUI's Continuous = On), waits for
        the evaluation and returns the data. Requesting 'noise'/'lineshape' also switches that Autoeval to
        Active, NOT requesting it switches it to Inactive (that is how the GUI implements the request)."""
        datasets = tuple(datasets)
        mask = sum(DATASET_BITS[d] for d in datasets)
        for i, d in enumerate(DATA_MAPS):                        # forget old 'new data' flags
            if d in datasets:
                write_shared(STATUS_MAP, OFF_READY + i, b"\x00")
        for i in range(5):                                       # ... and old result flags
            write_shared(STATUS_MAP, cell(G_RESULTS, i) + 16, b"\x00")
        t0 = time.time()
        self.send(1, REQ_DATA, 1 if continuous else 0, mask)
        deadline = time.monotonic() + timeout_s
        while True:
            st = self.status()
            if all(st["ready"][d] for d in datasets):
                break
            if time.monotonic() > deadline:
                raise LWAError(f"no data for {datasets} after {timeout_s:.0f} s (ready: {st['ready']}). "
                               "Is the GUI idle and the laser in range?")
            time.sleep(0.05)
        out = {"t_start": t0, "duration_s": time.time() - t0, "states": st["states"],
               "states_nominal": states_nominal(st["states"])}
        for i, d in enumerate(DATA_MAPS):
            if d in datasets:
                r = read_dataset(d)
                write_shared(STATUS_MAP, OFF_READY + i, b"\x00")
                r["binned"] = self.binned.get(d, False)
                r["x"] = (np.linspace(r["x_first"], r["x_last"], r["n"]) if r["n"] > 1 else
                          np.array([r["x_first"]]))
                if d == "noise":
                    if r["n"] and np.nanmax(r["y"]) < 0:          # RIN mode: published in dB/Hz
                        r["unit"] = "dB/Hz"
                    else:                                         # FN mode: published as AMPLITUDE (Hz/rtHz)
                        r["y_published"] = r["y"]                 # (verified: GUI export = published^2)
                        r["y"] = r["y"] ** 2
                        r["unit"] = "Hz2/Hz"
                out[d] = r
        if results:
            out["results"] = self.read_results()
        return out

    def read_results(self, timeout_s: float = 1.0, require_new: bool = True) -> dict:
        """The GUI's result slots, written by the GUI itself after each evaluation (with a 'new' flag):
        effective_beta_Hz, lineshape fit voigt_fwhm_Hz / lorentz_width_Hz / gauss_width_Hz, and
        intrinsic_display_Hz (100 = the '<0.1 kHz' display limit; the real intrinsic value is NOT published).
        capture() clears the flags before it starts, so require_new=True returns only this capture's values
        (None = not updated, e.g. lineshape fit when lineshape is not evaluated).
        NOTE: never send REQ_PUBLISH_RESULTS - it makes the GUI overwrite the slots with its unsynced zero table."""
        t0 = time.monotonic()
        st = self.status()
        while not st["results_new"][1] and time.monotonic() - t0 < timeout_s:
            time.sleep(0.02)
            st = self.status()
        return {k: (None if (v == -1.0 or (require_new and not new)) else v)
                for k, v, new in zip(RESULT_LABELS, st["results"], st["results_new"])}

    def capture_averaged(self, n: int, datasets=("noise",), timeout_s: float = 120.0,
                         on_capture=None, scales: dict | None = None, mode: str = "power") -> dict:
        """n captures averaged in linear power (see average_captures). Equivalent to the GUI's Averaging = n,
        but every capture is kept and there is no dB-averaging bias.
        Measured on the instrument (GUI in continuous capture): ~0.45 s per capture, n = 10 in 4.4 s."""
        caps = []
        for k in range(n):
            c = self.capture(datasets, timeout_s)
            caps.append(c)
            if on_capture:
                on_capture(k, c)
        return average_captures(caps, datasets, scales, mode)


# =============================================================================
# Averaging and analysis (pure numpy - testable without the instrument)
# =============================================================================
def detect_scale(y: np.ndarray, unit: str | None = None) -> str:
    """'db' for RIN data (dB/Hz, detected by negative values), else 'power' (Hz^2/Hz)."""
    return "db" if np.nanmax(y) < 0 else "power"


def average_captures(caps: list, datasets, scales: dict | None = None, mode: str = "power") -> dict:
    """Average n captures.
    mode='power' (default, unbiased): linear power - FN (Hz^2/Hz) directly, RIN (dB) via 10^(y/10).
    mode='gui': exactly what the GUI's Averaging does (measured 2026-10-21) - FN: amplitude average
      (mean of sqrt(S))^2, which reads (pi/4 + (1-pi/4)/n) low (0.807 = -0.93 dB at n = 10);
      RIN: mean of the dB values, -2.17 dB at n = 10 (-2.33 dB at n = 20) relative to power: Gamma(1+1/n)^n.
    'std' = spread between captures; 'all' keeps every capture."""
    scales = scales or {}
    out = {"n": len(caps), "captures": caps, "t_start": caps[0]["t_start"],
           "duration_s": sum(c["duration_s"] for c in caps),
           "states_nominal": all(c["states_nominal"] for c in caps)}
    for d in datasets:
        x0 = caps[0][d]["x"]
        ys = []
        for c in caps:
            x, y = c[d]["x"], c[d]["y"]
            ys.append(y if (len(x) == len(x0) and np.allclose(x, x0)) else np.interp(x0, x, y))
        Y = np.vstack(ys)
        sc = scales.get(d, "auto")
        if sc == "auto":
            sc = detect_scale(Y[0])
        if sc == "db":
            mean = np.mean(Y, axis=0) if mode == "gui" else 10 * np.log10(np.mean(10 ** (Y / 10), axis=0))
        else:
            mean = np.mean(np.sqrt(Y), axis=0) ** 2 if (mode == "gui" and d == "noise") else Y.mean(axis=0)
        out[d] = {"x": x0, "y": mean, "scale": sc, "averaging": mode, "all": Y,
                  "unit": caps[0][d].get("unit"),
                  "std": Y.std(axis=0, ddof=1) if len(caps) > 1 else np.zeros_like(x0)}
    res = [c.get("results") or {} for c in caps]
    if res and res[0]:
        out["results"] = {}
        for k in RESULT_LABELS:
            vals = np.array([r.get(k) for r in res if r.get(k) is not None], dtype=float)
            out["results"][k] = {"mean": float(vals.mean()) if len(vals) else None,
                                 "std": float(vals.std(ddof=1)) if len(vals) > 1 else None,
                                 "values": vals.tolist()}
    return out


def to_hz2_per_hz(y: np.ndarray, unit: str) -> np.ndarray:
    """Frequency-noise density in Hz^2/Hz from the published unit."""
    if unit in ("Hz2/Hz", "Hz^2/Hz"):
        return y
    if unit in ("Hz/rtHz", "Hz/sqrtHz"):
        return y ** 2
    raise ValueError("unit must be 'Hz2/Hz' or 'Hz/rtHz' (FN data are published in Hz/rtHz)")


def intrinsic_linewidth(f, s_hz2, floor_range=(5e6, 6e6)) -> float:
    """pi x white frequency-noise floor (same as HighFinesse_FN.get_data in u_shaped_lib)."""
    m = (f > floor_range[0]) & (f < floor_range[1])
    return float(np.pi * np.mean(s_hz2[m])) if m.any() else float("nan")


def beta_separation_linewidth(f, s_hz2, f_min=None) -> float:
    """Effective linewidth sqrt(8 ln2 * sum of S*df over the bins above the beta line 8 ln2 f / pi^2)
    (Di Domenico 2010). Rectangle sum over the FFT bins exactly as the GUI does it: reproduces the GUI's
    'Effective (beta)' to 1e-9 on the same spectrum (verified 2026-10-21)."""
    m = s_hz2 > 8 * np.log(2) * f / np.pi ** 2
    if f_min is not None:
        m &= f >= f_min
    if not m.any():
        return float("nan")
    df = (f[-1] - f[0]) / (len(f) - 1)
    return float(np.sqrt(8 * np.log(2) * np.sum(s_hz2[m]) * df))


def intrinsic_mode_amplitude(f, s_hz2, floor_range=(1e6, 1e7), bins=500) -> float:
    """GUI-like 'Mode(stat)' estimate: pi * (mode of the histogram of the AMPLITUDE sqrt(S))^2 in floor_range.
    For a single capture this is ~ pi*S0/2 (Rayleigh mode) - about HALF of intrinsic_linewidth(); it matched the
    GUI's Intrinsic within the histogram spread (36.9 vs 34.3 Hz, 32.6 vs 30.6 Hz, 2026-10-21)."""
    m = (f > floor_range[0]) & (f < floor_range[1])
    if m.sum() < 10:
        return float("nan")
    h, e = np.histogram(np.sqrt(s_hz2[m]), bins=bins)
    k = int(np.argmax(h))
    return float(np.pi * ((e[k] + e[k + 1]) / 2) ** 2)


def guess_noise_unit(f, y, gui_intrinsic, floor_range=(5e6, 6e6)) -> str | None:
    """Which unit makes pi*floor agree with the GUI's intrinsic linewidth?"""
    if not gui_intrinsic or gui_intrinsic <= 0:
        return None
    cand = {u: intrinsic_linewidth(f, to_hz2_per_hz(y, u), floor_range) for u in ("Hz2/Hz", "Hz/rtHz")}
    err = {u: abs(np.log(v / gui_intrinsic)) if v > 0 else np.inf for u, v in cand.items()}
    return min(err, key=err.get)


def log_bin(x, y, bins_per_decade=20):
    """Average y (linear) in logarithmic x bins - like the binned RIN files."""
    m = x > 0
    x, y = x[m], y[m]
    if len(x) < 2:
        return x, y
    lo = np.floor(np.log10(x.min()) * bins_per_decade)
    hi = np.ceil(np.log10(x.max()) * bins_per_decade)
    edges = 10 ** (np.arange(lo, hi + 1) / bins_per_decade)
    idx = np.digitize(x, edges)                      # bin k holds edges[k-1] <= x < edges[k]
    xb, yb = [], []
    for k in np.unique(idx):
        s = idx == k
        xb.append(np.sqrt(edges[k - 1] * edges[k]) if 1 <= k < len(edges) else x[s].mean())
        yb.append(y[s].mean())
    return np.array(xb), np.array(yb)


# =============================================================================
# Saving
# =============================================================================
# =============================================================================
# HDF5 files (repo convention: compressed data are saved as .h5, not .npz / data .csv)
# =============================================================================
def _h5py():
    try:
        import h5py
        return h5py
    except ImportError:
        raise LWAError("h5py is not installed:  py -3 -m pip install h5py")


def _h5_set_attrs(obj, attrs: dict):
    for k, v in attrs.items():
        if v is None:
            obj.attrs[k] = "None"
        elif isinstance(v, (bool, np.bool_)):
            obj.attrs[k] = bool(v)
        elif isinstance(v, (int, float, str, np.integer, np.floating)):
            obj.attrs[k] = v
        elif isinstance(v, (dict, list, tuple)):
            obj.attrs[k] = json.dumps(v, default=str)
        else:
            obj.attrs[k] = str(v)


def _h5_write_tree(g, tree: dict):
    for k, v in tree.items():
        if v is None or k == "_attrs":
            continue
        if isinstance(v, dict):
            sub = g.create_group(k)
            _h5_set_attrs(sub, v.get("_attrs", {}))
            _h5_write_tree(sub, v)
            continue
        arr = np.asarray(v)
        if arr.dtype.kind in "fiub":
            big = arr.size > 64
            g.create_dataset(k, data=arr, **(dict(compression="gzip", compression_opts=4, shuffle=True)
                                               if big else {}))
        else:
            g.attrs[k] = str(v)


def write_h5(path, tree: dict, attrs: dict | None = None):
    """Nested dict -> HDF5: dicts become groups (their '_attrs' dict -> attributes), numeric arrays become
    gzip-compressed datasets, other values attributes. Viewable directly in VS Code with an HDF5 viewer."""
    h5py = _h5py()
    with h5py.File(path, "w") as f:
        _h5_set_attrs(f, attrs or {})
        _h5_write_tree(f, tree)


def read_h5(path) -> dict:
    """HDF5 -> nested dict ({'_attrs': {...}} per group), for analysis and tests."""
    h5py = _h5py()

    def walk(g):
        out = {"_attrs": {k: (v.decode() if isinstance(v, bytes) else v) for k, v in g.attrs.items()}}
        for k, v in g.items():
            out[k] = walk(v) if isinstance(v, h5py.Group) else v[()]
        return out

    with h5py.File(path, "r") as f:
        return walk(f)


def load_h5_xy(spec: str) -> np.ndarray:
    """'file.h5' or 'file.h5::group/dataset' -> (N, 2) array [x, y]; x = the 'x' dataset of the same group.
    Default dataset: noise/mean (measurement files), else noise/last (probe files)."""
    h5py = _h5py()
    path, _, ds = spec.partition("::")
    with h5py.File(path, "r") as f:
        if not ds:
            ds = next((c for c in ("noise/mean", "noise/last", "noise/y") if c in f), None)
            if ds is None:
                raise ValueError(f"{path}: give a dataset, e.g. {path}::noise/mean  (contents: {list(f)})")
        y = f[ds][()]
        if y.ndim != 1:
            raise ValueError(f"{spec} is {y.shape}; pick a 1-D dataset (e.g. noise/mean, noise/last)")
        x = f[ds.rsplit("/", 1)[0] + "/x" if "/" in ds else "x"][()]
    return np.column_stack([x, y])


def save_measurement(folder: Path, stem: str, meas: dict, datasets, settings: dict, extra_meta: dict,
                     noise_unit: str = "Hz2/Hz", bins_per_decade: int = 20, save_all: bool = True,
                     floor_range=(5e6, 6e6)) -> dict:
    """Writes <stem>.h5 (everything: x, mean, std, every capture, binned spectrum, GUI results per capture,
    analysis and metadata as attributes) and <stem>_PSD.txt / _RIN.txt (GUI export format for lwa_lib /
    rin_utils). Returns the metadata dict (incl. 'analysis')."""
    folder.mkdir(parents=True, exist_ok=True)
    summary, tree = {}, {}
    for d in datasets:
        r = meas[d]
        unit = r.get("unit") or ("dB/Hz" if r.get("scale") == "db" else "published unit")
        g = {"_attrs": {"unit": unit, "averaging": r.get("averaging", "power"), "scale": r.get("scale"),
                        "n_captures": int(meas.get("n", 1)),
                        "x_unit": "Hz (Fourier frequency)" if d == "noise" else
                                  ("Hz (offset)" if d == "lineshape" else "s")},
             "x": r["x"], "mean": r["y"], "std": r.get("std")}
        if save_all and "all" in r:
            g["captures"] = r["all"]
        if d == "noise":
            if r.get("scale", detect_scale(r["y"])) != "db":                      # FN: Hz^2/Hz since capture()
                s = r["y"]
                xb, sb = log_bin(r["x"], s, bins_per_decade)
                g["binned"] = {"_attrs": {"unit": "Hz2/Hz", "bins_per_decade": bins_per_decade,
                                          "method": "linear mean per log bin"}, "x": xb, "y": sb}
                summary["intrinsic_linewidth_Hz_python"] = intrinsic_linewidth(r["x"], s, floor_range)
                summary["intrinsic_GUI_like_mode_Hz_python"] = intrinsic_mode_amplitude(r["x"], s)
                summary["effective_linewidth_Hz_python_beta"] = beta_separation_linewidth(r["x"], s)
            else:                                                                 # RIN: dB/Hz
                xb, pb = log_bin(r["x"], 10 ** (r["y"] / 10), bins_per_decade)
                g["binned"] = {"_attrs": {"unit": "dB/Hz", "bins_per_decade": bins_per_decade,
                                          "method": "linear-power mean per log bin, then dB"},
                               "x": xb, "y": 10 * np.log10(pb)}
            write_gui_format(folder / f"{stem}_{'PSD' if r.get('scale') != 'db' else 'RIN'}.txt", r["x"], r["y"],
                             fn=r.get("scale") != "db", n_avg=meas.get("n", 1), averaging=r.get("averaging", "power"),
                             effective=summary.get("effective_linewidth_Hz_python_beta"),
                             intrinsic=summary.get("intrinsic_linewidth_Hz_python"), t=meas["t_start"])
        tree[d] = g
    caps = meas.get("captures") or []
    if caps:
        tree["capture_info"] = {"_attrs": {"note": "one entry per capture"},
                                "t_start_unix_s": np.array([c["t_start"] for c in caps]),
                                "duration_s": np.array([c["duration_s"] for c in caps]),
                                "states_nominal": np.array([bool(c["states_nominal"]) for c in caps])}
        tree["gui_results"] = {"_attrs": {"note": "GUI result slots per capture (NaN = not updated); Effective (beta) "
                                                  "matches the GUI exactly; Intrinsic is not published by the GUI"},
                               **{k: np.array([(c.get("results") or {}).get(k) if (c.get("results") or {}).get(k)
                                               is not None else np.nan for c in caps], dtype=float)
                                  for k in RESULT_LABELS}}
    meta = {"stem": stem, "timestamp": _dt.datetime.fromtimestamp(meas["t_start"]).isoformat(),
            "n_averaged": meas.get("n", 1), "duration_s": meas["duration_s"],
            "states_nominal": meas["states_nominal"], "gui_results": meas.get("results"),
            "analysis": summary, "units": "noise: Hz2/Hz (FN) or dB/Hz (RIN)", "floor_range_Hz": list(floor_range),
            "settings_read_back": settings, **extra_meta,
            "points": {d: int(len(meas[d]["y"])) for d in datasets}, "created_by": "lwa_utils.py"}
    attrs = {k: v for k, v in meta.items() if k != "analysis"}
    attrs.update(summary)                                    # linewidths as plain root attributes
    write_h5(folder / f"{stem}.h5", tree, attrs)
    return meta


def write_gui_format(path, x, y, fn=True, n_avg=1, averaging="power", effective=None, intrinsic=None, t=None):
    """Same layout as the GUI's 'File > Save > Rawdata' (12 '#' lines + column header), so the repo's
    lwa_lib.LWA / HighFinesse_FN.get_data read it unchanged. Effective = Python beta (= GUI formula),
    Intrinsic = pi * mean white-noise floor (the GUI's Mode(stat) value is not published)."""
    ts = _dt.datetime.fromtimestamp(t or time.time()).strftime("%H:%M:%S")
    dB_like = averaging == "gui"                     # reproduces the GUI's (dB / amplitude) averaging
    res = (x[-1] - x[0]) / (len(x) - 1) if len(x) > 1 else 0
    hdr = ["#Device=LWA-1k 1550 (captured with lwa_utils.py)", "#Datatype=Frequencynoise", f"#Timestamp={ts}",
           "#OpticalPower=n/a", f"#Outputmode={'FN' if fn else 'RIN'} mode", "#Range[V]=n/a",
           f"#Range[Hz]={res:.0f}",
           # Averaging / Av count follow the GUI's meaning (dB-averaged for RIN): Bias_tee/rin_utils.hf_av_count adds
           # its dB-averaging correction from them. A Python linear-power average needs NO correction -> 0 / 0.
           f"#Averaging={1 if (dB_like and n_avg > 1) else 0}",
           f"#Av count= {n_avg if (dB_like and n_avg > 1) else 0}",
           f"#Binning mode=raw; Python {averaging} average of {n_avg} capture(s)",
           f"#Effective: {effective if effective is not None else float('nan')}Hz",
           f"#Intrinsic: {intrinsic if intrinsic is not None else float('nan')}Hz",
           "Frequency [Hz],Frequency noise density [Hz\u00b2 / Hz]" if fn else
           "Frequency [Hz],Intensity noise density [dB / Hz]"]
    with open(path, "w", encoding="latin-1", newline="\r\n") as f:
        f.write("\n".join(hdr) + "\n")
        for a, b in zip(x, y):
            f.write(f"{float(a):.5f},{float(b)!r}\n")


def plot_measurement(meas: dict, datasets, noise_unit: str, title: str = "", path_stem: Path | None = None,
                     show: bool = True):
    import matplotlib.pyplot as plt
    n = len([d for d in datasets if d in ("noise", "lineshape")])
    if n == 0:
        return
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 4.5), squeeze=False)
    k = 0
    if "noise" in datasets:
        ax = axes[0, k]; k += 1
        r = meas["noise"]
        f = r["x"]
        m = f > 0
        if r.get("scale", detect_scale(r["y"])) == "db":                       # RIN mode
            ax.semilogx(f[m], r["y"][m], lw=0.6, label=f"mean of {meas.get('n', 1)} (linear power)")
            ax.set_ylabel("RIN [dB/Hz]")
        else:
            s = r["y"]                                                      # Hz^2/Hz since capture()
            ax.loglog(f[m], s[m], lw=0.6, label=f"mean of {meas.get('n', 1)}")
            ax.loglog(f[m], 8 * np.log(2) * f[m] / np.pi ** 2, "r--", lw=1, label="beta line")
            ax.set_ylabel("FN PSD [Hz$^2$/Hz]")
        ax.set_xlabel("Fourier frequency [Hz]")
        ax.legend(); ax.grid(True, which="both", alpha=0.3)
    if "lineshape" in datasets:
        ax = axes[0, k]
        r = meas["lineshape"]
        ax.semilogy(r["x"], np.abs(r["y"]), lw=0.6)
        ax.set_xlabel("Frequency offset [Hz]"); ax.set_ylabel("Lineshape [a.u.]")
        ax.grid(True, alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    if path_stem:
        for ext in ("png", "pdf"):
            fig.savefig(f"{path_stem}.{ext}", dpi=150)
    if show:
        plt.show(block=False); plt.pause(0.1)
    else:
        plt.close(fig)


# =============================================================================
# Diagnostics (CLI)
# =============================================================================
def _p(ok, msg):
    print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")
    return ok


def cmd_check(args) -> int:
    """Read-only staged test. Does not change any setting and does not start a capture."""
    print("LWA-1k connection check (read-only)\n1. Environment")
    if not _p(IS_WINDOWS, "Windows"):
        return 1
    if not _p(struct.calcsize("P") == 8, f"64-bit Python {sys.version.split()[0]}"):
        return 1
    try:
        _p(True, f"h5py {_h5py().__version__} (data files are saved as .h5)")
    except LWAError as e:
        _p(False, str(e))
    print("2. GUI process")
    procs = find_gui_processes()
    if not _p(len(procs) == 1, f"exactly one LWA_Control.exe running: {procs}"):
        return 1
    print("3. Shared memory")
    st = read_status()
    if not _p(st is not None, "LWA_Status_Rec_map exists"):
        return 1
    _p(st["record_size"] == STATUS_SIZE, f"record size {st['record_size']} (expected {STATUS_SIZE})")
    stored_ok = window_pid(st["gui_hwnd"]) == procs[0]["pid"]
    _p(stored_ok, f"handle stored by the GUI 0x{st['gui_hwnd']:X} is a live window of the GUI")
    print("         GUI windows:")
    for w in list_windows(procs[0]["pid"]):
        print(f"           0x{w['hwnd']:X}  visible={w['visible']!s:5}  class={w['class']!r}  title={w['title']!r}")
    try:
        hwnd, _, how = find_gui_window(st["gui_hwnd"])
        _p(True, f"commands will go to 0x{hwnd:X} ({how})")
    except LWAError as e:
        _p(False, str(e))
    for d in DATA_MAPS:
        h = read_shared(DATA_MAPS[d], DATA_HDR)
        if _p(h is not None, f"{DATA_MAPS[d]} exists"):
            hd = parse_data_header(h)
            print(f"           last published: n={hd['n']} x={hd['x_first']:.6g}..{hd['x_last']:.6g} "
                  f"ready={st['ready'][d]} count={st['counts'][d]}")
    print("         status record as last published: digitizer", st["digitizer_raw"], "analyzer",
          st["analyzer_raw"], "results", [round(v, 3) for v in st["results"]])
    print("4. Instrument state (as published by the GUI)")
    for k, v in st["states"].items():
        nom = STATE_NOMINAL.get(k)
        print(f"         {k:12s} = {v}" + ("" if nom is None else ("   nominal" if v == nom else f"   (nominal {nom})")))
    _p(states_nominal(st["states"]), "all states nominal - compare with the GUI status panel")
    print("5. Optional cross-check with HighFinesse's lwaData.dll")
    _dll_crosscheck(procs[0]["path"], st)
    print("\nRead-only check done. Next: `python lwa_utils.py settings` (asks the GUI to publish its settings).")
    return 0


def _dll_crosscheck(gui_path, st):
    try:
        folder = Path(gui_path).parent if gui_path else None
        dll = folder / "lwaData.dll" if folder else None
        if not dll or not dll.is_file():
            print("         lwaData.dll not next to the GUI - skipped")
            return
        os.add_dll_directory(str(folder))
        lib = ctypes.CDLL(str(dll))
        lib.Init.restype = ctypes.c_int
        if not _p(lib.Init() == 0, "lwaData.dll Init() == 0"):
            return
        names = ["GetDigitizerState", "GetAnalyzerState", "GetNoiseLevel", "GetRangeLevel", "GetPowerLevel",
                 "GetPowerState", "GetPolControlState"]
        for item, fn in zip(STATE_ITEMS, names):
            v = ctypes.c_int(-999)
            getattr(lib, fn)(ctypes.byref(v))
            _p(v.value == st["states"][item], f"{item:12s} DLL={v.value} python={st['states'][item]}")
        lib.close()
    except Exception as e:  # noqa: BLE001
        print(f"         DLL cross-check not possible: {e}")


def _elevation(pid: int | None = None):
    """True/False = process token elevated, None = cannot tell (access denied -> usually elevated)."""
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
    adv.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
    _k32.GetCurrentProcess.restype = wt.HANDLE
    hp = _k32.GetCurrentProcess() if pid is None else _k32.OpenProcess(0x1000, False, pid)
    if not hp:
        return None
    tok = wt.HANDLE()
    if not adv.OpenProcessToken(hp, 0x0008, ctypes.byref(tok)):      # TOKEN_QUERY
        return None
    val, ret = wt.DWORD(), wt.DWORD()
    ok = adv.GetTokenInformation(tok, 20, ctypes.byref(val), 4, ctypes.byref(ret))   # TokenElevation
    _k32.CloseHandle(tok)
    return bool(val.value) if ok else None


def cmd_ping(args) -> int:
    """Send only the harmless 'publish Digitizer/Analyzer settings' requests and report every detail."""
    st = read_status()
    if st is None:
        print("GUI not running"); return 1
    hwnd, pid, how = find_gui_window(st["gui_hwnd"])
    print(f"target window 0x{hwnd:X} ({how}), GUI pid {pid}")
    print(f"this Python elevated: {_elevation()}   GUI elevated: {_elevation(pid)} (None = access denied)")
    _u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    for method in ("SendMessageTimeout", "PostMessage"):
        for g in (G_DIGITIZER, G_ANALYZER):
            write_shared(STATUS_MAP, cell(g, 0) + 16, b"\x00")
        ctypes.set_last_error(0)
        if method == "PostMessage":
            r1 = _u32.PostMessageW(hwnd, WM_LWA, (1 << 16) | REQ_PUBLISH_DIGITIZER, 0)
            r2 = _u32.PostMessageW(hwnd, WM_LWA, (1 << 16) | REQ_PUBLISH_ANALYZER, 0)
        else:
            res = ctypes.c_size_t(0)
            r1 = _u32.SendMessageTimeoutW(hwnd, WM_LWA, (1 << 16) | REQ_PUBLISH_DIGITIZER, 0, 2, 3000,
                                          ctypes.byref(res))
            r2 = _u32.SendMessageTimeoutW(hwnd, WM_LWA, (1 << 16) | REQ_PUBLISH_ANALYZER, 0, 2, 3000,
                                          ctypes.byref(res))
        err = ctypes.get_last_error()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 3:
            s2 = read_status()
            if s2["digitizer_new"][0] or s2["analyzer_new"][0]:
                break
            time.sleep(0.05)
        print(f"{method:18s} returns {r1},{r2}  last error {err}  -> new flags dig={s2['digitizer_new'][0]} "
              f"ana={s2['analyzer_new'][0]} after {time.monotonic() - t0:.2f} s")
        print(f"{'':18s} digitizer {decode_table(s2['digitizer_raw'], DIGITIZER_ROWS)}")
        print(f"{'':18s} analyzer  {decode_table(s2['analyzer_raw'], ANALYZER_ROWS)}")
    return 0


def cmd_dump(args) -> int:
    """Every cell of the status record (int / double / new flag), plus the raw header bytes."""
    buf = read_shared(STATUS_MAP, STATUS_SIZE)
    if buf is None:
        print("GUI not running"); return 1
    print("header bytes 0x00-0x2F:", buf[:0x30].hex(" "))
    for g in range(5):
        for i in range(13):
            o = cell(g, i)
            iv = struct.unpack_from("<i", buf, o)[0]
            dv = struct.unpack_from("<d", buf, o + 8)[0]
            if iv or dv or buf[o + 16] or buf[o + 4:o + 8] != b"\0\0\0\0":
                print(f"group {g} item {i:2d} @0x{o:03X}: int={iv:<8d} pad={buf[o+4:o+8].hex()} "
                      f"double={dv:<14.6g} new={buf[o+16]} rest={buf[o+17:o+24].hex()}")
    return 0


def cmd_snapshot(args) -> int:
    """Read-only: save whatever the GUI last published (data + results), without sending anything."""
    st = read_status()
    if st is None:
        print("GUI not running"); return 1
    print("results slots:", st["results"], "new:", st["results_new"])
    print("states:", st["states"], "ready:", st["ready"], "counts:", st["counts"])
    tree = {}
    for d in DATA_MAPS:
        r = read_dataset(d)
        if not r or r["n"] == 0:
            print(f"{d}: nothing published"); continue
        x = np.linspace(r["x_first"], r["x_last"], r["n"])
        tree[d] = {"_attrs": {"unit": "as published (FN: Hz/rtHz, RIN: dB/Hz)"}, "x": x, "y": r["y"]}
        print(f"{d}: n={r['n']} x={r['x_first']:.8g}..{r['x_last']:.8g}")
    tree["gui_results"] = {k: np.array([v]) for k, v in zip(RESULT_LABELS, st["results"])}
    write_h5("snapshot.h5", tree, {"created": _dt.datetime.now().isoformat(), "states": st["states"]})
    print("-> snapshot.h5")
    return 0


def cmd_settings(args) -> int:
    lwa = LWA1k(raw_output=False, verbose=False)
    print(json.dumps(lwa.read_settings(), indent=2))
    return 0


def cmd_set(args) -> int:
    if not args.allow_settings:
        print(SETTINGS_WARNING)
        return 1
    lwa = LWA1k(raw_output=False, allow_settings=True)
    groups = {"digitizer": {}, "analyzer": {}, "evaluation": {}}
    for item in args.assignments:
        key, _, val = item.partition("=")
        panel, _, name = key.partition(".")
        if panel not in groups or not name or not val:
            raise SystemExit(f"use panel.name=value, panel in {list(groups)}: {item}")
        groups[panel][name] = float(val) if name.endswith("_s") else (int(val) if val.isdigit() else val)
    if groups["digitizer"]:
        lwa.set_digitizer(**groups["digitizer"])
    if groups["analyzer"]:
        lwa.set_analyzer(**groups["analyzer"])
    if groups["evaluation"]:
        lwa.set_evaluation(**groups["evaluation"])
    print(json.dumps(lwa.read_settings(), indent=2))
    return 0


def cmd_probe(args) -> int:
    """One capture with every step logged (probe_log.json)."""
    log = {"started": _dt.datetime.now().isoformat(), "steps": []}

    def step(_step, **kw):
        e = {"t": round(time.monotonic() - t0, 3), "step": _step, **kw}
        log["steps"].append(e)
        print(json.dumps(e, default=str)[:400])

    t0 = time.monotonic()
    lwa = LWA1k(raw_output=True)
    step("connected", hwnd=hex(lwa.hwnd), gui=lwa.gui_path)
    step("settings", **lwa.read_settings())
    ok = False
    try:
        ds = tuple(args.datasets.split(","))
        caps = []
        t_series = time.monotonic()
        for k in range(args.repeat):
            c = lwa.capture(ds, timeout_s=args.timeout)
            caps.append(c)
            step("capture", index=k + 1, duration_s=round(c["duration_s"], 2), states=c["states"],
                 results=c.get("results"))
        if args.repeat > 1:
            d = [c["duration_s"] for c in caps]
            step("timing", n=args.repeat, total_s=round(time.monotonic() - t_series, 2),
                 per_capture_mean_s=round(float(np.mean(d)), 3), min_s=round(min(d), 3), max_s=round(max(d), 3))
        cap = caps[0]
        for d in ds:
            r = cap[d]
            step("dataset", name=d, n=r["n"], x_first=r["x_first"], x_last=r["x_last"],
                 dx=(r["x_last"] - r["x_first"]) / max(r["n"] - 1, 1), y_min=float(np.min(r["y"])),
                 y_max=float(np.max(r["y"])), first=r["y"][:4].tolist())
        tree = {}
        for d in ds:
            all_y = np.vstack([c[d]["y"] for c in caps])
            g = {"_attrs": {"unit": cap[d].get("unit", ""), "n_captures": len(caps),
                            "mean_method": "linear-power average (dB data via 10^(x/10))"},
                 "x": cap[d]["x"], "captures": all_y, "first": all_y[0], "last": all_y[-1]}
            if len(caps) > 1:
                g["mean"] = average_captures(caps, (d,))[d]["y"]
            tree[d] = g
        if "noise" in ds:
            step("noise_unit", unit=cap["noise"].get("unit"),
                 note="FN data are converted from the published Hz/rtHz to Hz^2/Hz on capture")
        tree["capture_info"] = {"t_start_unix_s": np.array([c["t_start"] for c in caps]),
                                "duration_s": np.array([c["duration_s"] for c in caps])}
        tree["gui_results"] = {k: np.array([(c.get("results") or {}).get(k) if (c.get("results") or {}).get(k)
                                            is not None else np.nan for c in caps], dtype=float)
                               for k in RESULT_LABELS}
        write_h5("probe.h5", tree, {"created": _dt.datetime.now().isoformat(), "gui": lwa.gui_path,
                                    "datasets": list(ds), "note": "compare/level: probe.h5::noise/last, ::noise/mean"})
        step("saved", file="probe.h5", datasets=["<d>/x", "<d>/captures", "<d>/first", "<d>/last", "<d>/mean"])
        ok = True
    except Exception as e:  # noqa: BLE001
        step("error", type=type(e).__name__, msg=str(e))
    finally:
        Path(args.log).write_text(json.dumps(log, indent=2, default=str))
    print(f"\nProbe {'finished' if ok else 'FAILED'} - log in {args.log}")
    return 0 if ok else 1


def load_xy(path: str) -> np.ndarray:
    """Two numeric columns from a GUI export, our .h5 ('file.h5' or 'file.h5::noise/last') or a CSV
    (any delimiter, decimal comma, header lines)."""
    if path.partition("::")[0].lower().endswith((".h5", ".hdf5")):
        return load_h5_xy(path)
    if path.endswith(".npy"):
        return np.load(path)
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        s = line.strip()
        if not s:
            continue
        for delim in ("\t", ";", ":", ",", None):
            parts = s.split(delim) if delim else s.split()
            if len(parts) < 2:
                continue
            try:
                rows.append([float(p.strip().replace(",", ".")) if delim != "," else float(p) for p in parts][:2])
                break
            except ValueError:
                continue
    if not rows:
        raise ValueError(f"no numeric data in {path}")
    return np.asarray(rows, dtype=float)


def cmd_compare(args) -> int:
    ref, test = load_xy(args.gui_file), load_xy(args.python_file)
    if args.square:
        test[:, 1] = test[:, 1] ** 2
    print(f"GUI export : {len(ref):8d} points, x {ref[0, 0]:.6g} .. {ref[-1, 0]:.6g}")
    print(f"Python     : {len(test):8d} points, x {test[0, 0]:.6g} .. {test[-1, 0]:.6g}")
    if len(ref) == len(test):
        rel = lambda a, b: np.max(np.abs(a - b) / np.maximum(np.abs(a), 1e-30))  # noqa: E731
        dx, dy = rel(ref[:, 0], test[:, 0]), rel(ref[:, 1], test[:, 1])
        print(f"max relative difference  x: {dx:.3e}   y: {dy:.3e}")
        ok = dx < args.rtol and dy < args.rtol
    else:
        lo, hi = max(ref[0, 0], test[0, 0]), min(ref[-1, 0], test[-1, 0])
        m = (ref[:, 0] >= lo) & (ref[:, 0] <= hi)
        yi = np.interp(ref[m, 0], test[:, 0], test[:, 1])
        r = np.abs(yi - ref[m, 1]) / np.maximum(np.abs(ref[m, 1]), 1e-30)
        print(f"different point counts - interpolated: median rel. diff {np.median(r):.3e}, "
              f"95th pct {np.percentile(r, 95):.3e}")
        ok = np.median(r) < max(args.rtol, 1e-3)
    if not ok and not args.square:
        print("Mismatch: if the GUI file is in Hz^2/Hz and ours in Hz/rtHz, retry with --square")
    eff = None
    for line in Path(args.gui_file).read_text(encoding="latin-1", errors="replace").splitlines()[:15]:
        if line.startswith("#Effective:"):
            eff = float(line.split(":")[1].strip().replace("Hz", "").replace(",", "."))
    if eff is not None and np.nanmin(test[:, 1]) >= 0:
        py = beta_separation_linewidth(test[:, 0], test[:, 1])
        ok_e = abs(py - eff) <= 1e-5 * max(abs(eff), 1)
        print(f"Effective (beta): GUI header {eff:.6f} Hz | Python on the Python file {py:.6f} Hz -> "
              f"{'MATCH' if ok_e else 'MISMATCH'}")
        ok = ok and ok_e
    print("RESULT:", "MATCH" if ok else "MISMATCH")
    return 0 if ok else 1


def cmd_level(args) -> int:
    """Level difference B - A in dB between two spectra (GUI export .txt, our .csv / _PSD.txt / _RIN.txt).
    dB files (RIN) are converted to linear power first; FN files must both be in Hz^2/Hz (GUI exports and all
    files written by this module are). Both spectra are averaged LINEARLY inside each log bin, then compared."""
    a, b = load_xy(args.file_a), load_xy(args.file_b)
    lin = lambda y: 10 ** (y / 10) if np.nanmax(y) < 0 else y                     # noqa: E731
    xa, ya = a[:, 0], lin(a[:, 1])
    xb, yb = b[:, 0], lin(b[:, 1])
    yb_on_a = np.interp(xa, xb, yb) if (len(xa) != len(xb) or not np.allclose(xa, xb)) else yb
    m = (xa >= args.band[0]) & (xa <= args.band[1])
    fx, pa = log_bin(xa[m], ya[m], args.bins)
    _, pb = log_bin(xa[m], yb_on_a[m], args.bins)
    d = 10 * np.log10(pb / pa)
    print(f"A = {args.file_a}\nB = {args.file_b}")
    print(f"band {args.band[0]:g}-{args.band[1]:g} Hz, {len(d)} log bins: level B - A  median {np.median(d):+.3f} dB, "
          f"band-mean ratio {10 * np.log10(np.mean(yb_on_a[m]) / np.mean(ya[m])):+.3f} dB "
          f"(linear factor {10 ** (np.median(d) / 10):.3f})")
    print("use the MEDIAN - the band mean is dominated by the strongest spurs, which averaging does not change")
    print("reference (random noise, B = GUI average, A = linear-power average): FN n=10 -0.93 dB (0.807), "
          "n=20 -0.99 dB; RIN n=10 -2.17 dB, n=20 -2.33 dB; same capture: 0.000 dB")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HighFinesse LWA-1k diagnostics (see module docstring)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="read-only connection test")
    sub.add_parser("settings", help="print digitizer/analyzer settings + state")
    sub.add_parser("snapshot", help="read-only: save the last published data + results")
    sub.add_parser("dump", help="print every non-zero cell of the status record")
    sub.add_parser("ping", help="send only the harmless publish-settings requests, report every detail")
    p = sub.add_parser("set", help="change settings, e.g. analyzer.cutoff=1kHz evaluation.fit_function=Voigt")
    p.add_argument("assignments", nargs="+")
    p.add_argument("--allow-settings", action="store_true", help="experimental, see SETTINGS_WARNING")
    p = sub.add_parser("probe", help="one capture, everything logged")
    p.add_argument("--datasets", default="noise,lineshape")
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--log", default="probe_log.json")
    p.add_argument("--repeat", type=int, default=1, help="number of captures (timing + probe_noise_mean.csv)")
    p = sub.add_parser("level", help="level difference B - A [dB] of two spectra in a frequency band")
    p.add_argument("file_a"); p.add_argument("file_b")
    p.add_argument("--band", type=float, nargs=2, default=(1e6, 9e6), metavar=("F_LO", "F_HI"))
    p.add_argument("--bins", type=int, default=20, help="log bins per decade")
    p = sub.add_parser("compare", help="compare a GUI 'File > Save' export with a Python file")
    p.add_argument("gui_file"); p.add_argument("python_file", help="e.g. probe.h5::noise/last or <stem>.h5")
    p.add_argument("--rtol", type=float, default=1e-5)
    p.add_argument("--square", action="store_true", help="square the Python y (Hz/rtHz -> Hz^2/Hz)")
    a = ap.parse_args(argv)
    try:
        return {"check": cmd_check, "settings": cmd_settings, "ping": cmd_ping, "dump": cmd_dump, "snapshot": cmd_snapshot, "level": cmd_level, "set": cmd_set, "probe": cmd_probe,
                "compare": cmd_compare}[a.cmd](a)
    except LWAError as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
