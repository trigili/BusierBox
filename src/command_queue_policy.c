#define _POSIX_C_SOURCE 200809L

#include <string.h>

#include "command_queue_policy.h"
#include "effective_config.h"

static int exact_value(const char *s, const char *a, const char *b)
{
    return s && (!strcmp(s, a) || !strcmp(s, b));
}

static int valid_port_value(const char *s)
{
    const char *p;

    if (!s || !s[0])
        return 0;
    for (p = s; *p; p++) {
        if (*p < '0' || *p > '9')
            return 0;
    }
    return 1;
}

static int valid_uint_value(const char *s)
{
    return valid_port_value(s);
}

static int valid_policy_value(const char *s)
{
    return s && (!strcmp(s, "none") || !strcmp(s, "busierbox-only") ||
                 !strcmp(s, "allowlist") || !strcmp(s, "custom"));
}

static int valid_execution_value(const char *s)
{
    return s && (!strcmp(s, "metadata-only") || !strcmp(s, "execute"));
}

static int valid_backoff_value(const char *s)
{
    return s && (!strcmp(s, "none") || !strcmp(s, "linear") || !strcmp(s, "exponential"));
}

static int valid_token_value(const char *s)
{
    const char *p;

    if (!s)
        return 1;
    for (p = s; *p; p++)
        if (*p == '\r' || *p == '\n')
            return 0;
    return 1;
}

static void policy_add_error(struct command_queue_policy_report *report, const char *error)
{
    if (report->count < (int)(sizeof(report->errors) / sizeof(report->errors[0])))
        report->errors[report->count++] = error;
}

struct command_queue_policy_report bb_command_queue_validate_policy(void)
{
    struct command_queue_policy_report report = {{0}, 0};

    if (!exact_value(BB_COMMAND_QUEUE_ENABLE, "yes", "no"))
        policy_add_error(&report, "invalid command queue enable value");
    if (!valid_port_value(BB_COMMAND_QUEUE_PORT))
        policy_add_error(&report, "invalid command queue port");
    if (!valid_uint_value(BB_COMMAND_QUEUE_POLL_INTERVAL_SEC))
        policy_add_error(&report, "invalid command queue poll interval");
    if (!valid_uint_value(BB_COMMAND_QUEUE_POLL_JITTER_PCT))
        policy_add_error(&report, "invalid command queue poll jitter");
    if (!valid_backoff_value(BB_COMMAND_QUEUE_POLL_BACKOFF))
        policy_add_error(&report, "invalid command queue poll backoff");
    if (!valid_uint_value(BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC))
        policy_add_error(&report, "invalid command queue poll max interval");
    if (!valid_uint_value(BB_COMMAND_QUEUE_MAX_POLLS))
        policy_add_error(&report, "invalid command queue max polls");
    if (!exact_value(BB_COMMAND_QUEUE_TLS, "yes", "no"))
        policy_add_error(&report, "invalid command queue TLS value");
    if (!exact_value(BB_COMMAND_QUEUE_REQUIRE_TOKEN, "yes", "no"))
        policy_add_error(&report, "invalid command queue token requirement");
    if (!exact_value(BB_COMMAND_QUEUE_TOKEN_SOURCE, "manual", "generated"))
        policy_add_error(&report, "invalid command queue token source");
    if (!valid_token_value(BB_COMMAND_QUEUE_TOKEN))
        policy_add_error(&report, "invalid command queue token value");
    if (!strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") &&
        !strcmp(BB_COMMAND_QUEUE_REQUIRE_TOKEN, "yes") &&
        !BB_COMMAND_QUEUE_TOKEN[0])
        policy_add_error(&report, "enabled command queue requires BB_COMMAND_QUEUE_TOKEN when token requirement is yes");
    if (!valid_policy_value(BB_COMMAND_QUEUE_ALLOWED_COMMANDS))
        policy_add_error(&report, "invalid command queue allowed commands policy");
    if (!valid_execution_value(BB_COMMAND_QUEUE_EXECUTION))
        policy_add_error(&report, "invalid command queue execution mode");
    if (!exact_value(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "yes", "no"))
        policy_add_error(&report, "invalid command queue arbitrary-execution flag");
    if (strcmp(BB_COMMAND_QUEUE_ENABLE, "yes")) {
        if (strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "none"))
            policy_add_error(&report, "disabled command queue must keep allowed commands policy none");
        if (strcmp(BB_COMMAND_QUEUE_EXECUTION, "metadata-only"))
            policy_add_error(&report, "disabled command queue must keep execution mode metadata-only");
        if (strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "no"))
            policy_add_error(&report, "disabled command queue must not allow arbitrary execution");
    }
    if (!strcmp(BB_COMMAND_QUEUE_EXECUTION, "execute") &&
        !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "none"))
        policy_add_error(&report, "command queue execution mode execute requires a non-none allowed commands policy");
    if (!strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "yes") &&
        strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "custom"))
        policy_add_error(&report, "arbitrary command queue execution requires allowed commands policy custom");
    return report;
}

int bb_command_queue_policy_valid(const struct command_queue_policy_report *report)
{
    return report->count == 0;
}
