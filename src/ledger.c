#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#include "applets.h"
#include "json_helpers.h"
#include "runtime_config.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_RUNTIME_ROOT
#define BB_RUNTIME_ROOT "./.busierbox"
#endif

#undef BB_RUNTIME_ROOT
#define BB_RUNTIME_ROOT bb_config_get("BB_RUNTIME_ROOT")

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
    if (bb_mkdir_p(run_dir, 0700) != 0)
        return;
    fp = fopen(bb_ledger_path(ledger, sizeof(ledger)), "a");
    if (!fp)
        return;
    fputs("{\"op\":", fp);
    bb_json_string(fp, op);
    fputs(",\"path\":", fp);
    bb_json_string(fp, path);
    fputs(",\"scope\":", fp);
    bb_json_string(fp, scope ? scope : "runtime");
    fprintf(fp, ",\"ts\":%ld", (long)now);
    if (detail && *detail) {
        fputs(",\"detail\":", fp);
        bb_json_string(fp, detail);
    }
    fputs("}\n", fp);
    fclose(fp);
}
