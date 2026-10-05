#!/usr/bin/env python3
"""
Live connectivity test for bias_tee_characterization instruments.

Tests:
  1. AFG_Siglent  (SDG6022X)    — connect, IDN, output_status OFF
  2. SCOPE_SIGLENT_SDS           — connect, IDN, SetChannel, nearest_vdiv/tdiv  (skipped if SCOPE_IP='')
  3. Keithley 2450               — connect, IDN, SetHighZVoltmeter, AssertHighZ
  4. ESA_RS_FSW50                — connect, IDN                                 (skipped if FSW_IP='')
  5. ESA_SIGLENT (SSA3021X)      — connect, IDN                                 (skipped if SSA_IP='')

Safe: SDG output stays OFF throughout.  Keithley is put in high-Z mode (0 A source / relay open).
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lab-control'))
import Lab_control as pic

# --- IPs from bias_tee_characterization.py ---
AFG_IP      = '192.168.1.101'
AFG_CH      = 1
SCOPE_IP    = '192.168.1.52'   # Siglent SDS2352X-E
FSW_IP      = '192.168.1.7'
SSA_IP      = '192.168.1.11'
KEITHLEY_IP = '192.168.1.151'

PASS = '\033[32mPASS\033[0m'
FAIL = '\033[31mFAIL\033[0m'
SKIP = '\033[33mSKIP\033[0m'


def check(label, condition, detail=''):
    tag = PASS if condition else FAIL
    print('  [%s] %s' % (tag, label) + ('  (%s)' % detail if detail else ''))
    return condition


# =============================================================================
print('\n=== 1. AFG_Siglent (SDG6022X) ===')
# =============================================================================
try:
    afg = pic.AFG_Siglent(IP_address=AFG_IP, channel=AFG_CH, frequency=1e3,
                          waveform='SINE', vpp=0.5, offset=0, load=50)
    idn = afg.instr.query('*IDN?').strip()
    check('IDN?', bool(idn), idn)
    check('IDN contains Siglent or SDG', 'SDG' in idn or 'Siglent' in idn.title(), idn)

    afg.output_status(channel=AFG_CH, status='OFF')
    outp = afg.instr.query('C%d:OUTP?' % AFG_CH).strip()
    off = 'OFF' in outp.upper()
    check('output_status OFF', off, outp)

    afg.CloseConnection()
    print('  AFG connection closed.')
except Exception as e:
    print('  [%s] AFG_Siglent: %s' % (FAIL, e))

# =============================================================================
if not SCOPE_IP:
    print('\n[%s] 2. SCOPE_SIGLENT_SDS — SCOPE_IP is empty, skipping' % SKIP)
else:
    print('\n=== 2. SCOPE_SIGLENT_SDS (SDS2352X-E) ===')
    try:
        sc = pic.SCOPE_SIGLENT_SDS(IP_address=SCOPE_IP)
        idn = sc.instr.query('*IDN?').strip()
        check('IDN?', bool(idn), idn)
        check('IDN contains SDS or Siglent', 'SDS' in idn or 'Siglent' in idn.title(), idn)

        check('nearest_vdiv(0.07) returns a valid step',
              pic.SCOPE_SIGLENT_SDS.nearest_vdiv(0.07) in pic.SCOPE_SIGLENT_SDS.VDIV_LIST)
        check('nearest_tdiv(1e-5) returns a valid step',
              pic.SCOPE_SIGLENT_SDS.nearest_tdiv(1e-5) in pic.SCOPE_SIGLENT_SDS.TDIV_LIST)

        vi = sc.SetChannel(1, coupling='D50', vdiv=0.1, offset=0.0)
        got = sc.instr.query('C1:CPL?').strip()
        check('SetChannel D50', 'D50' in got.upper(), got)

        info = sc.GetAcquisitionInfo(1)
        check('GetAcquisitionInfo has tdiv and sample_rate',
              'tdiv' in info and 'sample_rate_Sa_s' in info, str(info))

        sc.closeConnection()
        print('  Scope connection closed.')
    except Exception as e:
        print('  [%s] SCOPE_SIGLENT_SDS: %s' % (FAIL, e))

# =============================================================================
print('\n=== 3. Keithley 2450 ===')
# =============================================================================
try:
    k = pic.DC_KEITHLEY_2450(channel=21, GPIB_interface=-1, IP_address=KEITHLEY_IP)
    idn = k.instr.query('*IDN?').strip()
    check('IDN?', bool(idn), idn)
    check('IDN contains Keithley or 2450', 'KEITHLEY' in idn.upper() or '2450' in idn, idn)

    k.SetHighZVoltmeter(vlim=20, nplc=1)
    check('source function is current', k.instr.query(':SOUR:FUNC?').strip().upper().startswith('CURR'))
    check('source current is 0 A', float(k.instr.query(':SOUR:CURR?')) == 0.0)
    offstate = k.instr.query(':OUTP:CURR:SMOD?').strip().upper()
    check('output-off state is HIMP', offstate.startswith('HIMP'), offstate)

    k.SwitchOn()
    check('output ON', int(k.instr.query(':OUTP?')) == 1)
    v = k.GetMeas()
    check('voltage read-back is finite float', isinstance(v, float), '%.4f V' % v)

    k.SwitchOff()
    check('output OFF', int(k.instr.query(':OUTP?')) == 0)

    try:
        k.AssertHighZ()
        check('AssertHighZ passes when in Hi-Z', True)
    except RuntimeError as e:
        check('AssertHighZ passes when in Hi-Z', False, str(e))

    k.CloseConnection()
    print('  Keithley connection closed.')
except Exception as e:
    print('  [%s] Keithley 2450: %s' % (FAIL, e))

# =============================================================================
if not FSW_IP:
    print('\n[%s] 4. ESA_RS_FSW50 — FSW_IP is empty, skipping' % SKIP)
else:
    print('\n=== 4. ESA_RS_FSW50 ===')
    try:
        fsw = pic.ESA_RS_FSW50(IP_address=FSW_IP)
        idn = fsw.instr.query('*IDN?').strip()
        check('IDN?', bool(idn), idn)
        check('IDN contains Rohde or FSW', 'ROHDE' in idn.upper() or 'FSW' in idn.upper(), idn)
        fsw.CloseConnection()
        print('  FSW connection closed.')
    except Exception as e:
        print('  [%s] ESA_RS_FSW50: %s' % (FAIL, e))

# =============================================================================
if not SSA_IP:
    print('\n[%s] 5. ESA_SIGLENT (SSA3021X) — SSA_IP is empty, skipping' % SKIP)
else:
    print('\n=== 5. ESA_SIGLENT (SSA3021X) ===')
    try:
        ssa = pic.ESA_SIGLENT(IP_address=SSA_IP, USB_interface=-1)
        idn = ssa.instr.query('*IDN?').strip()
        check('IDN?', bool(idn), idn)
        check('IDN contains Siglent or SSA', 'SSA' in idn or 'Siglent' in idn.title(), idn)
        ssa.CloseConnection()
        print('  SSA connection closed.')
    except Exception as e:
        print('  [%s] ESA_SIGLENT: %s' % (FAIL, e))

print('\nDone.')
