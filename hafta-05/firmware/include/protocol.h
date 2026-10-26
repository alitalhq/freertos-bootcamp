#pragma once
#include <stdint.h>
#include <stddef.h>
/* Strict parsing: malformed input must never become a valid command. */
int parse_u32(const char *text, uint32_t limit, uint32_t *value);
int parse_hex(const char *text, uint8_t *out, size_t capacity, size_t *length);
void format_hex(const uint8_t *data, size_t length, char *out);
