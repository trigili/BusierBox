#define _POSIX_C_SOURCE 200112L

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "applets.h"

static const char *sane_path = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";

static void print_commands(void)
{
    printf("# eval \"$(busierbox envfix)\" to repair the current shell environment\n");
    printf("export PATH='%s'\n", sane_path);
    printf("[ -n \"${TERM:-}\" ] || export TERM='vt100'\n");
    printf("[ -n \"${HOME:-}\" ] || export HOME='/'\n");
    printf("[ -d /proc ] || echo 'suggestion: mount -t proc proc /proc' >&2\n");
    printf("[ -d /dev/pts ] || echo 'suggestion: mkdir -p /dev/pts && mount -t devpts devpts /dev/pts' >&2\n");
    printf("# --apply creates a safe local fallback HOME when needed; it does not mount filesystems.\n");
}

static int apply_env(void)
{
    int rc = 0;

    if (setenv("PATH", sane_path, 1) != 0) {
        fprintf(stderr, "envfix: setenv PATH failed: %s\n", strerror(errno));
        rc = 1;
    }

    if (!getenv("TERM") && setenv("TERM", "vt100", 1) != 0) {
        fprintf(stderr, "envfix: setenv TERM failed: %s\n", strerror(errno));
        rc = 1;
    }

    if (!getenv("HOME") && setenv("HOME", "/", 1) != 0) {
        fprintf(stderr, "envfix: setenv HOME failed: %s\n", strerror(errno));
        rc = 1;
    }

    if (access(".busierbox-home", F_OK) != 0 && mkdir(".busierbox-home", 0700) != 0 && errno != EEXIST) {
        fprintf(stderr, "envfix: mkdir .busierbox-home failed: %s\n", strerror(errno));
        rc = 1;
    }

    puts("envfix: applied to current busierbox process environment");
    puts("envfix: created .busierbox-home when possible for use as a local HOME fallback");
    puts("envfix: note that child process changes cannot modify the parent shell");
    return rc;
}

int applet_envfix_main(int argc, char **argv)
{
    if (argc > 1 && strcmp(argv[1], "--apply") == 0)
        return apply_env();

    if (argc > 1 && (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0)) {
        puts("usage: busierbox envfix [--apply]");
        puts("without --apply, prints shell commands suitable for eval");
        return 0;
    }

    print_commands();
    return 0;
}
