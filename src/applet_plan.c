#define _POSIX_C_SOURCE 200809L

#include <limits.h>
#include <stdio.h>
#include <string.h>

#include "applets.h"
#include "command_queue_policy.h"
#include "effective_config.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_RECOVERY_BINARY_NAME
#define BB_RECOVERY_BINARY_NAME "busierbox_recovery"
#endif

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static void plan_print_config_source_text(void)
{
    printf("effective_config_source=%s\n", bb_config_effective_source());
    printf("trailer_present=%s\n", bb_config_trailer_present() ? "yes" : "no");
    printf("trailer_valid=%s\n", bb_config_trailer_valid() ? "yes" : "no");
    printf("trailer_encoding=%s\n", bb_config_trailer_encoding());
    if (bb_config_trailer_present() && !bb_config_trailer_valid())
        printf("trailer_status=%s\n", bb_config_trailer_error());
}

static void plan_print_config_source_json(void)
{
    fputs(",\"config\":{\"effective_config_source\":", stdout);
    bb_json_string(stdout, bb_config_effective_source());
    printf(",\"trailer_present\":%s,\"trailer_valid\":%s",
           bb_config_trailer_present() ? "true" : "false",
           bb_config_trailer_valid() ? "true" : "false");
    fputs(",\"trailer_encoding\":", stdout);
    bb_json_string(stdout, bb_config_trailer_encoding());
    if (bb_config_trailer_present() && !bb_config_trailer_valid()) {
        fputs(",\"trailer_status\":", stdout);
        bb_json_string(stdout, bb_config_trailer_error());
    }
    fputc('}', stdout);
}

static int noresidue_active(void)
{
    return !strcmp(BB_RUNTIME_MODE, "no-residue");
}

static int noresidue_aggressive(void)
{
    return !strcmp(BB_NORESIDUE_LEVEL, "aggressive");
}

static const char *noresidue_guarantee_text(void)
{
    return noresidue_aggressive() ?
        "aggressive minimizes BusierBox runtime residue but cannot guarantee absence of residue" :
        "best-effort cleanup removes owned runtime state where reasonable";
}

static void plan_print_noresidue_policy_json(void)
{
    fputs("{\"active\":", stdout);
    fputs(noresidue_active() ? "true" : "false", stdout);
    fputs(",\"level\":", stdout);
    bb_json_string(stdout, BB_NORESIDUE_LEVEL);
    fputs(",\"cleanup_scope\":", stdout);
    bb_json_string(stdout, "BusierBox-owned runtime roots and ledgered files only");
    fputs(",\"best_effort\":true", stdout);
    fputs(",\"aggressive_minimizes_runtime_residue\":", stdout);
    fputs(noresidue_aggressive() ? "true" : "false", stdout);
    fputs(",\"forensic_no_trace\":false", stdout);
    fputs(",\"external_writes_require_explicit_apply\":true", stdout);
    fputs(",\"guarantee\":", stdout);
    bb_json_string(stdout, noresidue_guarantee_text());
    fputc('}', stdout);
}

static void plan_print_noresidue_policy_text(void)
{
    printf("noresidue_policy_active=%s\n", noresidue_active() ? "yes" : "no");
    printf("noresidue_policy_level=%s\n", BB_NORESIDUE_LEVEL);
    puts("noresidue_policy_cleanup_scope=BusierBox-owned runtime roots and ledgered files only");
    puts("noresidue_policy_best_effort=yes");
    printf("noresidue_policy_aggressive_minimizes_runtime_residue=%s\n", noresidue_aggressive() ? "yes" : "no");
    puts("noresidue_policy_forensic_no_trace=no");
    puts("noresidue_policy_external_writes_require_explicit_apply=yes");
    printf("noresidue_policy_guarantee=%s\n", noresidue_guarantee_text());
}

