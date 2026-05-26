#define _POSIX_C_SOURCE 200809L

#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

#include "applets.h"
#include "runtime_config.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

/*
 * Minimal mkdir -p used for runtime-owned directories.  Existing directories
 * are accepted; callers still choose the permission mode appropriate for the
 * root they are creating.
 */
int bb_mkdir_p(const char *path, mode_t mode)
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

/*
 * Shared runtime-tree remover.  Callers are responsible for proving ownership
 * of the root they pass in; this helper intentionally performs only recursive
 * deletion mechanics and treats already-missing paths as clean.
 */
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

/*
 * Read small operator/runtime metadata files into caller-owned memory.  The
 * bound is part of the ownership contract: callers choose a maximum size and
 * receive NULL rather than a truncated buffer when the file is larger.
 */
char *bb_read_text_file(const char *path, size_t max_bytes)
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

int bb_read_first_line(const char *path, char *out, size_t outsz)
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

int bb_path_exists(const char *path)
{
    return access(path, F_OK) == 0;
}

int bb_executable_file(const char *path)
{
    return access(path, X_OK) == 0;
}

int bb_dir_is_noexec(const char *path)
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

unsigned long long bb_path_available_bytes(const char *path)
{
    struct statvfs v;

    if (statvfs(path, &v) != 0)
        return 0;
    return (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize;
}

int bb_path_entry_count(const char *path, const char *entry)
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

int bb_path_has_duplicate_entries(const char *path)
{
    char *outer, *save = NULL, *p;
    int dup = 0;

    if (!path)
        return 0;
    outer = strdup(path);
    if (!outer)
        return 0;
    for (p = strtok_r(outer, ":", &save); p; p = strtok_r(NULL, ":", &save)) {
        if (bb_path_entry_count(path, *p ? p : ".") > 1) {
            dup = 1;
            break;
        }
    }
    free(outer);
    return dup;
}

int bb_extract_root_usable(const char *path)
{
    if (!path || !path[0] || !bb_path_exists(path))
        return 0;
    if (access(path, W_OK | X_OK) != 0)
        return 0;
    return !bb_dir_is_noexec(path);
}

unsigned long long bb_extract_required_bytes(unsigned long long payload_size)
{
    unsigned long long need = payload_size * 4ULL;
    if (need < 8ULL * 1024ULL * 1024ULL)
        need = 8ULL * 1024ULL * 1024ULL;
    return need;
}

int bb_enough_space_for_extract(unsigned long long size, const char *root)
{
    struct statvfs v;
    unsigned long long free_bytes;

    if (statvfs(root, &v) != 0)
        return 1;
    free_bytes = (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize;
    return free_bytes > bb_extract_required_bytes(size);
}

/*
 * Select and create the runtime root used for payload extraction.  Successful
 * directory creation is ledgered because cleanup owns only BusierBox-created
 * runtime trees; callers receive the root path, not ownership of the ledger.
 */
int bb_choose_extract_root(char *out, size_t outsz)
{
    char path[PATH_MAX];
    const char *runtime_root = bb_config_get("BB_RUNTIME_ROOT");
    const char *fallback_enabled = bb_config_get("BB_RUNTIME_ALLOW_FALLBACK_ROOT");
    const char *fallback_root = bb_config_get("BB_RUNTIME_FALLBACK_ROOT");
    const char *roots[2];
    int i, nroots = 0;

    if (runtime_root && runtime_root[0])
        roots[nroots++] = runtime_root;
    if (fallback_enabled && !strcmp(fallback_enabled, "yes") &&
        fallback_root && fallback_root[0])
        roots[nroots++] = fallback_root;

    for (i = 0; i < nroots; i++) {
        if (!roots[i] || !roots[i][0])
            continue;
        snprintf(path, sizeof(path), "%s", roots[i]);
        if (bb_mkdir_p(path, 0700) != 0)
            continue;
        bb_ledger_record("mkdir", path, "runtime", "runtime root");
        if (!bb_extract_root_usable(path))
            continue;
        snprintf(out, outsz, "%s", path);
        return 0;
    }
    return -1;
}

static void print_extract_root_probe_json(FILE *out, const char *role, const char *path,
                                          unsigned long long payload_size, int selected,
                                          void (*json_string)(FILE *, const char *))
{
    int configured = path && path[0];
    int exists = configured && bb_path_exists(path);
    int writable = exists && access(path, W_OK) == 0;
    int executable = exists && access(path, X_OK) == 0;
    int noexec = exists && bb_dir_is_noexec(path);

    fprintf(out, "{\"role\":");
    json_string(out, role);
    fprintf(out, ",\"configured\":%s,\"path\":", configured ? "true" : "false");
    if (configured)
        json_string(out, path);
    else
        fputs("null", out);
    fprintf(out, ",\"exists\":%s,\"writable\":%s,\"executable\":%s,\"noexec\":%s",
            exists ? "true" : "false",
            writable ? "true" : "false",
            executable ? "true" : "false",
            noexec ? "true" : "false");
    fprintf(out, ",\"available_bytes\":%llu,\"free_space_ok\":%s,\"selected\":%s}",
            exists ? bb_path_available_bytes(path) : 0ULL,
            exists && bb_enough_space_for_extract(payload_size, path) ? "true" : "false",
            selected ? "true" : "false");
}

void bb_print_extraction_runtime_json(FILE *out, unsigned long long payload_size,
                                      void (*json_string)(FILE *, const char *))
{
    const char *runtime_root = bb_config_get("BB_RUNTIME_ROOT");
    const char *fallback_root = bb_config_get("BB_RUNTIME_FALLBACK_ROOT");
    const char *fallback_enabled_value = bb_config_get("BB_RUNTIME_ALLOW_FALLBACK_ROOT");
    const char *selected = NULL;
    int fallback_enabled = fallback_enabled_value && !strcmp(fallback_enabled_value, "yes");

    if (bb_extract_root_usable(runtime_root))
        selected = runtime_root;
    else if (fallback_enabled && bb_extract_root_usable(fallback_root))
        selected = fallback_root;

    fprintf(out, "{\"runtime_root\":");
    json_string(out, runtime_root ? runtime_root : "");
    fprintf(out, ",\"fallback_root\":");
    json_string(out, fallback_root ? fallback_root : "");
    fprintf(out, ",\"fallback_enabled\":%s,\"required_bytes\":%llu,\"writable_executable\":%s,\"selected_root\":",
            fallback_enabled ? "true" : "false",
            bb_extract_required_bytes(payload_size),
            selected ? "true" : "false");
    if (selected)
        json_string(out, selected);
    else
        fputs("null", out);
    fprintf(out, ",\"roots\":[");
    print_extract_root_probe_json(out, "runtime", runtime_root, payload_size,
                                  selected && runtime_root && !strcmp(selected, runtime_root), json_string);
    fputc(',', out);
    print_extract_root_probe_json(out, "fallback", fallback_root, payload_size,
                                  selected && fallback_root && !strcmp(selected, fallback_root), json_string);
    fprintf(out, "]}");
}
