"""Line-console command queue rendering helpers."""

from gritlib.console_display import console_table
from gritlib.config_utils import DEFAULT_CONFIG
from gritlib.event_log import append_event
from gritlib.line_state import line_action_state_text
from gritlib.shell_utils import shquote


def line_command_queue_time_text(iso):
    if iso and len(iso) >= 16 and "T" in iso:
        date, rest = iso.split("T", 1)
        return f"{date[5:]} {rest[:5]}"
    return iso or "-"


def line_command_queue_result_text(rec):
    status = rec.get("result_status") or ""
    code = rec.get("result_exit_code")
    if status and code not in (None, ""):
        return f"{status}/{code}"
    return status or "-"


def line_command_queue_humanize(text):
    return str(text or "").replace("_", "-").replace("-", " ").strip().capitalize()


def dispatch_legacy_line_queue_number(choice, *, view_func=None):
    if str(choice or "").strip() != "20":
        return False
    if view_func:
        view_func(detailed=True)
    return True


def line_command_queue_action_text(rec):
    action_id = str((rec or {}).get("action_id") or "")
    action_key = action_id.rsplit(":", 1)[-1]
    labels = {
        "inspect-command-queue": "Review queue",
        "list-command-queue": "Show mailbox",
        "queue-command": "Queue command",
        "clear-command-queue": "Clear queue",
        "start-command-queue-listener": "Start mailbox listener",
        "stop-command-queue-listener": "Stop mailbox listener",
    }
    if action_key in labels:
        return labels[action_key]
    label = str((rec or {}).get("label") or "").strip()
    return label or line_command_queue_humanize(action_key) or "-"


def line_command_queue_state_text(rec):
    return line_action_state_text(rec)


def line_command_queue_action_summary(records):
    counts = {}
    needs_input = 0
    confirm = 0
    for rec in records or []:
        state = line_command_queue_state_text(rec)
        counts[state] = counts.get(state, 0) + 1
        if str((rec or {}).get("operator_action_state") or "") == "needs-input":
            needs_input += 1
        if (rec or {}).get("requires_confirmation"):
            confirm += 1
    order = ("ready", "needs input", "empty", "stopped", "running", "disabled", "unavailable")
    parts = [f"{key}={counts[key]}" for key in order if counts.get(key)]
    parts.extend(f"{key}={value}" for key, value in sorted(counts.items()) if key not in order)
    if needs_input:
        parts.append(f"input needed={needs_input}")
    if confirm:
        parts.append(f"confirm={confirm}")
    return "  queue actions: " + "  ".join(parts) if parts else ""


def line_command_queue_mailbox_detail(rec):
    details = []
    work = rec.get("work_kind") or rec.get("request_name") or rec.get("bridge_profile") or ""
    if work:
        details.append(("work", work))
    if rec.get("pending_reason"):
        details.append(("reason", rec["pending_reason"]))
    created = line_command_queue_time_text(rec.get("created_at"))
    if created != "-":
        details.append(("created", created))
    return details


def print_line_mailbox_records(mailbox_records, title=None):
    mailbox_records = list(mailbox_records or [])
    if mailbox_records:
        mailbox_cols = [
            ("Command", lambda r: str(r.get("command_id") or "-")[:20]),
            ("Target", lambda r: r.get("target_id") or "-"),
            ("Status", lambda r: r.get("status") or "-"),
            ("Result", line_command_queue_result_text),
            ("Waiting", lambda r: r.get("waiting_for") or "-"),
            ("Seen", lambda r: line_command_queue_time_text(r.get("target_last_seen"))),
        ]
        console_table(
            title or f"Mailbox  ({len(mailbox_records)} records)",
            mailbox_records[:8], mailbox_cols, detail_fn=line_command_queue_mailbox_detail,
            footer="queue result N  |  queue COMMAND  |  queue ? for help",
        )
    else:
        console_table(title or "Mailbox  (none)", [], [], footer="queue COMMAND  |  queue ? for help")


