#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "applets.h"
#include "json_helpers.h"
#include "payload_runtime.h"
#include "runtime_config.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BUSIERBOX_ARTIFACT_TIER
#define BUSIERBOX_ARTIFACT_TIER "core"
#endif
#ifndef BB_TARGET_PRESET
#define BB_TARGET_PRESET "native"
#endif
#ifndef BB_TARGET_NAME
#define BB_TARGET_NAME "native"
#endif
#ifndef BB_PAYLOAD_PRESET
#define BB_PAYLOAD_PRESET "default"
#endif
#ifndef BB_USER_OVERLAY_ENABLE
#define BB_USER_OVERLAY_ENABLE "no"
#endif
#ifndef BB_USER_OVERLAY_ROOT
#define BB_USER_OVERLAY_ROOT "./overlay"
#endif

#define BB_RUNTIME_MODE bb_config_get("BB_RUNTIME_MODE")
#define BB_RUNTIME_ROOT bb_config_get("BB_RUNTIME_ROOT")
#define BB_RUNTIME_ALLOW_FALLBACK_ROOT bb_config_get("BB_RUNTIME_ALLOW_FALLBACK_ROOT")
#define BB_RUNTIME_FALLBACK_ROOT bb_config_get("BB_RUNTIME_FALLBACK_ROOT")
#define BB_ZERO_ARG_MODE bb_config_get("BB_ZERO_ARG_MODE")
#define json_string_payload bb_json_string

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static void print_doctor_manifest_summary_json(FILE *out, int payload_manifest_found, int applet_count)
{
    const char *const *heavy_tools = bb_payload_heavy_tools();
    int heavy_count = 0;
    int i;
    for (i = 0; heavy_tools[i]; i++)
        heavy_count++;
    fprintf(out, ",\"manifest_summary\":{\"target_preset\":");
    json_string_payload(out, BB_TARGET_PRESET);
    fprintf(out, ",\"target_name\":");
    json_string_payload(out, BB_TARGET_NAME);
    fprintf(out, ",\"payload_preset\":");
    json_string_payload(out, BB_PAYLOAD_PRESET);
    fprintf(out, ",\"artifact_tier\":");
    json_string_payload(out, BUSIERBOX_ARTIFACT_TIER);
    fprintf(out, ",\"runtime_mode\":");
    json_string_payload(out, BB_RUNTIME_MODE);
    fprintf(out, ",\"zero_arg_mode\":");
    json_string_payload(out, BB_ZERO_ARG_MODE);
    fprintf(out, ",\"payload_manifest_found\":%s", payload_manifest_found ? "true" : "false");
    fprintf(out, ",\"busybox_applets_count\":%d,\"configured_heavy_tools_count\":%d}",
            applet_count, heavy_count);
}

static void print_doctor_payload_runtime_health_json(FILE *out, int have_payload, const char *payload)
{
    char busybox[PATH_MAX], symlink_count_path[PATH_MAX], symlink_count[32] = "";
    char terminfo[PATH_MAX], tmux_ti[PATH_MAX], zsh_path[PATH_MAX], bin_dir[PATH_MAX];

    fprintf(out, ",\"payload_runtime_health\":{\"present\":%s", have_payload ? "true" : "false");
    if (!have_payload || !payload || !payload[0]) {
        fprintf(out, "}");
        return;
    }
    snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
    snprintf(symlink_count_path, sizeof(symlink_count_path),
             "%s/share/busierbox/applet-symlink-count.txt", payload);
    bb_read_first_line(symlink_count_path, symlink_count, sizeof(symlink_count));
    snprintf(terminfo, sizeof(terminfo), "%s/share/terminfo", payload);
    snprintf(tmux_ti, sizeof(tmux_ti), "%s/share/terminfo/t/tmux", payload);
    snprintf(zsh_path, sizeof(zsh_path), "%s/bin/zsh", payload);
    snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);

    fprintf(out, ",\"dir\":");
    json_string_payload(out, payload);
    fprintf(out, ",\"busybox_executable\":%s", bb_executable_file(busybox) ? "true" : "false");
    fprintf(out, ",\"applet_symlink_count\":");
    if (symlink_count[0])
        json_string_payload(out, symlink_count);
    else
        fprintf(out, "null");
    fprintf(out, ",\"terminfo_present\":%s", bb_path_exists(terminfo) ? "true" : "false");
    fprintf(out, ",\"tmux_terminfo_present\":%s", bb_path_exists(tmux_ti) ? "true" : "false");
    fprintf(out, ",\"zsh_present\":%s", bb_executable_file(zsh_path) ? "true" : "false");
    fprintf(out, ",\"payload_bin_path_count\":%d", bb_path_entry_count(getenv("PATH"), bin_dir));
    fprintf(out, "}");
}

