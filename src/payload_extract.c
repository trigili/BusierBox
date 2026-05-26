#define _POSIX_C_SOURCE 200809L

#include <fcntl.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#include "applets.h"
#include "../third_party/miniz/miniz.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

struct payload_stream {
    FILE *fp;
    unsigned long long remaining;
    int tgz;
    mz_stream z;
    unsigned char in[8192];
    unsigned char out[8192];
    int eof;
    size_t out_pos;
    size_t out_len;
};

static int stream_init_tar(struct payload_stream *s, FILE *fp, unsigned long long size)
{
    memset(s, 0, sizeof(*s));
    s->fp = fp;
    s->remaining = size;
    return 0;
}

static int gzip_skip_header(FILE *fp, unsigned long long *remaining)
{
    unsigned char h[10];
    int flg, c;
    if (*remaining < 10 || fread(h, 1, 10, fp) != 10)
        return -1;
    *remaining -= 10;
    if (h[0] != 0x1f || h[1] != 0x8b || h[2] != 8)
        return -1;
    flg = h[3];
    if (flg & 0x04) {
        unsigned char x[2];
        unsigned int len;
        if (*remaining < 2 || fread(x, 1, 2, fp) != 2)
            return -1;
        *remaining -= 2;
        len = (unsigned int)x[0] | ((unsigned int)x[1] << 8);
        if (*remaining < len || fseek(fp, (long)len, SEEK_CUR) != 0)
            return -1;
        *remaining -= len;
    }
    if (flg & 0x08) {
        do {
            if (*remaining < 1 || (c = fgetc(fp)) == EOF)
                return -1;
            (*remaining)--;
        } while (c != 0);
    }
    if (flg & 0x10) {
        do {
            if (*remaining < 1 || (c = fgetc(fp)) == EOF)
                return -1;
            (*remaining)--;
        } while (c != 0);
    }
    if (flg & 0x02) {
        if (*remaining < 2 || fseek(fp, 2, SEEK_CUR) != 0)
            return -1;
        *remaining -= 2;
    }
    if (flg & 0xe0)
        return -1;
    return 0;
}

static int stream_init_tgz(struct payload_stream *s, FILE *fp, unsigned long long size)
{
    memset(s, 0, sizeof(*s));
    s->fp = fp;
    s->remaining = size;
    s->tgz = 1;
    if (gzip_skip_header(fp, &s->remaining) != 0)
        return -1;
    memset(&s->z, 0, sizeof(s->z));
    if (mz_inflateInit2(&s->z, -MZ_DEFAULT_WINDOW_BITS) != MZ_OK)
        return -1;
    return 0;
}

static void stream_end(struct payload_stream *s)
{
    if (s->tgz)
        mz_inflateEnd(&s->z);
}

static int stream_read(struct payload_stream *s, void *buf, size_t len)
{
    unsigned char *dst = buf;
    size_t done = 0;
    while (done < len) {
        if (!s->tgz) {
            size_t want = len - done;
            if (s->remaining < want)
                return -1;
            if (fread(dst + done, 1, want, s->fp) != want)
                return -1;
            s->remaining -= want;
            return 0;
        }
        if (s->out_pos < s->out_len) {
            size_t n = s->out_len - s->out_pos;
            if (n > len - done)
                n = len - done;
            memcpy(dst + done, s->out + s->out_pos, n);
            s->out_pos += n;
            done += n;
            continue;
        }
        s->out_pos = s->out_len = 0;
        if (s->z.avail_in == 0 && s->remaining > 8) {
            size_t want = sizeof(s->in);
            if (want > s->remaining - 8)
                want = (size_t)(s->remaining - 8);
            if (fread(s->in, 1, want, s->fp) != want)
                return -1;
            s->remaining -= want;
            s->z.next_in = s->in;
            s->z.avail_in = (mz_uint)want;
        }
        s->z.next_out = s->out;
        s->z.avail_out = sizeof(s->out);
        {
            int rc = mz_inflate(&s->z, MZ_NO_FLUSH);
            s->out_len = sizeof(s->out) - s->z.avail_out;
            if (rc == MZ_STREAM_END)
                s->eof = 1;
            else if (rc != MZ_OK)
                return -1;
            if (s->out_len == 0 && s->eof)
                return -1;
        }
    }
    return 0;
}

static int octal(const char *p, size_t n, unsigned long long *out)
{
    unsigned long long v = 0;
    size_t i;
    for (i = 0; i < n; i++) {
        if (p[i] == '\0' || p[i] == ' ')
            break;
        if (p[i] < '0' || p[i] > '7')
            return -1;
        v = (v << 3) + (unsigned)(p[i] - '0');
    }
    *out = v;
    return 0;
}

static int safe_member_path(const char *name)
{
    if (!name[0] || name[0] == '/' || strstr(name, "/../") || !strcmp(name, "..") || !strncmp(name, "../", 3))
        return 0;
    return 1;
}

