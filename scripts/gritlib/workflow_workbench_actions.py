"""Workbench action catalog records for grit-console workflows."""

import shlex

from gritlib.build_config import build_config_path
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.operator_network import operator_advertised_host
from gritlib.record_utils import record_count_by_key, records_by_key
from gritlib.service_status import configured_daemon_services
from gritlib.shell_utils import shquote
from gritlib.target_records import selected_target_context
from gritlib.workbench_jobs import (
    run_workbench_action_headless_command, start_workbench_job_headless_command,
)

def render_daemon_service_args(daemon_services):
    services = list(daemon_services or [])
    if not services:
        services = ["file-service", "command-queue"]
    return " ".join("--daemon-service " + shquote(service) for service in services)


def bringup_recommend_command(config_path, operator_host, release_dir, target_ctx=None, stage_recommended=False):
    target_ctx = target_ctx or {}
    parts = [
        "scripts/grit-console",
        "bringup",
        "--recommend-only",
        "--json",
        "--operator-config", config_path,
        "--operator-host", operator_host,
    ]
    if release_dir:
        parts.extend(["--release-dir", release_dir])
    if target_ctx.get("target_id"):
        parts.extend(["--target-id", target_ctx.get("target_id", "")])
    if target_ctx.get("target_label"):
        parts.extend(["--target-label", target_ctx.get("target_label", "")])
    for alias in target_ctx.get("target_aliases") or []:
        parts.extend(["--target-alias", alias])
    if stage_recommended:
        parts.append("--stage-recommended-artifact")
    return " ".join(shquote(str(part)) for part in parts)


