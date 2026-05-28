#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "applets.h"
#include "effective_config.h"
#include "json_helpers.h"
#include "payload_runtime.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

struct check_result {
    const char *name;
    int ok;
    int skipped;
    char detail[256];
};

struct reality_opts {
    const char *operator_host;
    const char *file_port;
    const char *tls;
    int check_upload;
    const char *fetch_request;
};

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static void set_result(struct check_result *r, int ok, int skipped, const char *detail)
{
    r->ok = ok;
    r->skipped = skipped;
    snprintf(r->detail, sizeof(r->detail), "%s", detail ? detail : "");
}

static void set_errno_result(struct check_result *r, const char *prefix)
{
    char detail[256];
    snprintf(detail, sizeof(detail), "%s: %s", prefix, strerror(errno));
    set_result(r, 0, 0, detail);
}

static void runtime_probe_dir(char *out, size_t outsz)
{
    snprintf(out, outsz, "%s/reality-test", BB_RUNTIME_ROOT);
}

static void check_runtime_root(struct check_result *r)
{
    char dir[PATH_MAX];
    runtime_probe_dir(dir, sizeof(dir));
    if (bb_mkdir_p(dir, 0700) == 0)
        set_result(r, 1, 0, dir);
    else
        set_errno_result(r, dir);
}

static void check_temp_file(struct check_result *r)
{
    char dir[PATH_MAX], path[PATH_MAX + 64];
    int fd;
    runtime_probe_dir(dir, sizeof(dir));
    if (bb_mkdir_p(dir, 0700) != 0) {
        set_errno_result(r, "mkdir runtime probe dir");
        return;
    }
    snprintf(path, sizeof(path), "%s/write-test.%ld", dir, (long)getpid());
    fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (fd < 0) {
        set_errno_result(r, "create temp file");
        return;
    }
    if (write(fd, "ok\n", 3) != 3) {
        close(fd);
        unlink(path);
        set_errno_result(r, "write temp file");
        return;
    }
    close(fd);
    unlink(path);
    set_result(r, 1, 0, path);
}

static void check_exec_runtime(struct check_result *r)
{
    char dir[PATH_MAX], path[PATH_MAX + 64], cmd[PATH_MAX + 128];
    int fd, rc;
    runtime_probe_dir(dir, sizeof(dir));
    if (bb_mkdir_p(dir, 0700) != 0) {
        set_errno_result(r, "mkdir runtime probe dir");
        return;
    }
    snprintf(path, sizeof(path), "%s/exec-test.%ld.sh", dir, (long)getpid());
    fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0700);
    if (fd < 0) {
        set_errno_result(r, "create exec probe");
        return;
    }
    if (write(fd, "#!/bin/sh\nexit 0\n", 17) != 17) {
        close(fd);
        unlink(path);
        set_errno_result(r, "write exec probe");
        return;
    }
    close(fd);
    chmod(path, 0700);
    snprintf(cmd, sizeof(cmd), "%s >/dev/null 2>&1", path);
    rc = system(cmd);
    unlink(path);
    if (rc != -1 && WIFEXITED(rc) && WEXITSTATUS(rc) == 0)
        set_result(r, 1, 0, path);
    else
        set_result(r, 0, 0, "runtime root is not executable or /bin/sh cannot run script");
}

static void check_fork_probe(struct check_result *r)
{
    pid_t pid;
    int status;
    pid = fork();
    if (pid < 0) {
        set_errno_result(r, "fork");
        return;
    }
    if (pid == 0)
        _exit(0);
    if (waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0)
        set_result(r, 1, 0, "fork/wait ok");
    else
        set_result(r, 0, 0, "fork child did not exit cleanly");
}

static void check_spawn_sh(struct check_result *r)
{
    int rc = system("/bin/sh -c 'exit 0' >/dev/null 2>&1");
    if (rc != -1 && WIFEXITED(rc) && WEXITSTATUS(rc) == 0)
        set_result(r, 1, 0, "/bin/sh");
    else
        set_result(r, 0, 0, "/bin/sh failed");
}

static void check_pipe_probe(struct check_result *r)
{
    int fds[2];
    char c = 0;
    if (pipe(fds) != 0) {
        set_errno_result(r, "pipe");
        return;
    }
    if (write(fds[1], "x", 1) != 1 || read(fds[0], &c, 1) != 1 || c != 'x') {
        close(fds[0]);
        close(fds[1]);
        set_errno_result(r, "pipe io");
        return;
    }
    close(fds[0]);
    close(fds[1]);
    set_result(r, 1, 0, "pipe read/write ok");
}

