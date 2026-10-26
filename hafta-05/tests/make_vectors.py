"""Host üreticisinden ortak test vektörleri üretir (web/frame.js testleri de bunları kullanır)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "host"))
import proto  # noqa: E402

v = {
    "crc": [{"ascii": "123456789", "crc": proto.crc16_ccitt_false(b"123456789")},
            {"ascii": "", "crc": proto.crc16_ccitt_false(b"")}],
    "frames": [
        {"name": "STOP seq0", "hex": proto.control(0, proto.STOP).hex()},
        {"name": "START seq1", "hex": proto.control(1, proto.START).hex()},
        {"name": "SNAPSHOT seq7", "hex": proto.control(7, proto.SNAPSHOT).hex()},
        {"name": "SETPOINT 1000 seq2", "hex": proto.control(2, proto.SETPOINT, 1000).hex()},
        {"name": "STALL_NEXT 80 seq3", "hex": proto.control(3, proto.STALL_NEXT, 80).hex()},
        {"name": "DATA seq 0x01020304 'A5 5A x'", "hex": proto.frame(proto.DATA, 0x01020304, b"\xA5\x5Ax").hex()},
    ],
}
out = pathlib.Path(__file__).with_name("vectors.json")
out.write_text(json.dumps(v, indent=1) + "\n")
print(out)
