#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <netdb.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "applets.h"
#include "effective_config.h"
#include "command_queue_policy.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

struct poll_run_result {
    int attempted;
    int attempts;
    int successes;
    int failures;
    int delivered_commands;
    int rejected_commands;
    int result_uploads;
    int result_upload_failures;
    int last_delay_sec;
    int stopped_by_limit;
    int stopped_by_signal;
    int event_count;
    int event_info_count;
    int event_warning_count;
    int event_poll_attempt_count;
    int event_poll_complete_count;
    int event_poll_no_command_count;
    int event_poll_error_count;
    int event_execution_decision_count;
    int event_result_upload_count;
    int event_result_upload_error_count;
    int event_shutdown_count;
    int event_daemon_state_error_count;
    char last_status[64];
    char last_error[160];
    char last_command_id[96];
    char last_command[512];
    int last_timeout_sec;
    int last_max_output_bytes;
};

struct daemon_state {
    int present;
    int valid;
    int running;
    int ownership_verified;
    int stale;
    int pid;
    char status[64];
    char error[160];
    char started_at[32];
    char endpoint[512];
};

struct stop_result {
    int attempted;
    int signaled;
    int stopped;
    int missing;
    int stale;
    int skipped;
    char status[64];
    char error[160];
};

static volatile sig_atomic_t stop_daemon;

static void utc_timestamp(char *out, size_t outsz);

static int yes_value(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "on"));
}

static const char *execution_rejection_reason(void)
{
    if (!strcmp(BB_COMMAND_QUEUE_EXECUTION, "metadata-only"))
        return "command queue execution mode is metadata-only";
    return "command queue execution mode execute requested, but target command execution is not implemented";
}

static int valid_backoff_value(const char *s)
{
    return s && (!strcmp(s, "none") || !strcmp(s, "linear") || !strcmp(s, "exponential"));
}

static int parse_nonnegative_int(const char *s, int fallback)
{
    char *end = NULL;
    long v;

    if (!s || !s[0])
        return fallback;
    errno = 0;
    v = strtol(s, &end, 10);
    if (errno || !end || *end || v < 0 || v > 86400)
        return fallback;
    return (int)v;
}

static int parse_pid_value(const char *s)
{
    char *end = NULL;
    long v;

    if (!s || !s[0])
        return 0;
    errno = 0;
    v = strtol(s, &end, 10);
    if (errno || !end || *end || v <= 1 || v > 4194304)
        return 0;
    return (int)v;
}

static int poll_delay_for_attempt(int attempt, int interval_sec, const char *backoff,
                                  int max_interval_sec, int jitter_pct)
{
    int delay = interval_sec;

    if (interval_sec < 0)
        interval_sec = 0;
    if (max_interval_sec < interval_sec)
        max_interval_sec = interval_sec;
    if (!strcmp(backoff ? backoff : "", "linear"))
        delay = interval_sec * (attempt + 1);
    else if (!strcmp(backoff ? backoff : "", "exponential")) {
        int i;
        delay = interval_sec;
        for (i = 0; i < attempt && delay < max_interval_sec; i++) {
            if (delay > max_interval_sec / 2) {
                delay = max_interval_sec;
                break;
            }
            delay *= 2;
        }
    }
    if (delay > max_interval_sec)
        delay = max_interval_sec;
    if (jitter_pct > 0 && delay > 0) {
        int span = (delay * jitter_pct) / 100;
        if (span > 0)
            delay = delay - span + (int)((time(NULL) + attempt) % (unsigned int)(span * 2 + 1));
    }
    return delay < 0 ? 0 : delay;
}

static void handle_stop(int signo)
{
    (void)signo;
    stop_daemon = 1;
}

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static void print_help(void)
{
    puts("usage: busierbox command-queue [status|poll|once|daemon|stop] [--json] [--dry-run|--live] [--operator-host HOST]");
    puts("       busierbox command-queue daemon --live [--max-polls N] [--poll-interval-sec N] [--poll-backoff none|linear|exponential] [--poll-jitter-pct N] [--poll-max-interval-sec N] [--event-log PATH] [--state-file PATH]");
    puts("Inspect explicit opt-in command queue policy and target polling state.");
    puts("Live mode can receive queued command metadata; command execution is not implemented.");
}

static int mode_would_poll(const char *mode, int enabled, const char *operator_host, const struct command_queue_policy_report *report)
{
    return bb_command_queue_policy_valid(report) && enabled && operator_host && operator_host[0] &&
           strcmp(mode, "status") != 0 && strcmp(mode, "stop") != 0;
}

static const char *mode_status(const char *mode, int enabled, const char *operator_host,
                               const struct command_queue_policy_report *report, int dry_run)
{
    if (!bb_command_queue_policy_valid(report))
        return "invalid_policy";
    if (!strcmp(mode, "stop"))
        return "stop_requested";
    if (!enabled)
        return "disabled";
    if (!strcmp(mode, "status"))
        return "configured";
    if (!operator_host || !operator_host[0])
        return "missing_operator_host";
    if (!dry_run)
        return "polling";
    if (!strcmp(mode, "poll"))
        return "poll_dry_run";
    if (!strcmp(mode, "once"))
        return "once_dry_run";
    if (!strcmp(mode, "daemon"))
        return "daemon_dry_run";
    return "unknown";
}

static int mode_requires_operator_host(const char *mode)
{
    return strcmp(mode, "status") != 0 && strcmp(mode, "stop") != 0;
}

static const char *mode_lifecycle(const char *mode)
{
    if (!strcmp(mode, "status"))
        return "inspect";
    if (!strcmp(mode, "stop"))
        return "stop";
    if (!strcmp(mode, "poll"))
        return "single-poll";
    if (!strcmp(mode, "once"))
        return "single-cycle";
    if (!strcmp(mode, "daemon"))
        return "long-running";
    return "unknown";
}

static void default_state_path(char *out, size_t outsz)
{
    snprintf(out, outsz, "%s/run/command-queue-daemon.state", BB_RUNTIME_ROOT);
}

static int ensure_parent_dir(const char *path)
{
    char dir[PATH_MAX];
    char *slash;

    if (!path || !path[0])
        return -1;
    snprintf(dir, sizeof(dir), "%s", path);
    slash = strrchr(dir, '/');
    if (!slash)
        return 0;
    if (slash == dir)
        slash[1] = '\0';
    else
        *slash = '\0';
    return bb_mkdir_p(dir, 0700);
}

static void kv_value(const char *line, const char *key, char *out, size_t outsz)
{
    size_t key_len = strlen(key);

    if (outsz)
        out[0] = '\0';
    if (strncmp(line, key, key_len) || line[key_len] != '=')
        return;
    snprintf(out, outsz, "%s", line + key_len + 1);
    if (outsz && out[0]) {
        size_t len = strlen(out);
        while (len > 0 && (out[len - 1] == '\n' || out[len - 1] == '\r')) {
            out[len - 1] = '\0';
            len--;
        }
    }
}

static int command_line_looks_owned(int pid)
{
    char path[64];
    FILE *fh;
    char buf[512];
    size_t n, i;
    int saw_command_queue = 0;

    if (pid <= 1)
        return 0;
    snprintf(path, sizeof(path), "/proc/%d/cmdline", pid);
    fh = fopen(path, "rb");
    if (!fh)
        return 0;
    n = fread(buf, 1, sizeof(buf) - 1, fh);
    fclose(fh);
    buf[n] = '\0';
    for (i = 0; i < n; i++) {
        if (buf[i] == '\0')
            buf[i] = ' ';
    }
    if (strstr(buf, "command-queue") || strstr(buf, "command_queue"))
        saw_command_queue = 1;
    return saw_command_queue;
}

