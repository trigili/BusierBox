#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "applets.h"
#include "json_helpers.h"
#include "runtime_config.h"
#include "sha256.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BUSIERBOX_PAYLOAD_VERSION
#define BUSIERBOX_PAYLOAD_VERSION "dev"
#endif

#ifndef BUSIERBOX_ARTIFACT_TIER
#define BUSIERBOX_ARTIFACT_TIER "core"
#endif
#ifndef BUSIERBOX_BUILD_TIMESTAMP
#define BUSIERBOX_BUILD_TIMESTAMP "unknown"
#endif
#ifndef BUSIERBOX_GIT_COMMIT
#define BUSIERBOX_GIT_COMMIT "unknown"
#endif
#ifndef BB_TARGET_PRESET
#define BB_TARGET_PRESET "native"
#endif
#ifndef BB_TARGET_NAME
#define BB_TARGET_NAME "native"
#endif
#ifndef BB_TARGET_ARCH
#define BB_TARGET_ARCH "native"
#endif
#ifndef BB_TARGET_ENDIAN
#define BB_TARGET_ENDIAN "auto"
#endif
#ifndef BB_TARGET_CPU
#define BB_TARGET_CPU "host"
#endif
#ifndef BB_TARGET_ABI
#define BB_TARGET_ABI "default"
#endif
#ifndef BB_TARGET_LIBC
#define BB_TARGET_LIBC "host"
#endif
#ifndef BB_KERNEL_FLOOR
#define BB_KERNEL_FLOOR "host"
#endif
#ifndef BB_STATIC_POLICY
#define BB_STATIC_POLICY "static-preferred"
#endif
#ifndef BB_PAYLOAD_PRESET
#define BB_PAYLOAD_PRESET "default"
#endif
#ifndef BB_DOTFILES_ENABLE
#define BB_DOTFILES_ENABLE "yes"
#endif
#ifndef BB_DOTFILE_ZSH_MODE
#define BB_DOTFILE_ZSH_MODE "default"
#endif
#ifndef BB_DOTFILE_BASH_MODE
#define BB_DOTFILE_BASH_MODE "default"
#endif
#ifndef BB_DOTFILE_TMUX_MODE
#define BB_DOTFILE_TMUX_MODE "default"
#endif
#ifndef BB_DOTFILE_GDB_MODE
#define BB_DOTFILE_GDB_MODE "default"
#endif
#ifndef BB_DOTFILE_PROFILE_MODE
#define BB_DOTFILE_PROFILE_MODE "default"
#endif
#ifndef BB_USER_OVERLAY_ENABLE
#define BB_USER_OVERLAY_ENABLE "no"
#endif
#ifndef BB_USER_OVERLAY_ROOT
#define BB_USER_OVERLAY_ROOT "./overlay"
#endif
#ifndef BB_USER_OVERLAY_ALLOW_OVERRIDE
#define BB_USER_OVERLAY_ALLOW_OVERRIDE "no"
#endif
#ifndef BB_GDBSERVER_PROVIDER
#define BB_GDBSERVER_PROVIDER "auto"
#endif

#ifndef BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS
#define BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS 0
#endif
#ifndef BB_RUNTIME_MODE
#define BB_RUNTIME_MODE "extract"
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

#ifndef BB_FULL_ZERO_ARG_MODE
#define BB_FULL_ZERO_ARG_MODE "help"
#endif
#ifndef BB_ZERO_ARG_MODE
#define BB_ZERO_ARG_MODE BB_FULL_ZERO_ARG_MODE
#endif
#ifndef BB_ZERO_ARG_LOG_MODE
#define BB_ZERO_ARG_LOG_MODE "quiet"
#endif
#ifndef BB_ZERO_ARG_CUSTOM_COMMAND
#define BB_ZERO_ARG_CUSTOM_COMMAND ""
#endif
#ifndef BB_RSHELL_MODE
#define BB_RSHELL_MODE "ssh"
#endif
#ifndef BB_RSHELL_TRANSPORT
#define BB_RSHELL_TRANSPORT BB_RSHELL_MODE
#endif
#ifndef BB_RSHELL_AUTHKEYS_MODE
#define BB_RSHELL_AUTHKEYS_MODE "disabled"
#endif
#ifndef BB_RSHELL_RUN_MODE
#define BB_RSHELL_RUN_MODE "auto"
#endif
#ifndef BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING
#define BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING "no"
#endif
#ifndef BB_RSHELL_SOCAT_PORT
#define BB_RSHELL_SOCAT_PORT "22203"
#endif
#ifndef BB_RSHELL_SHELL_PROVIDER
#define BB_RSHELL_SHELL_PROVIDER "auto"
#endif
#ifndef BB_RSHELL_CUSTOM_SHELL
#define BB_RSHELL_CUSTOM_SHELL ""
#endif
#ifndef BB_RSHELL_RETRY_COUNT
#define BB_RSHELL_RETRY_COUNT "1"
#endif
#ifndef BB_RSHELL_RETRY_INTERVAL_SEC
#define BB_RSHELL_RETRY_INTERVAL_SEC "5"
#endif
#ifndef BB_RSHELL_RETRY_JITTER_PCT
#define BB_RSHELL_RETRY_JITTER_PCT "20"
#endif
#ifndef BB_RSHELL_RETRY_BACKOFF
#define BB_RSHELL_RETRY_BACKOFF "none"
#endif
#ifndef BB_RSHELL_RETRY_MAX_INTERVAL_SEC
#define BB_RSHELL_RETRY_MAX_INTERVAL_SEC "300"
#endif
#ifndef BB_RSHELL_ENCRYPTION
#define BB_RSHELL_ENCRYPTION "tls"
#endif
#ifndef BB_RSHELL_ALLOW_PLAINTEXT
#define BB_RSHELL_ALLOW_PLAINTEXT "no"
#endif
#ifndef BB_BUILTIN_TLS_ENABLE
#define BB_BUILTIN_TLS_ENABLE "no"
#endif
#ifndef BB_AUTORUN_GUARD_ENABLE
#define BB_AUTORUN_GUARD_ENABLE "yes"
#endif
#ifndef BB_AUTORUN_GUARD_PATH
#define BB_AUTORUN_GUARD_PATH "/tmp/busierbox-autorun"
#endif
#ifndef BB_AUTORUN_REENTRY_ACTION
#define BB_AUTORUN_REENTRY_ACTION "status"
#endif
#ifndef BB_AUTORUN_STALE_LOCK_POLICY
#define BB_AUTORUN_STALE_LOCK_POLICY "recover"
#endif
#ifndef BB_RECOVERY_BINARY_NAME
#define BB_RECOVERY_BINARY_NAME "busierbox_recovery"
#endif
#ifndef BB_OPERATOR_REMOTE_FORWARD_PORT
#define BB_OPERATOR_REMOTE_FORWARD_PORT "2200"
#endif
#ifndef BB_OPERATOR_SERVER_HOST
#define BB_OPERATOR_SERVER_HOST ""
#endif
#ifndef BB_OPERATOR_SERVER_USER
#define BB_OPERATOR_SERVER_USER "operator"
#endif
#ifndef BB_OPERATOR_SERVER_SSH_PORT
#define BB_OPERATOR_SERVER_SSH_PORT "22"
#endif
#ifndef BB_OPERATOR_TARGET_BIND_HOST
#define BB_OPERATOR_TARGET_BIND_HOST "127.0.0.1"
#endif
#ifndef BB_OPERATOR_TARGET_DROPBEAR_PORT
#define BB_OPERATOR_TARGET_DROPBEAR_PORT "2222"
#endif
#ifndef BB_OPERATOR_KNOWN_HOSTS_POLICY
#define BB_OPERATOR_KNOWN_HOSTS_POLICY "off"
#endif

