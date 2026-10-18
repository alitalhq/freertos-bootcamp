"""SystemView ödevi görselleri: .SVDat izlerinden işaretli zaman çizelgeleri.

Her görsel bir buton olayını (CSV event_id) t0'dan itibaren gösterir: kesmeler,
görevlerin çalıştığı (dolu) ve CPU beklediği (Ready, taralı) aralıklar, Idle ve
uygulama olayları (BTN_*). Zamanlar iz içindeki DWT sayacından (80 MHz).

Kullanım: python sv_figures.py   ->  figures/1_cpu_bekleme.png, 2_kuyruk_bekleme.png,
                                     3_once_sonra_uart_onceligi.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from svdat import ISR_NAMES, Trace, btn_times, decode  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis" / "figures"

ROWS = ["EXTI15_10", "USART2", "SysTick", "telemetry", "button", "uart_tx", "Idle"]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLOR = {"EXTI15_10": "#d03b3b", "USART2": "#eb6834", "SysTick": "#eda100",
         "telemetry": "#1baf7a", "button": "#2a78d6", "uart_tx": "#7a5bd6", "Idle": "#b9b8b1"}
BTN_LABEL = {"BTN_ACCEPT": "t0", "BTN_TASK": "t1", "BTN_ENQUEUE": "t2", "BTN_DROP": "DROP",
             "BTN_TX_START": "t3", "BTN_TX_TC": "t4"}


def segments(tr: Trace) -> tuple[dict[str, list], dict[str, list]]:
    """(çalışma, Ready) aralıkları satır adına göre, µs."""
    run: dict[str, list] = {r: [] for r in ROWS}
    ready: dict[str, list] = {r: [] for r in ROWS}
    cur, cur_t = None, 0.0
    isr: list[tuple[str, float]] = []
    ready_t: dict[str, float] = {}

    def close(t: float) -> None:
        nonlocal cur
        if cur is not None and cur in run:
            run[cur].append((cur_t, t))
        cur = None

    for e in tr.events:
        name = tr.tasks.get(e.arg0, "?")
        if e.kind == "TASK_START_EXEC":
            close(e.t_us)
            cur, cur_t = name, e.t_us
            if name in ready_t:
                ready[name].append((ready_t.pop(name), e.t_us))
        elif e.kind == "TASK_STOP_EXEC":
            close(e.t_us)
        elif e.kind == "IDLE":
            close(e.t_us)
            cur, cur_t = "Idle", e.t_us
        elif e.kind == "TASK_START_READY":
            ready_t.setdefault(name, e.t_us)
        elif e.kind == "TASK_STOP_READY":
            ready_t.pop(name, None)
        elif e.kind == "ISR_ENTER":
            isr.append((ISR_NAMES.get(e.arg0, f"IRQ{e.arg0}"), e.t_us))
        elif e.kind in ("ISR_EXIT", "ISR_TO_SCHEDULER") and isr:
            n, t0 = isr.pop()
            if n in run:
                run[n].append((t0, e.t_us))
    return run, ready


def draw(ax, tr: Trace, event_id: int, t_from: float, t_to: float, title: str) -> dict[str, float]:
    """t0'a göre ms ekseninde [t_from, t_to] penceresini çizer; BTN zamanlarını döndürür."""
    bt = btn_times(tr, event_id)
    t0 = bt["BTN_ACCEPT"]
    run, ready = segments(tr)
    ms = lambda t: (t - t0) / 1000  # noqa: E731
    ax.set_facecolor(SURFACE)
    for y, row in enumerate(ROWS):
        bars = [(ms(a), ms(b) - ms(a)) for a, b in run[row] if ms(b) >= t_from and ms(a) <= t_to]
        if bars:
            ax.broken_barh(bars, (y - 0.32, 0.64), facecolors=COLOR[row], edgecolor="none")
        rb = [(ms(a), ms(b) - ms(a)) for a, b in ready[row] if ms(b) >= t_from and ms(a) <= t_to]
        if rb:
            ax.broken_barh(rb, (y - 0.32, 0.64), facecolors="none", edgecolor=COLOR[row], hatch="////",
                           linewidth=0.8)
    # Birbirine pencerenin %2'sinden yakın olaylar tek çizgi ve tek etiket olur.
    groups: list[list] = []
    for k, t in sorted(bt.items(), key=lambda kv: kv[1]):
        x = ms(t)
        if not t_from <= x <= t_to:
            continue
        if groups and x - groups[-1][0] < (t_to - t_from) * 0.02:
            groups[-1][1].append(BTN_LABEL[k])
        else:
            groups.append([x, [BTN_LABEL[k]]])
    for x, labels in groups:
        ax.axvline(x, color=INK, lw=0.8, ls="--", zorder=1)
        ax.text(x, -0.62, " ".join(labels), ha="center", va="bottom", fontsize=8.5, color=INK, fontweight="bold")
    ax.set_yticks(range(len(ROWS)), ROWS, fontsize=9, color=INK)
    ax.set_ylim(len(ROWS) - 0.4, -0.9)
    ax.set_xlim(t_from, t_to)
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="x", colors=INK2, labelsize=8.5)
    ax.set_xlabel("basıştan (t0) itibaren süre (ms) — SystemView izi, DWT 80 MHz", color=INK2, fontsize=8.5)
    ax.set_title(title, loc="left", fontsize=10.5, color=INK)
    return {k: ms(v) for k, v in bt.items()}


def note(ax, x0: float, x1: float, y: float, text: str, color: str = INK) -> None:
    ax.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="<->", color=color, lw=1.4))
    ax.text((x0 + x1) / 2, y - 0.18, text, ha="center", va="bottom", fontsize=9, color=color,
            bbox=dict(fc=SURFACE, ec="none", pad=1.5))


