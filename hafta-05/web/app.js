/* Web Serial arayüzü. Kart satırları JSON; komutlar çerçeveli CONTROL. */
'use strict';
const $ = (id) => document.getElementById(id);
const F = window.Frame;
let transport = 'none';           // none | serial | demo
let port = null, reader = null, writer = null, demo = null;
let ctrlSeq = 0, session = null, lastSnapAt = 0, autoTimer = null;
const records = [];
const pending = new Map();        // seq -> {name, timer}

function log(dir, text, cls) {
  records.push({ time: new Date().toISOString(), mode: transport, session, dir, text });
  const el = document.createElement('div');
  if (cls) el.className = cls;
  el.textContent = `${new Date().toLocaleTimeString('tr-TR')} ${dir === 'tx' ? '→' : dir === 'rx' ? '←' : '!'} ${text}`;
  $('log').append(el);
  while ($('log').children.length > 300) $('log').firstChild.remove();
  $('log').scrollTop = $('log').scrollHeight;
}

function setMode() {
  const m = $('mode');
  m.className = 'badge ' + (transport === 'serial' ? 'hw' : transport === 'demo' ? 'demo' : '');
  m.textContent = transport === 'serial' ? 'GERÇEK KART' : transport === 'demo' ? 'DEMO · tarayıcı modeli, kart ölçümü değil' : 'Bağlı değil';
  $('connect').disabled = $('demo').disabled = transport !== 'none';
  $('disconnect').disabled = transport === 'none';
  document.querySelectorAll('[data-cmd]').forEach((b) => (b.disabled = transport === 'none'));
  $('banner').textContent = transport === 'none' ? 'Bağlantı yok. Gösterilen değerler güncel değil.' : '';
}

function clearView() {
  for (const id of ['state', 'lastSeq', 'setpoint', 'rem', 'cap', 'sbh', 'trg', 'eq1', 'eq2', 'rej', 'errs', 'to', 'gap',
    'jobs', 'done', 'jq', 'eq3', 'logs', 'smax', 'heap']) $(id).textContent = '—';
  $('state').className = 'state';
  $('fill').style.width = '0';
}

/* ---- kart satırları ---- */
const snap = {};
function onLine(text) {
  let d;
  try { d = JSON.parse(text); } catch { log('rx', text, 'err'); return; }
  if (d.t !== 'R' && d.t !== 'L') log('rx', text);
  switch (d.t) {
    case 'H':
      if (session !== null && d.sid !== session) { log('!', `yeni oturum ${d.sid} (önceki ${session}): eski değerler silindi`, 'err'); clearView(); }
      session = d.sid; $('sid').textContent = d.sid; $('fw').textContent = d.fw;
      break;
    case 'R': $('lastSeq').textContent = d.s; break;
    case 'P': case 'B': setRunning(false); settle(d.t === 'P' ? d.a : null); break;
    case 'G': setRunning(true); settle(d.a); break;
    case 'A': settle(d.a, d.c ? '' : 'reddedildi'); break;
    case 'V': $('setpoint').textContent = d.a; break;
    default:
      if (/^S\d$/.test(d.t)) { Object.assign(snap, d); if (d.t === 'S9') { renderSnap(); settleName('SNAPSHOT'); } }
  }
}

function setRunning(run) {
  $('state').textContent = run ? 'RUNNING' : 'STOPPED';
  $('state').className = 'state ' + (run ? 'run' : 'stopped');
}

function renderSnap() {
  const s = snap;
  lastSnapAt = Date.now();
  if (s.sid !== undefined && session !== null && s.sid !== session) { clearView(); session = s.sid; }
  setRunning(!!s.run);
  $('rem').textContent = s.rem; $('cap').textContent = s.cap; $('sbh').textContent = s.sbh; $('trg').textContent = s.trg;
  $('fill').style.width = `${(100 * s.rem / s.cap).toFixed(1)}%`;
  const ok = (a, b) => (a === b ? `${a} = ${b} ✓` : `${a} ≠ ${b} (akış sürüyor olabilir)`);
  $('eq1').textContent = ok(s.isr, s.acc + s.rej);
  $('eq2').textContent = ok(s.acc, s.rd + s.rem);
  $('eq3').textContent = ok(s.ja, s.jd + s.jx + s.jq + s.ji);
  $('rej').textContent = s.rej;
  $('errs').textContent = `${s.crc} / ${s.len} / ${s.hdr}`;
  $('to').textContent = s.to;
  $('gap').textContent = `${s.gap} / ${s.dup}`;
  $('jobs').textContent = `${s.ja} / ${s.jr}`;
  $('done').textContent = `${s.jd} / ${s.jx}`;
  $('jq').textContent = `${s.jq} / ${s.ji} / ${s.jqh}`;
  $('logs').textContent = `${s.ll} / ${s.ldr}`;
  $('smax').textContent = `${(s.smax / 1000).toFixed(3)} / ${(s.bmax / 1000).toFixed(3)} ms`;
  $('heap').textContent = `${s.heap} / ${s.hmin} B`;
}

/* ---- komutlar ve ACK zaman aşımı ---- */
function settle(seq, err) {
  const p = pending.get(seq);
  if (!p) return;
  clearTimeout(p.timer); pending.delete(seq);
  $('ackState').textContent = err ? `${p.name}: ${err}` : `${p.name}: ACK alındı`;
}
function settleName(name) { for (const [seq, p] of pending) if (p.name === name) settle(seq); }

