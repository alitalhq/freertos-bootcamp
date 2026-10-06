"""Ödev 2 ölçüm aracı: karta RUN komutu gönderir, ham oturumu ve CSV'yi kaydeder.

Kart tek derlemedir (hafta-02/firmware/odev02); sürüm ve senaryo RUN ile
seçilir. Her koşu için üç dosya yazılır:
  <ad>_raw.txt   UART'tan gelen her bayt, olduğu gibi (TEL/BTN/LAB/CFG/REC/CNT)
  <ad>.csv       REC satırları: t0..t4 ve durum
  <ad>_meta.txt  CFG/TSK/CNT satırları

Örnekler:
  python capture.py run --variant C --scenario S6              # fiziksel B1 basışları
  python capture.py run --variant A --scenario S5 --inject auto
  python capture.py matrix --inject auto                       # A/B/C-S5, B/C-S6
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


def run_name(variant: str, scenario: str, inject: bool) -> str:
    return f"{variant}-{scenario}" + ("a" if inject else "")


def run_command(variant: str, scenario: str, inject: bool, target: int,
                seed: int, run_id: int, gap_min: int, gap_max: int) -> str:
    period, burst, work = SCENARIOS[scenario]
    return (f"RUN name={run_name(variant, scenario, inject)} var={variant} "
            f"period={period} burst={burst} work={work} target={target} "
            f"inject={int(inject)} gmin={gap_min} gmax={gap_max} seed={seed} run={run_id}\n")


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
            timeout_s: float, overwrite: bool) -> int:
    """RUN gönderir, END'e kadar her baytı kaydeder, CSV ve meta dosyalarını yazar."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"{name}_raw.txt"
    if raw_path.exists() and not overwrite:
        print(f"{raw_path} exists (use --overwrite)", file=sys.stderr)
        return 1

    framer, col = LineFramer(), ExportCollector()
    raw = bytearray()
    started = False   # RUN sonrası yeniden başlayan kartın satırlarından itibaren kaydet
    pending: list[bytes] = []
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
                if not started:
                    # Kart LAB satırını ilk TEL'lerden sonra gönderebilir: bu
                    # koşunun adını taşıyan satırları bekletip LAB gelince ekle.
                    if len(line.fields) > 1 and line.fields[1] == name:
                        pending.append(line_raw)
                    if line.kind != "LAB" or not pending or pending[-1] is not line_raw:
                        continue
                    started = True
                    for early in pending[:-1]:
                        raw += early
                raw += line_raw
                if line.kind == "LAB":
                    print("board:", line_raw.decode(errors="replace").rstrip())
                elif line.kind == "BTN":
                    btn += 1
                    print(f"\rBTN {btn}/{target}", end="", flush=True)
                exp = col.feed(line)
                if exp is None:
                    continue
                print()
                raw_path.write_bytes(bytes(raw))
                exp.cfg["scenario"] = name   # dosya adı koşu adıyla aynı olsun
                csv_path, _ = write_export(exp, out_dir, overwrite=overwrite)
                print(summarize(exp))
                print(f"saved {raw_path.name}, {csv_path.name}, {name}_meta.txt")
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
        name = run_name(variant, scenario, inject)
        cmd = run_command(variant, scenario, inject, a.target, a.seed + i,
                          int(time.time()) % 100000, a.gap_min, a.gap_max)
        rc = capture(port, cmd, name, a.out, a.target, a.timeout, a.overwrite)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
