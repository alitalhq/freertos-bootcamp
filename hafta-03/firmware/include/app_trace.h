#pragma once
#include <stdint.h>
enum { TR_RUN, TR_SEND_BEGIN, TR_SEND_OK, TR_SEND_FAIL, TR_RECEIVE, TR_DONE, TR_COUNT };
void AppTrace_Init(void);
void AppTrace_Start(uint32_t duration_ms);
void AppTrace_Stop(void);
void AppTrace_Tick(void);
void AppTrace_Event(unsigned event, uint32_t run, uint32_t id, uint32_t detail);
void AppTrace_NameQueue(void *queue);
const uint8_t *AppTrace_Data(void);
extern volatile uint32_t app_trace_bytes, app_trace_dropped, app_trace_complete, app_trace_reason;
