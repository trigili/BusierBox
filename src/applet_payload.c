#define _POSIX_C_SOURCE 200809L

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "applets.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BUSIERBOX_PAYLOAD_VERSION
#define BUSIERBOX_PAYLOAD_VERSION "dev"
#endif

static const char *heavy_tools[] = {"zsh", "tmux", "strace", "gdbserver", "dropbear", "curl", NULL};
static const char *busybox_tools[] = {
    "sh", "ash", "cat", "ls", "cp", "mv", "rm", "mkdir", "chmod", "touch",
    "dd", "uname", "id", "which", "readlink", "stat", "df", "free", "ps",
    "mount", "env", "grep", "sleep", "tee", "tar", "gzip", "nc",
    "sed", "awk", "find", "xargs", "dmesg", "ifconfig", "ip",
    "netstat", "ping", "wget", NULL
};

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static int rm_rf(const char *path);

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

static int candidate_payload(char *out, size_t outsz)
{
    const char *env = getenv("BUSIERBOX_PAYLOAD_DIR");
    char exe_dir[PATH_MAX];
    char path[PATH_MAX];
    uid_t uid = getuid();

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

    snprintf(path, sizeof(path), ".busierbox/payload");
    if (payload_valid(path)) {
        snprintf(out, outsz, "%s", path);
        return 0;
    }
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
    return -1;
}

