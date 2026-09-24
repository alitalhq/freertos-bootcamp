#include "workload.h"
#include "timebase.h"

#define CALIB_ITERS    10000U
#define CALIB_REPEATS  5

/* Sonuç buraya yazılır; derleyici işi "kullanılmayan" diye silemez (R-WRK-1). */
volatile uint32_t g_workload_sink;

static WorkloadCalib s_calib;

void workload_run(uint32_t iters)
{
    uint32_t x = g_workload_sink | 1U;   /* xorshift32 sıfır olmamalı */
    for (uint32_t i = 0; i < iters; i++)
    {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
    }
    g_workload_sink = x;
}

void workload_calibrate(uint32_t target_us)
{
    /* Scheduler öncesi: preemption yok, yalnızca HAL'in 1 ms TIM6 tick
       kesmesi araya girebilir. En kısa ölçümü almak bu kesmeyi dışlar. */
    uint32_t best = UINT32_MAX;
    for (int r = 0; r < CALIB_REPEATS; r++)
    {
        uint32_t t0 = timer_us();
        workload_run(CALIB_ITERS);
        uint32_t dt = timer_us() - t0;
        if (dt < best)
        {
            best = dt;
        }
    }

    s_calib.calib_iters = CALIB_ITERS;
    s_calib.calib_us = best;
    /* iters = hedef_us * (CALIB_ITERS / best); 64-bit ara sonuç taşmasın */
    s_calib.work_iters = (best == 0U) ? 0U
        : (uint32_t)(((uint64_t)target_us * CALIB_ITERS) / best);
}

const WorkloadCalib *workload_calib(void)
{
    return &s_calib;
}
