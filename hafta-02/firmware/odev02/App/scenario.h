#ifndef SCENARIO_H
#define SCENARIO_H

#include <stdint.h>

/* Çalışan deneyin parametreleri. Kayıtlı ayar yoksa derleme varsayılanı
   (SCENARIO, VARIANT), varsa PC'nin gönderdiği RUN komutu (lab.h). */
typedef struct {
    char     name[16];      /* "A-S5" gibi; otomatik basışta sonda 'a' */
    uint32_t variant;       /* 'A', 'B' ya da 'C' */
    uint32_t period_ms;     /* telemetri periyodu, 0 = kapalı */
    uint32_t burst;         /* periyot başına TEL mesajı (S6: 4) */
    uint32_t work_us;       /* hedef ek CPU işi (kalibre edilir) */
    uint32_t target;        /* bu kadar kabul edilen olaydan sonra export */
    uint32_t inject;        /* 0 = elle basış, 1 = otomatik (EXTI yazılım tetik) */
    uint32_t gap_min_ms;    /* otomatik basışlar arası aralık */
    uint32_t gap_max_ms;
    uint32_t seed;          /* otomatik aralıklar için sözde rastgele tohum */
    uint32_t run_id;        /* PC'nin verdiği deneme numarası */
    uint32_t trace;         /* 1 = SystemView kaydı açık (app_trace.h) */
    uint32_t tx_prio;       /* UartTxTask önceliği; 0 = sürümün varsayılanı (1) */
} RunConfig;

/* app_init'te, kalibrasyondan önce çağrılır. */
void run_config_init(void);

const RunConfig *run_config(void);

/* C: BTN yanıtı aktarım sınırında öne alınır (uart_tx.c). */
static inline int variant_btn_first(const RunConfig *c)
{
    return c->variant == 'C';
}

#endif /* SCENARIO_H */
