/*
 * Hafta 5 ödevi: çerçeveli UART veri yolu, StreamBuffer ve task notification.
 *
 * Veri düzlemi
 *   UART RX ISR ──▶ rxStream (StreamBuffer, SPSC) ──▶ ParserTask (3)
 *   ParserTask ──Job kuyruğa + Give──▶ ExecuteTask (2) ──Resp kuyruğa + bit──▶ TxTask (2)
 *   LogTask (1) ──▶ logMsgs (MessageBuffer, SPSC) ──▶ TxTask
 *   TxTask ──▶ txStream (StreamBuffer, SPSC, küçük) ──▶ UART TX ISR
 *
 * Kontrol düzlemi (notification indeksi 1; indeks 0 StreamBuffer'a ayrılmış)
 *   ExecuteTask  : iş sayacı   (Give / Take(pdFALSE))
 *   ControlTask  : olay bitleri (STOP/START/buton/UART hatası, eSetBits)
 *   SetpointTask : en güncel ayar (eSetValueWithOverwrite)
 *   TxTask       : uyandırma bitleri (cevap, log, not, snapshot)
 *
 * Cevaplar seyrek ama acil, loglar yoğun ama düşük öncelikli ve aynı UART'ı
 * paylaşıyorlar. TxTask satır sınırlarında önce cevapları seçer; txStream
 * küçük tutulduğu için bir cevabın önünde en fazla TX_SB_SIZE bayt bekler.
 */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "stream_buffer.h"
#include "message_buffer.h"
#include <stdio.h>
#include <string.h>

#define FW_VERSION       "h5-1.0"
#define NI               1U        /* uygulama notification indeksi */

/* ControlTask olay bitleri */
#define EV_STOP_UART     0x01U
#define EV_START         0x02U
#define EV_STOP_BTN      0x04U
#define EV_UART_ERR      0x08U
#define EV_PROTO_ERR     0x10U     /* CRC/uzunluk/başlık hatası */
/* TxTask uyandırma bitleri */
#define TX_RESP          0x01U
#define TX_LOG           0x02U
#define TX_NOTE          0x04U
#define TX_SNAP          0x08U
/* HOLD maskesi (deney kontrolü, T6) */
#define HOLD_EXEC        0x01U
#define HOLD_CONTROL     0x02U
#define HOLD_SETPOINT    0x04U

#define MAX_PAYLOAD      48U
#define HDR_LEN          10U       /* SYNC(2) VER TYPE SEQ(4) LEN(2) */
#define FRAME_TIMEOUT_MS 100U
#define JOBQ_LEN         32U
#define RESPQ_LEN        16U
#define NOTEQ_LEN        16U
#define LOG_MB_SIZE      1024U
#define TX_SB_SIZE       128U
#define LOG_LINE_LEN     80U
#define BTN_DEBOUNCE_US  50000U

typedef struct { uint32_t seq, t_valid; uint8_t len; uint8_t payload[MAX_PAYLOAD]; } Job;
typedef struct { uint32_t seq, sum, setpoint, t_valid, t_done, stop_ep, start_ep; } Resp;
typedef struct { char kind; uint32_t a, b, c; } Note;   /* ACK ve olay satırları */

/* Başlangıç ayarı: SRAM2'de, yazılım reset'inde korunur (linker SRAM2'yi kullanmıyor). */
typedef struct { uint32_t magic, capacity, trigger, boots, check; } BootCfg;
#define BOOT_CFG   ((volatile BootCfg *)0x10000000U)
#define BOOT_MAGIC 0x48354346U   /* "H5CF" */

/* ---- Sayaçlar (muhasebe) ------------------------------------------------- */
typedef struct {
    /* UART ISR */
    volatile uint32_t isr_bytes, sb_accepted, sb_rejected, uart_err, rearm_err, tx_bytes;
    /* parser */
    uint32_t parser_read, ok_data, ok_ctrl, crc_err, len_err, hdr_err, timeout_err;
    uint32_t gap_data, dup_data, gap_ctrl, dup_ctrl, ctrl_rej, stalls, sb_hwm;
    /* iş yolu */
    uint32_t job_acc, job_rej, job_done, job_cancel, jobq_hwm, no_data_for_notify;
    volatile uint32_t job_inflight;
    /* TX yolu */
    uint32_t log_lines, log_drop, resp_lines, resp_drop, note_drop;
    /* kontrol */
    uint32_t stops, starts, btn_stops, btn_bounce, stop_max_us, btn_max_us;
    uint32_t stop_epoch, start_epoch;     /* RUNNING <=> eşit; iş başlangıcında R satırına yazılır */
} Stats;
static Stats st;

