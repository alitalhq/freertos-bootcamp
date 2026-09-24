#ifndef EXPERIMENT_H
#define EXPERIMENT_H

#include <stdint.h>

/* Deney akışı (spec §8, ADR-003). Durum yalnızca ileri gider. */
typedef enum {
    EXP_WARMUP = 0,   /* ButtonTask -> RUNNING (5 s sonra) */
    EXP_RUNNING,      /* buton ISR -> STOPPING (hedef sayıya ulaşınca) */
    EXP_STOPPING,     /* telemetri durur, txQ boşaltılır, export */
    EXP_DONE,         /* UartTxTask: END gönderildi */
} ExpState;

extern volatile uint8_t g_exp_state;   /* ExpState */

#endif /* EXPERIMENT_H */
