"""Ödev 2 analizi: measurements/ altındaki A/B/C ölçümlerinden özet tablo ve grafikler.

Tüm çıktılar yalnızca ham CSV + meta dosyalarından üretilir (elle düzeltme yok):
  measurements/summary.csv              resmî koşular (fiziksel B1 basışları)
  measurements/auto/summary.csv         destekleyici koşular (otomatik basış), varsa
  analysis/plots/response_per_event.png olay no -> R, 20 ms çizgisi
  analysis/plots/stage_breakdown.png    koşu -> aşama ortalamaları (yığılmış)
  analysis/plots/drops_s5.png           S5: kaybolan mesajın türü (BTN mi TEL mi?)
  analysis/plots/tel_wait.png           koşu -> TEL kuyruk beklemesi (ort / maks)

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
RUNS = ["A-S5", "B-S5", "C-S5", "B-S6", "C-S6"]
LABELS = {
    "A-S5": "A · S5", "B-S5": "B · S5", "C-S5": "C · S5", "B-S6": "B · S6", "C-S6": "C · S6",
}
DEADLINE_US = 20_000
U32 = 2 ** 32
STAGES = [("t0_us", "t1_us", "t1−t0 task wait"),
          ("t1_us", "t2_us", "t2−t1 prepare"),
          ("t2_us", "t3_us", "t3−t2 pre-TX wait"),
          ("t3_us", "t4_us", "t4−t3 UART + TC")]

# Renkler: Hafta 1 ile aynı palet (açık tema).
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
CRITICAL = "#d03b3b"


# ------------------------------------------------------------------ veri --

def diff(a: int | None, b: int | None) -> int | None:
    """uint32 farkı mod 2^32 (spec R-REC-3)."""
    return None if a is None or b is None else (b - a) % U32


def load(folder: Path, name: str) -> tuple[list[dict], dict[str, str]]:
    rows = []
    with (folder / f"{name}.csv").open() as f:
        for r in csv.DictReader(f):
            r["event_id"] = int(r["event_id"])
            for k in ("t0_us", "t1_us", "t2_us", "t3_us", "t4_us"):
                r[k] = int(r[k]) if r[k] else None       # boş = ölçülmedi
            rows.append(r)
    meta = {}
    for line in (folder / f"{name}_meta.txt").read_text().splitlines():
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


def ok_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["status"] == "ok"]


def summarize(name: str, rows: list[dict], meta: dict) -> dict:
    ok = ok_rows(rows)
    rs = [r_us(r) for r in ok]
    status = lambda s: sum(r["status"] == s for r in rows)  # noqa: E731
    tel_sent = int(meta.get("tel_sent", 0))
    tel_drop = int(meta.get("tel_tx_drop", 0))
    out = {
        "run": name,
        "variant": meta.get("variant"),
        "presses": "auto" if meta.get("inject") == "1" else "manual (B1)",
        "prio_btn": meta.get("prio_btn"),
        "telemetry_period_ms": meta.get("period_ms"),
        "tel_per_period": meta.get("burst"),
        "work_us_target": meta.get("work_us"),
        "accepted": len(rows),
        "ok": len(ok),
        "btn_drop": status("btn_drop"),
        "tx_drop": status("tx_drop"),
        "tx_error": status("tx_error"),
        "timeout": status("timeout"),
        "rec_overflow": meta.get("rec_overflow"),
        "late_over_20ms": sum(x > DEADLINE_US for x in rs),
        "r_min_ms": ms(min(rs)) if rs else "",
        "r_median_ms": ms(statistics.median(rs)) if rs else "",
        "r_avg_ms": ms(statistics.mean(rs)) if rs else "",
        "r_p95_ms": ms(float(np.percentile(rs, 95))) if rs else "",
        "r_max_ms": ms(max(rs)) if rs else "",
    }
    for a, b, label in STAGES:
        vals = [diff(r[a], r[b]) for r in ok]
        key = label.split()[0].replace("−", "_")
        out[f"{key}_avg_ms"] = ms(statistics.mean(vals)) if vals else ""
        out[f"{key}_max_ms"] = ms(max(vals)) if vals else ""
    out.update({
        "tel_sent": tel_sent,
        "tel_tx_drop": tel_drop,
        "tel_loss_pct": f"{100 * tel_drop / (tel_sent + tel_drop):.3f}" if tel_sent + tel_drop else "",
        "tel_wait_avg_ms": ms(int(meta["tel_wait_avg_us"])) if "tel_wait_avg_us" in meta else "",
        "tel_wait_max_ms": ms(int(meta["tel_wait_max_us"])) if "tel_wait_max_us" in meta else "",
        "tx_pending_hwm": meta.get("txq_hwm"),
        "run_length_s": f"{int(meta.get('period_n', 0)) * int(meta.get('period_ms', 0)) / 1000:.0f}",
        "ignored_presses": meta.get("ignored"),
        "uart_error": meta.get("uart_error"),
        "uart_timeout": meta.get("uart_timeout"),
    })
    return out


def write_summary(folder: Path, data: dict) -> Path:
    summary = [summarize(n, *data[n]) for n in RUNS if n in data]
    out = folder / "summary.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
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
    return plt.subplots(figsize=(w, h), facecolor=SURFACE, **kw)


def save(fig, name: str) -> Path:
    out = PLOTS / name
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


def r_panel(ax, rows: list[dict], title: str, ymax: float) -> None:
    ok = [(r["event_id"], r_us(r) / 1000) for r in ok_rows(rows)]
    lost = [r["event_id"] for r in rows if r["status"] != "ok"]
    on_time = [(x, y) for x, y in ok if y <= DEADLINE_US / 1000]
    late = [(x, y) for x, y in ok if y > DEADLINE_US / 1000]
    style(ax, "R = t4 − t0 (ms)")
    ax.plot(*zip(*ok), color=GRID, linewidth=1.5, zorder=1)
    if on_time:
        ax.scatter(*zip(*on_time), s=22, color=SERIES[0], edgecolor=SURFACE, linewidth=1, zorder=3,
                   label="response ≤ 20 ms")
    if late:
        ax.scatter(*zip(*[(x, min(y, ymax * 0.985)) for x, y in late]), s=26, marker="s", color=CRITICAL,
                   edgecolor=SURFACE, linewidth=1, zorder=3, label="response > 20 ms")
    if lost:
        ax.scatter(lost, [ymax * 0.03] * len(lost), marker="x", s=30, color=CRITICAL, linewidth=1.5,
                   zorder=3, label=f"no response (tx_drop) ×{len(lost)}")
    ax.axhline(DEADLINE_US / 1000, color=CRITICAL, linestyle="--", linewidth=1, zorder=2)
    ax.text(34.5, DEADLINE_US / 1000, "deadline 20 ms", ha="right", va="bottom", fontsize=8, color=INK2)
    ax.set_ylim(0, ymax)
    ax.set_xlim(-1, 35)
    ax.set_xlabel("event id", color=INK2, fontsize=9)
    ax.set_title(f"{title}   n={len(rows)}, ok={len(ok)}, >20 ms={len(late)}", loc="left", fontsize=10,
                 color=INK)


def plot_response_per_event(data: dict) -> Path:
    """Üst sıra S5 (ortak 0–180 ms), alt sıra S6 ve C·S5 yakın çekim (0–30 ms)."""
    fig, axes = new_fig(13, 6.6, nrows=2, ncols=3)
    for ax, name in zip(axes[0], ["A-S5", "B-S5", "C-S5"]):
        r_panel(ax, data[name][0], LABELS[name], 180)
    for ax, name in zip(axes[1], ["B-S6", "C-S6"]):
        r_panel(ax, data[name][0], LABELS[name], 30)
    r_panel(axes[1, 2], data["C-S5"][0], "C · S5 (zoom)", 30)
    axes[0, 0].legend(loc="center right", fontsize=8, frameon=False, labelcolor=INK2)
    axes[1, 0].legend(loc="upper left", fontsize=8, frameon=False, labelcolor=INK2)
    fig.suptitle("Response time per button event, physical B1 presses (top: S5 on a 0–180 ms axis; "
                 "bottom: 0–30 ms)", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return save(fig, "response_per_event.png")


def stage_means(rows: list[dict]) -> list[float]:
    ok = ok_rows(rows)
    return [statistics.mean(diff(r[a], r[b]) for r in ok) / 1000 for a, b, _ in STAGES]


def plot_stage_breakdown(data: dict) -> Path:
    fig, (ax1, ax2) = new_fig(11, 4.8, ncols=2, gridspec_kw={"width_ratios": [3, 2]})
    for ax, names, ymax in ((ax1, ["A-S5", "B-S5", "C-S5"], 150), (ax2, ["B-S6", "C-S6"], 15)):
        style(ax, "mean duration (ms)")
        x = np.arange(len(names))
        bottom = np.zeros(len(names))
        means = np.array([stage_means(data[n][0]) for n in names])
        for i, (_, _, label) in enumerate(STAGES):
            ax.bar(x, means[:, i], bottom=bottom, width=0.6, color=SERIES[i], edgecolor=SURFACE,
                   linewidth=1.5, label=label)
            bottom += means[:, i]
        for xi, total, n, m in zip(x, bottom, names, means):
            ax.text(xi, total + ymax * 0.015,
                    f"{total:.2f} ms\nt1−t0 {m[0]:.2f} · t3−t2 {m[2]:.2f}\nn={len(ok_rows(data[n][0]))}",
                    ha="center", va="bottom", fontsize=8, color=INK2)
        ax.axhline(DEADLINE_US / 1000, color=CRITICAL, linestyle="--", linewidth=1)
        ax.set_xticks(x, [LABELS[n] for n in names])
        ax.set_ylim(0, ymax)
    ax1.set_title("S5: 100 Hz + 5 ms CPU work", loc="left", fontsize=10, color=INK)
    ax2.set_title("S6: 4 TEL every 100 ms (own scale)", loc="left", fontsize=10, color=INK)
    ax1.legend(loc="upper right", fontsize=8, frameon=False, labelcolor=INK2)
    fig.suptitle("Where the response time goes: mean of each stage, successful responses only",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return save(fig, "stage_breakdown.png")


def plot_drops_s5(data: dict) -> Path:
    """S5'te toplam kayıp neredeyse sabit; sürüm yalnızca kimin kaybolduğunu değiştirir."""
    names = ["A-S5", "B-S5", "C-S5"]
    btn = np.array([sum(r["status"] == "tx_drop" for r in data[n][0]) for n in names])
    tel = np.array([int(data[n][1].get("tel_tx_drop", 0)) for n in names])
    fig, ax = new_fig(7, 4.4)
    style(ax, "messages dropped at the 16-message limit")
    x = np.arange(len(names))
    ax.bar(x, btn, width=0.55, color=CRITICAL, edgecolor=SURFACE, linewidth=1.5, label="BTN reply dropped")
    ax.bar(x, tel, bottom=btn, width=0.55, color=SERIES[0], edgecolor=SURFACE, linewidth=1.5,
           label="TEL message dropped")
    for xi, b, t in zip(x, btn, tel):
        ax.text(xi, b + t + 0.4, f"{b + t} total\nBTN {b} · TEL {t}", ha="center", va="bottom", fontsize=9,
                color=INK2)
    ax.set_xticks(x, [LABELS[n] for n in names])
    ax.set_ylim(0, 30)
    ax.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=INK2)
    fig.suptitle("S5, 35 presses each: who pays when the TX limit is full?", x=0.01, ha="left",
                 fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return save(fig, "drops_s5.png")


def plot_tel_wait(data: dict) -> Path:
    fig, (ax1, ax2) = new_fig(10, 4.2, ncols=2, gridspec_kw={"width_ratios": [3, 2]})
    for ax, names, ymax in ((ax1, ["A-S5", "B-S5", "C-S5"], 180), (ax2, ["B-S6", "C-S6"], 30)):
        style(ax, "TEL wait: enqueue → TX start (ms)")
        x = np.arange(len(names))
        avg = [int(data[n][1]["tel_wait_avg_us"]) / 1000 for n in names]
        mx = [int(data[n][1]["tel_wait_max_us"]) / 1000 for n in names]
        ax.bar(x - 0.16, avg, width=0.3, color=SERIES[0], label="mean")
        ax.bar(x + 0.16, mx, width=0.3, color=SERIES[1], label="max")
        for xi, a, m in zip(x, avg, mx):
            ax.text(xi - 0.16, a + ymax * 0.01, f"{a:.1f}", ha="center", va="bottom", fontsize=8, color=INK2)
            ax.text(xi + 0.16, m + ymax * 0.01, f"{m:.1f}", ha="center", va="bottom", fontsize=8, color=INK2)
        ax.set_xticks(x, [LABELS[n] for n in names])
        ax.set_ylim(0, ymax)
    lengths = " · ".join(f"{n[0]} {int(data[n][1]['period_n']) * 10 / 1000:.0f} s" for n in ["A-S5", "B-S5", "C-S5"])
    ax1.set_title(f"S5 — mean depends on run length ({lengths}); compare max only", loc="left",
                  fontsize=9, color=INK2)
    ax2.set_title("S6", loc="left", fontsize=9, color=INK2)
    ax1.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=INK2)
    fig.suptitle("Telemetry cost: how long TEL messages waited in the queue (all TEL of the run)",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return save(fig, "tel_wait.png")


def main() -> None:
    PLOTS.mkdir(parents=True, exist_ok=True)
    data = {n: load(MEAS, n) for n in RUNS}
    print(f"wrote {write_summary(MEAS, data)}")
    for p in (plot_response_per_event(data), plot_stage_breakdown(data), plot_drops_s5(data),
              plot_tel_wait(data)):
        print(f"wrote {p}")

    auto = MEAS / "auto"
    if auto.is_dir():
        adata = {n: load(auto, n + "a") for n in RUNS if (auto / f"{n}a.csv").exists()}
        if adata:
            print(f"wrote {write_summary(auto, adata)}")


if __name__ == "__main__":
    main()
