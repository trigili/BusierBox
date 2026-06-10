#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif
#ifndef _BSD_SOURCE
#define _BSD_SOURCE 1
#endif
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifdef HAVE_WOLFSSL
#include <wolfssl/ssl.h>
#endif

#include "applets.h"
#include "json_helpers.h"
#include "effective_config.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef GRIT_OPERATOR_FILE_SERVICE_ENABLE
#define GRIT_OPERATOR_FILE_SERVICE_ENABLE "no"
#endif
#ifndef GRIT_OPERATOR_FILE_SERVICE_PORT
#define GRIT_OPERATOR_FILE_SERVICE_PORT "22204"
#endif
#ifndef GRIT_OPERATOR_FILE_SERVICE_TLS
#define GRIT_OPERATOR_FILE_SERVICE_TLS "yes"
#endif

struct upload_opts {
    const char *host;
    const char *port;
    const char *tls;
    const char *dest;
    const char *method;
    const char *target_id;
    const char *target_label;
    const char *target_aliases[16];
    int target_alias_count;
    int quiet;
};

static int yes_value(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "on"));
}

static const char *path_basename(const char *path)
{
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
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

static void clean_url_part(const char *in, char *out, size_t outsz)
{
    size_t i, j = 0;
    if (!outsz)
        return;
    for (i = 0; in && in[i] && j + 1 < outsz; i++) {
        unsigned char c = (unsigned char)in[i];
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
            (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')
            out[j++] = (char)c;
        else
            out[j++] = '_';
    }
    if (!j && outsz > 1) {
        snprintf(out, outsz, "%s", "upload");
        return;
    }
    out[j] = '\0';
}

static int tcp_connect_host(const char *host, const char *port)
{
    struct addrinfo hints, *res, *rp;
    int sock = -1;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, port, &hints, &res) != 0)
        return -1;
    for (rp = res; rp; rp = rp->ai_next) {
        sock = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (sock < 0)
            continue;
        if (connect(sock, rp->ai_addr, rp->ai_addrlen) == 0)
            break;
        close(sock);
        sock = -1;
    }
    freeaddrinfo(res);
    return sock;
}

static int write_full_fd(int fd, const void *buf, size_t len)
{
    const char *p = buf;
    size_t off = 0;
    while (off < len) {
        ssize_t n = write(fd, p + off, len - off);
        if (n > 0) {
            off += (size_t)n;
            continue;
        }
        if (n < 0 && errno == EINTR)
            continue;
        return -1;
    }
    return 0;
}

#ifdef HAVE_WOLFSSL
static int wait_fd_event(int fd, short events)
{
    struct pollfd p;
    p.fd = fd;
    p.events = events;
    p.revents = 0;
    for (;;) {
        if (poll(&p, 1, -1) >= 0)
            return 0;
        if (errno != EINTR)
            return -1;
    }
}

static int tls_write_full(WOLFSSL *ssl, const void *buf, size_t len)
{
    const char *p = buf;
    size_t off = 0;
    int fd = wolfSSL_get_fd(ssl);

    while (off < len) {
        int chunk = (len - off) > 16384 ? 16384 : (int)(len - off);
        int n = wolfSSL_write(ssl, p + off, chunk);
        if (n > 0) {
            off += (size_t)n;
            continue;
        }
        switch (wolfSSL_get_error(ssl, n)) {
        case WOLFSSL_ERROR_WANT_READ:
            if (wait_fd_event(fd, POLLIN) != 0)
                return -1;
            continue;
        case WOLFSSL_ERROR_WANT_WRITE:
            if (wait_fd_event(fd, POLLOUT) != 0)
                return -1;
            continue;
        default:
            return -1;
        }
    }
    return 0;
}

static int tls_read_some(WOLFSSL *ssl, char *buf, int len)
{
    int fd = wolfSSL_get_fd(ssl);
    for (;;) {
        int n = wolfSSL_read(ssl, buf, len);
        if (n > 0)
            return n;
        switch (wolfSSL_get_error(ssl, n)) {
        case WOLFSSL_ERROR_WANT_READ:
            if (wait_fd_event(fd, POLLIN) != 0)
                return -1;
            continue;
        case WOLFSSL_ERROR_WANT_WRITE:
            if (wait_fd_event(fd, POLLOUT) != 0)
                return -1;
            continue;
        case WOLFSSL_ERROR_ZERO_RETURN:
            return 0;
        default:
            return -1;
        }
    }
}
#endif

