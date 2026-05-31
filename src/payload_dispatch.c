#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "applets.h"
#include "runtime_config.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

static int path_has_component(const char *pathvar, const char *dir)
{
    size_t dlen = strlen(dir);
    const char *p = pathvar;
    while (p && *p) {
        const char *colon = strchr(p, ':');
        size_t seglen = colon ? (size_t)(colon - p) : strlen(p);
        if (seglen == dlen && strncmp(p, dir, dlen) == 0)
            return 1;
        p = colon ? colon + 1 : NULL;
    }
    return 0;
}

static void set_payload_env(const char *payload)
{
    char path[PATH_MAX * 2], home[PATH_MAX], lib[PATH_MAX], bin_dir[PATH_MAX];
    char abs_payload[PATH_MAX];
    const char *old_path = getenv("PATH");

    /* Resolve to absolute path so PATH stays valid after directory changes. */
    if (payload[0] != '/') {
        char cwd[PATH_MAX];
        if (getcwd(cwd, sizeof(cwd)) != NULL)
            snprintf(abs_payload, sizeof(abs_payload), "%s/%s", cwd, payload);
        else
            snprintf(abs_payload, sizeof(abs_payload), "%s", payload);
    } else {
        snprintf(abs_payload, sizeof(abs_payload), "%s", payload);
    }
    payload = abs_payload;

    snprintf(bin_dir, sizeof(bin_dir), "%s/bin", payload);
    if (!old_path || !path_has_component(old_path, bin_dir))
        snprintf(path, sizeof(path), "%s/bin:%s", payload, old_path ? old_path : "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin");
    else
        snprintf(path, sizeof(path), "%s", old_path);
    snprintf(home, sizeof(home), "%s/home", payload);
    snprintf(lib, sizeof(lib), "%s/lib", payload);
    setenv("GRIT_PAYLOAD_DIR", payload, 1);
    setenv("PATH", path, 1);
    setenv("HOME", home, 1);
    if (!getenv("TERM"))
        setenv("TERM", "xterm-256color", 1);
    snprintf(lib, sizeof(lib), "%s/home", payload);
    if (bb_path_exists(lib))
        setenv("ZDOTDIR", lib, 1);
    snprintf(lib, sizeof(lib), "%s/lib", payload);
    if (bb_path_exists(lib))
        setenv("LD_LIBRARY_PATH", lib, 1);
    snprintf(lib, sizeof(lib), "%s/share/terminfo", payload);
    if (bb_path_exists(lib)) {
        const char *old_ti = getenv("TERMINFO_DIRS");
        if (old_ti && *old_ti) {
            char ti_path[PATH_MAX * 2];
            snprintf(ti_path, sizeof(ti_path), "%s:%s", lib, old_ti);
            setenv("TERMINFO_DIRS", ti_path, 1);
        } else {
            setenv("TERMINFO_DIRS", lib, 1);
        }
    }
}

static int execv_alloc(const char *path, char **argv)
{
    execv(path, argv);
    fprintf(stderr, "grit: exec %s failed: %s\n", path, strerror(errno));
    return errno == ENOENT ? 127 : 126;
}

static void payload_root_from_payload(const char *payload, char *root, size_t rootsz)
{
    size_t len;
    snprintf(root, rootsz, "%s", payload);
    len = strlen(root);
    if (len >= 8 && !strcmp(root + len - 8, "/payload"))
        root[len - 8] = '\0';
}

static volatile sig_atomic_t no_residue_signal = 0;
static volatile sig_atomic_t no_residue_child = -1;

static void no_residue_signal_handler(int sig)
{
    no_residue_signal = sig;
    if (no_residue_child > 1)
        kill((pid_t)no_residue_child, sig);
}

static void cleanup_no_residue_root(const char *root, const char *detail)
{
    const char *runtime_root = bb_config_get("GRIT_RUNTIME_ROOT");
    const char *fallback_root = bb_config_get("GRIT_RUNTIME_FALLBACK_ROOT");

    if (!root || !root[0])
        return;
    /*
     * no-residue cleanup owns only griTTYkit runtime roots.  Refuse any other
     * path before calling the shared recursive remover so interrupted payload
     * commands cannot turn a stale or malformed payload path into broad deletion.
     */
    if (strcmp(root, runtime_root) && strcmp(root, fallback_root))
        return;
    if (!strcmp(bb_config_get("GRIT_NORESIDUE_LEVEL"), "aggressive"))
        bb_ledger_record("remove", root, "runtime", "aggressive no-residue cleanup");
    else
        bb_ledger_record("remove", root, "runtime", detail);
    bb_rm_rf(root);
}

