# SEGGER SystemView ve RTT hedef kaynakları

| Bileşen | Kaynak | Commit |
|---|---|---|
| SystemView (`SYSVIEW/`, `SEGGER/`, `Config/Global.h`, `FreeRTOSV10/`) | https://github.com/SEGGERMicro/SystemView | `92ca7a810c5765ba64911919acd511c61b6b083f` |
| RTT (`RTT/`) | https://github.com/SEGGERMicro/RTT | `4d8feab3150f86f37a9d323ddc88d6cdf5673072` |

Dosyalar FreeRTOS Bootcamp Hafta 3 paketindeki `firmware/vendor` kopyasından alındı (commit'ler `segger.lock.json` ile aynı). Lisanslar: `LICENSE-SystemView.md`, `LICENSE-RTT.md`.

- `FreeRTOSV10/` SystemView deposundaki `Sample/FreeRTOSV10` örneğidir. FreeRTOS 10.3.1 için gereken çekirdek yaması `Middlewares/Third_Party/FreeRTOS` altına uygulandı (bkz. `hafta-02/README.md`).
- `Config/SEGGER_SYSVIEW_Conf.h` ve `Config/SEGGER_RTT_Conf.h` bu projeye aittir; SEGGER'in örnek yapılandırma dosyası (`SEGGER_SYSVIEW_Config_FreeRTOS.c`) yerine `App/app_trace.c` kullanılır.
