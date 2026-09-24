"""UART Monitor: NUCLEO-L476RG Ödev 01 PC arayüzü.

Arayüz ölçümü gösterir, ölçüme karışmaz: R ve aşama süreleri yalnızca
kartın t0..t4 damgalarından hesaplanır; PC saati R'de kullanılmaz.

Kullanım:
  python monitor.py                              # grafik arayüz
  python monitor.py --headless [--port PORT]     # arayüzsüz: END'e kadar dinle, kaydet
"""
from __future__ import annotations

import argparse
import glob
import queue
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import serial

from protocol import Export, ExportCollector, LineFramer, parse_line, write_export

BAUD = 115200
DEADLINE_MS = 20.0
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "measurements"


def list_ports() -> list[str]:
    return sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*") + glob.glob("COM*"))


class SerialReader(threading.Thread):
    """Seri porttan okur, ham parçaları kuyruğa koyar (GUI iş parçacığı dışında)."""

    def __init__(self, port: str, out: queue.Queue):
        super().__init__(daemon=True)
        self.ser = serial.Serial(port, BAUD, timeout=0.1)
        self.out = out
        self._stop = threading.Event()

    def run(self) -> None:
        try:
            while not self._stop.is_set():
                data = self.ser.read(4096)
                if data:
                    self.out.put(data)
        except serial.SerialException as e:
            self.out.put(e)
        finally:
            self.ser.close()

    def stop(self) -> None:
        self._stop.set()


class Session:
    """Gelen satırları sınıflandırır ve sayaçları tutar (arayüzden bağımsız)."""

    def __init__(self) -> None:
        self.framer = LineFramer()
        self.collector = ExportCollector()
        self.scenario = "?"
        self.tel_count = 0
        self.btn_count = 0
        self.format_errors = 0
        self.unknown = 0
        self.last_tel = ""
        self.tel_times: deque[float] = deque()   # yalnızca gösterim: PC'de gözlenen hız
        self.new_btn: list[tuple[str, str]] = []
        self.new_export: Export | None = None

    def feed(self, data: bytes) -> None:
        for raw in self.framer.feed(data):
            line = parse_line(raw)
            if line.kind in {"TEL", "BTN"}:
                if not line.length_ok:
                    self.format_errors += 1
                    continue
                self.scenario = line.fields[1]
                if line.kind == "TEL":
                    self.tel_count += 1
                    self.last_tel = raw.decode().rstrip()
                    self.tel_times.append(time.monotonic())
                else:
                    self.btn_count += 1
                    self.new_btn.append((line.fields[0], line.fields[1]))
            elif line.kind == "UNKNOWN":
                self.unknown += 1
            else:
                exp = self.collector.feed(line)
                if exp:
                    self.new_export = exp

    def tel_rate_hz(self) -> float:
        now = time.monotonic()
        while self.tel_times and now - self.tel_times[0] > 1.0:
            self.tel_times.popleft()
        return float(len(self.tel_times))


def save_export(exp: Export, out_dir: Path, overwrite: bool) -> tuple[Path, Path]:
    """Var olan dosya ezilmeyecekse zaman damgalı adla kaydeder."""
    try:
        return write_export(exp, out_dir, overwrite=overwrite)
    except FileExistsError:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        exp.cfg["scenario"] = f"{exp.scenario}_{stamp}"
        return write_export(exp, out_dir)


def summarize(exp: Export) -> str:
    rs = [r.r_us / 1000 for r in exp.records if r.status == "ok" and r.r_us is not None]
    lost = sum(r.status != "ok" for r in exp.records)
    s = f"{exp.scenario}: {len(exp.records)} records, {len(rs)} ok, {lost} not ok"
    if rs:
        late = sum(r > DEADLINE_MS for r in rs)
        s += f" | R min/avg/max = {min(rs):.2f}/{sum(rs)/len(rs):.2f}/{max(rs):.2f} ms, >{DEADLINE_MS:.0f} ms: {late}"
    return s


# ---------------------------------------------------------------- headless --

