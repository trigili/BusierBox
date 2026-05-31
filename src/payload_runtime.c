#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "applets.h"
#include "effective_config.h"
#include "payload_runtime.h"
#include "sha256.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

#ifndef GRIT_PAYLOAD_VERSION
#define GRIT_PAYLOAD_VERSION "dev"
#endif

#define BBX_TRAILER_SIZE 512
#define BBX_MAGIC "BBXPAYLOADv1"
#define BBX_PAYLOAD_ID_FILE ".grit-payload-id"
#define BBX_PAYLOAD_MODE_FILE ".grit-extract-mode"

static const char *busybox_tools[] = {
#include "grit_busybox_applets.h"
    NULL
};

static const char *heavy_tools[] = {
#include "grit_heavy_tools.h"
    NULL
};

const char *const *bb_payload_busybox_tools(void)
{
    return busybox_tools;
}

const char *const *bb_payload_heavy_tools(void)
{
    return heavy_tools;
}

static const char *saved_argv0;

void bb_set_argv0(const char *argv0)
{
    saved_argv0 = argv0;
}

static int read_exe_dir(char *out, size_t outsz)
{
    ssize_t n = readlink("/proc/self/exe", out, outsz - 1);
    char *slash;
    if (n < 0)
        return -1;
    out[n] = '\0';
    slash = strrchr(out, '/');
    if (!slash)
        return -1;
    *slash = '\0';
    return 0;
}

static int find_self_path(char *out, size_t outsz)
{
    ssize_t n = readlink("/proc/self/exe", out, outsz - 1);
    if (n >= 0) {
        out[n] = '\0';
        return 0;
    }
    if (saved_argv0 && strchr(saved_argv0, '/')) {
        snprintf(out, outsz, "%s", saved_argv0);
        return 0;
    }
    if (saved_argv0) {
        const char *path = getenv("PATH");
        char *dup, *save = NULL, *p;
        if (!path)
            return -1;
        dup = strdup(path);
        if (!dup)
            return -1;
        for (p = strtok_r(dup, ":", &save); p; p = strtok_r(NULL, ":", &save)) {
            snprintf(out, outsz, "%s/%s", *p ? p : ".", saved_argv0);
            if (access(out, X_OK) == 0) {
                free(dup);
                return 0;
            }
        }
        free(dup);
    }
    return -1;
}

static int parse_trailer_text(char *text, struct embedded_payload *ep)
{
    char *line, *save = NULL;
    memset(ep, 0, sizeof(*ep));
    line = strtok_r(text, "\n", &save);
    if (!line || strcmp(line, BBX_MAGIC))
        return -1;
    while ((line = strtok_r(NULL, "\n", &save)) != NULL) {
        char *eq;
        if (!strcmp(line, "END"))
            break;
        eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq++ = '\0';
        if (!strcmp(line, "offset"))
            ep->offset = strtoull(eq, NULL, 10);
        else if (!strcmp(line, "size"))
            ep->size = strtoull(eq, NULL, 10);
        else if (!strcmp(line, "sha256"))
            snprintf(ep->sha256, sizeof(ep->sha256), "%s", eq);
        else if (!strcmp(line, "version"))
            snprintf(ep->version, sizeof(ep->version), "%s", eq);
        else if (!strcmp(line, "format"))
            snprintf(ep->format, sizeof(ep->format), "%s", eq);
        else if (!strcmp(line, "compressed_size"))
            ep->compressed_size = strtoull(eq, NULL, 10);
    }
    if (!ep->offset || !ep->size || strlen(ep->sha256) != 64 || !ep->version[0] || !ep->format[0])
        return -1;
    if (strcmp(ep->format, "tar") && strcmp(ep->format, "tgz"))
        return -1;
    ep->present = 1;
    return 0;
}

