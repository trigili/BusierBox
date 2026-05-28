#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <netdb.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include "effective_config.h"
#include "command_queue_policy.h"
#include "json_helpers.h"

struct poll_run_result {
    int attempted;
    int attempts;
    int successes;
    int failures;
    int stopped_by_limit;
    int stopped_by_signal;
    char last_status[64];
    char last_error[160];
};

static volatile sig_atomic_t stop_daemon;

static int yes_value(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "on"));
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
    puts("usage: busierbox command-queue [status|poll|once|daemon] [--json] [--dry-run|--live] [--operator-host HOST]");
    puts("       busierbox command-queue daemon --live [--max-polls N] [--poll-interval-sec N] [--event-log PATH]");
    puts("Inspect explicit opt-in command queue policy and target polling state.");
    puts("Live mode only contacts the operator endpoint and logs poll attempts; queued command delivery/execution is not implemented.");
}

static int mode_would_poll(const char *mode, int enabled, const char *operator_host, const struct command_queue_policy_report *report)
{
    return bb_command_queue_policy_valid(report) && enabled && operator_host && operator_host[0] && (strcmp(mode, "status") != 0);
}

static const char *mode_status(const char *mode, int enabled, const char *operator_host,
                               const struct command_queue_policy_report *report, int dry_run)
{
    if (!bb_command_queue_policy_valid(report))
        return "invalid_policy";
    if (!enabled)
        return "disabled";
    if (!operator_host || !operator_host[0])
        return "missing_operator_host";
    if (!strcmp(mode, "status"))
        return "configured";
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
    return strcmp(mode, "status") != 0;
}

static const char *mode_lifecycle(const char *mode)
{
    if (!strcmp(mode, "status"))
        return "inspect";
    if (!strcmp(mode, "poll"))
        return "single-poll";
    if (!strcmp(mode, "once"))
        return "single-cycle";
    if (!strcmp(mode, "daemon"))
        return "long-running";
    return "unknown";
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
                              const char *error)
{
    FILE *fh;
    char ts[32];

    if (!path || !path[0])
        return;
    fh = fopen(path, "a");
    if (!fh)
        return;
    utc_timestamp(ts, sizeof(ts));
    fputs("{\"schema\":1,\"ts\":", fh);
    bb_json_string(fh, ts);
    fputs(",\"service\":\"command-queue\",\"event\":", fh);
    bb_json_string(fh, event);
    fputs(",\"level\":", fh);
    bb_json_string(fh, error && error[0] ? "warning" : "info");
    fputs(",\"details\":{\"mode\":", fh);
    bb_json_string(fh, mode);
    fputs(",\"endpoint\":", fh);
    bb_json_string(fh, endpoint ? endpoint : "");
    fprintf(fh, ",\"attempt\":%d,\"executes_commands\":false,\"delivery_supported\":false,\"result_upload_supported\":false", attempt);
    fputs(",\"status\":", fh);
    bb_json_string(fh, status ? status : "");
    if (error && error[0]) {
        fputs(",\"error\":", fh);
        bb_json_string(fh, error);
    }
    fputs("}}\n", fh);
    fclose(fh);
}

static int connect_operator_once(const char *host, const char *port, char *err, size_t errsz)
{
    struct addrinfo hints, *res = NULL, *rp;
    int rc, fd = -1;

    if (errsz)
        err[0] = '\0';
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
            close(fd);
            freeaddrinfo(res);
            return 0;
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
                                            int interval_sec, int max_polls,
                                            const char *event_log)
{
    struct poll_run_result result;
    char endpoint[512];
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
    while (!stop_daemon && (limit <= 0 || result.attempts < limit)) {
        char error[160] = "";
        result.attempted = 1;
        result.attempts++;
        append_poll_event(event_log, "command_queue_poll_attempt", mode, endpoint, result.attempts, "attempt", "");
        if (connect_operator_once(operator_host, BB_COMMAND_QUEUE_PORT, error, sizeof(error)) == 0) {
            result.successes++;
            snprintf(result.last_status, sizeof(result.last_status), "connected");
            result.last_error[0] = '\0';
            append_poll_event(event_log, "command_queue_poll_complete", mode, endpoint, result.attempts, "connected", "");
        } else {
            result.failures++;
            snprintf(result.last_status, sizeof(result.last_status), "error");
            snprintf(result.last_error, sizeof(result.last_error), "%s", error);
            append_poll_event(event_log, "command_queue_poll_error", mode, endpoint, result.attempts, "error", error);
        }
        if (strcmp(mode, "daemon"))
            break;
        if (limit > 0 && result.attempts >= limit)
            break;
        if (interval_sec > 0)
            sleep((unsigned int)interval_sec);
    }
    result.stopped_by_signal = stop_daemon ? 1 : 0;
    result.stopped_by_limit = (!result.stopped_by_signal && !strcmp(mode, "daemon") && limit > 0 && result.attempts >= limit);
    append_poll_event(event_log, "command_queue_poll_shutdown", mode, endpoint, result.attempts,
                      result.stopped_by_signal ? "signal" : "complete", "");
    return result;
}

