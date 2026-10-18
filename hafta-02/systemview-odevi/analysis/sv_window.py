"""Bir .SVDat izinden kısa bir pencere dosyası üretir (SystemView ekran görüntüsü için).

Dosya = izdeki ilk senkron bloğu (görev listesi, sistem tanımı, modüller) +
istenen zaman aralığındaki paketler. Paket sınırları svdat.py ile bulunur; pencere
içindeki zaman farkları korunur, yalnızca pencerenin başlangıç anı kayar.

Kullanım: python sv_window.py <iz.SVDat> <event_id> <önce_ms> <sonra_ms> <çıkış.SVDat>
  sonra_ms, olayın son BTN kaydından (TX_TC ya da DROP) itibarendir; "@25" gibi
  verilirse t0'dan (BTN_ACCEPT) itibarendir.
"""
from __future__ import annotations

import sys
from pathlib import Path

from svdat import BTN_BASE, CPU_HZ, FIXED_U32, _str, _u32

SYNC_INFO = {0, 9, 10, 12, 13, 14, 21, 22, 24, 25, 27}   # senkron bloğunu oluşturan olaylar


def packets(b: bytes):
    """(başlangıç, bitiş, olay, zaman, ilk_parametre) — ilk senkrondan itibaren."""
    i = b.find(b"\x00" * 10)
    t = 0
    while i < len(b):
        start = i
        try:
            eid, i = _u32(b, i)
            arg = 0
            if eid in FIXED_U32:
                for k in range(FIXED_U32[eid]):
                    v, i = _u32(b, i)
                    arg = v if k == 0 else arg
            elif eid == 9:
                _, i = _u32(b, i)
                _, i = _u32(b, i)
                _, i = _str(b, i)
            elif eid == 14:
                _, i = _str(b, i)
            elif eid == 22:
                _, i = _u32(b, i)
                _, i = _u32(b, i)
                _, i = _str(b, i)
            else:
                n, i = _u32(b, i)
                if n:
                    arg, _ = _u32(b[i:i + n], 0)
                i += n
            delta, i = _u32(b, i)
        except IndexError:
            return
        t += delta
        yield start, i, eid, t, arg


def main(src: str, event_id: int, before_ms: float, after: str, dst: str) -> None:
    b = Path(src).read_bytes()
    pk = list(packets(b))
    # İlk senkron bloğu: baştan, senkron dışı ilk pakete kadar
    k = 0
    while pk[k][2] in SYNC_INFO:
        k += 1
    head = b[pk[0][0]:pk[k][0]]
    mine = [p for p in pk if BTN_BASE <= p[2] < BTN_BASE + 6 and p[4] == event_id]
    t0, t_last = mine[0][3], mine[-1][3]
    lo = t0 - before_ms * CPU_HZ / 1000
    if after.startswith("@"):
        hi = t0 + float(after[1:]) * CPU_HZ / 1000
    else:
        hi = t_last + float(after) * CPU_HZ / 1000
    body = [p for p in pk if lo <= p[3] <= hi]      # ara senkronlar da kalır: zaman farkı taşırlar
    out = head + b"".join(b[s:e] for s, e, *_ in body)
    Path(dst).write_bytes(out)
    print(f"{dst}: {len(out)} bytes, {len(body)} packets, {(hi - lo) * 1000 / CPU_HZ:.1f} ms")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4], sys.argv[5])