#undef BB_RUNTIME_MODE
#undef BB_RUNTIME_ROOT
#undef BB_RUNTIME_ALLOW_FALLBACK_ROOT
#undef BB_RUNTIME_FALLBACK_ROOT
#undef BB_ZERO_ARG_MODE
#undef BB_ZERO_ARG_LOG_MODE
#undef BB_ZERO_ARG_CUSTOM_COMMAND
#undef BB_RSHELL_TRANSPORT
#undef BB_RSHELL_ENCRYPTION
#undef BB_RSHELL_ALLOW_PLAINTEXT
#undef BB_RSHELL_AUTHKEYS_MODE
#undef BB_RSHELL_RUN_MODE
#undef BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING
#undef BB_RSHELL_SOCAT_PORT
#undef BB_RSHELL_SHELL_PROVIDER
#undef BB_RSHELL_CUSTOM_SHELL
#undef BB_RSHELL_RETRY_COUNT
#undef BB_RSHELL_RETRY_INTERVAL_SEC
#undef BB_RSHELL_RETRY_JITTER_PCT
#undef BB_RSHELL_RETRY_BACKOFF
#undef BB_RSHELL_RETRY_MAX_INTERVAL_SEC
#undef BB_AUTORUN_GUARD_ENABLE
#undef BB_AUTORUN_GUARD_PATH
#undef BB_AUTORUN_REENTRY_ACTION
#undef BB_AUTORUN_STALE_LOCK_POLICY
#undef BB_OPERATOR_REMOTE_FORWARD_PORT
#undef BB_OPERATOR_SERVER_HOST
#undef BB_OPERATOR_SERVER_USER
#undef BB_OPERATOR_SERVER_SSH_PORT
#undef BB_OPERATOR_TARGET_BIND_HOST
#undef BB_OPERATOR_TARGET_DROPBEAR_PORT
#undef BB_OPERATOR_KNOWN_HOSTS_POLICY
#define BB_RUNTIME_MODE bb_config_get("BB_RUNTIME_MODE")
#define BB_RUNTIME_ROOT bb_config_get("BB_RUNTIME_ROOT")
#define BB_RUNTIME_ALLOW_FALLBACK_ROOT bb_config_get("BB_RUNTIME_ALLOW_FALLBACK_ROOT")
#define BB_RUNTIME_FALLBACK_ROOT bb_config_get("BB_RUNTIME_FALLBACK_ROOT")
#define BB_ZERO_ARG_MODE bb_config_get("BB_ZERO_ARG_MODE")
#define BB_ZERO_ARG_LOG_MODE bb_config_get("BB_ZERO_ARG_LOG_MODE")
#define BB_ZERO_ARG_CUSTOM_COMMAND bb_config_get("BB_ZERO_ARG_CUSTOM_COMMAND")
#define BB_RSHELL_TRANSPORT bb_config_get("BB_RSHELL_TRANSPORT")
#define BB_RSHELL_ENCRYPTION bb_config_get("BB_RSHELL_ENCRYPTION")
#define BB_RSHELL_ALLOW_PLAINTEXT bb_config_get("BB_RSHELL_ALLOW_PLAINTEXT")
#define BB_RSHELL_AUTHKEYS_MODE bb_config_get("BB_RSHELL_AUTHKEYS_MODE")
#define BB_RSHELL_RUN_MODE bb_config_get("BB_RSHELL_RUN_MODE")
#define BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING bb_config_get("BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING")
#define BB_RSHELL_SOCAT_PORT bb_config_get("BB_RSHELL_SOCAT_PORT")
#define BB_RSHELL_SHELL_PROVIDER bb_config_get("BB_RSHELL_SHELL_PROVIDER")
#define BB_RSHELL_CUSTOM_SHELL bb_config_get("BB_RSHELL_CUSTOM_SHELL")
#define BB_RSHELL_RETRY_COUNT bb_config_get("BB_RSHELL_RETRY_COUNT")
#define BB_RSHELL_RETRY_INTERVAL_SEC bb_config_get("BB_RSHELL_RETRY_INTERVAL_SEC")
#define BB_RSHELL_RETRY_JITTER_PCT bb_config_get("BB_RSHELL_RETRY_JITTER_PCT")
#define BB_RSHELL_RETRY_BACKOFF bb_config_get("BB_RSHELL_RETRY_BACKOFF")
#define BB_RSHELL_RETRY_MAX_INTERVAL_SEC bb_config_get("BB_RSHELL_RETRY_MAX_INTERVAL_SEC")
#define BB_AUTORUN_GUARD_ENABLE bb_config_get("BB_AUTORUN_GUARD_ENABLE")
#define BB_AUTORUN_GUARD_PATH bb_config_get("BB_AUTORUN_GUARD_PATH")
#define BB_AUTORUN_REENTRY_ACTION bb_config_get("BB_AUTORUN_REENTRY_ACTION")
#define BB_AUTORUN_STALE_LOCK_POLICY bb_config_get("BB_AUTORUN_STALE_LOCK_POLICY")
#define BB_OPERATOR_REMOTE_FORWARD_PORT bb_config_get("BB_OPERATOR_REMOTE_FORWARD_PORT")
#define BB_OPERATOR_SERVER_HOST bb_config_get("BB_OPERATOR_SERVER_HOST")
#define BB_OPERATOR_SERVER_USER bb_config_get("BB_OPERATOR_SERVER_USER")
#define BB_OPERATOR_SERVER_SSH_PORT bb_config_get("BB_OPERATOR_SERVER_SSH_PORT")
#define BB_OPERATOR_TARGET_BIND_HOST bb_config_get("BB_OPERATOR_TARGET_BIND_HOST")
#define BB_OPERATOR_TARGET_DROPBEAR_PORT bb_config_get("BB_OPERATOR_TARGET_DROPBEAR_PORT")
#define BB_OPERATOR_KNOWN_HOSTS_POLICY bb_config_get("BB_OPERATOR_KNOWN_HOSTS_POLICY")

#define BBX_TRAILER_SIZE 512
#define BBX_MAGIC "BBXPAYLOADv1"
#define BBX_PAYLOAD_ID_FILE ".busierbox-payload-id"
#define BBX_PAYLOAD_MODE_FILE ".busierbox-extract-mode"

static const char *busybox_tools[] = {
#include "bbx_busybox_applets.h"
    NULL
};

static const char *heavy_tools[] = {
#include "bbx_heavy_tools.h"
    NULL
};

static int compare_strings(const void *a, const void *b)
{
    return strcmp(*(const char **)a, *(const char **)b);
}

void bb_print_applet_list(FILE *out)
{
    int total = 0;
    int i, idx = 0;
    const char **all_tools;
    int col = 0;

    fprintf(out, "busierbox: %s artifact, launcher, survey, and payload runtime manager\n\n", BUSIERBOX_ARTIFACT_TIER);
    fprintf(out, "usage: busierbox <command> [args...]\n");
    fprintf(out, "       <command> [args...]   when invoked through a symlink\n\n");
    
    fprintf(out, "native applets:\n  ");
    for (i = 0; i < (int)bb_applet_count; i++)
        fprintf(out, "%s%s", i ? ", " : "", bb_applets[i].name);
    fprintf(out, "\n\n");
    
    if (BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS) {
        for (i = 0; busybox_tools[i]; i++) {
            total++;
        }
        for (i = 0; heavy_tools[i]; i++) {
            total++;
        }
    }
    
    if (total == 0) {
        fprintf(out, "no payload tools advertised by this artifact tier.\n");
        return;
    }

    all_tools = malloc(sizeof(char *) * (size_t)(total + 1));
    if (!all_tools) {
        fprintf(out, "error: out of memory listing applets\n");
        return;
    }
    
    if (BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS) {
        for (i = 0; busybox_tools[i]; i++) {
            all_tools[idx++] = busybox_tools[i];
        }
        for (i = 0; heavy_tools[i]; i++) {
            all_tools[idx++] = heavy_tools[i];
        }
    }
    all_tools[idx] = NULL;
    
    qsort(all_tools, (size_t)idx, sizeof(char *), compare_strings);
    
    fprintf(out, "staged payload tools:\n\t");
    for (i = 0; i < idx; i++) {
        int len = (int)strlen(all_tools[i]);
        if (col + len + 2 > 70) {
            fprintf(out, "\n\t");
            col = 0;
        }
        fprintf(out, "%s%s", all_tools[i], (i == idx - 1) ? "" : ", ");
        col += len + 2;
    }
    fprintf(out, "\n");
    
    free(all_tools);
}

int bb_payload_tool_supported(const char *name)
{
    int i;
    for (i = 0; busybox_tools[i]; i++) {
        if (strcmp(name, busybox_tools[i]) == 0)
            return 1;
    }
    for (i = 0; heavy_tools[i]; i++) {
        if (strcmp(name, heavy_tools[i]) == 0)
            return 1;
    }
    return 0;
}

static int operator_reverse_ssh_possible(void)
{
    return !strcmp(BB_RSHELL_TRANSPORT, "ssh");
}

