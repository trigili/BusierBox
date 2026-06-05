"""Line REPL file/release workflow callback adapters."""

from gritlib import command_queue as command_queue_module
from gritlib.event_log import append_event
from gritlib.file_transfers import render_fetch_command
from gritlib.line_configure import configure_line_artifact
from gritlib.line_files import (
    download_line_target,
    fetch_line_staged,
    print_current_line_files,
    stage_line_binary,
    stage_line_file,
    unstage_line_file,
)
from gritlib.line_release import stage_line_release
from gritlib.operator_io import view_line_path
from gritlib.shell_utils import shquote
from gritlib.staged_files import load_staged
from gritlib import target_records
from gritlib import workflow_runners


def _resolve_file_workflow_dependencies(
    service_start_command_func,
    target_id_func,
    target_context_func,
    target_callbacks,
    route_service_callbacks,
):
    if service_start_command_func is None and route_service_callbacks is not None:
        service_start_command = route_service_callbacks["service_start_command"]
        service_start_command_func = lambda _cfg, service: service_start_command(service)
    if target_callbacks is not None:
        if target_id_func is None:
            target_filter = target_callbacks["target_filter"]
            target_id_func = lambda _cfg: target_filter()
        if target_context_func is None:
            target_context = target_callbacks["target_context"]
            target_context_func = lambda _cfg: target_context()
    return service_start_command_func, target_id_func, target_context_func


def _build_file_service_start_callback(cfg, start_service_func, service_start_command_func):
    def start_file_service_process():
        return start_service_func(
            cfg,
            "file-service",
            headless_command=service_start_command_func(cfg, "file-service"),
        )

    return start_file_service_process


def _build_release_stage_callbacks(cfg, line_input_fn, start_file_service_process, append_event_fn):
    def stage_release(selector, start_file_service=False):
        return stage_line_release(
            cfg,
            selector,
            start_file_service=start_file_service,
            start_file_service_fn=start_file_service_process,
            append_event_fn=append_event_fn,
        )

    def stage_binary(
        selector="",
        request_name="",
        prompt_for_missing=True,
        prompt_start=True,
        start_file_service=False,
        show_headless=False,
    ):
        return stage_line_binary(
            cfg,
            selector=selector,
            request_name=request_name,
            prompt_for_missing=prompt_for_missing,
            prompt_start=prompt_start,
            start_file_service=start_file_service,
            show_headless=show_headless,
            line_input_fn=line_input_fn,
            start_file_service_fn=start_file_service_process,
            append_event_fn=append_event_fn,
        )

    def configure_artifact(args):
        return configure_line_artifact(cfg, args, append_event_fn=append_event_fn)

    return {
        "stage_release": stage_release,
        "stage_binary": stage_binary,
        "configure_artifact": configure_artifact,
    }


def _build_staged_file_callbacks(cfg, start_file_service_process, append_event_fn):
    def stage_file(path_text="", request_name="", start_file_service=False):
        return stage_line_file(
            cfg,
            path_text,
            request_name,
            start_file_service=start_file_service,
            start_file_service_fn=start_file_service_process,
            append_event_fn=append_event_fn,
        )

    def unstage_file(request_name):
        return unstage_line_file(cfg, request_name, append_event_fn=append_event_fn)

    return {
        "stage_file": stage_file,
        "unstage_file": unstage_file,
    }


def _build_target_file_transfer_callbacks(
    cfg,
    target_id_func,
    target_context_func,
    scoped_target_cfg_func,
    queue_command_func,
    start_file_service_process,
    append_event_fn,
):
    def download_target(target_path, queue=False, start_file_service=False):
        return download_line_target(
            cfg,
            target_path,
            queue=queue,
            start_file_service=start_file_service,
            target_id_fn=lambda: target_id_func(cfg),
            target_context_fn=lambda: target_context_func(cfg),
            queue_command_fn=queue_command_func,
            start_file_service_fn=start_file_service_process,
            append_event_fn=append_event_fn,
        )

    def scoped_target_cfg(target_id, target_label=""):
        return scoped_target_cfg_func(
            cfg,
            target_id,
            target_label=target_label,
        )

    def fetch_staged(request_name, queue=False, start_file_service=False):
        return fetch_line_staged(
            cfg,
            request_name,
            queue=queue,
            start_file_service=start_file_service,
            target_id_fn=lambda: target_id_func(cfg),
            target_context_fn=lambda: target_context_func(cfg),
            scoped_target_cfg_fn=scoped_target_cfg,
            queue_command_fn=queue_command_func,
            start_file_service_fn=start_file_service_process,
            append_event_fn=append_event_fn,
        )

    return {
        "download_target": download_target,
        "fetch_staged": fetch_staged,
        "scoped_target_cfg": scoped_target_cfg,
    }


