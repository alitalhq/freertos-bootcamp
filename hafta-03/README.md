# Hafta 03: Queue, kapasite ve gönderme beklemesi

Kuyruk dolunca üretici ne yapıyor, ve bunun kabul, kayıp ve gecikmeye etkisi ne? Yorum: [analysis/report.md](analysis/report.md).

| Varyant | Kapasite | Gönderme beklemesi | Değişen tek etken |
|---|---|---|---|
| A | 4 | 0 | başlangıç |
| B | 16 | 0 | A → B: kapasite |
| C | 4 | 20 ms | A → C: bekleme politikası |

## Sonuç özeti (yoğun yük: 10 normal + 24 art arda + 10 normal)

| Varyant | Kabul / başarısız | Gecikme en çok | Üreticinin en uzun beklemesi |
|---|---|---|---|
| A | 24 / 20 | 61 ms | 0,05 ms |
| B | 36 / 8 | 300 ms | 0,06 ms |
| C | 34 / 10 | 80 ms | 19,8 ms |

Normal yükte üç varyant da 44/44. İz kapalı A/yoğun: 24/20, en çok gecikme 60 ms.

## Klasörler

| Klasör | İçerik |
|---|---|
| `firmware/` | **Eğitmenin Hafta 3 referans firmware'i** (değiştirilmedi, kaynak: [`firmware/KAYNAK.md`](firmware/KAYNAK.md)) |
| `tools/capture.py` | Eğitmenin ölçüm aracı (değiştirilmedi) |
| `measurements/` | 7 koşunun CSV, ham seri oturum (`.txt`) ve metadata (`.json`) dosyaları |
| `traces/` | Özgün SystemView kayıtları (`.SVDat`); `traces/ekran/` görseller için kesilmiş kısa pencereler |
| `analysis/` | Tablo (`summary.csv`, `summary.py`), 3 işaretli SystemView görseli, yorum, `.SVDat` çözücüsü ve pencere/işaretleme betikleri |
| `ai-usage.md` | Yapay zekâ kullanımı ve doğrulama |

Benim katkım: macOS'ta derleme ve yükleme, ölçümler, `analysis/` altındaki bütün betikler ve görseller, yorum.

## Kart ve sürümler

| | |
|---|---|
| Kart | NUCLEO-L476RG, 80 MHz, ST-LINK (kart üstü), **J-Link yok**, macOS |
| Seri port | ST-LINK VCP, **230400** 8N1 |
| RTOS | FreeRTOS 11.1.0; Producer öncelik 2, Consumer 1, Console 3 |
| Derleme | STM32CubeIDE 2.2.0, Debug. ELF SHA256 `a15a00eb…c437481` (31 812 B text) |
| İz | SystemView, 200 ms RAM kaydı (yoğun yükte 11. mesajdan önce başlar), V4.10b ile açıldı |

## Nasıl tekrarlanır?

1. CubeIDE: *File → Import → Existing Projects into Workspace* → `hafta-03/firmware` → **RTOS_Hafta_3_L476RG**, Debug olarak derle, ST-LINK ile yükle.
2. Ölçümler (butona basmak gerekmiyor; yük yazılımla üretiliyor):

   ```sh
   pip install pyserial
   P=/dev/cu.usbmodem103            # Windows'ta COM4 gibi
   for v in A B C; do python3 hafta-03/tools/capture.py --port $P --variant $v --load NORMAL --output hafta-03/measurements; done
   for v in A B C; do python3 hafta-03/tools/capture.py --port $P --variant $v --load BURST  --output hafta-03/measurements; done
   python3 hafta-03/tools/capture.py --port $P --variant A --load BURST --no-trace --output hafta-03/measurements
   ```

   `.SVDat` dosyaları sonra `traces/` klasörüne taşındı.
3. Tablo: `python3 hafta-03/analysis/summary.py`
4. Görsel pencereleri: `python3 hafta-03/analysis/sv_window.py <iz.SVDat> <mesaj> <başlangıç_ms> <bitiş_ms> <çıkış.SVDat>`, sonra SystemView'de *File → Open*.

SystemView V4.10b uygulama olaylarını `Function #512…517` olarak gösteriyor:

| # | Olay |
|---|---|
| 512 | RUN |
| 513 | SEND_BEGIN |
| 514 | SEND_OK |
| 515 | SEND_FAIL |
| 516 | RECEIVE |
| 517 | DONE |
