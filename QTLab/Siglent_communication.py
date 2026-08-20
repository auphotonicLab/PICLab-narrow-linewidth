"""
siglent_sds800x_hd.py
 
Python control library for a Siglent SDS800X HD oscilloscope, based on the
official SDS Series Programming Guide (SCPI command set).
 
Supports:
    * USB           -> via NI-VISA / pyvisa   (SiglentScope.connect_usb)
    * LAN (VISA)    -> via NI-VISA / pyvisa   (SiglentScope.connect_lan_visa)
    * LAN (sockets) -> raw TCP, no VISA needed (SiglentScope.connect_lan_socket)
 
You can develop against USB now and switch to LAN later just by changing
the connect_* call you use -- everything else in the script stays the same.
 
Requirements:
    pip install pyvisa numpy
    # For USB, and for connect_lan_visa(), you also need NI-VISA (or another
    # VISA runtime) installed on the PC: https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html
    # connect_lan_socket() needs nothing beyond the standard library + numpy.
 
Notes on how a Siglent scope samples multiple channels:
    All *enabled* analog channels are digitized from the same clock and the
    same trigger event -- there is no separate "trigger both channels"
    command. To get channel 1 and channel 2 data that belong to the same
    trigger instant, just make sure both channels are switched ON, arm a
    single acquisition (arm_single_trigger()), and then read out each
    channel's waveform with capture_channel() / capture_channels().
"""
 
from __future__ import annotations
 
import csv
import json
import socket
import struct
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple
 
import numpy as np
 
try:
    import pyvisa
except ImportError:  # pyvisa is optional if you only ever use raw sockets
    pyvisa = None
 
 
# ===========================================================================
# Low-level transports
# ===========================================================================
 
class ScopeConnectionError(RuntimeError):
    pass
 
 
class _VisaTransport:
    """USB or LAN transport using NI-VISA / pyvisa."""
 
    def __init__(self, resource: str, timeout_ms: int = 20000):
        if pyvisa is None:
            raise ScopeConnectionError(
                "pyvisa is not installed. Run: pip install pyvisa"
            )
        self._rm = pyvisa.ResourceManager()
        self._inst = self._rm.open_resource(resource)
        self._inst.timeout = timeout_ms
        self._inst.read_termination = "\n"
        self._inst.write_termination = "\n"
        self._inst.chunk_size = 20 * 1024 * 1024
 
    def write(self, cmd: str) -> None:
        self._inst.write(cmd)
 
    def query(self, cmd: str) -> str:
        return self._inst.query(cmd).strip()
 
    def query_raw_block(self, cmd: str) -> bytes:
        """Send `cmd` and read back an IEEE-488.2 '#N<len><data>' block,
        returning just the payload bytes."""
        data = self._inst.query_binary_values(
            cmd, datatype="B", container=bytes, header_fmt="ieee"
        )
        return data
 
    def close(self) -> None:
        try:
            self._inst.close()
        except Exception:
            pass
 
 
class _SocketTransport:
    """Raw LAN transport straight to the SCPI socket server (port 5025).
    No VISA installation required."""
 
    def __init__(self, ip: str, port: int = 5025, timeout: float = 20.0):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect((ip, port))
        self._buf = b""
 
    def _fill(self, nbytes: int) -> None:
        while len(self._buf) < nbytes:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ScopeConnectionError("Socket closed by instrument")
            self._buf += chunk
 
    def write(self, cmd: str) -> None:
        self._sock.sendall(cmd.encode("ascii") + b"\n")
 
    def query(self, cmd: str) -> str:
        self.write(cmd)
        while b"\n" not in self._buf:
            self._fill(len(self._buf) + 1)
        line, _, self._buf = self._buf.partition(b"\n")
        return line.decode(errors="replace").strip()
 
    def query_raw_block(self, cmd: str) -> bytes:
        self.write(cmd)
        self._fill(2)  # '#' + 1 digit telling how many length-digits follow
        if self._buf[0:1] != b"#":
            raise ScopeConnectionError(f"Expected block header, got {self._buf[:32]!r}")
        ndigits = int(self._buf[1:2])
        header_len = 2 + ndigits
        self._fill(header_len)
        length = int(self._buf[2:header_len])
        total = header_len + length + 2  # +2 trailing terminator bytes ("\n\n")
        self._fill(total)
        data = self._buf[header_len:header_len + length]
        self._buf = self._buf[total:]
        return data
 
    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass
 
 
# ===========================================================================
# Waveform preamble (see ":WAVeform:PREamble" in the Programming Guide)
# ===========================================================================
 
