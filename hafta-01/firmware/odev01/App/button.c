#include <stdbool.h>

#include "button.h"
#include "app_config.h"
#include "experiment.h"
#include "scenario.h"
#include "records.h"
#include "timebase.h"
#include "msg.h"
#include "stats.h"
#include "uart_tx.h"

#include "main.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

volatile uint8_t g_exp_state = EXP_WARMUP;

static QueueHandle_t s_button_q;

/* ISR'a ait durum (yalnızca EXTI kesmesi yazar) */
static volatile uint32_t s_irq_entry_us;
static uint32_t s_last_accepted_us;
static bool     s_have_first_edge;     /* ilk kenar her zaman kabul (R-BTN-3) */
static uint32_t s_next_id;

void button_irq_entry(void)
{
    s_irq_entry_us = timer_us();
}

/* HAL_GPIO_EXTI_IRQHandler bayrağı temizledikten sonra çağırır. */
void HAL_GPIO_EXTI_Callback(uint16_t pin)
{
    if (pin != B1_Pin)
    {
        return;
    }
    const uint32_t now = s_irq_entry_us;

    /* 30 ms tekrar-kenar filtresi. İşaretsiz fark sayaç taşmasına dayanıklı. */
    if (s_have_first_edge && (uint32_t)(now - s_last_accepted_us) < DEBOUNCE_US)
    {
        g_stats.bounce_rejected++;
        return;
    }
    s_have_first_edge = true;
    s_last_accepted_us = now;

    /* Isınmada ya da deney bittikten sonra gelen basış olay sayılmaz. */
    if (g_exp_state != EXP_RUNNING)
    {
        g_stats.ignored++;
        return;
    }

    const uint32_t id = s_next_id++;
    g_stats.accepted++;
    records_open(id, now);
    if (s_next_id >= TARGET_EVENTS)
    {
        g_exp_state = EXP_STOPPING;
    }

    ButtonEvent e = { id, now };
    BaseType_t wake = pdFALSE;
    if (xQueueSendFromISR(s_button_q, &e, &wake) != pdPASS)
    {
        /* Kuyruğa giremeyen olay kaybolmaz: kimliği ve t0'ı kayıtta kalır. */
        g_stats.btn_q_drop++;
        records_set_status(id, ST_BTN_DROP);
    }
    else
    {
        UBaseType_t n = uxQueueMessagesWaitingFromISR(s_button_q);
        if (n > g_stats.buttonq_hwm)
        {
            g_stats.buttonq_hwm = n;   /* yalnızca bu ISR yazar */
        }
    }
    portYIELD_FROM_ISR(wake);
}

static void post_export_marker(void)
{
    TxMsg m = { .type = MSG_CTRL_EXPORT };
    /* Deney bitti; burada beklemek ölçümü etkilemez. FIFO olduğu için
       işaret, kuyruktaki tüm mesajlardan sonra işlenir. */
    xQueueSend(uart_tx_queue(), &m, portMAX_DELAY);
}

static void ButtonTask(void *arg)
{
    (void)arg;
    const Scenario *sc = scenario_get();
    ButtonEvent e;

    /* Isınma: telemetri çalışıyor, basışlar yok sayılıyor, LD2 sönük. */
    vTaskDelay(pdMS_TO_TICKS(WARMUP_MS));
    g_exp_state = EXP_RUNNING;
    HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_SET);

    for (;;)
    {
        xQueueReceive(s_button_q, &e, portMAX_DELAY);
        records_stamp(e.id, T1, timer_us());

        TxMsg m;
        TextBuilder b;
        msg_begin(&b, &m, MSG_BTN, e.id);
        tb_put_str(&b, "BTN,");
        tb_put_u32(&b, e.id);
        tb_put_str(&b, ",");
        tb_put_str(&b, sc->name);
        tb_put_str(&b, ",PRESSED");
        if (!msg_finish(&b))
        {
            g_stats.msg_overflow++;
            configASSERT(0);
        }

        records_stamp(e.id, T2, timer_us());   /* gönderimden hemen önce */
        if (!uart_tx_post(&m))
        {
            g_stats.btn_tx_drop++;
            records_set_status(e.id, ST_TX_DROP);
        }

        /* Son olay işlendi ve kuyrukta bekleyen yoksa export'u başlat.
           Öncelik 2 > 1: buttonQ boşken UartTxTask henüz çalışmamış olur. */
        if (g_exp_state == EXP_STOPPING && uxQueueMessagesWaiting(s_button_q) == 0U)
        {
            post_export_marker();
            vTaskSuspend(NULL);
        }
    }
}

void button_create(void)
{
    s_button_q = xQueueCreate(BUTTON_QUEUE_LEN, sizeof(ButtonEvent));
    configASSERT(s_button_q != NULL);

    BaseType_t ok = xTaskCreate(ButtonTask, "button", STACK_BUTTON, NULL,
                                PRIO_BUTTON, NULL);
    configASSERT(ok == pdPASS);
}