static void print_autoexec_config(void)
{
    printf("zero_arg_mode=%s\n", BB_ZERO_ARG_MODE);
    printf("runtime_mode=%s\n", BB_RUNTIME_MODE);
    printf("runtime_root=%s\n", BB_RUNTIME_ROOT);
    printf("runtime_allow_fallback_root=%s\n", BB_RUNTIME_ALLOW_FALLBACK_ROOT);
    printf("runtime_fallback_root=%s\n", BB_RUNTIME_FALLBACK_ROOT);
    printf("zero_arg_log_mode=%s\n", BB_ZERO_ARG_LOG_MODE);
    printf("zero_arg_custom_command_set=%s\n", BB_ZERO_ARG_CUSTOM_COMMAND[0] ? "yes" : "no");
    printf("rshell_transport=%s\n", BB_RSHELL_TRANSPORT);
    printf("rshell_encryption=%s\n", BB_RSHELL_ENCRYPTION);
    printf("rshell_allow_plaintext=%s\n", BB_RSHELL_ALLOW_PLAINTEXT);
    printf("rshell_authkeys_mode=%s\n", BB_RSHELL_AUTHKEYS_MODE);
    printf("rshell_run_mode=%s\n", BB_RSHELL_RUN_MODE);
    printf("rshell_generate_hostkey_if_missing=%s\n", BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING);
    printf("rshell_socat_port=%s\n", BB_RSHELL_SOCAT_PORT);
    printf("rshell_shell_provider=%s\n", BB_RSHELL_SHELL_PROVIDER);
    printf("rshell_retry_count=%s\n", BB_RSHELL_RETRY_COUNT);
    printf("rshell_retry_interval_sec=%s\n", BB_RSHELL_RETRY_INTERVAL_SEC);
    printf("rshell_retry_jitter_pct=%s\n", BB_RSHELL_RETRY_JITTER_PCT);
    printf("rshell_retry_backoff=%s\n", BB_RSHELL_RETRY_BACKOFF);
    printf("rshell_retry_max_interval_sec=%s\n", BB_RSHELL_RETRY_MAX_INTERVAL_SEC);
    printf("builtin_tls_enabled=%s\n", BB_BUILTIN_TLS_ENABLE);
    printf("rshell_operator_host=%s\n", BB_OPERATOR_SERVER_HOST);
    printf("rshell_target_dropbear_port=%s\n", BB_OPERATOR_TARGET_DROPBEAR_PORT);
    printf("autorun_guard_enabled=%s\n", BB_AUTORUN_GUARD_ENABLE);
    printf("autorun_guard_path=%s\n", BB_AUTORUN_GUARD_PATH);
    printf("autorun_reentry_action=%s\n", BB_AUTORUN_REENTRY_ACTION);
    printf("autorun_stale_lock_policy=%s\n", BB_AUTORUN_STALE_LOCK_POLICY);
    printf("operator_reverse_ssh_possible=%s\n", operator_reverse_ssh_possible() ? "yes" : "no");
    printf("operator_reverse_ssh_catch_hint=ssh -p %s root@127.0.0.1\n", BB_OPERATOR_REMOTE_FORWARD_PORT);
}

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static const char *saved_argv0;

void bb_set_argv0(const char *argv0)
{
    saved_argv0 = argv0;
}

struct embedded_payload {
    int present;
    char exe[PATH_MAX];
    unsigned long long offset;
    unsigned long long size;
    char sha256[65];
    char version[128];
    char format[16];
    unsigned long long compressed_size;
};

#define json_string_payload bb_json_string

static int read_exe_dir(char *out, size_t outsz)
{
    ssize_t n = readlink("/proc/self/exe", out, outsz - 1);
    char *slash;
    if (n < 0)
        return -1;
    out[n] = '\0';
    slash = strrchr(out, '/');
    if (!slash)
        return -1;
    *slash = '\0';
    return 0;
}

static int find_self_path(char *out, size_t outsz)
{
    ssize_t n = readlink("/proc/self/exe", out, outsz - 1);
    if (n >= 0) {
        out[n] = '\0';
        return 0;
    }
    if (saved_argv0 && strchr(saved_argv0, '/')) {
        snprintf(out, outsz, "%s", saved_argv0);
        return 0;
    }
    if (saved_argv0) {
        const char *path = getenv("PATH");
        char *dup, *save = NULL, *p;
        if (!path)
            return -1;
        dup = strdup(path);
        if (!dup)
            return -1;
        for (p = strtok_r(dup, ":", &save); p; p = strtok_r(NULL, ":", &save)) {
            snprintf(out, outsz, "%s/%s", *p ? p : ".", saved_argv0);
            if (access(out, X_OK) == 0) {
                free(dup);
                return 0;
            }
        }
        free(dup);
    }
    return -1;
}

static int parse_trailer_text(char *text, struct embedded_payload *ep)
{
    char *line, *save = NULL;
    memset(ep, 0, sizeof(*ep));
    line = strtok_r(text, "\n", &save);
    if (!line || strcmp(line, BBX_MAGIC))
        return -1;
    while ((line = strtok_r(NULL, "\n", &save)) != NULL) {
        char *eq;
        if (!strcmp(line, "END"))
            break;
        eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq++ = '\0';
        if (!strcmp(line, "offset"))
            ep->offset = strtoull(eq, NULL, 10);
        else if (!strcmp(line, "size"))
            ep->size = strtoull(eq, NULL, 10);
        else if (!strcmp(line, "sha256"))
            snprintf(ep->sha256, sizeof(ep->sha256), "%s", eq);
        else if (!strcmp(line, "version"))
            snprintf(ep->version, sizeof(ep->version), "%s", eq);
        else if (!strcmp(line, "format"))
            snprintf(ep->format, sizeof(ep->format), "%s", eq);
        else if (!strcmp(line, "compressed_size"))
            ep->compressed_size = strtoull(eq, NULL, 10);
    }
    if (!ep->offset || !ep->size || strlen(ep->sha256) != 64 || !ep->version[0] || !ep->format[0])
        return -1;
    if (strcmp(ep->format, "tar") && strcmp(ep->format, "tgz"))
        return -1;
    ep->present = 1;
    return 0;
}

static int get_embedded_payload(struct embedded_payload *ep)
{
    FILE *fp;
    long fsize;
    char trailer[BBX_TRAILER_SIZE + 1];

    memset(ep, 0, sizeof(*ep));
    if (find_self_path(ep->exe, sizeof(ep->exe)) != 0)
        return -1;
    fp = fopen(ep->exe, "rb");
    if (!fp)
        return -1;
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return -1;
    }
    fsize = ftell(fp);
    fsize -= (long)bb_config_file_trailer_span(ep->exe);
    if (fsize < BBX_TRAILER_SIZE) {
        fclose(fp);
        return -1;
    }
    if (fseek(fp, fsize - BBX_TRAILER_SIZE, SEEK_SET) != 0 || fread(trailer, 1, BBX_TRAILER_SIZE, fp) != BBX_TRAILER_SIZE) {
        fclose(fp);
        return -1;
    }
    fclose(fp);
    trailer[BBX_TRAILER_SIZE] = '\0';
    /* parse_trailer_text does memset(ep, 0) internally; preserve the exe path
     * we already resolved above so verify_embedded_hash can open the binary. */
    {
        char saved_exe[PATH_MAX];
        snprintf(saved_exe, sizeof(saved_exe), "%s", ep->exe);
        if (parse_trailer_text(trailer, ep) != 0)
            return -1;
        snprintf(ep->exe, sizeof(ep->exe), "%s", saved_exe);
    }
    if (ep->offset + ep->size + BBX_TRAILER_SIZE > (unsigned long long)fsize)
        return -1;
    return 0;
}

static int payload_valid(const char *payload)
{
    char busybox[PATH_MAX], version[PATH_MAX], found[128];

    snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
    snprintf(version, sizeof(version), "%s/VERSION", payload);
    if (!bb_executable_file(busybox))
        return 0;
    if (bb_read_first_line(version, found, sizeof(found)) != 0)
        return 0;
    return strcmp(found, BUSIERBOX_PAYLOAD_VERSION) == 0;
}

static void payload_mode_path(char *out, size_t outsz, const char *payload)
{
    snprintf(out, outsz, "%s/%s", payload, BBX_PAYLOAD_MODE_FILE);
}

static int payload_is_full(const char *payload)
{
    char path[PATH_MAX], mode[32];
    payload_mode_path(path, sizeof(path), payload);
    if (bb_read_first_line(path, mode, sizeof(mode)) != 0)
        return 1; /* Legacy extractions were always full. */
    return !strcmp(mode, "full");
}

static const char *payload_extraction_mode(const char *payload, char *out, size_t outsz)
{
    char path[PATH_MAX], mode[32];
    payload_mode_path(path, sizeof(path), payload);
    if (bb_read_first_line(path, mode, sizeof(mode)) != 0) {
        snprintf(out, outsz, "full");
        return out; /* Legacy extractions predate the marker and were full. */
    }
    if (!strcmp(mode, "core") || !strcmp(mode, "full"))
        snprintf(out, outsz, "%s", mode);
    else
        snprintf(out, outsz, "unknown");
    return out;
}

static void write_payload_mode(const char *payload, const char *mode)
{
    char path[PATH_MAX];
    FILE *fp;
    payload_mode_path(path, sizeof(path), payload);
    fp = fopen(path, "w");
    if (!fp)
        return;
    fprintf(fp, "%s\n", mode);
    fclose(fp);
}

