/* RAM single-shot capture. USART2 only exports AFTER capture has stopped. */
#include "FreeRTOS.h"
#include "task.h"
#include "board.h"
#include "app_trace.h"
#include "SEGGER_SYSVIEW.h"
#include "SEGGER_RTT.h"
extern const SEGGER_SYSVIEW_OS_API SYSVIEW_X_OS_TraceAPI;
static void descriptions(void);
static SEGGER_SYSVIEW_MODULE module = {"M=Week3_Queue,T=W3", TR_COUNT, 0, descriptions, 0};
static void *named_queue;
static volatile uint32_t ticks_left;
volatile uint32_t app_trace_bytes, app_trace_dropped, app_trace_complete, app_trace_reason;
static const char *const labels[] = {
    "0 RUN run=%u id=%u detail=%u", "1 SEND_BEGIN run=%u id=%u wait_ticks=%u",
    "2 SEND_OK run=%u id=%u send_us=%u", "3 SEND_FAIL run=%u id=%u send_us=%u",
    "4 RECEIVE run=%u id=%u latency_us=%u", "5 DONE run=%u id=%u detail=%u"
};
static void descriptions(void) {
    for (unsigned i=0;i<TR_COUNT;i++) SEGGER_SYSVIEW_RecordModuleDescription(&module, labels[i]);
}
static void system_description(void) {
    SEGGER_SYSVIEW_SendSysDesc("N=Bootcamp Week3 Queue Lab (FreeRTOS 11.1.0),D=STM32L476RG,O=FreeRTOS");
    SEGGER_SYSVIEW_SendSysDesc("I#15=SysTick,I#54=USART2,I#56=EXTI15_10");
    if (named_queue) SEGGER_SYSVIEW_NameResource((U32)named_queue, "MessageQueue");
}
void SEGGER_SYSVIEW_Conf(void) {
    SEGGER_SYSVIEW_Init(SystemCoreClock, SystemCoreClock, &SYSVIEW_X_OS_TraceAPI, system_description);
    SEGGER_SYSVIEW_SetRAMBase(0x20000000U);
}
void AppTrace_Init(void) { SEGGER_SYSVIEW_Conf(); SEGGER_SYSVIEW_RegisterModule(&module); }
void AppTrace_NameQueue(void *queue) { named_queue=queue; }
void AppTrace_Event(unsigned e,uint32_t run,uint32_t id,uint32_t detail) {
    SEGGER_SYSVIEW_RecordU32x3(module.EventOffset+e,run,id,detail);
}
void AppTrace_Start(uint32_t ms) {
    taskENTER_CRITICAL();
    SEGGER_SYSVIEW_Stop();
    _SEGGER_RTT.aUp[1].WrOff=0; _SEGGER_RTT.aUp[1].RdOff=0;
    SEGGER_SYSVIEW_GetMainContext()->DropCount=0;
    app_trace_complete=0; app_trace_bytes=0; app_trace_dropped=0; app_trace_reason=0;
    SEGGER_SYSVIEW_Start();
    system_description(); SEGGER_SYSVIEW_SendTaskList();
    SEGGER_SYSVIEW_SendModule(0); descriptions();
    SEGGER_SYSVIEW_OnTaskStartExec((U32)xTaskGetCurrentTaskHandle());
    ticks_left=pdMS_TO_TICKS(ms);
    taskEXIT_CRITICAL();
}
void AppTrace_Stop(void) {
    SEGGER_SYSVIEW_Stop(); ticks_left=0;
    app_trace_bytes=_SEGGER_RTT.aUp[1].WrOff;
    app_trace_dropped=SEGGER_SYSVIEW_GetMainContext()->DropCount;
    app_trace_complete=1;
}
void AppTrace_Tick(void) {
    /* Called after the port's balanced SysTick trace exits. All tracing IRQs
       have priority >= 5; protect snapshot bookkeeping from priority-6 IRQs. */
    UBaseType_t mask=portSET_INTERRUPT_MASK_FROM_ISR();
    if(ticks_left) {
        if (_SEGGER_RTT.aUp[1].WrOff > SEGGER_SYSVIEW_RTT_BUFFER_SIZE-2048U) {
            app_trace_reason=2; AppTrace_Stop();
        } else if (--ticks_left==0) { app_trace_reason=1; AppTrace_Stop(); }
    }
    portCLEAR_INTERRUPT_MASK_FROM_ISR(mask);
}
const uint8_t *AppTrace_Data(void) { return (const uint8_t *)_SEGGER_RTT.aUp[1].pBuffer; }
