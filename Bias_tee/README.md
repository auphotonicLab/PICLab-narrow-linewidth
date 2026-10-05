# Bias tee characterization

Characterizes the custom bias tee (1 kHz – 10 MHz) while mimicking a Thorlabs amplified photodetector
(PDA05CF2, PDA10A2, ...). A Siglent SDG6022X supplies AC + DC, the receiver is the Siglent SDS2352X-E scope
(raw time data → flat-top FFT), the R&S FSW50 or the Siglent SSA3021X, and a Keithley 2450 monitors the DC port.

| File | Role |
|---|---|
| `bias_tee_characterization.py` | Settings + `STAGES_TO_RUN`. Edit, then run this one. |
| `bias_tee_utils.py` | Instrument handling, safety checks, analysis, plots, saving. |
| `../lab-control/Lab_control.py` | Instrument classes (SDG, Keithley 2450, FSW50, SSA, SDS scope). |

---

## 1. Loads and impedances – what the script assumes and does

Everything below is about **which impedance each instrument sees**, because it decides what the numbers mean.

### 1.1 Signal generator (SDG6022X)
* Output impedance 50 Ω. The SDG shows/uses amplitude and offset **as seen by a 50 Ω load**; into a high-impedance
  load the real voltage is **twice** the typed value.
* The script forces the load setting to 50 Ω (`C1:OUTP LOAD,50`) *before* setting amplitude/offset, and **reads
  `C1:OUTP?` back at every frequency point** – it stops if the load is not 50 Ω.
* Amplitude, offset and frequency are also read back (`C1:BSWV?`) and compared with what was asked for, before the
  output is switched on. The SDG output is forced OFF while configuring, at every re-wiring prompt and at exit.
* Typed `VPP = 0.5` therefore means 0.5 Vpp across 50 Ω = 0.25 V peak = **−2.04 dBm**, which is drawn as the dotted
  "ideal" line in the report.

### 1.2 Thorlabs PD emulation (DC levels)
* A Thorlabs PD has a 50 Ω series resistor: **0–5 V into 50 Ω = 0–10 V into Hi-Z**.
* `PD_DC_LEVELS_V` are "PD output **into 50 Ω**" values, typed directly as the SDG offset (SDG in 50 Ω mode).
* In the bias tee the AC path ends in 50 Ω (receiver) but the DC path is (almost) open, so the DC voltage at the DC
  port – what the Keithley reads – is the open-circuit value: **`DC_AT_TEE_FACTOR` (= 2) × typed offset**
  (offset 4.5 V → Keithley ≈ 9 V; PD limit into Hi-Z is 10 V).
* This relies on **no DC current flowing**, i.e. the DC block (EF500) / AC-coupling in front of the receiver. If DC
  could leak into the 50 Ω receiver the Keithley would read ≈ 1 × offset instead – the script flags that
  (deviation > `DC_TOL_FRAC`/`DC_TOL_ABS_V` from the expected value).
* `DC + VPP/2` must stay ≤ `PD_MAX_50OHM_V` (5 V). Hence the top level is **4.5 V**, not 5 V (4.5 + 0.25 = 4.75 V);
  `validate_config` warns if you set more. (Whether the SDG accepts ±5 V offset into 50 Ω is **not verified**.)

### 1.3 Receivers
| Receiver | Input as used | How the power is obtained |
|---|---|---|
| **FSW50 / SSA3021X** | 50 Ω | Peak of the trace, dBm directly (SSA starts at 9 kHz; lower points are skipped). |
| **SDS2352X-E scope** | **1 MΩ** input → needs an **external 50 Ω feed-through terminator** on the BNC | Raw 8-bit record → flat-top FFT → `P = Vpk²/(2·50 Ω)` (dBm into 50 Ω). Coupling `D1M`/`A1M`. |

* The scope's 1 MΩ input is *not* a 50 Ω load; without the feed-through the AC path would see a ~open end and the
  numbers (and the PD/bias-tee behaviour) would be wrong. The scope's own input capacitance is in parallel with the
  terminator; it is the same in reference and measurement. The channel menu of your scope may offer a 50 Ω input
  (`D50`/`A50`; the guide says "varies by model") – not checked, not used.
