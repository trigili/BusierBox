#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "applets.h"
#include "command_queue_policy.h"
#include "json_helpers.h"
#include "runtime_config.h"

#define json_string_payload bb_json_string

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

static int rshell_session_policy_valid(const char *policy)
{
    return !strcmp(policy, "single") ||
           !strcmp(policy, "reconnect") ||
           !strcmp(policy, "persistent");
}

static int rshell_session_policy_reconnects(const char *policy)
{
    return !strcmp(policy, "reconnect") || !strcmp(policy, "persistent");
}

static const char *rshell_post_disconnect_retry_count(const char *policy)
{
    if (!strcmp(policy, "single"))
        return "0";
    if (!strcmp(policy, "persistent"))
        return "-1";
    return BB_RSHELL_RETRY_COUNT;
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

static void print_command_queue_mode_record(FILE *out, const char *mode)
{
    int polls = command_queue_mode_polls(mode);

    fprintf(out, "{\"mode\":");
    json_string_payload(out, mode);
    fprintf(out, ",\"requires_operator_host\":%s", polls ? "true" : "false");
    fprintf(out, ",\"would_poll_if_configured\":%s", polls ? "true" : "false");
    fprintf(out, ",\"target_polling_supported\":%s", polls ? "true" : "false");
    fprintf(out, ",\"requires_explicit_target_action\":true");
    fprintf(out, ",\"delivery_supported\":false");
    fprintf(out, ",\"result_upload_supported\":true");
    fprintf(out, ",\"execution_supported\":false");
    fprintf(out, ",\"executes_commands\":false");
    fprintf(out, ",\"operator_supplied_command_execution\":false");
    fprintf(out, ",\"active_control_channel\":false");
    fprintf(out, ",\"lifecycle\":");
    json_string_payload(out, command_queue_mode_lifecycle(mode));
    fprintf(out, "}");
}

static void print_command_queue_mode_records(FILE *out)
{
    fprintf(out, ",\"mode_records\":[");
    print_command_queue_mode_record(out, "status");
    fprintf(out, ",");
    print_command_queue_mode_record(out, "poll");
    fprintf(out, ",");
    print_command_queue_mode_record(out, "once");
    fprintf(out, ",");
    print_command_queue_mode_record(out, "daemon");
    fprintf(out, ",");
    print_command_queue_mode_record(out, "stop");
    fprintf(out, "]");
}

static void print_command_queue_mode_index_array(FILE *out, const char *field, const char *value)
{
    static const char *modes[] = {"status", "poll", "once", "daemon", "stop"};
    size_t i;
    int first = 1;

    fprintf(out, "[");
    for (i = 0; i < sizeof(modes) / sizeof(modes[0]); i++) {
        const char *mode = modes[i];
        int polls = command_queue_mode_polls(mode);
        const char *candidate = "";
        if (!strcmp(field, "mode"))
            candidate = mode;
        else if (!strcmp(field, "lifecycle"))
            candidate = command_queue_mode_lifecycle(mode);
        else if (!strcmp(field, "would_poll_if_configured"))
            candidate = polls ? "true" : "false";
        else if (!strcmp(field, "target_polling_supported"))
            candidate = polls ? "true" : "false";
        else if (!strcmp(field, "execution_supported"))
            candidate = "false";
        else if (!strcmp(field, "active_control_channel"))
            candidate = "false";
        else if (!strcmp(field, "operator_supplied_command_execution"))
            candidate = "false";
        if (strcmp(candidate, value))
            continue;
        fprintf(out, "%s%zu", first ? "" : ",", i);
        first = 0;
    }
    fprintf(out, "]");
}

static void print_command_queue_mode_indexes(FILE *out)
{
    static const char *modes[] = {"status", "poll", "once", "daemon", "stop"};
    static const char *lifecycles[] = {"inspect", "single-poll", "single-cycle", "long-running", "stop"};
    static const char *bools[] = {"true", "false"};
    size_t i;

    fprintf(out, ",\"mode_records_by_mode\":{");
    for (i = 0; i < sizeof(modes) / sizeof(modes[0]); i++) {
        if (i)
            fprintf(out, ",");
        json_string_payload(out, modes[i]);
        fprintf(out, ":");
        print_command_queue_mode_index_array(out, "mode", modes[i]);
    }
    fprintf(out, "},\"mode_records_by_lifecycle\":{");
    for (i = 0; i < sizeof(lifecycles) / sizeof(lifecycles[0]); i++) {
        if (i)
            fprintf(out, ",");
        json_string_payload(out, lifecycles[i]);
        fprintf(out, ":");
        print_command_queue_mode_index_array(out, "lifecycle", lifecycles[i]);
    }
    fprintf(out, "},\"mode_records_by_would_poll_if_configured\":{");
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fprintf(out, ",");
        json_string_payload(out, bools[i]);
        fprintf(out, ":");
        print_command_queue_mode_index_array(out, "would_poll_if_configured", bools[i]);
    }
    fprintf(out, "},\"mode_records_by_target_polling_supported\":{");
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fprintf(out, ",");
        json_string_payload(out, bools[i]);
        fprintf(out, ":");
        print_command_queue_mode_index_array(out, "target_polling_supported", bools[i]);
    }
    fprintf(out, "},\"mode_records_by_execution_supported\":{");
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fprintf(out, ",");
        json_string_payload(out, bools[i]);
        fprintf(out, ":");
        print_command_queue_mode_index_array(out, "execution_supported", bools[i]);
    }
    fprintf(out, "},\"mode_records_by_active_control_channel\":{");
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fprintf(out, ",");
        json_string_payload(out, bools[i]);
        fprintf(out, ":");
        print_command_queue_mode_index_array(out, "active_control_channel", bools[i]);
    }
    fprintf(out, "},\"mode_records_by_operator_supplied_command_execution\":{");
    for (i = 0; i < sizeof(bools) / sizeof(bools[0]); i++) {
        if (i)
            fprintf(out, ",");
        json_string_payload(out, bools[i]);
        fprintf(out, ":");
        print_command_queue_mode_index_array(out, "operator_supplied_command_execution", bools[i]);
    }
    fprintf(out, "}");
}

