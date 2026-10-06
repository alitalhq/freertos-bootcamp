#ifndef UART_TX_H
#define UART_TX_H

#include <stdbool.h>
#include "msg.h"

/* Kuyrukları ve UartTxTask'ı oluşturur. UART'ın tek sahibi bu modül (R-TSK-2).
   tx_q: TEL (A/B'de BTN de), urgent_q: yalnızca C'de BTN. İki kuyruğun
   toplamında en fazla TX_PENDING_MAX mesaj bekler. */
void uart_tx_create(void);

/* Üreticiler (TelemetryTask, ButtonTask) için: mesajı beklemeden doğru
   kuyruğa kopyalar (R-Q-3). Toplam sınır doluysa false; drop'u çağıran sayar. */
bool uart_tx_post(TxMsg *m);

/* Deney sonu export işareti: tx_q'nun sonuna girer, yer açılana kadar bekler. */
void uart_tx_post_export(void);

/* RX kesmesinden LAB yanıtı göndermek için. */
void uart_tx_post_from_isr(TxMsg *m);

#endif /* UART_TX_H */