static void check_pty_probe(struct check_result *r)
{
    int fd = open("/dev/ptmx", O_RDWR | O_NOCTTY);
    if (fd >= 0) {
        close(fd);
        set_result(r, 1, 0, "/dev/ptmx");
        return;
    }
    if (access("/dev/pts", F_OK) != 0)
        set_result(r, 0, 0, "/dev/pts missing");
    else
        set_errno_result(r, "open /dev/ptmx");
}

static void check_readable_path(struct check_result *r, const char *path)
{
    if (access(path, R_OK) == 0)
        set_result(r, 1, 0, path);
    else if (access(path, F_OK) == 0)
        set_errno_result(r, path);
    else
        set_result(r, 0, 0, "missing");
}

static void check_bind_localhost(struct check_result *r)
{
    int fd;
    struct sockaddr_in addr;

    fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        set_errno_result(r, "socket");
        return;
    }
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = 0;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) == 0)
        set_result(r, 1, 0, "127.0.0.1 ephemeral");
    else
        set_errno_result(r, "bind localhost");
    close(fd);
}

static int connect_with_timeout(const char *host, const char *port, char *detail, size_t detailsz)
{
    struct addrinfo hints, *res = NULL, *ai;
    int ok = 0;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, port, &hints, &res) != 0) {
        snprintf(detail, detailsz, "resolve failed");
        return 0;
    }
    for (ai = res; ai; ai = ai->ai_next) {
        int fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        int flags, err = 0;
        socklen_t errsz = sizeof(err);
        fd_set wfds;
        struct timeval tv;
        if (fd < 0)
            continue;
        flags = fcntl(fd, F_GETFL, 0);
        if (flags >= 0)
            fcntl(fd, F_SETFL, flags | O_NONBLOCK);
        if (connect(fd, ai->ai_addr, ai->ai_addrlen) == 0) {
            ok = 1;
            close(fd);
            break;
        }
        if (errno != EINPROGRESS) {
            snprintf(detail, detailsz, "%s", strerror(errno));
            close(fd);
            continue;
        }
        FD_ZERO(&wfds);
        FD_SET(fd, &wfds);
        tv.tv_sec = 2;
        tv.tv_usec = 0;
        if (select(fd + 1, NULL, &wfds, NULL, &tv) > 0 &&
            getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &errsz) == 0 && err == 0)
            ok = 1;
        else if (err)
            snprintf(detail, detailsz, "%s", strerror(err));
        else
            snprintf(detail, detailsz, "timeout");
        close(fd);
        if (ok)
            break;
    }
    freeaddrinfo(res);
    if (ok)
        snprintf(detail, detailsz, "%s:%s", host, port);
    return ok;
}

