#include <string.h>

#include "uart_tx.h"
#include "app_config.h"
#include "experiment.h"
#include "export.h"
#include "records.h"
#include "timebase.h"
#include "stats.h"

#include "main.h"
#include "usart.h"
#include "task.h"

typedef enum { TX_OK, TX_START_ERR, TX_ERROR, TX_TIMEOUT } TxResult;

static QueueHandle_t s_txq;
static TaskHandle_t  s_task;

/* Aktarım bitene kadar HAL bu tampondan okur; görev TC'yi beklerken
   tampon değişmez (spec §4, "TX tamponu aktarım sonuna kadar geçerli"). */
static uint8_t s_tx_buf[EXPORT_LINE_MAX];

/* Kesme ile paylaşılan durum: şu an hattaki mesaj hangi buton olayı? */
static volatile bool     s_cur_is_btn;
static volatile uint32_t s_cur_id;
static volatile bool     s_tx_failed;

bool uart_tx_post(const TxMsg *m)
{
    if (xQueueSend(s_txq, m, 0) != pdPASS)
    {
        return false;
    }
    stats_update_max(&g_stats.txq_hwm, (uint32_t)uxQueueMessagesWaiting(s_txq));
    return true;
}

QueueHandle_t uart_tx_queue(void)
{
    return s_txq;
}

/* s_tx_buf'taki len baytı IT ile gönderir ve TC'yi bekler (ADR-001). */
static TxResult send_buf(uint16_t len, bool is_btn, uint32_t id)
{
    /* Önceki aktarımdan (ör. timeout sonrası geç gelen TC) kalmış
       bildirimi beklemeden tüket. */
    (void)ulTaskNotifyTake(pdTRUE, 0);
    s_tx_failed = false;
    s_cur_id = id;
    s_cur_is_btn = is_btn;

    if (is_btn)
    {
        records_stamp(id, T3, timer_us());   /* UART başlatmadan hemen önce */
    }
    if (HAL_UART_Transmit_IT(&huart2, s_tx_buf, len) != HAL_OK)
    {
        s_cur_is_btn = false;
        g_stats.uart_start_err++;
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
    if (s_tx_failed)
    {
        return TX_ERROR;
    }
    g_stats.uart_tx_ok++;
    return TX_OK;
}

/* export.c için: tek bir metin satırını gönderir. */
void uart_tx_send_line(const char *s, uint16_t len)
{
    memcpy(s_tx_buf, s, len);
    (void)send_buf(len, false, 0);
}

static void UartTxTask(void *arg)
{
    (void)arg;
    TxMsg m;

    for (;;)
    {
        xQueueReceive(s_txq, &m, portMAX_DELAY);

        if (m.type == MSG_CTRL_EXPORT)
        {
            /* Kuyruk FIFO: bu işaretten önceki tüm mesajlar gönderildi. */
            export_all();
            g_exp_state = EXP_DONE;
            vTaskSuspend(NULL);
        }

        memcpy(s_tx_buf, m.data, MSG_LEN);
        const bool is_btn = (m.type == MSG_BTN);
        TxResult r = send_buf(MSG_LEN, is_btn, m.event_id);

        if (is_btn)
        {
            if (r == TX_TIMEOUT)
            {
                records_set_status(m.event_id, ST_TIMEOUT);
            }
            else if (r != TX_OK)
            {
                records_set_status(m.event_id, ST_TX_ERROR);
            }
            /* TX_OK: durum TC callback'inde t4 ile birlikte "ok" yapıldı. */
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
   callback'i TC (son bit hattan çıktı) işlenirken çağırır: t4 (R-UART-4). */

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

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart != &huart2)
    {
        return;
    }
    g_stats.uart_error++;
    s_tx_failed = true;
    s_cur_is_btn = false;
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(s_task, &wake);
    portYIELD_FROM_ISR(wake);
}