int bb_get_embedded_payload(struct embedded_payload *ep)
{
    FILE *fp;
    long fsize;
    char trailer[BBX_TRAILER_SIZE + 1];

    memset(ep, 0, sizeof(*ep));
    if (find_self_path(ep->exe, sizeof(ep->exe)) != 0)
        return -1;
    fp = fopen(ep->exe, "rb");
    if (!fp)
        return -1;
    if (fseek(fp, 0, SEEK_END) != 0) {
        fclose(fp);
        return -1;
    }
    fsize = ftell(fp);
    fsize -= (long)bb_config_file_trailer_span(ep->exe);
    if (fsize < BBX_TRAILER_SIZE) {
        fclose(fp);
        return -1;
    }
    if (fseek(fp, fsize - BBX_TRAILER_SIZE, SEEK_SET) != 0 || fread(trailer, 1, BBX_TRAILER_SIZE, fp) != BBX_TRAILER_SIZE) {
        fclose(fp);
        return -1;
    }
    fclose(fp);
    trailer[BBX_TRAILER_SIZE] = '\0';
    /* parse_trailer_text does memset(ep, 0) internally; preserve the exe path
     * we already resolved above so bb_verify_embedded_hash can open the binary. */
    {
        char saved_exe[PATH_MAX];
        snprintf(saved_exe, sizeof(saved_exe), "%s", ep->exe);
        if (parse_trailer_text(trailer, ep) != 0)
            return -1;
        snprintf(ep->exe, sizeof(ep->exe), "%s", saved_exe);
    }
    if (ep->offset + ep->size + BBX_TRAILER_SIZE > (unsigned long long)fsize)
        return -1;
    return 0;
}

int bb_payload_valid(const char *payload)
{
    char busybox[PATH_MAX], version[PATH_MAX], found[128];

    snprintf(busybox, sizeof(busybox), "%s/bin/busybox", payload);
    snprintf(version, sizeof(version), "%s/VERSION", payload);
    if (!bb_executable_file(busybox))
        return 0;
    if (bb_read_first_line(version, found, sizeof(found)) != 0)
        return 0;
    return strcmp(found, GRIT_PAYLOAD_VERSION) == 0;
}

static void payload_mode_path(char *out, size_t outsz, const char *payload)
{
    snprintf(out, outsz, "%s/%s", payload, BBX_PAYLOAD_MODE_FILE);
}

int bb_payload_is_full(const char *payload)
{
    char path[PATH_MAX], mode[32];
    payload_mode_path(path, sizeof(path), payload);
    if (bb_read_first_line(path, mode, sizeof(mode)) != 0)
        return 1; /* Legacy extractions were always full. */
    return !strcmp(mode, "full");
}

const char *bb_payload_extraction_mode(const char *payload, char *out, size_t outsz)
{
    char path[PATH_MAX], mode[32];
    payload_mode_path(path, sizeof(path), payload);
    if (bb_read_first_line(path, mode, sizeof(mode)) != 0) {
        snprintf(out, outsz, "full");
        return out; /* Legacy extractions predate the marker and were full. */
    }
    if (!strcmp(mode, "core") || !strcmp(mode, "full"))
        snprintf(out, outsz, "%s", mode);
    else
        snprintf(out, outsz, "unknown");
    return out;
}

static void write_payload_mode(const char *payload, const char *mode)
{
    char path[PATH_MAX];
    FILE *fp;
    payload_mode_path(path, sizeof(path), payload);
    fp = fopen(path, "w");
    if (!fp)
        return;
    fprintf(fp, "%s\n", mode);
    fclose(fp);
}

static int yes_str(const char *s)
{
    return s && (!strcmp(s, "yes") || !strcmp(s, "1") || !strcmp(s, "true"));
}

