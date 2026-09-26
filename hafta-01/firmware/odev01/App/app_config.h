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

/* ==== Lab modu (standart dışı, ADR-004) ==================================
   0: Resmi ödev derlemesi. S0–S5 bu ayarla ölçüldü; aşağıdaki hiçbir çözüm
      ve UART komut kanalı derlenmez.
   1: Lab derlemesi. Kart bir kez yüklenir; PC arayüzü UART'tan RUN komutuyla
      periyot, CPU işi, çözüm maskesi ve basış kaynağını (elle/otomatik) seçer. */
#ifndef APP_LAB_MODE
#define APP_LAB_MODE           0
#endif

#if APP_LAB_MODE
/* S5'teki birikimli gecikmeye karşı çözüm denemeleri. Her biri kendi
   #ifdef bloğunda; çalışma anında RunConfig.fix_mask ile seçilir. */
#define ENABLE_FIX_UART_PRIO          /* F1: UartTxTask önceliği 4 (kök neden) */
#define ENABLE_FIX_BTN_PRIO           /* F4: ButtonTask önceliği 4 (tek başına naif; F1 ile optimal) */
#endif

/* fix_mask bitleri. Arayüzdeki 4 seçenek: 0 standart, 4 naif, 1 kök neden,
   5 optimal (1|4). 0x2 ve 0x8 önceki deneylerde kullanıldı, artık yok. */
#define FIX_UART_PRIO          0x1U
#define FIX_BTN_PRIO           0x4U

#define PRIO_RAISED            4       /* çözümlerde kullanılan yükseltilmiş öncelik */
#define PRIO_INJECT            5       /* otomatik basış üreteci (lab), her şeyin üstünde */
#define STACK_INJECT           128

#endif /* APP_CONFIG_H */
