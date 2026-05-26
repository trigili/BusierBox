#ifndef BUSIERBOX_TRAILER_CONFIG_H
#define BUSIERBOX_TRAILER_CONFIG_H

#include <stddef.h>

#define BB_CONFIG_TRAILER_SIZE 4096
#define BB_CONFIG_TRAILER_MAGIC "BBXCONFIGv1"

struct bb_config_trailer {
    int present;
    int valid;
    char error[160];
    char encoding[16];
    char payload[BB_CONFIG_TRAILER_SIZE + 1];
    size_t payload_len;
};

size_t bb_config_file_trailer_span(const char *path);
void bb_config_read_trailer_file(const char *path, struct bb_config_trailer *out);

#endif
