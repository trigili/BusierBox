#ifndef GRIT_RSHELL_TLS_H
#define GRIT_RSHELL_TLS_H

#ifdef HAVE_WOLFSSL
int rshell_builtin_tls(const char *host, const char *port, const char *shell_cmd);
#endif

#endif /* GRIT_RSHELL_TLS_H */
