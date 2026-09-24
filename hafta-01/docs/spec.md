# Ödev 01 — Yük Altında Buton Yanıtı · Teknik Şartname (Spec)

> Kaynak: `Hafta_1_RTOS_Bootcamp/odev-01.html` (Erhan Konak, FreeRTOS Bootcamp, Hafta 1)
> Son teslim: **27 Eylül 2026 Pazar 11.00 (UTC+3)**. GitHub'a yüklenecek, Telegram'a depo linki + video gidecek.
> Kart: **NUCLEO-L476RG** (STM32L476RG, Cortex-M4F, 80 MHz, 128 KB RAM)

Bu doküman ödev metnini **uygulanabilir gereksinimlere** çevirir. Her gereksinimin bir kimliği var (`R-xx`).
Bu kimlikler kodda, testlerde ve raporda referans olarak kullanılacak. "Ödev standardı" olarak işaretli
maddeler değiştirilemez. Değiştirmek zorunda kalırsak nedeni README'ye yazılır.

---

## 1. Amaç

"Çalışıyor" demek yetmez. Butona basıldığında yanıtın **ne kadar sürede**, **hangi koşulda** ve **hangi
aşamada gecikerek** geldiğini gerçek kart ölçümüyle gösterip açıklamamız gerekiyor.

Teslim edilecekler:
1. FreeRTOS firmware'i: 3 uygulama görevi, buton ISR'ı, UART'ı yöneten tek görev.
2. PC arayüzü: UART telemetrisini ve buton yanıtını gösteren, CSV kaydeden, grafik çizen uygulama.
3. 6 senaryonun (S0–S5) ham ölçümleri, özet tablo, en az 2 grafik.
4. Analiz raporu: gecikme hangi aşamada ve neden değişti, hangi ölçüm bunu destekliyor, neyi henüz bilmiyoruz.
5. Dokümantasyon (setup, code-notes, ai-usage) ve kısa video.

**Değerlendirme ölçütleri:** kurulan sistem, ölçümün güvenilirliği, tekrar üretilebilirlik ve kendi
açıklamamız. Kartlar arasında mutlak süre yarışı yapılmıyor.

---

## 2. Donanım ve platform

| Öğe | Seçim | Not |
|---|---|---|
| Kart | NUCLEO-L476RG | |
| Buton | B1 (USER), **PC13**, aktif düşük | Basış = **düşen kenar** → EXTI15_10 |
| UART | **USART2**, PA2 (TX) / PA3 (RX) | ST-LINK Sanal COM Portu (VCP), ek kablo gerekmez |
| LED | LD2, **PA5** | Durum göstergesi (ısınma/hazır/export) |
| Sistem saati | **80 MHz** (MSI 4 MHz → PLL) | Raporlanacak |
| µs zaman kaynağı | **TIM2** (32-bit), PSC=79 → **1 MHz**, ARR=0xFFFFFFFF, serbest sayım | Çözünürlük 1 µs. ~71,6 dakikada bir tur atar |
| RTOS tick | **SysTick**, `configTICK_RATE_HZ = 1000` | |
| HAL timebase | **TIM6** | SysTick'i FreeRTOS kullandığı için HAL'e ayrı timer gerekir (CubeMX de bunu uyarır) |

**R-HW-1:** Tüm t₀…t₄ zaman damgaları aynı saatten, TIM2->CNT'den okunur. PC saati ile MCU saati
birbirinden **asla çıkarılmaz**.

---

## 3. Görev mimarisi

### 3.1 Görevler (ödev standardı)

| Görev | FreeRTOS önceliği | Sorumluluk | Bloklandığı yer |
|---|---|---|---|
| `TelemetryTask` | **3** (yüksek) | Periyodik TEL mesajı üretir, gerekirse kalibre CPU işi yapar, `txQ`'ya bırakır | `xTaskDelayUntil` (S0'da süresiz bekleme) |
| `ButtonTask` | **2** (orta) | `buttonQ`'dan olayı alır, BTN yanıtını üretir, `txQ`'ya bırakır | `xQueueReceive(buttonQ, portMAX_DELAY)` |
| `UartTxTask` | **1** (düşük) | UART'ın **tek sahibi**. `txQ`'yu FIFO sırasıyla tüketir, IT ile gönderir, TC'yi bekler | `xQueueReceive(txQ)` + `ulTaskNotifyTake` |
| Idle | 0 | Sayıya dahil değil | |

