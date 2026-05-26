#define _POSIX_C_SOURCE 200809L

#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "applets.h"

const char *bb_ptrace_probe_status(void)
{
    pid_t child, r;
    int status;

    child = fork();
    if (child < 0)
        return "fork-failed";
    if (child == 0) {
        if (ptrace(PTRACE_TRACEME, 0, NULL, NULL) < 0)
            _exit(2);
        raise(SIGSTOP);
        _exit(0);
    }
    r = waitpid(child, &status, 0);
    if (r != child) {
        kill(child, SIGKILL);
        waitpid(child, NULL, 0);
        return "unknown";
    }
    if (WIFSTOPPED(status) && WSTOPSIG(status) == SIGSTOP) {
        ptrace(PTRACE_CONT, child, NULL, 0);
        waitpid(child, &status, 0);
        return "basic-ok";
    }
    if (WIFEXITED(status) && WEXITSTATUS(status) == 2)
        return "denied";
    kill(child, SIGKILL);
    waitpid(child, NULL, 0);
    return "unknown";
}

unsigned long long bb_mem_available_kb(void)
{
    FILE *fp = fopen("/proc/meminfo", "r");
    char key[64], unit[32];
    unsigned long long val;

    if (!fp)
        return 0;
    while (fscanf(fp, "%63s %llu %31s\n", key, &val, unit) == 3) {
        if (!strcmp(key, "MemAvailable:")) {
            fclose(fp);
            return val;
        }
    }
    fclose(fp);
    return 0;
}

int bb_has_default_route(void)
{
    FILE *fp = fopen("/proc/net/route", "r");
    char line[256], iface[64], dest[64];

    if (!fp)
        return 0;
    if (!fgets(line, sizeof(line), fp)) {
        fclose(fp);
        return 0;
    }
    while (fgets(line, sizeof(line), fp)) {
        if (sscanf(line, "%63s %63s", iface, dest) == 2 && !strcmp(dest, "00000000")) {
            fclose(fp);
            return 1;
        }
    }
    fclose(fp);
    return 0;
}
