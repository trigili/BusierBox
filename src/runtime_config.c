#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "applets.h"
#include "command_queue_policy.h"
#include "json_helpers.h"
#include "runtime_config.h"
#include "trailer_config.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_RUNTIME_MODE
#define BB_RUNTIME_MODE "extract"
#endif
#ifndef BB_NORESIDUE_LEVEL
#define BB_NORESIDUE_LEVEL "best-effort"
#endif
#ifndef BB_RUNTIME_ROOT
#define BB_RUNTIME_ROOT "./.busierbox"
#endif
#ifndef BB_RUNTIME_ALLOW_FALLBACK_ROOT
#define BB_RUNTIME_ALLOW_FALLBACK_ROOT "no"
#endif
#ifndef BB_RUNTIME_FALLBACK_ROOT
#define BB_RUNTIME_FALLBACK_ROOT "/tmp/.busierbox"
#endif
#ifndef BB_ZERO_ARG_MODE
#define BB_ZERO_ARG_MODE "help"
#endif
#ifndef BB_ZERO_ARG_LOG_MODE
#define BB_ZERO_ARG_LOG_MODE "quiet"
#endif
#ifndef BB_ZERO_ARG_CUSTOM_COMMAND
#define BB_ZERO_ARG_CUSTOM_COMMAND ""
#endif
#ifndef BB_RSHELL_TRANSPORT
#define BB_RSHELL_TRANSPORT "ssh"
#endif
#ifndef BB_RSHELL_ENCRYPTION
#define BB_RSHELL_ENCRYPTION "tls"
#endif
#ifndef BB_RSHELL_ALLOW_PLAINTEXT
#define BB_RSHELL_ALLOW_PLAINTEXT "no"
#endif
#ifndef BB_RSHELL_AUTHKEYS_MODE
#define BB_RSHELL_AUTHKEYS_MODE "disabled"
#endif
#ifndef BB_RSHELL_RUN_MODE
#define BB_RSHELL_RUN_MODE "auto"
#endif
#ifndef BB_RSHELL_SESSION_POLICY
#define BB_RSHELL_SESSION_POLICY "single"
#endif
#ifndef BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING
#define BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING "no"
#endif
#ifndef BB_RSHELL_SOCAT_PORT
#define BB_RSHELL_SOCAT_PORT "22203"
#endif
#ifndef BB_RSHELL_SHELL_PROVIDER
#define BB_RSHELL_SHELL_PROVIDER "auto"
#endif
#ifndef BB_RSHELL_CUSTOM_SHELL
#define BB_RSHELL_CUSTOM_SHELL ""
#endif
#ifndef BB_RSHELL_RETRY_COUNT
#define BB_RSHELL_RETRY_COUNT "1"
#endif
#ifndef BB_RSHELL_RETRY_INTERVAL_SEC
#define BB_RSHELL_RETRY_INTERVAL_SEC "5"
#endif
#ifndef BB_RSHELL_RETRY_JITTER_PCT
#define BB_RSHELL_RETRY_JITTER_PCT "20"
#endif
#ifndef BB_RSHELL_RETRY_BACKOFF
#define BB_RSHELL_RETRY_BACKOFF "none"
#endif
#ifndef BB_RSHELL_RETRY_MAX_INTERVAL_SEC
#define BB_RSHELL_RETRY_MAX_INTERVAL_SEC "300"
#endif
#ifndef BB_AUTORUN_GUARD_ENABLE
#define BB_AUTORUN_GUARD_ENABLE "yes"
#endif
#ifndef BB_AUTORUN_GUARD_PATH
#define BB_AUTORUN_GUARD_PATH "./.busierbox/run"
#endif
#ifndef BB_AUTORUN_REENTRY_ACTION
#define BB_AUTORUN_REENTRY_ACTION "status"
#endif
#ifndef BB_AUTORUN_STALE_LOCK_POLICY
#define BB_AUTORUN_STALE_LOCK_POLICY "recover"
#endif
#ifndef BB_OPERATOR_REMOTE_FORWARD_PORT
#define BB_OPERATOR_REMOTE_FORWARD_PORT "2200"
#endif
#ifndef BB_OPERATOR_SERVER_HOST
#define BB_OPERATOR_SERVER_HOST ""
#endif
#ifndef BB_OPERATOR_SERVER_USER
#define BB_OPERATOR_SERVER_USER "operator"
#endif
#ifndef BB_OPERATOR_SERVER_SSH_PORT
#define BB_OPERATOR_SERVER_SSH_PORT "22"
#endif
#ifndef BB_OPERATOR_TARGET_BIND_HOST
#define BB_OPERATOR_TARGET_BIND_HOST "127.0.0.1"
#endif
#ifndef BB_OPERATOR_TARGET_DROPBEAR_PORT
#define BB_OPERATOR_TARGET_DROPBEAR_PORT "2222"
#endif
#ifndef BB_OPERATOR_KNOWN_HOSTS_POLICY
#define BB_OPERATOR_KNOWN_HOSTS_POLICY "off"
#endif
#ifndef BB_OPERATOR_FILE_SERVICE_ENABLE
#define BB_OPERATOR_FILE_SERVICE_ENABLE "no"
#endif
#ifndef BB_OPERATOR_FILE_SERVICE_PORT
#define BB_OPERATOR_FILE_SERVICE_PORT "22204"
#endif
#ifndef BB_OPERATOR_FILE_SERVICE_TLS
#define BB_OPERATOR_FILE_SERVICE_TLS "yes"
#endif
#ifndef BB_COMMAND_QUEUE_ENABLE
#define BB_COMMAND_QUEUE_ENABLE "no"
#endif
#ifndef BB_COMMAND_QUEUE_PORT
#define BB_COMMAND_QUEUE_PORT "22205"
#endif
#ifndef BB_COMMAND_QUEUE_TLS
#define BB_COMMAND_QUEUE_TLS "yes"
#endif
#ifndef BB_COMMAND_QUEUE_REQUIRE_TOKEN
#define BB_COMMAND_QUEUE_REQUIRE_TOKEN "yes"
#endif
#ifndef BB_COMMAND_QUEUE_TOKEN_SOURCE
#define BB_COMMAND_QUEUE_TOKEN_SOURCE "manual"
#endif
#ifndef BB_COMMAND_QUEUE_ALLOWED_COMMANDS
#define BB_COMMAND_QUEUE_ALLOWED_COMMANDS "none"
#endif
#ifndef BB_COMMAND_QUEUE_ALLOW_ARBITRARY
#define BB_COMMAND_QUEUE_ALLOW_ARBITRARY "no"
#endif
#ifndef BB_COMMAND_QUEUE_POLL_INTERVAL_SEC
#define BB_COMMAND_QUEUE_POLL_INTERVAL_SEC "5"
#endif
#ifndef BB_COMMAND_QUEUE_POLL_JITTER_PCT
#define BB_COMMAND_QUEUE_POLL_JITTER_PCT "0"
#endif
#ifndef BB_COMMAND_QUEUE_POLL_BACKOFF
#define BB_COMMAND_QUEUE_POLL_BACKOFF "none"
#endif
#ifndef BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC
#define BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC "300"
#endif
#ifndef BB_COMMAND_QUEUE_MAX_POLLS
#define BB_COMMAND_QUEUE_MAX_POLLS "0"
#endif
#ifndef BB_BUILTIN_TLS_ENABLE
#define BB_BUILTIN_TLS_ENABLE "no"
#endif

