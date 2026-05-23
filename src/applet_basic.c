#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>
#include <utime.h>

#include "applets.h"

#ifndef PATH_MAX
#define PATH_MAX 4096
#endif

extern char **environ;

static int is_help(int argc, char **argv)
{
    return argc > 1 && (!strcmp(argv[1], "--help") || !strcmp(argv[1], "-h"));
}

int applet_list_main(int argc, char **argv)
{
    int verbose = argc > 1 && !strcmp(argv[1], "-v");

    if (is_help(argc, argv)) {
        puts("usage: busierbox list [-v]");
        return 0;
    }
    bb_list_applets(verbose);
    return 0;
}

static int copy_stream(FILE *in, FILE *out)
{
    char buf[8192];
    size_t n;

    while ((n = fread(buf, 1, sizeof(buf), in)) > 0) {
        if (fwrite(buf, 1, n, out) != n)
            return 1;
    }
    return ferror(in) ? 1 : 0;
}

int applet_cat_main(int argc, char **argv)
{
    int rc = 0, i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox cat [FILE...]");
        return 0;
    }
    if (argc == 1)
        return copy_stream(stdin, stdout);
    for (i = 1; i < argc; i++) {
        FILE *fp = !strcmp(argv[i], "-") ? stdin : fopen(argv[i], "rb");
        if (!fp) {
            fprintf(stderr, "cat: %s: %s\n", argv[i], strerror(errno));
            rc = 1;
            continue;
        }
        if (copy_stream(fp, stdout))
            rc = 1;
        if (fp != stdin)
            fclose(fp);
    }
    return rc;
}

static void mode_string(mode_t mode, char out[11])
{
    const char *rwx = "rwxrwxrwx";
    int i;
    out[0] = S_ISDIR(mode) ? 'd' : S_ISLNK(mode) ? 'l' : '-';
    for (i = 0; i < 9; i++)
        out[i + 1] = (mode & (1 << (8 - i))) ? rwx[i] : '-';
    out[10] = '\0';
}

static int ls_one(const char *path, int long_mode)
{
    DIR *dir = opendir(path);
    struct dirent *de;
    int rc = 0;

    if (!dir) {
        struct stat st;
        if (lstat(path, &st) != 0) {
            fprintf(stderr, "ls: %s: %s\n", path, strerror(errno));
            return 1;
        }
        if (long_mode) {
            char m[11];
            mode_string(st.st_mode, m);
            printf("%s %8ld %s\n", m, (long)st.st_size, path);
        } else {
            puts(path);
        }
        return 0;
    }

    while ((de = readdir(dir)) != NULL) {
        char full[PATH_MAX];
        struct stat st;
        if (de->d_name[0] == '.')
            continue;
        if (!long_mode) {
            puts(de->d_name);
            continue;
        }
        snprintf(full, sizeof(full), "%s/%s", path, de->d_name);
        if (lstat(full, &st) == 0) {
            char m[11];
            mode_string(st.st_mode, m);
            printf("%s %8ld %s\n", m, (long)st.st_size, de->d_name);
        } else {
            rc = 1;
        }
    }
    closedir(dir);
    return rc;
}

int applet_ls_main(int argc, char **argv)
{
    int long_mode = 0, start = 1, rc = 0, i;
    if (is_help(argc, argv)) {
        puts("usage: busierbox ls [-l] [PATH...]");
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "-l")) {
        long_mode = 1;
        start = 2;
    }
    if (start == argc)
        return ls_one(".", long_mode);
    for (i = start; i < argc; i++)
        rc |= ls_one(argv[i], long_mode);
    return rc;
}

int applet_hexdump_main(int argc, char **argv)
{
    FILE *fp = stdin;
    unsigned char buf[16];
    unsigned long off = 0;
    size_t n, i;

    if (is_help(argc, argv)) {
        puts("usage: busierbox hexdump [FILE]");
        return 0;
    }
    if (argc > 1 && strcmp(argv[1], "-")) {
        fp = fopen(argv[1], "rb");
        if (!fp) {
            fprintf(stderr, "hexdump: %s: %s\n", argv[1], strerror(errno));
            return 1;
        }
    }
    while ((n = fread(buf, 1, sizeof(buf), fp)) > 0) {
        printf("%08lx  ", off);
        for (i = 0; i < 16; i++)
            i < n ? printf("%02x ", buf[i]) : printf("   ");
        printf(" |");
        for (i = 0; i < n; i++)
            putchar(isprint(buf[i]) ? buf[i] : '.');
        puts("|");
        off += (unsigned long)n;
    }
    if (fp != stdin)
        fclose(fp);
    return 0;
}

