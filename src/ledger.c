#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#include "applets.h"
#include "effective_config.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

const char *bb_ledger_path(char *out, size_t outsz)
{
    snprintf(out, outsz, "%s/run/cleanup-ledger.jsonl", GRIT_RUNTIME_ROOT);
    return out;
}

static const char *first_nonempty_env(const char *a, const char *b)
{
    const char *value = getenv(a);

    if (value && value[0])
        return value;
    value = getenv(b);
    return value && value[0] ? value : "";
}

void bb_ledger_record(const char *op, const char *path, const char *scope, const char *detail)
{
    char run_dir[PATH_MAX], ledger[PATH_MAX];
    const char *target_id = first_nonempty_env("GRIT_TARGET_ID", "GRIT_TARGET_ID");
    const char *target_label = first_nonempty_env("GRIT_TARGET_LABEL", "GRIT_TARGET_LABEL");
    FILE *fp;
    time_t now = time(NULL);

    snprintf(run_dir, sizeof(run_dir), "%s/run", GRIT_RUNTIME_ROOT);
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
    if (target_id[0]) {
        fputs(",\"target_id\":", fp);
        bb_json_string(fp, target_id);
        fputs(",\"target_identity_source\":\"environment\",\"target_identity_confidence\":\"operator-supplied\"", fp);
    }
    if (target_label[0]) {
        fputs(",\"target_label\":", fp);
        bb_json_string(fp, target_label);
    }
    fputs("}\n", fp);
    fclose(fp);
}

int bb_ledger_entry_count(const char *path)
{
    FILE *fp = fopen(path, "r");
    char line[1024];
    int count = 0;

    if (!fp)
        return 0;
    while (fgets(line, sizeof(line), fp)) {
        if (line[strspn(line, " \t\r\n")] != '\0')
            count++;
    }
    fclose(fp);
    return count;
}

void bb_print_cleanup_ledger_json(FILE *out, void (*json_string)(FILE *, const char *))
{
    char path[PATH_MAX];

    bb_ledger_path(path, sizeof(path));
    fprintf(out, "{\"path\":");
    json_string(out, path);
    fprintf(out, ",\"present\":%s,\"entry_count\":%d}",
            bb_path_exists(path) ? "true" : "false",
            bb_ledger_entry_count(path));
}
