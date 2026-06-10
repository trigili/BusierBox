"""Workflow, target-command, and job rendering for status printers."""

from gritlib.target_commands import (
    print_target_command_summary,
    target_command_display_line,
)
from gritlib.workbench_jobs import (
    print_workbench_job_ownership,
    print_workbench_job_summary,
)
from gritlib.workflow_actions import print_workbench_action_summary


def print_generated_target_commands(doc):
    print("Generated target commands:")
    print_target_command_summary(doc)
    for rec in doc.get("target_command_records") or []:
        if isinstance(rec, dict):
            print("  " + target_command_display_line(rec))


def print_operator_workflow_actions(doc):
    print("Operator modules:")
    print_workbench_action_summary(doc)
    for rec in doc.get("workbench_actions") or []:
        bg = "yes" if rec.get("background_supported") else "no"
        confirm = "yes" if rec.get("requires_confirmation") else "no"
        runnable = "yes" if rec.get("foreground_runnable") else "no"
        print(f"  {rec.get('id', '')} category={rec.get('category', '')} script={rec.get('script', '')} background={bg} confirm={confirm} foreground_runnable={runnable}")
        print(f"    {rec.get('command', '')}")
        if rec.get("dry_run_command"):
            print(f"    dry_run: {rec.get('dry_run_command', '')}")
        if rec.get("run_command"):
            print(f"    run: {rec.get('run_command', '')}")
        if rec.get("start_job_command"):
            print(f"    start_job: {rec.get('start_job_command', '')}")


def print_target_workflow_actions(doc):
    if doc.get("target_workflow_actions"):
        print("Target modules:")
        for rec in doc.get("target_workflow_actions") or []:
            requires_input = "yes" if rec.get("requires_input") else "no"
            available = "yes" if rec.get("available") else "no"
            offline = "yes" if rec.get("offline_supported") else "no"
            requires_online = "yes" if rec.get("requires_target_online") else "no"
            bridge = f" bridge_profile={rec.get('bridge_profile', '')}" if rec.get("bridge_profile") else ""
            print(
                f"  {rec.get('id', '')} target={rec.get('target_id', '')} "
                f"category={rec.get('category', '')} workflow={rec.get('workflow', '')} "
                f"available={available} input={requires_input} offline={offline} "
                f"requires_online={requires_online} state={rec.get('operator_action_state', '') or '-'} "
                f"reason={rec.get('operator_action_reason', '') or '-'} "
                f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'}{bridge}"
            )
            print(f"    {rec.get('headless_command', rec.get('command', ''))}")


def print_workbench_jobs(doc):
    print_workbench_job_summary(doc)
    for rec in doc.get("workbench_jobs") or []:
        cancel = "yes" if rec.get("cancel_supported") else "no"
        managed = "yes" if rec.get("pid_managed") else "no"
        exit_status = rec.get("exit_status", "")
        exit_suffix = f" exit_status={exit_status} outcome={rec.get('outcome', '')}" if rec.get("exit_status_known") else ""
        duration = rec.get("duration_sec", "")
        elapsed = rec.get("elapsed_sec", "")
        duration_suffix = f" duration_sec={duration}" if rec.get("duration_known") else ""
        elapsed_suffix = f" elapsed_sec={elapsed}" if rec.get("elapsed_known") else ""
        print(f"  job {rec.get('id', '')} action={rec.get('action_id', '')} state={rec.get('effective_state', '')} pid={rec.get('pid', '') or '-'} managed={managed} cancel_supported={cancel}{exit_suffix}{duration_suffix}{elapsed_suffix}")
        print_workbench_job_ownership(rec)
        print(f"    command: {rec.get('command', '')}")
        print(f"    log: {rec.get('log_path', '')}")
        if rec.get("finished_at"):
            print(f"    finished_at: {rec.get('finished_at', '')}")
        for line in rec.get("last_output_tail") or []:
            print(f"    | {line}")


def print_snapshot_workflow_actions(snap):
    print("Operator modules:")
    print_workbench_action_summary(snap)
    actions = snap.get("workbench_actions") or []
    preview_action_limit = 12
    for rec in actions[:preview_action_limit]:
        bg = "yes" if rec.get("background_supported") else "no"
        confirm = "yes" if rec.get("requires_confirmation") else "no"
        runnable = "yes" if rec.get("foreground_runnable") else "no"
        print(f"  {rec.get('id', '')} category={rec.get('category', '')} script={rec.get('script', '')} background={bg} confirm={confirm} foreground_runnable={runnable}")
        print(f"    {rec.get('command', '')}")
        if rec.get("dry_run_command"):
            print(f"    dry_run: {rec.get('dry_run_command', '')}")
        if rec.get("run_command"):
            print(f"    run: {rec.get('run_command', '')}")
        if rec.get("start_job_command"):
            print(f"    start_job: {rec.get('start_job_command', '')}")
    if len(actions) > preview_action_limit:
        print(f"  ... {len(actions) - preview_action_limit} more operator module(s); choose module 11 in line mode for the full list")


def print_snapshot_target_workflow_actions(snap):
    if snap.get("target_workflow_actions"):
        print("Target modules:")
        actions = snap.get("target_workflow_actions") or []
        for rec in actions[:3]:
            requires_input = "yes" if rec.get("requires_input") else "no"
            available = "yes" if rec.get("available") else "no"
            offline = "yes" if rec.get("offline_supported") else "no"
            requires_online = "yes" if rec.get("requires_target_online") else "no"
            bridge = f" bridge_profile={rec.get('bridge_profile', '')}" if rec.get("bridge_profile") else ""
            print(
                f"  {rec.get('id', '')} target={rec.get('target_id', '')} "
                f"category={rec.get('category', '')} workflow={rec.get('workflow', '')} "
                f"available={available} input={requires_input} offline={offline} "
                f"requires_online={requires_online} state={rec.get('operator_action_state', '') or '-'} "
                f"reason={rec.get('operator_action_reason', '') or '-'} "
                f"enter={'yes' if rec.get('can_run_from_curses_enter') else 'no'}{bridge}"
            )
            print(f"    {rec.get('headless_command', rec.get('command', ''))}")
        if len(actions) > 3:
            print(f"  ... {len(actions) - 3} more target module(s); choose module 11 in line mode for the full list")


def print_snapshot_workbench_jobs(snap):
    print_workbench_job_summary(snap)
    for rec in snap.get("workbench_jobs") or []:
        cancel = "yes" if rec.get("cancel_supported") else "no"
        managed = "yes" if rec.get("pid_managed") else "no"
        exit_status = rec.get("exit_status", "")
        exit_suffix = f" exit_status={exit_status} outcome={rec.get('outcome', '')}" if rec.get("exit_status_known") else ""
        print(f"  job {rec.get('id', '')} action={rec.get('action_id', '')} state={rec.get('effective_state', '')} pid={rec.get('pid', '') or '-'} managed={managed} cancel_supported={cancel}{exit_suffix}")
        print_workbench_job_ownership(rec)
        print(f"    command: {rec.get('command', '')}")
        print(f"    log: {rec.get('log_path', '')}")
        if rec.get("finished_at"):
            print(f"    finished_at: {rec.get('finished_at', '')}")
        for line in rec.get("last_output_tail") or []:
            print(f"    | {line}")