struct cfg_entry {
    const char *key;
    const char *compiled;
    char value[256];
    int has_override;
    char cli_value[256];
    int has_cli_override;
};

static struct cfg_entry cfg[] = {
    {"BB_RUNTIME_MODE", BB_RUNTIME_MODE, "", 0},
    {"BB_NORESIDUE_LEVEL", BB_NORESIDUE_LEVEL, "", 0},
    {"BB_RUNTIME_ROOT", BB_RUNTIME_ROOT, "", 0},
    {"BB_RUNTIME_ALLOW_FALLBACK_ROOT", BB_RUNTIME_ALLOW_FALLBACK_ROOT, "", 0},
    {"BB_RUNTIME_FALLBACK_ROOT", BB_RUNTIME_FALLBACK_ROOT, "", 0},
    {"BB_ZERO_ARG_MODE", BB_ZERO_ARG_MODE, "", 0},
    {"BB_ZERO_ARG_LOG_MODE", BB_ZERO_ARG_LOG_MODE, "", 0},
    {"BB_ZERO_ARG_CUSTOM_COMMAND", BB_ZERO_ARG_CUSTOM_COMMAND, "", 0},
    {"BB_RSHELL_TRANSPORT", BB_RSHELL_TRANSPORT, "", 0},
    {"BB_RSHELL_ENCRYPTION", BB_RSHELL_ENCRYPTION, "", 0},
    {"BB_RSHELL_ALLOW_PLAINTEXT", BB_RSHELL_ALLOW_PLAINTEXT, "", 0},
    {"BB_RSHELL_AUTHKEYS_MODE", BB_RSHELL_AUTHKEYS_MODE, "", 0},
    {"BB_RSHELL_RUN_MODE", BB_RSHELL_RUN_MODE, "", 0},
    {"BB_RSHELL_SESSION_POLICY", BB_RSHELL_SESSION_POLICY, "", 0},
    {"BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING", BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING, "", 0},
    {"BB_RSHELL_SOCAT_PORT", BB_RSHELL_SOCAT_PORT, "", 0},
    {"BB_RSHELL_SHELL_PROVIDER", BB_RSHELL_SHELL_PROVIDER, "", 0},
    {"BB_RSHELL_CUSTOM_SHELL", BB_RSHELL_CUSTOM_SHELL, "", 0},
    {"BB_RSHELL_RETRY_COUNT", BB_RSHELL_RETRY_COUNT, "", 0},
    {"BB_RSHELL_RETRY_INTERVAL_SEC", BB_RSHELL_RETRY_INTERVAL_SEC, "", 0},
    {"BB_RSHELL_RETRY_JITTER_PCT", BB_RSHELL_RETRY_JITTER_PCT, "", 0},
    {"BB_RSHELL_RETRY_BACKOFF", BB_RSHELL_RETRY_BACKOFF, "", 0},
    {"BB_RSHELL_RETRY_MAX_INTERVAL_SEC", BB_RSHELL_RETRY_MAX_INTERVAL_SEC, "", 0},
    {"BB_AUTORUN_GUARD_ENABLE", BB_AUTORUN_GUARD_ENABLE, "", 0},
    {"BB_AUTORUN_GUARD_PATH", BB_AUTORUN_GUARD_PATH, "", 0},
    {"BB_AUTORUN_REENTRY_ACTION", BB_AUTORUN_REENTRY_ACTION, "", 0},
    {"BB_AUTORUN_STALE_LOCK_POLICY", BB_AUTORUN_STALE_LOCK_POLICY, "", 0},
    {"BB_OPERATOR_REMOTE_FORWARD_PORT", BB_OPERATOR_REMOTE_FORWARD_PORT, "", 0},
    {"BB_OPERATOR_SERVER_HOST", BB_OPERATOR_SERVER_HOST, "", 0},
    {"BB_OPERATOR_SERVER_USER", BB_OPERATOR_SERVER_USER, "", 0},
    {"BB_OPERATOR_SERVER_SSH_PORT", BB_OPERATOR_SERVER_SSH_PORT, "", 0},
    {"BB_OPERATOR_TARGET_BIND_HOST", BB_OPERATOR_TARGET_BIND_HOST, "", 0},
    {"BB_OPERATOR_TARGET_DROPBEAR_PORT", BB_OPERATOR_TARGET_DROPBEAR_PORT, "", 0},
    {"BB_OPERATOR_KNOWN_HOSTS_POLICY", BB_OPERATOR_KNOWN_HOSTS_POLICY, "", 0},
    {"BB_OPERATOR_FILE_SERVICE_ENABLE", BB_OPERATOR_FILE_SERVICE_ENABLE, "", 0},
    {"BB_OPERATOR_FILE_SERVICE_PORT", BB_OPERATOR_FILE_SERVICE_PORT, "", 0},
    {"BB_OPERATOR_FILE_SERVICE_TLS", BB_OPERATOR_FILE_SERVICE_TLS, "", 0},
    {"BB_COMMAND_QUEUE_ENABLE", BB_COMMAND_QUEUE_ENABLE, "", 0},
    {"BB_COMMAND_QUEUE_PORT", BB_COMMAND_QUEUE_PORT, "", 0},
    {"BB_COMMAND_QUEUE_TLS", BB_COMMAND_QUEUE_TLS, "", 0},
    {"BB_COMMAND_QUEUE_REQUIRE_TOKEN", BB_COMMAND_QUEUE_REQUIRE_TOKEN, "", 0},
    {"BB_COMMAND_QUEUE_TOKEN_SOURCE", BB_COMMAND_QUEUE_TOKEN_SOURCE, "", 0},
    {"BB_COMMAND_QUEUE_ALLOWED_COMMANDS", BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "", 0},
    {"BB_COMMAND_QUEUE_ALLOW_ARBITRARY", BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "", 0},
    {"BB_COMMAND_QUEUE_POLL_INTERVAL_SEC", BB_COMMAND_QUEUE_POLL_INTERVAL_SEC, "", 0},
    {"BB_COMMAND_QUEUE_POLL_JITTER_PCT", BB_COMMAND_QUEUE_POLL_JITTER_PCT, "", 0},
    {"BB_COMMAND_QUEUE_POLL_BACKOFF", BB_COMMAND_QUEUE_POLL_BACKOFF, "", 0},
    {"BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC", BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC, "", 0},
    {"BB_COMMAND_QUEUE_MAX_POLLS", BB_COMMAND_QUEUE_MAX_POLLS, "", 0},
};

