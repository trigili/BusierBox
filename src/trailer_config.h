#ifndef GRIT_TRAILER_CONFIG_H
#define GRIT_TRAILER_CONFIG_H

#include <stddef.h>

#define GRIT_CONFIG_TRAILER_SIZE 4096
#define GRIT_CONFIG_TRAILER_MAGIC "BBXCONFIGv1"

struct bb_config_trailer {
    int present;
    int valid;
    char error[160];
    char encoding[16];
    char payload[GRIT_CONFIG_TRAILER_SIZE + 1];
    size_t payload_len;
};

size_t bb_config_file_trailer_span(const char *path);
void bb_config_read_trailer_file(const char *path, struct bb_config_trailer *out);

#endif
