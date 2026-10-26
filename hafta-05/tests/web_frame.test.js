// node --test tests/  : web kodlayıcısı host üreticisiyle aynı baytları üretiyor mu?
const test = require('node:test');
const assert = require('node:assert');
const F = require('../web/frame.js');
const v = require('./vectors.json');

test('CRC vektörleri', () => {
  for (const c of v.crc) assert.strictEqual(F.crc16(Buffer.from(c.ascii)), c.crc);
});

test('çerçeve vektörleri', () => {
  const made = [F.control(0, F.OP.STOP), F.control(1, F.OP.START), F.control(7, F.OP.SNAPSHOT),
    F.control(2, F.OP.SETPOINT, 1000), F.control(3, F.OP.STALL_NEXT, 80),
    F.frame(1, 0x01020304, Uint8Array.from([0xa5, 0x5a, 0x78]))];
  made.forEach((m, i) => assert.strictEqual(F.hex(m), v.frames[i].hex, v.frames[i].name));
});
