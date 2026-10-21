"""Offline tests - no instrument, no Windows needed:   python -m pytest test_lwa_utils_offline.py -q

1. the shared-memory decoding against absolute addresses taken from lwaData.dll's machine code
2. the command encoding against what lwaData.dll sends
3. the analysis formulas against exact results
4. the full capture / averaging / settings / saving flow against a simulated GUI that implements the protocol
   as decoded from LWA_Control.exe
"""
import json
import struct

import numpy as np
import pytest

import lwa_utils as L

STATUS_BASE = 0x5684C8      # lwaData.dll's private copy of the status record
DATA_BASE = 0x568B10        # ... of the time-data map


# ---------------------------------------------------------------- 1. layout
def test_layout_matches_dll_addresses():
    assert L.OFF_HWND == 0x5684D0 - STATUS_BASE
    assert L.OFF_READY == 0x5684DA - STATUS_BASE
    assert L.OFF_COUNT == 0x5684E0 - STATUS_BASE
    for i, addr in enumerate([0x568768, 0x568780, 0x568798, 0x5687B0, 0x5687C8, 0x5687E0, 0x5687F8]):
        assert L.cell(L.G_STATES, i) == addr - STATUS_BASE          # GetDigitizerState ... GetPolControlState
    assert L.cell(L.G_RESULTS, 0) + 8 == 0x5689E0 - STATUS_BASE      # Get_Linewidths value
    assert L.cell(L.G_RESULTS, 0) + 16 == 0x5689E8 - STATUS_BASE     # ... and its 'new' flag
    assert L.cell(L.G_MISC, 7) + 8 == 0x568950 - STATUS_BASE         # SetLineshapeTimeInt double
    assert L.cell(5, 0) == L.STATUS_SIZE
    assert L.GROUP_STRIDE == 0x27 * 8


def test_data_header():
    b = bytearray(0x28)
    b[0x568B20 - DATA_BASE] = 1
    struct.pack_into("<i", b, 0x568B24 - DATA_BASE, 600000)
    struct.pack_into("<d", b, 0x568B30 - DATA_BASE, 0.0)        # 3rd arg of _Set_xxxData = first x
    struct.pack_into("<d", b, 0x568B28 - DATA_BASE, 3.0e7)      # 4th arg = last x
    h = L.parse_data_header(bytes(b))
    assert h == {"valid": True, "n": 600000, "x_first": 0.0, "x_last": 3.0e7}


# ---------------------------------------------------------------- 2. commands
def test_command_encoding_matches_dll():
    # lwaData.dll: SetAnalyzerPowermode(m) -> (0x20002, 0x20000|m); SetLineshapeFitFun(i) -> (0x20004, 0x80000|i)
    assert (2 << 16) | L.PANEL_ANALYZER == 0x20002
    assert L.lparam(L.ANALYZER_ROWS["power_mode"][0], 1) == 0x20001
    assert (2 << 16) | L.PANEL_EVALUATION == 0x20004
    assert L.lparam(L.EVALUATION_ROWS["fit_function"][0], 2) == 0x80002
    assert L.lparam(L.EVALUATION_ROWS["lineshape_time_int_s"][0], 3) == 0x70003   # SetLineshapeTimeInt
    assert (1 << 16) | L.REQ_DATA == 0x10007 and (1 << 16) | L.REQ_BINNING == 0x10008
    assert (2 << 16) | L.PANEL_CAPTURE == 0x20006                                   # StartMeasurement


def test_option_index():
    assert L.option_index("cutoff", "1 kHz", L.ANALYZER_ROWS["cutoff"][1]) == 1
    assert L.option_index("range_V", "AUTO", L.DIGITIZER_ROWS["range_V"][1]) == 11
    assert L.option_index("intrinsic", "mode(stat)", L.EVALUATION_ROWS["intrinsic"][1]) == 1
    assert L.option_index("noise_autoeval", True, L.EVALUATION_ROWS["noise_autoeval"][1]) == 1
    with pytest.raises(ValueError):
        L.option_index("cutoff", "5kHz", L.ANALYZER_ROWS["cutoff"][1])


