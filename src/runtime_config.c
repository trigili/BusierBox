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
#ifndef BB_COMMAND_QUEUE_TOKEN
#define BB_COMMAND_QUEUE_TOKEN ""
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
    {"BB_COMMAND_QUEUE_TOKEN", BB_COMMAND_QUEUE_TOKEN, "", 0},
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

static const char *config_category(const char *key)
{
    if (!strncmp(key, "BB_RUNTIME_", strlen("BB_RUNTIME_")) || !strcmp(key, "BB_NORESIDUE_LEVEL"))
        return "runtime";
    if (!strncmp(key, "BB_ZERO_ARG_", strlen("BB_ZERO_ARG_")))
        return "zero_arg";
    if (!strncmp(key, "BB_RSHELL_", strlen("BB_RSHELL_")))
        return "rshell";
    if (!strncmp(key, "BB_AUTORUN_", strlen("BB_AUTORUN_")))
        return "autorun";
    if (!strncmp(key, "BB_OPERATOR_", strlen("BB_OPERATOR_")))
        return "operator";
    if (!strncmp(key, "BB_COMMAND_QUEUE_", strlen("BB_COMMAND_QUEUE_")))
        return "command_queue";
    return "other";
}

static const char *config_source_for_entry(const struct cfg_entry *ent)
{
    const char *env;
    if (ent->has_cli_override)
        return "cli";
    env = getenv(ent->key);
    if (env && *env)
        return "env";
    if (ent->has_override)
        return "trailer";
    return "compiled";
}

static void print_config_records(FILE *out)
{
    size_t i;
    fputc('[', out);
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++) {
        const char *effective = bb_config_get(cfg[i].key);
        if (i)
            fputc(',', out);
        fputs("{\"key\":", out);
        bb_json_string(out, cfg[i].key);
        fputs(",\"category\":", out);
        bb_json_string(out, config_category(cfg[i].key));
        fputs(",\"source\":", out);
        bb_json_string(out, config_source_for_entry(&cfg[i]));
        fputs(",\"compiled\":", out);
        bb_json_string(out, cfg[i].compiled);
        fputs(",\"effective\":", out);
        bb_json_string(out, effective);
        fputs(",\"changed\":", out);
        fputs(strcmp(cfg[i].compiled, effective) ? "true" : "false", out);
        fputs("}", out);
    }
    fputc(']', out);
}

static int config_record_matches(const char *kind, const char *value, const struct cfg_entry *ent)
{
    const char *effective = bb_config_get(ent->key);
    if (!strcmp(kind, "category"))
        return !strcmp(config_category(ent->key), value);
    if (!strcmp(kind, "source"))
        return !strcmp(config_source_for_entry(ent), value);
    if (!strcmp(kind, "changed"))
        return !strcmp(value, strcmp(ent->compiled, effective) ? "yes" : "no");
    return 0;
}

static void print_config_index_array(FILE *out, const char *kind, const char *value)
{
    size_t i;
    int first = 1;
    fputc('[', out);
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++) {
        if (!config_record_matches(kind, value, &cfg[i]))
            continue;
        if (!first)
            fputc(',', out);
        fprintf(out, "%zu", i);
        first = 0;
    }
    fputc(']', out);
}

static void print_config_record_indexes(FILE *out)
{
    static const char *categories[] = {
        "runtime", "zero_arg", "rshell", "autorun", "operator", "command_queue", "other", NULL
    };
    static const char *sources[] = {"compiled", "trailer", "env", "cli", NULL};
    size_t i;

    fputs(",\"config_records_by_key\":{", out);
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++) {
        if (i)
            fputc(',', out);
        bb_json_string(out, cfg[i].key);
        fprintf(out, ":[%zu]", i);
    }
    fputs("},\"config_records_by_category\":{", out);
    for (i = 0; categories[i]; i++) {
        if (i)
            fputc(',', out);
        bb_json_string(out, categories[i]);
        fputc(':', out);
        print_config_index_array(out, "category", categories[i]);
    }
    fputs("},\"config_records_by_source\":{", out);
    for (i = 0; sources[i]; i++) {
        if (i)
            fputc(',', out);
        bb_json_string(out, sources[i]);
        fputc(':', out);
        print_config_index_array(out, "source", sources[i]);
    }
    fputs("},\"config_records_by_changed\":{", out);
    bb_json_string(out, "yes");
    fputc(':', out);
    print_config_index_array(out, "changed", "yes");
    fputc(',', out);
    bb_json_string(out, "no");
    fputc(':', out);
    print_config_index_array(out, "changed", "no");
    fputc('}', out);
}

