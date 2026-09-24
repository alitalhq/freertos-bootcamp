# ADR-002: Mikrosaniye zaman kaynağı — TIM2 (32-bit, 1 MHz)

**Durum:** Kabul edildi
**Tarih:** 24.09.2026
**Karar veren:** alitalhq
**İlgili gereksinimler:** R-HW-1, R-BTN-2, R-REC-3 (spec §2, §6)

## Bağlam

t₀…t₄ aynı kart saatinden alınacak. Ödev en az **1 µs** çözünürlük istiyor. t₀ ISR içinde okunuyor, bu yüzden
okuma hızlı, monoton ve ISR içinden güvenle yapılabilir olmalı. Farklar `uint32_t` ile (mod 2³²) hesaplanıyor.
Bu yöntemin güvenli olması için bir olayın süresi (≤ 1 s timeout) sayacın bir turundan çok kısa olmalı. CSV'deki
mutlak t değerlerinin okunabilir olması da işimizi kolaylaştırıyor.

## Karar

**TIM2**'yi serbest sayan bir sayaç olarak kullanıyoruz: PSC = 79 (80 MHz / 80 = 1 MHz), ARR = 0xFFFFFFFF.
Okuma `timer_us() { return TIM2->CNT; }` şeklinde.

## Değerlendirilen seçenekler

### Seçenek A: TIM2 @ 1 MHz ✅

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Düşük. CubeMX'te 3 ayar + `HAL_TIM_Base_Start` |
| Çözünürlük | 1 µs (ödevin alt sınırı) |
| Tur süresi | 2³² µs ≈ **71,6 dakika** |
| Okuma maliyeti | Tek yükleme komutu (APB1 erişimi, birkaç çevrim) |

**Artıları:** Değerler doğrudan µs cinsinden. Tur süresi bir deneyden çok uzun. L476'da TIM2 32-bit.
**Eksileri:** 1 µs çözünürlük, kısa aralıkları (t₂−t₁ gibi) kaba ölçüyor. Çözünürlük doğruluk garantisi değil.

### Seçenek B: DWT->CYCCNT (80 MHz çevrim sayacı)

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Düşük. DEMCR.TRCENA + CYCCNTENA |
| Çözünürlük | 12,5 ns |
| Tur süresi | 2³² / 80 MHz ≈ **53,7 s** |
| Okuma maliyeti | En düşük (çekirdek içi yazmaç) |

**Artıları:** En yüksek çözünürlük, çevre birimi gerektirmiyor.
**Eksileri:** Deney birkaç dakika sürdüğü için CSV'deki mutlak değerler sık sık tur atıyor ve okunması zorlaşıyor. µs'ye çevirmek için bölme gerekiyor. Çekirdek uyku modlarına girerse (WFI) sayma davranışı ayrıca doğrulanmalı.

### Seçenek C: FreeRTOS tick (`xTaskGetTickCount`)

| Boyut | Değerlendirme |
|---|---|
| Çözünürlük | 1 ms |
| Ödeve uygunluk | **Uygun değil** (< 1 µs şartı) |

### Seçenek D: TIM5 @ 1 MHz

TIM2 ile eşdeğer (L476'da o da 32-bit). TIM2 başka bir iş için gerekirse yedek olarak kalıyor.

## Ödünleşim analizi

B daha ince çözünürlük veriyor. Ama ödevin sorusu **milisaniye mertebesindeki** aşamalarla ilgili:
kuyruk beklemesi, preemption ve 5,56 ms'lik hat süresi. Bu aşamalar için 1 µs fazlasıyla yeterli. A, µs cinsinden
okunabilir ham veri ve 71 dakikalık tur süresiyle analizi basitleştiriyor. İnce çözünürlük ihtiyacı doğarsa
(örneğin ISR maliyetini ölçmek için) DWT, ana ölçüm zincirini değiştirmeden **ek araç** olarak kullanılabilir.

## Sonuçlar

- **Kolaylaşan:** CSV doğrudan µs cinsinden. Taşma hesabı basit. ISR'daki okuma ucuz.
- **Zorlaşan:** 1 µs altındaki olaylar (TXE ISR süresi gibi) bu kaynakla ölçülemez.
- **Tekrar bakılacak:** t₀ şu an ISR girişindeki okuma, fiziksel kenar değil. İleride butonu TIM2 input-capture kanalına (örn. PA0/PA15) jumper'la bağlayarak fiziksel kenar zamanını donanımla yakalamak mümkün. Bu ödevin kapsamı dışında, raporda sınırlama olarak yazılır.

## Aksiyonlar

1. [ ] CubeMX: TIM2 Internal Clock, PSC 79, ARR 4294967295. TIM2 kesmesi kapalı.
2. [ ] `timebase.c`: `timebase_init()` (başlatma) ve `timer_us()`.
3. [ ] F1 doğrulaması: `HAL_Delay(1000)` ≈ 1 000 000 µs ölçülmeli.
4. [ ] README'ye timer ayarlarını ve "çözünürlük ≠ doğruluk" notunu ekle.