static StreamBufferHandle_t rxStream, txStream;
static MessageBufferHandle_t logMsgs;
static QueueHandle_t jobQ, respQ, noteQ;
static TaskHandle_t parserTask, execTask, controlTask, setpointTask, txTask, logTask;

static uint8_t rxByte;
static uint32_t rxCapacity = 1024, rxTrigger = 1, sessionId;
static volatile uint32_t running = 1, holdMask, stepRequest, setpoint;
static volatile uint32_t pendingTrigger, stallNextMs, logRate;   /* B/s */
static volatile uint32_t stopT0Uart, stopT0Btn, lastBtnUs;
static volatile uint32_t ctrlSeqStop, ctrlSeqStart, ctrlWasHeld, rxLastUs;

/* ---- Yardımcılar ------------------------------------------------------------ */

static uint16_t crc16_ccitt_false(const uint8_t *p, size_t n)
{
    uint16_t crc = 0xFFFFU;                 /* poly 0x1021, init 0xFFFF, refin/refout false */
    while (n--) {
        crc ^= (uint16_t)(*p++) << 8;
        for (int i = 0; i < 8; ++i) crc = (crc & 0x8000U) ? (uint16_t)((crc << 1) ^ 0x1021U) : (uint16_t)(crc << 1);
    }
    return crc;
}

static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }

static void note(char kind, uint32_t a, uint32_t b, uint32_t c)
{
    Note n = { kind, a, b, c };
    if (xQueueSend(noteQ, &n, 0) != pdPASS) ++st.note_drop;
    xTaskNotifyIndexed(txTask, NI, TX_NOTE, eSetBits);
}

/* ---- UART kesmeleri --------------------------------------------------------- */

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart != &huart2) return;
    BaseType_t woken = pdFALSE;
    ++st.isr_bytes;
    rxLastUs = timer_us();                    /* 100 ms timeout her baytta yenilenir */
    if (xStreamBufferSendFromISR(rxStream, &rxByte, 1, &woken) == 1) ++st.sb_accepted;
    else ++st.sb_rejected;                   /* rxStream dolu: bayt reddedildi */
    if (HAL_UART_Receive_IT(&huart2, &rxByte, 1) != HAL_OK) ++st.rearm_err;
    portYIELD_FROM_ISR(woken);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart != &huart2) return;
    ++st.uart_err;
    if (HAL_UART_Receive_IT(&huart2, &rxByte, 1) != HAL_OK) ++st.rearm_err;
    BaseType_t woken = pdFALSE;
    xTaskNotifyIndexedFromISR(controlTask, NI, EV_UART_ERR, eSetBits, &woken);
    portYIELD_FROM_ISR(woken);
}

/* board.c USART2_IRQHandler'dan HAL'den önce çağrılır: TX tamamen bizde. */
void app_uart_tx_isr(void)
{
    if ((USART2->CR1 & USART_CR1_TXEIE) && (USART2->ISR & USART_ISR_TXE)) {
        uint8_t b;
        BaseType_t woken = pdFALSE;
        if (xStreamBufferReceiveFromISR(txStream, &b, 1, &woken) == 1) {
            USART2->TDR = b;
            ++st.tx_bytes;
        } else {
            CLEAR_BIT(USART2->CR1, USART_CR1_TXEIE);   /* tampon boş: kesmeyi kapat */
        }
        portYIELD_FROM_ISR(woken);
    }
}

void app_button_isr(uint32_t now)
{
    if (now - lastBtnUs < BTN_DEBOUNCE_US) { ++st.btn_bounce; return; }
    lastBtnUs = now;
    stopT0Btn = now;                          /* t0 = ISR girişi */
    BaseType_t woken = pdFALSE;
    xTaskNotifyIndexedFromISR(controlTask, NI, EV_STOP_BTN, eSetBits, &woken);
    portYIELD_FROM_ISR(woken);
}

