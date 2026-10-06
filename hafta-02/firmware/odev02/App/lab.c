#include "lab.h"

#if APP_LAB_MODE
#include <string.h>

#include "button.h"
#include "experiment.h"
#include "msg.h"
#include "stats.h"
#include "uart_tx.h"

#include "main.h"
#include "usart.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

/* ---- SRAM2'de yeniden başlatmaya dayanan ayar --------------------------
   Linker SRAM2'ye (0x10000000) hiçbir bölüm yerleştirmiyor; başlangıç kodu
   da burayı sıfırlamıyor. Yazılım reset'inde içerik korunur, güç kesilince
   bozulur: magic + checksum ile doğrulanır. */
#define LAB_MAGIC   0x4C414231U   /* "LAB1" */

typedef struct {
    uint32_t  magic;
    RunConfig cfg;
    uint32_t  check;
} LabStore;

#define LAB_STORE ((volatile LabStore *)0x10000000U)

static uint32_t checksum(const RunConfig *c)
{
    const uint8_t *p = (const uint8_t *)c;
    uint32_t h = 2166136261U;                 /* FNV-1a */
    for (uint32_t i = 0; i < sizeof *c; i++)
    {
        h = (h ^ p[i]) * 16777619U;
    }
    return h;
}

void lab_load_config(RunConfig *cfg)
{
    RunConfig c;
    memcpy(&c, (const void *)&LAB_STORE->cfg, sizeof c);
    if (LAB_STORE->magic != LAB_MAGIC || LAB_STORE->check != checksum(&c))
    {
        return;                               /* geçerli ayar yok: varsayılan kalır */
    }
    c.name[sizeof c.name - 1] = '\0';
    if (c.target == 0U || c.target > REC_POOL_SIZE) { c.target = TARGET_EVENTS; }
    if (c.gap_max_ms < c.gap_min_ms)              { c.gap_max_ms = c.gap_min_ms; }
    *cfg = c;
}

static void store_and_reset(const RunConfig *c)
{
    memcpy((void *)&LAB_STORE->cfg, c, sizeof *c);
    LAB_STORE->check = checksum(c);
    LAB_STORE->magic = LAB_MAGIC;
    __DSB();
    NVIC_SystemReset();
}

/* ---- LAB satırı (UartTxTask üzerinden, UART'ın tek sahibi korunur) ---- */

static void build_lab_msg(TxMsg *m)
{
    const RunConfig *c = run_config();
    TextBuilder b;
    msg_begin(&b, m, MSG_TEL, 0);    /* veri mesajı gibi gönderilir, kayıt tutulmaz */
    tb_put_str(&b, "LAB,");
    tb_put_u32(&b, c->run_id);
    tb_put_str(&b, ",");
    tb_put_str(&b, c->name);
    tb_put_str(&b, ",P");
    tb_put_u32(&b, c->period_ms);
    tb_put_str(&b, ",W");
    tb_put_u32(&b, c->work_us);
    tb_put_str(&b, ",F");
    tb_put_u32(&b, c->fix_mask);
    tb_put_str(&b, ",I");
    tb_put_u32(&b, c->inject);
    tb_put_str(&b, ",N");
    tb_put_u32(&b, c->target);
    (void)msg_finish(&b);
}

/* ---- Komut satırı ayrıştırma (USART2 RX kesmesi) ---------------------- */

static uint8_t  s_rx_byte;
static char     s_line[112];
static uint32_t s_line_len;

static uint32_t parse_u32(const char *s)
{
    uint32_t v = 0;
    while (*s >= '0' && *s <= '9')
    {
        v = v * 10U + (uint32_t)(*s++ - '0');
    }
    return v;
}

