/* Çerçeve kodlayıcı: host/proto.py ile aynı; tests/web_frame.test.js ortak vektörlerle sınar. */
(function (root) {
  'use strict';
  const OP = { STOP: 1, START: 2, SNAPSHOT: 3, SETPOINT: 4, STALL_NEXT: 5 };

  function crc16(bytes) {
    let crc = 0xffff;
    for (const b of bytes) {
      crc ^= b << 8;
      for (let i = 0; i < 8; i++) crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
    return crc;
  }

  function frame(type, seq, payload) {
    const body = new Uint8Array(8 + payload.length);
    const v = new DataView(body.buffer);
    body[0] = 0x01; body[1] = type;
    v.setUint32(2, seq >>> 0, true);
    v.setUint16(6, payload.length, true);
    body.set(payload, 8);
    const crc = crc16(body);
    return Uint8Array.from([0xa5, 0x5a, ...body, crc & 0xff, crc >> 8]);
  }

  function control(seq, op, arg) {
    if (arg === undefined) return frame(0x02, seq, Uint8Array.of(op));
    const p = new Uint8Array(5);
    p[0] = op;
    new DataView(p.buffer).setUint32(1, arg >>> 0, true);
    return frame(0x02, seq, p);
  }

  const hex = (b) => Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
  const api = { OP, crc16, frame, control, hex };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Frame = api;
})(typeof window !== 'undefined' ? window : globalThis);
