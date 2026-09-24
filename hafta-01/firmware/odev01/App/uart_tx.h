#ifndef UART_TX_H
#define UART_TX_H

#include <stdbool.h>
#include "msg.h"
#include "FreeRTOS.h"
#include "queue.h"

/* txQ'yu ve UartTxTask'ı oluşturur. UART'ın tek sahibi bu modül (R-TSK-2). */
void uart_tx_create(void);

/* Üreticiler (TelemetryTask, ButtonTask) için: mesajı beklemeden txQ'ya
   kopyalar (R-Q-3). Kuyruk doluysa false döner; drop'u çağıran sayar. */
bool uart_tx_post(const TxMsg *m);

/* Deney sonu export işaretini göndermek için (bkz. button.c). */
QueueHandle_t uart_tx_queue(void);

#endif /* UART_TX_H */
