#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "applets.h"

const struct bb_applet bb_applets[] = {
    {"list", applet_list_main, "list compiled applets"},
    {"sh", applet_sh_main, "small interactive shell loop"},
    {"survey", applet_survey_main, "print embedded Linux triage information"},
    {"envfix", applet_envfix_main, "print or apply environment repair commands"},
    {"nc", applet_nc_main, "tiny TCP netcat"},
    {"http", applet_http_main, "tiny plain-HTTP client"},
    {"serve", applet_serve_main, "tiny HTTP file server"},
    {"cat", applet_cat_main, "concatenate files"},
    {"ls", applet_ls_main, "list directory entries"},
    {"hexdump", applet_hexdump_main, "basic hex and ASCII dump"},
    {"strings", applet_strings_main, "print printable ASCII strings"},
    {"sha256sum", applet_sha256sum_main, "calculate SHA-256 digests"},
    {"base64", applet_base64_main, "base64 encode or decode data"},
    {"dd", applet_dd_main, "copy byte streams with block controls"},
    {"uname", applet_uname_main, "print system name"},
    {"id", applet_id_main, "print uid and gid"},
    {"which", applet_which_main, "search PATH for commands"},
    {"readlink", applet_readlink_main, "print symbolic link target"},
    {"stat", applet_stat_main, "print file metadata"},
    {"df", applet_df_main, "print filesystem free space"},
    {"free", applet_free_main, "print memory summary"},
    {"ps", applet_ps_main, "list processes from /proc"},
    {"mount", applet_mount_main, "print mounted filesystems"},
    {"env", applet_env_main, "print environment or run with assignments"},
    {"cp", applet_cp_main, "copy files"},
    {"mv", applet_mv_main, "rename files"},
    {"rm", applet_rm_main, "remove files"},
    {"mkdir", applet_mkdir_main, "create directories"},
    {"chmod", applet_chmod_main, "change file mode"},
    {"touch", applet_touch_main, "create or update files"},
    {"grep-lite", applet_grep_main, "simple fixed-string grep"},
    {"sleep", applet_sleep_main, "sleep for seconds"},
    {"tee", applet_tee_main, "copy stdin to stdout and files"},
};

const unsigned int bb_applet_count = sizeof(bb_applets) / sizeof(bb_applets[0]);

static const char *base_name(const char *path)
{
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

static void usage(FILE *out)
{
    unsigned int i;

    fprintf(out, "busierbox: embedded Linux debug toolkit Tier 0 MVP\n\n");
    fprintf(out, "usage: busierbox <applet> [args...]\n");
    fprintf(out, "       <applet> [args...]   when invoked through a symlink\n\n");
    fprintf(out, "applets:\n");
    for (i = 0; i < bb_applet_count; i++)
        fprintf(out, "  %-10s %s\n", bb_applets[i].name, bb_applets[i].summary);
}

void bb_list_applets(int verbose)
{
    unsigned int i;

    for (i = 0; i < bb_applet_count; i++) {
        if (verbose)
            printf("%-10s %s\n", bb_applets[i].name, bb_applets[i].summary);
        else
            printf("%s\n", bb_applets[i].name);
    }
}

int bb_dispatch(const char *name, int argc, char **argv)
{
    unsigned int i;

    for (i = 0; i < bb_applet_count; i++) {
        if (strcmp(name, bb_applets[i].name) == 0)
            return bb_applets[i].main(argc, argv);
    }

    return -1;
}

int main(int argc, char **argv)
{
    const char *invoked;
    int rc;

    if (argc < 1 || !argv || !argv[0]) {
        usage(stderr);
        return 2;
    }

    invoked = base_name(argv[0]);
    if (strcmp(invoked, "busierbox") != 0) {
        rc = bb_dispatch(invoked, argc, argv);
        if (rc >= 0)
            return rc;
    }

    if (argc < 2 || strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {
        usage(argc < 2 ? stderr : stdout);
        return argc < 2 ? 2 : 0;
    }

    rc = bb_dispatch(argv[1], argc - 1, argv + 1);
    if (rc >= 0)
        return rc;

    fprintf(stderr, "busierbox: unknown applet: %s\n", argv[1]);
    usage(stderr);
    return 127;
}
