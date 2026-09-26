#ifndef LAB_H
#define LAB_H

/* Lab modu (APP_LAB_MODE=1, ADR-004): PC'den UART komutuyla deney seçimi ve
   otomatik basış üreteci. Resmi derlemede bu dosyanın hiçbir parçası yok.

   PC -> kart komutları (LF ile biten ASCII satırlar):
     RUN name=S5 period=10 work=5000 target=35 fix=3 inject=1 gmin=500 gmax=1500 seed=7 run=12
         Ayarı SRAM2'ye yazar ve kartı yeniden başlatır: her deney temiz
         durumdan (boş kuyruklar, sıfır sayaçlar, yeni kalibrasyon) başlar.
     STOP     Deneyi hedef sayıya ulaşmadan bitirir ve export başlatır.
     PING     Geçerli ayarı LAB satırıyla bildirir.
     DEFAULT  SRAM2'deki ayarı siler, derleme varsayılanıyla yeniden başlar.

   Kart -> PC: açılışta ve PING'de 64 baytlık "LAB,..." satırı. */

#include "app_config.h"

#if APP_LAB_MODE
#include "scenario.h"

/* run_config_init içinden: SRAM2'de geçerli ayar varsa cfg'yi ezer. */
void lab_load_config(RunConfig *cfg);

/* UartTxTask başında (scheduler çalışırken): RX'i kurar, LAB satırı gönderir. */
void lab_start(void);

/* app_create_tasks içinden: otomatik basış görevini oluşturur (inject=1 ise). */
void lab_create_tasks(void);

/* USART2 hata callback'inden: RX'i yeniden kurar. */
void lab_rx_rearm(void);

/* Export için: otomatik üretilen basış sayısı. */
uint32_t lab_injected_count(void);
#endif

#endif /* LAB_H */