static void read_daemon_state(const char *path, struct daemon_state *state)
{
    FILE *fh;
    char line[768];
    int saw_schema = 0, saw_service = 0;

    memset(state, 0, sizeof(*state));
    snprintf(state->status, sizeof(state->status), "missing");
    if (!path || !path[0]) {
        snprintf(state->error, sizeof(state->error), "missing state path");
        return;
    }
    fh = fopen(path, "r");
    if (!fh) {
        if (errno != ENOENT)
            snprintf(state->error, sizeof(state->error), "%s", strerror(errno));
        return;
    }
    state->present = 1;
    while (fgets(line, sizeof(line), fh)) {
        char value[512];

        kv_value(line, "schema", value, sizeof(value));
        if (value[0] && !strcmp(value, "1"))
            saw_schema = 1;
        kv_value(line, "service", value, sizeof(value));
        if (value[0] && !strcmp(value, "command-queue"))
            saw_service = 1;
        kv_value(line, "pid", value, sizeof(value));
        if (value[0])
            state->pid = parse_pid_value(value);
        kv_value(line, "started_at", value, sizeof(value));
        if (value[0])
            snprintf(state->started_at, sizeof(state->started_at), "%s", value);
        kv_value(line, "endpoint", value, sizeof(value));
        if (value[0])
            snprintf(state->endpoint, sizeof(state->endpoint), "%s", value);
    }
    fclose(fh);
    state->valid = saw_schema && saw_service && state->pid > 1;
    if (!state->valid) {
        snprintf(state->status, sizeof(state->status), "invalid");
        snprintf(state->error, sizeof(state->error), "invalid command queue daemon state");
        return;
    }
    if (kill((pid_t)state->pid, 0) == 0) {
        state->running = 1;
        state->ownership_verified = command_line_looks_owned(state->pid);
        snprintf(state->status, sizeof(state->status), "running");
    } else {
        state->stale = 1;
        snprintf(state->status, sizeof(state->status), "stale");
        snprintf(state->error, sizeof(state->error), "%s", strerror(errno));
    }
}

static int write_daemon_state(const char *path, const char *mode, const char *endpoint,
                              int interval_sec, int jitter_pct, const char *backoff,
                              int max_interval_sec, int max_polls, const char *event_log,
                              char *err, size_t errsz)
{
    FILE *fh;
    char ts[32];

    if (!path || !path[0])
        return 0;
    if (ensure_parent_dir(path) != 0) {
        snprintf(err, errsz, "state directory failed: %s", strerror(errno));
        return -1;
    }
    fh = fopen(path, "w");
    if (!fh) {
        snprintf(err, errsz, "state write failed: %s", strerror(errno));
        return -1;
    }
    utc_timestamp(ts, sizeof(ts));
    fprintf(fh, "schema=1\nservice=command-queue\npid=%ld\nmode=%s\nstarted_at=%s\n",
            (long)getpid(), mode, ts);
    fprintf(fh, "endpoint=%s\npoll_interval_sec=%d\npoll_jitter_pct=%d\npoll_backoff=%s\npoll_max_interval_sec=%d\nmax_polls=%d\n",
            endpoint ? endpoint : "", interval_sec, jitter_pct, backoff ? backoff : "", max_interval_sec, max_polls);
    fprintf(fh, "event_log=%s\n", event_log ? event_log : "");
    if (fclose(fh) != 0) {
        snprintf(err, errsz, "state close failed: %s", strerror(errno));
        return -1;
    }
    return 0;
}

static void remove_daemon_state_if_ours(const char *path)
{
    struct daemon_state state;

    if (!path || !path[0])
        return;
    read_daemon_state(path, &state);
    if (state.valid && state.pid == (int)getpid())
        unlink(path);
}

static void utc_timestamp(char *out, size_t outsz)
{
    time_t now = time(NULL);
    struct tm tmv;

    if (!outsz)
        return;
    if (now == (time_t)-1 || !gmtime_r(&now, &tmv)) {
        snprintf(out, outsz, "unknown");
        return;
    }
    strftime(out, outsz, "%Y-%m-%dT%H:%M:%SZ", &tmv);
}

static void append_poll_event(const char *path, const char *event, const char *mode,
                              const char *endpoint, int attempt, const char *status,
                              const char *error, const char *command_id,
                              const char *command, int timeout_sec,
                              int max_output_bytes)
{
    FILE *fh;
    char ts[32];
    char id[192];
    int live_poll_event = 0;
    int live_poll_supported = 0;

    if (!path || !path[0])
        return;
    fh = fopen(path, "a");
    if (!fh)
        return;
    if (event && (!strncmp(event, "command_queue_poll_", strlen("command_queue_poll_")) ||
                  !strcmp(event, "command_queue_execution_decision") ||
                  !strncmp(event, "command_queue_result_upload", strlen("command_queue_result_upload"))))
        live_poll_event = 1;
    live_poll_supported = live_poll_event && !strcmp(BB_COMMAND_QUEUE_TLS, "no");
    utc_timestamp(ts, sizeof(ts));
    snprintf(id, sizeof(id), "cqevt-%ld-%d-%s", (long)getpid(), attempt, event ? event : "event");
    fputs("{\"schema\":1,\"ts\":", fh);
    bb_json_string(fh, ts);
    fputs(",\"id\":", fh);
    bb_json_string(fh, id);
    fputs(",\"service\":\"command-queue\",\"event\":", fh);
    bb_json_string(fh, event);
    fputs(",\"level\":", fh);
    bb_json_string(fh, error && error[0] ? "warning" : "info");
    fputs(",\"session\":\"\",\"remote\":", fh);
    bb_json_string(fh, endpoint ? endpoint : "");
    fputs(",\"details\":{\"mode\":", fh);
    bb_json_string(fh, mode);
    fputs(",\"endpoint\":", fh);
    bb_json_string(fh, endpoint ? endpoint : "");
    fprintf(fh, ",\"attempt\":%d,\"executes_commands\":false,\"execution_mode\":", attempt);
    bb_json_string(fh, BB_COMMAND_QUEUE_EXECUTION);
    fprintf(fh, ",\"delivery_supported\":%s,\"result_upload_supported\":%s",
            live_poll_supported ? "true" : "false", live_poll_supported ? "true" : "false");
    fputs(",\"status\":", fh);
    bb_json_string(fh, status ? status : "");
    if (command_id && command_id[0]) {
        fputs(",\"command_id\":", fh);
        bb_json_string(fh, command_id);
    }
    if (command && command[0]) {
        fputs(",\"command\":", fh);
        bb_json_string(fh, command);
    }
    if (timeout_sec > 0)
        fprintf(fh, ",\"timeout_sec\":%d", timeout_sec);
    if (max_output_bytes > 0)
        fprintf(fh, ",\"max_output_bytes\":%d", max_output_bytes);
    if (error && error[0]) {
        fputs(",\"error\":", fh);
        bb_json_string(fh, error);
    }
    fputs("}}\n", fh);
    fclose(fh);
}

static void count_poll_run_event(struct poll_run_result *run, const char *event, const char *error)
{
    if (!run)
        return;
    run->event_count++;
    if (error && error[0])
        run->event_warning_count++;
    else
        run->event_info_count++;
    if (!strcmp(event ? event : "", "command_queue_poll_attempt"))
        run->event_poll_attempt_count++;
    else if (!strcmp(event ? event : "", "command_queue_poll_complete"))
        run->event_poll_complete_count++;
    else if (!strcmp(event ? event : "", "command_queue_poll_no_command"))
        run->event_poll_no_command_count++;
    else if (!strcmp(event ? event : "", "command_queue_poll_error"))
        run->event_poll_error_count++;
    else if (!strcmp(event ? event : "", "command_queue_execution_decision"))
        run->event_execution_decision_count++;
    else if (!strcmp(event ? event : "", "command_queue_result_upload"))
        run->event_result_upload_count++;
    else if (!strcmp(event ? event : "", "command_queue_result_upload_error"))
        run->event_result_upload_error_count++;
    else if (!strcmp(event ? event : "", "command_queue_poll_shutdown"))
        run->event_shutdown_count++;
    else if (!strcmp(event ? event : "", "command_queue_daemon_state_error"))
        run->event_daemon_state_error_count++;
}

static void append_run_poll_event(const char *path, struct poll_run_result *run,
                                  const char *event, const char *mode,
                                  const char *endpoint, int attempt,
                                  const char *status, const char *error)
{
    count_poll_run_event(run, event, error);
    append_poll_event(path, event, mode, endpoint, attempt, status, error,
                      NULL, NULL, 0, 0);
}

static void append_run_poll_command_event(const char *path, struct poll_run_result *run,
                                          const char *event, const char *mode,
                                          const char *endpoint, int attempt,
                                          const char *status, const char *error)
{
    count_poll_run_event(run, event, error);
    append_poll_event(path, event, mode, endpoint, attempt, status, error,
                      run ? run->last_command_id : NULL,
                      run ? run->last_command : NULL,
                      run ? run->last_timeout_sec : 0,
                      run ? run->last_max_output_bytes : 0);
}

static void parse_header_value(const char *response, const char *name, char *out, size_t outsz)
{
    const char *p = response;
    size_t name_len = strlen(name);

    if (outsz)
        out[0] = '\0';
    while (p && *p) {
        const char *line_end = strstr(p, "\r\n");
        size_t line_len = line_end ? (size_t)(line_end - p) : strlen(p);
        if (line_len > name_len + 1 && !strncasecmp(p, name, name_len) && p[name_len] == ':') {
            const char *v = p + name_len + 1;
            while (*v == ' ' || *v == '\t')
                v++;
            snprintf(out, outsz, "%.*s", (int)(line_len - (size_t)(v - p)), v);
            return;
        }
        if (!line_end)
            return;
        p = line_end + 2;
    }
}

