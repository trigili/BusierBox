#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
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

static void clean_header_value(const char *in, char *out, size_t outsz)
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

static int run_downloader(const char *tool, const char *url, const char *out, int tls,
                          const char *target_id, const char *target_label,
                          const char *target_aliases)
{
    pid_t pid = fork();
    if (pid < 0)
        return -1;
    if (pid == 0) {
        char id_header[320], label_header[320], alias_header[1152];
        int have_id = target_id && target_id[0];
        int have_label = target_label && target_label[0];
        int have_alias = target_aliases && target_aliases[0];
        if (have_id)
            snprintf(id_header, sizeof(id_header), "X-BusierBox-Target-Id: %s", target_id);
        if (have_label)
            snprintf(label_header, sizeof(label_header), "X-BusierBox-Target-Label: %s", target_label);
        if (have_alias)
            snprintf(alias_header, sizeof(alias_header), "X-BusierBox-Target-Alias: %s", target_aliases);
        if (!strcmp(tool, "wget")) {
            if (tls && have_id && have_label && have_alias)
                execlp("wget", "wget", "--no-check-certificate", "--header", id_header, "--header", label_header, "--header", alias_header, "-O", out, url, (char *)NULL);
            else if (tls && have_id && have_label)
                execlp("wget", "wget", "--no-check-certificate", "--header", id_header, "--header", label_header, "-O", out, url, (char *)NULL);
            else if (tls && have_id && have_alias)
                execlp("wget", "wget", "--no-check-certificate", "--header", id_header, "--header", alias_header, "-O", out, url, (char *)NULL);
            else if (tls && have_label && have_alias)
                execlp("wget", "wget", "--no-check-certificate", "--header", label_header, "--header", alias_header, "-O", out, url, (char *)NULL);
            else if (tls && have_id)
                execlp("wget", "wget", "--no-check-certificate", "--header", id_header, "-O", out, url, (char *)NULL);
            else if (tls && have_label)
                execlp("wget", "wget", "--no-check-certificate", "--header", label_header, "-O", out, url, (char *)NULL);
            else if (tls && have_alias)
                execlp("wget", "wget", "--no-check-certificate", "--header", alias_header, "-O", out, url, (char *)NULL);
            else if (tls)
                execlp("wget", "wget", "--no-check-certificate", "-O", out, url, (char *)NULL);
            else if (have_id && have_label && have_alias)
                execlp("wget", "wget", "--header", id_header, "--header", label_header, "--header", alias_header, "-O", out, url, (char *)NULL);
            else if (have_id && have_label)
                execlp("wget", "wget", "--header", id_header, "--header", label_header, "-O", out, url, (char *)NULL);
            else if (have_id && have_alias)
                execlp("wget", "wget", "--header", id_header, "--header", alias_header, "-O", out, url, (char *)NULL);
            else if (have_label && have_alias)
                execlp("wget", "wget", "--header", label_header, "--header", alias_header, "-O", out, url, (char *)NULL);
            else if (have_id)
                execlp("wget", "wget", "--header", id_header, "-O", out, url, (char *)NULL);
            else if (have_label)
                execlp("wget", "wget", "--header", label_header, "-O", out, url, (char *)NULL);
            else if (have_alias)
                execlp("wget", "wget", "--header", alias_header, "-O", out, url, (char *)NULL);
            else
                execlp("wget", "wget", "-O", out, url, (char *)NULL);
        } else {
            if (tls && have_id && have_label && have_alias)
                execlp("curl", "curl", "-fkL", "-H", id_header, "-H", label_header, "-H", alias_header, "-o", out, url, (char *)NULL);
            else if (tls && have_id && have_label)
                execlp("curl", "curl", "-fkL", "-H", id_header, "-H", label_header, "-o", out, url, (char *)NULL);
            else if (tls && have_id && have_alias)
                execlp("curl", "curl", "-fkL", "-H", id_header, "-H", alias_header, "-o", out, url, (char *)NULL);
            else if (tls && have_label && have_alias)
                execlp("curl", "curl", "-fkL", "-H", label_header, "-H", alias_header, "-o", out, url, (char *)NULL);
            else if (tls && have_id)
                execlp("curl", "curl", "-fkL", "-H", id_header, "-o", out, url, (char *)NULL);
            else if (tls && have_label)
                execlp("curl", "curl", "-fkL", "-H", label_header, "-o", out, url, (char *)NULL);
            else if (tls && have_alias)
                execlp("curl", "curl", "-fkL", "-H", alias_header, "-o", out, url, (char *)NULL);
            else if (tls)
                execlp("curl", "curl", "-fkL", "-o", out, url, (char *)NULL);
            else if (have_id && have_label && have_alias)
                execlp("curl", "curl", "-fL", "-H", id_header, "-H", label_header, "-H", alias_header, "-o", out, url, (char *)NULL);
            else if (have_id && have_label)
                execlp("curl", "curl", "-fL", "-H", id_header, "-H", label_header, "-o", out, url, (char *)NULL);
            else if (have_id && have_alias)
                execlp("curl", "curl", "-fL", "-H", id_header, "-H", alias_header, "-o", out, url, (char *)NULL);
            else if (have_label && have_alias)
                execlp("curl", "curl", "-fL", "-H", label_header, "-H", alias_header, "-o", out, url, (char *)NULL);
            else if (have_id)
                execlp("curl", "curl", "-fL", "-H", id_header, "-o", out, url, (char *)NULL);
            else if (have_label)
                execlp("curl", "curl", "-fL", "-H", label_header, "-o", out, url, (char *)NULL);
            else if (have_alias)
                execlp("curl", "curl", "-fL", "-H", alias_header, "-o", out, url, (char *)NULL);
            else
                execlp("curl", "curl", "-fL", "-o", out, url, (char *)NULL);
        }
        _exit(127);
    }
    return wait_status_ok(pid) ? 0 : -1;
}

