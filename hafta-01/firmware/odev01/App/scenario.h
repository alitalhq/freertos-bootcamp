#ifndef SCENARIO_H
#define SCENARIO_H

#include <stdint.h>

/* Çalışan deneyin parametreleri. Resmi derlemede SCENARIO tablosundan,
   lab modunda (APP_LAB_MODE) PC'nin gönderdiği RUN komutundan gelir. */
typedef struct {
    char     name[16];      /* "S0".."S5", çözümlüyse "S5-F1" gibi, özel "C.." */
    uint32_t period_ms;     /* telemetri periyodu, 0 = kapalı */
    uint32_t work_us;       /* hedef ek CPU işi (kalibre edilir) */
    uint32_t target;        /* bu kadar kabul edilen olaydan sonra export */
    uint32_t fix_mask;      /* FIX_* bitleri; resmi derlemede her zaman 0 */
    uint32_t inject;        /* 0 = elle basış, 1 = otomatik (EXTI yazılım tetik) */
    uint32_t gap_min_ms;    /* otomatik basışlar arası aralık */
    uint32_t gap_max_ms;
    uint32_t seed;          /* otomatik aralıklar için sözde rastgele tohum */
    uint32_t run_id;        /* PC'nin verdiği deneme numarası */
} RunConfig;

/* app_init'te, kalibrasyondan önce çağrılır. */
void run_config_init(void);

const RunConfig *run_config(void);

#endif /* SCENARIO_H */
