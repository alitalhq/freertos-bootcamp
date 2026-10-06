#ifndef STATS_H
#define STATS_H

#include <stdint.h>

/* Deney sayaçları (spec §8). Her alanı tek bir bağlam artırır; yazan
   bağlam yorumda belirtildi. Export sırasında okunur. */
typedef struct {
    /* buton ISR */
    volatile uint32_t accepted;       /* filtreden geçen ve deneye alınan basış */
    volatile uint32_t bounce_rejected;/* 30 ms içinde gelen tekrar kenarı */
    volatile uint32_t ignored;        /* ısınmada ya da deney bittikten sonra gelen basış */
    volatile uint32_t btn_q_drop;     /* buttonQ dolu */
    volatile uint32_t buttonq_hwm;    /* buttonQ en yüksek doluluk */
    volatile uint32_t rec_overflow;   /* kayıt havuzu doldu */
    /* üreticiler */
    volatile uint32_t tel_sent;       /* TelemetryTask: txQ'ya giren TEL */
    volatile uint32_t tel_tx_drop;    /* TelemetryTask: txQ dolu */
    volatile uint32_t btn_tx_drop;    /* ButtonTask: txQ dolu */
    volatile uint32_t msg_overflow;   /* üreticiler: 63 baytı aşan metin */
    volatile uint32_t txq_hwm;        /* üreticiler: txQ en yüksek doluluk */
    /* UART */
    volatile uint32_t uart_tx_ok;     /* UartTxTask: TC ile biten gönderim */
    volatile uint32_t uart_start_err; /* UartTxTask: HAL_UART_Transmit_IT != HAL_OK */
    volatile uint32_t uart_error;     /* USART2 ISR: ErrorCallback */
    volatile uint32_t uart_timeout;   /* UartTxTask: 1 s içinde TC gelmedi */
    /* TelemetryTask zamanlaması (yalnızca TelemetryTask yazar) */
    uint32_t period_min_us, period_max_us, period_sum_us, period_n;
    uint32_t work_min_us, work_max_us, work_sum_us, work_n;
} Stats;

extern Stats g_stats;

/* Birden çok görevin güncellediği maksimumlar için (kritik bölgede). */
void stats_update_max(volatile uint32_t *field, uint32_t value);

/* TelemetryTask: gözlenen aktivasyon periyodu ve kalibre iş süresi (µs). */
void stats_period_sample(uint32_t us);
void stats_work_sample(uint32_t us);

#endif /* STATS_H */
