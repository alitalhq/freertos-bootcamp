"""RTOS Lab: yük altında buton yanıtı deney ve analiz arayüzü (PySide6).

Düzen: solda sabit kontrol çubuğu (bağlantı, deney ayarları, canlı durum,
deneme listesi), sağda kaydırılan tek bir rapor sayfası (bulgu cümlesi,
olay başına R, aşamalar, geç kalan olayın dökümü, karşılaştırma, kayıtlar).
Arayüz metinleri Türkçe; teknik terimler (UART, TC, txQ, ButtonTask…) aynen.

- Açılışta resmi S0–S5 ölçümleri ve S5 çözüm denemeleri gösterilir.
- Lab firmware'i (APP_LAB_MODE=1) yüklü karta bağlanıp kendi deneyini
  koşturabilirsin: telemetri periyodu, CPU yükü, çözüm yolu, elle/otomatik basış.

Kullanım: python lab_app.py
"""
from __future__ import annotations

import csv
import os
import queue
import sys
import time
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QFont  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QButtonGroup, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QGroupBox, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QTabWidget, QTableWidget,
    QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

import matplotlib  # noqa: E402

matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

import serial  # noqa: E402

from labctl import FIX_BITS, FIX_PRESETS, PRESETS, LabConfig, fix_label  # noqa: E402
from monitor import SerialReader, Session, list_ports  # noqa: E402
from protocol import CSV_HEADER  # noqa: E402
from runs import (  # noqa: E402
    DEADLINE_MS, GROUP_FILES, GROUP_LAB, GROUP_SESSION, LINE_MS, STAGES, Run, default_runs, from_export,
    load_csv, load_raw,
)

WARMUP_S = 5.0
STATUS_TR = {"ok": "ok", "tx_drop": "kayıp (txQ dolu)", "btn_drop": "kayıp (buttonQ dolu)",
             "tx_error": "UART hatası", "timeout": "zaman aşımı", "pending": "bekliyor"}


def num(v: float | None, d: int = 2) -> str:
    """Türkçe ondalık: 5,56"""
    return "–" if v is None else f"{v:.{d}f}".replace(".", ",")


# ---- Tema ---------------------------------------------------------------------
# Veri renkleri dataviz referans paletinden (her iki modda doğrulayıcıdan geçti).
# Açık modda aqua/sarı 3:1'in altında: rahatlatma = değer etiketleri + kayıt tablosu.

@dataclass(frozen=True)
class Theme:
    name: str
    page: str
    surface: str
    raised: str
    ink: str
    ink2: str
    muted: str
    grid: str
    accent: str
    accent_ink: str
    ok: str
    critical: str
    stages: tuple


LIGHT = Theme("light", page="#f3f2ef", surface="#fcfcfb", raised="#ffffff", ink="#0b0b0b", ink2="#52514e",
              muted="#8a897f", grid="#e4e3df", accent="#4a3aa7", accent_ink="#ffffff", ok="#2a78d6",
              critical="#d03b3b", stages=("#2a78d6", "#eb6834", "#1baf7a", "#eda100"))
DARK = Theme("dark", page="#121211", surface="#1a1a19", raised="#232321", ink="#ffffff", ink2="#c3c2b7",
             muted="#8a897f", grid="#383835", accent="#9085e9", accent_ink="#121211", ok="#3987e5",
             critical="#d03b3b", stages=("#3987e5", "#d95926", "#199e70", "#c98500"))
T = DARK   # varsayılan: koyu tema


def stage_color(key: str) -> str:
    return T.stages[[k for k, *_ in STAGES].index(key)]


