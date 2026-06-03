"""Line-console command queue rendering helpers."""

from gritlib.console_display import console_table


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


def print_line_command_queue_records(queue_summary, mailbox_records, command_queue_actions, include_queue_summary=True):
    queue_summary = queue_summary or {}
    mailbox_records = list(mailbox_records or [])
    command_queue_actions = list(command_queue_actions or [])
    command_records = queue_summary.get("commands") or []

    def _mailbox_detail(rec):
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
            f"Mailbox  ({len(mailbox_records)} records)",
            mailbox_records[:8], mailbox_cols, detail_fn=_mailbox_detail,
        )
    else:
        print("Mailbox  (none)")

    if command_queue_actions:
        action_cols = [
            ("Action", "id"),
            ("State", lambda r: r.get("operator_action_state") or "-"),
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
    print(f"  id={rec.get('id', '')}")
    print(f"  status={rec.get('status', '') or '-'}")
    print(f"  command={rec.get('command', '')}")
    print(f"  target={rec.get('target_id', '') or '-'} label={rec.get('target_label', '') or '-'}")
    print(f"  created={rec.get('created_at', '') or '-'} delivered={rec.get('delivered_at', '') or '-'} result_at={rec.get('result_received_at', '') or '-'}")
    if result:
        print(f"  result_status={result.get('status', '') or '-'} exit={result.get('exit_code', '') if result.get('exit_code', '') != '' else '-'}")
        print(f"  stdout_bytes={result.get('stdout_bytes', '') if result.get('stdout_bytes', '') != '' else rec.get('result_stdout_bytes', '')}")
        print(f"  stderr_bytes={result.get('stderr_bytes', '') if result.get('stderr_bytes', '') != '' else rec.get('result_stderr_bytes', '')}")
        print(f"  output_bytes={rec.get('result_output_bytes', '')} exceeded_limit={'yes' if rec.get('result_output_exceeded_limit') else 'no'}")
        print(f"  source={rec.get('result_source_path', '') or '-'}")
    else:
        print("  result_status=none")
        waiting_for = "delivery" if rec.get("status") == "queued" else "result-upload" if rec.get("status") == "delivered" else "-"
        print(f"  waiting_for={waiting_for}")
