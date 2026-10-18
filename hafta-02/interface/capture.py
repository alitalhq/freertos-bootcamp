"""Ödev 2 ölçüm aracı: karta RUN komutu gönderir, ham oturumu ve CSV'yi kaydeder.

Kart tek derlemedir (hafta-02/firmware/odev02); sürüm ve senaryo RUN ile
seçilir. Her koşu için üç dosya yazılır:
  <ad>_raw.txt   UART'tan gelen her bayt, olduğu gibi (TEL/BTN/LAB/CFG/REC/CNT)
  <ad>.csv       REC satırları: t0..t4 ve durum
  <ad>_meta.txt  CFG/TSK/CNT satırları
--trace ile kart SystemView kaydını da açar; END'den sonra gelen TRC/HEX
satırlarından dördüncü dosya yazılır (koşu adının sonuna 't' eklenir):
  <ad>.SVDat     SystemView kaydı (File → Open), son ~1–2 saniye

Örnekler:
  python capture.py run --variant C --scenario S6              # fiziksel B1 basışları
  python capture.py run --variant A --scenario S5 --inject auto
  python capture.py matrix --inject auto                       # A/B/C-S5, B/C-S6
  python capture.py run --variant B --scenario S6 --trace      # + SystemView kaydı
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import serial

from protocol import ExportCollector, LineFramer, parse_line, write_export

BAUD = 115200
DEADLINE_MS = 20.0
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "measurements"

# Senaryolar: (periyot ms, periyot başına TEL, CPU işi µs). firmware scenario.c ile aynı.
SCENARIOS = {
    "S0": (0, 1, 0), "S1": (100, 1, 0), "S2": (20, 1, 0), "S3": (10, 1, 0),
    "S4": (10, 1, 2000), "S5": (10, 1, 5000), "S6": (100, 4, 0),
}
VARIANTS = ("A", "B", "C")

# Ödev 2 zorunlu (A/B/C-S5) ve ek (B/C-S6) koşuları
MATRIX = [("A", "S5"), ("B", "S5"), ("C", "S5"), ("B", "S6"), ("C", "S6")]


def find_port() -> str | None:
    ports = sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*"))
    return ports[0] if ports else None


def run_name(variant: str, scenario: str, inject: bool, trace: bool = False) -> str:
    return f"{variant}-{scenario}" + ("a" if inject else "") + ("t" if trace else "")


def run_command(variant: str, scenario: str, inject: bool, target: int,
                seed: int, run_id: int, gap_min: int, gap_max: int, trace: bool = False) -> str:
    period, burst, work = SCENARIOS[scenario]
    return (f"RUN name={run_name(variant, scenario, inject, trace)} var={variant} "
            f"period={period} burst={burst} work={work} target={target} "
            f"inject={int(inject)} gmin={gap_min} gmax={gap_max} seed={seed} run={run_id} "
            f"trace={int(trace)}\n")


def fnv1a(data: bytes) -> int:
    h = 2166136261
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


class TraceCollector:
    """END'den sonra gelen SystemView kaydını toplar ve doğrular.

    TRC,run=<id>,bytes=<n>,fnv=<u32>,wrapped=<0|1>
    HEX,<offset>,<hex>     (sıralı, boşluksuz)
    TRC_END
    """

    def __init__(self) -> None:
        self.header: dict[str, str] = {}
        self.header_line = ""
        self.data = bytearray()
        self.done = False

    def feed(self, text: str) -> None:
        if text.startswith("TRC,"):
            self.header_line = text
            self.header = dict(kv.split("=", 1) for kv in text.split(",")[1:] if "=" in kv)
        elif text.startswith("HEX,"):
            _, off, chunk = text.split(",", 2)
            if int(off) != len(self.data):
                raise ValueError(f"trace offset {off} != {len(self.data)}")
            self.data += bytes.fromhex(chunk)
        elif text == "TRC_END":
            if len(self.data) != int(self.header["bytes"]):
                raise ValueError(f"trace length {len(self.data)} != {self.header['bytes']}")
            if fnv1a(self.data) != int(self.header["fnv"]):
                raise ValueError("trace checksum mismatch")
            self.done = True


class RunFilter:
    """Ham oturuma yalnızca bu koşunun satırlarını alır.

    RUN sonrası kart yeniden başlar. LAB satırı ilk TEL'lerden sonra gelebilir;
    o yüzden bu koşunun adını taşıyan tam (64 bayt) satırlar LAB gelene kadar
    bekletilir. Kart TEL sırasını 0'dan başlatır: sıra geri giderse daha önce
    bekletilenler (aynı adı taşısa da) önceki koşuya aittir ve atılır.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.started = False
        self._pending: list[bytes] = []
        self._last_seq = -1

    def feed(self, line_raw: bytes, line) -> list[bytes]:
        if self.started:
            return [line_raw]
        if not line.length_ok:
            return []
        if line.kind == "TEL" and line.fields and line.fields[0].isdigit():
            seq = int(line.fields[0])
            if seq <= self._last_seq:
                self._pending.clear()      # kart yeniden başladı
            self._last_seq = seq
        if len(line.fields) > 1 and line.fields[1] == self.name:
            if line.kind == "LAB":
                self.started = True
                return self._pending + [line_raw]
            self._pending.append(line_raw)
        return []