@dataclass
class WaveformPreamble:
    vertical_gain: float          # V/div, without probe attenuation
    vertical_offset: float        # V, without probe attenuation
    code_per_div: float
    adc_bit: int
    horizontal_interval: float    # s, = 1 / sample_rate
    horizontal_offset: float      # s, trigger offset of first point
    wave_array_count: int
    first_point: int
    probe_attenuation: float
    vertical_coupling: int        # 0=DC,1=AC,2=GND
    bandwidth_limit: int          # 0=OFF,1=20M,2=200M
    wave_source: int              # 0=C1,1=C2,2=C3,3=C4,...
 
 
def _parse_preamble(raw: bytes) -> WaveformPreamble:
    return WaveformPreamble(
        vertical_gain=struct.unpack_from("<f", raw, 156)[0],
        vertical_offset=struct.unpack_from("<f", raw, 160)[0],
        code_per_div=struct.unpack_from("<f", raw, 164)[0],
        adc_bit=struct.unpack_from("<h", raw, 172)[0],
        wave_array_count=struct.unpack_from("<i", raw, 116)[0],
        first_point=struct.unpack_from("<i", raw, 132)[0],
        horizontal_interval=struct.unpack_from("<f", raw, 176)[0],
        horizontal_offset=struct.unpack_from("<d", raw, 180)[0],
        vertical_coupling=struct.unpack_from("<h", raw, 326)[0],
        probe_attenuation=struct.unpack_from("<f", raw, 328)[0],
        bandwidth_limit=struct.unpack_from("<h", raw, 334)[0],
        wave_source=struct.unpack_from("<h", raw, 344)[0],
    )
 
 
# ===========================================================================
# Main driver class
# ===========================================================================
 
