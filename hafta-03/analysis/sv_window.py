"""Hafta 3 izinden kısa pencere dosyası üretir (SystemView ekran görüntüsü için).

Dosya = izin başındaki senkron bloğu (görev listesi, sistem tanımı, modüller) + bir
mesajın SEND_BEGIN anına göre [başlangıç, bitiş] ms aralığındaki bütün paketler.

Kullanım: python sv_window.py <iz.SVDat> <mesaj_no> <başlangıç_ms> <bitiş_ms> <çıkış.SVDat>
"""
from __future__ import annotations

import sys
from pathlib import Path

from svdat import CPU_HZ, FIXED_U32, W3_BASE, _str, _u32

SYNC_INFO = {0, 9, 10, 12, 13, 14, 21, 22, 24, 25, 27}


def packets(b: bytes):
    """(başlangıç, bitiş, olay, zaman, parametreler)"""
    i = b.find(b"\x00" * 10)
    t = 0
    while i < len(b):
        start = i
        args: list[int] = []
        try:
            eid, i = _u32(b, i)
            if eid in FIXED_U32:
                for _ in range(FIXED_U32[eid]):
                    v, i = _u32(b, i)
                    args.append(v)
            elif eid in (9, 22):
                _, i = _u32(b, i)
                _, i = _u32(b, i)
                _, i = _str(b, i)
            elif eid == 14:
                _, i = _str(b, i)
            else:
                n, i = _u32(b, i)
                j = 0
                while j < n and len(args) < 3:
                    v, j = _u32(b[i:i + n], j)
                    args.append(v)
                i += n
            delta, i = _u32(b, i)
        except IndexError:
            return
        t += delta
        yield start, i, eid, t, args


def main(src: str, seq: int, from_ms: float, to_ms: float, dst: str) -> None:
    b = Path(src).read_bytes()
    pk = list(packets(b))
    t0 = next(p[3] for p in pk if p[2] == W3_BASE + 1 and len(p[4]) > 1 and p[4][1] == seq)
    lo, hi = t0 + from_ms * CPU_HZ / 1000, t0 + to_ms * CPU_HZ / 1000
    # Pencereden önceki bütün tanım paketleri (görev listesi, sistem tanımı, modüller):
    # tek seferlik kayıtta bunlar başlangıçtaki ilk olaylarla karışık gelir.
    head = [p for p in pk if p[3] < lo and p[2] in SYNC_INFO]
    body = [p for p in pk if lo <= p[3] <= hi]
    Path(dst).write_bytes(b"".join(b[s:e] for s, e, *_ in head + body))
    print(f"{dst}: {len(body)} packets, {to_ms - from_ms:.1f} ms")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5])
