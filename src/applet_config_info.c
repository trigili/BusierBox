#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "applets.h"
#include "command_queue_policy.h"
#include "effective_config.h"
#include "payload_runtime.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BUSIERBOX_PAYLOAD_VERSION
#define BUSIERBOX_PAYLOAD_VERSION "dev"
#endif
#ifndef BUSIERBOX_ARTIFACT_TIER
#define BUSIERBOX_ARTIFACT_TIER "core"
#endif
#ifndef BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS
#define BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS 0
#endif
#ifndef BB_GDBSERVER_PROVIDER
#define BB_GDBSERVER_PROVIDER "auto"
#endif

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static int read_exe_dir(char *out, size_t outsz)
{
    ssize_t n = readlink("/proc/self/exe", out, outsz - 1);
    char *slash;
    if (n < 0)
        return -1;
    out[n] = '\0';
    slash = strrchr(out, '/');
    if (!slash)
        return -1;
    *slash = '\0';
    return 0;
}

static void print_noresidue_policy_info(void)
{
    int active = !strcmp(BB_RUNTIME_MODE, "no-residue");
    int aggressive = !strcmp(BB_NORESIDUE_LEVEL, "aggressive");

    printf("noresidue_policy_active=%s\n", active ? "yes" : "no");
    printf("noresidue_policy_level=%s\n", BB_NORESIDUE_LEVEL);
    puts("noresidue_policy_cleanup_scope=BusierBox-owned runtime roots and ledgered files only");
    puts("noresidue_policy_best_effort=yes");
    printf("noresidue_policy_aggressive_minimizes_runtime_residue=%s\n", aggressive ? "yes" : "no");
    puts("noresidue_policy_forensic_no_trace=no");
    puts("noresidue_policy_external_writes_require_explicit_apply=yes");
    printf("noresidue_policy_guarantee=%s\n", aggressive ?
        "aggressive minimizes BusierBox runtime residue but cannot guarantee absence of residue" :
        "best-effort cleanup removes owned runtime state where reasonable");
}

int applet_config_info_main(int argc, char **argv)
{
    const char *const *heavy_tools = bb_payload_heavy_tools();
    char payload[PATH_MAX], hash_path[PATH_MAX], hash[256] = "unknown";
    char manifest[PATH_MAX];
    char exe_dir[PATH_MAX];
    struct embedded_payload ep;
    int have_embedded;
    int have_payload;
    struct command_queue_policy_report command_queue_policy = bb_command_queue_validate_policy();
    int command_queue_policy_valid = bb_command_queue_policy_valid(&command_queue_policy);
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox config-info");
        return 0;
    }
    puts("build_target=native");
#ifdef __GLIBC__
    puts("libc=glibc");
#else
    puts("libc=unknown");