def test_decode_table_gui_defaults():
    # default tables in LWA_Control.exe's data section
    assert L.decode_table([11, 0, 9, 0, 1, 0], L.DIGITIZER_ROWS) == {
        "range_V": "auto", "coupling": "AC", "range_Hz": "30MHz", "res_Hz": 0, "continuous": "On", "averaging": "Off"}
    assert L.decode_table([0, 0, 0, 0], L.ANALYZER_ROWS)["cutoff"] == "10Hz"


# ---------------------------------------------------------------- 3. analysis
def test_white_noise_linewidths_exact():
    dnu = 5e3                                   # Lorentzian FWHM
    f = np.linspace(0, 3e7, 600001)
    s = np.full_like(f, dnu / np.pi)            # white FN: S0 = dnu / pi  (Hz^2/Hz)
    assert L.intrinsic_linewidth(f, s, (5e6, 6e6)) == pytest.approx(dnu, rel=1e-9)
    # beta line crosses S0 at f_c = pi^2 S0 / (8 ln2) -> sqrt(8 ln2 S0 f_c) = pi S0 = dnu
    assert L.beta_separation_linewidth(f, s) == pytest.approx(dnu, rel=1e-2)   # bin quantisation at the crossing
    # GUI formula: sqrt(8 ln2 * sum(S df)) over bins above the line - check against a hand computation
    m = s > 8 * np.log(2) * f / np.pi ** 2
    assert L.beta_separation_linewidth(f, s) == pytest.approx(np.sqrt(8 * np.log(2) * s[m].sum() * 50.0), rel=1e-12)
    # GUI-like Mode(stat) on a single exponential periodogram ~ pi*S0/2
    rng = np.random.default_rng(1)
    s1 = (dnu / np.pi) * rng.exponential(size=f.size)
    assert L.intrinsic_mode_amplitude(f, s1) == pytest.approx(dnu / 2, rel=0.15)


def test_units_and_guess():
    f = np.linspace(0, 3e7, 30001)
    y_rt = np.full_like(f, np.sqrt(1000 / np.pi))          # published in Hz/rtHz
    assert L.guess_noise_unit(f, y_rt, 1000.0) == "Hz/rtHz"
    assert L.guess_noise_unit(f, y_rt ** 2, 1000.0) == "Hz2/Hz"
    assert L.guess_noise_unit(f, y_rt, None) is None


def test_db_data_averaged_in_linear_power():
    x = np.linspace(50, 1e7, 1000)
    rng = np.random.default_rng(0)
    p_lin = 1e-13 * rng.exponential(size=(50, x.size))          # periodogram-like scatter
    caps = [{"t_start": 0, "duration_s": 0.1, "states_nominal": True, "noise": {"x": x, "y": 10 * np.log10(pl)}}
            for pl in p_lin]
    avg = L.average_captures(caps, ("noise",))
    assert avg["noise"]["scale"] == "db"
    assert np.allclose(avg["noise"]["y"], 10 * np.log10(p_lin.mean(axis=0)))
    # dB averaging would be ~2.5 dB too low for exponential statistics
    assert np.median(avg["noise"]["y"] - np.mean(10 * np.log10(p_lin), axis=0)) > 2.0
    # GUI-compatible averaging: RIN = mean of dB, FN = amplitude average (mean sqrt(S))^2
    gui = L.average_captures(caps, ("noise",), mode="gui")
    assert np.allclose(gui["noise"]["y"], np.mean(10 * np.log10(p_lin), axis=0))
    two = [dict(c, noise={"x": x, "y": np.full_like(x, v)}) for c, v in zip(caps[:2], (9.0, 16.0))]
    assert np.allclose(L.average_captures(two, ("noise",), mode="gui")["noise"]["y"], 12.25)   # ((3+4)/2)^2
    assert np.allclose(L.average_captures(two, ("noise",))["noise"]["y"], 12.5)
    # amplitude averaging of exponential spectra reads pi/4 + (1-pi/4)/n low (0.807 at n = 10, as the GUI)
    E = rng.exponential(size=(10, 200000))
    capsE = [{"t_start": 0, "duration_s": 0, "states_nominal": True, "noise": {"x": np.arange(200000.), "y": e}}
             for e in E]
    ratio = L.average_captures(capsE, ("noise",), mode="gui")["noise"]["y"].mean()
    assert ratio == pytest.approx(np.pi / 4 + (1 - np.pi / 4) / 10, rel=0.01)


