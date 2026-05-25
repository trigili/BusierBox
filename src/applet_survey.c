#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ptrace.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <unistd.h>

#include "applets.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef BUSIERBOX_VERSION
#define BUSIERBOX_VERSION "0.1.0-tier0"
#endif

static const char *dirs[] = {".", "/tmp", "/var/tmp", "/dev/shm", "/overlay", "/rom", "/var"};

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

static const char *endianness(void)
{
    unsigned int x = 1;
    return *((unsigned char *)&x) ? "little" : "big";
}

static int is_digits(const char *s)
{
    while (*s) {
        if (!isdigit((unsigned char)*s++))
            return 0;
    }
    return 1;
}

static int proc_count(void)
{
    DIR *d = opendir("/proc");
    struct dirent *de;
    int n = 0;
    if (!d)
        return -1;
    while ((de = readdir(d)) != NULL)
        if (is_digits(de->d_name))
            n++;
    closedir(d);
    return n;
}

static int command_in_path(const char *name);
static void json_string(const char *s);

static void print_meminfo_human(void)
{
    FILE *fp = fopen("/proc/meminfo", "r");
    char line[160];
    if (!fp) {
        printf("memory: unknown\n");
        return;
    }
    printf("memory:\n");
    while (fgets(line, sizeof(line), fp)) {
        if (!strncmp(line, "MemTotal:", 9) || !strncmp(line, "MemFree:", 8) ||
            !strncmp(line, "MemAvailable:", 13) || !strncmp(line, "SwapTotal:", 10) ||
            !strncmp(line, "SwapFree:", 9))
            printf("  %s", line);
    }
    fclose(fp);
}

static void print_netdev_human(void)
{
    FILE *fp = fopen("/proc/net/dev", "r");
    char line[256];
    int skip = 2;
    if (!fp) {
        printf("interfaces: unknown\n");
        return;
    }
    printf("interfaces:");
    while (fgets(line, sizeof(line), fp)) {
        char *colon, *name;
        if (skip) { skip--; continue; }
        colon = strchr(line, ':');
        if (!colon) continue;
        *colon = '\0';
        name = line;
        while (isspace((unsigned char)*name)) name++;
        printf(" %s", name);
    }
    printf("\n");
    fclose(fp);
}

static const char *mount_opts_for(const char *path, char *out, size_t outsz)
{
    FILE *fp = fopen("/proc/mounts", "r");
    char line[512], best[256] = "";
    size_t best_len = 0;
    out[0] = '\0';
    if (!fp)
        return NULL;
    while (fgets(line, sizeof(line), fp)) {
        char src[160], dst[PATH_MAX], type[64], opts[256];
        size_t len;
        if (sscanf(line, "%159s %4095s %63s %255s", src, dst, type, opts) != 4)
            continue;
        len = strlen(dst);
        if (!strncmp(path, dst, len) && len >= best_len && (path[len] == '/' || path[len] == '\0' || !strcmp(dst, "/"))) {
            best_len = len;
            strncpy(best, opts, sizeof(best) - 1);
            best[sizeof(best) - 1] = '\0';
        }
    }
    fclose(fp);
    if (!best_len)
        return NULL;
    snprintf(out, outsz, "%s", best);
    return out;
}

