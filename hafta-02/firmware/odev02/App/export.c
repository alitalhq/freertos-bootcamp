#include "export.h"
#include "app_config.h"
#include "scenario.h"
#include "records.h"
#include "stats.h"
#include "msg.h"
#include "workload.h"
#include "lab.h"

#include "main.h"
#include "FreeRTOS.h"
#include "task.h"

static char s_line[EXPORT_LINE_MAX];

static void begin(TextBuilder *b, const char *tag)
{
    tb_init(b, s_line, EXPORT_LINE_MAX - 1);   /* son bayt LF için */
    tb_put_str(b, tag);
}

static void kv(TextBuilder *b, const char *key, uint32_t v)
{
    tb_put_str(b, ",");
    tb_put_str(b, key);
    tb_put_str(b, "=");
    tb_put_u32(b, v);
}

static void send(TextBuilder *b)
{
    configASSERT(!b->overflow);
    s_line[b->len++] = '\n';
    uart_tx_send_line(s_line, (uint16_t)b->len);
}

static void export_cfg(void)
{
    const RunConfig *sc = run_config();
    TextBuilder b;

    begin(&b, "CFG,scenario=");
    tb_put_str(&b, sc->name);
    kv(&b, "sysclk_hz", SystemCoreClock);
    kv(&b, "tick_hz", configTICK_RATE_HZ);
    kv(&b, "timer_hz", 1000000U);
    kv(&b, "baud", 115200U);
    tb_put_str(&b, ",freertos=" tskKERNEL_VERSION_NUMBER);
#ifdef __OPTIMIZE__
    tb_put_str(&b, ",opt=O1+");
#else
    tb_put_str(&b, ",opt=O0");
#endif
    send(&b);

    begin(&b, "CFG");
    kv(&b, "period_ms", sc->period_ms);
    kv(&b, "work_us", sc->work_us);
    kv(&b, "target_events", sc->target);
    kv(&b, "warmup_ms", WARMUP_MS);
    kv(&b, "debounce_us", DEBOUNCE_US);
    kv(&b, "deadline_us", DEADLINE_US);
    send(&b);

    begin(&b, "CFG");
    kv(&b, "msg_len", MSG_LEN);
    kv(&b, "txq_len", TX_QUEUE_LEN);
    kv(&b, "btnq_len", BUTTON_QUEUE_LEN);
    send(&b);

    const WorkloadCalib *wc = workload_calib();
    begin(&b, "CFG");
    kv(&b, "calib_iters", wc->calib_iters);
    kv(&b, "calib_us", wc->calib_us);
    kv(&b, "work_iters", wc->work_iters);
    send(&b);

    /* Standart dışı ayarlar: resmi derlemede lab=0, fix=0, inject=0. */
    begin(&b, "CFG");
    kv(&b, "lab", APP_LAB_MODE);
    kv(&b, "fix", sc->fix_mask);
    kv(&b, "inject", sc->inject);
#if APP_LAB_MODE
    kv(&b, "gap_min_ms", sc->gap_min_ms);
    kv(&b, "gap_max_ms", sc->gap_max_ms);
    kv(&b, "seed", sc->seed);
    kv(&b, "run", sc->run_id);
    kv(&b, "injected", lab_injected_count());
#endif
    send(&b);
}

/* REC,<Sx>,<id>,<t0>,<t1>,<t2>,<t3>,<t4>,<status> — eksik alan boş (R-REC-4) */
static void export_records(void)
{
    const char *name = run_config()->name;
    uint32_t n = g_stats.accepted;
    if (n > REC_POOL_SIZE)
    {
        n = REC_POOL_SIZE;
    }
    for (uint32_t id = 0; id < n; id++)
    {
        const EventRecord *r = records_get(id);
        TextBuilder b;
        begin(&b, "REC,");
        tb_put_str(&b, name);
        tb_put_str(&b, ",");
        tb_put_u32(&b, id);
        for (int s = T0; s < T_COUNT; s++)
        {
            tb_put_str(&b, ",");
            if (r->valid[s])
            {
                tb_put_u32(&b, r->t[s]);
            }
        }
        tb_put_str(&b, ",");
        tb_put_str(&b, records_status_name(r->status));
        send(&b);
        HAL_GPIO_TogglePin(LD2_GPIO_Port, LD2_Pin);   /* export göstergesi */
    }
}

/* TSK,<ad>,<öncelik>,<stack_hwm_words>: stack yeterliliği (spec §14) */
static void export_tasks(void)
{
    static TaskStatus_t st[8];
    UBaseType_t n = uxTaskGetSystemState(st, 8, NULL);
    for (UBaseType_t i = 0; i < n; i++)
    {
        TextBuilder b;
        begin(&b, "TSK,");
        tb_put_str(&b, st[i].pcTaskName);
        kv(&b, "prio", st[i].uxCurrentPriority);
        kv(&b, "stack_hwm_words", st[i].usStackHighWaterMark);
        send(&b);
    }
}

static void export_counters(void)
{
    TextBuilder b;

    begin(&b, "CNT");
    kv(&b, "accepted", g_stats.accepted);
    kv(&b, "bounce_rejected", g_stats.bounce_rejected);
    kv(&b, "ignored", g_stats.ignored);
    kv(&b, "btn_q_drop", g_stats.btn_q_drop);
    kv(&b, "buttonq_hwm", g_stats.buttonq_hwm);
    kv(&b, "rec_overflow", g_stats.rec_overflow);
    send(&b);

    begin(&b, "CNT");
    kv(&b, "tel_sent", g_stats.tel_sent);
    kv(&b, "tel_tx_drop", g_stats.tel_tx_drop);
    kv(&b, "btn_tx_drop", g_stats.btn_tx_drop);
    kv(&b, "msg_overflow", g_stats.msg_overflow);
    kv(&b, "txq_hwm", g_stats.txq_hwm);
    send(&b);

    begin(&b, "CNT");
    kv(&b, "uart_tx_ok", g_stats.uart_tx_ok);
    kv(&b, "uart_start_err", g_stats.uart_start_err);
    kv(&b, "uart_error", g_stats.uart_error);
    kv(&b, "uart_timeout", g_stats.uart_timeout);
    kv(&b, "free_heap", (uint32_t)xPortGetMinimumEverFreeHeapSize());
    send(&b);

    /* Gözlenen telemetri periyodu ve iş süresi. n=0 ise min/max anlamsız. */
    begin(&b, "CNT");
    kv(&b, "period_n", g_stats.period_n);
    if (g_stats.period_n > 0U)
    {
        kv(&b, "period_min_us", g_stats.period_min_us);
        kv(&b, "period_avg_us", g_stats.period_sum_us / g_stats.period_n);
        kv(&b, "period_max_us", g_stats.period_max_us);
    }
    kv(&b, "work_n", g_stats.work_n);
    if (g_stats.work_n > 0U)
    {
        kv(&b, "work_min_us", g_stats.work_min_us);
        kv(&b, "work_avg_us", g_stats.work_sum_us / g_stats.work_n);
        kv(&b, "work_max_us", g_stats.work_max_us);
    }
    send(&b);
}

void export_all(void)
{
    TextBuilder b;

    export_cfg();
    export_records();
    export_tasks();
    export_counters();

    begin(&b, "END");
    send(&b);
    HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);
}