static void url_encode_request_name(const char *in, char *out, size_t outsz)
{
    static const char hex[] = "0123456789ABCDEF";
    size_t i = 0;

    while (in && *in && i + 1 < outsz) {
        unsigned char c = (unsigned char)*in++;
        if ((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
            (c >= '0' && c <= '9') || c == '-' || c == '_' ||
            c == '.' || c == '/' || c == '~') {
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

static void check_outbound_operator(struct check_result *r)
{
    char detail[256];
    const char *host = BB_OPERATOR_SERVER_HOST;
    const char *port = !strcmp(BB_RSHELL_TRANSPORT, "ssh") ? BB_OPERATOR_SERVER_SSH_PORT : BB_RSHELL_SOCAT_PORT;
    if (!host || !*host || !strcmp(BB_RSHELL_TRANSPORT, "none")) {
        set_result(r, 0, 1, "operator endpoint not configured");
        return;
    }
    detail[0] = '\0';
    set_result(r, connect_with_timeout(host, port, detail, sizeof(detail)), 0, detail);
}

static void check_operator_upload(struct check_result *r, const struct reality_opts *opts)
{
    char dir[PATH_MAX], path[PATH_MAX + 64], portbuf[32];
    int fd, rc;
    char *argv[9];
    int argc = 0;

    if (!opts->check_upload) {
        set_result(r, 0, 1, "enable with --check-upload");
        return;
    }
    if (!opts->operator_host || !*opts->operator_host) {
        set_result(r, 0, 1, "operator host not configured");
        return;
    }
    runtime_probe_dir(dir, sizeof(dir));
    if (bb_mkdir_p(dir, 0700) != 0) {
        set_errno_result(r, "mkdir runtime probe dir");
        return;
    }
    snprintf(path, sizeof(path), "%s/upload-check.%ld.txt", dir, (long)getpid());
    fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (fd < 0) {
        set_errno_result(r, "create upload probe");
        return;
    }
    if (write(fd, "busierbox reality-test upload\n", 30) != 30) {
        close(fd);
        unlink(path);
        set_errno_result(r, "write upload probe");
        return;
    }
    close(fd);
    snprintf(portbuf, sizeof(portbuf), "%s", opts->file_port && *opts->file_port ? opts->file_port : BB_OPERATOR_FILE_SERVICE_PORT);
    argv[argc++] = "--host";
    argv[argc++] = (char *)opts->operator_host;
    argv[argc++] = "--port";
    argv[argc++] = portbuf;
    argv[argc++] = "--tls";
    argv[argc++] = (char *)(opts->tls && *opts->tls ? opts->tls : BB_OPERATOR_FILE_SERVICE_TLS);
    argv[argc++] = "--dest";
    argv[argc++] = "reality-test-upload.txt";
    argv[argc++] = "--quiet";
    rc = bb_operator_upload_file(path, "busierbox-reality-upload.txt", "reality-test", argc, argv);
    unlink(path);
    if (rc == 0)
        set_result(r, 1, 0, "upload accepted by operator file-service");
    else
        set_result(r, 0, 0, "operator upload failed");
}

static void check_operator_fetch(struct check_result *r, const struct reality_opts *opts)
{
    char detail[256], encoded[PATH_MAX * 3], request[PATH_MAX * 4], portbuf[32], hostbuf[256];
    struct addrinfo hints, *res = NULL, *ai;
    int ok = 0;

    if (!opts->fetch_request || !*opts->fetch_request) {
        set_result(r, 0, 1, "enable with --check-fetch REQUEST");
        return;
    }
    if (!opts->operator_host || !*opts->operator_host) {
        set_result(r, 0, 1, "operator host not configured");
        return;
    }
    if (strcmp(opts->tls && *opts->tls ? opts->tls : BB_OPERATOR_FILE_SERVICE_TLS, "no")) {
        set_result(r, 0, 1, "active fetch check currently requires --no-tls");
        return;
    }
    snprintf(portbuf, sizeof(portbuf), "%s", opts->file_port && *opts->file_port ? opts->file_port : BB_OPERATOR_FILE_SERVICE_PORT);
    snprintf(hostbuf, sizeof(hostbuf), "%s", opts->operator_host);
    url_encode_request_name(opts->fetch_request, encoded, sizeof(encoded));
    snprintf(request, sizeof(request),
             "GET /fetch?name=%s HTTP/1.1\r\nHost: %s\r\nConnection: close\r\n\r\n",
             encoded, hostbuf);
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(hostbuf, portbuf, &hints, &res) != 0) {
        set_result(r, 0, 0, "resolve failed");
        return;
    }
    detail[0] = '\0';
    for (ai = res; ai; ai = ai->ai_next) {
        int fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        char buf[256];
        ssize_t n;
        if (fd < 0)
            continue;
        if (connect(fd, ai->ai_addr, ai->ai_addrlen) != 0) {
            snprintf(detail, sizeof(detail), "%s", strerror(errno));
            close(fd);
            continue;
        }
        if (write(fd, request, strlen(request)) < 0) {
            snprintf(detail, sizeof(detail), "write request: %s", strerror(errno));
            close(fd);
            continue;
        }
        n = read(fd, buf, sizeof(buf) - 1);
        close(fd);
        if (n > 0) {
            buf[n] = '\0';
            if (strstr(buf, " 200 ")) {
                ok = 1;
                snprintf(detail, sizeof(detail), "fetch accepted by operator file-service");
                break;
            }
            snprintf(detail, sizeof(detail), "%.120s", buf);
        }
    }
    freeaddrinfo(res);
    set_result(r, ok, 0, detail[0] ? detail : "no response");
}

static void check_payload_busybox(struct check_result *r)
{
    char payload[PATH_MAX], busybox[PATH_MAX + 64];
    if (bb_candidate_payload_dir(payload, sizeof(payload)) != 0) {
        set_result(r, 0, 1, "payload not extracted");
        return;
    }
    snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
    if (bb_executable_file(busybox))
        set_result(r, 1, 0, busybox);
    else
        set_result(r, 0, 0, "payload BusyBox missing or not executable");
}

static void check_core_payload_extractable(struct check_result *r)
{
    char root[PATH_MAX];
    if (!bb_embedded_payload_available()) {
        set_result(r, 0, 1, "no embedded payload");
        return;
    }
    if (bb_extract_root_usable(BB_RUNTIME_ROOT)) {
        set_result(r, 1, 0, BB_RUNTIME_ROOT);
        return;
    }
    if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") && bb_extract_root_usable(BB_RUNTIME_FALLBACK_ROOT)) {
        set_result(r, 1, 0, BB_RUNTIME_FALLBACK_ROOT);
        return;
    }
    if (bb_choose_extract_root(root, sizeof(root)) == 0) {
        set_result(r, 1, 0, root);
        return;
    }
    set_result(r, 0, 0, "no usable runtime root for extraction");
}

static void check_heavy_tool(struct check_result *r)
{
    const char *const *tools = bb_payload_heavy_tools();
    char payload[PATH_MAX], path[PATH_MAX + 128];
    if (!tools[0]) {
        set_result(r, 0, 1, "no heavy tools selected");
        return;
    }
    if (bb_candidate_payload_dir(payload, sizeof(payload)) != 0) {
        set_result(r, 0, 1, "payload not extracted");
        return;
    }
    snprintf(path, sizeof(path), "%s/bin/%s", payload, tools[0]);
    if (bb_executable_file(path))
        set_result(r, 1, 0, path);
    else
        set_result(r, 0, 0, "selected heavy tool missing or not executable");
}

static void check_dmesg_readable(struct check_result *r)
{
    if (access("/dev/kmsg", R_OK) == 0)
        set_result(r, 1, 0, "/dev/kmsg");
    else if (access("/proc/kmsg", R_OK) == 0)
        set_result(r, 1, 0, "/proc/kmsg");
    else
        set_result(r, 0, 0, "kernel message buffer not readable");
}

static void run_checks(struct check_result checks[], size_t n, const struct reality_opts *opts)
{
    size_t i;
    for (i = 0; i < n; i++) {
        if (!strcmp(checks[i].name, "runtime_root_writable"))
            check_runtime_root(&checks[i]);
        else if (!strcmp(checks[i].name, "temporary_file"))
            check_temp_file(&checks[i]);
        else if (!strcmp(checks[i].name, "runtime_root_executable"))
            check_exec_runtime(&checks[i]);
        else if (!strcmp(checks[i].name, "fork"))
            check_fork_probe(&checks[i]);
        else if (!strcmp(checks[i].name, "spawn_sh"))
            check_spawn_sh(&checks[i]);
        else if (!strcmp(checks[i].name, "pty"))
            check_pty_probe(&checks[i]);
        else if (!strcmp(checks[i].name, "pipes"))
            check_pipe_probe(&checks[i]);
        else if (!strcmp(checks[i].name, "read_proc"))
            check_readable_path(&checks[i], "/proc");
        else if (!strcmp(checks[i].name, "read_sys"))
            check_readable_path(&checks[i], "/sys");
        else if (!strcmp(checks[i].name, "bind_localhost"))
            check_bind_localhost(&checks[i]);
        else if (!strcmp(checks[i].name, "connect_operator"))
            check_outbound_operator(&checks[i]);
        else if (!strcmp(checks[i].name, "upload_operator"))
            check_operator_upload(&checks[i], opts);
        else if (!strcmp(checks[i].name, "fetch_operator"))
            check_operator_fetch(&checks[i], opts);
        else if (!strcmp(checks[i].name, "extract_core_payload"))
            check_core_payload_extractable(&checks[i]);
        else if (!strcmp(checks[i].name, "exec_payload_busybox"))
            check_payload_busybox(&checks[i]);
        else if (!strcmp(checks[i].name, "exec_heavy_tool"))
            check_heavy_tool(&checks[i]);
        else if (!strcmp(checks[i].name, "tmp_noexec"))
            set_result(&checks[i], bb_dir_is_noexec("/tmp"), 0, bb_dir_is_noexec("/tmp") ? "/tmp noexec" : "/tmp exec allowed");
        else if (!strcmp(checks[i].name, "rootfs_read_only"))
            set_result(&checks[i], access("/", W_OK) != 0, 0, access("/", W_OK) == 0 ? "rootfs writable by current user" : "rootfs not writable by current user");
        else if (!strcmp(checks[i].name, "ptrace"))
            set_result(&checks[i], !strcmp(bb_ptrace_probe_status(), "basic-ok"), 0, bb_ptrace_probe_status());
        else if (!strcmp(checks[i].name, "dmesg_readable"))
            check_dmesg_readable(&checks[i]);
        else if (!strcmp(checks[i].name, "procfs_partial"))
            set_result(&checks[i], access("/proc/self", R_OK) == 0 && access("/proc/mounts", R_OK) == 0, 0, "requires /proc/self and /proc/mounts");
    }
}

static int is_constraint_check(const char *name)
{
    return !strcmp(name, "tmp_noexec") ||
        !strcmp(name, "rootfs_read_only") ||
        !strcmp(name, "procfs_partial");
}

static int is_operator_check(const char *name)
{
    return !strcmp(name, "connect_operator") ||
        !strcmp(name, "upload_operator") ||
        !strcmp(name, "fetch_operator");
}

static int constraint_detected(const struct check_result *r)
{
    if (!strcmp(r->name, "procfs_partial"))
        return !r->skipped && !r->ok;
    return !r->skipped && r->ok;
}

static const char *check_status(const struct check_result *r)
{
    return r->skipped ? "skipped" : (r->ok ? "pass" : "fail");
}

static const char *check_type(const struct check_result *r)
{
    if (is_constraint_check(r->name))
        return "constraint";
    if (is_operator_check(r->name))
        return "operator";
    return "capability";
}

static void print_check_index_array(struct check_result checks[], size_t n, const char *field, const char *value)
{
    size_t i;
    int first = 1;

    putchar('[');
    for (i = 0; i < n; i++) {
        const char *candidate = "";
        if (!strcmp(field, "name"))
            candidate = checks[i].name;
        else if (!strcmp(field, "status"))
            candidate = check_status(&checks[i]);
        else if (!strcmp(field, "type"))
            candidate = check_type(&checks[i]);
        if (strcmp(candidate, value))
            continue;
        printf("%s%zu", first ? "" : ",", i);
        first = 0;
    }
    putchar(']');
}

static void print_check_indexes(struct check_result checks[], size_t n)
{
    static const char *statuses[] = {"pass", "fail", "skipped", NULL};
    static const char *types[] = {"capability", "operator", "constraint", NULL};
    size_t i;

    printf(",\"checks_by_name\":{");
    for (i = 0; i < n; i++) {
        if (i)
            putchar(',');
        bb_json_string(stdout, checks[i].name);
        putchar(':');
        print_check_index_array(checks, n, "name", checks[i].name);
    }
    printf("},\"checks_by_status\":{");
    for (i = 0; statuses[i]; i++) {
        if (i)
            putchar(',');
        bb_json_string(stdout, statuses[i]);
        putchar(':');
        print_check_index_array(checks, n, "status", statuses[i]);
    }
    printf("},\"checks_by_type\":{");
    for (i = 0; types[i]; i++) {
        if (i)
            putchar(',');
        bb_json_string(stdout, types[i]);
        putchar(':');
        print_check_index_array(checks, n, "type", types[i]);
    }
    putchar('}');
}

static void print_json(struct check_result checks[], size_t n)
{
    size_t i;
    int pass = 0, fail = 0, skip = 0;
    int capability_pass = 0, capability_fail = 0, operator_pass = 0, operator_fail = 0, operator_skip = 0;
    int tmp_noexec = 0, rootfs_read_only = 0, procfs_partial = 0;
    printf("{\"schema\":1,\"runtime_root\":");
    bb_json_string(stdout, BB_RUNTIME_ROOT);
    printf(",\"operator_host\":");
    bb_json_string(stdout, BB_OPERATOR_SERVER_HOST);
    printf(",\"checks\":[");
    for (i = 0; i < n; i++) {
        if (i)
            putchar(',');
        printf("{\"name\":");
        bb_json_string(stdout, checks[i].name);
        printf(",\"status\":");
        bb_json_string(stdout, check_status(&checks[i]));
        printf(",\"type\":");
        bb_json_string(stdout, check_type(&checks[i]));
        printf(",\"ok\":%s,\"skipped\":%s", (!checks[i].skipped && checks[i].ok) ? "true" : "false", checks[i].skipped ? "true" : "false");
        if (is_constraint_check(checks[i].name))
            printf(",\"detected\":%s", constraint_detected(&checks[i]) ? "true" : "false");
        else
            printf(",\"available\":%s", (!checks[i].skipped && checks[i].ok) ? "true" : "false");
        printf(",\"detail\":");
        bb_json_string(stdout, checks[i].detail);
        printf("}");
        if (checks[i].skipped)
            skip++;
        else if (checks[i].ok)
            pass++;
        else
            fail++;
        if (is_operator_check(checks[i].name)) {
            if (checks[i].skipped)
                operator_skip++;
            else if (checks[i].ok)
                operator_pass++;
            else
                operator_fail++;
        } else if (!is_constraint_check(checks[i].name) && !checks[i].skipped) {
            if (checks[i].ok)
                capability_pass++;
            else
                capability_fail++;
        }
        if (!strcmp(checks[i].name, "tmp_noexec"))
            tmp_noexec = constraint_detected(&checks[i]);
        else if (!strcmp(checks[i].name, "rootfs_read_only"))
            rootfs_read_only = constraint_detected(&checks[i]);
        else if (!strcmp(checks[i].name, "procfs_partial"))
            procfs_partial = constraint_detected(&checks[i]);
    }
    printf("]");
    print_check_indexes(checks, n);
    printf(",\"api_collections\":{\"checks\":{\"name\":\"checks\",\"count_summary_key\":\"summary.check_count\",\"indexes\":[\"checks_by_name\",\"checks_by_status\",\"checks_by_type\"]}}");
    printf(",\"summary\":{\"check_count\":%zu,\"pass\":%d,\"fail\":%d,\"skipped\":%d", n, pass, fail, skip);
    printf(",\"capability_pass\":%d,\"capability_fail\":%d", capability_pass, capability_fail);
    printf(",\"operator_pass\":%d,\"operator_fail\":%d,\"operator_skipped\":%d", operator_pass, operator_fail, operator_skip);
    printf(",\"constraints\":{\"tmp_noexec\":%s,\"rootfs_read_only\":%s,\"procfs_partial\":%s}}}\n",
           tmp_noexec ? "true" : "false",
           rootfs_read_only ? "true" : "false",
           procfs_partial ? "true" : "false");
}

static void print_text(struct check_result checks[], size_t n)
{
    size_t i;
    int pass = 0, fail = 0, skip = 0;
    puts("BusierBox reality-test");
    printf("runtime_root=%s\n", BB_RUNTIME_ROOT);
    for (i = 0; i < n; i++) {
        const char *status = checks[i].skipped ? "skipped" : (checks[i].ok ? "pass" : "fail");
        printf("%-24s %s", checks[i].name, status);
        if (checks[i].detail[0])
            printf("  %s", checks[i].detail);
        putchar('\n');
        if (checks[i].skipped)
            skip++;
        else if (checks[i].ok)
            pass++;
        else
            fail++;
    }
    printf("summary pass=%d fail=%d skipped=%d\n", pass, fail, skip);
}

int applet_reality_test_main(int argc, char **argv)
{
    struct reality_opts opts;
    struct check_result checks[] = {
        {"runtime_root_writable", 0, 0, ""},
        {"temporary_file", 0, 0, ""},
        {"runtime_root_executable", 0, 0, ""},
        {"fork", 0, 0, ""},
        {"spawn_sh", 0, 0, ""},
        {"pty", 0, 0, ""},
        {"pipes", 0, 0, ""},
        {"read_proc", 0, 0, ""},
        {"read_sys", 0, 0, ""},
        {"bind_localhost", 0, 0, ""},
        {"connect_operator", 0, 0, ""},
        {"upload_operator", 0, 0, ""},
        {"fetch_operator", 0, 0, ""},
        {"extract_core_payload", 0, 0, ""},
        {"exec_payload_busybox", 0, 0, ""},
        {"exec_heavy_tool", 0, 0, ""},
        {"tmp_noexec", 0, 0, ""},
        {"rootfs_read_only", 0, 0, ""},
        {"ptrace", 0, 0, ""},
        {"dmesg_readable", 0, 0, ""},
        {"procfs_partial", 0, 0, ""},
    };
    int json = 0;
    int i;

    opts.operator_host = BB_OPERATOR_SERVER_HOST;
    opts.file_port = BB_OPERATOR_FILE_SERVICE_PORT;
    opts.tls = BB_OPERATOR_FILE_SERVICE_TLS;
    opts.check_upload = 0;
    opts.fetch_request = NULL;

    if (is_help(argc, argv)) {
        puts("usage: busierbox reality-test [--json] [--operator-host HOST] [--file-port PORT] [--tls yes|no|--no-tls] [--check-upload] [--check-fetch REQUEST]");
        puts("       busierbox reality-test push [--host HOST] [--port PORT] [--tls yes|no]");
        puts("Actively probes target runtime capabilities and degrades gracefully on broken systems.");
        puts("Upload/fetch checks are side-effecting and run only when explicitly requested.");
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "push")) {
        const char *roots[] = { BB_RUNTIME_ROOT, ".", "/tmp", NULL };
        char path[PATH_MAX];
        int r;
        if (argc > 2 && (!strcmp(argv[2], "--help") || !strcmp(argv[2], "-h"))) {
            puts("usage: busierbox reality-test push [--host HOST] [--port PORT] [--tls yes|no]");
            puts("Generate reality-test JSON and upload it to the receive-only operator file service.");
            puts("Operator upload/fetch probes are not enabled by this generated report.");
            return 0;
        }
        for (r = 0; roots[r]; r++) {
            int fd, saved, rc;
            char *reality_argv[] = { "reality-test", "--json", NULL };
            if (roots[r][0] && strcmp(roots[r], "."))
                bb_mkdir_p(roots[r], 0700);
            snprintf(path, sizeof(path), "%s/.busierbox-reality-test.%ld.XXXXXX", roots[r], (long)getpid());
            fd = mkstemp(path);
            if (fd < 0)
                continue;
            fflush(stdout);
            saved = dup(STDOUT_FILENO);
            if (saved < 0 || dup2(fd, STDOUT_FILENO) < 0) {
                if (saved >= 0)
                    close(saved);
                close(fd);
                unlink(path);
                continue;
            }
            rc = applet_reality_test_main(2, reality_argv);
            fflush(stdout);
            dup2(saved, STDOUT_FILENO);
            close(saved);
            close(fd);
            if (rc != 0) {
                unlink(path);
                return rc;
            }
            rc = bb_operator_upload_file(path, "busierbox-reality-test.json", "reality-test", argc - 2, argv + 2);
            unlink(path);
            return rc;
        }
        fputs("reality-test: unable to create temporary reality-test JSON\n", stderr);
        return 1;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--operator-host")) {
            if (++i >= argc) {
                fputs("reality-test: --operator-host requires a value\n", stderr);
                return 2;
            }
            opts.operator_host = argv[i];
        } else if (!strcmp(argv[i], "--file-port")) {
            if (++i >= argc) {
                fputs("reality-test: --file-port requires a value\n", stderr);
                return 2;
            }
            opts.file_port = argv[i];
        } else if (!strcmp(argv[i], "--tls")) {
            if (++i >= argc || (strcmp(argv[i], "yes") && strcmp(argv[i], "no"))) {
                fputs("reality-test: --tls requires yes or no\n", stderr);
                return 2;
            }
            opts.tls = argv[i];
        } else if (!strcmp(argv[i], "--no-tls")) {
            opts.tls = "no";
        } else if (!strcmp(argv[i], "--check-upload")) {
            opts.check_upload = 1;
        } else if (!strcmp(argv[i], "--check-fetch")) {
            if (++i >= argc) {
                fputs("reality-test: --check-fetch requires a request name\n", stderr);
                return 2;
            }
            opts.fetch_request = argv[i];
        }
        else {
            fprintf(stderr, "reality-test: unknown option %s\n", argv[i]);
            return 2;
        }
    }

    run_checks(checks, sizeof(checks) / sizeof(checks[0]), &opts);
    if (json)
        print_json(checks, sizeof(checks) / sizeof(checks[0]));
    else
        print_text(checks, sizeof(checks) / sizeof(checks[0]));
    return 0;
}
