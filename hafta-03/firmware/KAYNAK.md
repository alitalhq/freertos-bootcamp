# Firmware kaynağı

Bu klasör **eğitmenin Hafta 3 referans firmware'idir** (FreeRTOS Bootcamp, Erhan Konak, `Hafta_3/firmware`, 5–6 Ekim 2026 paketi). Ödev metni referansın kullanılmasına izin veriyor; uygulama kodu (`src/`, `include/`) değiştirilmedi.

Bu repoda yapılanlar:
- `vendor/` yalnız derlemenin kullandığı 71 dosyaya indirildi (64 kaynak/başlık + 7 lisans, 67,9 MB → 4,8 MB). Hangi dosyaların kullanıldığı CubeIDE derlemesinin `.d` bağımlılık listelerinden çıkarıldı; ardından temiz derleme 0 hata, 0 uyarı verdi ve ELF boyutu değişmedi.
- Sabit kütüphane sürümleri: `dependencies.lock.json` (CMSIS 5.9.0, cmsis-device-l4 v1.7.4, HAL v1.13.5, FreeRTOS-Kernel V11.1.0) ve `segger.lock.json` (SystemView, RTT).
- Windows'a özgü derleme betikleri (`build*.ps1`) ve hazır binary'ler (`prebuilt/`) alınmadı.

Derleme (macOS, STM32CubeIDE 2.2.0): *File → Import → Existing Projects into Workspace* → bu klasör → **RTOS_Hafta_3_L476RG**, Debug.