/* ---- TX yolu ------------------------------------------------------------------ */

static void tx_kick(void)
{
    taskENTER_CRITICAL();                     /* USART2 IRQ (öncelik 6) maskelenir */
    SET_BIT(USART2->CR1, USART_CR1_TXEIE);
    taskEXIT_CRITICAL();
}

/* Yalnız TxTask çağırır. Satır bölünmez: yer açılana kadar bloklanır. */
static void tx_line(const char *s, size_t n)
{
    configASSERT(n <= TX_SB_SIZE);
    tx_kick();
    size_t w = xStreamBufferSend(txStream, s, n, portMAX_DELAY);
    configASSERT(w == n);
    tx_kick();
}

/* Bir satırda en çok 6 alan: en kötü durumda ~115 bayt, TX_SB_SIZE'a sığar. */
static void kv_line(const char *tag, const char *const *keys, const uint32_t *vals, int count)
{
    char l[TX_SB_SIZE];
    int n = snprintf(l, sizeof l, "{\"t\":\"%s\"", tag);
    for (int i = 0; i < count; ++i)
        n += snprintf(l + n, sizeof l - (size_t)n, ",\"%s\":%lu", keys[i], (unsigned long)vals[i]);
    n += snprintf(l + n, sizeof l - (size_t)n, "}\n");
    configASSERT(n < (int)sizeof l);
    tx_line(l, (size_t)n);
}
#define KV(tag, ...) do { \
    static const char *const k_[] = { __VA_ARGS__ }; \
    kv_line(tag, k_, v_, (int)(sizeof k_ / sizeof k_[0])); } while (0)

static void hello(void)
{
    char l[TX_SB_SIZE];
    int n = snprintf(l, sizeof l, "{\"t\":\"H\",\"fw\":\"%s\",\"sid\":%lu,\"cap\":%lu,\"trg\":%lu,\"baud\":230400,\"tick\":1000}\n",
                     FW_VERSION, (unsigned long)sessionId, (unsigned long)rxCapacity, (unsigned long)rxTrigger);
    tx_line(l, (size_t)n);
}

static void snapshot(void)
{
    hello();                                  /* SNAPSHOT aynı zamanda HELLO/durum isteği */
    { const uint32_t v_[] = { sessionId, rxCapacity, rxTrigger, logRate, running, holdMask };
      KV("S1", "sid", "cap", "trg", "lr", "run", "hold"); }
    { const uint32_t v_[] = { st.isr_bytes, st.sb_accepted, st.sb_rejected, st.parser_read,
                              (uint32_t)xStreamBufferBytesAvailable(rxStream), st.uart_err };
      KV("S2", "isr", "acc", "rej", "rd", "rem", "ue"); }
    { const uint32_t v_[] = { st.ok_data, st.ok_ctrl, st.crc_err, st.len_err, st.hdr_err, st.timeout_err };
      KV("S3", "okd", "okc", "crc", "len", "hdr", "to"); }
    { const uint32_t v_[] = { st.gap_data, st.dup_data, st.gap_ctrl, st.dup_ctrl, st.ctrl_rej, st.stalls };
      KV("S4", "gap", "dup", "gapc", "dupc", "crej", "stl"); }
    { const uint32_t v_[] = { st.job_acc, st.job_rej, st.job_done, st.job_cancel,
                              (uint32_t)uxQueueMessagesWaiting(jobQ), st.job_inflight };
      KV("S5", "ja", "jr", "jd", "jx", "jq", "ji"); }
    { const uint32_t v_[] = { st.jobq_hwm, st.no_data_for_notify, st.sb_hwm, st.rearm_err, st.tx_bytes, st.note_drop };
      KV("S6", "jqh", "nnd", "sbh", "re", "txb", "ndr"); }
    { const uint32_t v_[] = { st.log_lines, st.log_drop, st.resp_lines, st.resp_drop, st.stops, st.starts };
      KV("S7", "ll", "ldr", "rl", "rdr", "stp", "sta"); }
    { const uint32_t v_[] = { st.btn_stops, st.btn_bounce, st.stop_max_us, st.btn_max_us,
                              (uint32_t)xPortGetFreeHeapSize(), (uint32_t)xPortGetMinimumEverFreeHeapSize() };
      KV("S8", "btn", "bnc", "smax", "bmax", "heap", "hmin"); }
    /* stack yüksek su izi (word cinsinden boş kalan en az alan) */
    { const uint32_t v_[] = { uxTaskGetStackHighWaterMark(parserTask), uxTaskGetStackHighWaterMark(execTask),
                              uxTaskGetStackHighWaterMark(controlTask), uxTaskGetStackHighWaterMark(setpointTask),
                              uxTaskGetStackHighWaterMark(txTask), uxTaskGetStackHighWaterMark(logTask) };
      KV("S9", "P", "E", "C", "S", "T", "L"); }
}