* **Receiver load errors cancel in the comparisons:** every result is "sample − reference" measured with the *same*
  receiver and cables/adapters (stage 1: direct vs. EF500; stage 2: EF500 vs. EF500+tee; stage 3: 0 V vs. DC level).
  Absolute dBm values are only as good as the 50 Ω assumption.
* **DC-coupled ESA = risk.** The FSW manual requires you to protect a DC-coupled input from DC. The script therefore
  forces the SDG off, verifies offset = 0 V by read-back before the output is switched on, and refuses any offset while
  an ESA is DC-coupled. The scope's 1 MΩ DC coupling tolerates DC and is not treated as dangerous.
* AC coupling of a receiver acts as a high-pass at low frequency – stage 1-C (EF500, receiver AC-coupled, pure AC)
  isolates that effect from the DC block.
* SSA3021X: no coupling command is used; **its maximum DC input rating is not in the files I have – check before using
  it with DC** (stage 3).

### 1.4 DC block (EF500) and bias tee
* EF500: BNC feed-through in a 50 Ω system; its insertion loss is stage 1. Use the same BNC–SMA adapters in the
  reference and the measurement.
* Bias tee: AC path terminated by the receiver (through the EF500); DC port goes **only** to the Keithley. Nothing else
  may be connected to the DC port.

### 1.5 DC monitor (Keithley 2450) – high impedance, why it matters
* **Why:** the DC path (inductor, 100 mH rated 9 mA according to the slides) sees the SDG's open-circuit voltage
  (2 × offset) behind 50 Ω. Any low-resistance load on the DC port draws `I ≈ 2·offset / 50 Ω`: an offset of only
  **0.225 V already gives 9 mA**, 4.5 V gives ~180 mA. The Keithley must never present a short (or source voltage).
* **How it is configured** (`SetHighZVoltmeter`): `*RST`, **source 0 A**, voltage limit 20 V, **measure voltage, 2-wire**,
  and the **output-off state set to HIGH-IMPEDANCE** (`:OUTP:CURR:SMOD HIMP`, and also `:OUTP:VOLT:SMOD HIMP`). The 2450
  reference manual states that the default (normal) output-off state is a 0 V source – i.e. a near short – and that
  the current source must use the high-impedance off state.
* **Input resistance:** Keithley's own specification (SPEC-2450C, August 2020): voltage-measurement **input resistance
  > 10 GΩ on all ranges** (page 2) and sense input impedance > 10 GΩ (page 4). So at 9 V the current is < 1 nA – a
  factor > 10⁶ below 9 mA; the exact number does not matter, only that it is not a source/short. *(This value is from
  the datasheet, not from the reference manual, and I read it through a web summary – please glance at page 2.)*
  Source: <https://download.tek.com/document/SPEC-2450C_August_2020.pdf>
* **Checks while running:**
  * `AssertHighZ()`: function = CURR, source = 0 A, off-state = HIMP – before the signal is switched on and at every DC reading.
  * The voltage limit (20 V) is above the largest DC at the tee (9 V); the manual warns that an external voltage above
    the limit makes the 2450 draw excessive current.
  * The Keithley must be **disconnected during its `*RST`** (the off-state is briefly "normal" until HIMP is set); the
    script says so and waits for you.
  * It prints/logs which terminals are used (reset selects **FRONT**; connect to the front HI/LO).
  * Reading outside **25 %–150 %** of 2 × offset (`DC_ABORT_LOW_FRAC`/`HIGH_FRAC`) → SDG off, stage aborted, partial
    data saved (`_PARTIAL_*`) – means "not connected / wrong terminals / wrong SDG load".
  * Reading > `PD_MAX_HIZ_V` + 1 V → abort.
* NPLC = 1 (20 ms at 50 Hz mains) averages most of the small AC that leaks through the inductors at ≥ 1 kHz.

### 1.6 Protection against a short on the DC port
A short at the DC port is the one thing that can hurt the inductors (offset 0.225 V → 9 mA; 4.5 V → ~180 mA). What is done:

