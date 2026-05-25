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
#ifndef BB_OPERATOR_TARGET_DROPBEAR_PORT
#define BB_OPERATOR_TARGET_DROPBEAR_PORT "2222"
#endif

#define BBX_TRAILER_SIZE 512
#define BBX_MAGIC "BBXPAYLOADv1"
#define BBX_PAYLOAD_ID_FILE ".busierbox-payload-id"

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

static int rm_rf(const char *path);
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

static void json_string_payload(FILE *out, const char *s)
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

static const char *ledger_path(char *out, size_t outsz)
{
    snprintf(out, outsz, "%s/run/cleanup-ledger.jsonl", BB_RUNTIME_ROOT);
    return out;
}

static void ledger_record(const char *op, const char *path, const char *scope, const char *detail)
{
    char run_dir[PATH_MAX], ledger[PATH_MAX];
    FILE *fp;
    time_t now = time(NULL);

    snprintf(run_dir, sizeof(run_dir), "%s/run", BB_RUNTIME_ROOT);
    if (mkdir_p(run_dir, 0700) != 0)
        return;
    fp = fopen(ledger_path(ledger, sizeof(ledger)), "a");
    if (!fp)
        return;
    fputs("{\"op\":", fp);
    json_string_payload(fp, op);
    fputs(",\"path\":", fp);
    json_string_payload(fp, path);
    fputs(",\"scope\":", fp);
    json_string_payload(fp, scope ? scope : "runtime");
    fprintf(fp, ",\"ts\":%ld", (long)now);
    if (detail && *detail) {
        fputs(",\"detail\":", fp);
        json_string_payload(fp, detail);
    }
    fputs("}\n", fp);
    fclose(fp);
}

static int path_exists(const char *path)
{
    return access(path, F_OK) == 0;
}

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
        ledger_record("mkdir", path, "runtime", "runtime root");
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