static void TxTask(void *arg)
{
    (void)arg;
    char l[TX_SB_SIZE];
    int n;
    hello();
    for (;;) {
        uint32_t bits = 0;
        xTaskNotifyWaitIndexed(NI, 0, UINT32_MAX, &bits, pdMS_TO_TICKS(5));
        if (bits & TX_SNAP) snapshot();
        /* Her satırdan önce yeniden kontrol: önce notlar, sonra cevaplar, en son loglar. */
        for (;;) {
            Note nt;
            Resp r;
            if (xQueueReceive(noteQ, &nt, 0) == pdPASS) {
                n = snprintf(l, sizeof l, "{\"t\":\"%c\",\"a\":%lu,\"b\":%lu,\"c\":%lu}\n",
                             nt.kind, (unsigned long)nt.a, (unsigned long)nt.b, (unsigned long)nt.c);
                tx_line(l, (size_t)n);
            } else if (xQueueReceive(respQ, &r, 0) == pdPASS) {
                const uint32_t tq = timer_us();       /* cevabın txStream'e girdiği an */
                n = snprintf(l, sizeof l, "{\"t\":\"R\",\"s\":%lu,\"c\":%lu,\"v\":%lu,\"d\":%lu,\"q\":%lu,\"e\":%lu,\"g\":%lu}\n",
                             (unsigned long)r.seq, (unsigned long)r.sum, (unsigned long)r.setpoint,
                             (unsigned long)(r.t_done - r.t_valid), (unsigned long)(tq - r.t_valid),
                             (unsigned long)r.stop_ep, (unsigned long)r.start_ep);
                tx_line(l, (size_t)n);
                ++st.resp_lines;
            } else {
                size_t m = xMessageBufferReceive(logMsgs, l, sizeof l, 0);
                if (m == 0) break;
                tx_line(l, m);
            }
        }
    }
}

/* Düşük öncelikli yoğun log üreticisi (sesli tarifteki "log datası"). */
static void LogTask(void *arg)
{
    (void)arg;
    TickType_t last = xTaskGetTickCount();
    uint32_t carry = 0, counter = 0;
    char l[LOG_LINE_LEN + 4];
    for (;;) {
        vTaskDelayUntil(&last, pdMS_TO_TICKS(10));
        carry += logRate;                      /* 10 ms'de logRate/100 bayt */
        while (carry >= 100U * LOG_LINE_LEN) {
            carry -= 100U * LOG_LINE_LEN;
            int n = snprintf(l, sizeof l, "{\"t\":\"L\",\"n\":%lu,\"p\":\"", (unsigned long)counter++);
            while (n < (int)LOG_LINE_LEN - 3) l[n++] = 'x';
            l[n++] = '"'; l[n++] = '}'; l[n++] = '\n';
            if (xMessageBufferSend(logMsgs, l, (size_t)n, 0) == 0) ++st.log_drop;
            else { ++st.log_lines; xTaskNotifyIndexed(txTask, NI, TX_LOG, eSetBits); }
        }
    }
}

/* ---- İş yolu ------------------------------------------------------------------ */

/* Bir sayaç birimi alınmış olarak çağrılır. STOP kontrolü ile kuyruktan alma tek
   adımda: ControlTask (öncelik 4) araya giremez, STOP'tan sonra yeni iş başlamaz.
   Durdurulmuşsa sayaç birimi geri verilir (bekleyen işler saklanır, iptal yok). */
