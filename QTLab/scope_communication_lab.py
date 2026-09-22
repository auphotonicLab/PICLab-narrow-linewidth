"""
scope_communication_lab.py

USB control of a Siglent SDS800X HD oscilloscope for the teaching lab.
Sends SCPI commands to the instrument.
"""

import struct
import time
from datetime import datetime

import numpy as np
import pyvisa

SERIAL = "SDS08A0D911874"


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(resource=None):
    """Open a USB connection to the scope. Pass `resource` by hand if
    another USB instrument confuses the automatic serial-number match."""
    rm = pyvisa.ResourceManager()
    resources = rm.list_resources()
    print("Available VISA resources:", resources)

    if resource is None:
        resource = [r for r in resources if SERIAL in r][0]

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
    """A simple edge trigger on one channel. `level` is the trigger voltage, in V."""
    inst.write(":TRIGger:TYPE EDGE")
    inst.write(f":TRIGger:EDGE:SOURce C{channel}")
    inst.write(f":TRIGger:EDGE:LEVel {level}")
    inst.write(f":TRIGger:EDGE:SLOPe {slope}")


def set_memory_depth(inst, points, retries=5, delay=0.3):
    """Number of datapoints to capture, e.g. "10k", "1M", "10M". Legal values
    depend on the model/channel count -- see :ACQuire:MDEPth in the guide.

    The scope only accepts :ACQuire:MDEPth while running, not while stopped,
    so this puts it into free-run first and checks the value stuck. Call it
    before single_trigger(), not after -- that would throw away the record."""
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
        f"legal value for this model/channel count, and that Memory "
        f"Management isn't capping it lower (:ACQuire:MMANagement?)."
    )


# ---------------------------------------------------------------------------
# Acquisition
# ---------------------------------------------------------------------------

def single_trigger(inst, timeout_s=30):
    """Arm one single acquisition and wait for it to complete, so all
    enabled channels come from the same trigger event. Raises TimeoutError
    rather than silently leaving stale data from the previous acquisition."""
    inst.write(":TRIGger:MODE SINGle")
    inst.write(":TRIGger:RUN")
    start = time.time()
    while _query(inst, ":TRIGger:STATus?") != "Stop":
        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"No trigger within {timeout_s} s. Check the trigger level, "
                f"slope and source, and that the laser is actually sweeping."
            )
        time.sleep(0.05)


def get_waveform(inst, channel):
    """Read one channel's captured waveform as (time_seconds, volts) numpy
    arrays. Reads in chunks of :WAVeform:MAXPoint and stitches them together,
    since a single :WAVeform:DATA? query can't return the whole record at
    large memory depths."""
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
            # byte offsets below are from the ":WAVeform:PREamble" table
            preamble = _query_binary(inst, ":WAVeform:PREamble?")
        raw = _query_binary(inst, ":WAVeform:DATA?")
        if not raw:
            inst.clear()
            raise RuntimeError(
                f"No waveform data for C{channel}: either the channel is "
                f"switched off, or the scope has no acquisition in memory."
            )
        codes.append(np.frombuffer(raw, dtype="<i2"))  # little-endian i16
        start += chunk_size
    codes = np.concatenate(codes)

    vertical_gain = struct.unpack_from("<f", preamble, 156)[0]
    vertical_offset = struct.unpack_from("<f", preamble, 160)[0]
    code_per_div = struct.unpack_from("<f", preamble, 164)[0]
    sample_interval = struct.unpack_from("<f", preamble, 176)[0]

    if not code_per_div:
        raise RuntimeError(
            "The waveform preamble is empty (code_per_div = 0), so the raw "
            "codes cannot be scaled to volts -- the scope has no valid "
            f"acquisition for C{channel}."
        )

    volts = codes * (vertical_gain / code_per_div) - vertical_offset
    t = np.arange(len(volts)) * sample_interval
    return t, volts


# ---------------------------------------------------------------------------
# Saving results
# ---------------------------------------------------------------------------

def save_waveform(inst, filename, t, channels):
    """Save time + one or more channels' voltage, plus the instrument's
    current settings, to a compressed .npz file. `channels` is a dict of
    {channel_number: voltage_array}, e.g. {1: v1, 2: v2}. Settings are read
    back from the instrument so the file records what it actually did."""
    arrays = {
        "time_s": t,
        "instrument_idn": _query(inst, "*IDN?"),
        "saved": datetime.now().isoformat(),
        "memory_depth": _query(inst, ":ACQuire:MDEPth?"),
        "sample_rate_hz": float(_query(inst, ":ACQuire:SRATe?")),
        "timebase_s_div": float(_query(inst, ":TIMebase:SCALe?")),
        "timebase_delay_s": float(_query(inst, ":TIMebase:DELay?")),
        "trigger_source": _query(inst, ":TRIGger:EDGE:SOURce?"),
        "trigger_level_v": float(_query(inst, ":TRIGger:EDGE:LEVel?")),
        "trigger_slope": _query(inst, ":TRIGger:EDGE:SLOPe?"),
    }
    for ch, v in channels.items():
        arrays[f"CH{ch}_volts"] = v
        arrays[f"CH{ch}_scale_v_div"] = float(_query(inst, f":CHANnel{ch}:SCALe?"))
        arrays[f"CH{ch}_offset_v"] = float(_query(inst, f":CHANnel{ch}:OFFSet?"))
        arrays[f"CH{ch}_coupling"] = _query(inst, f":CHANnel{ch}:COUPling?")

    np.savez_compressed(filename, **arrays)
    print("Saved", filename, "-- load it back with np.load()")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _query(inst, cmd, retries=5, delay=0.05):
    """inst.query(), retrying on an empty reply (happens right after a big
    :WAVeform:DATA? transfer -- the scope just needs a moment)."""
    for attempt in range(retries):
        reply = inst.query(cmd)
        if reply != "":
            return reply
        time.sleep(delay)
    raise RuntimeError(f"Scope gave no reply to {cmd!r} after {retries} retries")


def _query_binary(inst, cmd, retries=3, timeout_ms=60000):
    """inst.query_binary_values(), recovering from a corrupted/incomplete
    block (happens on large transfers, e.g. 10M points) by flushing with
    inst.clear() and retrying. Also raises the timeout for big transfers."""
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
            f"Scope gave a corrupted or incomplete reply to {cmd!r} after "
            f"{retries} retries, even after flushing the interface. Try "
            f"reconnecting with connect()."
        )
    finally:
        inst.timeout = orig_timeout