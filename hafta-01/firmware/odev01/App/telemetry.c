#include "telemetry.h"
#include "app_config.h"
#include "scenario.h"
#include "msg.h"
#include "stats.h"
#include "uart_tx.h"
#include "experiment.h"
#include "timebase.h"
#include "workload.h"

#include "FreeRTOS.h"
#include "task.h"

static void TelemetryTask(void *arg)
{
    (void)arg;
    const Scenario *sc = scenario_get();

    if (sc->period_ms == 0U)
    {
        /* S0: telemetri kapalı. Boş döngüde dönmek yerine bloklan (R-SCN-2). */
        vTaskSuspend(NULL);
    }

    const TickType_t period = pdMS_TO_TICKS(sc->period_ms);
    configASSERT(period > 0U);

    const uint32_t iters = workload_calib()->work_iters;
    uint32_t seq = 0;
    uint32_t prev_act = 0;
    TickType_t last = xTaskGetTickCount();

    for (;;)
    {
        /* Deney bitti: telemetriyi durdur ki txQ boşalıp export başlasın. */
        if (g_exp_state >= EXP_STOPPING)
        {
            vTaskSuspend(NULL);
        }

        /* Gerçek aktivasyon periyodu: planlanan değil, gözlenen (spec §7.1). */
        const uint32_t act = timer_us();
        if (seq > 0U)
        {
            stats_period_sample(act - prev_act);
        }
        prev_act = act;

        /* S4/S5: kalibre CPU işi. Süre duvar saatidir; kesme süresi dahil. */
        if (iters > 0U)
        {
            workload_run(iters);
            stats_work_sample(timer_us() - act);
        }

        TxMsg m;
        TextBuilder b;
        msg_begin(&b, &m, MSG_TEL, seq);
        tb_put_str(&b, "TEL,");
        tb_put_u32(&b, seq);
        tb_put_str(&b, ",");
        tb_put_str(&b, sc->name);
        tb_put_str(&b, ",");
        tb_put_u32(&b, (uint32_t)(xTaskGetTickCount() * portTICK_PERIOD_MS));
        if (!msg_finish(&b))
        {
            g_stats.msg_overflow++;
            configASSERT(0);
        }

        if (uart_tx_post(&m))
        {
            g_stats.tel_sent++;
        }
        else
        {
            g_stats.tel_tx_drop++;
        }
        seq++;

        /* Mutlak periyot tabanı: iş süresi periyodu kaydırmaz (spec §7.1).
           FreeRTOS 10.3.1'de xTaskDelayUntil yok; eşdeğeri vTaskDelayUntil. */
        vTaskDelayUntil(&last, period);
    }
}

void telemetry_create(void)
{
    BaseType_t ok = xTaskCreate(TelemetryTask, "telemetry", STACK_TELEMETRY,
                                NULL, PRIO_TELEMETRY, NULL);
    configASSERT(ok == pdPASS);
}
