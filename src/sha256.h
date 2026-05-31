#ifndef GRIT_SHA256_H
#define GRIT_SHA256_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t data[64];
    uint32_t datalen;
    uint64_t bitlen;
    uint32_t state[8];
} bb_sha256_ctx;

void bb_sha256_init(bb_sha256_ctx *ctx);
void bb_sha256_update(bb_sha256_ctx *ctx, const uint8_t *data, size_t len);
void bb_sha256_final(bb_sha256_ctx *ctx, uint8_t hash[32]);
void bb_sha256_hex(const uint8_t hash[32], char out[65]);

#endif

