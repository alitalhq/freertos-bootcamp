#include <string.h>
#include "msg.h"

#define MSG_TEXT_MAX (MSG_LEN - 1)   /* son bayt LF'e ayrılmış */

void msg_begin(MsgBuilder *b, TxMsg *m, MsgType type, uint32_t event_id)
{
    m->type = (uint8_t)type;
    m->event_id = event_id;
    b->m = m;
    b->len = 0;
    b->overflow = false;
}

static void put_char(MsgBuilder *b, char c)
{
    if (b->len < MSG_TEXT_MAX)
    {
        b->m->data[b->len++] = c;
    }
    else
    {
        b->overflow = true;   /* sessizce kesme yok: finish false döner */
    }
}

void msg_put_str(MsgBuilder *b, const char *s)
{
    while (*s != '\0')
    {
        put_char(b, *s++);
    }
}

void msg_put_u32(MsgBuilder *b, uint32_t v)
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

bool msg_finish(MsgBuilder *b)
{
    memset(&b->m->data[b->len], ' ', MSG_TEXT_MAX - b->len);
    b->m->data[MSG_LEN - 1] = '\n';
    return !b->overflow;
}
