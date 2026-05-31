#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "applets.h"
#include "json_helpers.h"
#include "payload_runtime.h"

#ifndef GRIT_ARTIFACT_TIER
#define GRIT_ARTIFACT_TIER "core"
#endif
#ifndef GRIT_ADVERTISE_PAYLOAD_TOOLS
#define GRIT_ADVERTISE_PAYLOAD_TOOLS 0
#endif

#define json_string_payload bb_json_string

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static int compare_strings(const void *a, const void *b)
{
    return strcmp(*(const char **)a, *(const char **)b);
}

void bb_print_applet_list(FILE *out)
{
    const char *const *busybox_tools = bb_payload_busybox_tools();
    const char *const *heavy_tools = bb_payload_heavy_tools();
    int total = 0;
    int i, idx = 0;
    const char **all_tools;
    int col = 0;

    fprintf(out, "grit: %s artifact, launcher, survey, and payload runtime manager\n\n", GRIT_ARTIFACT_TIER);
    fprintf(out, "usage: grit <command> [args...]\n");
    fprintf(out, "       <command> [args...]   when invoked through a symlink\n\n");

    fprintf(out, "native applets:\n  ");
    for (i = 0; i < (int)bb_applet_count; i++)
        fprintf(out, "%s%s", i ? ", " : "", bb_applets[i].name);
    fprintf(out, "\n\n");

    if (GRIT_ADVERTISE_PAYLOAD_TOOLS) {
        for (i = 0; busybox_tools[i]; i++)
            total++;
        for (i = 0; heavy_tools[i]; i++)
            total++;
    }

    if (total == 0) {
        fprintf(out, "no payload tools advertised by this artifact tier.\n");
        return;
    }

    all_tools = malloc(sizeof(char *) * (size_t)(total + 1));
    if (!all_tools) {
        fprintf(out, "error: out of memory listing applets\n");
        return;
    }

    if (GRIT_ADVERTISE_PAYLOAD_TOOLS) {
        for (i = 0; busybox_tools[i]; i++)
            all_tools[idx++] = busybox_tools[i];
        for (i = 0; heavy_tools[i]; i++)
            all_tools[idx++] = heavy_tools[i];
    }
    all_tools[idx] = NULL;

    qsort(all_tools, (size_t)idx, sizeof(char *), compare_strings);

    fprintf(out, "staged payload tools:\n\t");
    for (i = 0; i < idx; i++) {
        int len = (int)strlen(all_tools[i]);
        if (col + len + 2 > 70) {
            fprintf(out, "\n\t");
            col = 0;
        }
        fprintf(out, "%s%s", all_tools[i], (i == idx - 1) ? "" : ", ");
        col += len + 2;
    }
    fprintf(out, "\n");

    free(all_tools);
}

int bb_payload_tool_supported(const char *name)
{
    const char *const *busybox_tools = bb_payload_busybox_tools();
    const char *const *heavy_tools = bb_payload_heavy_tools();
    int i;
    for (i = 0; busybox_tools[i]; i++) {
        if (strcmp(name, busybox_tools[i]) == 0)
            return 1;
    }
    for (i = 0; heavy_tools[i]; i++) {
        if (strcmp(name, heavy_tools[i]) == 0)
            return 1;
    }
    return 0;
}

int applet_list_main(int argc, char **argv)
{
    const char *const *busybox_tools = bb_payload_busybox_tools();
    const char *const *heavy_tools = bb_payload_heavy_tools();
    int i;
    if (is_help(argc, argv)) {
        puts("usage: grit list [--plain|--json]");
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "--plain")) {
        for (i = 0; i < (int)bb_applet_count; i++)
            printf("native %s\n", bb_applets[i].name);
        if (GRIT_ADVERTISE_PAYLOAD_TOOLS) {
            for (i = 0; busybox_tools[i]; i++)
                printf("busybox %s\n", busybox_tools[i]);
            for (i = 0; heavy_tools[i]; i++)
                printf("tool %s\n", heavy_tools[i]);
        }
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "--json")) {
        printf("{\"artifact_tier\":\"%s\",\"native\":[", GRIT_ARTIFACT_TIER);
        for (i = 0; i < (int)bb_applet_count; i++)
            printf("%s\"%s\"", i ? "," : "", bb_applets[i].name);
        printf("],\"busybox_applets\":[");
        if (GRIT_ADVERTISE_PAYLOAD_TOOLS) {
            for (i = 0; busybox_tools[i]; i++)
                printf("%s\"%s\"", i ? "," : "", busybox_tools[i]);
        }
        printf("],\"staged_tools\":[");
        if (GRIT_ADVERTISE_PAYLOAD_TOOLS) {
            for (i = 0; heavy_tools[i]; i++)
                printf("%s\"%s\"", i ? "," : "", heavy_tools[i]);
        }
        printf("]}\n");
        return 0;
    }
    bb_print_applet_list(stdout);
    return 0;
}
