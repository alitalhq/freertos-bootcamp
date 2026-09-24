# ADR-003: Senaryo seçimi ve deney sonlandırma — derleme zamanı + otomatik bitiş

**Durum:** Kabul edildi
**Tarih:** 24.09.2026
**Karar veren:** alitalhq
**İlgili gereksinimler:** R-SCN-1, R-REC-5, R-TSK-2 (spec §7, §8)

## Bağlam

Her senaryoda şu akış tekrarlanacak: 5 s ısınma, en az 30 basış, telemetriyi durdurma, TX kuyruğunu boşaltma,
kayıtları dışarı aktarma (export). Ödevde üç kısıt var:

- Ana ölçüm sırasında MCU sayaçları sürekli yazdırılmayacak.
- Telemetri ve buton görevi UART'a dokunmayacak.
- "MCU tarafında ek komut görevi zorunlu değil."

Deneyin nasıl başlatılıp bitirileceğine karar vermemiz gerekiyor. Ekleyeceğimiz her mekanizma (RX kesmesi,
ek görev) ölçülen sisteme yük ekliyor.

## Karar

- **Senaryo seçimi derleme zamanında** yapılıyor: `App/app_config.h` içinde `#define SCENARIO n`. Her senaryo ayrı bir yüklemeyle koşuluyor.
- **Deney kendiliğinden bitiyor.** `TARGET_EVENTS` (varsayılan 35) kabul edilen basışa ulaşılınca ISR `experiment_done` bayrağını set ediyor. TelemetryTask üretimi durduruyor. UartTxTask kuyruğu boşaltıp `CFG → REC × N → CNT → END` export'unu **kendisi** yapıyor.
- LD2 durumu gösteriyor: sönük = ısınma, yanık = hazır, yanıp sönme = export.

## Değerlendirilen seçenekler

### Seçenek A: Derleme zamanı seçim + otomatik bitiş ✅

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Düşük |
| Ölçüme etkisi | Yok. Ek kesme ya da görev eklenmiyor |
| Tekrar üretilebilirlik | Yüksek. Senaryo, derlenen koda ve CFG satırına işleniyor |
| Kullanım kolaylığı | Orta. Her senaryo için yeniden yükleme gerekiyor (6 kez) |

**Artıları:** Ölçülen sistem ödevdeki 3 görevle birebir aynı kalıyor. UART'ın tek sahibi kuralı korunuyor.
**Eksileri:** Senaryo değiştirmek için yeniden derleme gerekiyor. Hedef sayı sabit, fazladan basış ekleyemiyoruz.

### Seçenek B: PC'den UART RX komutu (`S3`, `START`, `STOP`)

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Orta. RX kesmesi, satır ayrıştırma, durum makinesi |
| Ölçüme etkisi | Düşük ama sıfır değil. RX kesmesi ve olası ek görev |
| Tekrar üretilebilirlik | Yüksek (komutlar loglanırsa) |
| Kullanım kolaylığı | Yüksek. Tek yükleme, arayüzden yönetim |

**Artıları:** En iyi kullanım deneyimi. Video çekimi kolaylaşıyor.
**Eksileri:** Komutları işleyecek ek görev ya da ISR mantığı ödevin 3 görevli modelini değiştiriyor ve kapsamı büyütüyor.

### Seçenek C: Butona uzun basarak bitirme

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Orta. Bırakma kenarı ya da seviye takibi gerekiyor |
| Ölçüme etkisi | Buton ISR'ı ve filtre mantığı karmaşıklaşıyor |
| Ödeve uygunluk | Zayıf. "Sadece basış kenarını kullanın" kuralıyla çelişiyor |

## Ödünleşim analizi

A, **ölçülen sistemi ödev tanımıyla aynı tutmayı** kullanım kolaylığının önüne koyuyor. Yeniden yüklemenin
maliyeti (6 × ~20 s) küçük. B'nin eklediği RX yolu küçük olsa da raporda ayrıca açıklanması gereken bir
değişken olurdu. C, ödev kuralıyla çeliştiği için elendi.

## Sonuçlar

- **Kolaylaşan:** Temiz ölçüm modeli. Export'u UART sahibi yaptığı için eşzamanlılık sorunu yok.
- **Zorlaşan:** Deney sırasında senaryo değişmiyor. Yanlış senaryoyla yüklenen bir koşu tamamen tekrarlanmak zorunda. Bunu CFG satırındaki `scenario` alanıyla fark ediyoruz.
- **Tekrar bakılacak:** F8 sonrası zaman kalırsa B opsiyonel bir geliştirme olarak eklenir (spec §15 madde 3). Ana ölçümler yine A ile alınır.

## Aksiyonlar

1. [ ] `app_config.h`: `SCENARIO`, `TARGET_EVENTS`, `WARMUP_MS = 5000`, senaryo tablosu (periyot, iş süresi).
2. [ ] ISR: ısınma ve bitiş sonrası basışları `ignored_presses` olarak say.
3. [ ] UartTxTask: `experiment_done` + kuyruk boş → export durumu.
4. [ ] PC arayüzü: `CFG…END` bloğunu yakalayıp `measurements/Sx.csv` ve `Sx_meta.txt` olarak kaydet.
