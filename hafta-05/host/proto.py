"""Hafta 5 çerçeveli protokol: CRC, çerçeve kodlama ve seed'li üretici."""
import random
import struct

SYNC = b"\xA5\x5A"
VERSION = 0x01
DATA, CONTROL = 0x01, 0x02
MAX_PAYLOAD = 48

# CONTROL opcode'ları (01-05 ödev, 10-15 bu çözümün ek komutları; README'de)
STOP, START, SNAPSHOT, SETPOINT, STALL_NEXT = 0x01, 0x02, 0x03, 0x04, 0x05
HOLD, STEP, SETPOINT_NO_OVERWRITE, TRIGGER, LOG_RATE, RX_CAPACITY = 0x10, 0x11, 0x12, 0x13, 0x14, 0x15
HOLD_EXEC, HOLD_CONTROL, HOLD_SETPOINT = 1, 2, 4

SEED = 4526                      # öğrenci numarasının son 4 hanesi
PRNG = "Python random.Random (Mersenne Twister MT19937)"


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def frame(ftype: int, seq: int, payload: bytes, length: int | None = None) -> bytes:
    """length verilirse LEN alanına o yazılır (bilerek yanlış uzunluk testi için)."""
    body = struct.pack("<BBIH", VERSION, ftype, seq & 0xFFFFFFFF,
                       len(payload) if length is None else length) + payload
    return SYNC + body + struct.pack("<H", crc16_ccitt_false(body))


def control(seq: int, op: int, arg: int | None = None) -> bytes:
    payload = bytes([op]) if arg is None else bytes([op]) + struct.pack("<I", arg)
    return frame(CONTROL, seq, payload)


def checksum(payload: bytes) -> int:
    return sum(payload) & 0xFFFF


class Gen:
    """Aynı seed -> aynı payload ve bozulma kararları."""

    def __init__(self, seed: int = SEED, stream: str = ""):
        self.rng = random.Random(f"{seed}:{stream}")

    def payload(self, n: int, with_sync: bool = False) -> bytes:
        p = bytearray(self.rng.getrandbits(8) for _ in range(n))
        if with_sync:
            i = self.rng.randrange(0, n - 1)
            p[i:i + 2] = SYNC
        return bytes(p)

    def chunks(self, data: bytes, lo: int = 1, hi: int = 17):
        i = 0
        while i < len(data):
            n = self.rng.randint(lo, hi)
            yield data[i:i + n]
            i += n
