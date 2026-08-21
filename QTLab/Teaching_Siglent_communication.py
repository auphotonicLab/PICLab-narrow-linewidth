
Siglent scope lab · PY
"""
siglent_scope_lab.py
 
Minimal USB control of a Siglent SDS800X HD oscilloscope for the teaching
lab. Every function just sends SCPI commands to the instrument -- see the
SDS Series Programming Guide for the full command reference.
 
Install once:
    pip install pyvisa pyvisa-py numpy
 
Example experiment run:
 
    from siglent_scope_lab import *
 
    inst = connect()
 
    set_vertical(inst, 1, volts_per_div=0.5)
    set_vertical(inst, 2, volts_per_div=1.0)
    set_horizontal(inst, seconds_per_div=1e-3)
    set_trigger(inst, channel=1, level=0.1)
    set_memory_depth(inst, "1M")
 
    single_trigger(inst)
    t, v1 = get_waveform(inst, 1)
    t, v2 = get_waveform(inst, 2)
 
    save_waveform(inst, "my_measurement.npz", t, {1: v1, 2: v2})
 
To load a saved measurement back later (e.g. in an analysis script):
 
    import numpy as np
    data = np.load("my_measurement.npz")
    t, v1 = data["time_s"], data["CH1_volts"]
"""
 
import struct
import time
from datetime import datetime
 
import numpy as np
import pyvisa
 
 
def connect(resource=None):
    """Open a USB connection to the scope.
 
    Prints every VISA resource the computer can see, so you can find the
    right resource name to pass in by hand if auto-detection picks the
    wrong one (e.g. if you have another USB instrument connected too)."""
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    print("Available VISA resources:", resources)
 
    if resource is None:
        resource = [r for r in resources if r.startswith("USB")][0]
 
    inst = rm.open_resource(resource)
    inst.timeout = 20000
    inst.read_termination = "\n"
    inst.write_termination = "\n"
    print("Connected to:", inst.query("*IDN?"))
    return inst
 
 
def set_vertical(inst, channel, volts_per_div, offset=0.0, coupling="DC"):
    """Vertical settings for one channel (1, 2, 3 or 4)."""
    inst.write(f":CHANnel{channel}:SWITch ON")
    inst.write(f":CHANnel{channel}:SCALe {volts_per_div}")
    inst.write(f":CHANnel{channel}:OFFSet {offset}")
    inst.write(f":CHANnel{channel}:COUPling {coupling}")
 
 
def set_horizontal(inst, seconds_per_div, delay=0.0):
    """Horizontal (timebase) settings, shared by all channels."""
    inst.write(f":TIMebase:SCALe {seconds_per_div}")
    inst.write(f":TIMebase:DELay {delay}")
 
 
def set_trigger(inst, channel=1, level=0.0, slope="RISing"):
    """A simple edge trigger on one channel."""
    inst.write(":TRIGger:TYPE EDGE")
    inst.write(f":TRIGger:EDGE:SOURce C{channel}")
    inst.write(f":TRIGger:EDGE:LEVel {level}")
    inst.write(f":TRIGger:EDGE:SLOPe {slope}")
 
 
def set_memory_depth(inst, points):
    """Number of datapoints to capture, e.g. "10k", "1M", "10M".
    Legal values depend on the model and number of channels in use --
    see :ACQuire:MDEPth in the Programming Guide."""
    inst.write(f":ACQuire:MDEPth {points}")
 
 
def single_trigger(inst, timeout_s=30):
    """Arm one single acquisition and wait for it to complete. All enabled
    channels are captured together from this one trigger event -- that's
    what makes their waveforms directly comparable afterwards."""
    inst.write(":TRIGger:MODE SINGle")
    inst.write(":TRIGger:RUN")
    start = time.time()
    while inst.query(":TRIGger:STATus?") != "Stop" and time.time() - start < timeout_s:
        time.sleep(0.05)
 
 
