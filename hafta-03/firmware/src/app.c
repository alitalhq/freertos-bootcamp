/* Week 3 producer/consumer experiment. Trace is exported only AFTER capture. */
#include "board.h"
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "app_trace.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define N_MESSAGES 44U
#define SERVICE_MS 20U
typedef struct { uint32_t sequence, generated_us, value; } Message;
typedef struct { uint32_t generated, send_us, latency_us, received, ok; } Sample;
static Sample samples[N_MESSAGES];
static QueueHandle_t q4,q16,message_q,rx_q;
static uint8_t rx_byte;
static volatile uint32_t rx_errors,rx_drops,rx_rearm;
static TaskHandle_t producer_handle,consumer_handle;
static volatile uint32_t producer_done=1,consumer_done=1,active;
static uint32_t run_id,trace_run_id,attempted,accepted,failed,consumed;
static char variant='A';
static unsigned burst,enable_trace=1;
static TickType_t send_wait;
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart) {
    if(uart!=&huart2)return;
    BaseType_t woken=pdFALSE;
    if(xQueueSendFromISR(rx_q,&rx_byte,&woken)!=pdPASS)rx_drops++;
    if(HAL_UART_Receive_IT(&huart2,&rx_byte,1)!=HAL_OK)rx_rearm=1;
    /* board.c records the single ISR exit, including a pending switch. */
    if(woken)portYIELD();
}
void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart) {
    if(uart==&huart2){rx_errors++;rx_rearm=1;}
}
static void output(const char *fmt,...) {
    char line[240];va_list ap;va_start(ap,fmt);
    int len=vsnprintf(line,sizeof line,fmt,ap);va_end(ap);
    if(len>0 && len<(int)sizeof line && HAL_UART_Transmit(&huart2,(uint8_t*)line,(uint16_t)len,2000)!=HAL_OK)
        fatal(__FILE__,__LINE__);
}
static uint32_t checksum(const uint8_t *data,uint32_t size) {
    uint32_t hash=2166136261U;
    for(uint32_t i=0;i<size;i++){hash^=data[i];hash*=16777619U;}
    return hash;
}
static void Producer(void *arg) {
    (void)arg;
    for(;;) {
        ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
        for(unsigned i=0;i<N_MESSAGES;i++) {
            /* Normal: 44 messages / 100 ms gaps. Burst: 10 normal, 24
               consecutive send attempts, 10 normal. Blocking stretches burst. */
            if(enable_trace && i==(burst?10U:0U)) {
                AppTrace_Start(200);
                AppTrace_Event(TR_RUN,run_id,0,((uint32_t)variant<<16)|(burst<<8)|(uint32_t)send_wait);
            }
            Message m={i+1,timer_us(),1000U+i};samples[i].generated=m.generated_us;attempted++;
            uint32_t begin=timer_us();AppTrace_Event(TR_SEND_BEGIN,run_id,m.sequence,send_wait);
            BaseType_t result=xQueueSend(message_q,&m,send_wait);
            uint32_t elapsed=timer_us()-begin;samples[i].send_us=elapsed;samples[i].ok=(result==pdPASS);
            if(result==pdPASS)accepted++;else failed++;
            AppTrace_Event(result==pdPASS?TR_SEND_OK:TR_SEND_FAIL,run_id,m.sequence,elapsed);
            if(!(burst && i>=10U && i<33U))vTaskDelay(pdMS_TO_TICKS(100));
        }
        producer_done=1;
    }
}
static void Consumer(void *arg) {
    (void)arg;Message m;
    for(;;) {
        ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
        for(;;) {
            if(xQueueReceive(message_q,&m,pdMS_TO_TICKS(25))==pdPASS) {
                unsigned i=m.sequence-1U;configASSERT(i<N_MESSAGES);
                samples[i].latency_us=timer_us()-m.generated_us;samples[i].received=1;
                AppTrace_Event(TR_RECEIVE,run_id,m.sequence,samples[i].latency_us);
                /* Peripheral/service wait model. This is NOT 20 ms CPU work. */
                vTaskDelay(pdMS_TO_TICKS(SERVICE_MS));consumed++;
                AppTrace_Event(TR_DONE,run_id,m.sequence,0);
            }
            if(producer_done && uxQueueMessagesWaiting(message_q)==0)break;
        }
        consumer_done=1;
    }
}
static void report(void) {
    output("#RESULT,%lu,%c,%s,%lu,%lu,%lu,%lu,%lu,%lu,%lu\n",(unsigned long)run_id,variant,
        burst?"BURST":"NORMAL",(unsigned long)attempted,(unsigned long)accepted,
        (unsigned long)failed,(unsigned long)consumed,(unsigned long)enable_trace,
        (unsigned long)app_trace_bytes,(unsigned long)app_trace_dropped);
    output("#COLUMNS,id,ok,received,generated_us,send_us,latency_us\n");
    for(unsigned i=0;i<N_MESSAGES;i++)output("#ROW,%u,%lu,%lu,%lu,%lu,%lu\n",i+1,
        (unsigned long)samples[i].ok,(unsigned long)samples[i].received,
        (unsigned long)samples[i].generated,(unsigned long)samples[i].send_us,(unsigned long)samples[i].latency_us);
    output("#STACK,%lu,%lu,%lu\n",(unsigned long)uxTaskGetStackHighWaterMark(producer_handle),
        (unsigned long)uxTaskGetStackHighWaterMark(consumer_handle),(unsigned long)uxTaskGetStackHighWaterMark(NULL));
    output("#RX,%lu,%lu\n",(unsigned long)rx_errors,(unsigned long)rx_drops);
    output("#END,%lu\n",(unsigned long)run_id);
}
static void export_trace(void) {
    if(!app_trace_complete||!app_trace_bytes){output("#ERROR,NO_TRACE\n");return;}
    const uint8_t *data=AppTrace_Data();uint32_t size=app_trace_bytes;
    output("#TRACE,%lu,%lu,%08lX,%lu,%lu\n",(unsigned long)trace_run_id,(unsigned long)size,
        (unsigned long)checksum(data,size),(unsigned long)app_trace_dropped,(unsigned long)app_trace_reason);
    const char *hex="0123456789ABCDEF";
    for(uint32_t off=0;off<size;off+=64U){
        char line[129];uint32_t n=size-off;if(n>64U)n=64U;
        for(uint32_t i=0;i<n;i++){line[2*i]=hex[data[off+i]>>4];line[2*i+1]=hex[data[off+i]&15];}
        line[2*n]=0;output("#HEX,%lu,%s\n",(unsigned long)off,line);
    }
    output("#TRACE_END,%lu\n",(unsigned long)trace_run_id);
}
static void command(const char *line) {
    if(!strcmp(line,"HELLO")){output("#HELLO,WEEK3,1,STM32L476RG,230400,80000000\n");return;}
    if(!strcmp(line,"TRACE")){export_trace();return;}
    if(!strcmp(line,"TRACE ON")){enable_trace=1;output("#ACK,TRACE_ON\n");return;}
    if(!strcmp(line,"TRACE OFF")){enable_trace=0;output("#ACK,TRACE_OFF\n");return;}
    char v=0,load[12]={0},extra=0;
    if(sscanf(line,"RUN %c %11s %c",&v,load,&extra)==2&&(v=='A'||v=='B'||v=='C')&&
       (!strcmp(load,"NORMAL")||!strcmp(load,"BURST"))){
        variant=v;burst=!strcmp(load,"BURST");message_q=(v=='B')?q16:q4;send_wait=(v=='C')?pdMS_TO_TICKS(20):0;
        configASSERT(xQueueReset(message_q)==pdPASS);AppTrace_NameQueue(message_q);
        memset(samples,0,sizeof samples);attempted=accepted=failed=consumed=0;
        app_trace_bytes=app_trace_complete=app_trace_dropped=app_trace_reason=0;
        run_id++;trace_run_id=run_id;output("#RUN,%lu,%c,%s\n",(unsigned long)run_id,v,load);
        producer_done=consumer_done=0;active=1;HAL_GPIO_WritePin(GPIOA,GPIO_PIN_5,GPIO_PIN_SET);
        xTaskNotifyGive(consumer_handle);xTaskNotifyGive(producer_handle);return;
    }
    output("#ERROR,BAD_COMMAND\n");
}
static void Console(void *arg) {
    (void)arg;char line[64];unsigned n=0,overflow=0;
    configASSERT(HAL_UART_Receive_IT(&huart2,&rx_byte,1)==HAL_OK);
    output("#HELLO,WEEK3,1,STM32L476RG,230400,80000000\n");
    for(;;){
        if(active&&producer_done&&consumer_done){
            taskENTER_CRITICAL();if(enable_trace&&!app_trace_complete)AppTrace_Stop();taskEXIT_CRITICAL();
            HAL_GPIO_WritePin(GPIOA,GPIO_PIN_5,GPIO_PIN_RESET);active=0;report();
        }
        uint8_t ch;
        if(rx_rearm && HAL_UART_Receive_IT(&huart2,&rx_byte,1)==HAL_OK)rx_rearm=0;
        while(xQueueReceive(rx_q,&ch,0)==pdPASS){
            if(ch=='\r')continue;
            if(ch=='\n'){
                line[n]=0;
                /* No serial output during measured run. UI prevents commands. */
                if(!active){if(overflow)output("#ERROR,LINE_TOO_LONG\n");else if(n)command(line);}
                n=overflow=0;
            }else if(n<sizeof line-1U)line[n++]=(char)ch;
            else overflow=1;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
void app_button_isr(uint32_t now){(void)now;/* Deterministic software load, not B1. */}
void app_init(void){
    q4=xQueueCreate(4,sizeof(Message));q16=xQueueCreate(16,sizeof(Message));rx_q=xQueueCreate(128,1);configASSERT(q4&&q16&&rx_q);
    vQueueAddToRegistry(q4,"Queue4");vQueueAddToRegistry(q16,"Queue16");
    configASSERT(xTaskCreate(Producer,"Producer",768,NULL,2,&producer_handle)==pdPASS);
    configASSERT(xTaskCreate(Consumer,"Consumer",768,NULL,1,&consumer_handle)==pdPASS);
    configASSERT(xTaskCreate(Console,"Console",1024,NULL,3,NULL)==pdPASS);
}