| Layer | What | Covers |
|---|---|---|
| **Hardware (recommended)** | **100 kΩ resistor in series with the Keithley HI line, mounted at the bias tee DC connector** (e.g. inside a BNC/SMA-to-banana adapter), LO direct. Then `DC_PORT_SERIES_R_OHM = 100e3`. | Any short downstream of the resistor (cable, banana plugs, Keithley in the wrong mode): ≤ 9 V / 100 kΩ = 90 µA, independent of software. |
| Software pre-check | Each DC sweep first applies only `DC_PRECHECK_OFFSET_V` (0.1 V → ≤ 4 mA into a dead short) and requires the Keithley to read ≈ 2× that; otherwise the SDG is switched off and the real level is **never applied**. | Keithley not connected, wrong terminals, short / wrong load on the DC port, wrong SDG load. |
| Software, every point | Keithley must read 25 %–150 % of 2 × offset or the stage aborts (SDG off, partial data saved). | A short or disconnection appearing during the sweep (detected within one point, ≈ SETTLE_S). |
| Software, before output ON | `AssertHighZ()` (0 A, high-Z off-state) and **voltage limit > 1.2 × expected DC + 1 V**. | Keithley left in voltage mode / normal off-state / too low a limit (the 2450 would then sink current). |
| Config check | `validate_config` rejects a pre-check offset whose short current exceeds half the rating; the wiring prompt warns when the highest DC level would exceed the rating into a short and no series resistor is declared. | Mis-set levels. |

*The series resistor does not disturb the DC reading:* the Keithley draws ~0 A, so there is no voltage drop; the divider with the
> 10 GΩ input gives an error of R/(R + 10 GΩ) ≈ 1·10⁻⁵ (90 µV at 9 V for 100 kΩ). Cable capacitance × 100 kΩ is ~10–100 µs –
irrelevant against `SETTLE_S`. It must sit **at the bias tee end**: a resistor at the Keithley end would leave the cable
itself unprotected. It does not protect against a fault inside the bias tee or between SDG and tee. If you want to confirm it:
read the same DC level (SDG straight into the Keithley) with and without the resistor – the readings should agree to ≪ 0.1 %.

---

## 2. Running

1. In `bias_tee_characterization.py` set `MEASUREMENT` (`'scope'`, `'fsw'`, `'ssa'`), the IP addresses (**`SCOPE_IP`
   is empty**), `SAVE_FOLDER` (defaults to a `data` folder next to the script) and `STAGES_TO_RUN`.
2. Run the script. A pop-up asks for the label; data go to `SAVE_FOLDER/<label>/`.
3. Follow the on-screen wiring prompts (the SDG output is off while you re-wire).
4. For the scope's own FFT in the screenshots: enable Math → FFT (Flat Top) on the scope screen first.

| Stage | Wiring | Result |
|---|---|---|
| 1 | SDG → receiver, then SDG → EF500 → receiver (receiver DC-coupled, **pure AC**), optionally AC-coupled | DC block insertion loss |
| 2 | Reference: SDG → EF500 → receiver. Then SDG → bias tee (AC out → EF500 → receiver, DC out → Keithley), pure AC | Bias tee insertion loss |
| 3 | As stage 2 with DC levels `PD_DC_LEVELS_V` | AC response vs DC level, harmonics, Keithley DC |

## 3. Output files (per stage, `<timestamp>_stage<N>_…`)
`_data.h5` (all data, **all settings**, instrument read-backs, script sources), `_summary.csv`, `_report.pdf/.svg`,
`_spectra.pdf/.svg`, `_fftcheck.pdf/.svg` (scope), `_screenshots/*.png`, `_log.txt`. An aborted stage saves
`_PARTIAL_data.h5/_PARTIAL_summary.csv`. The load/impedance model above is also stored in the h5 (`/analysis`, attr
`load_model`).

## 4. Not verified on real hardware
Everything has been run against simulated instruments only. In particular: SDG ±5 V offset limit into 50 Ω; real reply
formats of the scope; SSA screenshot format and its DC input rating; the scope's FFT readout vs `_fftcheck`; the 2450
front-panel reading (expected ≈ 2 × offset).
First check without the bias tee (set up by hand): SDG in 50 Ω mode, 0.5 V DC offset, AC amplitude minimal, output straight into the
Keithley (already in its 0 A high-Z voltmeter mode, e.g. after a stage-2 run starts) – it should read ≈ 1.000 V.