static const char *http_body(const char *response)
{
    const char *body;

    if (!response)
        return "";
    body = strstr(response, "\r\n\r\n");
    return body ? body + 4 : "";
}

static int json_get_string_field(const char *json, const char *key, char *out, size_t outsz)
{
    char needle[96];
    const char *p;
    size_t n = 0;

    if (outsz)
        out[0] = '\0';
    if (!json || !key || !out || !outsz)
        return -1;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p)
        return -1;
    p += strlen(needle);
    while (*p == ' ' || *p == '\t')
        p++;
    if (*p != ':')
        return -1;
    p++;
    while (*p == ' ' || *p == '\t')
        p++;
    if (*p != '"')
        return -1;
    p++;
    while (*p && *p != '"' && n + 1 < outsz) {
        if (*p == '\\' && p[1]) {
            p++;
            if (*p == 'n')
                out[n++] = '\n';
            else if (*p == 'r')
                out[n++] = '\r';
            else if (*p == 't')
                out[n++] = '\t';
            else
                out[n++] = *p;
        } else {
            out[n++] = *p;
        }
        p++;
    }
    out[n] = '\0';
    return *p == '"' ? 0 : -1;
}

static int json_get_int_field(const char *json, const char *key, int fallback)
{
    char needle[96];
    const char *p;
    char *end = NULL;
    long v;

    if (!json || !key)
        return fallback;
    snprintf(needle, sizeof(needle), "\"%s\"", key);
    p = strstr(json, needle);
    if (!p)
        return fallback;
    p += strlen(needle);
    while (*p == ' ' || *p == '\t')
        p++;
    if (*p != ':')
        return fallback;
    p++;
    while (*p == ' ' || *p == '\t')
        p++;
    errno = 0;
    v = strtol(p, &end, 10);
    if (errno || end == p || v < 0 || v > INT_MAX)
        return fallback;
    return (int)v;
}

static int send_all(int fd, const char *buf, size_t len, char *err, size_t errsz, const char *what)
{
    size_t off = 0;

    while (off < len) {
        ssize_t n = send(fd, buf + off, len - off, 0);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            snprintf(err, errsz, "%s failed: %s", what, strerror(errno));
            return -1;
        }
        if (n == 0) {
            snprintf(err, errsz, "%s failed: short write", what);
            return -1;
        }
        off += (size_t)n;
    }
    return 0;
}

static int recv_until_close(int fd, char *buf, size_t bufsz, char *err, size_t errsz, const char *what)
{
    size_t used = 0;

    if (!bufsz)
        return -1;
    while (used + 1 < bufsz) {
        ssize_t n = recv(fd, buf + used, bufsz - used - 1, 0);
        if (n < 0) {
            if (errno == EINTR)
                continue;
            snprintf(err, errsz, "%s failed: %s", what, strerror(errno));
            return -1;
        }
        if (n == 0)
            break;
        used += (size_t)n;
    }
    buf[used] = '\0';
    if (used + 1 == bufsz) {
        snprintf(err, errsz, "%s too large", what);
        return -1;
    }
    return (int)used;
}

static int connect_operator_once(const char *host, const char *port, struct poll_run_result *run,
                                 char *err, size_t errsz)
{
    struct addrinfo hints, *res = NULL, *rp;
    int rc, fd = -1;
    char request[512];
    char response[8192];

    if (errsz)
        err[0] = '\0';
    if (strcmp(BB_COMMAND_QUEUE_TLS, "no")) {
        snprintf(err, errsz, "live command queue polling requires BB_COMMAND_QUEUE_TLS=no in this build");
        return -1;
    }
    memset(&hints, 0, sizeof(hints));
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_family = AF_UNSPEC;
    rc = getaddrinfo(host, port, &hints, &res);
    if (rc != 0) {
        snprintf(err, errsz, "resolve failed: %s", gai_strerror(rc));
        return -1;
    }
    for (rp = res; rp; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd < 0)
            continue;
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) == 0) {
            snprintf(request, sizeof(request),
                     "GET /command-queue/poll HTTP/1.1\r\n"
                     "Host: %s:%s\r\n"
                     "User-Agent: busierbox-command-queue\r\n"
                     "X-BusierBox-Command-Queue-Mode: poll\r\n"
                     "X-BusierBox-Command-Queue-Token: %s\r\n"
                     "Connection: close\r\n\r\n",
                     host, port, BB_COMMAND_QUEUE_TOKEN);
            if (send_all(fd, request, strlen(request), err, errsz, "poll request") != 0) {
                close(fd);
                freeaddrinfo(res);
                return -1;
            }
            if (recv_until_close(fd, response, sizeof(response), err, errsz, "poll response") < 0) {
                close(fd);
                freeaddrinfo(res);
                return -1;
            }
            close(fd);
            freeaddrinfo(res);
            if (!strncmp(response, "HTTP/1.1 204", 12) || !strncmp(response, "HTTP/1.0 204", 12)) {
                snprintf(err, errsz, "no queued command");
                return 1;
            }
            if (!strncmp(response, "HTTP/1.1 200", 12) || !strncmp(response, "HTTP/1.0 200", 12)) {
                const char *body = http_body(response);
                parse_header_value(response, "X-BusierBox-Command-Id", err, errsz);
                if (run) {
                    json_get_string_field(body, "command", run->last_command, sizeof(run->last_command));
                    run->last_timeout_sec = json_get_int_field(body, "timeout_sec", 0);
                    run->last_max_output_bytes = json_get_int_field(body, "max_output_bytes", 0);
                }
                return 0;
            }
            snprintf(err, errsz, "unexpected poll response");
            return -1;
        }
        snprintf(err, errsz, "connect failed: %s", strerror(errno));
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (errsz && !err[0])
        snprintf(err, errsz, "connect failed");
    return -1;
}

static int post_rejected_result_once(const char *host, const char *port,
                                     const char *command_id, char *err, size_t errsz)
{
    struct addrinfo hints, *res = NULL, *rp;
    int rc, fd = -1;
    char body[512];
    char request[1024];
    char response[1024];

    if (errsz)
        err[0] = '\0';
    if (!command_id || !command_id[0]) {
        snprintf(err, errsz, "missing command id for result upload");
        return -1;
    }
    if (strcmp(BB_COMMAND_QUEUE_TLS, "no")) {
        snprintf(err, errsz, "live command queue result upload requires BB_COMMAND_QUEUE_TLS=no in this build");
        return -1;
    }
    snprintf(body, sizeof(body),
             "{\"schema\":1,\"command_id\":\"%s\",\"status\":\"rejected\","
             "\"exit_code\":null,\"stdout_bytes\":0,\"stderr_bytes\":0,"
             "\"execution_mode\":\"%s\",\"execution_supported\":false,\"executes_commands\":false,"
             "\"reason\":\"%s\"}\n",
             command_id, BB_COMMAND_QUEUE_EXECUTION, execution_rejection_reason());
    memset(&hints, 0, sizeof(hints));
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_family = AF_UNSPEC;
    rc = getaddrinfo(host, port, &hints, &res);
    if (rc != 0) {
        snprintf(err, errsz, "resolve failed: %s", gai_strerror(rc));
        return -1;
    }
    for (rp = res; rp; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd < 0)
            continue;
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) == 0) {
            snprintf(request, sizeof(request),
                     "POST /command-queue/result HTTP/1.1\r\n"
                     "Host: %s:%s\r\n"
                     "User-Agent: busierbox-command-queue\r\n"
                     "X-BusierBox-Command-Queue-Token: %s\r\n"
                     "Content-Type: application/json\r\n"
                     "Content-Length: %lu\r\n"
                     "Connection: close\r\n\r\n%s",
                     host, port, BB_COMMAND_QUEUE_TOKEN, (unsigned long)strlen(body), body);
            if (send_all(fd, request, strlen(request), err, errsz, "result upload") != 0) {
                close(fd);
                freeaddrinfo(res);
                return -1;
            }
            if (recv_until_close(fd, response, sizeof(response), err, errsz, "result upload response") < 0) {
                close(fd);
                freeaddrinfo(res);
                return -1;
            }
            close(fd);
            freeaddrinfo(res);
            if (!strncmp(response, "HTTP/1.1 200", 12) || !strncmp(response, "HTTP/1.0 200", 12))
                return 0;
            snprintf(err, errsz, "unexpected result upload response");
            return -1;
        }
        snprintf(err, errsz, "connect failed: %s", strerror(errno));
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (errsz && !err[0])
        snprintf(err, errsz, "connect failed");
    return -1;
}

