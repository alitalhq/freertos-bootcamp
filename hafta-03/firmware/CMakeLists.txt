cmake_minimum_required(VERSION 3.20)
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_ASM_COMPILER arm-none-eabi-gcc)
project(rtos_week3 C ASM)
set(CMAKE_C_STANDARD 11)
set(V ${CMAKE_CURRENT_SOURCE_DIR}/vendor)
if(NOT EXISTS ${V}/freertos/tasks.c)
  message(FATAL_ERROR "Run python ../tools/fetch_dependencies.py first")
endif()
set(CPU -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard)
add_executable(bootcamp
  src/main.c src/board.c src/app.c src/syscalls.c src/app_trace.c
  ${V}/systemview/SYSVIEW/SEGGER_SYSVIEW.c
  ${V}/systemview/Sample/FreeRTOSV11/SEGGER_SYSVIEW_FreeRTOS.c
  ${V}/rtt/RTT/SEGGER_RTT.c
  ${V}/device/Source/Templates/system_stm32l4xx.c
  ${V}/device/Source/Templates/gcc/startup_stm32l476xx.s
  ${V}/hal/Src/stm32l4xx_hal.c
  ${V}/hal/Src/stm32l4xx_hal_cortex.c
  ${V}/hal/Src/stm32l4xx_hal_rcc.c ${V}/hal/Src/stm32l4xx_hal_rcc_ex.c
  ${V}/hal/Src/stm32l4xx_hal_gpio.c
  ${V}/hal/Src/stm32l4xx_hal_pwr.c ${V}/hal/Src/stm32l4xx_hal_pwr_ex.c
  ${V}/hal/Src/stm32l4xx_hal_flash.c ${V}/hal/Src/stm32l4xx_hal_flash_ex.c
  ${V}/hal/Src/stm32l4xx_hal_uart.c ${V}/hal/Src/stm32l4xx_hal_uart_ex.c
  ${V}/hal/Src/stm32l4xx_hal_dma.c
  ${V}/freertos/tasks.c ${V}/freertos/queue.c ${V}/freertos/list.c
  ${V}/freertos/portable/GCC/ARM_CM4F/port.c
  ${V}/freertos/portable/MemMang/heap_4.c)
target_include_directories(bootcamp PRIVATE include ${V}/hal/Inc ${V}/device/Include
  ${V}/cmsis/CMSIS/Core/Include ${V}/freertos/include ${V}/freertos/portable/GCC/ARM_CM4F)
target_include_directories(bootcamp PRIVATE ${V}/systemview/SYSVIEW ${V}/systemview/SEGGER ${V}/systemview/Sample/FreeRTOSV11 ${V}/rtt/RTT)
target_compile_definitions(bootcamp PRIVATE STM32L476xx USE_HAL_DRIVER)
target_compile_options(bootcamp PRIVATE ${CPU} -Og -g3 -ffunction-sections -fdata-sections -Wall -Wextra)
target_link_options(bootcamp PRIVATE ${CPU} -T${CMAKE_CURRENT_SOURCE_DIR}/STM32L476RG.ld
  --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections -Wl,-Map=bootcamp.map -Wl,--print-memory-usage)
set_target_properties(bootcamp PROPERTIES SUFFIX .elf)
add_custom_command(TARGET bootcamp POST_BUILD
  COMMAND arm-none-eabi-objcopy -O ihex bootcamp.elf bootcamp.hex
  COMMAND arm-none-eabi-objcopy -O binary bootcamp.elf bootcamp.bin
  COMMAND arm-none-eabi-size bootcamp.elf)
