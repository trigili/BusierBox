#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <string.h>

#include "effective_config.h"
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
    puts("usage: busierbox command-queue [status|poll|once|daemon] [--json] [--dry-run]");
    puts("Inspect explicit opt-in command queue policy and target polling plan.");
    puts("This build does not fetch, deliver, or execute queued commands.");
}

static int mode_would_poll(const char *mode, int enabled)
{
    return enabled && (strcmp(mode, "status") != 0);
}

static const char *mode_status(const char *mode, int enabled)
{
    if (!enabled)
        return "disabled";
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

static void print_json(const char *mode, int dry_run)
{
    int enabled = yes_value(BB_COMMAND_QUEUE_ENABLE);
    fputs("{\"schema\":1,\"command\":\"command-queue\",\"mode\":", stdout);
    bb_json_string(stdout, mode);
    printf(",\"enabled\":%s", enabled ? "true" : "false");
    printf(",\"dry_run\":%s", dry_run ? "true" : "false");
    printf(",\"would_poll\":%s", mode_would_poll(mode, enabled) ? "true" : "false");
    fputs(",\"operator_host\":", stdout);
    bb_json_string(stdout, BB_OPERATOR_SERVER_HOST);
    fputs(",\"port\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_PORT);
    fputs(",\"tls\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_TLS);
    fputs(",\"endpoint\":", stdout);
    if (BB_OPERATOR_SERVER_HOST[0]) {
        char endpoint[512];
        snprintf(endpoint, sizeof(endpoint), "%s:%s", BB_OPERATOR_SERVER_HOST, BB_COMMAND_QUEUE_PORT);
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
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"delivery_supported\":false", stdout);
    fputs(",\"result_upload_supported\":false", stdout);
    fputs(",\"poll_transport_supported\":false", stdout);
    fputs(",\"status\":", stdout);
    bb_json_string(stdout, mode_status(mode, enabled));
    fputs(",\"safety_boundary\":\"target polling is explicit and dry-run only in this build; no command delivery or execution is implemented\"", stdout);
    fputs(",\"queued_command\":null}\n", stdout);
}

static void print_text(const char *mode, int dry_run)
{
    int enabled = yes_value(BB_COMMAND_QUEUE_ENABLE);
    printf("command_queue_mode=%s\n", mode);
    printf("command_queue_enable=%s\n", BB_COMMAND_QUEUE_ENABLE);
    printf("command_queue_dry_run=%s\n", dry_run ? "yes" : "no");
    printf("command_queue_would_poll=%s\n", mode_would_poll(mode, enabled) ? "yes" : "no");
    printf("command_queue_operator_host=%s\n", BB_OPERATOR_SERVER_HOST);
    printf("command_queue_port=%s\n", BB_COMMAND_QUEUE_PORT);
    if (BB_OPERATOR_SERVER_HOST[0])
        printf("command_queue_endpoint=%s:%s\n", BB_OPERATOR_SERVER_HOST, BB_COMMAND_QUEUE_PORT);
    else
        puts("command_queue_endpoint=");
    printf("command_queue_tls=%s\n", BB_COMMAND_QUEUE_TLS);
    printf("command_queue_require_token=%s\n", BB_COMMAND_QUEUE_REQUIRE_TOKEN);
    printf("command_queue_token_source=%s\n", BB_COMMAND_QUEUE_TOKEN_SOURCE);
    printf("command_queue_allowed_commands=%s\n", BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    printf("command_queue_allow_arbitrary=%s\n", BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    puts("command_queue_execution_supported=no");
    puts("command_queue_delivery_supported=no");
    puts("command_queue_result_upload_supported=no");
    puts("command_queue_poll_transport_supported=no");
    printf("command_queue_status=%s\n", mode_status(mode, enabled));
    puts("command_queue_safety_boundary=explicit target polling dry-run only; queued command delivery/execution is not implemented");
}

int applet_command_queue_main(int argc, char **argv)
{
    const char *mode = "status";
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
        } else if (!strcmp(argv[i], "status") || !strcmp(argv[i], "poll") ||
                   !strcmp(argv[i], "once") || !strcmp(argv[i], "daemon")) {
            mode = argv[i];
        } else {
            fprintf(stderr, "command-queue: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json)
        print_json(mode, dry_run);
    else
        print_text(mode, dry_run);
    return 0;
}