def test_gui_format_file_is_readable_like_a_gui_export(tmp_path):
    x = np.linspace(49.99996, 9999992, 2001)
    y = np.full_like(x, 20.0)
    p = tmp_path / "t_PSD.txt"
    L.write_gui_format(p, x, y, fn=True, n_avg=10, effective=4300.5, intrinsic=62.8)
    lines = p.read_text(encoding="latin-1").splitlines()
    assert len([ln for ln in lines if ln.startswith("#")]) == 12 and lines[12].startswith("Frequency [Hz],")
    # lwa_lib.LWA logic: header row 13 -> data; linewidth from header line 11
    assert float(lines[11].split()[1][:-2]) == 62.8
    # power average -> no dB-averaging correction in Bias_tee/rin_utils (Averaging=0); 'gui' -> GUI meaning
    assert "#Averaging=0" in lines and "#Av count= 0" in lines and "power average of 10" in lines[9]
    L.write_gui_format(tmp_path / "g.txt", x, y, fn=False, n_avg=10, averaging="gui")
    g = (tmp_path / "g.txt").read_text(encoding="latin-1").splitlines()
    assert "#Averaging=1" in g and "#Av count= 10" in g
    d = np.loadtxt(lines[13:], delimiter=",")
    assert d.shape == (2001, 2) and np.allclose(d[:, 1], 20.0)
    assert "Frequency" in lines[12].split()[1]


def test_level_command_and_rin_binned(tmp_path, capsys):
    x = np.linspace(50, 1e7, 200000)
    rng = np.random.default_rng(3)
    E = rng.exponential(size=(10, x.size)) * 1e-13                       # RIN-like noise, linear
    caps = [{"t_start": 0, "duration_s": 0, "states_nominal": True, "noise": {"x": x, "y": 10 * np.log10(e)}}
            for e in E]
    pw, gui = L.average_captures(caps, ("noise",)), L.average_captures(caps, ("noise",), mode="gui")
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    np.savetxt(a, np.column_stack([x, pw["noise"]["y"]]), delimiter=",", header="x,y", comments="")
    np.savetxt(b, np.column_stack([x, gui["noise"]["y"]]), delimiter=",", header="x,y", comments="")
    assert L.main(["level", str(a), str(b)]) == 0
    out = capsys.readouterr().out
    med = float(out.split("median ")[1].split(" dB")[0])
    assert med == pytest.approx(-2.17, abs=0.08)                          # dB averaging, n = 10
    meta = L.save_measurement(tmp_path, "r", pw, ("noise",), {}, {}, bins_per_decade=10)
    h = L.read_h5(tmp_path / "r.h5")
    rb = h["noise"]["binned"]["y"]
    assert np.all(rb < 0) and abs(np.median(rb) + 130) < 1                # RIN binned in dB, linear bin means
    assert h["noise"]["_attrs"]["unit"] == "dB/Hz" and h["noise"]["captures"].shape == (10, x.size)
    assert not list(tmp_path.glob("*.csv"))[2:] and not list(tmp_path.glob("*.npz"))   # only a.csv/b.csv
    assert (tmp_path / "r_RIN.txt").exists() and "intrinsic_linewidth_Hz_python" not in meta["analysis"]