def run_headless(port: str | None, out_dir: Path, overwrite: bool, timeout_s: float) -> int:
    port = port or (list_ports() or [None])[0]
    if port is None:
        print("no serial port found", file=sys.stderr)
        return 1
    q: queue.Queue = queue.Queue()
    reader = SerialReader(port, q)
    reader.start()
    sess = Session()
    print(f"listening on {port}, waiting for END (timeout {timeout_s:.0f} s)")
    t_end = time.monotonic() + timeout_s
    last_btn = 0
    while time.monotonic() < t_end:
        try:
            item = q.get(timeout=0.2)
        except queue.Empty:
            continue
        if isinstance(item, Exception):
            print(f"serial error: {item}", file=sys.stderr)
            return 1
        sess.feed(item)
        if sess.btn_count != last_btn:
            last_btn = sess.btn_count
            print(f"Butona basıldı · event {sess.new_btn[-1][0]} · {sess.scenario}")
        if sess.new_export:
            csv_path, meta_path = save_export(sess.new_export, out_dir, overwrite)
            print(summarize(sess.new_export))
            print(f"saved {csv_path} and {meta_path.name} | format_errors={sess.format_errors}")
            reader.stop()
            return 0
    reader.stop()
    print("timeout: END not received", file=sys.stderr)
    return 2


# --------------------------------------------------------------------- GUI --

