"""Deneme (run) modeli: kayıtları yükler, aşama sürelerini hesaplar ve
deadline ihlallerinin nedenini ölçülen verilerden çıkarır.

Arayüzden bağımsızdır (Qt yok); lab_app.py ve testler kullanır.
Kullanıcıya görünen metinler Türkçedir (teknik terimler olduğu gibi).
"""
from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from protocol import CSV_HEADER, Export, ExportCollector, LineFramer, Record, parse_kv, parse_line

DEADLINE_MS = 20.0
LINE_MS = 64 * 10 / 115200 * 1000        # bir 64 baytlık mesajın hat süresi: 5,556 ms
STAGES = [                                # (anahtar, etiket, t_başlangıç, t_bitiş)
    ("task", "Görev bekleme (t1−t0)", 0, 1),
    ("prep", "Yanıt hazırlama (t2−t1)", 1, 2),
    ("pretx", "TX öncesi bekleme (t3−t2)", 2, 3),
    ("line", "UART + TC (t4−t3)", 3, 4),
]
ROOT = Path(__file__).resolve().parents[1]

GROUP_OFFICIAL = "Resmi ölçümler (elle)"
GROUP_LAB = "Lab: S5 çözümleri (otomatik)"
GROUP_SESSION = "Bu oturum"
GROUP_FILES = "Dosyalar"


def ms(v: float) -> str:
    """Türkçe ondalık gösterim: 5,56."""
    return f"{v:.2f}".replace(".", ",")


@dataclass
class Event:
    rec: Record
    stages_ms: dict[str, float | None]
    r_ms: float | None

    @property
    def ok(self) -> bool:
        return self.rec.status == "ok"

    @property
    def late(self) -> bool:
        return self.ok and self.r_ms is not None and self.r_ms > DEADLINE_MS


