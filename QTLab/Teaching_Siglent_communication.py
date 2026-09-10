
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
 
    save_waveform(inst, "my_measurement.csv", t, {1: v1, 2: v2})
"""
 
import struct
import time
from datetime import datetime

import numpy as np
import pyvisa

# Number of horizontal divisions on screen for this model. Used to convert
# the scope's timebase (s/div) into an actual record length in seconds.
HORIZONTAL_DIVISIONS = 10


# ---------------------------------------------------------------------------
# Internal helpers -- retry wrappers for two quirks specific to this
# instrument (see each docstring for the evidence). Everything below this
# section is plain SCPI: write a command, or query and parse the reply.
# ---------------------------------------------------------------------------

def _query(inst, cmd, retries=5, delay=0.05):
    """inst.query(), but retries on an empty reply.

    Right after a large :WAVeform:DATA? block transfer, the very next SCPI
    query sometimes comes back empty (a transport hiccup, not a real error --
    the scope is just still catching its breath). Retrying a few ms later
    always succeeds, so treat that as normal instead of crashing."""
    for attempt in range(retries):
        reply = inst.query(cmd)
        if reply != "":
            return reply
        time.sleep(delay)
    raise RuntimeError(f"Scope gave no reply to {cmd!r} after {retries} retries")


def _query_binary(inst, cmd, retries=3, timeout_ms=60000):
    """inst.query_binary_values(), but recovers from a corrupted/incomplete
    block instead of crashing.

    At large memory depths (e.g. 10M points = 20 MB for one WORD-width
    channel), a :WAVeform:DATA? transfer that gets interrupted -- a timeout
    mid-read, a cell that was manually stopped -- leaves the tail end of
    that block sitting unread in the USB buffer. The *next* read then finds
    those stray bytes instead of a fresh '#' block header and pyvisa raises
    a ValueError. inst.clear() flushes the stale bytes; retrying after that
    reliably recovers. Also gives big transfers more time than the default
    query timeout, since 20+ MB over USB can take longer than 20 s."""
    orig_timeout = inst.timeout
    inst.timeout = timeout_ms
    try:
        for attempt in range(retries):
            try:
                return inst.query_binary_values(
                    cmd, datatype="B", container=bytes, header_fmt="ieee"
                )
            except (ValueError, pyvisa.errors.VisaIOError):
                inst.clear()
                time.sleep(0.2)
        raise RuntimeError(
            f"Scope gave a corrupted/incomplete reply to {cmd!r} after "
            f"{retries} retries, even after flushing the interface. Try "
            f"reconnecting (osc.connect())."
        )
    finally:
        inst.timeout = orig_timeout


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(resource=None):
    """Open a USB connection to the scope.
 
    Prints every VISA resource the computer can see, so you can find the
    right resource name to pass in by hand if auto-detection picks the
    wrong one (e.g. if you have another USB instrument connected too)."""
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    print("Available VISA resources:", resources)
 
    if resource is None:
        resource = [r for r in resources if "SDS08A0D911874" in r][0]
 
    inst = rm.open_resource(resource)
    inst.timeout = 20000
    inst.read_termination = "\n"
    inst.write_termination = "\n"
    print("Connected to:", inst.query("*IDN?"))
    return inst


# ---------------------------------------------------------------------------
# Instrument configuration
# ---------------------------------------------------------------------------

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
 
 
def set_memory_depth(inst, points, retries=5, delay=0.3):
    """Number of datapoints to capture, e.g. "10k", "1M", "10M".
    Legal values depend on the model and number of channels in use --
    see :ACQuire:MDEPth in the Programming Guide.

    Confirmed empirically: this scope silently ignores :ACQuire:MDEPth
    (no SCPI error, just keeps the old value) when the request is sent
    while the acquisition is fully Stopped -- the opposite of the front
    panel, which requires you to STOP before changing it from the menu.
    Over SCPI it only reliably takes effect while the scope is actively
    running, so this puts it into a free-running state, writes the depth,
    and verifies it stuck before returning (retrying a few times, since a
    single attempt occasionally doesn't land). If you call this right
    before single_trigger(), the mode change here is harmless -- that call
    immediately switches to SINGle and re-arms anyway."""
    inst.write(":TRIGger:MODE AUTO")
    inst.write(":TRIGger:RUN")
    time.sleep(0.3)
    for attempt in range(retries):
        inst.write(f":ACQuire:MDEPth {points}")
        time.sleep(delay)
        got = _query(inst, ":ACQuire:MDEPth?")
        if got.strip().lower() == str(points).strip().lower():
            return
    raise RuntimeError(
        f"Requested memory depth {points!r} did not take effect after "
        f"{retries} retries (scope still reports {got!r}). Check it's a "
        f"legal value for your model/channel count (:ACQuire:MDEPth in the "
        f"Programming Guide), and that Memory Management isn't capping it "
        f"lower (:ACQuire:MMANagement?)."
    )


# ---------------------------------------------------------------------------
# Acquisition
# ---------------------------------------------------------------------------

def single_trigger(inst, timeout_s=30, force_on_timeout=False):
    """Arm one single acquisition and wait for it to complete. All enabled
    channels are captured together from this one trigger event -- that's
    what makes their waveforms directly comparable afterwards.

    Raises TimeoutError if the trigger condition is never met, rather than
    returning quietly and letting you read stale data from the previous
    acquisition. Pass force_on_timeout=True to force an acquisition instead
    (useful when you just want to see whatever is on the inputs)."""
    inst.write(":TRIGger:MODE SINGle")
    inst.write(":TRIGger:RUN")
    start = time.time()
    while _query(inst, ":TRIGger:STATus?") != "Stop":
        if time.time() - start > timeout_s:
            if not force_on_timeout:
                raise TimeoutError(
                    f"No trigger within {timeout_s} s (status "
                    f"{_query(inst, ':TRIGger:STATus?')!r}). Check the trigger "
                    f"level/source, or pass force_on_timeout=True."
                )
            inst.write(":TRIGger:MODE FTRIG")
            force_on_timeout = False  # only force once
            start = time.time()
        time.sleep(0.05)
 
 
def get_waveform(inst, channel):
    """Read one channel's captured waveform. Returns (time_seconds, volts)
    as numpy arrays.
 
    A single :WAVeform:DATA? query can only return up to :WAVeform:MAXPoint
    points at a time, so for large memory depths (e.g. 10M points) this
    reads the waveform in chunks and stitches them back together."""
    if _query(inst, ":TRIGger:STATus?") != "Stop":
        raise RuntimeError(
            "The scope is still acquiring -- run single_trigger() first, "
            "otherwise the readout is not one consistent record."
        )
    inst.write(f":WAVeform:SOURce C{channel}")
    inst.write(":WAVeform:WIDTh WORD")

    total_points = int(float(_query(inst, ":ACQuire:POINts?")))
    max_points = int(float(_query(inst, ":WAVeform:MAXPoint?")))
 
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
            preamble = _query_binary(inst, ":WAVeform:PREamble?")
        raw = _query_binary(inst, ":WAVeform:DATA?")
        if not raw:
            # An empty block leaves the USBTMC stream out of step -- every
            # later query then returns ''. Resync before reporting.
            inst.clear()
            raise RuntimeError(
                f"No waveform data for C{channel}: the scope has no "
                f"acquisition in memory. Arm a trigger that actually fires."
            )
        # 16-bit signed, LOW byte first (little-endian). Decoding these as
        # big-endian ('>i2') swaps the bytes, which turns the fine 16-count
        # ADC steps into 256-count jumps and makes the trace collapse onto a
        # handful of discrete levels.
        codes.append(np.frombuffer(raw, dtype="<i2"))
        start += chunk_size
    codes = np.concatenate(codes).astype(np.float64)
 
    vertical_gain = struct.unpack_from("<f", preamble, 156)[0]
    vertical_offset = struct.unpack_from("<f", preamble, 160)[0]
    code_per_div = struct.unpack_from("<f", preamble, 164)[0]
    sample_interval = struct.unpack_from("<f", preamble, 176)[0]
    trigger_delay = struct.unpack_from("<d", preamble, 180)[0]
    probe_attenuation = struct.unpack_from("<f", preamble, 328)[0] or 1.0

    if not code_per_div:
        raise RuntimeError(
            "The waveform preamble is empty (code_per_div = 0), so the raw "
            "codes cannot be scaled to volts -- the scope has no valid "
            f"acquisition for C{channel}."
        )
    # gain/offset in the preamble are referred to the BNC input, i.e. BEFORE
    # probe scaling -- multiply by probe_attenuation to get the volts the
    # probe tip actually sees (what CHANnel:SCALe/OFFSet are expressed in).
    volts = (codes * (vertical_gain / code_per_div) - vertical_offset) * probe_attenuation

    # The scope's trigger point is the horizontal center of the screen, so
    # the first sample is half a screen-width of divisions before it.
    seconds_per_div = float(_query(inst, ":TIMebase:SCALe?"))
    record_start = trigger_delay - (HORIZONTAL_DIVISIONS / 2) * seconds_per_div
    t = record_start + np.arange(len(volts)) * sample_interval
    return t, volts


# ---------------------------------------------------------------------------
# Saving results
# ---------------------------------------------------------------------------

def save_waveform(inst, filename, t, channels):
    """Save time + one or more channels' voltage to a CSV file.
 
    `channels` is a dict of {channel_number: voltage_array}, e.g. {1: v1, 2: v2}.
    The instrument's current settings are written as '#' comment lines at
    the top of the file, above the data."""
    header_lines = [
        f"# instrument: {_query(inst, '*IDN?')}",
        f"# saved: {datetime.now().isoformat()}",
        f"# timebase: {_query(inst, ':TIMebase:SCALe?')} s/div, delay {_query(inst, ':TIMebase:DELay?')} s",
        f"# trigger: {_query(inst, ':TRIGger:EDGE:SOURce?')} edge, level {_query(inst, ':TRIGger:EDGE:LEVel?')} V, slope {_query(inst, ':TRIGger:EDGE:SLOPe?')}",
    ]
    for ch in channels:
        header_lines.append(
            f"# CH{ch}: {_query(inst, f':CHANnel{ch}:SCALe?')} V/div, "
            f"offset {_query(inst, f':CHANnel{ch}:OFFSet?')} V, "
            f"{_query(inst, f':CHANnel{ch}:COUPling?')} coupling"
        )
 
    data = np.column_stack([t] + [channels[ch] for ch in channels])
    column_header = "time_s," + ",".join(f"CH{ch}_volts" for ch in channels)
 
    with open(filename, "w") as f:
        f.write("\n".join(header_lines) + "\n")
        np.savetxt(f, data, delimiter=",", header=column_header, comments="")
 
    print("Saved", filename)
 