static int archive_path(char *out, size_t outsz)
{
    char exe_dir[PATH_MAX], path[PATH_MAX];

    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(path, sizeof(path), "%s/payload.tar.gz", exe_dir);
        if (path_exists(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }
    if (path_exists("dist/payload.tar.gz")) {
        snprintf(out, outsz, "%s", "dist/payload.tar.gz");
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
    uid_t uid = getuid();
    const char *roots[] = {".busierbox", NULL, NULL, NULL};
    char tmp[PATH_MAX], vartmp[PATH_MAX], shm[PATH_MAX];
    int i;

    snprintf(tmp, sizeof(tmp), "/tmp/busierbox-%ld", (long)uid);
    snprintf(vartmp, sizeof(vartmp), "/var/tmp/busierbox-%ld", (long)uid);
    snprintf(shm, sizeof(shm), "/dev/shm/busierbox-%ld", (long)uid);
    roots[1] = tmp;
    roots[2] = vartmp;
    roots[3] = shm;

    for (i = 0; i < 4; i++) {
        snprintf(path, sizeof(path), "%s", roots[i]);
        if (mkdir_p(path, 0700) != 0)
            continue;
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

static int run_tar_extract(const char *archive, const char *root)
{
    pid_t pid = fork();
    int status;
    char lock[PATH_MAX], tmp[PATH_MAX], final[PATH_MAX], extracted[PATH_MAX];

    snprintf(lock, sizeof(lock), "%s/.extract.lock", root);
    snprintf(tmp, sizeof(tmp), "%s/payload.tmp.%ld", root, (long)getpid());
    snprintf(final, sizeof(final), "%s/payload", root);
    snprintf(extracted, sizeof(extracted), "%s/payload", tmp);

    if (!enough_space(archive, root)) {
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

    if (pid < 0) {
        rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    if (pid == 0) {
        execlp("tar", "tar", "-xzf", archive, "-C", tmp, (char *)0);
        _exit(127);
    }
    while (waitpid(pid, &status, 0) < 0) {
        if (errno != EINTR)
            rm_rf(tmp);
            rmdir(lock);
            return -1;
    }
    if (!(WIFEXITED(status) && WEXITSTATUS(status) == 0)) {
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
    return 0;
}

static int ensure_payload(char *payload, size_t payloadsz)
{
    char archive[PATH_MAX], root[PATH_MAX];

    if (candidate_payload(payload, payloadsz) == 0)
        return 0;
    if (archive_path(archive, sizeof(archive)) != 0)
        return -1;
    if (choose_extract_root(root, sizeof(root)) != 0)
        return -1;
    if (run_tar_extract(archive, root) != 0)
        return -1;
    snprintf(payload, payloadsz, "%s/payload", root);
    return payload_valid(payload) ? 0 : -1;
}

static int is_heavy_tool(const char *name)
{
    int i;
    for (i = 0; heavy_tools[i]; i++)
        if (!strcmp(name, heavy_tools[i]))
            return 1;
    return 0;
}

static void set_payload_env(const char *payload)
{
    char path[PATH_MAX * 2], home[PATH_MAX], lib[PATH_MAX];
    const char *old_path = getenv("PATH");

    snprintf(path, sizeof(path), "%s/bin:%s", payload, old_path ? old_path : "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin");
    snprintf(home, sizeof(home), "%s/home", payload);
    snprintf(lib, sizeof(lib), "%s/lib", payload);
    setenv("BUSIERBOX_PAYLOAD_DIR", payload, 1);
    setenv("PATH", path, 1);
    setenv("HOME", home, 1);
    if (!getenv("TERM"))
        setenv("TERM", "vt100", 1);
    snprintf(lib, sizeof(lib), "%s/home", payload);
    if (path_exists(lib))
        setenv("ZDOTDIR", lib, 1);
    snprintf(lib, sizeof(lib), "%s/lib", payload);
    if (path_exists(lib))
        setenv("LD_LIBRARY_PATH", lib, 1);
}

static int execv_alloc(const char *path, char **argv)
{
    execv(path, argv);
    fprintf(stderr, "busierbox: exec %s failed: %s\n", path, strerror(errno));
    return errno == ENOENT ? 127 : 126;
}

int bb_exec_payload_applet(const char *name, int argc, char **argv)
{
    char payload[PATH_MAX], exe[PATH_MAX];
    char **child;
    int i;

    if (ensure_payload(payload, sizeof(payload)) != 0) {
        fprintf(stderr, "busierbox: payload unavailable; run 'busierbox extract' after creating dist/payload.tar.gz\n");
        return 127;
    }
    set_payload_env(payload);

    if (is_heavy_tool(name)) {
        snprintf(exe, sizeof(exe), "%s/bin/%s", payload, name);
        return execv_alloc(exe, argv);
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
    execv(exe, child);
    fprintf(stderr, "busierbox: exec BusyBox applet %s failed: %s\n", name, strerror(errno));
    free(child);
    return errno == ENOENT ? 127 : 126;
}

int applet_list_main(int argc, char **argv)
{
    int verbose = argc > 1 && !strcmp(argv[1], "-v");
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox list [-v]");
        return 0;
    }
    puts("native:");
    bb_list_applets(verbose);
    puts("busybox:");
    for (i = 0; busybox_tools[i]; i++)
        puts(busybox_tools[i]);
    puts("payload:");
    for (i = 0; heavy_tools[i]; i++)
        puts(heavy_tools[i]);
    return 0;
}

int applet_extract_main(int argc, char **argv)
{
    char payload[PATH_MAX], archive[PATH_MAX], root[PATH_MAX];

    if (is_help(argc, argv)) {
        puts("usage: busierbox extract");
        puts("Extracts dist/payload.tar.gz or adjacent payload.tar.gz into a writable runtime directory.");
        return 0;
    }
    if (candidate_payload(payload, sizeof(payload)) == 0) {
        printf("payload: reuse %s\n", payload);
        return 0;
    }
    if (archive_path(archive, sizeof(archive)) != 0) {
        fprintf(stderr, "extract: payload.tar.gz not found beside busierbox, in dist/, or in cwd\n");
        return 1;
    }
    if (choose_extract_root(root, sizeof(root)) != 0) {
        fprintf(stderr, "extract: no writable executable runtime directory found\n");
        return 1;
    }
    if (run_tar_extract(archive, root) != 0) {
        fprintf(stderr, "extract: tar extraction failed for %s\n", archive);
        return 1;
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

int applet_clean_main(int argc, char **argv)
{
    if (is_help(argc, argv)) {
        puts("usage: busierbox clean");
        puts("Removes the local .busierbox extraction directory.");
        return 0;
    }
    if (rm_rf(".busierbox") != 0) {
        fprintf(stderr, "clean: %s\n", strerror(errno));
        return 1;
    }
    puts("clean: removed .busierbox");
    return 0;
}

int applet_config_info_main(int argc, char **argv)
{
    char payload[PATH_MAX], hash_path[PATH_MAX], hash[256] = "unknown";
    char manifest[PATH_MAX];
    char exe_dir[PATH_MAX];
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
    printf("payload_version=%s\n", BUSIERBOX_PAYLOAD_VERSION);
    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(hash_path, sizeof(hash_path), "%s/payload.tar.gz.sha256", exe_dir);
        read_first_line(hash_path, hash, sizeof(hash));
    }
    printf("payload_archive_hash=%s\n", hash);
    puts("native_applets=list survey envfix extract clean config-info");
    printf("payload_present=%s\n", candidate_payload(payload, sizeof(payload)) == 0 ? payload : "no");
    printf("payload_tools_present=");
    for (i = 0; heavy_tools[i]; i++)
        printf("%s%s:%s", i ? "," : "", heavy_tools[i], candidate_payload(payload, sizeof(payload)) == 0 ? "yes" : "unknown");
    printf("\n");
    if (candidate_payload(payload, sizeof(payload)) == 0) {
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
