#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "applets.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_RUNTIME_ROOT
#define BB_RUNTIME_ROOT "./.busierbox"
#endif
#ifndef BB_RUNTIME_ALLOW_FALLBACK_ROOT
#define BB_RUNTIME_ALLOW_FALLBACK_ROOT "no"
#endif
#ifndef BB_RUNTIME_FALLBACK_ROOT
#define BB_RUNTIME_FALLBACK_ROOT "/tmp/.busierbox"
#endif

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

static void print_clean_json(int dry_run, int include_external, int ledger, int external_applied)
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
    fputs(dry_run ? ",\"would_remove\":" : ",\"removed\":", stdout);
    print_clean_json_array_runtime_roots(dry_run || ledger);
    fputs(",\"external_entries\":", stdout);
    print_clean_json_external_entries(include_external);
    puts("}");
}

static int remove_runtime_root_checked(const char *path)
{
    struct stat st;

    if (!path || !path[0])
        return 0;
    if (lstat(path, &st) != 0)
        return errno == ENOENT ? 0 : -1;
    if (!S_ISDIR(st.st_mode)) {
        fprintf(stderr, "clean: skipping non-directory runtime root candidate %s\n", path);
        return 0;
    }
    return bb_rm_rf(path);
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

static int clean_external_from_ledger(int quiet)
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

        if (!strcmp(path, "/root/.ssh/authorized_keys") &&
            !strcmp(op, "modify") && !strcmp(mode, "root-merge")) {
            if (remove_rshell_marked_block(path) != 0) {
                fprintf(stderr, "clean: failed to remove BusierBox rshell block from %s: %s\n", path, strerror(errno));
                failures = 1;
            } else if (!quiet) {
                printf("clean: removed BusierBox rshell block from %s\n", path);
            }
        } else if (!strcmp(path, "/root/.ssh/authorized_keys") &&
                   !strcmp(op, "write") && !strcmp(mode, "root-copy")) {
            if (unlink(path) != 0 && errno != ENOENT) {
                fprintf(stderr, "clean: failed to remove %s: %s\n", path, strerror(errno));
                failures = 1;
            } else if (!quiet) {
                printf("clean: removed external %s\n", path);
            }
        } else if (!strcmp(op, "backup") &&
                   !strncmp(path, "/root/.ssh/authorized_keys.busierbox.bak.", 41)) {
            if (unlink(path) != 0 && errno != ENOENT) {
                fprintf(stderr, "clean: failed to remove backup %s: %s\n", path, strerror(errno));
                failures = 1;
            } else if (!quiet) {
                printf("clean: removed external backup %s\n", path);
            }
        }
    }
    fclose(fp);
    return failures ? -1 : 0;
}

int bb_clean_external_from_ledger(void)
{
    return clean_external_from_ledger(0);
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
            print_clean_json(1, external, ledger, 0);
            return 0;
        }
        return print_clean_dry_run(external);
    }
    if (external && !apply) {
        fputs("clean: external cleanup requires --external --apply\n", stderr);
        return 2;
    }
    if (external && apply && clean_external_from_ledger(json) != 0)
        return 1;
    if (ledger) {
        bb_ledger_record("remove", BB_RUNTIME_ROOT, "runtime", "clean --ledger");
        if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
            BB_RUNTIME_FALLBACK_ROOT[0] &&
            strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT))
            bb_ledger_record("remove", BB_RUNTIME_FALLBACK_ROOT, "runtime", "clean --ledger fallback root");
    }
    if (remove_runtime_root_checked(BB_RUNTIME_ROOT) != 0) {
        fprintf(stderr, "clean: %s\n", strerror(errno));
        return 1;
    }
    if (ledger &&
        !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
        BB_RUNTIME_FALLBACK_ROOT[0] &&
        strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT) &&
        remove_runtime_root_checked(BB_RUNTIME_FALLBACK_ROOT) != 0) {
        fprintf(stderr, "clean: fallback root %s: %s\n", BB_RUNTIME_FALLBACK_ROOT, strerror(errno));
        return 1;
    }
    if (json) {
        print_clean_json(0, external, ledger, external && apply);
        return 0;
    }
    printf("clean: removed %s\n", BB_RUNTIME_ROOT);
    return 0;
}
