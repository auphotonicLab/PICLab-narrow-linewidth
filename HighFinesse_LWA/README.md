# HighFinesse LWA-1k (1550) – automation from Python

`lwa_measurement.py` (settings) + `lwa_utils.py` (machinery) drive the HighFinesse
linewidth analyzer through its own GUI. They set the GUI settings, start
captures, collect the full-resolution noise spectrum / lineshape / time series
plus HighFinesse's linewidth results, average, analyse and save.

Requirements: Windows, **64-bit** Python ≥ 3.8, `numpy`, `matplotlib`, `h5py` (`py -3 -m pip install h5py`).
`LWA_Control.exe` must be running and initialised. Run from the VS Code terminal.

## Status on the instrument (tested 2026-10-21, GUI in continuous capture, RIN mode)

| | Result |
|---|---|
| Connection, shared memory, instrument state | ✅ identical to HighFinesse's own `lwaData.dll` (7/7 values) |
| Window handle | ⚠️ the GUI stores a stale handle; the script finds the main window `TForm_GUI` itself |
| **Same capture, GUI export vs Python (FN)** | ✅ **identical on all 200 000 points (1e-10 = CSV digits)**. The GUI publishes **Hz/√Hz**; its export is the square (Hz²/Hz) |
| RIN capture vs GUI export | ✅ same grid and unit (dB/Hz), same statistics |
| Effective (β) | ✅ Python `beta_separation_linewidth` = GUI to 1e-9: √(8 ln2 · Σ S·Δf) over the bins above the β-line |
| Intrinsic (GUI *Mode(stat)*) | ⚠️ not published by the GUI. ≈ π·(mode of the amplitude histogram)² ≈ **π·S₀/2**, about half of π·mean(S). Python saves both (`intrinsic_GUI_like_mode_Hz_python`, `intrinsic_linewidth_Hz_python`) |
| GUI result slots | effective β, Voigt FWHM, Lorentzian width, Gaussian width (lineshape fit); slot 0 = 100 = "<0.1 kHz" |
| Averaging n = 10 | ✅ independent captures. Python averages in **linear power** (unbiased). The GUI's own Averaging is biased low: **RIN is averaged in dB** (−2.17 dB at n = 10, −2.33 dB at n = 20; theory Γ(1+1/n)ⁿ), **FN is averaged as amplitude Hz/√Hz** (0.808× = −0.93 dB at n = 10, −0.99 dB at n = 20; theory π/4 + (1−π/4)/n). Offsets apply to random noise, not to spurs/tones. `AVERAGING = 'gui'` reproduces the GUI for comparisons |
| Units saved | FN always in **Hz²/Hz** (published Hz/√Hz is squared on capture), RIN in dB/Hz. Each measurement also gets a `_PSD.txt` / `_RIN.txt` in the GUI's export format, which `lwa_lib.LWA` reads unchanged |
| Speed | GUI capturing continuously: ~0.45 s per capture (n = 10 ≈ 4.5 s). GUI idle (single runs): ~0.5 s from request to data |
| **Remote settings** | ❌ **disabled**: the GUI's remote module never syncs its copy of the panel tables (publishes all zeros); setting one row would reset the other rows of that panel. The same applies to its "publish results" request (zeros), which is never sent |

`verify_against_gui.py` regenerates the four verification figures (same capture, power vs dB averaging, linewidths, FN GUI averaging).

**Settings are therefore made in the GUI.** Python captures, averages, analyses and saves.

**Averaging (e.g. n = 10, then n = 1):** keep the GUI's *Averaging* **Off**. `n_average`
captures are averaged here in linear power (dB data via 10^(x/10), Hz/√Hz via x²), and every capture is
kept in the measurement's `.h5` (`noise/captures`). The GUI averages in dB, which biases the result low (see `Bias_tee/README.md`).

**Side effect to know:** a capture request sets the GUI's noise/lineshape Autoeval to match the requested
datasets. `DATASETS = ('noise',)` switches the lineshape Autoeval **off**; add `'lineshape'` to keep it on.

