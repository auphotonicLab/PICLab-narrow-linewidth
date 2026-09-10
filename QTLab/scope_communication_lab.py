"""
scope_communication_lab.py

USB control of a Siglent SDS800X HD oscilloscope for the teaching lab.
Every function just sends SCPI commands to the instrument -- see the SDS
Series Programming Guide for the full command reference.

Install once:
    pip install pyvisa pyvisa-py numpy

Example experiment run:

    import scope_communication_lab as scope

    inst = scope.connect()

    scope.set_vertical(inst, 1, volts_per_div=0.5)
    scope.set_vertical(inst, 2, volts_per_div=1.0)
    scope.set_horizontal(inst, seconds_per_div=1e-3)
    scope.set_trigger(inst, channel=1, level=0.1)
    scope.set_memory_depth(inst, "1M")

    scope.single_trigger(inst)
    t, v1 = scope.get_waveform(inst, 1)
    t, v2 = scope.get_waveform(inst, 2)

    scope.save_waveform(inst, "my_measurement.npz", t, {1: v1, 2: v2})

To load a saved measurement back later (e.g. in an analysis script):

    import numpy as np
    data = np.load("my_measurement.npz")
    t, v1 = data["time_s"], data["CH1_volts"]
    print(str(data["instrument_idn"]), float(data["timebase_s_div"]))

Note on the time axis: t starts at zero at the first recorded sample. It is
not referenced to the trigger. Use the laser's sweep-synchronisation signal,
recorded on its own channel, to find where the sweep actually starts.
"""

import struct
import time
from datetime import datetime

import numpy as np
import pyvisa

SERIAL = "SDS08A0D911874"


# ---------------------------------------------------------------------------
# Internal helpers -- retry wrappers for two quirks of this instrument.
# Everything below this section is plain SCPI: write a command, or query
# and parse the reply.
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
    """inst.query_binary_values(), but recovers from a corrupted or
    incomplete block instead of crashing.

    At large memory depths (e.g. 10M points = 20 MB for one WORD-width
    channel), a :WAVeform:DATA? transfer that gets interrupted -- a timeout
    mid-read, a cell that was manually stopped -- leaves the tail end of that
    block sitting unread in the USB buffer. The *next* read then finds those
    stray bytes instead of a fresh '#' block header, and pyvisa raises a
    ValueError. inst.clear() flushes the stale bytes; retrying after that
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
            f"Scope gave a corrupted or incomplete reply to {cmd!r} after "
            f"{retries} retries, even after flushing the interface. Try "
            f"reconnecting with connect()."
        )
    finally:
        inst.timeout = orig_timeout


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(resource=None):
    """Open a USB connection to the scope.

    Prints every VISA resource the computer can see, so you can find the
    right resource name to pass in by hand if the automatic choice picks the
    wrong one (e.g. if another USB instrument is connected too)."""
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
    """A simple edge trigger on one channel."""
    inst.write(":TRIGger:TYPE EDGE")
    inst.write(f":TRIGger:EDGE:SOURce C{channel}")
    inst.write(f":TRIGger:EDGE:LEVel {level}")
    inst.write(f":TRIGger:EDGE:SLOPe {slope}")


def set_memory_depth(inst, points, retries=5, delay=0.3):
    """Number of datapoints to capture, given as a string: "10k", "1M", "10M".
    Legal values depend on the model and the number of channels in use --
    see :ACQuire:MDEPth in the Programming Guide.

    Confirmed empirically: this scope silently ignores :ACQuire:MDEPth (no
    SCPI error, it just keeps the old value) when the request is sent while
    the acquisition is fully stopped -- the opposite of the front panel,
    which requires you to STOP before changing it from the menu. Over SCPI it
    only takes effect while the scope is actively running, so this puts it
    into a free-running state, writes the depth, and checks it stuck before
    returning. Call it before single_trigger(), which re-arms the scope
    anyway; calling it afterwards would throw away the record you just took."""
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
        f"{retries} retries (scope still reports {got!r}). Check that it is a "
        f"legal value for your model and channel count (:ACQuire:MDEPth in "
        f"the Programming Guide), and that Memory Management isn't capping it "
        f"lower (:ACQuire:MMANagement?)."
    )


# ---------------------------------------------------------------------------
# Acquisition
# ---------------------------------------------------------------------------

def single_trigger(inst, timeout_s=30):
    """Arm one single acquisition and wait for it to complete. All enabled
    channels are captured together from this one trigger event -- that is
    what makes their waveforms directly comparable afterwards.

    Raises TimeoutError if the trigger condition is never met, rather than
    returning quietly and letting you read stale data from the previous
    acquisition."""
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
    """Read one channel's captured waveform. Returns (time_seconds, volts)
    as numpy arrays.

    A single :WAVeform:DATA? query can only return up to :WAVeform:MAXPoint
    points at a time, so for large memory depths (e.g. 10M points) this reads
    the waveform in chunks and stitches them back together."""
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
            # The preamble tells us how to turn raw codes into volts and
            # seconds (byte offsets are from the ":WAVeform:PREamble" table
            # in the Programming Guide).
            preamble = _query_binary(inst, ":WAVeform:PREamble?")
        raw = _query_binary(inst, ":WAVeform:DATA?")
        if not raw:
            inst.clear()
            raise RuntimeError(
                f"No waveform data for C{channel}: either the channel is "
                f"switched off, or the scope has no acquisition in memory."
            )
        # 16-bit signed, LOW byte first (little-endian). Decoding these as
        # big-endian ('>i2') swaps the bytes, which turns the fine 16-count
        # ADC steps into 256-count jumps and makes the trace collapse onto a
        # handful of discrete levels.
        codes.append(np.frombuffer(raw, dtype="<i2"))
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

    # t = 0 is the first recorded sample, NOT the trigger. Only time
    # differences matter for anything measured in this lab; to find where
    # the laser sweep starts, look at the sweep-synchronisation signal.
    t = np.arange(len(volts)) * sample_interval
    return t, volts


# ---------------------------------------------------------------------------
# Saving results
# ---------------------------------------------------------------------------

def save_waveform(inst, filename, t, channels):
    """Save time + one or more channels' voltage, plus the instrument's
    current settings, to a single compressed .npz file (much smaller and
    faster than a CSV at millions of points).

    `channels` is a dict of {channel_number: voltage_array}, e.g. {1: v1, 2: v2}.

    The settings are read back from the instrument rather than copied from
    whatever was requested earlier, so the file records what the scope was
    actually doing.

    Load it back with:
        data = np.load("my_measurement.npz")
        t, v1 = data["time_s"], data["CH1_volts"]
        print(str(data["instrument_idn"]), float(data["timebase_s_div"]))
    """
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
