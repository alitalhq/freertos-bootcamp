#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "app_trace.h"
UART_HandleTypeDef huart2;
volatile const char *fault_file;
volatile int fault_line;
volatile uint32_t work_sink;

void fatal(const char *file, int line) {
    __disable_irq();
    fault_file = file; fault_line = line;
    GPIOA->BSRR = GPIO_PIN_5;
    for (;;) __NOP(); /* Inspect fault_file/fault_line in debugger. */
}
void vApplicationMallocFailedHook(void) { fatal(__FILE__, __LINE__); }
void vApplicationStackOverflowHook(TaskHandle_t task, char *name) {
    (void)task; (void)name; fatal(__FILE__, __LINE__);
}
void HardFault_Handler(void) { fatal(__FILE__, __LINE__); }
void MemManage_Handler(void) { fatal(__FILE__, __LINE__); }
void BusFault_Handler(void) { fatal(__FILE__, __LINE__); }
void UsageFault_Handler(void) { fatal(__FILE__, __LINE__); }
void SysTick_Handler(void) {
    HAL_IncTick();
    if (xTaskGetSchedulerState() != taskSCHEDULER_NOT_STARTED) {
        extern void xPortSysTickHandler(void);
        xPortSysTickHandler();
        AppTrace_Tick();
    }
}
void USART2_IRQHandler(void) {
    traceISR_ENTER(); HAL_UART_IRQHandler(&huart2);
    if(SCB->ICSR & SCB_ICSR_PENDSVSET_Msk) traceISR_EXIT_TO_SCHEDULER();
    else traceISR_EXIT();
}
void EXTI15_10_IRQHandler(void) {
    traceISR_ENTER();
    const uint32_t now = timer_us(); /* ISR entry reference, not physical edge. */
    if (__HAL_GPIO_EXTI_GET_IT(GPIO_PIN_13)) {
        __HAL_GPIO_EXTI_CLEAR_IT(GPIO_PIN_13);
        app_button_isr(now);
    }
    traceISR_EXIT();
}
uint32_t timer_us(void) { return TIM2->CNT; }

void board_init(void) {
    HAL_Init();
    HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);
    __HAL_RCC_PWR_CLK_ENABLE();
    if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) fatal(__FILE__, __LINE__);
    RCC_OscInitTypeDef osc = {0};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSI;
    osc.PLL.PLLM = 1; osc.PLL.PLLN = 10;
    osc.PLL.PLLP = RCC_PLLP_DIV7;
    osc.PLL.PLLQ = RCC_PLLQ_DIV2; osc.PLL.PLLR = RCC_PLLR_DIV2;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) fatal(__FILE__, __LINE__);
    RCC_ClkInitTypeDef clk = {0};
    clk.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV1; clk.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_4) != HAL_OK) fatal(__FILE__, __LINE__);
    SystemCoreClockUpdate();
    __HAL_RCC_GPIOA_CLK_ENABLE(); __HAL_RCC_GPIOC_CLK_ENABLE(); __HAL_RCC_SYSCFG_CLK_ENABLE();
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_5; gpio.Mode = GPIO_MODE_OUTPUT_PP; gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &gpio);
    gpio.Pin = GPIO_PIN_2 | GPIO_PIN_3; gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_PULLUP; gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH; gpio.Alternate = GPIO_AF7_USART2;
    HAL_GPIO_Init(GPIOA, &gpio);
    __HAL_RCC_USART2_CLK_ENABLE();
    huart2.Instance = USART2;
    huart2.Init.BaudRate = 230400;
    huart2.Init.WordLength = UART_WORDLENGTH_8B;
    huart2.Init.StopBits = UART_STOPBITS_1; huart2.Init.Parity = UART_PARITY_NONE;
    huart2.Init.Mode = UART_MODE_TX_RX; huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart2.Init.OverSampling = UART_OVERSAMPLING_16;
    huart2.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    huart2.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_UART_Init(&huart2) != HAL_OK) fatal(__FILE__, __LINE__);
    HAL_NVIC_SetPriority(USART2_IRQn, 6, 0); HAL_NVIC_EnableIRQ(USART2_IRQn);
    __HAL_RCC_TIM2_CLK_ENABLE();
    TIM2->PSC = (SystemCoreClock / 1000000U) - 1U;
    TIM2->ARR = 0xFFFFFFFFU; TIM2->EGR = TIM_EGR_UG; TIM2->CR1 = TIM_CR1_CEN;
    gpio.Pin = GPIO_PIN_13; gpio.Mode = GPIO_MODE_IT_FALLING; gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOC, &gpio);
    HAL_NVIC_SetPriority(EXTI15_10_IRQn, 6, 0); /* Enabled only after RTOS queues exist. */
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0; DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

__attribute__((noinline)) void work_iterations(uint32_t n) {
    uint32_t x = work_sink | 1U;
    for (uint32_t i = 0; i < n; ++i) { x ^= x << 13; x ^= x >> 17; x ^= x << 5; }
    work_sink = x;
}
uint32_t calibrate_work(void) {
    /* Before scheduler; SysTick can add a small calibration error. Best of five. */
    uint32_t best = UINT32_MAX;
    for (int i = 0; i < 5; ++i) {
        uint32_t start = DWT->CYCCNT;
        work_iterations(10000);
        uint32_t elapsed = DWT->CYCCNT - start;
        if (elapsed < best) best = elapsed;
    }
    configASSERT(best != 0);
    return (uint32_t)(((uint64_t)10000 * (SystemCoreClock / 1000U)) / best);
}
