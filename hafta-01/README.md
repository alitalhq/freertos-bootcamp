# Hafta 01: Yük Altında Buton Yanıtı

Butona basıldığında "butona basıldı" yanıtının UART'tan ne kadar sürede çıktığını ölçüyoruz: **R = t₄ − t₀**. Telemetri hızı ve CPU yükü değiştikçe gecikmenin **hangi aşamada** ve **neden** değiştiğini gerçek kart ölçümleriyle açıklıyoruz.

| Belge | İçerik |
|---|---|
| [docs/spec.md](docs/spec.md) | Ödev metninden çıkarılan numaralı gereksinimler (R-xx), fazlar, kararlar |
| [docs/adr/](docs/adr/) | Mimari kararlar: UART IT (001), TIM2 zaman tabanı (002), deney akışı (003), lab modu ve S5 çözümleri (004) |
| [analysis/report.md](analysis/report.md) | **Analiz raporu**: sonuçlar, aşama analizi, hipotezler, ölçüm sınırları |
| [observations.md](observations.md) | Gözlemler: ne yaptım ve nasıl çalıştırılır, ne bekledim ve ne gözlemledim, çözüm olarak ne yaptım |
| [docs/code-notes.md](docs/code-notes.md) | ISR, görevler, UART TC ve zaman hesapları, kod bloklarıyla |
| [docs/setup.md](docs/setup.md) | CubeMX ayarları adım adım, karşılaşılan tuzaklar |
| [docs/ai-usage.md](docs/ai-usage.md) | Yapay zekâ kullanımı ve doğrulama |

## Sonuç özeti

Her senaryoda 35 basış yapıldı. R değerleri ms cinsinden, yalnızca yanıtı gelen olaylar için. Tam tablo: [measurements/summary.csv](measurements/summary.csv).

Resmi ölçümler `2dd9b59` commit'indeki firmware ile alındı. Güncel resmi derleme (`APP_LAB_MODE 0`) aynı davranışı veriyor: 26.09.2026'daki regresyon testinde S5 telemetri periyodu, CPU işi ve buton yanıtlarındaki birikim deseni µs düzeyinde aynı çıktı.

