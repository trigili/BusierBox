#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#include "applets.h"

static int split_line(char *line, char **argv, int max)
{
    int argc = 0;
    char *p = line;

    while (*p && argc < max - 1) {
        while (isspace((unsigned char)*p))
            p++;
        if (!*p)
            break;
        argv[argc++] = p;
        while (*p && !isspace((unsigned char)*p))
            p++;
        if (*p)
            *p++ = '\0';
    }
    argv[argc] = NULL;
    return argc;
}

int applet_sh_main(int argc, char **argv)
{
    char line[1024];

    if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        puts("usage: busierbox sh");
        puts("Minimal interactive shell: whitespace splitting, exit, applet dispatch, execvp fallback.");
        puts("No job control, pipes, quoting, globbing, variables, or scripting.");
        return 0;
    }

    (void)argv;
    if (!isatty(STDIN_FILENO))
        fprintf(stderr, "busierbox sh: interactive loop only; scripting is not implemented\n");

    while (1) {
        char *av[64];
        int ac, rc;

        if (isatty(STDIN_FILENO)) {
            fputs("bb$ ", stdout);
            fflush(stdout);
        }
        if (!fgets(line, sizeof(line), stdin))
            break;
        line[strcspn(line, "\n")] = '\0';
        ac = split_line(line, av, 64);
        if (ac == 0)
            continue;
        if (!strcmp(av[0], "exit"))
            return ac > 1 ? atoi(av[1]) : 0;
        rc = bb_dispatch(av[0], ac, av);
        if (rc >= 0)
            continue;

        {
            pid_t pid = fork();
            if (pid < 0) {
                fprintf(stderr, "sh: fork: %s\n", strerror(errno));
                continue;
            }
            if (pid == 0) {
                execvp(av[0], av);
                fprintf(stderr, "sh: %s: %s\n", av[0], strerror(errno));
                _exit(127);
            }
            while (waitpid(pid, &rc, 0) < 0 && errno == EINTR)
                ;
        }
    }
    return 0;
}
