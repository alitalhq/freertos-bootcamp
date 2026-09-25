# Kod Notları

Ölçüm zincirinin her halkası, kodun ilgili yeriyle birlikte. Kod blokları `firmware/odev01/App/` altındaki gerçek kaynaklardan alındı. Gereksinim kimlikleri (R-xx) [spec.md](spec.md)'ye aittir.

```
B1 düşen kenar → EXTI ISR (t0) → buttonQ → ButtonTask (t1, t2) → txQ → UartTxTask (t3) → USART2 TC ISR (t4)
                                          TelemetryTask (öncelik 3) ──┘
```

## 1. Zaman tabanı: `timebase.h`

```c
static inline uint32_t timer_us(void)
{
    return TIM2->CNT;
}
```

TIM2, 80 MHz / (79+1) = 1 MHz'de serbest sayıyor. Tek bir yazmaç okuması, ISR içinden de güvenle çağrılabiliyor. 32-bit sayaç ~71,6 dakikada bir tur atıyor. Farklar her yerde `uint32_t` çıkarmasıyla alınıyor (`b - a`). Bir olay bir turdan çok daha kısa sürdüğü için taşma sonucu bozmuyor (R-REC-3, ADR-002).

## 2. Buton ISR ve 30 ms filtre: `button.c`

**t₀ ISR'ın ilk satırında alınıyor.** CubeMX'in ürettiği `EXTI15_10_IRQHandler`, HAL'in bayrak temizleme ve dağıtım koduna geçmeden önce USER CODE bloğunda bizim fonksiyonumuzu çağırıyor:

```c
/* stm32l4xx_it.c */
  /* USER CODE BEGIN EXTI15_10_IRQn 0 */
  button_irq_entry();   /* t0: HAL dağıtımından önce (R-BTN-2) */
```

```c
void button_irq_entry(void)
{
    s_irq_entry_us = timer_us();
}
```

Asıl işi HAL, bayrağı temizledikten sonra çağırdığı callback yapıyor:

```c
void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
    ...
    const uint32_t now = s_irq_entry_us;

    /* 30 ms tekrar-kenar filtresi. İşaretsiz fark sayaç taşmasına dayanıklı. */
    if (s_have_first_edge && (uint32_t)(now - s_last_accepted_us) < DEBOUNCE_US)
    {
        g_stats.bounce_rejected++;
        return;
    }
    s_have_first_edge = true;
    s_last_accepted_us = now;
```

- **İlk kenar her zaman kabul ediliyor** (`s_have_first_edge`). Böylece ilk basış filtreye takılmıyor (R-BTN-3).
- Filtre, son **kabul edilen** kenara göre çalışıyor. 30 ms içindeki tekrar kenarları sayılıp atılıyor. 210 resmi basışta `bounce_rejected = 0`. Basit bir tekrar filtresi, donanımsal debounce garantisi vermez.
- Isınmada ya da deney bittikten sonra gelen basışlar olay sayılmıyor (`ignored`).

```c
    const uint32_t id = s_next_id++;
    g_stats.accepted++;
    records_open(id, now);
    ...
    ButtonEvent e = { id, now };
    BaseType_t wake = pdFALSE;
    if (xQueueSendFromISR(s_button_q, &e, &wake) != pdPASS)
    {
        /* Kuyruğa giremeyen olay kaybolmaz: kimliği ve t0'ı kayıtta kalır. */
        g_stats.btn_q_drop++;
        records_set_status(id, ST_BTN_DROP);
    }
    ...
    portYIELD_FROM_ISR(wake);
}
```

- Olay kuyruğa **değer olarak** kopyalanıyor (`{id, t0}`). Tek bir global zaman damgası kullanılmıyor, böylece olay kimlikleri karışmıyor.
- Kayıt, kuyruğa göndermeden **önce** açılıyor. Kuyruk dolu olsa bile olayın kimliği ve t₀'ı kaybolmuyor.
- ISR içinde bekleme ya da UART yok. `portYIELD_FROM_ISR`, ButtonTask'ı uyandırdıysa ISR'dan çıkar çıkmaz ona geçiliyor.
- NVIC önceliği 6. `configLIBRARY_MAX_SYSCALL_INTERRUPT_PRIORITY = 5` olduğu için FromISR API'leri çağrılabiliyor (R-BTN-7).

