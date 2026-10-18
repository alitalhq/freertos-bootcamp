"""SystemView .SVDat çözücü (Hafta 2'deki çözücünün Hafta 3 olaylarına uyarlaması).

Kart post-mortem halka tamponunu gönderir; dosya bir senkron noktasından (10 × 0x00)
itibaren okunur. Her paket: olay kimliği, (kimlik >= 24 ise) uzunluk, yük ve zaman
farkı (DWT, 80 MHz). Biçim: SEGGER_SYSVIEW.c (_SendPacket, _EncodeStr).

Kullanım:
    from svdat import decode
    tr = decode(Path("B-S5t2.SVDat"))
    tr.tasks     -> {kimlik: ad}
    tr.events    -> [Event(t_us, kind, arg0, arg1)]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

CPU_HZ = 80_000_000

# Kimlik < 24 olan sistem olaylarının yükündeki U32 sayısı (string'liler ayrı)
FIXED_U32 = {0: 0, 1: 1, 2: 1, 3: 0, 4: 1, 5: 0, 6: 1, 7: 2, 8: 1, 10: 0, 11: 0,
             12: 1, 13: 2, 15: 1, 16: 1, 17: 0, 18: 0, 19: 1, 20: 0, 21: 4}
NAMES = {2: "ISR_ENTER", 3: "ISR_EXIT", 4: "TASK_START_EXEC", 5: "TASK_STOP_EXEC",
         6: "TASK_START_READY", 7: "TASK_STOP_READY", 17: "IDLE", 18: "ISR_TO_SCHEDULER"}
# Hafta 3 referans firmware'inin modülü: M=Week3_Queue, olaylar 512 + n, parametre (run, id, ayrıntı)
W3_BASE = 512
W3_NAMES = ["RUN", "SEND_BEGIN", "SEND_OK", "SEND_FAIL", "RECEIVE", "DONE"]
ISR_NAMES = {15: "SysTick", 54: "USART2", 56: "EXTI15_10"}


@dataclass
class Event:
    t_us: float
    kind: str
    arg0: int = 0
    arg1: int = 0
    arg2: int = 0


@dataclass
class Trace:
    tasks: dict[int, str] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)


def _u32(b: bytes, i: int) -> tuple[int, int]:
    v = sh = 0
    while True:
        x = b[i]
        i += 1
        v |= (x & 0x7F) << sh
        sh += 7
        if not x & 0x80:
            return v, i


def _str(b: bytes, i: int) -> tuple[str, int]:
    n = b[i]
    i += 1
    if n == 255:                       # uzun string: 255, hi, lo
        n = (b[i] << 8) | b[i + 1]
        i += 2
    return b[i:i + n].decode("utf-8", errors="replace"), i + n


def decode(path: Path) -> Trace:
    b = path.read_bytes()
    i = b.find(b"\x00" * 10)          # ilk senkron: öncesi yarım paket olabilir
    if i < 0:
        raise ValueError("no sync in trace")
    tr = Trace()
    t = 0
    while i < len(b):
        try:
            eid, i = _u32(b, i)
            args: list[int] = []
            if eid in FIXED_U32:
                for _ in range(FIXED_U32[eid]):
                    v, i = _u32(b, i)
                    args.append(v)
            elif eid == 9:                       # TASK_INFO: id, öncelik, ad
                tid, i = _u32(b, i)
                _, i = _u32(b, i)
                name, i = _str(b, i)
                tr.tasks[tid] = name
            elif eid == 14:                      # SYSDESC
                _, i = _str(b, i)
            elif eid == 22:                      # MODULEDESC: modül, ofset, metin
                _, i = _u32(b, i)
                _, i = _u32(b, i)
                _, i = _str(b, i)
            elif eid < 24:
                raise ValueError(f"unknown system event {eid} at {i}")
            else:                                # uzunluklu paket
                n, i = _u32(b, i)
                payload, i = b[i:i + n], i + n
                j = 0
                while j < len(payload) and len(args) < 3:
                    v, j = _u32(payload, j)
                    args.append(v)
            delta, i = _u32(b, i)
        except IndexError:
            break                                # son paket kesik
        t += delta
        t_us = t * 1e6 / CPU_HZ
        if eid in NAMES:
            tr.events.append(Event(t_us, NAMES[eid], *(args + [0, 0, 0])[:3]))
        elif W3_BASE <= eid < W3_BASE + len(W3_NAMES):
            tr.events.append(Event(t_us, W3_NAMES[eid - W3_BASE], *(args + [0, 0, 0])[:3]))
    return tr


def msg_times(tr: Trace, seq: int) -> dict[str, float]:
    """Bir mesajın (sıra no) iz içindeki W3 olay zamanları (µs)."""
    return {e.kind: e.t_us for e in tr.events if e.kind in W3_NAMES and e.arg1 == seq}
