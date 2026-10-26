#pragma once
#include "stm32l4xx_hal.h"
extern UART_HandleTypeDef huart2;
void board_init(void);
uint32_t timer_us(void);
void work_iterations(uint32_t iterations);
uint32_t calibrate_work(void);
void fatal(const char *file, int line);
void app_init(void);
void app_button_isr(uint32_t now);
void app_uart_tx_isr(void);