static void print_command_queue_mode_summary(FILE *out)
{
    fprintf(out, ",\"mode_summary\":{\"mode_count\":5,\"polling_mode_count\":3,\"operator_host_required_mode_count\":3");
    fprintf(out, ",\"target_polling_supported_mode_count\":3,\"result_upload_supported_mode_count\":5");
    fprintf(out, ",\"execution_supported_mode_count\":0,\"active_control_channel_mode_count\":0,\"operator_supplied_command_execution_mode_count\":0}");
}

static void print_command_queue_mode_api_collections(FILE *out)
{
    fprintf(out, ",\"api_collections\":{\"mode_records\":{\"name\":\"mode_records\",\"count\":5");
    fprintf(out, ",\"count_summary_key\":\"mode_summary.mode_count\",\"primary_key\":\"mode\",\"summary_key\":\"mode_summary.mode_count\"");
    fprintf(out, ",\"indexes\":[\"mode_records_by_mode\",\"mode_records_by_lifecycle\",\"mode_records_by_would_poll_if_configured\",\"mode_records_by_target_polling_supported\",\"mode_records_by_execution_supported\",\"mode_records_by_active_control_channel\",\"mode_records_by_operator_supplied_command_execution\"]}}");
}

#ifndef BUSIERBOX_PAYLOAD_VERSION
#define BUSIERBOX_PAYLOAD_VERSION "dev"
#endif
#ifndef BUSIERBOX_ARTIFACT_TIER
#define BUSIERBOX_ARTIFACT_TIER "core"
#endif
#ifndef BUSIERBOX_BUILD_TIMESTAMP
#define BUSIERBOX_BUILD_TIMESTAMP "unknown"
#endif
#ifndef BUSIERBOX_GIT_COMMIT
#define BUSIERBOX_GIT_COMMIT "unknown"
#endif
#ifndef BB_TARGET_PRESET
#define BB_TARGET_PRESET "native"
#endif
#ifndef BB_TARGET_NAME
#define BB_TARGET_NAME "native"
#endif
#ifndef BB_TARGET_ARCH
#define BB_TARGET_ARCH "native"
#endif
#ifndef BB_TARGET_ENDIAN
#define BB_TARGET_ENDIAN "auto"
#endif
#ifndef BB_TARGET_CPU
#define BB_TARGET_CPU "host"
#endif
#ifndef BB_TARGET_ABI
#define BB_TARGET_ABI "default"
#endif
#ifndef BB_TARGET_LIBC
#define BB_TARGET_LIBC "host"
#endif
#ifndef BB_KERNEL_FLOOR
#define BB_KERNEL_FLOOR "host"
#endif
#ifndef BB_STATIC_POLICY
#define BB_STATIC_POLICY "static-preferred"
#endif
#ifndef BB_PAYLOAD_PRESET
#define BB_PAYLOAD_PRESET "default"
#endif
#ifndef BB_DOTFILES_ENABLE
#define BB_DOTFILES_ENABLE "yes"
#endif
#ifndef BB_DOTFILE_ZSH_MODE
#define BB_DOTFILE_ZSH_MODE "default"
#endif
#ifndef BB_DOTFILE_BASH_MODE
#define BB_DOTFILE_BASH_MODE "default"
#endif
#ifndef BB_DOTFILE_TMUX_MODE
#define BB_DOTFILE_TMUX_MODE "default"
#endif
#ifndef BB_DOTFILE_GDB_MODE
#define BB_DOTFILE_GDB_MODE "default"
#endif
#ifndef BB_DOTFILE_PROFILE_MODE
#define BB_DOTFILE_PROFILE_MODE "default"
#endif
#ifndef BB_USER_OVERLAY_ENABLE
#define BB_USER_OVERLAY_ENABLE "no"
#endif
#ifndef BB_USER_OVERLAY_ROOT
#define BB_USER_OVERLAY_ROOT "./overlay"
#endif
#ifndef BB_USER_OVERLAY_ALLOW_OVERRIDE
#define BB_USER_OVERLAY_ALLOW_OVERRIDE "no"
#endif
#ifndef BB_GDBSERVER_PROVIDER
#define BB_GDBSERVER_PROVIDER "auto"
#endif
#ifndef BB_FULL_ZERO_ARG_MODE
#define BB_FULL_ZERO_ARG_MODE "help"
#endif
#ifndef BB_ZERO_ARG_MODE
#define BB_ZERO_ARG_MODE BB_FULL_ZERO_ARG_MODE
#endif
#ifndef BB_ENABLE_SURVEY
#define BB_ENABLE_SURVEY 1
#endif
#ifndef BB_ENABLE_DOCTOR
#define BB_ENABLE_DOCTOR 1
#endif
#ifndef BB_ENABLE_EXTRACT
#define BB_ENABLE_EXTRACT 1
#endif
#ifndef BB_ENABLE_CONFIG_INFO
#define BB_ENABLE_CONFIG_INFO 1
#endif
#include "effective_config.h"

