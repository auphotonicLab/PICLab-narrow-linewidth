# Photodetector characterization

`photodetector_characterization.py` measures the DC transfer curve (output voltage vs. optical power) of a photodetector, e.g. Thorlabs PDA05CF2, while you turn a VOA by hand.

## Setup

    Laser -> VOA -> splitter -+-> monitor arm -> PM100USB (photodiode sensor)
                              +-> DUT arm     -> photodetector -> Keithley 2450 (high-Z voltmeter, 0 A source)

- `SPLIT_RATIO` = P(DUT arm) / P(monitor arm). Set `MEASURE_SPLIT_RATIO = True` once to measure it with the power meter.
- Hi-Z: the detector goes straight into the Keithley. For 50 ohm, add a 50 ohm feed-through and set `LOAD` and `TIA_GAIN`.
- Fiber adapter: SM05FCA (FC/APC) or SM05FC (FC/PC) in the detector's internal SM05 thread.
- Keep the detector arm below ~2-3 mW (the PDA05CF2 reaches its 10 V max output at ~1 mW at 1550 nm).

## Running

Run from the VS Code terminal: `python photodetector_characterization.py`, not the Interactive Window, so the live plot works.
It measures the dark offset (laser off), then records while you turn the VOA. Stop with Ctrl+C or by closing the live plot.

Results: gain (V/W), responsivity (A/W), dark offset/noise, 1 % compression point.
Data (CSV + PNG) is saved in `SAVE_FOLDER`. Uses `../lab-control/Lab_control.py`.
