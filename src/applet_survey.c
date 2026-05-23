#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <unistd.h>

#include "applets.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BUSIERBOX_VERSION
#define BUSIERBOX_VERSION "0.1.0-tier0"
#endif

static const char *dirs[] = {".", "/tmp", "/var/tmp", "/dev/shm", "/var"};

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static const char *endianness(void)
{
    unsigned int x = 1;
    return *((unsigned char *)&x) ? "little" : "big";
}

static int is_digits(const char *s)
{
    while (*s) {
        if (!isdigit((unsigned char)*s++))
            return 0;
    }
    return 1;
}

static int proc_count(void)
{
    DIR *d = opendir("/proc");
    struct dirent *de;
    int n = 0;
    if (!d)
        return -1;
    while ((de = readdir(d)) != NULL)
        if (is_digits(de->d_name))
            n++;
    closedir(d);
    return n;
}

static void print_meminfo_human(void)
{
    FILE *fp = fopen("/proc/meminfo", "r");
    char line[160];
    if (!fp) {
        printf("memory: unknown\n");
        return;
    }
    printf("memory:\n");
    while (fgets(line, sizeof(line), fp)) {
        if (!strncmp(line, "MemTotal:", 9) || !strncmp(line, "MemFree:", 8) ||
            !strncmp(line, "MemAvailable:", 13) || !strncmp(line, "SwapTotal:", 10) ||
            !strncmp(line, "SwapFree:", 9))
            printf("  %s", line);
    }
    fclose(fp);
}

static void print_netdev_human(void)
{
    FILE *fp = fopen("/proc/net/dev", "r");
    char line[256];
    int skip = 2;
    if (!fp) {
        printf("interfaces: unknown\n");
        return;
    }
    printf("interfaces:");
    while (fgets(line, sizeof(line), fp)) {
        char *colon, *name;
        if (skip) { skip--; continue; }
        colon = strchr(line, ':');
        if (!colon) continue;
        *colon = '\0';
        name = line;
        while (isspace((unsigned char)*name)) name++;
        printf(" %s", name);
    }
    printf("\n");
    fclose(fp);
}

static const char *mount_opts_for(const char *path, char *out, size_t outsz)
{
    FILE *fp = fopen("/proc/mounts", "r");
    char line[512], best[256] = "";
    size_t best_len = 0;
    out[0] = '\0';
    if (!fp)
        return NULL;
    while (fgets(line, sizeof(line), fp)) {
        char src[160], dst[PATH_MAX], type[64], opts[256];
        size_t len;
        if (sscanf(line, "%159s %4095s %63s %255s", src, dst, type, opts) != 4)
            continue;
        len = strlen(dst);
        if (!strncmp(path, dst, len) && len >= best_len && (path[len] == '/' || path[len] == '\0' || !strcmp(dst, "/"))) {
            best_len = len;
            strncpy(best, opts, sizeof(best) - 1);
            best[sizeof(best) - 1] = '\0';
        }
    }
    fclose(fp);
    if (!best_len)
        return NULL;
    snprintf(out, outsz, "%s", best);
    return out;
}

