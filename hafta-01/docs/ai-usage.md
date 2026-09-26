# Yapay Zekâ Kullanımı

**Araç:** Claude (Claude Code)

## Hangi işlerde destek alındı?

- Ödev metninin numaralı gereksinimlere ([spec.md](spec.md)) ve karar kayıtlarına (ADR) dönüştürülmesi
- CubeMX yapılandırması ve firmware kodu (`App/`)
- PC arayüzü, protokol ayrıştırma ve testler (`interface/`)
- Analiz betiği, grafikler ve rapor taslağı
- Hata analizi: S5'teki birikimli gecikmenin kök nedeni ve çözüm denemeleri
- README ve doküman taslakları

## Üretilen kod ve sonuçlar nasıl kontrol edildi?

Hiçbir kod ya da iddia doğrudan kabul edilmedi. Her adım kartta ya da ham veriyle sınandı:

- **Donanım:** SYSCLK 80 MHz ve TIM2 1 MHz UART çıktısında görüldü. `HAL_Delay(1000)` TIM2 ile ~1 000 367 µs ölçüldü.
- **UART:** 100 Hz'de her mesajın tam 64 bayt olduğu ve sıra numaralarında boşluk olmadığı kontrol edildi. Ölçülen hat kullanımı (%55,6) hesapla birebir tuttu.
- **Ölçüm zinciri:** Her kayıtta t₀ < t₁ < t₂ < t₃ < t₄ sırası kontrol edildi. t₄−t₃ = 5 560 µs, hesaplanan hat süresine (5 556 µs) uyuyor.
- **Arayüz:** Protokol kodu gerçek kart çıktısıyla test edildi. Veri farklı parça boyutlarında verildiğinde de aynı sonucu verdi. Arayüz kartla canlı denendi.
- **Rapor:** Rapordaki sayılar ham CSV'den yeniden hesaplanıp karşılaştırıldı.

## Hangi öneriler değiştirildi, neden?

Kontroller sırasında birkaç öneri ya da iddia yanlış çıktı ve düzeltildi:

| Öneri / iddia | Neden yanlıştı | Sonuç |
|---|---|---|
| CubeMX'te `USE_TIMERS` kapatılsın | CMSIS_V2 bu ayarı zorunlu açık tutuyor | Açık bırakıldı |
| Kart varsayılanlarıyla başlamak yeterli | BSP buton kesmesini yükselen kenara kuruyor ve önceliğini eziyordu | BSP kapatıldı, pinler elle ayarlandı |
| `xTaskDelayUntil` kullanılsın | FreeRTOS 10.3.1'de yok, derleme hatası verdi | `vTaskDelayUntil` kullanıldı |
| Export satırı için 128 bayt yeter | S5'te 130 baytlık satır export'u durdurdu | Satır bölündü, tampon 192 bayta çıkarıldı |
| "7 başarılı yanıt = 7 kayıp telemetri" | Veriyle karşılaştırıldığında 7'den yalnızca 6'sı açıklanıyordu | Rapora "6'sı açıklanıyor, 1'i bilinmiyor" olarak yazıldı |
| "UART önceliğini yükseltmek telemetriyi etkilemez" | Ölçüm: iş süresi +36 µs, periyot sapması ±110 µs | Bedel ölçülen değerlerle yazıldı |
| Rapordaki bazı sayılar | Ham veriden yeniden sayıldığında farklı çıktı | Düzeltildi |

Tasarım kararları da öneriler arasından seçildi ya da değiştirildi:
- Zorunlu S0–S5 ölçümleri standart ayarlarla alındı. Çözüm denemeleri ayrı bir derlemeye (`APP_LAB_MODE`) ayrıldı.
- Yedi çözüm varyantından tekrar edenler çıkarıldı, dört tanesi tutuldu.
- Arayüz birkaç kez yeniden düzenlendi: önce referanstan farklı bir düzen, sonra Türkçe metinler ve koyu tema, en son tek işli sekmeler.