def _build_file_view_callbacks(cfg, target_id_func, load_staged_func, fetch_command_func, append_event_fn, quote):
    def view_path(*args, **_kwargs):
        path_text = args[-1] if args else ""
        return view_line_path(cfg, path_text, append_event_fn=append_event_fn)

    def print_files(verbose=False):
        return print_current_line_files(
            cfg,
            load_staged_func(cfg).get("staged", {}),
            target_filter_id=target_id_func(cfg),
            verbose=verbose,
            fetch_command=lambda name: fetch_command_func(name, cfg),
            quote=quote,
            append_event_fn=append_event_fn,
        )

    return {
        "view_path": view_path,
        "print_line_files": print_files,
    }


def build_line_file_workflow_callbacks(
    cfg,
    *,
    line_input_fn,
    start_service_func,
    service_start_command_func=None,
    target_id_func=None,
    target_context_func=None,
    scoped_target_cfg_func,
    queue_command_func,
    target_callbacks=None,
    route_service_callbacks=None,
    load_staged_func,
    fetch_command_func,
    append_event_fn,
    quote,
):
    service_start_command_func, target_id_func, target_context_func = _resolve_file_workflow_dependencies(
        service_start_command_func,
        target_id_func,
        target_context_func,
        target_callbacks,
        route_service_callbacks,
    )
    start_file_service_process = _build_file_service_start_callback(
        cfg,
        start_service_func,
        service_start_command_func,
    )
    release_callbacks = _build_release_stage_callbacks(cfg, line_input_fn, start_file_service_process, append_event_fn)
    staged_callbacks = _build_staged_file_callbacks(cfg, start_file_service_process, append_event_fn)
    transfer_callbacks = _build_target_file_transfer_callbacks(
        cfg,
        target_id_func,
        target_context_func,
        scoped_target_cfg_func,
        queue_command_func,
        start_file_service_process,
        append_event_fn,
    )
    view_callbacks = _build_file_view_callbacks(
        cfg,
        target_id_func,
        load_staged_func,
        fetch_command_func,
        append_event_fn,
        quote,
    )

    return {
        "stage_release": release_callbacks["stage_release"],
        "stage_binary": release_callbacks["stage_binary"],
        "configure_artifact": release_callbacks["configure_artifact"],
        "stage_file": staged_callbacks["stage_file"],
        "download_target": transfer_callbacks["download_target"],
        "fetch_staged": transfer_callbacks["fetch_staged"],
        "unstage_file": staged_callbacks["unstage_file"],
        "scoped_target_cfg": transfer_callbacks["scoped_target_cfg"],
        "view_path": view_callbacks["view_path"],
        "print_line_files": view_callbacks["print_line_files"],
    }


def build_default_line_file_workflow_callbacks(
    cfg,
    *,
    line_input,
    line_target_callbacks,
    line_route_service_callbacks,
):
    return build_line_file_workflow_callbacks(
        cfg,
        line_input_fn=line_input,
        start_service_func=workflow_runners.start_service_process,
        target_callbacks=line_target_callbacks,
        route_service_callbacks=line_route_service_callbacks,
        scoped_target_cfg_func=target_records.scoped_target_cfg,
        queue_command_func=command_queue_module.queue_command,
        load_staged_func=load_staged,
        fetch_command_func=render_fetch_command,
        append_event_fn=append_event,
        quote=shquote,
    )