static int loaded;
static int trailer_present;
static int trailer_valid;
static int override_count;
static char trailer_error[160] = "not loaded";
static char trailer_encoding[16] = "none";

static struct cfg_entry *find_entry(const char *key)
{
    size_t i;
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++)
        if (!strcmp(cfg[i].key, key))
            return &cfg[i];
    return NULL;
}

static int self_path(char *out, size_t outsz)
{
    ssize_t n = readlink("/proc/self/exe", out, outsz - 1);
    if (n < 0)
        return -1;
    out[n] = '\0';
    return 0;
}

static void set_error(const char *s)
{
    snprintf(trailer_error, sizeof(trailer_error), "%s", s);
}

static int secret_like_value(const char *value)
{
    char upper[256];
    size_t i;
    const char *markers[] = {
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN DSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----",
        "PASSWORD=",
        "PASSWD=",
        "TOKEN=",
        "PRIVATE_KEY=",
        NULL
    };
    if (!value)
        return 0;
    for (i = 0; i + 1 < sizeof(upper) && value[i]; i++) {
        unsigned char c = (unsigned char)value[i];
        upper[i] = (char)((c >= 'a' && c <= 'z') ? c - ('a' - 'A') : c);
    }
    upper[i] = '\0';
    for (i = 0; markers[i]; i++)
        if (strstr(upper, markers[i]))
            return 1;
    return 0;
}

