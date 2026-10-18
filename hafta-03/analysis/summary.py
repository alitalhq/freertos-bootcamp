"""Ödev 3 karşılaştırma tablosu: measurements/*.json + *.csv -> summary.csv ve Markdown tablo.

Yalnız ham dosyalardan hesaplanır. Başarısız gönderimlerin gecikmesi hesaba katılmaz (0 sayılmaz).
Kullanım: python summary.py
"""
from __future__ import annotations

import csv
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEAS = ROOT / "measurements"
ORDER = [("A", "NORMAL", True), ("B", "NORMAL", True), ("C", "NORMAL", True),
         ("A", "BURST", True), ("B", "BURST", True), ("C", "BURST", True), ("A", "BURST", False)]


def row(meta_path: Path) -> dict:
    m = json.loads(meta_path.read_text())
    recs = list(csv.DictReader(open(meta_path.with_suffix(".csv"))))
    ok = [r for r in recs if r["accepted"] == "1"]
    lat = [int(r["generation_to_receive_us"]) / 1000 for r in ok if r["generation_to_receive_us"]]
    send_ok = [int(r["send_call_us"]) / 1000 for r in ok]
    send_fail = [int(r["send_call_us"]) / 1000 for r in recs if r["accepted"] == "0"]
    t = m["trace"] or {}
    assert m["attempted"] == m["accepted"] + m["failed"] == len(recs)
    assert m["accepted"] == m["consumed"]
    return {
        "variant": m["variant"], "load": m["load"], "trace": int(m["trace_enabled"]), "run_id": m["run_id"],
        "file": meta_path.stem,
        "attempted": m["attempted"], "accepted": m["accepted"], "failed": m["failed"], "consumed": m["consumed"],
        "latency_avg_ms": f"{st.mean(lat):.2f}", "latency_max_ms": f"{max(lat):.2f}",
        "send_ok_max_ms": f"{max(send_ok):.3f}",
        "send_fail_avg_ms": f"{st.mean(send_fail):.3f}" if send_fail else "",
        "send_fail_max_ms": f"{max(send_fail):.3f}" if send_fail else "",
        "trace_bytes": t.get("bytes", ""), "trace_drops": t.get("drops", ""), "trace_stop": t.get("stop_reason", ""),
        "stack_free_words": " ".join(m["stack_words"]),
    }


def main() -> None:
    metas = {}
    for p in MEAS.glob("*.json"):
        m = json.loads(p.read_text())
        metas[(m["variant"], m["load"], bool(m["trace_enabled"]))] = p
    rows = [row(metas[k]) for k in ORDER]
    with open(ROOT / "analysis" / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("| # | Varyant | Yük | İz | Girişim | Kabul | Başarısız | Tüketilen | Gecikme ort / maks (ms) | Gönderme maks: kabul / başarısız (ms) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        print(f"| {i:02d} | {r['variant']} | {'normal' if r['load'] == 'NORMAL' else 'yoğun'} | "
              f"{'açık' if r['trace'] else 'kapalı'} | {r['attempted']} | {r['accepted']} | {r['failed']} | "
              f"{r['consumed']} | {r['latency_avg_ms']} / {r['latency_max_ms']} | "
              f"{r['send_ok_max_ms']} / {r['send_fail_max_ms'] or '–'} |")


if __name__ == "__main__":
    main()
