#include <string.h>
#include "msg.h"

#define MSG_TEXT_MAX (MSG_LEN - 1)   /* son bayt LF'e ayrılmış */

void tb_init(TextBuilder *b, char *buf, uint32_t cap)
{
    b->buf = buf;
    b->cap = cap;
    b->len = 0;
    b->overflow = false;
}

static void put_char(TextBuilder *b, char c)
{
    if (b->len < b->cap)
    {
        b->buf[b->len++] = c;
    }
    else
    {
        b->overflow = true;   /* sessizce kesme yok: çağıran kontrol eder */
    }
}

void tb_put_str(TextBuilder *b, const char *s)
{
    while (*s != '\0')
    {
        put_char(b, *s++);
    }
}

void tb_put_u32(TextBuilder *b, uint32_t v)
{
    char tmp[10];              /* 2^32-1 en fazla 10 hane */
    int n = 0;
    do
    {
        tmp[n++] = (char)('0' + (v % 10U));
        v /= 10U;
    } while (v != 0U);
    while (n > 0)
    {
        put_char(b, tmp[--n]);
    }
}

void msg_begin(TextBuilder *b, TxMsg *m, MsgType type, uint32_t event_id)
{
    m->type = (uint8_t)type;
    m->event_id = event_id;
    tb_init(b, m->data, MSG_TEXT_MAX);
}

bool msg_finish(TextBuilder *b)
{
    memset(&b->buf[b->len], ' ', MSG_TEXT_MAX - b->len);
    b->buf[MSG_LEN - 1] = '\n';
    return !b->overflow;
}
