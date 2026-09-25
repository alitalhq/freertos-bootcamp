# Yapay Zekâ Kullanımı

Ödevde yapay zekâ kullanımı serbest. Bu belge, hangi işlerde destek alındığını, üretilen içeriğin nasıl doğrulandığını ve nelerin değiştirildiğini anlatıyor.

**Kullanılan araç:** Claude (Claude Code, terminal üzerinden).

## Hangi işlerde destek alındı?

| Alan | Yapay zekânın yaptığı | Benim yaptığım |
|---|---|---|
| Şartname | Ödev metnini numaralı gereksinimlere (spec.md) ve fazlara dönüştürdü, 3 ADR yazdı | Gözden geçirdim, kararları onayladım (IDE, depo, dil kuralları) |
| CubeMX kurulumu | Hangi ayarın nerede yapılacağını adım adım anlattı, üretilen `.ioc` ve kodu dosyadan kontrol etti | Tüm ayarları CubeMX'te kendim yaptım |
| Firmware | `App/` altındaki kodun taslağını yazdı ve komut satırından derleyip karta yükledi | Her fazda karttaki davranışı gözledim, butona bastım |
| PC arayüzü | `protocol.py`, `monitor.py` ve testleri yazdı | Arayüzü kartla canlı test ettim |
| Ölçüm | Her senaryoyu derleyip yükledi, UART'ı dinleyip CSV'ye kaydetti | 6 × 35 basışı yaptım |
| Analiz | `analyze.py`, grafikler ve rapor taslağı | _(doldurulacak)_ |
| Dokümantasyon | README, setup, code-notes taslakları | _(doldurulacak)_ |

## Üretilen içerik nasıl doğrulandı?

Kod ya da iddia, kabul edilmeden önce kartta veya veriyle sınandı:

- **Donanım adımları (F0/F1):** SYSCLK = 80 MHz ve TIM2 1 MHz, UART çıktısında görüldü. `HAL_Delay(1000)` TIM2 ile ~1 000 367 µs ölçüldü.
- **UART sahibi (F3):** S1 ve S3'te 10 s'lik akışta her TEL satırının tam 64 bayt olduğu ve sıra numaralarında boşluk olmadığı kontrol edildi. S3'te ölçülen hat kullanımı 6 406 B/s ÷ 11 520 B/s = %55,6, hesapla birebir.
- **Ölçüm zinciri (F4):** 5 basışlık testte her kayıtta t₀ < t₁ < t₂ < t₃ < t₄. t₄−t₃ = 5 560 µs, hesaplanan 5 556 µs'ye uyuyor.
- **Yük (F5):** Butonsuz otomatik testte iş süresi (2 011 / 5 049 µs) ve periyot (9 993–10 002 µs) ölçüldü.
- **Arayüz (F7):** Protokol kodu gerçek kart çıktısıyla test edildi. Veri 1, 7, 64 ve 4096 baytlık parçalar halinde verildiğinde aynı sonuç çıktı. Arayüz kartla canlı denendi.
- **Rapor (F9):** Rapordaki sayılar ham CSV'den yeniden hesaplanıp karşılaştırıldı.

## Yapay zekânın hataları ve yapılan düzeltmeler

Süreçte yapay zekânın önerileri ya da iddiaları birkaç kez yanlış çıktı. Hepsi test ya da veriyle yakalandı:

| Hata | Nasıl yakalandı | Düzeltme |
|---|---|---|
| CubeMX'te `USE_TIMERS`'ın kapatılmasını önerdi | Ayar CubeMX'te gri, değiştirilemiyordu (CMSIS_V2 zorunlu tutuyor) | Açık bırakıldı, spec R-TSK-4 güncellendi |
| "Initialize peripherals: Yes" demenin yeterli olacağını varsaydı | Üretilen kodda PC13 **yükselen** kenardaydı ve BSP EXTI önceliğini 15'e eziyordu | BSP kapatıldı, pinler elle ayarlandı |
| FreeRTOS'un `xTaskDelayUntil` sağladığını varsaydı | Derleme hatası: FreeRTOS 10.3.1'de yok | `vTaskDelayUntil` kullanıldı |
| Export satır tamponunu 128 bayt seçti | S5 testinde export yarıda kaldı: satır 130 bayttı, `configASSERT` durdurdu | Satır bölündü, tampon 192 bayta çıkarıldı |
| Bir testin beklentisini yanlış yazdı (fixture'da 1 BTN var dedi, 2 vardı) | Test başarısız oldu, veriye bakıldı | Test düzeltildi (kod doğruydu) |
| S5 için "7 başarılı BTN = 7 kayıp TEL" dedi | Veriyle kontrol: olay 34 telemetri durduktan sonra geldi | Raporda "7'nin 6'sı açıklanıyor, 1'i bilinmiyor" olarak düzeltildi |
| Rapor taslağında S4 için "10 olay" yazdı | Ham veriden yeniden sayıldı: 9 | Düzeltildi |
| İlk S5 testinde bir düşüşü açıklayamadı (88 → 56 ms) | Resmi S5 ölçümünde son olayda aynı düşüş görüldü | Mekanizma bulundu: telemetri durunca kuyruk 5,56 ms/mesaj hızla eriyor |

## Kendi cümlelerimle

> _Bu bölüm bilerek boş bırakıldı. Ödev, kişinin öğrendiğini ve doğruladığını **kendi cümleleriyle** anlatmasını istiyor._

- **Bu kod neden böyle çalışıyor?** _(Örn. neden UART'ın tek sahibi var, neden t₀ ISR'ın ilk satırında alınıyor.)_
- **Hangi önerileri değiştirdim ya da reddettim, neden?** _(Örn. dil kuralları, S5 çözümlerini standart dışı ek deneye bırakma kararı.)_
- **Kendim neyi kontrol ettim?**
- **Nerede zorlandım?**