def print_line_command_queue_records(
    queue_summary,
    mailbox_records,
    command_queue_actions,
    include_queue_summary=True,
    include_actions=True,
    detailed=False,
):
    queue_summary = queue_summary or {}
    mailbox_records = list(mailbox_records or [])
    command_queue_actions = list(command_queue_actions or [])
    command_records = queue_summary.get("commands") or []

    if include_queue_summary:
        status_bits = [
            f"enabled={queue_summary.get('enabled', 'no')}",
            f"queued={len(command_records)}",
            f"results={queue_summary.get('result_count', 0)}",
            f"pending_mailbox={len([rec for rec in mailbox_records if rec.get('pending_work')])}",
        ]
        print(f"Command queue  ({'  '.join(status_bits)})")
        policy_errors = queue_summary.get("policy_errors") or []
        if policy_errors:
            print(f"  policy: invalid  errors={len(policy_errors)}")
        elif queue_summary.get("policy_valid"):
            print("  policy: valid")
        else:
            print("  policy: not configured")
        if detailed:
            print(
                "  policy details: "
                f"execution={queue_summary.get('execution_mode', '-') or '-'} "
                f"delivery={'yes' if queue_summary.get('delivery_supported') else 'no'} "
                f"result_upload={'yes' if queue_summary.get('result_upload_supported') else 'no'}"
            )
            limits = queue_summary.get("command_limits") if isinstance(queue_summary.get("command_limits"), dict) else {}
            if limits:
                print(
                    "  limits: "
                    f"timeout={limits.get('timeout_sec', '-') or '-'} "
                    f"max_output={limits.get('max_output_bytes', '-') or '-'} "
                    f"expire={limits.get('expire_sec', '-') or '-'}"
                )
        if command_records:
            command_cols = [
                ("Command", lambda r: str(r.get("id") or "-")[:20]),
                ("Status", lambda r: r.get("status") or "-"),
                ("Target", lambda r: r.get("target_id") or "-"),
                ("Result", line_command_queue_result_text),
                ("Created", lambda r: line_command_queue_time_text(r.get("created_at"))),
            ]
            console_table(
                f"Queued commands  ({len(command_records)} total)",
                command_records[:8], command_cols,
                footer="queue result N  |  queue clear --confirm  |  queue ? for help",
            )
        else:
            print("  no queued commands")

    print_line_mailbox_records(mailbox_records)

    if not include_actions:
        return

    if command_queue_actions:
        action_summary = line_command_queue_action_summary(command_queue_actions)
        if action_summary:
            print(action_summary)
        action_cols = [
            ("Action", line_command_queue_action_text),
            ("State", line_command_queue_state_text),
            ("Pending", lambda r: str(r.get("target_mailbox_pending_work_count", 0))),
            ("Offline", lambda r: str(r.get("fleet_offline_target_count", 0))),
        ]
        console_table(
            f"Queue actions  ({len(command_queue_actions)} total)",
            command_queue_actions, action_cols,
            footer="queue COMMAND  |  queue list  |  queue ? for help",
        )
    else:
        print("\n  queue COMMAND  |  queue list  |  queue ? for help")


def print_line_command_queue_view(
    cfg,
    *,
    detailed=False,
    mailbox_only=False,
    snapshot_func,
    queue_summary_func,
    clear_results_func,
    append_event_fn=append_event,
):
    clear_results_func(cfg)
    snap = snapshot_func(cfg)
    command_queue_actions = snap.get("command_queue_workflow_actions") or []
    mailbox_records = snap.get("target_mailbox_records") or []
    queue_summary = queue_summary_func(cfg)

    if mailbox_only:
        print_line_mailbox_records(mailbox_records, title=f"Target mailbox  ({len(mailbox_records)} records)")
    else:
        print_line_command_queue_records(
            queue_summary,
            mailbox_records,
            command_queue_actions,
            detailed=detailed,
        )

    append_event_fn(cfg, "workbench", "workbench_command_queue_inspected", details={
        "command_count": len((queue_summary.get("commands") or [])),
        "target_mailbox_record_count": len(mailbox_records),
        "command_queue_workflow_action_count": len(command_queue_actions),
    })