static struct poll_run_result run_live_poll(const char *mode, const char *operator_host,
                                            int interval_sec, int jitter_pct,
                                            const char *backoff,
                                            int backoff_max_interval_sec, int max_polls,
                                            const char *event_log, const char *state_file)
{
    struct poll_run_result result;
    char endpoint[512];
    char state_error[160] = "";
    int limit = (!strcmp(mode, "daemon")) ? max_polls : 1;

    memset(&result, 0, sizeof(result));
    snprintf(result.last_status, sizeof(result.last_status), "not_run");
    if (!operator_host || !operator_host[0]) {
        snprintf(result.last_status, sizeof(result.last_status), "missing_operator_host");
        return result;
    }
    snprintf(endpoint, sizeof(endpoint), "%s:%s", operator_host, BB_COMMAND_QUEUE_PORT);
    if (limit <= 0 && strcmp(mode, "daemon"))
        limit = 1;
    signal(SIGINT, handle_stop);
    signal(SIGTERM, handle_stop);
    if (!strcmp(mode, "daemon") &&
        write_daemon_state(state_file, mode, endpoint, interval_sec, jitter_pct, backoff,
                           backoff_max_interval_sec, max_polls, event_log,
                           state_error, sizeof(state_error)) != 0) {
        snprintf(result.last_status, sizeof(result.last_status), "state_error");
        snprintf(result.last_error, sizeof(result.last_error), "%s", state_error);
        append_run_poll_event(event_log, &result, "command_queue_daemon_state_error", mode, endpoint, 0, "error", state_error);
        return result;
    }
    while (!stop_daemon && (limit <= 0 || result.attempts < limit)) {
        char error[160] = "";
        result.attempted = 1;
        result.attempts++;
        append_run_poll_event(event_log, &result, "command_queue_poll_attempt", mode, endpoint, result.attempts, "attempt", "");
        int poll_rc = connect_operator_once(operator_host, BB_COMMAND_QUEUE_PORT, &result, error, sizeof(error));
        if (poll_rc == 0) {
            char upload_error[160] = "";
            result.successes++;
            result.delivered_commands++;
            result.rejected_commands++;
            snprintf(result.last_status, sizeof(result.last_status), "delivered-rejected");
            snprintf(result.last_command_id, sizeof(result.last_command_id), "%s", error);
            result.last_error[0] = '\0';
            append_run_poll_command_event(event_log, &result, "command_queue_poll_complete", mode, endpoint, result.attempts, "delivered", "");
            append_run_poll_command_event(event_log, &result, "command_queue_execution_decision", mode, endpoint, result.attempts, "rejected", execution_rejection_reason());
            if (post_rejected_result_once(operator_host, BB_COMMAND_QUEUE_PORT,
                                          result.last_command_id, upload_error, sizeof(upload_error)) == 0) {
                result.result_uploads++;
                append_run_poll_command_event(event_log, &result, "command_queue_result_upload", mode, endpoint, result.attempts, "result-uploaded", "");
            } else {
                result.result_upload_failures++;
                snprintf(result.last_error, sizeof(result.last_error), "%s", upload_error);
                append_run_poll_command_event(event_log, &result, "command_queue_result_upload_error", mode, endpoint, result.attempts, "error", upload_error);
            }
        } else if (poll_rc == 1) {
            result.successes++;
            snprintf(result.last_status, sizeof(result.last_status), "no-command");
            result.last_error[0] = '\0';
            append_run_poll_event(event_log, &result, "command_queue_poll_no_command", mode, endpoint, result.attempts, "no-command", "");
        } else {
            result.failures++;
            snprintf(result.last_status, sizeof(result.last_status), "error");
            snprintf(result.last_error, sizeof(result.last_error), "%s", error);
            append_run_poll_event(event_log, &result, "command_queue_poll_error", mode, endpoint, result.attempts, "error", error);
        }
        if (strcmp(mode, "daemon"))
            break;
        if (limit > 0 && result.attempts >= limit)
            break;
        result.last_delay_sec = poll_delay_for_attempt(result.attempts - 1, interval_sec, backoff,
                                                       backoff_max_interval_sec, jitter_pct);
        if (result.last_delay_sec > 0)
            sleep((unsigned int)result.last_delay_sec);
    }
    result.stopped_by_signal = stop_daemon ? 1 : 0;
    result.stopped_by_limit = (!result.stopped_by_signal && !strcmp(mode, "daemon") && limit > 0 && result.attempts >= limit);
    append_run_poll_event(event_log, &result, "command_queue_poll_shutdown", mode, endpoint, result.attempts,
                          result.stopped_by_signal ? "signal" : "complete", "");
    if (!strcmp(mode, "daemon"))
        remove_daemon_state_if_ours(state_file);
    return result;
}

static void stop_daemon_from_state(const char *state_file, const char *event_log,
                                   struct stop_result *stop, struct daemon_state *state)
{
    int i;

    memset(stop, 0, sizeof(*stop));
    snprintf(stop->status, sizeof(stop->status), "missing");
    read_daemon_state(state_file, state);
    if (!state->present) {
        stop->missing = 1;
        append_poll_event(event_log, "command_queue_daemon_stop", "stop", state_file, 0, "missing", "",
                          NULL, NULL, 0, 0);
        return;
    }
    if (!state->valid) {
        stop->skipped = 1;
        snprintf(stop->status, sizeof(stop->status), "invalid_state");
        snprintf(stop->error, sizeof(stop->error), "%s", state->error);
        append_poll_event(event_log, "command_queue_daemon_stop", "stop", state_file, 0, "invalid_state", state->error,
                          NULL, NULL, 0, 0);
        return;
    }
    if (!state->running) {
        stop->stale = 1;
        snprintf(stop->status, sizeof(stop->status), "stale");
        unlink(state_file);
        append_poll_event(event_log, "command_queue_daemon_stop", "stop", state_file, 0, "stale", "",
                          NULL, NULL, 0, 0);
        return;
    }
    if (!state->ownership_verified) {
        stop->skipped = 1;
        snprintf(stop->status, sizeof(stop->status), "ownership_unverified");
        snprintf(stop->error, sizeof(stop->error), "refusing to signal unverified pid");
        append_poll_event(event_log, "command_queue_daemon_stop", "stop", state_file, 0,
                          "ownership_unverified", stop->error, NULL, NULL, 0, 0);
        return;
    }
    stop->attempted = 1;
    if (kill((pid_t)state->pid, SIGTERM) != 0) {
        snprintf(stop->status, sizeof(stop->status), "signal_failed");
        snprintf(stop->error, sizeof(stop->error), "%s", strerror(errno));
        append_poll_event(event_log, "command_queue_daemon_stop", "stop", state_file, 0,
                          "signal_failed", stop->error, NULL, NULL, 0, 0);
        return;
    }
    stop->signaled = 1;
    snprintf(stop->status, sizeof(stop->status), "signaled");
    for (i = 0; i < 20; i++) {
        struct timespec ts;

        if (kill((pid_t)state->pid, 0) != 0 && errno == ESRCH) {
            stop->stopped = 1;
            snprintf(stop->status, sizeof(stop->status), "stopped");
            unlink(state_file);
            break;
        }
        ts.tv_sec = 0;
        ts.tv_nsec = 100000000L;
        nanosleep(&ts, NULL);
    }
    append_poll_event(event_log, "command_queue_daemon_stop", "stop", state_file, 0, stop->status, stop->error,
                      NULL, NULL, 0, 0);
}

static void print_mode_record_json(const char *name, int selected, int dry_run, int live_would_poll)
{
    int polls_operator = strcmp(name, "status") != 0 && strcmp(name, "stop") != 0;
    int live_selected = !dry_run && selected && polls_operator && live_would_poll;
    int live_available = !dry_run && polls_operator && live_would_poll;

    fputs("{\"mode\":", stdout);
    bb_json_string(stdout, name);
    printf(",\"selected\":%s", selected ? "true" : "false");
    printf(",\"requires_operator_host\":%s", mode_requires_operator_host(name) ? "true" : "false");
    printf(",\"would_poll_if_configured\":%s", polls_operator ? "true" : "false");
    printf(",\"dry_run_only\":%s", dry_run ? "true" : "false");
    fputs(",\"requires_explicit_target_action\":true", stdout);
    printf(",\"would_contact_operator\":%s", live_available ? "true" : "false");
    printf(",\"delivery_supported\":%s", live_available ? "true" : "false");
    printf(",\"result_upload_supported\":%s", live_available ? "true" : "false");
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    printf(",\"active_control_channel\":%s", live_selected ? "true" : "false");
    fputs(",\"operator_supplied_command_execution\":false", stdout);
    fputs(",\"lifecycle\":", stdout);
    bb_json_string(stdout, mode_lifecycle(name));
    fputc('}', stdout);
}

