#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netdb.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "applets.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

static int help_arg(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static int connect_tcp(const char *host, const char *port)
{
    struct addrinfo hints, *res, *rp;
    int fd = -1, rc;

    memset(&hints, 0, sizeof(hints));
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_family = AF_UNSPEC;
    rc = getaddrinfo(host, port, &hints, &res);
    if (rc != 0) {
        fprintf(stderr, "connect: %s\n", gai_strerror(rc));
        return -1;
    }
    for (rp = res; rp; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd < 0)
            continue;
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) == 0)
            break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

static int listen_tcp(const char *port)
{
    struct addrinfo hints, *res, *rp;
    int fd = -1, yes = 1, rc;

    memset(&hints, 0, sizeof(hints));
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_family = AF_INET;
    hints.ai_flags = AI_PASSIVE;
    rc = getaddrinfo(NULL, port, &hints, &res);
    if (rc != 0) {
        fprintf(stderr, "listen: %s\n", gai_strerror(rc));
        return -1;
    }
    for (rp = res; rp; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd < 0)
            continue;
        setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
        if (bind(fd, rp->ai_addr, rp->ai_addrlen) == 0 && listen(fd, 8) == 0)
            break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

static int pump_socket(int fd)
{
    int stdin_open = 1;
    char buf[8192];

    while (1) {
        fd_set rfds;
        int maxfd = fd, rc;
        FD_ZERO(&rfds);
        FD_SET(fd, &rfds);
        if (stdin_open) {
            FD_SET(STDIN_FILENO, &rfds);
            if (STDIN_FILENO > maxfd) maxfd = STDIN_FILENO;
        }
        rc = select(maxfd + 1, &rfds, NULL, NULL, NULL);
        if (rc < 0) {
            if (errno == EINTR) continue;
            perror("select");
            return 1;
        }
        if (FD_ISSET(fd, &rfds)) {
            ssize_t n = read(fd, buf, sizeof(buf));
            if (n < 0) return 1;
            if (n == 0) break;
            if (write(STDOUT_FILENO, buf, (size_t)n) != n) return 1;
        }
        if (stdin_open && FD_ISSET(STDIN_FILENO, &rfds)) {
            ssize_t n = read(STDIN_FILENO, buf, sizeof(buf));
            if (n < 0) return 1;
            if (n == 0) {
                shutdown(fd, SHUT_WR);
                stdin_open = 0;
            } else if (write(fd, buf, (size_t)n) != n) {
                return 1;
            }
        }
    }
    return 0;
}

int applet_nc_main(int argc, char **argv)
{
    int fd, lfd;
    if (help_arg(argc, argv)) {
        puts("usage: busierbox nc HOST PORT");
        puts("       busierbox nc -l PORT");
        puts("TCP only; no command execution mode.");
        return 0;
    }
    if (argc == 3 && !strcmp(argv[1], "-l")) {
        lfd = listen_tcp(argv[2]);
        if (lfd < 0) return 1;
        fd = accept(lfd, NULL, NULL);
        close(lfd);
        if (fd < 0) { perror("accept"); return 1; }
        lfd = pump_socket(fd);
        close(fd);
        return lfd;
    }
    if (argc != 3) {
        fprintf(stderr, "usage: busierbox nc HOST PORT\n");
        return 2;
    }
    fd = connect_tcp(argv[1], argv[2]);
    if (fd < 0) return 1;
    lfd = pump_socket(fd);
    close(fd);
    return lfd;
}

struct url_parts {
    char host[256];
    char port[16];
    char path[1024];
};

static int parse_http_url(const char *url, struct url_parts *u)
{
    const char *p, *slash, *colon;
    size_t host_len;

    if (strncmp(url, "http://", 7) != 0)
        return -1;
    p = url + 7;
    slash = strchr(p, '/');
    if (!slash)
        slash = p + strlen(p);
    colon = memchr(p, ':', (size_t)(slash - p));
    host_len = (size_t)((colon ? colon : slash) - p);
    if (host_len == 0 || host_len >= sizeof(u->host))
        return -1;
    memcpy(u->host, p, host_len);
    u->host[host_len] = '\0';
    if (colon) {
        size_t port_len = (size_t)(slash - colon - 1);
        if (port_len == 0 || port_len >= sizeof(u->port))
            return -1;
        memcpy(u->port, colon + 1, port_len);
        u->port[port_len] = '\0';
    } else {
        strcpy(u->port, "80");
    }
    if (*slash)
        snprintf(u->path, sizeof(u->path), "%s", slash);
    else
        strcpy(u->path, "/");
    return 0;
}

static int write_all_fd(int fd, const void *buf, size_t len)
{
    const char *p = buf;
    while (len) {
        ssize_t n = write(fd, p, len);
        if (n <= 0) return -1;
        p += n;
        len -= (size_t)n;
    }
    return 0;
}

static int http_read_response(int fd, FILE *out)
{
    char buf[4096];
    int header = 1, state = 0;
    ssize_t n, i;
    while ((n = read(fd, buf, sizeof(buf))) > 0) {
        for (i = 0; i < n; i++) {
            if (header) {
                char c = buf[i];
                state = (state == 0 && c == '\r') ? 1 :
                        (state == 1 && c == '\n') ? 2 :
                        (state == 2 && c == '\r') ? 3 :
                        (state == 3 && c == '\n') ? 4 : 0;
                if (state == 4) {
                    header = 0;
                    if (i + 1 < n)
                        fwrite(buf + i + 1, 1, (size_t)(n - i - 1), out);
                    break;
                }
            } else {
                fwrite(buf + i, 1, (size_t)(n - i), out);
                break;
            }
        }
    }
    return n < 0 ? 1 : 0;
}

int applet_http_main(int argc, char **argv)
{
    struct url_parts u;
    const char *method, *url, *outfile = NULL, *file = NULL, *data = NULL;
    FILE *out = stdout, *body = NULL;
    long body_len = 0;
    int i, fd, rc;
    char req[2048];

    if (help_arg(argc, argv) || argc < 3) {
        puts("usage: busierbox http get URL [-o FILE]");
        puts("       busierbox http post URL --file FILE");
        puts("       busierbox http post URL --data STRING");
        puts("Plain HTTP only. Supported URLs: http://host[:port]/path");
        return argc < 3 && !help_arg(argc, argv) ? 2 : 0;
    }
    method = argv[1];
    url = argv[2];
    for (i = 3; i < argc; i++) {
        if (!strcmp(argv[i], "-o") && i + 1 < argc) outfile = argv[++i];
        else if (!strcmp(argv[i], "--file") && i + 1 < argc) file = argv[++i];
        else if (!strcmp(argv[i], "--data") && i + 1 < argc) data = argv[++i];
        else { fprintf(stderr, "http: unknown option: %s\n", argv[i]); return 2; }
    }
    if (parse_http_url(url, &u) != 0) {
        fprintf(stderr, "http: unsupported URL: %s\n", url);
        return 2;
    }
    if (outfile) {
        out = fopen(outfile, "wb");
        if (!out) { perror(outfile); return 1; }
    }
    fd = connect_tcp(u.host, u.port);
    if (fd < 0) { if (out != stdout) fclose(out); return 1; }
    if (!strcmp(method, "get")) {
        snprintf(req, sizeof(req), "GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: busierbox\r\nConnection: close\r\n\r\n", u.path, u.host);
        rc = write_all_fd(fd, req, strlen(req));
    } else if (!strcmp(method, "post")) {
        if (file) {
            struct stat st;
            body = fopen(file, "rb");
            if (!body || stat(file, &st) != 0) { perror(file); close(fd); if (out != stdout) fclose(out); return 1; }
            body_len = (long)st.st_size;
        } else if (data) {
            body_len = (long)strlen(data);
        } else {
            fprintf(stderr, "http: post needs --file or --data\n");
            close(fd); if (out != stdout) fclose(out); return 2;
        }
        snprintf(req, sizeof(req), "POST %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: busierbox\r\nConnection: close\r\nContent-Length: %ld\r\nContent-Type: application/octet-stream\r\n\r\n", u.path, u.host, body_len);
        rc = write_all_fd(fd, req, strlen(req));
        if (rc == 0 && data) rc = write_all_fd(fd, data, strlen(data));
        if (rc == 0 && body) {
            char b[8192];
            size_t n;
            while ((n = fread(b, 1, sizeof(b), body)) > 0)
                if (write_all_fd(fd, b, n) != 0) { rc = -1; break; }
            fclose(body);
        }
    } else {
        fprintf(stderr, "http: method must be get or post\n");
        close(fd); if (out != stdout) fclose(out); return 2;
    }
    shutdown(fd, SHUT_WR);
    if (rc == 0)
        rc = http_read_response(fd, out);
    close(fd);
    if (out != stdout)
        fclose(out);
    return rc == 0 ? 0 : 1;
}

static int safe_path(const char *p)
{
    return p[0] == '/' && !strstr(p, "..");
}

static void send_simple(int fd, const char *status, const char *type, const char *body)
{
    char hdr[256];
    snprintf(hdr, sizeof(hdr), "HTTP/1.0 %s\r\nContent-Type: %s\r\nContent-Length: %ld\r\nConnection: close\r\n\r\n",
             status, type, (long)strlen(body));
    write_all_fd(fd, hdr, strlen(hdr));
    write_all_fd(fd, body, strlen(body));
}

static int serve_file(int fd, const char *root, const char *url_path)
{
    char path[PATH_MAX], buf[8192], hdr[256];
    struct stat st;
    int f;
    ssize_t n;

    if (!safe_path(url_path)) {
        send_simple(fd, "400 Bad Request", "text/plain", "bad path\n");
        return 0;
    }
    snprintf(path, sizeof(path), "%s%s", root, !strcmp(url_path, "/") ? "" : url_path);
    if (stat(path, &st) != 0) {
        send_simple(fd, "404 Not Found", "text/plain", "not found\n");
        return 0;
    }
    if (S_ISDIR(st.st_mode)) {
        DIR *d = opendir(path);
        struct dirent *de;
        write_all_fd(fd, "HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n<pre>\n", 73);
        if (d) {
            while ((de = readdir(d))) {
                if (!strcmp(de->d_name, "."))
                    continue;
                write_all_fd(fd, de->d_name, strlen(de->d_name));
                write_all_fd(fd, "\n", 1);
            }
            closedir(d);
        }
        write_all_fd(fd, "</pre>\n", 7);
        return 0;
    }
    if (!S_ISREG(st.st_mode)) {
        send_simple(fd, "403 Forbidden", "text/plain", "not a regular file\n");
        return 0;
    }
    f = open(path, O_RDONLY);
    if (f < 0) {
        send_simple(fd, "403 Forbidden", "text/plain", "open failed\n");
        return 0;
    }
    snprintf(hdr, sizeof(hdr), "HTTP/1.0 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Length: %ld\r\nConnection: close\r\n\r\n", (long)st.st_size);
    write_all_fd(fd, hdr, strlen(hdr));
    while ((n = read(f, buf, sizeof(buf))) > 0)
        write_all_fd(fd, buf, (size_t)n);
    close(f);
    return 0;
}

int applet_serve_main(int argc, char **argv)
{
    const char *port = "8080", *dir = ".";
    int i, lfd;

    if (help_arg(argc, argv)) {
        puts("usage: busierbox serve [-p PORT] [DIR]");
        puts("Tiny HTTP file server; one connection at a time.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-p") && i + 1 < argc) port = argv[++i];
        else dir = argv[i];
    }
    lfd = listen_tcp(port);
    if (lfd < 0) return 1;
    fprintf(stderr, "serve: http://0.0.0.0:%s/ from %s\n", port, dir);
    for (;;) {
        char req[1024], method[16], path[512];
        int cfd = accept(lfd, NULL, NULL);
        ssize_t n;
        if (cfd < 0) {
            if (errno == EINTR) continue;
            perror("accept");
            break;
        }
        n = read(cfd, req, sizeof(req) - 1);
        if (n > 0) {
            req[n] = '\0';
            if (sscanf(req, "%15s %511s", method, path) == 2 && !strcmp(method, "GET"))
                serve_file(cfd, dir, path);
            else
                send_simple(cfd, "405 Method Not Allowed", "text/plain", "GET only\n");
        }
        close(cfd);
    }
    close(lfd);
    return 1;
}
