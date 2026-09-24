#include "scenario.h"
#include "app_config.h"

static const Scenario k_scenarios[] = {
    { "S0",   0, 0    },   /* telemetri kapalı, referans */
    { "S1", 100, 0    },   /* 10 Hz  */
    { "S2",  20, 0    },   /* 50 Hz  */
    { "S3",  10, 0    },   /* 100 Hz */
    { "S4",  10, 2000 },   /* 100 Hz + ~2 ms CPU işi */
    { "S5",  10, 5000 },   /* 100 Hz + ~5 ms CPU işi */
};

_Static_assert(SCENARIO >= 0 && SCENARIO < (int)(sizeof k_scenarios / sizeof k_scenarios[0]),
               "SCENARIO 0..5 araliginda olmali");

const Scenario *scenario_get(void)
{
    return &k_scenarios[SCENARIO];
}
