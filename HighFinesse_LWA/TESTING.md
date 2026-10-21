# Self-check plan: HighFinesse GUI vs Python

Work through the steps in order. Each step has a pass criterion; if one fails, stop there.
Steps 2–5 need the GUI's *File → Save → Rawdata* right after a Python capture: Python receives exactly
the capture the GUI is showing.

All commands go in the VS Code terminal (PowerShell). Start from the folder and stay in `diag_out`:

```powershell
cd "C:\Users\Group Login\Documents\Code\PICLab-narrow-linewidth\HighFinesse_LWA"
mkdir diag_out -Force; cd diag_out
```

`py -3` is the system Python 3.14 (64-bit). Don't select the repo's `.venv`: it points to another user's Python.

---

## 0 · Before you start

- [ ] **Exactly one** `LWA_Control.exe` is running, showing Digitizer *Connected* and Analyzer *FN mode* or *RIN mode*.
      Never start a second instance: it overwrites the shared memory (restart the GUI if that happens).
- [ ] GUI: *Digitizer → Averaging = Off*, *Evaluation → Division = 0*.
- [ ] Note whether the Noise-spectrum and Lineshape *Active* buttons are on. A Python request switches each
      one to match the requested datasets (`--datasets noise,lineshape` keeps both on).
- [ ] Offline tests (no instrument needed). Install pytest and h5py once with `py -3 -m pip install pytest h5py`,
      then:
      ```powershell
      py -3 -m pytest ..\test_lwa_utils_offline.py -q
      ```
      **Pass:** `18 passed`.

## 1 · Connection (read-only, changes nothing)

```powershell
py -3 ..\lwa_utils.py check
```
**Pass:**
- `exactly one LWA_Control.exe`
- `record size 1608`
- `commands will go to 0x… (TForm_GUI …)`
- the `lwaData.dll` cross-check: 7 × PASS, DLL = Python
- digitizer = 1, analyzer = 1, range = 1

The line `handle stored by the GUI … is a live window` may FAIL; that is normal, because the GUI stores a stale handle.
If digitizer/analyzer show −1 while the GUI says *Connected*, restart the GUI.

## 2 · Same capture, FN: Python = GUI export

1. GUI: *Noise mode = FN*, capture **idle** (white *Run* button).
2. ```powershell
   py -3 ..\lwa_utils.py probe --repeat 1 --datasets noise,lineshape
   ```
   The GUI runs one capture; `probe.h5` is written (`noise/last` = that capture, in Hz²/Hz).
3. Without touching the GUI: *File → Save → Rawdata* → `…\HighFinesse_LWA\diag_out\GUI_FN.txt`
4. ```powershell
   py -3 ..\lwa_utils.py compare GUI_FN.txt probe.h5::noise/last
   ```
   **Pass:** `max relative difference … y: ~1e-10`, `Effective (beta) … MATCH`, `RESULT: MATCH`.

## 3 · Same capture, RIN

1. GUI: *Noise mode = RIN*, wait until the power LEDs/bars are stable, capture idle.
2. ```powershell
   py -3 ..\lwa_utils.py probe --repeat 1 --datasets noise,lineshape
   ```
3. GUI *File → Save → Rawdata* → `GUI_RIN.txt`
4. ```powershell
   py -3 ..\lwa_utils.py compare GUI_RIN.txt probe.h5::noise/last
   ```
   **Pass:** `RESULT: MATCH` (both in dB/Hz; there is no Effective line in RIN mode).

## 4 · GUI averaging vs Python power averaging, FN

Do a and b back to back, so the laser does not drift in between.

1. GUI: *FN*, *Averaging* = on with 10 (your usual setting), capture until 10 are averaged, then
   *File → Save → Rawdata* → `GUI_FN_n10.txt`. Then set *Averaging = Off* again.
2. ```powershell
   py -3 ..\lwa_utils.py probe --repeat 10 --datasets noise,lineshape
   py -3 ..\lwa_utils.py level probe.h5::noise/mean GUI_FN_n10.txt
   ```
   `probe.h5::noise/mean` is the Python linear-power average of the 10 captures (`noise/captures` holds all 10).
   **Pass:** median ≈ **−0.93 dB** (factor ≈ 0.81), ±0.1 dB. For n = 20, ≈ −0.99 dB.
3. Optional: `py -3 ..\lwa_utils.py level GUI_FN.txt GUI_FN_n10.txt` (single GUI capture as the reference) gives
   the same ≈ −0.93 dB, with more scatter.

## 5 · GUI averaging vs Python power averaging, RIN