class SiglentSDS800XHD:
    """Driver for the Siglent SDS800X HD oscilloscope."""
 
    # Number of horizontal divisions on screen for this model (see Programming
    # Guide "Read Waveform Data Example" grid table).
    HORIZONTAL_DIVISIONS = 10
 
    def __init__(self, transport):
        self._t = transport
        self.idn = self.query("*IDN?")
 
    # -- connection helpers -------------------------------------------------
 
    @classmethod
    def connect_usb(cls, visa_resource: Optional[str] = None) -> "SiglentSDS800XHD":
        """Connect over USB via NI-VISA. If `visa_resource` is omitted, the
        first USB VISA instrument found is used."""
        if pyvisa is None:
            raise ScopeConnectionError("pyvisa not installed: pip install pyvisa")
        rm = pyvisa.ResourceManager()
        if visa_resource is None:
            candidates = [r for r in rm.list_resources() if r.startswith("USB")]
            if not candidates:
                raise ScopeConnectionError(
                    f"No USB VISA instruments found. Seen: {rm.list_resources()}"
                )
            visa_resource = candidates[0]
        return cls(_VisaTransport(visa_resource))
 
    @classmethod
    def connect_lan_visa(cls, ip: str) -> "SiglentSDS800XHD":
        """Connect over LAN using VISA/VXI-11. Requires NI-VISA."""
        return cls(_VisaTransport(f"TCPIP0::{ip}::inst0::INSTR"))
 
    @classmethod
    def connect_lan_socket(cls, ip: str, port: int = 5025) -> "SiglentSDS800XHD":
        """Connect over LAN using a raw SCPI socket. No VISA required."""
        return cls(_SocketTransport(ip, port))
 
    def close(self) -> None:
        self._t.close()
 
    def __enter__(self):
        return self
 
    def __exit__(self, *exc):
        self.close()
 
    # -- low level ------------------------------------------------------
 
    def write(self, cmd: str) -> None:
        self._t.write(cmd)
 
    def query(self, cmd: str) -> str:
        return self._t.query(cmd)
 
    def query_float(self, cmd: str) -> float:
        return float(self.query(cmd))
 
    # -- vertical (channel) settings ------------------------------------
 
    def configure_channel(self, channel: int, *, enabled: bool = True, scale: Optional[float] = None, offset: Optional[float] = None, coupling: Optional[str] = None, probe_attenuation: Optional[float] = None, bandwidth_limit: Optional[str] = None, impedance: Optional[str] = None, unit: Optional[str] = None, label: Optional[str] = None) -> None:
        """Configure the vertical settings of one analog channel (1..N).
 
        scale/offset are in V/div and V. coupling is "DC"|"AC"|"GND".
        bandwidth_limit is "FULL"|"20M"|"200M". impedance is "ONEMeg"|"FIFTy".
        unit is "V"|"A"."""
        self.write(f":CHANnel{channel}:SWITch {'ON' if enabled else 'OFF'}")
        if probe_attenuation is not None:
            # Set this before SCALe/OFFSet since it changes their meaning.
            self.write(f":CHANnel{channel}:PROBe VALue,{probe_attenuation:.6E}")
        if impedance is not None:
            self.write(f":CHANnel{channel}:IMPedance {impedance}")
        if coupling is not None:
            self.write(f":CHANnel{channel}:COUPling {coupling}")
        if scale is not None:
            self.write(f":CHANnel{channel}:SCALe {scale:.6E}")
        if offset is not None:
            self.write(f":CHANnel{channel}:OFFSet {offset:.6E}")
        if bandwidth_limit is not None:
            self.write(f":CHANnel{channel}:BWLimit {bandwidth_limit}")
        if unit is not None:
            self.write(f":CHANnel{channel}:UNIT {unit}")
        if label is not None:
            self.write(f':CHANnel{channel}:LABel:TEXT "{label}"')
            self.write(f":CHANnel{channel}:LABel ON")
 
    # -- horizontal (timebase) settings ----------------------------------
 
    def configure_horizontal(self, *, scale: Optional[float] = None, delay: Optional[float] = None) -> None:
        """scale is s/div, delay is s."""
        if scale is not None:
            self.write(f":TIMebase:SCALe {scale:.6E}")
        if delay is not None:
            self.write(f":TIMebase:DELay {delay:.6E}")
 
    # -- acquisition (memory depth / datapoints / acquisition type) -----
 
    def set_memory_depth(self, points) -> None:
        """`points` must be one of the enumerated values for your model/
        channel-count, e.g. "10M", "1M", "100k" (see :ACQuire:MDEPth in the
        Programming Guide for the SDS800X HD table)."""
        self.write(f":ACQuire:MDEPth {points}")
 
    def set_acquisition_type(self, acq_type: str = "NORMal", averages: Optional[int] = None, eres_bits: Optional[float] = None) -> None:
        """`acq_type`: "NORMal" | "PEAK" | "AVERage" | "ERES".
        `averages` (with AVERage) one of 4,16,32,...,8192.
        `eres_bits` (with ERES) one of 0.5,1.0,...,4.0."""
        t = acq_type.upper()
        if t.startswith("AVER") and averages:
            self.write(f":ACQuire:TYPE AVERage,{averages}")
        elif t.startswith("ERES") and eres_bits:
            self.write(f":ACQuire:TYPE ERES,{eres_bits}")
        else:
            self.write(f":ACQuire:TYPE {acq_type}")
 
    # -- trigger ----------------------------------------------------------
 
    def configure_edge_trigger(self, *, source: str = "C1", level: float = 0.0, slope: str = "RISing", coupling: str = "DC", mode: str = "NORMal") -> None:
        """source: "C1".."C4"|"D0".."Dn"|"EX"|"EX5"|"LINE". level in V.
        slope: "RISing"|"FALLing"|"ALTernate". coupling: "DC"|"AC"|"HFREJect"|"LFREJect".
        mode: "AUTO"|"NORMal"|"SINGle"|"FTRIG"."""
        self.write(":TRIGger:TYPE EDGE")
        self.write(f":TRIGger:EDGE:SOURce {source}")
        self.write(f":TRIGger:EDGE:LEVel {level:.6E}")
        self.write(f":TRIGger:EDGE:SLOPe {slope}")
        self.write(f":TRIGger:EDGE:COUPling {coupling}")
        self.write(f":TRIGger:MODE {mode}")
 
    def arm_single_trigger(self, timeout_s: float = 30.0, poll_interval: float = 0.05) -> bool:
        """Arms a SINGLE acquisition and blocks until the scope has
        triggered and finished capturing (status goes to "Stop"), or until
        `timeout_s` elapses. All enabled channels are captured together on
        this one trigger event -- read them out afterwards with
        capture_channel()/capture_channels()."""
        self.write(":TRIGger:MODE SINGle")
        self.write(":TRIGger:RUN")
        t0 = time.time()
        while True:
            status = self.query(":TRIGger:STATus?").strip().lower()
            if status == "stop":
                return True
            if time.time() - t0 > timeout_s:
                return False
            time.sleep(poll_interval)
 
    def force_trigger(self) -> None:
        """Forces an immediate acquisition regardless of trigger conditions."""
        self.write(":TRIGger:MODE FTRIG")
 
    def run(self) -> None:
        self.write(":TRIGger:RUN")
 
    def stop(self) -> None:
        self.write(":TRIGger:STOP")
 
    # -- waveform capture --------------------------------------------------
 
    @staticmethod
    def _decode_codes(raw: bytes, width: str) -> np.ndarray:
        if width.upper().startswith("BYTE"):
            return np.frombuffer(raw, dtype=np.int8)
        # WORD: 16-bit, upper byte transmitted first -> big-endian.
        return np.frombuffer(raw, dtype=">i2")
 
    def capture_channel(self, channel: int, width: str = "WORD", points: Optional[int] = None, chunked: bool = True) -> Tuple[np.ndarray, np.ndarray, WaveformPreamble]:
        """Reads one channel's captured waveform as (time_s, voltage_v,
        preamble). Does NOT trigger the scope -- call arm_single_trigger()
        (or force_trigger()) first so the data is fresh.
 
        Automatically reads the waveform in chunks of :WAVeform:MAXPoint if
        the requested number of points exceeds what a single query can
        return (relevant for large memory depths)."""
        self.write(f":WAVeform:SOURce C{channel}")
        self.write(f":WAVeform:WIDTh {width}")
 
        max_point = int(self.query_float(":WAVeform:MAXPoint?"))
        total_points = points or int(self.query_float(":ACQuire:POINts?"))
 
        codes_chunks = []
        preamble = None
        start = 0
        while start < total_points:
            npts = min(max_point, total_points - start) if chunked else total_points
            self.write(f":WAVeform:STARt {start}")
            self.write(f":WAVeform:POINt {npts}")
            if preamble is None:
                raw_pre = self._t.query_raw_block(":WAVeform:PREamble?")
                preamble = _parse_preamble(raw_pre)
            raw_data = self._t.query_raw_block(":WAVeform:DATA?")
            codes_chunks.append(self._decode_codes(raw_data, width))
            start += npts
            if not chunked:
                break
 
        codes = np.concatenate(codes_chunks)
 
        voltage = codes.astype(np.float64) * (preamble.vertical_gain / preamble.code_per_div) \
            - preamble.vertical_offset
 
        # Live timebase scale (s/div); simpler & safer than decoding the
        # preamble's timebase enum, which is model-dependent.
        tdiv = self.query_float(":TIMebase:SCALe?")
        delay = preamble.horizontal_offset
        interval = preamble.horizontal_interval
        n = len(voltage)
        index = np.arange(n)
        time_s = delay - (tdiv * self.HORIZONTAL_DIVISIONS / 2) + index * interval
 
        return time_s, voltage, preamble
 
    def capture_channels(self, channels: Sequence[int] = (1, 2), width: str = "WORD") -> Dict[int, dict]:
        """Reads out several channels (already-acquired data -- call
        arm_single_trigger() once beforehand so they all come from the same
        trigger event)."""
        result = {}
        for ch in channels:
            t, v, pre = self.capture_channel(ch, width=width)
            result[ch] = {"time": t, "voltage": v, "preamble": pre}
        return result
 
    # -- settings snapshot (for saving alongside data) ---------------------
 
    def get_settings_snapshot(self, channels: Sequence[int] = (1, 2)) -> dict:
        snap = {
            "idn": self.idn,
            "timestamp": datetime.now().isoformat(),
            "timebase": {
                "scale_s_div": self.query_float(":TIMebase:SCALe?"),
                "delay_s": self.query_float(":TIMebase:DELay?"),
            },
            "acquire": {
                "memory_depth": self.query(":ACQuire:MDEPth?"),
                "sample_rate_sa_s": self.query_float(":ACQuire:SRATe?"),
                "points": self.query_float(":ACQuire:POINts?"),
                "type": self.query(":ACQuire:TYPE?"),
                "mem_management": self.query(":ACQuire:MMANagement?"),
            },
            "trigger": {
                "type": self.query(":TRIGger:TYPE?"),
                "mode": self.query(":TRIGger:MODE?"),
                "status": self.query(":TRIGger:STATus?"),
                "edge_source": self.query(":TRIGger:EDGE:SOURce?"),
                "edge_level_v": self.query_float(":TRIGger:EDGE:LEVel?"),
                "edge_slope": self.query(":TRIGger:EDGE:SLOPe?"),
                "edge_coupling": self.query(":TRIGger:EDGE:COUPling?"),
            },
            "channels": {},
        }
        for ch in channels:
            snap["channels"][str(ch)] = {
                "enabled": self.query(f":CHANnel{ch}:SWITch?"),
                "scale_v_div": self.query_float(f":CHANnel{ch}:SCALe?"),
                "offset_v": self.query_float(f":CHANnel{ch}:OFFSet?"),
                "coupling": self.query(f":CHANnel{ch}:COUPling?"),
                "probe_attenuation": self.query_float(f":CHANnel{ch}:PROBe?"),
                "bandwidth_limit": self.query(f":CHANnel{ch}:BWLimit?"),
                "impedance": self.query(f":CHANnel{ch}:IMPedance?"),
                "unit": self.query(f":CHANnel{ch}:UNIT?"),
            }
        return snap
 
    # -- top level convenience: capture + save ------------------------------
 
    def save_capture(self, name: str, channels: Sequence[int] = (1, 2), out_dir: str = ".", width: str = "WORD", description: str = "", also_csv: bool = True, arm: bool = True) -> Path:
        """One-call workflow: (optionally) arm + wait for a single trigger,
        read out `channels`, and write everything to disk under a folder
        named after `name` plus a timestamp:
 
            <out_dir>/<name>_<YYYYmmdd_HHMMSS>/
                waveform.npz    - compressed numpy arrays: time, ch<N>_voltage
                waveform.csv    - the same data, human readable  (optional)
                settings.json   - full scope settings snapshot + your name/description
 
        Returns the folder Path that was created.
        """
        if arm:
            ok = self.arm_single_trigger()
            if not ok:
                raise TimeoutError("Timed out waiting for the scope to trigger")
 
        data = self.capture_channels(channels, width=width)
        settings = self.get_settings_snapshot(channels)
        settings["capture_name"] = name
        settings["description"] = description
        # preambles aren't JSON-serialisable dataclasses by default -> convert
        settings["waveform_preamble"] = {
            str(ch): vars(d["preamble"]) for ch, d in data.items()
        }
 
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name) or "capture"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = Path(out_dir) / f"{safe_name}_{stamp}"
        folder.mkdir(parents=True, exist_ok=True)
 
        ref_time = None
        npz_kwargs = {}
        for ch, d in data.items():
            npz_kwargs[f"ch{ch}_voltage"] = d["voltage"]
            if ref_time is None:
                ref_time = d["time"]
        npz_kwargs["time"] = ref_time
        np.savez_compressed(folder / "waveform.npz", **npz_kwargs)
 
        with open(folder / "settings.json", "w") as f:
            json.dump(settings, f, indent=2, default=str)
 
        if also_csv:
            with open(folder / "waveform.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["time_s"] + [f"ch{ch}_volt" for ch in channels])
                cols = [data[ch]["voltage"] for ch in channels]
                for i, t in enumerate(ref_time):
                    w.writerow([t] + [c[i] for c in cols])
 
        return folder
 
 
# ===========================================================================
# Example usage
# ===========================================================================
 
if __name__ == "__main__":
    # --- 1. Connect -------------------------------------------------------
    # Start on USB:
    scope = SiglentSDS800XHD.connect_usb()
    # Later, to switch to LAN, use one of these instead (same API from here on):
    #   scope = SiglentSDS800XHD.connect_lan_visa("192.168.1.50")
    #   scope = SiglentSDS800XHD.connect_lan_socket("192.168.1.50")
 
    print("Connected to:", scope.idn)
 
    # --- 2. Vertical settings for both channels ----------------------------
    scope.configure_channel(
        1, enabled=True, scale=0.5, offset=0.0, coupling="DC",
        probe_attenuation=10.0, bandwidth_limit="FULL", label="CH1",
    )
    scope.configure_channel(
        2, enabled=True, scale=1.0, offset=0.0, coupling="DC",
        probe_attenuation=10.0, bandwidth_limit="FULL", label="CH2",
    )
 
    # --- 3. Horizontal settings ---------------------------------------------
    scope.configure_horizontal(scale=1e-3, delay=0.0)  # 1 ms/div, centered
 
    # --- 4. Trigger (edge on channel 1) -------------------------------------
    scope.configure_edge_trigger(source="C1", level=0.1, slope="RISing", coupling="DC")
 
    # --- 5. Memory depth / number of datapoints ------------------------------
    scope.set_memory_depth("1M")  # must be a legal value for your model/#channels
 
    # --- 6. Trigger once and read out both channels together ----------------
    folder = scope.save_capture(
        name="power_supply_ripple_test",   # <- your descriptive name here
        channels=(1, 2),
        description="Ripple measurement at 5V/2A load, 1ms/div",
    )
    print("Saved capture to:", folder)
 
    scope.close()