#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "applets.h"
#include "effective_config.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

struct clean_result {
    int writes_attempted;
    int writes_blocked;
    int paths_cleaned;
    int paths_failed;
    int cleanup_complete;
    const char *cleanup_warning;
};

#define MAX_CLEANUP_RECORDS 256

struct cleanup_record {
    char op[64];
    char path[PATH_MAX];
    char scope[64];
    char detail[512];
    char cleanup_action[64];
};

static int json_get_string_field(const char *line, const char *key, char *out, size_t outsz);

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static void print_ledger_human(void)
{
    char path[PATH_MAX], line[1024];
    FILE *fp = fopen(bb_ledger_path(path, sizeof(path)), "r");
    if (!fp) {
        printf("cleanup-ledger: no ledger at %s\n", path);
        return;
    }
    while (fgets(line, sizeof(line), fp))
        fputs(line, stdout);
    fclose(fp);
}

static int print_clean_dry_run(int include_external)
{
    char path[PATH_MAX], line[1024];
    FILE *fp = fopen(bb_ledger_path(path, sizeof(path)), "r");

    printf("Would remove:\n");
    printf("  %s\n", BB_RUNTIME_ROOT);
    if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
        BB_RUNTIME_FALLBACK_ROOT[0] &&
        strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT))
        printf("  %s (fallback root, if BusierBox used it)\n", BB_RUNTIME_FALLBACK_ROOT);
    if (!fp) {
        printf("Ledger: no ledger at %s\n", path);
        return 0;
    }
    while (fgets(line, sizeof(line), fp)) {
        if (strstr(line, "\"scope\":\"external\"")) {
            if (include_external)
                printf("  external recorded: %s", line);
            else
                printf("External changes recorded but not removed without --external --apply:\n  %s", line);
        }
    }
    fclose(fp);
    return 0;
}

static void print_clean_json_array_runtime_roots(int ledger)
{
    int wrote = 0;
    fputc('[', stdout);
    bb_json_string(stdout, BB_RUNTIME_ROOT);
    wrote = 1;
    if (ledger &&
        !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
        BB_RUNTIME_FALLBACK_ROOT[0] &&
        strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT)) {
        if (wrote)
            fputc(',', stdout);
        bb_json_string(stdout, BB_RUNTIME_FALLBACK_ROOT);
    }
    fputc(']', stdout);
}

static void print_clean_json_external_entries(int include_external)
{
    char path[PATH_MAX], line[2048];
    FILE *fp = fopen(bb_ledger_path(path, sizeof(path)), "r");
    int first = 1;

    fputc('[', stdout);
    if (fp) {
        while (fgets(line, sizeof(line), fp)) {
            line[strcspn(line, "\r\n")] = '\0';
            if (!line[0] || !strstr(line, "\"scope\":\"external\""))
                continue;
            if (!first)
                fputc(',', stdout);
            if (include_external)
                fputs(line, stdout);
            else {
                fputs("{\"blocked_without_external_apply\":true,\"entry\":", stdout);
                fputs(line, stdout);
                fputc('}', stdout);
            }
            first = 0;
        }
        fclose(fp);
    }
    fputc(']', stdout);
}

static int count_external_entries(void)
{
    char path[PATH_MAX], line[2048];
    FILE *fp = fopen(bb_ledger_path(path, sizeof(path)), "r");
    int count = 0;

    if (!fp)
        return 0;
    while (fgets(line, sizeof(line), fp))
        if (strstr(line, "\"scope\":\"external\""))
            count++;
    fclose(fp);
    return count;
}

static int path_is_under_dir(const char *path, const char *dir)
{
    size_t len;

    if (!path || !dir || !dir[0])
        return 0;
    len = strlen(dir);
    if (!strcmp(path, dir))
        return 1;
    return !strncmp(path, dir, len) && (dir[len - 1] == '/' || path[len] == '/');
}

