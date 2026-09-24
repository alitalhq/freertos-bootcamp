#include <stdio.h>
#include <string.h>

#include "app.h"
#include "app_config.h"
#include "timebase.h"

#include "main.h"
#include "usart.h"
#include "FreeRTOS.h"
#include "task.h"

#if APP_BRINGUP
/* Yalnızca scheduler başlamadan önce kullanılır. Ödev modunda UART'ın tek
   sahibi UartTxTask olacak (R-TSK-2); polling gönderim ana deneyde yok. */
static void bringup_print(const char *s)
{
    HAL_UART_Transmit(&huart2, (const uint8_t *)s, (uint16_t)strlen(s), 100);
}

/* F2 doğrulaması: scheduler çalışıyorsa LD2 yanıp söner. */
static void BlinkTask(void *arg)
{
    (void)arg;
    for (;;)
    {
        HAL_GPIO_TogglePin(LD2_GPIO_Port, LD2_Pin);
        vTaskDelay(pdMS_TO_TICKS(BRINGUP_BLINK_MS));
    }
}
#endif

void app_init(void)
{
    timebase_init();

#if APP_BRINGUP
    char line[96];

    bringup_print("\r\nhello from odev01 (NUCLEO-L476RG)\r\n");

    snprintf(line, sizeof line, "SYSCLK=%lu Hz\r\n", (unsigned long)SystemCoreClock);
    bringup_print(line);

    /* F1 doğrulaması: HAL_Delay(1000) süresini TIM2 ile ölç.
       Beklenen ~1 000 000 us. HAL_Delay tick'i yuvarladığı için
       birkaç ms fazla çıkması normaldir. */
    for (int i = 0; i < 3; i++)
    {
        uint32_t t0 = timer_us();
        HAL_Delay(1000);
        uint32_t dt = timer_us() - t0;   /* mod 2^32 fark */
        snprintf(line, sizeof line, "HAL_Delay(1000) = %lu us\r\n", (unsigned long)dt);
        bringup_print(line);
    }

    bringup_print("starting scheduler, LD2 should blink\r\n");
#endif
}

void app_create_tasks(void)
{
#if APP_BRINGUP
    BaseType_t ok = xTaskCreate(BlinkTask, "blink", 128, NULL, 1, NULL);
    configASSERT(ok == pdPASS);
#endif
}
