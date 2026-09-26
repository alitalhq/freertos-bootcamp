#include <string.h>

#include "scenario.h"
#include "app_config.h"
#if APP_LAB_MODE
#include "lab.h"
#endif

typedef struct {
    const char *name;
    uint32_t    period_ms;
    uint32_t    work_us;
} Scenario;

/* Ödevin altı zorunlu senaryosu (spec §7.1) */
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

static RunConfig s_cfg;

void run_config_init(void)
{
    const Scenario *sc = &k_scenarios[SCENARIO];
    strncpy(s_cfg.name, sc->name, sizeof s_cfg.name - 1);
    s_cfg.period_ms = sc->period_ms;
    s_cfg.work_us = sc->work_us;
    s_cfg.target = TARGET_EVENTS;
    s_cfg.fix_mask = 0;
    s_cfg.inject = 0;

#if APP_LAB_MODE
    /* PC'den RUN komutuyla gelen ayar varsa derleme varsayılanını ezer. */
    lab_load_config(&s_cfg);
#endif
}

const RunConfig *run_config(void)
{
    return &s_cfg;
}
