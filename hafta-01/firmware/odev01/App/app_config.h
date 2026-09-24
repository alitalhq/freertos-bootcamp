#ifndef APP_CONFIG_H
#define APP_CONFIG_H

/* ---- Senaryo seçimi (ADR-003, spec §7) --------------------------------
   Her senaryo ayrı derlenip yüklenir. 0..5 -> S0..S5 */
#ifndef SCENARIO
#define SCENARIO               1
#endif

/* ---- Görev öncelikleri (ödev standardı, spec §3.1) -------------------- */
#define PRIO_TELEMETRY         3
#define PRIO_BUTTON            2
#define PRIO_UART_TX           1

/* ---- Stack boyutları (word = 4 bayt) ---------------------------------- */
#define STACK_TELEMETRY        256
#define STACK_BUTTON           256
#define STACK_UART_TX          256

/* ---- Kuyruklar (ödev standardı, spec §3.3) ---------------------------- */
#define BUTTON_QUEUE_LEN       8
#define TX_QUEUE_LEN           16

/* ---- Mesaj formatı (ödev standardı, spec §3.4) ------------------------ */
#define MSG_LEN                64      /* 63 bayt metin + LF */

/* ---- UART gönderim gözetimi (spec §4) --------------------------------- */
#define UART_TX_TIMEOUT_MS     1000    /* deney timeout'u; 20 ms deadline ile karıştırma */

#endif /* APP_CONFIG_H */