def qss(t: Theme) -> str:
    return f"""
* {{ font-family: 'Helvetica Neue', Arial; font-size: 13px; color: {t.ink}; }}
QMainWindow, QScrollArea, QWidget#page {{ background: {t.page}; }}
QWidget#sidebar {{ background: {t.surface}; border-right: 1px solid {t.grid}; }}
QLabel, QRadioButton {{ background: transparent; }}
QLabel#brand {{ font-size: 20px; font-weight: 700; }}
QLabel#section {{ color: {t.muted}; font-size: 11px; font-weight: 700; letter-spacing: 1px; margin-top: 10px; }}
QLabel#muted {{ color: {t.ink2}; }}
QLabel#small {{ color: {t.ink2}; font-size: 11px; }}
QLabel#warn {{ color: {t.critical}; font-size: 11px; }}
QLabel#title {{ font-size: 24px; font-weight: 700; }}
QLabel#headline {{ font-size: 16px; }}
QLabel#h2 {{ font-size: 15px; font-weight: 700; margin-top: 8px; }}
QLabel#metrics {{ font-size: 14px; color: {t.ink2}; }}
QLabel#chip {{ border: 1px solid {t.grid}; border-radius: 10px; padding: 2px 10px; color: {t.ink2}; font-size: 11px; }}
QFrame#rule {{ background: {t.grid}; max-height: 1px; min-height: 1px; border: 0; }}
QPushButton {{ background: {t.raised}; border: 1px solid {t.grid}; border-radius: 7px; padding: 6px 10px; }}
QPushButton:hover {{ border-color: {t.muted}; }}
QPushButton:disabled {{ color: {t.muted}; }}
QPushButton#run {{ background: {t.accent}; color: {t.accent_ink}; border: 0; font-weight: 700; padding: 9px; }}
QPushButton#run:disabled {{ background: {t.grid}; color: {t.muted}; }}
QPushButton#link {{ background: transparent; border: 0; color: {t.accent}; padding: 2px; }}
QComboBox, QSpinBox {{ background: {t.raised}; border: 1px solid {t.grid}; border-radius: 7px; padding: 4px 8px; }}
QComboBox QAbstractItemView {{ background: {t.raised}; selection-background-color: {t.grid}; }}
QListWidget {{ background: {t.surface}; border: 0; outline: 0; }}
QListWidget::item {{ padding: 4px 2px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {t.grid}; color: {t.ink}; }}
QRadioButton::indicator {{ width: 12px; height: 12px; border-radius: 7px; border: 1px solid {t.muted};
    background: {t.raised}; }}
QRadioButton::indicator:checked {{ background: {t.accent}; border: 1px solid {t.accent}; }}
QTableWidget, QTextBrowser {{ background: {t.surface}; border: 1px solid {t.grid}; border-radius: 8px;
    gridline-color: {t.grid}; }}
QHeaderView::section {{ background: {t.raised}; color: {t.ink2}; border: 0; border-bottom: 1px solid {t.grid};
    padding: 4px; }}
QTableWidget::item:selected {{ background: {t.grid}; color: {t.ink}; }}
QTableCornerButton::section {{ background: {t.raised}; border: 0; }}
QHeaderView {{ background: {t.surface}; }}
QProgressBar {{ background: {t.grid}; border: 0; border-radius: 4px; max-height: 8px; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
QTabWidget::pane {{ border: 0; border-top: 1px solid {t.grid}; background: {t.page}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {t.ink2}; padding: 9px 16px; margin-right: 4px;
    border: 0; border-bottom: 2px solid transparent; font-size: 13px; }}
QTabBar::tab:selected {{ color: {t.ink}; border-bottom: 2px solid {t.accent}; font-weight: 700; }}
QTabBar::tab:hover {{ color: {t.ink}; }}
QGroupBox {{ background: {t.surface}; border: 1px solid {t.grid}; border-radius: 10px; margin-top: 18px;
    padding: 14px 12px 10px 12px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {t.ink2}; }}
QLabel#phase {{ font-size: 20px; font-weight: 700; }}
QLabel#press {{ font-size: 16px; font-weight: 700; color: {t.accent}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {t.grid}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""


def label(text: str, obj: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def rule() -> QFrame:
    f = QFrame()
    f.setObjectName("rule")
    return f


# ---- Grafikler ------------------------------------------------------------------

TR_TICKS = FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))


class Chart(FigureCanvasQTAgg):
    def __init__(self, w: float, h: float):
        self.fig = Figure(figsize=(w, h))
        super().__init__(self.fig)
        self.setMinimumHeight(int(h * 80))
        self.setMinimumWidth(320)          # figsize genişliği alanı taşırmasın
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)   # genişlik alana uyar
        self._hover_pts: list[tuple[float, float, str]] = []
        self._tip = None
        self.mpl_connect("motion_notify_event", self._on_move)

    def begin(self):
        self.fig.clear()
        self.fig.set_facecolor(T.surface)
        self._hover_pts, self._tip = [], None

    def style_ax(self, ax, ylabel="", xlabel="", grid="y"):
        ax.set_facecolor(T.surface)
        if grid:
            ax.grid(axis=grid, color=T.grid, linewidth=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(T.grid)
        ax.tick_params(colors=T.ink2, labelsize=9)
        ax.set_ylabel(ylabel, color=T.ink2, fontsize=9)
        ax.set_xlabel(xlabel, color=T.ink2, fontsize=9)

    def set_hover(self, ax, pts):
        """pts: (x, y, metin). İmleç bir noktaya 12 px yakınsa ipucu gösterir."""
        self._hover_ax, self._hover_pts = ax, pts
        self._tip = ax.annotate("", xy=(0, 0), xytext=(12, 12), textcoords="offset points", fontsize=9,
                                color=T.ink, bbox=dict(boxstyle="round,pad=0.45", fc=T.raised, ec=T.muted, lw=0.8))
        self._tip.set_visible(False)

    def _on_move(self, ev):
        if not self._hover_pts or self._tip is None:
            return
        if ev.inaxes is not self._hover_ax:
            if self._tip.get_visible():
                self._tip.set_visible(False)
                self.draw_idle()
            return
        tr = self._hover_ax.transData
        best, bd = None, 12.0 ** 2
        for x, y, text in self._hover_pts:
            px, py = tr.transform((x, y))
            d = (px - ev.x) ** 2 + (py - ev.y) ** 2
            if d < bd:
                best, bd = (x, y, text), d
        if best:
            right = ev.x > self.width() * 0.6
            self._tip.xy = best[:2]
            self._tip.set_text(best[2])
            self._tip.set_position((-12 if right else 12, 12))
            self._tip.set_ha("right" if right else "left")
            self._tip.set_visible(True)
        else:
            self._tip.set_visible(False)
        self.draw_idle()


def event_tip(e) -> str:
    s = e.stages_ms
    r = "yanıt yok" if e.r_ms is None else f"R = {num(e.r_ms)} ms"
    return (f"olay {e.rec.event_id} · {STATUS_TR.get(e.rec.status, e.rec.status)}\n{r}\n"
            f"görev {num(s['task'])} · TX öncesi {num(s['pretx'])} · hat {num(s['line'])}")


class ResponseChart(Chart):
    def show(self, run: Run | None):
        self.begin()
        ax = self.fig.add_subplot(111)
        self.style_ax(ax, "R = t4 − t0 (ms)", "olay no")
        if run is None or not run.events:
            self.draw_idle()
            return
        ok = run.ok_events
        top = max([DEADLINE_MS * 1.3] + [e.r_ms * 1.12 for e in ok])
        on = [(e.rec.event_id, e.r_ms) for e in ok if e.r_ms <= DEADLINE_MS]
        late = [(e.rec.event_id, e.r_ms) for e in ok if e.r_ms > DEADLINE_MS]
        lost = [e.rec.event_id for e in run.events if not e.ok]
        ax.axhspan(DEADLINE_MS, top, color=T.critical, alpha=0.06, lw=0)
        ax.axhline(DEADLINE_MS, color=T.critical, ls="--", lw=1)
        if ok:
            ax.plot([e.rec.event_id for e in ok], [e.r_ms for e in ok], color=T.grid, lw=1.2, zorder=1)
        if on:
            ax.scatter(*zip(*on), s=30, color=T.ok, edgecolor=T.surface, lw=1.2, zorder=3, label="20 ms tutuldu")
        if late:
            ax.scatter(*zip(*late), s=34, marker="s", color=T.critical, edgecolor=T.surface, lw=1.2, zorder=3,
                       label="20 ms aşıldı")
        if lost:
            ax.scatter(lost, [top * 0.035] * len(lost), marker="x", s=38, color=T.critical, lw=1.8, zorder=3,
                       label=f"yanıt yok ×{len(lost)}")
        ax.text(0.995, DEADLINE_MS / top, "deadline 20 ms", transform=ax.transAxes, ha="right", va="bottom",
                fontsize=8, color=T.ink2)
        ax.set_ylim(0, top)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.yaxis.set_major_formatter(TR_TICKS)
        ax.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=T.ink2, ncols=3)
        self.set_hover(ax, [(e.rec.event_id, e.r_ms if e.ok else top * 0.035, event_tip(e)) for e in run.events
                            if e.ok or e.rec.status != "ok"])
        self.fig.tight_layout()
        self.draw_idle()


class StageChart(Chart):
    """Aşama ortalamaları: yatay çubuk, değer etiketli."""

    def show(self, run: Run | None):
        self.begin()
        ax = self.fig.add_subplot(111)
        self.style_ax(ax, grid="x")
        if run is None or not run.ok_events:
            self.draw_idle()
            return
        means = run.stage_means()
        keys = [k for k, *_ in STAGES][::-1]
        vals = [means[k] for k in keys]
        bars = ax.barh([lbl for _, lbl, *_ in STAGES][::-1], vals, color=[stage_color(k) for k in keys],
                       height=0.56, edgecolor=T.surface, lw=2)
        vmax = max(vals + [1e-3])
        total = sum(vals) or 1
        for b, v in zip(bars, vals):
            ax.text(b.get_width() + vmax * 0.02, b.get_y() + b.get_height() / 2,
                    f"{num(v)} ms  (%{v / total * 100:.0f})", va="center", fontsize=9, color=T.ink)
        ax.set_xlim(0, vmax * 1.38)
        ax.xaxis.set_major_formatter(TR_TICKS)
        ax.tick_params(axis="y", colors=T.ink, labelsize=9)
        ax.set_xlabel(f"yanıtı gelen {len(run.ok_events)} olayın ortalaması (ms)", color=T.ink2, fontsize=9)
        self.fig.tight_layout()
        self.draw_idle()


class BudgetChart(Chart):
    """Tek olayın dökümü: aşamalar t0'dan başlayarak yan yana, deadline ve pay."""

    def show(self, ev):
        self.begin()
        ax = self.fig.add_subplot(111)
        self.style_ax(ax, xlabel="buton ISR'ından (t0) itibaren geçen süre (ms)", grid="x")
        ax.set_yticks([])
        if ev is None:
            self.draw_idle()
            return
        left = 0.0
        for key, lbl, *_ in STAGES:
            v = ev.stages_ms[key]
            if v is None:
                continue
            ax.barh([0], [v], left=left, height=0.46, color=stage_color(key), edgecolor=T.surface, lw=2,
                    label=f"{lbl}: {num(v)} ms")
            left += v
        ax.axvline(DEADLINE_MS, color=T.critical, ls="--", lw=1.2)
        ax.text(DEADLINE_MS, 0.36, " 20 ms", color=T.ink2, fontsize=8, va="bottom")
        if ev.r_ms is not None:
            margin = DEADLINE_MS - ev.r_ms
            col = T.ok if margin >= 0 else T.critical
            ax.annotate("", xy=(DEADLINE_MS, -0.36), xytext=(left, -0.36),
                        arrowprops=dict(arrowstyle="<->", color=col, lw=1.3))
            ax.text((DEADLINE_MS + left) / 2, -0.42, f"pay {num(margin)} ms", color=col, fontsize=9,
                    ha="center", va="top")
        else:
            ax.text(left, 0, f"  ✕ yanıt yok ({STATUS_TR.get(ev.rec.status, ev.rec.status)})", color=T.critical,
                    va="center", fontsize=10)
        ax.set_xlim(0, max(DEADLINE_MS, left) * 1.1)
        ax.set_ylim(-0.75, 0.6)
        ax.xaxis.set_major_formatter(TR_TICKS)
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncols=2, fontsize=8, frameon=False,
                  labelcolor=T.ink2)
        self.fig.tight_layout()
        self.draw_idle()