@dataclass
class Run:
    key: str                     # benzersiz kimlik
    label: str                   # arayüzde görünen ad
    group: str                   # GROUP_* sabitlerinden biri
    cfg: dict[str, str] = field(default_factory=dict)
    cnt: dict[str, str] = field(default_factory=dict)
    tasks: list[dict[str, str]] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    raw: bytes = b""             # canlı oturumun ham UART baytları (varsa)

    # ---- özet ----------------------------------------------------------
    @property
    def official(self) -> bool:
        return self.group == GROUP_OFFICIAL

    @property
    def ok_events(self) -> list[Event]:
        return [e for e in self.events if e.ok and e.r_ms is not None]

    @property
    def r_values(self) -> list[float]:
        return [e.r_ms for e in self.ok_events]

    def stat(self) -> dict[str, float | int | None]:
        rs = self.r_values
        return {
            "n": len(self.events),
            "ok": len(rs),
            "avg": statistics.mean(rs) if rs else None,
            "max": max(rs) if rs else None,
            "p95": sorted(rs)[max(0, int(round(0.95 * len(rs))) - 1)] if rs else None,
            "late": sum(r > DEADLINE_MS for r in rs),
            "lost": len(self.events) - len(rs),
            "tel_lost": int(self.cnt.get("tel_tx_drop", 0) or 0),
        }

    def stage_means(self) -> dict[str, float]:
        out = {}
        for key, *_ in STAGES:
            vals = [e.stages_ms[key] for e in self.ok_events if e.stages_ms[key] is not None]
            out[key] = statistics.mean(vals) if vals else 0.0
        return out

    # ---- deney koşulları ------------------------------------------------
    @property
    def period_ms(self) -> int:
        return int(self.cfg.get("period_ms", 0) or 0)

    @property
    def work_us(self) -> int:
        return int(self.cfg.get("work_us", 0) or 0)

    @property
    def fix(self) -> int:
        return int(self.cfg.get("fix", 0) or 0)

    @property
    def inject(self) -> bool:
        return self.cfg.get("inject", "0") == "1"

    def conditions(self) -> str:
        tel = "telemetri kapalı" if self.period_ms == 0 else f"{1000 / self.period_ms:.0f} Hz telemetri"
        work = f" + {self.work_us / 1000:g} ms CPU işi" if self.work_us else ""
        press = "otomatik basış" if self.inject else "elle basış"
        return f"{tel}{work} · {press}"

    # ---- birikim (backlog) ---------------------------------------------
    def backlog_slope_ms_per_event(self) -> float | None:
        """TX öncesi beklemenin olay numarasına göre eğimi (en küçük kareler).
        ~+10 ms/olay: her yanıt kuyruğa kalıcı +1 mesaj ekliyor."""
        pts = [(e.rec.event_id, e.stages_ms["pretx"]) for e in self.ok_events if e.stages_ms["pretx"] is not None]
        if len(pts) < 5:
            return None
        xs, ys = zip(*pts)
        mx, my = statistics.mean(xs), statistics.mean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        return sum((x - mx) * (y - my) for x, y in pts) / den if den else None

    def uart_starved(self) -> bool:
        """Hattın periyot başına en fazla 1 mesaj taşıyabildiği durum: CPU işinden
        sonra kalan pencere bir mesaj süresinden kısa ve UART görevi yükseltilmemiş."""
        if self.period_ms == 0 or self.work_us == 0:
            return False
        free_ms = self.period_ms - self.work_us / 1000
        return free_ms < LINE_MS and not (self.fix & 0x1) and not (self.fix & 0x8)

    # ---- nedenler --------------------------------------------------------
    def diagnose(self, ev: Event) -> tuple[str, str]:
        """(baskın aşama, açıklama). Yalnızca ölçülen damgalar ve deney
        koşullarından çıkarım yapar."""
        s = ev.stages_ms
        if ev.rec.status == "tx_drop":
            why = ("Yanıt gönderilmek istendiğinde txQ doluydu (16/16), bu yüzden düştü. Kuyruk doldu, "
                   "çünkü mesajlar UART görevinin başlatabileceğinden hızlı geliyor.")
            if self.uart_starved():
                why += (f" Bu yükte öncelik 1'deki UART görevi {self.period_ms} ms'lik periyot başına yalnızca "
                        f"bir {ms(LINE_MS)} ms'lik mesaj başlatabiliyor.")
            if s["task"] is not None and s["task"] > 0.3:
                why += (f" Basış CPU işi penceresine de denk geldi (t1−t0 = {ms(s['task'])} ms), "
                        "boşalan yeri önce TelemetryTask doldurdu.")
            return "pretx", why
        if ev.rec.status != "ok" or ev.r_ms is None:
            return "", f"Yanıt yok ({ev.rec.status})."

        dom = max((k for k, *_ in STAGES), key=lambda k: s[k] or 0.0)
        pretx, task = s["pretx"] or 0.0, s["task"] or 0.0
        parts = []
        if dom == "line":
            parts.append(f"Sürenin çoğu yanıtın kendi hat süresi ({ms(LINE_MS)} ms). Önünde bekleyen bir şey yoktu.")
        if pretx > 0.2:
            if pretx <= LINE_MS * 1.05:
                parts.append(f"TX öncesi bekleme {ms(pretx)} ms: yanıt, hatta o an giden telemetri mesajının "
                             "bitmesini bekledi.")
            else:
                ahead = f"{pretx / LINE_MS:.1f}".replace(".", ",")
                parts.append(f"TX öncesi bekleme {ms(pretx)} ms ≈ txQ'da önünde {ahead} mesaj: "
                             "birikim oluşmuştu.")
                if self.uart_starved():
                    free = self.period_ms - self.work_us / 1000
                    parts.append(f"Kök neden: öncelik 3'teki {self.work_us / 1000:g} ms'lik işten sonra her "
                                 f"periyotta yalnızca {ms(free)} ms kalıyor; bu, bir mesajdan ({ms(LINE_MS)} ms) "
                                 "kısa. Öncelik 1'deki UART görevi periyot başına tek mesaj başlatabiliyor, bu da "
                                 "telemetri hızına eşit; her yanıt hiç erimeyen bir mesaj ekliyor.")
        if task > 0.3:
            parts.append(f"Görev bekleme {ms(task)} ms: basış, öncelik 3'teki TelemetryTask CPU işini yaparken geldi; "
                         "öncelik 2'deki ButtonTask işin bitmesini bekledi.")
        verdict = "AŞILDI" if ev.late else "tutuldu"
        head = f"R = {ms(ev.r_ms)} ms, deadline {verdict} (pay {ms(DEADLINE_MS - ev.r_ms)} ms). "
        return dom, head + " ".join(parts)

    def cause_counts(self) -> dict[str, int]:
        """Aşan ya da kaybolan olaylarda baskın aşama sayısı."""
        out: dict[str, int] = {}
        names = dict((k, lbl) for k, lbl, *_ in STAGES)
        for e in self.events:
            if e.late or not e.ok:
                dom, _ = self.diagnose(e)
                label = "kayıp (txQ dolu)" if not e.ok else names[dom]
                out[label] = out.get(label, 0) + 1
        return out


