#include "stats.h"
#include "FreeRTOS.h"
#include "task.h"

Stats g_stats;

void stats_update_max(volatile uint32_t *field, uint32_t value)
{
    /* Oku-karşılaştır-yaz arasında başka görev araya girmesin. */
    taskENTER_CRITICAL();
    if (value > *field)
    {
        *field = value;
    }
    taskEXIT_CRITICAL();
}
