#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "applets.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_RECOVERY_BINARY_NAME
#define BB_RECOVERY_BINARY_NAME "busierbox_recovery"
#endif

struct recovery_method {
    const char *name;
    const char *path;
    const char *kind;
    const char *survives_reboot;
    const char *intrusiveness;
    const char *reversibility;
    const char *requires_external_write;
};

static const struct recovery_method recovery_methods[] = {
    {"openwrt-procd", "etc/init.d/busierbox_recovery", "OpenWrt/procd init script", "yes", "medium", "backup/remove script", "yes"},
    {"sysv-init", "etc/rc.d/S99busierbox_recovery", "SysV init.d/rcS hook", "yes", "medium", "backup/remove script", "yes"},
    {"systemd-unit", "etc/systemd/system/busierbox-recovery.service", "systemd unit", "yes", "medium", "backup/remove unit", "yes"},
    {"cron-reboot", "etc/crontabs/root", "cron @reboot line", "yes", "medium", "remove marked block", "yes"},
    {"at-job", "var/spool/at", "at job spool", "maybe", "high", "manual/provider-specific", "yes"},
    {"rc-local", "etc/rc.local", "rc.local marked block", "yes", "low", "remove marked block", "yes"},
    {"hotplug-iface", "etc/hotplug.d/iface/99-busierbox-recovery", "OpenWrt hotplug.d iface hook", "event", "medium", "remove script", "yes"},
    {"profile", "etc/profile.d/busierbox-recovery.sh", "shell profile hook", "login-only", "low", "remove script", "yes"},
};

struct recovery_storage {
    const char *path;
    const char *class_name;
    const char *survives_reboot;
    const char *notes;
};

static const struct recovery_storage recovery_storage_paths[] = {
    {"/overlay", "persistent", "yes", "OpenWrt writable overlay when present"},
    {"/root", "persistent", "yes", "root home on most installed systems"},
    {"/etc", "persistent", "yes", "configuration partition/rootfs overlay"},
    {"/usr/bin", "persistent", "yes", "binary location when rootfs is writable"},
    {"/tmp", "volatile", "no", "tmpfs on OpenWrt and most embedded Linux targets"},
    {"/var/tmp", "usually-volatile", "maybe", "may be tmpfs or persistent depending on target"},
    {"/dev/shm", "volatile", "no", "tmpfs shared memory"},
};

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "-h") || !strcmp(argv[1], "--help") || !strcmp(argv[1], "help"));
}

static int path_exists(const char *path)
{
    return access(path, F_OK) == 0;
}

