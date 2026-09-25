# Kurulum

Projeyi sıfırdan kurmak için gereken adımlar ve yol boyunca karşılaşılan tuzaklar. Depodaki `odev01.ioc` bu ayarların hepsini içeriyor. Sadece derlemek istiyorsan README'deki "Derleme ve yükleme" bölümü yeterli.

## 1. Araçlar

- **STM32CubeIDE 2.x** (st.com, hesap gerektirir).
- **STM32CubeMX** ayrı olarak kurulmalı. CubeIDE 2.x'te CubeMX artık IDE'nin içinde değil: IDE'nin "New STM32 Project" sihirbazı `.ioc` olmadan boş proje üretiyor.
- İlk yüklemede CubeIDE, ST-LINK firmware güncellemesi isteyebilir: *Open in update mode → Upgrade*. Sonra kartı çıkarıp tekrar tak.

## 2. CubeMX projesi

File → New Project → **Board Selector** → `NUCLEO-L476RG` → "Initialize all peripherals with default mode?" → **Yes**.

| Yer | Ayar |
|---|---|
| System Core → SYS | Debug: **Serial Wire** (ya da Trace Asynchronous Sw), Timebase Source: **TIM6** |
| Timers → TIM2 | Clock Source Internal, Prescaler **79**, Counter Period **4294967295**, kesme **kapalı** |
| Connectivity → USART2 | Asynchronous, **115200 8N1**, NVIC: USART2 global interrupt **açık** |
| **Bsp → NUCLEO-L476RG** | **Human Machine Interface kapalı** (aşağıdaki tuzağa bakın) |
| Pinout: PC13 | `GPIO_EXTI13`. GPIO: **Falling edge**, No pull, etiket `B1` |
| Pinout: PA5 | `GPIO_Output`. Push-pull, Low, etiket `LD2` |
| System Core → NVIC | EXTI line[15:10] ve USART2: **Preemption 6**, "Uses FreeRTOS functions" işaretli |
| Middleware → FREERTOS | CMSIS_V2. TOTAL_HEAP_SIZE **20000**, CHECK_FOR_STACK_OVERFLOW **Option2**, USE_MALLOC_FAILED_HOOK **Enabled**. `defaultTask` önceliği **Low** |
| Clock Configuration | HCLK **80 MHz** |
| Project Manager | Name `odev01`, Location `hafta-01/firmware` (**Browse** ile seç), Toolchain **STM32CubeIDE**, "Generate Under Root" işaretli. Code Generator: "pair of .c/.h files per peripheral" işaretli |

**GENERATE CODE** → CubeIDE: File → Import → Existing Projects into Workspace. Sonra `App/` klasörünü include path'e ve Source Location'a ekle (sağ tık → *Add/remove include path*, Properties → C/C++ General → Paths and Symbols → Source Location).

## 3. Tuzaklar

| Belirti | Neden | Çözüm |
|---|---|---|
| PC13/PA5 pembe, GPIO panelinde görünmüyor, pin moduna tıklayınca "unlocked" yazıyor | Pinler **BSP** bileşenine ait | Bsp → NUCLEO-L476RG → Human Machine Interface'i kapat, sonra pinleri elle ata |
| BSP açıkken üretilen kod EXTI'yi yükselen kenara kuruyor, sonra `BSP_PB_Init` düşen kenara çevirip **önceliği 15'e eziyor** | BSP kendi başlatma sırasını kullanıyor | BSP'yi kapat |
| `main.c` USER CODE dışında `HAL_GPIO_EXTI_Callback` tanımlıyor | BSP demo kodu | BSP'yi kapat, USER CODE WHILE bloğunda kalan demo satırlarını sil |
| `USE_TIMERS` gri, kapatılamıyor | CMSIS_V2 `xTimerPendFunctionCall`'a ihtiyaç duyuyor | Açık kalabilir. Timer görevi yazılım timer'ı olmadığı için uykuda kalıyor |
| `defaultTask` için Delete düğmesi soluk | Bu CubeMX sürümünde son görev silinemiyor | Önceliği Low yap. `StartDefaultTask` USER CODE bloğunda `vTaskDelete(NULL)` |
| Project Location "can't contain \ / : * …" hatası | Alan elle yazılırken ara durum geçersiz sayılıyor | **Browse** ile seç |
| `xTaskDelayUntil` tanımsız | FW_L4 1.18.2 içindeki FreeRTOS 10.3.1 | `vTaskDelayUntil` kullan |

## 4. Komut satırından derleme / yükleme (opsiyonel)

CubeIDE bir kez derledikten sonra `Debug/` altındaki makefile, IDE'nin getirdiği araçlarla kullanılabilir:

```bash
TOOLS=$(dirname "$(find /Applications/STM32CubeIDE.app -path '*gnu-tools-for-stm32*/tools/bin/arm-none-eabi-gcc' | head -1)")
MAKE=$(find /Applications/STM32CubeIDE.app -path '*make*/tools/bin/make' | head -1)
CLI=$(find /Applications/STM32CubeIDE.app -name STM32_Programmer_CLI -type f | head -1)
PATH="$TOOLS:$PATH" "$MAKE" -C hafta-01/firmware/odev01/Debug all
"$CLI" -c port=SWD mode=UR -w hafta-01/firmware/odev01/Debug/odev01.elf -v -rst
```

`App/` altına yeni bir `.c` dosyası eklendiyse, makefile'ların güncellenmesi için önce IDE'de bir kez derle.

## 5. PC arayüzü

```bash
cd hafta-01/interface && pip install -r requirements.txt
python monitor.py
```

Tkinter, Python ile birlikte geliyor. Seri port macOS'ta `/dev/cu.usbmodem*`. Aynı porta iki program aynı anda bağlanamaz: arayüz açıkken `--headless` çalışmaz.
