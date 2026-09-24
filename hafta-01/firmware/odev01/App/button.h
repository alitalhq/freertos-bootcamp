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

#endif /* BUTTON_H */
