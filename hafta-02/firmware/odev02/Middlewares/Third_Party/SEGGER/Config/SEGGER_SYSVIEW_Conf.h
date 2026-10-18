/* SystemView hedef ayarları (Ödev 2, SystemView ödevi).
 *
 * J-Link yok: kayıt RAM'deki halka tampona yapılır (post-mortem modu) ve deney
 * sonunda USART2 üzerinden .SVDat olarak dışarı alınır (App/app_trace.c). */
#ifndef SEGGER_SYSVIEW_CONF_H
#define SEGGER_SYSVIEW_CONF_H

/* Halka tampon: en eski veri üstüne yazılır, durdurulduğunda son ~1–2 s kalır. */
#define SEGGER_SYSVIEW_POST_MORTEM_MODE   1
#define SEGGER_SYSVIEW_RTT_BUFFER_SIZE    32768
#define SEGGER_SYSVIEW_RTT_CHANNEL        1
/* Her 256 pakette bir senkron + görev listesi: kesilmiş tamponun başından
   bağımsız olarak SystemView çözmeye başlayabilsin. */
#define SEGGER_SYSVIEW_SYNC_PERIOD_SHIFT  8

/* Zaman damgası: DWT CYCCNT, 80 MHz (app_trace.c etkinleştirir). TIM2 (1 MHz)
   ile aynı saat değildir; iki saatin mutlak değerleri birbirinden çıkarılmaz. */
#define SEGGER_SYSVIEW_TIMESTAMP_BITS     32
#define SEGGER_SYSVIEW_GET_TIMESTAMP()    (*(volatile unsigned long *)0xE0001004UL)
#define SEGGER_SYSVIEW_GET_INTERRUPT_ID() ((*(volatile unsigned long *)0xE000ED04UL) & 0x1FFUL)

#define SEGGER_SYSVIEW_ID_BASE            0x20000000UL

#endif /* SEGGER_SYSVIEW_CONF_H */
