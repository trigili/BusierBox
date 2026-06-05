"""Line REPL completion callback adapters."""

from gritlib import command_queue as command_queue_module
from gritlib.console_workbench import workbench_snapshot
from gritlib.event_log import append_event
from gritlib import line_configure
from gritlib.line_completions import build_line_completion_callbacks
from gritlib.line_repl_runtime import install_readline_completer
from gritlib.release_artifacts import release_context
from gritlib.staged_files import load_staged


def build_line_completion_adapter(
    cfg,
    *,
    workbench_snapshot_func,
    current_action_records_func=None,
    bridge_profile_records_func=None,
    release_context_func,
    command_queue_summary_func,
    generated_target_command_records_func=None,
    workbench_config_field_records_func=None,
    service_status_rows_func=None,
    service_completion_names_func=None,
    service_names_func=None,
    route_service_callbacks=None,
    target_callbacks=None,
    action_callbacks=None,
    option_callbacks=None,
    load_staged_func,
    find_survey_uploads_func,
    append_event_fn,
):
    bundle = build_line_completion_bundle(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        current_action_records_func=current_action_records_func,
        bridge_profile_records_func=bridge_profile_records_func,
        release_context_func=release_context_func,
        command_queue_summary_func=command_queue_summary_func,
        generated_target_command_records_func=generated_target_command_records_func,
        workbench_config_field_records_func=workbench_config_field_records_func,
        service_status_rows_func=service_status_rows_func,
        service_completion_names_func=service_completion_names_func,
        service_names_func=service_names_func,
        route_service_callbacks=route_service_callbacks,
        target_callbacks=target_callbacks,
        action_callbacks=action_callbacks,
        option_callbacks=option_callbacks,
        load_staged_func=load_staged_func,
        find_survey_uploads_func=find_survey_uploads_func,
        append_event_fn=append_event_fn,
    )
    return (
        bundle["line_completion_candidates"],
        bundle["print_line_completions"],
    )


def build_line_completion_bundle(
    cfg,
    *,
    workbench_snapshot_func,
    current_action_records_func=None,
    bridge_profile_records_func=None,
    release_context_func,
    command_queue_summary_func,
    generated_target_command_records_func=None,
    workbench_config_field_records_func=None,
    service_status_rows_func=None,
    service_completion_names_func=None,
    service_names_func=None,
    route_service_callbacks=None,
    target_callbacks=None,
    action_callbacks=None,
    option_callbacks=None,
    load_staged_func,
    find_survey_uploads_func,
    append_event_fn,
):
    if current_action_records_func is None and action_callbacks is not None:
        current_action_records = action_callbacks["current_action_records"]
        current_action_records_func = lambda _snapshot_func: current_action_records()
    if workbench_config_field_records_func is None and option_callbacks is not None:
        workbench_config_fields = option_callbacks["workbench_config_fields"]
        workbench_config_field_records_func = lambda _cfg: workbench_config_fields()
    if generated_target_command_records_func is None and target_callbacks is not None:
        target_command_records = target_callbacks["target_command_records"]
        generated_target_command_records_func = lambda _cfg: target_command_records()
    if route_service_callbacks is not None:
        if bridge_profile_records_func is None:
            bridge_profile_records_func = lambda _cfg: route_service_callbacks["bridge_profile_records"]()
        if service_status_rows_func is None:
            service_status_rows_func = lambda _cfg: route_service_callbacks["service_rows"]()
        if service_completion_names_func is None:
            service_completion_names_func = lambda _rows: route_service_callbacks[
                "service_completion_names"
            ]()
        if service_names_func is None:
            service_names_func = lambda _rows: route_service_callbacks["service_names"]()

    line_completion_candidates, print_line_completions = build_line_completion_callbacks(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        line_action_records_func=lambda: current_action_records_func(
            lambda: workbench_snapshot_func(cfg)
        ),
        bridge_profile_records_func=bridge_profile_records_func,
        release_context_func=release_context_func,
        command_queue_summary_func=command_queue_summary_func,
        generated_target_command_records_func=generated_target_command_records_func,
        workbench_config_field_records_func=workbench_config_field_records_func,
        service_status_rows_func=service_status_rows_func,
        service_completion_names_func=service_completion_names_func,
        service_names_func=service_names_func,
        load_staged_func=load_staged_func,
        find_survey_uploads_func=lambda limit=20: find_survey_uploads_func(cfg, limit=limit),
        append_event_func=lambda service, event, details=None: append_event_fn(
            cfg,
            service,
            event,
            details=details,
        ),
    )
    return {
        "line_completion_candidates": line_completion_candidates,
        "print_line_completions": print_line_completions,
    }


def install_line_completion_bundle(readline_module, have_readline, completion_callbacks):
    return install_readline_completer(
        readline_module,
        have_readline,
        completion_callbacks["line_completion_candidates"],
    )


def setup_line_completion_bundle(
    cfg,
    *,
    readline_module,
    have_readline,
    workbench_snapshot_func,
    current_action_records_func=None,
    bridge_profile_records_func=None,
    release_context_func,
    command_queue_summary_func,
    generated_target_command_records_func=None,
    workbench_config_field_records_func=None,
    service_status_rows_func=None,
    service_completion_names_func=None,
    service_names_func=None,
    route_service_callbacks=None,
    target_callbacks=None,
    action_callbacks=None,
    option_callbacks=None,
    load_staged_func,
    find_survey_uploads_func,
    append_event_fn,
):
    bundle = build_line_completion_bundle(
        cfg,
        workbench_snapshot_func=workbench_snapshot_func,
        current_action_records_func=current_action_records_func,
        bridge_profile_records_func=bridge_profile_records_func,
        release_context_func=release_context_func,
        command_queue_summary_func=command_queue_summary_func,
        generated_target_command_records_func=generated_target_command_records_func,
        workbench_config_field_records_func=workbench_config_field_records_func,
        service_status_rows_func=service_status_rows_func,
        service_completion_names_func=service_completion_names_func,
        service_names_func=service_names_func,
        route_service_callbacks=route_service_callbacks,
        target_callbacks=target_callbacks,
        action_callbacks=action_callbacks,
        option_callbacks=option_callbacks,
        load_staged_func=load_staged_func,
        find_survey_uploads_func=find_survey_uploads_func,
        append_event_fn=append_event_fn,
    )
    install_line_completion_bundle(readline_module, have_readline, bundle)
    return bundle


def setup_default_line_completion_bundle(
    cfg,
    *,
    readline_module,
    have_readline,
    line_route_service_callbacks,
    line_target_callbacks,
    line_option_callbacks,
    line_action_callbacks,
):
    return setup_line_completion_bundle(
        cfg,
        readline_module=readline_module,
        have_readline=have_readline,
        workbench_snapshot_func=workbench_snapshot,
        action_callbacks=line_action_callbacks,
        release_context_func=release_context,
        command_queue_summary_func=command_queue_module.command_queue_summary,
        route_service_callbacks=line_route_service_callbacks,
        target_callbacks=line_target_callbacks,
        option_callbacks=line_option_callbacks,
        load_staged_func=load_staged,
        find_survey_uploads_func=line_configure.find_survey_uploads,
        append_event_fn=append_event,
    )
