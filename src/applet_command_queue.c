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
    puts("usage: busierbox command-queue [status|poll|once|daemon] [--json]");
    puts("Inspect explicit opt-in command queue policy. This build does not execute queued commands.");
}

static void print_json(const char *mode)
{
    int enabled = yes_value(BB_COMMAND_QUEUE_ENABLE);
    fputs("{\"schema\":1,\"command\":\"command-queue\",\"mode\":", stdout);
    bb_json_string(stdout, mode);
    printf(",\"enabled\":%s", enabled ? "true" : "false");
    fputs(",\"port\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_PORT);
    fputs(",\"tls\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_TLS);
    fputs(",\"require_token\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_REQUIRE_TOKEN);
    fputs(",\"token_source\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_TOKEN_SOURCE);
    fputs(",\"allowed_commands\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    fputs(",\"allow_arbitrary\":", stdout);
    bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"status\":", stdout);
    bb_json_string(stdout, enabled ? "configured_not_implemented" : "disabled");
    fputs(",\"safety_boundary\":\"target polling is explicit; no queued command execution is implemented in this build\"", stdout);
    fputs(",\"queued_command\":null}\n", stdout);
}

static void print_text(const char *mode)
{
    int enabled = yes_value(BB_COMMAND_QUEUE_ENABLE);
    printf("command_queue_mode=%s\n", mode);
    printf("command_queue_enable=%s\n", BB_COMMAND_QUEUE_ENABLE);
    printf("command_queue_port=%s\n", BB_COMMAND_QUEUE_PORT);
    printf("command_queue_tls=%s\n", BB_COMMAND_QUEUE_TLS);
    printf("command_queue_require_token=%s\n", BB_COMMAND_QUEUE_REQUIRE_TOKEN);
    printf("command_queue_token_source=%s\n", BB_COMMAND_QUEUE_TOKEN_SOURCE);
    printf("command_queue_allowed_commands=%s\n", BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    printf("command_queue_allow_arbitrary=%s\n", BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    puts("command_queue_execution_supported=no");
    printf("command_queue_status=%s\n", enabled ? "configured_not_implemented" : "disabled");
    puts("command_queue_safety_boundary=explicit target polling only; queued command execution is not implemented");
}

int applet_command_queue_main(int argc, char **argv)
{
    const char *mode = "status";
    int json = 0;
    int i;

    if (is_help(argc, argv)) {
        print_help();
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json")) {
            json = 1;
        } else if (!strcmp(argv[i], "status") || !strcmp(argv[i], "poll") ||
                   !strcmp(argv[i], "once") || !strcmp(argv[i], "daemon")) {
            mode = argv[i];
        } else {
            fprintf(stderr, "command-queue: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json)
        print_json(mode);
    else
        print_text(mode);
    return 0;
}
