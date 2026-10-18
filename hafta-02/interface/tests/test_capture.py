"""capture.py testleri: RUN komutu ve firmware senaryo tablosuyla uyum."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from capture import MATRIX, SCENARIOS, RunFilter, TraceCollector, fnv1a, run_command, run_name  # noqa: E402
from protocol import LineFramer, parse_line  # noqa: E402

SCENARIO_C = Path(__file__).resolve().parents[2] / "firmware" / "odev02" / "App" / "scenario.c"


def test_scenarios_match_firmware_table():
    rows = re.findall(r'\{\s*"(S\d)",\s*(\d+),\s*(\d+),\s*(\d+)\s*\}', SCENARIO_C.read_text())
    fw = {name: (int(p), int(b), int(w)) for name, p, b, w in rows}
    assert fw == SCENARIOS


def test_run_command_fields():
    cmd = run_command("C", "S6", True, 35, 7, 12, 500, 1500)
    assert cmd.endswith("\n")
    assert cmd.split() == ["RUN", "name=C-S6a", "var=C", "period=100", "burst=4", "work=0",
                           "target=35", "inject=1", "gmin=500", "gmax=1500", "seed=7", "run=12",
                           "trace=0", "txprio=0"]
    assert "name=C-S6at" in run_command("C", "S6", True, 35, 7, 12, 500, 1500, trace=True)


def test_run_name_fits_board_buffer():
    # RunConfig.name 16 bayt (NUL dahil)
    assert all(len(run_name(v, s, True, True, 4)) <= 15 for v in "ABC" for s in SCENARIOS)


def test_matrix_is_assignment_set():
    assert MATRIX == [("A", "S5"), ("B", "S5"), ("C", "S5"), ("B", "S6"), ("C", "S6")]


def line64(text: str) -> bytes:
    return text.ljust(63).encode() + b"\n"


def test_run_filter_drops_previous_run_with_same_name():
    # 6 Ekim A-S5 koşusunun başı: kart varsayılan ayarla (adı yine A-S5) çalışırken
    # RUN geldi; yarım kalan eski TEL satırı reset baytıyla yeni TEL,0'a yapıştı.
    stream = (line64("TEL,377,A-S5,3775")
              + line64("TEL,378,A-S5,3785")[:40] + b"\xf0" + line64("TEL,0,A-S5,5")
              + line64("TEL,1,A-S5,15")
              + line64("LAB,95496,A-S5,P10,VA,B1,W5000,I0,N35")
              + line64("TEL,2,A-S5,25"))
    f = RunFilter("A-S5")
    kept = []
    for raw in LineFramer().feed(stream):
        kept += f.feed(raw, parse_line(raw))
    texts = [k.decode(errors="replace").split()[0] for k in kept]
    # TEL,0 reset baytından ayıklanıp kurtarılır; eski koşunun TEL,377'si atılır.
    assert texts == ["TEL,0,A-S5,5", "TEL,1,A-S5,15", "LAB,95496,A-S5,P10,VA,B1,W5000,I0,N35",
                     "TEL,2,A-S5,25"]
    assert all(len(k) == 64 for k in kept)


def test_run_filter_keeps_tel_sent_before_lab():
    stream = b"".join(line64(f"TEL,{i},C-S6,100") for i in range(4)) + line64("LAB,1,C-S6,P100")
    f = RunFilter("C-S6")
    kept = []
    for raw in LineFramer().feed(stream):
        kept += f.feed(raw, parse_line(raw))
    assert len(kept) == 5 and f.started


def test_trace_collector_rebuilds_and_checks_bytes():
    data = bytes(range(256)) * 3
    lines = [f"TRC,run=5,bytes={len(data)},fnv={fnv1a(data)},wrapped=1"]
    lines += [f"HEX,{off},{data[off:off + 48].hex().upper()}" for off in range(0, len(data), 48)]
    lines.append("TRC_END")
    c = TraceCollector()
    for line in lines:
        c.feed(line)
    assert c.done and bytes(c.data) == data and c.header["wrapped"] == "1"


def test_trace_collector_rejects_gap_and_bad_checksum():
    import pytest
    c = TraceCollector()
    c.feed("TRC,run=1,bytes=4,fnv=0,wrapped=0")
    with pytest.raises(ValueError):
        c.feed("HEX,2,AABB")             # ofset atladı
    c = TraceCollector()
    c.feed("TRC,run=1,bytes=2,fnv=0,wrapped=0")
    c.feed("HEX,0,AABB")
    with pytest.raises(ValueError):
        c.feed("TRC_END")                # checksum tutmuyor


def test_run_filter_recovers_lab_line_hit_by_reset_byte():
    # txprio=4: LAB ilk satır; reset baytı onun başına yapıştı.
    stream = (line64("TEL,377,B-S5,3775")[:30] + b"\xf0" + line64("LAB,7,B-S5atp4,P10")
              + line64("TEL,0,B-S5atp4,5"))
    f = RunFilter("B-S5atp4")
    kept = []
    for raw in LineFramer().feed(stream):
        kept += f.feed(raw, parse_line(raw))
    assert f.started
    assert [k.split(b",")[0] for k in kept] == [b"LAB", b"TEL"]
    assert all(len(k) == 64 for k in kept)
