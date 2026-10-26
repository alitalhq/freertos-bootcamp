# Hafta 5 — CubeIDE'den karta yükleme

Hedef kart **NUCLEO-L476RG / STM32L476RG**.
FreeRTOS kernel **V11.1.0** uygulamayla birlikte derlenir ve aynı ELF/HEX içinde
karta yüklenir. Kernel'i ayrıca yüklemiyorsunuz.

## Projede ne var?

```text
firmware/
  .project / .cproject              CubeIDE projesi
  RTOS_Hafta_5_L476RG.launch        ST-LINK debug ayarı
  src/main.c                       başlangıç
  src/app.c                        StreamBuffer / Notify deneyleri
  src/board.c                      saat, UART, GPIO, IRQ
  include/FreeRTOSConfig.h          kernel ayarları
  vendor/freertos/                  FreeRTOS V11.1.0 kaynakları
    tasks.c, queue.c, list.c, stream_buffer.c
    portable/GCC/ARM_CM4F/port.c     Cortex-M4F portu
    portable/MemMang/heap_4.c       heap yöneticisi
  vendor/hal/                      STM32L4 HAL
  vendor/cmsis/                    ARM CMSIS
  vendor/device/                   ST başlıkları, startup ve system dosyası
  STM32L476RG.ld                    linker script
  prebuilt/Hafta5_L476RG.hex        doğrudan yüklenebilir hazır dosya
```

Kaynaklar ve lisansları bu klasördedir. Hafta 4'e kaynak bağımlılığı yoktur.
Bu elle düzenlenmiş CubeIDE projesidir; `.ioc` dosyası gerektirmez.
`Linked` altında görünen kernel/HAL dosyaları aynı projenin `vendor` içindeki
dosyalarına işaret eder; kaynak kod iki kez çoğaltılmaz.

## Yol A — CubeIDE ile derle ve debug et

1. Kartı **ST-LINK USB** bağlantısından bilgisayara takın.
2. CubeIDE'de **File → Import → General → Existing Projects into Workspace**.
3. **Select root directory** için şu klasörü seçin:
   `F:\2026_Eylul_RTOS_Bootcamp\Hafta_5\firmware`
4. `RTOS_Hafta_5_L476RG` projesini seçip Finish yapın.
   Mevcut klasörde çalışmak için **Copy projects into workspace** seçili olmasın.
5. Projeye sağ tıklayın → **Build Configurations → Set Active → Debug**.
6. **Build Project**. Çıktı:
   `Debug/RTOS_Hafta_5_L476RG.elf`
7. **Run → Debug Configurations → STM32 C/C++ Application** altında
   `RTOS_Hafta_5_L476RG` yapılandırmasını seçip **Debug**.
   Proje adı `RTOS_Hafta_5_L476RG`, uygulama dosyası
   `Debug/RTOS_Hafta_5_L476RG.elf`, debug probe **ST-LINK (SWD)** olmalıdır.
8. Program `main()` girişinde durursa **Resume / F8** yapın.
   Bu adım olmadan UART task'ları henüz çalışmıyor olabilir.
9. Chrome/Edge'de `Hafta_5/seri-lab.html` açın.
   **Karta bağlan** → ST-LINK Virtual COM portunu seçin.
   Ayar **230400 baud / 8N1**. Başka seri terminal aynı portu açık tutmamalı.

CubeIDE'de kernel'e bakmak için `vendor/freertos/tasks.c` veya
`Linked/tasks.c`; StreamBuffer için `stream_buffer.c` açın.
NotifyWorker ve StreamReader'a breakpoint koyarken tüm sistem durur;
bu sırada tarayıcı komutları timeout olabilir.

## Yol B — Derlemeden hazır HEX yükle

1. STM32CubeProgrammer'ı açın, bağlantı türü **ST-LINK**, port **SWD** seçin.
2. **Connect**.
3. **Erasing & Programming** bölümünde
   `prebuilt/Hafta5_L476RG.hex` dosyasını seçin.
4. **Verify programming** ve **Run after programming** seçeneklerini açın.
5. **Start Programming**.
6. Program çalışınca HTML arayüzünden COM portuna bağlanın.

HEX adres bilgisini içerir; ayrıca başlangıç adresi girmeniz gerekmez.
BIN kullanırsanız başlangıç adresi `0x08000000` olmalıdır.
Hazır dosya FreeRTOS dahil uygulamanın tamamını içerir.

## Derleme doğrulaması

- Yerel kernel/HAL/CMSIS kaynaklarıyla CMake + Arm GCC: başarılı.
- STM32CubeIDE **2.2.0**, Debug: **0 hata / 0 uyarı**.
- CubeIDE ELF: 25172 byte text, 104 byte data, 30016 byte BSS.
- CMake hazır HEX SHA-256:
  `366EB0C05A37684A3E8FC070B1919C2E36287083B543A2175E5044499B087F38`
- 21 Ekim 2026: COM4 kartına ST-LINK CLI ile yükleme ve flash doğrulaması başarılı. UART üzerinden 15 kontrol geçti. CubeIDE GUI debug oturumu bu testte açılmadı.

CubeIDE komut satırı derlemesi:

```powershell
./Hafta_5/firmware/build_cubeide.ps1
```

Resmî kaynaklar:
[STM32CubeIDE kullanım rehberi](https://www.st.com/resource/en/user_manual/dm00629856-stm32cubeide-user-guide-stmicroelectronics.pdf),
[STM32CubeProgrammer kullanım rehberi](https://www.st.com/resource/en/user_manual/dm00403500-stm32cubeprogrammer-software-description-stmicroelectronics.pdf).
