#include "protocol.h"
#include <string.h>
int parse_u32(const char *text, uint32_t limit, uint32_t *value) {
    uint32_t n = 0;
    if (!text || !*text) return 0;
    for (; *text; ++text) {
        if (*text < '0' || *text > '9') return 0;
        uint32_t digit = (uint32_t)(*text - '0');
        if (digit > limit || n > (limit - digit) / 10U) return 0;
        n = n * 10U + digit;
    }
    *value = n;
    return 1;
}
static int nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
int parse_hex(const char *text, uint8_t *out, size_t capacity, size_t *length) {
    if (!text) return 0;
    size_t n = strlen(text);
    if (!n || (n & 1U) || n / 2U > capacity) return 0;
    /* Validate the whole input before touching the output. */
    for (size_t i = 0; i < n; ++i) if (nibble(text[i]) < 0) return 0;
    for (size_t i = 0; i < n / 2U; ++i)
        out[i] = (uint8_t)((nibble(text[2*i]) << 4) | nibble(text[2*i+1]));
    *length = n / 2U;
    return 1;
}
void format_hex(const uint8_t *data, size_t length, char *out) {
    const char digits[] = "0123456789ABCDEF";
    for (size_t i = 0; i < length; ++i) {
        out[2*i] = digits[data[i] >> 4];
        out[2*i+1] = digits[data[i] & 15];
    }
    out[2*length] = 0;
}
