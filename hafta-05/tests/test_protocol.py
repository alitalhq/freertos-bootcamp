"""Protokol birim testleri (kart gerekmez):  python3 -m unittest discover tests"""
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "host"))
import proto  # noqa: E402


class Protocol(unittest.TestCase):
    def test_crc_check_value(self):
        self.assertEqual(proto.crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_frame_layout(self):
        f = proto.frame(proto.DATA, 0x01020304, b"\x10\x20\x30")
        self.assertEqual(f[:2], b"\xA5\x5A")
        self.assertEqual(f[2], 0x01)                       # VERSION
        self.assertEqual(f[3], proto.DATA)
        self.assertEqual(f[4:8], b"\x04\x03\x02\x01")     # SEQ little-endian
        self.assertEqual(f[8:10], b"\x03\x00")            # LEN little-endian
        self.assertEqual(len(f), 12 + 3)
        crc = proto.crc16_ccitt_false(f[2:-2])             # CRC: VERSION..PAYLOAD
        self.assertEqual(f[-2:], crc.to_bytes(2, "little"))

    def test_control_lengths(self):
        self.assertEqual(len(proto.control(0, proto.STOP)), 13)            # LEN=1
        self.assertEqual(len(proto.control(0, proto.SETPOINT, 0)), 17)     # LEN=5

    def test_seed_reproducible(self):
        a, b = proto.Gen(stream="T2"), proto.Gen(stream="T2")
        self.assertEqual([a.payload(32, True) for _ in range(5)], [b.payload(32, True) for _ in range(5)])
        self.assertNotEqual(proto.Gen(stream="T2").payload(32), proto.Gen(stream="T3").payload(32))

    def test_sync_inside_payload(self):
        p = proto.Gen(stream="x").payload(20, with_sync=True)
        self.assertIn(b"\xA5\x5A", p)

    def test_shared_vectors(self):
        v = json.loads((HERE / "vectors.json").read_text())
        for c in v["crc"]:
            self.assertEqual(proto.crc16_ccitt_false(c["ascii"].encode()), c["crc"])
        self.assertEqual(v["frames"][0]["hex"], proto.control(0, proto.STOP).hex())


if __name__ == "__main__":
    unittest.main()