static int strings_file(FILE *fp, int min_len)
{
    char *buf = NULL;
    size_t cap = 0, len = 0;
    int c;

    while ((c = fgetc(fp)) != EOF) {
        if (isprint((unsigned char)c) || c == '\t') {
            if (len + 1 >= cap) {
                size_t ncap = cap ? cap * 2 : 64;
                char *nbuf = realloc(buf, ncap);
                if (!nbuf) {
                    free(buf);
                    return 1;
                }
                buf = nbuf;
                cap = ncap;
            }
            buf[len++] = (char)c;
        } else {
            if ((int)len >= min_len) {
                buf[len] = '\0';
                puts(buf);
            }
            len = 0;
        }
    }
    if ((int)len >= min_len) {
        buf[len] = '\0';
        puts(buf);
    }
    free(buf);
    return 0;
}

int applet_strings_main(int argc, char **argv)
{
    int min_len = 4, i = 1, rc = 0;
    if (is_help(argc, argv)) {
        puts("usage: busierbox strings [-n LEN] [FILE...]");
        return 0;
    }
    if (argc > 2 && !strcmp(argv[1], "-n")) {
        min_len = atoi(argv[2]);
        if (min_len < 1)
            min_len = 1;
        i = 3;
    }
    if (i == argc)
        return strings_file(stdin, min_len);
    for (; i < argc; i++) {
        FILE *fp = !strcmp(argv[i], "-") ? stdin : fopen(argv[i], "rb");
        if (!fp) {
            fprintf(stderr, "strings: %s: %s\n", argv[i], strerror(errno));
            rc = 1;
            continue;
        }
        rc |= strings_file(fp, min_len);
        if (fp != stdin)
            fclose(fp);
    }
    return rc;
}

/* SHA-256 implementation adapted from Brad Conte's public-domain crypto-algorithms. */
typedef struct {
    uint8_t data[64];
    uint32_t datalen;
    uint64_t bitlen;
    uint32_t state[8];
} SHA256_CTX;

#define ROTRIGHT(a,b) (((a) >> (b)) | ((a) << (32-(b))))
#define CH(x,y,z) (((x) & (y)) ^ (~(x) & (z)))
#define MAJ(x,y,z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))
#define EP0(x) (ROTRIGHT(x,2) ^ ROTRIGHT(x,13) ^ ROTRIGHT(x,22))
#define EP1(x) (ROTRIGHT(x,6) ^ ROTRIGHT(x,11) ^ ROTRIGHT(x,25))
#define SIG0(x) (ROTRIGHT(x,7) ^ ROTRIGHT(x,18) ^ ((x) >> 3))
#define SIG1(x) (ROTRIGHT(x,17) ^ ROTRIGHT(x,19) ^ ((x) >> 10))

static const uint32_t k256[64] = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};