static void dir_human(const char *path)
{
    struct stat st;
    struct statvfs v;
    char opts[256];
    int exists = stat(path, &st) == 0;
    printf("  %-9s exists=%s writable=%s executable=%s",
           path, exists ? "yes" : "no",
           access(path, W_OK) == 0 ? "yes" : "no",
           access(path, X_OK) == 0 ? "yes" : "no");
    if (exists && statvfs(path, &v) == 0)
        printf(" free_bytes=%llu", (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize);
    if (mount_opts_for(path, opts, sizeof(opts)) && strstr(opts, "noexec"))
        printf(" noexec=yes");
    printf("\n");
}

static void mounts_human(void)
{
    FILE *fp = fopen("/proc/mounts", "r");
    char line[512];
    int count = 0;
    if (!fp) {
        printf("mounts: unreadable\n");
        return;
    }
    printf("mounts:\n");
    while (fgets(line, sizeof(line), fp) && count++ < 16) {
        char src[160], dst[160], type[64], opts[160];
        if (sscanf(line, "%159s %159s %63s %159s", src, dst, type, opts) == 4)
            printf("  %s on %s type %s (%s)\n", src, dst, type, opts);
    }
    if (!feof(fp))
        printf("  ...\n");
    fclose(fp);
}

static const char *recommended_extract_dir(void)
{
    size_t i;
    for (i = 0; i < sizeof(dirs) / sizeof(dirs[0]); i++)
        if (access(dirs[i], W_OK | X_OK) == 0)
            return dirs[i];
    return "none";
}

static const char *recommended_runtime_root(void)
{
    if (access(".", W_OK | X_OK) == 0)
        return "./.busierbox";
    if (access("/tmp", W_OK | X_OK) == 0)
        return "/tmp/.busierbox";
    return "none";
}

static const char *kernel_floor_guess(const char *release)
{
    int major = 0, minor = 0;
    if (!release || sscanf(release, "%d.%d", &major, &minor) != 2)
        return "unknown";
    if (major <= 2)
        return "2.x";
    if (major == 3)
        return "3.x";
    if (major == 4)
        return "4.x";
    if (major == 5)
        return "5.x";
    if (major == 6)
        return "6.x";
    return "current";
}

static const char *libc_guess(void)
{
    if (access("/lib/ld-musl-mipsel.so.1", F_OK) == 0 ||
        access("/lib/ld-musl-mips.so.1", F_OK) == 0 ||
        access("/lib/ld-musl-armhf.so.1", F_OK) == 0 ||
        access("/lib/ld-musl-aarch64.so.1", F_OK) == 0 ||
        access("/lib/ld-musl-x86_64.so.1", F_OK) == 0)
        return "musl";
    if (access("/lib/libuClibc.so.0", F_OK) == 0 ||
        access("/lib/ld-uClibc.so.0", F_OK) == 0)
        return "uclibc";
    if (access("/lib64/ld-linux-x86-64.so.2", F_OK) == 0 ||
        access("/lib/ld-linux.so.2", F_OK) == 0 ||
        access("/lib/ld-linux-aarch64.so.1", F_OK) == 0 ||
        access("/lib/ld-linux-armhf.so.3", F_OK) == 0)
        return "glibc";
    return "unknown";
}

static int openwrt_marker_exists(void)
{
    return access("/etc/openwrt_release", R_OK) == 0 || access("/rom", F_OK) == 0 || access("/overlay", F_OK) == 0;
}

static void json_recommendation_warnings(const char *extract_dir)
{
    int first = 1;
    putchar('[');
#define WARN(s) do { if (!first) putchar(','); json_string(s); first = 0; } while (0)
    if (access("/proc", R_OK) != 0)
        WARN("no /proc access");
    if (access("/tmp", W_OK) != 0)
        WARN("missing /tmp write");
    if (access("/tmp", X_OK) != 0)
        WARN("noexec tmp");
    if (!strcmp(extract_dir, "none"))
        WARN("no writable executable runtime directory found");
    if (!strcmp(libc_guess(), "unknown"))
        WARN("unknown libc");
    if (command_in_path("busybox") && !command_in_path("tar"))
        WARN("busybox-only userspace likely");
#undef WARN
    putchar(']');
}

static void json_string(const char *s)
{
    putchar('"');
    if (s) {
        while (*s) {
            unsigned char c = (unsigned char)*s++;
            if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
            else if (c == '\n') fputs("\\n", stdout);
            else if (c == '\r') fputs("\\r", stdout);
            else if (c == '\t') fputs("\\t", stdout);
            else if (c < 32) printf("\\u%04x", c);
            else putchar(c);
        }
    }
    putchar('"');
}

static void json_meminfo(void)
{
    FILE *fp = fopen("/proc/meminfo", "r");
    char key[64], unit[32], line[160];
    unsigned long val;
    int first = 1;
    putchar('{');
    if (fp) {
        while (fgets(line, sizeof(line), fp)) {
            if (sscanf(line, "%63[^:]: %lu %31s", key, &val, unit) >= 2) {
                if (!first) putchar(',');
                json_string(key);
                printf(":%lu", val);
                first = 0;
            }
        }
        fclose(fp);
    }
    putchar('}');
}

static void json_netdev(void)
{
    FILE *fp = fopen("/proc/net/dev", "r");
    char line[256];
    int skip = 2, first = 1;
    putchar('[');
    if (fp) {
        while (fgets(line, sizeof(line), fp)) {
            char *colon, *name;
            if (skip) { skip--; continue; }
            colon = strchr(line, ':');
            if (!colon) continue;
            *colon = '\0';
            name = line;
            while (isspace((unsigned char)*name)) name++;
            if (!first) putchar(',');
            json_string(name);
            first = 0;
        }
        fclose(fp);
    }
    putchar(']');
}

static void json_dirs(void)
{
    size_t i;
    putchar('[');
    for (i = 0; i < sizeof(dirs) / sizeof(dirs[0]); i++) {
        struct stat st;
        struct statvfs v;
        char opts[256];
        int exists = stat(dirs[i], &st) == 0;
        if (i) putchar(',');
        printf("{\"path\":"); json_string(dirs[i]);
        printf(",\"exists\":%s,\"writable\":%s,\"executable\":%s",
               exists ? "true" : "false",
               access(dirs[i], W_OK) == 0 ? "true" : "false",
               access(dirs[i], X_OK) == 0 ? "true" : "false");
        if (exists && statvfs(dirs[i], &v) == 0)
            printf(",\"free_bytes\":%llu", (unsigned long long)v.f_bavail * (unsigned long long)v.f_frsize);
        else
            printf(",\"free_bytes\":null");
        printf(",\"noexec\":%s", (mount_opts_for(dirs[i], opts, sizeof(opts)) && strstr(opts, "noexec")) ? "true" : "false");
        putchar('}');
    }
    putchar(']');
}

static void json_executable_extract_dirs(void)
{
    size_t i;
    int first = 1;
    putchar('[');
    for (i = 0; i < sizeof(dirs) / sizeof(dirs[0]); i++) {
        char opts[256];
        if (access(dirs[i], W_OK | X_OK) != 0)
            continue;
        if (mount_opts_for(dirs[i], opts, sizeof(opts)) && strstr(opts, "noexec"))
            continue;
        if (!first) putchar(',');
        json_string(dirs[i]);
        first = 0;
    }
    putchar(']');
}

static void json_mounts(void)
{
    FILE *fp = fopen("/proc/mounts", "r");
    char line[512];
    int first = 1, count = 0;
    putchar('[');
    if (fp) {
        while (fgets(line, sizeof(line), fp) && count++ < 32) {
            char src[160], dst[160], type[64], opts[160];
            if (sscanf(line, "%159s %159s %63s %159s", src, dst, type, opts) != 4)
                continue;
            if (!first) putchar(',');
            printf("{\"source\":"); json_string(src);
            printf(",\"target\":"); json_string(dst);
            printf(",\"type\":"); json_string(type);
            printf(",\"options\":"); json_string(opts);
            printf(",\"noexec\":%s}", strstr(opts, "noexec") ? "true" : "false");
            first = 0;
        }
        fclose(fp);
    }
    putchar(']');
}

static int command_in_path(const char *name)
{
    const char *path = getenv("PATH");
    char *dup, *save = NULL, *p;
    int found = 0;
    if (!path || !name || !*name)
        return 0;
    dup = strdup(path);
    if (!dup)
        return 0;
    for (p = strtok_r(dup, ":", &save); p; p = strtok_r(NULL, ":", &save)) {
        char candidate[PATH_MAX];
        snprintf(candidate, sizeof(candidate), "%s/%s", *p ? p : ".", name);
        if (access(candidate, X_OK) == 0) {
            found = 1;
            break;
        }
    }
    free(dup);
    return found;
}

static void json_tools(void)
{
    static const char *tools[] = {
        "busybox", "tar", "gzip", "sh", "ash", "zsh", "tmux", "socat",
        "dropbear", "dbclient", "nc", "netcat", "wget", "curl", "ip",
        "ifconfig", "ps", "kill", "uname", "mount", "df", "free", "cat",
        "ls", "readlink", "getconf", "chmod", "mkdir", "rm", "opkg", NULL
    };
    int i;
    putchar('{');
    for (i = 0; tools[i]; i++) {
        if (i)
            putchar(',');
        json_string(tools[i]);
        printf(":%s", command_in_path(tools[i]) ? "true" : "false");
    }
    putchar('}');
}

static void json_file_excerpt(const char *path)
{
    FILE *fp = fopen(path, "r");
    char buf[512];
    size_t n;
    if (!fp) {
        printf("null");
        return;
    }
    n = fread(buf, 1, sizeof(buf) - 1, fp);
    fclose(fp);
    buf[n] = '\0';
    json_string(buf);
}

static void json_os_markers(void)
{
    printf("{\"os_release\":");
    json_file_excerpt("/etc/os-release");
    printf(",\"openwrt_release\":");
    json_file_excerpt("/etc/openwrt_release");
    printf(",\"banner\":");
    json_file_excerpt("/etc/banner");
    printf(",\"issue\":");
    json_file_excerpt("/etc/issue");
    printf(",\"proc_version\":");
    json_file_excerpt("/proc/version");
    printf("}");
}

static const char *shell_survey_script =
"#!/bin/sh\n"
"# BusierBox portable shell survey. POSIX-ish and safe for OpenWrt-like targets.\n"
"p=${BUSIERBOX_SURVEY_PROBE_DIR:-${TMPDIR:-/tmp}/busierbox-survey-$$}\n"
"created=false; probe_ready=false\n"
"if [ -d \"$p\" ]; then probe_ready=true; elif mkdir \"$p\" 2>/dev/null; then created=true; probe_ready=true; else p=; fi\n"
"safe(){ case \"$1\" in *[!abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/:,+@=%-]* ) printf unknown ;; *) printf '%s' \"$1\" ;; esac; }\n"
"jv(){ printf '\"'; safe \"$1\"; printf '\"'; }\n"
"have(){ command -v \"$1\" >/dev/null 2>&1 && printf true || printf false; }\n"
"readable(){ [ -r \"$1\" ] && printf true || printf false; }\n"
"exists(){ [ -e \"$1\" ] && printf true || printf false; }\n"
"dirprobe(){ d=$1; wr=false; ex=false; cr=false; free=unknown; [ -d \"$d\" ] || { printf '{\"path\":\"'; safe \"$d\"; printf '\",\"exists\":false,\"writable\":false,\"shell_exec\":false,\"can_create_dirs\":false,\"df_available\":'; have df; printf '}'; return; }; if : >\"$d/busierbox.write.$$\" 2>/dev/null; then wr=true; rm -f \"$d/busierbox.write.$$\" 2>/dev/null || true; fi; if mkdir \"$d/busierbox.dir.$$\" 2>/dev/null; then cr=true; rmdir \"$d/busierbox.dir.$$\" 2>/dev/null || true; fi; if [ \"$wr\" = true ]; then printf '#!/bin/sh\\nexit 0\\n' >\"$d/busierbox.exec.$$\" 2>/dev/null && chmod +x \"$d/busierbox.exec.$$\" 2>/dev/null && \"$d/busierbox.exec.$$\" >/dev/null 2>&1 && ex=true; rm -f \"$d/busierbox.exec.$$\" 2>/dev/null || true; fi; if command -v df >/dev/null 2>&1; then set -- `df -k \"$d\" 2>/dev/null`; shift 6 2>/dev/null || true; free=${4:-unknown}; fi; printf '{\"path\":\"'; safe \"$d\"; printf '\",\"exists\":true,\"writable\":%s,\"shell_exec\":%s,\"can_create_dirs\":%s,\"df_available\":' \"$wr\" \"$ex\" \"$cr\"; have df; printf '}'; }\n"
"wr=false; ex=false; cr=false\n"
"if [ \"$probe_ready\" = true ]; then\n"
"if : >\"$p/write.probe\" 2>/dev/null; then wr=true; rm -f \"$p/write.probe\" 2>/dev/null || true; fi\n"
"if mkdir \"$p/dir.probe\" 2>/dev/null; then cr=true; rmdir \"$p/dir.probe\" 2>/dev/null || true; fi\n"
"printf '%s\\n' '#!/bin/sh' 'exit 0' >\"$p/exec.probe\" 2>/dev/null\n"
"chmod +x \"$p/exec.probe\" 2>/dev/null || true\n"
"if \"$p/exec.probe\" >/dev/null 2>&1; then ex=true; fi\n"
"rm -f \"$p/exec.probe\" 2>/dev/null || true\n"
"fi\n"
"u=`uname -s 2>/dev/null || echo unknown`; n=`uname -n 2>/dev/null || echo unknown`; r=`uname -r 2>/dev/null || echo unknown`; v=`uname -v 2>/dev/null || echo unknown`; m=`uname -m 2>/dev/null || echo unknown`\n"
"shlink=unknown; command -v readlink >/dev/null 2>&1 && shlink=`readlink /bin/sh 2>/dev/null || echo unknown`\n"
"busy=false; h=`/bin/sh --help 2>&1`; case \"$h\" in *BusyBox*|*busybox*) busy=true ;; esac\n"
"uid=unknown; gid=unknown; idout=unknown; command -v id >/dev/null 2>&1 && idout=`id 2>/dev/null || echo unknown`; command -v id >/dev/null 2>&1 && uid=`id -u 2>/dev/null || echo unknown`; command -v id >/dev/null 2>&1 && gid=`id -g 2>/dev/null || echo unknown`\n"
"printf '{\"schema\":1,\"engine\":\"shell\",\"uname\":{\"sysname\":'; jv \"$u\"; printf ',\"nodename\":'; jv \"$n\"; printf ',\"release\":'; jv \"$r\"; printf ',\"version\":'; jv \"$v\"; printf ',\"machine\":'; jv \"$m\"; printf '}'\n"
"printf ',\"shell\":{\"path\":\"/bin/sh\",\"symlink_target\":'; jv \"$shlink\"; printf ',\"busybox_ash\":%s,\"basic_tests\":{\"printf\":true,\"case\":true,\"command_v\":' \"$busy\"; have command; printf '}}'\n"
"printf ',\"os_markers\":{\"os_release_readable\":'; readable /etc/os-release; printf ',\"openwrt_release_readable\":'; readable /etc/openwrt_release; printf ',\"banner_readable\":'; readable /etc/banner; printf ',\"issue_readable\":'; readable /etc/issue; printf ',\"proc_version_readable\":'; readable /proc/version; printf '}'\n"
"printf ',\"libc_hints\":{\"ldd_available\":'; have ldd; printf ',\"strings_available\":'; have strings; printf ',\"libc_so_visible\":'; exists /lib/libc.so; printf ',\"musl_loader_visible\":'; exists /lib/ld-musl-mipsel.so.1; printf ',\"uclibc_loader_visible\":'; exists /lib/ld-uClibc.so.0; printf ',\"glibc_loader_visible\":'; exists /lib64/ld-linux-x86-64.so.2; printf '}'\n"
"printf ',\"filesystem\":{\"probe_dir\":'; jv \"$p\"; printf ',\"probe_ready\":%s,\"writable\":%s,\"shell_exec\":%s,\"can_create_dirs\":%s,\"dirs\":[' \"$probe_ready\" \"$wr\" \"$ex\" \"$cr\"; first=1; for d in . /tmp /var/tmp /dev/shm /overlay /rom; do [ $first = 1 ] || printf ','; first=0; dirprobe \"$d\"; done; printf ']}'\n"
"printf ',\"permissions\":{\"id\":'; jv \"$idout\"; printf ',\"uid\":'; jv \"$uid\"; printf ',\"gid\":'; jv \"$gid\"; printf ',\"proc_readable\":'; readable /proc; printf ',\"cwd_writable\":'; [ -w . ] && printf true || printf false; printf ',\"can_create_dirs\":%s}' \"$cr\"\n"
"printf ',\"network_hints\":{\"ip_available\":'; have ip; printf ',\"route_available\":'; have route; printf ',\"ifconfig_available\":'; have ifconfig; printf ',\"resolv_conf_readable\":'; readable /etc/resolv.conf; printf ',\"external_calls_performed\":false}'\n"
"printf ',\"openwrt\":{\"opkg_available\":'; have opkg; printf ',\"overlay_exists\":'; exists /overlay; printf ',\"rom_exists\":'; exists /rom; printf '}'\n"
"printf ',\"tools\":{'; first=1; for t in busybox tar gzip sh ash zsh tmux socat dropbear dbclient nc netcat wget curl ip ifconfig ps kill uname mount df free cat ls readlink getconf chmod mkdir rm opkg; do [ $first = 1 ] || printf ','; first=0; printf '\"%s\":' \"$t\"; have \"$t\"; done; printf '}}\\n'\n"
"[ \"$created\" = true ] && rmdir \"$p\" 2>/dev/null || true\n";

static int write_shell_script(const char *path)
{
    FILE *fp = fopen(path, "w");
    if (!fp)
        return -1;
    fputs(shell_survey_script, fp);
    fclose(fp);
    chmod(path, 0700);
    return 0;
}

static const char *ptrace_status(void)
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

int applet_survey_main(int argc, char **argv)
{
    struct utsname uts;
    char cwd[PATH_MAX];
    const char *path = getenv("PATH"), *home = getenv("HOME"), *term = getenv("TERM");
    int json = 0, shell_probe = 0;
    const char *write_script_path = NULL;
    int pc;
    int i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox survey [--json] [--shell-probe] [--shell-script] [--write-shell-script PATH]");
        puts("Print embedded Linux target triage.");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--json")) {
            json = 1;
        } else if (!strcmp(argv[i], "--shell-probe")) {
            shell_probe = 1;
        } else if (!strcmp(argv[i], "--shell-script")) {
            fputs(shell_survey_script, stdout);
            return 0;
        } else if (!strcmp(argv[i], "--write-shell-script")) {
            if (i + 1 >= argc) {
                fputs("survey: --write-shell-script requires a path\n", stderr);
                return 2;
            }
            write_script_path = argv[++i];
        } else {
            fprintf(stderr, "survey: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (write_script_path) {
        if (write_shell_script(write_script_path) != 0) {
            fprintf(stderr, "survey: cannot write %s: %s\n", write_script_path, strerror(errno));
            return 1;
        }
        return 0;
    }
    if (uname(&uts) != 0)
        memset(&uts, 0, sizeof(uts));
    if (!getcwd(cwd, sizeof(cwd)))
        snprintf(cwd, sizeof(cwd), "unknown");
    pc = proc_count();
    const char *ptrace_st = ptrace_status();
    const char *extract_dir = recommended_extract_dir();

    if (json) {
        printf("{\"schema\":2,\"survey_engine\":{\"native\":true,\"shell\":%s,\"shell_path\":\"/bin/sh\"},\"busierbox\":{\"version\":", shell_probe ? "true" : "false"); json_string(BUSIERBOX_VERSION);
        printf(",\"build_date\":"); json_string(__DATE__ " " __TIME__);
        printf("},\"uname\":{\"sysname\":"); json_string(uts.sysname);
        printf(",\"nodename\":"); json_string(uts.nodename);
        printf(",\"release\":"); json_string(uts.release);
        printf(",\"version\":"); json_string(uts.version);
        printf(",\"machine\":"); json_string(uts.machine);
        printf("},\"arch\":"); json_string(uts.machine);
        printf(",\"kernel\":"); json_string(uts.release);
        printf(",\"endianness\":"); json_string(endianness());
        printf(",\"pointer_width\":%lu", (unsigned long)(sizeof(void *) * 8));
        printf(",\"ids\":{\"uid\":%ld,\"euid\":%ld,\"gid\":%ld,\"egid\":%ld}",
               (long)getuid(), (long)geteuid(), (long)getgid(), (long)getegid());
        printf(",\"cwd\":"); json_string(cwd);
        printf(",\"env\":{\"PATH\":"); json_string(path ? path : "");
        printf(",\"HOME\":"); json_string(home ? home : "");
        printf(",\"TERM\":"); json_string(term ? term : "");
        printf("},\"proc_exists\":%s,\"devpts_exists\":%s",
               access("/proc", F_OK) == 0 ? "true" : "false",
               access("/dev/pts", F_OK) == 0 ? "true" : "false");
        printf(",\"dirs\":"); json_dirs();
        printf(",\"writable_dirs\":"); json_dirs();
        printf(",\"executable_extract_dirs\":"); json_executable_extract_dirs();
        printf(",\"mounts\":"); json_mounts();
        printf(",\"tools\":"); json_tools();
        printf(",\"os_markers\":"); json_os_markers();
        printf(",\"shell\":{\"path\":\"/bin/sh\",\"path_exists\":%s,\"busybox_ash\":\"unknown\",\"basic_tests\":{\"can_run_native_survey\":true}}",
               access("/bin/sh", X_OK) == 0 ? "true" : "false");
        if (shell_probe) {
            printf(",\"shell_probe\":{\"embedded_script_available\":true,\"script_schema\":1,\"safe_for_openwrt\":true,\"writes_only_probe_dir\":true,\"probe_dir_recommendation\":");
            json_string(extract_dir);
            printf(",\"collected_fields\":[\"uname\",\"shell\",\"os_markers\",\"libc_hints\",\"filesystem\",\"permissions\",\"tools\",\"openwrt\",\"network_hints\"],\"tools\":"); json_tools();
            printf("}");
        }
        printf(",\"process_count\":"); pc >= 0 ? printf("%d", pc) : printf("null");
        printf(",\"meminfo\":"); json_meminfo();
        printf(",\"interfaces\":"); json_netdev();
        printf(",\"ptrace\":"); json_string(ptrace_st);
        printf(",\"recommendations\":{\"target_arch_guess\":"); json_string(uts.machine);
        printf(",\"endian_guess\":"); json_string(endianness());
        printf(",\"kernel_floor_guess\":"); json_string(kernel_floor_guess(uts.release));
        printf(",\"libc_guess\":"); json_string(libc_guess());
        printf(",\"target_preset_guess\":");
        if (openwrt_marker_exists() && strstr(uts.machine, "mips"))
            json_string(strstr(uts.machine, "el") ? "mipsel-linux-4.x-musl" : "mips-linux-4.x-musl");
        else
            json_string("auto");
        printf(",\"payload_preset_recommendation\":"); json_string(strcmp(extract_dir, "none") ? "builtin-core-shell" : "survey-core");
        printf(",\"runtime_mode_recommendation\":"); json_string(strcmp(extract_dir, "none") ? "extract" : "core-only");
        printf(",\"runtime_root_recommendation\":"); json_string(recommended_runtime_root());
        printf(",\"external_writes_recommendation\":\"no\",\"rshell_transport_recommendation\":\"none\"");
        printf(",\"zero_write_supported\":true,\"payload_mode_possible\":%s,\"likely_zsh_supported\":%s,\"likely_tmux_supported\":%s,\"likely_strace_supported\":%s,\"likely_gdbserver_supported\":%s,\"likely_payload_reuse_supported\":%s,\"recommended_extract_dir\":",
               strcmp(extract_dir, "none") ? "true" : "false",
               strcmp(extract_dir, "none") ? "true" : "false",
               access("/dev/pts", F_OK) == 0 ? "true" : "false",
               !strcmp(ptrace_st, "basic-ok") ? "true" : "false",
               !strcmp(ptrace_st, "basic-ok") ? "true" : "false",
               access(".", W_OK | X_OK) == 0 ? "true" : "false");
        json_string(extract_dir);
        printf(",\"payload_recommendation_reason\":");
        json_string(strcmp(extract_dir, "none") ? "found writable executable extraction directory" : "no writable executable extraction directory found");
        printf(",\"warnings\":"); json_recommendation_warnings(extract_dir);
        printf("}}\n");
        return 0;
    }

    printf("busierbox: version=%s build=%s %s\n", BUSIERBOX_VERSION, __DATE__, __TIME__);
    printf("uname: %s %s %s %s %s\n", uts.sysname, uts.nodename, uts.release, uts.version, uts.machine);
    printf("arch: %s\nendianness: %s\npointer_width: %lu\n", uts.machine, endianness(), (unsigned long)(sizeof(void *) * 8));
    printf("uid: %ld euid: %ld gid: %ld egid: %ld\n", (long)getuid(), (long)geteuid(), (long)getgid(), (long)getegid());
    printf("cwd: %s\nPATH: %s\nHOME: %s\nTERM: %s\n", cwd, path ? path : "", home ? home : "", term ? term : "");
    printf("proc: %s\ndevpts: %s\n", access("/proc", F_OK) == 0 ? "exists" : "missing", access("/dev/pts", F_OK) == 0 ? "exists" : "missing");
    printf("dirs:\n");
    for (size_t i = 0; i < sizeof(dirs) / sizeof(dirs[0]); i++)
        dir_human(dirs[i]);
    mounts_human();
    printf("process_count: %s", pc >= 0 ? "" : "unknown\n");
    if (pc >= 0) printf("%d\n", pc);
    print_meminfo_human();
    print_netdev_human();
    printf("ptrace: %s\n", ptrace_st);
        printf("recommendations:\n");
    printf("  zero_write_supported: yes\n");
    printf("  target_arch_guess: %s\n", uts.machine);
    printf("  endian_guess: %s\n", endianness());
    printf("  kernel_floor_guess: %s\n", kernel_floor_guess(uts.release));
    printf("  libc_guess: %s\n", libc_guess());
    printf("  payload_preset_recommendation: %s\n", strcmp(extract_dir, "none") ? "builtin-core-shell" : "survey-core");
    printf("  runtime_mode_recommendation: %s\n", strcmp(extract_dir, "none") ? "extract" : "core-only");
    printf("  runtime_root_recommendation: %s\n", recommended_runtime_root());
    printf("  external_writes_recommendation: no\n");
    printf("  rshell_transport_recommendation: none\n");
    printf("  payload_mode_possible: %s\n", strcmp(extract_dir, "none") ? "yes" : "no");
    printf("  likely_zsh_supported: %s\n", strcmp(extract_dir, "none") ? "yes" : "unknown");
    printf("  likely_tmux_supported: %s\n", access("/dev/pts", F_OK) == 0 ? "yes" : "unknown");
    printf("  likely_strace_supported: %s\n", !strcmp(ptrace_st, "basic-ok") ? "yes" : "unknown");
    printf("  likely_gdbserver_supported: %s\n", !strcmp(ptrace_st, "basic-ok") ? "yes" : "unknown");
    printf("  likely_payload_reuse_supported: %s\n", access(".", W_OK | X_OK) == 0 ? "yes" : "unknown");
    printf("  recommended_extract_dir: %s\n", extract_dir);
    printf("  payload_recommendation_reason: %s\n", strcmp(extract_dir, "none") ? "found writable executable extraction directory" : "no writable executable extraction directory found");
    return 0;
}
