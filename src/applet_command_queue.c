#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <string.h>

#include "effective_config.h"
#include "command_queue_policy.h"
#include "json_helpers.h"

static int yes_value(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "on"));
}

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static void print_help(void)
{
    puts("usage: busierbox command-queue [status|poll|once|daemon] [--json] [--dry-run] [--operator-host HOST]");
    puts("Inspect explicit opt-in command queue policy and target polling plan.");
    puts("This build does not fetch, deliver, or execute queued commands.");
}

static int mode_would_poll(const char *mode, int enabled, const char *operator_host, const struct command_queue_policy_report *report)
{
    return bb_command_queue_policy_valid(report) && enabled && operator_host && operator_host[0] && (strcmp(mode, "status") != 0);
}

static const char *mode_status(const char *mode, int enabled, const char *operator_host, const struct command_queue_policy_report *report)
{
    if (!bb_command_queue_policy_valid(report))
        return "invalid_policy";
    if (!enabled)
        return "disabled";
    if (!operator_host || !operator_host[0])
        return "missing_operator_host";
    if (!strcmp(mode, "status"))
        return "configured";
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

static void print_mode_semantics_json(const char *name, int selected)
{
    fputc('"', stdout);
    fputs(name, stdout);
    fputs("\":{", stdout);
    printf("\"selected\":%s", selected ? "true" : "false");
    printf(",\"requires_operator_host\":%s", mode_requires_operator_host(name) ? "true" : "false");
    printf(",\"would_poll_if_configured\":%s", strcmp(name, "status") ? "true" : "false");
    fputs(",\"dry_run_only\":true", stdout);
    fputs(",\"requires_explicit_target_action\":true", stdout);
    fputs(",\"would_contact_operator\":false", stdout);
    fputs(",\"delivery_supported\":false", stdout);
    fputs(",\"result_upload_supported\":false", stdout);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    fputs(",\"active_control_channel\":false", stdout);
    fputs(",\"operator_supplied_command_execution\":false", stdout);
    fputs(",\"lifecycle\":", stdout);
    bb_json_string(stdout, mode_lifecycle(name));
    fputc('}', stdout);
}

static void print_all_mode_semantics_json(const char *mode)
{
    fputs(",\"mode_semantics\":{", stdout);
    print_mode_semantics_json("status", !strcmp(mode, "status"));
    fputc(',', stdout);
    print_mode_semantics_json("poll", !strcmp(mode, "poll"));
    fputc(',', stdout);
    print_mode_semantics_json("once", !strcmp(mode, "once"));
    fputc(',', stdout);
    print_mode_semantics_json("daemon", !strcmp(mode, "daemon"));
    fputc('}', stdout);
}

static void print_json(const char *mode, int dry_run, const char *operator_host)
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
    fputs(",\"operator_queue_records_only\":false", stdout);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    fputs(",\"delivery_supported\":false", stdout);
    fputs(",\"poll_transport_supported\":false", stdout);
    fputs(",\"result_upload_supported\":false", stdout);
    fputs(",\"active_control_channel\":false", stdout);
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
    fputs(",\"poll_transport_supported\":false", stdout);
    fputs(",\"active_control_channel\":false", stdout);
    fputs(",\"status\":", stdout);
    bb_json_string(stdout, mode_status(mode, enabled, operator_host, &policy));
    fputs(",\"poll_plan\":{", stdout);
    fputs("\"mode\":", stdout); bb_json_string(stdout, mode);
    fputs(",\"status\":", stdout); bb_json_string(stdout, mode_status(mode, enabled, operator_host, &policy));
    printf(",\"enabled\":%s", enabled ? "true" : "false");
    printf(",\"policy_valid\":%s", valid ? "true" : "false");
    printf(",\"configured_for_polling\":%s", configured_for_polling ? "true" : "false");
    printf(",\"missing_operator_host\":%s", (valid && enabled && (!operator_host || !operator_host[0])) ? "true" : "false");
    printf(",\"would_poll\":%s", would_poll ? "true" : "false");
    fputs(",\"dry_run_only\":true", stdout);
    fputs(",\"requires_explicit_target_action\":true", stdout);
    fputs(",\"would_contact_operator\":false", stdout);
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
    fputs(",\"active_control_channel\":false", stdout);
    fputs(",\"queued_command_available\":false", stdout);
    fputs(",\"operator_supplied_command_execution\":false", stdout);
    fputc('}', stdout);
    print_all_mode_semantics_json(mode);
    fputs(",\"safety_boundary\":\"target polling is explicit and dry-run only in this build; no command delivery or execution is implemented\"", stdout);
    fputs(",\"queued_command\":null}\n", stdout);
}

static void print_text(const char *mode, int dry_run, const char *operator_host)
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
    puts("command_queue_poll_transport_supported=no");
    puts("command_queue_active_control_channel=no");
    printf("command_queue_status=%s\n", mode_status(mode, enabled, operator_host, &policy));
    puts("command_queue_poll_plan_dry_run_only=yes");
    puts("command_queue_poll_plan_requires_explicit_target_action=yes");
    puts("command_queue_poll_plan_would_contact_operator=no");
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
    puts("command_queue_modes_active_control_channel=no");
    puts("command_queue_safety_boundary=explicit target polling dry-run only; queued command delivery/execution is not implemented");
}

int applet_command_queue_main(int argc, char **argv)
{
    const char *mode = "status";
    const char *operator_host = BB_OPERATOR_SERVER_HOST;
    int json = 0, dry_run = 1;
    int i;

    if (is_help(argc, argv)) {
        print_help();
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json")) {
            json = 1;
        } else if (!strcmp(argv[i], "--dry-run")) {
            dry_run = 1;
        } else if (!strcmp(argv[i], "--operator-host") && i + 1 < argc) {
            operator_host = argv[++i];
        } else if (!strcmp(argv[i], "status") || !strcmp(argv[i], "poll") ||
                   !strcmp(argv[i], "once") || !strcmp(argv[i], "daemon")) {
            mode = argv[i];
        } else {
            fprintf(stderr, "command-queue: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json)
        print_json(mode, dry_run, operator_host);
    else
        print_text(mode, dry_run, operator_host);
    return 0;
}
