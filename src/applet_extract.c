#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <string.h>

#include "applets.h"
#include "payload_runtime.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

int applet_extract_main(int argc, char **argv)
{
    char payload[PATH_MAX], archive[PATH_MAX], root[PATH_MAX];
    struct embedded_payload ep;
    int i, force = 0;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--force"))
            force = 1;
    }
    if (is_help(argc, argv)) {
        puts("usage: busierbox extract [--force]");
        puts("Extracts embedded payload into a writable runtime directory.");
        puts("  --force  Remove any existing extracted payload before extracting.");
        return 0;
    }
    if (force) {
        char old_payload[PATH_MAX];
        if (bb_candidate_payload_dir(old_payload, sizeof(old_payload)) == 0) {
            printf("extract: removing existing payload at %s\n", old_payload);
            bb_rm_rf(old_payload);
        }
    }
    if (!force && bb_candidate_payload_dir(payload, sizeof(payload)) == 0 && bb_payload_is_full(payload)) {
        printf("payload: reuse %s\n", payload);
        return 0;
    }
    if (bb_choose_extract_root(root, sizeof(root)) != 0) {
        fprintf(stderr, "extract: no writable executable runtime directory found\n");
        return 1;
    }
    if (bb_get_embedded_payload(&ep) == 0) {
        if (bb_extract_embedded_to_root(&ep, root, 0) != 0) {
            fprintf(stderr, "extract: embedded payload extraction failed\n");
            return 1;
        }
    } else {
        if (bb_payload_archive_path(archive, sizeof(archive)) != 0) {
            fprintf(stderr, "extract: no embedded payload found and no dev fallback archive found\n");
            return 1;
        }
        fprintf(stderr, "extract: warning: using dev-only external payload archive fallback: %s\n", archive);
        if (bb_extract_archive_file_to_root(archive, root, 0) != 0) {
            fprintf(stderr, "extract: archive extraction failed for %s\n", archive);
            return 1;
        }
    }
    snprintf(payload, sizeof(payload), "%s/payload", root);
    if (!bb_payload_valid(payload)) {
        fprintf(stderr, "extract: extracted payload failed validation\n");
        return 1;
    }
    bb_write_artifact_manifest_file(root);
    printf("payload: extracted %s\n", payload);
    return 0;
}