SHORT_FIX = {0: "standart", 4: "naif", 1: "kök neden", 5: "optimal"}


def short_label(run: Run) -> str:
    name = run.cfg.get("scenario", run.label)
    if run.official:
        return f"{name}\nelle"
    return f"{name}\n{SHORT_FIX.get(run.fix, f'F{run.fix}')}"


class CompareChart(Chart):
    """Aşama ortalamaları yığılmış (doğrusal). Eşiği çok aşanlar kırpılır ve
    değeri yazılır; log ölçek yığını çarpıtacağı için kullanılmaz."""

    def show(self, runs: list[Run]):
        self.begin()
        ax = self.fig.add_subplot(111)
        self.style_ax(ax, "aşama ortalaması (ms)")
        if not runs:
            ax.text(0.5, 0.5, "Karşılaştırmak için soldaki listeden deneme işaretle", transform=ax.transAxes,
                    ha="center", color=T.ink2)
            self.draw_idle()
            return
        x = list(range(len(runs)))
        totals = [sum(r.stage_means().values()) for r in runs]
        maxes = [r.stat()["max"] or 0 for r in runs]
        vals_all = maxes + totals
        cap = DEADLINE_MS * 1.6 if any(v > DEADLINE_MS * 2 for v in vals_all) else max(vals_all + [DEADLINE_MS]) * 1.2
        bottoms = [0.0] * len(runs)
        for key, lbl, *_ in STAGES:
            vals = [r.stage_means()[key] for r in runs]
            ax.bar(x, vals, bottom=bottoms, width=0.6, color=stage_color(key), edgecolor=T.surface, lw=2,
                   label=lbl)
            bottoms = [b + v for b, v in zip(bottoms, vals)]
        ax.scatter(x, [min(m, cap * 0.985) for m in maxes], marker="_", s=300, color=T.ink, lw=2, zorder=4,
                   label="en büyük R")
        ax.axhline(DEADLINE_MS, color=T.critical, ls="--", lw=1)
        for xi, tot, mx, r in zip(x, totals, maxes, runs):
            st = r.stat()
            bad = st["late"] or st["lost"]
            clipped = tot > cap
            txt = (f"▲ ort. {tot:.0f} ms\n" if clipped else f"{num(tot, 1)}\n") + \
                  f"{st['late']} aşan · {st['lost']} kayıp"
            ax.text(xi, cap * 0.9 if clipped else max(tot, mx) + cap * 0.02, txt, ha="center",
                    va="top" if clipped else "bottom", fontsize=8, color=T.critical if bad else T.ink2,
                    bbox=dict(fc=T.surface, ec="none", pad=1) if clipped else None)
        ax.set_ylim(0, cap)
        ax.yaxis.set_major_formatter(TR_TICKS)
        ax.set_xticks(x, [short_label(r) for r in runs], fontsize=8, color=T.ink2)
        self.fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncols=3, fontsize=8, frameon=False,
                        labelcolor=T.ink2)
        self.fig.tight_layout(rect=(0, 0.14, 1, 1))
        self.draw_idle()


# ---- Bulgu cümlesi --------------------------------------------------------------

def headline(run: Run) -> str:
    """Rapor sayfasının en üstündeki tek cümlelik sonuç."""
    st, means = run.stat(), run.stage_means()
    total = sum(means.values()) or 1
    dom_key = max(means, key=means.get)
    dom_label = {"task": "görev beklemesine", "prep": "yanıt hazırlamaya", "pretx": "TX öncesi beklemeye",
                 "line": "UART gönderimine"}[dom_key]
    share = means[dom_key] / total * 100
    if st["ok"] == 0:
        return "Bu denemede PC'ye hiç yanıt ulaşmadı."
    if st["late"] == 0 and st["lost"] == 0:
        s = (f"{st['ok']} yanıtın hepsi 20 ms deadline'ını tuttu: en kötü durum {num(st['max'], 1)} ms, "
             f"{num(DEADLINE_MS - st['max'], 1)} ms pay kaldı.")
    else:
        s = f"{st['ok']} yanıttan {st['late']} tanesi 20 ms'yi aştı"
        s += f", {st['lost']} yanıt kayboldu" if st["lost"] else ""
        s += f" (en kötü {st['max']:.0f} ms)."
    s += f" Sürenin çoğu {dom_label} gidiyor (%{share:.0f})."
    if run.uart_starved():
        s += " Öncelik 1'deki UART görevi CPU işi yüzünden aç kalıyor, bu yüzden kuyrukta birikim oluşuyor."
    elif dom_key == "line":
        s += " Bu, yanıtın kendi 5,56 ms'lik hat süresi; önünde bekleyen bir şey yok."
    return s