static int has_traversal(const char *s)
{
    const char *p = s;
    size_t len;
    if (!s || !*s)
        return 1;
    while (*p) {
        while (*p == '/' || *p == '\\')
            p++;
        len = 0;
        while (p[len] && p[len] != '/' && p[len] != '\\')
            len++;
        if (len == 2 && p[0] == '.' && p[1] == '.')
            return 1;
        p += len;
    }
    return 0;
}

static void url_encode(const char *in, char *out, size_t outsz)
{
    static const char hex[] = "0123456789ABCDEF";
    size_t i = 0;
    while (*in && i + 1 < outsz) {
        unsigned char c = (unsigned char)*in++;
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_' || c == '.' || c == '/' || c == '~') {
            out[i++] = (char)c;
        } else if (i + 3 < outsz) {
            out[i++] = '%';
            out[i++] = hex[c >> 4];
            out[i++] = hex[c & 15];
        } else {
            break;
        }
    }
    out[i] = '\0';
}

static const char *base_name(const char *path)
{
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

int applet_fetch_main(int argc, char **argv)
{
    const char *request = NULL;
    const char *host = NULL;
    const char *out = NULL;
    const char *target_id_arg = NULL;
    const char *target_label_arg = NULL;
    const char *target_alias_args[16];
    int target_alias_arg_count = 0;
    int port = 22204;
    int tls = 1;
    int force = 0;
    char encoded[PATH_MAX * 3];
    char url[PATH_MAX * 4];
    char tmp[PATH_MAX];
    char target_id[256], target_label[256], target_alias[256], target_aliases[1024];
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox fetch REQUEST --host HOST [--port PORT] [--output PATH] [--force] [--no-tls] [--target-id ID] [--target-label LABEL] [--target-alias ALIAS]");
        puts("Fetches an operator-staged file from busierbox-server only when explicitly run on the target.");
        puts("Refuses path traversal and refuses to overwrite an existing output unless --force is present.");
        return 0;
    }

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--host")) {
            if (++i >= argc) {
                fputs("fetch: --host requires a value\n", stderr);
                return 2;
            }
            host = argv[i];
        } else if (!strcmp(argv[i], "--port")) {
            if (++i >= argc) {
                fputs("fetch: --port requires a value\n", stderr);
                return 2;
            }
            port = atoi(argv[i]);
        } else if (!strcmp(argv[i], "--output") || !strcmp(argv[i], "-o")) {
            if (++i >= argc) {
                fputs("fetch: --output requires a path\n", stderr);
                return 2;
            }
            out = argv[i];
        } else if (!strcmp(argv[i], "--force")) {
            force = 1;
        } else if (!strcmp(argv[i], "--target-id")) {
            if (++i >= argc) {
                fputs("fetch: --target-id requires a value\n", stderr);
                return 2;
            }
            target_id_arg = argv[i];
        } else if (!strcmp(argv[i], "--target-label")) {
            if (++i >= argc) {
                fputs("fetch: --target-label requires a value\n", stderr);
                return 2;
            }
            target_label_arg = argv[i];
        } else if (!strcmp(argv[i], "--target-alias")) {
            if (++i >= argc) {
                fputs("fetch: --target-alias requires a value\n", stderr);
                return 2;
            }
            if (target_alias_arg_count >= (int)(sizeof(target_alias_args) / sizeof(target_alias_args[0]))) {
                fputs("fetch: too many --target-alias values\n", stderr);
                return 2;
            }
            target_alias_args[target_alias_arg_count++] = argv[i];
        } else if (!strcmp(argv[i], "--no-tls")) {
            tls = 0;
        } else if (!strcmp(argv[i], "--tls")) {
            if (++i >= argc) {
                fputs("fetch: --tls requires yes or no\n", stderr);
                return 2;
            }
            tls = (!strcmp(argv[i], "yes") || !strcmp(argv[i], "true") || !strcmp(argv[i], "1"));
        } else if (!request) {
            request = argv[i];
        } else {
            fprintf(stderr, "fetch: unexpected argument: %s\n", argv[i]);
            return 2;
        }
    }
    if (!request || !host) {
        fputs("fetch: REQUEST and --host are required\n", stderr);
        return 2;
    }
    if (port <= 0 || port > 65535) {
        fputs("fetch: invalid --port\n", stderr);
        return 2;
    }
    if (has_traversal(request)) {
        fputs("fetch: refusing request name with path traversal\n", stderr);
        return 2;
    }
    if (!out)
        out = request[0] ? request : base_name(request);
    if (has_traversal(out)) {
        fputs("fetch: refusing output path with path traversal\n", stderr);
        return 2;
    }
    if (!force && access(out, F_OK) == 0) {
        fprintf(stderr, "fetch: refusing to overwrite %s without --force\n", out);
        return 1;
    }
    url_encode(request, encoded, sizeof(encoded));
    snprintf(url, sizeof(url), "%s://%s:%d/fetch?name=%s", tls ? "https" : "http", host, port, encoded);
    snprintf(tmp, sizeof(tmp), "%s.tmp.%ld", out, (long)getpid());
    clean_header_value(target_id_arg, target_id, sizeof(target_id));
    clean_header_value(target_label_arg, target_label, sizeof(target_label));
    target_aliases[0] = '\0';
    for (i = 0; i < target_alias_arg_count; i++) {
        clean_header_value(target_alias_args[i], target_alias, sizeof(target_alias));
        if (!target_alias[0])
            continue;
        if (target_aliases[0])
            snprintf(target_aliases + strlen(target_aliases), sizeof(target_aliases) - strlen(target_aliases),
                     ",%s", target_alias);
        else
            snprintf(target_aliases, sizeof(target_aliases), "%s", target_alias);
    }
    unlink(tmp);
    printf("fetch: downloading %s -> %s\n", request, out);
    if (run_downloader("wget", url, tmp, tls, target_id, target_label, target_aliases) != 0 &&
            run_downloader("curl", url, tmp, tls, target_id, target_label, target_aliases) != 0) {
        unlink(tmp);
        fputs("fetch: download failed; need wget or curl in PATH\n", stderr);
        return 1;
    }
    if (rename(tmp, out) != 0) {
        fprintf(stderr, "fetch: rename %s -> %s failed: %s\n", tmp, out, strerror(errno));
        unlink(tmp);
        return 1;
    }
    puts("fetch: ok");
    return 0;
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
    if (run_downloader("wget", url, out, !strncmp(url, "https:", 6), "", "", "") != 0 &&
        run_downloader("curl", url, out, !strncmp(url, "https:", 6), "", "", "") != 0) {
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
