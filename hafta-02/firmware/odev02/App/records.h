#ifndef RECORDS_H
#define RECORDS_H

#include <stdbool.h>
#include <stdint.h>

/* Ölçüm noktaları (spec §6.1) */
typedef enum { T0 = 0, T1, T2, T3, T4, T_COUNT } Stamp;

typedef enum {
    ST_PENDING = 0,
    ST_OK,
    ST_BTN_DROP,    /* buttonQ dolu: ISR kuyruğa koyamadı */
    ST_TX_DROP,     /* txQ dolu: ButtonTask yanıtı kuyruğa koyamadı */
    ST_TX_ERROR,    /* UART başlatma ya da aktarım hatası */
    ST_TIMEOUT,     /* 1 s içinde TC gelmedi */
} RecStatus;

/* Tek bir buton olayının kaydı. Sahiplik (R-REC-2): her zaman damgasını
   tek bir bağlam yazar ve her damganın kendi "geçerli" baytı var; böylece
   oku-değiştir-yaz yok, kritik bölge gerekmiyor. status ise olay zinciri
   boyunca sırayla el değiştirir (ISR -> ButtonTask -> UartTxTask -> TC). */
typedef struct {
    uint32_t         t[T_COUNT];
    volatile uint8_t valid[T_COUNT];   /* 0 değeri "ölçülmedi" demek değil */
    volatile uint8_t status;           /* RecStatus */
} EventRecord;

/* ISR: yeni olay kaydı açar. Havuz dolduysa false (rec_overflow sayılır). */
bool records_open(uint32_t id, uint32_t t0);

/* Görev ya da ISR: damga yaz / durum ata. Havuz dışı id sessizce yok sayılır
   (açılışta zaten rec_overflow olarak sayıldı). */
void records_stamp(uint32_t id, Stamp s, uint32_t t);
void records_set_status(uint32_t id, RecStatus st);

/* Export için (deney bittikten sonra) */
const EventRecord *records_get(uint32_t id);
const char *records_status_name(uint8_t st);

#endif /* RECORDS_H */