static void print_doctor_payload_inventory_json(FILE *out, const char *manifest)
{
    const char *const *heavy_tools = bb_payload_heavy_tools();

    fprintf(out, ",\"payload_inventory\":{\"manifest_found\":%s", manifest ? "true" : "false");
    fprintf(out, ",\"requested_payload_tools\":");
    if (manifest)
        bb_json_write_raw_field_or(out, manifest, "requested_payload_tools", "[]");
    else
        bb_json_write_string_array(out, heavy_tools);
    fprintf(out, ",\"built_payload_tools\":");
    bb_json_write_raw_field_or(out, manifest, "built_payload_tools", "[]");
    fprintf(out, ",\"staged_payload_tools\":");
    bb_json_write_raw_field_or(out, manifest, "staged_payload_tools", "[]");
    fprintf(out, ",\"missing_payload_tools\":");
    bb_json_write_raw_field_or(out, manifest, "missing_payload_tools", "[]");
    fprintf(out, ",\"missing_payload_tool_reasons\":");
    bb_json_write_raw_field_or(out, manifest, "missing_payload_tool_reasons", "{}");
    fprintf(out, ",\"overlay_enabled\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_enabled", !strcmp(BB_USER_OVERLAY_ENABLE, "yes") ? "true" : "false");
    fprintf(out, ",\"overlay_root\":");
    if (manifest)
        bb_json_write_raw_field_or(out, manifest, "overlay_root", "null");
    else
        json_string_payload(out, BB_USER_OVERLAY_ROOT);
    fprintf(out, ",\"overlay_applied_paths\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_applied_paths", "[]");
    fprintf(out, ",\"overlay_files\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_files", "[]");
    fprintf(out, ",\"overlay_tools\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_tools", "[]");
    fprintf(out, ",\"overlay_warnings\":");
    bb_json_write_raw_field_or(out, manifest, "overlay_warnings", "[]");
    fprintf(out, ",\"user_provided_tools\":");
    bb_json_write_raw_field_or(out, manifest, "user_provided_tools", "[]");
    fprintf(out, ",\"included_shared_libs\":");
    bb_json_write_raw_field_or(out, manifest, "included_shared_libs", "[]");
    fprintf(out, ",\"applet_symlink_skips\":");
    bb_json_write_raw_field_or(out, manifest, "applet_symlink_skips", "[]");
    fprintf(out, "}");
}

