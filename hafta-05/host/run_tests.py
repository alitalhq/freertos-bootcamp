"""Hafta 5 kabul testleri T1-T9: kartla konuşur, evidence/Tn altına ham kayıt yazar.

Kullanım:  python3 run_tests.py --port /dev/cu.usbmodem103 T1 T2 ...
T7B (fiziksel buton) ayrı çalıştırılır; B1'e en az 20 kez basmanız gerekir.
"""
import argparse
import csv
import hashlib
import json
import pathlib
import platform
import statistics
import subprocess
import sys
import threading
import time

import serial

import proto
from link import BAUD, Link, now_ns, pace

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
ELF = ROOT / "firmware" / "Debug" / "RTOS_Hafta_5_L476RG.elf"
PRIORITIES = {"Control": 4, "Parser": 3, "Execute": 2, "Tx": 2, "Setpoint": 1, "Log": 1}
CUBE_PROG = ("/Applications/STM32CubeIDE.app/Contents/Eclipse/plugins/"
             "com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer.macosaarch64_1.0.100.202603051304/"
             "tools/bin/STM32_Programmer_CLI")


# ---- yardımcılar --------------------------------------------------------------

def pct(values, p):
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def lat_stats(us):
    """us listesi -> ms cinsinden özet."""
    if not us:
        return {"n": 0}
    return {"n": len(us), "p50_ms": round(pct(us, 50) / 1000, 3), "p95_ms": round(pct(us, 95) / 1000, 3),
            "p99_ms": round(pct(us, 99) / 1000, 3), "max_ms": round(max(us) / 1000, 3)}


def sha256(path):
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True).stdout.strip()
    except OSError:
        return None


def equalities(s):
    return {
        "isr == acc + rej": [s["isr"], s["acc"] + s["rej"], s["isr"] == s["acc"] + s["rej"]],
        "acc == rd + rem": [s["acc"], s["rd"] + s["rem"], s["acc"] == s["rd"] + s["rem"]],
        "ja == jd + jx + jq + ji": [s["ja"], s["jd"] + s["jx"] + s["jq"] + s["ji"],
                                    s["ja"] == s["jd"] + s["jx"] + s["jq"] + s["ji"]],
    }


DELTA_KEYS = ["isr", "acc", "rej", "rd", "okd", "okc", "crc", "len", "hdr", "to", "gap", "dup",
              "crej", "stl", "ja", "jr", "jd", "jx", "ll", "ldr", "rl", "rdr", "ue", "re", "ndr"]


def delta(a, b):
    return {k: b[k] - a[k] for k in DELTA_KEYS if k in a and k in b}


