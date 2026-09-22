#!/usr/bin/env python3
"""
Bias tee characterization
--------------------------
Sweeps a sine tone across FREQUENCIES_HZ and measures the AC response at the
RF output port (oscilloscope or ESA) while the Keithley monitors DC current on
the DC port.  The sweep is run twice: once AC-only, once with a DC offset.

Wiring
------
  AFG CH1          →  Bias tee  RF+DC  (combined) port
  Bias tee RF port →  Scope CH1  or  ESA RF input
  Bias tee DC port →  1 MΩ resistor  →  Keithley HI  (Keithley LO to ground)

The 1 MΩ series resistor is essential: the Keithley is configured as a 0 V
voltage source (ammeter mode), which would otherwise short the DC port and
pull excessive current through the bias tee inductor.  With 1 MΩ in series,
current is limited to V_DC / 1e6, typically well under 10 µA.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import time
import matplotlib.pyplot as plt
from Lab_control import AFG_Siglent, DC_KEITHLEY_2450, RTO1024, ESA_RS_FSV30

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FREQUENCIES_HZ = [1e3, 10e3, 100e3, 1e6, 5e6, 10e6, 50e6, 100e6]

VPP          = 0.5   # AFG sine amplitude (Vpp)
DC_OFFSET_V  = 1.0   # DC offset added in the second sweep (V)
AFG_LOAD     = 50    # Ω

USE_SCOPE = True     # True → RTO1024 oscilloscope,  False → RS FSV30 ESA

AFG_IP             = '192.168.1.101'
SCOPE_IP           = '192.168.1.87'
ESA_IP             = '192.168.1.7'
KEITHLEY_GPIB_CH   = -1   # -1 = LAN/TCP (GPIB_interface=-1 routes to IP_address)

# ---------------------------------------------------------------------------
# Connect
# ---------------------------------------------------------------------------
print('Connecting to instruments...')

afg = AFG_Siglent(IP_address=AFG_IP, channel=1,
                  frequency=FREQUENCIES_HZ[0], waveform='SINE',
                  vpp=VPP, offset=0, load=AFG_LOAD)
afg.output_status(channel=1, status='ON')

keithley = DC_KEITHLEY_2450(channel=21, GPIB_interface=-1, IP_address='192.168.1.151')
keithley.SetMode('Voltage')   # source 0 V, measure current (ammeter)
keithley.SetSourceValue(0.0)
keithley.SetCompliance(50e-6) # 50 µA hard limit — belt-and-suspenders on top of 1 MΩ
keithley.SwitchOn()

if USE_SCOPE:
    ac_instr = RTO1024(IP_address=SCOPE_IP)
    ac_instr.instr.write('CHANnel1:STATe ON')
    ac_instr.instr.write('TRIGger:A:SOURce CHAN1')
    ac_instr.instr.write('TRIGger:A:MODE AUTO')
else:
    ac_instr = ESA_RS_FSV30(IP_address=ESA_IP)

# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------

def _setup_scope(freq):
    time_scale = max(3.0 / (freq * 10), 1e-9)   # ~3 periods across 10 div
    ac_instr.instr.write('TIMebase:SCALe ' + str(time_scale))
    time.sleep(0.05)


def measure_ac(freq):
    """Return Vpp (scope) or peak power dBm (ESA) at the RF output port."""
    if USE_SCOPE:
        _setup_scope(freq)
        ac_instr.single()
        _, v = ac_instr.getWaveform(channel=1)
        return float(np.ptp(v))
    else:
        c_mhz = freq / 1e6
        span  = max(c_mhz * 0.2,  0.001)
        rbw   = max(c_mhz * 0.01, 0.0001)
        ac_instr.SetSpectrumParameters(centerFreq=c_mhz, spanFreq=span,
                                       resolutionBW=rbw, videoBW=rbw,
                                       dataPointsInSweep=1001)
        return ac_instr.ReadPeakPower()


def run_sweep(label, dc_offset=0.0):
    amplitudes  = []
    dc_currents = []
    for freq in FREQUENCIES_HZ:
        afg.setParameters(channel=1, waveform='SINE', frequency=freq,
                          vpp=VPP, offset=dc_offset, load=AFG_LOAD)
        time.sleep(0.3)

        amp  = measure_ac(freq)
        dc_I = keithley.GetMeas()

        amplitudes.append(amp)
        dc_currents.append(dc_I)

        unit = 'Vpp' if USE_SCOPE else 'dBm'
        print(f'  [{label}]  {freq/1e6:8.4f} MHz   '
              f'AC = {amp:.4f} {unit}   DC = {dc_I * 1e6:.3f} µA')

    return np.array(amplitudes), np.array(dc_currents)

# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------
print('\n--- Sweep 1: AC only ---')
amp_ac, idc_ac = run_sweep('AC only', dc_offset=0.0)

print(f'\n--- Sweep 2: AC + {DC_OFFSET_V} V DC offset ---')
amp_dc, idc_dc = run_sweep('AC+DC', dc_offset=DC_OFFSET_V)

# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------
freq_mhz = np.array(FREQUENCIES_HZ) / 1e6
ac_unit  = 'Vpp' if USE_SCOPE else 'dBm'

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 7), sharex=True)

ax1.semilogx(freq_mhz, amp_ac, 'o-',  label='AC only')
ax1.semilogx(freq_mhz, amp_dc, 's--', label=f'AC + {DC_OFFSET_V} V DC')
ax1.set_ylabel(f'AC amplitude ({ac_unit})')
ax1.set_title('Bias tee — AC path response')
ax1.legend()
ax1.grid(True, which='both')

ax2.semilogx(freq_mhz, idc_ac * 1e6, 'o-',  label='AC only')
ax2.semilogx(freq_mhz, idc_dc * 1e6, 's--', label=f'AC + {DC_OFFSET_V} V DC')
ax2.set_xlabel('Frequency (MHz)')
ax2.set_ylabel('DC port current (µA)')
ax2.set_title('Bias tee — DC port current')
ax2.legend()
ax2.grid(True, which='both')

plt.tight_layout()
plt.savefig('bias_tee_characterization.png', dpi=150)
plt.show()

# ---------------------------------------------------------------------------
# Clean up
# ---------------------------------------------------------------------------
afg.output_status(channel=1, status='OFF')
keithley.SwitchOff()
keithley.CloseConnection()
afg.CloseConnection()
if USE_SCOPE:
    ac_instr.closeConnection()
else:
    ac_instr.CloseConnection()