def test_h5_is_compressed_and_roundtrips(tmp_path):
    import h5py
    y = np.random.default_rng(0).normal(size=(10, 5000))
    L.write_h5(tmp_path / "x.h5", {"noise": {"_attrs": {"unit": "Hz2/Hz"}, "x": np.arange(5000.), "captures": y},
                                   "meta_is_attr": "yes"}, {"n": 10, "plan": {"a": 1}, "flag": True, "none": None})
    with h5py.File(tmp_path / "x.h5") as f:
        assert f["noise/captures"].compression == "gzip"
    r = L.read_h5(tmp_path / "x.h5")
    assert np.array_equal(r["noise"]["captures"], y) and r["noise"]["_attrs"]["unit"] == "Hz2/Hz"
    assert r["_attrs"]["n"] == 10 and json.loads(r["_attrs"]["plan"]) == {"a": 1} and r["_attrs"]["flag"]


def test_log_bin():
    x = np.linspace(1, 1e6, 100000)
    xb, yb = L.log_bin(x, np.ones_like(x), 10)
    assert np.allclose(yb, 1) and np.all(np.diff(xb) > 0) and 40 <= len(xb) <= 61   # empty low bins dropped


# ---------------------------------------------------------------- 4. simulated GUI
class FakeGUI:
    """In-memory implementation of the GUI side, as decoded from LWA_Control.exe."""

    def __init__(self, n=2001):
        self.mem = {L.STATUS_MAP: bytearray(L.STATUS_SIZE)}
        for m in L.DATA_MAPS.values():
            self.mem[m] = bytearray(L.DATA_HDR + 8 * n)
        st = self.mem[L.STATUS_MAP]
        struct.pack_into("<i", st, 0, L.STATUS_SIZE)
        struct.pack_into("<Q", st, L.OFF_HWND, 0xABC)
        for i, v in enumerate([1, 1, 0, 1, 0, 0, 0]):
            struct.pack_into("<i", st, L.cell(L.G_STATES, i), v)
        self.dig = [11, 0, 9, 50, 1, 0]          # GUI-side tables
        self.ana = [0, 0, 0, 0]
        self.eval = [1, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 1, 0, 0]
        self.req = [False, False, False]
        self.binning = None
        self.n = n
        self.captures = 0
        self.log = []

    def read(self, name, nbytes):
        return bytes(self.mem[name][:nbytes]) if name in self.mem else None

    def write(self, name, off, data):
        self.mem[name][off:off + len(data)] = data

    def _set_array(self, group, vals, dtype="i"):
        st = self.mem[L.STATUS_MAP]
        for i, v in enumerate(vals):
            if dtype == "i":
                struct.pack_into("<i", st, L.cell(group, i), v)
            else:
                struct.pack_into("<d", st, L.cell(group, i) + 8, v)
            st[L.cell(group, i) + 16] = 1

    def _publish(self, k, name, y, x0, x1):
        b = self.mem[L.DATA_MAPS[name]]
        struct.pack_into("<i", b, 0x14, len(y))
        b[0x10] = 1
        struct.pack_into("<d", b, 0x18, x1)
        struct.pack_into("<d", b, 0x20, x0)
        b[L.DATA_HDR:L.DATA_HDR + 8 * len(y)] = np.asarray(y, "<f8").tobytes()
        st = self.mem[L.STATUS_MAP]
        st[L.OFF_READY + k] = 1
        struct.pack_into("<i", st, L.OFF_COUNT + 4 * k, len(y))

    def send(self, group, panel, row=0, value=0):
        self.log.append((group, panel, row, value))
        if group == 2 and panel == L.PANEL_DIGITIZER:
            self.dig[row] = value
        elif group == 2 and panel == L.PANEL_ANALYZER:
            self.ana[row] = value
        elif group == 2 and panel == L.PANEL_EVALUATION:
            self.eval[row] = value
        elif group == 1 and panel == L.REQ_PUBLISH_DIGITIZER:
            self._set_array(L.G_DIGITIZER, self.dig)
        elif group == 1 and panel == L.REQ_PUBLISH_ANALYZER:
            self._set_array(L.G_ANALYZER, self.ana)
        elif group == 1 and panel == L.REQ_PUBLISH_RESULTS:      # real GUI: overwrites with its zero table
            self._set_array(L.G_RESULTS, [0.0] * 5, "d")
        elif group == 1 and panel == L.REQ_BINNING:
            self.binning = value
        elif group == 1 and panel == L.REQ_DATA:
            self.req = [bool(value & 1), bool(value & 2), bool(value & 4)]
            self.eval[0], self.eval[4] = int(self.req[1]), int(self.req[2])   # autoeval follows the request
            self.captures += 1
            rng = np.random.default_rng(self.captures)
            if self.req[1]:
                self._publish(1, "noise", np.sqrt(1000 / np.pi) * (1 + 0.01 * rng.standard_normal(self.n)), 0, 3e7)
            if self.req[2]:
                self._publish(2, "lineshape", np.exp(-np.linspace(-5, 5, self.n) ** 2), -1e6, 1e6)
            # the GUI writes its results itself after each evaluation (flag 'new'); fit slots only with lineshape
            self._set_array(L.G_RESULTS, [1000.0 + self.captures, 2e4], "d")
            if self.req[0]:
                self._publish(0, "time", rng.standard_normal(self.n), 0, 1e-3)
        return 0