static void process_one(void)
{
    Job j;
    vTaskSuspendAll();
    const uint32_t run = running;
    const uint32_t ep_stop = st.stop_epoch, ep_start = st.start_epoch;
    const BaseType_t got = run ? xQueueReceive(jobQ, &j, 0) : pdFAIL;
    if (got == pdPASS) st.job_inflight = 1;
    (void)xTaskResumeAll();
    if (!run) { xTaskNotifyGiveIndexed(execTask, NI); return; }
    if (got != pdPASS) { ++st.no_data_for_notify; return; }   /* olmamalı */
    uint32_t sum = 0;
    for (uint8_t i = 0; i < j.len; ++i) sum += j.payload[i];
    vTaskDelay(pdMS_TO_TICKS(2));             /* servis beklemesi modeli, CPU yükü değil */
    Resp r = { j.seq, sum & 0xFFFFU, setpoint, j.t_valid, timer_us(), ep_stop, ep_start };
    ++st.job_done;
    st.job_inflight = 0;
    if (xQueueSend(respQ, &r, 0) != pdPASS) ++st.resp_drop;
    xTaskNotifyIndexed(txTask, NI, TX_RESP, eSetBits);
}

static void ExecuteTask(void *arg)
{
    (void)arg;
    for (;;) {
        if (holdMask & HOLD_EXEC) {           /* T6: kontrollü bekletme */
            if (stepRequest) {
                stepRequest = 0;
                uint32_t ret = ulTaskNotifyTakeIndexed(NI, pdFALSE, 0);
                uint32_t rem = ulTaskNotifyValueClearIndexed(NULL, NI, 0);
                note('K', ret, rem, 0);       /* Take dönüşü ve kalan */
                if (ret) process_one();
            }
            vTaskDelay(pdMS_TO_TICKS(1));
            continue;
        }
        if (!running) { vTaskDelay(pdMS_TO_TICKS(1)); continue; }   /* STOP: yeni iş başlatma */
        /* Take ile process_one arasında STOP gelirse sayaç process_one'da geri verilir. */
        if (ulTaskNotifyTakeIndexed(NI, pdFALSE, pdMS_TO_TICKS(5)) > 0) process_one();
    }
}

static void ControlTask(void *arg)
{
    (void)arg;
    for (;;) {
        if (holdMask & HOLD_CONTROL) { ctrlWasHeld = 1; vTaskDelay(pdMS_TO_TICKS(1)); continue; }
        uint32_t bits = 0;
        if (xTaskNotifyWaitIndexed(NI, 0, UINT32_MAX, &bits, pdMS_TO_TICKS(5)) != pdTRUE) continue;
        const uint32_t now = timer_us();
        const uint32_t held = ctrlWasHeld;   /* T6'da bilerek bekletildi: gecikme ölçümü sayılmaz */
        ctrlWasHeld = 0;
        if (bits & (EV_STOP_UART | EV_STOP_BTN)) {
            if (running) ++st.stop_epoch;
            running = 0;                      /* aynı maskede STOP baskın */
            HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_RESET);
            if (bits & EV_STOP_UART) {
                uint32_t lat = now - stopT0Uart;
                ++st.stops;
                if (!held && lat > st.stop_max_us) st.stop_max_us = lat;
                note('P', ctrlSeqStop, lat, bits);
            }
            if (bits & EV_STOP_BTN) {
                uint32_t lat = now - stopT0Btn;
                ++st.btn_stops;
                if (!held && lat > st.btn_max_us) st.btn_max_us = lat;
                note('B', st.btn_stops, lat, bits);
            }
        } else if (bits & EV_START) {
            if (!running) ++st.start_epoch;
            running = 1;
            HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);
            ++st.starts;
            note('G', ctrlSeqStart, now - stopT0Uart, bits);
        }
        if (bits & EV_UART_ERR) note('U', st.uart_err, 0, bits);
        if (bits & EV_PROTO_ERR) note('X', st.crc_err, st.len_err + st.hdr_err, bits);
    }
}