**Do not start a second LWA_Control.exe.** A second instance overwrites the shared memory (stored
window, states = −1). The running GUI republishes its state only when it changes, so restart the GUI if
`check` shows −1 states while the GUI says Connected.

## Data files

Per measurement: **`<stem>.h5`** (gzip-compressed, all arrays + metadata; repo convention, see `../CLAUDE.md`),
`<stem>_PSD.txt` / `<stem>_RIN.txt` (GUI export format for `lwa_lib` / `rin_utils`), `.png/.pdf`; per run
`summary.csv` and the log. Inside the `.h5`: `noise/{x, mean, std, captures, binned/{x,y}}`,
`lineshape/…`, `time/…`, `gui_results/<slot>` and `capture_info/…` per capture, and attributes with the Python
linewidths, settings, timing and state. Read it in Python with `lwa_utils.read_h5(path)`, or in VS Code
with the HDF5 viewer.

## Checking it yourself

**[TESTING.md](TESTING.md)** is the step-by-step self-check: same-capture comparisons FN and RIN, averaging offsets,
both measurement modes, robustness, and reference values. Helpers: `lwa_utils.py compare` (point-by-point +
Effective β) and `lwa_utils.py level` (level difference of two spectra, linear bin means).

**FN or RIN:** just switch the GUI's Noise mode; the scripts detect the unit (FN → Hz²/Hz, RIN → dB/Hz).

## How it works

HighFinesse documents no API, but `LWA_Control.exe` contains a remote interface
that its `lwaData.dll` uses. Both were reverse-engineered from the binaries in
`HighFinesse LWA-1k installation file and manual\src`:

* **Commands**: `SendMessage(GUI window, WM_USER+1, (group<<16)|panel, (row<<16)|value)`.
  * Group 2 sets row *row* of panel 1 (Digitizer), 2 (Analyzer) or 4 (Evaluation) to
    drop-down option *value*; the GUI then clicks that option itself. Panel 6 = Capture.
  * Group 1 are requests:
    * 7 = start a single capture and publish datasets (mask: time 1, noise 2, lineshape 4)
    * 8 = raw/binned output
    * 1 / 2 = publish the Digitizer / Analyzer settings
    * 5 = publish the linewidth results
* **Results**: four named shared-memory blocks (`LWA_Status_Rec_map`,
  `LWA_TimeData_map`, `LWA_NoiseData_map`, `LWA_LineshapeData_map`) that the
  GUI fills. Python reads them and only ever writes a single flag byte (or the
  time-int value), never a whole record.

`test_lwa_utils_offline.py` checks the decoding against addresses in the DLL's
machine code and runs the whole flow against a simulated GUI
(`py -3 -m pytest test_lwa_utils_offline.py -q`, 18 tests).

## Diagnostics (double-click in Explorer, or run the commands from the VS Code terminal)

* `run_check.bat`: read-only check, window list, `ping`, status dump → `diag_out\check_log.txt`
* `run_probe.bat`: 10 noise captures with timing → `diag_out\probe_log.txt`, `diag_out\probe.h5`
* `run_measurement.bat`: `lwa_measurement.py` unattended → `diag_out\test_run\`
* `py -3 lwa_utils.py compare <GUI raw export>.txt probe.h5::noise/last` (or `<stem>.h5`): point-by-point comparison

Still open: run `run_probe.bat` in **FN** mode, save the GUI's raw export right after, then compare, and
match slots 0/2/3 against the export header's *Intrinsic* value.

## Caveats

* This is an undocumented interface that is tied to this GUI version. `check` detects a different
  status-record layout. Ask HighFinesse (service@highfinesse.de) whether the
  remote interface is supported; that would also settle the unconfirmed items.
* A capture request also sets the GUI's noise/lineshape Autoeval to match the
  requested datasets; that is how the GUI implements it.
* Don't click in the GUI while a script runs.
* Group-1 requests 3, 4 and 6 are never sent: they overwrite the instrument-state block or are lost.