static size_t config_changed_count(void)
{
    size_t i;
    size_t count = 0;
    for (i = 0; i < sizeof(cfg) / sizeof(cfg[0]); i++)
        if (strcmp(cfg[i].compiled, bb_config_get(cfg[i].key)))
            count++;
    return count;
}

void bb_config_print_records_json(FILE *out)
{
    print_config_records(out);
}

void bb_config_print_record_indexes_json(FILE *out)
{
    print_config_record_indexes(out);
}

void bb_config_print_record_summary_json(FILE *out)
{
    fprintf(out, "{\"total_count\":%zu,\"changed_count\":%zu,\"environment_override_count\":%d,\"cli_override_count\":%d,\"trailer_override_count\":%d}",
            sizeof(cfg) / sizeof(cfg[0]),
            config_changed_count(),
            env_override_count(),
            cli_override_count(),
            bb_config_trailer_override_count());
}

void bb_config_print_record_api_collection_json(FILE *out)
{
    fputs("{\"name\":\"config_records\",\"count\":", out);
    fprintf(out, "%zu", sizeof(cfg) / sizeof(cfg[0]));
    fputs(",\"count_summary_key\":\"config_record_summary.total_count\"", out);
    fputs(",\"primary_key\":\"key\"", out);
    fputs(",\"summary_key\":\"config_record_summary.total_count\",\"indexes\":[\"config_records_by_key\",\"config_records_by_category\",\"config_records_by_source\",\"config_records_by_changed\"]}", out);
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

static void print_noresidue_policy_json(FILE *out)
{
    const char *runtime_mode = bb_config_get("BB_RUNTIME_MODE");
    const char *level = bb_config_get("BB_NORESIDUE_LEVEL");
    int active = !strcmp(runtime_mode, "no-residue");
    int aggressive = !strcmp(level, "aggressive");

    fprintf(out, "{\"active\":%s,\"level\":", active ? "true" : "false");
    bb_json_string(out, level);
    fprintf(out, ",\"runtime_mode\":");
    bb_json_string(out, runtime_mode);
    fprintf(out, ",\"cleanup_scope\":\"BusierBox-owned runtime roots and ledgered files only\"");
    fprintf(out, ",\"best_effort\":true");
    fprintf(out, ",\"aggressive_minimizes_runtime_residue\":%s", aggressive ? "true" : "false");
    fprintf(out, ",\"forensic_no_trace\":false");
    fprintf(out, ",\"external_writes_require_explicit_apply\":true");
    fprintf(out, ",\"guarantee\":");
    bb_json_string(out, aggressive ?
        "aggressive minimizes BusierBox runtime residue but cannot guarantee absence of residue" :
        "best-effort cleanup removes owned runtime state where reasonable");
    fprintf(out, "}");
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
    printf("command_queue_token_set=%s\n", bb_config_get("BB_COMMAND_QUEUE_TOKEN")[0] ? "yes" : "no");
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
        fputs(",\"config_records\":", stdout);
        bb_config_print_records_json(stdout);
        bb_config_print_record_indexes_json(stdout);
        fputs(",\"config_record_summary\":", stdout);
        bb_config_print_record_summary_json(stdout);
        fputs(",\"api_collections\":{\"config_records\":", stdout);
        bb_config_print_record_api_collection_json(stdout);
        fputc('}', stdout);
        fputs(",\"noresidue_policy\":", stdout);
        print_noresidue_policy_json(stdout);
        fputs(",\"rshell_readiness\":", stdout);
        bb_config_print_rshell_readiness_json(stdout, bb_json_string);
        fputs(",\"command_queue_policy\":{\"valid\":", stdout);
        fputs(command_queue_policy_valid ? "true" : "false", stdout);
        fputs(",\"enabled\":", stdout);
        fputs(!strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") ? "true" : "false", stdout);
        fputs(",\"default_enabled\":false", stdout);
        fputs(",\"configured_for_polling\":", stdout);
        fputs((command_queue_policy_valid && !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && BB_OPERATOR_SERVER_HOST[0]) ? "true" : "false", stdout);
        fputs(",\"missing_operator_host\":", stdout);
        fputs((command_queue_policy_valid && !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && !BB_OPERATOR_SERVER_HOST[0]) ? "true" : "false", stdout);
        fputs(",\"token_required\":", stdout);
        fputs(!strcmp(BB_COMMAND_QUEUE_REQUIRE_TOKEN, "yes") ? "true" : "false", stdout);
        fputs(",\"token_configured\":", stdout);
        fputs(BB_COMMAND_QUEUE_TOKEN[0] ? "true" : "false", stdout);
        fputs(",\"poll_transport_supported\":true", stdout);
        fputs(",\"live_polling_supported\":true", stdout);
        fputs(",\"delivery_supported\":false", stdout);
        fputs(",\"result_upload_supported\":true", stdout);
        fputs(",\"execution_supported\":false", stdout);
        fputs(",\"executes_commands\":false", stdout);
        fputs(",\"active_control_channel\":false", stdout);
        fputs(",\"operator_supplied_command_execution\":false", stdout);
        fputs(",\"arbitrary_policy_requested\":", stdout);
        fputs((command_queue_policy_valid && !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "custom") && !strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "yes")) ? "true" : "false", stdout);
        fputs(",\"arbitrary_execution_allowed\":false", stdout);
        fputs(",\"safe_disabled_default\":", stdout);
        fputs((command_queue_policy_valid && strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "none") && !strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "no")) ? "true" : "false", stdout);
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
    printf("command_queue_configured_for_polling=%s\n", (command_queue_policy_valid && !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && BB_OPERATOR_SERVER_HOST[0]) ? "yes" : "no");
    printf("command_queue_missing_operator_host=%s\n", (command_queue_policy_valid && !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && !BB_OPERATOR_SERVER_HOST[0]) ? "yes" : "no");
    puts("command_queue_poll_transport_supported=yes");
    puts("command_queue_live_polling_supported=yes");
    puts("command_queue_delivery_supported=no");
    puts("command_queue_result_upload_supported=yes");
    puts("command_queue_execution_supported=no");
    puts("command_queue_executes_commands=no");
    puts("command_queue_active_control_channel=no");
    puts("command_queue_operator_supplied_command_execution=no");
    printf("command_queue_arbitrary_policy_requested=%s\n", (command_queue_policy_valid && !strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "custom") && !strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "yes")) ? "yes" : "no");
    puts("command_queue_arbitrary_execution_allowed=no");
    printf("command_queue_safe_disabled_default=%s\n", (command_queue_policy_valid && strcmp(BB_COMMAND_QUEUE_ENABLE, "yes") && !strcmp(BB_COMMAND_QUEUE_ALLOWED_COMMANDS, "none") && !strcmp(BB_COMMAND_QUEUE_ALLOW_ARBITRARY, "no")) ? "yes" : "no");
    for (i = 0; i < command_queue_policy.count; i++)
        printf("command_queue_policy_error=%s\n", command_queue_policy.errors[i]);
    for (j = 0; j < sizeof(cfg) / sizeof(cfg[0]); j++) {
        printf("compiled_%s=%s\n", cfg[j].key, cfg[j].compiled);
        printf("effective_%s=%s\n", cfg[j].key, bb_config_get(cfg[j].key));
    }
    return 0;
}