- **R-TSK-1:** Preemptive scheduling (`configUSE_PREEMPTION=1`), öncelik ilişkisi 3 > 2 > 1. `configMAX_PRIORITIES >= 4`.
- **R-TSK-2:** `TelemetryTask` ve `ButtonTask` UART'a **dokunmaz**. `printf` kullanmaz. Yalnızca `txQ`'ya mesaj bırakır.
- **R-TSK-3:** CubeMX'in otomatik ürettiği `defaultTask` **silinir**. CMSIS-RTOS v2 kullanılırsa onun önceliği
  (osPriorityNormal=24) bizim görevlerimizin üstünde kalır ve ölçümü bozar. Görevleri native API ile
  (`xTaskCreate`) 1/2/3 öncelikleriyle oluşturuyoruz.
- **R-TSK-4:** Timer servis görevi (`configUSE_TIMERS`) kullanılmıyorsa kapatılır. Açık kalırsa önceliği raporda belirtilir.
- **R-TSK-5:** `xTaskCreate` ve `xQueueCreate` dönüş değerleri kontrol edilir. Hata olursa `Error_Handler`'a gidilir.
- **R-TSK-6:** `configASSERT`, `configCHECK_FOR_STACK_OVERFLOW=2` ve `vApplicationMallocFailedHook` açık olur.

### 3.2 Veri akışı

```
 B1 (PC13) ──düşen kenar──► EXTI ISR ──ButtonEvent{id,t0}──► buttonQ (8)
                                                                 │
                                                                 ▼
                                   ButtonTask (P2): t1 … hazırla … t2
                                                                 │ TxMsg{BTN,id,64B}
 TelemetryTask (P3): [CPU işi] + TEL mesajı ─────────────────────┤
                                                                 ▼
                                                            txQ (16, FIFO)
                                                                 │
                                                                 ▼
                    UartTxTask (P1): t3 → HAL_UART_Transmit_IT → bekle
                                                                 │
                    USART2 TC kesmesi → HAL_UART_TxCpltCallback: t4, görevi uyandır
                                                                 │
                                                                 ▼
                                                        PC arayüzü (VCP)
```

### 3.3 Kuyruklar ve mesajlar (ödev standardı)

- **R-Q-1:** `buttonQ`: 8 eleman, `ButtonEvent { uint32_t id; uint32_t t0; }` (değer olarak kopyalanır).
- **R-Q-2:** `txQ`: 16 eleman, FIFO. Eleman: `TxMsg { uint8_t type; uint32_t event_id; char data[64]; }`,
  **değer olarak kopyalanır**. Yerel bir tamponun adresi kuyruğa konmaz.
- **R-Q-3:** Üreticiler `xQueueSend(txQ, &m, 0)` ile gönderir (beklemeden). Başarısız olursa drop sayılır
  (TEL ve BTN için ayrı sayaçlar tutulur). BTN drop olursa ilgili kaydın durumu `tx_drop` olur.
- **R-Q-4:** Kuyruk yüksek su seviyesi (high-water mark) izlenir. Her başarılı gönderimden sonra
  `uxQueueMessagesWaiting` ile en yüksek doluluk kaydedilir ve raporlanır.

### 3.4 Mesaj formatı (ödev standardı)

- **R-MSG-1:** Her TEL ve BTN mesajı tam **64 bayt**: ASCII metin, **boşlukla 63 bayta** tamamlanır, 64. bayt `\n` (LF).
- **R-MSG-2:** Metin 63 baytı aşıyorsa sessizce kesilmez: hata sayacı artırılır ve `configASSERT` tetiklenir.
- Formatlar:
  - `TEL,<seq>,<Sx>,<uptime_ms>` + boşluklar + `\n`
  - `BTN,<event_id>,<Sx>,PRESSED` + boşluklar + `\n`