def run_gui(out_dir: Path) -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure


    root = tk.Tk()
    root.title("UART Monitor · Ödev 01")
    root.geometry("1100x680")

    q: queue.Queue = queue.Queue()
    state = {"reader": None, "sess": Session(), "flash_until": 0.0}

    # --- üst çubuk: port seçimi ---
    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    ttk.Label(top, text="Port").pack(side="left")
    port_var = tk.StringVar()
    port_box = ttk.Combobox(top, textvariable=port_var, width=28, state="readonly")
    port_box.pack(side="left", padx=4)

    def refresh_ports():
        ports = list_ports()
        port_box["values"] = ports
        if ports and port_var.get() not in ports:
            port_var.set(ports[0])

    ttk.Button(top, text="↻", width=3, command=refresh_ports).pack(side="left")
    conn_btn = ttk.Button(top, text="Connect")
    conn_btn.pack(side="left", padx=8)
    status_var = tk.StringVar(value="disconnected")
    ttk.Label(top, textvariable=status_var).pack(side="left", padx=8)
    overwrite_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(top, text="Overwrite existing CSV", variable=overwrite_var).pack(side="right")

    body = ttk.Frame(root, padding=(8, 0, 8, 8))
    body.pack(fill="both", expand=True)
    left = ttk.Frame(body, width=360)
    left.pack(side="left", fill="y")
    left.pack_propagate(False)
    right = ttk.Frame(body)
    right.pack(side="left", fill="both", expand=True, padx=(8, 0))

    # --- sol: canlı sayaçlar ---
    live = ttk.LabelFrame(left, text="Live", padding=8)
    live.pack(fill="x")
    vars_ = {k: tk.StringVar(value="-") for k in ("scenario", "tel", "rate", "btn", "fmt", "last")}
    for label, key in [("Scenario", "scenario"), ("TEL received", "tel"), ("TEL rate (PC)", "rate"),
                       ("BTN received", "btn"), ("Format errors", "fmt")]:
        row = ttk.Frame(live)
        row.pack(fill="x")
        ttk.Label(row, text=label, width=14).pack(side="left")
        ttk.Label(row, textvariable=vars_[key]).pack(side="left")
    ttk.Label(live, textvariable=vars_["last"], font=("Menlo", 10), foreground="#666").pack(fill="x", pady=(6, 0))

    btn_banner = tk.Label(left, text="—", font=("Helvetica", 18, "bold"), height=2, bg="#e8e8e8")
    btn_banner.pack(fill="x", pady=8)

    btn_frame = ttk.LabelFrame(left, text="BTN events", padding=4)
    btn_frame.pack(fill="both", expand=True)
    btn_list = tk.Listbox(btn_frame, font=("Menlo", 11))
    btn_list.pack(fill="both", expand=True)

    export_var = tk.StringVar(value="Waiting for end-of-run export (CFG…END)")
    ttk.Label(left, textvariable=export_var, wraplength=340, justify="left").pack(fill="x", pady=(8, 0))

    # --- sağ: R grafiği ---
    fig = Figure(figsize=(6, 4), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=right)
    canvas.get_tk_widget().pack(fill="both", expand=True)

    def plot_export(exp: Export) -> None:
        ax.clear()
        ok = [(r.event_id, r.r_us / 1000) for r in exp.records if r.status == "ok" and r.r_us is not None]
        bad = [r for r in exp.records if r.status != "ok"]
        if ok:
            xs, ys = zip(*ok)
            colors = ["#c0392b" if y > DEADLINE_MS else "#2e6fd8" for y in ys]
            ax.plot(xs, ys, color="#bbb", linewidth=1, zorder=1)
            ax.scatter(xs, ys, c=colors, s=28, zorder=2, label="R (ok)")
        for r in bad:
            ax.axvline(r.event_id, color="#e67e22", linestyle=":", linewidth=1)
        if bad:
            ax.plot([], [], color="#e67e22", linestyle=":", label=f"not ok ({len(bad)})")
        ax.axhline(DEADLINE_MS, color="#c0392b", linestyle="--", linewidth=1, label="deadline 20 ms")
        ax.set_xlabel("event id")
        ax.set_ylabel("R = t4 − t0 (ms)")
        ax.set_title(f"{exp.scenario} · n={len(exp.records)} · board timestamps only")
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.3)
        ax.legend(loc="upper left", fontsize=9)
        canvas.draw_idle()

    def load_csv():
        import csv as _csv
        from protocol import Record
        path = filedialog.askopenfilename(initialdir=out_dir, filetypes=[("CSV", "*.csv")])
        if not path:
            return
        exp = Export()
        with open(path) as f:
            for row in _csv.DictReader(f):
                ts = [int(row[k]) if row[k] else None for k in ("t0_us", "t1_us", "t2_us", "t3_us", "t4_us")]
                exp.records.append(Record(row["scenario"], int(row["event_id"]), ts, row["status"]))
        exp.cfg["scenario"] = exp.records[0].scenario if exp.records else Path(path).stem
        plot_export(exp)
        export_var.set(f"Loaded {path}\n{summarize(exp)}")

    ttk.Button(top, text="Load CSV…", command=load_csv).pack(side="right", padx=8)

    # --- bağlantı ---
    def toggle_connect():
        if state["reader"]:
            state["reader"].stop()
            state["reader"] = None
            conn_btn.config(text="Connect")
            status_var.set("disconnected")
            return
        port = port_var.get()
        if not port:
            messagebox.showerror("UART Monitor", "No serial port selected")
            return
        try:
            state["reader"] = SerialReader(port, q)
        except serial.SerialException as e:
            messagebox.showerror("UART Monitor", str(e))
            return
        state["sess"] = Session()
        btn_list.delete(0, "end")
        state["reader"].start()
        conn_btn.config(text="Disconnect")
        status_var.set(f"connected · {port} · {BAUD} 8N1")

    conn_btn.config(command=toggle_connect)

    # --- periyodik güncelleme (GUI iş parçacığında) ---
    def poll():
        sess: Session = state["sess"]
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, Exception):
                status_var.set(f"serial error: {item}")
                state["reader"] = None
                conn_btn.config(text="Connect")
                break
            sess.feed(item)

        for event_id, scn in sess.new_btn:
            btn_list.insert(0, f"Butona basıldı · event {event_id} · {scn}")
            btn_banner.config(text=f"Butona basıldı · event {event_id}", bg="#7bd389")
            state["flash_until"] = time.monotonic() + 1.0
        sess.new_btn.clear()
        if time.monotonic() > state["flash_until"]:
            btn_banner.config(bg="#e8e8e8")

        if sess.new_export:
            exp, sess.new_export = sess.new_export, None
            csv_path, meta_path = save_export(exp, out_dir, overwrite_var.get())
            export_var.set(f"Saved {csv_path.name} + {meta_path.name}\n{summarize(exp)}")
            plot_export(exp)
        elif sess.collector.active:
            export_var.set("Receiving export…")

        vars_["scenario"].set(sess.scenario)
        vars_["tel"].set(str(sess.tel_count))
        vars_["rate"].set(f"{sess.tel_rate_hz():.0f} Hz")
        vars_["btn"].set(str(sess.btn_count))
        vars_["fmt"].set(str(sess.format_errors))
        vars_["last"].set(sess.last_tel[:40])
        root.after(50, poll)

    refresh_ports()
    root.after(50, poll)
    root.protocol("WM_DELETE_WINDOW", lambda: (state["reader"] and state["reader"].stop(), root.destroy()))
    root.mainloop()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headless", action="store_true", help="no GUI: listen until END, save and exit")
    ap.add_argument("--port", help="serial port (default: first /dev/cu.usbmodem*)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory for Sx.csv")
    ap.add_argument("--overwrite", action="store_true", help="overwrite existing Sx.csv")
    ap.add_argument("--timeout", type=float, default=600, help="headless timeout in seconds")
    args = ap.parse_args()
    if args.headless:
        return run_headless(args.port, args.out, args.overwrite, args.timeout)
    run_gui(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