| Senaryo | Telemetri | Ek CPU işi | Yanıt | R ort | R max | > 20 ms | Değişen aşama |
|---|---|---|---|---|---|---|---|
| S0 | kapalı | – | 35/35 | 5,67 | 5,67 | 0 | (referans: %98'i hat süresi) |
| S1 | 10 Hz | – | 35/35 | 5,88 | 9,80 | 0 | t₃−t₂ TX öncesi bekleme |
| S2 | 50 Hz | – | 35/35 | 6,31 | 10,72 | 0 | t₃−t₂ |
| S3 | 100 Hz | – | 35/35 | 7,30 | 11,29 | 0 | t₃−t₂ |
| S4 | 100 Hz | ~2 ms | 35/35 | 8,57 | 13,26 | 0 | + t₁−t₀ görev beklemesi |
| S5 | 100 Hz | ~5 ms | **23/35** | **109,5** | **164,0** | **22** | t₃−t₂ birikimli, txQ 16/16 dolu |

- **Frekans arttıkça (S0→S3)** yalnızca TX öncesi bekleme (t₃−t₂) büyüyor. BTN yanıtı, hatta o an giden 5,56 ms'lik TEL mesajının bitmesini bekliyor.
- **CPU yükü eklenince (S4, S5)** görev beklemesi (t₁−t₀) de büyüyor. ButtonTask, öncelik 3'teki telemetri işinin bitmesini bekliyor.
- **S5'te iki yük birleşiyor.** En düşük öncelikli UART görevi periyot başına yalnızca 1 mesaj başlatabiliyor, bu da telemetri üretimine tam eşit. Her BTN yanıtı kalıcı birikim yaratıyor. Kuyruk dolunca yanıtlar kayboluyor. Ayrıntı: [rapor §4.4](analysis/report.md#44-s5-iki-yük-birleşince-kapasite-sıfıra-iniyor).

![Olay başına yanıt süresi](analysis/plots/response_per_event.png)

### Standart dışı ek deney: S5'i çözmek

Kök neden ölçümle doğrulandı ve giderildi ([rapor §8](analysis/report.md#8-standart-dışı-ek-deney-s5i-çözmek), [ADR-004](docs/adr/ADR-004-lab-modu-ve-cozumler.md)). Aynı S5 yükünde, 35 otomatik basışla:

| Varyant | Yanıt | Max R | > 20 ms |
|---|---|---|---|
| Standart (ödev) | 24/35 | 164,7 ms | 24 |
| Naif: ButtonTask önceliği ↑ | 35/35 | 164,7 ms | **34** |
| Kök neden: UartTxTask önceliği ↑ | 35/35 | 16,3 ms | 0 |
| **Optimal: UartTxTask + ButtonTask, CPU işinin üstünde** | **35/35** | **10,3 ms** | **0** |

Bu sonuçlar lab derlemesiyle (`APP_LAB_MODE 1`) alındı. Zorunlu S0–S5 ölçümleri standart derlemeyle alındı ve bu ek deneyden etkilenmiyor.

![S5 çözümleri](analysis/plots/lab_fixes.png)

## Depo yapısı

```
hafta-01/
├── README.md, observations.md
├── firmware/odev01/        STM32CubeIDE projesi
│   ├── odev01.ioc          CubeMX yapılandırması
│   ├── Core/, Drivers/, Middlewares/   CubeMX üretir (FreeRTOSConfig.h: Core/Inc)
│   └── App/                uygulama kodu: görevler, ISR, kayıtlar, export
├── interface/              PC arayüzü (Python): monitor.py, protocol.py, tests/
├── measurements/           S0–S5 ham CSV + meta, summary.csv
├── analysis/               analyze.py, report.md, plots/
└── docs/                   spec, ADR'ler, kurulum, kod notları, AI kullanımı
```

## Kart, bağlantılar ve araç sürümleri

| | |
|---|---|
| Kart | NUCLEO-L476RG (STM32L476RG, Cortex-M4F) |
| Bağlantı | Yalnızca USB (ST-LINK). Ek kablo gerekmiyor |
| Buton | B1 (USER, mavi): **PC13**, aktif düşük, düşen kenar → EXTI15_10 |
| UART | **USART2** PA2/PA3 → ST-LINK sanal COM portu (macOS: `/dev/cu.usbmodem*`) |
| LED | LD2: **PA5**. Sönük = ısınma, yanık = deney sürüyor, yanıp sönme = export |

| Araç | Sürüm |
|---|---|
| STM32CubeIDE | 2.2.0 (GNU Tools for STM32 14.3.rel1) |
| STM32CubeMX | 6.18.1 (CubeIDE 2.x'te ayrı uygulama) |
| STM32Cube FW_L4 | V1.18.2 (FreeRTOS **V10.3.1**, CMSIS-RTOS v2) |
| STM32CubeProgrammer | 2.23.0 · ST-LINK FW V2J48M35 |
| Python | 3.13.5 · pyserial 3.5 · matplotlib 3.10.8 |
| İşletim sistemi | macOS 26.6 |

## Derleme ve yükleme

1. STM32CubeIDE → File → Import → General → **Existing Projects into Workspace** → `hafta-01/firmware/odev01`.
2. Senaryoyu seç: `App/app_config.h` → `#define SCENARIO n` (0…5). Varsayılan 1.
3. **Build** (Debug), ardından kart USB'deyken **Run**.

`TEST_AUTO_STOP_MS` yalnızca geliştirme testleri için var. Ölçüm derlemelerinde tanımlı **olmamalı**. Varsayılan hali yorum satırı.

## Arayüzü başlatma

```bash
cd hafta-01/interface
pip install -r requirements.txt
python monitor.py                 # grafik arayüz
python monitor.py --headless      # arayüzsüz: END'e kadar dinler, measurements/'a kaydeder
python -m pytest tests            # protokol testleri (gerçek kart çıktısıyla)
```

Arayüz şunları yapıyor:
- Port seçimi ve bağlanma.
- TEL/BTN ayrımı, 64 bayt kontrolü.
- **"Butona basıldı"** göstergesi.
- Deney sonu export'unu `measurements/Sx.csv` + `Sx_meta.txt` olarak kaydetme. Var olan dosyayı ezmiyor, zaman damgalı yeni adla kaydediyor.
- R grafiği.

R, yalnızca kartın t₀…t₄ damgalarından hesaplanıyor; PC saati kullanılmıyor.

## RTOS Lab arayüzü (standart dışı)

`interface/lab_app.py`: karta doğrudan bağlanan, deney koşturan ve sonuçları analiz eden masaüstü uygulaması (PySide6).

```bash
cd hafta-01/interface
pip install -r requirements.txt
python lab_app.py
```

Türkçe arayüz, koyu tema (sol üstten açık temaya geçilebilir). Solda deneme listesi, sağda seçili denemenin başlığı ve tek işli sekmeler:

| Sekme | Ne gösterir |
|---|---|
| **Özet** | Bir cümlelik sonuç, olay başına R grafiği, zamanın aşamalara dağılımı ve teşhis |
| **Neden geç kaldı?** | Olay listesi (geç ve kayıp olanlar üstte). Seçilen olayın aşama dökümü, 20 ms payı ve ölçümden çıkarılan neden |
| **Karşılaştır** | İşaretlenen denemelerin aşama ortalamaları yan yana, özet tablo |
| **Kayıtlar** | Olay bazında tablo, kartın gönderdiği CFG/CNT/TSK değerleri |
| **Yeni deney** | 1 · Kart, 2 · Yük (senaryo ya da özel periyot + CPU işi), 3 · Çözüm (standart / naif / kök neden / optimal), 4 · Basışlar (otomatik ya da elle, olay sayısı). **Deneyi başlat** dediğinde kart bu ayarlarla yeniden başlar, 5 s ısınır, basışları toplar ve kayıtları gönderir. Sonuç Özet sekmesinde açılır |
| **Rehber** | Ölçüm, S5'in neden başarısız olduğu ve çözümler |

- **Açılışta** resmi S0–S5 ölçümleri ve S5 çözüm denemeleri yüklü gelir. Kart bağlı olmasa da incelenebilir.
- **Kendi deneyin için** karta bir kez lab derlemesini yükle: `App/app_config.h` → `#define APP_LAB_MODE 1`, derle, yükle.
- **Kayıt:** Sol alttaki **CSV kaydet** (ödev formatı + meta), **Ham kaydet** (ham UART baytları), **Aç…** (ikisini de açar).

Komut satırından aynı deneyler: `python labctl.py run --preset S5 --fix optimal --inject auto`.

## Senaryo seçimi ve ölçüm adımları

Her senaryo için:
1. `SCENARIO`'yu ayarla, derle, yükle.
2. Arayüzü bağla (ya da `--headless` başlat). Kartın siyah RESET butonuna bas.
3. **5 s ısınma** bekle. Bu sürede LD2 sönük ve basışlar sayılmıyor.
4. LD2 yanınca **35 kez** bas. Aralarında ≥ 0,5 s bırak ve aralıkları değiştir.
5. 35. basıştan sonra telemetri durur, TX kuyruğu boşalır ve kart `CFG → REC × 35 → TSK → CNT → END` gönderir. Arayüz bunu kaydeder.
6. Tüm senaryolardan sonra: `python analysis/analyze.py` → `summary.csv` ve grafikler.

Her kabul edilen olay şu durumlardan biriyle biter: `ok`, `btn_drop`, `tx_drop`, `tx_error` ya da `timeout`. Sayaçlar `Sx_meta.txt` dosyasında.

## Timer ve FreeRTOS ayarları

| Ayar | Değer |
|---|---|
| SYSCLK | 80 MHz (HSI16 → PLL M=1 N=10 R=2) |
| µs zaman kaynağı | TIM2 32-bit, PSC 79 → 1 MHz, ARR 0xFFFFFFFF, serbest sayım, kesme yok. ~71,6 dk'da bir tur atar; farklar mod 2³² |
| HAL timebase | TIM6 (SysTick FreeRTOS'ta) |
| FreeRTOS | preemptive, tick 1000 Hz, `configMAX_PRIORITIES` 56, heap_4 20 000 B, `configCHECK_FOR_STACK_OVERFLOW` 2, malloc-failed hook, `configASSERT` açık |
| Görevler | TelemetryTask 3 · ButtonTask 2 · UartTxTask 1 · Idle 0 · Tmr Svc 2 (uykuda) |
| NVIC | grouping 4; `LIBRARY_MAX_SYSCALL` 5; EXTI15_10 = 6, USART2 = 6; TIM6/SysTick/PendSV = 15 |
| Derleme | Debug, `-O0`. CPU işi aynı derlemeyle kalibre edildi |

## Ödev standardından sapmalar ve notlar

| Konu | Açıklama |
|---|---|
| `xTaskDelayUntil` → `vTaskDelayUntil` | CubeMX paketindeki FreeRTOS 10.3.1'de `xTaskDelayUntil` yok, 10.4 ile geldi. Davranış aynı: mutlak periyot tabanı |
| Timer servis görevi açık | CMSIS-RTOS v2 arayüzü `USE_TIMERS`'ı zorunlu tutuyor. Yazılım timer'ı kullanılmadığı için görev hep uykuda |
| `defaultTask` kendini siliyor | CubeMX silmeye izin vermedi. Öncelik Low'a indirildi, görev ilk satırında `vTaskDelete(NULL)` çağırıyor |
| Board BSP kapalı | CubeMX'in NUCLEO BSP'si EXTI önceliğini 15'e eziyor ve kendi callback'ini tanımlıyordu. Kapatıldı, PC13/PA5 normal GPIO olarak ayarlandı ([setup.md](docs/setup.md)) |

| Lab derlemesi | `APP_LAB_MODE 1`: UART komut kanalı, otomatik basış ve çözüm varyantları (`#ifdef ENABLE_FIX_*`). Yalnızca rapor §8 ve lab arayüzü için. Varsayılan 0 |

Zorunlu S0–S5 ölçümlerinde ödevin **standart ayarlarının** hiçbiri değiştirilmedi: 115200 8N1, 64 bayt, kuyruklar 8/16 FIFO, IT + TC'ye kadar blok, öncelikler 3 > 2 > 1, deadline 20 ms.