static int mkdir_p(const char *path, mode_t mode)
{
    char tmp[PATH_MAX];
    char *p;

    if (!path || !*path)
        return -1;
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

static char *read_text_file(const char *path, size_t max)
{
    FILE *fp = fopen(path, "rb");
    char *buf;
    size_t n;

    if (!fp)
        return NULL;
    buf = (char *)malloc(max + 1);
    if (!buf) {
        fclose(fp);
        return NULL;
    }
    n = fread(buf, 1, max, fp);
    buf[n] = '\0';
    fclose(fp);
    return buf;
}

static const char *payload_base_name(const char *path)
{
    const char *slash;
    if (!path || !*path)
        return "persistence";
    slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

static const struct recovery_method *find_recovery_method(const char *name)
{
    size_t i;
    if (!strcmp(name, "procd"))
        name = "openwrt-procd";
    else if (!strcmp(name, "rcS"))
        name = "sysv-init";
    else if (!strcmp(name, "systemd"))
        name = "systemd-unit";
    else if (!strcmp(name, "cron"))
        name = "cron-reboot";
    else if (!strcmp(name, "rc.local"))
        name = "rc-local";
    else if (!strcmp(name, "hotplug"))
        name = "hotplug-iface";
    for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++)
        if (!strcmp(recovery_methods[i].name, name))
            return &recovery_methods[i];
    return NULL;
}

static void recovery_join(char *out, size_t outsz, const char *root, const char *rel)
{
    if (!root || !*root || !strcmp(root, "/"))
        snprintf(out, outsz, "/%s", rel);
    else
        snprintf(out, outsz, "%s/%s", root, rel);
}

static void recovery_bin_path(char *out, size_t outsz, const char *root, const char *name)
{
    char rel[PATH_MAX];
    snprintf(rel, sizeof(rel), "usr/bin/%s", name);
    recovery_join(out, outsz, root, rel);
}

static void recovery_script_path(char *out, size_t outsz, const char *root, const char *name)
{
    char rel[PATH_MAX];
    snprintf(rel, sizeof(rel), "usr/bin/%s.recovery.sh", name);
    recovery_join(out, outsz, root, rel);
}

static void fprint_shell_quoted(FILE *fp, const char *s)
{
    fputc('\'', fp);
    for (; s && *s; s++) {
        if (*s == '\'')
            fputs("'\\''", fp);
        else
            fputc(*s, fp);
    }
    fputc('\'', fp);
}

static int file_is_empty_or_missing(const char *path)
{
    struct stat st;
    if (stat(path, &st) != 0)
        return errno == ENOENT ? 1 : 0;
    return st.st_size == 0;
}

static int copy_self_to(const char *dst, const char *argv0)
{
    char src[PATH_MAX];
    FILE *in, *out;
    char buf[8192];
    size_t n;
    ssize_t len = readlink("/proc/self/exe", src, sizeof(src) - 1);

    if (len < 0) {
        if (!argv0 || !*argv0)
            return -1;
        snprintf(src, sizeof(src), "%s", argv0);
    } else {
        src[len] = '\0';
    }
    in = fopen(src, "rb");
    if (!in)
        return -1;
    out = fopen(dst, "wb");
    if (!out) {
        fclose(in);
        return -1;
    }
    while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
        if (fwrite(buf, 1, n, out) != n) {
            fclose(in);
            fclose(out);
            return -1;
        }
    }
    fclose(in);
    if (fclose(out) != 0)
        return -1;
    chmod(dst, 0755);
    return 0;
}

static int copy_file_path(const char *src, const char *dst)
{
    FILE *in, *out;
    char buf[8192];
    size_t n;
    in = fopen(src, "rb");
    if (!in)
        return -1;
    out = fopen(dst, "wb");
    if (!out) {
        fclose(in);
        return -1;
    }
    while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
        if (fwrite(buf, 1, n, out) != n) {
            fclose(in);
            fclose(out);
            return -1;
        }
    }
    fclose(in);
    return fclose(out);
}

static int backup_existing_file(const char *path, char *backup, size_t backupsz)
{
    struct stat st;
    if (stat(path, &st) != 0)
        return 0;
    snprintf(backup, backupsz, "%s.busierbox.bak.%ld", path, (long)time(NULL));
    if (copy_file_path(path, backup) != 0)
        return -1;
    chmod(backup, st.st_mode & 0777);
    return 1;
}