- Export satırları (deney bittikten sonra gönderilir, 64 bayt kuralına tabi değildir ama LF ile biter):
  - `CFG,<anahtar>=<değer>,...`: saat, tick, senaryo, iterasyon sayısı gibi ayarlar
  - `REC,<Sx>,<id>,<t0>,<t1>,<t2>,<t3>,<t4>,<status>`: bilinmeyen alanlar boş bırakılır
  - `CNT,<ad>=<değer>,...`: sayaçlar
  - `END`

---

## 4. UART gönderimi (ödev standardı)

- **R-UART-1:** 115200 baud, 8N1, akış kontrolü yok.
- **R-UART-2:** Gönderim **interrupt (IT)** modunda yapılır (`HAL_UART_Transmit_IT`). Polling kullanılmaz.
  DMA'ya geçersek README'de belirtilir.
  - *Neden IT:* L4 HAL'de IT modunda `HAL_UART_TxCpltCallback`, son bitin hattan çıktığını gösteren
    **TC (Transmission Complete)** bayrağıyla çağrılır. Bu tam olarak t₄ için istediğimiz olaydır.
    Bedeli: bayt başına bir TXE kesmesi. Bu yükü raporda not ediyoruz.
- **R-UART-3:** `UartTxTask` akışı:
  1. `xQueueReceive(txQ, &m, portMAX_DELAY)`
  2. Mesajı statik `txBuf[64]` tamponuna kopyala. Tampon aktarım bitene kadar değişmez.
  3. BTN mesajıysa: `rec[id].t3 = timer_us()`, **HAL çağrısından hemen önce**.
  4. `HAL_UART_Transmit_IT(...)` → `HAL_OK` dönmezse durum `tx_error` olur, bir sonraki mesaja geçilir.
  5. `ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000))`
     - 0 dönerse (1 s geçti): `HAL_UART_AbortTransmit`, durum `timeout`. Görev sonsuza kadar beklemez.
- **R-UART-4:** `HAL_UART_TxCpltCallback` içinde: aktarılan mesaj BTN ise `rec[id].t4 = timer_us()` ve
  durum `ok`. Ardından `vTaskNotifyGiveFromISR` + `portYIELD_FROM_ISR`. Callback kısa tutulur.
- **R-UART-5:** `HAL_UART_ErrorCallback` hata sayacını artırır ve görevi uyandırır. O mesajın durumu `tx_error` olur.

**Hat kapasitesi hesabı** (8N1 → bayt başına 10 bit):
64 B × 10 bit / 115200 = **5,556 ms / mesaj**

| Telemetri | Hat doluluğu (yalnızca TEL) |
|---|---|
| 10 Hz | %5,6 |
| 50 Hz | %27,8 |
| 100 Hz | %55,6 |

BTN mesajları buna eklenir. CPU yüzdesi ile UART yüzdesi toplanmaz.

---

## 5. Buton ISR ve tekrar-kenar filtresi

- **R-BTN-1:** Yalnızca **basış kenarı** kullanılır (PC13, falling edge). Bırakma kenarı kullanılmaz.
- **R-BTN-2:** ISR'ın ilk satırı `now = TIM2->CNT` okumasıdır. Sonra kesme bayrağı temizlenir.
- **R-BTN-3:** 30 ms tekrar-kenar filtresi:
  - `first_edge` bayrağı ayrı tutulur. **İlk kenar her zaman kabul edilir**.
  - Son **kabul edilen** kenardan sonraki 30 ms içinde gelen kenarlar sayılır (`bounce_rejected++`) ve atılır.
  - Karşılaştırma `(uint32_t)(now - last_accepted) < 30000` şeklinde işaretsiz yapılır (sayaç taşmasına dayanıklı).
