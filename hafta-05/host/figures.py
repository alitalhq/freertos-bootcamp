"""Ham kayıtlardan (evidence/*/raw.jsonl, result.json) grafik ve özet tablo üretir.

python3 host/figures.py   ->  evidence/figures/*.png ve evidence/summary.md
Bütün grafikler kart ölçümüdür (TIM2 1 MHz); tarayıcı demosu kullanılmadı.
"""
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

EV = pathlib.Path(__file__).resolve().parent.parent / "evidence"
OUT = EV / "figures"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 130})


def raw(name, kind):
    p = EV / name / "raw.jsonl"
    return [d for d in map(json.loads, p.read_text().splitlines()) if d.get("t") == kind] if p.exists() else []


def result(name):
    p = EV / name / "result.json"
    return json.loads(p.read_text()) if p.exists() else None


def fig_t1():
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for i, trig in enumerate((1, 8, 32)):
        d = sorted(r["d"] / 1000 for r in raw(f"T1/trigger{trig}", "R"))
        if d:
            ax.plot(d, [k / len(d) for k in range(1, len(d) + 1)], color=SERIES[i], lw=2, label=f"trigger {trig} (n={len(d)})")
    ax.axvline(50, color=MUTED, lw=1, ls="--")
    ax.text(49, 0.05, "hedef p99 ≤ 50 ms", ha="right", color=MUTED)
    ax.set_xscale("log")
    ax.set_xlabel("doğrulama → iş tamamlandı (ms, log ölçek)")
    ax.set_ylabel("birikimli oran")
    ax.set_title("T1 · temiz trafik 200 DATA/s, kart ölçümü", loc="left", color=INK)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "t1_latency.png")


def fig_t4():
    r = result("T4")
    if not r:
        return
    occ = [n["c"] for n in r["stall_notes"]]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.bar(range(1, len(occ) + 1), occ, color=SERIES[0], width=0.7, label="ölçülen doluluk (80 ms sonunda)")
    ax.axhline(r["occupancy_estimate_B"], color=SERIES[1], lw=2, label=f"tahmin {r['occupancy_estimate_B']:.0f} B")
    ax.axhline(1024, color=MUTED, lw=1, ls="--")
    ax.text(len(occ) + 0.4, 1024, "kapasite 1024 B", va="bottom", ha="right", color=MUTED)
    ax.set_ylim(0, 1100)
    ax.set_xlabel("STALL_NEXT tekrarı")
    ax.set_ylabel("rxStream doluluğu (B)")
    ax.set_title("T4 · parser 80 ms durunca RX doluluğu", loc="left", color=INK)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "t4_occupancy.png")


def fig_t7():
    uart = [d["b"] for d in raw("T7", "P")]
    btn = [d["b"] for d in raw("T7B", "B")]
    if not uart:
        return
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.scatter(uart, [1] * len(uart), s=40, color=SERIES[0], alpha=0.6, label=f"UART STOP (n={len(uart)})")
    if btn:
        ax.scatter(btn, [0] * len(btn), s=40, color=SERIES[1], alpha=0.8, label=f"buton STOP (n={len(btn)})")
    ax.set_yticks([0, 1], ["buton", "UART"])
    ax.set_ylim(-0.6, 1.6)
    ax.set_xlabel("t0 → ControlTask STOPPED uyguladı (µs)")
    ax.set_title(f"T7 · STOP gecikmesi; en çok {max(uart + btn)} µs, hedef 50 000 µs", loc="left", color=INK)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    fig.savefig(OUT / "t7_stop.png")


def fig_t9():
    r = result("T9")
    if not r:
        return
    lv = r["levels"]
    x = list(range(len(lv)))
    fig, ax = plt.subplots(figsize=(7, 3.4))
    w = 0.38
    ax.bar([i - w / 2 for i in x], [l["validate_to_txstream"]["p50_ms"] for l in lv], w, color=SERIES[0], label="p50")
    ax.bar([i + w / 2 for i in x], [l["validate_to_txstream"]["p99_ms"] for l in lv], w, color=SERIES[1], label="p99")
    for i, l in enumerate(lv):
        ax.text(i + w / 2, l["validate_to_txstream"]["p99_ms"], f"{l['validate_to_txstream']['p99_ms']:.1f}",
                ha="center", va="bottom", color=INK, fontsize=9)
    ax.set_xticks(x, [f"{l['log_rate_Bps'] // 1000} kB/s\n(düşen {l['log_dropped']})" for l in lv])
    ax.set_xlabel("istenen log yükü (aynı UART; 230400 baud ≈ 23 kB/s)")
    ax.set_ylabel("doğrulama → txStream (ms)")
    ax.set_title("T9 · log yükü altında cevap gecikmesi, 50 DATA/s", loc="left", color=INK)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "t9_log_load.png")


def summary():
    rows = ["| Test | Sonuç | Ana sayı |", "|---|---|---|"]
    for trig in (1, 8, 32):
        r = result(f"T1/trigger{trig}")
        if r:
            s = r["responses"]["validate_to_done"]
            rows.append(f"| T1 trigger {trig} | {'PASS' if r['pass'] else 'FAIL'} | {r['responses']['completed_unique']}/"
                        f"{r['responses']['sent']} tamam, {r['host_rate']}/s, p50 {s['p50_ms']} / p99 {s['p99_ms']} / "
                        f"maks {s['max_ms']} ms |")
    simple = {
        "T2": lambda r: f"{r['responses']['completed_unique']}/1000 tekil, {r['writes']} parça yazma",
        "T3": lambda r: ", ".join(f"{k}: {v['recovered_1st']}+{v['recovered_2nd']}/{v['n']}" for k, v in r["per_kind"].items())
        + f"; bozuk işlenen {len(r['bad_seq_processed'])}",
        "T4": lambda r: f"doluluk maks {r['occupancy_after_stall_B']['max']} B (tahmin {r['occupancy_estimate_B']:.0f}), "
        f"ret {r['delta']['rej']}, eksik {r['responses']['missing']}",
        "T5": lambda r: f"ret toplam {r['delta_total']['rej']} B, temiz akış eksik {len(r['clean_missing'])}",
        "T6": lambda r: ", ".join(f"{k} {'✓' if v else '✗'}" for k, v in r["parts_pass"].items()),
        "T7": lambda r: f"UART STOP n={r['uart_stop_latency_board']['n']} maks {r['uart_stop_latency_board']['max_ms']} ms, "
        f"durmuşken başlayan iş {r['epoch_check']['started_while_stopped']}",
        "T7B": lambda r: f"buton n={r['button_stop_latency_board']['n']} maks {r['button_stop_latency_board']['max_ms']} ms",
        "T8": lambda r: f"port {sum(x['clean_20_ok'] for x in r['port_reopen'])}/10, reset "
        f"{sum(bool(x['clean_20_ok']) for x in r['board_reset'])}/5",
        "T9": lambda r: ", ".join(f"{l['log_rate_Bps'] // 1000}k: p99 {l['validate_to_txstream']['p99_ms']} ms" for l in r["levels"]),
    }
    for name, f in simple.items():
        r = result(name)
        if r:
            rows.append(f"| {name} | {'PASS' if r['pass'] else 'FAIL'} | {f(r)} |")
    (EV / "summary.md").write_text("\n".join(rows) + "\n")
    print("\n".join(rows))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (fig_t1, fig_t4, fig_t7, fig_t9):
        f()
    summary()