static int yes_str(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true"));
}

static int candidate_payload(char *out, size_t outsz)
{
    const char *env = getenv("BUSIERBOX_PAYLOAD_DIR");
    char exe_dir[PATH_MAX];
    char path[PATH_MAX];
    uid_t uid = getuid();
    int fallback_ok = yes_str(BB_RUNTIME_ALLOW_FALLBACK_ROOT) ||
                      yes_str(getenv("BUSIERBOX_ALLOW_FALLBACK_ROOT"));

    if (env && payload_valid(env)) {
        snprintf(out, outsz, "%s", env);
        return 0;
    }

    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(path, sizeof(path), "%s/payload", exe_dir);
        if (payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }

    if (BB_RUNTIME_ROOT[0]) {
        snprintf(path, sizeof(path), "%s/payload", BB_RUNTIME_ROOT);
        if (payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }

    /* Legacy /tmp, /var/tmp, /dev/shm locations — only checked when fallback
     * root is explicitly permitted.  In strict mode these are not considered. */
    if (fallback_ok) {
        snprintf(path, sizeof(path), "/tmp/busierbox-%ld/payload", (long)uid);
        if (payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        snprintf(path, sizeof(path), "/var/tmp/busierbox-%ld/payload", (long)uid);
        if (payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        snprintf(path, sizeof(path), "/dev/shm/busierbox-%ld/payload", (long)uid);
        if (payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        if (payload_valid("runtime/payload")) {
            snprintf(out, outsz, "%s", "runtime/payload");
            return 0;
        }
    }
    return -1;
}

static int archive_path(char *out, size_t outsz)
{
    char exe_dir[PATH_MAX], path[PATH_MAX];

    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(path, sizeof(path), "%s/payload.tar", exe_dir);
        if (bb_path_exists(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        snprintf(path, sizeof(path), "%s/payload.tar.gz", exe_dir);
        if (bb_path_exists(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }
    if (bb_path_exists("dist/payload.tar")) {
        snprintf(out, outsz, "%s", "dist/payload.tar");
        return 0;
    }
    if (bb_path_exists("dist/payload.tar.gz")) {
        snprintf(out, outsz, "%s", "dist/payload.tar.gz");
        return 0;
    }
    if (bb_path_exists("payload.tar")) {
        snprintf(out, outsz, "%s", "payload.tar");
        return 0;
    }
    if (bb_path_exists("payload.tar.gz")) {
        snprintf(out, outsz, "%s", "payload.tar.gz");
        return 0;
    }
    return -1;
}

static int verify_embedded_hash(const struct embedded_payload *ep)
{
    FILE *fp = fopen(ep->exe, "rb");
    bb_sha256_ctx ctx;
    uint8_t buf[8192], hash[32];
    char hex[65];
    unsigned long long left = ep->size;
    if (!fp)
        return -1;
    if (fseek(fp, (long)ep->offset, SEEK_SET) != 0) {
        fclose(fp);
        return -1;
    }
    bb_sha256_init(&ctx);
    while (left) {
        size_t n = left > sizeof(buf) ? sizeof(buf) : (size_t)left;
        if (fread(buf, 1, n, fp) != n) {
            fclose(fp);
            return -1;
        }
        bb_sha256_update(&ctx, buf, n);
        left -= n;
    }
    fclose(fp);
    bb_sha256_final(&ctx, hash);
    bb_sha256_hex(hash, hex);
    return strcmp(hex, ep->sha256) == 0 ? 0 : -1;
}

static void write_payload_id(const struct embedded_payload *ep, const char *payload_dir)
{
    char id_path[PATH_MAX];
    FILE *fp;
    snprintf(id_path, sizeof(id_path), "%s/%s", payload_dir, BBX_PAYLOAD_ID_FILE);
    fp = fopen(id_path, "w");
    if (!fp)
        return;
    fprintf(fp, "sha256=%s\n", ep->sha256);
    fprintf(fp, "size=%llu\n", ep->size);
    fprintf(fp, "version=%s\n", ep->version);
    fprintf(fp, "format=%s\n", ep->format);
    fclose(fp);
}

static int payload_id_matches(const struct embedded_payload *ep, const char *payload_dir)
{
    char id_path[PATH_MAX], line[256], key[64], val[192];
    char found_sha256[65] = "", found_size[32] = "", found_version[128] = "", found_format[16] = "";
    char expected_size[32];
    FILE *fp;

    if (!ep->present)
        return 1;
    snprintf(id_path, sizeof(id_path), "%s/%s", payload_dir, BBX_PAYLOAD_ID_FILE);
    fp = fopen(id_path, "r");
    if (!fp)
        return 0;
    while (fgets(line, sizeof(line), fp)) {
        char *eq;
        line[strcspn(line, "\r\n")] = '\0';
        eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq++ = '\0';
        strncpy(key, line, sizeof(key) - 1);
        key[sizeof(key) - 1] = '\0';
        strncpy(val, eq, sizeof(val) - 1);
        val[sizeof(val) - 1] = '\0';
        if (!strcmp(key, "sha256"))
            strncpy(found_sha256, val, sizeof(found_sha256) - 1);
        else if (!strcmp(key, "size"))
            strncpy(found_size, val, sizeof(found_size) - 1);
        else if (!strcmp(key, "version"))
            strncpy(found_version, val, sizeof(found_version) - 1);
        else if (!strcmp(key, "format"))
            strncpy(found_format, val, sizeof(found_format) - 1);
    }
    fclose(fp);
    snprintf(expected_size, sizeof(expected_size), "%llu", ep->size);
    return strcmp(found_sha256, ep->sha256) == 0 &&
           strcmp(found_size, expected_size) == 0 &&
           strcmp(found_version, ep->version) == 0 &&
           strcmp(found_format, ep->format) == 0;
}

static int extract_embedded_to_root(const struct embedded_payload *ep, const char *root, int core_only)
{
    char lock[PATH_MAX], tmp[PATH_MAX], final[PATH_MAX], extracted[PATH_MAX];
    FILE *fp;
    int rc;

    snprintf(lock, sizeof(lock), "%s/.extract.lock", root);
    snprintf(tmp, sizeof(tmp), "%s/payload.tmp.%ld", root, (long)getpid());
    snprintf(final, sizeof(final), "%s/payload", root);
    snprintf(extracted, sizeof(extracted), "%s/payload", tmp);

    if (!bb_enough_space_for_extract(ep->size, root)) {
        fprintf(stderr, "extract: not enough free space in %s\n", root);
        return -1;
    }
    int waits = 0;
    while (mkdir(lock, 0700) != 0) {
        if (errno != EEXIST)
            return -1;
        sleep(1);
        if (payload_valid(final) && (core_only || payload_is_full(final)))
            return 0;
        if (++waits > 30) {
            rmdir(lock);
            waits = 0;
        }
    }
    bb_rm_rf(tmp);
    if (bb_mkdir_p(tmp, 0700) != 0) {
        rmdir(lock);
        return -1;
    }

    if (verify_embedded_hash(ep) != 0) {
        bb_rm_rf(tmp);
        rmdir(lock);
        fprintf(stderr, "extract: embedded payload sha256 mismatch\n");
        return -1;
    }
    fp = fopen(ep->exe, "rb");
    if (!fp || fseek(fp, (long)ep->offset, SEEK_SET) != 0) {
        if (fp)
            fclose(fp);
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    rc = bb_extract_payload_stream(fp, ep->size, ep->format, tmp, core_only);
    fclose(fp);
    if (rc != 0) {
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    if (!payload_valid(extracted)) {
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    bb_rm_rf(final);
    if (rename(extracted, final) != 0) {
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    bb_rm_rf(tmp);
    rmdir(lock);
    write_payload_id(ep, final);
    write_payload_mode(final, core_only ? "core" : "full");
    bb_ledger_record("extract", root, "payload", core_only ? "embedded core payload extracted" : "embedded payload extracted");
    bb_ledger_record("write", final, "payload", "payload root");
    return 0;
}

static int extract_archive_file_to_root(const char *archive, const char *root, int core_only)
{
    struct embedded_payload ep;
    FILE *fp;
    struct stat st;
    int rc, is_tgz;

    memset(&ep, 0, sizeof(ep));
    snprintf(ep.exe, sizeof(ep.exe), "%s", archive);
    if (stat(archive, &st) != 0)
        return -1;
    ep.size = (unsigned long long)st.st_size;
    snprintf(ep.version, sizeof(ep.version), "%s", BUSIERBOX_PAYLOAD_VERSION);
    is_tgz = strstr(archive, ".gz") || strstr(archive, ".tgz");
    snprintf(ep.format, sizeof(ep.format), "%s", is_tgz ? "tgz" : "tar");

    if (!bb_enough_space_for_extract(ep.size, root))
        return -1;
    fp = fopen(archive, "rb");
    if (!fp)
        return -1;
    {
        char tmp[PATH_MAX], final[PATH_MAX], extracted[PATH_MAX];
        snprintf(tmp, sizeof(tmp), "%s/payload.devtmp.%ld", root, (long)getpid());
        snprintf(final, sizeof(final), "%s/payload", root);
        snprintf(extracted, sizeof(extracted), "%s/payload", tmp);
        bb_rm_rf(tmp);
        if (bb_mkdir_p(tmp, 0700) == 0)
            rc = bb_extract_payload_stream(fp, ep.size, ep.format, tmp, core_only);
        else
            rc = -1;
        if (rc == 0 && payload_valid(extracted)) {
            bb_rm_rf(final);
            rc = rename(extracted, final);
            if (rc == 0) {
                write_payload_mode(final, core_only ? "core" : "full");
                bb_ledger_record("extract", root, "payload", core_only ? "archive core payload extracted" : "archive payload extracted");
                bb_ledger_record("write", final, "payload", "payload root");
            }
        } else {
            rc = -1;
        }
        bb_rm_rf(tmp);
    }
    fclose(fp);
    return rc;
}

int bb_ensure_payload_mode(char *payload, size_t payloadsz, int require_full)
{
    char archive[PATH_MAX], root[PATH_MAX];
    struct embedded_payload ep;
    int have_ep = (get_embedded_payload(&ep) == 0);

    if (!strcmp(BB_RUNTIME_MODE, "core-only"))
        return -1;

    if (candidate_payload(payload, payloadsz) == 0) {
        if (have_ep && !payload_id_matches(&ep, payload)) {
            fprintf(stderr, "busierbox: extracted payload is from a different binary; re-extracting...\n");
            bb_rm_rf(payload);
            /* fall through to extract */
        } else if (require_full && !payload_is_full(payload)) {
            fprintf(stderr, "busierbox: upgrading core payload extraction to full payload...\n");
            bb_rm_rf(payload);
            /* fall through to extract */
        } else {
            return 0;
        }
    }
    if (bb_choose_extract_root(root, sizeof(root)) != 0)
        return -1;
    if (have_ep) {
        if (extract_embedded_to_root(&ep, root, !require_full) != 0)
            return -1;
    } else {
        if (archive_path(archive, sizeof(archive)) != 0)
            return -1;
        fprintf(stderr, "busierbox: warning: using dev-only external payload archive fallback: %s\n", archive);
        if (extract_archive_file_to_root(archive, root, !require_full) != 0)
            return -1;
    }
    bb_write_artifact_manifest_file(root);
    snprintf(payload, payloadsz, "%s/payload", root);
    return payload_valid(payload) && (!require_full || payload_is_full(payload)) ? 0 : -1;
}

static int ensure_payload(char *payload, size_t payloadsz)
{
    return bb_ensure_payload_mode(payload, payloadsz, 1);
}

int bb_ensure_payload_dir(char *payload, size_t payloadsz)
{
    return ensure_payload(payload, payloadsz);
}

int bb_candidate_payload_dir(char *payload, size_t payloadsz)
{
    return candidate_payload(payload, payloadsz);
}

int bb_embedded_payload_available(void)
{
    struct embedded_payload ep;
    return get_embedded_payload(&ep) == 0;
}

int bb_dev_payload_archive_available(void)
{
    char archive[PATH_MAX];
    return archive_path(archive, sizeof(archive)) == 0;
}

int bb_payload_tool_is_heavy(const char *name)
{
    int i;
    for (i = 0; heavy_tools[i]; i++)
        if (!strcmp(name, heavy_tools[i]))
            return 1;
    return 0;
}

int applet_list_main(int argc, char **argv)
{
    int i;
    if (is_help(argc, argv)) {
        puts("usage: busierbox list [--plain|--json]");
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "--plain")) {
        for (i = 0; i < (int)bb_applet_count; i++)
            printf("native %s\n", bb_applets[i].name);
        if (BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS) {
            for (i = 0; busybox_tools[i]; i++)
                printf("busybox %s\n", busybox_tools[i]);
            for (i = 0; heavy_tools[i]; i++)
                printf("tool %s\n", heavy_tools[i]);
        }
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "--json")) {
        printf("{\"artifact_tier\":\"%s\",\"native\":[", BUSIERBOX_ARTIFACT_TIER);
        for (i = 0; i < (int)bb_applet_count; i++)
            printf("%s\"%s\"", i ? "," : "", bb_applets[i].name);
        printf("],\"busybox_applets\":[");
        if (BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS) {
            for (i = 0; busybox_tools[i]; i++)
                printf("%s\"%s\"", i ? "," : "", busybox_tools[i]);
        }
        printf("],\"staged_tools\":[");
        if (BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS) {
            for (i = 0; heavy_tools[i]; i++)
                printf("%s\"%s\"", i ? "," : "", heavy_tools[i]);
        }
        printf("]}\n");
        return 0;
    }
    bb_print_applet_list(stdout);
    return 0;
}

int applet_extract_main(int argc, char **argv)
{
    char payload[PATH_MAX], archive[PATH_MAX], root[PATH_MAX];
    struct embedded_payload ep;
    int i, force = 0;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--force"))
            force = 1;
    }
    if (is_help(argc, argv)) {
        puts("usage: busierbox extract [--force]");
        puts("Extracts embedded payload into a writable runtime directory.");
        puts("  --force  Remove any existing extracted payload before extracting.");
        return 0;
    }
    if (force) {
        char old_payload[PATH_MAX];
        if (candidate_payload(old_payload, sizeof(old_payload)) == 0) {
            printf("extract: removing existing payload at %s\n", old_payload);
            bb_rm_rf(old_payload);
        }
    }
    if (!force && candidate_payload(payload, sizeof(payload)) == 0 && payload_is_full(payload)) {
        printf("payload: reuse %s\n", payload);
        return 0;
    }
    if (bb_choose_extract_root(root, sizeof(root)) != 0) {
        fprintf(stderr, "extract: no writable executable runtime directory found\n");
        return 1;
    }
    if (get_embedded_payload(&ep) == 0) {
        if (extract_embedded_to_root(&ep, root, 0) != 0) {
            fprintf(stderr, "extract: embedded payload extraction failed\n");
            return 1;
        }
    } else {
        if (archive_path(archive, sizeof(archive)) != 0) {
            fprintf(stderr, "extract: no embedded payload found and no dev fallback archive found\n");
            return 1;
        }
        fprintf(stderr, "extract: warning: using dev-only external payload archive fallback: %s\n", archive);
        if (extract_archive_file_to_root(archive, root, 0) != 0) {
            fprintf(stderr, "extract: archive extraction failed for %s\n", archive);
            return 1;
        }
    }
    snprintf(payload, sizeof(payload), "%s/payload", root);
    if (!payload_valid(payload)) {
        fprintf(stderr, "extract: extracted payload failed validation\n");
        return 1;
    }
    bb_write_artifact_manifest_file(root);
    printf("payload: extracted %s\n", payload);
    return 0;
}

static void doctor_rshell_server_listener(char *out, size_t outsz)
{
    if (!strcmp(BB_RSHELL_TRANSPORT, "ssh"))
        snprintf(out, outsz, "scripts/busierbox-server --transport ssh --ssh-port %s", BB_OPERATOR_SERVER_SSH_PORT);
    else if (!strcmp(BB_RSHELL_ENCRYPTION, "none"))
        snprintf(out, outsz, "scripts/busierbox-server --transport plain-shell --shell-port %s", BB_RSHELL_SOCAT_PORT);
    else
        snprintf(out, outsz, "scripts/busierbox-server --transport tls-shell --shell-port %s", BB_RSHELL_SOCAT_PORT);
}

static void doctor_rshell_connect_hint(char *out, size_t outsz)
{
    if (!strcmp(BB_RSHELL_TRANSPORT, "ssh"))
        snprintf(out, outsz, "ssh -p %s root@127.0.0.1", BB_OPERATOR_REMOTE_FORWARD_PORT);
    else if (!strcmp(BB_RSHELL_TRANSPORT, "none"))
        snprintf(out, outsz, "reverse access disabled");
    else
        snprintf(out, outsz, "shell stream is attached by scripts/busierbox-server");
}

static void print_doctor_manifest_summary_json(FILE *out, int payload_manifest_found, int applet_count)
{
    int heavy_count = 0;
    int i;
    for (i = 0; heavy_tools[i]; i++)
        heavy_count++;
    fprintf(out, ",\"manifest_summary\":{\"target_preset\":");
    json_string_payload(out, BB_TARGET_PRESET);
    fprintf(out, ",\"target_name\":");
    json_string_payload(out, BB_TARGET_NAME);
    fprintf(out, ",\"payload_preset\":");
    json_string_payload(out, BB_PAYLOAD_PRESET);
    fprintf(out, ",\"artifact_tier\":");
    json_string_payload(out, BUSIERBOX_ARTIFACT_TIER);
    fprintf(out, ",\"runtime_mode\":");
    json_string_payload(out, BB_RUNTIME_MODE);
    fprintf(out, ",\"zero_arg_mode\":");
    json_string_payload(out, BB_ZERO_ARG_MODE);
    fprintf(out, ",\"payload_manifest_found\":%s", payload_manifest_found ? "true" : "false");
    fprintf(out, ",\"busybox_applets_count\":%d,\"configured_heavy_tools_count\":%d}",
            applet_count, heavy_count);
}

static void print_doctor_rshell_readiness_json(FILE *out)
{
    char server[256], hint[256];
    int warning_count = 0;
    doctor_rshell_server_listener(server, sizeof(server));
    doctor_rshell_connect_hint(hint, sizeof(hint));

    fprintf(out, ",\"rshell_readiness\":{\"enabled\":%s", strcmp(BB_RSHELL_TRANSPORT, "none") ? "true" : "false");
    fprintf(out, ",\"transport\":");
    json_string_payload(out, BB_RSHELL_TRANSPORT);
    fprintf(out, ",\"encryption\":");
    json_string_payload(out, BB_RSHELL_ENCRYPTION);
    fprintf(out, ",\"run_mode\":");
    json_string_payload(out, BB_RSHELL_RUN_MODE);
    fprintf(out, ",\"zero_arg_autorun\":%s", !strcmp(BB_ZERO_ARG_MODE, "rshell") ? "true" : "false");
    fprintf(out, ",\"operator_host_set\":%s", BB_OPERATOR_SERVER_HOST[0] ? "true" : "false");
    fprintf(out, ",\"operator_host\":");
    json_string_payload(out, BB_OPERATOR_SERVER_HOST);
    fprintf(out, ",\"operator_shell_port\":");
    json_string_payload(out, BB_RSHELL_SOCAT_PORT);
    fprintf(out, ",\"operator_ssh_port\":");
    json_string_payload(out, BB_OPERATOR_SERVER_SSH_PORT);
    fprintf(out, ",\"remote_forward_port\":");
    json_string_payload(out, BB_OPERATOR_REMOTE_FORWARD_PORT);
    {
        char target_dropbear[256];
        snprintf(target_dropbear, sizeof(target_dropbear), "%s:%s", BB_OPERATOR_TARGET_BIND_HOST, BB_OPERATOR_TARGET_DROPBEAR_PORT);
        fprintf(out, ",\"target_dropbear\":");
        json_string_payload(out, target_dropbear);
    }
    fprintf(out, ",\"server_listener\":");
    json_string_payload(out, server);
    fprintf(out, ",\"connect_hint\":");
    json_string_payload(out, hint);
    fprintf(out, ",\"warnings\":[");
    if (!strcmp(BB_RSHELL_TRANSPORT, "none")) {
        json_string_payload(out, "reverse access disabled");
        warning_count++;
    }
    if (strcmp(BB_RSHELL_TRANSPORT, "none") && !BB_OPERATOR_SERVER_HOST[0]) {
        if (warning_count++)
            fputc(',', out);
        json_string_payload(out, "operator host is not configured");
    }
    if (strcmp(BB_RSHELL_TRANSPORT, "none") && strcmp(BB_ZERO_ARG_MODE, "rshell")) {
        if (warning_count++)
            fputc(',', out);
        json_string_payload(out, "zero-arg execution will not start reverse access");
    }
    if (strcmp(BB_RSHELL_TRANSPORT, "ssh") && !strcmp(BB_RSHELL_ENCRYPTION, "none")) {
        if (warning_count++)
            fputc(',', out);
        json_string_payload(out, "plaintext shell transport is insecure/debug-only");
    }
    fprintf(out, "]}");
}

static void print_doctor_cleanup_ledger_json(FILE *out)
{
    char path[PATH_MAX];
    bb_ledger_path(path, sizeof(path));
    fprintf(out, ",\"cleanup_ledger\":{\"path\":");
    json_string_payload(out, path);
    fprintf(out, ",\"present\":%s,\"entry_count\":%d}",
            bb_path_exists(path) ? "true" : "false",
            bb_ledger_entry_count(path));
}

static void print_doctor_payload_runtime_health_json(FILE *out, int have_payload, const char *payload)
{
    char busybox[PATH_MAX], symlink_count_path[PATH_MAX], symlink_count[32] = "";
    char terminfo[PATH_MAX], tmux_ti[PATH_MAX], zsh_path[PATH_MAX], bin_dir[PATH_MAX];

    fprintf(out, ",\"payload_runtime_health\":{\"present\":%s", have_payload ? "true" : "false");
    if (!have_payload || !payload || !payload[0]) {
        fprintf(out, "}");
        return;
    }
    snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
    snprintf(symlink_count_path, sizeof(symlink_count_path),
             "%s/share/busierbox/applet-symlink-count.txt", payload);
    bb_read_first_line(symlink_count_path, symlink_count, sizeof(symlink_count));
    snprintf(terminfo, sizeof(terminfo), "%s/share/terminfo", payload);
    snprintf(tmux_ti, sizeof(tmux_ti), "%s/share/terminfo/t/tmux", payload);
    snprintf(zsh_path, sizeof(zsh_path), "%s/bin/zsh", payload);
    snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);

    fprintf(out, ",\"dir\":");
    json_string_payload(out, payload);
    fprintf(out, ",\"busybox_executable\":%s", bb_executable_file(busybox) ? "true" : "false");
    fprintf(out, ",\"applet_symlink_count\":");
    if (symlink_count[0])
        json_string_payload(out, symlink_count);
    else
        fprintf(out, "null");
    fprintf(out, ",\"terminfo_present\":%s", bb_path_exists(terminfo) ? "true" : "false");
    fprintf(out, ",\"tmux_terminfo_present\":%s", bb_path_exists(tmux_ti) ? "true" : "false");
    fprintf(out, ",\"zsh_present\":%s", bb_executable_file(zsh_path) ? "true" : "false");
    fprintf(out, ",\"payload_bin_path_count\":%d", bb_path_entry_count(getenv("PATH"), bin_dir));
    fprintf(out, "}");
}

static void print_doctor_payload_inventory_json(FILE *out, const char *manifest)
{
    fprintf(out, ",\"payload_inventory\":{\"manifest_found\":%s", manifest ? "true" : "false");
    fprintf(out, ",\"requested_payload_tools\":");
    if (manifest)
        bb_json_write_raw_field_or(out, manifest, "requested_payload_tools", "[]");
    else
        bb_json_write_string_array(out, heavy_tools);
    fprintf(out, ",\"built_payload_tools\":");
    bb_json_write_raw_field_or(out, manifest, "built_payload_tools", "[]");
    fprintf(out, ",\"staged_payload_tools\":");
    bb_json_write_raw_field_or(out, manifest, "staged_payload_tools", "[]");
    fprintf(out, ",\"missing_payload_tools\":");
    bb_json_write_raw_field_or(out, manifest, "missing_payload_tools", "[]");
    fprintf(out, ",\"missing_payload_tool_reasons\":");
    bb_json_write_raw_field_or(out, manifest, "missing_payload_tool_reasons", "{}");
    fprintf(out, ",\"overlay_enabled\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_enabled", !strcmp(BB_USER_OVERLAY_ENABLE, "yes") ? "true" : "false");
    fprintf(out, ",\"overlay_root\":");
    if (manifest)
        bb_json_write_raw_field_or(out, manifest, "overlay_root", "null");
    else
        json_string_payload(out, BB_USER_OVERLAY_ROOT);
    fprintf(out, ",\"overlay_applied_paths\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_applied_paths", "[]");
    fprintf(out, ",\"overlay_files\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_files", "[]");
    fprintf(out, ",\"overlay_tools\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_tools", "[]");
    fprintf(out, ",\"overlay_warnings\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_warnings", "[]");
    fprintf(out, ",\"user_provided_tools\":");
    bb_json_write_raw_field_or(out, manifest, "user_provided_tools", "[]");
    fprintf(out, ",\"included_shared_libs\":");
    bb_json_write_raw_field_or(out, manifest, "included_shared_libs", "[]");
    fprintf(out, ",\"applet_symlink_skips\":");
    bb_json_write_raw_field_or(out, manifest, "applet_symlink_skips", "[]");
    fprintf(out, "}");
}

int applet_doctor_main(int argc, char **argv)
{
    struct embedded_payload ep;
    char payload[PATH_MAX], manifest_path[PATH_MAX], busybox[PATH_MAX];
    char root[PATH_MAX];
    char *manifest = NULL;
    int have_payload = 0;
    int applet_count = 0;
    int json = 0;
    int support_token = 0;
    int i;

    memset(&ep, 0, sizeof(ep));

    if (is_help(argc, argv)) {
        puts("usage: busierbox doctor [--json|--support-token]");
        puts("Reports embedded payload, extraction, BusyBox, and staged tool health.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--support-token"))
            support_token = 1;
        else {
            fprintf(stderr, "doctor: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json && support_token) {
        fputs("doctor: choose one of --json or --support-token\n", stderr);
        return 2;
    }
    if (support_token)
        return bb_print_support_token();

    if (get_embedded_payload(&ep) == 0) {
        if (json) {
            int hash_ok = verify_embedded_hash(&ep) == 0;
            have_payload = candidate_payload(payload, sizeof(payload)) == 0;
            if (have_payload) {
                snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
                snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
                if (bb_path_exists(manifest_path))
                    manifest = bb_read_text_file(manifest_path, 1024 * 1024);
            } else {
                root[0] = '\0';
                if (bb_extract_root_usable(BB_RUNTIME_ROOT))
                    snprintf(root, sizeof(root), "%s", BB_RUNTIME_ROOT);
                else if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
                         bb_extract_root_usable(BB_RUNTIME_FALLBACK_ROOT))
                    snprintf(root, sizeof(root), "%s", BB_RUNTIME_FALLBACK_ROOT);
            }
            if (manifest)
                applet_count = bb_json_array_count_field(manifest, "busybox_applets");
            else {
                for (i = 0; busybox_tools[i]; i++)
                    applet_count++;
            }
            printf("{\"schema\":1,\"embedded_payload\":{\"present\":true,\"format\":");
            json_string_payload(stdout, ep.format);
            printf(",\"size\":%llu,\"sha256\":", ep.size);
            json_string_payload(stdout, ep.sha256);
            printf(",\"version\":");
            json_string_payload(stdout, ep.version);
            printf(",\"hash_ok\":%s}", hash_ok ? "true" : "false");
            printf(",\"extracted_payload\":{\"present\":%s", have_payload ? "true" : "false");
            if (have_payload) {
                char mode[32];
                printf(",\"dir\":");
                json_string_payload(stdout, payload);
                printf(",\"extraction_mode\":");
                json_string_payload(stdout, payload_extraction_mode(payload, mode, sizeof(mode)));
                printf(",\"busybox_present\":%s", bb_executable_file(busybox) ? "true" : "false");
                printf(",\"manifest_found\":%s", bb_path_exists(manifest_path) ? "true" : "false");
                printf(",\"identity_match\":%s", payload_id_matches(&ep, payload) ? "true" : "false");
            } else if (root[0]) {
                printf(",\"candidate_extract_root\":");
                json_string_payload(stdout, root);
            }
            printf("}");
            printf(",\"extraction_runtime\":");
            bb_print_extraction_runtime_json(stdout, ep.size, json_string_payload);
            printf(",\"payload_manifest\":{\"found\":%s,\"busybox_applets_count\":%d",
                   manifest ? "true" : "false", applet_count);
            if (manifest) {
                printf(",\"overlay_enabled\":%s", !strcmp(bb_json_bool_value(manifest, "overlay_enabled"), "yes") ? "true" : "false");
            }
            printf("}");
            print_doctor_payload_inventory_json(stdout, manifest);
            print_doctor_payload_runtime_health_json(stdout, have_payload, payload);
            print_doctor_manifest_summary_json(stdout, manifest != NULL, applet_count);
            print_doctor_rshell_readiness_json(stdout);
            printf(",\"runtime_config\":");
            bb_config_print_runtime_summary_json(stdout, json_string_payload);
            print_doctor_cleanup_ledger_json(stdout);
            printf(",\"environment\":{\"path_has_duplicates\":%s,\"home_set\":%s,\"shell_set\":%s",
                   bb_path_has_duplicate_entries(getenv("PATH")) ? "true" : "false",
                   getenv("HOME") && *getenv("HOME") ? "true" : "false",
                   getenv("SHELL") && *getenv("SHELL") ? "true" : "false");
            if (have_payload) {
                char bin_dir[PATH_MAX];
                snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
                printf(",\"payload_bin_path_count\":%d", bb_path_entry_count(getenv("PATH"), bin_dir));
            }
            printf("},\"host\":{\"mem_available_kb\":%llu,\"devpts_available\":%s,\"ptrace_probe\":",
                   bb_mem_available_kb(), bb_path_exists("/dev/pts") ? "true" : "false");
            json_string_payload(stdout, bb_ptrace_probe_status());
            printf(",\"default_route_present\":%s}", bb_has_default_route() ? "true" : "false");
            printf(",\"artifact\":{\"tier\":");
            json_string_payload(stdout, BUSIERBOX_ARTIFACT_TIER);
            printf(",\"runtime_mode\":");
            json_string_payload(stdout, BB_RUNTIME_MODE);
            printf(",\"runtime_root\":");
            json_string_payload(stdout, BB_RUNTIME_ROOT);
            printf("}}\n");
            free(manifest);
            return 0;
        }
        printf("embedded_payload=yes\n");
        printf("embedded_format=%s\n", ep.format);
        printf("embedded_size=%llu\n", ep.size);
        printf("embedded_sha256=%s\n", ep.sha256);
        printf("embedded_version=%s\n", ep.version);
        printf("embedded_hash_ok=%s\n", verify_embedded_hash(&ep) == 0 ? "yes" : "no");
    } else {
        if (json) {
            have_payload = candidate_payload(payload, sizeof(payload)) == 0;
            if (have_payload) {
                snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
                snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
                if (bb_path_exists(manifest_path))
                    manifest = bb_read_text_file(manifest_path, 1024 * 1024);
            }
            if (manifest)
                applet_count = bb_json_array_count_field(manifest, "busybox_applets");
            else {
                for (i = 0; busybox_tools[i]; i++)
                    applet_count++;
            }
            printf("{\"schema\":1,\"embedded_payload\":{\"present\":false},\"extracted_payload\":{\"present\":%s",
                   have_payload ? "true" : "false");
            if (have_payload) {
                char mode[32];
                printf(",\"dir\":");
                json_string_payload(stdout, payload);
                printf(",\"extraction_mode\":");
                json_string_payload(stdout, payload_extraction_mode(payload, mode, sizeof(mode)));
                printf(",\"busybox_present\":%s", bb_executable_file(busybox) ? "true" : "false");
                printf(",\"manifest_found\":%s", bb_path_exists(manifest_path) ? "true" : "false");
            }
            printf("}");
            printf(",\"extraction_runtime\":");
            bb_print_extraction_runtime_json(stdout, 1, json_string_payload);
            printf(",\"payload_manifest\":{\"found\":%s,\"busybox_applets_count\":%d}",
                   manifest ? "true" : "false", applet_count);
            print_doctor_payload_inventory_json(stdout, manifest);
            print_doctor_payload_runtime_health_json(stdout, have_payload, payload);
            print_doctor_manifest_summary_json(stdout, manifest != NULL, applet_count);
            print_doctor_rshell_readiness_json(stdout);
            printf(",\"runtime_config\":");
            bb_config_print_runtime_summary_json(stdout, json_string_payload);
            print_doctor_cleanup_ledger_json(stdout);
            printf(",\"environment\":{\"path_has_duplicates\":%s,\"home_set\":%s,\"shell_set\":%s}",
                   bb_path_has_duplicate_entries(getenv("PATH")) ? "true" : "false",
                   getenv("HOME") && *getenv("HOME") ? "true" : "false",
                   getenv("SHELL") && *getenv("SHELL") ? "true" : "false");
            printf(",\"host\":{\"mem_available_kb\":%llu,\"devpts_available\":%s,\"ptrace_probe\":",
                   bb_mem_available_kb(), bb_path_exists("/dev/pts") ? "true" : "false");
            json_string_payload(stdout, bb_ptrace_probe_status());
            printf(",\"default_route_present\":%s}", bb_has_default_route() ? "true" : "false");
            printf(",\"artifact\":{\"tier\":");
            json_string_payload(stdout, BUSIERBOX_ARTIFACT_TIER);
            printf(",\"runtime_mode\":");
            json_string_payload(stdout, BB_RUNTIME_MODE);
            printf(",\"runtime_root\":");
            json_string_payload(stdout, BB_RUNTIME_ROOT);
            printf("}}\n");
            free(manifest);
            return 0;
        }
        puts("embedded_payload=no");
    }

    if (candidate_payload(payload, sizeof(payload)) == 0) {
        char mode[32];
        have_payload = 1;
        printf("extracted_payload=yes\n");
        printf("payload_dir=%s\n", payload);
        printf("payload_extraction_mode=%s\n", payload_extraction_mode(payload, mode, sizeof(mode)));
    } else {
        puts("extracted_payload=no");
        if (bb_choose_extract_root(root, sizeof(root)) == 0)
            printf("candidate_extract_root=%s\n", root);
    }

    if (have_payload) {
        snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
        printf("busybox_present=%s\n", bb_executable_file(busybox) ? "yes" : "no");
        snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
        printf("payload_manifest_found=%s\n", bb_path_exists(manifest_path) ? "yes" : "no");
        if (ep.present)
            printf("payload_identity_match=%s\n", payload_id_matches(&ep, payload) ? "yes" : "no (stale or different binary)");
        if (bb_path_exists(manifest_path))
            manifest = bb_read_text_file(manifest_path, 1024 * 1024);
    }

    if (manifest) {
        printf("busybox_applets=");
        applet_count = bb_json_array_summary(manifest, "busybox_applets", stdout);
        printf("\n");
        printf("busybox_applets_count=%d\n", applet_count);
        printf("staged_tools=");
        bb_json_array_summary(manifest, "staged_payload_tools", stdout);
        printf("\n");
        printf("missing_tools=");
        bb_json_array_summary(manifest, "missing_payload_tools", stdout);
        printf("\n");
        printf("missing_tool_reasons=");
        bb_json_object_summary(manifest, "missing_payload_tool_reasons", stdout);
        printf("\n");
        printf("overlay_enabled=%s\n", bb_json_bool_value(manifest, "overlay_enabled"));
        printf("overlay_tools=");
        bb_json_array_summary(manifest, "overlay_tools", stdout);
        printf("\n");
        printf("overlay_files=");
        bb_json_array_summary(manifest, "overlay_files", stdout);
        printf("\n");
        printf("overlay_warnings=");
        bb_json_array_summary(manifest, "overlay_warnings", stdout);
        printf("\n");
        free(manifest);
    } else {
        int i;
        for (i = 0; busybox_tools[i]; i++)
            applet_count++;
        printf("busybox_applets_count=%d\n", applet_count);
    }

    if (have_payload) {
        char symlink_count_path[PATH_MAX], symlink_count[32] = "unknown";
        char terminfo[PATH_MAX], tmux_ti[PATH_MAX], zsh_path[PATH_MAX];
        char bin_dir[PATH_MAX];
        snprintf(symlink_count_path, sizeof(symlink_count_path),
                 "%s/share/busierbox/applet-symlink-count.txt", payload);
        bb_read_first_line(symlink_count_path, symlink_count, sizeof(symlink_count));
        printf("applet_symlink_count=%s\n", symlink_count);
        snprintf(terminfo, sizeof(terminfo), "%s/share/terminfo", payload);
        snprintf(tmux_ti, sizeof(tmux_ti), "%s/share/terminfo/t/tmux", payload);
        printf("terminfo_present=%s\n", bb_path_exists(terminfo) ? "yes" : "no");
        printf("tmux_terminfo_present=%s\n", bb_path_exists(tmux_ti) ? "yes" : "no");
        snprintf(zsh_path, sizeof(zsh_path), "%s/bin/zsh", payload);
        printf("zsh_present=%s\n", bb_executable_file(zsh_path) ? "yes" : "no");
        snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
        printf("payload_bin_path_count=%d\n", bb_path_entry_count(getenv("PATH"), bin_dir));
    }
    printf("path_has_duplicates=%s\n", bb_path_has_duplicate_entries(getenv("PATH")) ? "yes" : "no");
    printf("home_set=%s\n", getenv("HOME") && *getenv("HOME") ? "yes" : "no");
    printf("shell_set=%s\n", getenv("SHELL") && *getenv("SHELL") ? "yes" : "no");

    if (bb_choose_extract_root(root, sizeof(root)) == 0) {
        printf("extract_root_writable_executable=yes\n");
        printf("extract_root=%s\n", root);
        printf("extract_root_noexec=%s\n", bb_dir_is_noexec(root) ? "yes" : "no");
        printf("extract_root_free_space_ok=%s\n", bb_enough_space_for_extract(ep.present ? ep.size : 1, root) ? "yes" : "no");
        printf("extract_root_available_bytes=%llu\n", bb_path_available_bytes(root));
    } else {
        puts("extract_root_writable_executable=no");
    }
    printf("mem_available_kb=%llu\n", bb_mem_available_kb());
    printf("devpts_available=%s\n", bb_path_exists("/dev/pts") ? "yes" : "no");
    printf("ptrace_probe=%s\n", bb_ptrace_probe_status());
    printf("default_route_present=%s\n", bb_has_default_route() ? "yes" : "no");
    if (!bb_path_exists("/dev/pts"))
        puts("recommendation=mount devpts for tmux/dropbear interactive sessions");
    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    print_autoexec_config();
    if (have_payload) {
        char ti[PATH_MAX];
        snprintf(ti, sizeof(ti), "%s/share/terminfo", payload);
        if (!bb_path_exists(ti))
            puts("recommendation=stage terminfo when using tmux/screen/htop");
    }
    return 0;
}

int applet_config_info_main(int argc, char **argv)
{
    char payload[PATH_MAX], hash_path[PATH_MAX], hash[256] = "unknown";
    char manifest[PATH_MAX];
    char exe_dir[PATH_MAX];
    struct embedded_payload ep;
    int have_embedded;
    int have_payload;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox config-info");
        return 0;
    }
    puts("build_target=native");
#ifdef __GLIBC__
    puts("libc=glibc");
#else
    puts("libc=unknown");
#endif
    puts("core_static_status=see build output");
    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    print_autoexec_config();
    printf("trailer_override_present=%s\n", bb_config_trailer_present() ? "yes" : "no");
    printf("trailer_override_valid=%s\n", bb_config_trailer_valid() ? "yes" : "no");
    printf("trailer_override_encoding=%s\n", bb_config_trailer_encoding());
    printf("trailer_override_count=%d\n", bb_config_trailer_override_count());
    printf("trailer_override_status=%s\n", bb_config_trailer_error());
    printf("effective_config_source=%s\n", bb_config_effective_source());
    printf("compiled_zero_arg_mode=%s\n", bb_config_compiled("BB_ZERO_ARG_MODE"));
    printf("compiled_rshell_transport=%s\n", bb_config_compiled("BB_RSHELL_TRANSPORT"));
    printf("compiled_rshell_operator_host=%s\n", bb_config_compiled("BB_OPERATOR_SERVER_HOST"));
    printf("effective_zero_arg_mode=%s\n", BB_ZERO_ARG_MODE);
    printf("effective_rshell_transport=%s\n", BB_RSHELL_TRANSPORT);
    printf("effective_rshell_operator_host=%s\n", BB_OPERATOR_SERVER_HOST);
    have_embedded = get_embedded_payload(&ep) == 0;
    have_payload = candidate_payload(payload, sizeof(payload)) == 0;
    printf("embedded_payload=%s\n", have_embedded ? "yes" : "no");
    printf("payload_version=%s\n", BUSIERBOX_PAYLOAD_VERSION);
    printf("gdbserver_provider=%s\n", BB_GDBSERVER_PROVIDER);
    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(hash_path, sizeof(hash_path), "%s/payload.tar.gz.sha256", exe_dir);
        bb_read_first_line(hash_path, hash, sizeof(hash));
    }
    printf("payload_archive_hash=%s\n", hash);
    printf("native_applets=");
    for (i = 0; i < (int)bb_applet_count; i++)
        printf("%s%s", i ? " " : "", bb_applets[i].name);
    printf("\n");
    printf("payload_present=%s\n", have_payload ? payload : "no");
    if (have_payload) {
        char mode[32];
        printf("payload_extraction_mode=%s\n", payload_extraction_mode(payload, mode, sizeof(mode)));
    }
    printf("payload_tools_present=");
    if (BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS) {
        for (i = 0; heavy_tools[i]; i++)
            printf("%s%s:%s", i ? "," : "", heavy_tools[i], have_payload ? "yes" : "available-after-extract");
    } else {
        printf("none");
    }
    printf("\n");
    if (have_payload) {
        char busybox[PATH_MAX];
        snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
        printf("busybox_present=%s\n", bb_executable_file(busybox) ? "yes" : "no");
        snprintf(manifest, sizeof(manifest), "%s/manifest.json", payload);
        if (bb_path_exists(manifest)) {
            FILE *fp = fopen(manifest, "r");
            char line[256];
            printf("payload_manifest=%s\n", manifest);
            puts("payload_manifest_summary_begin");
            if (fp) {
                while (fgets(line, sizeof(line), fp))
                    fputs(line, stdout);
                fclose(fp);
            }
            puts("payload_manifest_summary_end");
        }
    }
    puts("busybox_dispatch=yes");
    return 0;
}
