# Yapay Zekâ Kullanımı

**Araç:** Claude (Claude Code)

## Hangi işlerde destek alındı?

- Ödev metni ile eğitmenin sesli açıklamasının karşılaştırılması (ses kaydı yerel olarak metne çevrildi)
- Görev / kuyruk / notification mimarisinin tartışılması
- `firmware/src/app.c` taslağı
- Host üreticisi ve testler (`host/`, `tests/`)
- Web arayüzü
- README ve rapor taslakları

Mimari kararlar tartışılarak verildi:
- STOP'ta işleri saklama politikası;
- TX tamponunun küçük tutulması;
- ek kontrol komutları.

## Nasıl kontrol edildi?

- **Protokol:**
  - CRC `"123456789"` → `0x29B1` doğrulandı.
  - Host (Python) ve web (JS) kodlayıcıları aynı vektör dosyasıyla (`tests/vectors.json`) sınanıyor. Python 6/6, JS 2/2 geçti.
- **Derleme:**
  - CubeIDE Debug derlemesi 0 hata, 0 uyarı verdi.
  - `app.c` ayrıca `-Wall -Wextra` ile elle derlendi; uyarı yok.
  - `vendor/` budandıktan sonra temiz derleme yeniden geçti.
- **Stack:** `-fstack-usage` çıktısı okundu. En büyük çerçeve TxTask'ta 208 B.
- **Kart üzerinde:** T1–T9 kabul ölçütleri `host/run_tests.py` içinde kod olarak yazılı; `tests/check_evidence.py` sonuçları kontrol ediyor. *Kart ölçümleri henüz alınmadı.*

## Hangi öneriler değiştirildi, neden?

| Öneri | Neden yanlıştı | Sonuç |
|---|---|---|
| Yarım çerçeve timeout'u `xStreamBufferReceive(…, 100 ms)`'nin 0 dönmesiyle anlaşılsın | Trigger 8/32'de okuyucu her baytta uyanmaz. Süre "her yeni baytta yenilenmez"; az bayt gelirse 200 ms'ye kadar uzayabilir | UART ISR her baytta zaman damgası yazıyor. Parser, son bayttan beri kalan süre kadar bekliyor |
| Execute: `if (running) Take(…); işle` | `Take`'te bloklanmışken STOP uygulanır, sonra DATA gelirse iş STOP'tan sonra başlar | STOP kontrolü ve kuyruktan alma `vTaskSuspendAll` içinde tek adım; durdurulmuşsa sayaç geri veriliyor. `R` satırındaki `e`/`g` alanları bunu her cevapta kanıtlıyor |
| SNAPSHOT tek satırda 9 alan, 124 B tampon | En kötü durumda satır ~130 B. `snprintf` keser ama dönen uzunluk tamponu aşar; TX'e taşma yazılırdı | Satır başına en çok 6 alan, uzunluk `configASSERT` ile korunuyor |
| `HAL_UART_Receive_IT` ilk kez ParserTask içinde çağrılsın | Görev bağlamında `CR1` oku-değiştir-yaz yapılırken TX kesmesi `TXEIE`'yi değiştirebilir | RX, `app_init`'te (zamanlayıcı başlamadan, kesmeler maskeliyken) açılıyor. Görev bağlamında `CR1`'e yalnız kritik bölge içinde dokunuluyor |