static void dir_human(const char *path)
{
    struct stat st;
    struct statvfs v;
    char opts[256];
    int exists = stat(path, &st) == 0;
    printf("  %-9s exists=%s writable=%s executable=%s",
           path, exists ? "yes" : "no",
           access(path, W_OK) == 0 ? "yes" : "no",
           access(path, X_OK) == 0 ? "yes" : "no");
    if (exists && statvfs(path, &v) == 0)
        printf(" free_bytes=%llu", (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize);
    if (mount_opts_for(path, opts, sizeof(opts)) && strstr(opts, "noexec"))
        printf(" noexec=yes");
    printf("\n");
}

static void mounts_human(void)
{
    FILE *fp = fopen("/proc/mounts", "r");
    char line[512];
    int count = 0;
    if (!fp) {
        printf("mounts: unreadable\n");
        return;
    }
    printf("mounts:\n");
    while (fgets(line, sizeof(line), fp) && count++ < 16) {
        char src[160], dst[160], type[64], opts[160];
        if (sscanf(line, "%159s %159s %63s %159s", src, dst, type, opts) == 4)
            printf("  %s on %s type %s (%s)\n", src, dst, type, opts);
    }
    if (!feof(fp))
        printf("  ...\n");
    fclose(fp);
}

static const char *recommended_extract_dir(void)
{
    size_t i;
    for (i = 0; i < sizeof(dirs) / sizeof(dirs[0]); i++)
        if (access(dirs[i], W_OK | X_OK) == 0)
            return dirs[i];
    return "none";
}

static void json_string(const char *s)
{
    putchar('"');
    if (s) {
        while (*s) {
            unsigned char c = (unsigned char)*s++;
            if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
            else if (c == '\n') fputs("\\n", stdout);
            else if (c == '\r') fputs("\\r", stdout);
            else if (c == '\t') fputs("\\t", stdout);
            else if (c < 32) printf("\\u%04x", c);
            else putchar(c);
        }
    }
    putchar('"');
}

static void json_meminfo(void)
{
    FILE *fp = fopen("/proc/meminfo", "r");
    char key[64], unit[32], line[160];
    unsigned long val;
    int first = 1;
    putchar('{');
    if (fp) {
        while (fgets(line, sizeof(line), fp)) {
            if (sscanf(line, "%63[^:]: %lu %31s", key, &val, unit) >= 2) {
                if (!first) putchar(',');
                json_string(key);
                printf(":%lu", val);
                first = 0;
            }
        }
        fclose(fp);
    }
    putchar('}');
}

static void json_netdev(void)
{
    FILE *fp = fopen("/proc/net/dev", "r");
    char line[256];
    int skip = 2, first = 1;
    putchar('[');
    if (fp) {
        while (fgets(line, sizeof(line), fp)) {
            char *colon, *name;
            if (skip) { skip--; continue; }
            colon = strchr(line, ':');
            if (!colon) continue;
            *colon = '\0';
            name = line;
            while (isspace((unsigned char)*name)) name++;
            if (!first) putchar(',');
            json_string(name);
            first = 0;
        }
        fclose(fp);
    }
    putchar(']');
}

static void json_dirs(void)
{
    size_t i;
    putchar('[');
    for (i = 0; i < sizeof(dirs) / sizeof(dirs[0]); i++) {
        struct stat st;
        struct statvfs v;
        char opts[256];
        int exists = stat(dirs[i], &st) == 0;
        if (i) putchar(',');
        printf("{\"path\":"); json_string(dirs[i]);
        printf(",\"exists\":%s,\"writable\":%s,\"executable\":%s",
               exists ? "true" : "false",
               access(dirs[i], W_OK) == 0 ? "true" : "false",
               access(dirs[i], X_OK) == 0 ? "true" : "false");
        if (exists && statvfs(dirs[i], &v) == 0)
            printf(",\"free_bytes\":%llu", (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize);
        else
            printf(",\"free_bytes\":null");
        printf(",\"noexec\":%s", (mount_opts_for(dirs[i], opts, sizeof(opts)) && strstr(opts, "noexec")) ? "true" : "false");
        putchar('}');
    }
    putchar(']');
}

static void json_mounts(void)
{
    FILE *fp = fopen("/proc/mounts", "r");
    char line[512];
    int first = 1, count = 0;
    putchar('[');
    if (fp) {
        while (fgets(line, sizeof(line), fp) && count++ < 32) {
            char src[160], dst[160], type[64], opts[160];
            if (sscanf(line, "%159s %159s %63s %159s", src, dst, type, opts) != 4)
                continue;
            if (!first) putchar(',');
            printf("{\"source\":"); json_string(src);
            printf(",\"target\":"); json_string(dst);
            printf(",\"type\":"); json_string(type);
            printf(",\"options\":"); json_string(opts);
            printf(",\"noexec\":%s}", strstr(opts, "noexec") ? "true" : "false");
            first = 0;
        }
        fclose(fp);
    }
    putchar(']');
}

static const char *ptrace_status(void)
{
    return "unknown";
}

int applet_survey_main(int argc, char **argv)
{
    struct utsname uts;
    char cwd[PATH_MAX];
    const char *path = getenv("PATH"), *home = getenv("HOME"), *term = getenv("TERM");
    int json = argc > 1 && !strcmp(argv[1], "--json");
    int pc;

    if (is_help(argc, argv)) {
        puts("usage: busierbox survey [--json]");
        puts("Print embedded Linux target triage.");
        return 0;
    }
    if (uname(&uts) != 0)
        memset(&uts, 0, sizeof(uts));
    if (!getcwd(cwd, sizeof(cwd)))
        snprintf(cwd, sizeof(cwd), "unknown");
    pc = proc_count();

    if (json) {
        printf("{\"busierbox\":{\"version\":"); json_string(BUSIERBOX_VERSION);
        printf(",\"build_date\":"); json_string(__DATE__ " " __TIME__);
        printf("},\"uname\":{\"sysname\":"); json_string(uts.sysname);
        printf(",\"nodename\":"); json_string(uts.nodename);
        printf(",\"release\":"); json_string(uts.release);
        printf(",\"version\":"); json_string(uts.version);
        printf(",\"machine\":"); json_string(uts.machine);
        printf("},\"arch\":"); json_string(uts.machine);
        printf(",\"kernel\":"); json_string(uts.release);
        printf(",\"endianness\":"); json_string(endianness());
        printf(",\"pointer_width\":%lu", (unsigned long)(sizeof(void *) * 8));
        printf(",\"ids\":{\"uid\":%ld,\"euid\":%ld,\"gid\":%ld,\"egid\":%ld}",
               (long)getuid(), (long)geteuid(), (long)getgid(), (long)getegid());
        printf(",\"cwd\":"); json_string(cwd);
        printf(",\"env\":{\"PATH\":"); json_string(path ? path : "");
        printf(",\"HOME\":"); json_string(home ? home : "");
        printf(",\"TERM\":"); json_string(term ? term : "");
        printf("},\"proc_exists\":%s,\"devpts_exists\":%s",
               access("/proc", F_OK) == 0 ? "true" : "false",
               access("/dev/pts", F_OK) == 0 ? "true" : "false");
        printf(",\"dirs\":"); json_dirs();
        printf(",\"writable_dirs\":"); json_dirs();
        printf(",\"mounts\":"); json_mounts();
        printf(",\"process_count\":"); pc >= 0 ? printf("%d", pc) : printf("null");
        printf(",\"meminfo\":"); json_meminfo();
        printf(",\"interfaces\":"); json_netdev();
        printf(",\"ptrace\":"); json_string(ptrace_status());
        printf(",\"recommendations\":{\"zero_write_supported\":true,\"payload_mode_possible\":%s,\"likely_tmux_supported\":%s,\"likely_strace_supported\":%s,\"likely_gdbserver_supported\":%s,\"recommended_extract_dir\":",
               strcmp(recommended_extract_dir(), "none") ? "true" : "false",
               access("/dev/pts", F_OK) == 0 ? "true" : "false",
               !strcmp(ptrace_status(), "basic-ok") ? "true" : "false",
               !strcmp(ptrace_status(), "basic-ok") ? "true" : "false");
        json_string(recommended_extract_dir());
        printf("}}\n");
        return 0;
    }

    printf("busierbox: version=%s build=%s %s\n", BUSIERBOX_VERSION, __DATE__, __TIME__);
    printf("uname: %s %s %s %s %s\n", uts.sysname, uts.nodename, uts.release, uts.version, uts.machine);
    printf("arch: %s\nendianness: %s\npointer_width: %lu\n", uts.machine, endianness(), (unsigned long)(sizeof(void *) * 8));
    printf("uid: %ld euid: %ld gid: %ld egid: %ld\n", (long)getuid(), (long)geteuid(), (long)getgid(), (long)getegid());
    printf("cwd: %s\nPATH: %s\nHOME: %s\nTERM: %s\n", cwd, path ? path : "", home ? home : "", term ? term : "");
    printf("proc: %s\ndevpts: %s\n", access("/proc", F_OK) == 0 ? "exists" : "missing", access("/dev/pts", F_OK) == 0 ? "exists" : "missing");
    printf("dirs:\n");
    for (size_t i = 0; i < sizeof(dirs) / sizeof(dirs[0]); i++)
        dir_human(dirs[i]);
    mounts_human();
    printf("process_count: %s", pc >= 0 ? "" : "unknown\n");
    if (pc >= 0) printf("%d\n", pc);
    print_meminfo_human();
    print_netdev_human();
    printf("ptrace: %s\n", ptrace_status());
    printf("recommendations:\n");
    printf("  zero_write_supported: yes\n");
    printf("  payload_mode_possible: %s\n", strcmp(recommended_extract_dir(), "none") ? "yes" : "no");
    printf("  likely_tmux_supported: %s\n", access("/dev/pts", F_OK) == 0 ? "yes" : "unknown");
    printf("  likely_strace_supported: %s\n", !strcmp(ptrace_status(), "basic-ok") ? "yes" : "unknown");
    printf("  likely_gdbserver_supported: %s\n", !strcmp(ptrace_status(), "basic-ok") ? "yes" : "unknown");
    printf("  recommended_extract_dir: %s\n", recommended_extract_dir());
    return 0;
}
