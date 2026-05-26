#ifndef BUSIERBOX_PAYLOAD_RUNTIME_H
#define BUSIERBOX_PAYLOAD_RUNTIME_H

#include <stddef.h>

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

struct embedded_payload {
    int present;
    char exe[PATH_MAX];
    unsigned long long offset;
    unsigned long long size;
    char sha256[65];
    char version[128];
    char format[16];
    unsigned long long compressed_size;
};

const char *const *bb_payload_busybox_tools(void);
const char *const *bb_payload_heavy_tools(void);
void bb_print_autoexec_config(void);
int bb_get_embedded_payload(struct embedded_payload *ep);
int bb_verify_embedded_hash(const struct embedded_payload *ep);
int bb_payload_valid(const char *payload);
const char *bb_payload_extraction_mode(const char *payload, char *out, size_t outsz);
int bb_payload_id_matches(const struct embedded_payload *ep, const char *payload_dir);

#endif
