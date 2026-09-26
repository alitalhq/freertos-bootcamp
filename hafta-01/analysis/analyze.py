"""Ödev 01 analizi: measurements/S0..S5 ham verisinden özet tablo ve grafikler.

Tüm çıktılar yalnızca ham CSV + meta dosyalarından üretilir (elle düzeltme yok):
  measurements/summary.csv
  analysis/plots/response_per_event.png   olay no -> R, 20 ms deadline
  analysis/plots/stage_breakdown.png      senaryo -> aşama ortalamaları (yığılmış)
  analysis/plots/stage_distribution.png   senaryo -> t1-t0 ve t3-t2 dağılımı
  measurements/lab/summary.csv, analysis/plots/lab_fixes.png
                                          standart dışı ek deney: S5 çözümleri

Kullanım: python analysis/analyze.py
"""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MEAS = ROOT / "measurements"
PLOTS = ROOT / "analysis" / "plots"
SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5"]
LABELS = {  # telemetri / ek CPU işi
    "S0": "S0\noff", "S1": "S1\n10 Hz", "S2": "S2\n50 Hz",
    "S3": "S3\n100 Hz", "S4": "S4\n100 Hz\n+2 ms", "S5": "S5\n100 Hz\n+5 ms",
}
DEADLINE_US = 20_000
U32 = 2 ** 32
STAGES = [("t0_us", "t1_us", "t1−t0 task wait"),
          ("t1_us", "t2_us", "t2−t1 prepare"),
          ("t2_us", "t3_us", "t3−t2 pre-TX wait"),
          ("t3_us", "t4_us", "t4−t3 UART + TC")]

# Renkler: dataviz referans paleti (açık tema), doğrulayıcıdan geçti.
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # kategorik sıra 1..4
CRITICAL = "#d03b3b"                                     # durum: deadline ihlali / kayıp


# ------------------------------------------------------------------ veri --

def diff(a: int | None, b: int | None) -> int | None:
    """uint32 farkı mod 2^32 (spec R-REC-3)."""
    return None if a is None or b is None else (b - a) % U32


def load(scn: str) -> tuple[list[dict], dict[str, str]]:
    rows = []
    with (MEAS / f"{scn}.csv").open() as f:
        for r in csv.DictReader(f):
            r["event_id"] = int(r["event_id"])
            for k in ("t0_us", "t1_us", "t2_us", "t3_us", "t4_us"):
                r[k] = int(r[k]) if r[k] else None       # boş = ölçülmedi
            rows.append(r)
    meta = {}
    for line in (MEAS / f"{scn}_meta.txt").read_text().splitlines():
        if line.startswith(("CFG,", "CNT,")):
            for kv in line.split(",")[1:]:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    meta[k] = v
    return rows, meta


def r_us(r: dict) -> int | None:
    return diff(r["t0_us"], r["t4_us"])


def ms(x: float | None) -> str:
    return "" if x is None else f"{x / 1000:.3f}"


def summarize(scn: str, rows: list[dict], meta: dict) -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    rs = [r_us(r) for r in ok]
    status = lambda s: sum(r["status"] == s for r in rows)  # noqa: E731
    out = {
        "scenario": scn,
        "telemetry_period_ms": meta.get("period_ms"),
        "work_us_target": meta.get("work_us"),
        "accepted": len(rows),
        "ok": len(ok),
        "not_ok": len(rows) - len(ok),
        "btn_drop": status("btn_drop"),
        "tx_drop": status("tx_drop"),
        "tx_error": status("tx_error"),
        "timeout": status("timeout"),
        "r_min_ms": ms(min(rs)) if rs else "",
        "r_avg_ms": ms(statistics.mean(rs)) if rs else "",
        "r_p95_ms": ms(float(np.percentile(rs, 95))) if rs else "",
        "r_max_ms": ms(max(rs)) if rs else "",
        "late_over_20ms": sum(x > DEADLINE_US for x in rs),
    }
    for a, b, name in STAGES:
        vals = [diff(r[a], r[b]) for r in ok]
        key = name.split()[0].replace("−", "_")
        out[f"{key}_avg_ms"] = ms(statistics.mean(vals)) if vals else ""
        out[f"{key}_max_ms"] = ms(max(vals)) if vals else ""
    period_avg = int(meta.get("period_avg_us", 0) or 0)
    out.update({
        "txq_hwm": meta.get("txq_hwm"),
        "buttonq_hwm": meta.get("buttonq_hwm"),
        "tel_sent": meta.get("tel_sent"),
        "tel_tx_drop": meta.get("tel_tx_drop"),
        "tel_rate_hz_measured": f"{1e6 / period_avg:.2f}" if period_avg else "",
        "tel_period_min_us": meta.get("period_min_us", ""),
        "tel_period_max_us": meta.get("period_max_us", ""),
        "work_avg_us_measured": meta.get("work_avg_us", ""),
        "work_max_us_measured": meta.get("work_max_us", ""),
        "bounce_rejected": meta.get("bounce_rejected"),
        "uart_error": meta.get("uart_error"),
        "uart_timeout": meta.get("uart_timeout"),
    })
    return out