static const char *ledger_cleanup_action(const char *path, const char *op, int ledger)
{
    if (op && !strcmp(op, "remove"))
        return "already-recorded-remove";
    if (path_is_under_dir(path, BB_RUNTIME_ROOT))
        return "remove_with_runtime_root";
    if (ledger &&
        !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
        BB_RUNTIME_FALLBACK_ROOT[0] &&
        strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT) &&
        path_is_under_dir(path, BB_RUNTIME_FALLBACK_ROOT))
        return "remove_with_fallback_root";
    return "not_in_default_clean_scope";
}

static int load_ledgered_cleanup_records(struct cleanup_record *records, int max_records, int ledger)
{
    char path[PATH_MAX], line[2048];
    FILE *fp = fopen(bb_ledger_path(path, sizeof(path)), "r");
    int count = 0;

    if (!fp)
        return 0;
    while (fgets(line, sizeof(line), fp)) {
        char ledger_path[PATH_MAX], op[64], scope[64], detail[512];

        if (json_get_string_field(line, "path", ledger_path, sizeof(ledger_path)) != 0)
            continue;
        scope[0] = '\0';
        if (json_get_string_field(line, "scope", scope, sizeof(scope)) == 0 &&
            !strcmp(scope, "external"))
            continue;
        if (!records || count >= max_records)
            continue;
        op[0] = '\0';
        detail[0] = '\0';
        json_get_string_field(line, "op", op, sizeof(op));
        json_get_string_field(line, "detail", detail, sizeof(detail));
        snprintf(records[count].op, sizeof(records[count].op), "%s", op);
        snprintf(records[count].path, sizeof(records[count].path), "%s", ledger_path);
        snprintf(records[count].scope, sizeof(records[count].scope), "%s", scope[0] ? scope : "runtime");
        snprintf(records[count].detail, sizeof(records[count].detail), "%s", detail);
        snprintf(records[count].cleanup_action, sizeof(records[count].cleanup_action), "%s",
                 ledger_cleanup_action(ledger_path, op, ledger));
        count++;
    }
    fclose(fp);
    return count;
}

static void print_ledgered_cleanup_paths_json(const struct cleanup_record *records, int count)
{
    int i;

    fputc('[', stdout);
    for (i = 0; i < count; i++) {
        if (i)
            fputc(',', stdout);
        fputs("{\"op\":", stdout);
        bb_json_string(stdout, records[i].op);
        fputs(",\"path\":", stdout);
        bb_json_string(stdout, records[i].path);
        fputs(",\"scope\":", stdout);
        bb_json_string(stdout, records[i].scope);
        fputs(",\"cleanup_action\":", stdout);
        bb_json_string(stdout, records[i].cleanup_action);
        if (records[i].detail[0]) {
            fputs(",\"detail\":", stdout);
            bb_json_string(stdout, records[i].detail);
        }
        fputc('}', stdout);
    }
    fputc(']', stdout);
}

static int cleanup_record_field_equals(const struct cleanup_record *record, const char *field,
                                       const char *value)
{
    if (!strcmp(field, "path"))
        return !strcmp(record->path, value);
    if (!strcmp(field, "scope"))
        return !strcmp(record->scope, value);
    if (!strcmp(field, "op"))
        return !strcmp(record->op, value);
    if (!strcmp(field, "cleanup_action"))
        return !strcmp(record->cleanup_action, value);
    return 0;
}

static const char *cleanup_record_field_value(const struct cleanup_record *record, const char *field)
{
    if (!strcmp(field, "path"))
        return record->path;
    if (!strcmp(field, "scope"))
        return record->scope;
    if (!strcmp(field, "op"))
        return record->op;
    if (!strcmp(field, "cleanup_action"))
        return record->cleanup_action;
    return "";
}

static void print_cleanup_record_index_json(const struct cleanup_record *records, int count,
                                            const char *field)
{
    int i, first_key = 1;

    fputc('{', stdout);
    for (i = 0; i < count; i++) {
        int j, first_index = 1, seen = 0;
        const char *value = cleanup_record_field_value(&records[i], field);

        if (!value[0])
            continue;
        for (j = 0; j < i; j++) {
            if (cleanup_record_field_equals(&records[j], field, value)) {
                seen = 1;
                break;
            }
        }
        if (seen)
            continue;
        if (!first_key)
            fputc(',', stdout);
        bb_json_string(stdout, value);
        fputc(':', stdout);
        fputc('[', stdout);
        for (j = 0; j < count; j++) {
            if (!cleanup_record_field_equals(&records[j], field, value))
                continue;
            if (!first_index)
                fputc(',', stdout);
            printf("%d", j);
            first_index = 0;
        }
        fputc(']', stdout);
        first_key = 0;
    }
    fputc('}', stdout);
}

