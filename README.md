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

- **C / MCU deneyimi:** _TBD_
- **Öğrenme hedefleri:** _TBD_
- **Eksik hazırlık başlıkları:** _TBD_
- **Karşılaşılan sorunlar:** CubeIDE 2.x'te CubeMX'in ayrı uygulama olması; CubeMX board BSP'sinin buton kesmesini sahiplenmesi; CubeMX paketindeki FreeRTOS 10.3.1'de `xTaskDelayUntil` bulunmaması. Ayrıntı: [hafta-01/docs/setup.md](hafta-01/docs/setup.md#3-tuzaklar)