static int parse_kv_payload(char *payload)
{
    char *line, *save = NULL;
    int count = 0;
    for (line = strtok_r(payload, "\n", &save); line; line = strtok_r(NULL, "\n", &save)) {
        char *eq;
        struct cfg_entry *ent;
        line[strcspn(line, "\r")] = '\0';
        if (!line[0] || line[0] == '#')
            continue;
        eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq++ = '\0';
        ent = find_entry(line);
        if (!ent)
            continue;
        if (secret_like_value(eq))
            return -1;
        snprintf(ent->value, sizeof(ent->value), "%s", eq);
        ent->has_override = 1;
        count++;
    }
    return count;
}

static void load_config(void)
{
    char path[PATH_MAX];
    struct bb_config_trailer trailer;

    if (loaded)
        return;
    loaded = 1;
    trailer_present = 0;
    trailer_valid = 0;
    override_count = 0;
    snprintf(trailer_encoding, sizeof(trailer_encoding), "none");
    set_error("absent");

    if (self_path(path, sizeof(path)) != 0)
        return;
    bb_config_read_trailer_file(path, &trailer);
    trailer_present = trailer.present;
    trailer_valid = trailer.valid;
    snprintf(trailer_encoding, sizeof(trailer_encoding), "%s", trailer.encoding);
    set_error(trailer.error);
    if (!trailer.present || !trailer.valid)
        return;
    override_count = parse_kv_payload(trailer.payload);
    if (override_count < 0) {
        override_count = 0;
        trailer_valid = 0;
        set_error("secret-like trailer value");
        return;
    }
    set_error("ok");
}

int bb_config_key_allowed(const char *key)
{
    return find_entry(key) != NULL;
}

const char *bb_config_compiled(const char *key)
{
    struct cfg_entry *ent = find_entry(key);
    return ent ? ent->compiled : "";
}

const char *bb_config_get(const char *key)
{
    struct cfg_entry *ent;
    const char *env;
    load_config();
    /*
     * Runtime configuration precedence is intentionally narrow and visible:
     * compiled defaults are the baseline, a valid trailer may override only
     * cfg[] keys, environment variables win for operator-side debugging, and
     * command-specific CLI flags win when an applet registers them here.
     */
    ent = find_entry(key);
    if (!ent)
        return "";
    if (ent->has_cli_override)
        return ent->cli_value;
    env = getenv(key);
    if (env && *env)
        return env;
    return ent->has_override ? ent->value : ent->compiled;
}

