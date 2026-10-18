/* RTT ayarları: yalnızca SystemView'in yukarı kanalı (1) kullanılır. */
#ifndef SEGGER_RTT_CONF_H
#define SEGGER_RTT_CONF_H

#define RTT_USE_ASM                       0
#define SEGGER_RTT_MAX_NUM_UP_BUFFERS     2
#define SEGGER_RTT_MAX_NUM_DOWN_BUFFERS   2
#define BUFFER_SIZE_UP                    16     /* kanal 0 kullanılmıyor */
#define BUFFER_SIZE_DOWN                  16
#define SEGGER_RTT_MODE_DEFAULT           SEGGER_RTT_MODE_NO_BLOCK_SKIP

/* RTT kilidi BASEPRI ile öncelik 5 ve altını (sayıca >= 5) maskeler. Kayıt yapan
   bütün kesmeler (EXTI15_10, USART2, SysTick) bu aralıkta; FreeRTOS'un
   configMAX_SYSCALL_INTERRUPT_PRIORITY değeriyle (5 << 4 = 0x50) aynı. */
#define SEGGER_RTT_MAX_INTERRUPT_PRIORITY 0x50

#endif /* SEGGER_RTT_CONF_H */