static void plan_print_extract(int json)
{
    char payload[PATH_MAX], ledger[PATH_MAX];
    int have_payload = bb_candidate_payload_dir(payload, sizeof(payload)) == 0;
    int have_embedded = bb_embedded_payload_available();
    int have_archive = bb_dev_payload_archive_available();

    if (json) {
        fputs("{\"schema\":1,\"command\":\"extract\",\"would_create\":[", stdout);
        bb_json_string(stdout, BB_RUNTIME_ROOT);
        fputs(",", stdout);
        {
            char p[PATH_MAX];
            snprintf(p, sizeof(p), "%s/payload", BB_RUNTIME_ROOT);
            bb_json_string(stdout, p);
        }
        fputs("],\"would_modify\":[", stdout);
        bb_json_string(stdout, BB_RUNTIME_ROOT);
        fputs("],\"would_remove\":[],\"would_start\":[],\"would_connect\":[],\"requires_external_writes\":false", stdout);
        fputs(",\"runtime_root\":", stdout); bb_json_string(stdout, BB_RUNTIME_ROOT);
        fputs(",\"runtime_mode\":", stdout); bb_json_string(stdout, BB_RUNTIME_MODE);
        fputs(",\"noresidue_level\":", stdout); bb_json_string(stdout, BB_NORESIDUE_LEVEL);
        fputs(",\"noresidue_policy\":", stdout); plan_print_noresidue_policy_json();
        fputs(",\"fallback_root\":", stdout); bb_json_string(stdout, BB_RUNTIME_FALLBACK_ROOT);
        printf(",\"fallback_enabled\":%s", !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") ? "true" : "false");
        fputs(",\"cleanup_ledger_path\":", stdout);
        bb_json_string(stdout, bb_ledger_path(ledger, sizeof(ledger)));
        printf(",\"payload_already_available\":%s,\"embedded_payload_available\":%s,\"dev_archive_available\":%s",
               have_payload ? "true" : "false", have_embedded ? "true" : "false", have_archive ? "true" : "false");
        plan_print_config_source_json();
        puts("}");
        return;
    }

    puts("Plan: extract");
    plan_print_config_source_text();
    printf("runtime_root=%s\n", BB_RUNTIME_ROOT);
    printf("runtime_mode=%s\n", BB_RUNTIME_MODE);
    printf("noresidue_level=%s\n", BB_NORESIDUE_LEVEL);
    plan_print_noresidue_policy_text();
    printf("fallback_root=%s\n", BB_RUNTIME_FALLBACK_ROOT);
    printf("fallback_enabled=%s\n", !strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") ? "yes" : "no");
    printf("cleanup_ledger_path=%s\n", bb_ledger_path(ledger, sizeof(ledger)));
    printf("payload_already_available=%s\n", have_payload ? "yes" : "no");
    printf("embedded_payload_available=%s\n", have_embedded ? "yes" : "no");
    printf("dev_archive_available=%s\n", have_archive ? "yes" : "no");
    puts("would_create:");
    printf("  %s\n", BB_RUNTIME_ROOT);
    printf("  %s/payload\n", BB_RUNTIME_ROOT);
    puts("would_modify:");
    printf("  %s\n", BB_RUNTIME_ROOT);
    puts("requires_external_writes=no");
}

static void plan_print_clean(int json)
{
    char ledger[PATH_MAX];
    if (json) {
        fputs("{\"schema\":1,\"command\":\"clean\",\"would_create\":[],\"would_modify\":[],\"would_remove\":[", stdout);
        bb_json_string(stdout, BB_RUNTIME_ROOT);
        if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") && BB_RUNTIME_FALLBACK_ROOT[0] && strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT)) {
            fputs(",", stdout);
            bb_json_string(stdout, BB_RUNTIME_FALLBACK_ROOT);
        }
        fputs("],\"would_start\":[],\"would_connect\":[],\"requires_external_writes\":false", stdout);
        fputs(",\"runtime_root\":", stdout); bb_json_string(stdout, BB_RUNTIME_ROOT);
        fputs(",\"runtime_mode\":", stdout); bb_json_string(stdout, BB_RUNTIME_MODE);
        fputs(",\"noresidue_level\":", stdout); bb_json_string(stdout, BB_NORESIDUE_LEVEL);
        fputs(",\"noresidue_policy\":", stdout); plan_print_noresidue_policy_json();
        fputs(",\"cleanup_ledger_path\":", stdout); bb_json_string(stdout, bb_ledger_path(ledger, sizeof(ledger)));
        plan_print_config_source_json();
        puts("}");
        return;
    }
    puts("Plan: clean");
    plan_print_config_source_text();
    printf("runtime_root=%s\n", BB_RUNTIME_ROOT);
    printf("runtime_mode=%s\n", BB_RUNTIME_MODE);
    printf("noresidue_level=%s\n", BB_NORESIDUE_LEVEL);
    plan_print_noresidue_policy_text();
    printf("cleanup_ledger_path=%s\n", bb_ledger_path(ledger, sizeof(ledger)));
    puts("would_remove:");
    printf("  %s\n", BB_RUNTIME_ROOT);
    if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") && BB_RUNTIME_FALLBACK_ROOT[0] && strcmp(BB_RUNTIME_FALLBACK_ROOT, BB_RUNTIME_ROOT))
        printf("  %s (fallback root, if used)\n", BB_RUNTIME_FALLBACK_ROOT);
    puts("requires_external_writes=no");
    puts("external_cleanup_note=external ledger cleanup still requires clean --external --apply");
}

static int rshell_policy_reconnects_after_disconnect(const char *policy)
{
    return !strcmp(policy, "reconnect") || !strcmp(policy, "persistent");
}

static int rshell_policy_stops_after_first_success(const char *policy)
{
    return !strcmp(policy, "single");
}

static int rshell_policy_persistent_lifecycle(const char *policy)
{
    return !strcmp(policy, "persistent");
}

static int rshell_policy_valid(const char *policy)
{
    return !strcmp(policy, "single") ||
           !strcmp(policy, "reconnect") ||
           !strcmp(policy, "persistent");
}

static const char *rshell_policy_post_disconnect_count(const char *policy)
{
    if (!strcmp(policy, "single"))
        return "0";
    if (!strcmp(policy, "persistent"))
        return "-1";
    return BB_RSHELL_RETRY_COUNT;
}

static void plan_print_rshell(int json)
{
    char guard[PATH_MAX], log_path[PATH_MAX], server[256], connect[256];
    snprintf(guard, sizeof(guard), "%s", BB_AUTORUN_GUARD_PATH);
    snprintf(log_path, sizeof(log_path), "%s/rshell.log", guard);
    if (!strcmp(BB_RSHELL_TRANSPORT, "ssh")) {
        snprintf(server, sizeof(server), "ssh server %s@%s:%s", BB_OPERATOR_SERVER_USER, BB_OPERATOR_SERVER_HOST, BB_OPERATOR_SERVER_SSH_PORT);
        snprintf(connect, sizeof(connect), "remote forward %s:%s", BB_OPERATOR_TARGET_BIND_HOST, BB_OPERATOR_REMOTE_FORWARD_PORT);
    } else if (!strcmp(BB_RSHELL_TRANSPORT, "builtin")) {
        snprintf(server, sizeof(server), "builtin TLS listener %s:%s", BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT);
        snprintf(connect, sizeof(connect), "builtin reverse shell");
    } else if (!strcmp(BB_RSHELL_TRANSPORT, "socat")) {
        snprintf(server, sizeof(server), "socat listener %s:%s", BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT);
        snprintf(connect, sizeof(connect), "socat reverse shell");
    } else {
        snprintf(server, sizeof(server), "disabled");
        snprintf(connect, sizeof(connect), "none");
    }

    if (json) {
        fputs("{\"schema\":1,\"command\":\"rshell\",\"would_create\":[", stdout);
        bb_json_string(stdout, guard);
        fputs(",", stdout);
        bb_json_string(stdout, log_path);
        fputs("],\"would_modify\":[", stdout);
        bb_json_string(stdout, guard);
        fputs("],\"would_remove\":[],\"would_start\":[", stdout);
        bb_json_string(stdout, BB_RSHELL_TRANSPORT);
        fputs("],\"would_connect\":[", stdout);
        bb_json_string(stdout, server);
        fputs("],\"requires_external_writes\":false", stdout);
        fputs(",\"runtime_root\":", stdout); bb_json_string(stdout, BB_RUNTIME_ROOT);
        fputs(",\"transport\":", stdout); bb_json_string(stdout, BB_RSHELL_TRANSPORT);
        fputs(",\"encryption\":", stdout); bb_json_string(stdout, BB_RSHELL_ENCRYPTION);
        fputs(",\"run_mode\":", stdout); bb_json_string(stdout, BB_RSHELL_RUN_MODE);
        fputs(",\"session_policy\":", stdout); bb_json_string(stdout, BB_RSHELL_SESSION_POLICY);
        printf(",\"session_policy_valid\":%s", rshell_policy_valid(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
        fputs(",\"session_policy_errors\":[", stdout);
        if (!rshell_policy_valid(BB_RSHELL_SESSION_POLICY))
            bb_json_string(stdout, "unsupported rshell session policy");
        fputs("]", stdout);
        printf(",\"session_semantics\":{\"retry_until_first_connection\":true,\"stop_after_first_success\":%s,\"reconnect_after_disconnect\":%s,\"persistent_lifecycle\":%s,\"fresh_session_on_reconnect\":%s,\"session_resume_supported\":false}",
               rshell_policy_stops_after_first_success(BB_RSHELL_SESSION_POLICY) ? "true" : "false",
               rshell_policy_reconnects_after_disconnect(BB_RSHELL_SESSION_POLICY) ? "true" : "false",
               rshell_policy_persistent_lifecycle(BB_RSHELL_SESSION_POLICY) ? "true" : "false",
               rshell_policy_reconnects_after_disconnect(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
        printf(",\"session_policy_summary\":{\"valid\":%s,\"retry_scope\":\"pre-connect",
               rshell_policy_valid(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
        if (rshell_policy_reconnects_after_disconnect(BB_RSHELL_SESSION_POLICY))
            fputs("+post-disconnect", stdout);
        fputs("\",\"post_disconnect_retry_count\":", stdout);
        bb_json_string(stdout, rshell_policy_post_disconnect_count(BB_RSHELL_SESSION_POLICY));
        printf(",\"stops_after_success\":%s,\"reconnects_after_disconnect\":%s,\"persistent_lifecycle\":%s,\"fresh_session_on_reconnect\":%s,\"session_resume_supported\":false}",
               rshell_policy_stops_after_first_success(BB_RSHELL_SESSION_POLICY) ? "true" : "false",
               rshell_policy_reconnects_after_disconnect(BB_RSHELL_SESSION_POLICY) ? "true" : "false",
               rshell_policy_persistent_lifecycle(BB_RSHELL_SESSION_POLICY) ? "true" : "false",
               rshell_policy_reconnects_after_disconnect(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
        fputs(",\"retry\":{\"pre_connect_count\":", stdout);
        bb_json_string(stdout, BB_RSHELL_RETRY_COUNT);
        fputs(",\"post_disconnect_count\":", stdout);
        bb_json_string(stdout, rshell_policy_post_disconnect_count(BB_RSHELL_SESSION_POLICY));
        fputs("}", stdout);
        fputs(",\"shell_provider\":", stdout); bb_json_string(stdout, BB_RSHELL_SHELL_PROVIDER);
        fputs(",\"operator_host\":", stdout); bb_json_string(stdout, BB_OPERATOR_SERVER_HOST);
        fputs(",\"expected_transport_behavior\":", stdout); bb_json_string(stdout, connect);
        printf(",\"zero_arg_autorun\":%s", !strcmp(BB_ZERO_ARG_MODE, "rshell") ? "true" : "false");
        printf(",\"no_residue_cleanup\":%s", !strcmp(BB_RUNTIME_MODE, "no-residue") ? "true" : "false");
        fputs(",\"noresidue_level\":", stdout); bb_json_string(stdout, BB_NORESIDUE_LEVEL);
        fputs(",\"noresidue_policy\":", stdout); plan_print_noresidue_policy_json();
        plan_print_config_source_json();
        puts("}");
        return;
    }

    puts("Plan: rshell");
    plan_print_config_source_text();
    printf("runtime_root=%s\n", BB_RUNTIME_ROOT);
    printf("transport=%s\n", BB_RSHELL_TRANSPORT);
    printf("encryption=%s\n", BB_RSHELL_ENCRYPTION);
    printf("run_mode=%s\n", BB_RSHELL_RUN_MODE);
    printf("session_policy=%s\n", BB_RSHELL_SESSION_POLICY);
    printf("session_policy_valid=%s\n", rshell_policy_valid(BB_RSHELL_SESSION_POLICY) ? "yes" : "no");
    if (!rshell_policy_valid(BB_RSHELL_SESSION_POLICY))
        puts("session_policy_error=unsupported rshell session policy");
    printf("retry_until_first_connection=yes\n");
    printf("post_disconnect_retry_count=%s\n", rshell_policy_post_disconnect_count(BB_RSHELL_SESSION_POLICY));
    printf("session_resume_supported=no\n");
    printf("shell_provider=%s\n", BB_RSHELL_SHELL_PROVIDER);
    printf("operator_host=%s\n", BB_OPERATOR_SERVER_HOST);
    printf("expected_transport_behavior=%s\n", connect);
    printf("zero_arg_autorun=%s\n", !strcmp(BB_ZERO_ARG_MODE, "rshell") ? "yes" : "no");
    printf("no_residue_cleanup=%s\n", !strcmp(BB_RUNTIME_MODE, "no-residue") ? "yes" : "no");
    printf("noresidue_level=%s\n", BB_NORESIDUE_LEVEL);
    plan_print_noresidue_policy_text();
    puts("would_create:");
    printf("  %s\n", guard);
    printf("  %s\n", log_path);
    puts("would_start:");
    printf("  %s transport\n", BB_RSHELL_TRANSPORT);
    puts("would_connect:");
    printf("  %s\n", server);
    puts("requires_external_writes=no");
}

static const char *command_queue_mode_lifecycle(const char *mode)
{
    if (!strcmp(mode, "status"))
        return "inspect";
    if (!strcmp(mode, "poll"))
        return "single-poll";
    if (!strcmp(mode, "once"))
        return "single-cycle";
    if (!strcmp(mode, "daemon"))
        return "long-running";
    if (!strcmp(mode, "stop"))
        return "stop";
    return "unknown";
}

static int command_queue_mode_polls(const char *mode)
{
    return strcmp(mode, "status") && strcmp(mode, "stop");
}

static void plan_print_command_queue_mode_record(const char *mode, int configured)
{
    int polls = command_queue_mode_polls(mode);
    int planned = configured && !strcmp(mode, "poll");

    fputs("{\"mode\":", stdout);
    bb_json_string(stdout, mode);
    printf(",\"planned\":%s", planned ? "true" : "false");
    printf(",\"would_start\":%s", planned ? "true" : "false");
    printf(",\"configured_for_polling\":%s", configured ? "true" : "false");
    printf(",\"requires_operator_host\":%s", polls ? "true" : "false");
    printf(",\"would_poll_if_configured\":%s", polls ? "true" : "false");
    fputs(",\"requires_explicit_target_action\":true", stdout);
    fputs(",\"execution_supported\":false", stdout);
    fputs(",\"executes_commands\":false", stdout);
    fputs(",\"operator_supplied_command_execution\":false", stdout);
    fputs(",\"active_control_channel\":false", stdout);
    fputs(",\"lifecycle\":", stdout);
    bb_json_string(stdout, command_queue_mode_lifecycle(mode));
    fputc('}', stdout);
}

static void plan_print_command_queue_mode_records(int configured)
{
    fputs(",\"mode_records\":[", stdout);
    plan_print_command_queue_mode_record("status", configured);
    fputc(',', stdout);
    plan_print_command_queue_mode_record("poll", configured);
    fputc(',', stdout);
    plan_print_command_queue_mode_record("once", configured);
    fputc(',', stdout);
    plan_print_command_queue_mode_record("daemon", configured);
    fputc(',', stdout);
    plan_print_command_queue_mode_record("stop", configured);
    fputc(']', stdout);
}

static void plan_print_command_queue_mode_index_array(const char *field, const char *value, int configured)
{
    static const char *modes[] = {"status", "poll", "once", "daemon", "stop"};
    size_t i;
    int first = 1;

    fputc('[', stdout);
    for (i = 0; i < sizeof(modes) / sizeof(modes[0]); i++) {
        const char *mode = modes[i];
        int polls = command_queue_mode_polls(mode);
        int planned = configured && !strcmp(mode, "poll");
        const char *candidate = "";
        if (!strcmp(field, "mode"))
            candidate = mode;
        else if (!strcmp(field, "lifecycle"))
            candidate = command_queue_mode_lifecycle(mode);
        else if (!strcmp(field, "would_poll_if_configured"))
            candidate = polls ? "true" : "false";
        else if (!strcmp(field, "planned"))
            candidate = planned ? "true" : "false";
        else if (!strcmp(field, "execution_supported"))
            candidate = "false";
        else if (!strcmp(field, "active_control_channel"))
            candidate = "false";
        if (strcmp(candidate, value))
            continue;
        printf("%s%zu", first ? "" : ",", i);
        first = 0;
    }
    fputc(']', stdout);
}

static void plan_print_command_queue_mode_indexes(int configured)
{
    static const char *modes[] = {"status", "poll", "once", "daemon", "stop"};
    static const char *lifecycles[] = {"inspect", "single-poll", "single-cycle", "long-running", "stop"};
    static const char *bools[] = {"true", "false"};
    size_t i;

    fputs(",\"mode_records_by_mode\":{", stdout);
    for (i = 0; i < sizeof(modes) / sizeof(modes[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, modes[i]);
        fputc(':', stdout);
        plan_print_command_queue_mode_index_array("mode", modes[i], configured);
    }
    fputs("},\"mode_records_by_lifecycle\":{", stdout);
    for (i = 0; i < sizeof(lifecycles) / sizeof(lifecycles[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, lifecycles[i]);
        fputc(':', stdout);
        plan_print_command_queue_mode_index_array("lifecycle", lifecycles[i], configured);
    }
    fputs("},\"mode_records_by_would_poll_if_configured\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        plan_print_command_queue_mode_index_array("would_poll_if_configured", bools[i], configured);
    }
    fputs("},\"mode_records_by_planned\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        plan_print_command_queue_mode_index_array("planned", bools[i], configured);
    }
    fputs("},\"mode_records_by_execution_supported\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        plan_print_command_queue_mode_index_array("execution_supported", bools[i], configured);
    }
    fputs("},\"mode_records_by_active_control_channel\":{", stdout);
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fputc(',', stdout);
        bb_json_string(stdout, bools[i]);
        fputc(':', stdout);
        plan_print_command_queue_mode_index_array("active_control_channel", bools[i], configured);
    }
    fputc('}', stdout);
}

static void plan_print_command_queue_mode_summary(int configured)
{
    fputs(",\"mode_summary\":{\"mode_count\":5,\"polling_mode_count\":3,\"operator_host_required_mode_count\":3", stdout);
    printf(",\"planned_mode_count\":%d", configured ? 1 : 0);
    fputs(",\"execution_supported_mode_count\":0,\"active_control_channel_mode_count\":0,\"operator_supplied_command_execution_mode_count\":0}", stdout);
}

static void plan_print_command_queue_api_collections(void)
{
    fputs(",\"api_collections\":{\"mode_records\":{\"name\":\"mode_records\",\"count\":5", stdout);
    fputs(",\"count_summary_key\":\"mode_summary.mode_count\",\"primary_key\":\"mode\",\"summary_key\":\"mode_summary.mode_count\"", stdout);
    fputs(",\"indexes\":[\"mode_records_by_mode\",\"mode_records_by_lifecycle\",\"mode_records_by_would_poll_if_configured\",\"mode_records_by_planned\",\"mode_records_by_execution_supported\",\"mode_records_by_active_control_channel\"]}}", stdout);
}

static void plan_print_command_queue(int json)
{
    int enabled = !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes");
    struct command_queue_policy_report policy = bb_command_queue_validate_policy();
    int valid = bb_command_queue_policy_valid(&policy);
    int configured = valid && enabled && BB_OPERATOR_SERVER_HOST[0];
    int i;

    if (json) {
        fputs("{\"schema\":1,\"command\":\"command-queue\",\"would_create\":[],\"would_modify\":[],\"would_remove\":[],\"would_start\":[", stdout);
        if (configured)
            bb_json_string(stdout, "command-queue poll");
        fputs("],\"would_connect\":[", stdout);
        if (configured) {
            char endpoint[128];
            snprintf(endpoint, sizeof(endpoint), "%s:%s", BB_OPERATOR_SERVER_HOST, BB_COMMAND_QUEUE_PORT);
            bb_json_string(stdout, endpoint);
        }
        fputs("],\"requires_external_writes\":false", stdout);
        printf(",\"enabled\":%s,\"policy_valid\":%s,\"configured_for_polling\":%s,\"missing_operator_host\":%s,\"execution_supported\":false,\"result_upload_supported\":true",
               enabled ? "true" : "false", valid ? "true" : "false",
               configured ? "true" : "false",
               (valid && enabled && !BB_OPERATOR_SERVER_HOST[0]) ? "true" : "false");
        fputs(",\"policy_errors\":[", stdout);
        for (i = 0; i < policy.count; i++) {
            if (i)
                fputc(',', stdout);
            bb_json_string(stdout, policy.errors[i]);
        }
        fputc(']', stdout);
        fputs(",\"require_token\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_REQUIRE_TOKEN);
        fputs(",\"token_source\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_TOKEN_SOURCE);
        printf(",\"token_required\":%s,\"token_configured\":%s",
               !strcmp(BB_COMMAND_QUEUE_REQUIRE_TOKEN, "yes") ? "true" : "false",
               BB_COMMAND_QUEUE_TOKEN[0] ? "true" : "false");
        fputs(",\"allowed_commands\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
        fputs(",\"allow_arbitrary\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
        fputs(",\"poll_interval_sec\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_POLL_INTERVAL_SEC);
        fputs(",\"poll_jitter_pct\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_POLL_JITTER_PCT);
        fputs(",\"poll_backoff\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_POLL_BACKOFF);
        fputs(",\"poll_max_interval_sec\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC);
        fputs(",\"max_polls\":", stdout); bb_json_string(stdout, BB_COMMAND_QUEUE_MAX_POLLS);
        fputs(",\"daemon_state_file\":", stdout);
        {
            char state_file[512];
            snprintf(state_file, sizeof(state_file), "%s/run/command-queue-daemon.state", BB_RUNTIME_ROOT);
            bb_json_string(stdout, state_file);
        }
        fputs(",\"daemon_state_file_supported\":true,\"daemon_status_supported\":true,\"daemon_stop_supported\":true", stdout);
        plan_print_command_queue_mode_records(configured);
        plan_print_command_queue_mode_indexes(configured);
        plan_print_command_queue_mode_summary(configured);
        plan_print_command_queue_api_collections();
        fputs(",\"safety_boundary\":", stdout); bb_json_string(stdout, "explicit opt-in target polling; queued command execution is not implemented");
        plan_print_config_source_json();
        puts("}");
        return;
    }
    puts("Plan: command-queue");
    plan_print_config_source_text();
    printf("enabled=%s\n", BB_COMMAND_QUEUE_ENABLE);
    printf("policy_valid=%s\n", valid ? "yes" : "no");
    for (i = 0; i < policy.count; i++)
        printf("policy_error=%s\n", policy.errors[i]);
    printf("configured_for_polling=%s\n", configured ? "yes" : "no");
    printf("missing_operator_host=%s\n", (valid && enabled && !BB_OPERATOR_SERVER_HOST[0]) ? "yes" : "no");
    printf("port=%s\n", BB_COMMAND_QUEUE_PORT);
    printf("tls=%s\n", BB_COMMAND_QUEUE_TLS);
    printf("require_token=%s\n", BB_COMMAND_QUEUE_REQUIRE_TOKEN);
    printf("token_source=%s\n", BB_COMMAND_QUEUE_TOKEN_SOURCE);
    printf("token_configured=%s\n", BB_COMMAND_QUEUE_TOKEN[0] ? "yes" : "no");
    printf("allowed_commands=%s\n", BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    printf("allow_arbitrary=%s\n", BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    printf("poll_interval_sec=%s\n", BB_COMMAND_QUEUE_POLL_INTERVAL_SEC);
    printf("poll_jitter_pct=%s\n", BB_COMMAND_QUEUE_POLL_JITTER_PCT);
    printf("poll_backoff=%s\n", BB_COMMAND_QUEUE_POLL_BACKOFF);
    printf("poll_max_interval_sec=%s\n", BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC);
    printf("max_polls=%s\n", BB_COMMAND_QUEUE_MAX_POLLS);
    printf("daemon_state_file=%s/run/command-queue-daemon.state\n", BB_RUNTIME_ROOT);
    puts("daemon_state_file_supported=yes");
    puts("daemon_status_supported=yes");
    puts("daemon_stop_supported=yes");
    puts("execution_supported=no");
    puts("result_upload_supported=yes");
    puts("safety_boundary=explicit opt-in target polling; queued command execution is not implemented");
    puts("requires_external_writes=no");
}

struct plan_recovery_method {
    const char *name;
    const char *path;
};

static const struct plan_recovery_method plan_recovery_methods[] = {
    {"openwrt-procd", "etc/init.d/busierbox_recovery"},
    {"sysv-init", "etc/rc.d/S99busierbox_recovery"},
    {"systemd-unit", "etc/systemd/system/busierbox-recovery.service"},
    {"cron-reboot", "etc/crontabs/root"},
    {"at-job", "var/spool/at"},
    {"rc-local", "etc/rc.local"},
    {"hotplug-iface", "etc/hotplug.d/iface/99-busierbox-recovery"},
    {"profile", "etc/profile.d/busierbox-recovery.sh"},
};

static const struct plan_recovery_method *find_plan_recovery_method(const char *name)
{
    size_t i;
    if (!strcmp(name, "procd"))
        name = "openwrt-procd";
    else if (!strcmp(name, "rcS"))
        name = "sysv-init";
    else if (!strcmp(name, "systemd"))
        name = "systemd-unit";
    else if (!strcmp(name, "cron"))
        name = "cron-reboot";
    else if (!strcmp(name, "rc.local"))
        name = "rc-local";
    else if (!strcmp(name, "hotplug"))
        name = "hotplug-iface";
    for (i = 0; i < sizeof(plan_recovery_methods) / sizeof(plan_recovery_methods[0]); i++)
        if (!strcmp(plan_recovery_methods[i].name, name))
            return &plan_recovery_methods[i];
    return NULL;
}

static void plan_recovery_join(char *out, size_t outsz, const char *root, const char *rel)
{
    if (!root || !*root || !strcmp(root, "/"))
        snprintf(out, outsz, "/%s", rel);
    else
        snprintf(out, outsz, "%s/%s", root, rel);
}

static void plan_recovery_bin_path(char *out, size_t outsz, const char *root, const char *name)
{
    char rel[PATH_MAX];
    snprintf(rel, sizeof(rel), "usr/bin/%s", name);
    plan_recovery_join(out, outsz, root, rel);
}

static const char *plan_recovery_action_category(const char *action)
{
    if (!strcmp(action, "evidence-push") || !strcmp(action, "evidence-then-rshell") || !strcmp(action, "dmesg-push"))
        return "evidence";
    if (!strcmp(action, "rshell"))
        return "reverse-shell";
    if (!strcmp(action, "command"))
        return "command";
    if (!strcmp(action, "script"))
        return "script";
    return "status";
}

static int plan_recovery_action_uploads_evidence(const char *action)
{
    return !strcmp(action, "evidence-push") || !strcmp(action, "evidence-then-rshell") || !strcmp(action, "dmesg-push");
}

static int plan_recovery_action_collects_dmesg(const char *action)
{
    return !strcmp(action, "dmesg-push");
}

static int plan_recovery_action_starts_rshell(const char *action)
{
    return !strcmp(action, "rshell") || !strcmp(action, "evidence-then-rshell");
}

static int plan_recovery_action_starts_rshell_after_evidence(const char *action)
{
    return !strcmp(action, "evidence-then-rshell");
}

static int plan_recovery_action_executes_operator_supplied_command(const char *action)
{
    return !strcmp(action, "command") || !strcmp(action, "script");
}

static void plan_recovery_print_action_semantics_json(const char *action)
{
    fputs("\"action_semantics\":{", stdout);
    fputs("\"category\":", stdout); bb_json_string(stdout, plan_recovery_action_category(action));
    printf(",\"uploads_evidence\":%s", plan_recovery_action_uploads_evidence(action) ? "true" : "false");
    printf(",\"collects_dmesg\":%s", plan_recovery_action_collects_dmesg(action) ? "true" : "false");
    printf(",\"starts_rshell\":%s", plan_recovery_action_starts_rshell(action) ? "true" : "false");
    printf(",\"starts_rshell_after_evidence\":%s", plan_recovery_action_starts_rshell_after_evidence(action) ? "true" : "false");
    printf(",\"executes_operator_supplied_command\":%s", plan_recovery_action_executes_operator_supplied_command(action) ? "true" : "false");
    fputs(",\"command_queue_enabled\":false", stdout);
    fputs(",\"hidden_control_channel\":false", stdout);
    fputs(",\"self_reinstall\":false", stdout);
    fputs(",\"survives_factory_reset_claim\":false", stdout);
    fputs(",\"requires_explicit_apply\":true", stdout);
    fputs(",\"requires_external_write\":true", stdout);
    fputs("}", stdout);
}

static int plan_recovery_install(int argc, char **argv, int json)
{
    const char *root = "/";
    const char *method = NULL;
    const char *action = "status-only";
    const char *name = BB_RECOVERY_BINARY_NAME;
    const char *script_file = NULL;
    const char *command = NULL;
    int external = 0;
    int i;
    const struct plan_recovery_method *m;
    char hook[PATH_MAX], bin[PATH_MAX], script_dst[PATH_MAX], generated[PATH_MAX * 2];
    char command_buf[PATH_MAX * 2];

    command_buf[0] = '\0';
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "install")) {
            i++;
            break;
        }
    }
    for (; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--external"))
            external = 1;
        else if (!strcmp(argv[i], "--root") && i + 1 < argc)
            root = argv[++i];
        else if (!strcmp(argv[i], "--method") && i + 1 < argc)
            method = argv[++i];
        else if (!strcmp(argv[i], "--action") && i + 1 < argc)
            action = argv[++i];
        else if (!strcmp(argv[i], "--name") && i + 1 < argc)
            name = argv[++i];
        else if (!strcmp(argv[i], "--file") && i + 1 < argc)
            script_file = argv[++i];
        else if (!strcmp(argv[i], "--")) {
            int j;
            command_buf[0] = '\0';
            for (j = i + 1; j < argc; j++) {
                if (command_buf[0])
                    strncat(command_buf, " ", sizeof(command_buf) - strlen(command_buf) - 1);
                strncat(command_buf, argv[j], sizeof(command_buf) - strlen(command_buf) - 1);
            }
            command = command_buf;
            break;
        } else {
            fprintf(stderr, "plan: unknown or incomplete recovery option %s\n", argv[i]);
            return 2;
        }
    }
    if (!method) {
        fputs("plan: recovery install requires --method\n", stderr);
        return 2;
    }
    m = find_plan_recovery_method(method);
    if (!m) {
        fprintf(stderr, "plan: unsupported recovery method %s\n", method);
        return 2;
    }
    if (strcmp(action, "rshell") && strcmp(action, "command") && strcmp(action, "script") &&
        strcmp(action, "status-only") && strcmp(action, "evidence-push") &&
        strcmp(action, "evidence-then-rshell") && strcmp(action, "dmesg-push")) {
        fprintf(stderr, "plan: unsupported recovery action %s\n", action);
        return 2;
    }
    if (!strcmp(action, "command") && (!command || !*command)) {
        fputs("plan: recovery action command requires -- COMMAND\n", stderr);
        return 2;
    }
    if (!strcmp(action, "script") && (!script_file || !*script_file)) {
        fputs("plan: recovery action script requires --file FILE\n", stderr);
        return 2;
    }
    plan_recovery_join(hook, sizeof(hook), root, m->path);
    plan_recovery_bin_path(bin, sizeof(bin), root, name);
    script_dst[0] = '\0';
    if (!strcmp(action, "script")) {
        char rel[PATH_MAX];
        snprintf(rel, sizeof(rel), "usr/bin/%s.recovery.sh", name);
        plan_recovery_join(script_dst, sizeof(script_dst), root, rel);
    }
    if (!strcmp(action, "rshell"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s rshell start", name);
    else if (!strcmp(action, "evidence-push"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s evidence push --quiet", name);
    else if (!strcmp(action, "evidence-then-rshell"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s evidence push --quiet && /usr/bin/%s rshell start", name, name);
    else if (!strcmp(action, "dmesg-push"))
        snprintf(generated, sizeof(generated), "bbx_dmesg_dir=%s/run; mkdir -p \"$bbx_dmesg_dir\" 2>/dev/null || bbx_dmesg_dir=.; bbx_dmesg=\"$bbx_dmesg_dir/%s-dmesg.txt\"; dmesg >\"$bbx_dmesg\" 2>&1; /usr/bin/%s evidence push \"$bbx_dmesg\" --dest %s-dmesg.txt --quiet; rm -f \"$bbx_dmesg\"", BB_RUNTIME_ROOT, name, name, name);
    else if (!strcmp(action, "command"))
        snprintf(generated, sizeof(generated), "%s", command);
    else if (!strcmp(action, "script"))
        snprintf(generated, sizeof(generated), "/usr/bin/%s.recovery.sh", name);
    else
        snprintf(generated, sizeof(generated), "/usr/bin/%s persistence status", name);

    if (json) {
        fputs("{\"schema\":1,\"command\":\"recovery install\",\"would_create\":[", stdout);
        bb_json_string(stdout, bin);
        if (script_dst[0]) {
            fputc(',', stdout);
            bb_json_string(stdout, script_dst);
        }
        fputs("],\"would_modify\":[", stdout);
        bb_json_string(stdout, hook);
        fputs("],\"would_remove\":[],\"would_start\":[", stdout);
        bb_json_string(stdout, generated);
        fputs("],\"would_connect\":[", stdout);
        if (!strcmp(action, "rshell") || !strcmp(action, "evidence-push") ||
            !strcmp(action, "evidence-then-rshell") || !strcmp(action, "dmesg-push"))
            bb_json_string(stdout, BB_OPERATOR_SERVER_HOST);
        fputs("],\"requires_external_writes\":", stdout);
        printf("%s", !strcmp(root, "/") ? "true" : "false");
        fputs(",\"root\":", stdout); bb_json_string(stdout, root);
        fputs(",\"method\":", stdout); bb_json_string(stdout, m->name);
        fputs(",\"action\":", stdout); bb_json_string(stdout, action);
        fputs(",\"action_category\":", stdout); bb_json_string(stdout, plan_recovery_action_category(action));
        printf(",\"uploads_evidence\":%s", plan_recovery_action_uploads_evidence(action) ? "true" : "false");
        printf(",\"collects_dmesg\":%s", plan_recovery_action_collects_dmesg(action) ? "true" : "false");
        printf(",\"starts_rshell\":%s", plan_recovery_action_starts_rshell(action) ? "true" : "false");
        printf(",\"starts_rshell_after_evidence\":%s", plan_recovery_action_starts_rshell_after_evidence(action) ? "true" : "false");
        printf(",\"executes_operator_supplied_command\":%s", plan_recovery_action_executes_operator_supplied_command(action) ? "true" : "false");
        fputs(",\"command_queue_enabled\":false", stdout);
        fputs(",\"hidden_control_channel\":false", stdout);
        fputs(",\"self_reinstall\":false", stdout);
        fputs(",\"survives_factory_reset_claim\":false", stdout);
        fputc(',', stdout);
        plan_recovery_print_action_semantics_json(action);
        fputs(",\"hook_path\":", stdout); bb_json_string(stdout, hook);
        fputs(",\"binary_path\":", stdout); bb_json_string(stdout, bin);
        if (script_dst[0]) {
            fputs(",\"script_source_path\":", stdout); bb_json_string(stdout, script_file);
            fputs(",\"script_dest_path\":", stdout); bb_json_string(stdout, script_dst);
        }
        fputs(",\"generated_command\":", stdout); bb_json_string(stdout, generated);
        printf(",\"external_flag_supplied\":%s", external ? "true" : "false");
        plan_print_config_source_json();
        puts("}");
        return 0;
    }

    puts("Plan: recovery install");
    plan_print_config_source_text();
    printf("root=%s\n", root);
    printf("method=%s\n", m->name);
    printf("action=%s\n", action);
    printf("action_category=%s\n", plan_recovery_action_category(action));
    printf("uploads_evidence=%s\n", plan_recovery_action_uploads_evidence(action) ? "yes" : "no");
    printf("collects_dmesg=%s\n", plan_recovery_action_collects_dmesg(action) ? "yes" : "no");
    printf("starts_rshell=%s\n", plan_recovery_action_starts_rshell(action) ? "yes" : "no");
    printf("starts_rshell_after_evidence=%s\n", plan_recovery_action_starts_rshell_after_evidence(action) ? "yes" : "no");
    printf("executes_operator_supplied_command=%s\n", plan_recovery_action_executes_operator_supplied_command(action) ? "yes" : "no");
    puts("command_queue_enabled=no");
    puts("hidden_control_channel=no");
    printf("hook_path=%s\n", hook);
    printf("binary_path=%s\n", bin);
    if (script_dst[0]) {
        printf("script_source_path=%s\n", script_file);
        printf("script_dest_path=%s\n", script_dst);
    }
    printf("generated_command=%s\n", generated);
    printf("requires_external_writes=%s\n", !strcmp(root, "/") ? "yes" : "no");
    printf("external_flag_supplied=%s\n", external ? "yes" : "no");
    puts("would_create:");
    printf("  %s\n", bin);
    if (script_dst[0])
        printf("  %s\n", script_dst);
    puts("would_modify:");
    printf("  %s\n", hook);
    puts("would_start:");
    printf("  %s\n", generated);
    puts("recovery_method_implications=install still requires explicit --apply; real-root writes require --external --apply");
    return 0;
}

int applet_plan_main(int argc, char **argv)
{
    int json = 0;
    const char *topic = NULL;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox plan [--json] [extract|rshell|clean|command-queue]");
        puts("       busierbox plan [--json] recovery install --method METHOD --action ACTION [options]");
        puts("Shows intended filesystem, process, and network impact without modifying the target.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!topic)
            topic = argv[i];
        else
            break;
    }
    if (!topic)
        topic = "summary";

    if (!strcmp(topic, "extract")) {
        plan_print_extract(json);
        return 0;
    }
    if (!strcmp(topic, "clean")) {
        plan_print_clean(json);
        return 0;
    }
    if (!strcmp(topic, "rshell")) {
        plan_print_rshell(json);
        return 0;
    }
    if (!strcmp(topic, "command-queue")) {
        plan_print_command_queue(json);
        return 0;
    }
    if (!strcmp(topic, "recovery") || !strcmp(topic, "persistence")) {
        if (i < argc && !strcmp(argv[i], "install"))
            return plan_recovery_install(argc, argv, json);
        fprintf(stderr, "plan: recovery supports: install --method METHOD --action ACTION\n");
        return 2;
    }
    if (!strcmp(topic, "summary")) {
        if (json) {
            fputs("{\"schema\":1,\"command\":\"summary\",\"available_plans\":[\"extract\",\"rshell\",\"clean\",\"command-queue\",\"recovery install\"]", stdout);
            plan_print_config_source_json();
            puts("}");
        } else {
            puts("Available plans:");
            puts("  busierbox plan extract");
            puts("  busierbox plan rshell");
            puts("  busierbox plan clean");
            puts("  busierbox plan command-queue");
            puts("  busierbox plan recovery install --method openwrt-procd --action rshell");
            plan_print_config_source_text();
        }
        return 0;
    }
    fprintf(stderr, "plan: unknown topic %s\n", topic);
    return 2;
}