static void SetpointTask(void *arg)
{
    (void)arg;
    for (;;) {
        if (holdMask & HOLD_SETPOINT) { vTaskDelay(pdMS_TO_TICKS(1)); continue; }
        uint32_t v = 0;
        if (xTaskNotifyWaitIndexed(NI, 0, 0, &v, pdMS_TO_TICKS(5)) == pdTRUE) {
            setpoint = v;                     /* 0 geçerli bir değer */
            note('V', v, 0, 0);
        }
    }
}

/* ---- Parser ------------------------------------------------------------------- */

enum { P_SYNC0, P_SYNC1, P_HDR, P_BODY };
static uint8_t fb[HDR_LEN + MAX_PAYLOAD + 2];
static size_t fn, need;
static int pstate = P_SYNC0;
static uint8_t replay[2 * sizeof fb];
static size_t rpHead, rpLen;
static uint32_t expectData, expectCtrl;

static void parser_reset(void) { pstate = P_SYNC0; fn = 0; need = 0; }

/* Hatalı çerçevede: SYNC'ten sonraki bayttan itibaren yeniden tara. Payload içinde
   A5 5A olabilir; geçerli çerçeve uzunluğuyla tüketildiği için yalnız hata
   sonrasında yeniden aranır. */
static void parser_resync(void)
{
    xTaskNotifyIndexed(controlTask, NI, EV_PROTO_ERR, eSetBits);   /* aynı bit tekrarı birleşir */
    uint8_t tmp[sizeof replay];
    size_t k = 0;
    for (size_t i = 1; i < fn; ++i) tmp[k++] = fb[i];
    for (size_t i = rpHead; i < rpLen && k < sizeof tmp; ++i) tmp[k++] = replay[i];
    memcpy(replay, tmp, k);
    rpHead = 0;
    rpLen = k;
    parser_reset();
}

static void seq_check(uint32_t seq, uint32_t *expect, uint32_t *gap, uint32_t *dup)
{
    if (seq == 0U) { *expect = 1; return; }  /* yeni test oturumu */
    if (seq > *expect) *gap += seq - *expect;
    else if (seq < *expect) { ++*dup; return; }
    *expect = seq + 1U;
}

static void dispatch_control(uint32_t seq, const uint8_t *p, uint16_t len, uint32_t t0)
{
    const uint8_t op = len ? p[0] : 0;
    const uint32_t arg = (len == 5U) ? rd32(p + 1) : 0;
    int ok = 1;
    switch (op) {
    case 0x01: if (len != 1) { ok = 0; break; }                       /* STOP */
        stopT0Uart = t0; ctrlSeqStop = seq;
        xTaskNotifyIndexed(controlTask, NI, EV_STOP_UART, eSetBits); break;
    case 0x02: if (len != 1) { ok = 0; break; }                       /* START */
        ctrlSeqStart = seq;
        xTaskNotifyIndexed(controlTask, NI, EV_START, eSetBits); break;
    case 0x03: if (len != 1) { ok = 0; break; }                       /* SNAPSHOT */
        xTaskNotifyIndexed(txTask, NI, TX_SNAP, eSetBits); break;
    case 0x04: if (len != 5 || arg > 1000U) { ok = 0; break; }        /* SETPOINT */
        xTaskNotifyIndexed(setpointTask, NI, arg, eSetValueWithOverwrite); break;
    case 0x05: if (len != 5 || arg > 200U) { ok = 0; break; }         /* STALL_NEXT */
        stallNextMs = arg; break;
    /* Ek komutlar (README'de belgelendi): deney kontrolü */
    case 0x10: if (len != 5 || arg > 7U) { ok = 0; break; }           /* HOLD maskesi */
        holdMask = arg; break;
    case 0x11: if (len != 1) { ok = 0; break; }                       /* STEP: tek Take */
        stepRequest = 1; break;
    case 0x12: if (len != 5 || arg > 1000U) { ok = 0; break; }        /* SETPOINT, overwrite yok */
        note('W', arg, xTaskNotifyIndexed(setpointTask, NI, arg, eSetValueWithoutOverwrite) == pdPASS, 0); break;
    case 0x13: if (len != 5 || (arg != 1U && arg != 8U && arg != 32U)) { ok = 0; break; }   /* trigger */
        pendingTrigger = arg; break;
    case 0x14: if (len != 5 || arg > 40000U) { ok = 0; break; }       /* log hızı, B/s */
        logRate = arg; break;
    case 0x15: if (len != 5 || (arg != 256U && arg != 512U && arg != 1024U)) { ok = 0; break; }
        BOOT_CFG->capacity = arg;                                     /* kapasite: reset ile */
        BOOT_CFG->check = BOOT_CFG->magic ^ arg ^ BOOT_CFG->trigger;
        __DSB(); NVIC_SystemReset(); break;
    default: ok = 0;
    }
    if (!ok) ++st.ctrl_rej;
    if (op != 0x01 && op != 0x02) note('A', seq, op, ok);
}