def summarize(exp) -> str:
    rs = [r.r_us / 1000 for r in exp.records if r.status == "ok" and r.r_us is not None]
    lost = sum(r.status != "ok" for r in exp.records)
    s = f"{exp.scenario}: {len(exp.records)} records, {len(rs)} ok, {lost} not ok"
    if rs:
        late = sum(r > DEADLINE_MS for r in rs)
        s += (f" | R min/avg/max = {min(rs):.2f}/{sum(rs) / len(rs):.2f}/{max(rs):.2f} ms,"
              f" >{DEADLINE_MS:.0f} ms: {late}")
    c = exp.cnt
    s += (f" | TEL drop {c.get('tel_tx_drop', '?')}, BTN drop {c.get('btn_tx_drop', '?')},"
          f" TEL wait max {int(c.get('tel_wait_max_us', 0)) / 1000:.2f} ms")
    return s


def capture(port: str, cmd: str, name: str, out_dir: Path, target: int,
            timeout_s: float, overwrite: bool, trace: bool = False) -> int:
    """RUN gönderir, END'e (iz istendiyse TRC_END'e) kadar her baytı kaydeder,
    CSV, meta ve varsa .SVDat dosyalarını yazar."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"{name}_raw.txt"
    if raw_path.exists() and not overwrite:
        print(f"{raw_path} exists (use --overwrite)", file=sys.stderr)
        return 1

    framer, col = LineFramer(), ExportCollector()
    raw = bytearray()
    run_filter = RunFilter(name)
    trc = TraceCollector() if trace else None
    exp = None
    btn = 0
    with serial.Serial(port, BAUD, timeout=0.1) as ser:
        ser.reset_input_buffer()
        ser.write(cmd.encode())
        print(f"sent: {cmd.strip()}")
        t_end = time.monotonic() + timeout_s
        while time.monotonic() < t_end:
            data = ser.read(4096)
            if not data:
                continue
            for line_raw in framer.feed(data):
                line = parse_line(line_raw)
                for keep in run_filter.feed(line_raw, line):
                    raw += keep
                if not run_filter.started:
                    continue
                if line.kind == "LAB":
                    print("board:", line_raw.decode(errors="replace").rstrip())
                elif line.kind == "BTN":
                    btn += 1
                    print(f"\rBTN {btn}/{target}", end="", flush=True)
                if exp is None:
                    exp = col.feed(line)
                    if exp is None:
                        continue
                    print()
                    if trc:
                        print("receiving SystemView trace…")
                elif trc:
                    trc.feed(line_raw.decode("ascii", errors="replace").strip())
                if trc and not trc.done:
                    continue
                raw_path.write_bytes(bytes(raw))
                exp.cfg["scenario"] = name   # dosya adı koşu adıyla aynı olsun
                csv_path, meta_path = write_export(exp, out_dir, overwrite=overwrite)
                print(summarize(exp))
                saved = [raw_path.name, csv_path.name, meta_path.name]
                if trc:
                    sv = out_dir / f"{name}.SVDat"
                    sv.write_bytes(bytes(trc.data))
                    with meta_path.open("a") as f:
                        f.write(trc.header_line + "\n")
                    saved.append(sv.name)
                    print(f"trace: {len(trc.data)} bytes, wrapped={trc.header.get('wrapped')}")
                print("saved " + ", ".join(saved))
                return 0
    raw_path.with_suffix(".partial.txt").write_bytes(bytes(raw))
    print("\ntimeout: END not received", file=sys.stderr)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for p in (sub.add_parser("run", help="one variant/scenario"),
              sub.add_parser("matrix", help="A/B/C-S5 and B/C-S6 in a row")):
        p.add_argument("--port")
        p.add_argument("--inject", choices=["manual", "auto"], default="manual",
                       help="manual: press B1 after LD2 turns on; auto: EXTI software trigger")
        p.add_argument("--target", type=int, default=35, help="accepted presses per run")
        p.add_argument("--seed", type=int, default=1)
        p.add_argument("--gap-min", type=int, default=500, help="auto press gap min (ms)")
        p.add_argument("--gap-max", type=int, default=1500, help="auto press gap max (ms)")
        p.add_argument("--out", type=Path, default=DEFAULT_OUT)
        p.add_argument("--timeout", type=float, default=900)
        p.add_argument("--overwrite", action="store_true")
        p.add_argument("--trace", action="store_true", help="record a SystemView trace (.SVDat)")
        if p.prog.endswith("run"):
            p.add_argument("--variant", choices=VARIANTS, required=True)
            p.add_argument("--scenario", choices=list(SCENARIOS), required=True)
    a = ap.parse_args()

    port = a.port or find_port()
    if not port:
        print("no serial port", file=sys.stderr)
        return 1
    inject = a.inject == "auto"
    runs = [(a.variant, a.scenario)] if a.cmd == "run" else MATRIX
    for i, (variant, scenario) in enumerate(runs):
        name = run_name(variant, scenario, inject, a.trace)
        cmd = run_command(variant, scenario, inject, a.target, a.seed + i,
                          int(time.time()) % 100000, a.gap_min, a.gap_max, a.trace)
        rc = capture(port, cmd, name, a.out, a.target, a.timeout, a.overwrite, a.trace)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
