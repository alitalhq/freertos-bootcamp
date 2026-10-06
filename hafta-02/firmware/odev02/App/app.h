#ifndef APP_H
#define APP_H

/* main.c -> USER CODE 2: scheduler başlamadan önceki donanım hazırlığı. */
void app_init(void);

/* freertos.c -> USER CODE RTOS_THREADS: uygulama görevlerini oluşturur. */
void app_create_tasks(void);

#endif /* APP_H */
