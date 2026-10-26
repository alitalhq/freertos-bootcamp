#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
int main(void) {
    board_init();
    app_init();
    vTaskStartScheduler();
    fatal(__FILE__, __LINE__);
}
