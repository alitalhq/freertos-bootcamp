# SystemView Ödevi

Hafta 2'nin A/B/C deneyini SEGGER SystemView iziyle açıklıyoruz. Rapor: [analysis/report.md](analysis/report.md).

| Klasör / dosya | İçerik |
|---|---|
| `traces/` | Orijinal SystemView kayıtları (`.SVDat`) |
| `traces/windows/` | Kesilmiş kısa parçalar (senkron noktalarından) |
| `traces/ekran/` | SystemView ekran görüntüleri için birkaç ms'lik pencereler (`analysis/sv_window.py`) |
| `measurements/` | Her koşunun ham UART oturumu, CSV ve meta dosyası |
| `experiment.csv` | Koşu → koşul, rol, iz dosyası ve izdeki olay kimlikleri |
| `analysis/` | Rapor, işaretli SystemView ekran görüntüleri (`screenshots/`), izden çizimler (`figures/`), `.SVDat` çözücüsü ve betikler |
| `SYSVIEW_Odev2_BTN.txt` | Uygulama olaylarının adları (SystemView'de elle yüklenir) |
| `ai-usage.md` | Yapay zekâ kullanımı ve doğrulama |

Firmware: [`../firmware/odev02`](../firmware/odev02). Ödev 2 ile aynı proje; SystemView desteği eklendi.

## Bağlantı ve sürümler

| | |
|---|---|
| Kart | NUCLEO-L476RG, 80 MHz; ST-LINK V2-1 (kart üstü), **J-Link yok** |
| Kayıt yolu | SystemView post-mortem halka tamponu (32 KB RAM) → deney sonunda USART2 (ST-LINK VCP) → `.SVDat` |
| SystemView (PC) | V4.10b, macOS, SEGGER Friendly License |
| SystemView hedef kaynakları | SEGGERMicro/SystemView `92ca7a8`, SEGGERMicro/RTT `4d8feab` |
| RTOS | FreeRTOS 10.3.1 + SEGGER `FreeRTOSV10_Core.patch` (yalnız CM4F'nin kullandığı dosyalar, `portmacro.h` hariç) |
| Zaman damgası | DWT CYCCNT, 80 MHz (TIM2 ölçümlerinden ayrı saat) |
| Ölçülen firmware commit'i | `ed4ba76` (`feat/hafta-02-systemview`) |

## Nasıl tekrarlanır?

1. CubeIDE'de `hafta-02/firmware/odev02` projesini açıp **Debug** olarak derle ve yükle.
2. Koşular (fiziksel B1 basışı, LD2 yanınca):

   ```sh
   cd hafta-02/interface
   python capture.py run --variant A --scenario S5 --trace --out ../systemview-odevi/measurements
   python capture.py run --variant B --scenario S5 --trace --tx-prio 4 --out ...   # iyileştirme
   python capture.py run --variant C --scenario S6 --out ...                        # iz kapalı
   python capture.py run --variant A --scenario S5 --trace --target 20 --suffix 2 --out ...  # kısa kayıt
   ```

   `--trace` ile `<koşu>.SVDat` de yazılır; `.SVDat` dosyaları sonra `traces/` klasörüne taşındı.
3. Görseller: `python analysis/sv_figures.py`
4. SystemView'de *File → Open* ile `.SVDat` açılır. Olay adları için *Project → Description Files* → `SYSVIEW_Odev2_BTN.txt`.

## Video için olay

`traces/windows/uart_bekleme_B-S5t2_olay18.SVDat`: B/S5'te 18 numaralı basış. t₀'dan 0,2 ms sonra yanıt hazır, 154 ms kuyrukta bekliyor, uart_tx her 10 ms'de bir kez çalışıyor (rapor bölüm 4).