class Test:
    """Bir testin klasörü, bağlantısı ve kayıtları."""

    def __init__(self, name, port, settings):
        self.name = name
        self.dir = EVIDENCE / name
        self.dir.mkdir(parents=True, exist_ok=True)
        for f in ("raw.jsonl", "sent.csv"):
            (self.dir / f).unlink(missing_ok=True)
        self.L = Link(port, self.dir / "raw.jsonl")
        self.sent = open(self.dir / "sent.csv", "w", newline="")
        self.sw = csv.writer(self.sent)
        self.sw.writerow(["host_ns", "kind", "seq", "len", "checksum", "note"])
        self.data = {}                      # seq -> checksum (geçerli DATA)
        self.bad = set()                    # bozuk gönderilen SEQ'ler
        self.settings = settings
        self.t_start = time.time()
        self.send_times = []

    def send_data(self, seq, payload, note=""):
        t = now_ns()
        self.L.write(proto.frame(proto.DATA, seq, payload))
        self.data[seq] = proto.checksum(payload)
        self.send_times.append(t)
        self.sw.writerow([t, "DATA", seq, len(payload), self.data[seq], note])

    def send_raw(self, data, kind, seq="", note=""):
        self.sw.writerow([now_ns(), kind, seq, len(data), "", note])
        self.L.write(data)

    def responses(self, start=0):
        out = {}
        for t, d in self.L.since(start, "R"):
            out.setdefault(d["s"], []).append((t, d))
        return out

    def send_rate(self):
        if len(self.send_times) < 2:
            return None
        return (len(self.send_times) - 1) / ((self.send_times[-1] - self.send_times[0]) / 1e9)

    def finish(self, result, passed):
        self.sent.close()
        hello = next((d for _, d in reversed(self.L.since(0, "H"))), {})
        manifest = {
            "test": self.name,
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_s": round(time.time() - self.t_start, 1),
            "firmware": {"git": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "firmware")),
                         "elf_sha256": sha256(ELF), "fw": hello.get("fw"), "session": hello.get("sid")},
            "host": {"script_sha256": sha256(__file__), "proto_sha256": sha256(pathlib.Path(__file__).with_name("proto.py")),
                     "python": platform.python_version(), "pyserial": serial.__version__, "os": platform.platform()},
            "baud": BAUD, "tick_hz": 1000,
            "rx_capacity": hello.get("cap"), "trigger": hello.get("trg"),
            "task_priorities": PRIORITIES, "service_time_ms": 2,
            "seed": proto.SEED, "prng": proto.PRNG,
            "host_bytes_written": self.L.bytes_written,
            "host_data_rate_per_s": round(self.send_rate(), 1) if self.send_rate() else None,
            **self.settings,
        }
        (self.dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        result = {"test": self.name, "pass": passed, **result}
        (self.dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        self.L.shutdown()
        print(f"{self.name}: {'PASS' if passed else 'FAIL'}")
        return result


def quiet(t, sec=0.6):
    time.sleep(sec)
    return t.L.snapshot()


def check_responses(t, start, expected):
    """expected: seq -> checksum. Tamamlanan, eksik, fazla, tekrarlı, yanlış checksum."""
    got = t.responses(start)
    missing = sorted(set(expected) - set(got))
    extra = sorted(set(got) - set(expected))
    dups = sorted(s for s, v in got.items() if len(v) > 1)
    wrong = sorted(s for s, v in got.items() if s in expected and v[0][1]["c"] != expected[s])
    d = [v[0][1]["d"] for s, v in got.items() if s in expected]
    q = [v[0][1]["q"] for s, v in got.items() if s in expected]
    return got, {"sent": len(expected), "completed_unique": len(set(got) & set(expected)),
                 "missing": len(missing), "missing_first": missing[:10], "extra": len(extra),
                 "extra_first": extra[:10], "duplicates": len(dups), "wrong_checksum": len(wrong),
                 "validate_to_done": lat_stats(d), "validate_to_tx": lat_stats(q)}


# ---- testler --------------------------------------------------------------------

def t1(port):
    results = {}
    ok_all = True
    for trig in (1, 8, 32):
        t = Test(f"T1/trigger{trig}", port, {"payload": 32, "target_rate": 200, "duration_s": 60, "trigger_set": trig})
        L = t.L
        L.new_session()
        m = L.mark()
        L.ack(L.ctrl(proto.TRIGGER, trig), proto.TRIGGER, m)
        before = L.snapshot()
        start = L.mark()
        g = proto.Gen(stream=f"T1-{trig}")
        for i in pace(200, 200 * 60):
            t.send_data(i, g.payload(32))
        after = quiet(t, 1.0)
        _, r = check_responses(t, start, t.data)
        dl = delta(before, after)
        rate = t.send_rate()
        eq = equalities(after)
        ok = (r["missing"] == r["extra"] == r["duplicates"] == r["wrong_checksum"] == 0
              and dl["crc"] == dl["gap"] == dl["rej"] == dl["dup"] == 0 and after["trg"] == trig
              and 180 <= rate <= 220 and r["validate_to_done"]["p99_ms"] <= 50
              and all(v[2] for v in eq.values()))
        ok_all &= ok
        results[trig] = t.finish({"responses": r, "delta": dl, "equalities": eq, "host_rate": round(rate, 2),
                                  "sb_hwm": after["sbh"], "jobq_hwm": after["jqh"], "snapshot_after": after}, ok)
    return ok_all


def t2(port):
    t = Test("T2", port, {"frames": 1000, "chunk_bytes": "1-17", "gap_ms": "0-3", "payload": "2-48, A5 5A içinde"})
    L = t.L
    L.new_session()
    before = L.snapshot()
    start = L.mark()
    g = proto.Gen(stream="T2")
    stream = bytearray()
    for i in range(1000):
        p = g.payload(g.rng.randint(2, 48), with_sync=True)
        t.data[i] = proto.checksum(p)
        t.sw.writerow([now_ns(), "DATA", i, len(p), t.data[i], "chunked"])
        stream += proto.frame(proto.DATA, i, p)
    writes = 0
    for c in g.chunks(bytes(stream)):
        L.write(c)
        writes += 1
        time.sleep(g.rng.randint(0, 3) / 1000)
    after = quiet(t, 1.0)
    _, r = check_responses(t, start, t.data)
    dl = delta(before, after)
    eq = equalities(after)
    ok = (r["completed_unique"] == 1000 and r["extra"] == r["duplicates"] == r["wrong_checksum"] == 0
          and dl["crc"] == dl["len"] == dl["hdr"] == 0 and all(v[2] for v in eq.values()))
    return t.finish({"writes": writes, "bytes": len(stream), "responses": r, "delta": dl, "equalities": eq}, ok)["pass"]


def t3(port):
    t = Test("T3", port, {"kinds": ["crc_bitflip", "len49", "garbage", "cut"], "per_kind": 25,
                          "silence_ms": 150, "good_after": 3})
    L = t.L
    L.new_session()
    g = proto.Gen(stream="T3")
    kinds = ["crc_bitflip", "len49", "garbage", "cut"] * 25
    g.rng.shuffle(kinds)
    before = L.snapshot()
    start = L.mark()
    seq = 0
    plan = []
    for k in kinds:
        bad_seq = None
        if k == "crc_bitflip":
            f = bytearray(proto.frame(proto.DATA, seq, g.payload(32)))
            bit = g.rng.randrange(10 * 8, len(f) * 8)       # payload veya CRC alanında bir bit
            f[bit // 8] ^= 1 << (bit % 8)
            bad_seq, data = seq, bytes(f)
        elif k == "len49":
            body = g.payload(49)
            data = proto.frame(proto.DATA, seq, body)        # LEN=49 > 48
            bad_seq = seq
        elif k == "garbage":
            data = g.payload(g.rng.randint(1, 64))
        else:
            f = proto.frame(proto.DATA, seq, g.payload(32))
            data = f[:g.rng.randint(3, len(f) - 1)]
            bad_seq = seq
        if bad_seq is not None:
            t.bad.add(bad_seq)
            seq += 1
        t.send_raw(data, k, bad_seq if bad_seq is not None else "")
        time.sleep(0.150)
        good = []
        for _ in range(3):
            t.send_data(seq, g.payload(32), f"after {k}")
            good.append(seq)
            seq += 1
            time.sleep(0.005)
        plan.append((k, bad_seq, good))
        time.sleep(0.03)
    after = quiet(t, 0.5)
    got = t.responses(start)
    per_kind = {}
    late = []
    for k, bad, good in plan:
        done = [s in got for s in good]
        # toparlanma: ilk tamamlanan sağlam çerçeve, ardından hepsi tamam
        rec = next((i + 1 for i in range(3) if all(done[i:])), None)
        e = per_kind.setdefault(k, {"n": 0, "recovered_1st": 0, "recovered_2nd": 0, "not_by_2nd": 0,
                                    "bad_processed": 0})
        e["n"] += 1
        e["recovered_1st" if rec == 1 else "recovered_2nd" if rec == 2 else "not_by_2nd"] += 1
        if bad is not None and bad in got:
            e["bad_processed"] += 1
        if rec not in (1, 2):
            late.append((k, good, done))
    dl = delta(before, after)
    eq = equalities(after)
    bad_done = sorted(t.bad & set(got))
    ok = not late and not bad_done and all(v[2] for v in eq.values()) and all(
        got[s][0][1]["c"] == c for s, c in t.data.items() if s in got)
    return t.finish({"per_kind": per_kind, "not_recovered_by_2nd": late, "bad_seq_processed": bad_done,
                     "delta": dl, "equalities": eq}, ok)["pass"]


def t4(port):
    t = Test("T4", port, {"target_rate": 200, "payload": 32, "stall_ms": 80, "stalls": 20, "rx_capacity_expected": 1024})
    L = t.L
    L.new_session()
    before = L.snapshot()
    assert before["cap"] == 1024, "T4 için RX kapasitesi 1024 olmalı"
    start = L.mark()
    g = proto.Gen(stream="T4")
    stalls = 0
    for i in pace(200, 200 * 23):
        if i % 200 == 100 and stalls < 20:
            L.ctrl(proto.STALL_NEXT, 80)
            stalls += 1
        t.send_data(i, g.payload(32))
    after = quiet(t, 1.0)
    _, r = check_responses(t, start, t.data)
    notes = [d for _, d in L.since(start, "T")]
    occ = [d["c"] for d in notes]
    dl = delta(before, after)
    eq = equalities(after)
    # tahmin: 80 ms * 200/s * 44 B (+ bir STALL çerçevesi 17 B)
    estimate = 0.080 * 200 * 44
    ok = (r["missing"] == r["duplicates"] == r["extra"] == 0 and dl["rej"] == 0 and dl["jr"] == 0
          and len(notes) == 20 and all(v[2] for v in eq.values()))
    return t.finish({"stall_notes": notes, "occupancy_after_stall_B": {"min": min(occ, default=None),
                     "max": max(occ, default=None), "mean": round(statistics.mean(occ), 1) if occ else None},
                     "occupancy_estimate_B": estimate, "sb_hwm_B": after["sbh"], "jobq_hwm": after["jqh"],
                     "responses": r, "delta": dl, "equalities": eq}, ok)["pass"]


def set_capacity(L, cap):
    m = L.mark()
    L.ctrl(proto.RX_CAPACITY, cap)                    # kart ayarı SRAM2'ye yazar ve reset atar
    h = L.wait(lambda d: d.get("t") == "H", m, 5.0)
    if h is None or h[1]["cap"] != cap:
        raise RuntimeError(f"kapasite {cap} olmadı: {h}")
    time.sleep(0.2)
    return h[1]


def t5(port):
    t = Test("T5", port, {"rx_capacity": 512, "stall_ms": 80, "burst_frames": 20, "burst_payload": 48,
                          "burst_bytes": 1200, "rounds": 5, "clean_after": 40})
    L = t.L
    L.new_session()
    hello = set_capacity(L, 512)
    L.new_session()
    before = L.snapshot()
    g = proto.Gen(stream="T5")
    seq = 0
    rounds = []
    clean = {}
    for rnd in range(5):
        b0 = L.snapshot()
        m = L.mark()
        L.ctrl(proto.STALL_NEXT, 80)
        time.sleep(0.005)                              # STALL çerçevesi parser'a ulaşsın
        burst = bytearray()
        for _ in range(20):
            p = g.payload(48)
            t.data[seq] = proto.checksum(p)
            t.sw.writerow([now_ns(), "DATA", seq, 48, t.data[seq], f"burst {rnd}"])
            burst += proto.frame(proto.DATA, seq, p)
            seq += 1
        L.write(bytes(burst))
        time.sleep(0.4)
        cm = L.mark()
        for _ in pace(200, 40):
            p = g.payload(32)
            t.send_data(seq, p, f"clean {rnd}")
            clean[seq] = proto.checksum(p)
            seq += 1
        a0 = quiet(t, 0.4)
        stall = L.wait(lambda d: d.get("t") == "T", m, 0.1)
        rounds.append({"round": rnd, "delta": delta(b0, a0), "stall_note": stall[1] if stall else None,
                       "clean_completed": sum(1 for s in t.responses(cm) if s in clean),
                       "equalities": equalities(a0)})
    after = L.snapshot()
    got = t.responses(0)
    clean_missing = sorted(s for s in clean if s not in got)
    eq = equalities(after)
    ok = (all(r["delta"]["rej"] > 0 for r in rounds) and not clean_missing
          and all(all(v[2] for v in r["equalities"].values()) for r in rounds) and all(v[2] for v in eq.values())
          and after["hmin"] == before["hmin"])
    res = {"hello": hello, "rounds": rounds, "clean_missing": clean_missing, "delta_total": delta(before, after),
           "equalities": eq, "heap_min_before_after": [before["hmin"], after["hmin"]],
           "burst_completed": sum(1 for s in t.data if s in got and s not in clean)}
    set_capacity(L, 1024)
    return t.finish(res, ok)["pass"]


def t6(port):
    t = Test("T6", port, {"parts": ["counter", "bits", "mailbox", "without_overwrite"]})
    L = t.L
    L.new_session()
    res = {}
    g = proto.Gen(stream="T6")

    def hold(mask):
        m = L.mark()
        L.ack(L.ctrl(proto.HOLD, mask), proto.HOLD, m)
        time.sleep(0.03)

    # 1) iş sayacı: 3 iş biriktir, STEP x4 -> dönüş 3/2/1/0, kalan 2/1/0/0
    hold(proto.HOLD_EXEC)
    start = L.mark()
    for i in range(3):
        t.send_data(i, g.payload(16))
    time.sleep(0.05)
    steps = []
    for _ in range(4):
        m = L.mark()
        L.ctrl(proto.STEP)
        k = L.wait(lambda d: d.get("t") == "K", m, 1.0)
        steps.append({"take_return": k[1]["a"], "remaining": k[1]["b"]} if k else None)
        time.sleep(0.02)
    hold(0)
    time.sleep(0.05)
    got = t.responses(start)
    res["counter"] = {"steps": steps, "expected": [[3, 2], [2, 1], [1, 0], [0, 0]],
                      "responses": sorted(got), "data_in_queue_not_in_notification": True}
    ok_counter = [[s["take_return"], s["remaining"]] for s in steps if s] == [[3, 2], [2, 1], [1, 0], [0, 0]] \
        and sorted(got) == [0, 1, 2]

    # 2) olay bitleri: kontrol bekletilirken STOP + STOP + bozuk çerçeve -> tek uyanış, bitler birleşik
    hold(proto.HOLD_CONTROL)
    m = L.mark()
    L.ctrl(proto.STOP)
    L.ctrl(proto.STOP)
    bad = bytearray(proto.frame(proto.DATA, 3, g.payload(8)))
    bad[-1] ^= 0xFF
    t.send_raw(bytes(bad), "crc_bad", 3)
    time.sleep(0.05)
    hold(0)
    time.sleep(0.05)
    p = [d for _, d in L.since(m, "P")]
    x = [d for _, d in L.since(m, "X")]
    s1 = L.snapshot()
    stop_stop = {"P_notes": p, "X_notes": x, "running_after": s1["run"]}
    ok_bits1 = len(p) == 1 and p[0]["c"] == 0x11 and len(x) == 1 and s1["run"] == 0
    # STOP + START aynı maskede -> STOP baskın; ayrı START yeniden başlatır
    hold(proto.HOLD_CONTROL)
    m = L.mark()
    L.ctrl(proto.START)                      # şu an STOPPED; START önce gelse de maskede STOP baskın
    L.ctrl(proto.STOP)
    time.sleep(0.03)
    hold(0)
    time.sleep(0.05)
    p2 = [d for _, d in L.since(m, "P")]
    g2 = [d for _, d in L.since(m, "G")]
    s2 = L.snapshot()
    m = L.mark()
    L.ctrl(proto.START)
    gs = L.wait(lambda d: d.get("t") == "G", m, 1.0)
    s3 = L.snapshot()
    res["bits"] = {"stop_stop_err": stop_stop,
                   "stop_start_same_mask": {"P_notes": p2, "G_notes": g2, "running_after": s2["run"]},
                   "separate_start": {"G_note": gs[1] if gs else None, "running_after": s3["run"]}}
    ok_bits = ok_bits1 and len(p2) == 1 and p2[0]["c"] == 0x03 and not g2 and s2["run"] == 0 \
        and gs is not None and s3["run"] == 1

    # 3) mailbox: alıcı bekletilirken 21,22,23 -> yalnız 23; sonra 0 -> 0
    hold(proto.HOLD_SETPOINT)
    m = L.mark()
    for v in (21, 22, 23):
        L.ctrl(proto.SETPOINT, v)
    time.sleep(0.03)
    hold(0)
    time.sleep(0.05)
    v1 = [d["a"] for _, d in L.since(m, "V")]
    m = L.mark()
    L.ctrl(proto.SETPOINT, 0)
    time.sleep(0.05)
    v2 = [d["a"] for _, d in L.since(m, "V")]
    res["mailbox"] = {"after_21_22_23": v1, "after_0": v2}
    ok_mail = v1 == [23] and v2 == [0]

    # 4) WithoutOverwrite: bekleyen değer varken pdFAIL, yokken pdPASS
    hold(proto.HOLD_SETPOINT)
    m = L.mark()
    L.ctrl(proto.SETPOINT, 5)
    L.ctrl(proto.SETPOINT_NO_OVERWRITE, 7)
    time.sleep(0.03)
    w1 = [d for _, d in L.since(m, "W")]
    hold(0)
    time.sleep(0.05)
    v3 = [d["a"] for _, d in L.since(m, "V")]
    m = L.mark()
    L.ctrl(proto.SETPOINT_NO_OVERWRITE, 9)
    time.sleep(0.05)
    w2 = [d for _, d in L.since(m, "W")]
    v4 = [d["a"] for _, d in L.since(m, "V")]
    res["without_overwrite"] = {"pending_then_7": {"W": w1, "received": v3}, "idle_then_9": {"W": w2, "received": v4}}
    ok_wo = len(w1) == 1 and w1[0]["b"] == 0 and v3 == [5] and len(w2) == 1 and w2[0]["b"] == 1 and v4 == [9]

    res["parts_pass"] = {"counter": ok_counter, "bits": ok_bits, "mailbox": ok_mail, "without_overwrite": ok_wo}
    return t.finish(res, ok_counter and ok_bits and ok_mail and ok_wo)["pass"]


class Load:
    """Arka planda 200 DATA/s yük."""

    def __init__(self, t, rate=200, payload=32, stream="load"):
        self.t, self.rate, self.payload = t, rate, payload
        self.g = proto.Gen(stream=stream)
        self.stop = threading.Event()
        self.th = threading.Thread(target=self.run, daemon=True)
        self.seq = 0

    def run(self):
        t0 = time.perf_counter()
        while not self.stop.is_set():
            target = t0 + self.seq / self.rate
            d = target - time.perf_counter()
            if d > 0:
                time.sleep(d)
            self.t.send_data(self.seq, self.g.payload(self.payload))
            self.seq += 1

    def __enter__(self):
        self.th.start()
        return self

    def __exit__(self, *a):
        self.stop.set()
        self.th.join()


def epoch_check(t, start):
    """Her işin başladığı anda RUNNING mi? (stop_epoch == start_epoch)"""
    bad = [d for _, d in t.L.since(start, "R") if d["e"] != d["g"]]
    return {"responses": len(t.L.since(start, "R")), "started_while_stopped": len(bad), "first": bad[:5]}


def t7(port):
    t = Test("T7", port, {"load_rate": 200, "uart_cycles": 100, "stop_ms": 60, "run_ms": 60})
    L = t.L
    L.new_session()
    before = L.snapshot()
    start = L.mark()
    stops, starts, host_rtt = [], [], []
    with Load(t) as load:
        time.sleep(0.5)
        for i in range(100):
            m = L.mark()
            t0 = now_ns()
            seq = L.ctrl(proto.STOP)
            p = L.wait(lambda d: d.get("t") == "P" and d.get("a") == seq, m, 1.0)
            if p:
                stops.append(p[1]["b"])
                host_rtt.append((p[0] - t0) / 1000)
            time.sleep(0.06)
            m = L.mark()
            seq = L.ctrl(proto.START)
            gg = L.wait(lambda d: d.get("t") == "G" and d.get("a") == seq, m, 1.0)
            starts.append(gg is not None)
            time.sleep(0.06)
        time.sleep(0.3)
    after = quiet(t, 1.0)
    _, r = check_responses(t, start, t.data)
    ep = epoch_check(t, start)
    eq = equalities(after)
    dl = delta(before, after)
    ok = (len(stops) == 100 and max(stops) <= 50000 and all(starts) and ep["started_while_stopped"] == 0
          and r["wrong_checksum"] == 0 and all(v[2] for v in eq.values()))
    return t.finish({"uart_stop_latency_board": lat_stats(stops),
                     "host_send_to_stop_ack": {"note": "host yazma -> P satırı alındı; kart içi garanti değil",
                                               **lat_stats(host_rtt)},
                     "start_acks": sum(starts), "epoch_check": ep, "responses": r, "delta": dl,
                     "stop_policy": "bekleyen işler saklanır (iptal yok), yürüyen iş biter",
                     "equalities": eq}, ok)["pass"]


def t7b(port, presses=20, timeout=180):
    t = Test("T7B", port, {"load_rate": 200, "button_presses_min": presses, "debounce_ms": 50,
                           "restart": "host her buton STOP'undan 300 ms sonra START gönderir"})
    L = t.L
    L.new_session()
    before = L.snapshot()
    start = L.mark()
    lats = []
    print(f"B1 butonuna en az {presses} kez basın (aralarda ~1 s bekleyin)...", flush=True)
    end = time.monotonic() + timeout
    with Load(t):
        m = L.mark()
        while len(lats) < presses and time.monotonic() < end:
            b = L.wait(lambda d: d.get("t") == "B", m, 1.0)
            if not b:
                continue
            m = L.events.index(b) + 1
            lats.append(b[1]["b"])
            print(f"  basış {len(lats)}: {b[1]['b']} us", flush=True)
            time.sleep(0.3)
            L.ctrl(proto.START)
        time.sleep(0.3)
    after = quiet(t, 1.0)
    ep = epoch_check(t, start)
    eq = equalities(after)
    ok = len(lats) >= presses and max(lats) <= 50000 and ep["started_while_stopped"] == 0 and all(
        v[2] for v in eq.values())
    return t.finish({"button_stop_latency_board": lat_stats(lats), "bounces_rejected": after["bnc"] - before["bnc"],
                     "epoch_check": ep, "equalities": eq}, ok)["pass"]


def reset_board():
    r = subprocess.run([CUBE_PROG, "-c", "port=SWD", "mode=HOTPLUG", "-rst"], capture_output=True, text=True)
    return r.returncode == 0


def clean_burst(t, n, stream):
    g = proto.Gen(stream=stream)
    start = t.L.mark()
    t.L.new_session()
    sent = {}
    for i in pace(200, n):
        p = g.payload(32)
        t.L.write(proto.frame(proto.DATA, i, p))
        sent[i] = proto.checksum(p)
    time.sleep(0.4)
    got = t.responses(start)
    return sum(1 for s in sent if s in got and got[s][0][1]["c"] == sent[s]) == n


def t8(port):
    t = Test("T8", port, {"port_reopen_rounds": 10, "reset_rounds": 5,
                          "note": "port kapatma fiziksel kablo çekme ile aynı test değildir"})
    L = t.L
    g = proto.Gen(stream="T8")
    rounds = []
    for i in range(10):
        s0 = L.snapshot()
        f = proto.frame(proto.DATA, 1000 + i, g.payload(40))
        cut = g.rng.randint(4, len(f) - 2)
        t.send_raw(f[:cut], "cut_then_close", 1000 + i)
        L.close()                                     # yarım çerçeve içinde port kapandı
        time.sleep(0.3)
        L.open()
        s1 = L.snapshot()
        ok_clean = clean_burst(t, 20, f"T8-{i}")
        rounds.append({"round": i, "cut_at": cut, "same_session": s0["sid"] == s1["sid"],
                       "timeout_err_delta": s1["to"] - s0["to"], "clean_20_ok": ok_clean})
    resets = []
    for i in range(5):
        s0 = L.snapshot()
        m = L.mark()
        f = proto.frame(proto.DATA, 2000 + i, g.payload(40))
        t.send_raw(f[:20], "cut_then_reset", 2000 + i)
        okr = reset_board()
        h = L.wait(lambda d: d.get("t") == "H", m, 5.0)
        time.sleep(0.2)
        s1 = L.snapshot() if h else None
        ok_clean = clean_burst(t, 20, f"T8R-{i}") if h else False
        resets.append({"round": i, "reset_cmd_ok": okr, "hello": h[1] if h else None,
                       "old_sid": s0["sid"], "new_sid": s1["sid"] if s1 else None,
                       "counters_restarted": bool(s1) and s1["isr"] < s0["isr"], "clean_20_ok": ok_clean})
    ok = all(r["same_session"] and r["timeout_err_delta"] == 1 and r["clean_20_ok"] for r in rounds) and all(
        r["hello"] and r["new_sid"] != r["old_sid"] and r["counters_restarted"] and r["clean_20_ok"] for r in resets)
    return t.finish({"port_reopen": rounds, "board_reset": resets}, ok)["pass"]


def t9(port):
    """Sesli açıklama: düşük öncelikli log yükü aynı UART'ı kullanırken cevap gecikmesi."""
    t = Test("T9", port, {"data_rate": 50, "duration_s_per_level": 15, "log_rates_Bps": [0, 10000, 20000, 40000]})
    L = t.L
    L.new_session()
    levels = []
    seq = 0
    g = proto.Gen(stream="T9")
    for lr in (0, 10000, 20000, 40000):
        m = L.mark()
        L.ack(L.ctrl(proto.LOG_RATE, lr), proto.LOG_RATE, m)
        b0 = L.snapshot()
        start = L.mark()
        sent = {}
        tsend = {}
        for _ in pace(50, 50 * 15):
            p = g.payload(32)
            tsend[seq] = now_ns()
            t.send_data(seq, p, f"log {lr}")
            sent[seq] = proto.checksum(p)
            seq += 1
        m = L.mark()
        L.ack(L.ctrl(proto.LOG_RATE, 0), proto.LOG_RATE, m)
        a0 = quiet(t, 1.0)
        got = t.responses(start)
        q = [v[0][1]["q"] for s, v in got.items() if s in sent]
        rtt = [(v[0][0] - tsend[s]) / 1000 for s, v in got.items() if s in sent]
        dl = delta(b0, a0)
        dur = 15
        levels.append({"log_rate_Bps": lr, "responses": len(q), "sent": len(sent),
                       "validate_to_txstream": lat_stats(q),
                       "host_send_to_response_line": lat_stats(rtt),
                       "log_lines": dl["ll"], "log_dropped": dl["ldr"],
                       "log_Bps_delivered": round(dl["ll"] * 80 / dur), "resp_dropped": dl["rdr"]})
    ok = all(lv["responses"] == lv["sent"] and lv["resp_dropped"] == 0 for lv in levels) and \
        max(lv["validate_to_txstream"]["p99_ms"] for lv in levels) <= 20
    return t.finish({"levels": levels, "tx_stream_bytes": 128,
                     "note": "q: doğrulama -> cevabın txStream'e girdiği an (kart saati)"}, ok)["pass"]


TESTS = {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t6, "T7": t7, "T7B": t7b, "T8": t8, "T9": t9}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("tests", nargs="+", choices=list(TESTS))
    a = ap.parse_args()
    summary = {}
    for name in a.tests:
        summary[name] = TESTS[name](a.port)
    print(json.dumps(summary))
    sys.exit(0 if all(summary.values()) else 1)


if __name__ == "__main__":
    main()