- **R-BTN-4:** Kabul edilen olay için `id = next_id++`, kayıt havuzunda `rec[id].t0 = now`, durum `pending` olur.
- **R-BTN-5:** `xQueueSendFromISR(buttonQ, …)` başarısız olursa kayıt `t0` ile korunur, durum `btn_drop` olur,
  `btn_q_drop++`. Sonra `portYIELD_FROM_ISR(wake)` çağrılır.
- **R-BTN-6:** ISR içinde bekleme yapılmaz, UART/printf kullanılmaz.
- **R-BTN-7 (NVIC):** `configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY = 5`. EXTI15_10 ve USART2 önceliği sayısal
  olarak **≥ 5** olmalı (örn. 6), aksi halde FromISR API'leri çağrılamaz. NVIC grouping 4 bit preemption.
  (ISR öncelikleri görev öncelikleriyle aynı şey değildir.)
- Isınma (5 s) ve deney bittikten sonra gelen basışlar olay olarak kabul edilmez. `ignored_presses` sayacına yazılır.

---

## 6. Zaman damgaları ve kayıt havuzu

### 6.1 Ölçüm noktaları (ödev standardı)

| Nokta | Nerede? | Kod yeri |
|---|---|---|
| t₀ | Buton ISR girişi, filtreden kabul edilen kenar | `EXTI15_10_IRQHandler` / `HAL_GPIO_EXTI_Callback` |
| t₁ | `ButtonTask`, `xQueueReceive` döndükten hemen sonra | `button_task.c` |
| t₂ | Yanıt için `xQueueSend(txQ)` çağrısından hemen önce | `button_task.c` |
| t₃ | `HAL_UART_Transmit_IT` çağrısından hemen önce | `uart_tx_task.c` |
| t₄ | UART TC tamamlanması işlenirken | `HAL_UART_TxCpltCallback` |

**R = t₄ − t₀**, deney deadline'ı **R ≤ 20 ms**. Gözetim (timeout) süresi **1 s**. Bu iki değer birbirine karıştırılmaz.

### 6.2 Kayıt yapısı

```c
typedef enum { ST_PENDING, ST_OK, ST_BTN_DROP, ST_TX_DROP, ST_TX_ERROR, ST_TIMEOUT } rec_status_t;
typedef struct {
    uint32_t t0, t1, t2, t3, t4;
    uint8_t  have;      /* bit maskesi: hangi t'ler geçerli (0 değeri "yok" demek değil) */
    uint8_t  status;
} EventRecord;
```

- **R-REC-1:** Havuz boyutu `REC_POOL_SIZE = 128` (ödev en az 64 istiyor; bir senaryoda ≥30 olay bekleniyor).
  Doğrudan `id` ile indekslenir. `id >= REC_POOL_SIZE` olursa `rec_overflow++`, olay yine işlenir ama kaydedilmez.
