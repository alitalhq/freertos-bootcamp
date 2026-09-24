"""protocol.py testleri.

Fixture (fixtures/s5_dev_run.bin), kartın S5 geliştirme testindeki (10 basış)
gerçek UART çıktısından kısaltılmış bir parçadır; resmi ölçüm değildir.
Başında yarım bir satır ve iki parçanın birleştiği bozuk bir satır bilerek var.
"""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from protocol import CSV_HEADER, ExportCollector, LineFramer, Record, parse_line, write_export  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "s5_dev_run.bin"


def feed_in_chunks(data: bytes, size: int):
    framer = LineFramer()
    lines = []
    for i in range(0, len(data), size):
        lines += framer.feed(data[i:i + size])
    return lines


@pytest.mark.parametrize("chunk", [1, 7, 64, 4096])
def test_framing_is_independent_of_chunk_size(chunk):
    data = FIXTURE.read_bytes()
    assert feed_in_chunks(data, chunk) == feed_in_chunks(data, len(data))


def test_tel_btn_lines_are_64_bytes_except_damaged_ones():
    lines = [parse_line(l) for l in feed_in_chunks(FIXTURE.read_bytes(), 4096)]
    tel_btn = [l for l in lines if l.kind in {"TEL", "BTN"}]
    bad = [l for l in tel_btn if not l.length_ok]
    assert len(tel_btn) > 20
    assert len(bad) <= 1          # yalnızca fixture'daki birleşme satırı
    assert any(l.kind == "BTN" and l.fields[0] == "0" and l.length_ok for l in lines)


def test_export_is_collected_and_parsed():
    collector = ExportCollector()
    exports = []
    for raw in feed_in_chunks(FIXTURE.read_bytes(), 4096):
        exp = collector.feed(parse_line(raw))
        if exp:
            exports.append(exp)

    assert len(exports) == 1
    exp = exports[0]
    assert exp.scenario == "S5"
    assert exp.cfg["target_events"] == "10"
    assert len(exp.records) == 10
    assert [r.event_id for r in exp.records] == list(range(10))
    assert all(r.status == "ok" for r in exp.records)
    # zaman damgaları sıralı
    for r in exp.records:
        d = [Record.diff(a, b) for a, b in zip(r.t, r.t[1:])]
        assert all(x is not None and x < 1_000_000 for x in d)
    assert exp.records[0].r_us == 14579
    assert exp.cnt["txq_hwm"] == "11"
    assert {t["name"] for t in exp.tasks} >= {"telemetry", "button", "uart_tx"}


def test_missing_stamps_stay_empty_in_csv(tmp_path):
    collector = ExportCollector()
    lines = [
        b"CFG,scenario=S3,sysclk_hz=80000000\n",
        b"REC,S3,0,100,200,300,400,5900,ok\n",
        b"REC,S3,1,1000,1100,1200,,,tx_drop\n",
        b"CNT,accepted=2\n",
        b"END\n",
    ]
    exp = None
    for raw in lines:
        exp = collector.feed(parse_line(raw)) or exp
    csv_path, meta_path = write_export(exp, tmp_path)

    rows = list(csv.reader(csv_path.open()))
    assert rows[0] == CSV_HEADER
    assert rows[2] == ["S3", "1", "1000", "1100", "1200", "", "", "tx_drop"]
    assert exp.records[1].r_us is None
    assert "REC" not in meta_path.read_text()

    with pytest.raises(FileExistsError):
        write_export(exp, tmp_path)


def test_u32_wraparound_difference():
    assert Record.diff(2**32 - 10, 5) == 15


def test_session_counts_fixture_stream(tmp_path):
    from monitor import Session, save_export

    sess = Session()
    data = FIXTURE.read_bytes()
    for i in range(0, len(data), 100):
        sess.feed(data[i:i + 100])
    assert sess.btn_count == 2                   # fixture: BTN,0 ve export öncesi BTN,9
    assert sess.scenario == "S5"
    assert sess.format_errors <= 1
    assert sess.new_export is not None and len(sess.new_export.records) == 10

    first, _ = save_export(sess.new_export, tmp_path, overwrite=False)
    second, _ = save_export(sess.new_export, tmp_path, overwrite=False)
    assert first.name == "S5.csv" and second.name.startswith("S5_") and first.exists()
