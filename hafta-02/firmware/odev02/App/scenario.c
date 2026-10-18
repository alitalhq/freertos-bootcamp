#include <string.h>

#include "scenario.h"
#include "app_config.h"
#include "lab.h"

typedef struct {
    const char *name;
    uint32_t    period_ms;
    uint32_t    burst;
    uint32_t    work_us;
} Scenario;

/* Hafta 1'in S0–S5'i ve Hafta 2'nin S6 darbe yükü */
static const Scenario k_scenarios[] = {
    { "S0",   0, 1, 0    },   /* telemetri kapalı, referans */
    { "S1", 100, 1, 0    },   /* 10 Hz  */
    { "S2",  20, 1, 0    },   /* 50 Hz  */
    { "S3",  10, 1, 0    },   /* 100 Hz */
    { "S4",  10, 1, 2000 },   /* 100 Hz + ~2 ms CPU işi */
    { "S5",  10, 1, 5000 },   /* 100 Hz + ~5 ms CPU işi */
    { "S6", 100, 4, 0    },   /* her 100 ms'de 4 TEL: kısa kuyruk darbesi */
};

_Static_assert(SCENARIO >= 0 && SCENARIO < (int)(sizeof k_scenarios / sizeof k_scenarios[0]),
               "SCENARIO 0..6 araliginda olmali");
_Static_assert(VARIANT == 'A' || VARIANT == 'B' || VARIANT == 'C',
               "VARIANT 'A', 'B' ya da 'C' olmali");

static RunConfig s_cfg;

void run_config_init(void)
{
    const Scenario *sc = &k_scenarios[SCENARIO];
    s_cfg.name[0] = (char)VARIANT;
    s_cfg.name[1] = '-';
    strncpy(&s_cfg.name[2], sc->name, sizeof s_cfg.name - 3);
    s_cfg.variant = VARIANT;
    s_cfg.period_ms = sc->period_ms;
    s_cfg.burst = sc->burst;
    s_cfg.work_us = sc->work_us;
    s_cfg.target = TARGET_EVENTS;
    s_cfg.inject = 0;
    s_cfg.trace = 0;

    /* PC'den RUN komutuyla gelen ayar varsa derleme varsayılanını ezer. */
    lab_load_config(&s_cfg);
}

const RunConfig *run_config(void)
{
    return &s_cfg;
}
