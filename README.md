# FreeRTOS Bootcamp

FreeRTOS Bootcamp (Erhan Konak, 20 Eylül – 22 Kasım 2026) haftalık ödevleri.

| | |
|---|---|
| Kart | NUCLEO-L476RG (STM32L476RG, Cortex-M4F) |
| Geliştirme ortamı | STM32CubeIDE 2.2.0 + STM32CubeMX 6.18.1 (macOS) |
| RTOS | FreeRTOS V10.3.1 (STM32Cube FW_L4 V1.18.2, CMSIS-RTOS v2) |

## Haftalar

| Hafta | Konu | Klasör |
|---|---|---|
| 01 | Yük altında buton yanıtı: zamanlama ve gecikme analizi | [hafta-01](hafta-01/) · [rapor](hafta-01/analysis/report.md) |

## Hazırlık bilgileri

- **Kurulum durumu:** Tamamlandı. Proje derleniyor, karta yükleniyor ve debugger ile çalışıyor; kart UART üzerinden PC ile haberleşiyor.
- **C / MCU deneyimi:** Marmara Üniversitesi Bilgisayar Mühendisliği öğrencisiyim. C/C++ ile gömülü yazılım geliştiriyorum:
  - **T3 Vakfı** (Gömülü Yazılım Stajyeri): Zephyr RTOS'u T3 Gemstone kartına port ettim, I2C, SPI, CAN, GPIO ve sensör sürücüleri yazdım.
  - **Nebula UAV Team** (Takım Kaptanı): PX4/ArduPilot tabanlı otonom İHA'larda gömülü ve otomasyon sistemlerinden sorumluyum. Lazer taretin kontrol kartında ESP32 + FreeRTOS üzerinde CRC16 doğrulamalı özel bir haberleşme protokolü geliştirdik.
- **Öğrenme hedefleri:** Savunma sanayiinde gömülü yazılım alanında çalışmak istiyorum ve buna hazırlanıyorum. Bu eğitimle RTOS'ta görev ve öncelik tasarımını gerekçeleriyle yapabilmeyi, zamanlama davranışını ölçüp determinizm açısından yorumlayabilmeyi hedefliyorum.
- **Karşılaşılan sorunlar:** CubeIDE 2.x'te CubeMX'in ayrı uygulama olması; CubeMX board BSP'sinin buton kesmesini sahiplenmesi; CubeMX paketindeki FreeRTOS 10.3.1'de `xTaskDelayUntil` bulunmaması. Ayrıntı: [hafta-01/docs/setup.md](hafta-01/docs/setup.md#3-tuzaklar)
