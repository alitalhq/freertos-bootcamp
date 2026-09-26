"""Kart <-> PC seri protokolü: satır çerçeveleme, ayrıştırma ve CSV yazımı.

Arayüzden bağımsızdır; böylece kayıtlı kart çıktısıyla test edilebilir.
Protokol: hafta-01/docs/spec.md §3.4
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

MSG_LEN = 64                     # TEL/BTN satırları LF dahil tam 64 bayt
CSV_HEADER = ["scenario", "event_id", "t0_us", "t1_us", "t2_us", "t3_us", "t4_us", "status"]
U32 = 2 ** 32


class LineFramer:
    """Seri port veriyi parça parça verebilir; LF'e kadar biriktirip böler."""

    def __init__(self) -> None:
        self._buf = b""

    def feed(self, data: bytes) -> list[bytes]:
        self._buf += data
        *lines, self._buf = self._buf.split(b"\n")
        return [line + b"\n" for line in lines]


@dataclass
class Line:
    kind: str                    # TEL, BTN, LAB, CFG, REC, TSK, CNT, END, UNKNOWN
    fields: list[str]
    raw: bytes
    length_ok: bool = True       # yalnızca TEL/BTN için anlamlı


def parse_line(raw: bytes) -> Line:
    text = raw.decode("ascii", errors="replace").rstrip("\n").rstrip()
    parts = text.split(",")
    kind = parts[0] if parts[0] in {"TEL", "BTN", "LAB", "CFG", "REC", "TSK", "CNT", "END"} else "UNKNOWN"
    length_ok = len(raw) == MSG_LEN if kind in {"TEL", "BTN", "LAB"} else True
    return Line(kind, parts[1:], raw, length_ok)


def parse_kv(fields: list[str]) -> dict[str, str]:
    """CFG/CNT/TSK satırlarındaki anahtar=değer alanları."""
    out = {}
    for f in fields:
        if "=" in f:
            k, v = f.split("=", 1)
            out[k] = v
    return out


@dataclass
class Record:
    scenario: str
    event_id: int
    t: list[int | None]          # t0..t4; ölçülmediyse None (0 değil)
    status: str

    @staticmethod
    def diff(a: int | None, b: int | None) -> int | None:
        """uint32 farkı mod 2^32 (spec R-REC-3)."""
        return None if a is None or b is None else (b - a) % U32

    @property
    def r_us(self) -> int | None:
        return self.diff(self.t[0], self.t[4])


@dataclass
class Export:
    cfg: dict[str, str] = field(default_factory=dict)
    cnt: dict[str, str] = field(default_factory=dict)
    tasks: list[dict[str, str]] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)

    @property
    def scenario(self) -> str:
        return self.cfg.get("scenario", "S?")


class ExportCollector:
    """Deney sonu CFG ... END bloğunu toplar. END gelince Export döner."""

    def __init__(self) -> None:
        self._cur: Export | None = None

    @property
    def active(self) -> bool:
        return self._cur is not None

    def feed(self, line: Line) -> Export | None:
        if line.kind == "CFG" and self._cur is None:
            self._cur = Export()
        if self._cur is None or line.kind not in {"CFG", "REC", "TSK", "CNT", "END"}:
            return None

        exp = self._cur
        exp.raw_lines.append(line.raw.decode("ascii", errors="replace").rstrip("\n"))
        if line.kind == "CFG":
            exp.cfg.update(parse_kv(line.fields))
        elif line.kind == "CNT":
            exp.cnt.update(parse_kv(line.fields))
        elif line.kind == "TSK":
            exp.tasks.append({"name": line.fields[0], **parse_kv(line.fields[1:])})
        elif line.kind == "REC":
            f = line.fields
            ts = [int(x) if x else None for x in f[2:7]]
            exp.records.append(Record(f[0], int(f[1]), ts, f[7]))
        elif line.kind == "END":
            self._cur = None
            return exp
        return None


def write_export(exp: Export, out_dir: Path, overwrite: bool = False) -> tuple[Path, Path]:
    """Sx.csv (ham kayıtlar) ve Sx_meta.txt (CFG/TSK/CNT satırları) yazar.

    Eksik zaman damgası 0 değil boş bırakılır (spec R-REC-4). Var olan bir
    ölçüm dosyası sessizce ezilmez.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{exp.scenario}.csv"
    meta_path = out_dir / f"{exp.scenario}_meta.txt"
    if csv_path.exists() and not overwrite:
        raise FileExistsError(csv_path)

    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        for r in exp.records:
            w.writerow([r.scenario, r.event_id, *["" if t is None else t for t in r.t], r.status])

    meta_path.write_text("\n".join(line for line in exp.raw_lines if not line.startswith("REC")) + "\n")
    return csv_path, meta_path
