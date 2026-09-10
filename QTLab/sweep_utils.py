"""Provided utilities for the ring-resonator sweep analysis exercise.

This module handles the "instrumentation cleanup" stage only: loading the scope CSVs,
removing the detector dark offset, isolating a single sweep using the trigger channel,
and masking out laser mode-hop glitches. It deliberately does NOT touch anything to do
with the physics of the analysis -- building the frequency axis, fitting resonances,
extracting FSR/loaded Q, or the loss/coupling extraction are left to you.

Why mode-hop masking is provided rather than an exercise
----------------------------------------------------------
Every ~0.25 nm the laser mode-hops, producing a brief burst of high-frequency noise
simultaneously in CH2 (MZI) and CH3 (ring transmission). Masking these out sounds like a
simple thresholding problem, but the obvious first approach -- flag samples where some
derivative-based "energy" metric exceeds a threshold, then pad a fixed time margin around
each flagged region to catch the decaying tail -- has a nasty failure mode: whether a
fixed time margin is harmless or catastrophic depends entirely on the sample rate. At
500 kHz it pads out a negligible fraction of a resonance. At 5 kHz the *same* time margin
is only a few samples -- but an entire resonance may only span 5-10 samples at that rate,
so the fixed margin silently deletes the real resonance next to every mode hop and
replaces it with a straight interpolation line, while still looking like it "works" (the
glitches disappear, the plot looks clean, the fits just quietly return garbage). Finding
that out took directly comparing raw vs. masked data by eye at both sample rates.

The fix used here is hysteresis: a sample only joins the mask if it's contiguous with a
high-confidence ("core") glitch sample *and* still above a weaker secondary threshold, so
each glitch grows to its own natural extent regardless of sample rate. It's provided as-is
so you can spend your time on the actual ring-resonator physics instead of rediscovering
this.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import label

DATA_DIR = Path(r"C:\Users\au617810\OneDrive - Aarhus universitet\O-drive - Jeppe\QTLab\Data")
DARK_FILE = DATA_DIR / "dark_signal.csv"

TRIGGER_THRESHOLD_V = 4.0

# Mode-hop glitch detection (hysteresis on a high-frequency energy metric -- see module docstring)
GLITCH_ENERGY_WINDOW_S = 22e-6
GLITCH_ZSCORE_HIGH = 10.0  # core: samples confidently inside a mode-hop
GLITCH_ZSCORE_LOW = 3.0  # samples kept in the mask only if contiguous with a core sample


def load_sweep(path):
    """Load one scope CSV, skipping the '#'-commented header lines.

    Returns (t, ch1, ch2, ch3) as plain numpy arrays:
      ch1 = laser sweep trigger, ch2 = MZI response, ch3 = ring transmission (raw, no
      dark-offset applied yet).
    """
    df = pd.read_csv(path, comment="#")
    return (
        df["time_s"].values,
        df["CH1_volts"].values,
        df["CH2_volts"].values,
        df["CH3_volts"].values,
    )


def compute_ch3_dark_offset(dark_path=DARK_FILE):
    """CH3's mean level with the ring path blocked -- subtract this from CH3 elsewhere."""
    _, _, _, ch3_dark = load_sweep(dark_path)
    return float(np.average(ch3_dark))


def find_sweep_segment(t, ch1, threshold=TRIGGER_THRESHOLD_V):
    """Return (i0, i1) bounding one full sweep, from the CH1 trigger's rising edges.

    The trigger fires once at sweep start and again ~1.37 s later at the start of the next
    sweep (= end of this one). If only one edge is captured in the file, falls back to
    using the last sample as the end point.
    """
    above = ch1 > threshold
    rises = np.where(np.diff(above.astype(int)) == 1)[0]
    if len(rises) >= 2:
        return rises[0], rises[1]
    if len(rises) == 1:
        return rises[0], len(t) - 1
    raise ValueError("No trigger edge found above threshold")


def _rolling_std(x, window):
    kernel = np.ones(window) / window
    mean = np.convolve(x, kernel, mode="same")
    mean_sq = np.convolve(x * x, kernel, mode="same")
    return np.sqrt(np.clip(mean_sq - mean**2, 0, None))


def _zscore(energy):
    med = np.median(energy)
    mad = np.median(np.abs(energy - med))
    return (energy - med) / (1.4826 * mad + 1e-12)


def detect_mode_hops(t, ch2, ch3):
    """Boolean mask, True where CH2/CH3 show a mode-hop glitch (to be masked out).

    See the module docstring for why this uses hysteresis rather than a fixed time
    margin around each flagged region.
    """
    dt = np.median(np.diff(t))
    win = max(3, int(round(GLITCH_ENERGY_WINDOW_S / dt)))

    energy2 = _rolling_std(np.diff(ch2, prepend=ch2[0]), win)
    energy3 = _rolling_std(np.diff(ch3, prepend=ch3[0]), win)
    z = np.maximum(_zscore(energy2), _zscore(energy3))

    core = z > GLITCH_ZSCORE_HIGH
    weak = z > GLITCH_ZSCORE_LOW
    labels, _ = label(weak)
    core_labels = set(labels[core & (labels > 0)])
    return np.isin(labels, list(core_labels)) if core_labels else np.zeros_like(core)


def mask_and_interpolate(t, signal, mask):
    """Replace masked (glitch) samples with a linear interpolation across the gap."""
    good = ~mask
    cleaned = signal.copy()
    cleaned[mask] = np.interp(t[mask], t[good], signal[good])
    return cleaned


def load_and_clean_sweep(path, dark_offset=None):
    """One-call convenience wrapping everything above: load, dark-correct CH3, isolate
    one sweep via the trigger, and detect the mode-hop mask.

    Parameters
    ----------
    path : Path to a sweep CSV.
    dark_offset : CH3 dark level (volts). Computed from DARK_FILE if not given -- pass it
        in explicitly when processing many files so it's only computed once.

    Returns
    -------
    t, ch2, ch3, glitch_mask
        All sliced to the single sweep segment. `ch3` has the dark offset subtracted but
        is NOT glitch-interpolated yet -- that's your call to make (e.g. via
        `mask_and_interpolate`) depending on what you're about to do with it. `ch2` is
        raw MZI voltage, also not yet cleaned.
    """
    if dark_offset is None:
        dark_offset = compute_ch3_dark_offset()

    t, ch1, ch2, ch3_raw = load_sweep(path)
    ch3 = ch3_raw - dark_offset

    i0, i1 = find_sweep_segment(t, ch1)
    t, ch2, ch3 = t[i0:i1], ch2[i0:i1], ch3[i0:i1]

    glitch_mask = detect_mode_hops(t, ch2, ch3)
    return t, ch2, ch3, glitch_mask
