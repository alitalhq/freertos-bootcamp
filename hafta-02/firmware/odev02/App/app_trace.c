#include <stdbool.h>
#include <stddef.h>

#include "app_trace.h"
#include "app_config.h"
#include "export.h"
#include "msg.h"
#include "scenario.h"

#include "main.h"
#include "FreeRTOS.h"
#include "task.h"
#include "SEGGER_SYSVIEW.h"
#include "SEGGER_RTT.h"

extern const SEGGER_SYSVIEW_OS_API SYSVIEW_X_OS_TraceAPI;

/* ---- Uygulama olayları ------------------------------------------------
   SystemView'de "BTN" modülü altında görünür; parametre olay kimliğidir. */
static void module_desc(void);
static SEGGER_SYSVIEW_MODULE s_module = {
    "M=Odev2_BTN,T=BTN,S='Buton yanıt zinciri t0..t4'", TR_COUNT, 0, module_desc, NULL,
};

static const char *const k_event_desc[TR_COUNT] = {
    "0 BTN_ACCEPT id=%u",
    "1 BTN_TASK id=%u",
    "2 BTN_ENQUEUE id=%u pending=%u",
    "3 BTN_DROP id=%u pending=%u",
    "4 BTN_TX_START id=%u",
    "5 BTN_TX_TC id=%u",
};

static void module_desc(void)
{
    for (unsigned i = 0; i < TR_COUNT; i++)
    {
        SEGGER_SYSVIEW_RecordModuleDescription(&s_module, k_event_desc[i]);
    }
}

/* ---- Kaynak adları ve sistem tanımı -----------------------------------
   Post-mortem modunda SystemView her senkron noktasında bunu yeniden ister:
   tamponun başı üzerine yazılmış olsa da adlar ve koşu bilgisi dosyada kalır. */
#define MAX_NAMES 6
static struct { void *h; const char *name; } s_names[MAX_NAMES];
static uint32_t s_num_names;
static char     s_sysdesc[64];

void app_trace_name(void *handle, const char *name)
{
    if (s_num_names < MAX_NAMES)
    {
        s_names[s_num_names].h = handle;
        s_names[s_num_names].name = name;
        s_num_names++;
    }
}

static void send_sys_desc(void)
{
    SEGGER_SYSVIEW_SendSysDesc(s_sysdesc);
    /* O= SystemView'in API açıklama dosyasını seçer (SYSVIEW_FreeRTOS.txt):
       sürüm buraya değil N= alanına yazılır. */
    SEGGER_SYSVIEW_SendSysDesc("D=STM32L476RG,O=FreeRTOS");
    SEGGER_SYSVIEW_SendSysDesc("I#15=SysTick,I#54=USART2,I#56=EXTI15_10");
    for (uint32_t i = 0; i < s_num_names; i++)
    {
        SEGGER_SYSVIEW_NameResource((U32)s_names[i].h, s_names[i].name);
    }
}

void app_trace_init(void)
{
    /* SystemView zaman damgası: DWT CYCCNT (80 MHz). Debugger olmadan da sayar. */
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;

    const RunConfig *c = run_config();
    TextBuilder b;
    tb_init(&b, s_sysdesc, sizeof s_sysdesc - 1);
    tb_put_str(&b, "N=Odev2 FreeRTOS 10.3.1 ");
    tb_put_str(&b, c->name);
    tb_put_str(&b, " run=");
    tb_put_u32(&b, c->run_id);
    s_sysdesc[b.len] = '\0';

    SEGGER_SYSVIEW_Init(SystemCoreClock, SystemCoreClock, &SYSVIEW_X_OS_TraceAPI, send_sys_desc);
    /* SEGGER_SYSVIEW_Init_Ex, post-mortem modunda tamponu RTT kanal 1'e kurar ama
       paketlerin yazıldığı UpChannel'ı ayarlamaz (normal modda ayarlar). Ayarlanmazsa
       olaylar 16 baytlık kanal 0'a gider, kanal 1'de yalnız senkronlar kalır. */
    SEGGER_SYSVIEW_GetMainContext()->UpChannel = SEGGER_SYSVIEW_RTT_CHANNEL;
    SEGGER_SYSVIEW_SetRAMBase(SEGGER_SYSVIEW_ID_BASE);
    SEGGER_SYSVIEW_RegisterModule(&s_module);
}

/* ---- Kayıt penceresi ---------------------------------------------------- */

static volatile bool s_started;
static volatile bool s_stopped;
static uint32_t s_rd, s_wr;          /* durdurulduğu andaki halka sınırları */

void app_trace_start(void)
{
    if (!run_config()->trace)
    {
        return;
    }
    SEGGER_SYSVIEW_Start();          /* post-mortem: senkron + sistem bilgisi yazar */
    s_started = true;
}

