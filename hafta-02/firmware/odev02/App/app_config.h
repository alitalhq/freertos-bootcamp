#ifndef APP_CONFIG_H
#define APP_CONFIG_H

/* ---- Varsayılan deney (Hafta 2) ---------------------------------------
   Tek derleme: sürüm (A/B/C) ve senaryo (S0..S6) çalışma anında PC'nin
   gönderdiği RUN komutuyla seçilir (lab.h). Kayıtlı ayar yoksa bunlar
   kullanılır. SCENARIO: 0..6 -> S0..S6 */
#ifndef SCENARIO
#define SCENARIO               5
#endif
#ifndef VARIANT
#define VARIANT                'A'
#endif

/* ---- Görev öncelikleri (Ödev 2) ----------------------------------------
   A: TEL 3 > BTN 2 > TX 1, ortak FIFO
   B: BTN 4 > TEL 3 > TX 1, ortak FIFO
   C: B'nin öncelikleri, aktarım sınırında BTN önce */
#define PRIO_TELEMETRY         3
#define PRIO_BUTTON_A          2
#define PRIO_BUTTON_BC         4
#define PRIO_UART_TX           1     /* RUN txprio=N ile değiştirilebilir (iyileştirme deneyi) */

/* ---- Stack boyutları (word = 4 bayt) ---------------------------------- */
#define STACK_TELEMETRY        256
#define STACK_BUTTON           256
#define STACK_UART_TX          256

/* ---- Kuyruklar ---------------------------------------------------------
   Her sürümde en fazla TX_PENDING_MAX mesaj gönderilmeyi bekleyebilir.
   C'de bu sınır iki fiziksel kuyruğun (tx_q + urgent_q) toplamıdır. */
#define BUTTON_QUEUE_LEN       8
#define TX_PENDING_MAX         16
#define TX_QUEUE_LEN           TX_PENDING_MAX
#define URGENT_QUEUE_LEN       TX_PENDING_MAX

/* ---- Mesaj formatı (ödev standardı, spec §3.4) ------------------------ */
#define MSG_LEN                64      /* 63 bayt metin + LF */

/* ---- UART gönderim gözetimi (spec §4) --------------------------------- */
#define UART_TX_TIMEOUT_MS     1000    /* deney timeout'u; 20 ms deadline ile karıştırma */

/* ---- Buton ve deney akışı (spec §5, §8, ADR-003) ---------------------- */
#define DEBOUNCE_US            30000U  /* son kabul edilen kenardan sonra 30 ms */
#define WARMUP_MS              5000U   /* ısınma: basışlar yok sayılır, LD2 sönük */
#ifndef TARGET_EVENTS
#define TARGET_EVENTS          35U     /* bu kadar kabul edilen basıştan sonra export */
#endif
#define REC_POOL_SIZE          128U    /* ödev en az 64 istiyor */
#define DEADLINE_US            20000U  /* R = t4 - t0 <= 20 ms (yalnızca raporlama) */

/* Yalnızca geliştirme testi: tanımlanırsa deney buton beklemeden bu kadar
   ms sonra biter ve export yapılır (telemetri/yük doğrulaması için).
   Ölçüm derlemelerinde TANIMLI OLMAMALI. */
/* #define TEST_AUTO_STOP_MS   10000U */

/* ---- Otomatik basış (RUN inject=1) --------------------------------------
   EXTI13 yazılımla tetiklenir; gerçek basışla aynı ISR ve t0 noktası. */
#define PRIO_INJECT            5       /* otomatik basış üreteci, her şeyin üstünde */
#define STACK_INJECT           256     /* SystemView kaydı açıkken 128 taştı */

#endif /* APP_CONFIG_H */
