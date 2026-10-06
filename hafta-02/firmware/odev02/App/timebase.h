#ifndef TIMEBASE_H
#define TIMEBASE_H

#include <stdint.h>
#include "stm32l4xx.h"

/* TIM2'yi serbest sayan 1 MHz sayaç olarak başlatır (ADR-002). */
void timebase_init(void);

/* Mikrosaniye zaman damgası. ISR içinden güvenle çağrılabilir.
   32-bit sayaç ~71,6 dakikada bir sarar; farkları uint32_t ile alın. */
static inline uint32_t timer_us(void)
{
    return TIM2->CNT;
}

#endif /* TIMEBASE_H */
