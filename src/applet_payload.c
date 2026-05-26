#define _POSIX_C_SOURCE 200809L

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "applets.h"
#include "json_helpers.h"
#include "runtime_config.h"
#include "sha256.h"
#include "../third_party/miniz/miniz.h"

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

#ifdef BUSIERBOX_NO_OPEN_MEMSTREAM
#error "BusierBox manifest/config export requires open_memstream on this build; add a growable-buffer fallback before using this libc."
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

static int bb_applet_supported(const char *name)
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

int bb_rm_rf(const char *path);
static char *read_text_file(const char *path, size_t max_bytes);
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

static int mkdir_p(const char *path, mode_t mode)
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

#define json_string_payload bb_json_string

static int path_exists(const char *path)
{
    return access(path, F_OK) == 0;
}

static void write_artifact_manifest_file(const char *root);

static int executable_file(const char *path)
{
    return access(path, X_OK) == 0;
}

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

static int read_first_line(const char *path, char *out, size_t outsz)
{
    FILE *fp = fopen(path, "r");
    if (!fp)
        return -1;
    if (!fgets(out, (int)outsz, fp)) {
        fclose(fp);
        return -1;
    }
    out[strcspn(out, "\r\n")] = '\0';
    fclose(fp);
    return 0;
}

static int payload_valid(const char *payload)
{
    char busybox[PATH_MAX], version[PATH_MAX], found[128];

    snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
    snprintf(version, sizeof(version), "%s/VERSION", payload);
    if (!executable_file(busybox))
        return 0;
    if (read_first_line(version, found, sizeof(found)) != 0)
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
    if (read_first_line(path, mode, sizeof(mode)) != 0)
        return 1; /* Legacy extractions were always full. */
    return !strcmp(mode, "full");
}