int bb_config_set_cli_override(const char *key, const char *value)
{
    struct cfg_entry *ent = find_entry(key);
    if (!ent || !value)
        return -1;
    snprintf(ent->cli_value, sizeof(ent->cli_value), "%s", value);
    ent->has_cli_override = 1;
    return 0;
}

int bb_config_trailer_present(void)
{
    load_config();
    return trailer_present;
}

int bb_config_trailer_valid(void)
{
    load_config();
    return trailer_valid;
}

int bb_config_trailer_override_count(void)
{
    load_config();
    return override_count;
}

const char *bb_config_trailer_error(void)
{
    load_config();
    return trailer_error;
}

const char *bb_config_trailer_encoding(void)
{
    load_config();
    return trailer_encoding;
}

static int env_override_count(void)
{
    size_t i;
    int count = 0;
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++) {
        const char *env = getenv(cfg[i].key);
        if (env && *env)
            count++;
    }
    return count;
}

static int cli_override_count(void)
{
    size_t i;
    int count = 0;
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++)
        if (cfg[i].has_cli_override)
            count++;
    return count;
}

const char *bb_config_effective_source(void)
{
    load_config();
    if (cli_override_count() > 0)
        return "cli";
    if (env_override_count() > 0)
        return "env";
    if (trailer_valid && override_count > 0)
        return "trailer";
    return "compiled";
}

static void print_config_object(FILE *out, void (*json_string)(FILE *, const char *), int effective)
{
    size_t i;
    fputc('{', out);
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++) {
        if (i)
            fputc(',', out);
        json_string(out, cfg[i].key);
        fputc(':', out);
        json_string(out, effective ? bb_config_get(cfg[i].key) : cfg[i].compiled);
    }
    fputc('}', out);
}

void bb_config_print_compiled_json(FILE *out, void (*json_string)(FILE *, const char *))
{
    print_config_object(out, json_string, 0);
}

void bb_config_print_effective_json(FILE *out, void (*json_string)(FILE *, const char *))
{
    print_config_object(out, json_string, 1);
}

void bb_config_print_trailer_json(FILE *out, void (*json_string)(FILE *, const char *))
{
    fprintf(out, "{\"present\":%s,\"valid\":%s,\"encoding\":",
            bb_config_trailer_present() ? "true" : "false",
            bb_config_trailer_valid() ? "true" : "false");
    json_string(out, bb_config_trailer_encoding());
    fprintf(out, ",\"override_count\":%d,\"status\":", bb_config_trailer_override_count());
    json_string(out, bb_config_trailer_error());
    fputc('}', out);
}

void bb_config_print_runtime_summary_json(FILE *out, void (*json_string)(FILE *, const char *))
{
    fprintf(out, "{\"effective_config_source\":");
    json_string(out, bb_config_effective_source());
    fprintf(out, ",\"trailer_override\":");
    bb_config_print_trailer_json(out, json_string);
    fprintf(out, ",\"environment_override_count\":%d", env_override_count());
    fprintf(out, ",\"cli_override_count\":%d", cli_override_count());
    fputc('}', out);
}

static int operator_reverse_ssh_possible(void)
{
    return !strcmp(bb_config_get("BB_RSHELL_TRANSPORT"), "ssh");
}