int applet_doctor_main(int argc, char **argv)
{
    const char *const *busybox_tools = bb_payload_busybox_tools();
    struct embedded_payload ep;
    char payload[PATH_MAX], manifest_path[PATH_MAX], busybox[PATH_MAX];
    char root[PATH_MAX];
    char *manifest = NULL;
    int have_payload = 0;
    int applet_count = 0;
    int json = 0;
    int support_token = 0;
    int i;

    memset(&ep, 0, sizeof(ep));

    if (is_help(argc, argv)) {
        puts("usage: busierbox doctor [--json|--support-token]");
        puts("Reports embedded payload, extraction, BusyBox, and staged tool health.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json"))
            json = 1;
        else if (!strcmp(argv[i], "--support-token"))
            support_token = 1;
        else {
            fprintf(stderr, "doctor: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (json && support_token) {
        fputs("doctor: choose one of --json or --support-token\n", stderr);
        return 2;
    }
    if (support_token)
        return bb_print_support_token();

    if (bb_get_embedded_payload(&ep) == 0) {
        if (json) {
            int hash_ok = bb_verify_embedded_hash(&ep) == 0;
            have_payload = bb_candidate_payload_dir(payload, sizeof(payload)) == 0;
            if (have_payload) {
                snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
                snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
                if (bb_path_exists(manifest_path))
                    manifest = bb_read_text_file(manifest_path, 1024 * 1024);
            } else {
                root[0] = '\0';
                if (bb_extract_root_usable(BB_RUNTIME_ROOT))
                    snprintf(root, sizeof(root), "%s", BB_RUNTIME_ROOT);
                else if (!strcmp(BB_RUNTIME_ALLOW_FALLBACK_ROOT, "yes") &&
                         bb_extract_root_usable(BB_RUNTIME_FALLBACK_ROOT))
                    snprintf(root, sizeof(root), "%s", BB_RUNTIME_FALLBACK_ROOT);
            }
            if (manifest)
                applet_count = bb_json_array_count_field(manifest, "busybox_applets");
            else {
                for (i = 0; busybox_tools[i]; i++)
                    applet_count++;
            }
            printf("{\"schema\":1,\"embedded_payload\":{\"present\":true,\"format\":");
            json_string_payload(stdout, ep.format);
            printf(",\"size\":%llu,\"sha256\":", ep.size);
            json_string_payload(stdout, ep.sha256);
            printf(",\"version\":");
            json_string_payload(stdout, ep.version);
            printf(",\"hash_ok\":%s}", hash_ok ? "true" : "false");
            printf(",\"extracted_payload\":{\"present\":%s", have_payload ? "true" : "false");
            if (have_payload) {
                char mode[32];
                printf(",\"dir\":");
                json_string_payload(stdout, payload);
                printf(",\"extraction_mode\":");
                json_string_payload(stdout, bb_payload_extraction_mode(payload, mode, sizeof(mode)));
                printf(",\"busybox_present\":%s", bb_executable_file(busybox) ? "true" : "false");
                printf(",\"manifest_found\":%s", bb_path_exists(manifest_path) ? "true" : "false");
                printf(",\"identity_match\":%s", bb_payload_id_matches(&ep, payload) ? "true" : "false");
            } else if (root[0]) {
                printf(",\"candidate_extract_root\":");
                json_string_payload(stdout, root);
            }
            printf("}");
            printf(",\"extraction_runtime\":");
            bb_print_extraction_runtime_json(stdout, ep.size, json_string_payload);
            printf(",\"payload_manifest\":{\"found\":%s,\"busybox_applets_count\":%d",
                   manifest ? "true" : "false", applet_count);
            if (manifest)
                printf(",\"overlay_enabled\":%s", !strcmp(bb_json_bool_value(manifest, "overlay_enabled"), "yes") ? "true" : "false");
            printf("}");
            print_doctor_payload_inventory_json(stdout, manifest);
            print_doctor_payload_runtime_health_json(stdout, have_payload, payload);
            print_doctor_manifest_summary_json(stdout, manifest != NULL, applet_count);
            printf(",\"rshell_readiness\":");
            bb_config_print_rshell_readiness_json(stdout, json_string_payload);
            printf(",\"runtime_config\":");
            bb_config_print_runtime_summary_json(stdout, json_string_payload);
            printf(",\"cleanup_ledger\":");
            bb_print_cleanup_ledger_json(stdout, json_string_payload);
            printf(",\"environment\":{\"path_has_duplicates\":%s,\"home_set\":%s,\"shell_set\":%s",
                   bb_path_has_duplicate_entries(getenv("PATH")) ? "true" : "false",
                   getenv("HOME") && *getenv("HOME") ? "true" : "false",
                   getenv("SHELL") && *getenv("SHELL") ? "true" : "false");
            if (have_payload) {
                char bin_dir[PATH_MAX];
                snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
                printf(",\"payload_bin_path_count\":%d", bb_path_entry_count(getenv("PATH"), bin_dir));
            }
            printf("},\"host\":{\"mem_available_kb\":%llu,\"devpts_available\":%s,\"ptrace_probe\":",
                   bb_mem_available_kb(), bb_path_exists("/dev/pts") ? "true" : "false");
            json_string_payload(stdout, bb_ptrace_probe_status());
            printf(",\"default_route_present\":%s}", bb_has_default_route() ? "true" : "false");
            printf(",\"artifact\":{\"tier\":");
            json_string_payload(stdout, BUSIERBOX_ARTIFACT_TIER);
            printf(",\"runtime_mode\":");
            json_string_payload(stdout, BB_RUNTIME_MODE);
            printf(",\"runtime_root\":");
            json_string_payload(stdout, BB_RUNTIME_ROOT);
            printf("}}\n");
            free(manifest);
            return 0;
        }
        printf("embedded_payload=yes\n");
        printf("embedded_format=%s\n", ep.format);
        printf("embedded_size=%llu\n", ep.size);
        printf("embedded_sha256=%s\n", ep.sha256);
        printf("embedded_version=%s\n", ep.version);
        printf("embedded_hash_ok=%s\n", bb_verify_embedded_hash(&ep) == 0 ? "yes" : "no");
    } else {
        if (json) {
            have_payload = bb_candidate_payload_dir(payload, sizeof(payload)) == 0;
            if (have_payload) {
                snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
                snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
                if (bb_path_exists(manifest_path))
                    manifest = bb_read_text_file(manifest_path, 1024 * 1024);
            }
            if (manifest)
                applet_count = bb_json_array_count_field(manifest, "busybox_applets");
            else {
                for (i = 0; busybox_tools[i]; i++)
                    applet_count++;
            }
            printf("{\"schema\":1,\"embedded_payload\":{\"present\":false},\"extracted_payload\":{\"present\":%s",
                   have_payload ? "true" : "false");
            if (have_payload) {
                char mode[32];
                printf(",\"dir\":");
                json_string_payload(stdout, payload);
                printf(",\"extraction_mode\":");
                json_string_payload(stdout, bb_payload_extraction_mode(payload, mode, sizeof(mode)));
                printf(",\"busybox_present\":%s", bb_executable_file(busybox) ? "true" : "false");
                printf(",\"manifest_found\":%s", bb_path_exists(manifest_path) ? "true" : "false");
            }
            printf("}");
            printf(",\"extraction_runtime\":");
            bb_print_extraction_runtime_json(stdout, 1, json_string_payload);
            printf(",\"payload_manifest\":{\"found\":%s,\"busybox_applets_count\":%d}",
                   manifest ? "true" : "false", applet_count);
            print_doctor_payload_inventory_json(stdout, manifest);
            print_doctor_payload_runtime_health_json(stdout, have_payload, payload);
            print_doctor_manifest_summary_json(stdout, manifest != NULL, applet_count);
            printf(",\"rshell_readiness\":");
            bb_config_print_rshell_readiness_json(stdout, json_string_payload);
            printf(",\"runtime_config\":");
            bb_config_print_runtime_summary_json(stdout, json_string_payload);
            printf(",\"cleanup_ledger\":");
            bb_print_cleanup_ledger_json(stdout, json_string_payload);
            printf(",\"environment\":{\"path_has_duplicates\":%s,\"home_set\":%s,\"shell_set\":%s}",
                   bb_path_has_duplicate_entries(getenv("PATH")) ? "true" : "false",
                   getenv("HOME") && *getenv("HOME") ? "true" : "false",
                   getenv("SHELL") && *getenv("SHELL") ? "true" : "false");
            printf(",\"host\":{\"mem_available_kb\":%llu,\"devpts_available\":%s,\"ptrace_probe\":",
                   bb_mem_available_kb(), bb_path_exists("/dev/pts") ? "true" : "false");
            json_string_payload(stdout, bb_ptrace_probe_status());
            printf(",\"default_route_present\":%s}", bb_has_default_route() ? "true" : "false");
            printf(",\"artifact\":{\"tier\":");
            json_string_payload(stdout, BUSIERBOX_ARTIFACT_TIER);
            printf(",\"runtime_mode\":");
            json_string_payload(stdout, BB_RUNTIME_MODE);
            printf(",\"runtime_root\":");
            json_string_payload(stdout, BB_RUNTIME_ROOT);
            printf("}}\n");
            free(manifest);
            return 0;
        }
        puts("embedded_payload=no");
    }

    if (bb_candidate_payload_dir(payload, sizeof(payload)) == 0) {
        char mode[32];
        have_payload = 1;
        printf("extracted_payload=yes\n");
        printf("payload_dir=%s\n", payload);
        printf("payload_extraction_mode=%s\n", bb_payload_extraction_mode(payload, mode, sizeof(mode)));
    } else {
        puts("extracted_payload=no");
        if (bb_choose_extract_root(root, sizeof(root)) == 0)
            printf("candidate_extract_root=%s\n", root);
    }

    if (have_payload) {
        snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
        printf("busybox_present=%s\n", bb_executable_file(busybox) ? "yes" : "no");
        snprintf(manifest_path, sizeof(manifest_path), "%s/manifest.json", payload);
        printf("payload_manifest_found=%s\n", bb_path_exists(manifest_path) ? "yes" : "no");
        if (ep.present)
            printf("payload_identity_match=%s\n", bb_payload_id_matches(&ep, payload) ? "yes" : "no (stale or different binary)");
        if (bb_path_exists(manifest_path))
            manifest = bb_read_text_file(manifest_path, 1024 * 1024);
    }

    if (manifest) {
        printf("busybox_applets=");
        applet_count = bb_json_array_summary(manifest, "busybox_applets", stdout);
        printf("\n");
        printf("busybox_applets_count=%d\n", applet_count);
        printf("staged_tools=");
        bb_json_array_summary(manifest, "staged_payload_tools", stdout);
        printf("\n");
        printf("missing_tools=");
        bb_json_array_summary(manifest, "missing_payload_tools", stdout);
        printf("\n");
        printf("missing_tool_reasons=");
        bb_json_object_summary(manifest, "missing_payload_tool_reasons", stdout);
        printf("\n");
        printf("overlay_enabled=%s\n", bb_json_bool_value(manifest, "overlay_enabled"));
        printf("overlay_tools=");
        bb_json_array_summary(manifest, "overlay_tools", stdout);
        printf("\n");
        printf("overlay_files=");
        bb_json_array_summary(manifest, "overlay_files", stdout);
        printf("\n");
        printf("overlay_warnings=");
        bb_json_array_summary(manifest, "overlay_warnings", stdout);
        printf("\n");
        free(manifest);
    } else {
        for (i = 0; busybox_tools[i]; i++)
            applet_count++;
        printf("busybox_applets_count=%d\n", applet_count);
    }

    if (have_payload) {
        char symlink_count_path[PATH_MAX], symlink_count[32] = "unknown";
        char terminfo[PATH_MAX], tmux_ti[PATH_MAX], zsh_path[PATH_MAX];
        char bin_dir[PATH_MAX];
        snprintf(symlink_count_path, sizeof(symlink_count_path),
                 "%s/share/busierbox/applet-symlink-count.txt", payload);
        bb_read_first_line(symlink_count_path, symlink_count, sizeof(symlink_count));
        printf("applet_symlink_count=%s\n", symlink_count);
        snprintf(terminfo, sizeof(terminfo), "%s/share/terminfo", payload);
        snprintf(tmux_ti, sizeof(tmux_ti), "%s/share/terminfo/t/tmux", payload);
        printf("terminfo_present=%s\n", bb_path_exists(terminfo) ? "yes" : "no");
        printf("tmux_terminfo_present=%s\n", bb_path_exists(tmux_ti) ? "yes" : "no");
        snprintf(zsh_path, sizeof(zsh_path), "%s/bin/zsh", payload);
        printf("zsh_present=%s\n", bb_executable_file(zsh_path) ? "yes" : "no");
        snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
        printf("payload_bin_path_count=%d\n", bb_path_entry_count(getenv("PATH"), bin_dir));
    }
    printf("path_has_duplicates=%s\n", bb_path_has_duplicate_entries(getenv("PATH")) ? "yes" : "no");
    printf("home_set=%s\n", getenv("HOME") && *getenv("HOME") ? "yes" : "no");
    printf("shell_set=%s\n", getenv("SHELL") && *getenv("SHELL") ? "yes" : "no");

    if (bb_choose_extract_root(root, sizeof(root)) == 0) {
        printf("extract_root_writable_executable=yes\n");
        printf("extract_root=%s\n", root);
        printf("extract_root_noexec=%s\n", bb_dir_is_noexec(root) ? "yes" : "no");
        printf("extract_root_free_space_ok=%s\n", bb_enough_space_for_extract(ep.present ? ep.size : 1, root) ? "yes" : "no");
        printf("extract_root_available_bytes=%llu\n", bb_path_available_bytes(root));
    } else {
        puts("extract_root_writable_executable=no");
    }
    printf("mem_available_kb=%llu\n", bb_mem_available_kb());
    printf("devpts_available=%s\n", bb_path_exists("/dev/pts") ? "yes" : "no");
    printf("ptrace_probe=%s\n", bb_ptrace_probe_status());
    printf("default_route_present=%s\n", bb_has_default_route() ? "yes" : "no");
    if (!bb_path_exists("/dev/pts"))
        puts("recommendation=mount devpts for tmux/dropbear interactive sessions");
    printf("artifact_tier=%s\n", BUSIERBOX_ARTIFACT_TIER);
    bb_print_autoexec_config();
    if (have_payload) {
        char ti[PATH_MAX];
        snprintf(ti, sizeof(ti), "%s/share/terminfo", payload);
        if (!bb_path_exists(ti))
            puts("recommendation=stage terminfo when using tmux/screen/htop");
    }
    return 0;
}
