# ADR-001: UART gönderim yöntemi — Interrupt (IT)

**Durum:** Kabul edildi
**Tarih:** 24.09.2026
**Karar veren:** alitalhq
**İlgili gereksinimler:** R-UART-1…5, R-TSK-2 (spec §4)

## Bağlam

UART'ı yalnızca `UartTxTask` (öncelik 1) kullanıyor. Görev `txQ`'dan 64 baytlık mesajları FIFO sırasıyla alıp
gönderiyor. Ödev iki şey istiyor:

- Gönderim IT ya da DMA ile yapılacak, görev aktarım bitene kadar bloklanacak. Polling ana deneyde yasak.
- t₄, UART **TC (Transmission Complete)** olayı işlenirken kaydedilecek. "DMA bitti" ile "son bit hattan çıktı" aynı an değil.

Seçilen yöntem hem t₄'ün doğruluğunu hem de ölçüm sırasında CPU'ya binen ek yükü belirliyor.
100 Hz'de saniyede yaklaşık 100 TEL mesajı ve bunlara ek BTN mesajları gönderiliyor.
Her mesajın hatta kalma süresi 5,556 ms.

## Karar

Gönderimi **`HAL_UART_Transmit_IT`** ile yapıyoruz. `UartTxTask`, aktarım bitene kadar `ulTaskNotifyTake` ile
bekliyor. Bekleme 1 s sonra zaman aşımına uğruyor. `HAL_UART_TxCpltCallback` içinde t₄ kaydediliyor ve görev
`vTaskNotifyGiveFromISR` ile uyandırılıyor.

## Değerlendirilen seçenekler

### Seçenek A: Polling (`HAL_UART_Transmit`)

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Düşük |
| CPU yükü | Yüksek. Görev 5,56 ms boyunca meşgul-bekleme yapar |
| t₄ doğruluğu | Fonksiyonun dönüş anı bilinir, TC olayı görülmez |
| Ödeve uygunluk | **Uygun değil**. Ana deneyde yasak |

**Artıları:** En basit kod.
**Eksileri:** Ödev standardına aykırı. Ayrıca P1'in meşgul-beklemesi Idle'ı aç bırakır ve yük ölçümünü kirletir.

### Seçenek B: Interrupt (`HAL_UART_Transmit_IT`) ✅

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Düşük. Yalnızca USART2 NVIC kesmesi gerekir |
| CPU yükü | Her bayt için bir TXE kesmesi: 64 kesme/mesaj. 100 Hz'de ≈ 6 400 kesme/s |
| t₄ doğruluğu | L4 HAL son bayttan sonra TXEIE'yi kapatıp TCIE'yi açar. Callback **TC** ile çağrılır |
| Ekip deneyimi | HAL IT API'si iyi belgelenmiş, hata ayıklaması kolay |

**Artıları:** Kurulumu az. TC yolu doğrudan geliyor. Kesme akışı debugger'da kolay izleniyor.
**Eksileri:** Bayt başına kesme, ISR yükünü artırıyor. Bu süre görevlerin ölçülen aralıklarına (özellikle t₂−t₁ ve t₄−t₃) karışabiliyor.

### Seçenek C: DMA (`HAL_UART_Transmit_DMA`)

| Boyut | Değerlendirme |
|---|---|
| Karmaşıklık | Orta. DMA1 kanal ayarı, DMA IRQ önceliği (≥5) ve tampon ömrü yönetimi gerekir |
| CPU yükü | En düşük: mesaj başına birkaç kesme |
| t₄ doğruluğu | HAL, DMA tamamlanınca TCIE'yi açar ve callback yine TC ile gelir. Sürücüde doğrulanması gerekir |
| Ekip deneyimi | Daha az tanıdık, hata yüzeyi daha geniş |

**Artıları:** ISR yükü ölçümlere neredeyse hiç karışmıyor. Yüksek telemetri hızında en temiz yöntem.
**Eksileri:** Kurulum ve hata ayıklama maliyeti bir haftalık teslim süresinde risk. Ayrıca "DMA TC" ile "UART TC" karışıklığı ödevde özellikle uyarılan bir tuzak.

## Ödünleşim analizi

Asıl ödünleşim **ölçüm temizliği** ile **uygulama riski** arasında. IT'nin ek yükünü kabaca şöyle tahmin
ediyoruz: kesme başına ~1–3 µs × 6 400 kesme/s ≈ **%0,6–2 CPU**. Bu, S4 ve S5'teki %20 ve %50'lik bilinçli
yükün yanında küçük kalıyor. IT seçildiğinde TC yolu HAL tarafından garanti ediliyor. DMA ile aynı sonuca
ulaşmak için ek doğrulama gerekiyordu. Teslime bir hafta varken en kısa yoldan doğru t₄'e ulaşan seçenek B.

## Sonuçlar

- **Kolaylaşan:** TC tabanlı t₄. Ödevdeki "DMA bitti ≠ son bit" tuzağına baştan girilmiyor.
- **Zorlaşan:** Raporda TXE kesme yükünün ölçümlere etkisini açıklamamız gerekiyor. S5'te bu yük daha görünür olabilir.
- **Tekrar bakılacak:** S3–S5 sonuçlarında t₄−t₃, 5,56 ms'nin anlamlı ölçüde üstünde çıkarsa ya da ISR yükü ölçülebilir hale gelirse DMA'ya geçilir. Bu durumda README'de sapma nedeni yazılır.

## Aksiyonlar

1. [ ] CubeMX: USART2 global interrupt açık, NVIC önceliği 6.
2. [ ] `uart_tx_task.c`: statik `txBuf[64]`, t₃ → `HAL_UART_Transmit_IT` → `ulTaskNotifyTake(1 s)` → gerekirse timeout ve `HAL_UART_AbortTransmit`.
3. [ ] `HAL_UART_TxCpltCallback` / `HAL_UART_ErrorCallback`: t₄ ya da hata kaydı + notify.
4. [ ] F3 doğrulaması: t₄−t₃'ün S0'da ≈ 5,56 ms çıktığını gör. Mümkünse logic analyzer ile son biti karşılaştır.
5. [ ] Raporda TXE kesme yükünü tahmin edip bir cümleyle açıkla.
