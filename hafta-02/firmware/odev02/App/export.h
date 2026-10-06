#ifndef EXPORT_H
#define EXPORT_H

#include <stdint.h>

#define EXPORT_LINE_MAX  192   /* 64 baytlık mesajlardan uzun olabilir */

/* Deney sonu: CFG, REC x N, TSK, CNT ve END satırlarını gönderir
   (spec §3.4, §8). Yalnızca UartTxTask bağlamından çağrılır. */
void export_all(void);

/* uart_tx.c sağlar: tek satır gönder ve TC'yi bekle. */
void uart_tx_send_line(const char *s, uint16_t len);

#endif /* EXPORT_H */
