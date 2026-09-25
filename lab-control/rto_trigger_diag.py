#!/usr/bin/env python3
"""RTO1024 trigger command diagnostic — find correct SCPI syntax."""

import pyvisa as visa
import time

IP = '192.168.1.87'
rm = visa.ResourceManager()
instr = rm.open_resource(f'TCPIP0::{IP}::hislip0::INSTR')
instr.timeout = 10000

def q(cmd):
    try:
        r = instr.query(cmd).strip()
        print(f'  Q {cmd} -> {r!r}')
        return r
    except Exception as e:
        print(f'  Q {cmd} -> TIMEOUT/ERROR')
        return None

def w(cmd):
    instr.write(cmd)
    time.sleep(0.2)

print('=== Working trigger source commands ===')
for cmd in ['TRIGger1:SOURce?', 'TRIGger:SOURce?', 'TRIGger:A:SOURce?']:
    q(cmd)

print('\n=== Set source to CHAN3 and verify ===')
for set_cmd, get_cmd in [
    ('TRIGger1:SOURce CHAN3',  'TRIGger1:SOURce?'),
    ('TRIGger:SOURce CHAN3',   'TRIGger:SOURce?'),
]:
    w(set_cmd)
    r = q(get_cmd)
    print(f'  -> {"OK" if r and "3" in r else "FAIL"}: {set_cmd!r}')

print('\n=== Trigger level ===')
for cmd in ['TRIGger1:LEVel1?', 'TRIGger1:LEVel2?', 'TRIGger1:LEVel3?',
            'TRIGger:A:LEVel1?', 'TRIGger:A:LEVel3?',
            'TRIGger:LEVel?', 'TRIGger1:LEVel?']:
    q(cmd)

print('\n=== Trigger edge/mode ===')
for cmd in ['TRIGger1:EDGE:SLOPe?', 'TRIGger:A:EDGE:SLOPe?',
            'TRIGger1:TYPE?', 'TRIGger:TYPE?',
            'TRIGger1:MODE?', 'TRIGger:MODE?',
            'ACQuire:MODE?']:
    q(cmd)

instr.close()
print('\nDone.')
