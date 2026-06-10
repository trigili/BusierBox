"""Workbench job path, state, record, and display helpers for grit-console."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from gritlib.console_display import console_table, print_dry_run_notice
from gritlib.event_log import append_event
from gritlib.line_context import set_line_collection_context
from gritlib.line_search import set_line_search_results
from gritlib.process_status import pid_alive, pid_environ_contains
from gritlib.record_utils import format_counts, record_count_by_key, record_sum_by_key, records_by_key
from gritlib.session_state import (
    atomic_write_json, elapsed_seconds, read_json_file, state_file_path, utc_now,
)
from gritlib.shell_utils import shquote
from gritlib.workflow_support import select_workbench_action


DEFAULT_OPERATOR_SESSION_DIR = Path("local/operator-session")
DEFAULT_CONFIG = "local/operator-session/config.json"
DEFAULT_SERVER_CONFIG = Path("local/server-config.json")


def parse_line_jobs_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd not in {"jobs", "job"}:
        return {}
    first = str(args[0]).lower() if args else ""
    if cmd == "job":
        return {"action": "select", "selector": " ".join(args).strip()}
    if len(args) >= 2 and first in {"-k", "--kill", "--cancel", "kill", "cancel"}:
        return {"action": "cancel", "selector": " ".join(args[1:]).strip()}
    if len(args) >= 2 and first in {"-i", "--info", "info", "select", "use"}:
        return {"action": "select", "selector": " ".join(args[1:]).strip()}
    if first in {"-v", "--verbose", "verbose", "details"}:
        return {"action": "list", "verbose": True}
    return {"action": "list", "verbose": False}


def dispatch_line_jobs_command(
    jobs_cmd,
    *,
    cancel_func=None,
    select_func=None,
    list_func=None,
):
    action = (jobs_cmd or {}).get("action")
    try:
        if action == "cancel" and cancel_func:
            return cancel_func(jobs_cmd.get("selector", ""))
        if action == "select" and select_func:
            return select_func(jobs_cmd.get("selector", ""))
        if action == "list" and list_func:
            return list_func(verbose=bool(jobs_cmd.get("verbose")))
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported jobs command")


def dispatch_legacy_line_job_number(
    choice,
    cfg,
    *,
    input_func=None,
    snapshot_func=None,
    actions_func=None,
):
    text = str(choice or "").strip()
    if text == "12":
        snap = snapshot_func(cfg) if snapshot_func else {}
        runnable = [rec for rec in snap.get("workbench_actions") or [] if rec.get("background_supported")]
        for idx, rec in enumerate(runnable, 1):
            print(f"{idx}: {rec.get('id', '')} {rec.get('command', '')}")
        selected_line = input_func("background module id or number> ") if input_func else None
        selected = selected_line.strip() if selected_line is not None else ""
        if selected:
            try:
                action = runnable[int(selected) - 1]["id"] if selected.isdigit() else selected
                headless = (
                    "scripts/grit-console --config "
                    + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
                    + " --start-workbench-job "
                    + shquote(action)
                )
                rec = start_workbench_job_record(
                    cfg,
                    actions_func() if actions_func else [],
                    action,
                    headless_command=headless,
                )
                print(f"started job {rec.get('id', '')}: pid={rec.get('pid', '')} log={rec.get('log_path', '')}")
            except (ValueError, IndexError) as exc:
                print(exc)
        return True
    if text == "13":
        snap = snapshot_func(cfg) if snapshot_func else {}
        for rec in snap.get("workbench_jobs") or []:
            print(
                f"{rec.get('id', '')}: action={rec.get('action_id', '')} "
                f"state={rec.get('effective_state', '')} "
                f"managed={'yes' if rec.get('pid_managed') else 'no'} "
                f"cancel_supported={'yes' if rec.get('cancel_supported') else 'no'}"
            )
        job_line = input_func("job id> ") if input_func else None
        job_id = job_line.strip() if job_line is not None else ""
        if job_id:
            try:
                headless = (
                    "scripts/grit-console --config "
                    + shquote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
                    + " --cancel-workbench-job "
                    + shquote(job_id)
                )
                rec = cancel_workbench_job_record(
                    cfg,
                    actions_func() if actions_func else [],
                    job_id,
                    headless_command=headless,
                )
                print(f"cancel requested for {rec.get('id', job_id)}")
            except ValueError as exc:
                print(exc)
        return True
    return False


def print_workbench_job_summary(doc):
    doc = doc or {}
    summary = doc.get("summary") or {}
    print(
        "Workbench job summary: "
        f"total={summary.get('workbench_job_count', 0)} "
        f"running={summary.get('workbench_job_running_count', 0)} "
        f"managed={summary.get('workbench_job_pid_managed_count', 0)} "
        f"cancel_supported={summary.get('workbench_job_cancel_supported_count', 0)} "
        f"logs={summary.get('workbench_job_log_exists_count', 0)} "
        f"log_bytes={summary.get('workbench_job_log_total_size', 0)} "
        f"tail_truncated={summary.get('workbench_job_last_output_tail_truncated_count', 0)} "
        f"exit_status_known={summary.get('workbench_job_exit_status_known_count', 0)} "
        f"duration_known={summary.get('workbench_job_duration_known_count', 0)} "
        f"elapsed_known={summary.get('workbench_job_elapsed_known_count', 0)} "
        f"background={summary.get('workbench_job_background_supported_count', 0)} "
        f"long_running={summary.get('workbench_job_long_running_count', 0)}"
    )
    print(f"  states: {format_counts(summary.get('workbench_job_effective_state_counts') or {})}")
    print(f"  outcomes: {format_counts(summary.get('workbench_job_outcome_counts') or {})}")


def print_workbench_job_ownership(rec):
    evidence = rec.get("ownership_evidence") or []
    if evidence:
        print(f"    ownership: {','.join(str(item) for item in evidence)}")
    else:
        print("    ownership: none")
    if rec.get("cancel_supported"):
        return
    if rec.get("pid") and rec.get("pid_alive") and not rec.get("pid_managed"):
        print("    cancel: disabled; ownership unverified")
    elif rec.get("pid"):
        print("    cancel: disabled; process is not alive")
    else:
        print("    cancel: disabled; no pid")


def print_line_workbench_job_records(records, verbose=False, command_builder=None, quote=shquote):
    records = list(records or [])
    command_builder = command_builder or (lambda _job_id: "")

    def _detail(rec):
        if not verbose:
            return []
        details = []
        if rec.get("log_path"):
            details.append(("log", rec["log_path"]))
        details.append(("cancel", command_builder(str(rec.get("id") or ""))))
        return details

    cols = [
        ("Job", "id"),
        ("Action", "action_id"),
        ("State", lambda r: r.get("effective_state") or r.get("state") or "-"),
        ("Managed", lambda r: "yes" if r.get("pid_managed") else "no"),
        ("Cancel", lambda r: "yes" if r.get("cancel_supported") else "no"),
    ]
    console_table(
        f"Jobs  ({len(records)} total)" if records else "Jobs  (none)",
        records, cols, detail_fn=_detail,
        footer="use N, job ID, jobs cancel ID, jobs ?",
    )
    return [
        {
            "kind": "job",
            "label": f"{rec.get('id','')} action={rec.get('action_id','')} state={rec.get('effective_state','')}",
            "rec": rec,
            "command": command_builder(str(rec.get("id") or "")),
            "use_hint": f"use job {quote(str(rec.get('id', '')))}",
        }
        for rec in records
    ]


def workbench_job_record_by_selector(records, selector):
    text = str(selector or "").strip()
    if not text:
        return {}
    records = list(records or [])
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(records):
            return records[idx]
    for rec in records:
        if str(rec.get("id") or "") == text:
            return rec
    return {}


def require_workbench_job_record(records, selector):
    text = str(selector or "").strip()
    rec = workbench_job_record_by_selector(records, text)
    if not rec and text.isdigit():
        raise ValueError(f"job number out of range: {text}")
    if not rec:
        raise ValueError(f"unknown workbench job: {text}")
    return rec


def line_job_record(snapshot, selector):
    return workbench_job_record_by_selector(
        (snapshot or {}).get("workbench_jobs") or [],
        selector,
    )


def current_line_job_record(snapshot_func, selector):
    snapshot = snapshot_func() if snapshot_func else {}
    return line_job_record(snapshot, selector)


def print_line_jobs(
    cfg, snapshot, verbose=False, command_builder=None, quote=shquote
):
    jobs = (snapshot or {}).get("workbench_jobs") or []
    search_records = print_line_workbench_job_records(
        jobs,
        verbose=verbose,
        command_builder=command_builder,
        quote=quote,
    )
    set_line_search_results(cfg, search_records)
    append_event(cfg, "workbench", "workbench_jobs_listed", details={
        "job_count": len(jobs),
        "verbose": bool(verbose),
    })
    return jobs


def print_current_line_jobs(
    cfg, snapshot_func, verbose=False, command_builder=None, quote=shquote
):
    snapshot = snapshot_func() if snapshot_func else {}
    return print_line_jobs(
        cfg,
        snapshot,
        verbose=verbose,
        command_builder=command_builder,
        quote=quote,
    )


def select_line_job(cfg, snapshot, selector):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage:\n  use job ID\n  use job N")
    rec = require_workbench_job_record((snapshot or {}).get("workbench_jobs") or [], text)
    job_id = str(rec.get("id") or "")
    set_line_collection_context(cfg, f"job/{job_id}")
    state = rec.get("effective_state") or rec.get("state") or "?"
    action = rec.get("action_id") or "-"
    cancel = "  |  cancellable" if rec.get("cancel_supported") else ""
    print(f"  {job_id}  —  {state}  |  {action}{cancel}")
    if rec.get("cancel_supported"):
        print("  info, options, cancel, jobs, back")
    else:
        print("  info, options, jobs, back")
    append_event(cfg, "workbench", "workbench_job_selected", details={
        "job_id": job_id,
        "action_id": rec.get("action_id", ""),
        "effective_state": rec.get("effective_state", ""),
    })
    return rec


def select_current_line_job(cfg, snapshot_func, selector):
    snapshot = snapshot_func() if snapshot_func else {}
    return select_line_job(cfg, snapshot, selector)


def cancel_line_job(
    cfg, snapshot, actions, selector, command_builder=None
):
    text = str(selector or "").strip()
    if not text:
        module = str(cfg.get("_line_console_module") or "")
        if module.startswith("job/"):
            text = module.split("/", 1)[1]
    rec = require_workbench_job_record((snapshot or {}).get("workbench_jobs") or [], text)
    job_id = str(rec.get("id") or text)
    command_builder = command_builder or cancel_workbench_job_headless_command
    headless = command_builder(cfg, job_id)
    cancelled = cancel_workbench_job_record(
        cfg,
        actions,
        job_id,
        headless_command=headless,
    )
    print(f"cancel requested for {cancelled.get('id', job_id)}")
    return cancelled


def cancel_current_line_job(
    cfg, snapshot_func, actions_func, selector, command_builder=None
):
    snapshot = snapshot_func() if snapshot_func else {}
    actions = actions_func() if actions_func else []
    return cancel_line_job(
        cfg,
        snapshot,
        actions,
        selector,
        command_builder=command_builder,
    )


def start_line_job(
    cfg,
    action_selector="",
    *,
    select_action_func=None,
    selected_action_func=None,
    actions_func=None,
    headless_command_func=None,
    start_job_func=None,
):
    selector = str(action_selector or "").strip()
    if selector:
        if not select_action_func:
            raise ValueError("module selection support is unavailable")
        action = select_action_func(selector)
    else:
        if not selected_action_func:
            raise ValueError("selected module support is unavailable")
        action = selected_action_func()
    if not action or str(action.get("kind") or "") != "workbench":
        raise ValueError("no selected background-capable workbench module; use module MODULE first")
    if action.get("background_supported") is not True:
        raise ValueError(f"workbench module is not background-capable: {action.get('id', '')}")
    action_id = str(action.get("id") or "")
    if not headless_command_func or not start_job_func or not actions_func:
        raise ValueError("workbench job start support is unavailable")
    headless = headless_command_func(cfg, action_id)
    rec = start_job_func(
        cfg,
        actions_func(),
        action_id,
        headless_command=headless,
    )
    print(f"started job {rec.get('id', '')}: pid={rec.get('pid', '')} log={rec.get('log_path', '')}")
    return rec


def record_workbench_refresh(cfg, reason="manual", default_config=DEFAULT_SERVER_CONFIG):
    state = read_json_file(state_file_path(cfg), {"schema": 1, "services": {}})
    services = state.setdefault("services", {})
    rec = services.setdefault("workbench", {})
    count = int(rec.get("refresh_count", 0) or 0) + 1
    now = utc_now()
    headless = "scripts/grit-console --config " + shquote(str(cfg.get("_config_path", default_config))) + " --status"
    rec.update({
        "status": rec.get("status") or "open",
        "last_refresh_at": now,
        "refresh_count": count,
    })
    atomic_write_json(state_file_path(cfg), state)
    append_event(cfg, "workbench", "workbench_refreshed", details={
        "reason": reason,
        "refresh_count": count,
        "headless_command": headless,
    })
    rec["headless_command"] = headless
    return rec


def dispatch_legacy_refresh_choice(choice, cfg):
    if str(choice or "").strip() != "r":
        return False
    rec = record_workbench_refresh(cfg)
    print(f"refreshed workbench at {rec.get('last_refresh_at', '')}")
    return True


def workbench_jobs_path(cfg, default_operator_session_dir=DEFAULT_OPERATOR_SESSION_DIR):
    return Path(str(
        cfg.get("workbench_jobs_file") or
        Path(str(cfg.get("operator_session_dir", default_operator_session_dir))) / "workbench-jobs.json"
    ))


def workbench_jobs_state_record(cfg):
    path = workbench_jobs_path(cfg)
    rec = {
        "path": str(path),
        "exists": False,
        "valid": False,
        "schema": None,
        "job_count": 0,
        "error": "",
    }
    try:
        rec["exists"] = path.exists()
        if not rec["exists"]:
            return rec
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            rec["error"] = "workbench-jobs JSON is not an object"
            return rec
        jobs = data.get("jobs")
        if not isinstance(jobs, list):
            rec["error"] = "workbench-jobs JSON jobs field is not a list"
            return rec
        rec.update({
            "valid": True,
            "schema": data.get("schema"),
            "job_count": len(jobs),
        })
    except (OSError, json.JSONDecodeError) as exc:
        rec["error"] = str(exc)
    return rec


def workbench_jobs_state_status(cfg):
    state_record = workbench_jobs_state_record(cfg)
    state_record["has_jobs"] = int(state_record.get("job_count") or 0) > 0
    state_records = [state_record]
    state_index_maps = {
        "workbench_jobs_state_records_by_path": {
            rec.get("path", ""): rec for rec in state_records if rec.get("path")
        },
        "workbench_jobs_state_records_by_exists": records_by_key(
            state_records, "exists"
        ),
        "workbench_jobs_state_records_by_valid": records_by_key(
            state_records, "valid"
        ),
        "workbench_jobs_state_records_by_has_jobs": records_by_key(
            state_records, "has_jobs"
        ),
    }
    return {
        "state_record": state_record,
        "state_records": state_records,
        "state_index_maps": state_index_maps,
    }


def tail_text_file(path_text, line_limit=20, byte_limit=8192):
    path = Path(str(path_text or ""))
    if not path.is_file():
        return []
    try:
        data = path.read_bytes()
    except OSError:
        return []
    if len(data) > byte_limit:
        data = data[-byte_limit:]
    text = data.decode("utf-8", errors="replace")
    return text.splitlines()[-int(line_limit or 20):]


def workbench_job_log_tail_record(path_text, line_limit=20, byte_limit=8192):
    path = Path(str(path_text or ""))
    line_limit = int(line_limit or 20)
    byte_limit = int(byte_limit or 8192)
    rec = {
        "exists": False,
        "size": 0,
        "tail": [],
        "tail_count": 0,
        "tail_line_limit": line_limit,
        "tail_byte_limit": byte_limit,
        "tail_truncated": False,
        "line_count": 0,
    }
    if not path.is_file():
        return rec
    rec["exists"] = True
    try:
        data = path.read_bytes()
    except OSError:
        return rec
    rec["size"] = len(data)
    truncated_by_bytes = len(data) > byte_limit
    tail_data = data[-byte_limit:] if truncated_by_bytes else data
    text = tail_data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not truncated_by_bytes:
        rec["line_count"] = len(lines)
    tail = lines[-line_limit:]
    rec["tail"] = tail
    rec["tail_count"] = len(tail)
    rec["tail_truncated"] = truncated_by_bytes or len(lines) > line_limit
    return rec


def load_workbench_jobs(cfg):
    data = read_json_file(workbench_jobs_path(cfg), {"schema": 1, "jobs": []})
    if not isinstance(data, dict):
        data = {"schema": 1, "jobs": []}
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    data.setdefault("schema", 1)
    return data


def write_workbench_jobs(cfg, data):
    data.setdefault("schema", 1)
    if not isinstance(data.get("jobs"), list):
        data["jobs"] = []
    atomic_write_json(workbench_jobs_path(cfg), data)


def next_workbench_job_id(data):
    existing = {str(rec.get("id") or "") for rec in data.get("jobs") or [] if isinstance(rec, dict)}
    base = f"job-{int(time.time())}-{os.getpid()}"
    if base not in existing:
        return base
    for idx in range(2, 1000):
        candidate = f"{base}-{idx}"
        if candidate not in existing:
            return candidate
    raise ValueError("unable to allocate unique workbench job id")


def run_workbench_action_record(cfg, actions, selector, dry_run=False, confirmed=False, show_commands=True):
    action = select_workbench_action(actions, selector)
    action_id = str(action.get("id") or "")
    command = workbench_action_command_for_run(action, dry_run=dry_run)
    if not command:
        raise ValueError("workbench action has no command")
    if action.get("background_supported") is True:
        raise ValueError(f"workbench action is background-capable; use --start-workbench-job for {action_id}")
    if not dry_run and action.get("requires_confirmation") is True and not confirmed:
        raise ValueError(f"workbench action requires --confirm-workbench-action: {action_id}")
    if any(token in command for token in (" NAME ", " ARTIFACT ", "KEY=VALUE", "VALUE")):
        raise ValueError("workbench action command contains placeholders and must be configured before running")

    headless = run_workbench_action_headless_command(
        cfg,
        action_id,
        dry_run=dry_run,
        confirmed=confirmed,
    )
    print(f"workbench action: {action_id}")
    if show_commands:
        print(f"command={command}")
    append_event(cfg, "workbench", "workbench_action_run_requested", details={
        "action_id": action_id,
        "category": action.get("category", ""),
        "script": action.get("script", ""),
        "command": command,
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "headless_command": headless,
    })

    if dry_run and "--systemd-user-action" not in command:
        print_dry_run_notice(machine=show_commands)
        append_event(cfg, "workbench", "workbench_action_dry_run", details={
            "action_id": action_id,
            "category": action.get("category", ""),
            "script": action.get("script", ""),
            "command": command,
            "headless_command": headless,
        })
        return 0

    result = subprocess.run(
        ["/bin/sh", "-c", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)
    append_event(cfg, "workbench", "workbench_action_run_completed", details={
        "action_id": action_id,
        "category": action.get("category", ""),
        "script": action.get("script", ""),
        "command": command,
        "dry_run": bool(dry_run),
        "confirmed": bool(confirmed),
        "returncode": int(result.returncode),
        "headless_command": headless,
    })
    return int(result.returncode)


def start_workbench_job_record(
    cfg, actions, action_id, command_override=None, headless_command=""
):
    actions_by_id = {rec.get("id", ""): rec for rec in actions or [] if rec.get("id")}
    action = actions_by_id.get(str(action_id or ""))
    if not action:
        raise ValueError(f"unknown workbench action: {action_id}")
    if action.get("background_supported") is not True:
        raise ValueError(f"workbench action is not background-capable: {action_id}")
    command = str(command_override or action.get("command") or "").strip()
    if not command:
        raise ValueError("workbench action has no command")
    if not command_override and any(token in command for token in (" NAME ", " ARTIFACT ", "KEY=VALUE")):
        raise ValueError("workbench action command contains placeholders and must be configured before running")
    headless_command = headless_command or start_workbench_job_headless_command(cfg, action_id, command_override=command_override)
    data = load_workbench_jobs(cfg)
    job_id = next_workbench_job_id(data)
    operator_dir = Path(str(cfg.get("operator_session_dir", DEFAULT_OPERATOR_SESSION_DIR)))
    log_dir = operator_dir / "jobs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job_id}.log"
    exit_status_path = log_dir / f"{job_id}.exit-status"
    finished_at_path = log_dir / f"{job_id}.finished-at"
    env = os.environ.copy()
    env["GRIT_WORKBENCH_JOB_ID"] = job_id
    env["GRIT_WORKBENCH_ACTION_ID"] = str(action_id)
    env["GRIT_WORKBENCH_JOBS_FILE"] = str(workbench_jobs_path(cfg))
    wrapped_command = (
        "(\n"
        f"{command}\n"
        ")\n"
        "_grit_status=$?\n"
        f"printf '%s\\n' \"$_grit_status\" > {shquote(str(exit_status_path))}\n"
        f"date -u '+%Y-%m-%dT%H:%M:%SZ' > {shquote(str(finished_at_path))}\n"
        "exit \"$_grit_status\"\n"
    )
    with log_path.open("ab") as log:
        proc = subprocess.Popen(
            ["/bin/sh", "-c", wrapped_command],
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
        )
    rec = {
        "id": job_id,
        "action_id": str(action_id),
        "category": action.get("category", ""),
        "script": action.get("script", ""),
        "command": command,
        "state": "running",
        "pid": proc.pid,
        "process_group_id": proc.pid,
        "managed_by": "grit-console-workbench",
        "managed_by_pid": os.getpid(),
        "started_at": utc_now(),
        "log_path": str(log_path),
        "exit_status_path": str(exit_status_path),
        "finished_at_path": str(finished_at_path),
    }
    data["jobs"].append(rec)
    write_workbench_jobs(cfg, data)
    append_event(cfg, "workbench", "workbench_job_started", details={
        "job_id": job_id,
        "action_id": action_id,
        "command": command,
        "pid": proc.pid,
        "log_path": str(log_path),
        "headless_command": headless_command,
    })
    return {item.get("id"): item for item in workbench_job_records(cfg, [action])}.get(job_id, rec)


def cancel_workbench_job_record(cfg, actions, job_id, headless_command=""):
    data = load_workbench_jobs(cfg)
    for rec in data.get("jobs") or []:
        if not isinstance(rec, dict) or str(rec.get("id") or "") != str(job_id):
            continue
        current = {
            item.get("id"): item
            for item in workbench_job_records(cfg, actions)
        }.get(str(job_id), rec)
        if not current.get("cancel_supported"):
            raise ValueError(f"workbench job is not cancellable with current ownership evidence: {job_id}")
        pid = int(current.get("pid"))
        process_group = int(current.get("process_group_id") or pid)
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as exc:
            raise ValueError(f"unable to cancel workbench job {job_id}: {exc}") from exc
        rec.update({
            "state": "cancelling",
            "cancel_requested_at": utc_now(),
            "cancel_signal": "SIGTERM",
        })
        write_workbench_jobs(cfg, data)
        append_event(cfg, "workbench", "workbench_job_cancel_requested", details={
            "job_id": job_id,
            "pid": pid,
            "process_group_id": process_group,
            "ownership_evidence": current.get("ownership_evidence") or [],
            "headless_command": headless_command or cancel_workbench_job_headless_command(cfg, job_id),
        })
        return current
    raise ValueError(f"unknown workbench job: {job_id}")


def read_workbench_job_exit_status(path_text):
    path = Path(str(path_text or ""))
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text or not text.lstrip("-").isdigit():
        return None
    return int(text)


def workbench_job_ownership_evidence(pid, rec):
    if not pid:
        return []
    rec = rec if isinstance(rec, dict) else {}
    job_id = str(rec.get("id") or "")
    action_id = str(rec.get("action_id") or "")
    evidence = []
    if str(rec.get("managed_by") or "") == "grit-console-workbench":
        evidence.append("ledger:managed-by-workbench")
    if job_id and pid_environ_contains(pid, "GRIT_WORKBENCH_JOB_ID", job_id):
        evidence.append("environ:job-id")
    if action_id and pid_environ_contains(pid, "GRIT_WORKBENCH_ACTION_ID", action_id):
        evidence.append("environ:action-id")
    return evidence


def workbench_job_has_cancel_ownership(evidence):
    evidence = set(evidence or [])
    return "environ:job-id" in evidence and "environ:action-id" in evidence


def _workbench_actions_by_id(actions):
    return {rec.get("id", ""): rec for rec in (actions or []) if rec.get("id")}


def _workbench_job_process_state(rec):
    pid = rec.get("pid")
    pid_is_alive = pid_alive(pid) if pid else False
    state = str(rec.get("state") or "unknown")
    effective_state = state
    if state in ("starting", "running") and pid and not pid_is_alive:
        effective_state = "exited"
    ownership_evidence = workbench_job_ownership_evidence(pid, rec)
    cancel_ownership = workbench_job_has_cancel_ownership(ownership_evidence)
    return {
        "pid": pid,
        "pid_is_alive": pid_is_alive,
        "state": state,
        "effective_state": effective_state,
        "ownership_evidence": ownership_evidence,
        "cancel_ownership": cancel_ownership,
    }


def _read_workbench_job_finished_at(rec, finished_at_path):
    finished_at = str(rec.get("finished_at") or "")
    if not finished_at and finished_at_path and Path(finished_at_path).is_file():
        try:
            finished_at = Path(finished_at_path).read_text(encoding="utf-8").strip()
        except OSError:
            finished_at = ""
    return finished_at


def _workbench_job_completion_state(rec):
    exit_status_path = str(rec.get("exit_status_path") or "")
    finished_at_path = str(rec.get("finished_at_path") or "")
    exit_status = rec.get("exit_status")
    if exit_status in (None, ""):
        exit_status = read_workbench_job_exit_status(exit_status_path)
    exit_status_known = isinstance(exit_status, int)
    finished_at = _read_workbench_job_finished_at(rec, finished_at_path)
    started_at = str(rec.get("started_at") or "")
    duration_sec = elapsed_seconds(started_at, finished_at) if finished_at else None
    elapsed_sec = elapsed_seconds(started_at, utc_now()) if started_at else None
    outcome = "unknown"
    if exit_status_known:
        outcome = "succeeded" if exit_status == 0 else "failed"
    return {
        "exit_status_path": exit_status_path,
        "finished_at_path": finished_at_path,
        "exit_status": exit_status,
        "exit_status_known": exit_status_known,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "elapsed_sec": elapsed_sec,
        "outcome": outcome,
    }


def _workbench_job_tail_state(rec, log_path):
    log_tail = workbench_job_log_tail_record(log_path, rec.get("tail_limit", 20))
    output_tail = log_tail.get("tail") or []
    return {
        "log_exists": bool(log_tail.get("exists", False)),
        "log_size": int(log_tail.get("size", 0) or 0),
        "last_output_tail": output_tail,
        "last_output_tail_count": len(output_tail),
        "last_output_tail_truncated": bool(log_tail.get("tail_truncated", False)),
        "last_output_tail_line_limit": int(log_tail.get("tail_line_limit", 20) or 20),
        "last_output_tail_byte_limit": int(log_tail.get("tail_byte_limit", 8192) or 8192),
        "log_line_count": int(log_tail.get("line_count", 0) or 0),
    }


def _apply_workbench_job_record_fields(rec, action, process_state, completion_state, tail_state):
    log_path = str(rec.get("log_path") or "")
    cancel_supported = bool(
        process_state["pid"]
        and process_state["pid_is_alive"]
        and process_state["cancel_ownership"]
        and action.get("background_supported") is True
    )
    rec.update({
        "action_id": str(rec.get("action_id") or ""),
        "action_label": action.get("label", ""),
        "category": rec.get("category") or action.get("category", ""),
        "script": rec.get("script") or action.get("script", ""),
        "command": str(rec.get("command") or action.get("command", "")),
        "state": process_state["state"],
        "effective_state": process_state["effective_state"],
        "pid_alive": process_state["pid_is_alive"],
        "pid_managed": bool(process_state["cancel_ownership"]),
        "ownership_evidence": process_state["ownership_evidence"],
        "cancel_supported": cancel_supported,
        "log_path": log_path,
        "exit_status_path": completion_state["exit_status_path"],
        "finished_at_path": completion_state["finished_at_path"],
        "exit_status": completion_state["exit_status"] if completion_state["exit_status_known"] else "",
        "exit_status_known": completion_state["exit_status_known"],
        "started_at": completion_state["started_at"],
        "started_at_known": bool(completion_state["started_at"]),
        "finished_at": completion_state["finished_at"],
        "finished_at_known": bool(completion_state["finished_at"]),
        "duration_sec": completion_state["duration_sec"] if completion_state["duration_sec"] is not None else "",
        "duration_known": completion_state["duration_sec"] is not None,
        "elapsed_sec": completion_state["elapsed_sec"] if completion_state["elapsed_sec"] is not None else "",
        "elapsed_known": completion_state["elapsed_sec"] is not None,
        "outcome": completion_state["outcome"],
        **tail_state,
        "background_supported": bool(action.get("background_supported", False)),
        "long_running": bool(action.get("long_running", False)),
    })


def _workbench_job_record(raw, actions_by_id):
    rec = dict(raw)
    action = actions_by_id.get(str(rec.get("action_id") or "")) or {}
    process_state = _workbench_job_process_state(rec)
    completion_state = _workbench_job_completion_state(rec)
    log_path = str(rec.get("log_path") or "")
    tail_state = _workbench_job_tail_state(rec, log_path)
    _apply_workbench_job_record_fields(
        rec, action, process_state, completion_state, tail_state
    )
    return rec


def workbench_job_records(cfg, actions):
    data = load_workbench_jobs(cfg)
    actions_by_id = _workbench_actions_by_id(actions)
    records = []
    for raw in data.get("jobs") or []:
        if isinstance(raw, dict):
            records.append(_workbench_job_record(raw, actions_by_id))
    return records


def reconcile_workbench_job_completion_events(cfg):
    data = load_workbench_jobs(cfg)
    changed = False
    completion_events = []
    for rec in data.get("jobs") or []:
        if not isinstance(rec, dict) or rec.get("completed_event_at"):
            continue
        exit_status = rec.get("exit_status")
        if exit_status in (None, ""):
            exit_status = read_workbench_job_exit_status(rec.get("exit_status_path", ""))
        if not isinstance(exit_status, int):
            continue
        finished_at = str(rec.get("finished_at") or "")
        finished_at_path = str(rec.get("finished_at_path") or "")
        if not finished_at and finished_at_path and Path(finished_at_path).is_file():
            try:
                finished_at = Path(finished_at_path).read_text(encoding="utf-8").strip()
            except OSError:
                finished_at = ""
        if not finished_at:
            finished_at = utc_now()
        outcome = "succeeded" if exit_status == 0 else "failed"
        event_at = utc_now()
        rec.update({
            "state": "exited",
            "exit_status": exit_status,
            "finished_at": finished_at,
            "outcome": outcome,
            "completed_event_at": event_at,
        })
        changed = True
        completion_events.append({
            "job_id": rec.get("id", ""),
            "action_id": rec.get("action_id", ""),
            "exit_status": exit_status,
            "outcome": outcome,
            "finished_at": finished_at,
            "log_path": rec.get("log_path", ""),
        })
    if changed:
        write_workbench_jobs(cfg, data)
        for details in completion_events:
            append_event(cfg, "workbench", "workbench_job_completed", details=details)


def start_workbench_job_headless_command(
    cfg, action_id, command_override=None, default_config=DEFAULT_CONFIG
):
    parts = [
        "scripts/grit-console",
        "--config",
        str(cfg.get("_config_path", default_config)),
        "--start-workbench-job",
        str(action_id or ""),
    ]
    if command_override:
        parts.extend(["--job-command", str(command_override)])
    return " ".join(shquote(part) for part in parts)


def cancel_workbench_job_headless_command(cfg, job_id, default_config=DEFAULT_CONFIG):
    return (
        "scripts/grit-console --config "
        + shquote(str(cfg.get("_config_path", default_config)))
        + " --cancel-workbench-job "
        + shquote(str(job_id or ""))
    )


def run_workbench_action_headless_command(
    cfg, action_id, dry_run=False, confirmed=False, default_config=DEFAULT_SERVER_CONFIG
):
    parts = [
        "scripts/grit-console",
        "--config",
        str(cfg.get("_config_path", default_config)),
        "--run-workbench-action",
        str(action_id or ""),
    ]
    if dry_run:
        parts.append("--workbench-action-dry-run")
    if confirmed:
        parts.append("--confirm-workbench-action")
    return " ".join(shquote(str(part)) for part in parts)


def workbench_action_command_for_run(action, dry_run=False):
    command = str(action.get("command") or "").strip()
    if dry_run and "--systemd-user-action" in command and "--systemd-user-dry-run" not in command:
        command = command + " --systemd-user-dry-run"
    return command


def workbench_job_indexes(records):
    return {
        "workbench_jobs_by_id": {rec.get("id", ""): rec for rec in records or [] if rec.get("id")},
        "workbench_jobs_by_action": records_by_key(records, "action_id"),
        "workbench_jobs_by_state": records_by_key(records, "state"),
        "workbench_jobs_by_effective_state": records_by_key(records, "effective_state"),
        "workbench_jobs_by_category": records_by_key(records, "category"),
        "workbench_jobs_by_script": records_by_key(records, "script"),
        "workbench_jobs_by_pid": records_by_key(records, "pid"),
        "workbench_jobs_by_pid_managed": records_by_key(records, "pid_managed"),
        "workbench_jobs_by_cancel_supported": records_by_key(records, "cancel_supported"),
        "workbench_jobs_by_log_exists": records_by_key(records, "log_exists"),
        "workbench_jobs_by_exit_status_known": records_by_key(records, "exit_status_known"),
        "workbench_jobs_by_started_at_known": records_by_key(records, "started_at_known"),
        "workbench_jobs_by_finished_at_known": records_by_key(records, "finished_at_known"),
        "workbench_jobs_by_duration_known": records_by_key(records, "duration_known"),
        "workbench_jobs_by_elapsed_known": records_by_key(records, "elapsed_known"),
        "workbench_jobs_by_background_supported": records_by_key(records, "background_supported"),
        "workbench_jobs_by_long_running": records_by_key(records, "long_running"),
        "workbench_jobs_by_outcome": records_by_key(records, "outcome"),
        "workbench_jobs_by_exit_status": records_by_key(records, "exit_status"),
        "workbench_jobs_by_last_output_tail_truncated": records_by_key(records, "last_output_tail_truncated"),
    }


def workbench_job_summary(records):
    return {
        "total_count": len(records or []),
        "running_count": len([rec for rec in records or [] if rec.get("effective_state") in ("starting", "running")]),
        "pid_managed_count": len([rec for rec in records or [] if rec.get("pid_managed") is True]),
        "cancel_supported_count": len([rec for rec in records or [] if rec.get("cancel_supported") is True]),
        "log_exists_count": len([rec for rec in records or [] if rec.get("log_exists") is True]),
        "log_total_size": record_sum_by_key(records, "log_size"),
        "last_output_tail_truncated_count": len([rec for rec in records or [] if rec.get("last_output_tail_truncated") is True]),
        "exit_status_known_count": len([rec for rec in records or [] if rec.get("exit_status_known") is True]),
        "started_at_known_count": len([rec for rec in records or [] if rec.get("started_at_known") is True]),
        "finished_at_known_count": len([rec for rec in records or [] if rec.get("finished_at_known") is True]),
        "duration_known_count": len([rec for rec in records or [] if rec.get("duration_known") is True]),
        "elapsed_known_count": len([rec for rec in records or [] if rec.get("elapsed_known") is True]),
        "duration_total_sec": record_sum_by_key(records, "duration_sec"),
        "elapsed_total_sec": record_sum_by_key(records, "elapsed_sec"),
        "background_supported_count": len([rec for rec in records or [] if rec.get("background_supported") is True]),
        "long_running_count": len([rec for rec in records or [] if rec.get("long_running") is True]),
        "state_counts": record_count_by_key(records, "state"),
        "effective_state_counts": record_count_by_key(records, "effective_state"),
        "outcome_counts": record_count_by_key(records, "outcome"),
        "exit_status_counts": record_count_by_key(records, "exit_status"),
        "action_counts": record_count_by_key(records, "action_id"),
        "category_counts": record_count_by_key(records, "category"),
    }


def workbench_job_status_summary(stats=None):
    stats = stats or {}
    return {
        "workbench_job_count": stats.get("total_count", 0),
        "workbench_job_running_count": stats.get("running_count", 0),
        "workbench_job_pid_managed_count": stats.get("pid_managed_count", 0),
        "workbench_job_cancel_supported_count": stats.get("cancel_supported_count", 0),
        "workbench_job_log_exists_count": stats.get("log_exists_count", 0),
        "workbench_job_log_total_size": stats.get("log_total_size", 0),
        "workbench_job_last_output_tail_truncated_count": stats.get(
            "last_output_tail_truncated_count", 0
        ),
        "workbench_job_exit_status_known_count": stats.get(
            "exit_status_known_count", 0
        ),
        "workbench_job_started_at_known_count": stats.get("started_at_known_count", 0),
        "workbench_job_finished_at_known_count": stats.get(
            "finished_at_known_count", 0
        ),
        "workbench_job_duration_known_count": stats.get("duration_known_count", 0),
        "workbench_job_elapsed_known_count": stats.get("elapsed_known_count", 0),
        "workbench_job_duration_total_sec": stats.get("duration_total_sec", 0),
        "workbench_job_elapsed_total_sec": stats.get("elapsed_total_sec", 0),
        "workbench_job_background_supported_count": stats.get(
            "background_supported_count", 0
        ),
        "workbench_job_long_running_count": stats.get("long_running_count", 0),
        "workbench_job_state_counts": stats.get("state_counts") or {},
        "workbench_job_effective_state_counts": stats.get("effective_state_counts")
        or {},
        "workbench_job_outcome_counts": stats.get("outcome_counts") or {},
        "workbench_job_exit_status_counts": stats.get("exit_status_counts") or {},
        "workbench_job_action_counts": stats.get("action_counts") or {},
        "workbench_job_category_counts": stats.get("category_counts") or {},
    }


def workbench_job_status_context(cfg, workbench_actions=None):
    jobs = workbench_job_records(cfg, workbench_actions)
    stats = workbench_job_summary(jobs)
    return {
        "jobs": jobs,
        "index_maps": workbench_job_indexes(jobs),
        "stats": stats,
        "summary": workbench_job_status_summary(stats),
    }
