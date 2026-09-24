#include "records.h"
#include "app_config.h"
#include "stats.h"

static EventRecord s_pool[REC_POOL_SIZE];

bool records_open(uint32_t id, uint32_t t0)
{
    if (id >= REC_POOL_SIZE)
    {
        g_stats.rec_overflow++;
        return false;
    }
    s_pool[id].t[T0] = t0;
    s_pool[id].valid[T0] = 1;
    s_pool[id].status = ST_PENDING;
    return true;
}

void records_stamp(uint32_t id, Stamp s, uint32_t t)
{
    if (id < REC_POOL_SIZE)
    {
        s_pool[id].t[s] = t;     /* önce değer, sonra geçerli bayrağı */
        s_pool[id].valid[s] = 1;
    }
}

void records_set_status(uint32_t id, RecStatus st)
{
    if (id < REC_POOL_SIZE)
    {
        s_pool[id].status = (uint8_t)st;
    }
}

const EventRecord *records_get(uint32_t id)
{
    return (id < REC_POOL_SIZE) ? &s_pool[id] : 0;
}

const char *records_status_name(uint8_t st)
{
    switch (st)
    {
    case ST_OK:       return "ok";
    case ST_BTN_DROP: return "btn_drop";
    case ST_TX_DROP:  return "tx_drop";
    case ST_TX_ERROR: return "tx_error";
    case ST_TIMEOUT:  return "timeout";
    default:          return "pending";
    }
}
