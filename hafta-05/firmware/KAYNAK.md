# Kaynak

Başlangıç noktası eğitmenin Hafta 5 firmware paketi (CubeIDE projesi, FreeRTOS 11.1.0, STM32L4 HAL).

| Dosya | Durum |
|---|---|
| `src/app.c` | **Yeniden yazıldı.** ASCII komut laboratuvarı yerine çerçeveli veri hattı, parser, üç notification anlamı, TX sahibi, sayaçlar |
| `src/board.c` | **Bir satır:** `USART2_IRQHandler` önce `app_uart_tx_isr()` çağırıyor (TX baytları uygulamanın StreamBuffer'ından) |
| `include/board.h` | **Bir satır:** `app_uart_tx_isr` bildirimi |
| `src/main.c`, `src/protocol.c`, `src/syscalls.c`, `include/*`, `STM32L476RG.ld`, `.project`, `.cproject`, `CMakeLists.txt` | Değişmedi. `protocol.c` artık kullanılmıyor ama derlemede duruyor |
| `vendor/` | Yalnız derlemenin kullandığı 63 dosya ve lisanslar bırakıldı (66 MB → 4,5 MB). Liste, Debug derlemesinin `.d` bağımlılık dosyalarından ve `.project` bağlantılarından çıkarıldı; budamadan sonra temiz derleme yeniden geçti |
| `KARTA_YUKLE.md` | Eğitmenin yükleme rehberi, değişmedi. İçinde geçen `prebuilt/` ve `.launch` dosyaları repoya alınmadı; yükleme için ana README'ye bakın |

`Linked/` CubeIDE'nin sanal klasörüdür; dosyalar `.project` içinde `vendor/`'a bağlanıyor.