static void manifest_print_noresidue_policy(FILE *out)
{
    int active = !strcmp(BB_RUNTIME_MODE, "no-residue");
    int aggressive = !strcmp(BB_NORESIDUE_LEVEL, "aggressive");

    fprintf(out, "{\"active\":%s,\"level\":", active ? "true" : "false");
    json_string_payload(out, BB_NORESIDUE_LEVEL);
    fprintf(out, ",\"cleanup_scope\":\"BusierBox-owned runtime roots and ledgered files only\"");
    fprintf(out, ",\"best_effort\":true");
    fprintf(out, ",\"aggressive_minimizes_runtime_residue\":%s", aggressive ? "true" : "false");
    fprintf(out, ",\"persistent_target_logs_default\":");
    json_string_payload(out, aggressive ? "no" : "configured");
    fprintf(out, ",\"stdout_stderr_log_suppression\":");
    json_string_payload(out, aggressive ? "BB_ZERO_ARG_LOG_MODE=none" : "available via BB_ZERO_ARG_LOG_MODE=none");
    fprintf(out, ",\"in_memory_log_guarantee\":false");
    fprintf(out, ",\"forensic_no_trace\":false");
    fprintf(out, ",\"external_writes_require_explicit_apply\":true");
    fprintf(out, ",\"guarantee\":");
    json_string_payload(out, aggressive ?
        "aggressive minimizes BusierBox runtime residue but cannot guarantee absence of residue" :
        "best-effort cleanup removes owned runtime state where reasonable");
    fprintf(out, "}");
}

static const char *busybox_tools[] = {
#include "bbx_busybox_applets.h"
    NULL
};

static const char *heavy_tools[] = {
#include "bbx_heavy_tools.h"
    NULL
};

static int manifest_is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

typedef int (*manifest_capture_writer)(FILE *out, void *ctx);

static FILE *manifest_temp_stream(void)
{
    const char *roots[] = { BB_RUNTIME_ROOT, ".", "/tmp", NULL };
    char path[PATH_MAX];
    int i;

    for (i = 0; roots[i]; i++) {
        int fd;

        if (!roots[i][0])
            continue;
        if (strcmp(roots[i], ".") && bb_mkdir_p(roots[i], 0700) != 0)
            continue;
        snprintf(path, sizeof(path), "%s/.busierbox-capture.%ld.XXXXXX", roots[i], (long)getpid());
        fd = mkstemp(path);
        if (fd < 0)
            continue;
        unlink(path);
        {
            FILE *fp = fdopen(fd, "w+");
            if (fp)
                return fp;
        }
        close(fd);
    }
    return NULL;
}

static char *read_temp_stream(FILE *fp, size_t *len_out)
{
    long end;
    size_t len;
    char *buf;

    if (fflush(fp) != 0 || fseek(fp, 0, SEEK_END) != 0)
        return NULL;
    end = ftell(fp);
    if (end < 0 || fseek(fp, 0, SEEK_SET) != 0)
        return NULL;
    len = (size_t)end;
    buf = malloc(len + 1);
    if (!buf)
        return NULL;
    if (len && fread(buf, 1, len, fp) != len) {
        free(buf);
        return NULL;
    }
    buf[len] = '\0';
    if (len_out)
        *len_out = len;
    return buf;
}

static char *capture_json_alloc(manifest_capture_writer writer, void *ctx, size_t *len_out)
{
    char *buf = NULL;
    size_t len = 0;
    FILE *fp;

#ifndef BUSIERBOX_NO_OPEN_MEMSTREAM
    fp = open_memstream(&buf, &len);
    if (!fp)
        return NULL;
    if (writer(fp, ctx) != 0) {
        fclose(fp);
        free(buf);
        return NULL;
    }
    if (fclose(fp) != 0) {
        free(buf);
        return NULL;
    }
#else
    fp = manifest_temp_stream();
    if (!fp)
        return NULL;
    if (writer(fp, ctx) != 0) {
        fclose(fp);
        return NULL;
    }
    buf = read_temp_stream(fp, &len);
    if (fclose(fp) != 0) {
        free(buf);
        return NULL;
    }
    if (!buf)
        return NULL;
#endif
    if (len && buf[len - 1] == '\n')
        buf[--len] = '\0';
    if (len_out)
        *len_out = len;
    return buf;
}

