#include "stats.h"
#include "FreeRTOS.h"
#include "task.h"

Stats g_stats = {
    .period_min_us = UINT32_MAX,
    .work_min_us = UINT32_MAX,
};

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

static void sample(uint32_t *mn, uint32_t *mx, uint32_t *sum, uint32_t *n, uint32_t us)
{
    if (us < *mn) { *mn = us; }
    if (us > *mx) { *mx = us; }
    *sum += us;   /* birkaç dakikalık deney: 2^32 us (~71 dk) altında kalır */
    (*n)++;
}

void stats_period_sample(uint32_t us)
{
    sample(&g_stats.period_min_us, &g_stats.period_max_us,
           &g_stats.period_sum_us, &g_stats.period_n, us);
}

void stats_work_sample(uint32_t us)
{
    sample(&g_stats.work_min_us, &g_stats.work_max_us,
           &g_stats.work_sum_us, &g_stats.work_n, us);
}
