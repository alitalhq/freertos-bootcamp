#include <string.h>

#include "uart_tx.h"
#include "app_config.h"
#include "experiment.h"
#include "export.h"
#include "records.h"
#include "timebase.h"
#include "stats.h"
#include "scenario.h"
#include "lab.h"
#include "app_trace.h"

#include "main.h"
#include "usart.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "semphr.h"

typedef enum { TX_OK, TX_START_ERR, TX_TIMEOUT } TxResult;

/* Ödev 2 kuyruk düzeni: iki fiziksel kuyruk, tek toplam kabul sınırı.
   s_slots boş yerleri, s_items bekleyen mesajları sayar. Üretici önce yer
   ayırır, sonra kuyruğa yazar, en son s_items'ı artırır; böylece UartTxTask
   s_items'ı aldığında kuyruklardan birinde mutlaka bir mesaj vardır. */
static QueueHandle_t     s_tx_q;       /* TEL, LAB, export işareti; A/B'de BTN de */
static QueueHandle_t     s_urgent_q;   /* yalnızca C: BTN yanıtları */
static SemaphoreHandle_t s_slots;
static SemaphoreHandle_t s_items;
static bool              s_btn_first;  /* C: aktarım sınırında BTN önce */
static TaskHandle_t      s_task;

/* Aktarım bitene kadar HAL bu tampondan okur; görev TC'yi beklerken
   tampon değişmez (spec §4, "TX tamponu aktarım sonuna kadar geçerli"). */
static uint8_t s_tx_buf[EXPORT_LINE_MAX];

/* Kesme ile paylaşılan durum: şu an hattaki mesaj hangi buton olayı? */
static volatile bool     s_cur_is_btn;
static volatile uint32_t s_cur_id;

static QueueHandle_t queue_for(const TxMsg *m)
{
    return (s_btn_first && m->type == MSG_BTN) ? s_urgent_q : s_tx_q;
}

bool uart_tx_post(TxMsg *m)
{
    if (xSemaphoreTake(s_slots, 0) != pdPASS)
    {
        return false;                     /* 16 bekleyen sınırı dolu */
    }
    m->enq_us = timer_us();
    (void)xQueueSend(queue_for(m), m, 0); /* yer ayrıldı: kuyruk dolu olamaz */
    stats_update_max(&g_stats.txq_hwm,
                     TX_PENDING_MAX - (uint32_t)uxSemaphoreGetCount(s_slots));
    (void)xSemaphoreGive(s_items);
    return true;
}

uint32_t uart_tx_pending(void)
{
    return TX_PENDING_MAX - (uint32_t)uxSemaphoreGetCount(s_slots);
}

void uart_tx_post_export(void)
{
    TxMsg m = { .type = MSG_CTRL_EXPORT };
    /* Deney bitti; burada beklemek ölçümü etkilemez. İşaret tx_q'nun sonuna
       girer: A/B'de FIFO, C'de urgent_q önce seçildiği için bekleyen tüm
       mesajlar ondan önce gönderilir. */
    (void)xSemaphoreTake(s_slots, portMAX_DELAY);
    m.enq_us = timer_us();
    (void)xQueueSend(s_tx_q, &m, 0);
    (void)xSemaphoreGive(s_items);
}

void uart_tx_post_from_isr(TxMsg *m)
{
    BaseType_t wake = pdFALSE;
    if (xSemaphoreTakeFromISR(s_slots, &wake) == pdPASS)
    {
        m->enq_us = timer_us();
        (void)xQueueSendFromISR(s_tx_q, m, &wake);
        (void)xSemaphoreGiveFromISR(s_items, &wake);
    }
    portYIELD_FROM_ISR(wake);
}

/* Aktarım sınırında sıradaki mesajı seçer. Kritik bölgede yalnızca sıfır
   beklemeli alım var; UART aktarımı bölgenin dışında. Hattaki mesaj yarıda
   kesilmez: seçim ancak önceki aktarımın TC'si geldikten sonra yapılır. */
static void take_next(TxMsg *m)
{
    (void)xSemaphoreTake(s_items, portMAX_DELAY);

    BaseType_t got = pdFAIL;
    taskENTER_CRITICAL();
    if (s_btn_first)
    {
        got = xQueueReceive(s_urgent_q, m, 0);
    }
    if (got != pdPASS)
    {
        got = xQueueReceive(s_tx_q, m, 0);
    }
    taskEXIT_CRITICAL();
    configASSERT(got == pdPASS);

    (void)xSemaphoreGive(s_slots);        /* kuyruktan çıktı: yer boşaldı */
}

/* s_tx_buf'taki len baytı IT ile gönderir ve TC'yi bekler (ADR-001). */
static TxResult send_buf(uint16_t len, bool is_btn, uint32_t id)
{
    /* Önceki aktarımdan (ör. timeout sonrası geç gelen TC) kalmış
       bildirimi beklemeden tüket. */
    (void)ulTaskNotifyTake(pdTRUE, 0);
    s_cur_id = id;
    s_cur_is_btn = is_btn;

    if (is_btn)
    {
        records_stamp(id, T3, timer_us());   /* UART başlatmadan hemen önce */
        app_trace_event(TR_BTN_TX_START, id, 0);
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
    lab_start();                          /* RX'i kur, LAB satırını gönder */

    for (;;)
    {
        take_next(&m);

        if (m.type == MSG_CTRL_EXPORT)
        {
            /* Bu işaretten önce kuyruğa giren tüm mesajlar gönderildi. İz,
               export trafiği kayda girmesin diye burada durur. */
            app_trace_stop();
            export_all();
            app_trace_export();
            g_exp_state = EXP_DONE;
            /* Askıya alınmıyor: PING yanıtı gibi mesajlar hâlâ gönderilebilsin. */
            continue;
        }

        memcpy(s_tx_buf, m.data, MSG_LEN);
        if (m.type == MSG_TEL)
        {
            stats_tel_wait_sample(timer_us() - m.enq_us);   /* gönderim başlangıcı */
        }
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
    s_tx_q = xQueueCreate(TX_QUEUE_LEN, sizeof(TxMsg));
    s_urgent_q = xQueueCreate(URGENT_QUEUE_LEN, sizeof(TxMsg));
    s_slots = xSemaphoreCreateCounting(TX_PENDING_MAX, TX_PENDING_MAX);
    s_items = xSemaphoreCreateCounting(TX_PENDING_MAX, 0);
    configASSERT(s_tx_q != NULL && s_urgent_q != NULL && s_slots != NULL && s_items != NULL);
    app_trace_name(s_tx_q, "tx_q");
    app_trace_name(s_urgent_q, "urgent_q");
    app_trace_name(s_slots, "tx_slots");
    app_trace_name(s_items, "tx_items");
    s_btn_first = variant_btn_first(run_config());

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
        app_trace_event(TR_BTN_TX_TC, s_cur_id, 0);
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
    /* RX de açık. ORE/FE/NE/PE alıcı tarafının hataları; HAL yalnızca RX'i
       sonlandırır, süren gönderim etkilenmez. RX'i yeniden kur. */
    lab_rx_rearm();
}
