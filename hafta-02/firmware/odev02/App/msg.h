#ifndef MSG_H
#define MSG_H

#include <stdbool.h>
#include <stdint.h>
#include "app_config.h"

typedef enum {
    MSG_TEL = 0,
    MSG_BTN = 1,
    MSG_CTRL_EXPORT = 2,   /* veri değil: UartTxTask'a "export et" işareti */
} MsgType;

/* txQ elemanı: kuyruğa DEĞER olarak kopyalanır (R-Q-2). data NUL ile
   bitmez; her zaman tam MSG_LEN bayt gönderilir. */
typedef struct {
    uint8_t  type;          /* MsgType */
    uint32_t event_id;      /* BTN için olay kimliği, TEL için sıra no */
    char     data[MSG_LEN];
} TxMsg;

/* Metni parça parça kuran yardımcılar. printf yerine bunları kullanıyoruz:
   süreleri kısa ve sabit, yeniden girişli (reentrant) ve heap kullanmıyor. */
typedef struct {
    char    *buf;
    uint32_t cap;      /* yazılabilecek en fazla karakter */
    uint32_t len;
    bool     overflow;
} TextBuilder;

void tb_init(TextBuilder *b, char *buf, uint32_t cap);
void tb_put_str(TextBuilder *b, const char *s);
void tb_put_u32(TextBuilder *b, uint32_t v);

/* 64 baytlık TEL/BTN mesajı için: metin en fazla 63 bayt. */
void msg_begin(TextBuilder *b, TxMsg *m, MsgType type, uint32_t event_id);

/* Metni boşlukla 63 bayta tamamlar, 64. bayta LF koyar (R-MSG-1).
   Metin sığmadıysa false döner (R-MSG-2); çağıran sayacı artırır. */
bool msg_finish(TextBuilder *b);

#endif /* MSG_H */
