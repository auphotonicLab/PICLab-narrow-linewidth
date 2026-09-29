#!/usr/bin/env python3
"""
Check whether the SPD3303X output can be switched over the plain SCPI socket
(port 5025) using the command syntax from the SPD3303X manual:

    OUTPut {CH1|CH2|CH3},{ON|OFF}          e.g.  OUTPut CH1,ON

spd3303x_diag.py only ever sent 'OUTP:CH1 ON' over the socket, which is not a
valid SPD3303X command, so its conclusion that the socket ignores OUTPut was
never tested with the correct syntax.
 
Safe to run with the modulator connected: CH1 is set to 0 V / 10 mA first.
The result is read back from SYSTem:STATus? (bit 4 = CH1 on, bit 5 = CH2 on).
"""

import time
import pyvisa as visa

IP = '192.168.1.31'
CH = 1

rm = visa.ResourceManager()
dc = rm.open_resource(f'TCPIP0::{IP}::5025::SOCKET')
dc.write_termination = '\n'
dc.read_termination = '\n'
dc.timeout = 5000


def w(cmd):
    dc.write(cmd)
    time.sleep(0.3)          # the SPD3303X drops commands sent back-to-back


def ch_on():
    s = dc.query('SYSTem:STATus?').strip()
    time.sleep(0.1)
    return bool(int(s, 16) & (1 << (3 + CH))), s


print(dc.query('*IDN?').strip())
time.sleep(0.1)
w(f'CH{CH}:VOLTage 0')
w(f'CH{CH}:CURRent 0.01')

results = {}
for label, cmd_on in [
        ('manual syntax  ', f'OUTPut CH{CH},ON'),
        ('diag.py syntax ', f'OUTP:CH{CH} ON')]:
    w(f'OUTPut CH{CH},OFF')
    w(cmd_on)
    on, raw_on = ch_on()
    w(f'OUTPut CH{CH},OFF')
    off, raw_off = ch_on()
    results[label] = on
    print(f'{label} {cmd_on!r:22} -> CH{CH} on: {on}  (status {raw_on});'
          f' after OFF: {off} ({raw_off})')

dc.close()
print()
if results['manual syntax  ']:
    print('OUTPut works over the socket: the VXI-11 workaround in '
          'Lab_control.DC_Siglent is not needed.')
else:
    print('OUTPut did not switch over the socket: keep the VXI-11 workaround.')