static int append_recovery_block(const char *path, const char *method, const char *name,
                                 const char *action, const char *command)
{
    FILE *fp = fopen(path, "a");
    if (!fp)
        return -1;
    if (file_is_empty_or_missing(path)) {
        if (!strcmp(method, "openwrt-procd"))
            fputs("#!/bin/sh /etc/rc.common\nSTART=99\n\n", fp);
        else if (!strcmp(method, "sysv-init") || !strcmp(method, "rc-local") || !strcmp(method, "hotplug-iface") || !strcmp(method, "profile"))
            fputs("#!/bin/sh\n", fp);
    }
    fprintf(fp, "\n# BEGIN BUSIERBOX RECOVERY %s\n", name);
    fprintf(fp, "# method=%s; action=%s; authorized lab persistence/recovery hook\n", method, action);
    fprintf(fp, "# generated_command=%s\n", command);
    if (!strcmp(method, "cron-reboot")) {
        fputs("@reboot /bin/sh -c ", fp);
        fprint_shell_quoted(fp, command);
        fputs(" >/dev/null 2>&1\n", fp);
    }
    else if (!strcmp(method, "systemd-unit")) {
        fputs("[Unit]\nDescription=BusierBox authorized lab recovery action\n[Service]\nType=oneshot\nExecStart=/bin/sh -c ", fp);
        fprint_shell_quoted(fp, command);
        fputs("\n[Install]\nWantedBy=multi-user.target\n", fp);
    } else if (!strcmp(method, "openwrt-procd")) {
        fputs("start_service() {\n    /bin/sh -c ", fp);
        fprint_shell_quoted(fp, command);
        fputs(" >/dev/null 2>&1 &\n}\n", fp);
    } else {
        fputs("/bin/sh -c ", fp);
        fprint_shell_quoted(fp, command);
        fputs(" >/dev/null 2>&1 || true\n", fp);
    }
    fprintf(fp, "# END BUSIERBOX RECOVERY %s\n", name);
    return fclose(fp);
}

static int remove_recovery_block(const char *path, const char *name)
{
    char begin[256], end[256], tmp[PATH_MAX];
    FILE *in, *out;
    char line[4096];
    int skipping = 0, removed = 0;

    snprintf(begin, sizeof(begin), "BEGIN BUSIERBOX RECOVERY %s", name);
    snprintf(end, sizeof(end), "END BUSIERBOX RECOVERY %s", name);
    snprintf(tmp, sizeof(tmp), "%s.tmp.%ld", path, (long)getpid());
    in = fopen(path, "r");
    if (!in)
        return errno == ENOENT ? 0 : -1;
    out = fopen(tmp, "w");
    if (!out) {
        fclose(in);
        return -1;
    }
    while (fgets(line, sizeof(line), in)) {
        if (strstr(line, begin)) {
            skipping = 1;
            removed = 1;
            continue;
        }
        if (skipping) {
            if (strstr(line, end))
                skipping = 0;
            continue;
        }
        fputs(line, out);
    }
    fclose(in);
    if (fclose(out) != 0)
        return -1;
    if (!removed) {
        unlink(tmp);
        return 0;
    }
    if (rename(tmp, path) != 0) {
        unlink(tmp);
        return -1;
    }
    return 0;
}

static int recovery_status_one(const char *root, const struct recovery_method *m, const char *name,
                               char *action, size_t actionsz,
                               char *command, size_t commandsz)
{
    char path[PATH_MAX];
    char marker[256];
    char *text;
    char *begin, *end, *line;
    recovery_join(path, sizeof(path), root, m->path);
    snprintf(marker, sizeof(marker), "BEGIN BUSIERBOX RECOVERY %s", name);
    text = read_text_file(path, 1024 * 1024);
    if (!text)
        return 0;
    begin = strstr(text, marker);
    if (begin) {
        end = strstr(begin, "END BUSIERBOX RECOVERY");
        if (action && actionsz)
            action[0] = '\0';
        if (command && commandsz)
            command[0] = '\0';
        line = begin;
        while (line && (!end || line < end)) {
            char *next = strchr(line, '\n');
            if (next)
                *next = '\0';
            if (action && actionsz) {
                char *p = strstr(line, "action=");
                if (p) {
                    char *q;
                    p += 7;
                    q = strchr(p, ';');
                    if (!q)
                        q = p + strcspn(p, " \t\r\n");
                    snprintf(action, actionsz, "%.*s", (int)(q - p), p);
                }
            }
            if (command && commandsz) {
                const char *p = strstr(line, "# generated_command=");
                if (p)
                    snprintf(command, commandsz, "%s", p + 20);
            }
            if (!next)
                break;
            *next = '\n';
            line = next + 1;
        }
        free(text);
        return 1;
    }
    free(text);
    return 0;
}