static int read_http_status_fd(int fd)
{
    char buf[512];
    ssize_t n = read(fd, buf, sizeof(buf) - 1);
    int code = 0;
    if (n <= 0)
        return 0;
    buf[n] = '\0';
    if (sscanf(buf, "HTTP/%*s %d", &code) == 1)
        return code;
    return 0;
}

#ifdef HAVE_WOLFSSL
static int read_http_status_tls(WOLFSSL *ssl)
{
    char buf[512];
    int n = tls_read_some(ssl, buf, (int)sizeof(buf) - 1);
    int code = 0;
    if (n <= 0)
        return 0;
    buf[n] = '\0';
    if (sscanf(buf, "HTTP/%*s %d", &code) == 1)
        return code;
    return 0;
}
#endif

static int send_plain_upload(int sock, int filefd, const char *header, off_t size, int quiet)
{
    char buf[32768];
    off_t sent = 0;

    if (write_full_fd(sock, header, strlen(header)) != 0)
        return -1;
    while (1) {
        ssize_t n = read(filefd, buf, sizeof(buf));
        if (n > 0) {
            if (write_full_fd(sock, buf, (size_t)n) != 0)
                return -1;
            sent += n;
            if (!quiet && size > 0)
                fprintf(stderr, "\rupload: %lld/%lld bytes", (long long)sent, (long long)size);
            continue;
        }
        if (n == 0)
            break;
        if (errno == EINTR)
            continue;
        return -1;
    }
    if (!quiet)
        fputc('\n', stderr);
    return read_http_status_fd(sock);
}

#ifdef HAVE_WOLFSSL
static int send_tls_upload(int sock, int filefd, const char *header, off_t size, int quiet)
{
    WOLFSSL_CTX *ctx;
    WOLFSSL *ssl;
    char buf[32768];
    off_t sent = 0;
    int rc, status;

    wolfSSL_Init();
    ctx = wolfSSL_CTX_new(wolfSSLv23_client_method());
    if (!ctx)
        return -1;
    wolfSSL_CTX_set_verify(ctx, WOLFSSL_VERIFY_NONE, NULL);
    ssl = wolfSSL_new(ctx);
    if (!ssl) {
        wolfSSL_CTX_free(ctx);
        wolfSSL_Cleanup();
        return -1;
    }
    wolfSSL_set_fd(ssl, sock);
    rc = wolfSSL_connect(ssl);
    if (rc != WOLFSSL_SUCCESS) {
        wolfSSL_free(ssl);
        wolfSSL_CTX_free(ctx);
        wolfSSL_Cleanup();
        return -1;
    }
    if (tls_write_full(ssl, header, strlen(header)) != 0) {
        wolfSSL_free(ssl);
        wolfSSL_CTX_free(ctx);
        wolfSSL_Cleanup();
        return -1;
    }
    while (1) {
        ssize_t n = read(filefd, buf, sizeof(buf));
        if (n > 0) {
            if (tls_write_full(ssl, buf, (size_t)n) != 0) {
                wolfSSL_free(ssl);
                wolfSSL_CTX_free(ctx);
                wolfSSL_Cleanup();
                return -1;
            }
            sent += n;
            if (!quiet && size > 0)
                fprintf(stderr, "\rupload: %lld/%lld bytes", (long long)sent, (long long)size);
            continue;
        }
        if (n == 0)
            break;
        if (errno == EINTR)
            continue;
        wolfSSL_free(ssl);
        wolfSSL_CTX_free(ctx);
        wolfSSL_Cleanup();
        return -1;
    }
    if (!quiet)
        fputc('\n', stderr);
    status = read_http_status_tls(ssl);
    wolfSSL_shutdown(ssl);
    wolfSSL_free(ssl);
    wolfSSL_CTX_free(ctx);
    wolfSSL_Cleanup();
    return status;
}
#endif

