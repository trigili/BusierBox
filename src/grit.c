#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "applets.h"
#include "json_helpers.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef GRIT_ENABLE_SURVEY
#define GRIT_ENABLE_SURVEY 1
#endif
#ifndef GRIT_ENABLE_DOCTOR
#define GRIT_ENABLE_DOCTOR 1
#endif
#ifndef GRIT_ENABLE_CONFIG_INFO
#define GRIT_ENABLE_CONFIG_INFO 1
#endif
#ifndef GRIT_ENABLE_EXTRACT
#define GRIT_ENABLE_EXTRACT 1
#endif
#ifndef GRIT_ENABLE_FETCH_FULL
#define GRIT_ENABLE_FETCH_FULL 1
#endif
#ifndef GRIT_ARTIFACT_TIER
#define GRIT_ARTIFACT_TIER "full"
#endif
#ifndef GRIT_ARTIFACT_KIND
#define GRIT_ARTIFACT_KIND GRIT_ARTIFACT_TIER
#endif
#ifndef GRIT_FULL_ZERO_ARG_MODE
#define GRIT_FULL_ZERO_ARG_MODE "help"
#endif
#ifndef GRIT_ZERO_ARG_MODE
#define GRIT_ZERO_ARG_MODE GRIT_FULL_ZERO_ARG_MODE
#endif
#include "effective_config.h"

const struct bb_applet bb_applets[] = {
    {"list", applet_list_main, "list native applets and payload tools"},
#if GRIT_ENABLE_SURVEY
    {"survey", applet_survey_main, "print embedded Linux triage information"},
#endif
    {"envfix", applet_envfix_main, "print or apply environment repair commands"},
#if GRIT_ENABLE_EXTRACT
    {"extract", applet_extract_main, "extract or reuse the payload runtime"},
#endif
    {"clean", applet_clean_main, "remove local extracted payload runtime"},
    {"cleanup-ledger", applet_cleanup_ledger_main, "inspect griTTYkit cleanup ledger"},
#if GRIT_ENABLE_CONFIG_INFO
    {"config-info", applet_config_info_main, "print build and payload information"},
#endif
    {"config-export", applet_config_export_main, "export rebuild-oriented artifact config"},
    {"runtime-config", applet_runtime_config_main, "print effective runtime override configuration"},
#if GRIT_ENABLE_DOCTOR
    {"doctor", applet_doctor_main, "inspect embedded and extracted payload health"},
#endif
    {"reality-test", applet_reality_test_main, "actively test target runtime capabilities"},
#if GRIT_ENABLE_FETCH_FULL
    {"fetch", applet_fetch_main, "fetch an operator-staged file"},
    {"fetch-full", applet_fetch_full_main, "download a full griTTYkit artifact"},
#endif
    {"manifest", applet_manifest_main, "print artifact manifest metadata"},
    {"persistence", applet_recovery_main, "survey and manage explicit persistence hooks"},
    {"recovery", applet_recovery_main, "deprecated alias for persistence"},
    {"rshell", applet_rshell_main, "start configured reverse shell transport"},
    {"plan", applet_plan_main, "preview filesystem, process, and network impact"},
    {"put", applet_upload_main, "upload a target file to the receive-only operator service"},
    {"upload", applet_upload_main, "alias for put"},
    {"config-push", applet_upload_main, "upload effective runtime config to the operator service"},
    {"evidence", applet_upload_main, "upload operator evidence to the receive-only service"},
    {"command-queue", applet_command_queue_main, "inspect explicit opt-in command queue status"},
};

const unsigned int bb_applet_count = sizeof(bb_applets) / sizeof(bb_applets[0]);

static const char *base_name(const char *path)
{
    const char *slash = strrchr(path, '/');
    return slash ? slash + 1 : path;
}

static void usage(FILE *out)
{
    bb_print_applet_list(out);
}