static void recovery_print_survey(int json, const char *root)
{
    size_t i;
    if (json) {
        fputs("{\"schema\":1,\"mode\":\"survey\",\"root\":", stdout);
        bb_json_string(stdout, root);
        fputs(",\"storage\":[", stdout);
        for (i = 0; i < sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]); i++) {
            char path[PATH_MAX];
            recovery_join(path, sizeof(path), root, recovery_storage_paths[i].path + 1);
            printf("%s{\"path\":", i ? "," : "");
            bb_json_string(stdout, path);
            fputs(",\"class\":", stdout); bb_json_string(stdout, recovery_storage_paths[i].class_name);
            fputs(",\"survives_reboot\":", stdout); bb_json_string(stdout, recovery_storage_paths[i].survives_reboot);
            printf(",\"present\":%s,\"writable\":%s", path_exists(path) ? "true" : "false", access(path, W_OK) == 0 ? "true" : "false");
            fputs(",\"notes\":", stdout); bb_json_string(stdout, recovery_storage_paths[i].notes);
            fputc('}', stdout);
        }
        fputs("],\"methods\":[", stdout);
        for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
            char path[PATH_MAX];
            recovery_join(path, sizeof(path), root, recovery_methods[i].path);
            printf("%s{\"name\":", i ? "," : "");
            bb_json_string(stdout, recovery_methods[i].name);
            fputs(",\"kind\":", stdout); bb_json_string(stdout, recovery_methods[i].kind);
            fputs(",\"path\":", stdout); bb_json_string(stdout, path);
            printf(",\"present\":%s", path_exists(path) ? "true" : "false");
            fputs(",\"survives_reboot\":", stdout); bb_json_string(stdout, recovery_methods[i].survives_reboot);
            fputs(",\"intrusiveness\":", stdout); bb_json_string(stdout, recovery_methods[i].intrusiveness);
            fputs(",\"reversibility\":", stdout); bb_json_string(stdout, recovery_methods[i].reversibility);
            fputs(",\"requires_external_write\":", stdout); bb_json_string(stdout, recovery_methods[i].requires_external_write);
            fputc('}', stdout);
        }
        puts("]}");
        return;
    }
    puts("Persistence survey");
    printf("  root: %s\n\n", root);
    puts("Safety policy");
    puts("  survey/plan: no target modification");
    puts("  install: requires --method and --apply");
    puts("  real-root writes: require --external --apply");
    puts("  intrusive operations: marked in the method table");
    puts("");
    puts("Storage candidates");
    printf("  %-18s %-17s %-7s %-8s %-8s %s\n",
           "Path", "Class", "Present", "Writable", "Survives", "Notes");
    for (i = 0; i < sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]); i++) {
        char path[PATH_MAX];
        recovery_join(path, sizeof(path), root, recovery_storage_paths[i].path + 1);
        printf("  %-18s %-17s %-7s %-8s %-8s %s\n",
               path, recovery_storage_paths[i].class_name, path_exists(path) ? "yes" : "no",
               access(path, W_OK) == 0 ? "yes" : "no", recovery_storage_paths[i].survives_reboot,
               recovery_storage_paths[i].notes);
    }
    puts("");
    puts("Persistence methods");
    printf("  %-15s %-44s %-7s %-9s %s\n",
           "Method", "Path", "Present", "Intrusive", "Reversible");
    for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
        char path[PATH_MAX];
        recovery_join(path, sizeof(path), root, recovery_methods[i].path);
        printf("  %-15s %-44s %-7s %-9s %s\n",
               recovery_methods[i].name, path, path_exists(path) ? "yes" : "no",
               recovery_methods[i].intrusiveness,
               recovery_methods[i].reversibility);
    }
}