static int enough_space_size(unsigned long long size, const char *root)
{
    struct statvfs v;
    unsigned long long free_bytes, need_bytes;
    if (statvfs(root, &v) != 0)
        return 1;
    free_bytes = (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize;
    need_bytes = size * 4ULL;
    if (need_bytes < 8ULL * 1024ULL * 1024ULL)
        need_bytes = 8ULL * 1024ULL * 1024ULL;
    return free_bytes > need_bytes;
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

static int tar_extract_stream(struct payload_stream *s, const char *root)
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
        if (type == '5') {
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

static int extract_embedded_to_root(const struct embedded_payload *ep, const char *root)
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
        if (payload_valid(final))
            return 0;
        if (++waits > 30) {
            rmdir(lock);
            waits = 0;
        }
    }
    rm_rf(tmp);
    if (mkdir_p(tmp, 0700) != 0) {
        rmdir(lock);
        return -1;
    }

    if (verify_embedded_hash(ep) != 0) {
        rm_rf(tmp);
        rmdir(lock);
        fprintf(stderr, "extract: embedded payload sha256 mismatch\n");
        return -1;
    }
    fp = fopen(ep->exe, "rb");
    if (!fp || fseek(fp, (long)ep->offset, SEEK_SET) != 0) {
        if (fp)
            fclose(fp);
        rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    if (!strcmp(ep->format, "tar"))
        rc = stream_init_tar(&s, fp, ep->size);
    else
        rc = stream_init_tgz(&s, fp, ep->size);
    if (rc == 0)
        rc = tar_extract_stream(&s, tmp);
    stream_end(&s);
    fclose(fp);
    if (rc != 0) {
        rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    if (!payload_valid(extracted)) {
        rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    rm_rf(final);
    if (rename(extracted, final) != 0) {
        rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    rm_rf(tmp);
    rmdir(lock);
    write_payload_id(ep, final);
    ledger_record("extract", root, "payload", "embedded payload extracted");
    ledger_record("write", final, "payload", "payload root");
    return 0;
}

static int extract_archive_file_to_root(const char *archive, const char *root)
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
        rm_rf(tmp);
        if (mkdir_p(tmp, 0700) == 0)
            rc = tar_extract_stream(&s, tmp);
        else
            rc = -1;
        if (rc == 0 && payload_valid(extracted)) {
            rm_rf(final);
            rc = rename(extracted, final);
            if (rc == 0) {
                ledger_record("extract", root, "payload", "archive payload extracted");
                ledger_record("write", final, "payload", "payload root");
            }
        } else {
            rc = -1;
        }
        rm_rf(tmp);
    }
    stream_end(&s);
    fclose(fp);
    return rc;
}

static int ensure_payload(char *payload, size_t payloadsz)
{
    char archive[PATH_MAX], root[PATH_MAX];
    struct embedded_payload ep;
    int have_ep = (get_embedded_payload(&ep) == 0);

    if (!strcmp(BB_RUNTIME_MODE, "core-only"))
        return -1;

    if (candidate_payload(payload, payloadsz) == 0) {
        if (have_ep && !payload_id_matches(&ep, payload)) {
            fprintf(stderr, "busierbox: extracted payload is from a different binary; re-extracting...\n");
            rm_rf(payload);
            /* fall through to extract */
        } else {
            return 0;
        }
    }
    if (choose_extract_root(root, sizeof(root)) != 0)
        return -1;
    if (have_ep) {
        if (extract_embedded_to_root(&ep, root) != 0)
            return -1;
    } else {
        if (archive_path(archive, sizeof(archive)) != 0)
            return -1;
        fprintf(stderr, "busierbox: warning: using dev-only external payload archive fallback: %s\n", archive);
        if (extract_archive_file_to_root(archive, root) != 0)
            return -1;
    }
    snprintf(payload, payloadsz, "%s/payload", root);
    return payload_valid(payload) ? 0 : -1;
}

int bb_ensure_payload_dir(char *payload, size_t payloadsz)
{
    return ensure_payload(payload, payloadsz);
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

static int exec_payload_command(const char *path, char **argv, const char *payload)
{
    pid_t pid;
    int status;
    char root[PATH_MAX];

    if (strcmp(BB_RUNTIME_MODE, "no-residue") != 0)
        return execv_alloc(path, argv);

    pid = fork();
    if (pid < 0) {
        fprintf(stderr, "busierbox: fork %s failed: %s\n", path, strerror(errno));
        return 1;
    }
    if (pid == 0) {
        execv(path, argv);
        fprintf(stderr, "busierbox: exec %s failed: %s\n", path, strerror(errno));
        _exit(errno == ENOENT ? 127 : 126);
    }
    if (waitpid(pid, &status, 0) < 0)
        return 1;
    payload_root_from_payload(payload, root, sizeof(root));
    if (root[0] && (!strcmp(root, BB_RUNTIME_ROOT) || !strcmp(root, BB_RUNTIME_FALLBACK_ROOT))) {
        ledger_record("remove", root, "runtime", "no-residue foreground payload command");
        rm_rf(root);
    }
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

    if (ensure_payload(payload, sizeof(payload)) != 0) {
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
        if (!strcmp(name, "zsh"))
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

int applet_manifest_main(int argc, char **argv)
{
    int json = argc > 1 && !strcmp(argv[1], "--json");
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox manifest [--json]");
        puts("Print artifact and preset metadata embedded in this BusierBox binary.");
        return 0;
    }

    if (json) {
        printf("{\"schema\":1,\"busierbox\":{\"payload_version\":");
        json_string_payload(stdout, BUSIERBOX_PAYLOAD_VERSION);
        printf(",\"artifact_tier\":");
        json_string_payload(stdout, BUSIERBOX_ARTIFACT_TIER);
        printf("},\"runtime\":{\"mode\":");
        json_string_payload(stdout, BB_RUNTIME_MODE);
        printf(",\"root\":");
        json_string_payload(stdout, BB_RUNTIME_ROOT);
        printf(",\"allow_fallback_root\":");
        json_string_payload(stdout, BB_RUNTIME_ALLOW_FALLBACK_ROOT);
        printf(",\"fallback_root\":");
        json_string_payload(stdout, BB_RUNTIME_FALLBACK_ROOT);
        printf("},\"zero_arg\":{\"mode\":");
        json_string_payload(stdout, BB_ZERO_ARG_MODE);
        printf(",\"log_mode\":");
        json_string_payload(stdout, BB_ZERO_ARG_LOG_MODE);
        printf("},\"rshell\":{\"transport\":");
        json_string_payload(stdout, BB_RSHELL_TRANSPORT);
        printf(",\"encryption\":");
        json_string_payload(stdout, BB_RSHELL_ENCRYPTION);
        printf(",\"run_mode\":");
        json_string_payload(stdout, BB_RSHELL_RUN_MODE);
        printf(",\"shell_provider\":");
        json_string_payload(stdout, BB_RSHELL_SHELL_PROVIDER);
        printf("},\"native_features\":{\"survey\":%s,\"doctor\":%s,\"extract\":%s,\"config_info\":%s",
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
        printf(",\"wolfssl\":true");
#else
        printf(",\"wolfssl\":false");
#endif
        printf("},\"payload_tools\":{\"busybox_applets\":[");
        for (i = 0; busybox_tools[i]; i++) {
            if (i)
                putchar(',');
            json_string_payload(stdout, busybox_tools[i]);
        }
        printf("],\"heavy_tools\":[");
        for (i = 0; heavy_tools[i]; i++) {
            if (i)
                putchar(',');
            json_string_payload(stdout, heavy_tools[i]);
        }
        printf("]}}\n");
        return 0;
    }

    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    printf("payload_version=%s\n", BUSIERBOX_PAYLOAD_VERSION);
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
            rm_rf(old_payload);
        }
    }
    if (!force && candidate_payload(payload, sizeof(payload)) == 0) {
        printf("payload: reuse %s\n", payload);
        return 0;
    }
    if (choose_extract_root(root, sizeof(root)) != 0) {
        fprintf(stderr, "extract: no writable executable runtime directory found\n");
        return 1;
    }
    if (get_embedded_payload(&ep) == 0) {
        if (extract_embedded_to_root(&ep, root) != 0) {
            fprintf(stderr, "extract: embedded payload extraction failed\n");
            return 1;
        }
    } else {
        if (archive_path(archive, sizeof(archive)) != 0) {
            fprintf(stderr, "extract: no embedded payload found and no dev fallback archive found\n");
            return 1;
        }
        fprintf(stderr, "extract: warning: using dev-only external payload archive fallback: %s\n", archive);
        if (extract_archive_file_to_root(archive, root) != 0) {
            fprintf(stderr, "extract: archive extraction failed for %s\n", archive);
            return 1;
        }
    }
    snprintf(payload, sizeof(payload), "%s/payload", root);
    if (!payload_valid(payload)) {
        fprintf(stderr, "extract: extracted payload failed validation\n");
        return 1;
    }
    printf("payload: extracted %s\n", payload);
    return 0;
}

static int rm_rf(const char *path)
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
            if (rm_rf(child) != 0) {
                closedir(d);
                return -1;
            }
        }
        closedir(d);
        return rmdir(path);
    }
    return unlink(path);
}

static void print_ledger_human(void)
{
    char path[PATH_MAX], line[1024];
    FILE *fp = fopen(ledger_path(path, sizeof(path)), "r");
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
    FILE *fp = fopen(ledger_path(path, sizeof(path)), "r");

    printf("Would remove:\n");
    printf("  %s\n", BB_RUNTIME_ROOT);
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

static int clean_external_from_ledger(void)
{
    char ledger[PATH_MAX], line[2048];
    FILE *fp = fopen(ledger_path(ledger, sizeof(ledger)), "r");
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
            } else {
                printf("clean: removed BusierBox rshell block from %s\n", path);
            }
        } else if (!strcmp(path, "/root/.ssh/authorized_keys") &&
                   !strcmp(op, "write") && !strcmp(mode, "root-copy")) {
            if (unlink(path) != 0 && errno != ENOENT) {
                fprintf(stderr, "clean: failed to remove %s: %s\n", path, strerror(errno));
                failures = 1;
            } else {
                printf("clean: removed external %s\n", path);
            }
        } else if (!strcmp(op, "backup") &&
                   !strncmp(path, "/root/.ssh/authorized_keys.busierbox.bak.", 41)) {
            if (unlink(path) != 0 && errno != ENOENT) {
                fprintf(stderr, "clean: failed to remove backup %s: %s\n", path, strerror(errno));
                failures = 1;
            } else {
                printf("clean: removed external backup %s\n", path);
            }
        }
    }
    fclose(fp);
    return failures ? -1 : 0;
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

    fp = fopen(ledger_path(path, sizeof(path)), "r");
    if (!json) {
        print_ledger_human();
        return 0;
    }
    printf("{\"schema\":1,\"path\":");
    json_string_payload(stdout, path);
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
    int dry_run = 0, ledger = 0, external = 0, apply = 0;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox clean [--dry-run] [--ledger] [--external --apply]");
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
        else {
            fprintf(stderr, "clean: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (dry_run)
        return print_clean_dry_run(external);
    if (external && !apply) {
        fputs("clean: external cleanup requires --external --apply\n", stderr);
        return 2;
    }
    if (external && apply && clean_external_from_ledger() != 0)
        return 1;
    if (ledger)
        ledger_record("remove", BB_RUNTIME_ROOT, "runtime", "clean --ledger");
    if (rm_rf(BB_RUNTIME_ROOT) != 0) {
        fprintf(stderr, "clean: %s\n", strerror(errno));
        return 1;
    }
    printf("clean: removed %s\n", BB_RUNTIME_ROOT);
    return 0;
}

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

static int copy_self_to(const char *dst)
{
    char src[PATH_MAX];
    FILE *in, *out;
    char buf[8192];
    size_t n;
    ssize_t len = readlink("/proc/self/exe", src, sizeof(src) - 1);
    if (len < 0) {
        if (!saved_argv0 || !*saved_argv0)
            return -1;
        snprintf(src, sizeof(src), "%s", saved_argv0);
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

static int append_recovery_block(const char *path, const char *method, const char *name)
{
    FILE *fp = fopen(path, "a");
    if (!fp)
        return -1;
    fprintf(fp, "\n# BEGIN BUSIERBOX RECOVERY %s\n", name);
    fprintf(fp, "# method=%s; authorized lab recovery hook\n", method);
    if (!strcmp(method, "cron-reboot"))
        fprintf(fp, "@reboot /usr/bin/%s recovery status >/dev/null 2>&1\n", name);
    else if (!strcmp(method, "systemd-unit")) {
        fprintf(fp, "[Unit]\nDescription=BusierBox authorized lab recovery\n[Service]\nType=oneshot\nExecStart=/usr/bin/%s recovery status\n[Install]\nWantedBy=multi-user.target\n", name);
    } else {
        fprintf(fp, "/usr/bin/%s recovery status >/dev/null 2>&1 || true\n", name);
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

static int recovery_status_one(const char *root, const struct recovery_method *m, const char *name)
{
    char path[PATH_MAX];
    char marker[256];
    char *text;
    recovery_join(path, sizeof(path), root, m->path);
    snprintf(marker, sizeof(marker), "BEGIN BUSIERBOX RECOVERY %s", name);
    text = read_text_file(path, 1024 * 1024);
    if (!text)
        return 0;
    if (strstr(text, marker)) {
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
        json_string_payload(stdout, root);
        fputs(",\"storage\":[", stdout);
        for (i = 0; i < sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]); i++) {
            char path[PATH_MAX];
            recovery_join(path, sizeof(path), root, recovery_storage_paths[i].path + 1);
            printf("%s{\"path\":", i ? "," : "");
            json_string_payload(stdout, path);
            fputs(",\"class\":", stdout); json_string_payload(stdout, recovery_storage_paths[i].class_name);
            fputs(",\"survives_reboot\":", stdout); json_string_payload(stdout, recovery_storage_paths[i].survives_reboot);
            printf(",\"present\":%s,\"writable\":%s", path_exists(path) ? "true" : "false", access(path, W_OK) == 0 ? "true" : "false");
            fputs(",\"notes\":", stdout); json_string_payload(stdout, recovery_storage_paths[i].notes);
            fputc('}', stdout);
        }
        fputs("],\"methods\":[", stdout);
        for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
            char path[PATH_MAX];
            recovery_join(path, sizeof(path), root, recovery_methods[i].path);
            printf("%s{\"name\":", i ? "," : "");
            json_string_payload(stdout, recovery_methods[i].name);
            fputs(",\"kind\":", stdout); json_string_payload(stdout, recovery_methods[i].kind);
            fputs(",\"path\":", stdout); json_string_payload(stdout, path);
            printf(",\"present\":%s", path_exists(path) ? "true" : "false");
            fputs(",\"survives_reboot\":", stdout); json_string_payload(stdout, recovery_methods[i].survives_reboot);
            fputs(",\"intrusiveness\":", stdout); json_string_payload(stdout, recovery_methods[i].intrusiveness);
            fputs(",\"reversibility\":", stdout); json_string_payload(stdout, recovery_methods[i].reversibility);
            fputs(",\"requires_external_write\":", stdout); json_string_payload(stdout, recovery_methods[i].requires_external_write);
            fputc('}', stdout);
        }
        puts("]}");
        return;
    }
    printf("recovery_root=%s\n", root);
    puts("recovery_policy=survey and plan never modify the target; install requires --method and --apply");
    puts("recovery_storage:");
    for (i = 0; i < sizeof(recovery_storage_paths) / sizeof(recovery_storage_paths[0]); i++) {
        char path[PATH_MAX];
        recovery_join(path, sizeof(path), root, recovery_storage_paths[i].path + 1);
        printf("%s\tclass=%s\tpresent=%s\twritable=%s\tsurvives=%s\t%s\n",
               path, recovery_storage_paths[i].class_name, path_exists(path) ? "yes" : "no",
               access(path, W_OK) == 0 ? "yes" : "no", recovery_storage_paths[i].survives_reboot,
               recovery_storage_paths[i].notes);
    }
    puts("recovery_methods:");
    for (i = 0; i < sizeof(recovery_methods) / sizeof(recovery_methods[0]); i++) {
        char path[PATH_MAX];
        recovery_join(path, sizeof(path), root, recovery_methods[i].path);
        printf("%s\tpath=%s\tpresent=%s\tsurvives=%s\tintrusive=%s\treversible=%s\n",
               recovery_methods[i].name, path, path_exists(path) ? "yes" : "no",
               recovery_methods[i].survives_reboot, recovery_methods[i].intrusiveness,
               recovery_methods[i].reversibility);
    }
}

static int applet_recovery_install(int argc, char **argv, int uninstall)
{
    const char *root = "/";
    const char *method = NULL;
    const char *name = BB_RECOVERY_BINARY_NAME;
    int dry_run = 0, apply = 0, external = 0;
    const struct recovery_method *m;
    char hook[PATH_MAX], bin[PATH_MAX], bindir[PATH_MAX], backup[PATH_MAX];
    int backup_status;
    int i;

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
        else if (!strcmp(argv[i], "--name") && i + 1 < argc)
            name = argv[++i];
        else {
            fprintf(stderr, "recovery: unknown or incomplete option %s\n", argv[i]);
            return 2;
        }
    }
    if (!method) {
        fputs("recovery: install/uninstall requires --method\n", stderr);
        return 2;
    }
    m = find_recovery_method(method);
    if (!m) {
        fprintf(stderr, "recovery: unsupported method %s\n", method);
        return 2;
    }
    recovery_join(hook, sizeof(hook), root, m->path);
    recovery_bin_path(bin, sizeof(bin), root, name);
    snprintf(bindir, sizeof(bindir), "%s", bin);
    {
        char *slash = strrchr(bindir, '/');
        if (slash)
            *slash = '\0';
    }
    if (!dry_run && !apply) {
        fputs("recovery: modifying actions require --apply; use --dry-run to preview\n", stderr);
        return 2;
    }
    if (!strcmp(root, "/") && apply && !external) {
        fputs("recovery: real-root install/uninstall requires --external --apply\n", stderr);
        return 2;
    }
    if (dry_run) {
        printf("Would %s recovery method=%s name=%s root=%s\n", uninstall ? "uninstall" : "install", method, name, root);
        printf("Would %s binary: %s\n", uninstall ? "remove" : "copy self to", bin);
        printf("Would %s hook: %s\n", uninstall ? "remove marked block/file" : "write marked hook", hook);
        if (!uninstall && path_exists(hook))
            printf("Would backup existing hook before modification: %s.busierbox.bak.<timestamp>\n", hook);
        return 0;
    }
    if (uninstall) {
        ledger_record("remove", hook, !strcmp(root, "/") ? "external" : "recovery-fakeroot", "recovery uninstall hook");
        ledger_record("remove", bin, !strcmp(root, "/") ? "external" : "recovery-fakeroot", "recovery uninstall binary");
        remove_recovery_block(hook, name);
        unlink(bin);
        printf("recovery: uninstalled method=%s name=%s\n", method, name);
        return 0;
    }
    if (mkdir_p(bindir, 0755) != 0) {
        fprintf(stderr, "recovery: cannot create %s: %s\n", bindir, strerror(errno));
        return 1;
    }
    if (copy_self_to(bin) != 0) {
        fprintf(stderr, "recovery: cannot copy binary to %s: %s\n", bin, strerror(errno));
        return 1;
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
        fprintf(stderr, "recovery: cannot backup hook %s: %s\n", hook, strerror(errno));
        return 1;
    }
    if (backup_status > 0)
        ledger_record("backup", backup, !strcmp(root, "/") ? "external" : "recovery-fakeroot", hook);
    if (append_recovery_block(hook, method, name) != 0) {
        fprintf(stderr, "recovery: cannot write hook %s: %s\n", hook, strerror(errno));
        return 1;
    }
    chmod(hook, 0755);
    ledger_record("write", bin, !strcmp(root, "/") ? "external" : "recovery-fakeroot", "recovery binary");
    ledger_record("modify", hook, !strcmp(root, "/") ? "external" : "recovery-fakeroot", backup_status > 0 ? backup : "recovery marked hook");
    printf("recovery: installed method=%s name=%s\n", method, name);
    return 0;
}

int applet_recovery_main(int argc, char **argv)
{
    const char *cmd = argc > 1 ? argv[1] : "--help";
    const char *root = "/";
    const char *name = BB_RECOVERY_BINARY_NAME;
    int json = 0;
    int i;

    if (is_help(argc, argv) || !strcmp(cmd, "--help")) {
        puts("usage: busierbox recovery --survey|--plan [--json] [--root ROOT]");
        puts("       busierbox recovery status [--root ROOT] [--name NAME]");
        puts("       busierbox recovery install --method METHOD --dry-run|--apply [--external] [--root ROOT] [--name NAME]");
        puts("       busierbox recovery uninstall --method METHOD --dry-run|--apply [--external] [--root ROOT] [--name NAME]");
        puts("Recovery is authorized lab recovery only. Survey and plan never modify the target.");
        return 0;
    }
    if (!strcmp(cmd, "install"))
        return applet_recovery_install(argc, argv, 0);
    if (!strcmp(cmd, "uninstall"))
        return applet_recovery_install(argc, argv, 1);

    for (i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--root") && i + 1 < argc)
            root = argv[++i];
        else if (!strcmp(argv[i], "--name") && i + 1 < argc)
            name = argv[++i];
        else {
            fprintf(stderr, "recovery: unknown or incomplete option %s\n", argv[i]);
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
            puts("recovery_plan=choose one explicit method, run install --dry-run, then install --apply only when authorized");
        return 0;
    }
    if (!strcmp(cmd, "status")) {
        size_t j;
        int found = 0;
        for (j = 0; j < sizeof(recovery_methods) / sizeof(recovery_methods[0]); j++) {
            if (recovery_status_one(root, &recovery_methods[j], name)) {
                printf("installed_method=%s\n", recovery_methods[j].name);
                found = 1;
            }
        }
        if (!found)
            puts("installed=no");
        return 0;
    }
    fprintf(stderr, "recovery: unknown command %s\n", cmd);
    return 2;
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

int applet_doctor_main(int argc, char **argv)
{
    struct embedded_payload ep;
    char payload[PATH_MAX], manifest_path[PATH_MAX], busybox[PATH_MAX];
    char root[PATH_MAX];
    char *manifest = NULL;
    int have_payload = 0;
    int applet_count = 0;

    memset(&ep, 0, sizeof(ep));

    if (is_help(argc, argv)) {
        puts("usage: busierbox doctor");
        puts("Reports embedded payload, extraction, BusyBox, and staged tool health.");
        return 0;
    }

    if (get_embedded_payload(&ep) == 0) {
        printf("embedded_payload=yes\n");
        printf("embedded_format=%s\n", ep.format);
        printf("embedded_size=%llu\n", ep.size);
        printf("embedded_sha256=%s\n", ep.sha256);
        printf("embedded_version=%s\n", ep.version);
        printf("embedded_hash_ok=%s\n", verify_embedded_hash(&ep) == 0 ? "yes" : "no");
    } else {
        puts("embedded_payload=no");
    }

    if (candidate_payload(payload, sizeof(payload)) == 0) {
        have_payload = 1;
        printf("extracted_payload=yes\n");
        printf("payload_dir=%s\n", payload);
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
    have_embedded = get_embedded_payload(&ep) == 0;
    have_payload = candidate_payload(payload, sizeof(payload)) == 0;
    printf("embedded_payload=%s\n", have_embedded ? "yes" : "no");
    printf("payload_version=%s\n", BUSIERBOX_PAYLOAD_VERSION);
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
