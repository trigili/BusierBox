#ifndef GRIT_JSON_HELPERS_H
#define GRIT_JSON_HELPERS_H

#include <stdio.h>

void bb_json_string(FILE *out, const char *s);
int bb_json_array_summary(const char *json, const char *key, FILE *out);
const char *bb_json_bool_value(const char *json, const char *key);
int bb_json_object_summary(const char *json, const char *key, FILE *out);
int bb_json_array_count_field(const char *json, const char *key);
int bb_json_write_raw_field_or(FILE *out, const char *json, const char *key, const char *fallback);
void bb_json_write_string_array(FILE *out, const char *const *items);

#endif