#endif
    puts("core_static_status=see build output");
    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    bb_print_autoexec_config();
    printf("trailer_override_present=%s\n", bb_config_trailer_present() ? "yes" : "no");
    printf("trailer_override_valid=%s\n", bb_config_trailer_valid() ? "yes" : "no");
    printf("trailer_override_encoding=%s\n", bb_config_trailer_encoding());
    printf("trailer_override_count=%d\n", bb_config_trailer_override_count());
    printf("trailer_override_status=%s\n", bb_config_trailer_error());
    printf("effective_config_source=%s\n", bb_config_effective_source());
    printf("compiled_zero_arg_mode=%s\n", bb_config_compiled("BB_ZERO_ARG_MODE"));
    printf("compiled_noresidue_level=%s\n", bb_config_compiled("BB_NORESIDUE_LEVEL"));
    printf("compiled_rshell_transport=%s\n", bb_config_compiled("BB_RSHELL_TRANSPORT"));
    printf("compiled_rshell_session_policy=%s\n", bb_config_compiled("BB_RSHELL_SESSION_POLICY"));
    printf("compiled_rshell_operator_host=%s\n", bb_config_compiled("BB_OPERATOR_SERVER_HOST"));
    printf("compiled_command_queue_enable=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_ENABLE"));
    printf("compiled_command_queue_allowed_commands=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_ALLOWED_COMMANDS"));
    printf("compiled_command_queue_allow_arbitrary=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_ALLOW_ARBITRARY"));
    printf("compiled_command_queue_poll_interval_sec=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_POLL_INTERVAL_SEC"));
    printf("compiled_command_queue_poll_jitter_pct=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_POLL_JITTER_PCT"));
    printf("compiled_command_queue_poll_backoff=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_POLL_BACKOFF"));
    printf("compiled_command_queue_poll_max_interval_sec=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC"));
    printf("compiled_command_queue_max_polls=%s\n", bb_config_compiled("BB_COMMAND_QUEUE_MAX_POLLS"));
    printf("effective_zero_arg_mode=%s\n", BB_ZERO_ARG_MODE);
    printf("effective_noresidue_level=%s\n", BB_NORESIDUE_LEVEL);
    print_noresidue_policy_info();
    printf("effective_rshell_transport=%s\n", BB_RSHELL_TRANSPORT);
    printf("effective_rshell_session_policy=%s\n", BB_RSHELL_SESSION_POLICY);
    printf("effective_rshell_operator_host=%s\n", BB_OPERATOR_SERVER_HOST);
    printf("effective_command_queue_enable=%s\n", BB_COMMAND_QUEUE_ENABLE);
    printf("effective_command_queue_allowed_commands=%s\n", BB_COMMAND_QUEUE_ALLOWED_COMMANDS);
    printf("effective_command_queue_allow_arbitrary=%s\n", BB_COMMAND_QUEUE_ALLOW_ARBITRARY);
    printf("effective_command_queue_poll_interval_sec=%s\n", BB_COMMAND_QUEUE_POLL_INTERVAL_SEC);
    printf("effective_command_queue_poll_jitter_pct=%s\n", BB_COMMAND_QUEUE_POLL_JITTER_PCT);
    printf("effective_command_queue_poll_backoff=%s\n", BB_COMMAND_QUEUE_POLL_BACKOFF);
    printf("effective_command_queue_poll_max_interval_sec=%s\n", BB_COMMAND_QUEUE_POLL_MAX_INTERVAL_SEC);
    printf("effective_command_queue_max_polls=%s\n", BB_COMMAND_QUEUE_MAX_POLLS);
    printf("effective_command_queue_policy_valid=%s\n", command_queue_policy_valid ? "yes" : "no");
    for (i = 0; i < command_queue_policy.count; i++)
        printf("effective_command_queue_policy_error=%s\n", command_queue_policy.errors[i]);
    have_embedded = bb_get_embedded_payload(&ep) == 0;
    have_payload = bb_candidate_payload_dir(payload, sizeof(payload)) == 0;
    printf("embedded_payload=%s\n", have_embedded ? "yes" : "no");
    printf("payload_version=%s\n", BUSIERBOX_PAYLOAD_VERSION);
    printf("gdbserver_provider=%s\n", BB_GDBSERVER_PROVIDER);
    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(hash_path, sizeof(hash_path), "%s/payload.tar.gz.sha256", exe_dir);
        bb_read_first_line(hash_path, hash, sizeof(hash));
    }
    printf("payload_archive_hash=%s\n", hash);
    printf("native_applets=");
    for (i = 0; i < (int)bb_applet_count; i++)
        printf("%s%s", i ? " " : "", bb_applets[i].name);
    printf("\n");
    printf("payload_present=%s\n", have_payload ? payload : "no");
    if (have_payload) {
        char mode[32];
        printf("payload_extraction_mode=%s\n", bb_payload_extraction_mode(payload, mode, sizeof(mode)));
    }
    printf("payload_tools_present=");
    if (BUSIERBOX_ADVERTISE_PAYLOAD_TOOLS) {
        for (i = 0; heavy_tools[i]; i++)
            printf("%s%s:%s", i ? "," : "", heavy_tools[i], have_payload ? "yes" : "available-after-extract");
    } else {
        printf("none");
    }
    printf("\n");
    if (have_payload) {
        char busybox[PATH_MAX];
        snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
        printf("busybox_present=%s\n", bb_executable_file(busybox) ? "yes" : "no");
        snprintf(manifest, sizeof(manifest), "%s/manifest.json", payload);
        if (bb_path_exists(manifest)) {
            FILE *fp = fopen(manifest, "r");
            char line[256];
            printf("payload_manifest=%s\n", manifest);
            puts("payload_manifest_summary_begin");
            if (fp) {
                while (fgets(line, sizeof(line), fp))
                    fputs(line, stdout);
                fclose(fp);
            }
            puts("payload_manifest_summary_end");
        }
    }
    puts("busybox_dispatch=yes");
    return 0;
}