static int parse_common_opts(int argc, char **argv, struct upload_opts *opts)
{
    int i;
    opts->host = GRIT_OPERATOR_SERVER_HOST;
    opts->port = GRIT_OPERATOR_FILE_SERVICE_PORT;
    opts->tls = GRIT_OPERATOR_FILE_SERVICE_TLS;
    opts->dest = NULL;
    opts->method = "PUT";
    opts->target_id = NULL;
    opts->target_label = NULL;
    opts->target_alias_count = 0;
    opts->quiet = 0;

    for (i = 0; i < argc; i++) {
        if (!strcmp(argv[i], "--host")) {
            if (++i >= argc) {
                fputs("upload: --host requires a value\n", stderr);
                return -1;
            }
            opts->host = argv[i];
        } else if (!strcmp(argv[i], "--port")) {
            if (++i >= argc) {
                fputs("upload: --port requires a value\n", stderr);
                return -1;
            }
            opts->port = argv[i];
        } else if (!strcmp(argv[i], "--tls")) {
            if (++i >= argc) {
                fputs("upload: --tls requires yes or no\n", stderr);
                return -1;
            }
            opts->tls = argv[i];
        } else if (!strcmp(argv[i], "--no-tls")) {
            opts->tls = "no";
        } else if (!strcmp(argv[i], "--dest")) {
            if (++i >= argc) {
                fputs("upload: --dest requires a value\n", stderr);
                return -1;
            }
            opts->dest = argv[i];
        } else if (!strcmp(argv[i], "--post")) {
            opts->method = "POST";
        } else if (!strcmp(argv[i], "--target-id")) {
            if (++i >= argc) {
                fputs("upload: --target-id requires a value\n", stderr);
                return -1;
            }
            opts->target_id = argv[i];
        } else if (!strcmp(argv[i], "--target-label")) {
            if (++i >= argc) {
                fputs("upload: --target-label requires a value\n", stderr);
                return -1;
            }
            opts->target_label = argv[i];
        } else if (!strcmp(argv[i], "--target-alias")) {
            if (++i >= argc) {
                fputs("upload: --target-alias requires a value\n", stderr);
                return -1;
            }
            if (opts->target_alias_count >= (int)(sizeof(opts->target_aliases) / sizeof(opts->target_aliases[0]))) {
                fputs("upload: too many --target-alias values\n", stderr);
                return -1;
            }
            opts->target_aliases[opts->target_alias_count++] = argv[i];
        } else if (!strcmp(argv[i], "--quiet") || !strcmp(argv[i], "-q")) {
            opts->quiet = 1;
        } else {
            fprintf(stderr, "upload: unknown option %s\n", argv[i]);
            return -1;
        }
    }
    return 0;
}

