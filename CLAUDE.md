# Conventions for this repository (PICLab-narrow-linewidth)

## Data files
- **Save compressed / array data as HDF5 (`.h5`, via `h5py`)**, not `.npz` and not data `.csv`.
  One `.h5` per measurement: arrays as gzip-compressed datasets (`compression="gzip", compression_opts=4,
  shuffle=True`), grouped logically (e.g. `noise/x`, `noise/mean`, `noise/captures`), with metadata
  (settings, units, timestamps, analysis results) as attributes. The `.h5` files are viewed directly in VS Code
  (HDF5 viewer extension).
- Keep exceptions small and deliberate:
  - instrument-native text formats that existing loaders need, e.g. the HighFinesse GUI export layout
    (`_PSD.txt` / `_RIN.txt`, read by `lwa_lib.LWA` and `Bias_tee/rin_utils.py`);
  - small human-readable tables such as `summary.csv` (one row per measurement);
  - logs (`.txt` / `.json`).
- Reference implementation: `HighFinesse_LWA/lwa_utils.py` → `write_h5`, `read_h5`, `load_h5_xy`.

## Spectra and averaging
- Average noise spectra in **linear power** (dB values via 10^(x/10), amplitudes via x^2), and log-bin
  with linear means. dB only for display or as the final value.
- HighFinesse LWA-1k GUI averaging is biased (see `HighFinesse_LWA/README.md`): FN is averaged as amplitude
  (−0.93 dB at n = 10, −0.99 dB at n = 20); RIN is averaged in dB (−2.17 dB at n = 10, −2.33 dB at n = 20).

## Scripts
- Measurement scripts: a settings block of UPPERCASE constants at the top + a `*_utils.py` module, run from
  the VS Code terminal with `py -3` (system Python 3.14, 64-bit; the repo `.venv` is broken).
