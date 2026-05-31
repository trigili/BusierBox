#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sha256.h"
#include "trailer_config.h"

static void trailer_set_error(struct bb_config_trailer *out, const char *s)
{
    snprintf(out->error, sizeof(out->error), "%s", s);
}

static int hexval(int c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

static int hex_to_bytes(const char *hex, unsigned char *out, size_t outsz, size_t *len_out)
{
    size_t i, n;
    if (!hex)
        return -1;
    n = strlen(hex);
    if (!n || (n % 2) || n / 2 > outsz)
        return -1;
    for (i = 0; i < n; i += 2) {
        int hi = hexval((unsigned char)hex[i]);
        int lo = hexval((unsigned char)hex[i + 1]);
        if (hi < 0 || lo < 0)
            return -1;
        out[i / 2] = (unsigned char)((hi << 4) | lo);
    }
    *len_out = n / 2;
    return 0;
}

size_t bb_config_file_trailer_span(const char *path)
{
    FILE *fp;
    long fsize;
    char magic[sizeof(GRIT_CONFIG_TRAILER_MAGIC)];
    size_t magic_len = strlen(GRIT_CONFIG_TRAILER_MAGIC);
    if (!path)
        return 0;
    fp = fopen(path, "rb");
    if (!fp)
        return 0;
    if (fseek(fp, 0, SEEK_END) != 0 || (fsize = ftell(fp)) < (long)GRIT_CONFIG_TRAILER_SIZE) {
        fclose(fp);
        return 0;
    }
    if (fseek(fp, fsize - GRIT_CONFIG_TRAILER_SIZE, SEEK_SET) != 0 ||
        fread(magic, 1, magic_len, fp) != magic_len) {
        fclose(fp);
        return 0;
    }
    fclose(fp);
    return memcmp(magic, GRIT_CONFIG_TRAILER_MAGIC, magic_len) == 0 ? GRIT_CONFIG_TRAILER_SIZE : 0;
}

void bb_config_read_trailer_file(const char *path, struct bb_config_trailer *out)
{
    unsigned char raw[GRIT_CONFIG_TRAILER_SIZE + 1];
    unsigned char payload[GRIT_CONFIG_TRAILER_SIZE + 1];
    char meta[GRIT_CONFIG_TRAILER_SIZE + 1];
    char *raw_text = (char *)raw;
    char *line, *save = NULL, *payload_start = NULL;
    char version[16] = "", encoding[16] = "plain", payload_format[16] = "raw", sha[65] = "", key_hex[129] = "";
    unsigned long payload_size = 0, payload_offset = 0;
    unsigned char key[64], hash[32];
    char got[65];
    size_t key_len = 0, payload_len = 0;
    FILE *fp;
    long fsize;
    size_t i;

    memset(out, 0, sizeof(*out));
    snprintf(out->encoding, sizeof(out->encoding), "none");
    trailer_set_error(out, "absent");

    if (!path || !bb_config_file_trailer_span(path))
        return;
    out->present = 1;
    snprintf(out->encoding, sizeof(out->encoding), "unknown");
    trailer_set_error(out, "invalid");

    fp = fopen(path, "rb");
    if (!fp)
        return;
    if (fseek(fp, 0, SEEK_END) != 0 || (fsize = ftell(fp)) < (long)GRIT_CONFIG_TRAILER_SIZE ||
        fseek(fp, fsize - GRIT_CONFIG_TRAILER_SIZE, SEEK_SET) != 0 ||
        fread(raw, 1, GRIT_CONFIG_TRAILER_SIZE, fp) != GRIT_CONFIG_TRAILER_SIZE) {
        fclose(fp);
        return;
    }
    fclose(fp);
    raw[GRIT_CONFIG_TRAILER_SIZE] = '\0';
    memcpy(meta, raw, GRIT_CONFIG_TRAILER_SIZE + 1);

    line = strtok_r(meta, "\n", &save);
    if (!line || strcmp(line, GRIT_CONFIG_TRAILER_MAGIC))
        return;
    snprintf(out->encoding, sizeof(out->encoding), "%s", encoding);
    while ((line = strtok_r(NULL, "\n", &save)) != NULL) {
        char *eq;
        if (!strcmp(line, "ENDMETA")) {
            payload_start = raw_text + (line + strlen(line) + 1 - meta);
            break;
        }
        eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq++ = '\0';
        if (!strcmp(line, "version"))
            snprintf(version, sizeof(version), "%s", eq);
        else if (!strcmp(line, "encoding"))
            snprintf(encoding, sizeof(encoding), "%s", eq);
        else if (!strcmp(line, "payload_format"))
            snprintf(payload_format, sizeof(payload_format), "%s", eq);
        else if (!strcmp(line, "size"))
            payload_size = strtoul(eq, NULL, 10);
        else if (!strcmp(line, "payload_offset"))
            payload_offset = strtoul(eq, NULL, 10);
        else if (!strcmp(line, "sha256"))
            snprintf(sha, sizeof(sha), "%s", eq);
        else if (!strcmp(line, "key_hex"))
            snprintf(key_hex, sizeof(key_hex), "%s", eq);
    }
    snprintf(out->encoding, sizeof(out->encoding), "%s", encoding);
    if (strcmp(version, "1")) {
        trailer_set_error(out, "unsupported version");
        return;
    }
    if (!payload_start || payload_size == 0 || payload_size >= GRIT_CONFIG_TRAILER_SIZE || strlen(sha) != 64) {
        trailer_set_error(out, "payload bounds invalid");
        return;
    }
    if (payload_offset != (unsigned long)(payload_start - (char *)raw) ||
        payload_offset + payload_size > GRIT_CONFIG_TRAILER_SIZE) {
        trailer_set_error(out, "payload bounds invalid");
        return;
    }
    if (!strcmp(payload_format, "hex")) {
        if (hex_to_bytes(payload_start, payload, sizeof(payload) - 1, &payload_len) != 0 ||
            payload_len == 0 || payload_size != strlen(payload_start)) {
            trailer_set_error(out, "invalid hex payload");
            return;
        }
    } else if (!strcmp(payload_format, "raw")) {
        memcpy(payload, payload_start, payload_size);
        payload_len = payload_size;
    } else {
        trailer_set_error(out, "unsupported payload format");
        return;
    }
    if (!strcmp(encoding, "xor")) {
        if (hex_to_bytes(key_hex, key, sizeof(key), &key_len) != 0) {
            trailer_set_error(out, "invalid xor key");
            return;
        }
        for (i = 0; i < payload_len; i++)
            payload[i] = (unsigned char)(payload[i] ^ key[i % key_len]);
    } else if (strcmp(encoding, "plain")) {
        trailer_set_error(out, "unsupported encoding");
        return;
    }
    payload[payload_len] = '\0';
    {
        bb_sha256_ctx ctx;
        bb_sha256_init(&ctx);
        bb_sha256_update(&ctx, payload, payload_len);
        bb_sha256_final(&ctx, hash);
    }
    bb_sha256_hex(hash, got);
    if (strcmp(got, sha)) {
        trailer_set_error(out, "checksum mismatch");
        return;
    }
    memcpy(out->payload, payload, payload_len + 1);
    out->payload_len = payload_len;
    out->valid = 1;
    trailer_set_error(out, "ok");
}
