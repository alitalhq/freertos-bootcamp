#ifndef APP_TRACE_H
#define APP_TRACE_H

#include <stdint.h>

/* SystemView kaydı (SystemView ödevi). J-Link yok: kayıt RAM'deki halka
   tampona yapılır (post-mortem modu), deney bitince USART2'den .SVDat olarak
   alınır. Kayıt yalnızca RUN trace=1 ile açılır; trace=0'da kancalar derlenmiş
   ama kayıt kapalıdır (iz açık/kapalı karşılaştırması aynı binary ile).

   Uygulama olayları buton zincirinin t0..t4 noktalarıdır; parametre olay
   kimliğidir, CSV'deki event_id ile aynı. */
typedef enum {
    TR_BTN_ACCEPT = 0,   /* t0: EXTI ISR basışı kabul etti */
    TR_BTN_TASK,         /* t1: ButtonTask olayı aldı */
    TR_BTN_ENQUEUE,      /* t2: yanıt TX kuyruğuna girdi (+ bekleyen mesaj) */
    TR_BTN_DROP,         /* yanıt kuyruğa giremedi (+ bekleyen mesaj) */
    TR_BTN_TX_START,     /* t3: UART gönderimi başladı */
    TR_BTN_TX_TC,        /* t4: TC kesmesi, son bit hattan çıktı */
    TR_COUNT
} TraceEvent;

/* app_init'ten, scheduler öncesi: DWT sayacı ve SystemView. */
void app_trace_init(void);

/* Kaynak adları (kuyruk, semaphore): SystemView'de adres yerine ad görünsün. */
void app_trace_name(void *handle, const char *name);

/* Deney RUNNING'e geçince (ButtonTask). trace=0 ise bir şey yapmaz. */
void app_trace_start(void);

/* Export'tan hemen önce (UartTxTask): kayıt durur, tampon sabitlenir. */
void app_trace_stop(void);

/* Görev ya da ISR bağlamından. Kayıt kapalıyken kayıt yazılmaz. */
void app_trace_event(TraceEvent e, uint32_t id, uint32_t detail);

/* IRQ handler'larının başı ve sonu (stm32l4xx_it.c). */
void app_trace_isr_enter(void);
void app_trace_isr_exit(void);

/* END satırından sonra: TRC, HEX…, TRC_END. Yalnızca UartTxTask'tan. */
void app_trace_export(void);

#endif /* APP_TRACE_H */
