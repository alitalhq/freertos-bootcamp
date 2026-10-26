"""Seri bağlantı: kart satırlarını host zamanıyla kaydeder, çerçeve gönderir."""
import json
import threading
import time

import serial

import proto

BAUD = 230400


def now_ns() -> int:
    return time.perf_counter_ns()


class Link:
    def __init__(self, port: str, raw_path=None):
        self.port = port
        self.ser = None
        self.events = []                 # (host_ns, dict) ; JSON olmayan satırlar {"t":"?"}
        self.cv = threading.Condition()
        self.raw = open(raw_path, "a") if raw_path else None
        self.bytes_written = 0
        self.ctrl_seq = 0
        self.wlock = threading.Lock()    # yük thread'i ile kontrol gönderimi aynı anda: çerçeve bölünmesin
        self._stop = threading.Event()
        self._thread = None
        self.open()

    # ---- bağlantı -------------------------------------------------------------
    def open(self):
        self.ser = serial.Serial(self.port, BAUD, timeout=0.05)
        self._stop.clear()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join()
        self.ser.close()

    def shutdown(self):
        self.close()
        if self.raw:
            self.raw.close()

    def _reader(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(4096)
            except (serial.SerialException, OSError):
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                t = now_ns()
                text = line.decode("ascii", "replace").strip()
                try:
                    ev = json.loads(text)
                except ValueError:
                    ev = {"t": "?", "raw": text}
                with self.cv:
                    self.events.append((t, ev))
                    self.cv.notify_all()
                if self.raw:
                    self.raw.write(json.dumps({"host_ns": t, **ev}) + "\n")

    # ---- gönderme -------------------------------------------------------------
    def write(self, data: bytes) -> int:
        with self.wlock:
            n = self.ser.write(data)
            self.bytes_written += n
            return n

    def ctrl(self, op: int, arg=None) -> int:
        """CONTROL gönderir, kullanılan SEQ'i döndürür."""
        with self.wlock:
            seq = self.ctrl_seq
            self.ctrl_seq += 1
            n = self.ser.write(proto.control(seq, op, arg))
            self.bytes_written += n
        return seq

    def new_session(self):
        """Test oturumu: CONTROL SEQ 0'dan başlar (kart sıra takibini sıfırlar)."""
        self.ctrl_seq = 0

    # ---- bekleme ---------------------------------------------------------------
    def mark(self) -> int:
        with self.cv:
            return len(self.events)

    def wait(self, pred, start: int, timeout: float):
        """start indeksinden sonra pred'i sağlayan ilk olay; yoksa None."""
        end = time.monotonic() + timeout
        i = start
        with self.cv:
            while True:
                while i < len(self.events):
                    if pred(self.events[i][1]):
                        return self.events[i]
                    i += 1
                left = end - time.monotonic()
                if left <= 0:
                    return None
                self.cv.wait(left)

    def since(self, start: int, kind=None):
        with self.cv:
            ev = self.events[start:]
        return [e for e in ev if kind is None or e[1].get("t") == kind]

    def ack(self, seq: int, op: int, start: int, timeout=1.0):
        e = self.wait(lambda d: d.get("t") == "A" and d.get("a") == seq and d.get("b") == op, start, timeout)
        if e is None:
            raise TimeoutError(f"ACK yok: op=0x{op:02x} seq={seq}")
        return e[1]

    def snapshot(self, timeout=2.0) -> dict:
        start = self.mark()
        self.ctrl(proto.SNAPSHOT)
        if self.wait(lambda d: d.get("t") == "S9", start, timeout) is None:
            raise TimeoutError("SNAPSHOT cevabı yok")
        snap = {}
        for _, d in self.since(start):
            if d.get("t") in ("H", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"):
                tag = d["t"]
                for k, v in d.items():
                    if k != "t":
                        snap[f"{tag}.{k}" if tag == "S9" else k] = v
        return snap


def pace(rate: float, count: int):
    """count adım, saniyede rate; mutlak zamanlama (birikmiş kayma yok)."""
    t0 = time.perf_counter()
    for i in range(count):
        target = t0 + i / rate
        while True:
            d = target - time.perf_counter()
            if d <= 0:
                break
            time.sleep(d - 0.0008 if d > 0.0015 else 0)
        yield i