static void print_residue_plan_api_json(int cleanup_count)
{
    fputs(",\"api\":{\"schema\":1,\"collections_key\":\"api_collections\",\"resources_key\":\"api_resources\",\"resource_count\":1}", stdout);
    fputs(",\"api_collections\":{\"ledgered_cleanup_paths\":{\"name\":\"ledgered_cleanup_paths\",\"count\":", stdout);
    printf("%d", cleanup_count);
    fputs(",\"count_summary_key\":\"ledgered_cleanup_path_count\",\"summary_key\":\"ledgered_cleanup_path_count\",\"primary_key\":\"path\",\"indexes\":[", stdout);
    bb_json_string(stdout, "ledgered_cleanup_paths_by_path");
    fputc(',', stdout);
    bb_json_string(stdout, "ledgered_cleanup_paths_by_scope");
    fputc(',', stdout);
    bb_json_string(stdout, "ledgered_cleanup_paths_by_op");
    fputc(',', stdout);
    bb_json_string(stdout, "ledgered_cleanup_paths_by_cleanup_action");
    fputs("]}}", stdout);
    fputs(",\"api_resources\":[{\"name\":\"ledgered_cleanup_paths\",\"records_key\":\"ledgered_cleanup_paths\",\"collection_key\":\"api_collections.ledgered_cleanup_paths\",\"count\":", stdout);
    printf("%d", cleanup_count);
    fputs(",\"summary_key\":\"ledgered_cleanup_path_count\",\"primary_key\":\"path\"}]", stdout);
    fputs(",\"api_resources_by_name\":{\"ledgered_cleanup_paths\":{\"name\":\"ledgered_cleanup_paths\",\"records_key\":\"ledgered_cleanup_paths\",\"collection_key\":\"api_collections.ledgered_cleanup_paths\",\"count\":", stdout);
    printf("%d", cleanup_count);
    fputs(",\"summary_key\":\"ledgered_cleanup_path_count\",\"primary_key\":\"path\"}}", stdout);
    fputs(",\"api_resources_by_records_key\":{\"ledgered_cleanup_paths\":[{\"name\":\"ledgered_cleanup_paths\",\"records_key\":\"ledgered_cleanup_paths\",\"collection_key\":\"api_collections.ledgered_cleanup_paths\",\"count\":", stdout);
    printf("%d", cleanup_count);
    fputs(",\"summary_key\":\"ledgered_cleanup_path_count\",\"primary_key\":\"path\"}]}", stdout);
    fputs(",\"api_resources_by_summary_key\":{\"ledgered_cleanup_path_count\":[{\"name\":\"ledgered_cleanup_paths\",\"records_key\":\"ledgered_cleanup_paths\",\"collection_key\":\"api_collections.ledgered_cleanup_paths\",\"count\":", stdout);
    printf("%d", cleanup_count);
    fputs(",\"summary_key\":\"ledgered_cleanup_path_count\",\"primary_key\":\"path\"}]}", stdout);
}

static void print_clean_json_string_array_item(const char *s, int *first)
{
    if (!*first)
        fputc(',', stdout);
    bb_json_string(stdout, s);
    *first = 0;
}

