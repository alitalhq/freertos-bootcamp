#include "app.h"
#include "timebase.h"
#include "uart_tx.h"
#include "button.h"
#include "telemetry.h"

void app_init(void)
{
    /* Scheduler öncesi: yalnızca donanım hazırlığı. UART'a buradan
       yazılmaz; UART'ın tek sahibi UartTxTask (R-TSK-2). */
    timebase_init();
}

void app_create_tasks(void)
{
    /* Tüketici önce: üreticiler çalışmaya başladığında txQ hazır olsun. */
    uart_tx_create();
    button_create();
    telemetry_create();
}