def get_waveform(inst, channel):
    """Read one channel's captured waveform. Returns (time_seconds, volts)
    as numpy arrays.
 
    A single :WAVeform:DATA? query can only return up to :WAVeform:MAXPoint
    points at a time, so for large memory depths (e.g. 10M points) this
    reads the waveform in chunks and stitches them back together."""
    # Read this before any of the big binary transfers below -- querying it
    # right after a large :WAVeform:DATA? response can return an empty
    # string on some USB/VISA setups, so it's safest done first.
    seconds_per_div = float(inst.query(":TIMebase:SCALe?"))
 
    inst.write(f":WAVeform:SOURce C{channel}")
    inst.write(":WAVeform:WIDTh WORD")
 
    total_points = int(float(inst.query(":ACQuire:POINts?")))
    max_points = int(float(inst.query(":WAVeform:MAXPoint?")))
 
    codes = []
    preamble = None
    start = 0
    while start < total_points:
        chunk_size = min(max_points, total_points - start)
        inst.write(f":WAVeform:STARt {start}")
        inst.write(f":WAVeform:POINt {chunk_size}")
        if preamble is None:
            # The preamble tells us how to turn raw codes into volts/seconds
            # (byte offsets are from the ":WAVeform:PREamble" table in the guide).
            preamble = inst.query_binary_values(":WAVeform:PREamble?", datatype="B", container=bytes, header_fmt="ieee")
        raw = inst.query_binary_values(":WAVeform:DATA?", datatype="B", container=bytes, header_fmt="ieee")
        codes.append(np.frombuffer(raw, dtype=">i2"))  # 16-bit signed, upper byte first
        start += chunk_size
    codes = np.concatenate(codes)
 
    vertical_gain = struct.unpack_from("<f", preamble, 156)[0]
    vertical_offset = struct.unpack_from("<f", preamble, 160)[0]
    code_per_div = struct.unpack_from("<f", preamble, 164)[0]
    sample_interval = struct.unpack_from("<f", preamble, 176)[0]
    trigger_delay = struct.unpack_from("<d", preamble, 180)[0]
 
    volts = codes * (vertical_gain / code_per_div) - vertical_offset
    t = trigger_delay - 5 * seconds_per_div + np.arange(len(volts)) * sample_interval
    return t, volts
 
 
def save_waveform(inst, filename, t, channels):
    """Save time + one or more channels' voltage, plus the instrument's
    current settings, to a single compressed .npz file (much smaller and
    faster than a CSV at millions of points).
 
    `channels` is a dict of {channel_number: voltage_array}, e.g. {1: v1, 2: v2}.
 
    Load it back with:
        data = np.load("my_measurement.npz")
        t, v1 = data["time_s"], data["CH1_volts"]
        print(str(data["instrument_idn"]), float(data["timebase_s_div"]))
    """
    arrays = {"time_s": t, "instrument_idn": inst.query("*IDN?"), "saved": datetime.now().isoformat(),
              "timebase_s_div": float(inst.query(":TIMebase:SCALe?")),
              "timebase_delay_s": float(inst.query(":TIMebase:DELay?")),
              "trigger_source": inst.query(":TRIGger:EDGE:SOURce?"),
              "trigger_level_v": float(inst.query(":TRIGger:EDGE:LEVel?")),
              "trigger_slope": inst.query(":TRIGger:EDGE:SLOPe?")}
    for ch, v in channels.items():
        arrays[f"CH{ch}_volts"] = v
        arrays[f"CH{ch}_scale_v_div"] = float(inst.query(f":CHANnel{ch}:SCALe?"))
        arrays[f"CH{ch}_offset_v"] = float(inst.query(f":CHANnel{ch}:OFFSet?"))
        arrays[f"CH{ch}_coupling"] = inst.query(f":CHANnel{ch}:COUPling?")
 
    np.savez_compressed(filename, **arrays)
    print("Saved", filename, "-- load it back with np.load()")
 