void bb_print_autoexec_config(void)
{
    const char *zero_arg_custom_command = bb_config_get("BB_ZERO_ARG_CUSTOM_COMMAND");

    printf("zero_arg_mode=%s\n", bb_config_get("BB_ZERO_ARG_MODE"));
    printf("runtime_mode=%s\n", bb_config_get("BB_RUNTIME_MODE"));
    printf("noresidue_level=%s\n", bb_config_get("BB_NORESIDUE_LEVEL"));
    printf("runtime_root=%s\n", bb_config_get("BB_RUNTIME_ROOT"));
    printf("runtime_allow_fallback_root=%s\n", bb_config_get("BB_RUNTIME_ALLOW_FALLBACK_ROOT"));
    printf("runtime_fallback_root=%s\n", bb_config_get("BB_RUNTIME_FALLBACK_ROOT"));
    printf("zero_arg_log_mode=%s\n", bb_config_get("BB_ZERO_ARG_LOG_MODE"));
    printf("zero_arg_custom_command_set=%s\n", zero_arg_custom_command[0] ? "yes" : "no");
    printf("rshell_transport=%s\n", bb_config_get("BB_RSHELL_TRANSPORT"));
    printf("rshell_encryption=%s\n", bb_config_get("BB_RSHELL_ENCRYPTION"));
    printf("rshell_allow_plaintext=%s\n", bb_config_get("BB_RSHELL_ALLOW_PLAINTEXT"));
    printf("rshell_authkeys_mode=%s\n", bb_config_get("BB_RSHELL_AUTHKEYS_MODE"));
    printf("rshell_run_mode=%s\n", bb_config_get("BB_RSHELL_RUN_MODE"));
    printf("rshell_session_policy=%s\n", bb_config_get("BB_RSHELL_SESSION_POLICY"));
    printf("rshell_generate_hostkey_if_missing=%s\n", bb_config_get("BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING"));
    printf("rshell_socat_port=%s\n", bb_config_get("BB_RSHELL_SOCAT_PORT"));
    printf("rshell_shell_provider=%s\n", bb_config_get("BB_RSHELL_SHELL_PROVIDER"));
    printf("rshell_retry_count=%s\n", bb_config_get("BB_RSHELL_RETRY_COUNT"));
    printf("rshell_retry_interval_sec=%s\n", bb_config_get("BB_RSHELL_RETRY_INTERVAL_SEC"));
    printf("rshell_retry_jitter_pct=%s\n", bb_config_get("BB_RSHELL_RETRY_JITTER_PCT"));
    printf("rshell_retry_backoff=%s\n", bb_config_get("BB_RSHELL_RETRY_BACKOFF"));
    printf("rshell_retry_max_interval_sec=%s\n", bb_config_get("BB_RSHELL_RETRY_MAX_INTERVAL_SEC"));
    printf("builtin_tls_enabled=%s\n", BB_BUILTIN_TLS_ENABLE);
    printf("rshell_operator_host=%s\n", bb_config_get("BB_OPERATOR_SERVER_HOST"));
    printf("rshell_target_dropbear_port=%s\n", bb_config_get("BB_OPERATOR_TARGET_DROPBEAR_PORT"));
    printf("operator_file_service_enable=%s\n", bb_config_get("BB_OPERATOR_FILE_SERVICE_ENABLE"));
    printf("operator_file_service_port=%s\n", bb_config_get("BB_OPERATOR_FILE_SERVICE_PORT"));
    printf("operator_file_service_tls=%s\n", bb_config_get("BB_OPERATOR_FILE_SERVICE_TLS"));
    printf("command_queue_enable=%s\n", bb_config_get("BB_COMMAND_QUEUE_ENABLE"));
    printf("command_queue_port=%s\n", bb_config_get("BB_COMMAND_QUEUE_PORT"));
    printf("command_queue_tls=%s\n", bb_config_get("BB_COMMAND_QUEUE_TLS"));
    printf("command_queue_require_token=%s\n", bb_config_get("BB_COMMAND_QUEUE_REQUIRE_TOKEN"));
    printf("command_queue_token_source=%s\n", bb_config_get("BB_COMMAND_QUEUE_TOKEN_SOURCE"));
    printf("command_queue_allowed_commands=%s\n", bb_config_get("BB_COMMAND_QUEUE_ALLOWED_COMMANDS"));
    printf("command_queue_allow_arbitrary=%s\n", bb_config_get("BB_COMMAND_QUEUE_ALLOW_ARBITRARY"));
    printf("command_queue_poll_interval_sec=%s\n", bb_config_get("BB_COMMAND_QUEUE_POLL_INTERVAL_SEC"));
    printf("command_queue_poll_jitter_pct=%s\n", bb_config_get("BB_COMMAND_QUEUE_POLL_JITTER_PCT"));
    printf("command_queue_poll_backoff=%s\n", bb_config_get("BB_COMMAND_QUEUE_POLL_BACKOFF"));
    printf("command_queue_poll_max_interval_sec=%s\n", bb_config_get("BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC"));
    printf("command_queue_max_polls=%s\n", bb_config_get("BB_COMMAND_QUEUE_MAX_POLLS"));
    printf("autorun_guard_enabled=%s\n", bb_config_get("BB_AUTORUN_GUARD_ENABLE"));
    printf("autorun_guard_path=%s\n", bb_config_get("BB_AUTORUN_GUARD_PATH"));
    printf("autorun_reentry_action=%s\n", bb_config_get("BB_AUTORUN_REENTRY_ACTION"));
    printf("autorun_stale_lock_policy=%s\n", bb_config_get("BB_AUTORUN_STALE_LOCK_POLICY"));
    printf("operator_reverse_ssh_possible=%s\n", operator_reverse_ssh_possible() ? "yes" : "no");
    printf("operator_reverse_ssh_catch_hint=ssh -p %s root@127.0.0.1\n",
           bb_config_get("BB_OPERATOR_REMOTE_FORWARD_PORT"));
}