def _workbench_configuration_action_records(config_path, build_config):
    return [
        {
            "id": "configure-binary",
            "category": "configuration",
            "label": "Configure griTTYkit binary options",
            "script": "scripts/menuconfig",
            "command": "scripts/menuconfig",
            "config_path": build_config,
            "writes_config": True,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "resolve-target",
            "category": "configuration",
            "label": "Resolve target/device preset metadata",
            "script": "scripts/lib/resolve-target",
            "command": "scripts/lib/resolve-target --config " + shquote(config_path),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_tooling_action_records(config_path):
    return [
        {
            "id": "tool-provider-check",
            "category": "tooling",
            "label": "Check payload tool provider compatibility",
            "script": "scripts/lib/check-tool-providers",
            "command": "scripts/lib/check-tool-providers --tool TOOL",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "dropin-tool-status",
            "category": "tooling",
            "label": "Inspect local drop-in tool status",
            "script": "scripts/tools/dropin-tool-status",
            "command": "scripts/tools/dropin-tool-status --tool TOOL --json",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "check-dropin-tool",
            "category": "tooling",
            "label": "Validate a candidate drop-in tool",
            "script": "scripts/tools/check-dropin-tool",
            "command": "scripts/tools/check-dropin-tool --tool TOOL --path PATH",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "install-dropin-tool",
            "category": "tooling",
            "label": "Install a validated drop-in payload tool",
            "script": "scripts/tools/install-dropin-tool",
            "command": "scripts/tools/install-dropin-tool --tool TOOL --source SOURCE",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_configuration_tooling_action_records(config_path, build_config):
    records = []
    records.extend(_workbench_configuration_action_records(config_path, build_config))
    records.extend(_workbench_tooling_action_records(config_path))
    return records


def _workbench_build_action_records(config_path):
    return [
        {
            "id": "package-artifact",
            "category": "build",
            "label": "Build/package selected artifact",
            "script": "make",
            "command": "make package",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": True,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "release-current",
            "category": "release",
            "label": "Build current target and stage a small release",
            "script": "scripts/lib/release-current",
            "command": "scripts/lib/release-current --config",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": True,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
    ]


def _workbench_bringup_action_records(config_path, release_dir, operator_host, target_ctx):
    return [
        {
            "id": "bringup-recommend",
            "category": "bringup",
            "label": "Generate bringup recommendation with current operator route",
            "script": "scripts/grit-console",
            "command": bringup_recommend_command(config_path, operator_host, release_dir, target_ctx),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "bringup-stage-recommended",
            "category": "bringup",
            "label": "Select and stage recommended bringup artifact",
            "script": "scripts/grit-console",
            "command": bringup_recommend_command(config_path, operator_host, release_dir, target_ctx, stage_recommended=True),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
    ]


def _workbench_artifact_trailer_action_records(config_path):
    return [
        {
            "id": "inspect-artifact",
            "category": "artifact",
            "label": "Inspect artifact metadata without execution",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console artifact inspect ARTIFACT",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "verify-artifact",
            "category": "artifact",
            "label": "Verify artifact integrity and execution",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console artifact verify ARTIFACT",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "configure-trailer",
            "category": "trailer",
            "label": "Configure runtime trailer overrides",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console artifact config set ARTIFACT KEY=VALUE",
            "config_path": config_path,
            "writes_config": True,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_release_action_records(config_path, release_dir):
    return [
        {
            "id": "make-release",
            "category": "release",
            "label": "Build release bundle",
            "script": "scripts/make-release",
            "command": "scripts/make-release --name NAME --targets native --payload-presets survey-core,default",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": True,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "release-index",
            "category": "release",
            "label": "Inspect release index",
            "script": "scripts/lib/release-index",
            "command": "scripts/lib/release-index --release-dir " + shquote(release_dir),
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "release-find",
            "category": "release",
            "label": "Find compatible release artifacts",
            "script": "scripts/lib/release-find",
            "command": "scripts/lib/release-find --release-dir " + shquote(release_dir) + " FIND_ARGS",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "release-self-test",
            "category": "release",
            "label": "Validate release bundle",
            "script": "scripts/lib/release-self-test",
            "command": "scripts/lib/release-self-test --release-dir " + shquote(release_dir) + " --json",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_build_artifact_release_action_records(config_path, release_dir, operator_host, target_ctx):
    records = []
    records.extend(_workbench_build_action_records(config_path))
    records.extend(_workbench_bringup_action_records(
        config_path,
        release_dir,
        operator_host,
        target_ctx,
    ))
    records.extend(_workbench_artifact_trailer_action_records(config_path))
    records.extend(_workbench_release_action_records(config_path, release_dir))
    return records


def _workbench_offline_source_action_records(config_path):
    return [
        {
            "id": "verify-sources",
            "category": "offline",
            "label": "Verify pinned source downloads",
            "script": "scripts/lib/verify-sources",
            "command": "scripts/lib/verify-sources",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "fetch-sources",
            "category": "offline",
            "label": "Fetch pinned source downloads",
            "script": "scripts/lib/fetch-sources",
            "command": "scripts/lib/fetch-sources",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "check-licensing",
            "category": "offline",
            "label": "Validate licensing and source policy",
            "script": "scripts/lib/check-licensing",
            "command": "scripts/lib/check-licensing",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_offline_mirror_action_records(config_path):
    return [
        {
            "id": "source-mirror-plan",
            "category": "offline",
            "label": "Plan source mirror for offline rebuilds",
            "script": "scripts/lib/mirror-sources",
            "command": "scripts/lib/mirror-sources --matrix tests/matrix/release-full.json --source-only --include-buildroot-packages --all-supported-tools --out MIRROR_DIR --dry-run",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "offline-readiness",
            "category": "offline",
            "label": "Check offline source mirror readiness",
            "script": "scripts/lib/check-offline-readiness",
            "command": "scripts/lib/check-offline-readiness --mirror MIRROR_DIR --matrix tests/matrix/release-full.json",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_offline_pack_action_records(config_path):
    return [
        {
            "id": "offline-pack",
            "category": "offline",
            "label": "Pack downloaded sources for transfer",
            "script": "scripts/lib/offline-pack",
            "command": "scripts/lib/offline-pack",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "offline-unpack",
            "category": "offline",
            "label": "Restore downloaded sources from offline pack",
            "script": "scripts/lib/offline-unpack",
            "command": "scripts/lib/offline-unpack ARCHIVE",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_offline_action_records(config_path):
    records = []
    records.extend(_workbench_offline_source_action_records(config_path))
    records.extend(_workbench_offline_mirror_action_records(config_path))
    records.extend(_workbench_offline_pack_action_records(config_path))
    return records


def _workbench_operator_daemon_action_records(config_path, daemon_command):
    return [
        {
            "id": "operator-daemon-start",
            "category": "daemon",
            "label": "Start operator daemon for selected services",
            "script": "scripts/grit-console",
            "command": daemon_command,
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": True,
            "background_supported": True,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_job_requested",
        },
        {
            "id": "operator-daemon-status",
            "category": "daemon",
            "label": "Inspect operator daemon and managed listener state",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " --status",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": False,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
        {
            "id": "operator-daemon-stop",
            "category": "daemon",
            "label": "Stop managed operator daemon services",
            "script": "scripts/grit-console",
            "command": "scripts/grit-console --config " + shquote(config_path) + " --stop",
            "config_path": config_path,
            "writes_config": False,
            "runs_build": False,
            "long_running": False,
            "background_supported": False,
            "requires_confirmation": True,
            "execution_default": "show-command",
            "target_execution": False,
            "event": "workbench_action_selected",
        },
    ]


def _workbench_systemd_user_action_record(
    config_path,
    daemon_service_args,
    action,
    label,
    *,
    writes_config=False,
    requires_confirmation=False,
):
    return {
        "id": f"systemd-user-{action}",
        "category": "daemon",
        "label": label,
        "script": "scripts/grit-console",
        "command": "scripts/grit-console --config " + shquote(config_path) + " " + daemon_service_args + " --systemd-user-action " + action,
        "config_path": config_path,
        "writes_config": bool(writes_config),
        "runs_build": False,
        "long_running": False,
        "background_supported": False,
        "requires_confirmation": bool(requires_confirmation),
        "execution_default": "show-command",
        "target_execution": False,
        "event": "workbench_action_selected",
    }


def _workbench_systemd_user_action_records(config_path, daemon_service_args):
    return [
        _workbench_systemd_user_action_record(
            config_path,
            daemon_service_args,
            "print",
            "Print systemd user service for operator daemon",
        ),
        _workbench_systemd_user_action_record(
            config_path,
            daemon_service_args,
            "install",
            "Install systemd user service for operator daemon",
            writes_config=True,
            requires_confirmation=True,
        ),
        _workbench_systemd_user_action_record(
            config_path,
            daemon_service_args,
            "start",
            "Start systemd user service for operator daemon",
            requires_confirmation=True,
        ),
        _workbench_systemd_user_action_record(
            config_path,
            daemon_service_args,
            "stop",
            "Stop systemd user service for operator daemon",
            requires_confirmation=True,
        ),
        _workbench_systemd_user_action_record(
            config_path,
            daemon_service_args,
            "restart",
            "Restart systemd user service for operator daemon",
            requires_confirmation=True,
        ),
        _workbench_systemd_user_action_record(
            config_path,
            daemon_service_args,
            "status",
            "Check systemd user service for operator daemon",
        ),
    ]


def _workbench_daemon_action_records(config_path, daemon_service_args, daemon_command):
    records = []
    records.extend(_workbench_operator_daemon_action_records(config_path, daemon_command))
    records.extend(_workbench_systemd_user_action_records(config_path, daemon_service_args))
    return records


def workbench_action_records(cfg):
    config_path = str(cfg.get("_config_path", DEFAULT_CONFIG))
    build_config = str(build_config_path(cfg))
    release_dir = str(cfg.get("release_dir") or ".")
    daemon_services = configured_daemon_services(cfg, [])
    daemon_service_args = render_daemon_service_args(daemon_services)
    daemon_command = "scripts/grit-console --config " + shquote(config_path) + " --daemon " + daemon_service_args
    target_ctx = selected_target_context(cfg)
    operator_host = operator_advertised_host(cfg)

    records = []
    records.extend(_workbench_configuration_tooling_action_records(config_path, build_config))
    records.extend(_workbench_build_artifact_release_action_records(config_path, release_dir, operator_host, target_ctx))
    records.extend(_workbench_offline_action_records(config_path))
    records.extend(_workbench_daemon_action_records(config_path, daemon_service_args, daemon_command))
    return annotate_workbench_actions(
        records,
        cfg,
        run_workbench_action_headless_command,
        start_workbench_job_headless_command,
    )


def annotate_workbench_actions(records, cfg, run_command_builder, start_job_command_builder):
    placeholder_tokens = {
        "NAME", "ARTIFACT", "KEY=VALUE", "VALUE", "LOCAL_PATH",
        "REQUEST_NAME", "RELEASE_SELECTOR", "FIND_ARGS", "TOOL",
        "PATH", "MIRROR_DIR", "SOURCE", "ARCHIVE",
    }
    for rec in records or []:
        action_id = str(rec.get("id") or "")
        command = str(rec.get("command") or "")
        try:
            command_tokens = shlex.split(command)
        except ValueError:
            command_tokens = command.split()
        has_placeholder = any(token in placeholder_tokens for token in command_tokens)
        background = rec.get("background_supported") is True
        foreground_runnable = bool(command and not background and not has_placeholder)
        requires_confirmation = rec.get("requires_confirmation") is True
        if has_placeholder:
            operator_action_state = "needs-input"
            operator_action_reason = "input-placeholder"
            can_run_from_curses_enter = False
            curses_enter_action = "use-action-11"
        elif background:
            operator_action_state = "background-ready"
            operator_action_reason = "start-background-job"
            can_run_from_curses_enter = True
            curses_enter_action = "start-job"
        elif requires_confirmation:
            operator_action_state = "confirm-required"
            operator_action_reason = "confirmation-required"
            can_run_from_curses_enter = False
            curses_enter_action = "use-action-11"
        elif foreground_runnable:
            operator_action_state = "ready"
            operator_action_reason = "run-now"
            can_run_from_curses_enter = False
            curses_enter_action = "use-action-11"
        else:
            operator_action_state = "unavailable"
            operator_action_reason = "no-runnable-command"
            can_run_from_curses_enter = False
            curses_enter_action = "none"
        rec["has_placeholder"] = bool(has_placeholder)
        rec["foreground_runnable"] = foreground_runnable
        rec["dry_run_supported"] = foreground_runnable
        rec["has_run_command"] = foreground_runnable
        rec["has_dry_run_command"] = foreground_runnable
        rec["has_start_job_command"] = background
        rec["operator_action_state"] = operator_action_state
        rec["operator_action_reason"] = operator_action_reason
        rec["can_run_from_curses_enter"] = bool(can_run_from_curses_enter)
        rec["curses_enter_action"] = curses_enter_action
        rec["run_command"] = run_command_builder(cfg, action_id) if foreground_runnable else ""
        rec["dry_run_command"] = run_command_builder(cfg, action_id, dry_run=True) if foreground_runnable else ""
        rec["start_job_command"] = start_job_command_builder(cfg, action_id) if background else ""
    return records


def workbench_action_indexes(records):
    return {
        "workbench_actions_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "workbench_actions_by_category": records_by_key(records, "category"),
        "workbench_actions_by_script": records_by_key(records, "script"),
        "workbench_actions_by_background_supported": records_by_key(records, "background_supported"),
        "workbench_actions_by_long_running": records_by_key(records, "long_running"),
        "workbench_actions_by_writes_config": records_by_key(records, "writes_config"),
        "workbench_actions_by_runs_build": records_by_key(records, "runs_build"),
        "workbench_actions_by_requires_confirmation": records_by_key(records, "requires_confirmation"),
        "workbench_actions_by_execution_default": records_by_key(records, "execution_default"),
        "workbench_actions_by_target_execution": records_by_key(records, "target_execution"),
        "workbench_actions_by_event": records_by_key(records, "event"),
        "workbench_actions_by_config_path": records_by_key(records, "config_path"),
        "workbench_actions_by_foreground_runnable": records_by_key(records, "foreground_runnable"),
        "workbench_actions_by_dry_run_supported": records_by_key(records, "dry_run_supported"),
        "workbench_actions_by_has_placeholder": records_by_key(records, "has_placeholder"),
        "workbench_actions_by_has_run_command": records_by_key(records, "has_run_command"),
        "workbench_actions_by_has_dry_run_command": records_by_key(records, "has_dry_run_command"),
        "workbench_actions_by_has_start_job_command": records_by_key(records, "has_start_job_command"),
        "workbench_actions_by_operator_action_state": records_by_key(records, "operator_action_state"),
        "workbench_actions_by_operator_action_reason": records_by_key(records, "operator_action_reason"),
        "workbench_actions_by_can_run_from_curses_enter": records_by_key(records, "can_run_from_curses_enter"),
        "workbench_actions_by_curses_enter_action": records_by_key(records, "curses_enter_action"),
    }


def workbench_action_summary(records):
    return {
        "total_count": len(records or []),
        "background_supported_count": len([rec for rec in records or [] if rec.get("background_supported") is True]),
        "long_running_count": len([rec for rec in records or [] if rec.get("long_running") is True]),
        "writes_config_count": len([rec for rec in records or [] if rec.get("writes_config") is True]),
        "runs_build_count": len([rec for rec in records or [] if rec.get("runs_build") is True]),
        "requires_confirmation_count": len([rec for rec in records or [] if rec.get("requires_confirmation") is True]),
        "target_execution_count": len([rec for rec in records or [] if rec.get("target_execution") is True]),
        "foreground_runnable_count": len([rec for rec in records or [] if rec.get("foreground_runnable") is True]),
        "dry_run_supported_count": len([rec for rec in records or [] if rec.get("dry_run_supported") is True]),
        "has_placeholder_count": len([rec for rec in records or [] if rec.get("has_placeholder") is True]),
        "has_run_command_count": len([rec for rec in records or [] if rec.get("has_run_command") is True]),
        "has_dry_run_command_count": len([rec for rec in records or [] if rec.get("has_dry_run_command") is True]),
        "has_start_job_command_count": len([rec for rec in records or [] if rec.get("has_start_job_command") is True]),
        "can_run_from_curses_enter_count": len([rec for rec in records or [] if rec.get("can_run_from_curses_enter") is True]),
        "category_counts": record_count_by_key(records, "category"),
        "script_counts": record_count_by_key(records, "script"),
        "execution_default_counts": record_count_by_key(records, "execution_default"),
        "event_counts": record_count_by_key(records, "event"),
        "config_path_counts": record_count_by_key(records, "config_path"),
        "foreground_runnable_counts": record_count_by_key(records, "foreground_runnable"),
        "dry_run_supported_counts": record_count_by_key(records, "dry_run_supported"),
        "has_placeholder_counts": record_count_by_key(records, "has_placeholder"),
        "has_run_command_counts": record_count_by_key(records, "has_run_command"),
        "has_dry_run_command_counts": record_count_by_key(records, "has_dry_run_command"),
        "has_start_job_command_counts": record_count_by_key(records, "has_start_job_command"),
        "operator_action_state_counts": record_count_by_key(records, "operator_action_state"),
        "operator_action_reason_counts": record_count_by_key(records, "operator_action_reason"),
        "can_run_from_curses_enter_counts": record_count_by_key(records, "can_run_from_curses_enter"),
        "curses_enter_action_counts": record_count_by_key(records, "curses_enter_action"),
    }


def workbench_action_status_summary(stats=None):
    stats = stats or {}
    return {
        "workbench_action_count": stats.get("total_count", 0),
        "workbench_action_background_supported_count": stats.get(
            "background_supported_count", 0
        ),
        "workbench_action_long_running_count": stats.get("long_running_count", 0),
        "workbench_action_writes_config_count": stats.get("writes_config_count", 0),
        "workbench_action_runs_build_count": stats.get("runs_build_count", 0),
        "workbench_action_requires_confirmation_count": stats.get(
            "requires_confirmation_count", 0
        ),
        "workbench_action_target_execution_count": stats.get(
            "target_execution_count", 0
        ),
        "workbench_action_foreground_runnable_count": stats.get(
            "foreground_runnable_count", 0
        ),
        "workbench_action_dry_run_supported_count": stats.get(
            "dry_run_supported_count", 0
        ),
        "workbench_action_has_placeholder_count": stats.get(
            "has_placeholder_count", 0
        ),
        "workbench_action_has_run_command_count": stats.get("has_run_command_count", 0),
        "workbench_action_has_dry_run_command_count": stats.get(
            "has_dry_run_command_count", 0
        ),
        "workbench_action_has_start_job_command_count": stats.get(
            "has_start_job_command_count", 0
        ),
        "workbench_action_can_run_from_curses_enter_count": stats.get(
            "can_run_from_curses_enter_count", 0
        ),
        "workbench_action_category_counts": stats.get("category_counts") or {},
        "workbench_action_script_counts": stats.get("script_counts") or {},
        "workbench_action_execution_default_counts": stats.get(
            "execution_default_counts"
        ) or {},
        "workbench_action_event_counts": stats.get("event_counts") or {},
        "workbench_action_config_path_counts": stats.get("config_path_counts") or {},
        "workbench_action_foreground_runnable_counts": stats.get(
            "foreground_runnable_counts"
        ) or {},
        "workbench_action_dry_run_supported_counts": stats.get(
            "dry_run_supported_counts"
        ) or {},
        "workbench_action_has_placeholder_counts": stats.get(
            "has_placeholder_counts"
        ) or {},
        "workbench_action_has_run_command_counts": stats.get(
            "has_run_command_counts"
        ) or {},
        "workbench_action_has_dry_run_command_counts": stats.get(
            "has_dry_run_command_counts"
        ) or {},
        "workbench_action_has_start_job_command_counts": stats.get(
            "has_start_job_command_counts"
        ) or {},
        "workbench_action_operator_action_state_counts": stats.get(
            "operator_action_state_counts"
        ) or {},
        "workbench_action_operator_action_reason_counts": stats.get(
            "operator_action_reason_counts"
        ) or {},
        "workbench_action_can_run_from_curses_enter_counts": stats.get(
            "can_run_from_curses_enter_counts"
        ) or {},
        "workbench_action_curses_enter_action_counts": stats.get(
            "curses_enter_action_counts"
        ) or {},
    }


def workbench_action_status_context(cfg):
    actions = workbench_action_records(cfg)
    stats = workbench_action_summary(actions)
    return {
        "actions": actions,
        "index_maps": workbench_action_indexes(actions),
        "stats": stats,
        "summary": workbench_action_status_summary(stats),
    }