static const char *payload_extraction_mode(const char *payload, char *out, size_t outsz)
{
    char path[PATH_MAX], mode[32];
    payload_mode_path(path, sizeof(path), payload);
    if (read_first_line(path, mode, sizeof(mode)) != 0) {
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
        if (path_exists(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        snprintf(path, sizeof(path), "%s/payload.tar.gz", exe_dir);
        if (path_exists(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }
    if (path_exists("dist/payload.tar")) {
        snprintf(out, outsz, "%s", "dist/payload.tar");
        return 0;
    }
    if (path_exists("dist/payload.tar.gz")) {
        snprintf(out, outsz, "%s", "dist/payload.tar.gz");
        return 0;
    }
    if (path_exists("payload.tar")) {
        snprintf(out, outsz, "%s", "payload.tar");
        return 0;
    }
    if (path_exists("payload.tar.gz")) {
        snprintf(out, outsz, "%s", "payload.tar.gz");
        return 0;
    }
    return -1;
}

static int dir_is_noexec(const char *path)
{
    FILE *fp = fopen("/proc/mounts", "r");
    char line[512], best[PATH_MAX] = "", best_opts[256] = "";
    size_t best_len = 0;

    if (!fp)
        return 0;
    while (fgets(line, sizeof(line), fp)) {
        char src[160], dst[PATH_MAX], type[64], opts[256];
        size_t len;
        (void)src;
        (void)type;
        if (sscanf(line, "%159s %4095s %63s %255s", src, dst, type, opts) != 4)
            continue;
        len = strlen(dst);
        if ((!strcmp(dst, "/") || !strncmp(path, dst, len)) && len >= best_len) {
            snprintf(best, sizeof(best), "%s", dst);
            snprintf(best_opts, sizeof(best_opts), "%s", opts);
            best_len = len;
        }
    }
    fclose(fp);
    (void)best;
    return strstr(best_opts, "noexec") != NULL;
}

static int choose_extract_root(char *out, size_t outsz)
{
    char path[PATH_MAX];
    const char *roots[4];
    int i, nroots = 0;

    if (BB_RUNTIME_ROOT[0])
        roots[nroots++] = BB_RUNTIME_ROOT;
    if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") && BB_RUNTIME_FALLBACK_ROOT[0])
        roots[nroots++] = BB_RUNTIME_FALLBACK_ROOT;

    for (i = 0; i < nroots; i++) {
        if (!roots[i] || !roots[i][0])
            continue;
        snprintf(path, sizeof(path), "%s", roots[i]);
        if (mkdir_p(path, 0700) != 0)
            continue;
        bb_ledger_record("mkdir", path, "runtime", "runtime root");
        if (access(path, W_OK | X_OK) != 0)
            continue;
        if (dir_is_noexec(path))
            continue;
        snprintf(out, outsz, "%s", path);
        return 0;
    }
    return -1;
}

static int enough_space(const char *archive, const char *root)
{
    struct stat st;
    struct statvfs v;
    unsigned long long free_bytes, need_bytes;

    if (stat(archive, &st) != 0 || statvfs(root, &v) != 0)
        return 1;
    free_bytes = (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize;
    need_bytes = (unsigned long long)st.st_size * 4ULL;
    if (need_bytes < 8ULL * 1024ULL * 1024ULL)
        need_bytes = 8ULL * 1024ULL * 1024ULL;
    return free_bytes > need_bytes;
}

static unsigned long long extract_required_bytes(unsigned long long payload_size)
{
    unsigned long long need = payload_size * 4ULL;
    if (need < 8ULL * 1024ULL * 1024ULL)
        need = 8ULL * 1024ULL * 1024ULL;
    return need;
}

static int enough_space_size(unsigned long long size, const char *root)
{
    struct statvfs v;
    unsigned long long free_bytes;
    if (statvfs(root, &v) != 0)
        return 1;
    free_bytes = (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize;
    return free_bytes > extract_required_bytes(size);
}

struct payload_stream {
    FILE *fp;
    unsigned long long remaining;
    int tgz;
    int eof;
    mz_stream z;
    unsigned char in[8192];
    unsigned char out[8192];
    size_t out_pos;
    size_t out_len;
};

static int stream_init_tar(struct payload_stream *s, FILE *fp, unsigned long long size)
{
    memset(s, 0, sizeof(*s));
    s->fp = fp;
    s->remaining = size;
    return 0;
}

static int gzip_skip_header(FILE *fp, unsigned long long *remaining)
{
    unsigned char h[10];
    int flg, c;
    if (*remaining < 10 || fread(h, 1, 10, fp) != 10)
        return -1;
    *remaining -= 10;
    if (h[0] != 0x1f || h[1] != 0x8b || h[2] != 8)
        return -1;
    flg = h[3];
    if (flg & 0x04) {
        unsigned char x[2];
        unsigned int len;
        if (*remaining < 2 || fread(x, 1, 2, fp) != 2)
            return -1;
        *remaining -= 2;
        len = (unsigned int)x[0] | ((unsigned int)x[1] << 8);
        if (*remaining < len || fseek(fp, (long)len, SEEK_CUR) != 0)
            return -1;
        *remaining -= len;
    }
    if (flg & 0x08) {
        do {
            if (*remaining < 1 || (c = fgetc(fp)) == EOF)
                return -1;
            (*remaining)--;
        } while (c != 0);
    }
    if (flg & 0x10) {
        do {
            if (*remaining < 1 || (c = fgetc(fp)) == EOF)
                return -1;
            (*remaining)--;
        } while (c != 0);
    }
    if (flg & 0x02) {
        if (*remaining < 2 || fseek(fp, 2, SEEK_CUR) != 0)
            return -1;
        *remaining -= 2;
    }
    if (flg & 0xe0)
        return -1;
    return 0;
}

static int stream_init_tgz(struct payload_stream *s, FILE *fp, unsigned long long size)
{
    memset(s, 0, sizeof(*s));
    s->fp = fp;
    s->remaining = size;
    s->tgz = 1;
    if (gzip_skip_header(fp, &s->remaining) != 0)
        return -1;
    memset(&s->z, 0, sizeof(s->z));
    if (mz_inflateInit2(&s->z, -MZ_DEFAULT_WINDOW_BITS) != MZ_OK)
        return -1;
    return 0;
}

static void stream_end(struct payload_stream *s)
{
    if (s->tgz)
        mz_inflateEnd(&s->z);
}

static int stream_read(struct payload_stream *s, void *buf, size_t len)
{
    unsigned char *dst = buf;
    size_t done = 0;
    while (done < len) {
        if (!s->tgz) {
            size_t want = len - done;
            if (s->remaining < want)
                return -1;
            if (fread(dst + done, 1, want, s->fp) != want)
                return -1;
            s->remaining -= want;
            return 0;
        }
        if (s->out_pos < s->out_len) {
            size_t n = s->out_len - s->out_pos;
            if (n > len - done)
                n = len - done;
            memcpy(dst + done, s->out + s->out_pos, n);
            s->out_pos += n;
            done += n;
            continue;
        }
        s->out_pos = s->out_len = 0;
        if (s->z.avail_in == 0 && s->remaining > 8) {
            size_t want = sizeof(s->in);
            if (want > s->remaining - 8)
                want = (size_t)(s->remaining - 8);
            if (fread(s->in, 1, want, s->fp) != want)
                return -1;
            s->remaining -= want;
            s->z.next_in = s->in;
            s->z.avail_in = (mz_uint)want;
        }
        s->z.next_out = s->out;
        s->z.avail_out = sizeof(s->out);
        {
            int rc = mz_inflate(&s->z, MZ_NO_FLUSH);
            s->out_len = sizeof(s->out) - s->z.avail_out;
            if (rc == MZ_STREAM_END)
                s->eof = 1;
            else if (rc != MZ_OK)
                return -1;
            if (s->out_len == 0 && s->eof)
                return -1;
        }
    }
    return 0;
}

static int octal(const char *p, size_t n, unsigned long long *out)
{
    unsigned long long v = 0;
    size_t i;
    for (i = 0; i < n; i++) {
        if (p[i] == '\0' || p[i] == ' ')
            break;
        if (p[i] < '0' || p[i] > '7')
            return -1;
        v = (v << 3) + (unsigned)(p[i] - '0');
    }
    *out = v;
    return 0;
}

static int safe_member_path(const char *name)
{
    if (!name[0] || name[0] == '/' || strstr(name, "/../") || !strcmp(name, "..") || !strncmp(name, "../", 3))
        return 0;
    return 1;
}

static int core_payload_member(const char *name)
{
    return !strcmp(name, "payload/bin/busybox") ||
           !strcmp(name, "payload/VERSION") ||
           !strcmp(name, "payload/manifest.json") ||
           !strcmp(name, "payload/busybox-applets.txt") ||
           !strcmp(name, "payload/staged-tools.txt") ||
           !strcmp(name, "payload/built-tools.txt") ||
           !strcmp(name, "payload/requested-tools.txt") ||
           !strcmp(name, "payload/missing-tools.txt") ||
           !strcmp(name, "payload/share/busierbox/missing-tools.txt") ||
           !strcmp(name, "payload/share/busierbox/applet-symlink-count.txt");
}

static int stream_skip(struct payload_stream *s, unsigned long long n)
{
    unsigned char buf[8192];
    while (n) {
        size_t chunk = n > sizeof(buf) ? sizeof(buf) : (size_t)n;
        if (stream_read(s, buf, chunk) != 0)
            return -1;
        n -= chunk;
    }
    return 0;
}

static int tar_extract_stream(struct payload_stream *s, const char *root, int core_only)
{
    unsigned char hdr[512], buf[8192];
    int zero_blocks = 0;
    while (1) {
        char name[256], full[PATH_MAX], linkname[256], type;
        unsigned long long size = 0, mode = 0, pad, left, stored64 = 0;
        unsigned int i, sum = 0, stored = 0;
        int fd;

        if (stream_read(s, hdr, 512) != 0)
            return -1;
        for (i = 0; i < 512; i++)
            if (hdr[i])
                break;
        if (i == 512) {
            if (++zero_blocks == 2)
                return 0;
            continue;
        }
        zero_blocks = 0;
        if (octal((char *)hdr + 148, 8, &stored64) != 0)
            return -1;
        stored = (unsigned int)stored64;
        for (i = 0; i < 512; i++)
            sum += (i >= 148 && i < 156) ? ' ' : hdr[i];
        if (stored != sum)
            return -1;
        snprintf(name, sizeof(name), "%.*s", 100, (char *)hdr);
        if (hdr[345])
            snprintf(name, sizeof(name), "%.*s/%.*s", 155, (char *)hdr + 345, 100, (char *)hdr);
        if (!safe_member_path(name))
            return -1;
        if (octal((char *)hdr + 100, 8, &mode) != 0 || octal((char *)hdr + 124, 12, &size) != 0)
            return -1;
        mode &= 0777;
        type = hdr[156] ? hdr[156] : '0';
        snprintf(full, sizeof(full), "%s/%s", root, name);
        if (core_only && type != '5' && !core_payload_member(name)) {
            pad = (512 - (size % 512)) % 512;
            if (stream_skip(s, size + pad) != 0)
                return -1;
            continue;
        }
        if (type == '5') {
            if (core_only && strcmp(name, "payload") && strcmp(name, "payload/bin") &&
                strcmp(name, "payload/share") && strcmp(name, "payload/share/busierbox"))
                continue;
            if (mkdir_p(full, (mode_t)mode) != 0)
                return -1;
        } else if (type == '0') {
            char *slash = strrchr(full, '/');
            if (slash) {
                *slash = '\0';
                if (mkdir_p(full, 0700) != 0)
                    return -1;
                *slash = '/';
            }
            fd = open(full, O_WRONLY | O_CREAT | O_TRUNC, (mode_t)mode);
            if (fd < 0)
                return -1;
            left = size;
            while (left) {
                size_t n = left > sizeof(buf) ? sizeof(buf) : (size_t)left;
                if (stream_read(s, buf, n) != 0 || write(fd, buf, n) != (ssize_t)n) {
                    close(fd);
                    return -1;
                }
                left -= n;
            }
            close(fd);
            chmod(full, (mode_t)mode);
        } else if (type == '2') {
            if (core_only && !core_payload_member(name))
                continue;
            snprintf(linkname, sizeof(linkname), "%.*s", 100, (char *)hdr + 157);
            if (!safe_member_path(linkname))
                return -1;
            unlink(full);
            if (symlink(linkname, full) != 0)
                return -1;
        } else {
            return -1;
        }
        pad = (512 - (size % 512)) % 512;
        if ((type == '0') && pad && stream_read(s, buf, (size_t)pad) != 0)
            return -1;
    }
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
    struct payload_stream s;
    int rc;

    snprintf(lock, sizeof(lock), "%s/.extract.lock", root);
    snprintf(tmp, sizeof(tmp), "%s/payload.tmp.%ld", root, (long)getpid());
    snprintf(final, sizeof(final), "%s/payload", root);
    snprintf(extracted, sizeof(extracted), "%s/payload", tmp);

    if (!enough_space_size(ep->size, root)) {
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
    if (mkdir_p(tmp, 0700) != 0) {
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
    if (!strcmp(ep->format, "tar"))
        rc = stream_init_tar(&s, fp, ep->size);
    else
        rc = stream_init_tgz(&s, fp, ep->size);
    if (rc == 0)
        rc = tar_extract_stream(&s, tmp, core_only);
    stream_end(&s);
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
    struct payload_stream s;
    int rc, is_tgz;

    memset(&ep, 0, sizeof(ep));
    snprintf(ep.exe, sizeof(ep.exe), "%s", archive);
    if (stat(archive, &st) != 0)
        return -1;
    ep.size = (unsigned long long)st.st_size;
    snprintf(ep.version, sizeof(ep.version), "%s", BUSIERBOX_PAYLOAD_VERSION);
    is_tgz = strstr(archive, ".gz") || strstr(archive, ".tgz");
    snprintf(ep.format, sizeof(ep.format), "%s", is_tgz ? "tgz" : "tar");

    if (!enough_space_size(ep.size, root))
        return -1;
    fp = fopen(archive, "rb");
    if (!fp)
        return -1;
    rc = is_tgz ? stream_init_tgz(&s, fp, ep.size) : stream_init_tar(&s, fp, ep.size);
    if (rc == 0) {
        char tmp[PATH_MAX], final[PATH_MAX], extracted[PATH_MAX];
        snprintf(tmp, sizeof(tmp), "%s/payload.devtmp.%ld", root, (long)getpid());
        snprintf(final, sizeof(final), "%s/payload", root);
        snprintf(extracted, sizeof(extracted), "%s/payload", tmp);
        bb_rm_rf(tmp);
        if (mkdir_p(tmp, 0700) == 0)
            rc = tar_extract_stream(&s, tmp, core_only);
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
    stream_end(&s);
    fclose(fp);
    return rc;
}

static int ensure_payload_mode(char *payload, size_t payloadsz, int require_full)
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
    if (choose_extract_root(root, sizeof(root)) != 0)
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
    write_artifact_manifest_file(root);
    snprintf(payload, payloadsz, "%s/payload", root);
    return payload_valid(payload) && (!require_full || payload_is_full(payload)) ? 0 : -1;
}

static int ensure_payload(char *payload, size_t payloadsz)
{
    return ensure_payload_mode(payload, payloadsz, 1);
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

static int is_heavy_tool(const char *name)
{
    int i;
    for (i = 0; heavy_tools[i]; i++)
        if (!strcmp(name, heavy_tools[i]))
            return 1;
    return 0;
}

static int path_has_component(const char *pathvar, const char *dir)
{
    size_t dlen = strlen(dir);
    const char *p = pathvar;
    while (p && *p) {
        const char *colon = strchr(p, ':');
        size_t seglen = colon ? (size_t)(colon - p) : strlen(p);
        if (seglen == dlen && strncmp(p, dir, dlen) == 0)
            return 1;
        p = colon ? colon + 1 : NULL;
    }
    return 0;
}

static void set_payload_env(const char *payload)
{
    char path[PATH_MAX * 2], home[PATH_MAX], lib[PATH_MAX], bin_dir[PATH_MAX];
    char abs_payload[PATH_MAX];
    const char *old_path = getenv("PATH");

    /* Resolve to absolute path so PATH stays valid after directory changes */
    if (payload[0] != '/') {
        char cwd[PATH_MAX];
        if (getcwd(cwd, sizeof(cwd)) != NULL)
            snprintf(abs_payload, sizeof(abs_payload), "%s/%s", cwd, payload);
        else
            snprintf(abs_payload, sizeof(abs_payload), "%s", payload);
    } else {
        snprintf(abs_payload, sizeof(abs_payload), "%s", payload);
    }
    payload = abs_payload;

    snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
    if (!old_path || !path_has_component(old_path, bin_dir))
        snprintf(path, sizeof(path), "%s/bin:%s", payload, old_path ? old_path : "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin");
    else
        snprintf(path, sizeof(path), "%s", old_path);
    snprintf(home, sizeof(home), "%s/home", payload);
    snprintf(lib, sizeof(lib), "%s/lib", payload);
    setenv("BUSIERBOX_PAYLOAD_DIR", payload, 1);
    setenv("PATH", path, 1);
    setenv("HOME", home, 1);
    if (!getenv("TERM"))
        setenv("TERM", "xterm-256color", 1);
    snprintf(lib, sizeof(lib), "%s/home", payload);
    if (path_exists(lib))
        setenv("ZDOTDIR", lib, 1);
    snprintf(lib, sizeof(lib), "%s/lib", payload);
    if (path_exists(lib))
        setenv("LD_LIBRARY_PATH", lib, 1);
    snprintf(lib, sizeof(lib), "%s/share/terminfo", payload);
    if (path_exists(lib)) {
        const char *old_ti = getenv("TERMINFO_DIRS");
        if (old_ti && *old_ti) {
            char ti_path[PATH_MAX * 2];
            snprintf(ti_path, sizeof(ti_path), "%s:%s", lib, old_ti);
            setenv("TERMINFO_DIRS", ti_path, 1);
        } else {
            setenv("TERMINFO_DIRS", lib, 1);
        }
    }
}

static int execv_alloc(const char *path, char **argv)
{
    execv(path, argv);
    fprintf(stderr, "busierbox: exec %s failed: %s\n", path, strerror(errno));
    return errno == ENOENT ? 127 : 126;
}

static void payload_root_from_payload(const char *payload, char *root, size_t rootsz)
{
    size_t len;
    snprintf(root, rootsz, "%s", payload);
    len = strlen(root);
    if (len >= 8 && !strcmp(root + len - 8, "/payload"))
        root[len - 8] = '\0';
}

static volatile sig_atomic_t no_residue_signal = 0;
static volatile sig_atomic_t no_residue_child = -1;

static void no_residue_signal_handler(int sig)
{
    no_residue_signal = sig;
    if (no_residue_child > 1)
        kill((pid_t)no_residue_child, sig);
}

static void cleanup_no_residue_root(const char *root, const char *detail)
{
    if (!root || !root[0])
        return;
    if (strcmp(root, BB_RUNTIME_ROOT) && strcmp(root, BB_RUNTIME_FALLBACK_ROOT))
        return;
    bb_ledger_record("remove", root, "runtime", detail);
    bb_rm_rf(root);
}

static int exec_payload_command(const char *path, char **argv, const char *payload)
{
    pid_t pid;
    int status;
    char root[PATH_MAX];
    struct sigaction sa, old_int, old_term, old_hup, old_quit;

    if (strcmp(BB_RUNTIME_MODE, "no-residue") != 0)
        return execv_alloc(path, argv);

    payload_root_from_payload(payload, root, sizeof(root));
    no_residue_signal = 0;

    pid = fork();
    if (pid < 0) {
        fprintf(stderr, "busierbox: fork %s failed: %s\n", path, strerror(errno));
        cleanup_no_residue_root(root, "no-residue fork failure");
        return 1;
    }
    if (pid == 0) {
        execv(path, argv);
        fprintf(stderr, "busierbox: exec %s failed: %s\n", path, strerror(errno));
        _exit(errno == ENOENT ? 127 : 126);
    }

    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = no_residue_signal_handler;
    sigemptyset(&sa.sa_mask);
    no_residue_child = pid;
    sigaction(SIGINT, &sa, &old_int);
    sigaction(SIGTERM, &sa, &old_term);
    sigaction(SIGHUP, &sa, &old_hup);
    sigaction(SIGQUIT, &sa, &old_quit);

    while (waitpid(pid, &status, 0) < 0) {
        if (errno == EINTR)
            continue;
        status = 1 << 8;
        break;
    }
    no_residue_child = -1;
    sigaction(SIGINT, &old_int, NULL);
    sigaction(SIGTERM, &old_term, NULL);
    sigaction(SIGHUP, &old_hup, NULL);
    sigaction(SIGQUIT, &old_quit, NULL);

    cleanup_no_residue_root(root, no_residue_signal ? "no-residue interrupted foreground payload command" : "no-residue foreground payload command");
    if (no_residue_signal)
        return 128 + no_residue_signal;
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    if (WIFSIGNALED(status))
        return 128 + WTERMSIG(status);
    return 1;
}

static int wait_status_ok(pid_t pid)
{
    int status;
    if (waitpid(pid, &status, 0) < 0)
        return 0;
    return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

static int run_downloader(const char *tool, const char *url, const char *out)
{
    pid_t pid = fork();
    if (pid < 0)
        return -1;
    if (pid == 0) {
        if (!strcmp(tool, "wget"))
            execlp("wget", "wget", "-O", out, url, (char *)NULL);
        else
            execlp("curl", "curl", "-fL", "-o", out, url, (char *)NULL);
        _exit(127);
    }
    return wait_status_ok(pid) ? 0 : -1;
}

static int file_sha256_hex(const char *path, char out[65])
{
    FILE *fp = fopen(path, "rb");
    bb_sha256_ctx ctx;
    uint8_t buf[8192], hash[32];
    size_t n;
    if (!fp)
        return -1;
    bb_sha256_init(&ctx);
    while ((n = fread(buf, 1, sizeof(buf), fp)) > 0)
        bb_sha256_update(&ctx, buf, n);
    if (ferror(fp)) {
        fclose(fp);
        return -1;
    }
    fclose(fp);
    bb_sha256_final(&ctx, hash);
    bb_sha256_hex(hash, out);
    return 0;
}

int applet_fetch_full_main(int argc, char **argv)
{
    const char *url = NULL;
    const char *out = "busierbox-full";
    const char *expected_sha = NULL;
    int exec_after = 0;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox fetch-full URL [OUT] [--sha256 HASH] [--exec]");
        puts("Downloads a full BusierBox artifact with wget or curl, chmods it executable,");
        puts("optionally verifies a sha256 hash, and optionally execs it.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--exec")) {
            exec_after = 1;
        } else if (!strcmp(argv[i], "--sha256")) {
            if (i + 1 >= argc) {
                fprintf(stderr, "fetch-full: --sha256 requires a hash\n");
                return 2;
            }
            expected_sha = argv[++i];
        } else if (!url) {
            url = argv[i];
        } else {
            out = argv[i];
        }
    }
    if (!url) {
        fprintf(stderr, "fetch-full: URL required\n");
        return 2;
    }
    printf("fetch-full: downloading %s -> %s\n", url, out);
    if (run_downloader("wget", url, out) != 0 && run_downloader("curl", url, out) != 0) {
        fprintf(stderr, "fetch-full: download failed; need wget or curl in PATH\n");
        return 1;
    }
    if (expected_sha) {
        char got[65];
        if (file_sha256_hex(out, got) != 0) {
            fprintf(stderr, "fetch-full: unable to hash %s\n", out);
            return 1;
        }
        if (strcmp(got, expected_sha)) {
            fprintf(stderr, "fetch-full: sha256 mismatch for %s\nexpected: %s\n     got: %s\n", out, expected_sha, got);
            return 1;
        }
    }
    if (chmod(out, 0755) != 0) {
        fprintf(stderr, "fetch-full: chmod %s failed: %s\n", out, strerror(errno));
        return 1;
    }
    if (exec_after) {
        char exec_path[PATH_MAX];
        char *child[] = {exec_path, "doctor", NULL};
        if (strchr(out, '/'))
            snprintf(exec_path, sizeof(exec_path), "%s", out);
        else
            snprintf(exec_path, sizeof(exec_path), "./%s", out);
        execv(exec_path, child);
        fprintf(stderr, "fetch-full: exec %s failed: %s\n", exec_path, strerror(errno));
        return errno == ENOENT ? 127 : 126;
    }
    puts("fetch-full: ok");
    return 0;
}

int bb_exec_payload_applet(const char *name, int argc, char **argv)
{
    char payload[PATH_MAX], exe[PATH_MAX];
    char **child;
    int i;

    if (!bb_applet_supported(name)) {
        fprintf(stderr, "busierbox: %s: applet not found\n\n", name);
        bb_print_applet_list(stderr);
        return 127;
    }

    if (ensure_payload_mode(payload, sizeof(payload), is_heavy_tool(name)) != 0) {
        fprintf(stderr, "busierbox: payload unavailable; run 'busierbox extract' after creating dist/payload.tar.gz\n");
        return 127;
    }
    set_payload_env(payload);

    if (is_heavy_tool(name)) {
        int ret;
        snprintf(exe, sizeof(exe), "%s/bin/%s", payload, name);
        child = calloc((size_t)argc + 1, sizeof(char *));
        if (!child)
            return 1;
        child[0] = (char *)name;
        for (i = 1; i < argc; i++)
            child[i] = argv[i];
        child[argc] = NULL;
        if (!strcmp(name, "zsh") || !strcmp(name, "bash"))
            setenv("SHELL", exe, 1);
        ret = exec_payload_command(exe, child, payload);
        free(child);
        return ret;
    }

    snprintf(exe, sizeof(exe), "%s/bin/busybox", payload);
    child = calloc((size_t)argc + 2, sizeof(char *));
    if (!child)
        return 1;
    child[0] = exe;
    child[1] = (char *)name;
    for (i = 1; i < argc; i++)
        child[i + 1] = argv[i];
    child[argc + 1] = NULL;
    if (strcmp(BB_RUNTIME_MODE, "no-residue") == 0) {
        int ret = exec_payload_command(exe, child, payload);
        free(child);
        return ret;
    }
    execv(exe, child);
    fprintf(stderr, "busierbox: exec BusyBox applet %s failed: %s\n", name, strerror(errno));
    free(child);
    return errno == ENOENT ? 127 : 126;
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

static void write_manifest_json(FILE *out)
{
    int i;

    fprintf(out, "{\"schema\":1,\"busierbox\":{\"payload_version\":");
    json_string_payload(out, BUSIERBOX_PAYLOAD_VERSION);
    fprintf(out, ",\"artifact_tier\":");
    json_string_payload(out, BUSIERBOX_ARTIFACT_TIER);
    fprintf(out, ",\"build_timestamp\":");
    json_string_payload(out, BUSIERBOX_BUILD_TIMESTAMP);
    fprintf(out, ",\"git_commit\":");
    json_string_payload(out, BUSIERBOX_GIT_COMMIT);
    fprintf(out, "},\"target\":{\"preset\":");
    json_string_payload(out, BB_TARGET_PRESET);
    fprintf(out, ",\"name\":");
    json_string_payload(out, BB_TARGET_NAME);
    fprintf(out, ",\"arch\":");
    json_string_payload(out, BB_TARGET_ARCH);
    fprintf(out, ",\"endian\":");
    json_string_payload(out, BB_TARGET_ENDIAN);
    fprintf(out, ",\"cpu\":");
    json_string_payload(out, BB_TARGET_CPU);
    fprintf(out, ",\"abi\":");
    json_string_payload(out, BB_TARGET_ABI);
    fprintf(out, ",\"libc\":");
    json_string_payload(out, BB_TARGET_LIBC);
    fprintf(out, ",\"kernel_floor\":");
    json_string_payload(out, BB_KERNEL_FLOOR);
    fprintf(out, ",\"static_policy\":");
    json_string_payload(out, BB_STATIC_POLICY);
    fprintf(out, "},\"payload\":{\"preset\":");
    json_string_payload(out, BB_PAYLOAD_PRESET);
    fprintf(out, ",\"gdbserver_provider\":");
    json_string_payload(out, BB_GDBSERVER_PROVIDER);
    fprintf(out, "},\"runtime\":{\"mode\":");
    json_string_payload(out, BB_RUNTIME_MODE);
    fprintf(out, ",\"root\":");
    json_string_payload(out, BB_RUNTIME_ROOT);
    fprintf(out, ",\"allow_fallback_root\":");
    json_string_payload(out, BB_RUNTIME_ALLOW_FALLBACK_ROOT);
    fprintf(out, ",\"fallback_root\":");
    json_string_payload(out, BB_RUNTIME_FALLBACK_ROOT);
    fprintf(out, "},\"zero_arg\":{\"mode\":");
    json_string_payload(out, BB_ZERO_ARG_MODE);
    fprintf(out, ",\"log_mode\":");
    json_string_payload(out, BB_ZERO_ARG_LOG_MODE);
    fprintf(out, "},\"rshell\":{\"transport\":");
    json_string_payload(out, BB_RSHELL_TRANSPORT);
    fprintf(out, ",\"encryption\":");
    json_string_payload(out, BB_RSHELL_ENCRYPTION);
    fprintf(out, ",\"run_mode\":");
    json_string_payload(out, BB_RSHELL_RUN_MODE);
    fprintf(out, ",\"shell_provider\":");
    json_string_payload(out, BB_RSHELL_SHELL_PROVIDER);
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
    fprintf(out, ",\"authkeys_mode\":");
    json_string_payload(out, BB_RSHELL_AUTHKEYS_MODE);
    fprintf(out, ",\"retry\":{\"count\":");
    json_string_payload(out, BB_RSHELL_RETRY_COUNT);
    fprintf(out, ",\"interval_sec\":");
    json_string_payload(out, BB_RSHELL_RETRY_INTERVAL_SEC);
    fprintf(out, ",\"jitter_pct\":");
    json_string_payload(out, BB_RSHELL_RETRY_JITTER_PCT);
    fprintf(out, ",\"backoff\":");
    json_string_payload(out, BB_RSHELL_RETRY_BACKOFF);
    fprintf(out, ",\"max_interval_sec\":");
    json_string_payload(out, BB_RSHELL_RETRY_MAX_INTERVAL_SEC);
    fprintf(out, "}");
    fprintf(out, "},\"dotfiles\":{\"enabled\":");
    json_string_payload(out, BB_DOTFILES_ENABLE);
    fprintf(out, ",\"zsh\":");
    json_string_payload(out, BB_DOTFILE_ZSH_MODE);
    fprintf(out, ",\"bash\":");
    json_string_payload(out, BB_DOTFILE_BASH_MODE);
    fprintf(out, ",\"tmux\":");
    json_string_payload(out, BB_DOTFILE_TMUX_MODE);
    fprintf(out, ",\"gdb\":");
    json_string_payload(out, BB_DOTFILE_GDB_MODE);
    fprintf(out, ",\"profile\":");
    json_string_payload(out, BB_DOTFILE_PROFILE_MODE);
    fprintf(out, "},\"overlay\":{\"enabled\":");
    json_string_payload(out, BB_USER_OVERLAY_ENABLE);
    fprintf(out, ",\"root\":");
    json_string_payload(out, BB_USER_OVERLAY_ROOT);
    fprintf(out, ",\"allow_override\":");
    json_string_payload(out, BB_USER_OVERLAY_ALLOW_OVERRIDE);
    fprintf(out, "},\"compiled_config\":");
    bb_config_print_compiled_json(out, json_string_payload);
    fprintf(out, ",\"effective_config\":");
    bb_config_print_effective_json(out, json_string_payload);
    fprintf(out, ",\"trailer_override\":");
    bb_config_print_trailer_json(out, json_string_payload);
    fprintf(out, ",\"native_features\":{\"survey\":%s,\"doctor\":%s,\"extract\":%s,\"config_info\":%s",
#if BB_ENABLE_SURVEY
           "true",
#else
           "false",
#endif
#if BB_ENABLE_DOCTOR
           "true",
#else
           "false",
#endif
#if BB_ENABLE_EXTRACT
           "true",
#else
           "false",
#endif
#if BB_ENABLE_CONFIG_INFO
           "true"
#else
           "false"
#endif
    );
#ifdef HAVE_WOLFSSL
    fprintf(out, ",\"wolfssl\":true");
#else
    fprintf(out, ",\"wolfssl\":false");
#endif
    fprintf(out, "},\"payload_tools\":{\"busybox_applets\":[");
    for (i = 0; busybox_tools[i]; i++) {
        if (i)
            fputc(',', out);
        json_string_payload(out, busybox_tools[i]);
    }
    fprintf(out, "],\"heavy_tools\":[");
    for (i = 0; heavy_tools[i]; i++) {
        if (i)
            fputc(',', out);
        json_string_payload(out, heavy_tools[i]);
    }
    fprintf(out, "]}}\n");
}

static int base64_write_bytes(const unsigned char *data, size_t len)
{
    static const char tab[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i;
    for (i = 0; i < len; i += 3) {
        size_t n = len - i;
        unsigned int v;
        if (n > 3)
            n = 3;
        v = ((unsigned int)data[i] << 16) |
            ((unsigned int)(n > 1 ? data[i + 1] : 0) << 8) |
            (unsigned int)(n > 2 ? data[i + 2] : 0);
        putchar(tab[(v >> 18) & 63]);
        putchar(tab[(v >> 12) & 63]);
        putchar(n > 1 ? tab[(v >> 6) & 63] : '=');
        putchar(n > 2 ? tab[v & 63] : '=');
    }
    putchar('\n');
    return ferror(stdout) ? 1 : 0;
}

static char *manifest_json_alloc(size_t *len_out)
{
    char *buf = NULL;
    size_t len = 0;
    FILE *fp = open_memstream(&buf, &len);
    if (!fp)
        return NULL;
    write_manifest_json(fp);
    if (fclose(fp) != 0) {
        free(buf);
        return NULL;
    }
    if (len && buf[len - 1] == '\n')
        buf[--len] = '\0';
    if (len_out)
        *len_out = len;
    return buf;
}

static int print_manifest_base64(void)
{
    size_t len = 0;
    char *json = manifest_json_alloc(&len);
    int rc;
    if (!json) {
        fputs("manifest: cannot allocate manifest buffer\n", stderr);
        return 1;
    }
    rc = base64_write_bytes((const unsigned char *)json, len);
    free(json);
    return rc;
}

static int write_config_export_json(FILE *out)
{
    char *manifest = manifest_json_alloc(NULL);
    if (!manifest)
        return -1;
    fprintf(out, "{\"schema\":1,\"kind\":\"busierbox-config-export\",\"manifest\":%s}\n", manifest);
    free(manifest);
    return ferror(out) ? -1 : 0;
}

static char *config_export_json_alloc(size_t *len_out)
{
    char *buf = NULL;
    size_t len = 0;
    FILE *fp = open_memstream(&buf, &len);
    if (!fp)
        return NULL;
    if (write_config_export_json(fp) != 0 || fclose(fp) != 0) {
        free(buf);
        return NULL;
    }
    if (len && buf[len - 1] == '\n')
        buf[--len] = '\0';
    if (len_out)
        *len_out = len;
    return buf;
}

static int print_config_export_base64(void)
{
    size_t len = 0;
    char *json = config_export_json_alloc(&len);
    int rc;
    if (!json) {
        fputs("config-export: cannot allocate export buffer\n", stderr);
        return 1;
    }
    rc = base64_write_bytes((const unsigned char *)json, len);
    free(json);
    return rc;
}

static int print_support_token(void)
{
    char *manifest = manifest_json_alloc(NULL);
    char *token = NULL;
    size_t token_len = 0;
    FILE *fp;
    int rc;
    if (!manifest) {
        fputs("doctor: cannot allocate manifest buffer\n", stderr);
        return 1;
    }
    fp = open_memstream(&token, &token_len);
    if (!fp) {
        free(manifest);
        fputs("doctor: cannot allocate support token buffer\n", stderr);
        return 1;
    }
    fprintf(fp, "{\"schema\":1,\"kind\":\"busierbox-support-token\",");
    fprintf(fp, "\"warning\":\"operator host and ports may be embedded; private key material is not included\",");
    fprintf(fp, "\"manifest\":%s}", manifest);
    free(manifest);
    if (fclose(fp) != 0) {
        free(token);
        fputs("doctor: cannot finalize support token\n", stderr);
        return 1;
    }
    rc = base64_write_bytes((const unsigned char *)token, token_len);
    free(token);
    return rc;
}

static void write_artifact_manifest_file(const char *root)
{
    char dir[PATH_MAX], path[PATH_MAX], tmp[PATH_MAX];
    FILE *fp;

    snprintf(dir, sizeof(dir), "%s/manifest", root);
    if (mkdir_p(dir, 0700) != 0)
        return;
    snprintf(path, sizeof(path), "%s/artifact.json", dir);
    snprintf(tmp, sizeof(tmp), "%s/artifact.json.tmp.%ld", dir, (long)getpid());
    fp = fopen(tmp, "w");
    if (!fp)
        return;
    write_manifest_json(fp);
    if (fclose(fp) != 0) {
        unlink(tmp);
        return;
    }
    if (rename(tmp, path) != 0) {
        unlink(tmp);
        return;
    }
    bb_ledger_record("write", path, "runtime", "artifact manifest");
}

int applet_manifest_main(int argc, char **argv)
{
    int json = 0, base64 = 0;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox manifest [--json|--base64]");
        puts("Print artifact and preset metadata embedded in this BusierBox binary.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--base64"))
            base64 = 1;
        else {
            fprintf(stderr, "manifest: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json && base64) {
        fputs("manifest: choose one of --json or --base64\n", stderr);
        return 2;
    }

    if (json) {
        write_manifest_json(stdout);
        return 0;
    }
    if (base64)
        return print_manifest_base64();

    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    printf("payload_version=%s\n", BUSIERBOX_PAYLOAD_VERSION);
    printf("build_timestamp=%s\n", BUSIERBOX_BUILD_TIMESTAMP);
    printf("git_commit=%s\n", BUSIERBOX_GIT_COMMIT);
    printf("target_preset=%s\n", BB_TARGET_PRESET);
    printf("target_name=%s\n", BB_TARGET_NAME);
    printf("target_arch=%s\n", BB_TARGET_ARCH);
    printf("target_endian=%s\n", BB_TARGET_ENDIAN);
    printf("target_cpu=%s\n", BB_TARGET_CPU);
    printf("target_abi=%s\n", BB_TARGET_ABI);
    printf("target_libc=%s\n", BB_TARGET_LIBC);
    printf("kernel_floor=%s\n", BB_KERNEL_FLOOR);
    printf("static_policy=%s\n", BB_STATIC_POLICY);
    printf("payload_preset=%s\n", BB_PAYLOAD_PRESET);
    printf("gdbserver_provider=%s\n", BB_GDBSERVER_PROVIDER);
    printf("runtime_mode=%s\n", BB_RUNTIME_MODE);
    printf("runtime_root=%s\n", BB_RUNTIME_ROOT);
    printf("zero_arg_mode=%s\n", BB_ZERO_ARG_MODE);
    printf("rshell_transport=%s\n", BB_RSHELL_TRANSPORT);
    printf("rshell_encryption=%s\n", BB_RSHELL_ENCRYPTION);
    printf("heavy_tools=");
    for (i = 0; heavy_tools[i]; i++)
        printf("%s%s", i ? " " : "", heavy_tools[i]);
    printf("\n");
    return 0;
}

int applet_config_export_main(int argc, char **argv)
{
    int json = 0, base64 = 0;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox config-export [--json|--base64]");
        puts("Export rebuild-oriented artifact config metadata. No private key material is included.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--base64"))
            base64 = 1;
        else {
            fprintf(stderr, "config-export: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json && base64) {
        fputs("config-export: choose one of --json or --base64\n", stderr);
        return 2;
    }
    if (base64)
        return print_config_export_base64();
    (void)json;
    if (write_config_export_json(stdout) != 0) {
        fputs("config-export: cannot write export JSON\n", stderr);
        return 1;
    }
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
    if (choose_extract_root(root, sizeof(root)) != 0) {
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
    write_artifact_manifest_file(root);
    printf("payload: extracted %s\n", payload);
    return 0;
}

int bb_rm_rf(const char *path)
{
    struct stat st;

    if (lstat(path, &st) != 0)
        return errno == ENOENT ? 0 : -1;
    if (S_ISDIR(st.st_mode)) {
        DIR *d = opendir(path);
        struct dirent *de;
        if (!d)
            return -1;
        while ((de = readdir(d)) != NULL) {
            char child[PATH_MAX];
            if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, ".."))
                continue;
            snprintf(child, sizeof(child), "%s/%s", path, de->d_name);
            if (bb_rm_rf(child) != 0) {
                closedir(d);
                return -1;
            }
        }
        closedir(d);
        return rmdir(path);
    }
    return unlink(path);
}

static char *read_text_file(const char *path, size_t max_bytes)
{
    FILE *fp = fopen(path, "r");
    char *buf;
    size_t n;
    long len;
    if (!fp)
        return NULL;
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return NULL;
    }
    len = ftell(fp);
    if (len < 0 || (size_t)len > max_bytes) {
        fclose(fp);
        return NULL;
    }
    rewind(fp);
    buf = calloc(1, (size_t)len + 1);
    if (!buf) {
        fclose(fp);
        return NULL;
    }
    n = fread(buf, 1, (size_t)len, fp);
    fclose(fp);
    buf[n] = '\0';
    return buf;
}

static int json_array_summary(const char *json, const char *key, FILE *out)
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

static const char *json_bool_value(const char *json, const char *key)
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

static int json_object_summary(const char *json, const char *key, FILE *out)
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

static int json_array_count_field(const char *json, const char *key)
{
    FILE *out = fopen("/dev/null", "w");
    int count;
    if (!out)
        return 0;
    count = json_array_summary(json, key, out);
    fclose(out);
    return count;
}

static int path_entry_count(const char *path, const char *entry)
{
    char *dup, *save = NULL, *p;
    int count = 0;
    if (!path || !entry || !*entry)
        return 0;
    dup = strdup(path);
    if (!dup)
        return 0;
    for (p = strtok_r(dup, ":", &save); p; p = strtok_r(NULL, ":", &save)) {
        if (!strcmp(*p ? p : ".", entry))
            count++;
    }
    free(dup);
    return count;
}

static int path_has_duplicate_entries(const char *path)
{
    char *outer, *save = NULL, *p;
    int dup = 0;
    if (!path)
        return 0;
    outer = strdup(path);
    if (!outer)
        return 0;
    for (p = strtok_r(outer, ":", &save); p; p = strtok_r(NULL, ":", &save)) {
        if (path_entry_count(path, *p ? p : ".") > 1) {
            dup = 1;
            break;
        }
    }
    free(outer);
    return dup;
}

static const char *ptrace_probe_status(void)
{
    pid_t child, r;
    int status;

    child = fork();
    if (child < 0)
        return "fork-failed";
    if (child == 0) {
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL) < 0)
            _exit(2);
        raise(SIGSTOP);
        _exit(0);
    }
    r = waitpid(child, &status, 0);
    if (r != child) {
        kill(child, SIGKILL);
        waitpid(child, NULL, 0);
        return "unknown";
    }
    if (WIFSTOPPED(status) && WSTOPSIG(status) == SIGSTOP) {
        ptrace(PTRACE_CONT, child, NULL, 0);
        waitpid(child, &status, 0);
        return "basic-ok";
    }
    if (WIFEXITED(status) && WEXITSTATUS(status) == 2)
        return "denied";
    kill(child, SIGKILL);
    waitpid(child, NULL, 0);
    return "unknown";
}

static unsigned long long statvfs_available_bytes(const char *path)
{
    struct statvfs v;
    if (statvfs(path, &v) != 0)
        return 0;
    return (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize;
}

static int extract_root_currently_usable(const char *path)
{
    if (!path || !path[0] || !path_exists(path))
        return 0;
    if (access(path, W_OK | X_OK) != 0)
        return 0;
    return !dir_is_noexec(path);
}

static void print_extract_root_probe_json(FILE *out, const char *role, const char *path,
                                          unsigned long long payload_size, int selected)
{
    int configured = path && path[0];
    int exists = configured && path_exists(path);
    int writable = exists && access(path, W_OK) == 0;
    int executable = exists && access(path, X_OK) == 0;
    int noexec = exists && dir_is_noexec(path);

    fprintf(out, "{\"role\":");
    json_string_payload(out, role);
    fprintf(out, ",\"configured\":%s,\"path\":", configured ? "true" : "false");
    if (configured)
        json_string_payload(out, path);
    else
        fputs("null", out);
    fprintf(out, ",\"exists\":%s,\"writable\":%s,\"executable\":%s,\"noexec\":%s",
            exists ? "true" : "false",
            writable ? "true" : "false",
            executable ? "true" : "false",
            noexec ? "true" : "false");
    fprintf(out, ",\"available_bytes\":%llu,\"free_space_ok\":%s,\"selected\":%s}",
            exists ? statvfs_available_bytes(path) : 0ULL,
            exists && enough_space_size(payload_size, path) ? "true" : "false",
            selected ? "true" : "false");
}

static void print_doctor_extraction_runtime_json(FILE *out, unsigned long long payload_size)
{
    const char *selected = NULL;
    int fallback_enabled = !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes");

    if (extract_root_currently_usable(BB_RUNTIME_ROOT))
        selected = BB_RUNTIME_ROOT;
    else if (fallback_enabled && extract_root_currently_usable(BB_RUNTIME_FALLBACK_ROOT))
        selected = BB_RUNTIME_FALLBACK_ROOT;

    fprintf(out, ",\"extraction_runtime\":{\"runtime_root\":");
    json_string_payload(out, BB_RUNTIME_ROOT);
    fprintf(out, ",\"fallback_root\":");
    json_string_payload(out, BB_RUNTIME_FALLBACK_ROOT);
    fprintf(out, ",\"fallback_enabled\":%s,\"required_bytes\":%llu,\"writable_executable\":%s,\"selected_root\":",
            fallback_enabled ? "true" : "false",
            extract_required_bytes(payload_size),
            selected ? "true" : "false");
    if (selected)
        json_string_payload(out, selected);
    else
        fputs("null", out);
    fprintf(out, ",\"roots\":[");
    print_extract_root_probe_json(out, "runtime", BB_RUNTIME_ROOT, payload_size,
                                  selected && !strcmp(selected, BB_RUNTIME_ROOT));
    fputc(',', out);
    print_extract_root_probe_json(out, "fallback", BB_RUNTIME_FALLBACK_ROOT, payload_size,
                                  selected && !strcmp(selected, BB_RUNTIME_FALLBACK_ROOT));
    fprintf(out, "]}");
}

static unsigned long long mem_available_kb(void)
{
    FILE *fp = fopen("/proc/meminfo", "r");
    char key[64], unit[32];
    unsigned long long val;
    if (!fp)
        return 0;
    while (fscanf(fp, "%63s %llu %31s\n", key, &val, unit) == 3) {
        if (!strcmp(key, "MemAvailable:")) {
            fclose(fp);
            return val;
        }
    }
    fclose(fp);
    return 0;
}

static int has_default_route(void)
{
    FILE *fp = fopen("/proc/net/route", "r");
    char line[256], iface[64], dest[64];
    if (!fp)
        return 0;
    if (!fgets(line, sizeof(line), fp)) {
        fclose(fp);
        return 0;
    }
    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "%63s %63s", iface, dest) == 2 && !strcmp(dest, "00000000")) {
            fclose(fp);
            return 1;
        }
    }
    fclose(fp);
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

static int cleanup_ledger_entry_count(const char *path)
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

static void print_doctor_runtime_config_json(FILE *out)
{
    fprintf(out, ",\"runtime_config\":{\"effective_config_source\":");
    json_string_payload(out, bb_config_effective_source());
    fprintf(out, ",\"trailer_override\":");
    bb_config_print_trailer_json(out, json_string_payload);
    fprintf(out, "}");
}

static void print_doctor_cleanup_ledger_json(FILE *out)
{
    char path[PATH_MAX];
    bb_ledger_path(path, sizeof(path));
    fprintf(out, ",\"cleanup_ledger\":{\"path\":");
    json_string_payload(out, path);
    fprintf(out, ",\"present\":%s,\"entry_count\":%d}",
            path_exists(path) ? "true" : "false",
            cleanup_ledger_entry_count(path));
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
    read_first_line(symlink_count_path, symlink_count, sizeof(symlink_count));
    snprintf(terminfo, sizeof(terminfo), "%s/share/terminfo", payload);
    snprintf(tmux_ti, sizeof(tmux_ti), "%s/share/terminfo/t/tmux", payload);
    snprintf(zsh_path, sizeof(zsh_path), "%s/bin/zsh", payload);
    snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);

    fprintf(out, ",\"dir\":");
    json_string_payload(out, payload);
    fprintf(out, ",\"busybox_executable\":%s", executable_file(busybox) ? "true" : "false");
    fprintf(out, ",\"applet_symlink_count\":");
    if (symlink_count[0])
        json_string_payload(out, symlink_count);
    else
        fprintf(out, "null");
    fprintf(out, ",\"terminfo_present\":%s", path_exists(terminfo) ? "true" : "false");
    fprintf(out, ",\"tmux_terminfo_present\":%s", path_exists(tmux_ti) ? "true" : "false");
    fprintf(out, ",\"zsh_present\":%s", executable_file(zsh_path) ? "true" : "false");
    fprintf(out, ",\"payload_bin_path_count\":%d", path_entry_count(getenv("PATH"), bin_dir));
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
        return print_support_token();

    if (get_embedded_payload(&ep) == 0) {
        if (json) {
            int hash_ok = verify_embedded_hash(&ep) == 0;
            have_payload = candidate_payload(payload, sizeof(payload)) == 0;
            if (have_payload) {
                snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
                snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
                if (path_exists(manifest_path))
                    manifest = read_text_file(manifest_path, 1024 * 1024);
            } else {
                root[0] = '\0';
                if (BB_RUNTIME_ROOT[0] && access(BB_RUNTIME_ROOT, W_OK | X_OK) == 0 && !dir_is_noexec(BB_RUNTIME_ROOT))
                    snprintf(root, sizeof(root), "%s", BB_RUNTIME_ROOT);
                else if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") && BB_RUNTIME_FALLBACK_ROOT[0] &&
                         access(BB_RUNTIME_FALLBACK_ROOT, W_OK | X_OK) == 0 && !dir_is_noexec(BB_RUNTIME_FALLBACK_ROOT))
                    snprintf(root, sizeof(root), "%s", BB_RUNTIME_FALLBACK_ROOT);
            }
            if (manifest)
                applet_count = json_array_count_field(manifest, "busybox_applets");
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
                printf(",\"busybox_present\":%s", executable_file(busybox) ? "true" : "false");
                printf(",\"manifest_found\":%s", path_exists(manifest_path) ? "true" : "false");
                printf(",\"identity_match\":%s", payload_id_matches(&ep, payload) ? "true" : "false");
            } else if (root[0]) {
                printf(",\"candidate_extract_root\":");
                json_string_payload(stdout, root);
            }
            printf("}");
            print_doctor_extraction_runtime_json(stdout, ep.size);
            printf(",\"payload_manifest\":{\"found\":%s,\"busybox_applets_count\":%d",
                   manifest ? "true" : "false", applet_count);
            if (manifest) {
                printf(",\"overlay_enabled\":%s", !strcmp(json_bool_value(manifest, "overlay_enabled"), "yes") ? "true" : "false");
            }
            printf("}");
            print_doctor_payload_runtime_health_json(stdout, have_payload, payload);
            print_doctor_manifest_summary_json(stdout, manifest != NULL, applet_count);
            print_doctor_rshell_readiness_json(stdout);
            print_doctor_runtime_config_json(stdout);
            print_doctor_cleanup_ledger_json(stdout);
            printf(",\"environment\":{\"path_has_duplicates\":%s,\"home_set\":%s,\"shell_set\":%s",
                   path_has_duplicate_entries(getenv("PATH")) ? "true" : "false",
                   getenv("HOME") && *getenv("HOME") ? "true" : "false",
                   getenv("SHELL") && *getenv("SHELL") ? "true" : "false");
            if (have_payload) {
                char bin_dir[PATH_MAX];
                snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
                printf(",\"payload_bin_path_count\":%d", path_entry_count(getenv("PATH"), bin_dir));
            }
            printf("},\"host\":{\"mem_available_kb\":%llu,\"devpts_available\":%s,\"ptrace_probe\":",
                   mem_available_kb(), path_exists("/dev/pts") ? "true" : "false");
            json_string_payload(stdout, ptrace_probe_status());
            printf(",\"default_route_present\":%s}", has_default_route() ? "true" : "false");
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
                if (path_exists(manifest_path))
                    manifest = read_text_file(manifest_path, 1024 * 1024);
            }
            if (manifest)
                applet_count = json_array_count_field(manifest, "busybox_applets");
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
                printf(",\"busybox_present\":%s", executable_file(busybox) ? "true" : "false");
                printf(",\"manifest_found\":%s", path_exists(manifest_path) ? "true" : "false");
            }
            printf("}");
            print_doctor_extraction_runtime_json(stdout, 1);
            printf(",\"payload_manifest\":{\"found\":%s,\"busybox_applets_count\":%d}",
                   manifest ? "true" : "false", applet_count);
            print_doctor_payload_runtime_health_json(stdout, have_payload, payload);
            print_doctor_manifest_summary_json(stdout, manifest != NULL, applet_count);
            print_doctor_rshell_readiness_json(stdout);
            print_doctor_runtime_config_json(stdout);
            print_doctor_cleanup_ledger_json(stdout);
            printf(",\"environment\":{\"path_has_duplicates\":%s,\"home_set\":%s,\"shell_set\":%s}",
                   path_has_duplicate_entries(getenv("PATH")) ? "true" : "false",
                   getenv("HOME") && *getenv("HOME") ? "true" : "false",
                   getenv("SHELL") && *getenv("SHELL") ? "true" : "false");
            printf(",\"host\":{\"mem_available_kb\":%llu,\"devpts_available\":%s,\"ptrace_probe\":",
                   mem_available_kb(), path_exists("/dev/pts") ? "true" : "false");
            json_string_payload(stdout, ptrace_probe_status());
            printf(",\"default_route_present\":%s}", has_default_route() ? "true" : "false");
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
        if (choose_extract_root(root, sizeof(root)) == 0)
            printf("candidate_extract_root=%s\n", root);
    }

    if (have_payload) {
        snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
        printf("busybox_present=%s\n", executable_file(busybox) ? "yes" : "no");
        snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
        printf("payload_manifest_found=%s\n", path_exists(manifest_path) ? "yes" : "no");
        if (ep.present)
            printf("payload_identity_match=%s\n", payload_id_matches(&ep, payload) ? "yes" : "no (stale or different binary)");
        if (path_exists(manifest_path))
            manifest = read_text_file(manifest_path, 1024 * 1024);
    }

    if (manifest) {
        printf("busybox_applets=");
        applet_count = json_array_summary(manifest, "busybox_applets", stdout);
        printf("\n");
        printf("busybox_applets_count=%d\n", applet_count);
        printf("staged_tools=");
        json_array_summary(manifest, "staged_payload_tools", stdout);
        printf("\n");
        printf("missing_tools=");
        json_array_summary(manifest, "missing_payload_tools", stdout);
        printf("\n");
        printf("missing_tool_reasons=");
        json_object_summary(manifest, "missing_payload_tool_reasons", stdout);
        printf("\n");
        printf("overlay_enabled=%s\n", json_bool_value(manifest, "overlay_enabled"));
        printf("overlay_tools=");
        json_array_summary(manifest, "overlay_tools", stdout);
        printf("\n");
        printf("overlay_files=");
        json_array_summary(manifest, "overlay_files", stdout);
        printf("\n");
        printf("overlay_warnings=");
        json_array_summary(manifest, "overlay_warnings", stdout);
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
        read_first_line(symlink_count_path, symlink_count, sizeof(symlink_count));
        printf("applet_symlink_count=%s\n", symlink_count);
        snprintf(terminfo, sizeof(terminfo), "%s/share/terminfo", payload);
        snprintf(tmux_ti, sizeof(tmux_ti), "%s/share/terminfo/t/tmux", payload);
        printf("terminfo_present=%s\n", path_exists(terminfo) ? "yes" : "no");
        printf("tmux_terminfo_present=%s\n", path_exists(tmux_ti) ? "yes" : "no");
        snprintf(zsh_path, sizeof(zsh_path), "%s/bin/zsh", payload);
        printf("zsh_present=%s\n", executable_file(zsh_path) ? "yes" : "no");
        snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
        printf("payload_bin_path_count=%d\n", path_entry_count(getenv("PATH"), bin_dir));
    }
    printf("path_has_duplicates=%s\n", path_has_duplicate_entries(getenv("PATH")) ? "yes" : "no");
    printf("home_set=%s\n", getenv("HOME") && *getenv("HOME") ? "yes" : "no");
    printf("shell_set=%s\n", getenv("SHELL") && *getenv("SHELL") ? "yes" : "no");

    if (choose_extract_root(root, sizeof(root)) == 0) {
        printf("extract_root_writable_executable=yes\n");
        printf("extract_root=%s\n", root);
        printf("extract_root_noexec=%s\n", dir_is_noexec(root) ? "yes" : "no");
        printf("extract_root_free_space_ok=%s\n", enough_space_size(ep.present ? ep.size : 1, root) ? "yes" : "no");
        printf("extract_root_available_bytes=%llu\n", statvfs_available_bytes(root));
    } else {
        puts("extract_root_writable_executable=no");
    }
    printf("mem_available_kb=%llu\n", mem_available_kb());
    printf("devpts_available=%s\n", path_exists("/dev/pts") ? "yes" : "no");
    printf("ptrace_probe=%s\n", ptrace_probe_status());
    printf("default_route_present=%s\n", has_default_route() ? "yes" : "no");
    if (!path_exists("/dev/pts"))
        puts("recommendation=mount devpts for tmux/dropbear interactive sessions");
    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    print_autoexec_config();
    if (have_payload) {
        char ti[PATH_MAX];
        snprintf(ti, sizeof(ti), "%s/share/terminfo", payload);
        if (!path_exists(ti))
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
        read_first_line(hash_path, hash, sizeof(hash));
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
        printf("busybox_present=%s\n", executable_file(busybox) ? "yes" : "no");
        snprintf(manifest, sizeof(manifest), "%s/manifest.json", payload);
        if (path_exists(manifest)) {
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