static void print_residue_plan_json(int include_external, int ledger)
{
    char ledger_path_buf[PATH_MAX];
    struct cleanup_record *cleanup_records = calloc(MAX_CLEANUP_RECORDS, sizeof(*cleanup_records));
    int cleanup_count = cleanup_records ?
        load_ledgered_cleanup_records(cleanup_records, MAX_CLEANUP_RECORDS, ledger) : 0;
    int first = 1;
    int aggressive = !strcmp(BB_RUNTIME_MODE, "no-residue") && !strcmp(BB_NORESIDUE_LEVEL, "aggressive");

    fputs("{\"runtime_mode\":", stdout);
    bb_json_string(stdout, BB_RUNTIME_MODE);
    fputs(",\"noresidue_level\":", stdout);
    bb_json_string(stdout, BB_NORESIDUE_LEVEL);
    fputs(",\"intended_write_paths\":[", stdout);
    print_clean_json_string_array_item(BB_RUNTIME_ROOT, &first);
    if (ledger) {
        first = 0;
        if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
            BB_RUNTIME_FALLBACK_ROOT[0] &&
            strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT))
            print_clean_json_string_array_item(BB_RUNTIME_FALLBACK_ROOT, &first);
    }
    print_clean_json_string_array_item(bb_ledger_path(ledger_path_buf, sizeof(ledger_path_buf)), &first);
    fputs("],\"cleanup_commands\":[", stdout);
    first = 1;
    print_clean_json_string_array_item("busierbox clean --dry-run --json", &first);
    print_clean_json_string_array_item("busierbox clean --ledger --json", &first);
    if (count_external_entries() > 0)
        print_clean_json_string_array_item("busierbox clean --external --apply", &first);
    printf("],\"ledgered_cleanup_path_count\":%d", cleanup_count);
    printf(",\"external_blocked_count\":%d", include_external ? 0 : count_external_entries());
    fputs(",\"ledgered_cleanup_paths\":", stdout);
    print_ledgered_cleanup_paths_json(cleanup_records, cleanup_count);
    fputs(",\"ledgered_cleanup_paths_by_path\":", stdout);
    print_cleanup_record_index_json(cleanup_records, cleanup_count, "path");
    fputs(",\"ledgered_cleanup_paths_by_scope\":", stdout);
    print_cleanup_record_index_json(cleanup_records, cleanup_count, "scope");
    fputs(",\"ledgered_cleanup_paths_by_op\":", stdout);
    print_cleanup_record_index_json(cleanup_records, cleanup_count, "op");
    fputs(",\"ledgered_cleanup_paths_by_cleanup_action\":", stdout);
    print_cleanup_record_index_json(cleanup_records, cleanup_count, "cleanup_action");
    print_residue_plan_api_json(cleanup_count);
    fputs(",\"uncleanable_paths\":[", stdout);
    if (!include_external) {
        char path[PATH_MAX], line[2048];
        FILE *fp = fopen(bb_ledger_path(path, sizeof(path)), "r");
        first = 1;
        if (fp) {
            while (fgets(line, sizeof(line), fp)) {
                char external_path[PATH_MAX];
                if (!strstr(line, "\"scope\":\"external\""))
                    continue;
                if (json_get_string_field(line, "path", external_path, sizeof(external_path)) == 0)
                    print_clean_json_string_array_item(external_path, &first);
            }
            fclose(fp);
        }
    }
    fputs("],\"features_disabled\":[", stdout);
    first = 1;
    if (aggressive) {
        print_clean_json_string_array_item("runtime fallback root", &first);
        print_clean_json_string_array_item("cwd scratch fallback for generated upload files", &first);
        print_clean_json_string_array_item("persistent target logs by default", &first);
        print_clean_json_string_array_item("forensic no-trace claims", &first);
    } else {
        print_clean_json_string_array_item("forensic no-trace claims", &first);
    }
    fputs("],\"cleanup_limits\":[", stdout);
    first = 1;
    print_clean_json_string_array_item("kernel logs", &first);
    print_clean_json_string_array_item("shell history", &first);
    print_clean_json_string_array_item("filesystem journals", &first);
    print_clean_json_string_array_item("flash wear-leveling", &first);
    print_clean_json_string_array_item("audit logs", &first);
    print_clean_json_string_array_item("crash dumps", &first);
    print_clean_json_string_array_item("remote service logs", &first);
    print_clean_json_string_array_item("operator-side records", &first);
    fputs("],\"forensic_no_trace\":false", stdout);
    free(cleanup_records);
    fputc('}', stdout);
}

