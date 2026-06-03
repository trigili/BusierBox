"""Line-console option metadata."""


SERVICE_OPTIONS = {
    "ssh": [
        ("GRIT_OPERATOR_REMOTE_FORWARD_PORT", "forward_port", "port the target opens for reverse forward"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP/hostname the target connects to"),
        ("GRIT_OPERATOR_SERVER_SSH_PORT", "GRIT_OPERATOR_SERVER_SSH_PORT", "operator SSH port"),
        ("GRIT_OPERATOR_SERVER_USER", "GRIT_OPERATOR_SERVER_USER", "SSH user on the operator side"),
        ("GRIT_OPERATOR_KNOWN_HOSTS_POLICY", "GRIT_OPERATOR_KNOWN_HOSTS_POLICY", "how to handle host key verification"),
    ],
    "tls-shell": [
        ("GRIT_RSHELL_SOCAT_PORT", "GRIT_RSHELL_SOCAT_PORT", "port to listen on (and target connects to)"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP/hostname for target-side command"),
        ("GRIT_RSHELL_ENCRYPTION", "encryption", "transport encryption: tls / none"),
        ("GRIT_RSHELL_ALLOW_PLAINTEXT", "GRIT_RSHELL_ALLOW_PLAINTEXT", "allow unencrypted fallback"),
        ("GRIT_RSHELL_TRANSPORT", "build", "active reverse-shell transport"),
        ("GRIT_RSHELL_SHELL_PROVIDER", "GRIT_RSHELL_SHELL_PROVIDER", "shell to launch on the target (auto/ash/bash/zsh)"),
    ],
    "plain-shell": [
        ("GRIT_RSHELL_SOCAT_PORT", "GRIT_RSHELL_SOCAT_PORT", "port to listen on"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP/hostname for target-side command"),
        ("GRIT_RSHELL_TRANSPORT", "build", "active reverse-shell transport"),
        ("GRIT_RSHELL_SHELL_PROVIDER", "GRIT_RSHELL_SHELL_PROVIDER", "shell to launch on the target"),
    ],
    "file-service": [
        ("GRIT_OPERATOR_FILE_SERVICE_PORT", "GRIT_OPERATOR_FILE_SERVICE_PORT", "file service listen port"),
        ("GRIT_OPERATOR_FILE_SERVICE_TLS", "GRIT_OPERATOR_FILE_SERVICE_TLS", "TLS for file service connections"),
        ("GRIT_OPERATOR_FILE_SERVICE_ENABLE", "GRIT_OPERATOR_FILE_SERVICE_ENABLE", "enable file service in zero-arg mode"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in staged fetch commands"),
    ],
    "command-queue": [
        ("GRIT_COMMAND_QUEUE_PORT", "GRIT_COMMAND_QUEUE_PORT", "command queue listen port"),
        ("GRIT_COMMAND_QUEUE_TLS", "GRIT_COMMAND_QUEUE_TLS", "TLS for command queue connections"),
        ("GRIT_COMMAND_QUEUE_ENABLE", "GRIT_COMMAND_QUEUE_ENABLE", "enable command queue in zero-arg mode"),
        ("GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "GRIT_COMMAND_QUEUE_REQUIRE_TOKEN", "require auth token from targets"),
        ("GRIT_COMMAND_QUEUE_TOKEN", "GRIT_COMMAND_QUEUE_TOKEN", "shared token (if token required)"),
        ("GRIT_COMMAND_QUEUE_EXECUTION", "GRIT_COMMAND_QUEUE_EXECUTION", "command execution mode"),
    ],
    "bridge": [
        ("GRIT_OPERATOR_TARGET_BIND_HOST", "GRIT_OPERATOR_TARGET_BIND_HOST", "bind address for bridge listeners"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP for generated commands"),
    ],
    "probe": [
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP listen port"),
        ("GRIT_PROBE_TFTP_PORT", "GRIT_PROBE_TFTP_PORT", "probe TFTP UDP listen port"),
        ("GRIT_PROBE_FTP_PORT", "GRIT_PROBE_FTP_PORT", "probe FTP listen port"),
        ("GRIT_PROBE_DNS_PORT", "GRIT_PROBE_DNS_PORT", "probe DNS UDP listen port"),
        ("GRIT_PROBE_DNS_NAME", "GRIT_PROBE_DNS_NAME", "probe DNS TXT query name"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in probe command"),
    ],
    "probe-tftp": [
        ("GRIT_PROBE_TFTP_PORT", "GRIT_PROBE_TFTP_PORT", "probe TFTP UDP listen port"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in TFTP command"),
    ],
    "probe-ftp": [
        ("GRIT_PROBE_FTP_PORT", "GRIT_PROBE_FTP_PORT", "probe FTP listen port"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in FTP command"),
    ],
    "probe-dns": [
        ("GRIT_PROBE_DNS_PORT", "GRIT_PROBE_DNS_PORT", "probe DNS UDP listen port"),
        ("GRIT_PROBE_DNS_NAME", "GRIT_PROBE_DNS_NAME", "probe DNS TXT query name"),
        ("GRIT_PROBE_PORT", "GRIT_PROBE_PORT", "probe HTTP result upload port embedded in probe.sh"),
        ("GRIT_OPERATOR_SERVER_HOST", "GRIT_OPERATOR_SERVER_HOST", "operator IP used in DNS command"),
    ],
}


GRIT_TO_CFG_KEY = {
    grit: cfg_key
    for entries in SERVICE_OPTIONS.values()
    for grit, cfg_key, _desc in entries
}
