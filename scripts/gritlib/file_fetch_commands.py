"""Staged-file fetch command rendering helpers."""

import urllib.parse
from pathlib import Path

from gritlib.bridge_routes import target_route_context
from gritlib.config_utils import yes
from gritlib.operator_network import operator_advertised_host
from gritlib.shell_utils import shquote
from gritlib.target_context import selected_target_context


def render_fetch_command(request_name, cfg, host=None, force=False):
    host = operator_advertised_host(cfg, host=host)
    route = target_route_context(
        cfg,
        "file-service",
        direct_host=host,
        direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
    )
    target_ctx = selected_target_context(cfg)
    cmd = [
        "grit",
        "fetch",
        request_name,
        "--host",
        str(route.get("host") or host),
        "--port",
        str(route.get("port") or cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204)),
    ]
    if not yes(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes")):
        cmd.append("--no-tls")
    if force:
        cmd.append("--force")
    if target_ctx.get("target_id"):
        cmd.extend(["--target-id", target_ctx.get("target_id", "")])
    if target_ctx.get("target_label"):
        cmd.extend(["--target-label", target_ctx.get("target_label", "")])
    for alias in target_ctx.get("target_aliases") or []:
        cmd.extend(["--target-alias", alias])
    return " ".join(shquote(part) for part in cmd)


def render_staged_fetch_url(request_name, cfg, host=None):
    host = operator_advertised_host(cfg, host=host)
    route = target_route_context(
        cfg,
        "file-service",
        direct_host=host,
        direct_port=cfg.get("GRIT_OPERATOR_FILE_SERVICE_PORT", 22204),
    )
    scheme = "https" if yes(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes")) else "http"
    query = urllib.parse.urlencode({"name": str(request_name or "")})
    return (
        f"{scheme}://{route.get('host') or host}:"
        f"{route.get('port') or cfg.get('GRIT_OPERATOR_FILE_SERVICE_PORT', 22204)}"
        f"/fetch?{query}"
    )


def staged_fetch_output_name(request_name):
    name = Path(str(request_name or "")).name
    return name or "grit"


def staged_fetch_target_commands(request_name, cfg, output_name=None, executable=False):
    output = "./" + staged_fetch_output_name(output_name or request_name)
    url = render_staged_fetch_url(request_name, cfg)
    tls = yes(cfg.get("GRIT_OPERATOR_FILE_SERVICE_TLS", "yes"))
    wget_parts = ["wget"]
    if tls:
        wget_parts.append("--no-check-certificate")
    wget_parts.extend(["-O", output, url])
    curl_parts = ["curl", "-fLk" if tls else "-fL", "-o", output, url]
    commands = {
        "url": url,
        "wget": " ".join(shquote(part) for part in wget_parts),
        "curl": " ".join(shquote(part) for part in curl_parts),
        "grit": render_fetch_command(request_name, cfg),
    }
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or "OPERATOR_IP"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/fetch"
    if parsed.query:
        path += "?" + parsed.query
    if tls:
        commands["nc_note"] = "requires file-service TLS=no; use wget/curl/grit, or set GRIT_OPERATOR_FILE_SERVICE_TLS=no"
    else:
        safe_path = path.replace("'", "")
        safe_host = str(host).replace("'", "")
        commands["nc"] = (
            "printf 'GET "
            + safe_path
            + " HTTP/1.0\\r\\nHost: "
            + safe_host
            + "\\r\\nConnection: close\\r\\n\\r\\n' | nc "
            + shquote(str(host))
            + " "
            + shquote(str(port))
            + " | sed '1,/^\\r*$/d' > "
            + shquote(output)
        )
    if executable:
        commands["run"] = "chmod +x " + shquote(output) + " && " + shquote(output) + " --help"
    return commands


def print_staged_fetch_target_options(request_name, cfg, output_name=None, executable=False):
    commands = staged_fetch_target_commands(
        request_name,
        cfg,
        output_name=output_name,
        executable=executable,
    )
    print("  Target fetch options:")
    print(f"    url:   {commands['url']}")
    print(f"    wget:  {commands['wget']}")
    print(f"    curl:  {commands['curl']}")
    if commands.get("nc"):
        print(f"    nc:    {commands['nc']}")
    elif commands.get("nc_note"):
        print(f"    nc:    {commands['nc_note']}")
    print(f"    grit:  {commands['grit']}")
    if executable:
        print(f"    run:   {commands['run']}")
    return commands