static int core_payload_member(const char *name)
{
    return !strcmp(name, "payload/bin/busybox") ||
           !strcmp(name, "payload/VERSION") ||
           !strcmp(name, "payload/manifest.json") ||
           !strcmp(name, "payload/busybox-applets.txt") ||
           !strcmp(name, "payload/staged-tools.txt") ||
           !strcmp(name, "payload/built-tools.txt") ||
           !strcmp(name, "payload/requested-tools.txt") ||
           !strcmp(name, "payload/missing-tools.txt") ||
           !strcmp(name, "payload/share/busierbox/missing-tools.txt") ||
           !strcmp(name, "payload/share/busierbox/applet-symlink-count.txt");
}

static int stream_skip(struct payload_stream *s, unsigned long long n)
{
    unsigned char buf[8192];
    while (n) {
        size_t chunk = n > sizeof(buf) ? sizeof(buf) : (size_t)n;
        if (stream_read(s, buf, chunk) != 0)
            return -1;
        n -= chunk;
    }
    return 0;
}

static int tar_extract_stream(struct payload_stream *s, const char *root, int core_only)
{
    unsigned char hdr[512], buf[8192];
    int zero_blocks = 0;
    while (1) {
        char name[256], full[PATH_MAX], linkname[256], type;
        unsigned long long size = 0, mode = 0, pad, left, stored64 = 0;
        unsigned int i, sum = 0, stored = 0;
        int fd;

        if (stream_read(s, hdr, 512) != 0)
            return -1;
        for (i = 0; i < 512; i++)
            if (hdr[i])
                break;
        if (i == 512) {
            if (++zero_blocks == 2)
                return 0;
            continue;
        }
        zero_blocks = 0;
        if (octal((char *)hdr + 148, 8, &stored64) != 0)
            return -1;
        stored = (unsigned int)stored64;
        for (i = 0; i < 512; i++)
            sum += (i >= 148 && i < 156) ? ' ' : hdr[i];
        if (stored != sum)
            return -1;
        snprintf(name, sizeof(name), "%.*s", 100, (char *)hdr);
        if (hdr[345])
            snprintf(name, sizeof(name), "%.*s/%.*s", 155, (char *)hdr + 345, 100, (char *)hdr);
        if (!safe_member_path(name))
            return -1;
        if (octal((char *)hdr + 100, 8, &mode) != 0 || octal((char *)hdr + 124, 12, &size) != 0)
            return -1;
        mode &= 0777;
        type = hdr[156] ? hdr[156] : '0';
        snprintf(full, sizeof(full), "%s/%s", root, name);
        if (core_only && type != '5' && !core_payload_member(name)) {
            pad = (512 - (size % 512)) % 512;
            if (stream_skip(s, size + pad) != 0)
                return -1;
            continue;
        }
        if (type == '5') {
            if (core_only && strcmp(name, "payload") && strcmp(name, "payload/bin") &&
                strcmp(name, "payload/share") && strcmp(name, "payload/share/busierbox"))
                continue;
            if (bb_mkdir_p(full, (mode_t)mode) != 0)
                return -1;
        } else if (type == '0') {
            char *slash = strrchr(full, '/');
            if (slash) {
                *slash = '\0';
                if (bb_mkdir_p(full, 0700) != 0)
                    return -1;
                *slash = '/';
            }
            fd = open(full, O_WRONLY | O_CREAT | O_TRUNC, (mode_t)mode);
            if (fd < 0)
                return -1;
            left = size;
            while (left) {
                size_t n = left > sizeof(buf) ? sizeof(buf) : (size_t)left;
                if (stream_read(s, buf, n) != 0 || write(fd, buf, n) != (ssize_t)n) {
                    close(fd);
                    return -1;
                }
                left -= n;
            }
            close(fd);
            chmod(full, (mode_t)mode);
        } else if (type == '2') {
            if (core_only && !core_payload_member(name))
                continue;
            snprintf(linkname, sizeof(linkname), "%.*s", 100, (char *)hdr + 157);
            if (!safe_member_path(linkname))
                return -1;
            unlink(full);
            if (symlink(linkname, full) != 0)
                return -1;
        } else {
            return -1;
        }
        pad = (512 - (size % 512)) % 512;
        if ((type == '0') && pad && stream_read(s, buf, (size_t)pad) != 0)
            return -1;
    }
}

int bb_extract_payload_stream(FILE *fp, unsigned long long size, const char *format,
                              const char *root, int core_only)
{
    struct payload_stream s;
    int rc;
    int initialized = 0;

    if (!strcmp(format, "tar"))
        rc = stream_init_tar(&s, fp, size);
    else
        rc = stream_init_tgz(&s, fp, size);
    if (rc == 0) {
        initialized = 1;
        rc = tar_extract_stream(&s, root, core_only);
    }
    if (initialized)
        stream_end(&s);
    return rc;
}