int bb_operator_upload_file(const char *path, const char *source_path, const char *kind,
                            int argc, char **argv)
{
    struct upload_opts opts;
    struct stat st;
    char source[512], url_name[128], header[8192];
    char target_id[256], target_label[256], target_alias[256], target_aliases[1024], target_headers[1536];
    int fd, sock, status, i;

    if (parse_common_opts(argc, argv, &opts) != 0)
        return 2;
    if (!opts.host || !opts.host[0]) {
        fputs("upload: operator host is not configured; set GRIT_OPERATOR_SERVER_HOST or pass --host\n", stderr);
        return 2;
    }
    fd = open(path, O_RDONLY);
    if (fd < 0) {
        fprintf(stderr, "upload: cannot open %s: %s\n", path, strerror(errno));
        return 1;
    }
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode)) {
        fprintf(stderr, "upload: %s is not a regular file\n", path);
        close(fd);
        return 1;
    }
    clean_header_value(source_path && *source_path ? source_path : path, source, sizeof(source));
    clean_url_part(opts.dest ? opts.dest : path_basename(source), url_name, sizeof(url_name));
    clean_header_value(opts.target_id, target_id, sizeof(target_id));
    clean_header_value(opts.target_label, target_label, sizeof(target_label));
    target_aliases[0] = '\0';
    for (i = 0; i < opts.target_alias_count; i++) {
        clean_header_value(opts.target_aliases[i], target_alias, sizeof(target_alias));
        if (!target_alias[0])
            continue;
        if (target_aliases[0])
            snprintf(target_aliases + strlen(target_aliases), sizeof(target_aliases) - strlen(target_aliases),
                     ",%s", target_alias);
        else
            snprintf(target_aliases, sizeof(target_aliases), "%s", target_alias);
    }
    target_headers[0] = '\0';
    if (target_id[0])
        snprintf(target_headers + strlen(target_headers), sizeof(target_headers) - strlen(target_headers),
                 "X-griTTYkit-Target-Id: %s\r\n", target_id);
    if (target_label[0])
        snprintf(target_headers + strlen(target_headers), sizeof(target_headers) - strlen(target_headers),
                 "X-griTTYkit-Target-Label: %s\r\n", target_label);
    if (target_aliases[0])
        snprintf(target_headers + strlen(target_headers), sizeof(target_headers) - strlen(target_headers),
                 "X-griTTYkit-Target-Alias: %s\r\n", target_aliases);
    snprintf(header, sizeof(header),
             "%s /upload/%s HTTP/1.1\r\n"
             "Host: %s\r\n"
             "User-Agent: grit-upload/1\r\n"
             "Content-Length: %lld\r\n"
             "Content-Type: application/octet-stream\r\n"
             "X-griTTYkit-Upload-Kind: %s\r\n"
             "X-griTTYkit-Source-Path: %s\r\n"
             "X-griTTYkit-Uid: %ld\r\n"
             "X-griTTYkit-Gid: %ld\r\n"
             "X-griTTYkit-Mode: %04o\r\n"
             "%s"
             "Connection: close\r\n\r\n",
             opts.method, url_name, opts.host, (long long)st.st_size,
             kind && *kind ? kind : "file", source, (long)st.st_uid, (long)st.st_gid,
             (unsigned int)(st.st_mode & 07777), target_headers);

    sock = tcp_connect_host(opts.host, opts.port);
    if (sock < 0) {
        fprintf(stderr, "upload: failed to connect to %s:%s\n", opts.host, opts.port);
        close(fd);
        return 1;
    }
    if (!opts.quiet)
        fprintf(stderr, "upload: sending %s to %s:%s tls=%s\n", path, opts.host, opts.port, opts.tls);
    if (yes_value(opts.tls)) {
#ifdef HAVE_WOLFSSL
        status = send_tls_upload(sock, fd, header, st.st_size, opts.quiet);
#else
        fputs("upload: TLS requested but this artifact was built without wolfSSL; rebuild with GRIT_BUILTIN_TLS_ENABLE=yes or use --no-tls with a plaintext operator service\n", stderr);
        close(sock);
        close(fd);
        return 2;
#endif
    } else {
        status = send_plain_upload(sock, fd, header, st.st_size, opts.quiet);
    }
    close(sock);
    close(fd);
    if (status >= 200 && status < 300) {
        if (!opts.quiet)
            fprintf(stderr, "upload: accepted by operator service (HTTP %d)\n", status);
        return 0;
    }
    fprintf(stderr, "upload: operator service rejected upload%s%d\n", status ? " with HTTP " : "", status);
    return 1;
}

static void usage(void)
{
    puts("usage: grit put PATH [--host HOST] [--port PORT] [--tls yes|no] [--dest NAME] [--target-id ID] [--target-label LABEL] [--target-alias ALIAS]");
    puts("       grit upload PATH [--host HOST] [--port PORT] [--tls yes|no] [--dest NAME] [--target-id ID] [--target-label LABEL] [--target-alias ALIAS]");
    puts("Upload a local target file to the receive-only operator file service.");
}

static int write_generated_json_file(const char *label, int (*writer)(FILE *out), char *path, size_t pathsz)
{
    const char *roots[] = { GRIT_RUNTIME_ROOT, ".", "/tmp", NULL };
    int aggressive_noresidue = !strcmp(GRIT_RUNTIME_MODE, "no-residue") &&
                               !strcmp(GRIT_NORESIDUE_LEVEL, "aggressive");
    int i;

    for (i = 0; roots[i]; i++) {
        int fd;
        if (aggressive_noresidue && i > 0)
            break;
        if (roots[i][0] && strcmp(roots[i], ".")) {
            if (bb_mkdir_p(roots[i], 0700) == 0)
                bb_ledger_record("mkdir", roots[i], "runtime", "generated upload scratch root");
        }
        snprintf(path, pathsz, "%s/.grit-%s.%ld.XXXXXX", roots[i], label, (long)getpid());
        fd = mkstemp(path);
        if (fd < 0)
            continue;
        bb_ledger_record("write", path, "runtime", "generated upload scratch file");
        {
            FILE *fp = fdopen(fd, "w");
            int ok;
            if (!fp) {
                close(fd);
                bb_ledger_record("remove", path, "runtime", "generated upload scratch cleanup");
                unlink(path);
                continue;
            }
            ok = writer(fp) == 0;
            if (fclose(fp) != 0)
                ok = 0;
            if (!ok) {
                bb_ledger_record("remove", path, "runtime", "generated upload scratch cleanup");
                unlink(path);
                continue;
            }
        }
        return 0;
    }
    return -1;
}

