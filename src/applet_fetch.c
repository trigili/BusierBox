#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include "applets.h"
#include "sha256.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
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