static void print_mode_semantics_json(const char *name, int selected, int dry_run)
{
    fputc('"', stdout);
    fputs(name, stdout);
    fputs("\":{", stdout);
    printf("\"selected\":%s", selected ? "true" : "false");
    printf(",\"requires_operator_host\":%s", mode_requires_operator_host(name) ? "true" : "false");
    printf(",\"would_poll_if_configured\":%s", strcmp(name, "status") ? "true" : "false");
    printf(",\"dry_run_only\":%s", dry_run ? "true" : "false");
    fputs(",\"requires_explicit_target_action\":true", stdout);
    printf(",\"would_contact_operator\":%s", (!dry_run && strcmp(name, "status")) ? "true" : "false");
    fputs(",\"delivery_supported\":false", stdout);
    fputs(",\"result_upload_supported\":false", stdout);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    printf(",\"active_control_channel\":%s", (!dry_run && selected && strcmp(name, "status")) ? "true" : "false");
    fputs(",\"operator_supplied_command_execution\":false", stdout);
    fputs(",\"lifecycle\":", stdout);
    bb_json_string(stdout, mode_lifecycle(name));
    fputc('}', stdout);
}

static void print_all_mode_semantics_json(const char *mode, int dry_run)
{
    fputs(",\"mode_semantics\":{", stdout);
    print_mode_semantics_json("status", !strcmp(mode, "status"), dry_run);
    fputc(',', stdout);
    print_mode_semantics_json("poll", !strcmp(mode, "poll"), dry_run);
    fputc(',', stdout);
    print_mode_semantics_json("once", !strcmp(mode, "once"), dry_run);
    fputc(',', stdout);
    print_mode_semantics_json("daemon", !strcmp(mode, "daemon"), dry_run);
    fputc('}', stdout);
}

static void print_poll_run_json(const struct poll_run_result *run)
{
    fputs(",\"poll_run\":{", stdout);
    printf("\"attempted\":%s", run && run->attempted ? "true" : "false");
    printf(",\"attempts\":%d", run ? run->attempts : 0);
    printf(",\"successes\":%d", run ? run->successes : 0);
    printf(",\"failures\":%d", run ? run->failures : 0);
    printf(",\"stopped_by_limit\":%s", run && run->stopped_by_limit ? "true" : "false");
    printf(",\"stopped_by_signal\":%s", run && run->stopped_by_signal ? "true" : "false");
    fputs(",\"last_status\":", stdout);
    bb_json_string(stdout, run ? run->last_status : "not_run");
    fputs(",\"last_error\":", stdout);
    bb_json_string(stdout, run ? run->last_error : "");
    fputs(",\"queued_command_available\":false,\"delivery_supported\":false,\"result_upload_supported\":false,\"execution_supported\":false,\"executes_commands\":false}", stdout);
}

static void print_json(const char *mode, int dry_run, const char *operator_host,
                       int interval_sec, int max_polls, const char *event_log,
                       const struct poll_run_result *run)
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
    safe_disabled_default = !enabled && valid && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "none") && !yes_value(BB_COMMAND_QUEUE_ALLOW_ARBITRARY);

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
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    fputs(",\"delivery_supported\":false", stdout);
    printf(",\"poll_transport_supported\":%s", dry_run ? "false" : "true");
    fputs(",\"result_upload_supported\":false", stdout);
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
    fputs(",\"allowed_commands\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    fputs(",\"allow_arbitrary\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    printf(",\"arbitrary_policy_requested\":%s", arbitrary_requested ? "true" : "false");
    fputs(",\"arbitrary_execution_allowed\":false", stdout);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    fputs(",\"delivery_supported\":false", stdout);
    fputs(",\"result_upload_supported\":false", stdout);
    printf(",\"poll_transport_supported\":%s", dry_run ? "false" : "true");
    printf(",\"active_control_channel\":%s", (!dry_run && would_poll) ? "true" : "false");
    printf(",\"poll_interval_sec\":%d", interval_sec);
    printf(",\"max_polls\":%d", max_polls);
    fputs(",\"event_log\":", stdout);
    bb_json_string(stdout, event_log ? event_log : "");
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
    fputs(",\"delivery_supported\":false", stdout);
    fputs(",\"result_upload_supported\":false", stdout);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    printf(",\"active_control_channel\":%s", (!dry_run && would_poll) ? "true" : "false");
    fputs(",\"queued_command_available\":false", stdout);
    fputs(",\"operator_supplied_command_execution\":false", stdout);
    fputc('}', stdout);
    print_all_mode_semantics_json(mode, dry_run);
    print_poll_run_json(run);
    fputs(",\"safety_boundary\":\"target polling is explicit; live mode contacts the operator endpoint but command delivery/execution is not implemented\"", stdout);
    fputs(",\"queued_command\":null}\n", stdout);
}