GUIDE = """
<p><b>R = t4 − t0</b>: buton ISR'ından (t0) yanıtın UART gönderim-tamamlandı (TC) kesmesine (t4) kadar geçen
süre; kartın 1 µs'lik sayacıyla ölçülür, PC saati hiç kullanılmaz. Kaybolan bir yanıt hiçbir zaman
"tutuldu" sayılmaz.</p>
<p><b>Aşamalar:</b> görev bekleme (ISR → ButtonTask olayı alır; öncelik 3'teki iş çalışırken büyür) ·
yanıt hazırlama (~25 µs) · TX öncesi bekleme (txQ + hattın dolu olması + UART görevinin CPU alması) ·
UART + TC (hatta 5,56 ms).</p>
<p><b>S5 neden başarısız:</b> her 10 ms'lik periyot ~5 ms'lik öncelik 3 işiyle başlıyor. Öncelik 1'deki UART
görevi yalnızca kalan ~4,95 ms'de mesaj başlatabiliyor; mesaj ise 5,56 ms sürüyor. Hat periyot başına en fazla
bir mesaj taşıyor, bu da telemetri hızına eşit. Her yanıt hiç erimeyen bir mesaj ekliyor.</p>
<p><b>Çözümler</b> (lab firmware'i, her biri kendi <code>#ifdef</code> bloğunda): naif ButtonTask önceliği
(tek başına işe yaramaz: nedeni başka yerde) · <b>kök neden: UART görevinin önceliği</b> · <b>optimal: UART ve
Button görevleri CPU işinin üstünde</b>.</p>
<p><b>CPU işini kesmek hata mı?</b> Öncelik "ne kadar önemli"ye değil "ne kadar acil ve kısa"ya göre verilir.
Üste alınan görevler mesaj/basış başına yalnızca onlarca µs sürer ve sınırlıdır (basış en fazla ~33/s, mesaj
~180/s); CPU işi periyotta ~36 µs uzar ve yine 10 ms'ye rahat sığar. Üstelik UART artık aç kalmadığı için
telemetri kaybı 9'dan 0'a iner.</p>
<p><b>Kendi deneyin:</b> karta bir kez lab derlemesini yükle (<code>APP_LAB_MODE 1</code>), bağlan, ayarları seç ve
Deneyi başlat'a bas. Kart bu ayarlarla yeniden başlar, 5 s ısınır, basışları toplar ve kayıtları gönderir.
Otomatik basış EXTI13'ü yazılımla tetikler (aynı ISR ve t0 yolu); elle basışta LD2 yanınca B1'e sen basarsın.</p>
"""


# ---- Pencere ----------------------------------------------------------------------

def scroll_page(inner: QWidget) -> QScrollArea:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    inner.setObjectName("page")
    inner.setAttribute(Qt.WA_StyledBackground, True)
    sc.setWidget(inner)
    return sc