def line_command_queue_record_by_selector(commands, selector):
    text = str(selector or "").strip()
    if not text:
        return {}
    rows = list(commands or [])
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(rows):
            return rows[idx]
        return {}
    for rec in rows:
        if text == str(rec.get("id") or ""):
            return rec
    return {}


def print_line_command_result_record(rec):
    rec = rec or {}
    result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
    print("Command result:")
    status = rec.get("status") or "-"
    if result:
        result_status = result.get("status") or "-"
        exit_code = result.get("exit_code", "")
        exit_text = exit_code if exit_code != "" else "-"
        print(f"  summary: {status}; result {result_status}; exit {exit_text}")
    else:
        waiting_for = "delivery" if rec.get("status") == "queued" else "result-upload" if rec.get("status") == "delivered" else "-"
        print(f"  summary: {status}; waiting for {waiting_for}; result none")
    print(f"  id: {rec.get('id', '')}")
    print(f"  status: {status}")
    print(f"  command: {rec.get('command', '')}")
    print(f"  target: {rec.get('target_id', '') or '-'} ({rec.get('target_label', '') or '-'})")
    print(f"  created: {rec.get('created_at', '') or '-'}")
    print(f"  delivered: {rec.get('delivered_at', '') or '-'}")
    print(f"  result at: {rec.get('result_received_at', '') or '-'}")
    if result:
        stdout_bytes = result.get("stdout_bytes", "") if result.get("stdout_bytes", "") != "" else rec.get("result_stdout_bytes", "")
        stderr_bytes = result.get("stderr_bytes", "") if result.get("stderr_bytes", "") != "" else rec.get("result_stderr_bytes", "")
        exit_code = result.get("exit_code", "") if result.get("exit_code", "") != "" else "-"
        print(f"  result: {result.get('status', '') or '-'}")
        print(f"  exit: {exit_code}")
        print(f"  stdout bytes: {stdout_bytes}")
        print(f"  stderr bytes: {stderr_bytes}")
        print(f"  output bytes: {rec.get('result_output_bytes', '')}")
        print(f"  exceeded limit: {'yes' if rec.get('result_output_exceeded_limit') else 'no'}")
        print(f"  source: {rec.get('result_source_path', '') or '-'}")
    else:
        print("  result: none")
        waiting_for = "delivery" if rec.get("status") == "queued" else "result-upload" if rec.get("status") == "delivered" else "-"
        print(f"  waiting for: {waiting_for}")


def queue_line_command(
    cfg, command, queue_func, target_filter_func=None,
    quote=shquote, default_config=DEFAULT_CONFIG
):
    text = str(command or "").strip()
    if not text:
        raise ValueError("usage: queue COMMAND")
    target_filter_func = target_filter_func or (lambda _cfg: "")
    headless = (
        "scripts/grit-console --config "
        + quote(str(cfg.get("_config_path", default_config)))
    )
    target_id = str(target_filter_func(cfg) or "")
    if target_id:
        headless += " --target-id " + quote(target_id)
    headless += " --queue-command " + quote(text) + " --list-command-queue"
    rec = queue_func(cfg, text)
    print(f"queued {rec['id']}: {rec['command']}")
    if rec.get("target_id"):
        print(f"target: {rec.get('target_id', '')} ({rec.get('target_label', '') or '-'})")
    print(f"execution supported: {'yes' if rec.get('execution_supported') else 'no'}")
    print("delivery supported: no")
    append_event(cfg, "workbench", "workbench_command_queued", details={
        "command_id": rec.get("id", ""),
        "target_id": rec.get("target_id", ""),
        "target_label": rec.get("target_label", ""),
        "headless_command": headless,
    })
    return rec


