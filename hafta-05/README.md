# Hafta 05: StreamBuffer + Task Notification veri hattı

Çerçeveli UART verisini kesmeden StreamBuffer'a, parser'dan iş kuyruğuna, oradan cevap olarak aynı UART'a taşıyan bir sistem. Üç ayrı notification anlamı kullanılıyor: sayaç, olay bitleri ve mailbox. Tasarım ve cevaplar: [report.md](report.md).

> **Durum:** firmware, host testleri, web arayüzü ve birim testleri hazır. **Kart ölçümleri (T1–T9) henüz alınmadı**; `evidence/` boş. Raporda ölçüm gerektiren yerler "ölçülecek" diye işaretli.

## Mimari

```
UART RX ─ISR─▶ rxStream (256/512/1024 B) ─▶ Parser (3) ─Job kuyruğa + Give─▶ Execute (2)
                                              │                               │ Resp kuyruğa + bit
                                              ├─STOP/START/hata bitleri─▶ Control (4) ──▶ LED, ACK
                                              └─SETPOINT değeri──────────▶ Setpoint (1)
Log (1) ─▶ logMsgs (MessageBuffer 1024 B) ─┐                                   ▼
                                           └──────────────────────────▶ Tx (2) ─▶ txStream (128 B) ─ISR─▶ UART TX
B1 butonu ─EXTI ISR─▶ Control (STOP)
```