static void print_text(const char *mode, int dry_run, const char *operator_host,
                       int interval_sec, int max_polls, const char *event_log,
                       const struct poll_run_result *run)
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
    printf("command_queue_allowed_commands=%s\n", BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    printf("command_queue_allow_arbitrary=%s\n", BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    printf("command_queue_arbitrary_policy_requested=%s\n", arbitrary_requested ? "yes" : "no");
    puts("command_queue_arbitrary_execution_allowed=no");
    puts("command_queue_execution_supported=no");
    puts("command_queue_executes_commands=no");
    puts("command_queue_delivery_supported=no");
    puts("command_queue_result_upload_supported=no");
    printf("command_queue_poll_transport_supported=%s\n", dry_run ? "no" : "yes");
    printf("command_queue_active_control_channel=%s\n", (!dry_run && mode_would_poll(mode, enabled, operator_host, &policy)) ? "yes" : "no");
    printf("command_queue_poll_interval_sec=%d\n", interval_sec);
    printf("command_queue_max_polls=%d\n", max_polls);
    printf("command_queue_event_log=%s\n", event_log ? event_log : "");
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
    puts("command_queue_modes_execute_commands=no");
    printf("command_queue_modes_active_control_channel=%s\n", dry_run ? "no" : "yes");
    printf("command_queue_poll_run_attempted=%s\n", run && run->attempted ? "yes" : "no");
    printf("command_queue_poll_run_attempts=%d\n", run ? run->attempts : 0);
    printf("command_queue_poll_run_successes=%d\n", run ? run->successes : 0);
    printf("command_queue_poll_run_failures=%d\n", run ? run->failures : 0);
    printf("command_queue_poll_run_stopped_by_limit=%s\n", run && run->stopped_by_limit ? "yes" : "no");
    printf("command_queue_poll_run_stopped_by_signal=%s\n", run && run->stopped_by_signal ? "yes" : "no");
    printf("command_queue_poll_run_last_status=%s\n", run ? run->last_status : "not_run");
    printf("command_queue_poll_run_last_error=%s\n", run ? run->last_error : "");
    puts("command_queue_safety_boundary=explicit target polling; live mode contacts the operator endpoint but queued command delivery/execution is not implemented");
}

int applet_command_queue_main(int argc, char **argv)
{
    const char *mode = "status";
    const char *operator_host = BB_OPERATOR_SERVER_HOST;
    const char *event_log = "";
    struct poll_run_result run;
    int json = 0, dry_run = 1;
    int interval_sec = parse_nonnegative_int(BB_COMMAND_QUEUE_POLL_INTERVAL_SEC, 5);
    int max_polls = parse_nonnegative_int(BB_COMMAND_QUEUE_MAX_POLLS, 0);
    int i;

    memset(&run, 0, sizeof(run));
    snprintf(run.last_status, sizeof(run.last_status), "not_run");
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
        } else if (!strcmp(argv[i], "--max-polls") && i + 1 < argc) {
            max_polls = parse_nonnegative_int(argv[++i], max_polls);
        } else if (!strcmp(argv[i], "--event-log") && i + 1 < argc) {
            event_log = argv[++i];
        } else if (!strcmp(argv[i], "status") || !strcmp(argv[i], "poll") ||
                   !strcmp(argv[i], "once") || !strcmp(argv[i], "daemon")) {
            mode = argv[i];
        } else {
            fprintf(stderr, "command-queue: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (!strcmp(mode, "status"))
        dry_run = 1;
    if (!dry_run) {
        struct command_queue_policy_report policy = bb_command_queue_validate_policy();
        if (!bb_command_queue_policy_valid(&policy)) {
            snprintf(run.last_status, sizeof(run.last_status), "invalid_policy");
        } else if (!yes_value(BB_COMMAND_QUEUE_ENABLE)) {
            snprintf(run.last_status, sizeof(run.last_status), "disabled");
        } else if (!operator_host || !operator_host[0]) {
            snprintf(run.last_status, sizeof(run.last_status), "missing_operator_host");
        } else {
            run = run_live_poll(mode, operator_host, interval_sec, max_polls, event_log);
        }
    }
    if (json)
        print_json(mode, dry_run, operator_host, interval_sec, max_polls, event_log, &run);
    else
        print_text(mode, dry_run, operator_host, interval_sec, max_polls, event_log, &run);
    return 0;
}
