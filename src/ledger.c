#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#include "applets.h"
#include "runtime_config.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_RUNTIME_ROOT
#define BB_RUNTIME_ROOT "./.busierbox"
#endif

#undef BB_RUNTIME_ROOT
#define BB_RUNTIME_ROOT bb_config_get("BB_RUNTIME_ROOT")

static int ledger_mkdir_p(const char *path, mode_t mode)
{
    char tmp[PATH_MAX];
    char *p;

    snprintf(tmp, sizeof(tmp), "%s", path);
    for (p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, mode) != 0 && errno != EEXIST)
                return -1;
            *p = '/';
        }
    }
    if (mkdir(tmp, mode) != 0 && errno != EEXIST)
        return -1;
    return 0;
}

static void ledger_json_string(FILE *out, const char *s)
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

const char *bb_ledger_path(char *out, size_t outsz)
{
    snprintf(out, outsz, "%s/run/cleanup-ledger.jsonl", BB_RUNTIME_ROOT);
    return out;
}

void bb_ledger_record(const char *op, const char *path, const char *scope, const char *detail)
{
    char run_dir[PATH_MAX], ledger[PATH_MAX];
    FILE *fp;
    time_t now = time(NULL);

    snprintf(run_dir, sizeof(run_dir), "%s/run", BB_RUNTIME_ROOT);
    if (ledger_mkdir_p(run_dir, 0700) != 0)
        return;
    fp = fopen(bb_ledger_path(ledger, sizeof(ledger)), "a");
    if (!fp)
        return;
    fputs("{\"op\":", fp);
    ledger_json_string(fp, op);
    fputs(",\"path\":", fp);
    ledger_json_string(fp, path);
    fputs(",\"scope\":", fp);
    ledger_json_string(fp, scope ? scope : "runtime");
    fprintf(fp, ",\"ts\":%ld", (long)now);
    if (detail && *detail) {
        fputs(",\"detail\":", fp);
        ledger_json_string(fp, detail);
    }
    fputs("}\n", fp);
    fclose(fp);
}
