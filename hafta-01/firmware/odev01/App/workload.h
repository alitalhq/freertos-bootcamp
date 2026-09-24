#ifndef WORKLOAD_H
#define WORKLOAD_H

#include <stdint.h>

/* Kalibrasyon sonucu (export CFG satırında raporlanır, R-WRK-3). */
typedef struct {
    uint32_t calib_iters;   /* ölçülen örnek iş büyüklüğü */
    uint32_t calib_us;      /* bu işin en kısa süresi (5 tekrar) */
    uint32_t work_iters;    /* senaryonun work_us hedefi için iterasyon */
} WorkloadCalib;

/* Scheduler başlamadan önce çağrılır: iterasyon/süre oranını ölçer ve
   senaryonun hedef süresine karşılık gelen iterasyonu hesaplar. */
void workload_calibrate(uint32_t target_us);

const WorkloadCalib *workload_calib(void);

/* Sabit iterasyonlu CPU işi (S4/S5). Kesmeleri kapatmaz, bloklamaz. */
void workload_run(uint32_t iters);

#endif /* WORKLOAD_H */
