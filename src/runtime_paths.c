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