static void rshell_server_listener(char *out, size_t outsz)
{
    const char *transport = bb_config_get("BB_RSHELL_TRANSPORT");
    const char *encryption = bb_config_get("BB_RSHELL_ENCRYPTION");
    const char *shell_port = bb_config_get("BB_RSHELL_SOCAT_PORT");
    const char *ssh_port = bb_config_get("BB_OPERATOR_SERVER_SSH_PORT");

    if (!strcmp(transport, "ssh"))
        snprintf(out, outsz, "scripts/busierbox-server --transport ssh --ssh-port %s", ssh_port);
    else if (!strcmp(encryption, "none"))
        snprintf(out, outsz, "scripts/busierbox-server --transport plain-shell --shell-port %s", shell_port);
    else
        snprintf(out, outsz, "scripts/busierbox-server --transport tls-shell --shell-port %s", shell_port);
}

static void rshell_connect_hint(char *out, size_t outsz)
{
    const char *transport = bb_config_get("BB_RSHELL_TRANSPORT");
    const char *remote_forward_port = bb_config_get("BB_OPERATOR_REMOTE_FORWARD_PORT");

    if (!strcmp(transport, "ssh"))
        snprintf(out, outsz, "ssh -p %s root@127.0.0.1", remote_forward_port);
    else if (!strcmp(transport, "none"))
        snprintf(out, outsz, "reverse access disabled");
    else
        snprintf(out, outsz, "shell stream is attached by scripts/busierbox-server");
}

static int rshell_session_policy_valid(const char *policy)
{
    return !strcmp(policy, "single") ||
           !strcmp(policy, "reconnect") ||
           !strcmp(policy, "persistent");
}

void bb_config_print_rshell_readiness_json(FILE *out, void (*json_string)(FILE *, const char *))
{
    const char *transport = bb_config_get("BB_RSHELL_TRANSPORT");
    const char *encryption = bb_config_get("BB_RSHELL_ENCRYPTION");
    const char *run_mode = bb_config_get("BB_RSHELL_RUN_MODE");
    const char *session_policy = bb_config_get("BB_RSHELL_SESSION_POLICY");
    const char *zero_arg_mode = bb_config_get("BB_ZERO_ARG_MODE");
    const char *operator_host = bb_config_get("BB_OPERATOR_SERVER_HOST");
    const char *shell_port = bb_config_get("BB_RSHELL_SOCAT_PORT");
    const char *ssh_port = bb_config_get("BB_OPERATOR_SERVER_SSH_PORT");
    const char *remote_forward_port = bb_config_get("BB_OPERATOR_REMOTE_FORWARD_PORT");
    const char *target_bind_host = bb_config_get("BB_OPERATOR_TARGET_BIND_HOST");
    const char *target_dropbear_port = bb_config_get("BB_OPERATOR_TARGET_DROPBEAR_PORT");
    char server[256], hint[256], target_dropbear[256];
    int warning_count = 0;

    rshell_server_listener(server, sizeof(server));
    rshell_connect_hint(hint, sizeof(hint));
    snprintf(target_dropbear, sizeof(target_dropbear), "%s:%s", target_bind_host, target_dropbear_port);

    fprintf(out, "{\"enabled\":%s", strcmp(transport, "none") ? "true" : "false");
    fprintf(out, ",\"transport\":");
    json_string(out, transport);
    fprintf(out, ",\"encryption\":");
    json_string(out, encryption);
    fprintf(out, ",\"run_mode\":");
    json_string(out, run_mode);
    fprintf(out, ",\"session_policy\":");
    json_string(out, session_policy);
    fprintf(out, ",\"session_policy_valid\":%s", rshell_session_policy_valid(session_policy) ? "true" : "false");
    fprintf(out, ",\"session_policy_errors\":[");
    if (!rshell_session_policy_valid(session_policy))
        json_string(out, "unsupported rshell session policy");
    fprintf(out, "]");
    fprintf(out, ",\"zero_arg_autorun\":%s", !strcmp(zero_arg_mode, "rshell") ? "true" : "false");
    fprintf(out, ",\"operator_host_set\":%s", operator_host[0] ? "true" : "false");
    fprintf(out, ",\"operator_host\":");
    json_string(out, operator_host);
    fprintf(out, ",\"operator_shell_port\":");
    json_string(out, shell_port);
    fprintf(out, ",\"operator_ssh_port\":");
    json_string(out, ssh_port);
    fprintf(out, ",\"remote_forward_port\":");
    json_string(out, remote_forward_port);
    fprintf(out, ",\"target_dropbear\":");
    json_string(out, target_dropbear);
    fprintf(out, ",\"server_listener\":");
    json_string(out, server);
    fprintf(out, ",\"connect_hint\":");
    json_string(out, hint);
    fprintf(out, ",\"warnings\":[");
    if (!strcmp(transport, "none")) {
        json_string(out, "reverse access disabled");
        warning_count++;
    }
    if (strcmp(transport, "none") && !operator_host[0]) {
        if (warning_count++)
            fputc(',', out);
        json_string(out, "operator host is not configured");
    }
    if (strcmp(transport, "none") && strcmp(zero_arg_mode, "rshell")) {
        if (warning_count++)
            fputc(',', out);
        json_string(out, "zero-arg execution will not start reverse access");
    }
    if (!rshell_session_policy_valid(session_policy)) {
        if (warning_count++)
            fputc(',', out);
        json_string(out, "unsupported rshell session policy");
    }
    if (strcmp(transport, "ssh") && !strcmp(encryption, "none")) {
        if (warning_count++)
            fputc(',', out);
        json_string(out, "plaintext shell transport is insecure/debug-only");
    }
    fprintf(out, "]}");
}