def line_command_queue_record(queue_summary, selector):
    return line_command_queue_record_by_selector(
        (queue_summary or {}).get("commands") or [],
        selector,
    )


def print_line_command_result(cfg, queue_summary, selector):
    text = str(selector or "").strip()
    if not text:
        raise ValueError("usage: queue result ID|NUMBER")
    rec = line_command_queue_record(queue_summary, text)
    if not rec:
        raise ValueError(f"command queue id not found: {text}")
    result = rec.get("result") if isinstance(rec.get("result"), dict) else {}
    print_line_command_result_record(rec)
    append_event(cfg, "workbench", "workbench_command_result_inspected", details={
        "command_id": str(rec.get("id") or ""),
        "status": str(rec.get("status") or ""),
        "has_result": bool(result),
        "result_status": str(result.get("status") or ""),
        "target_id": str(rec.get("target_id") or ""),
        "target_label": str(rec.get("target_label") or ""),
    })
    return rec


def parse_line_queue_command(cmd, args):
    cmd = str(cmd or "").strip().lower()
    args = list(args or [])
    if cmd not in {"mailbox", "queue"}:
        return {}
    if args:
        return {"action": "run", "args": args}
    return {"action": "view", "args": []}


def dispatch_line_queue_command(
    queue_cmd,
    *,
    original_cmd="",
    set_context_func=None,
    run_func=None,
    view_func=None,
):
    action = (queue_cmd or {}).get("action")
    try:
        if not (str(original_cmd or "").lower() == "queue" and action == "run"):
            if set_context_func:
                set_context_func()
        if action == "run" and run_func:
            return run_func(queue_cmd.get("args") or [])
        if action == "view" and view_func:
            return view_func()
    except ValueError as exc:
        print(exc)
        return None
    raise ValueError("unsupported queue command")


def run_line_queue_command(
    cfg,
    args,
    *,
    queue_summary_func,
    queue_func,
    clear_queue_func,
    view_func,
    target_filter_func=None,
    clear_selectable_results_func=None,
    quote=shquote,
):
    if clear_selectable_results_func:
        clear_selectable_results_func()
    args = list(args or [])
    if not args:
        view_func()
        return None
    subcmd = str(args[0] or "").lower()
    if subcmd in {"list", "show", "mailbox", "ls"}:
        view_func()
        return None
    if subcmd in {"target", "targets", "agent", "agents"}:
        view_func(mailbox_only=True)
        return None
    if subcmd in {"result", "results"}:
        if len(args) == 1 and subcmd == "results":
            view_func()
            return None
        return print_line_command_result(cfg, queue_summary_func(cfg), " ".join(args[1:]).strip())
    if subcmd == "clear":
        if "--confirm" not in args[1:]:
            raise ValueError("usage: queue clear --confirm")
        count = clear_queue_func(cfg)
        headless = (
            "scripts/grit-console --config "
            + quote(str(cfg.get("_config_path", DEFAULT_CONFIG)))
            + " --clear-command-queue --list-command-queue"
        )
        print(f"cleared {count} queued command record(s)")
        append_event(cfg, "workbench", "workbench_command_queue_cleared", details={
            "count": count,
            "headless_command": headless,
        })
        return count
    if subcmd == "command":
        return queue_line_command(
            cfg, " ".join(args[1:]).strip(), queue_func,
            target_filter_func=target_filter_func, quote=quote,
        )
    if subcmd == "--":
        return queue_line_command(
            cfg, " ".join(args[1:]).strip(), queue_func,
            target_filter_func=target_filter_func, quote=quote,
        )
    return queue_line_command(
        cfg, " ".join(args).strip(), queue_func,
        target_filter_func=target_filter_func, quote=quote,
    )