class LabWindow(QMainWindow):
    """Solda deneme listesi; sağda seçili denemenin başlığı ve tek işli sekmeler."""

    TAB_SUMMARY, TAB_WHY, TAB_COMPARE, TAB_RECORDS, TAB_RUN, TAB_GUIDE = range(6)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTOS Lab")
        self.resize(1400, 900)
        self.runs: list[Run] = default_runs()
        self.q: queue.Queue = queue.Queue()
        self.reader: SerialReader | None = None
        self.sess = Session()
        self.raw = bytearray()
        self.phase, self.phase_t = "IDLE", 0.0
        self.run_counter = 0
        self.pending_cfg: LabConfig | None = None
        self.flash_until = 0.0
        self.current_key: str | None = None
        s5 = next((r for r in self.runs if r.official and r.cfg.get("scenario") == "S5"), None)
        self.compare_keys = {r.key for r in self.runs if r is s5 or r.group == GROUP_LAB}
        self._events: list = []

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_sidebar())
        h.addWidget(self._build_main(), 1)
        self.setCentralWidget(root)

        self._refresh_ports()
        self._fill_run_list(select=s5.key if s5 else None)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(50)

    # ---- sol: deneme listesi -----------------------------------------------
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setFixedWidth(290)
        v = QVBoxLayout(side)
        v.setContentsMargins(16, 18, 16, 14)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(label("RTOS Lab", "brand"))
        top.addStretch(1)
        self.theme_btn = QPushButton("Açık tema")
        self.theme_btn.setObjectName("link")
        self.theme_btn.clicked.connect(self._toggle_theme)
        top.addWidget(self.theme_btn)
        v.addLayout(top)
        v.addWidget(label("yük altında buton yanıtı · NUCLEO-L476RG", "small"))
        v.addWidget(label("DENEMELER", "section"))
        v.addWidget(label("İncelemek için bir denemeye tıkla. Mavi nokta: tüm deadline'lar tutuldu, "
                          "kırmızı: aşan ya da kaybolan yanıt var.", "small", wrap=True))
        self.run_list = QListWidget()
        self.run_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.run_list.setTextElideMode(Qt.ElideRight)
        self.run_list.itemClicked.connect(self._run_clicked)
        v.addWidget(self.run_list, 1)
        row = QHBoxLayout()
        for text, fn in (("Aç…", self._open_file), ("CSV kaydet", self._save_csv), ("Ham kaydet", self._save_raw)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        v.addLayout(row)
        return side

    # ---- sağ: başlık + sekmeler ---------------------------------------------
    def _build_main(self) -> QWidget:
        w = QWidget()
        w.setObjectName("page")
        w.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(w)
        v.setContentsMargins(28, 18, 28, 10)
        v.setSpacing(6)
        chips = QHBoxLayout()
        self.chip_group, self.chip_press, self.chip_fix = label("", "chip"), label("", "chip"), label("", "chip")
        for c in (self.chip_group, self.chip_press, self.chip_fix):
            chips.addWidget(c)
        chips.addStretch(1)
        v.addLayout(chips)
        self.title = label("", "title")
        self.conditions = label("", "muted")
        self.metrics = label("", "metrics")
        self.metrics.setTextFormat(Qt.RichText)
        v.addWidget(self.title)
        v.addWidget(self.conditions)
        v.addWidget(self.metrics)
        v.addSpacing(6)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_summary(), "Özet")
        self.tabs.addTab(self._tab_why(), "Neden geç kaldı?")
        self.tabs.addTab(self._tab_compare(), "Karşılaştır")
        self.tabs.addTab(self._tab_records(), "Kayıtlar")
        self.tabs.addTab(self._tab_run(), "Yeni deney")
        guide = QTextBrowser()
        guide.setHtml(GUIDE)
        self.tabs.addTab(guide, "Rehber")
        v.addWidget(self.tabs, 1)
        return w

    def _tab_summary(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 14, 8, 8)
        v.setSpacing(10)
        self.headline = label("", "headline", wrap=True)
        v.addWidget(self.headline)
        v.addWidget(label("Olay başına yanıt süresi", "h2"))
        v.addWidget(label("Her nokta bir buton basışı. Kareler deadline'ı aştı, ✕ hiç yanıt almadı. "
                          "Bir noktanın üzerine gelince aşamaları görünür.", "muted", wrap=True))
        self.resp_chart = ResponseChart(9, 3.2)
        v.addWidget(self.resp_chart)
        v.addWidget(label("Zaman nereye gidiyor?", "h2"))
        row = QHBoxLayout()
        self.stage_chart = StageChart(5.2, 2.5)
        self.diag = QTextBrowser()
        self.diag.setMinimumHeight(200)
        row.addWidget(self.stage_chart, 5)
        row.addWidget(self.diag, 4)
        v.addLayout(row)
        v.addStretch(1)
        return scroll_page(page)

    def _tab_why(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 14, 8, 8)
        left = QVBoxLayout()
        left.addWidget(label("Olaylar", "h2"))
        left.addWidget(label("Aşan ve kaybolanlar üstte", "small"))
        self.event_list = QListWidget()
        self.event_list.setFixedWidth(260)
        self.event_list.currentRowChanged.connect(self._show_event)
        left.addWidget(self.event_list, 1)
        h.addLayout(left)
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(label("Seçili olayın süresi aşamalara bölünmüş hali", "h2"))
        right.addWidget(label("R = görev bekleme + yanıt hazırlama + TX öncesi bekleme + UART. Kırmızı kesik çizgi "
                              "20 ms deadline; ok ise kalan pay.", "muted", wrap=True))
        self.budget_chart = BudgetChart(9, 2.0)
        right.addWidget(self.budget_chart)
        right.addWidget(label("Neden?", "h2"))
        self.cause = label("", "", wrap=True)
        self.cause.setTextFormat(Qt.RichText)
        right.addWidget(self.cause)
        right.addStretch(1)
        h.addSpacing(16)
        h.addLayout(right, 1)
        return scroll_page(page)

    def _tab_compare(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 14, 8, 8)
        left = QVBoxLayout()
        left.addWidget(label("Hangi denemeler?", "h2"))
        left.addWidget(label("Karşılaştırmak istediklerini işaretle", "small"))
        self.cmp_list = QListWidget()
        self.cmp_list.setFixedWidth(260)
        self.cmp_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cmp_list.itemChanged.connect(self._cmp_checked)
        left.addWidget(self.cmp_list, 1)
        h.addLayout(left)
        right = QVBoxLayout()
        right.addWidget(label("Çubuklar aşama ortalamalarını üst üste koyar, kısa çizgi en büyük R'dir. "
                              "Deadline'ı çok aşanlar kırpılır ve değeri üstüne yazılır.", "muted", wrap=True))
        self.cmp_chart = CompareChart(9, 3.6)
        right.addWidget(self.cmp_chart)
        self.cmp_table = QTableWidget()
        self.cmp_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cmp_table.setMinimumHeight(220)
        self.cmp_table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        right.addWidget(self.cmp_table, 1)
        h.addSpacing(16)
        h.addLayout(right, 1)
        return scroll_page(page)

    def _tab_records(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 14, 8, 8)
        split = QSplitter(Qt.Vertical)
        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.addWidget(label("Olay kayıtları", "h2"))
        self.rec_table = QTableWidget()
        self.rec_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tv.addWidget(self.rec_table)
        bottom = QWidget()
        bv = QVBoxLayout(bottom)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.addWidget(label("Kartın gönderdiği ayarlar ve sayaçlar", "h2"))
        self.cnt_table = QTableWidget()
        self.cnt_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        bv.addWidget(self.cnt_table)
        split.addWidget(top)
        split.addWidget(bottom)
        split.setSizes([420, 260])
        v.addWidget(split)
        return page

    def _tab_run(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        h.setContentsMargins(0, 14, 8, 8)
        h.setSpacing(18)
        form = QVBoxLayout()

        # 1) kart
        box = QGroupBox("1 · Kart")
        g = QGridLayout(box)
        self.port_box = QComboBox()
        self.port_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        refresh = QPushButton("↻")
        refresh.setFixedWidth(34)
        refresh.setToolTip("Seri portları yenile")
        refresh.clicked.connect(self._refresh_ports)
        self.conn_btn = QPushButton("Bağlan")
        self.conn_btn.clicked.connect(self._toggle_connect)
        self.conn_label = label("● bağlı değil", "small")
        g.addWidget(self.port_box, 0, 0)
        g.addWidget(refresh, 0, 1)
        g.addWidget(self.conn_btn, 0, 2)
        g.addWidget(self.conn_label, 1, 0, 1, 3)
        g.addWidget(label("Kartta lab firmware'i (APP_LAB_MODE 1) yüklü olmalı.", "small", wrap=True), 2, 0, 1, 3)
        g.setColumnStretch(0, 1)
        form.addWidget(box)

        # 2) yük
        box = QGroupBox("2 · Yük")
        g = QGridLayout(box)
        self.preset = QComboBox()
        for k, (p, wk) in PRESETS.items():
            tel = "telemetri kapalı" if p == 0 else f"{1000 // p} Hz"
            self.preset.addItem(f"{k} · {tel}" + (f" + {wk // 1000} ms" if wk else ""), k)
        self.preset.addItem("Özel", "C")
        self.preset.setCurrentIndex(5)
        self.period = QSpinBox()
        self.period.setRange(0, 1000)
        self.period.setSuffix(" ms")
        self.period.setToolTip("Telemetri periyodu; 0 telemetriyi kapatır")
        self.work = QSpinBox()
        self.work.setRange(0, 9500)
        self.work.setSingleStep(500)
        self.work.setSuffix(" µs")
        self.work.setToolTip("Öncelik 3'teki TelemetryTask'ın her periyotta yaptığı kalibre CPU işi")
        self.load_label = label("", "small", wrap=True)
        self.load_warn = label("", "warn", wrap=True)
        g.addWidget(label("Senaryo", "muted"), 0, 0)
        g.addWidget(self.preset, 0, 1)
        g.addWidget(label("Telemetri periyodu", "muted"), 1, 0)
        g.addWidget(self.period, 1, 1)
        g.addWidget(label("CPU işi / periyot", "muted"), 2, 0)
        g.addWidget(self.work, 2, 1)
        g.addWidget(self.load_label, 3, 0, 1, 2)
        g.addWidget(self.load_warn, 4, 0, 1, 2)
        g.setColumnStretch(1, 1)
        form.addWidget(box)

        # 3) çözüm
        box = QGroupBox("3 · Çözüm")
        bv = QVBoxLayout(box)
        self.fix_box = QComboBox()
        for _, lbl, mask in FIX_PRESETS:
            self.fix_box.addItem(lbl, mask)
        self.fix_note = label("", "small", wrap=True)
        bv.addWidget(self.fix_box)
        bv.addWidget(self.fix_note)
        form.addWidget(box)

        # 4) basışlar
        box = QGroupBox("4 · Basışlar")
        g = QGridLayout(box)
        self.auto_rb = QRadioButton("Otomatik (kart üretir)")
        self.manual_rb = QRadioButton("Elle (B1'e sen basarsın)")
        self.auto_rb.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.auto_rb)
        grp.addButton(self.manual_rb)
        self.events = QSpinBox()
        self.events.setRange(1, 128)
        self.events.setValue(35)
        self.events.setSuffix(" olay")
        self.gmin = QSpinBox()
        self.gmin.setRange(100, 5000)
        self.gmin.setValue(500)
        self.gmin.setSuffix(" ms")
        self.gmax = QSpinBox()
        self.gmax.setRange(100, 10000)
        self.gmax.setValue(1500)
        self.gmax.setSuffix(" ms")
        g.addWidget(self.auto_rb, 0, 0, 1, 2)
        g.addWidget(self.manual_rb, 0, 2, 1, 2)
        g.addWidget(label("Olay sayısı", "muted"), 1, 0)
        g.addWidget(self.events, 1, 1, 1, 3)
        g.addWidget(label("Aralık", "muted"), 2, 0)
        g.addWidget(self.gmin, 2, 1)
        g.addWidget(label("–", "muted"), 2, 2)
        g.addWidget(self.gmax, 2, 3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        form.addWidget(box)
        form.addStretch(1)
        formw = QWidget()
        formw.setLayout(form)
        formw.setFixedWidth(430)
        h.addWidget(formw)

        # canlı durum
        live = QVBoxLayout()
        live.setSpacing(10)
        self.run_btn = QPushButton("▶  Deneyi başlat")
        self.run_btn.setObjectName("run")
        self.run_btn.clicked.connect(self._start)
        row = QHBoxLayout()
        self.stop_btn = QPushButton("Durdur ve kayıtları al")
        self.ping_btn = QPushButton("Kartı yokla (Ping)")
        self.stop_btn.clicked.connect(self._stop)
        self.ping_btn.clicked.connect(lambda: self._send("PING\n"))
        row.addWidget(self.stop_btn, 1)
        row.addWidget(self.ping_btn)
        box = QGroupBox("Canlı durum")
        lv = QVBoxLayout(box)
        self.phase_label = label("beklemede", "phase")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 35)
        self.count_label = label("", "muted")
        self.press_label = label("", "press")
        self.msg_label = label("Kartı bağla, ayarları seç ve deneyi başlat. Sonuç soldaki listeye \"Bu oturum\" "
                               "altında eklenir ve Özet sekmesinde açılır.", "muted", wrap=True)
        for x in (self.phase_label, self.progress, self.count_label, self.press_label, self.msg_label):
            lv.addWidget(x)
        lv.addStretch(1)
        live.addWidget(self.run_btn)
        live.addLayout(row)
        live.addWidget(box, 1)
        h.addLayout(live, 1)

        self.preset.currentIndexChanged.connect(self._apply_preset)
        self.period.valueChanged.connect(self._custom_edit)
        self.work.valueChanged.connect(self._custom_edit)
        self.fix_box.currentIndexChanged.connect(self._fix_changed)
        self.auto_rb.toggled.connect(self._press_mode_changed)
        self._apply_preset()
        self._fix_changed()
        self._set_run_controls(False)
        return scroll_page(page)

    # ---- tema -----------------------------------------------------------------
    def _toggle_theme(self):
        global T
        T = DARK if T is LIGHT else LIGHT
        self.theme_btn.setText("Açık tema" if T is DARK else "Koyu tema")
        QApplication.instance().setStyleSheet(qss(T))
        self._fill_run_list(select=self.current_key)

    # ---- deney kontrolleri ------------------------------------------------
    def _apply_preset(self):
        key = self.preset.currentData()
        if key in PRESETS:
            for sb, val in zip((self.period, self.work), PRESETS[key]):
                sb.blockSignals(True)
                sb.setValue(val)
                sb.blockSignals(False)
        self._update_load_label()

    def _custom_edit(self):
        match = next((k for k, v in PRESETS.items() if v == (self.period.value(), self.work.value())), "C")
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(self.preset.findData(match))
        self.preset.blockSignals(False)
        self._update_load_label()

    def _update_load_label(self):
        p, w = self.period.value(), self.work.value()
        self.load_warn.setText("")
        self.load_warn.setVisible(False)
        if p == 0:
            self.load_label.setText("telemetri kapalı · UART yalnızca buton yanıtlarını taşır")
            return
        free = p - w / 1000
        self.load_label.setText(f"{1000 / p:.0f} Hz · CPU %{w / 10 / p:.0f} · hat %{LINE_MS / p * 100:.0f} · "
                                f"periyotta {num(free)} ms boş")
        warn = ""
        if w / 1000 >= p:
            warn = "CPU işi periyottan kısa olmalı."
        elif w and free < LINE_MS:
            warn = f"Boş süre bir mesajdan ({num(LINE_MS)} ms) kısa: standart tasarım UART'ı aç bırakır."
        self.load_warn.setText(warn)
        self.load_warn.setVisible(bool(warn))

    def _fix_changed(self):
        mask = self.fix_box.currentData()
        bits = ", ".join(v for b, v in FIX_BITS.items() if mask & b) or "ödev tasarımı, değişiklik yok"
        self.fix_note.setText(bits)

    def _press_mode_changed(self):
        auto = self.auto_rb.isChecked()
        self.gmin.setEnabled(auto)
        self.gmax.setEnabled(auto)

    def _set_run_controls(self, connected: bool):
        for b in (self.run_btn, self.stop_btn, self.ping_btn):
            b.setEnabled(connected)

    # ---- seri port ------------------------------------------------------------
    def _refresh_ports(self):
        cur = self.port_box.currentText()
        self.port_box.clear()
        ports = list_ports()
        self.port_box.addItems(ports)
        self.port_box.setPlaceholderText("kart bulunamadı: USB'yi tak, ↻'ye bas")
        self.conn_btn.setEnabled(bool(ports) or self.reader is not None)
        if cur:
            self.port_box.setCurrentText(cur)

    def _toggle_connect(self):
        if self.reader:
            self._disconnect()
            return
        port = self.port_box.currentText()
        if not port:
            QMessageBox.warning(self, "RTOS Lab", "Seri port bulunamadı.")
            return
        try:
            self.reader = SerialReader(port, self.q)
        except serial.SerialException as e:
            QMessageBox.critical(self, "RTOS Lab", f"{e}\n\nPortu başka bir program (örn. monitor.py) kullanıyor olabilir.")
            return
        self.reader.start()
        self.sess = Session()
        self.conn_btn.setText("Bağlantıyı kes")
        self.conn_label.setText(f"● bağlı: {Path(port).name}")
        self.conn_label.setStyleSheet(f"color: {T.ok};")
        self._set_run_controls(True)
        self._send("PING\n")
        self._say("Bağlandı. Kartın durumu soruldu…")

    def _disconnect(self):
        if self.reader:
            self.reader.stop()
        self.reader = None
        self.conn_btn.setText("Bağlan")
        self.conn_label.setText("● bağlı değil")
        self.conn_label.setStyleSheet("")
        self._set_run_controls(False)
        self._set_phase("IDLE")

    def _send(self, text: str):
        if self.reader:
            try:
                self.reader.ser.write(text.encode())
            except serial.SerialException as e:
                self._say(f"Seri porta yazılamadı: {e}", error=True)

    def _start(self):
        p, w = self.period.value(), self.work.value()
        if p and w / 1000 >= p:
            QMessageBox.warning(self, "RTOS Lab", "CPU işi telemetri periyodundan kısa olmalı.")
            return
        if self.gmax.value() < self.gmin.value():
            self.gmax.setValue(self.gmin.value())
        self.run_counter += 1
        cfg = LabConfig(period_ms=p, work_us=w, fix=self.fix_box.currentData(),
                        inject=1 if self.auto_rb.isChecked() else 0, target=self.events.value(),
                        gap_min_ms=self.gmin.value(), gap_max_ms=self.gmax.value(),
                        seed=int(time.time()) % 10000 + 1, run_id=self.run_counter)
        self.pending_cfg = cfg
        self.sess, self.raw = Session(), bytearray()
        self.progress.setRange(0, cfg.target)
        self.progress.setValue(0)
        self._send(cfg.command())
        self._set_phase("SENT")
        self._say("Ayarlar gönderildi; kart bu ayarlarla yeniden başlıyor.")

    def _stop(self):
        self._send("STOP\n")
        self._say("Durdurma istendi: kart kuyruğunu boşaltıp kayıtları gönderiyor.")

    # ---- canlı veri -------------------------------------------------------
    def _set_phase(self, phase: str):
        self.phase, self.phase_t = phase, time.monotonic()

    def _poll(self):
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, Exception):
                self._say(f"Seri port hatası: {item}", error=True)
                self._disconnect()
                return
            self.raw.extend(item)
            self.sess.feed(item)

        for line in self.sess.new_lab:
            self._on_lab_line(line)
        self.sess.new_lab.clear()
        for event_id, _ in self.sess.new_btn:
            self.press_label.setText(f"Butona basıldı · olay {event_id}")
            self.flash_until = time.monotonic() + 0.6
        self.sess.new_btn.clear()
        if self.flash_until and time.monotonic() > self.flash_until:
            self.press_label.setText("")
            self.flash_until = 0.0
        if self.sess.collector.active and self.phase not in ("EXPORT", "IDLE"):
            self._set_phase("EXPORT")
        if self.sess.new_export:
            self._on_export(self.sess.new_export)
            self.sess.new_export = None

        el = time.monotonic() - self.phase_t
        if self.phase == "SENT" and el > 4:
            self._say("RUN'a yanıt gelmedi. Kartta lab firmware'i (APP_LAB_MODE 1) yüklü mü?", error=True)
            self._set_phase("IDLE")
        if self.phase == "WARMUP" and el >= WARMUP_S:
            self._set_phase("RUNNING")
            manual = self.pending_cfg and not self.pending_cfg.inject
            self._say("Şimdi mavi B1 butonuna bas (LD2 yanık)." if manual
                      else "Deney sürüyor: basışları kart üretiyor.")
        txt = {"IDLE": "beklemede", "SENT": "kart yeniden başlıyor…", "RUNNING": "deney sürüyor",
               "EXPORT": "kayıtlar alınıyor…"}.get(self.phase, "")
        if self.phase == "WARMUP":
            txt = f"ısınma · {num(max(0.0, WARMUP_S - el), 1)} s"
        self.phase_label.setText(txt)
        target = self.pending_cfg.target if self.pending_cfg else 0
        if self.phase in ("RUNNING", "WARMUP", "EXPORT"):
            self.count_label.setText(f"{self.sess.btn_count} / {target} basış   ·   {self.sess.tel_count} telemetri mesajı")
            self.progress.setValue(min(self.sess.btn_count, target))

    def _on_lab_line(self, line: str):
        parts = line.split(",")
        if self.phase == "SENT":
            self._set_phase("WARMUP")
            self.sess.tel_count = self.sess.btn_count = 0
            self._say(f"Kart {parts[2]} ayarıyla yeniden başladı ({' '.join(parts[3:])}).")
        else:
            self._say(f"Kart hazır: {line}")

    def _on_export(self, exp):
        cfg = self.pending_cfg
        lbl = f"#{cfg.run_id if cfg else '?'} {exp.scenario} · {fix_label(int(exp.cfg.get('fix', 0) or 0))}"
        run = from_export(exp, f"live:{time.time()}", lbl, GROUP_SESSION, bytes(self.raw))
        self.runs.append(run)
        self.compare_keys.add(run.key)
        self._fill_run_list(select=run.key)
        self._set_phase("IDLE")
        self._say(f"Kayıtlar alındı ({run.stat()['n']} olay) ve Özet sekmesinde açıldı. Saklamak için soldan "
                  "CSV ve ham oturumu kaydet.")
        self.tabs.setCurrentIndex(self.TAB_SUMMARY)

    def _say(self, text: str, error: bool = False):
        self.msg_label.setText(text)
        self.msg_label.setStyleSheet(f"color: {T.critical};" if error else "")

    # ---- deneme listeleri --------------------------------------------------
    def _fill_run_list(self, select: str | None = None):
        self.run_list.clear()
        group = None
        for r in self.runs:
            if r.group != group:
                group = r.group
                head = QListWidgetItem(group.upper())
                head.setFlags(Qt.NoItemFlags)
                f = QFont()
                f.setPointSize(10)
                f.setBold(True)
                head.setFont(f)
                head.setForeground(QColor(T.muted))
                self.run_list.addItem(head)
            st = r.stat()
            good = st["late"] == 0 and st["lost"] == 0
            it = QListWidgetItem(f"●  {r.label}")
            it.setData(Qt.UserRole, r.key)
            it.setForeground(QColor(T.ok if good else T.critical))
            it.setToolTip(f"{'tüm deadline tutuldu' if good else 'aşan ya da kaybolan yanıt var'}\n"
                          f"{r.conditions()}\nen büyük R {num(st['max'] or 0, 1)} ms · {st['late']} aşan · "
                          f"{st['lost']} kayıp")
            self.run_list.addItem(it)
        key = select or self.current_key or (self.runs[0].key if self.runs else None)
        for i in range(self.run_list.count()):
            if self.run_list.item(i).data(Qt.UserRole) == key:
                self.run_list.setCurrentRow(i)
        self._show_run(key)
        self._fill_compare_list()

    def _fill_compare_list(self):
        self.cmp_list.blockSignals(True)
        self.cmp_list.clear()
        for r in self.runs:
            it = QListWidgetItem(r.label)
            it.setData(Qt.UserRole, r.key)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if r.key in self.compare_keys else Qt.Unchecked)
            self.cmp_list.addItem(it)
        self.cmp_list.blockSignals(False)
        self._update_compare()

    def _run_clicked(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        if key:
            self._show_run(key)
            if self.tabs.currentIndex() in (self.TAB_RUN, self.TAB_GUIDE):
                self.tabs.setCurrentIndex(self.TAB_SUMMARY)

    def _cmp_checked(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        (self.compare_keys.add if item.checkState() == Qt.Checked else self.compare_keys.discard)(key)
        self._update_compare()

    def current_run(self) -> Run | None:
        return next((r for r in self.runs if r.key == self.current_key), None)

    # ---- seçili denemeyi göster ------------------------------------------------
    def _show_run(self, key: str | None):
        run = next((r for r in self.runs if r.key == key), None)
        if run is None:
            return
        self.current_key = key
        st = run.stat()
        self.chip_group.setText("resmi · standart tasarım" if run.official else run.group.lower())
        self.chip_press.setText("otomatik basış" if run.inject else "elle basış")
        self.chip_fix.setText(fix_label(run.fix) if run.fix else "çözüm yok")
        self.title.setText(run.label)
        self.conditions.setText(run.conditions())
        self.headline.setText(headline(run))
        bad = lambda cond: f"color:{T.critical};font-weight:700" if cond else f"color:{T.ink};font-weight:700"  # noqa: E731
        sep = f"<span style='color:{T.grid}'>&nbsp;&nbsp;|&nbsp;&nbsp;</span>"
        self.metrics.setText(
            f"yanıt <span style='{bad(st['ok'] < st['n'])}'>{st['ok']}/{st['n']}</span>{sep}"
            f"ortalama <span style='{bad((st['avg'] or 0) > DEADLINE_MS)}'>{num(st['avg'])}</span> ms{sep}"
            f"en büyük <span style='{bad((st['max'] or 0) > DEADLINE_MS)}'>{num(st['max'])}</span> ms{sep}"
            f"20 ms aşan <span style='{bad(st['late'])}'>{st['late']}</span>{sep}"
            f"kayıp yanıt <span style='{bad(st['lost'])}'>{st['lost']}</span>")
        self.resp_chart.show(run)
        self.stage_chart.show(run)
        self._fill_diag(run)
        self._fill_events(run)
        self._fill_records(run)
        self._fill_counters(run)

    def _fill_diag(self, run: Run):
        lines = []
        if run.period_ms:
            free = run.period_ms - run.work_us / 1000
            lines.append(f"Her {run.period_ms} ms'lik periyotta: {run.work_us / 1000:g} ms öncelik 3 işi, "
                         f"geriye {num(free)} ms kalıyor; bir mesajın hat süresi {num(LINE_MS)} ms.")
        else:
            lines.append("Telemetri kapalı; UART yalnızca buton yanıtlarını taşıyor.")
        if run.uart_starved():
            lines.append(f"<span style='color:{T.critical}'><b>UART aç kalıyor.</b> Öncelik 1'deki UART görevi "
                         "periyot başına en fazla bir mesaj başlatabiliyor; bu telemetri hızına eşit, dolayısıyla "
                         "her yanıt birikime ekleniyor.</span>")
        slope = run.backlog_slope_ms_per_event()
        if slope is not None:
            lines.append(f"TX öncesi bekleme eğilimi: <b>olay başına {num(slope)} ms</b> "
                         + ("— birikim her basışta büyüyor." if slope > 1 else "— birikim yok."))
        if run.cnt.get("txq_hwm"):
            lines.append(f"txQ en yüksek doluluk {run.cnt['txq_hwm']}/16 · kayıp telemetri "
                         f"{run.cnt.get('tel_tx_drop', 0)}")
        self.diag.setHtml("<p>" + "<br><br>".join(lines) + "</p>")

    def _fill_events(self, run: Run):
        self._events = sorted(run.events, key=lambda e: (e.ok and not e.late, e.rec.event_id))
        self.event_list.blockSignals(True)
        self.event_list.clear()
        for e in self._events:
            if not e.ok:
                text, col = f"olay {e.rec.event_id:<3} ✕ yanıt yok", T.critical
            elif e.late:
                text, col = f"olay {e.rec.event_id:<3} {num(e.r_ms):>7} ms  aştı", T.critical
            else:
                text, col = f"olay {e.rec.event_id:<3} {num(e.r_ms):>7} ms", T.ink2
            it = QListWidgetItem(text)
            it.setForeground(QColor(col))
            it.setFont(QFont("Menlo", 11))
            self.event_list.addItem(it)
        self.event_list.blockSignals(False)
        self.event_list.setCurrentRow(0)
        self._show_event(0)

    def _show_event(self, idx: int):
        run = self.current_run()
        if run is None or not (0 <= idx < len(self._events)):
            self.budget_chart.show(None)
            self.cause.setText("")
            return
        ev = self._events[idx]
        self.budget_chart.show(ev)
        _, why = run.diagnose(ev)
        self.cause.setText(f"<p style='font-size:14px'>{why}</p>")

    def _fill_records(self, run: Run):
        cols = ["olay", "durum", "t1−t0", "t2−t1", "t3−t2", "t4−t3", "R (ms)", "neden"]
        t = self.rec_table
        t.setColumnCount(len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.setRowCount(len(run.events))
        for i, e in enumerate(run.events):
            _, why = run.diagnose(e)
            vals = [str(e.rec.event_id), STATUS_TR.get(e.rec.status, e.rec.status)] + \
                   ["" if e.stages_ms[k] is None else num(e.stages_ms[k], 3) for k, *_ in STAGES] + \
                   ["" if e.r_ms is None else num(e.r_ms, 3), why]
            for j, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if (e.late or not e.ok) and j in (1, 6):
                    it.setForeground(QColor(T.critical))
                t.setItem(i, j, it)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(len(cols) - 1, QHeaderView.Stretch)

    def _fill_counters(self, run: Run):
        rows = [("CFG", k, v) for k, v in run.cfg.items()] + [("CNT", k, v) for k, v in run.cnt.items()] + \
               [("TSK", tk["name"], f"öncelik {tk.get('prio')} · {tk.get('stack_hwm_words')} word boş")
                for tk in run.tasks]
        t = self.cnt_table
        t.setColumnCount(3)
        t.setHorizontalHeaderLabels(["", "anahtar", "değer"])
        t.setRowCount(max(1, len(rows)))
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                t.setItem(i, j, QTableWidgetItem(str(val)))
        if not rows:
            t.setItem(0, 1, QTableWidgetItem("bu deneme için meta dosyası yok"))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def _update_compare(self):
        runs = [r for r in self.runs if r.key in self.compare_keys]
        self.cmp_chart.show(runs)
        cols = ["deneme", "koşullar", "yanıt", "ort. R", "en büyük R", "aşan", "kayıp", "txQ max"] + \
               [lb.split(" (")[0] for _, lb, *_ in STAGES]
        t = self.cmp_table
        t.setColumnCount(len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.setRowCount(len(runs))
        for i, r in enumerate(runs):
            st, sm = r.stat(), r.stage_means()
            vals = [r.label, r.conditions(), f"{st['ok']}/{st['n']}", num(st["avg"]), num(st["max"]),
                    str(st["late"]), str(st["lost"]), r.cnt.get("txq_hwm", "")] + [num(sm[k]) for k, *_ in STAGES]
            for j, val in enumerate(vals):
                it = QTableWidgetItem(val)
                if j in (4, 5) and st["late"]:
                    it.setForeground(QColor(T.critical))
                t.setItem(i, j, it)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    # ---- dosyalar -----------------------------------------------------------
    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Oturum aç", str(Path(__file__).resolve().parents[1]),
                                              "Oturumlar (*.csv *.bin *.txt);;Tüm dosyalar (*)")
        if not path:
            return
        p = Path(path)
        run = load_csv(p, GROUP_FILES, f"{p.stem} · dosya") if p.suffix == ".csv" else load_raw(p)
        if run is None:
            QMessageBox.warning(self, "RTOS Lab", "Bu dosyada deney sonu export'u (CFG…END) bulunamadı.")
            return
        self.runs.append(run)
        self._fill_run_list(select=run.key)

    def _save_csv(self):
        run = self.current_run()
        if run is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "CSV kaydet", f"{run.cfg.get('scenario', 'deneme')}.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(CSV_HEADER)
            for e in run.events:
                w.writerow([e.rec.scenario, e.rec.event_id, *["" if t is None else t for t in e.rec.t], e.rec.status])
        meta = Path(path).with_name(Path(path).stem + "_meta.txt")
        meta.write_text("\n".join([f"CFG,{k}={v}" for k, v in run.cfg.items()] +
                                  [f"CNT,{k}={v}" for k, v in run.cnt.items()] +
                                  [f"TSK,{t['name']},prio={t.get('prio')},stack_hwm_words={t.get('stack_hwm_words')}"
                                   for t in run.tasks]) + "\n")
        QMessageBox.information(self, "RTOS Lab", f"{Path(path).name} ve {meta.name} kaydedildi.")

    def _save_raw(self):
        run = self.current_run()
        if run is None or not run.raw:
            QMessageBox.information(self, "RTOS Lab", "Ham baytlar yalnızca bu oturumda kaydedilen denemelerde var.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Ham oturumu kaydet",
                                              f"{run.cfg.get('scenario', 'deneme')}_ham.bin", "Ham UART (*.bin)")
        if path:
            Path(path).write_bytes(run.raw)
            QMessageBox.information(self, "RTOS Lab", f"Ham UART oturumu kaydedildi ({len(run.raw)} bayt).")

    def closeEvent(self, ev):
        if self.reader:
            self.reader.stop()
        super().closeEvent(ev)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(qss(T))
    w = LabWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