static int exec_payload_command(const char *path, char **argv, const char *payload)
{
    pid_t pid;
    int status;
    char root[PATH_MAX];
    struct sigaction sa, old_int, old_term, old_hup, old_quit;

    if (strcmp(bb_config_get("GRIT_RUNTIME_MODE"), "no-residue") != 0)
        return execv_alloc(path, argv);

    payload_root_from_payload(payload, root, sizeof(root));
    no_residue_signal = 0;

    pid = fork();
    if (pid < 0) {
        fprintf(stderr, "grit: fork %s failed: %s\n", path, strerror(errno));
        cleanup_no_residue_root(root, "no-residue fork failure");
        return 1;
    }
    if (pid == 0) {
        execv(path, argv);
        fprintf(stderr, "grit: exec %s failed: %s\n", path, strerror(errno));
        _exit(errno == ENOENT ? 127 : 126);
    }

    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = no_residue_signal_handler;
    sigemptyset(&sa.sa_mask);
    no_residue_child = pid;
    sigaction(SIGINT, &sa, &old_int);
    sigaction(SIGTERM, &sa, &old_term);
    sigaction(SIGHUP, &sa, &old_hup);
    sigaction(SIGQUIT, &sa, &old_quit);

    while (waitpid(pid, &status, 0) < 0) {
        if (errno == EINTR)
            continue;
        status = 1 << 8;
        break;
    }
    no_residue_child = -1;
    sigaction(SIGINT, &old_int, NULL);
    sigaction(SIGTERM, &old_term, NULL);
    sigaction(SIGHUP, &old_hup, NULL);
    sigaction(SIGQUIT, &old_quit, NULL);

    cleanup_no_residue_root(root, no_residue_signal ? "no-residue interrupted foreground payload command" : "no-residue foreground payload command");
    if (no_residue_signal)
        return 128 + no_residue_signal;
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    if (WIFSIGNALED(status))
        return 128 + WTERMSIG(status);
    return 1;
}

int bb_exec_payload_applet(const char *name, int argc, char **argv)
{
    char payload[PATH_MAX], exe[PATH_MAX];
    char **child;
    int i;

    if (!bb_payload_tool_supported(name)) {
        fprintf(stderr, "grit: %s: applet not found\n\n", name);
        bb_print_applet_list(stderr);
        return 127;
    }

    if (bb_ensure_payload_mode(payload, sizeof(payload), bb_payload_tool_is_heavy(name)) != 0) {
        fprintf(stderr, "grit: payload unavailable; run 'grit extract' after creating dist/payload.tar.gz\n");
        return 127;
    }
    set_payload_env(payload);

    if (bb_payload_tool_is_heavy(name)) {
        int ret;
        snprintf(exe, sizeof(exe), "%s/bin/%s", payload, name);
        child = calloc((size_t)argc + 1, sizeof(char *));
        if (!child)
            return 1;
        child[0] = (char *)name;
        for (i = 1; i < argc; i++)
            child[i] = argv[i];
        child[argc] = NULL;
        if (!strcmp(name, "zsh") || !strcmp(name, "bash"))
            setenv("SHELL", exe, 1);
        ret = exec_payload_command(exe, child, payload);
        free(child);
        return ret;
    }

    snprintf(exe, sizeof(exe), "%s/bin/busybox", payload);
    child = calloc((size_t)argc + 2, sizeof(char *));
    if (!child)
        return 1;
    child[0] = exe;
    child[1] = (char *)name;
    for (i = 1; i < argc; i++)
        child[i + 1] = argv[i];
    child[argc + 1] = NULL;
    if (strcmp(bb_config_get("GRIT_RUNTIME_MODE"), "no-residue") == 0) {
        int ret = exec_payload_command(exe, child, payload);
        free(child);
        return ret;
    }
    execv(exe, child);
    fprintf(stderr, "grit: exec BusyBox applet %s failed: %s\n", name, strerror(errno));
    free(child);
    return errno == ENOENT ? 127 : 126;
}