static void write_manifest_json(FILE *out, int include_missing)
{
    struct command_queue_policy_report command_queue_policy = bb_command_queue_validate_policy();
    int command_queue_policy_valid = bb_command_queue_policy_valid(&command_queue_policy);
    int command_queue_arbitrary_requested = command_queue_policy_valid &&
        !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") &&
        !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "custom") &&
        !strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "yes");
    int i;

    fprintf(out, "{\"schema\":1,\"busierbox\":{\"payload_version\":");
    json_string_payload(out, BUSIERBOX_PAYLOAD_VERSION);
    fprintf(out, ",\"artifact_tier\":");
    json_string_payload(out, BUSIERBOX_ARTIFACT_TIER);
    fprintf(out, ",\"build_timestamp\":");
    json_string_payload(out, BUSIERBOX_BUILD_TIMESTAMP);
    fprintf(out, ",\"git_commit\":");
    json_string_payload(out, BUSIERBOX_GIT_COMMIT);
    fprintf(out, "},\"target\":{\"preset\":");
    json_string_payload(out, BB_TARGET_PRESET);
    fprintf(out, ",\"name\":");
    json_string_payload(out, BB_TARGET_NAME);
    fprintf(out, ",\"arch\":");
    json_string_payload(out, BB_TARGET_ARCH);
    fprintf(out, ",\"endian\":");
    json_string_payload(out, BB_TARGET_ENDIAN);
    fprintf(out, ",\"cpu\":");
    json_string_payload(out, BB_TARGET_CPU);
    fprintf(out, ",\"abi\":");
    json_string_payload(out, BB_TARGET_ABI);
    fprintf(out, ",\"libc\":");
    json_string_payload(out, BB_TARGET_LIBC);
    fprintf(out, ",\"kernel_floor\":");
    json_string_payload(out, BB_KERNEL_FLOOR);
    fprintf(out, ",\"static_policy\":");
    json_string_payload(out, BB_STATIC_POLICY);
    fprintf(out, "},\"payload\":{\"preset\":");
    json_string_payload(out, BB_PAYLOAD_PRESET);
    fprintf(out, ",\"gdbserver_provider\":");
    json_string_payload(out, BB_GDBSERVER_PROVIDER);
    fprintf(out, "},\"runtime\":{\"mode\":");
    json_string_payload(out, BB_RUNTIME_MODE);
    fprintf(out, ",\"noresidue_level\":");
    json_string_payload(out, BB_NORESIDUE_LEVEL);
    fprintf(out, ",\"noresidue_policy\":");
    manifest_print_noresidue_policy(out);
    fprintf(out, ",\"root\":");
    json_string_payload(out, BB_RUNTIME_ROOT);
    fprintf(out, ",\"allow_fallback_root\":");
    json_string_payload(out, BB_RUNTIME_ALLOW_FALLBACK_ROOT);
    fprintf(out, ",\"fallback_root\":");
    json_string_payload(out, BB_RUNTIME_FALLBACK_ROOT);
    fprintf(out, "},\"zero_arg\":{\"mode\":");
    json_string_payload(out, BB_ZERO_ARG_MODE);
    fprintf(out, ",\"log_mode\":");
    json_string_payload(out, BB_ZERO_ARG_LOG_MODE);
    fprintf(out, "},\"rshell\":{\"transport\":");
    json_string_payload(out, BB_RSHELL_TRANSPORT);
    fprintf(out, ",\"encryption\":");
    json_string_payload(out, BB_RSHELL_ENCRYPTION);
    fprintf(out, ",\"run_mode\":");
    json_string_payload(out, BB_RSHELL_RUN_MODE);
    fprintf(out, ",\"session_policy\":");
    json_string_payload(out, BB_RSHELL_SESSION_POLICY);
    fprintf(out, ",\"session_policy_valid\":%s", rshell_session_policy_valid(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
    fprintf(out, ",\"session_policy_errors\":[");
    if (!rshell_session_policy_valid(BB_RSHELL_SESSION_POLICY))
        json_string_payload(out, "unsupported rshell session policy");
    fprintf(out, "]");
    fprintf(out, ",\"session_semantics\":{\"retry_until_first_connection\":true");
    fprintf(out, ",\"stop_after_first_success\":%s", !strcmp(BB_RSHELL_SESSION_POLICY, "single") ? "true" : "false");
    fprintf(out, ",\"reconnect_after_disconnect\":%s", rshell_session_policy_reconnects(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
    fprintf(out, ",\"persistent_lifecycle\":%s", !strcmp(BB_RSHELL_SESSION_POLICY, "persistent") ? "true" : "false");
    fprintf(out, ",\"fresh_session_on_reconnect\":%s", rshell_session_policy_reconnects(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
    fprintf(out, ",\"session_resume_supported\":false}");
    fprintf(out, ",\"session_policy_summary\":{\"valid\":%s", rshell_session_policy_valid(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
    fprintf(out, ",\"errors\":[");
    if (!rshell_session_policy_valid(BB_RSHELL_SESSION_POLICY))
        json_string_payload(out, "unsupported rshell session policy");
    fprintf(out, "]");
    fprintf(out, ",\"retry_scope\":\"pre-connect");
    if (rshell_session_policy_reconnects(BB_RSHELL_SESSION_POLICY))
        fprintf(out, "+post-disconnect");
    fprintf(out, "\",\"pre_connect_retry_count\":");
    json_string_payload(out, BB_RSHELL_RETRY_COUNT);
    fprintf(out, ",\"post_disconnect_retry_count\":");
    json_string_payload(out, rshell_post_disconnect_retry_count(BB_RSHELL_SESSION_POLICY));
    fprintf(out, ",\"stops_after_success\":%s", !strcmp(BB_RSHELL_SESSION_POLICY, "single") ? "true" : "false");
    fprintf(out, ",\"reconnects_after_disconnect\":%s", rshell_session_policy_reconnects(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
    fprintf(out, ",\"persistent_lifecycle\":%s", !strcmp(BB_RSHELL_SESSION_POLICY, "persistent") ? "true" : "false");
    fprintf(out, ",\"fresh_session_on_reconnect\":%s", rshell_session_policy_reconnects(BB_RSHELL_SESSION_POLICY) ? "true" : "false");
    fprintf(out, ",\"session_resume_supported\":false}");
    fprintf(out, ",\"shell_provider\":");
    json_string_payload(out, BB_RSHELL_SHELL_PROVIDER);
    fprintf(out, ",\"operator_host\":");
    json_string_payload(out, BB_OPERATOR_SERVER_HOST);
    fprintf(out, ",\"operator_shell_port\":");
    json_string_payload(out, BB_RSHELL_SOCAT_PORT);
    fprintf(out, ",\"operator_ssh_port\":");
    json_string_payload(out, BB_OPERATOR_SERVER_SSH_PORT);
    fprintf(out, ",\"remote_forward_port\":");
    json_string_payload(out, BB_OPERATOR_REMOTE_FORWARD_PORT);
    {
        char target_dropbear[256];
        snprintf(target_dropbear, sizeof(target_dropbear), "%s:%s", BB_OPERATOR_TARGET_BIND_HOST, BB_OPERATOR_TARGET_DROPBEAR_PORT);
        fprintf(out, ",\"target_dropbear\":");
        json_string_payload(out, target_dropbear);
    }
    fprintf(out, ",\"authkeys_mode\":");
    json_string_payload(out, BB_RSHELL_AUTHKEYS_MODE);
    fprintf(out, ",\"retry\":{\"count\":");
    json_string_payload(out, BB_RSHELL_RETRY_COUNT);
    fprintf(out, ",\"interval_sec\":");
    json_string_payload(out, BB_RSHELL_RETRY_INTERVAL_SEC);
    fprintf(out, ",\"jitter_pct\":");
    json_string_payload(out, BB_RSHELL_RETRY_JITTER_PCT);
    fprintf(out, ",\"backoff\":");
    json_string_payload(out, BB_RSHELL_RETRY_BACKOFF);
    fprintf(out, ",\"max_interval_sec\":");
    json_string_payload(out, BB_RSHELL_RETRY_MAX_INTERVAL_SEC);
    fprintf(out, ",\"pre_connect_count\":");
    json_string_payload(out, BB_RSHELL_RETRY_COUNT);
    fprintf(out, ",\"post_disconnect_count\":");
    json_string_payload(out, rshell_post_disconnect_retry_count(BB_RSHELL_SESSION_POLICY));
    fprintf(out, "}");
    fprintf(out, "},\"operator_services\":{\"file_service\":{\"enabled\":");
    json_string_payload(out, BB_OPERATOR_FILE_SERVICE_ENABLE);
    fprintf(out, ",\"port\":");
    json_string_payload(out, BB_OPERATOR_FILE_SERVICE_PORT);
    fprintf(out, ",\"tls\":");
    json_string_payload(out, BB_OPERATOR_FILE_SERVICE_TLS);
    fprintf(out, ",\"target_initiated\":true,\"receive_only\":true}");
    fprintf(out, ",\"command_queue\":{\"enabled\":");
    json_string_payload(out, BB_COMMAND_QUEUE_ENABLE);
    fprintf(out, ",\"port\":");
    json_string_payload(out, BB_COMMAND_QUEUE_PORT);
    fprintf(out, ",\"tls\":");
    json_string_payload(out, BB_COMMAND_QUEUE_TLS);
    fprintf(out, ",\"require_token\":");
    json_string_payload(out, BB_COMMAND_QUEUE_REQUIRE_TOKEN);
    fprintf(out, ",\"token_source\":");
    json_string_payload(out, BB_COMMAND_QUEUE_TOKEN_SOURCE);
    fprintf(out, ",\"token_required\":%s,\"token_configured\":%s",
            !strcmp(BB_COMMAND_QUEUE_REQUIRE_TOKEN, "yes") ? "true" : "false",
            BB_COMMAND_QUEUE_TOKEN[0] ? "true" : "false");
    fprintf(out, ",\"allowed_commands\":");
    json_string_payload(out, BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    fprintf(out, ",\"allow_arbitrary\":");
    json_string_payload(out, BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    fprintf(out, ",\"execution_mode\":");
    json_string_payload(out, BB_COMMAND_QUEUE_EXECUTION);
    fprintf(out, ",\"metadata_only_default\":%s", !strcmp(BB_COMMAND_QUEUE_EXECUTION, "metadata-only") ? "true" : "false");
    fprintf(out, ",\"poll_interval_sec\":");
    json_string_payload(out, BB_COMMAND_QUEUE_POLL_INTERVAL_SEC);
    fprintf(out, ",\"poll_jitter_pct\":");
    json_string_payload(out, BB_COMMAND_QUEUE_POLL_JITTER_PCT);
    fprintf(out, ",\"poll_backoff\":");
    json_string_payload(out, BB_COMMAND_QUEUE_POLL_BACKOFF);
    fprintf(out, ",\"poll_max_interval_sec\":");
    json_string_payload(out, BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC);
    fprintf(out, ",\"max_polls\":");
    json_string_payload(out, BB_COMMAND_QUEUE_MAX_POLLS);
    fprintf(out, ",\"daemon_state_file\":");
    {
        char state_file[512];
        snprintf(state_file, sizeof(state_file), "%s/run/command-queue-daemon.state", BB_RUNTIME_ROOT);
        json_string_payload(out, state_file);
    }
    fprintf(out, ",\"daemon_state_file_supported\":true,\"daemon_status_supported\":true,\"daemon_stop_supported\":true");
    fprintf(out, ",\"policy_valid\":%s", command_queue_policy_valid ? "true" : "false");
    fprintf(out, ",\"policy_errors\":[");
    for (i = 0; i < command_queue_policy.count; i++) {
        if (i)
            fputc(',', out);
        json_string_payload(out, command_queue_policy.errors[i]);
    }
    fprintf(out, "],\"arbitrary_policy_requested\":%s,\"arbitrary_execution_allowed\":false,\"target_polling\":true,\"poll_transport_supported\":true,\"live_polling_supported\":true,\"delivery_supported\":false,\"result_upload_supported\":true,\"execution_supported\":false,\"executes_commands\":false,\"default_enabled\":false",
            command_queue_arbitrary_requested ? "true" : "false");
    print_command_queue_mode_records(out);
    print_command_queue_mode_indexes(out);
    print_command_queue_mode_summary(out);
    print_command_queue_mode_api_collections(out);
    fprintf(out, "}");
    fprintf(out, "},\"dotfiles\":{\"enabled\":");
    json_string_payload(out, BB_DOTFILES_ENABLE);
    fprintf(out, ",\"zsh\":");
    json_string_payload(out, BB_DOTFILE_ZSH_MODE);
    fprintf(out, ",\"bash\":");
    json_string_payload(out, BB_DOTFILE_BASH_MODE);
    fprintf(out, ",\"tmux\":");
    json_string_payload(out, BB_DOTFILE_TMUX_MODE);
    fprintf(out, ",\"gdb\":");
    json_string_payload(out, BB_DOTFILE_GDB_MODE);
    fprintf(out, ",\"profile\":");
    json_string_payload(out, BB_DOTFILE_PROFILE_MODE);
    fprintf(out, "},\"overlay\":{\"enabled\":");
    json_string_payload(out, BB_USER_OVERLAY_ENABLE);
    fprintf(out, ",\"root\":");
    json_string_payload(out, BB_USER_OVERLAY_ROOT);
    fprintf(out, ",\"allow_override\":");
    json_string_payload(out, BB_USER_OVERLAY_ALLOW_OVERRIDE);
    fprintf(out, "},\"licensing\":{\"project_license\":\"GPL-2.0-or-later\"");
    fprintf(out, ",\"supervisor_license\":\"GPL-2.0-or-later\"");
    fprintf(out, ",\"license_file\":\"LICENSE\",\"notice_file\":\"NOTICE\"");
    fprintf(out, ",\"combined_gplv2_compatible\":true,\"not_busybox_fork\":true");
    fprintf(out, ",\"third_party\":[");
    fprintf(out, "{\"name\":\"BusyBox\",\"license\":\"GPL-2.0\",\"role\":\"payload applets\"}");
    fprintf(out, ",{\"name\":\"Buildroot\",\"license\":\"GPL-2.0-or-later with package exceptions\",\"role\":\"target build system\"}");
    fprintf(out, ",{\"name\":\"doom-ascii\",\"license\":\"GPL-2.0-or-later\",\"role\":\"optional Doom engine; WAD user-provided\"}");
    fprintf(out, ",{\"name\":\"miniz\",\"license\":\"MIT OR Unlicense\",\"role\":\"payload archive helper\"}");
    fprintf(out, "]}");
    fprintf(out, ",\"compiled_config\":");
    bb_config_print_compiled_json(out, json_string_payload);
    fprintf(out, ",\"effective_config\":");
    bb_config_print_effective_json(out, json_string_payload);
    fprintf(out, ",\"config_records\":");
    bb_config_print_records_json(out);
    bb_config_print_record_indexes_json(out);
    fprintf(out, ",\"config_record_summary\":");
    bb_config_print_record_summary_json(out);
    fprintf(out, ",\"api_collections\":{\"config_records\":");
    bb_config_print_record_api_collection_json(out);
    fprintf(out, "}");
    fprintf(out, ",\"trailer_override\":");
    bb_config_print_trailer_json(out, json_string_payload);
    fprintf(out, ",\"native_features\":{\"survey\":%s,\"doctor\":%s,\"extract\":%s,\"config_info\":%s,\"persistence\":true,\"recovery_alias\":true",
#if BB_ENABLE_SURVEY
           "true",
#else
           "false",
#endif
#if BB_ENABLE_DOCTOR
           "true",
#else
           "false",
#endif
#if BB_ENABLE_EXTRACT
           "true",
#else
           "false",
#endif
#if BB_ENABLE_CONFIG_INFO
           "true"
#else
           "false"
#endif
    );
#ifdef HAVE_WOLFSSL
    fprintf(out, ",\"wolfssl\":true");
#else
    fprintf(out, ",\"wolfssl\":false");
#endif
    fprintf(out, "},\"payload_tools\":{\"busybox_applets\":[");
    for (i = 0; busybox_tools[i]; i++) {
        if (i)
            fputc(',', out);
        json_string_payload(out, busybox_tools[i]);
    }
    fprintf(out, "],\"heavy_tools\":[");
    for (i = 0; heavy_tools[i]; i++) {
        if (i)
            fputc(',', out);
        json_string_payload(out, heavy_tools[i]);
    }
    if (include_missing) {
        fprintf(out, "],\"requested_payload_tools\":[");
        for (i = 0; heavy_tools[i]; i++) {
            if (i)
                fputc(',', out);
            json_string_payload(out, heavy_tools[i]);
        }
        fprintf(out, "],\"missing_payload_tools\":[],\"missing_payload_tool_reasons\":{}");
    }
    fprintf(out, include_missing ? "}}\n" : "]}}\n");
}

static int base64_write_bytes(const unsigned char *data, size_t len)
{
    static const char tab[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i;

    for (i = 0; i < len; i += 3) {
        size_t n = len - i;
        unsigned int v;

        if (n > 3)
            n = 3;
        v = ((unsigned int)data[i] << 16) |
            ((unsigned int)(n > 1 ? data[i + 1] : 0) << 8) |
            (unsigned int)(n > 2 ? data[i + 2] : 0);
        putchar(tab[(v >> 18) & 63]);
        putchar(tab[(v >> 12) & 63]);
        putchar(n > 1 ? tab[(v >> 6) & 63] : '=');
        putchar(n > 2 ? tab[v & 63] : '=');
    }
    putchar('\n');
    return ferror(stdout) ? 1 : 0;
}

static int write_manifest_json_capture(FILE *out, void *ctx)
{
    write_manifest_json(out, ctx != NULL);
    return ferror(out) ? -1 : 0;
}

static char *manifest_json_alloc(size_t *len_out)
{
    return capture_json_alloc(write_manifest_json_capture, NULL, len_out);
}

static int print_manifest_base64(void)
{
    size_t len = 0;
    char *json = manifest_json_alloc(&len);
    int rc;

    if (!json) {
        fputs("manifest: cannot allocate manifest buffer\n", stderr);
        return 1;
    }
    rc = base64_write_bytes((const unsigned char *)json, len);
    free(json);
    return rc;
}

static int write_config_export_json(FILE *out)
{
    char *manifest = manifest_json_alloc(NULL);

    if (!manifest)
        return -1;
    fprintf(out, "{\"schema\":1,\"kind\":\"busierbox-config-export\",\"manifest\":%s}\n", manifest);
    free(manifest);
    return ferror(out) ? -1 : 0;
}

static int write_config_export_json_capture(FILE *out, void *ctx)
{
    (void)ctx;
    return write_config_export_json(out);
}

static char *config_export_json_alloc(size_t *len_out)
{
    return capture_json_alloc(write_config_export_json_capture, NULL, len_out);
}

static int print_config_export_base64(void)
{
    size_t len = 0;
    char *json = config_export_json_alloc(&len);
    int rc;

    if (!json) {
        fputs("config-export: cannot allocate export buffer\n", stderr);
        return 1;
    }
    rc = base64_write_bytes((const unsigned char *)json, len);
    free(json);
    return rc;
}

static int write_support_token_json_capture(FILE *out, void *ctx)
{
    const char *manifest = ctx;

    fprintf(out, "{\"schema\":1,\"kind\":\"busierbox-support-token\",");
    fprintf(out, "\"warning\":\"operator host and ports may be embedded; private key material is not included\",");
    fprintf(out, "\"manifest\":%s}", manifest);
    return ferror(out) ? -1 : 0;
}

int bb_print_support_token(void)
{
    char *manifest = manifest_json_alloc(NULL);
    char *token = NULL;
    size_t token_len = 0;
    int rc;

    if (!manifest) {
        fputs("doctor: cannot allocate manifest buffer\n", stderr);
        return 1;
    }
    token = capture_json_alloc(write_support_token_json_capture, manifest, &token_len);
    if (!token) {
        free(manifest);
        fputs("doctor: cannot finalize support token\n", stderr);
        return 1;
    }
    rc = base64_write_bytes((const unsigned char *)token, token_len);
    free(manifest);
    free(token);
    return rc;
}

void bb_write_artifact_manifest_file(const char *root)
{
    char dir[PATH_MAX], path[PATH_MAX], tmp[PATH_MAX];
    FILE *fp;

    snprintf(dir, sizeof(dir), "%s/manifest", root);
    if (bb_mkdir_p(dir, 0700) != 0)
        return;
    snprintf(path, sizeof(path), "%s/artifact.json", dir);
    snprintf(tmp, sizeof(tmp), "%s/artifact.json.tmp.%ld", dir, (long)getpid());
    fp = fopen(tmp, "w");
    if (!fp)
        return;
    write_manifest_json(fp, 0);
    if (fclose(fp) != 0) {
        unlink(tmp);
        return;
    }
    if (rename(tmp, path) != 0) {
        unlink(tmp);
        return;
    }
    bb_ledger_record("write", path, "runtime", "artifact manifest");
}

int applet_manifest_main(int argc, char **argv)
{
    int json = 0, base64 = 0;
    int include_missing = 0;
    int i;

    if (manifest_is_help(argc, argv)) {
        puts("usage: busierbox manifest [--json|--base64] [--include-missing]");
        puts("       busierbox manifest push [--host HOST] [--port PORT] [--tls yes|no]");
        puts("Print artifact and preset metadata embedded in this BusierBox binary.");
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "push")) {
        const char *roots[] = { BB_RUNTIME_ROOT, ".", "/tmp", NULL };
        char path[PATH_MAX];
        int r, rc;
        if (argc > 2 && (!strcmp(argv[2], "--help") || !strcmp(argv[2], "-h"))) {
            puts("usage: busierbox manifest push [--host HOST] [--port PORT] [--tls yes|no]");
            puts("Generate manifest JSON and upload it to the receive-only operator file service.");
            return 0;
        }
        for (r = 0; roots[r]; r++) {
            int fd;
            if (roots[r][0] && strcmp(roots[r], "."))
                bb_mkdir_p(roots[r], 0700);
            snprintf(path, sizeof(path), "%s/.busierbox-manifest.%ld.XXXXXX", roots[r], (long)getpid());
            fd = mkstemp(path);
            if (fd < 0)
                continue;
            {
                FILE *fp = fdopen(fd, "w");
                if (!fp) {
                    close(fd);
                    unlink(path);
                    continue;
                }
                write_manifest_json(fp, include_missing);
                if (fclose(fp) != 0) {
                    unlink(path);
                    continue;
                }
            }
            rc = bb_operator_upload_file(path, "busierbox-manifest.json", "manifest", argc - 2, argv + 2);
            unlink(path);
            return rc;
        }
        fputs("manifest: unable to create temporary manifest JSON\n", stderr);
        return 1;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--base64"))
            base64 = 1;
        else if (!strcmp(argv[i], "--include-missing"))
            include_missing = 1;
        else {
            fprintf(stderr, "manifest: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json && base64) {
        fputs("manifest: choose one of --json or --base64\n", stderr);
        return 2;
    }
    if (json) {
        write_manifest_json(stdout, include_missing);
        return 0;
    }
    if (base64)
        return print_manifest_base64();

    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    printf("payload_version=%s\n", BUSIERBOX_PAYLOAD_VERSION);
    printf("build_timestamp=%s\n", BUSIERBOX_BUILD_TIMESTAMP);
    printf("git_commit=%s\n", BUSIERBOX_GIT_COMMIT);
    puts("project_license=GPL-2.0-or-later");
    puts("supervisor_license=GPL-2.0-or-later");
    puts("combined_gplv2_compatible=yes");
    puts("not_busybox_fork=yes");
    puts("third_party_component=BusyBox GPL-2.0 payload applets");
    puts("third_party_component=Buildroot GPL-2.0-or-later target build system");
    puts("third_party_component=doom-ascii GPL-2.0-or-later optional Doom engine");
    puts("third_party_component=miniz MIT OR Unlicense payload archive helper");
    printf("target_preset=%s\n", BB_TARGET_PRESET);
    printf("target_name=%s\n", BB_TARGET_NAME);
    printf("target_arch=%s\n", BB_TARGET_ARCH);
    printf("target_endian=%s\n", BB_TARGET_ENDIAN);
    printf("target_cpu=%s\n", BB_TARGET_CPU);
    printf("target_abi=%s\n", BB_TARGET_ABI);
    printf("target_libc=%s\n", BB_TARGET_LIBC);
    printf("kernel_floor=%s\n", BB_KERNEL_FLOOR);
    printf("static_policy=%s\n", BB_STATIC_POLICY);
    printf("payload_preset=%s\n", BB_PAYLOAD_PRESET);
    printf("gdbserver_provider=%s\n", BB_GDBSERVER_PROVIDER);
    printf("runtime_mode=%s\n", BB_RUNTIME_MODE);
    printf("runtime_root=%s\n", BB_RUNTIME_ROOT);
    printf("zero_arg_mode=%s\n", BB_ZERO_ARG_MODE);
    printf("rshell_transport=%s\n", BB_RSHELL_TRANSPORT);
    printf("rshell_encryption=%s\n", BB_RSHELL_ENCRYPTION);
    printf("rshell_session_policy=%s\n", BB_RSHELL_SESSION_POLICY);
    printf("rshell_session_policy_valid=%s\n", rshell_session_policy_valid(BB_RSHELL_SESSION_POLICY) ? "yes" : "no");
    if (!rshell_session_policy_valid(BB_RSHELL_SESSION_POLICY))
        puts("rshell_session_policy_error=unsupported rshell session policy");
    printf("command_queue_enable=%s\n", BB_COMMAND_QUEUE_ENABLE);
    printf("command_queue_allowed_commands=%s\n", BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    printf("command_queue_allow_arbitrary=%s\n", BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    printf("command_queue_execution_mode=%s\n", BB_COMMAND_QUEUE_EXECUTION);
    printf("command_queue_token_configured=%s\n", BB_COMMAND_QUEUE_TOKEN[0] ? "yes" : "no");
    printf("command_queue_poll_interval_sec=%s\n", BB_COMMAND_QUEUE_POLL_INTERVAL_SEC);
    printf("command_queue_poll_jitter_pct=%s\n", BB_COMMAND_QUEUE_POLL_JITTER_PCT);
    printf("command_queue_poll_backoff=%s\n", BB_COMMAND_QUEUE_POLL_BACKOFF);
    printf("command_queue_poll_max_interval_sec=%s\n", BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC);
    printf("command_queue_max_polls=%s\n", BB_COMMAND_QUEUE_MAX_POLLS);
    printf("heavy_tools=");
    for (i = 0; heavy_tools[i]; i++)
        printf("%s%s", i ? " " : "", heavy_tools[i]);
    printf("\n");
    return 0;
}

int applet_config_export_main(int argc, char **argv)
{
    int json = 0, base64 = 0;
    int i;

    if (manifest_is_help(argc, argv)) {
        puts("usage: busierbox config-export [--json|--base64]");
        puts("Export rebuild-oriented artifact config metadata. No private key material is included.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--base64"))
            base64 = 1;
        else {
            fprintf(stderr, "config-export: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json && base64) {
        fputs("config-export: choose one of --json or --base64\n", stderr);
        return 2;
    }
    if (base64)
        return print_config_export_base64();
    (void)json;
    if (write_config_export_json(stdout) != 0) {
        fputs("config-export: cannot write export JSON\n", stderr);
        return 1;
    }
    return 0;
}