@pytest.fixture
def gui(monkeypatch):
    g = FakeGUI()
    monkeypatch.setattr(L, "IS_WINDOWS", True)
    monkeypatch.setattr(L, "read_shared", g.read)
    monkeypatch.setattr(L, "write_shared", g.write)
    monkeypatch.setattr(L, "_process_path", lambda pid: r"C:\LWA\LWA_Control.exe")

    class U32:
        IsWindow = staticmethod(lambda h: h == 0xABC)
        GetWindowThreadProcessId = staticmethod(lambda h, p: 0)
    monkeypatch.setattr(L, "_u32", U32, raising=False)

    class WT:
        DWORD = lambda *a: type("D", (), {"value": 1})()   # noqa: E731
    monkeypatch.setattr(L, "wt", WT, raising=False)
    monkeypatch.setattr(L.ctypes, "byref", lambda x: x)
    monkeypatch.setattr(L.LWA1k, "send", lambda self, *a: g.send(*a))
    monkeypatch.setattr(L, "find_gui_window", lambda stored: (stored, 1, "stored handle"))
    return g


def test_connect_sets_raw_output(gui):
    dev = L.LWA1k(verbose=False)
    assert gui.binning == 0 and dev.hwnd == 0xABC


def test_settings_blocked_by_default(gui):
    dev = L.LWA1k(verbose=False)
    with pytest.raises(L.LWAError, match="disabled"):
        dev.set_analyzer(cutoff="1kHz")
    with pytest.raises(L.LWAError):
        dev.set_evaluation(lineshape_time_int_s=0.5)
    assert not [m for m in gui.log if m[0] == 2]          # nothing was sent


def test_settings_roundtrip(gui):
    dev = L.LWA1k(verbose=False, allow_settings=True)
    dev.set_analyzer(cutoff="1kHz", noise_mode="FN")
    dev.set_digitizer(range_V="100mV", range_Hz="15MHz")
    dev.set_evaluation(fit_function="Voigt", intrinsic="Mode(stat)", lineshape_time_int_s=0.5)
    s = dev.read_settings()
    assert s["analyzer"]["cutoff"] == "1kHz"
    assert s["digitizer"]["range_V"] == "100mV" and s["digitizer"]["range_Hz"] == "15MHz"
    assert s["digitizer"]["averaging"] == "Off" and s["digitizer"]["res_Hz"] == 50
    assert gui.eval[8] == 2 and gui.eval[13] == 1
    assert s["lineshape_time_int_s"] == 0.5 and (2, 4, 7, 3) in gui.log
    with pytest.raises(L.LWAError):          # Averaging is not remotely settable
        dev._set_rows(L.PANEL_DIGITIZER, L.DIGITIZER_ROWS, L.DIGITIZER_SETTABLE, L.G_DIGITIZER, averaging="Binned")
    gui.mem[L.STATUS_MAP][L.cell(L.G_STATES, 1)] = 0      # analyzer disconnected
    with pytest.raises(L.LWAError):
        dev.set_analyzer(cutoff="10Hz")