static int candidate_payload(char *out, size_t outsz)
{
    const char *env = getenv("GRIT_PAYLOAD_DIR");
    char exe_dir[PATH_MAX];
    char path[PATH_MAX];
    uid_t uid = getuid();
    int fallback_ok = yes_str(GRIT_RUNTIME_ALLOW_FALLBACK_ROOT) ||
                      yes_str(getenv("GRIT_ALLOW_FALLBACK_ROOT"));

    if (env && bb_payload_valid(env)) {
        snprintf(out, outsz, "%s", env);
        return 0;
    }

    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(path, sizeof(path), "%s/payload", exe_dir);
        if (bb_payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }

    if (GRIT_RUNTIME_ROOT[0]) {
        snprintf(path, sizeof(path), "%s/payload", GRIT_RUNTIME_ROOT);
        if (bb_payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }

    /* Legacy /tmp, /var/tmp, /dev/shm locations — only checked when fallback
     * root is explicitly permitted.  In strict mode these are not considered. */
    if (fallback_ok) {
        snprintf(path, sizeof(path), "/tmp/grit-%ld/payload", (long)uid);
        if (bb_payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        snprintf(path, sizeof(path), "/var/tmp/grit-%ld/payload", (long)uid);
        if (bb_payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        snprintf(path, sizeof(path), "/dev/shm/grit-%ld/payload", (long)uid);
        if (bb_payload_valid(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        if (bb_payload_valid("runtime/payload")) {
            snprintf(out, outsz, "%s", "runtime/payload");
            return 0;
        }
    }
    return -1;
}

int bb_payload_archive_path(char *out, size_t outsz)
{
    char exe_dir[PATH_MAX], path[PATH_MAX];

    if (read_exe_dir(exe_dir, sizeof(exe_dir)) == 0) {
        snprintf(path, sizeof(path), "%s/payload.tar", exe_dir);
        if (bb_path_exists(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
        snprintf(path, sizeof(path), "%s/payload.tar.gz", exe_dir);
        if (bb_path_exists(path)) {
            snprintf(out, outsz, "%s", path);
            return 0;
        }
    }
    if (bb_path_exists("dist/payload.tar")) {
        snprintf(out, outsz, "%s", "dist/payload.tar");
        return 0;
    }
    if (bb_path_exists("dist/payload.tar.gz")) {
        snprintf(out, outsz, "%s", "dist/payload.tar.gz");
        return 0;
    }
    if (bb_path_exists("payload.tar")) {
        snprintf(out, outsz, "%s", "payload.tar");
        return 0;
    }
    if (bb_path_exists("payload.tar.gz")) {
        snprintf(out, outsz, "%s", "payload.tar.gz");
        return 0;
    }
    return -1;
}

int bb_verify_embedded_hash(const struct embedded_payload *ep)
{
    FILE *fp = fopen(ep->exe, "rb");
    bb_sha256_ctx ctx;
    uint8_t buf[8192], hash[32];
    char hex[65];
    unsigned long long left = ep->size;
    if (!fp)
        return -1;
    if (fseek(fp, (long)ep->offset, SEEK_SET) != 0) {
        fclose(fp);
        return -1;
    }
    bb_sha256_init(&ctx);
    while (left) {
        size_t n = left > sizeof(buf) ? sizeof(buf) : (size_t)left;
        if (fread(buf, 1, n, fp) != n) {
            fclose(fp);
            return -1;
        }
        bb_sha256_update(&ctx, buf, n);
        left -= n;
    }
    fclose(fp);
    bb_sha256_final(&ctx, hash);
    bb_sha256_hex(hash, hex);
    return strcmp(hex, ep->sha256) == 0 ? 0 : -1;
}

static void write_payload_id(const struct embedded_payload *ep, const char *payload_dir)
{
    char id_path[PATH_MAX];
    FILE *fp;
    snprintf(id_path, sizeof(id_path), "%s/%s", payload_dir, BBX_PAYLOAD_ID_FILE);
    fp = fopen(id_path, "w");
    if (!fp)
        return;
    fprintf(fp, "sha256=%s\n", ep->sha256);
    fprintf(fp, "size=%llu\n", ep->size);
    fprintf(fp, "version=%s\n", ep->version);
    fprintf(fp, "format=%s\n", ep->format);
    fclose(fp);
}

int bb_payload_id_matches(const struct embedded_payload *ep, const char *payload_dir)
{
    char id_path[PATH_MAX], line[256], key[64], val[192];
    char found_sha256[65] = "", found_size[32] = "", found_version[128] = "", found_format[16] = "";
    char expected_size[32];
    FILE *fp;

    if (!ep->present)
        return 1;
    snprintf(id_path, sizeof(id_path), "%s/%s", payload_dir, BBX_PAYLOAD_ID_FILE);
    fp = fopen(id_path, "r");
    if (!fp)
        return 0;
    while (fgets(line, sizeof(line), fp)) {
        char *eq;
        line[strcspn(line, "\r\n")] = '\0';
        eq = strchr(line, '=');
        if (!eq)
            continue;
        *eq++ = '\0';
        strncpy(key, line, sizeof(key) - 1);
        key[sizeof(key) - 1] = '\0';
        strncpy(val, eq, sizeof(val) - 1);
        val[sizeof(val) - 1] = '\0';
        if (!strcmp(key, "sha256"))
            strncpy(found_sha256, val, sizeof(found_sha256) - 1);
        else if (!strcmp(key, "size"))
            strncpy(found_size, val, sizeof(found_size) - 1);
        else if (!strcmp(key, "version"))
            strncpy(found_version, val, sizeof(found_version) - 1);
        else if (!strcmp(key, "format"))
            strncpy(found_format, val, sizeof(found_format) - 1);
    }
    fclose(fp);
    snprintf(expected_size, sizeof(expected_size), "%llu", ep->size);
    return strcmp(found_sha256, ep->sha256) == 0 &&
           strcmp(found_size, expected_size) == 0 &&
           strcmp(found_version, ep->version) == 0 &&
           strcmp(found_format, ep->format) == 0;
}

int bb_extract_embedded_to_root(const struct embedded_payload *ep, const char *root, int core_only)
{
    char lock[PATH_MAX], tmp[PATH_MAX], final[PATH_MAX], extracted[PATH_MAX];
    FILE *fp;
    int rc;

    snprintf(lock, sizeof(lock), "%s/.extract.lock", root);
    snprintf(tmp, sizeof(tmp), "%s/payload.tmp.%ld", root, (long)getpid());
    snprintf(final, sizeof(final), "%s/payload", root);
    snprintf(extracted, sizeof(extracted), "%s/payload", tmp);

    if (!bb_enough_space_for_extract(ep->size, root)) {
        fprintf(stderr, "extract: not enough free space in %s\n", root);
        return -1;
    }
    int waits = 0;
    while (mkdir(lock, 0700) != 0) {
        if (errno != EEXIST)
            return -1;
        sleep(1);
        if (bb_payload_valid(final) && (core_only || bb_payload_is_full(final)))
            return 0;
        if (++waits > 30) {
            rmdir(lock);
            waits = 0;
        }
    }
    bb_rm_rf(tmp);
    if (bb_mkdir_p(tmp, 0700) != 0) {
        rmdir(lock);
        return -1;
    }

    if (bb_verify_embedded_hash(ep) != 0) {
        bb_rm_rf(tmp);
        rmdir(lock);
        fprintf(stderr, "extract: embedded payload sha256 mismatch\n");
        return -1;
    }
    fp = fopen(ep->exe, "rb");
    if (!fp || fseek(fp, (long)ep->offset, SEEK_SET) != 0) {
        if (fp)
            fclose(fp);
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    rc = bb_extract_payload_stream(fp, ep->size, ep->format, tmp, core_only);
    fclose(fp);
    if (rc != 0) {
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    if (!bb_payload_valid(extracted)) {
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    bb_rm_rf(final);
    if (rename(extracted, final) != 0) {
        bb_rm_rf(tmp);
        rmdir(lock);
        return -1;
    }
    bb_rm_rf(tmp);
    rmdir(lock);
    write_payload_id(ep, final);
    write_payload_mode(final, core_only ? "core" : "full");
    bb_ledger_record("extract", root, "payload", core_only ? "embedded core payload extracted" : "embedded payload extracted");
    bb_ledger_record("write", final, "payload", "payload root");
    return 0;
}

int bb_extract_archive_file_to_root(const char *archive, const char *root, int core_only)
{
    struct embedded_payload ep;
    FILE *fp;
    struct stat st;
    int rc, is_tgz;

    memset(&ep, 0, sizeof(ep));
    snprintf(ep.exe, sizeof(ep.exe), "%s", archive);
    if (stat(archive, &st) != 0)
        return -1;
    ep.size = (unsigned long long)st.st_size;
    snprintf(ep.version, sizeof(ep.version), "%s", GRIT_PAYLOAD_VERSION);
    is_tgz = strstr(archive, ".gz") || strstr(archive, ".tgz");
    snprintf(ep.format, sizeof(ep.format), "%s", is_tgz ? "tgz" : "tar");

    if (!bb_enough_space_for_extract(ep.size, root))
        return -1;
    fp = fopen(archive, "rb");
    if (!fp)
        return -1;
    {
        char tmp[PATH_MAX], final[PATH_MAX], extracted[PATH_MAX];
        snprintf(tmp, sizeof(tmp), "%s/payload.devtmp.%ld", root, (long)getpid());
        snprintf(final, sizeof(final), "%s/payload", root);
        snprintf(extracted, sizeof(extracted), "%s/payload", tmp);
        bb_rm_rf(tmp);
        if (bb_mkdir_p(tmp, 0700) == 0)
            rc = bb_extract_payload_stream(fp, ep.size, ep.format, tmp, core_only);
        else
            rc = -1;
        if (rc == 0 && bb_payload_valid(extracted)) {
            bb_rm_rf(final);
            rc = rename(extracted, final);
            if (rc == 0) {
                write_payload_mode(final, core_only ? "core" : "full");
                bb_ledger_record("extract", root, "payload", core_only ? "archive core payload extracted" : "archive payload extracted");
                bb_ledger_record("write", final, "payload", "payload root");
            }
        } else {
            rc = -1;
        }
        bb_rm_rf(tmp);
    }
    fclose(fp);
    return rc;
}

int bb_ensure_payload_mode(char *payload, size_t payloadsz, int require_full)
{
    char archive[PATH_MAX], root[PATH_MAX];
    struct embedded_payload ep;
    int have_ep = (bb_get_embedded_payload(&ep) == 0);

    if (!strcmp(GRIT_RUNTIME_MODE, "core-only"))
        return -1;

    if (candidate_payload(payload, payloadsz) == 0) {
        if (have_ep && !bb_payload_id_matches(&ep, payload)) {
            fprintf(stderr, "grit: extracted payload is from a different binary; re-extracting...\n");
            bb_rm_rf(payload);
            /* fall through to extract */
        } else if (require_full && !bb_payload_is_full(payload)) {
            fprintf(stderr, "grit: upgrading core payload extraction to full payload...\n");
            bb_rm_rf(payload);
            /* fall through to extract */
        } else {
            return 0;
        }
    }
    if (bb_choose_extract_root(root, sizeof(root)) != 0)
        return -1;
    if (have_ep) {
        if (bb_extract_embedded_to_root(&ep, root, !require_full) != 0)
            return -1;
    } else {
        if (bb_payload_archive_path(archive, sizeof(archive)) != 0)
            return -1;
        fprintf(stderr, "grit: warning: using dev-only external payload archive fallback: %s\n", archive);
        if (bb_extract_archive_file_to_root(archive, root, !require_full) != 0)
            return -1;
    }
    bb_write_artifact_manifest_file(root);
    snprintf(payload, payloadsz, "%s/payload", root);
    return bb_payload_valid(payload) && (!require_full || bb_payload_is_full(payload)) ? 0 : -1;
}

static int ensure_payload(char *payload, size_t payloadsz)
{
    return bb_ensure_payload_mode(payload, payloadsz, 1);
}

int bb_ensure_payload_dir(char *payload, size_t payloadsz)
{
    return ensure_payload(payload, payloadsz);
}

int bb_candidate_payload_dir(char *payload, size_t payloadsz)
{
    return candidate_payload(payload, payloadsz);
}

int bb_embedded_payload_available(void)
{
    struct embedded_payload ep;
    return bb_get_embedded_payload(&ep) == 0;
}

int bb_dev_payload_archive_available(void)
{
    char archive[PATH_MAX];
    return bb_payload_archive_path(archive, sizeof(archive)) == 0;
}

int bb_payload_tool_is_heavy(const char *name)
{
    int i;
    for (i = 0; heavy_tools[i]; i++)
        if (!strcmp(name, heavy_tools[i]))
            return 1;
    return 0;
}