static void print_clean_result_json(const struct clean_result *result)
{
    printf(",\"writes_attempted\":%d", result ? result->writes_attempted : 0);
    printf(",\"writes_blocked\":%d", result ? result->writes_blocked : 0);
    printf(",\"paths_cleaned\":%d", result ? result->paths_cleaned : 0);
    printf(",\"paths_failed\":%d", result ? result->paths_failed : 0);
    printf(",\"cleanup_complete\":%s", result && result->cleanup_complete ? "true" : "false");
    fputs(",\"cleanup_warning\":", stdout);
    bb_json_string(stdout, result && result->cleanup_warning ? result->cleanup_warning : "");
}

static void print_clean_json(int dry_run, int include_external, int ledger, int external_applied,
                             const struct clean_result *result)
{
    char path[PATH_MAX];

    printf("{\"schema\":1,\"command\":\"clean\",\"dry_run\":%s", dry_run ? "true" : "false");
    fputs(",\"runtime_root\":", stdout);
    bb_json_string(stdout, BB_RUNTIME_ROOT);
    fputs(",\"fallback_root\":", stdout);
    bb_json_string(stdout, BB_RUNTIME_FALLBACK_ROOT);
    printf(",\"fallback_enabled\":%s", !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") ? "true" : "false");
    fputs(",\"cleanup_ledger_path\":", stdout);
    bb_json_string(stdout, bb_ledger_path(path, sizeof(path)));
    printf(",\"include_external\":%s,\"external_cleanup_applied\":%s",
           include_external ? "true" : "false", external_applied ? "true" : "false");
    fputs(",\"residue_plan\":", stdout);
    print_residue_plan_json(include_external, ledger);
    print_clean_result_json(result);
    fputs(dry_run ? ",\"would_remove\":" : ",\"removed\":", stdout);
    print_clean_json_array_runtime_roots(dry_run || ledger);
    fputs(",\"external_entries\":", stdout);
    print_clean_json_external_entries(include_external);
    puts("}");
}

static int remove_runtime_root_checked(const char *path, int *cleaned)
{
    struct stat st;

    if (cleaned)
        *cleaned = 0;
    if (!path || !path[0])
        return 0;
    if (lstat(path, &st) != 0)
        return errno == ENOENT ? 0 : -1;
    if (!S_ISDIR(st.st_mode)) {
        fprintf(stderr, "clean: skipping non-directory runtime root candidate %s\n", path);
        return 0;
    }
    if (bb_rm_rf(path) != 0)
        return -1;
    if (cleaned)
        *cleaned = 1;
    return 0;
}

static int json_get_string_field(const char *line, const char *key, char *out, size_t outsz)
{
    char needle[64];
    const char *p;
    size_t used = 0;

    if (!line || !key || !out || outsz == 0)
        return -1;
    out[0] = '\0';
    snprintf(needle, sizeof(needle), "\"%s\":\"", key);
    p = strstr(line, needle);
    if (!p)
        return -1;
    p += strlen(needle);
    while (*p && *p != '"') {
        char c = *p++;
        if (c == '\\' && *p) {
            c = *p++;
            if (c == 'n')
                c = '\n';
            else if (c == 'r')
                c = '\r';
            else if (c == 't')
                c = '\t';
        }
        if (used + 1 < outsz)
            out[used++] = c;
    }
    out[used] = '\0';
    return *p == '"' ? 0 : -1;
}

static int remove_rshell_marked_block(const char *path)
{
    char tmp[PATH_MAX], line[8192];
    FILE *in, *out;
    int skipping = 0, removed = 0;

    in = fopen(path, "r");
    if (!in)
        return errno == ENOENT ? 0 : -1;
    snprintf(tmp, sizeof(tmp), "%s.busierbox.clean.%ld", path, (long)getpid());
    out = fopen(tmp, "w");
    if (!out) {
        fclose(in);
        return -1;
    }
    while (fgets(line, sizeof(line), in)) {
        if (!strcmp(line, "# BEGIN BUSIERBOX RSHELL\n") ||
            !strcmp(line, "# BEGIN BUSIERBOX RSHELL\r\n")) {
            skipping = 1;
            removed = 1;
            continue;
        }
        if (skipping) {
            if (!strcmp(line, "# END BUSIERBOX RSHELL\n") ||
                !strcmp(line, "# END BUSIERBOX RSHELL\r\n"))
                skipping = 0;
            continue;
        }
        fputs(line, out);
    }
    if (fclose(in) != 0)
        removed = -1;
    if (fclose(out) != 0)
        removed = -1;
    if (removed < 0) {
        unlink(tmp);
        return -1;
    }
    if (!removed) {
        unlink(tmp);
        return 0;
    }
    if (rename(tmp, path) != 0) {
        unlink(tmp);
        return -1;
    }
    chmod(path, 0600);
    return 0;
}

static int clean_external_from_ledger(int quiet, struct clean_result *result)
{
    char ledger[PATH_MAX], line[2048];
    FILE *fp = fopen(bb_ledger_path(ledger, sizeof(ledger)), "r");
    int failures = 0;

    if (!fp)
        return 0;
    while (fgets(line, sizeof(line), fp)) {
        char op[32], path[PATH_MAX], scope[32], mode[64];

        if (json_get_string_field(line, "scope", scope, sizeof(scope)) != 0 ||
            strcmp(scope, "external") != 0)
            continue;
        if (json_get_string_field(line, "op", op, sizeof(op)) != 0 ||
            json_get_string_field(line, "path", path, sizeof(path)) != 0)
            continue;
        mode[0] = '\0';
        json_get_string_field(line, "mode", mode, sizeof(mode));
        if (result)
            result->writes_attempted++;

        if (!strcmp(path, "/root/.ssh/authorized_keys") &&
            !strcmp(op, "modify") && !strcmp(mode, "root-merge")) {
            int entry_failed = 0;
            if (remove_rshell_marked_block(path) != 0) {
                fprintf(stderr, "clean: failed to remove BusierBox rshell block from %s: %s\n", path, strerror(errno));
                failures = 1;
                entry_failed = 1;
                if (result)
                    result->paths_failed++;
            } else if (!quiet) {
                printf("clean: removed BusierBox rshell block from %s\n", path);
            }
            if (result && !entry_failed)
                result->paths_cleaned++;
        } else if (!strcmp(path, "/root/.ssh/authorized_keys") &&
                   !strcmp(op, "write") && !strcmp(mode, "root-copy")) {
            int entry_failed = 0;
            if (unlink(path) != 0 && errno != ENOENT) {
                fprintf(stderr, "clean: failed to remove %s: %s\n", path, strerror(errno));
                failures = 1;
                entry_failed = 1;
                if (result)
                    result->paths_failed++;
            } else if (!quiet) {
                printf("clean: removed external %s\n", path);
            }
            if (result && !entry_failed)
                result->paths_cleaned++;
        } else if (!strcmp(op, "backup") &&
                   !strncmp(path, "/root/.ssh/authorized_keys.busierbox.bak.", 41)) {
            int entry_failed = 0;
            if (unlink(path) != 0 && errno != ENOENT) {
                fprintf(stderr, "clean: failed to remove backup %s: %s\n", path, strerror(errno));
                failures = 1;
                entry_failed = 1;
                if (result)
                    result->paths_failed++;
            } else if (!quiet) {
                printf("clean: removed external backup %s\n", path);
            }
            if (result && !entry_failed)
                result->paths_cleaned++;
        } else {
            if (result)
                result->writes_blocked++;
            if (!quiet)
                printf("clean: skipped unsupported external ledger entry %s\n", path);
        }
    }
    fclose(fp);
    return failures ? -1 : 0;
}

int bb_clean_external_from_ledger(void)
{
    return clean_external_from_ledger(0, NULL);
}

int applet_cleanup_ledger_main(int argc, char **argv)
{
    int json = 0;
    char path[PATH_MAX], line[1024];
    FILE *fp;
    int first = 1;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox cleanup-ledger [--json]");
        puts("Print the BusierBox-created cleanup ledger.");
        return 0;
    }
    for (i = 1; i < argc; i++)
        if (!strcmp(argv[i], "--json"))
            json = 1;

    fp = fopen(bb_ledger_path(path, sizeof(path)), "r");
    if (!json) {
        print_ledger_human();
        return 0;
    }
    printf("{\"schema\":1,\"path\":");
    bb_json_string(stdout, path);
    printf(",\"entries\":[");
    if (fp) {
        while (fgets(line, sizeof(line), fp)) {
            line[strcspn(line, "\r\n")] = '\0';
            if (!line[0])
                continue;
            printf("%s%s", first ? "" : ",", line);
            first = 0;
        }
        fclose(fp);
    }
    printf("]}\n");
    return 0;
}

