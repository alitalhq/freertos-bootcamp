"""Lab modu kontrolü: karta RUN/STOP/PING komutları ve deney koşturma.

Kart APP_LAB_MODE=1 ile derlenmiş olmalı (ADR-004). Komut sözdizimi:
firmware/odev01/App/lab.h

CLI örneği:
  python labctl.py run --preset S5 --fix optimal --inject auto --out ../measurements/lab
"""
from __future__ import annotations

import argparse
import queue
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from monitor import DEFAULT_OUT, SerialReader, Session, list_ports, save_export, summarize

# ---- Çözüm bitleri (app_config.h ile aynı) ---------------------------------
FIX_UART_PRIO = 0x1   # F1: UartTxTask önceliği 4 (kök neden)
FIX_BTN_PRIO = 0x4    # F4: ButtonTask önceliği 4 (tek başına naif, F1 ile optimal)
FIX_TC_CHAIN = 0x8    # F8: sonraki gönderim TC kesmesinden (öncelikler değişmez)

FIX_BITS = {
    FIX_UART_PRIO: "UartTxTask önceliği 1→4",
    FIX_BTN_PRIO: "ButtonTask önceliği 2→4",
    FIX_TC_CHAIN: "sonraki gönderim TC kesmesinden (öncelikler aynı)",
}

# Arayüzde gösterilen hazır çözüm seçenekleri: (anahtar, etiket, maske)
FIX_PRESETS = [
    ("standard", "Standart (ödev tasarımı, yükte hatalı)", 0),
    ("naive", "Naif: ButtonTask önceliğini artır", FIX_BTN_PRIO),
    ("root", "Kök neden: UART görevinin önceliği", FIX_UART_PRIO),
    ("chain", "Öncelik değiştirmeden: TC zinciri", FIX_TC_CHAIN),
    ("optimal", "Optimal: UART ve Button görevleri CPU işinin üstünde", FIX_UART_PRIO | FIX_BTN_PRIO),
]
FIX_BY_KEY = {k: m for k, _, m in FIX_PRESETS}

# Ödevin altı senaryosu: (periyot ms, CPU işi µs)
PRESETS = {
    "S0": (0, 0), "S1": (100, 0), "S2": (20, 0),
    "S3": (10, 0), "S4": (10, 2000), "S5": (10, 5000),
}


def fix_label(mask: int) -> str:
    for _, label, m in FIX_PRESETS:
        if m == mask:
            return label
    return " + ".join(v for k, v in FIX_BITS.items() if mask & k) or "Standart"


@dataclass
class LabConfig:
    period_ms: int = 10
    work_us: int = 5000
    fix: int = 0
    inject: int = 1           # 1 = otomatik basış, 0 = elle
    target: int = 35
    gap_min_ms: int = 500
    gap_max_ms: int = 1500
    seed: int = 1
    run_id: int = 0
    name: str = ""

    def auto_name(self) -> str:
        """Kartta mesaja giren kısa ad: 'S5', 'S5-F3', özel ayarsa 'C10W5000-F3'."""
        base = next((k for k, v in PRESETS.items() if v == (self.period_ms, self.work_us)), None)
        base = base or f"C{self.period_ms}W{self.work_us}"
        name = base if self.fix == 0 else f"{base}-F{self.fix}"
        if self.inject:
            name += "a"      # otomatik basış
        return name[:15]

    def command(self) -> str:
        name = self.name or self.auto_name()
        return (f"RUN name={name} period={self.period_ms} work={self.work_us} "
                f"target={self.target} fix={self.fix} inject={self.inject} "
                f"gmin={self.gap_min_ms} gmax={self.gap_max_ms} seed={self.seed} run={self.run_id}\n")


def run_blocking(port: str, cfg: LabConfig, out_dir: Path, timeout_s: float = 600) -> int:
    """RUN gönderir, END'e kadar dinler, kaydeder. CLI için."""
    q: queue.Queue = queue.Queue()
    reader = SerialReader(port, q)
    reader.start()
    time.sleep(0.2)
    cmd = cfg.command()
    reader.ser.write(cmd.encode())
    print(f"sent: {cmd.strip()}")
    sess = Session()
    t_end = time.monotonic() + timeout_s
    btn = 0
    while time.monotonic() < t_end:
        try:
            item = q.get(timeout=0.2)
        except queue.Empty:
            continue
        if isinstance(item, Exception):
            print(f"serial error: {item}", file=sys.stderr)
            return 1
        sess.feed(item)
        for lab in sess.new_lab:
            print("board:", lab)
        sess.new_lab.clear()
        if sess.btn_count != btn:
            btn = sess.btn_count
            print(f"\rBTN {btn}/{cfg.target}", end="", flush=True)
        if sess.new_export:
            print()
            csv_path, _ = save_export(sess.new_export, out_dir, overwrite=True)
            print(summarize(sess.new_export))
            print(f"saved {csv_path}")
            reader.stop()
            return 0
    reader.stop()
    print("timeout", file=sys.stderr)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run one lab experiment and save it")
    r.add_argument("--port")
    r.add_argument("--preset", choices=list(PRESETS), default="S5")
    r.add_argument("--period", type=int, help="override telemetry period (ms, 0=off)")
    r.add_argument("--work", type=int, help="override CPU work (µs)")
    r.add_argument("--fix", default="standard", help="preset key or numeric mask")
    r.add_argument("--inject", choices=["auto", "manual"], default="auto")
    r.add_argument("--target", type=int, default=35)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--out", type=Path, default=DEFAULT_OUT / "lab")
    a = ap.parse_args()

    port = a.port or (list_ports() or [None])[0]
    if not port:
        print("no serial port", file=sys.stderr)
        return 1
    period, work = PRESETS[a.preset]
    fix = FIX_BY_KEY[a.fix] if a.fix in FIX_BY_KEY else int(a.fix, 0)
    cfg = LabConfig(period_ms=a.period if a.period is not None else period,
                    work_us=a.work if a.work is not None else work,
                    fix=fix, inject=1 if a.inject == "auto" else 0,
                    target=a.target, seed=a.seed, run_id=int(time.time()) % 100000)
    return run_blocking(port, cfg, a.out)


if __name__ == "__main__":
    sys.exit(main())
