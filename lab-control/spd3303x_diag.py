#!/usr/bin/env python3
"""
SPD3303X output-enable diagnostic.
Tries various command forms and reads SYST:STATUS? after each attempt.

SYST:STATUS? returns a hex string, e.g. "0x24".  Bit meanings (from manual):
  Bit 0 : CH1 output ON
  Bit 1 : CH2 output ON
  Bit 2 : tracking (0 = independent, 1 = series, 2 = parallel encoded in bits 2-3)
  Bit 4 : beep
  Bit 6 : baud
  Bit 7 : OTP

Run this with the DC supply powered on and cables disconnected.
"""

import pyvisa as visa
import time

IP = '192.168.1.31'

rm = visa.ResourceManager()
instr = rm.open_resource(f'TCPIP0::{IP}::5025::SOCKET')
instr.write_termination = '\n'
instr.read_termination = '\n'
instr.timeout = 5000


def status():
    try:
        s = instr.query('SYST:STATUS?').strip()
        print(f'  SYST:STATUS? raw = {repr(s)}')
        try:
            val = int(s, 16)
            ch1 = bool(val & 0x10)
            ch2 = bool(val & 0x20)
            track_bits = (val >> 2) & 0x03
            track_map = {0: 'independent', 1: 'series', 2: 'parallel'}
            print(f'  Decoded: CH1_ON={ch1}, CH2_ON={ch2}, track={track_map.get(track_bits, track_bits)}')
        except ValueError:
            pass
    except Exception as e:
        print(f'  SYST:STATUS? FAILED: {e}')


def err():
    try:
        e = instr.query('SYST:ERR?').strip()
        print(f'  SYST:ERR? = {e}')
    except Exception as ex:
        print(f'  SYST:ERR? FAILED: {ex}')


def w(cmd):
    try:
        instr.write(cmd)
        time.sleep(0.2)
        print(f'  write OK: {cmd!r}')
    except Exception as e:
        print(f'  write FAILED {cmd!r}: {e}')


def q(cmd):
    try:
        r = instr.query(cmd).strip()
        print(f'  query {cmd!r} = {r!r}')
        return r
    except Exception as e:
        print(f'  query {cmd!r} FAILED: {e}')
        return None


print('=== IDN ===')
q('*IDN?')

print('\n=== Baseline status ===')
status()
err()

print('\n=== Set V=1.5 I=0.02, check status ===')
w('CH1:VOLT 1.5')
w('CH1:CURR 0.02')
status()

print('\n=== Socket: OUTP:CH1 ON — status before/after ===')
status()
w('OUTP:CH1 ON')
err(); status()

instr.close()
print('\n--- closing socket, opening VXI11 ---')

instr2 = rm.open_resource(f'TCPIP0::{IP}::INSTR')
instr2.write_termination = '\n'
instr2.read_termination = '\n'
instr2.timeout = 5000

def w2(cmd):
    try:
        instr2.write(cmd)
        time.sleep(0.2)
        print(f'  VXI11 write OK: {cmd!r}')
    except Exception as e:
        print(f'  VXI11 write FAILED {cmd!r}: {e}')

def status2():
    try:
        s = instr2.query('SYST:STATUS?').strip()
        print(f'  VXI11 SYST:STATUS? = {repr(s)}')
        try:
            val = int(s, 16)
            print(f'  Decoded: CH1_ON={bool(val & 0x10)}, CH2_ON={bool(val & 0x20)}')
        except ValueError:
            pass
    except Exception as e:
        print(f'  VXI11 status FAILED: {e}')

print('\n=== VXI11: IDN ===')
try:
    print(f'  {instr2.query("*IDN?").strip()}')
except Exception as e:
    print(f'  FAILED: {e}')

print('\n=== VXI11: set V=1.5 I=0.02, then OUTP:CH1 ON ===')
status2()
w2('CH1:VOLT 1.5')
w2('CH1:CURR 0.02')
w2('OUTP:CH1 ON')
status2()

print('\n=== VXI11: try OUTPut CH1,ON ===')
w2('OUTPut CH1,ON')
try:
    e = instr2.query('SYST:ERR?').strip()
    print(f'  ERR: {e}')
except Exception as ex:
    print(f'  ERR query failed: {ex}')
status2()

w2('OUTP:CH1 OFF')
w2('CH1:VOLT 0')
w2('CH1:CURR 0')
instr2.close()
print('\nDone.')
# skip the cleanup block below
import sys; sys.exit(0)
w('CH1:VOLT 0')
w('CH1:CURR 0')
status()

instr.close()
print('\nDone.')