int applet_clean_main(int argc, char **argv)
{
    int dry_run = 0, ledger = 0, external = 0, apply = 0, json = 0;
    struct clean_result result = {0, 0, 0, 0, 0, ""};
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox clean [--dry-run] [--json] [--ledger] [--external --apply]");
        printf("Removes the configured BusierBox runtime directory (%s).\n", BB_RUNTIME_ROOT);
        puts("External cleanup is never applied unless both --external and --apply are present.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--dry-run"))
            dry_run = 1;
        else if (!strcmp(argv[i], "--ledger"))
            ledger = 1;
        else if (!strcmp(argv[i], "--external"))
            external = 1;
        else if (!strcmp(argv[i], "--apply"))
            apply = 1;
        else if (!strcmp(argv[i], "--json"))
            json = 1;
        else {
            fprintf(stderr, "clean: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (dry_run) {
        if (json) {
            result.writes_blocked = external ? 0 : count_external_entries();
            result.cleanup_warning = "dry-run only";
            print_clean_json(1, external, ledger, 0, &result);
            return 0;
        }
        return print_clean_dry_run(external);
    }
    if (external && !apply) {
        fputs("clean: external cleanup requires --external --apply\n", stderr);
        return 2;
    }
    if (external && apply) {
        if (clean_external_from_ledger(json, &result) != 0) {
            if (json) {
                result.cleanup_warning = "external cleanup failed";
                print_clean_json(0, external, ledger, 1, &result);
            }
            return 1;
        }
    } else {
        result.writes_blocked = count_external_entries();
    }
    if (ledger) {
        bb_ledger_record("remove", BB_RUNTIME_ROOT, "runtime", "clean --ledger");
        if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
            BB_RUNTIME_FALLBACK_ROOT[0] &&
            strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT))
            bb_ledger_record("remove", BB_RUNTIME_FALLBACK_ROOT, "runtime", "clean --ledger fallback root");
    }
    {
        int cleaned = 0;
        result.writes_attempted++;
        if (remove_runtime_root_checked(BB_RUNTIME_ROOT, &cleaned) != 0) {
            result.paths_failed++;
            result.cleanup_warning = "runtime root cleanup failed";
            if (json)
                print_clean_json(0, external, ledger, external && apply, &result);
            fprintf(stderr, "clean: %s\n", strerror(errno));
            return 1;
        }
        result.paths_cleaned += cleaned;
    }
    if (ledger &&
        !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
        BB_RUNTIME_FALLBACK_ROOT[0] &&
        strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT)) {
        int cleaned = 0;
        result.writes_attempted++;
        if (remove_runtime_root_checked(BB_RUNTIME_FALLBACK_ROOT, &cleaned) != 0) {
            result.paths_failed++;
            result.cleanup_warning = "fallback root cleanup failed";
            if (json)
                print_clean_json(0, external, ledger, external && apply, &result);
            fprintf(stderr, "clean: fallback root %s: %s\n", BB_RUNTIME_FALLBACK_ROOT, strerror(errno));
            return 1;
        }
        result.paths_cleaned += cleaned;
    }
    result.cleanup_complete = result.paths_failed == 0 && result.writes_blocked == 0;
    if (result.writes_blocked > 0)
        result.cleanup_warning = external && apply ?
            "unsupported external ledger entries require manual cleanup" :
            "external ledger entries require --external --apply";
    if (json) {
        print_clean_json(0, external, ledger, external && apply, &result);
        return 0;
    }
    if (result.writes_blocked > 0)
        printf("clean: external cleanup blocked entries=%d; use --external --apply\n", result.writes_blocked);
    printf("clean: removed %s\n", BB_RUNTIME_ROOT);
    return 0;
}