static void frame_done(void)
{
    const uint8_t type = fb[3];
    const uint32_t seq = rd32(fb + 4);
    const uint16_t len = (uint16_t)(fb[8] | (fb[9] << 8));
    const uint16_t crc = (uint16_t)(fb[HDR_LEN + len] | (fb[HDR_LEN + len + 1] << 8));
    if (crc16_ccitt_false(fb + 2, 8U + len) != crc) { ++st.crc_err; parser_resync(); return; }
    const uint32_t t0 = timer_us();           /* doğrulama anı */
    if (type == 0x01) {
        ++st.ok_data;
        seq_check(seq, &expectData, &st.gap_data, &st.dup_data);
        Job j = { seq, t0, (uint8_t)len, {0} };
        memcpy(j.payload, fb + HDR_LEN, len);
        if (xQueueSend(jobQ, &j, 0) == pdPASS) {
            ++st.job_acc;                     /* önce veri kabul, sonra bildirim */
            UBaseType_t q = uxQueueMessagesWaiting(jobQ);
            if (q > st.jobq_hwm) st.jobq_hwm = q;
            xTaskNotifyGiveIndexed(execTask, NI);
        } else {
            ++st.job_rej;
        }
    } else {
        ++st.ok_ctrl;
        seq_check(seq, &expectCtrl, &st.gap_ctrl, &st.dup_ctrl);
        dispatch_control(seq, fb + HDR_LEN, len, t0);
    }
    parser_reset();
}

static void parser_step(uint8_t b)
{
    switch (pstate) {
    case P_SYNC0:
        if (b == 0xA5U) { fb[0] = b; fn = 1; pstate = P_SYNC1; }
        break;
    case P_SYNC1:
        if (b == 0x5AU) { fb[1] = b; fn = 2; pstate = P_HDR; }
        else if (b != 0xA5U) parser_reset();
        break;
    case P_HDR:
        fb[fn++] = b;
        if (fn == HDR_LEN) {
            const uint16_t len = (uint16_t)(fb[8] | (fb[9] << 8));
            if (fb[2] != 0x01U || (fb[3] != 0x01U && fb[3] != 0x02U)) { ++st.hdr_err; parser_resync(); }
            else if (len > MAX_PAYLOAD) { ++st.len_err; parser_resync(); }
            else { need = HDR_LEN + len + 2U; pstate = P_BODY; }
        }
        break;
    default:
        fb[fn++] = b;
        if (fn == need) frame_done();
        break;
    }
}

static void parser_feed(const uint8_t *in, size_t n)
{
    size_t i = 0;
    for (;;) {
        uint8_t b;
        if (rpHead < rpLen) b = replay[rpHead++];
        else if (i < n) b = in[i++];
        else break;
        parser_step(b);
    }
}