- **R-REC-2 (sahiplik):** Her alanı tek bir yazıcı yazar. t0 → ISR, t1/t2 → ButtonTask, t3 → UartTxTask,
  t4 → TC callback. 32-bit hizalı yazma Cortex-M4'te atomiktir. `have` ve `status` güncellemeleri kısa bir
  kritik bölgede yapılır (görevde `taskENTER_CRITICAL`, ISR'da `taskENTER_CRITICAL_FROM_ISR`).
- **R-REC-3:** Farklar `uint32_t` ile (mod 2³²) hesaplanır. Olay süresi bir sayaç turundan (71 dk) kısa olduğundan güvenlidir.
- **R-REC-4:** Eksik zaman **0 yazılmaz**. CSV'de boş bırakılır.
- **R-REC-5:** Ana ölçüm sırasında kayıtlar ve sayaçlar UART'a **basılmaz**. Yalnızca deney bitince export edilir.

### 6.3 Aşamaların anlamı (raporda aynen kullanılacak)

| Aralık | Anlamı | Dikkat |
|---|---|---|
| t₁ − t₀ | ISR → ButtonTask'ın olayı alması | Yüksek öncelikli görevin preemption'ı dahildir |
| t₂ − t₁ | Yanıt hazırlama | Duvar saati aralığıdır, CPU süresi değildir; preemption içerebilir |
| t₃ − t₂ | Kuyruğa verme + FIFO'da bekleme + UART başlatma öncesi | Saf FIFO beklemesi değildir |
| t₄ − t₃ | UART başlatma + hat aktarımı (~5,56 ms) + TC gözlemi | TXE ISR yükü dahildir |
| R = t₄ − t₀ | Kart tarafında gözlenen toplam yanıt süresi | t₀ fiziksel basma anı değildir |

---

## 7. Senaryolar ve yük üretimi

### 7.1 Zorunlu senaryolar (ödev standardı)

| ID | Telemetri | Ek CPU işi | Hesaplanan ek CPU talebi | TEL hat doluluğu |
|---|---|---|---|---|
| S0 | Kapalı | Yok | 0 | 0 |
| S1 | 10 Hz (100 ms) | Yok | ~0 | %5,6 |
| S2 | 50 Hz (20 ms) | Yok | ~0 | %27,8 |
| S3 | 100 Hz (10 ms) | Yok | ~0 | %55,6 |
| S4 | 100 Hz (10 ms) | ~2 ms | ≈ %20 | %55,6 |
| S5 | 100 Hz (10 ms) | ~5 ms | ≈ %50 | %55,6 |

- **R-SCN-1:** Senaryo derleme zamanında seçilir: `App/app_config.h` içinde `#define SCENARIO 3`.
  Her senaryo için yeniden derleyip yüklüyoruz. (Opsiyonel geliştirme: PC'den UART RX komutuyla seçim.)
- **R-SCN-2:** S0'da `TelemetryTask` **bloklanır** (`vTaskSuspend(NULL)` ya da süresiz notify bekleme).
  Boş döngüde dönmez.
- **R-SCN-3:** Periyot `xTaskDelayUntil` ile tutulur. Tick'e tam bölünür (1 kHz tick → 100/20/10 tick).
  Gerçek periyot (ardışık aktivasyonlar arası µs) min/ortalama/max olarak ölçülüp raporlanır.

### 7.2 Kalibre CPU işi (S4, S5)

- **R-WRK-1:** `calibrated_work(iterations)`: sabit iterasyonlu bir hesaplama (örn. xorshift/CRC döngüsü).
  Sonuç `volatile` bir global'e yazılır, böylece derleyici optimizasyonla silemez.
- **R-WRK-2:** Kesmeler kapatılmaz. `vTaskDelay` CPU yükü sayılmaz.
- **R-WRK-3 (kalibrasyon):** Açılışta, **scheduler başlamadan önce** (preemption yokken) N iterasyonun süresi
  TIM2 ile ölçülür ve 2000 µs / 5000 µs için gereken iterasyon hesaplanır. Sonuç `CFG` satırında raporlanır.
  Çalışma sırasında her işin gerçek duvar-saati süresi de min/max olarak tutulur.
- **R-WRK-4:** Kalibrasyon, teslim edilen **aynı derleme ayarıyla** (optimizasyon seviyesi) yapılır ve rapora yazılır.

---

## 8. Deney akışı (her senaryo için aynı sıra)

1. `SCENARIO` ayarlanır, derlenip yüklenir. Açılışta kayıtlar ve sayaçlar sıfırdır.
2. Açılış: kalibrasyon → `CFG` satırları → görevler başlar. **5 s ısınma** boyunca LD2 söner, basışlar yok sayılır.
3. LD2 yanık = hazır. **En az 30 basış** yapılır (varsayılan hedef `TARGET_EVENTS = 35`). Basışlar arasında
   en az 0,5 s olur ve aralıklar bilinçli olarak değiştirilir (ritmik basılmaz, telemetriyle faz kilitlenmesin).
4. Hedef sayıya ulaşılınca ISR `experiment_done` bayrağını set eder. `TelemetryTask` üretimi durdurur.
5. `UartTxTask` önce `txQ`'yu boşaltır. Beklemede kalan aktarımlar ya tamamlanır ya da `timeout` alır.
   Sonra **export** eder: `CFG` → `REC` × N → `CNT` → `END`. LD2 yanıp söner.
   (Export'u UART sahibi olan görev yapar, böylece R-TSK-2 bozulmaz.)
6. PC arayüzü export'u `measurements/Sx.csv` olarak kaydeder. Ham CSV **elle düzeltilmez**.

**Her kabul edilen olay şu durumlardan birinde biter:** `ok` · `btn_drop` · `tx_drop` · `tx_error` · `timeout`.
Sayaçlar ayrı ayrı raporlanır: kabul edilen, bounce_rejected, ignored_presses, btn_q_drop, tx_drop_tel,
tx_drop_btn, uart_error, timeout, rec_overflow, txQ_hwm, buttonQ_hwm, tel_sent, gerçek periyot min/ort/max,
iş süresi min/max.

---

## 9. PC arayüzü (`interface/`)

**Dil:** Python 3 + `pyserial` + Tkinter (GUI) + matplotlib (gömülü grafik). Bağımlılıklar `requirements.txt` dosyasında.

| # | Özellik | Kabul kriteri |
|---|---|---|
| UI-1 | Port listesi, bağlan/kes | Bağlanınca yeni satırlar akmaya başlar |
| UI-2 | LF ile çerçeveleme | Seri okuma parça parça gelebilir. Tampon biriktirilir, `\n` ile bölünür |
| UI-3 | 64 bayt doğrulama | TEL/BTN satırı 64 bayt değilse `format_error` sayacı artar |
| UI-4 | TEL / BTN ayrımı | TEL sayısı ve gerçek hız (Hz) gösterilir, BTN ayrı panelde listelenir |
| UI-5 | "Butona basıldı" | BTN gelince belirgin gösterge + senaryo + olay kimliği |
| UI-6 | Export alma | `REC` satırları `scenario,event_id,t0_us,t1_us,t2_us,t3_us,t4_us,status` başlığıyla `measurements/Sx.csv`'ye, `CFG`/`CNT` satırları `Sx_meta.txt`'ye yazılır |
| UI-7 | Grafik | Olay no → R, 20 ms çizgisi, kayıplar ayrı işaretle |

- **R-PC-1:** Arayüz ölçüme karışmaz. PC tarafı zaman damgası R hesabında **kullanılmaz**.
- Varsayılan port macOS'ta `/dev/cu.usbmodem*` olur.

---

## 10. Analiz (`analysis/`)

- `analysis/analyze.py`: `measurements/S0..S5.csv` dosyalarını okur, **aynı ham veriden** üretir:
  - `measurements/summary.csv`: senaryo başına: n_ok, n_eksik, R min/ortalama/max (ve p95), 20 ms aşan tamamlanmış
    yanıt sayısı, drop/tx_error/timeout/rec_overflow, aşama ortalamaları, txQ HWM, gerçek telemetri hızı.
  - `analysis/plots/response_per_event.png`: olay no → R (her senaryo), 20 ms deadline çizgisi.
  - `analysis/plots/stage_breakdown.png`: senaryo → aşama ortalamaları (yığılmış sütun).
  - (opsiyonel) senaryo başına R dağılımı (box/strip plot).
- **R-AN-1:** Grafiklerde birim, örnek sayısı (n) ve dışlanan kayıtlar yazılır.
- **R-AN-2:** Kayıp yanıtlar "deadline karşılandı" diye sayılmaz. Gözlenen maksimum "worst-case" diye sunulmaz.
- **R-AN-3:** Sentetik veri gerçek sonuç gibi sunulmaz. Depodaki tüm CSV'ler gerçek kart ölçümüdür.

### 10.1 Ölçmeden önce hipotezlerimiz (rapor bunları doğrulayacak ya da yanlışlayacak)

| Senaryo | Beklenti | Neden | Hangi aşama? |
|---|---|---|---|
| S0 | R ≈ 5,6–6 ms, düşük varyans | Hat boş, tek mesaj ~5,56 ms | t₄−t₃ baskın |
| S1→S3 | Ortalama ve max R artar, varyans büyür | BTN mesajı FIFO'da devam eden TEL aktarımının (≤5,56 ms) ve kuyruktaki TEL'lerin arkasında bekler | **t₃−t₂** büyür, t₁−t₀ ~sabit |
| S4 | t₁−t₀'da ~0–2 ms'lik dağılım görülür | Basış, P3'ün 2 ms'lik işine denk gelirse ButtonTask bekler | t₁−t₀ + t₃−t₂ |
| S5 | t₁−t₀ 5 ms'ye kadar çıkar. txQ dolabilir, TEL drop ve 20 ms ihlali görülebilir | P3 her periyotta 5 ms CPU alır, bu sırada P1 UartTxTask TC sonrası yeni aktarımı başlatamaz, hat boşta kalır → etkin UART kapasitesi düşer | t₁−t₀, t₃−t₂, HWM |

Fark çıkmaması başarısızlık sayılmaz, ama açıklanması gerekir.

---

## 11. Firmware dosya yapısı

CubeMX'in ürettiği kod (`Core/`, `Drivers/`, `Middlewares/`) yeniden üretilince bizim kodumuz silinmesin diye
uygulama kodu ayrı bir `App/` klasöründe durur:

```
firmware/
├── <CubeIDE projesi: .ioc, Core/, Drivers/, Middlewares/FreeRTOS, FreeRTOSConfig.h>
└── App/
    ├── app_config.h        SCENARIO, periyotlar, TARGET_EVENTS, REC_POOL_SIZE, eşikler
    ├── app.c / app.h       app_init(): kalibrasyon, kuyruklar, görevler; ISR/callback köprüleri
    ├── timebase.c / .h     TIM2 1 MHz, timer_us()
    ├── records.c / .h      EventRecord havuzu, sayaçlar, HWM
    ├── button.c / .h       EXTI callback, 30 ms filtre, buttonQ
    ├── button_task.c
    ├── telemetry_task.c
    ├── workload.c / .h     calibrated_work + kalibrasyon
    ├── uart_tx_task.c      txQ tüketimi, IT gönderimi, TC/hata callback'leri, export
    └── msg.c / .h          64 baytlık TEL/BTN mesajlarını oluşturma ve doldurma
```

`main.c` içindeki `USER CODE` bloklarına yalnızca `app_init()` çağrısı ve callback yönlendirmeleri eklenir.
**Teslim şartı:** `FreeRTOSConfig.h` dahil tüm kaynak ve proje dosyaları depoda olur. Tek başına binary yeterli değildir.

---

## 12. Uygulama planı (fazlar ve kabul kriterleri)

| Faz | İş | Kabul kriteri (bitti sayılması için) |
|---|---|---|
| **F0** Ortam | Toolchain + CubeMX projesi, 80 MHz saat, LD2 blink, USART2 "hello" | Kart yükleniyor, VCP'de metin görülüyor |
| **F1** Zaman tabanı | TIM2 1 MHz, `timer_us()` | 1 s'lik `HAL_Delay` ≈ 1 000 000 µs ölçülüyor |
| **F2** FreeRTOS iskeleti | FreeRTOS etkin, TIM6 HAL timebase, defaultTask silinmiş, 3 görev + 2 kuyruk, hook'lar | Scheduler çalışıyor, assert/overflow yok |
| **F3** UART sahibi | UartTxTask + IT + TC notify + timeout + 64 baytlık mesajlar | Test mesajları PC'ye tam 64 bayt ve kayıpsız ulaşıyor |
| **F4** Buton yolu | EXTI ISR, 30 ms filtre, kayıt havuzu, ButtonTask, t0…t4 | S0'da her basış 1 BTN mesajı üretiyor, kayıtlarda t0<t1<t2<t3<t4 |
| **F5** Yük | TelemetryTask, xTaskDelayUntil, kalibre iş, senaryo seçimi | Ölçülen periyot ve iş süresi hedefe yakın, CFG'de raporlanıyor |
| **F6** Export | Deney sonu akışı, CFG/REC/CNT/END | Export satırları eksiksiz ve ayrıştırılabilir |
| **F7** PC arayüzü | Tkinter + pyserial + CSV + canlı grafik | UI-1…UI-7 sağlanıyor |
| **F8** Deneyler | S0–S5, her birinde ≥30 kabul edilen olay | 6 CSV + meta dosyaları (toplam ≥180 olay) |
| **F9** Analiz | analyze.py, summary.csv, 2+ grafik, report.md | Hipotezler veriyle tartışılmış |
| **F10** Teslim | README, setup, code-notes, ai-usage, video, commit SHA | Teslim kontrol listesi (§13) tamam |

Sıralama bağımlılığı: F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 (F3'ten sonra paralel başlayabilir) → F8 → F9 → F10.

---

## 13. Teslim kontrol listesi (ödevden)

- [ ] Firmware ve arayüz kaynakları derlenip çalıştırılabiliyor
- [ ] S0–S5 ham ölçümleri, kayıp sayaçları ve `summary.csv` depoda
- [ ] Grafikler ve `analysis/report.md` ham veriye dayanıyor, grafik kodu depoda
- [ ] `docs/code-notes.md`: ISR, görevler, UART TC ve zaman hesapları **kod bloklarıyla** açıklanmış (ekran görüntüsüyle değil)
- [ ] `docs/ai-usage.md`: hangi işte destek alındı, nasıl doğrulandı, neyi değiştirdik ve neden
- [ ] README: kart, bağlantılar, araç sürümleri, derleme/yükleme, arayüzü başlatma, senaryo seçimi, timer/FreeRTOS ayarları, veri/grafik/rapor linkleri
- [ ] Depo eğitmene erişilebilir (özel depoysa davet gönderilmiş), teslim commit SHA'sı paylaşılmış
- [ ] Video: fiziksel basış, arayüzdeki yanıt, frekans değişimi, ölçüm yorumu
- [ ] Telegram: hafta bilgisi, kısa açıklama, GitHub linki ve video

---

## 14. Riskler ve dikkat edilecekler

| Risk | Önlem |
|---|---|
| CubeMX `defaultTask`'ı yüksek öncelikte bırakır | R-TSK-3: silinir |
| SysTick'i hem HAL hem FreeRTOS kullanır | HAL timebase TIM6'ya alınır |
| NVIC önceliği < 5 olursa FromISR çağrısında assert/hard fault olur | R-BTN-7 |
| `HAL_UART_TxCpltCallback` DMA modunda TC yerine başka bir anda çağrılabilir | IT modu kullanılır, TC yolu sürücüde doğrulanır |
| Buton sıçraması (bounce) çift olay üretir | 30 ms filtre + sayaç |
| Ritmik basış telemetriyle faz kilitlenir ve varyansı gizler | Rastgele aralıklarla basılır |
| Kalibre iş optimizasyonla silinir | volatile sink, ölçülen iş süresi raporlanır |
| Ölçüm sırasında log basmak zamanlamayı bozar | Yalnızca deney sonunda export |
| Stack taşması | overflow hook + `uxTaskGetStackHighWaterMark` raporu |

---

## 15. Kararlar

| # | Karar | Durum |
|---|---|---|
| 1 | Geliştirme ortamı: **STM32CubeIDE** (CubeMX, derleyici, ST-LINK ve debugger tek pakette) | ✅ 24.09.2026 |
| 2 | GitHub deposu: `freertos-bootcamp`, **public** | ✅ 24.09.2026 |
| 3 | PC'den UART RX ile senaryo seçme/başlatma (opsiyonel, ödev zorunlu tutmuyor) | ⏳ Zaman kalırsa yapılır |
