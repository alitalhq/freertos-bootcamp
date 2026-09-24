#ifndef SCENARIO_H
#define SCENARIO_H

#include <stdint.h>

/* Senaryo tablosu (spec §7.1). Periyot 0 = telemetri kapalı. */
typedef struct {
    const char *name;        /* "S0".."S5" */
    uint32_t    period_ms;   /* telemetri periyodu */
    uint32_t    work_us;     /* hedef ek CPU işi (F5'te kalibre edilecek) */
} Scenario;

/* Derlenen senaryonun parametreleri */
const Scenario *scenario_get(void);

#endif /* SCENARIO_H */
