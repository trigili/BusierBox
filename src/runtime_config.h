#ifndef BUSIERBOX_RUNTIME_CONFIG_H
#define BUSIERBOX_RUNTIME_CONFIG_H

#include <stddef.h>
#include <stdio.h>

#define BB_CONFIG_TRAILER_SIZE 4096
#define BB_CONFIG_TRAILER_MAGIC "BBXCONFIGv1"

const char *bb_config_get(const char *key);
const char *bb_config_compiled(const char *key);
int bb_config_key_allowed(const char *key);
int bb_config_trailer_present(void);
int bb_config_trailer_valid(void);
int bb_config_trailer_override_count(void);
const char *bb_config_trailer_error(void);
const char *bb_config_trailer_encoding(void);
const char *bb_config_effective_source(void);
size_t bb_config_file_trailer_span(const char *path);
void bb_config_print_compiled_json(FILE *out, void (*json_string)(FILE *, const char *));
void bb_config_print_effective_json(FILE *out, void (*json_string)(FILE *, const char *));
void bb_config_print_trailer_json(FILE *out, void (*json_string)(FILE *, const char *));
void bb_config_print_runtime_summary_json(FILE *out, void (*json_string)(FILE *, const char *));

#endif
