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

static int valid_policy_value(const char *s)
{
    return s && (!strcmp(s, "none") || !strcmp(s, "busierbox-only") ||
                 !strcmp(s, "allowlist") || !strcmp(s, "custom"));
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
    if (!exact_value(BB_COMMAND_QUEUE_TLS, "yes", "no"))
        policy_add_error(&report, "invalid command queue TLS value");
    if (!exact_value(BB_COMMAND_QUEUE_REQUIRE_TOKEN, "yes", "no"))
        policy_add_error(&report, "invalid command queue token requirement");
    if (!exact_value(BB_COMMAND_QUEUE_TOKEN_SOURCE, "manual", "generated"))
        policy_add_error(&report, "invalid command queue token source");
    if (!valid_policy_value(BB_COMMAND_QUEUE_ALLOWED_COMMANDS))
        policy_add_error(&report, "invalid command queue allowed commands policy");
    if (!exact_value(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "yes", "no"))
        policy_add_error(&report, "invalid command queue arbitrary-execution flag");
    if (strcmp(BB_COMMAND_QUEUE_ENABLE, "yes")) {
        if (strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "none"))
            policy_add_error(&report, "disabled command queue must keep allowed commands policy none");
        if (strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "no"))
            policy_add_error(&report, "disabled command queue must not allow arbitrary execution");
    }
    if (!strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "yes") &&
        strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "custom"))
        policy_add_error(&report, "arbitrary command queue execution requires allowed commands policy custom");
    return report;
}

int bb_command_queue_policy_valid(const struct command_queue_policy_report *report)
{
    return report->count == 0;
}
