#ifndef BUTTON_H
#define BUTTON_H

#include <stdint.h>

/* buttonQ elemanı: ISR'dan değer olarak kopyalanır (R-Q-1). */
typedef struct {
    uint32_t id;
    uint32_t t0;
} ButtonEvent;

/* buttonQ'yu ve ButtonTask'ı oluşturur (öncelik 2). */
void button_create(void);

/* stm32l4xx_it.c -> EXTI15_10_IRQHandler'ın İLK satırı (USER CODE 0).
   t0'ı HAL'in bayrak temizleme ve dağıtım kodundan önce yakalar (R-BTN-2). */
void button_irq_entry(void);

/* Lab: STOP komutu (RX kesmesi). Deneyi bitirir; ButtonTask export'u başlatır. */
void button_request_stop_from_isr(void);

#define BUTTON_CTRL_STOP_ID  0xFFFFFFFFU   /* buttonQ'da olay değil, kontrol */

#endif /* BUTTON_H */