static void sha256_transform(SHA256_CTX *ctx, const uint8_t data[])
{
    uint32_t a,b,c,d,e,f,g,h,i,j,t1,t2,m[64];
    for (i = 0, j = 0; i < 16; ++i, j += 4)
        m[i] = (data[j] << 24) | (data[j+1] << 16) | (data[j+2] << 8) | data[j+3];
    for (; i < 64; ++i)
        m[i] = SIG1(m[i-2]) + m[i-7] + SIG0(m[i-15]) + m[i-16];
    a=ctx->state[0]; b=ctx->state[1]; c=ctx->state[2]; d=ctx->state[3];
    e=ctx->state[4]; f=ctx->state[5]; g=ctx->state[6]; h=ctx->state[7];
    for (i = 0; i < 64; ++i) {
        t1 = h + EP1(e) + CH(e,f,g) + k256[i] + m[i];
        t2 = EP0(a) + MAJ(a,b,c);
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    ctx->state[0]+=a; ctx->state[1]+=b; ctx->state[2]+=c; ctx->state[3]+=d;
    ctx->state[4]+=e; ctx->state[5]+=f; ctx->state[6]+=g; ctx->state[7]+=h;
}

static void sha256_init(SHA256_CTX *ctx)
{
    ctx->datalen = 0; ctx->bitlen = 0;
    ctx->state[0]=0x6a09e667; ctx->state[1]=0xbb67ae85; ctx->state[2]=0x3c6ef372; ctx->state[3]=0xa54ff53a;
    ctx->state[4]=0x510e527f; ctx->state[5]=0x9b05688c; ctx->state[6]=0x1f83d9ab; ctx->state[7]=0x5be0cd19;
}

static void sha256_update(SHA256_CTX *ctx, const uint8_t data[], size_t len)
{
    size_t i;
    for (i = 0; i < len; ++i) {
        ctx->data[ctx->datalen++] = data[i];
        if (ctx->datalen == 64) {
            sha256_transform(ctx, ctx->data);
            ctx->bitlen += 512;
            ctx->datalen = 0;
        }
    }
}

static void sha256_final(SHA256_CTX *ctx, uint8_t hash[])
{
    uint32_t i = ctx->datalen;
    if (ctx->datalen < 56) {
        ctx->data[i++] = 0x80;
        while (i < 56) ctx->data[i++] = 0;
    } else {
        ctx->data[i++] = 0x80;
        while (i < 64) ctx->data[i++] = 0;
        sha256_transform(ctx, ctx->data);
        memset(ctx->data, 0, 56);
    }
    ctx->bitlen += ctx->datalen * 8;
    ctx->data[63] = ctx->bitlen; ctx->data[62] = ctx->bitlen >> 8; ctx->data[61] = ctx->bitlen >> 16; ctx->data[60] = ctx->bitlen >> 24;
    ctx->data[59] = ctx->bitlen >> 32; ctx->data[58] = ctx->bitlen >> 40; ctx->data[57] = ctx->bitlen >> 48; ctx->data[56] = ctx->bitlen >> 56;
    sha256_transform(ctx, ctx->data);
    for (i = 0; i < 4; ++i) {
        hash[i]      = (ctx->state[0] >> (24 - i * 8)) & 0xff;
        hash[i + 4]  = (ctx->state[1] >> (24 - i * 8)) & 0xff;
        hash[i + 8]  = (ctx->state[2] >> (24 - i * 8)) & 0xff;
        hash[i + 12] = (ctx->state[3] >> (24 - i * 8)) & 0xff;
        hash[i + 16] = (ctx->state[4] >> (24 - i * 8)) & 0xff;
        hash[i + 20] = (ctx->state[5] >> (24 - i * 8)) & 0xff;
        hash[i + 24] = (ctx->state[6] >> (24 - i * 8)) & 0xff;
        hash[i + 28] = (ctx->state[7] >> (24 - i * 8)) & 0xff;
    }
}

static int sha256_file(const char *name, FILE *fp)
{
    SHA256_CTX ctx;
    uint8_t buf[8192], hash[32];
    size_t n, i;
    sha256_init(&ctx);
    while ((n = fread(buf, 1, sizeof(buf), fp)) > 0)
        sha256_update(&ctx, buf, n);
    if (ferror(fp))
        return 1;
    sha256_final(&ctx, hash);
    for (i = 0; i < sizeof(hash); i++)
        printf("%02x", hash[i]);
    printf("  %s\n", name);
    return 0;
}

int applet_sha256sum_main(int argc, char **argv)
{
    int rc = 0, i;
    if (is_help(argc, argv)) {
        puts("usage: busierbox sha256sum [FILE...]");
        return 0;
    }
    if (argc == 1)
        return sha256_file("-", stdin);
    for (i = 1; i < argc; i++) {
        FILE *fp = !strcmp(argv[i], "-") ? stdin : fopen(argv[i], "rb");
        if (!fp) {
            fprintf(stderr, "sha256sum: %s: %s\n", argv[i], strerror(errno));
            rc = 1;
            continue;
        }
        rc |= sha256_file(argv[i], fp);
        if (fp != stdin)
            fclose(fp);
    }
    return rc;
}

static const char b64tab[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static int base64_encode(FILE *fp)
{
    unsigned char in[3];
    size_t n;
    int col = 0;
    while ((n = fread(in, 1, 3, fp)) > 0) {
        unsigned int v = (in[0] << 16) | ((n > 1 ? in[1] : 0) << 8) | (n > 2 ? in[2] : 0);
        putchar(b64tab[(v >> 18) & 63]); putchar(b64tab[(v >> 12) & 63]);
        putchar(n > 1 ? b64tab[(v >> 6) & 63] : '=');
        putchar(n > 2 ? b64tab[v & 63] : '=');
        col += 4;
        if (col >= 76) { putchar('\n'); col = 0; }
    }
    if (col)
        putchar('\n');
    return ferror(fp) ? 1 : 0;
}

static int b64val(int c)
{
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

static int base64_decode(FILE *fp)
{
    int q[4], qn = 0, c;
    while ((c = fgetc(fp)) != EOF) {
        if (isspace((unsigned char)c))
            continue;
        q[qn++] = c == '=' ? -2 : b64val(c);
        if (q[qn - 1] == -1)
            return 1;
        if (qn == 4) {
            unsigned int v = ((q[0] & 63) << 18) | ((q[1] & 63) << 12) | ((q[2] >= 0 ? q[2] : 0) << 6) | (q[3] >= 0 ? q[3] : 0);
            putchar((v >> 16) & 0xff);
            if (q[2] != -2) putchar((v >> 8) & 0xff);
            if (q[3] != -2) putchar(v & 0xff);
            qn = 0;
        }
    }
    return 0;
}

int applet_base64_main(int argc, char **argv)
{
    int decode = 0, idx = 1;
    FILE *fp = stdin;
    if (is_help(argc, argv)) {
        puts("usage: busierbox base64 [-d] [FILE]");
        return 0;
    }
    if (argc > 1 && (!strcmp(argv[1], "-d") || !strcmp(argv[1], "--decode"))) {
        decode = 1;
        idx = 2;
    }
    if (idx < argc && strcmp(argv[idx], "-")) {
        fp = fopen(argv[idx], "rb");
        if (!fp) {
            fprintf(stderr, "base64: %s: %s\n", argv[idx], strerror(errno));
            return 1;
        }
    }
    idx = decode ? base64_decode(fp) : base64_encode(fp);
    if (fp != stdin)
        fclose(fp);
    return idx;
}

static long parse_long_arg(const char *s)
{
    char *end;
    long v = strtol(s, &end, 10);
    if (*end == 'k' || *end == 'K') v *= 1024;
    else if (*end == 'm' || *end == 'M') v *= 1024 * 1024;
    return v;
}

int applet_dd_main(int argc, char **argv)
{
    const char *ifn = NULL, *ofn = NULL;
    long bs = 512, count = -1, skip = 0, seek = 0, blocks = 0;
    int in = STDIN_FILENO, out = STDOUT_FILENO, i, rc = 0;
    char *buf;

    if (is_help(argc, argv)) {
        puts("usage: busierbox dd [if=FILE] [of=FILE] [bs=N] [count=N] [skip=N] [seek=N]");
        return 0;
    }
    for (i = 1; i < argc; i++) {
        if (!strncmp(argv[i], "if=", 3)) ifn = argv[i] + 3;
        else if (!strncmp(argv[i], "of=", 3)) ofn = argv[i] + 3;
        else if (!strncmp(argv[i], "bs=", 3)) bs = parse_long_arg(argv[i] + 3);
        else if (!strncmp(argv[i], "count=", 6)) count = parse_long_arg(argv[i] + 6);
        else if (!strncmp(argv[i], "skip=", 5)) skip = parse_long_arg(argv[i] + 5);
        else if (!strncmp(argv[i], "seek=", 5)) seek = parse_long_arg(argv[i] + 5);
        else { fprintf(stderr, "dd: unknown operand: %s\n", argv[i]); return 2; }
    }
    if (bs <= 0)
        bs = 512;
    buf = malloc((size_t)bs);
    if (!buf)
        return 1;
    if (ifn && (in = open(ifn, O_RDONLY)) < 0) { perror("dd input"); free(buf); return 1; }
    if (ofn && (out = open(ofn, O_WRONLY|O_CREAT, 0666)) < 0) { perror("dd output"); free(buf); if (in != STDIN_FILENO) close(in); return 1; }
    if (skip) lseek(in, skip * bs, SEEK_SET);
    if (seek) lseek(out, seek * bs, SEEK_SET);
    while (count < 0 || blocks < count) {
        ssize_t n = read(in, buf, (size_t)bs);
        if (n < 0) { rc = 1; break; }
        if (n == 0) break;
        if (write(out, buf, (size_t)n) != n) { rc = 1; break; }
        blocks++;
    }
    if (in != STDIN_FILENO) close(in);
    if (out != STDOUT_FILENO) close(out);
    free(buf);
    return rc;
}

int applet_uname_main(int argc, char **argv)
{
    struct utsname u;
    int all = argc > 1 && !strcmp(argv[1], "-a");
    if (is_help(argc, argv)) { puts("usage: busierbox uname [-a]"); return 0; }
    if (uname(&u) != 0) { perror("uname"); return 1; }
    if (all) printf("%s %s %s %s %s\n", u.sysname, u.nodename, u.release, u.version, u.machine);
    else puts(u.sysname);
    return 0;
}

int applet_id_main(int argc, char **argv)
{
    if (is_help(argc, argv)) { puts("usage: busierbox id"); return 0; }
    printf("uid=%ld gid=%ld euid=%ld egid=%ld\n", (long)getuid(), (long)getgid(), (long)geteuid(), (long)getegid());
    return 0;
}

int applet_which_main(int argc, char **argv)
{
    const char *path = getenv("PATH");
    int i, rc = 0;
    if (is_help(argc, argv) || argc < 2) { puts("usage: busierbox which COMMAND..."); return argc < 2 ? 2 : 0; }
    for (i = 1; i < argc; i++) {
        char *p, *save = NULL, *dup = strdup(path ? path : "");
        int found = 0;
        for (p = strtok_r(dup, ":", &save); p; p = strtok_r(NULL, ":", &save)) {
            char full[PATH_MAX];
            snprintf(full, sizeof(full), "%s/%s", *p ? p : ".", argv[i]);
            if (access(full, X_OK) == 0) { puts(full); found = 1; break; }
        }
        free(dup);
        if (!found) rc = 1;
    }
    return rc;
}

int applet_readlink_main(int argc, char **argv)
{
    char buf[PATH_MAX];
    ssize_t n;
    if (is_help(argc, argv)) { puts("usage: busierbox readlink LINK"); return 0; }
    if (argc != 2) { puts("usage: busierbox readlink LINK"); return 2; }
    n = readlink(argv[1], buf, sizeof(buf) - 1);
    if (n < 0) { perror("readlink"); return 1; }
    buf[n] = '\0';
    puts(buf);
    return 0;
}

int applet_stat_main(int argc, char **argv)
{
    int i, rc = 0;
    if (is_help(argc, argv) || argc < 2) { puts("usage: busierbox stat FILE..."); return argc < 2 ? 2 : 0; }
    for (i = 1; i < argc; i++) {
        struct stat st;
        if (lstat(argv[i], &st) != 0) { perror(argv[i]); rc = 1; continue; }
        printf("%s: mode=%lo size=%ld uid=%ld gid=%ld inode=%ld nlink=%ld\n",
               argv[i], (unsigned long)st.st_mode, (long)st.st_size, (long)st.st_uid,
               (long)st.st_gid, (long)st.st_ino, (long)st.st_nlink);
    }
    return rc;
}

int applet_df_main(int argc, char **argv)
{
    int i, start = argc > 1 ? 1 : 0;
    if (is_help(argc, argv)) { puts("usage: busierbox df [PATH...]"); return 0; }
    puts("path               1K-blocks       used  available");
    for (i = start; i < argc || (argc == 1 && i == 0); i++) {
        const char *p = argc == 1 ? "." : argv[i];
        struct statvfs v;
        unsigned long blocks, avail, used;
        if (statvfs(p, &v) != 0) { perror(p); continue; }
        blocks = (unsigned long)((v.f_blocks * v.f_frsize) / 1024);
        avail = (unsigned long)((v.f_bavail * v.f_frsize) / 1024);
        used = blocks > avail ? blocks - avail : 0;
        printf("%-18s %10lu %10lu %10lu\n", p, blocks, used, avail);
        if (argc == 1) break;
    }
    return 0;
}

int applet_free_main(int argc, char **argv)
{
    FILE *fp;
    char line[160];
    if (is_help(argc, argv)) { puts("usage: busierbox free"); return 0; }
    fp = fopen("/proc/meminfo", "r");
    if (!fp) { perror("free: /proc/meminfo"); return 1; }
    while (fgets(line, sizeof(line), fp)) {
        if (!strncmp(line, "MemTotal:", 9) || !strncmp(line, "MemFree:", 8) ||
            !strncmp(line, "MemAvailable:", 13) || !strncmp(line, "SwapTotal:", 10) ||
            !strncmp(line, "SwapFree:", 9))
            fputs(line, stdout);
    }
    fclose(fp);
    return 0;
}

static int is_digits(const char *s)
{
    if (!*s) return 0;
    while (*s) if (!isdigit((unsigned char)*s++)) return 0;
    return 1;
}

int applet_ps_main(int argc, char **argv)
{
    DIR *d;
    struct dirent *de;
    if (is_help(argc, argv)) { puts("usage: busierbox ps"); return 0; }
    d = opendir("/proc");
    if (!d) { perror("ps: /proc"); return 1; }
    puts("PID     COMM");
    while ((de = readdir(d))) {
        char path[PATH_MAX], comm[128] = "?";
        FILE *fp;
        if (!is_digits(de->d_name)) continue;
        snprintf(path, sizeof(path), "/proc/%s/comm", de->d_name);
        fp = fopen(path, "r");
        if (fp) {
            if (!fgets(comm, sizeof(comm), fp)) strcpy(comm, "?");
            comm[strcspn(comm, "\n")] = '\0';
            fclose(fp);
        }
        printf("%-7s %s\n", de->d_name, comm);
    }
    closedir(d);
    return 0;
}

int applet_mount_main(int argc, char **argv)
{
    FILE *fp;
    char line[512];
    if (is_help(argc, argv)) { puts("usage: busierbox mount"); puts("prints /proc/mounts; does not mount filesystems"); return 0; }
    fp = fopen("/proc/mounts", "r");
    if (!fp) fp = fopen("/etc/mtab", "r");
    if (!fp) { perror("mounts"); return 1; }
    while (fgets(line, sizeof(line), fp)) fputs(line, stdout);
    fclose(fp);
    return 0;
}

int applet_env_main(int argc, char **argv)
{
    int i = 1;
    if (is_help(argc, argv)) { puts("usage: busierbox env [KEY=VALUE...] [COMMAND [ARG...]]"); return 0; }
    while (i < argc && strchr(argv[i], '=')) {
        char *eq = strchr(argv[i], '=');
        *eq = '\0';
        setenv(argv[i], eq + 1, 1);
        *eq = '=';
        i++;
    }
    if (i < argc) {
        execvp(argv[i], &argv[i]);
        perror("env exec");
        return 127;
    }
    for (i = 0; environ[i]; i++)
        puts(environ[i]);
    return 0;
}

int applet_cp_main(int argc, char **argv)
{
    FILE *in, *out;
    int rc;
    if (is_help(argc, argv)) { puts("usage: busierbox cp SRC DST"); return 0; }
    if (argc != 3) { puts("usage: busierbox cp SRC DST"); return 2; }
    in = fopen(argv[1], "rb");
    if (!in) { perror(argv[1]); return 1; }
    out = fopen(argv[2], "wb");
    if (!out) { perror(argv[2]); fclose(in); return 1; }
    rc = copy_stream(in, out);
    fclose(in); fclose(out);
    return rc;
}

int applet_mv_main(int argc, char **argv)
{
    if (is_help(argc, argv)) { puts("usage: busierbox mv SRC DST"); return 0; }
    if (argc != 3) { puts("usage: busierbox mv SRC DST"); return 2; }
    if (rename(argv[1], argv[2]) != 0) { perror("mv"); return 1; }
    return 0;
}

int applet_rm_main(int argc, char **argv)
{
    int i, rc = 0;
    if (is_help(argc, argv) || argc < 2) { puts("usage: busierbox rm FILE..."); return argc < 2 ? 2 : 0; }
    for (i = 1; i < argc; i++) if (unlink(argv[i]) != 0) { perror(argv[i]); rc = 1; }
    return rc;
}

int applet_mkdir_main(int argc, char **argv)
{
    int i, rc = 0;
    if (is_help(argc, argv) || argc < 2) { puts("usage: busierbox mkdir DIR..."); return argc < 2 ? 2 : 0; }
    for (i = 1; i < argc; i++) if (mkdir(argv[i], 0777) != 0) { perror(argv[i]); rc = 1; }
    return rc;
}

int applet_chmod_main(int argc, char **argv)
{
    mode_t mode;
    int i, rc = 0;
    if (is_help(argc, argv)) { puts("usage: busierbox chmod MODE FILE..."); return 0; }
    if (argc < 3) { puts("usage: busierbox chmod MODE FILE..."); return 2; }
    mode = (mode_t)strtol(argv[1], NULL, 8);
    for (i = 2; i < argc; i++) if (chmod(argv[i], mode) != 0) { perror(argv[i]); rc = 1; }
    return rc;
}

int applet_touch_main(int argc, char **argv)
{
    int i, rc = 0;
    if (is_help(argc, argv) || argc < 2) { puts("usage: busierbox touch FILE..."); return argc < 2 ? 2 : 0; }
    for (i = 1; i < argc; i++) {
        int fd = open(argv[i], O_WRONLY|O_CREAT, 0666);
        if (fd < 0 || close(fd) != 0 || utime(argv[i], NULL) != 0) { perror(argv[i]); rc = 1; if (fd >= 0) close(fd); }
    }
    return rc;
}

int applet_grep_main(int argc, char **argv)
{
    const char *pat;
    char line[4096];
    int i, rc = 1;
    if (is_help(argc, argv) || argc < 2) { puts("usage: busierbox grep-lite PATTERN [FILE...]"); return argc < 2 ? 2 : 0; }
    pat = argv[1];
    if (argc == 2) {
        while (fgets(line, sizeof(line), stdin)) if (strstr(line, pat)) { fputs(line, stdout); rc = 0; }
        return rc;
    }
    for (i = 2; i < argc; i++) {
        FILE *fp = fopen(argv[i], "r");
        if (!fp) { perror(argv[i]); continue; }
        while (fgets(line, sizeof(line), fp)) if (strstr(line, pat)) { fputs(line, stdout); rc = 0; }
        fclose(fp);
    }
    return rc;
}

int applet_sleep_main(int argc, char **argv)
{
    if (is_help(argc, argv)) { puts("usage: busierbox sleep SECONDS"); return 0; }
    if (argc != 2) { puts("usage: busierbox sleep SECONDS"); return 2; }
    sleep((unsigned int)atoi(argv[1]));
    return 0;
}

int applet_tee_main(int argc, char **argv)
{
    FILE **files = NULL;
    char buf[8192];
    size_t n;
    int i, rc = 0;
    if (is_help(argc, argv)) { puts("usage: busierbox tee [FILE...]"); return 0; }
    if (argc > 1) {
        files = calloc((size_t)argc - 1, sizeof(*files));
        if (!files) return 1;
        for (i = 1; i < argc; i++) {
            files[i - 1] = fopen(argv[i], "wb");
            if (!files[i - 1]) { perror(argv[i]); rc = 1; }
        }
    }
    while ((n = fread(buf, 1, sizeof(buf), stdin)) > 0) {
        fwrite(buf, 1, n, stdout);
        for (i = 1; i < argc; i++) if (files[i - 1]) fwrite(buf, 1, n, files[i - 1]);
    }
    for (i = 1; i < argc; i++) if (files && files[i - 1]) fclose(files[i - 1]);
    free(files);
    return rc;
}