def test_capture_and_average(gui, tmp_path):
    dev = L.LWA1k(verbose=False)
    c = dev.capture(("noise", "lineshape"))
    assert c["noise"]["n"] == gui.n and c["noise"]["x"][-1] == 3e7
    assert c["results"]["intrinsic_display_Hz"] == 1001.0 and c["results"]["voigt_fwhm_Hz"] is None
    assert (1, L.REQ_PUBLISH_RESULTS, 0, 0) not in gui.log          # would zero the GUI's results
    assert c["states_nominal"]
    # flags are cleared after reading
    assert not any(L.parse_status(gui.read(L.STATUS_MAP, L.STATUS_SIZE))["ready"].values())
    avg = dev.capture_averaged(5, ("noise",))
    assert avg["noise"]["all"].shape == (5, gui.n)
    assert np.allclose(avg["noise"]["y"], 1000 / np.pi, rtol=0.05)          # FN converted to Hz^2/Hz
    assert avg["noise"]["unit"] == "Hz2/Hz"
    assert avg["results"]["intrinsic_display_Hz"]["mean"] == pytest.approx(np.mean([1002, 1003, 1004, 1005, 1006]))
    assert gui.eval[4] == 0          # lineshape not requested -> its autoeval switched off (GUI behaviour)
    meta = L.save_measurement(tmp_path, "t", avg, ("noise",), dev.read_settings(), {}, "Hz/rtHz")
    assert meta["analysis"]["intrinsic_linewidth_Hz_python"] == pytest.approx(1000, rel=0.02)
    h = L.read_h5(tmp_path / "t.h5")                       # one compressed .h5 per measurement
    assert h["_attrs"]["n_averaged"] == 5 and h["noise"]["captures"].shape == (5, gui.n)
    assert np.allclose(h["noise"]["mean"], avg["noise"]["y"]) and h["noise"]["_attrs"]["unit"] == "Hz2/Hz"
    assert h["_attrs"]["intrinsic_linewidth_Hz_python"] == pytest.approx(1000, rel=0.02)
    assert np.allclose(h["gui_results"]["intrinsic_display_Hz"], [1002, 1003, 1004, 1005, 1006])
    assert len(h["capture_info"]["duration_s"]) == 5 and "binned" in h["noise"]
    assert (tmp_path / "t_PSD.txt").exists()
    assert not list(tmp_path.glob("*.npz")) and not list(tmp_path.glob("*.json")) and not list(tmp_path.glob("*.csv"))
    # compare / level read the .h5 directly
    xy = L.load_xy(str(tmp_path / "t.h5"))
    assert xy.shape == (gui.n, 2) and np.allclose(xy[:, 1], avg["noise"]["y"])
    assert np.allclose(L.load_xy(str(tmp_path / "t.h5") + "::noise/std")[:, 1], h["noise"]["std"])


def test_capture_timeout(gui, monkeypatch):
    dev = L.LWA1k(verbose=False)
    monkeypatch.setattr(L.LWA1k, "send", lambda self, *a: 0)   # GUI never publishes
    with pytest.raises(L.LWAError):
        dev.capture(("noise",), timeout_s=0.2)


def test_compare_cli(tmp_path):
    x = np.linspace(0, 3e7, 1000)
    y = 300 + 0 * x
    a, b = tmp_path / "gui.txt", tmp_path / "py.csv"
    np.savetxt(a, np.column_stack([x, y ** 2]), delimiter="\t", header="Frequency\tHz^2/Hz")
    np.savetxt(b, np.column_stack([x, y, 0 * y]), delimiter=",", header="x,mean,std", comments="")
    assert L.main(["compare", str(a), str(b)]) == 1
    assert L.main(["compare", str(a), str(b), "--square"]) == 0