async function send(name, arg) {
  const seq = ctrlSeq++;
  const bytes = F.control(seq, F.OP[name], arg);
  $('lastFrame').textContent = F.hex(bytes);
  pending.set(seq, { name, timer: setTimeout(() => { pending.delete(seq); $('ackState').textContent = `${name}: ACK zaman aşımı (1 s)`; log('!', `${name} seq=${seq} ACK zaman aşımı`, 'err'); }, 1000) });
  log('tx', `${name}${arg === undefined ? '' : ' ' + arg} seq=${seq} ${F.hex(bytes)}`);
  if (transport === 'serial') await writer.write(bytes); else demo.receive(name, seq, arg);
}

function number(id, lo, hi) {
  const v = Number($(id).value);
  if (!Number.isInteger(v) || v < lo || v > hi) throw Error(`${lo}–${hi} arasında tam sayı girin`);
  return v;
}

document.querySelectorAll('[data-cmd]').forEach((b) => (b.onclick = async () => {
  try {
    const c = b.dataset.cmd;
    await send(c, c === 'SETPOINT' ? number('spValue', 0, 1000) : c === 'STALL_NEXT' ? number('stallMs', 0, 200) : undefined);
  } catch (e) { log('!', e.message, 'err'); }
}));

/* ---- bağlantı ---- */
async function readLoop() {
  const dec = new TextDecoder();
  let buf = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n')) >= 0) { const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1); if (line) onLine(line); }
    }
  } catch (e) { log('!', `port koptu: ${e.message}`, 'err'); }
  if (transport === 'serial') await disconnect();
}

$('connect').onclick = async () => {
  if (!('serial' in navigator)) { log('!', 'Web Serial yok: Chrome/Edge kullanın', 'err'); return; }
  try {
    port = await navigator.serial.requestPort();
    await port.open({ baudRate: 230400 });
    reader = port.readable.getReader(); writer = port.writable.getWriter();
    transport = 'serial'; session = null; ctrlSeq = 0; clearView(); setMode();
    readLoop();
    await send('SNAPSHOT');                // açılışta HELLO/durum
    startAuto();
  } catch (e) { log('!', e.message, 'err'); }
};

$('demo').onclick = () => {
  transport = 'demo'; session = null; ctrlSeq = 0; clearView(); setMode();
  demo = new Demo(onLine); demo.hello(); startAuto();
};

async function disconnect() {
  const was = transport;
  transport = 'none';
  clearInterval(autoTimer);
  for (const p of pending.values()) clearTimeout(p.timer);
  pending.clear();
  if (was === 'serial') {
    try { reader && (await reader.cancel()); } catch {}
    try { reader && reader.releaseLock(); writer && writer.releaseLock(); await port.close(); } catch {}
  }
  setMode();
  log('!', 'bağlantı kapandı; ekrandaki değerler eski');
}
$('disconnect').onclick = disconnect;

function startAuto() {
  clearInterval(autoTimer);
  autoTimer = setInterval(() => {
    if (transport !== 'none' && $('auto').checked) send('SNAPSHOT').catch(() => {});
    $('snapAge').textContent = lastSnapAt ? `${((Date.now() - lastSnapAt) / 1000).toFixed(1)} s önce` : '—';
  }, 1000);
}

/* ---- dışa aktarma ---- */
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('jsonl').onclick = () => download(`hafta5-${transport}-kayit.jsonl`, records.map((r) => JSON.stringify(r)).join('\n') + '\n', 'application/x-ndjson');
$('csv').onclick = () => download(`hafta5-${transport}-kayit.csv`,
  'time,mode,session,dir,text\n' + records.map((r) => [r.time, r.mode, r.session, r.dir, `"${r.text.replace(/"/g, '""')}"`].join(',')).join('\n') + '\n', 'text/csv');

/* ---- DEMO: yalnız arayüzü denemek için; sayılar uydurma ---- */
class Demo {
  constructor(emit) { this.emit = emit; this.run = 1; this.sp = 0; }
  out(o) { setTimeout(() => this.emit(JSON.stringify(o)), 5); }
  hello() { this.out({ t: 'H', fw: 'DEMO', sid: 0, cap: 1024, trg: 1, baud: 230400, tick: 1000 }); }
  receive(name, seq, arg) {
    if (name === 'STOP') { this.run = 0; this.out({ t: 'P', a: seq, b: 0, c: 1 }); }
    else if (name === 'START') { this.run = 1; this.out({ t: 'G', a: seq, b: 0, c: 2 }); }
    else if (name === 'SNAPSHOT') {
      this.hello();
      const z = { sid: 0, cap: 1024, trg: 1, run: this.run, isr: 0, acc: 0, rej: 0, rd: 0, rem: 0, crc: 0, len: 0, hdr: 0, to: 0,
        gap: 0, dup: 0, ja: 0, jr: 0, jd: 0, jx: 0, jq: 0, ji: 0, jqh: 0, sbh: 0, ll: 0, ldr: 0, smax: 0, bmax: 0, heap: 0, hmin: 0 };
      ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8'].forEach((t) => this.out({ t, ...z }));
      this.out({ t: 'S9' });
    } else { if (name === 'SETPOINT') this.out({ t: 'V', a: arg }); this.out({ t: 'A', a: seq, b: F.OP[name], c: 1 }); }
  }
}

setMode();
