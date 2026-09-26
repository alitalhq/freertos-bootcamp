#include "app.h"
#include "timebase.h"
#include "uart_tx.h"
#include "button.h"
#include "telemetry.h"
#include "scenario.h"
#include "workload.h"
#include "lab.h"

void app_init(void)
{
    /* Scheduler öncesi: yalnızca donanım hazırlığı. UART'a buradan
       yazılmaz; UART'ın tek sahibi UartTxTask (R-TSK-2). */
    timebase_init();
    run_config_init();
    workload_calibrate(run_config()->work_us);   /* R-WRK-3 */
}

void app_create_tasks(void)
{
    /* Tüketici önce: üreticiler çalışmaya başladığında txQ hazır olsun. */
    uart_tx_create();
    button_create();
    telemetry_create();
#if APP_LAB_MODE
    lab_create_tasks();                   /* otomatik basış (inject=1 ise) */
#endif
}