static void print_mode_semantics_json(const char *name, int selected, int dry_run, int live_would_poll)
{
    fputc('"', stdout);
    fputs(name, stdout);
    fputs("\":", stdout);
    print_mode_record_json(name, selected, dry_run, live_would_poll);
}

static void print_all_mode_semantics_json(const char *mode, int dry_run, int live_would_poll)
{
    fputs(",\"mode_semantics\":{", stdout);
    print_mode_semantics_json("status", !strcmp(mode, "status"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_semantics_json("poll", !strcmp(mode, "poll"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_semantics_json("once", !strcmp(mode, "once"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_semantics_json("daemon", !strcmp(mode, "daemon"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_semantics_json("stop", !strcmp(mode, "stop"), dry_run, live_would_poll);
    fputc('}', stdout);
}

static void print_mode_records_json(const char *mode, int dry_run, int live_would_poll)
{
    fputs(",\"mode_records\":[", stdout);
    print_mode_record_json("status", !strcmp(mode, "status"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_record_json("poll", !strcmp(mode, "poll"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_record_json("once", !strcmp(mode, "once"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_record_json("daemon", !strcmp(mode, "daemon"), dry_run, live_would_poll);
    fputc(',', stdout);
    print_mode_record_json("stop", !strcmp(mode, "stop"), dry_run, live_would_poll);
    fputc(']', stdout);
}

static void print_mode_index_array(const char *field, const char *value, const char *mode, int dry_run, int live_would_poll)
{
    static const char *names[] = {"status", "poll", "once", "daemon", "stop"};
    size_t i;
    int first = 1;

    fputc('[', stdout);
    for (i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        const char *name = names[i];
        int selected = !strcmp(mode, name);
        int polls_operator = strcmp(name, "status") != 0 && strcmp(name, "stop") != 0;
        int live_selected = !dry_run && selected && polls_operator && live_would_poll;
        int live_available = !dry_run && polls_operator && live_would_poll;
        const char *candidate = "";
        if (!strcmp(field, "mode"))
            candidate = name;
        else if (!strcmp(field, "lifecycle"))
            candidate = mode_lifecycle(name);
        else if (!strcmp(field, "would_poll_if_configured"))
            candidate = polls_operator ? "true" : "false";
        else if (!strcmp(field, "live_supported"))
            candidate = live_available ? "true" : "false";
        else if (!strcmp(field, "execution_supported"))
            candidate = "false";
        else if (!strcmp(field, "active_control_channel"))
            candidate = live_selected ? "true" : "false";
        else if (!strcmp(field, "operator_supplied_command_execution"))
            candidate = "false";
        if (strcmp(candidate, value))
            continue;
        printf("%s%zu", first ? "" : ",", i);
        first = 0;
    }
    fputc(']', stdout);
}

static void print_mode_indexes_json(const char *mode, int dry_run, int live_would_poll)
{
    static const char *names[] = {"status", "poll", "once", "daemon", "stop"};
    static const char *lifecycles[] = {"inspect", "single-poll", "single-cycle", "long-running", "stop"};
    static const char *bools[] = {"true", "false"};
    size_t i;

    fputs(",\"mode_records_by_mode\":{", stdout);
    for (i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, names[i]);
        fputc(':', stdout);
        print_mode_index_array("mode", names[i], mode, dry_run, live_would_poll);
    }
    fputs("},\"mode_records_by_lifecycle\":{", stdout);
    for (i = 0; i < sizeof(lifecycles) / sizeof(lifecycles[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, lifecycles[i]);
        fputc(':', stdout);
        print_mode_index_array("lifecycle", lifecycles[i], mode, dry_run, live_would_poll);
    }
    fputs("},\"mode_records_by_would_poll_if_configured\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        print_mode_index_array("would_poll_if_configured", bools[i], mode, dry_run, live_would_poll);
    }
    fputs("},\"mode_records_by_live_supported\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        print_mode_index_array("live_supported", bools[i], mode, dry_run, live_would_poll);
    }
    fputs("},\"mode_records_by_execution_supported\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        print_mode_index_array("execution_supported", bools[i], mode, dry_run, live_would_poll);
    }
    fputs("},\"mode_records_by_active_control_channel\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        print_mode_index_array("active_control_channel", bools[i], mode, dry_run, live_would_poll);
    }
    fputs("},\"mode_records_by_operator_supplied_command_execution\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        print_mode_index_array("operator_supplied_command_execution", bools[i], mode, dry_run, live_would_poll);
    }
    fputc('}', stdout);
}

static void print_mode_summary_json(const char *mode, int dry_run, int live_would_poll)
{
    int selected_polling_mode = strcmp(mode, "status") != 0 && strcmp(mode, "stop") != 0;
    int live_delivery_modes = (!dry_run && live_would_poll) ? 3 : 0;
    int active_control_modes = (!dry_run && live_would_poll && selected_polling_mode) ? 1 : 0;

    fputs(",\"mode_summary\":{", stdout);
    fputs("\"mode_count\":5", stdout);
    fputs(",\"polling_mode_count\":3", stdout);
    fputs(",\"operator_host_required_mode_count\":3", stdout);
    printf(",\"delivery_supported_mode_count\":%d", live_delivery_modes);
    printf(",\"result_upload_supported_mode_count\":%d", live_delivery_modes);
    fputs(",\"execution_supported_mode_count\":0", stdout);
    printf(",\"active_control_channel_mode_count\":%d", active_control_modes);
    fputs(",\"operator_supplied_command_execution_mode_count\":0", stdout);
    fputc('}', stdout);
}

static void print_api_collections_json(void)
{
    fputs(",\"api_collections\":{\"mode_records\":{\"name\":\"mode_records\",\"count\":5", stdout);
    fputs(",\"count_summary_key\":\"mode_summary.mode_count\",\"primary_key\":\"mode\",\"summary_key\":\"mode_summary.mode_count\"", stdout);
    fputs(",\"indexes\":[\"mode_records_by_mode\",\"mode_records_by_lifecycle\",\"mode_records_by_would_poll_if_configured\",\"mode_records_by_live_supported\",\"mode_records_by_execution_supported\",\"mode_records_by_active_control_channel\",\"mode_records_by_operator_supplied_command_execution\"]}}", stdout);
}

static void print_poll_run_json(const struct poll_run_result *run)
{
    fputs(",\"poll_run\":{", stdout);
    printf("\"attempted\":%s", run && run->attempted ? "true" : "false");
    printf(",\"attempts\":%d", run ? run->attempts : 0);
    printf(",\"successes\":%d", run ? run->successes : 0);
    printf(",\"failures\":%d", run ? run->failures : 0);
    printf(",\"delivered_commands\":%d", run ? run->delivered_commands : 0);
    printf(",\"rejected_commands\":%d", run ? run->rejected_commands : 0);
    printf(",\"result_uploads\":%d", run ? run->result_uploads : 0);
    printf(",\"result_upload_failures\":%d", run ? run->result_upload_failures : 0);
    printf(",\"last_delay_sec\":%d", run ? run->last_delay_sec : 0);
    printf(",\"stopped_by_limit\":%s", run && run->stopped_by_limit ? "true" : "false");
    printf(",\"stopped_by_signal\":%s", run && run->stopped_by_signal ? "true" : "false");
    fputs(",\"last_status\":", stdout);
    bb_json_string(stdout, run ? run->last_status : "not_run");
    fputs(",\"last_error\":", stdout);
    bb_json_string(stdout, run ? run->last_error : "");
    fputs(",\"last_command_id\":", stdout);
    bb_json_string(stdout, run ? run->last_command_id : "");
    fputs(",\"last_command\":", stdout);
    bb_json_string(stdout, run ? run->last_command : "");
    printf(",\"last_timeout_sec\":%d", run ? run->last_timeout_sec : 0);
    printf(",\"last_max_output_bytes\":%d", run ? run->last_max_output_bytes : 0);
    printf(",\"queued_command_available\":%s", run && run->delivered_commands > 0 ? "true" : "false");
    printf(",\"delivery_supported\":%s", run && run->delivered_commands > 0 ? "true" : "false");
    fputs(",\"result_upload_supported\":true,\"execution_supported\":false,\"executes_commands\":false,\"execution_decision\":\"rejected\"", stdout);
    printf(",\"event_count\":%d", run ? run->event_count : 0);
    printf(",\"event_info_count\":%d", run ? run->event_info_count : 0);
    printf(",\"event_warning_count\":%d", run ? run->event_warning_count : 0);
    fputs(",\"event_counts_by_event\":{", stdout);
    printf("\"command_queue_poll_attempt\":%d", run ? run->event_poll_attempt_count : 0);
    printf(",\"command_queue_poll_complete\":%d", run ? run->event_poll_complete_count : 0);
    printf(",\"command_queue_poll_no_command\":%d", run ? run->event_poll_no_command_count : 0);
    printf(",\"command_queue_poll_error\":%d", run ? run->event_poll_error_count : 0);
    printf(",\"command_queue_execution_decision\":%d", run ? run->event_execution_decision_count : 0);
    printf(",\"command_queue_result_upload\":%d", run ? run->event_result_upload_count : 0);
    printf(",\"command_queue_result_upload_error\":%d", run ? run->event_result_upload_error_count : 0);
    printf(",\"command_queue_poll_shutdown\":%d", run ? run->event_shutdown_count : 0);
    printf(",\"command_queue_daemon_state_error\":%d", run ? run->event_daemon_state_error_count : 0);
    fputs("},\"event_counts_by_level\":{", stdout);
    printf("\"info\":%d,\"warning\":%d", run ? run->event_info_count : 0, run ? run->event_warning_count : 0);
    fputs("}}", stdout);
}

static void print_daemon_state_json(const char *state_file, const struct daemon_state *state)
{
    fputs(",\"daemon_state\":{", stdout);
    fputs("\"state_file\":", stdout);
    bb_json_string(stdout, state_file ? state_file : "");
    printf(",\"present\":%s", state && state->present ? "true" : "false");
    printf(",\"valid\":%s", state && state->valid ? "true" : "false");
    printf(",\"running\":%s", state && state->running ? "true" : "false");
    printf(",\"stale\":%s", state && state->stale ? "true" : "false");
    printf(",\"ownership_verified\":%s", state && state->ownership_verified ? "true" : "false");
    printf(",\"pid\":%d", state ? state->pid : 0);
    fputs(",\"status\":", stdout);
    bb_json_string(stdout, state ? state->status : "missing");
    fputs(",\"error\":", stdout);
    bb_json_string(stdout, state ? state->error : "");
    fputs(",\"started_at\":", stdout);
    bb_json_string(stdout, state ? state->started_at : "");
    fputs(",\"endpoint\":", stdout);
    bb_json_string(stdout, state ? state->endpoint : "");
    fputc('}', stdout);
}

static void print_stop_result_json(const struct stop_result *stop)
{
    fputs(",\"stop_result\":{", stdout);
    printf("\"attempted\":%s", stop && stop->attempted ? "true" : "false");
    printf(",\"signaled\":%s", stop && stop->signaled ? "true" : "false");
    printf(",\"stopped\":%s", stop && stop->stopped ? "true" : "false");
    printf(",\"missing\":%s", stop && stop->missing ? "true" : "false");
    printf(",\"stale\":%s", stop && stop->stale ? "true" : "false");
    printf(",\"skipped\":%s", stop && stop->skipped ? "true" : "false");
    fputs(",\"status\":", stdout);
    bb_json_string(stdout, stop ? stop->status : "not_run");
    fputs(",\"error\":", stdout);
    bb_json_string(stdout, stop ? stop->error : "");
    fputc('}', stdout);
}

static void print_json(const char *mode, int dry_run, const char *operator_host,
                       int interval_sec, int jitter_pct, const char *backoff,
                       int backoff_max_interval_sec, int max_polls, const char *event_log,
                       const char *state_file, const struct daemon_state *daemon_state,
                       const struct stop_result *stop, const struct poll_run_result *run)
{
    int enabled = yes_value(BB_COMMAND_QUEUE_ENABLE);
    int arbitrary_requested;
    int configured_for_polling;
    int would_poll;
    int safe_disabled_default;
    struct command_queue_policy_report policy = bb_command_queue_validate_policy();
    int valid = bb_command_queue_policy_valid(&policy);
    int i;

    arbitrary_requested = valid && enabled && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "custom") && yes_value(BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    configured_for_polling = valid && enabled && operator_host && operator_host[0];
    would_poll = mode_would_poll(mode, enabled, operator_host, &policy);
    safe_disabled_default = !enabled && valid && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "none") && !strcmp(BB_COMMAND_QUEUE_EXECUTION, "metadata-only") && !yes_value(BB_COMMAND_QUEUE_ALLOW_ARBITRARY);

    fputs("{\"schema\":1,\"command\":\"command-queue\",\"mode\":", stdout);
    bb_json_string(stdout, mode);
    printf(",\"enabled\":%s", enabled ? "true" : "false");
    printf(",\"dry_run\":%s", dry_run ? "true" : "false");
    printf(",\"policy_valid\":%s", valid ? "true" : "false");
    fputs(",\"policy_errors\":[", stdout);
    for (i = 0; i < policy.count; i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, policy.errors[i]);
    }
    fputc(']', stdout);
    fputs(",\"policy_summary\":{", stdout);
    printf("\"enabled\":%s", enabled ? "true" : "false");
    fputs(",\"default_enabled\":false", stdout);
    printf(",\"valid\":%s", valid ? "true" : "false");
    printf(",\"error_count\":%d", policy.count);
    printf(",\"configured_for_polling\":%s", configured_for_polling ? "true" : "false");
    printf(",\"would_poll\":%s", would_poll ? "true" : "false");
    printf(",\"operator_queue_records_only\":%s", dry_run ? "false" : "true");
    fputs(",\"execution_mode\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_EXECUTION);
    printf(",\"metadata_only_default\":%s", !strcmp(BB_COMMAND_QUEUE_EXECUTION, "metadata-only") ? "true" : "false");
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    printf(",\"delivery_supported\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"poll_transport_supported\":%s", dry_run ? "false" : "true");
    printf(",\"result_upload_supported\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"active_control_channel\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"arbitrary_policy_requested\":%s", arbitrary_requested ? "true" : "false");
    fputs(",\"arbitrary_execution_allowed\":false", stdout);
    printf(",\"safe_disabled_default\":%s", safe_disabled_default ? "true" : "false");
    fputc('}', stdout);
    printf(",\"configured_for_polling\":%s", configured_for_polling ? "true" : "false");
    printf(",\"missing_operator_host\":%s", (valid && enabled && (!operator_host || !operator_host[0])) ? "true" : "false");
    printf(",\"would_poll\":%s", would_poll ? "true" : "false");
    fputs(",\"operator_host\":", stdout);
    bb_json_string(stdout, operator_host ? operator_host : "");
    fputs(",\"port\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_PORT);
    fputs(",\"tls\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_TLS);
    fputs(",\"endpoint\":", stdout);
    if (operator_host && operator_host[0]) {
        char endpoint[512];
        snprintf(endpoint, sizeof(endpoint), "%s:%s", operator_host, BB_COMMAND_QUEUE_PORT);
        bb_json_string(stdout, endpoint);
    } else {
        bb_json_string(stdout, "");
    }
    fputs(",\"require_token\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_REQUIRE_TOKEN);
    fputs(",\"token_source\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_TOKEN_SOURCE);
    printf(",\"token_required\":%s", !strcmp(BB_COMMAND_QUEUE_REQUIRE_TOKEN, "yes") ? "true" : "false");
    printf(",\"token_configured\":%s", BB_COMMAND_QUEUE_TOKEN[0] ? "true" : "false");
    fputs(",\"allowed_commands\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    fputs(",\"allow_arbitrary\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    fputs(",\"execution_mode\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_EXECUTION);
    printf(",\"metadata_only_default\":%s", !strcmp(BB_COMMAND_QUEUE_EXECUTION, "metadata-only") ? "true" : "false");
    printf(",\"arbitrary_policy_requested\":%s", arbitrary_requested ? "true" : "false");
    fputs(",\"arbitrary_execution_allowed\":false", stdout);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    printf(",\"delivery_supported\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"result_upload_supported\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"poll_transport_supported\":%s", dry_run ? "false" : "true");
    printf(",\"active_control_channel\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"poll_interval_sec\":%d", interval_sec);
    printf(",\"poll_jitter_pct\":%d", jitter_pct);
    fputs(",\"poll_backoff\":", stdout);
    bb_json_string(stdout, backoff ? backoff : "");
    printf(",\"poll_max_interval_sec\":%d", backoff_max_interval_sec);
    printf(",\"max_polls\":%d", max_polls);
    fputs(",\"event_log\":", stdout);
    bb_json_string(stdout, event_log ? event_log : "");
    fputs(",\"state_file\":", stdout);
    bb_json_string(stdout, state_file ? state_file : "");
    fputs(",\"status\":", stdout);
    bb_json_string(stdout, mode_status(mode, enabled, operator_host, &policy, dry_run));
    fputs(",\"poll_plan\":{", stdout);
    fputs("\"mode\":", stdout); bb_json_string(stdout, mode);
    fputs(",\"status\":", stdout); bb_json_string(stdout, mode_status(mode, enabled, operator_host, &policy, dry_run));
    printf(",\"enabled\":%s", enabled ? "true" : "false");
    printf(",\"policy_valid\":%s", valid ? "true" : "false");
    printf(",\"configured_for_polling\":%s", configured_for_polling ? "true" : "false");
    printf(",\"missing_operator_host\":%s", (valid && enabled && (!operator_host || !operator_host[0])) ? "true" : "false");
    printf(",\"would_poll\":%s", would_poll ? "true" : "false");
    printf(",\"dry_run_only\":%s", dry_run ? "true" : "false");
    fputs(",\"requires_explicit_target_action\":true", stdout);
    printf(",\"would_contact_operator\":%s", (!dry_run && would_poll) ? "true" : "false");
    fputs(",\"operator_host\":", stdout); bb_json_string(stdout, operator_host ? operator_host : "");
    fputs(",\"endpoint\":", stdout);
    if (operator_host && operator_host[0]) {
        char endpoint[512];
        snprintf(endpoint, sizeof(endpoint), "%s:%s", operator_host, BB_COMMAND_QUEUE_PORT);
        bb_json_string(stdout, endpoint);
    } else {
        bb_json_string(stdout, "");
    }
    printf(",\"delivery_supported\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"result_upload_supported\":%s", (!dry_run && would_poll) ? "true" : "false");
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    printf(",\"active_control_channel\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"queued_command_available\":%s", run && run->delivered_commands > 0 ? "true" : "false");
    fputs(",\"operator_supplied_command_execution\":false", stdout);
    fputc('}', stdout);
    print_all_mode_semantics_json(mode, dry_run, would_poll);
    print_mode_records_json(mode, dry_run, would_poll);
    print_mode_indexes_json(mode, dry_run, would_poll);
    print_mode_summary_json(mode, dry_run, would_poll);
    print_api_collections_json();
    print_poll_run_json(run);
    print_daemon_state_json(state_file, daemon_state);
    print_stop_result_json(stop);
    fputs(",\"safety_boundary\":\"target polling is explicit; live mode can receive queued command metadata but command execution is not implemented\"", stdout);
    fputs(",\"queued_command\":", stdout);
    if (run && run->delivered_commands > 0) {
        fputs("{\"id\":", stdout);
        bb_json_string(stdout, run->last_command_id);
        fputs(",\"command\":", stdout);
        bb_json_string(stdout, run->last_command);
        printf(",\"timeout_sec\":%d,\"max_output_bytes\":%d", run->last_timeout_sec, run->last_max_output_bytes);
        fputs(",\"execution_mode\":", stdout);
        bb_json_string(stdout, BB_COMMAND_QUEUE_EXECUTION);
        fputs(",\"execution_supported\":false,\"executes_commands\":false,\"execution_decision\":\"rejected\",\"execution_decision_reason\":", stdout);
        bb_json_string(stdout, execution_rejection_reason());
        fputc('}', stdout);
    } else {
        fputs("null", stdout);
    }
    fputs("}\n", stdout);
}

static void print_text(const char *mode, int dry_run, const char *operator_host,
                       int interval_sec, int jitter_pct, const char *backoff,
                       int backoff_max_interval_sec, int max_polls, const char *event_log,
                       const char *state_file, const struct daemon_state *daemon_state,
                       const struct stop_result *stop, const struct poll_run_result *run)
{
    int enabled = yes_value(BB_COMMAND_QUEUE_ENABLE);
    int arbitrary_requested;
    struct command_queue_policy_report policy = bb_command_queue_validate_policy();
    int valid = bb_command_queue_policy_valid(&policy);
    int i;

    arbitrary_requested = valid && enabled && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "custom") && yes_value(BB_COMMAND_QUEUE_ALLOW_ARBITRARY);

    printf("command_queue_mode=%s\n", mode);
    printf("command_queue_enable=%s\n", BB_COMMAND_QUEUE_ENABLE);
    printf("command_queue_dry_run=%s\n", dry_run ? "yes" : "no");
    printf("command_queue_policy_valid=%s\n", valid ? "yes" : "no");
    for (i = 0; i < policy.count; i++)
        printf("command_queue_policy_error=%s\n", policy.errors[i]);
    printf("command_queue_configured_for_polling=%s\n", (valid && enabled && operator_host && operator_host[0]) ? "yes" : "no");
    printf("command_queue_missing_operator_host=%s\n", (valid && enabled && (!operator_host || !operator_host[0])) ? "yes" : "no");
    printf("command_queue_would_poll=%s\n", mode_would_poll(mode, enabled, operator_host, &policy) ? "yes" : "no");
    printf("command_queue_operator_host=%s\n", operator_host ? operator_host : "");
    printf("command_queue_port=%s\n", BB_COMMAND_QUEUE_PORT);
    if (operator_host && operator_host[0])
        printf("command_queue_endpoint=%s:%s\n", operator_host, BB_COMMAND_QUEUE_PORT);
    else
        puts("command_queue_endpoint=");
    printf("command_queue_tls=%s\n", BB_COMMAND_QUEUE_TLS);
    printf("command_queue_require_token=%s\n", BB_COMMAND_QUEUE_REQUIRE_TOKEN);
    printf("command_queue_token_source=%s\n", BB_COMMAND_QUEUE_TOKEN_SOURCE);
    printf("command_queue_token_configured=%s\n", BB_COMMAND_QUEUE_TOKEN[0] ? "yes" : "no");
    printf("command_queue_allowed_commands=%s\n", BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    printf("command_queue_allow_arbitrary=%s\n", BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    printf("command_queue_execution_mode=%s\n", BB_COMMAND_QUEUE_EXECUTION);
    printf("command_queue_metadata_only_default=%s\n", !strcmp(BB_COMMAND_QUEUE_EXECUTION, "metadata-only") ? "yes" : "no");
    printf("command_queue_arbitrary_policy_requested=%s\n", arbitrary_requested ? "yes" : "no");
    puts("command_queue_arbitrary_execution_allowed=no");
    puts("command_queue_execution_supported=no");
    puts("command_queue_executes_commands=no");
    printf("command_queue_delivery_supported=%s\n", (!dry_run && mode_would_poll(mode, enabled, operator_host, &policy)) ? "yes" : "no");
    printf("command_queue_result_upload_supported=%s\n", (!dry_run && mode_would_poll(mode, enabled, operator_host, &policy)) ? "yes" : "no");
    printf("command_queue_poll_transport_supported=%s\n", dry_run ? "no" : "yes");
    printf("command_queue_active_control_channel=%s\n", (!dry_run && mode_would_poll(mode, enabled, operator_host, &policy)) ? "yes" : "no");
    printf("command_queue_poll_interval_sec=%d\n", interval_sec);
    printf("command_queue_poll_jitter_pct=%d\n", jitter_pct);
    printf("command_queue_poll_backoff=%s\n", backoff ? backoff : "");
    printf("command_queue_poll_max_interval_sec=%d\n", backoff_max_interval_sec);
    printf("command_queue_max_polls=%d\n", max_polls);
    printf("command_queue_event_log=%s\n", event_log ? event_log : "");
    printf("command_queue_state_file=%s\n", state_file ? state_file : "");
    printf("command_queue_status=%s\n", mode_status(mode, enabled, operator_host, &policy, dry_run));
    printf("command_queue_poll_plan_dry_run_only=%s\n", dry_run ? "yes" : "no");
    puts("command_queue_poll_plan_requires_explicit_target_action=yes");
    printf("command_queue_poll_plan_would_contact_operator=%s\n", (!dry_run && mode_would_poll(mode, enabled, operator_host, &policy)) ? "yes" : "no");
    puts("command_queue_poll_plan_queued_command_available=no");
    puts("command_queue_poll_plan_operator_supplied_command_execution=no");
    puts("command_queue_mode_status_lifecycle=inspect");
    puts("command_queue_mode_status_would_poll_if_configured=no");
    puts("command_queue_mode_poll_lifecycle=single-poll");
    puts("command_queue_mode_poll_would_poll_if_configured=yes");
    puts("command_queue_mode_once_lifecycle=single-cycle");
    puts("command_queue_mode_once_would_poll_if_configured=yes");
    puts("command_queue_mode_daemon_lifecycle=long-running");
    puts("command_queue_mode_daemon_would_poll_if_configured=yes");
    puts("command_queue_mode_stop_lifecycle=stop");
    puts("command_queue_mode_stop_would_poll_if_configured=no");
    puts("command_queue_modes_execute_commands=no");
    printf("command_queue_modes_active_control_channel=%s\n",
           (!dry_run && mode_would_poll(mode, enabled, operator_host, &policy)) ? "yes" : "no");
    printf("command_queue_poll_run_attempted=%s\n", run && run->attempted ? "yes" : "no");
    printf("command_queue_poll_run_attempts=%d\n", run ? run->attempts : 0);
    printf("command_queue_poll_run_successes=%d\n", run ? run->successes : 0);
    printf("command_queue_poll_run_failures=%d\n", run ? run->failures : 0);
    printf("command_queue_poll_run_delivered_commands=%d\n", run ? run->delivered_commands : 0);
    printf("command_queue_poll_run_rejected_commands=%d\n", run ? run->rejected_commands : 0);
    printf("command_queue_poll_run_result_uploads=%d\n", run ? run->result_uploads : 0);
    printf("command_queue_poll_run_result_upload_failures=%d\n", run ? run->result_upload_failures : 0);
    printf("command_queue_poll_run_last_delay_sec=%d\n", run ? run->last_delay_sec : 0);
    printf("command_queue_poll_run_stopped_by_limit=%s\n", run && run->stopped_by_limit ? "yes" : "no");
    printf("command_queue_poll_run_stopped_by_signal=%s\n", run && run->stopped_by_signal ? "yes" : "no");
    printf("command_queue_poll_run_last_status=%s\n", run ? run->last_status : "not_run");
    printf("command_queue_poll_run_last_error=%s\n", run ? run->last_error : "");
    printf("command_queue_poll_run_last_command_id=%s\n", run ? run->last_command_id : "");
    printf("command_queue_poll_run_last_command=%s\n", run ? run->last_command : "");
    printf("command_queue_poll_run_last_timeout_sec=%d\n", run ? run->last_timeout_sec : 0);
    printf("command_queue_poll_run_last_max_output_bytes=%d\n", run ? run->last_max_output_bytes : 0);
    printf("command_queue_daemon_state_present=%s\n", daemon_state && daemon_state->present ? "yes" : "no");
    printf("command_queue_daemon_state_valid=%s\n", daemon_state && daemon_state->valid ? "yes" : "no");
    printf("command_queue_daemon_running=%s\n", daemon_state && daemon_state->running ? "yes" : "no");
    printf("command_queue_daemon_stale=%s\n", daemon_state && daemon_state->stale ? "yes" : "no");
    printf("command_queue_daemon_ownership_verified=%s\n", daemon_state && daemon_state->ownership_verified ? "yes" : "no");
    printf("command_queue_daemon_pid=%d\n", daemon_state ? daemon_state->pid : 0);
    printf("command_queue_daemon_status=%s\n", daemon_state ? daemon_state->status : "missing");
    printf("command_queue_daemon_error=%s\n", daemon_state ? daemon_state->error : "");
    printf("command_queue_stop_attempted=%s\n", stop && stop->attempted ? "yes" : "no");
    printf("command_queue_stop_signaled=%s\n", stop && stop->signaled ? "yes" : "no");
    printf("command_queue_stop_stopped=%s\n", stop && stop->stopped ? "yes" : "no");
    printf("command_queue_stop_missing=%s\n", stop && stop->missing ? "yes" : "no");
    printf("command_queue_stop_stale=%s\n", stop && stop->stale ? "yes" : "no");
    printf("command_queue_stop_skipped=%s\n", stop && stop->skipped ? "yes" : "no");
    printf("command_queue_stop_status=%s\n", stop ? stop->status : "not_run");
    printf("command_queue_stop_error=%s\n", stop ? stop->error : "");
    puts("command_queue_safety_boundary=explicit target polling; live mode can receive queued command metadata but execution is not implemented");
}

int applet_command_queue_main(int argc, char **argv)
{
    const char *mode = "status";
    const char *operator_host = BB_OPERATOR_SERVER_HOST;
    const char *event_log = "";
    char default_state[PATH_MAX];
    const char *state_file;
    const char *backoff = BB_COMMAND_QUEUE_POLL_BACKOFF;
    struct poll_run_result run;
    struct daemon_state daemon_state;
    struct stop_result stop;
    int json = 0, dry_run = 1;
    int interval_sec = parse_nonnegative_int(BB_COMMAND_QUEUE_POLL_INTERVAL_SEC, 5);
    int jitter_pct = parse_nonnegative_int(BB_COMMAND_QUEUE_POLL_JITTER_PCT, 0);
    int backoff_max_interval_sec = parse_nonnegative_int(BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC, 300);
    int max_polls = parse_nonnegative_int(BB_COMMAND_QUEUE_MAX_POLLS, 0);
    int i;

    memset(&run, 0, sizeof(run));
    memset(&daemon_state, 0, sizeof(daemon_state));
    memset(&stop, 0, sizeof(stop));
    snprintf(run.last_status, sizeof(run.last_status), "not_run");
    snprintf(stop.status, sizeof(stop.status), "not_run");
    default_state_path(default_state, sizeof(default_state));
    state_file = default_state;
    if (is_help(argc, argv)) {
        print_help();
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json")) {
            json = 1;
        } else if (!strcmp(argv[i], "--dry-run")) {
            dry_run = 1;
        } else if (!strcmp(argv[i], "--live")) {
            dry_run = 0;
        } else if (!strcmp(argv[i], "--operator-host") && i + 1 < argc) {
            operator_host = argv[++i];
        } else if (!strcmp(argv[i], "--poll-interval-sec") && i + 1 < argc) {
            interval_sec = parse_nonnegative_int(argv[++i], interval_sec);
        } else if (!strcmp(argv[i], "--poll-backoff") && i + 1 < argc) {
            backoff = argv[++i];
            if (!valid_backoff_value(backoff)) {
                fprintf(stderr, "command-queue: invalid --poll-backoff %s\n", backoff);
                return 2;
            }
        } else if (!strcmp(argv[i], "--poll-jitter-pct") && i + 1 < argc) {
            jitter_pct = parse_nonnegative_int(argv[++i], jitter_pct);
        } else if (!strcmp(argv[i], "--poll-max-interval-sec") && i + 1 < argc) {
            backoff_max_interval_sec = parse_nonnegative_int(argv[++i], backoff_max_interval_sec);
        } else if (!strcmp(argv[i], "--max-polls") && i + 1 < argc) {
            max_polls = parse_nonnegative_int(argv[++i], max_polls);
        } else if (!strcmp(argv[i], "--event-log") && i + 1 < argc) {
            event_log = argv[++i];
        } else if (!strcmp(argv[i], "--state-file") && i + 1 < argc) {
            state_file = argv[++i];
        } else if (!strcmp(argv[i], "status") || !strcmp(argv[i], "poll") ||
                   !strcmp(argv[i], "once") || !strcmp(argv[i], "daemon") ||
                   !strcmp(argv[i], "stop")) {
            mode = argv[i];
        } else {
            fprintf(stderr, "command-queue: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (!strcmp(mode, "status"))
        dry_run = 1;
    if (!strcmp(mode, "stop")) {
        dry_run = 1;
        stop_daemon_from_state(state_file, event_log, &stop, &daemon_state);
    } else {
        read_daemon_state(state_file, &daemon_state);
    }
    if (!dry_run) {
        struct command_queue_policy_report policy = bb_command_queue_validate_policy();
        if (!bb_command_queue_policy_valid(&policy)) {
            snprintf(run.last_status, sizeof(run.last_status), "invalid_policy");
        } else if (!yes_value(BB_COMMAND_QUEUE_ENABLE)) {
            snprintf(run.last_status, sizeof(run.last_status), "disabled");
        } else if (!operator_host || !operator_host[0]) {
            snprintf(run.last_status, sizeof(run.last_status), "missing_operator_host");
        } else {
            run = run_live_poll(mode, operator_host, interval_sec, jitter_pct, backoff,
                                backoff_max_interval_sec, max_polls, event_log, state_file);
        }
        read_daemon_state(state_file, &daemon_state);
    }
    if (json)
        print_json(mode, dry_run, operator_host, interval_sec, jitter_pct,
                   backoff, backoff_max_interval_sec, max_polls, event_log,
                   state_file, &daemon_state, &stop, &run);
    else
        print_text(mode, dry_run, operator_host, interval_sec, jitter_pct,
                   backoff, backoff_max_interval_sec, max_polls, event_log,
                   state_file, &daemon_state, &stop, &run);
    return 0;
}