static int yes_value(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true") || !strcmp(s, "on"));
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

static int read_lock_pid(const char *lock_path, long *pid, char *mode, size_t modesz)
{
    FILE *fp = fopen(lock_path, "r");
    char key[64], val[128];
    *pid = -1;
    if (mode && modesz)
        mode[0] = '\0';
    if (!fp)
        return -1;
    while (fscanf(fp, "%63[^=]=%127s\n", key, val) == 2) {
        if (!strcmp(key, "pid"))
            *pid = strtol(val, NULL, 10);
        else if (!strcmp(key, "mode") && mode && modesz)
            snprintf(mode, modesz, "%s", val);
    }
    fclose(fp);
    return 0;
}

static const char *autorun_guard_path(void)
{
    const char *env = getenv("GRIT_AUTORUN_GUARD_PATH");
    return env && *env ? env : GRIT_AUTORUN_GUARD_PATH;
}

static void print_autorun_status(FILE *out)
{
    char lock_path[PATH_MAX], mode[128] = "";
    const char *guard_path = autorun_guard_path();
    long pid = -1;
    snprintf(lock_path, sizeof(lock_path), "%s/autorun.lock", guard_path);
    read_lock_pid(lock_path, &pid, mode, sizeof(mode));
    fprintf(out, "griTTYkit autorun already active.\n");
    fprintf(out, "  mode: %s\n", mode[0] ? mode : "unknown");
    fprintf(out, "  pid: %ld\n", pid);
    fprintf(out, "  guard: %s\n\n", guard_path);
    fprintf(out, "Explicit commands still work:\n");
    fprintf(out, "  grit doctor\n");
    fprintf(out, "  grit --help\n");
}

static int reentry_action(void)
{
    char *doctor_argv[] = { "doctor", NULL };
    if (!strcmp(GRIT_AUTORUN_REENTRY_ACTION, "doctor"))
        return applet_doctor_main(1, doctor_argv);
    if (!strcmp(GRIT_AUTORUN_REENTRY_ACTION, "help") || !strcmp(GRIT_AUTORUN_REENTRY_ACTION, "menu")) {
        usage(stdout);
        return 0;
    }
    print_autorun_status(stdout);
    return 0;
}

static int guard_needed(const char *mode)
{
    return !strcmp(mode, "rshell") || !strcmp(mode, "custom") || !strcmp(mode, "shell");
}

static int acquire_autorun_guard(const char *mode)
{
    char lock_path[PATH_MAX], status_path[PATH_MAX], old_mode[128] = "";
    const char *guard_path = autorun_guard_path();
    long old_pid = -1;
    int fd;
    time_t now;
    if (!yes_value(GRIT_AUTORUN_GUARD_ENABLE) || !guard_needed(mode) ||
        !strcmp(GRIT_AUTORUN_REENTRY_ACTION, "bootstrap-again"))
        return 1;
    if (bb_mkdir_p(guard_path, 0700) != 0) {
        fprintf(stderr, "autorun: unable to create guard path %s: %s\n", guard_path, strerror(errno));
        return 0;
    }
    bb_ledger_record("mkdir", guard_path, "runtime", "autorun guard path");
    snprintf(lock_path, sizeof(lock_path), "%s/autorun.lock", guard_path);
retry:
    fd = open(lock_path, O_CREAT | O_EXCL | O_WRONLY, 0600);
    if (fd < 0) {
        if (errno == EEXIST) {
            if (read_lock_pid(lock_path, &old_pid, old_mode, sizeof(old_mode)) == 0 &&
                old_pid > 0 && kill((pid_t)old_pid, 0) != 0 && errno == ESRCH &&
                !strcmp(GRIT_AUTORUN_STALE_LOCK_POLICY, "recover")) {
                unlink(lock_path);
                goto retry;
            }
            reentry_action();
            return 0;
        }
        fprintf(stderr, "autorun: unable to create lock %s: %s\n", lock_path, strerror(errno));
        return 0;
    }
    now = time(NULL);
    dprintf(fd, "mode=%s\npid=%ld\nstarted_at=%ld\nartifact_tier=%s\n", mode, (long)getpid(), (long)now, GRIT_ARTIFACT_TIER);
    close(fd);
    bb_ledger_record("write", lock_path, "runtime", "autorun lock");
    snprintf(status_path, sizeof(status_path), "%s/status", guard_path);
    fd = open(status_path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (fd >= 0) {
        dprintf(fd, "mode=%s\npid=%ld\nstarted_at=%ld\nartifact_tier=%s\n", mode, (long)getpid(), (long)now, GRIT_ARTIFACT_TIER);
        close(fd);
        bb_ledger_record("write", status_path, "runtime", "autorun status");
    }
    return 1;
}


static int run_custom_zero_arg(void)
{
    int rc;
    if (!GRIT_ZERO_ARG_CUSTOM_COMMAND[0]) {
        fputs("zero-arg custom mode selected but GRIT_ZERO_ARG_CUSTOM_COMMAND is empty\n", stderr);
        return 2;
    }
    rc = system(GRIT_ZERO_ARG_CUSTOM_COMMAND);
    if (rc == -1)
        return 1;
    if (WIFEXITED(rc))
        return WEXITSTATUS(rc);
    return 1;
}

static int run_zero_arg_mode(const char *mode)
{
    char *rshell_argv[] = { "rshell", NULL };
    char *survey_argv[] = { "survey", NULL };

    if (!mode || !*mode || !strcmp(mode, "help") || !strcmp(mode, "menu") ||
        !strcmp(mode, "doctor")) {
        usage(!mode || !*mode || !strcmp(mode, "help") ? stderr : stdout);
        return !mode || !*mode || !strcmp(mode, "help") ? 2 : 0;
    }
    if (!strcmp(mode, "survey"))
        return applet_survey_main(1, survey_argv);
    if (!strcmp(mode, "rshell")) {
        setenv("GRIT_ZERO_ARG_CONTEXT", "1", 1);
        return applet_rshell_main(1, rshell_argv);
    }
    if (!strcmp(mode, "custom"))
        return run_custom_zero_arg();
    fprintf(stderr, "unknown zero-arg mode: %s\n", mode);
    usage(stderr);
    return 2;
}

static const char *zero_arg_log_mode(void)
{
    const char *mode = getenv("GRIT_ZERO_ARG_LOG_MODE");
    return (mode && *mode) ? mode : GRIT_ZERO_ARG_LOG_MODE;
}

static int zero_arg_log_at_least_status(const char *log_mode)
{
    return !strcmp(log_mode, "status") || !strcmp(log_mode, "verbose");
}

static int zero_arg_log_verbose(const char *log_mode)
{
    return !strcmp(log_mode, "verbose");
}

static int zero_arg_main(void)
{
    const char *mode = getenv("GRIT_ZERO_ARG_MODE");
    const char *log_mode = zero_arg_log_mode();
    int rc;
    if (!mode || !*mode) {
        mode = GRIT_ZERO_ARG_MODE;
    }
    if (getenv("GRIT_NO_AUTORUN") && !strcmp(getenv("GRIT_NO_AUTORUN"), "1")) {
        usage(stdout);
        return 0;
    }
    if (!strcmp(log_mode, "none")) {
        int _devnull = open("/dev/null", O_WRONLY);
        if (_devnull >= 0) {
            dup2(_devnull, STDOUT_FILENO);
            dup2(_devnull, STDERR_FILENO);
            close(_devnull);
        }
    }
    if (!acquire_autorun_guard(mode))
        return 0;
    if (zero_arg_log_at_least_status(log_mode))
        fprintf(stderr, "grit: zero-arg mode=%s\n", mode);
    if (zero_arg_log_verbose(log_mode))
        fprintf(stderr, "grit: zero-arg log_mode=%s runtime=%s\n", log_mode, GRIT_RUNTIME_MODE);
    rc = run_zero_arg_mode(mode);
    if (zero_arg_log_at_least_status(log_mode))
        fprintf(stderr, "grit: zero-arg exit=%d\n", rc);
    return rc;
}

int main(int argc, char **argv)
{
    const char *invoked;
    int rc;

    if (argc < 1 || !argv || !argv[0]) {
        usage(stderr);
        return 2;
    }
    bb_set_argv0(argv[0]);

    invoked = base_name(argv[0]);
    if (strcmp(invoked, "grit") != 0 && strncmp(invoked, "grit-", 5) != 0) {
        rc = bb_dispatch(invoked, argc, argv);
        if (rc >= 0)
            return rc;
        if (argc >= 2 &&
            (strcmp(argv[1], "persistence") == 0 || strcmp(argv[1], "recovery") == 0)) {
            rc = bb_dispatch(argv[1], argc - 1, argv + 1);
            if (rc >= 0)
                return rc;
        }
        return bb_exec_payload_applet(invoked, argc, argv);
    }

    if (argc < 2)
        return zero_arg_main();

    if (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0) {
        usage(argc < 2 ? stderr : stdout);
        return 0;
    }

    rc = bb_dispatch(argv[1], argc - 1, argv + 1);
    if (rc >= 0)
        return rc;

    return bb_exec_payload_applet(argv[1], argc - 1, argv + 1);
}