static void ParserTask(void *arg)
{
    (void)arg;
    uint8_t buf[64];
    for (;;) {
        if (pendingTrigger) {                 /* okuyucu bağlamında, Receive dışında */
            xStreamBufferSetTriggerLevel(rxStream, pendingTrigger);
            rxTrigger = pendingTrigger;
            pendingTrigger = 0;
        }
        if (stallNextMs) {                    /* STALL_NEXT: yalnız bir kez, task gecikmesi */
            const uint32_t ms = stallNextMs;
            stallNextMs = 0;
            ++st.stalls;
            const uint32_t t0 = timer_us();
            vTaskDelay(pdMS_TO_TICKS(ms));
            /* a=istenen ms, b=gerçek süre us, c=bekleme sonunda rxStream doluluğu */
            note('T', ms, timer_us() - t0, (uint32_t)xStreamBufferBytesAvailable(rxStream));
        }
        const size_t avail = xStreamBufferBytesAvailable(rxStream);
        if (avail > st.sb_hwm) st.sb_hwm = avail;
        /* Yarım çerçeve varken bekleme, son bayttan itibaren kalan süre kadar.
           Trigger 8/32'de Receive her baytta uyanmaz; zamanı ISR tutuyor. */
        TickType_t wait = pdMS_TO_TICKS(FRAME_TIMEOUT_MS);
        if (pstate != P_SYNC0) {
            const uint32_t idle = timer_us() - rxLastUs;
            wait = idle >= FRAME_TIMEOUT_MS * 1000U ? 0 : pdMS_TO_TICKS((FRAME_TIMEOUT_MS * 1000U - idle) / 1000U + 1U);
        }
        const size_t n = xStreamBufferReceive(rxStream, buf, sizeof buf, wait);
        if (n > 0) {
            st.parser_read += n;
            parser_feed(buf, n);
        } else if (pstate != P_SYNC0 && timer_us() - rxLastUs >= FRAME_TIMEOUT_MS * 1000U) {
            ++st.timeout_err;                 /* yarım çerçeve temizlenir */
            parser_reset();
        }
    }
}

/* ---- Başlangıç -------------------------------------------------------------- */

void app_init(void)
{
    /* SRAM2'deki ayar: kapasite ve trigger yalnız başlangıçta seçilir. */
    if (BOOT_CFG->magic != BOOT_MAGIC ||
        BOOT_CFG->check != (BOOT_CFG->magic ^ BOOT_CFG->capacity ^ BOOT_CFG->trigger)) {
        BOOT_CFG->magic = BOOT_MAGIC; BOOT_CFG->capacity = 1024; BOOT_CFG->trigger = 1; BOOT_CFG->boots = 0;
        BOOT_CFG->check = BOOT_MAGIC ^ 1024U ^ 1U;
    }
    BOOT_CFG->boots++;
    rxCapacity = BOOT_CFG->capacity;
    rxTrigger = BOOT_CFG->trigger;
    sessionId = (BOOT_CFG->boots << 16) ^ (DWT->CYCCNT & 0xFFFFU);

    rxStream = xStreamBufferCreate(rxCapacity, rxTrigger);
    txStream = xStreamBufferCreate(TX_SB_SIZE, 1);
    logMsgs = xMessageBufferCreate(LOG_MB_SIZE);
    jobQ = xQueueCreate(JOBQ_LEN, sizeof(Job));
    respQ = xQueueCreate(RESPQ_LEN, sizeof(Resp));
    noteQ = xQueueCreate(NOTEQ_LEN, sizeof(Note));
    configASSERT(rxStream && txStream && logMsgs && jobQ && respQ && noteQ);

    /* RX burada açılır: zamanlayıcı başlayana kadar USART2 kesmesi BASEPRI ile maskeli,
       sonra CR1'e görev bağlamından dokunan tek yer tx_kick (kritik bölge). */
    configASSERT(HAL_UART_Receive_IT(&huart2, &rxByte, 1) == HAL_OK);

    configASSERT(xTaskCreate(ControlTask, "Control", 384, NULL, 4, &controlTask) == pdPASS);
    configASSERT(xTaskCreate(ParserTask, "Parser", 512, NULL, 3, &parserTask) == pdPASS);
    configASSERT(xTaskCreate(ExecuteTask, "Execute", 384, NULL, 2, &execTask) == pdPASS);
    configASSERT(xTaskCreate(TxTask, "Tx", 640, NULL, 2, &txTask) == pdPASS);
    configASSERT(xTaskCreate(SetpointTask, "Setpoint", 256, NULL, 1, &setpointTask) == pdPASS);
    configASSERT(xTaskCreate(LogTask, "Log", 384, NULL, 1, &logTask) == pdPASS);

    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, GPIO_PIN_SET);     /* RUNNING */
    HAL_NVIC_EnableIRQ(EXTI15_10_IRQn);                     /* görevler hazır: buton açılır */
}
