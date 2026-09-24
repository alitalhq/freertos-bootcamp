#ifndef MSG_H
#define MSG_H

#include <stdbool.h>
#include <stdint.h>
#include "app_config.h"

typedef enum {
    MSG_TEL = 0,
    MSG_BTN = 1,
} MsgType;

/* txQ elemanı: kuyruğa DEĞER olarak kopyalanır (R-Q-2). data NUL ile
   bitmez; her zaman tam MSG_LEN bayt gönderilir. */
typedef struct {
    uint8_t  type;          /* MsgType */
    uint32_t event_id;      /* BTN için olay kimliği, TEL için sıra no */
    char     data[MSG_LEN];
} TxMsg;

/* Mesajı parça parça kuran yardımcılar. printf yerine bunları kullanıyoruz:
   süreleri sabit ve kısa, yeniden girişli (reentrant) ve heap kullanmıyor. */
typedef struct {
    TxMsg   *m;
    uint32_t len;
    bool     overflow;
} MsgBuilder;

void msg_begin(MsgBuilder *b, TxMsg *m, MsgType type, uint32_t event_id);
void msg_put_str(MsgBuilder *b, const char *s);
void msg_put_u32(MsgBuilder *b, uint32_t v);

/* Metni boşlukla 63 bayta tamamlar, 64. bayta LF koyar (R-MSG-1).
   Metin sığmadıysa false döner (R-MSG-2); çağıran sayacı artırır. */
bool msg_finish(MsgBuilder *b);

#endif /* MSG_H */