## 3. ButtonTask (öncelik 2): t₁ ve t₂

```c
    for (;;)
    {
        xQueueReceive(s_button_q, &e, portMAX_DELAY);
        records_stamp(e.id, T1, timer_us());
        ... 64 baytlık "BTN,<id>,<Sx>,PRESSED" mesajını kur ...
        records_stamp(e.id, T2, timer_us());   /* gönderimden hemen önce */
        if (!uart_tx_post(&m))
        {
            g_stats.btn_tx_drop++;
            records_set_status(e.id, ST_TX_DROP);
        }
```

- **t₁**, `xQueueReceive` döndükten hemen sonra alınıyor. ISR'dan görevin CPU'yu almasına kadar geçen her şey t₁−t₀'nın içinde. S4/S5'teki telemetri preemption'ı da dahil.
- **t₂**, `xQueueSend` çağrısından hemen önce alınıyor. Bu yüzden t₃−t₂ kuyruk API'sini de kapsıyor, "saf FIFO beklemesi" değil.
- Mesaj `printf` olmadan kuruluyor (`msg.c`: `tb_put_str`, `tb_put_u32`). Süresi sabit (~25 µs, `-O0`), heap kullanmıyor ve yeniden girişli. Metin 63 baytı aşarsa sessizce kesilmiyor: sayaç artıyor ve `configASSERT` tetikleniyor (R-MSG-2).
- `uart_tx_post`, `xQueueSend(txQ, &m, 0)` çağırıyor. **Beklemiyor.** Kuyruk doluysa yanıt kaybediliyor (`tx_drop`) ve bu kayıtta görünüyor.

## 4. UartTxTask (öncelik 1): UART'ın tek sahibi, t₃

```c
static TxResult send_buf(uint16_t len, bool is_btn, uint32_t id)
{
    (void)ulTaskNotifyTake(pdTRUE, 0);   /* geç gelmiş eski bildirimi tüket */
    s_tx_failed = false;
    s_cur_id = id;
    s_cur_is_btn = is_btn;

    if (is_btn)
    {
        records_stamp(id, T3, timer_us());   /* UART başlatmadan hemen önce */
    }
    if (HAL_UART_Transmit_IT(&huart2, s_tx_buf, len) != HAL_OK)
    {
        ...
        return TX_START_ERR;
    }

    /* TC kesmesini bekle. Gelmezse sonsuza kadar bekleme (R-UART-3). */
    if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(UART_TX_TIMEOUT_MS)) == 0U)
    {
        s_cur_is_btn = false;             /* geç gelen TC t4 yazmasın */
        HAL_UART_AbortTransmit(&huart2);
        g_stats.uart_timeout++;
        return TX_TIMEOUT;
    }
    ...
}
```

