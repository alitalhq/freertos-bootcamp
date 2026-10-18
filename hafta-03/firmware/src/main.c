#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "app_trace.h"
int main(void) {
    board_init();
    AppTrace_Init();
    app_init();
    vTaskStartScheduler();
    fatal(__FILE__, __LINE__);
}