| Task | Öncelik | Ne bekliyor | Notification (indeks 1) |
|---|---|---|---|
| Control | 4 | olay bitleri | `eSetBits`: STOP_UART 0x01, START 0x02, STOP_BTN 0x04, UART_ERR 0x08, PROTO_ERR 0x10 |
| Parser | 3 | `xStreamBufferReceive` | (indeks 0 StreamBuffer'ın) |
| Execute | 2 | iş sayacı | `xTaskNotifyGiveIndexed` / `ulTaskNotifyTakeIndexed(pdFALSE)` |
| Tx | 2 | uyandırma bitleri | `eSetBits`: RESP, LOG, NOTE, SNAP |
| Setpoint | 1 | en güncel ayar | `eSetValueWithOverwrite` |
| Log | 1 | 10 ms periyot | — |

## Protokol

Giriş (host → kart), ödevdeki biçim: `A5 5A | VER 01 | TYPE (01 DATA, 02 CONTROL) | SEQ u32 LE | LEN u16 LE (0–48) | PAYLOAD | CRC16 LE`. CRC-16/CCITT-FALSE, VERSION..PAYLOAD üzerinde. `"123456789"` → `0x29B1`.

CONTROL opcode'ları:

| Op | LEN | Anlam |
|---|---|---|
| 01 / 02 / 03 | 1 | STOP / START / SNAPSHOT (aynı zamanda HELLO) |
| 04 | 5 | SETPOINT 0–1000 |
| 05 | 5 | STALL_NEXT 0–200 ms |
| **10** | 5 | *ek:* HOLD maskesi (1 Execute, 2 Control, 4 Setpoint; 0 bırak). T6 için alıcıyı bekletir |
| **11** | 1 | *ek:* STEP: Execute bir kez `Take(pdFALSE, 0)` yapar, dönüşü ve kalanı bildirir |
| **12** | 5 | *ek:* SETPOINT, `eSetValueWithoutOverwrite` ile (sonuç `W` satırında) |
| **13** | 5 | *ek:* trigger seviyesi 1 / 8 / 32 (parser kendi bağlamında, Receive dışında uygular) |
| **14** | 5 | *ek:* log yükü 0–40000 B/s |
| **15** | 5 | *ek:* RX kapasitesi 256 / 512 / 1024; SRAM2'ye yazılır, kart yeniden başlar |

Çıkış (kart → host): JSON satırları.

| `t` | Anlamı |
|---|---|
| `H` | HELLO: firmware, oturum kimliği, kapasite, trigger |
| `R` | Cevap: `s` SEQ, `c` checksum, `v` setpoint, `d` doğrulama→bitti µs, `q` doğrulama→txStream µs, `e`/`g` STOP/START sayısı (iş başladığında) |
| `A` | ACK: `a` SEQ, `b` opcode, `c` 1 kabul / 0 ret |
| `P` / `G` / `B` | UART STOP / START / buton STOP uygulandı; `b` t0→t1 µs, `c` bitler |
| `V` / `W` / `K` / `T` / `X` / `U` | Setpoint alındı / WithoutOverwrite sonucu / STEP sonucu / STALL uygulandı / protokol hatası / UART hatası |
| `S1`…`S9` | SNAPSHOT sayaçları (anahtarlar: [host/run_tests.py](host/run_tests.py) `equalities`) |
| `L` | Log satırı (yük) |

## Klasörler

| Klasör | İçerik |
|---|---|
| `firmware/` | CubeIDE projesi. Eğitmenin başlangıç paketinden; değişen dosyalar [firmware/KAYNAK.md](firmware/KAYNAK.md) |
| `host/` | `proto.py` (CRC, çerçeve, seed'li üretici), `link.py` (seri bağlantı), `run_tests.py` (T1–T9), `figures.py` (grafik + özet) |
| `tests/` | `test_protocol.py`, `web_frame.test.js` (ortak vektörler `vectors.json`), `check_evidence.py` (kabul kontrolü) |
| `web/` | Web Serial arayüzü (`index.html`), kart / demo ayrımı açık |
| `evidence/` | Her test için `raw.jsonl`, `sent.csv`, `manifest.json`, `result.json` (ölçülecek) |

## Kurulum ve çalıştırma

1. **Derle:** CubeIDE → *File → Import → Existing Projects into Workspace* → `hafta-05/firmware` → Debug derle. Komut satırından:

   ```sh
   STM32CubeIDE --launcher.suppressErrors -nosplash \
     -application org.eclipse.cdt.managedbuilder.core.headlessbuild \
     -data /tmp/ws -import hafta-05/firmware -cleanBuild 'RTOS_Hafta_5_L476RG/Debug'
   ```
2. **Yükle:** `STM32_Programmer_CLI -c port=SWD mode=UR -w hafta-05/firmware/Debug/RTOS_Hafta_5_L476RG.elf -v -rst`
3. **Kart gerektirmeyen testler:**

   ```sh
   python3 -m unittest discover hafta-05/tests
   node --test hafta-05/tests/web_frame.test.js
   ```
4. **Kart testleri:**

   ```sh
   pip install pyserial matplotlib
   P=/dev/cu.usbmodem103                     # Windows'ta COM4 gibi
   python3 hafta-05/host/run_tests.py --port $P T1 T2 T3 T4 T5 T6 T7 T8 T9
   python3 hafta-05/host/run_tests.py --port $P T7B   # B1'e en az 20 kez basın
   python3 hafta-05/host/figures.py
   python3 hafta-05/tests/check_evidence.py
   ```

   T8'in reset turu `STM32_Programmer_CLI` yolunu `run_tests.py` içindeki `CUBE_PROG`'dan okur.
5. **Web:** `hafta-05/web/index.html` dosyasını Chrome ya da Edge ile açın → *Karta bağlan*. Demo modu yalnız arayüzü denemek içindir; sayıları uydurmadır ve öyle etiketlidir.

## Kart ve sürümler

| | |
|---|---|
| Kart | NUCLEO-L476RG, 80 MHz, ST-LINK (kart üstü), macOS |
| Seri port | ST-LINK VCP, 230400 8N1 |
| RTOS | FreeRTOS 11.1.0, tick 1 kHz, heap_4 24 KB |
| Seed | 4526, Python `random.Random` (MT19937) |
| Derleme | STM32CubeIDE 2.2.0, Debug; 0 hata, 0 uyarı (`-Wall`, ayrıca `-Wextra` ile elle denendi) |