void app_trace_stop(void)
{
    if (!s_started || s_stopped)
    {
        return;
    }
    SEGGER_SYSVIEW_Stop();
    const SEGGER_RTT_BUFFER_UP *up = &_SEGGER_RTT.aUp[SEGGER_SYSVIEW_RTT_CHANNEL];
    s_rd = up->RdOff;                /* en eski bayt (halka dolduysa üzerine yazılmış) */
    s_wr = up->WrOff;                /* bir sonraki yazılacak yer */
    s_stopped = true;
}

void app_trace_event(TraceEvent e, uint32_t id, uint32_t detail)
{
    if (!s_started)
    {
        return;                      /* trace=0: hiç kayıt yok */
    }
    SEGGER_SYSVIEW_RecordU32x2(s_module.EventOffset + (unsigned)e, id, detail);
}

void app_trace_isr_enter(void)
{
    SEGGER_SYSVIEW_RecordEnterISR();
}

void app_trace_isr_exit(void)
{
    /* ISR bir görevi uyandırdıysa PendSV beklemededir: SystemView'e
       "scheduler'a dönüyor" diye kaydet, yoksa kesilen göreve dönüş. */
    if (SCB->ICSR & SCB_ICSR_PENDSVSET_Msk)
    {
        SEGGER_SYSVIEW_RecordExitISRToScheduler();
    }
    else
    {
        SEGGER_SYSVIEW_RecordExitISR();
    }
}

/* ---- Dışa aktarma ------------------------------------------------------
   TRC,run=<id>,bytes=<n>,fnv=<hex>,wrapped=<0|1>
   HEX,<offset>,<hex>        (en eskiden en yeniye, satır başına 48 bayt)
   TRC_END
   Baytlar SystemView'in .SVDat dosyasının kendisidir; PC birleştirip yazar. */

#define HEX_BYTES_PER_LINE 48

static uint32_t fnv1a(uint32_t h, uint8_t byte)
{
    return (h ^ byte) * 16777619U;
}

static void hex_line(char *out, uint32_t *len, const uint8_t *p, uint32_t n)
{
    static const char k_hex[] = "0123456789ABCDEF";
    for (uint32_t i = 0; i < n; i++)
    {
        out[(*len)++] = k_hex[p[i] >> 4];
        out[(*len)++] = k_hex[p[i] & 0xF];
    }
}

void app_trace_export(void)
{
    if (!s_stopped)
    {
        return;
    }
    const SEGGER_RTT_BUFFER_UP *up = &_SEGGER_RTT.aUp[SEGGER_SYSVIEW_RTT_CHANNEL];
    const uint8_t *buf = (const uint8_t *)up->pBuffer;
    const uint32_t size = up->SizeOfBuffer;
    const uint32_t total = (s_wr >= s_rd) ? (s_wr - s_rd) : (size - s_rd + s_wr);

    uint32_t h = 2166136261U;
    for (uint32_t i = 0, pos = s_rd; i < total; i++, pos = (pos + 1U == size) ? 0U : pos + 1U)
    {
        h = fnv1a(h, buf[pos]);
    }

    static char line[EXPORT_LINE_MAX];
    TextBuilder b;
    tb_init(&b, line, EXPORT_LINE_MAX - 1);
    tb_put_str(&b, "TRC,run=");
    tb_put_u32(&b, run_config()->run_id);
    tb_put_str(&b, ",bytes=");
    tb_put_u32(&b, total);
    tb_put_str(&b, ",fnv=");
    tb_put_u32(&b, h);
    tb_put_str(&b, ",wrapped=");
    tb_put_u32(&b, s_rd != 0U ? 1U : 0U);
    line[b.len++] = '\n';
    uart_tx_send_line(line, (uint16_t)b.len);

    uint8_t chunk[HEX_BYTES_PER_LINE];
    for (uint32_t off = 0, pos = s_rd; off < total;)
    {
        uint32_t n = total - off;
        if (n > HEX_BYTES_PER_LINE)
        {
            n = HEX_BYTES_PER_LINE;
        }
        for (uint32_t i = 0; i < n; i++, pos = (pos + 1U == size) ? 0U : pos + 1U)
        {
            chunk[i] = buf[pos];
        }
        tb_init(&b, line, EXPORT_LINE_MAX - 1);
        tb_put_str(&b, "HEX,");
        tb_put_u32(&b, off);
        tb_put_str(&b, ",");
        uint32_t len = b.len;
        hex_line(line, &len, chunk, n);
        line[len++] = '\n';
        uart_tx_send_line(line, (uint16_t)len);
        off += n;
    }

    uart_tx_send_line("TRC_END\n", 8);
}