# ------------------------------------------------------------- grafikler --

def style(ax, ylabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)


def new_fig(w: float, h: float, **kw):
    fig, axes = plt.subplots(figsize=(w, h), facecolor=SURFACE, **kw)
    return fig, axes


def plot_response_per_event(data: dict) -> Path:
    """Küçük katlar: S0–S4 ortak 0–25 ms ekseninde, S5 kendi ölçeğinde."""
    fig, axes = new_fig(12, 6.2, nrows=2, ncols=3)
    for ax, scn in zip(axes.flat, SCENARIOS):
        rows = data[scn][0]
        ok = [(r["event_id"], r_us(r) / 1000) for r in rows if r["status"] == "ok"]
        lost = [r["event_id"] for r in rows if r["status"] != "ok"]
        on_time = [(x, y) for x, y in ok if y <= DEADLINE_US / 1000]
        late = [(x, y) for x, y in ok if y > DEADLINE_US / 1000]
        style(ax, "R = t4 − t0 (ms)")
        ax.plot(*zip(*ok), color=GRID, linewidth=1.5, zorder=1)
        if on_time:
            ax.scatter(*zip(*on_time), s=22, color=SERIES[0], edgecolor=SURFACE,
                       linewidth=1, zorder=3, label="response ≤ 20 ms")
        if late:
            ax.scatter(*zip(*late), s=26, marker="s", color=CRITICAL, edgecolor=SURFACE,
                       linewidth=1, zorder=3, label="response > 20 ms")
        ax.axhline(DEADLINE_US / 1000, color=CRITICAL, linestyle="--", linewidth=1, zorder=2)
        ymax = 25 if scn != "S5" else 180
        if lost:
            ax.scatter(lost, [ymax * 0.03] * len(lost), marker="x", s=30, color=CRITICAL,
                       linewidth=1.5, zorder=3, label=f"no response (tx_drop) ×{len(lost)}")
        ax.set_ylim(0, ymax)
        ax.set_xlim(-1, 35)
        ax.set_xlabel("event id", color=INK2, fontsize=9)
        n_late = len(late)
        ax.set_title(f"{LABELS[scn].replace(chr(10), ' · ')}   n={len(rows)}, ok={len(ok)}, >20 ms={n_late}",
                     loc="left", fontsize=10, color=INK)
        ax.text(34.5, DEADLINE_US / 1000, "deadline 20 ms", ha="right", va="bottom",
                fontsize=8, color=INK2)
        if scn == "S5":
            ax.legend(loc="center right", fontsize=8, frameon=False, labelcolor=INK2)
    axes[0, 0].legend(loc="upper left", fontsize=8, frameon=False, labelcolor=INK2)
    fig.suptitle("Response time per button event (board timestamps; S0–S4 share a 0–25 ms axis, S5 has its own)",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = PLOTS / "response_per_event.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


def plot_stage_breakdown(data: dict) -> Path:
    """Yığılmış sütun: yalnızca 'ok' kayıtların aşama ortalamaları."""
    fig, (ax1, ax2) = new_fig(11, 4.8, ncols=2, gridspec_kw={"width_ratios": [5, 1.4]})
    for ax, scns, ymax in ((ax1, SCENARIOS[:5], 10), (ax2, ["S5"], 120)):
        style(ax, "mean duration (ms)")
        x = np.arange(len(scns))
        bottom = np.zeros(len(scns))
        for i, (a, b, name) in enumerate(STAGES):
            vals = np.array([statistics.mean(diff(r[a], r[b]) for r in data[s][0] if r["status"] == "ok") / 1000
                             for s in scns])
            ax.bar(x, vals, bottom=bottom, width=0.6, color=SERIES[i], edgecolor=SURFACE,
                   linewidth=1.5, label=name)
            bottom += vals
        for xi, total, s in zip(x, bottom, scns):
            n = sum(r["status"] == "ok" for r in data[s][0])
            ax.text(xi, total + ymax * 0.015, f"{total:.2f} ms\nn={n}", ha="center", va="bottom",
                    fontsize=8, color=INK2)
        ax.set_xticks(x, [LABELS[s] for s in scns])
        ax.set_ylim(0, ymax)
    ax1.axhline(DEADLINE_US / 1000, color=CRITICAL, linestyle="--", linewidth=1)
    ax2.axhline(DEADLINE_US / 1000, color=CRITICAL, linestyle="--", linewidth=1)
    ax2.text(-0.28, DEADLINE_US / 1000, "deadline 20 ms", ha="left", va="bottom", fontsize=8, color=INK2)
    ax1.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=INK2, ncols=2)
    ax2.set_title("S5 (own scale)", fontsize=9, color=INK2)
    fig.suptitle("Where the response time goes: mean of each stage, successful responses only",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = PLOTS / "stage_breakdown.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


def plot_stage_distribution(data: dict) -> Path:
    """Her olay bir nokta: hangi aşama hangi senaryoda dağılıyor?"""
    fig, axes = new_fig(11, 4.6, ncols=2)
    rng = np.random.default_rng(1)   # yalnızca yatay titreşim; veri değişmez
    for ax, (a, b, name), color in ((axes[0], STAGES[0], SERIES[0]), (axes[1], STAGES[2], SERIES[2])):
        style(ax, f"{name.split()[0]} (ms, log scale)")
        for i, s in enumerate(SCENARIOS):
            vals = [diff(r[a], r[b]) / 1000 for r in data[s][0] if diff(r[a], r[b]) is not None]
            xs = i + rng.uniform(-0.18, 0.18, len(vals))
            ax.scatter(xs, vals, s=14, color=color, alpha=0.75, edgecolor=SURFACE, linewidth=0.5)
            ax.hlines(statistics.median(vals), i - 0.28, i + 0.28, color=INK, linewidth=1.5)
        ax.set_yscale("log")
        ax.set_xticks(range(len(SCENARIOS)), [LABELS[s] for s in SCENARIOS])
        ax.set_title(name + ("  — grows with CPU load" if b == "t1_us"
                             else "  — grows with UART load; S5: UART task starved"),
                     loc="left", fontsize=10, color=INK)
    fig.suptitle("Per-event stage durations (dots = events that reached the stage, bar = median)",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = PLOTS / "stage_distribution.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


# ---------------------------------------------------- standart dışı ek deney --

LAB_ORDER = [("S5a", "standard"), ("S5-F4a", "naive:\nButtonTask prio"),
             ("S5-F1a", "root cause:\nUART prio"), ("S5-F5a", "optimal:\nUART + Button prio")]


def load_lab() -> list[tuple[str, str, list[dict], dict]]:
    out = []
    for name, label in LAB_ORDER:
        p = MEAS / "lab" / f"{name}.csv"
        if p.exists():
            rows = []
            with p.open() as f:
                for r in csv.DictReader(f):
                    r["event_id"] = int(r["event_id"])
                    for k in ("t0_us", "t1_us", "t2_us", "t3_us", "t4_us"):
                        r[k] = int(r[k]) if r[k] else None
                    rows.append(r)
            meta = {}
            for line in (MEAS / "lab" / f"{name}_meta.txt").read_text().splitlines():
                for kv in line.split(",")[1:]:
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        meta[k] = v
            out.append((name, label, rows, meta))
    return out


def plot_lab_fixes(lab) -> Path:
    """S5 yükü altında çözüm denemeleri: aşama ortalamaları (yığılmış) + max R.
    Eşiği çok aşanlar kırpılır, değeri üstte yazılır (log ölçek yığını çarpıtır)."""
    fig, ax = new_fig(12, 5)
    style(ax, "mean duration per stage (ms)")
    cap = 32
    x = np.arange(len(lab))
    bottom = np.zeros(len(lab))
    for i, (a, b, name) in enumerate(STAGES):
        vals = np.array([statistics.mean(diff(r[a], r[b]) for r in rows if r["status"] == "ok") / 1000
                         for _, _, rows, _ in lab])
        ax.bar(x, vals, bottom=bottom, width=0.62, color=SERIES[i], edgecolor=SURFACE, linewidth=1.5, label=name)
        bottom += vals
    maxes = [max(r_us(r) for r in rows if r["status"] == "ok") / 1000 for _, _, rows, _ in lab]
    ax.scatter(x, [min(m, cap * 0.985) for m in maxes], marker="_", s=320, color=INK, linewidth=2, zorder=4,
               label="max R")
    ax.axhline(DEADLINE_US / 1000, color=CRITICAL, linestyle="--", linewidth=1)
    ax.text(len(lab) - 0.45, DEADLINE_US / 1000, "deadline 20 ms", ha="right", va="bottom", fontsize=8, color=INK2)
    for xi, tot, mx, (_, _, rows, meta) in zip(x, bottom, maxes, lab):
        ok = [r for r in rows if r["status"] == "ok"]
        late = sum(r_us(r) > DEADLINE_US for r in ok)
        lost = len(rows) - len(ok)
        info = f"{late} late · {lost} lost\ntxQ max {meta.get('txq_hwm')}"
        if tot > cap:
            ax.text(xi, cap * 0.93, f"▲ mean {tot:.0f} ms\n" + info, ha="center", va="top", fontsize=8,
                    color=CRITICAL, bbox=dict(fc=SURFACE, ec="none", pad=1))
        else:
            ax.text(xi, max(tot, mx) + 0.6, f"max {mx:.1f} ms\n" + info, ha="center", va="bottom", fontsize=8,
                    color=CRITICAL if late or lost else INK2)
    ax.set_ylim(0, cap)
    ax.set_xticks(x, [lbl for _, lbl, _, _ in lab], fontsize=9)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncols=5, fontsize=8, frameon=False,
              labelcolor=INK2)
    fig.suptitle("S5 load (100 Hz + 5 ms CPU work), 35 auto presses each, same press sequence (seed 7) — "
                 "NON-STANDARD lab experiment", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = PLOTS / "lab_fixes.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


def main() -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    data = {s: load(s) for s in SCENARIOS}
    summary = [summarize(s, *data[s]) for s in SCENARIOS]
    with (MEAS / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    print(f"wrote {MEAS / 'summary.csv'}")
    for p in (plot_response_per_event(data), plot_stage_breakdown(data), plot_stage_distribution(data)):
        print(f"wrote {p}")

    lab = load_lab()
    if lab:
        lab_summary = [summarize(name, rows, meta) for name, _, rows, meta in lab]
        for row, (_, _, _, meta) in zip(lab_summary, lab):
            row["fix_mask"] = meta.get("fix")
            row["presses"] = "auto" if meta.get("inject") == "1" else "manual"
        with (MEAS / "lab" / "summary.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(lab_summary[0].keys()))
            w.writeheader()
            w.writerows(lab_summary)
        print(f"wrote {MEAS / 'lab' / 'summary.csv'}")
        print(f"wrote {plot_lab_fixes(lab)}")


if __name__ == "__main__":
    main()