static void parse_run(char *args)
{
    RunConfig c = *run_config();             /* belirtilmeyen alan eskisi kalır */
    c.fix_mask = 0;
    c.run_id = 0;
    for (char *tok = strtok(args, " "); tok != NULL; tok = strtok(NULL, " "))
    {
        char *eq = strchr(tok, '=');
        if (eq == NULL) { continue; }
        *eq = '\0';
        const char *k = tok, *v = eq + 1;
        if      (!strcmp(k, "name"))   { strncpy(c.name, v, sizeof c.name - 1);
                                         c.name[sizeof c.name - 1] = '\0'; }
        else if (!strcmp(k, "period")) { c.period_ms  = parse_u32(v); }
        else if (!strcmp(k, "work"))   { c.work_us    = parse_u32(v); }
        else if (!strcmp(k, "target")) { c.target     = parse_u32(v); }
        else if (!strcmp(k, "fix"))    { c.fix_mask   = parse_u32(v); }
        else if (!strcmp(k, "inject")) { c.inject     = parse_u32(v); }
        else if (!strcmp(k, "gmin"))   { c.gap_min_ms = parse_u32(v); }
        else if (!strcmp(k, "gmax"))   { c.gap_max_ms = parse_u32(v); }
        else if (!strcmp(k, "seed"))   { c.seed       = parse_u32(v); }
        else if (!strcmp(k, "run"))    { c.run_id     = parse_u32(v); }
    }
    store_and_reset(&c);                      /* dönmez */
}

static void handle_line_isr(char *line)
{
    if (!strncmp(line, "RUN", 3))
    {
        parse_run(line + 3);
    }
    else if (!strcmp(line, "STOP"))
    {
        button_request_stop_from_isr();
    }
    else if (!strcmp(line, "PING"))
    {
        TxMsg m;
        build_lab_msg(&m);
        uart_tx_post_from_isr(&m);
    }
    else if (!strcmp(line, "DEFAULT"))
    {
        LAB_STORE->magic = 0;
        __DSB();
        NVIC_SystemReset();
    }
}

void lab_rx_rearm(void)
{
    (void)HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1);
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart != &huart2)
    {
        return;
    }
    const char ch = (char)s_rx_byte;
    if (ch == '\n' || ch == '\r')
    {
        if (s_line_len > 0U)
        {
            s_line[s_line_len] = '\0';
            s_line_len = 0;
            handle_line_isr(s_line);
        }
    }
    else if (s_line_len < sizeof s_line - 1U)
    {
        s_line[s_line_len++] = ch;
    }
    else
    {
        s_line_len = 0;                       /* aşırı uzun satır: at */
    }
    lab_rx_rearm();
}

void lab_start(void)
{
    TxMsg m;
    build_lab_msg(&m);
    (void)uart_tx_post(&m);
    lab_rx_rearm();
}

/* ---- Otomatik basış üreteci ---------------------------------------------
   Gerçek butonla aynı yolu kullanır: EXTI13'ü yazılımla tetikler (SWIER),
   böylece aynı ISR, aynı 30 ms filtre ve aynı t0 noktası çalışır. Aralıklar
   [gmin, gmax] içinde sözde rastgeledir; telemetri fazına kilitlenmez. */

static volatile uint32_t s_injected;

uint32_t lab_injected_count(void)
{
    return s_injected;
}

static void InjectTask(void *arg)
{
    (void)arg;
    const RunConfig *c = run_config();
    uint32_t x = c->seed | 1U;
    const uint32_t span = c->gap_max_ms - c->gap_min_ms + 1U;

    while (g_exp_state == EXP_WARMUP)
    {
        vTaskDelay(pdMS_TO_TICKS(10));
    }
    while (g_exp_state == EXP_RUNNING)
    {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        vTaskDelay(pdMS_TO_TICKS(c->gap_min_ms + (x % span)));
        if (g_exp_state != EXP_RUNNING)
        {
            break;
        }
        s_injected++;
        EXTI->SWIER1 = EXTI_SWIER1_SWI13;    /* "basış" */
    }
    vTaskSuspend(NULL);
}

void lab_create_tasks(void)
{
    if (run_config()->inject == 0U)
    {
        return;
    }
    BaseType_t ok = xTaskCreate(InjectTask, "inject", STACK_INJECT, NULL, PRIO_INJECT, NULL);
    configASSERT(ok == pdPASS);
}

#endif /* APP_LAB_MODE */