static int applet_recovery_install(int argc, char **argv, int uninstall, const char *applet)
{
    const char *root = "/";
    const char *method = NULL;
    const char *action = "status-only";
    const char *name = BB_RECOVERY_BINARY_NAME;
    const char *script_file = NULL;
    int dry_run = 0, apply = 0, external = 0;
    const struct recovery_method *m;
    char hook[PATH_MAX], bin[PATH_MAX], script_dst[PATH_MAX], bindir[PATH_MAX], backup[PATH_MAX];
    char generated[PATH_MAX * 2];
    int backup_status;
    int i;

    generated[0] = '\0';
    for (i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--dry-run"))
            dry_run = 1;
        else if (!strcmp(argv[i], "--apply"))
            apply = 1;
        else if (!strcmp(argv[i], "--external"))
            external = 1;
        else if (!strcmp(argv[i], "--root") && i + 1 < argc)
            root = argv[++i];
        else if (!strcmp(argv[i], "--method") && i + 1 < argc)
            method = argv[++i];
        else if (!strcmp(argv[i], "--action") && i + 1 < argc)
            action = argv[++i];
        else if (!strcmp(argv[i], "--name") && i + 1 < argc)
            name = argv[++i];
        else if (!strcmp(argv[i], "--file") && i + 1 < argc)
            script_file = argv[++i];
        else if (!strcmp(argv[i], "--")) {
            int j;
            generated[0] = '\0';
            for (j = i + 1; j < argc; j++) {
                if (generated[0])
                    strncat(generated, " ", sizeof(generated) - strlen(generated) - 1);
                strncat(generated, argv[j], sizeof(generated) - strlen(generated) - 1);
            }
            break;
        }
        else {
            fprintf(stderr, "%s: unknown or incomplete option %s\n", applet, argv[i]);
            return 2;
        }
    }
    if (!method) {
        fprintf(stderr, "%s: install/uninstall requires --method\n", applet);
        return 2;
    }
    m = find_recovery_method(method);
    if (!m) {
        fprintf(stderr, "%s: unsupported method %s\n", applet, method);
        return 2;
    }
    if (strcmp(action, "rshell") && strcmp(action, "command") && strcmp(action, "script") && strcmp(action, "status-only")) {
        fprintf(stderr, "%s: unsupported recovery action %s\n", applet, action);
        return 2;
    }
    recovery_join(hook, sizeof(hook), root, m->path);
    recovery_bin_path(bin, sizeof(bin), root, name);
    recovery_script_path(script_dst, sizeof(script_dst), root, name);
    if (!strcmp(action, "rshell"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s rshell start", name);
    else if (!strcmp(action, "script")) {
        if (!script_file || !*script_file) {
            fprintf(stderr, "%s: recovery action script requires --file FILE\n", applet);
            return 2;
        }
        snprintf(generated, sizeof(generated), "/usr/bin/%s.recovery.sh", name);
    } else if (!strcmp(action, "command")) {
        if (!generated[0]) {
            fprintf(stderr, "%s: recovery action command requires -- COMMAND\n", applet);
            return 2;
        }
    } else {
        snprintf(generated, sizeof(generated), "/usr/bin/%s persistence status", name);
    }
    snprintf(bindir, sizeof(bindir), "%s", bin);
    {
        char *slash = strrchr(bindir, '/');
        if (slash)
            *slash = '\0';
    }
    if (!dry_run && !apply) {
        fprintf(stderr, "%s: modifying actions require --apply; use --dry-run to preview\n", applet);
        return 2;
    }
    if (!strcmp(root, "/") && apply && !external) {
        fprintf(stderr, "%s: real-root install/uninstall requires --external --apply\n", applet);
        return 2;
    }
    if (dry_run) {
        printf("Would %s persistence method=%s name=%s root=%s\n", uninstall ? "uninstall" : "install", method, name, root);
        printf("Action: %s\n", action);
        printf("Generated command: %s\n", generated);
        printf("Would %s binary: %s\n", uninstall ? "remove" : "copy self to", bin);
        if (!strcmp(action, "script"))
            printf("Would %s script: %s from %s\n", uninstall ? "remove" : "copy", script_dst, script_file);
        printf("Would %s hook: %s\n", uninstall ? "remove marked block/file" : "write marked hook", hook);
        if (!uninstall && path_exists(hook))
            printf("Would backup existing hook before modification: %s.busierbox.bak.<timestamp>\n", hook);
        return 0;
    }
    if (uninstall) {
        bb_ledger_record("remove", hook, !strcmp(root, "/") ? "external" : "recovery-fakeroot", "recovery uninstall hook");
        bb_ledger_record("remove", bin, !strcmp(root, "/") ? "external" : "recovery-fakeroot", "recovery uninstall binary");
        bb_ledger_record("remove", script_dst, !strcmp(root, "/") ? "external" : "recovery-fakeroot", "recovery uninstall script");
        remove_recovery_block(hook, name);
        unlink(bin);
        unlink(script_dst);
        printf("%s: uninstalled method=%s name=%s\n", applet, method, name);
        return 0;
    }
    if (mkdir_p(bindir, 0755) != 0) {
        fprintf(stderr, "%s: cannot create %s: %s\n", applet, bindir, strerror(errno));
        return 1;
    }
    if (copy_self_to(bin, argc > 0 ? argv[0] : NULL) != 0) {
        fprintf(stderr, "%s: cannot copy binary to %s: %s\n", applet, bin, strerror(errno));
        return 1;
    }
    if (!strcmp(action, "script")) {
        if (copy_file_path(script_file, script_dst) != 0) {
            fprintf(stderr, "%s: cannot copy script %s to %s: %s\n", applet, script_file, script_dst, strerror(errno));
            return 1;
        }
        chmod(script_dst, 0755);
    }
    {
        char hookdir[PATH_MAX];
        char *slash;
        snprintf(hookdir, sizeof(hookdir), "%s", hook);
        slash = strrchr(hookdir, '/');
        if (slash) {
            *slash = '\0';
            mkdir_p(hookdir, 0755);
        }
    }
    backup[0] = '\0';
    backup_status = backup_existing_file(hook, backup, sizeof(backup));
    if (backup_status < 0) {
        fprintf(stderr, "%s: cannot backup hook %s: %s\n", applet, hook, strerror(errno));
        return 1;
    }
    if (backup_status > 0)
        bb_ledger_record("backup", backup, !strcmp(root, "/") ? "external" : "recovery-fakeroot", hook);
    if (append_recovery_block(hook, method, name, action, generated) != 0) {
        fprintf(stderr, "%s: cannot write hook %s: %s\n", applet, hook, strerror(errno));
        return 1;
    }
    chmod(hook, 0755);
    {
        char detail[PATH_MAX * 2];
        snprintf(detail, sizeof(detail), "recovery binary method=%s action=%s name=%s", m->name, action, name);
        bb_ledger_record("write", bin, !strcmp(root, "/") ? "external" : "recovery-fakeroot", detail);
        if (!strcmp(action, "script")) {
            snprintf(detail, sizeof(detail), "recovery script method=%s action=%s name=%s source=%s", m->name, action, name, script_file);
            bb_ledger_record("write", script_dst, !strcmp(root, "/") ? "external" : "recovery-fakeroot", detail);
        }
        snprintf(detail, sizeof(detail), "recovery marked hook method=%s action=%s name=%s command=%s backup=%s", m->name, action, name, generated, backup_status > 0 ? backup : "none");
        bb_ledger_record("modify", hook, !strcmp(root, "/") ? "external" : "recovery-fakeroot", detail);
    }
    printf("%s: installed method=%s name=%s action=%s\n", applet, method, name, action);
    return 0;
}

int applet_recovery_main(int argc, char **argv)
{
    const char *cmd = argc > 1 ? argv[1] : "--help";
    const char *applet = payload_base_name(argc > 0 ? argv[0] : "persistence");
    const char *root = "/";
    const char *name = BB_RECOVERY_BINARY_NAME;
    int json = 0;
    int i;

    if (is_help(argc, argv) || !strcmp(cmd, "--help")) {
        if (!strcmp(applet, "recovery"))
            puts("recovery is a deprecated compatibility alias for persistence.");
        puts("usage: busierbox persistence --survey|--plan [--json] [--root ROOT]");
        puts("       busierbox persistence status [--json] [--root ROOT] [--name NAME]");
        puts("       busierbox persistence install --method METHOD [--action rshell|command|script|status-only] --dry-run|--apply [--external] [--root ROOT] [--name NAME] [--file SCRIPT] [-- COMMAND]");
        puts("       busierbox persistence uninstall --method METHOD --dry-run|--apply [--external] [--root ROOT] [--name NAME]");
        puts("Persistence is authorized lab persistence/recovery only. Survey and plan never modify the target.");
        puts("Install and uninstall require an explicit method plus --dry-run or --apply; real-root writes require --external --apply.");
        return 0;
    }
    if (!strcmp(cmd, "install"))
        return applet_recovery_install(argc, argv, 0, applet);
    if (!strcmp(cmd, "uninstall"))
        return applet_recovery_install(argc, argv, 1, applet);

    for (i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--root") && i + 1 < argc)
            root = argv[++i];
        else if (!strcmp(argv[i], "--name") && i + 1 < argc)
            name = argv[++i];
        else {
            fprintf(stderr, "%s: unknown or incomplete option %s\n", applet, argv[i]);
            return 2;
        }
    }
    if (!strcmp(cmd, "--survey") || !strcmp(cmd, "survey")) {
        recovery_print_survey(json, root);
        return 0;
    }
    if (!strcmp(cmd, "--plan") || !strcmp(cmd, "plan")) {
        recovery_print_survey(json, root);
        if (!json)
            puts("persistence_plan=choose one explicit method, run install --dry-run, then install --apply only when authorized");
        return 0;
    }
    if (!strcmp(cmd, "status")) {
        size_t j;
        int found = 0;
        if (json) {
            printf("{\"schema\":1,\"root\":");
            bb_json_string(stdout, root);
            fputs(",\"name\":", stdout);
            bb_json_string(stdout, name);
            fputs(",\"installations\":[", stdout);
        }
        for (j = 0; j < sizeof(recovery_methods) / sizeof(recovery_methods[0]); j++) {
            char action[64], generated[PATH_MAX * 2], path[PATH_MAX];
            if (recovery_status_one(root, &recovery_methods[j], name, action, sizeof(action), generated, sizeof(generated))) {
                recovery_join(path, sizeof(path), root, recovery_methods[j].path);
                if (json) {
                    printf("%s{\"method\":", found ? "," : "");
                    bb_json_string(stdout, recovery_methods[j].name);
                    fputs(",\"path\":", stdout); bb_json_string(stdout, path);
                    fputs(",\"action\":", stdout); bb_json_string(stdout, action[0] ? action : "unknown");
                    fputs(",\"generated_command\":", stdout); bb_json_string(stdout, generated);
                    fputc('}', stdout);
                } else {
                    printf("installed_method=%s\n", recovery_methods[j].name);
                    printf("installed_action=%s\n", action[0] ? action : "unknown");
                    if (generated[0])
                        printf("installed_command=%s\n", generated);
                }
                found = 1;
            }
        }
        if (json) {
            printf("],\"installed\":%s}\n", found ? "true" : "false");
        } else if (!found) {
            puts("installed=no");
        }
        return 0;
    }
    fprintf(stderr, "%s: unknown command %s\n", applet, cmd);
    return 2;
}