As step 4, in *RIN mode*: `GUI_RIN_n10.txt`, then

```powershell
py -3 ..\lwa_utils.py probe --repeat 10 --datasets noise,lineshape
py -3 ..\lwa_utils.py level probe.h5::noise/mean GUI_RIN_n10.txt --band 1e4 9e6
```
**Pass:** median ≈ **−2.17 dB** (n = 10), ≈ −2.33 dB (n = 20). Use the **median**: the band-mean line is
dominated by spurs, which averaging does not change.

## 6 · Measurement script, FN

In `lwa_measurement.py` set `SAVE_FOLDER`, keep `AVERAGING = 'power'`, and set
`DATASETS = ('noise', 'lineshape')` and `PLAN = [dict(name='avg10', n_average=10), dict(name='single', n_average=1)]`.
GUI: *FN*, *Averaging = Off*.

```powershell
cd ..
py -3 lwa_measurement.py
```
**Pass:**
- [ ] The console shows ~0.5 s per capture; there is no error.
- [ ] In `SAVE_FOLDER\<label>\` you find, per measurement: `<stem>.h5`, `_PSD.txt` and `.png/.pdf`, plus `summary.csv`
      and the log. Open the `.h5` in VS Code: `noise/mean` (Hz²/Hz), `noise/captures` (10 × 200 000 for avg10),
      `noise/binned`, `gui_results`, and attributes such as `n_averaged` and `effective_linewidth_Hz_python_beta`.
- [ ] The *single* measurement's `effective_linewidth_Hz_python_beta` (an attribute of its `.h5`) equals the GUI's
      *Effective (β)* for that last capture (the GUI shows it rounded).
- [ ] Your existing loader reads the file:
      ```python
      import sys; sys.path.insert(0, r'..\U_shaped_laser_package\src')
      from u_shaped_lib import lwa_lib
      d = lwa_lib.LWA(r'<SAVE_FOLDER>\<label>\<stem>_PSD.txt'); print(d.type, d.get_linewidth(), len(d.freqs))
      ```
      → `PSD <intrinsic> 199999`
- [ ] Optional: run again with `AVERAGING = 'gui'` and compare with the GUI's own n = 10 export:
      `py -3 lwa_utils.py level <stem>_PSD.txt diag_out\GUI_FN_n10.txt` → ≈ 0.0 dB.

## 7 · Measurement script, RIN

GUI: *Noise mode = RIN*. Nothing changes in the script; the unit is detected automatically.

```powershell
py -3 lwa_measurement.py
```
**Pass:**
- [ ] In the `.h5`: `noise/_attrs unit = dB/Hz`, `noise/mean` and `noise/binned/y` in dB/Hz (binned from linear
      power), no linewidth attributes. `_RIN.txt` has `#Outputmode=RIN mode`.
- [ ] `_RIN.txt` has `#Averaging=0` and `#Av count= 0` (power average). `Bias_tee/rin_utils` therefore adds **no**
      dB-averaging correction to it, which is correct. With `AVERAGING = 'gui'` it says `Averaging=1` and
      `Av count= 10`, and the correction is applied, also correctly.
- [ ] Optional: compare with an ESA RIN measurement via `Bias_tee/rin_compare_highfinesse.py`
      (`HIGHFINESSE_TXT` = the `_RIN.txt`).

## 8 · Robustness

- [ ] Close the GUI while `lwa_measurement.py` runs: the script stops with an error within ~5 s instead of hanging.
- [ ] Unplug the Digitizer USB during a run: `nominal=False` / a warning appears. Afterwards, restart the GUI.

## Reference values (2026-10-21, SN 1006)

| quantity | value |
|---|---|
| FN unit published by the GUI | Hz/√Hz; Python squares it, so files are in Hz²/Hz (= GUI export to 1e-10) |
| GUI FN averaging (amplitude) vs power | 0.807 / −0.93 dB (n = 10), 0.796 / −0.99 dB (n = 20) |
| GUI RIN averaging (dB) vs power | −2.17 dB (n = 10), −2.33 dB (n = 20) |
| Effective (β) | Python `beta_separation_linewidth` = GUI to ≤ 1e-9 |
| GUI Intrinsic (*Mode(stat)*) | not published; ≈ π·S₀/2 for a single capture, algorithm unclear with averaging |
| White floor, this laser | ≈ 21 Hz²/Hz (≈ 4.6 Hz/√Hz), at or below the 5 Hz/√Hz spec, so likely the analyzer floor |
| Time per capture | ≈ 0.45 s (GUI capturing continuously), ≈ 0.5 s (GUI idle) |