static void remove_generated_json_file(const char *path)
{
    if (!path || !path[0])
        return;
    bb_ledger_record("remove", path, "runtime", "generated upload scratch cleanup");
    unlink(path);
}

static int write_config_json(FILE *out)
{
    fputs("{\"schema\":1,\"kind\":\"config\",\"runtime\":", out);
    bb_config_print_runtime_summary_json(out, bb_json_string);
    fputs(",\"effective_config\":", out);
    bb_config_print_effective_json(out, bb_json_string);
    fputs("}\n", out);
    return 0;
}

static int write_evidence_json(FILE *out)
{
    time_t now = time(NULL);
    fputs("{\"schema\":1,\"kind\":\"evidence\",\"generated_at\":", out);
    fprintf(out, "%ld", (long)now);
    fputs(",\"runtime\":", out);
    bb_config_print_runtime_summary_json(out, bb_json_string);
    fputs(",\"rshell\":", out);
    bb_config_print_rshell_readiness_json(out, bb_json_string);
    fputs("}\n", out);
    return 0;
}

static void config_push_usage(void)
{
    puts("usage: grit config-push [--host HOST] [--port PORT] [--tls yes|no] [--target-id ID] [--target-label LABEL] [--target-alias ALIAS]");
    puts("Generate effective config JSON and upload it to the receive-only operator file service.");
}

int applet_upload_main(int argc, char **argv)
{
    const char *cmd = argc > 0 ? argv[0] : "upload";
    const char *path;

    if (!strcmp(cmd, "config-push") &&
        argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        config_push_usage();
        return 0;
    }
    if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        usage();
        return 0;
    }
    if (!strcmp(cmd, "config-push")) {
        char tmp[PATH_MAX];
        int rc;
        if (write_generated_json_file("config", write_config_json, tmp, sizeof(tmp)) != 0) {
            fputs("config-push: unable to create temporary config JSON\n", stderr);
            return 1;
        }
        rc = bb_operator_upload_file(tmp, "grit-config.json", "config", argc - 1, argv + 1);
        remove_generated_json_file(tmp);
        return rc;
    }
    if (!strcmp(cmd, "evidence")) {
        char tmp[PATH_MAX];
        int rc;
        if (argc < 2 || strcmp(argv[1], "push")) {
            puts("usage: grit evidence push [PATH] [--host HOST] [--port PORT] [--tls yes|no]");
            return argc > 1 ? 2 : 0;
        }
        if (argc > 2 && (!strcmp(argv[2], "--help") || !strcmp(argv[2], "-h"))) {
            puts("usage: grit evidence push [PATH] [--host HOST] [--port PORT] [--tls yes|no]");
            puts("Upload a supplied evidence file or a generated griTTYkit evidence summary.");
            return 0;
        }
        if (argc > 2 && argv[2][0] != '-') {
            return bb_operator_upload_file(argv[2], argv[2], "evidence", argc - 3, argv + 3);
        }
        if (write_generated_json_file("evidence", write_evidence_json, tmp, sizeof(tmp)) != 0) {
            fputs("evidence: unable to create temporary evidence JSON\n", stderr);
            return 1;
        }
        rc = bb_operator_upload_file(tmp, "grit-evidence.json", "evidence", argc - 2, argv + 2);
        remove_generated_json_file(tmp);
        return rc;
    }
    if (argc < 2) {
        usage();
        return 2;
    }
    path = argv[1];
    return bb_operator_upload_file(path, path, "file", argc - 2, argv + 2);
}
