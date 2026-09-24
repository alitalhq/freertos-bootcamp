#include <string.h>

#include "uart_tx.h"
#include "app_config.h"
#include "stats.h"

#include "main.h"
#include "usart.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

static QueueHandle_t s_txq;
static TaskHandle_t  s_task;

/* Aktarım bitene kadar HAL bu tampondan okur; görev TC'yi beklerken
   tampon değişmez (spec §4, "TX tamponu aktarım sonuna kadar geçerli"). */
static uint8_t s_tx_buf[MSG_LEN];

/* Kesmenin görev ile paylaştığı durum: callback'te hata mı oldu? */
static volatile bool s_tx_failed;

bool uart_tx_post(const TxMsg *m)
{
    if (xQueueSend(s_txq, m, 0) != pdPASS)
    {
        return false;
    }
    stats_update_max(&g_stats.txq_hwm, (uint32_t)uxQueueMessagesWaiting(s_txq));
    return true;
}

static void UartTxTask(void *arg)
{
    (void)arg;
    TxMsg m;

    for (;;)
    {
        xQueueReceive(s_txq, &m, portMAX_DELAY);
        memcpy(s_tx_buf, m.data, MSG_LEN);

        /* Önceki aktarımdan (ör. timeout sonrası geç gelen TC) kalmış
           bildirimi beklemeden tüket. */
        (void)ulTaskNotifyTake(pdTRUE, 0);
        s_tx_failed = false;

        /* t3 bu satırdan hemen önce kaydedilecek (F4, ADR-001). */
        if (HAL_UART_Transmit_IT(&huart2, s_tx_buf, MSG_LEN) != HAL_OK)
        {
            g_stats.uart_start_err++;
            continue;
        }

        /* TC kesmesini bekle. Gelmezse sonsuza kadar bekleme (R-UART-3). */
        if (ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(UART_TX_TIMEOUT_MS)) == 0U)
        {
            HAL_UART_AbortTransmit(&huart2);
            g_stats.uart_timeout++;
        }
        else if (!s_tx_failed)
        {
            g_stats.uart_tx_ok++;
        }
    }
}

void uart_tx_create(void)
{
    s_txq = xQueueCreate(TX_QUEUE_LEN, sizeof(TxMsg));
    configASSERT(s_txq != NULL);

    BaseType_t ok = xTaskCreate(UartTxTask, "uart_tx", STACK_UART_TX, NULL,
                                PRIO_UART_TX, &s_task);
    configASSERT(ok == pdPASS);
}

/* ---- USART2 kesme bağlamı ----------------------------------------------
   IT modunda HAL, son baytı TDR'ye yazdıktan sonra TC kesmesini açar ve bu
   callback'i TC (son bit hattan çıktı) anında çağırır. t4 burada alınacak. */

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart != &huart2)
    {
        return;
    }
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(s_task, &wake);
    portYIELD_FROM_ISR(wake);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart != &huart2)
    {
        return;
    }
    g_stats.uart_error++;
    s_tx_failed = true;
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(s_task, &wake);
    portYIELD_FROM_ISR(wake);
}