int applet_runtime_config_main(int argc, char **argv)
{
    int json = 0;
    int i;
    size_t j;
    struct command_queue_policy_report command_queue_policy = bb_command_queue_validate_policy();
    int command_queue_policy_valid = bb_command_queue_policy_valid(&command_queue_policy);

    if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        puts("usage: busierbox runtime-config [--json]");
        puts("Print compiled, trailer, environment, CLI, and effective runtime configuration.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else {
            fprintf(stderr, "runtime-config: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json) {
        fputs("{\"schema\":1,\"effective_config_source\":", stdout);
        bb_json_string(stdout, bb_config_effective_source());
        fputs(",\"trailer_override\":", stdout);
        bb_config_print_trailer_json(stdout, bb_json_string);
        fprintf(stdout, ",\"environment_override_count\":%d", env_override_count());
        fprintf(stdout, ",\"cli_override_count\":%d", cli_override_count());
        fputs(",\"compiled_config\":", stdout);
        bb_config_print_compiled_json(stdout, bb_json_string);
        fputs(",\"effective_config\":", stdout);
        bb_config_print_effective_json(stdout, bb_json_string);
        fputs(",\"command_queue_policy\":{\"valid\":", stdout);
        fputs(command_queue_policy_valid ? "true" : "false", stdout);
        fputs(",\"errors\":[", stdout);
        for (i = 0; i < command_queue_policy.count; i++) {
            if (i)
                fputc(',', stdout);
            bb_json_string(stdout, command_queue_policy.errors[i]);
        }
        fputs("]}", stdout);
        fputs("}\n", stdout);
        return 0;
    }
    printf("effective_config_source=%s\n", bb_config_effective_source());
    printf("trailer_present=%s\n", bb_config_trailer_present() ? "yes" : "no");
    printf("trailer_valid=%s\n", bb_config_trailer_valid() ? "yes" : "no");
    printf("trailer_encoding=%s\n", bb_config_trailer_encoding());
    printf("trailer_override_count=%d\n", bb_config_trailer_override_count());
    printf("trailer_status=%s\n", bb_config_trailer_error());
    printf("environment_override_count=%d\n", env_override_count());
    printf("cli_override_count=%d\n", cli_override_count());
    printf("command_queue_policy_valid=%s\n", command_queue_policy_valid ? "yes" : "no");
    for (i = 0; i < command_queue_policy.count; i++)
        printf("command_queue_policy_error=%s\n", command_queue_policy.errors[i]);
    for (j = 0; j < sizeof(cfg) / sizeof(cfg[0]); j++) {
        printf("compiled_%s=%s\n", cfg[j].key, cfg[j].compiled);
        printf("effective_%s=%s\n", cfg[j].key, bb_config_get(cfg[j].key));
    }
    return 0;
}