- Yalnızca bu görev `huart2`'ye dokunuyor. TelemetryTask ve ButtonTask mesajı `txQ`'ya bırakıyor (R-TSK-2).
- Gönderim **IT** modunda (ADR-001). Görev, TC bildirimi gelene kadar `ulTaskNotifyTake` ile bloklanıyor. Bu sırada CPU'yu tutmuyor.
- `s_tx_buf` statik. HAL aktarım bitene kadar bu tampondan okuyor ve görev TC'yi beklerken tampon değişmiyor.
- **1 s gözetim süresi** (deney timeout'u, 20 ms deadline ile karıştırılmamalı). TC gelmezse gönderim iptal ediliyor, görev sonsuza kadar beklemiyor.

## 5. TC callback: t₄

```c
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart != &huart2)
    {
        return;
    }
    if (s_cur_is_btn)
    {
        records_stamp(s_cur_id, T4, timer_us());
        records_set_status(s_cur_id, ST_OK);
        s_cur_is_btn = false;
    }
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(s_task, &wake);
    portYIELD_FROM_ISR(wake);
}
```

L4 HAL'in IT modunda son bayt TDR'ye yazılınca TXE kesmesi kapatılıp **TC** kesmesi açılıyor. Bu callback, son bit hattan çıktıktan sonra TC işlenirken çağrılıyor. t₄ burada alınıyor. Ölçüm tutarlılığı: 210 basışın tamamında t₄−t₃ = 5,560 ms. Hesaplanan hat süresi 5,556 ms; aradaki ~4 µs TC'nin gözlenme süresi.

t₄ yanıt gönderildikten **sonra** biliniyor. Bu yüzden yanıt mesajının içine konamıyor, kayıtta tutulup deney sonunda export ediliyor.

## 6. TelemetryTask (öncelik 3): periyot ve yük

```c
    for (;;)
    {
        if (g_exp_state >= EXP_STOPPING)
        {
            vTaskSuspend(NULL);
        }
        const uint32_t act = timer_us();
        if (seq > 0U)
        {
            stats_period_sample(act - prev_act);
        }
        prev_act = act;

        if (iters > 0U)
        {
            workload_run(iters);
            stats_work_sample(timer_us() - act);
        }
        ... "TEL,<seq>,<Sx>,<uptime_ms>" kur, uart_tx_post ...
        vTaskDelayUntil(&last, period);
    }
```

- `vTaskDelayUntil` mutlak periyot tabanını koruyor. İş süresi periyodu kaydırmıyor. Ölçülen periyot 100 Hz'de 9 993–10 008 µs. FreeRTOS 10.3.1'de `xTaskDelayUntil` bulunmadığı için bu eşdeğeri kullanılıyor.
- S0'da görev döngüye girmeden `vTaskSuspend(NULL)` ile bloklanıyor. Boş döngüde dönmüyor (R-SCN-2).
- **Kalibre iş** (`workload.c`): Xorshift döngüsü, sonucu `volatile g_workload_sink`'e yazılıyor, böylece optimizasyonla silinemiyor. Kesmeler kapatılmıyor. İterasyon sayısı, scheduler başlamadan önce 5 ölçümün en kısasına göre hesaplanıyor:

```c
    s_calib.work_iters = (uint32_t)(((uint64_t)target_us * CALIB_ITERS) / best);
```

## 7. Kayıt havuzu ve sahiplik: `records.c`

```c
typedef struct {
    uint32_t         t[T_COUNT];
    volatile uint8_t valid[T_COUNT];   /* 0 değeri "ölçülmedi" demek değil */
    volatile uint8_t status;           /* RecStatus */
} EventRecord;
```

- 128 kayıt, olay kimliğiyle doğrudan indeksleniyor. Taşarsa `rec_overflow` sayılıyor.
- **Her zaman damgasını tek bir bağlam yazıyor:** t₀ ISR, t₁/t₂ ButtonTask, t₃ UartTxTask, t₄ TC ISR. Her damganın kendi "geçerli" baytı var. Bu yüzden oku-değiştir-yaz yok ve kritik bölge gerekmiyor. 32-bit hizalı yazma Cortex-M4'te atomik.
- Ölçülmeyen damga CSV'de **boş** kalıyor, 0 yazılmıyor (R-REC-4).

## 8. Deney sonu ve export: FIFO işareti

```c
        if (g_exp_state == EXP_STOPPING && uxQueueMessagesWaiting(s_button_q) == 0U)
        {
            post_export_marker();   /* txQ'ya MSG_CTRL_EXPORT, beklemeli gönderim */
            vTaskSuspend(NULL);
        }
```

35. basışta ISR durumu `EXP_STOPPING` yapıyor. TelemetryTask bir sonraki turda duruyor. ButtonTask son olayı işleyince `txQ`'ya bir **export işareti** koyuyor. Kuyruk FIFO olduğu için işaret, önündeki tüm mesajlar gönderildikten sonra UartTxTask'a ulaşıyor. Export'u UART'ın sahibi yapıyor: `CFG → REC × N → TSK → CNT → END`. Ölçüm sırasında hiçbir sayaç UART'a basılmıyor (R-REC-5).

## 9. Zaman hesapları (PC tarafı): `analysis/analyze.py`

```python
def diff(a, b):
    """uint32 farkı mod 2^32 (spec R-REC-3)."""
    return None if a is None or b is None else (b - a) % 2**32

R = diff(t0, t4)   # yalnızca kart damgaları; PC saati kullanılmıyor
```

Eksik damgası olan olaylar (örneğin `tx_drop`) R hesabına girmiyor ve "deadline karşılandı" sayılmıyor. Tabloda ayrıca raporlanıyor.
