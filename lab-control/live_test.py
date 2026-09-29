#!/usr/bin/env python3
"""
Live connectivity and SCPI test.

Covers:
  1. DC_Siglent  — connect, VXI-11 outputStatus ON/OFF, SYST:STATUS? readback
  2. RTO1024     — connect, getOptions, hasHighDefinition, getVerticalInfo,
                   getMaxRealSampleRate, setHighDefinition (if K17 present),
                   acquireLongWaveform (1000 periods, no signal required),
                   SYSTem:ERRor? after every scope step

Safe to run with the modulator connected: DC output is 0 V / 10 mA throughout.
The scope acquisition runs on whatever is connected (or floating input).
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import Lab_control as pic

DC_IP  = '192.168.1.31'
OSC_IP = '192.168.1.87'
DC_CH  = 1
BIT_RATE = 20e6     # used only to size the acquireLongWaveform window

PASS = '\033[32mPASS\033[0m'
FAIL = '\033[31mFAIL\033[0m'

def check(label, condition, detail=''):
    tag = PASS if condition else FAIL
    print(f'  [{tag}] {label}' + (f'  ({detail})' if detail else ''))
    return condition

def scope_errors(osc, step):
    err = osc.instr.query('SYSTem:ERRor?').strip()
    ok = '0,' in err or err.startswith('0')
    check(f'SYSTem:ERRor? after {step}', ok, err)

# =============================================================================
print('\n=== 1. DC_Siglent (SPD3303X) ===')
# =============================================================================
try:
    dc = pic.DC_Siglent(IP_address=DC_IP, channel=DC_CH,
                        voltage=0.0, current=0.01, max_voltage=7.0)
    print(f'  Connected.')

    def dc_ch1_on():
        s = dc.instr.query('SYST:STATUS?').strip()
        return bool(int(s, 16) & 0x10), s

    # Baseline — output should be off (constructor no longer turns it on)
    on, raw = dc_ch1_on()
    check('Constructor leaves output OFF', not on, f'SYST:STATUS? = {raw}')

    # Turn ON
    dc.outputStatus(channel=DC_CH, status='ON')
    time.sleep(0.3)
    on, raw = dc_ch1_on()
    check('outputStatus ON sets bit 4', on, f'SYST:STATUS? = {raw}')

    # Turn OFF
    dc.outputStatus(channel=DC_CH, status='OFF')
    time.sleep(0.3)
    on, raw = dc_ch1_on()
    check('outputStatus OFF clears bit 4', not on, f'SYST:STATUS? = {raw}')

    dc.closeConnection()
    print('  DC connection closed.')

except Exception as e:
    print(f'  [ERROR] DC_Siglent: {e}')

# =============================================================================
print('\n=== 2. RTO1024 — connection and options ===')
# =============================================================================
osc = None
try:
    osc = pic.RTO1024(IP_address=OSC_IP)
    print()

    opts = osc.getOptions()
    print(f'  *OPT? options: {opts}')
    has_hd = osc.hasHighDefinition()
    check('hasHighDefinition() returns bool', isinstance(has_hd, bool),
          f'K17 present = {has_hd}')
    scope_errors(osc, '*OPT?')

    # ------------------------------------------------------------------
    print('\n=== 3. RTO1024 — getVerticalInfo ===')
    # ------------------------------------------------------------------
    vi = osc.getVerticalInfo(1)
    check('getVerticalInfo returns dict with expected keys',
          all(k in vi for k in ('volt_scale_V_per_div', 'offset_V',
                                'adc_word_step_V', 'adc_range_min_V')),
          str(vi))
    print(f'  CH1: {vi["volt_scale_V_per_div"]} V/div, offset {vi["offset_V"]} V, '
          f'ADC step {vi["adc_word_step_V"]*1e6:.2f} µV/level, '
          f'range [{vi["adc_range_min_V"]:.3f}, {vi["adc_range_max_V"]:.3f}] V')
    scope_errors(osc, 'getVerticalInfo')

    # ------------------------------------------------------------------
    print('\n=== 4. RTO1024 — getMaxRealSampleRate ===')
    # ------------------------------------------------------------------
    rate = osc.getMaxRealSampleRate()
    check('ACQuire:POINts:ARATe? returns ~10 GSa/s',
          8e9 <= rate <= 12e9, f'{rate/1e9:.3g} GSa/s')
    scope_errors(osc, 'getMaxRealSampleRate')

    # ------------------------------------------------------------------
    print('\n=== 5. RTO1024 — High Definition mode ===')
    # ------------------------------------------------------------------
    if has_hd:
        print('  K17 installed — enabling HD at 200 MHz …')
        on, bits = osc.setHighDefinition(True, 200e6)
        check('HDEFinition:STATe ON accepted', on)
        check('HDEFinition:RESolution? is sensible (10–16 bit)',
              10.0 <= bits <= 16.0, f'{bits} bit')
        scope_errors(osc, 'setHighDefinition ON')

        rate_hd = osc.getMaxRealSampleRate()
        check('Max sample rate halved in HD (4–6 GSa/s)',
              4e9 <= rate_hd <= 6e9, f'{rate_hd/1e9:.3g} GSa/s')

        on2, bits2 = osc.setHighDefinition(False)
        check('HDEFinition:STATe OFF accepted', not on2)
        scope_errors(osc, 'setHighDefinition OFF')
    else:
        print('  K17 not present — skipping HD tests.')
        on, bits = osc.setHighDefinition(True, 200e6)   # should silently skip
        check('setHighDefinition(True) without K17 returns (False, 8.0)',
              on is False and bits == 8.0, f'({on}, {bits})')

    # ------------------------------------------------------------------
    print('\n=== 6. RTO1024 — acquireLongWaveform (1000 periods) ===')
    # ------------------------------------------------------------------
    # Force AUTO trigger so SINGle completes without a connected signal
    osc.instr.write('TRIGger1:MODE AUTO')
    print('  Triggering single acquisition …')
    t, v = osc.acquireLongWaveform(channel=1, n_periods=1000,
                                   bit_rate=BIT_RATE,
                                   volt_scale=0.2,
                                   record_length=None)
    osc.instr.write('TRIGger1:MODE NORMal')
    acq = osc.last_acquisition
    dt  = acq['sample_interval_s']
    check('sample_interval_s is 100 ps or 200 ps (HD)',
          abs(dt - 1e-10) < 1e-11 or abs(dt - 2e-10) < 1e-11,
          f'{dt*1e12:.1f} ps')
    check('record_length > 0', acq['record_length'] > 0,
          f'{acq["record_length"]:,} pts')
    check('last_acquisition has expected keys',
          all(k in acq for k in ('sample_interval_s', 'sample_rate_Sa_s',
                                 'hd_mode', 'hd_resolution_bits', 'vertical')))
    vi1 = acq['vertical'].get(1)
    check('vertical info for CH1 in last_acquisition', vi1 is not None,
          str(vi1))
    scope_errors(osc, 'acquireLongWaveform')

    print(f'\n  Summary: {acq["record_length"]:,} pts, '
          f'{dt*1e12:.1f} ps/sample ({acq["sample_rate_Sa_s"]/1e9:.3g} GSa/s), '
          f'HD={acq["hd_mode"]}'
          + (f' {acq["hd_resolution_bits"]:.1f} bit' if acq["hd_mode"] else ' 8 bit'))

except Exception as e:
    import traceback
    print(f'\n  [ERROR] RTO1024: {e}')
    traceback.print_exc()
finally:
    if osc is not None:
        try:
            osc.closeConnection()
            print('\n  Scope connection closed.')
        except Exception:
            pass

print('\nDone.')
