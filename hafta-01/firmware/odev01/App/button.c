#include "button.h"
#include "app_config.h"
#include "scenario.h"
#include "msg.h"
#include "stats.h"
#include "uart_tx.h"

#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

static QueueHandle_t s_button_q;

static void ButtonTask(void *arg)
{
    (void)arg;
    const Scenario *sc = scenario_get();
    ButtonEvent e;

    for (;;)
    {
        xQueueReceive(s_button_q, &e, portMAX_DELAY);
        /* t1 burada kaydedilecek (F4). */

        TxMsg m;
        MsgBuilder b;
        msg_begin(&b, &m, MSG_BTN, e.id);
        msg_put_str(&b, "BTN,");
        msg_put_u32(&b, e.id);
        msg_put_str(&b, ",");
        msg_put_str(&b, sc->name);
        msg_put_str(&b, ",PRESSED");
        if (!msg_finish(&b))
        {
            g_stats.msg_overflow++;
            configASSERT(0);
        }

        /* t2 burada, gönderimden hemen önce kaydedilecek (F4). */
        if (!uart_tx_post(&m))
        {
            g_stats.btn_tx_drop++;
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
