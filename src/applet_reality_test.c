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

static void run_checks(struct check_result checks[], size_t n)
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
            set_result(&checks[i], 0, 1, "requires configured file-service and upload side effect");
        else if (!strcmp(checks[i].name, "fetch_operator"))
            set_result(&checks[i], 0, 1, "requires staged operator file");
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

static void print_json(struct check_result checks[], size_t n)
{
    size_t i;
    int pass = 0, fail = 0, skip = 0;
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
        bb_json_string(stdout, checks[i].skipped ? "skipped" : (checks[i].ok ? "pass" : "fail"));
        printf(",\"ok\":%s,\"detail\":", (!checks[i].skipped && checks[i].ok) ? "true" : "false");
        bb_json_string(stdout, checks[i].detail);
        printf("}");
        if (checks[i].skipped)
            skip++;
        else if (checks[i].ok)
            pass++;
        else
            fail++;
    }
    printf("],\"summary\":{\"pass\":%d,\"fail\":%d,\"skipped\":%d}}\n", pass, fail, skip);
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

    if (is_help(argc, argv)) {
        puts("usage: busierbox reality-test [--json]");
        puts("Actively probes target runtime capabilities and degrades gracefully on broken systems.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else {
            fprintf(stderr, "reality-test: unknown option %s\n", argv[i]);
            return 2;
        }
    }

    run_checks(checks, sizeof(checks) / sizeof(checks[0]));
    if (json)
        print_json(checks, sizeof(checks) / sizeof(checks[0]));
    else
        print_text(checks, sizeof(checks) / sizeof(checks[0]));
    return 0;
}
