#define _POSIX_C_SOURCE 200809L

#include <string.h>

#include "json_helpers.h"

void bb_json_string(FILE *out, const char *s)
{
    fputc('"', out);
    if (s) {
        while (*s) {
            unsigned char c = (unsigned char)*s++;
            if (c == '"' || c == '\\') {
                fputc('\\', out);
                fputc(c, out);
            } else if (c == '\n') {
                fputs("\\n", out);
            } else if (c == '\r') {
                fputs("\\r", out);
            } else if (c == '\t') {
                fputs("\\t", out);
            } else if (c < 32) {
                fprintf(out, "\\u%04x", c);
            } else {
                fputc(c, out);
            }
        }
    }
    fputc('"', out);
}

int bb_json_array_summary(const char *json, const char *key, FILE *out)
{
    char needle[96];
    const char *p, *end;
    int count = 0, first = 1;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p)
        return 0;
    p = strchr(p, '[');
    if (!p)
        return 0;
    end = strchr(p, ']');
    if (!end)
        return 0;
    fputc('[', out);
    while (p < end) {
        const char *q = strchr(p, '"');
        const char *r;
        if (!q || q >= end)
            break;
        r = strchr(q + 1, '"');
        if (!r || r > end)
            break;
        if (!first)
            fputc(',', out);
        fwrite(q + 1, 1, (size_t)(r - q - 1), out);
        first = 0;
        count++;
        p = r + 1;
    }
    fputc(']', out);
    return count;
}

const char *bb_json_bool_value(const char *json, const char *key)
{
    char needle[96];
    const char *p;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p)
        return "unknown";
    p = strchr(p, ':');
    if (!p)
        return "unknown";
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n')
        p++;
    if (!strncmp(p, "true", 4))
        return "yes";
    if (!strncmp(p, "false", 5))
        return "no";
    return "unknown";
}

int bb_json_object_summary(const char *json, const char *key, FILE *out)
{
    char needle[96];
    const char *p, *end;
    int count = 0, first = 1;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p)
        return 0;
    p = strchr(p, '{');
    if (!p)
        return 0;
    end = strchr(p, '}');
    if (!end)
        return 0;
    fputc('{', out);
    while (p < end) {
        const char *q = strchr(p, '"');
        const char *r, *v, *w;
        if (!q || q >= end)
            break;
        r = strchr(q + 1, '"');
        if (!r || r >= end)
            break;
        v = strchr(r + 1, '"');
        if (!v || v >= end)
            break;
        w = strchr(v + 1, '"');
        if (!w || w >= end)
            break;
        if (!first)
            fputc(',', out);
        fwrite(q + 1, 1, (size_t)(r - q - 1), out);
        fputc('=', out);
        fwrite(v + 1, 1, (size_t)(w - v - 1), out);
        first = 0;
        count++;
        p = w + 1;
    }
    fputc('}', out);
    return count;
}

int bb_json_array_count_field(const char *json, const char *key)
{
    FILE *out = fopen("/dev/null", "w");
    int count;
    if (!out)
        return 0;
    count = bb_json_array_summary(json, key, out);
    fclose(out);
    return count;
}

static const char *json_field_value(const char *json, const char *key)
{
    char needle[96];
    const char *p;

    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p)
        return NULL;
    p = strchr(p, ':');
    if (!p)
        return NULL;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')
        p++;
    return p;
}

static const char *json_raw_value_end(const char *p)
{
    const char *q;
    int depth = 0, in_string = 0, escaped = 0;

    if (!p || !*p)
        return NULL;
    if (*p == '[' || *p == '{') {
        for (q = p; *q; q++) {
            if (in_string) {
                if (escaped)
                    escaped = 0;
                else if (*q == '\\')
                    escaped = 1;
                else if (*q == '"')
                    in_string = 0;
                continue;
            }
            if (*q == '"') {
                in_string = 1;
                continue;
            }
            if (*q == '[' || *q == '{') {
                depth++;
                continue;
            }
            if (*q == ']' || *q == '}') {
                depth--;
                if (depth == 0)
                    return q + 1;
            }
        }
        return NULL;
    }
    if (*p == '"') {
        for (q = p + 1; *q; q++) {
            if (escaped)
                escaped = 0;
            else if (*q == '\\')
                escaped = 1;
            else if (*q == '"')
                return q + 1;
        }
        return NULL;
    }
    for (q = p; *q && *q != ',' && *q != '}' && *q != ']' &&
                *q != '\r' && *q != '\n'; q++)
        ;
    while (q > p && (q[-1] == ' ' || q[-1] == '\t'))
        q--;
    return q;
}

int bb_json_write_raw_field_or(FILE *out, const char *json, const char *key, const char *fallback)
{
    const char *p = json ? json_field_value(json, key) : NULL;
    const char *end = json_raw_value_end(p);

    if (!p || !end || end <= p) {
        fputs(fallback, out);
        return 0;
    }
    fwrite(p, 1, (size_t)(end - p), out);
    return 1;
}

void bb_json_write_string_array(FILE *out, const char *const *items)
{
    int i;

    fputc('[', out);
    for (i = 0; items[i]; i++) {
        if (i)
            fputc(',', out);
        bb_json_string(out, items[i]);
    }
    fputc(']', out);
}