def legend(fig) -> None:
    from matplotlib.patches import Patch
    h = [Patch(fc=INK2, label="çalışıyor"), Patch(fc="none", ec=INK2, hatch="////", label="Ready: CPU bekliyor")]
    fig.legend(handles=h, loc="lower right", ncols=2, fontsize=8, frameon=False)


def caption(fig, lines: list[str]) -> None:
    fig.text(0.01, 0.012, "\n".join(lines), fontsize=9, color=INK, va="bottom", ha="left", linespacing=1.5)


EVENTS_KEY = "t0 BTN_ACCEPT · t1 BTN_TASK · t2 BTN_ENQUEUE · t3 BTN_TX_START · t4 BTN_TX_TC · DROP BTN_DROP"


def fig_cpu_wait() -> Path:
    tr = decode(ROOT / "traces" / "A-S5t2.SVDat")
    fig, ax = plt.subplots(figsize=(12, 5.6), facecolor=SURFACE)
    b = draw(ax, tr, 18, -1.5, 7.5,
             "1 · CPU beklemesi — A/S5, basış #18 (A-S5t2): ButtonTask hazır ama CPU telemetride")
    note(ax, 0, b["BTN_TASK"], 4.55, f"button Ready: {b['BTN_TASK']:.2f} ms CPU bekleme", COLOR["button"])
    caption(fig, [
        f"• Basış, telemetry 5 ms'lik işini yaparken geldi. button hazır (Ready) ama önceliği 2 < 3: "
        f"{b['BTN_TASK']:.2f} ms CPU bekledi (t1 − t0).",
        "• Bu sırada uart_tx de TC'den (≈0,8 ms) beri hazır ama öncelik 1: hat ~4,5 ms boş kaldı.",
        "• telemetry işini bitirip TEL'i kuyruğa koydu ve son boş yeri aldı; button hemen ardından "
        "BTN_DROP ile düştü (16/16).",
        EVENTS_KEY,
    ])
    legend(fig)
    fig.tight_layout(rect=(0, 0.2, 1, 1))
    return save(fig, "1_cpu_bekleme.png")


def fig_queue_wait() -> Path:
    tr = decode(ROOT / "traces" / "B-S5t2.SVDat")
    fig, ax = plt.subplots(figsize=(12, 5.6), facecolor=SURFACE)
    b = draw(ax, tr, 18, -6, 168,
             "2 · Kuyruk (UART) beklemesi — B/S5, basış #18 (B-S5t2): yanıt hazır, TEL'lerin arkasında bekliyor")
    note(ax, b["BTN_ENQUEUE"], b["BTN_TX_START"], 4.55,
         f"t3 − t2 = {b['BTN_TX_START'] - b['BTN_ENQUEUE']:.0f} ms kuyrukta", COLOR["button"])
    caption(fig, [
        f"• button öncelik 4: yanıt {b['BTN_ENQUEUE']:.1f} ms'de kuyrukta (t2). Sonra {b['BTN_TX_START'] - b['BTN_ENQUEUE']:.0f} ms "
        "önündeki TEL mesajlarının gitmesini bekledi (t3).",
        "• uart_tx (öncelik 1) her 10 ms'de bir kez, telemetry işi bitince çalışabiliyor: hat periyot başına 1 mesaj "
        "taşıyor = telemetri hızı, birikim erimiyor.",
        "• Idle satırı dolu: CPU sık sık boş. Gecikme CPU'dan değil, kuyruk sırasından ve UART görevinin geç çalışmasından.",
        EVENTS_KEY,
    ])
    legend(fig)
    fig.tight_layout(rect=(0, 0.2, 1, 1))
    return save(fig, "2_kuyruk_bekleme.png")


def fig_before_after() -> Path:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(12, 9.4), facecolor=SURFACE, sharex=True)
    tr1 = decode(ROOT / "traces" / "B-S5t3.SVDat")
    b1 = draw(a1, tr1, 18, -2, 30, "Önce · B/S5, UART görev önceliği 1 (B-S5t3, basış #18)")
    a1.text(29.6, -0.62, f"t3 {b1['BTN_TX_START']:.0f} ms'de →", ha="right", va="bottom", fontsize=8.5,
            color="#d03b3b", fontweight="bold")
    tr2 = decode(ROOT / "traces" / "B-S5tp4.SVDat")
    b2 = draw(a2, tr2, 34, -2, 30, "Sonra · aynı yük, tek değişiklik: UART görev önceliği 4 (B-S5tp4, basış #34)")
    note(a2, 0, b2["BTN_TX_TC"], 4.55, f"R = {b2['BTN_TX_TC']:.1f} ms", COLOR["button"])
    a1.set_xlabel("")
    caption(fig, [
        f"• Önce: uart_tx her TC'den sonra hazır (taralı) ama telemetry işi bitene kadar bekliyor; yanıt "
        f"{b1['BTN_TX_START']:.0f} ms sonra gönderilmeye başlıyor, R = {b1['BTN_TX_TC']:.0f} ms.",
        f"• Sonra: uart_tx telemetry'yi birkaç µs kesip sıradaki mesajı hemen başlatıyor; kuyruk birikmiyor, "
        f"R = {b2['BTN_TX_TC']:.1f} ms.",
        "• Bedel: telemetry işi kesildiği için uzuyor (ortalama 5,20 → 5,28 ms); TEL kaybı 21 → 0.",
        EVENTS_KEY,
    ])
    legend(fig)
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    return save(fig, "3_once_sonra_uart_onceligi.png")


def save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    fig.savefig(p, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return p


if __name__ == "__main__":
    for p in (fig_cpu_wait(), fig_queue_wait(), fig_before_after()):
        print(f"wrote {p}")
