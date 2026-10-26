"""Kabul kontrolü: evidence/*/result.json dosyalarındaki PASS ve muhasebe eşitlikleri.

python3 tests/check_evidence.py   ->  her test için PASS/FAIL ve eksik kanıt
"""
import json
import pathlib
import sys

EV = pathlib.Path(__file__).resolve().parent.parent / "evidence"
REQUIRED = ["T1/trigger1", "T1/trigger8", "T1/trigger32", "T2", "T3", "T4", "T5", "T6", "T7", "T7B", "T8", "T9"]

bad = 0
for name in REQUIRED:
    d = EV / name
    missing = [f for f in ("result.json", "manifest.json", "raw.jsonl") if not (d / f).exists()]
    if missing:
        print(f"{name:14} EKSİK  {', '.join(missing)}")
        bad += 1
        continue
    r = json.loads((d / "result.json").read_text())
    m = json.loads((d / "manifest.json").read_text())
    eq = r.get("equalities", {})
    eq_ok = all(v[2] for v in eq.values())
    for key in ("seed", "baud", "task_priorities", "service_time_ms", "firmware"):
        if key not in m:
            print(f"{name:14} manifestte {key} yok")
            bad += 1
    status = "PASS" if r["pass"] else "FAIL"
    print(f"{name:14} {status}  eşitlikler: {'tamam' if eq_ok else 'BOZUK'}" + ("" if eq else " (yok)"))
    bad += (not r["pass"]) + (not eq_ok)
sys.exit(1 if bad else 0)