# ---- oluşturma / yükleme ----------------------------------------------------

def make_event(rec: Record) -> Event:
    st = {}
    for key, _, a, b in STAGES:
        d = Record.diff(rec.t[a], rec.t[b])
        st[key] = None if d is None else d / 1000
    r = rec.r_us
    return Event(rec, st, None if r is None else r / 1000)


def from_export(exp: Export, key: str, label: str, group: str, raw: bytes = b"") -> Run:
    return Run(key, label, group, dict(exp.cfg), dict(exp.cnt), list(exp.tasks),
               [make_event(r) for r in exp.records], raw)


def load_csv(csv_path: Path, group: str, label: str | None = None) -> Run:
    records = []
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            ts = [int(row[k]) if row[k] else None for k in ("t0_us", "t1_us", "t2_us", "t3_us", "t4_us")]
            records.append(Record(row["scenario"], int(row["event_id"]), ts, row["status"]))
    cfg, cnt, tasks = {}, {}, []
    meta = csv_path.with_name(csv_path.stem + "_meta.txt")
    if meta.exists():
        for line in meta.read_text().splitlines():
            parts = line.split(",")
            if parts[0] == "CFG":
                cfg.update(parse_kv(parts[1:]))
            elif parts[0] == "CNT":
                cnt.update(parse_kv(parts[1:]))
            elif parts[0] == "TSK":
                tasks.append({"name": parts[1], **parse_kv(parts[2:])})
    name = cfg.get("scenario", csv_path.stem)
    return Run(f"{group}:{csv_path}", label or name, group, cfg, cnt, tasks,
               [make_event(r) for r in records])


def load_raw(path: Path, group: str = GROUP_FILES) -> Run | None:
    """Ham UART oturumunu yeniden oynatır; içindeki son export'u döndürür."""
    framer, col, exp = LineFramer(), ExportCollector(), None
    data = path.read_bytes()
    for raw in framer.feed(data):
        exp = col.feed(parse_line(raw)) or exp
    if exp is None:
        return None
    return from_export(exp, f"{group}:{path}", f"{exp.scenario} · {path.name}", group, data)


def is_record_csv(path: Path) -> bool:
    """Olay kaydı CSV'si mi (summary.csv gibi özet dosyaları değil)?"""
    with path.open() as f:
        return f.readline().strip().split(",") == CSV_HEADER


def default_runs() -> list[Run]:
    """Açılışta gösterilen denemeler: resmi S0–S5 ve lab çözüm denemeleri."""
    from labctl import fix_label

    runs = []
    meas = ROOT / "measurements"
    for s in ["S0", "S1", "S2", "S3", "S4", "S5"]:
        p = meas / f"{s}.csv"
        if p.exists():
            runs.append(load_csv(p, GROUP_OFFICIAL, f"{s} · resmi"))
    lab = meas / "lab"
    if lab.exists():
        order = {0: 0, 4: 1, 1: 2, 8: 3, 5: 4}
        labs = [load_csv(p, GROUP_LAB) for p in sorted(lab.glob("*.csv")) if is_record_csv(p)]
        labs.sort(key=lambda r: (r.period_ms, r.work_us, order.get(r.fix, 99)))
        for r in labs:
            r.label = f"{r.cfg.get('scenario', '?')} · {fix_label(r.fix)}"
            runs.append(r)
    return runs
