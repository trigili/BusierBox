"""Callback bundle assembly for the line-console REPL."""

from typing import NamedTuple

from gritlib.line_repl_actions import build_default_line_action_callbacks
from gritlib.line_repl_completions import setup_default_line_completion_bundle
from gritlib.line_repl_core import build_default_line_core_callbacks
from gritlib.line_repl_files import build_default_line_file_workflow_callbacks
from gritlib.line_repl_jobs import build_default_line_job_callbacks
from gritlib.line_repl_legacy import build_default_line_legacy_callbacks
from gritlib.line_repl_navigation import build_default_line_navigation_callbacks
from gritlib.line_repl_options import build_default_line_option_callbacks
from gritlib.line_repl_probe import build_default_line_probe_callbacks
from gritlib.line_repl_queue import build_default_line_queue_callbacks
from gritlib.line_repl_routes import build_default_line_route_service_callbacks
from gritlib.line_repl_search import build_default_line_search_bundle
from gritlib.line_repl_sessions import build_default_line_session_callbacks
from gritlib.line_repl_show import build_default_line_display_show_callbacks
from gritlib.line_repl_survey import build_default_line_survey_callbacks
from gritlib.line_repl_targets import build_default_line_target_callbacks
from gritlib.line_repl_utility import build_default_line_utility_callbacks
from gritlib.line_repl_workflow import build_default_line_workflow_callbacks
from gritlib.line_repl_workspace import build_default_line_workspace_callbacks


class LineFoundationCallbacks(NamedTuple):
    target: object
    route_service: object
    option: object
    action: object
    completion: object


class LineOperationalCallbacks(NamedTuple):
    job: object
    queue: object
    probe: object
    session: object
    file: object
    search: object
    display_show: object


class LineDispatchCallbacks(NamedTuple):
    utility: object
    core: object
    navigation: object
    workflow: object
    legacy: object


class LineCallbackBundles(NamedTuple):
    foundation: LineFoundationCallbacks
    operational: LineOperationalCallbacks
    dispatch: LineDispatchCallbacks


def build_line_foundation_callbacks(cfg, line_input, *, readline_module=None, have_readline=False):
    line_target_callbacks = build_default_line_target_callbacks(cfg)

    line_route_service_callbacks = build_default_line_route_service_callbacks(cfg)

    line_option_callbacks = build_default_line_option_callbacks(cfg)

    line_action_callbacks = build_default_line_action_callbacks(
        cfg,
        line_input=line_input,
        line_route_service_callbacks=line_route_service_callbacks,
    )

    line_completion_callbacks = setup_default_line_completion_bundle(
        cfg,
        readline_module=readline_module,
        have_readline=have_readline,
        line_route_service_callbacks=line_route_service_callbacks,
        line_target_callbacks=line_target_callbacks,
        line_option_callbacks=line_option_callbacks,
        line_action_callbacks=line_action_callbacks,
    )

    return LineFoundationCallbacks(
        target=line_target_callbacks,
        route_service=line_route_service_callbacks,
        option=line_option_callbacks,
        action=line_action_callbacks,
        completion=line_completion_callbacks,
    )


def build_line_operational_callbacks(
    cfg,
    line_input,
    foundation_callbacks,
):
    line_job_callbacks = build_default_line_job_callbacks(
        cfg,
        line_action_callbacks=foundation_callbacks.action,
    )

    line_queue_callbacks = build_default_line_queue_callbacks(
        cfg,
        line_target_callbacks=foundation_callbacks.target,
    )

    line_probe_callbacks = build_default_line_probe_callbacks(
        cfg,
        line_input=line_input,
        line_route_service_callbacks=foundation_callbacks.route_service,
        line_target_callbacks=foundation_callbacks.target,
    )

    line_session_callbacks = build_default_line_session_callbacks(cfg)

    line_file_callbacks = build_default_line_file_workflow_callbacks(
        cfg,
        line_input=line_input,
        line_target_callbacks=foundation_callbacks.target,
        line_route_service_callbacks=foundation_callbacks.route_service,
    )

    line_search_callbacks = build_default_line_search_bundle(
        cfg,
        line_target_callbacks=foundation_callbacks.target,
        line_route_service_callbacks=foundation_callbacks.route_service,
        line_action_callbacks=foundation_callbacks.action,
        line_session_callbacks=line_session_callbacks,
        line_job_callbacks=line_job_callbacks,
        line_queue_callbacks=line_queue_callbacks,
    )
    line_display_show_callbacks = build_default_line_display_show_callbacks(
        cfg,
        line_action_callbacks=foundation_callbacks.action,
        line_option_callbacks=foundation_callbacks.option,
        line_target_callbacks=foundation_callbacks.target,
        line_route_service_callbacks=foundation_callbacks.route_service,
        line_probe_callbacks=line_probe_callbacks,
        line_file_callbacks=line_file_callbacks,
        line_job_callbacks=line_job_callbacks,
        line_session_callbacks=line_session_callbacks,
        line_queue_callbacks=line_queue_callbacks,
    )

    return LineOperationalCallbacks(
        job=line_job_callbacks,
        queue=line_queue_callbacks,
        probe=line_probe_callbacks,
        session=line_session_callbacks,
        file=line_file_callbacks,
        search=line_search_callbacks,
        display_show=line_display_show_callbacks,
    )


def build_line_dispatch_callbacks(
    cfg,
    line_input,
    foundation_callbacks,
    operational_callbacks,
):
    line_workspace_callbacks = build_default_line_workspace_callbacks(cfg)

    line_survey_callbacks = build_default_line_survey_callbacks(cfg)

    line_utility_callbacks = build_default_line_utility_callbacks(
        cfg,
        line_completion_callbacks=foundation_callbacks.completion,
        line_search_callbacks=operational_callbacks.search,
        line_display_show_callbacks=operational_callbacks.display_show,
        line_route_service_callbacks=foundation_callbacks.route_service,
    )
    line_core_callbacks = build_default_line_core_callbacks(
        cfg,
        line_probe_callbacks=operational_callbacks.probe,
        line_file_callbacks=operational_callbacks.file,
        line_display_show_callbacks=operational_callbacks.display_show,
        line_option_callbacks=foundation_callbacks.option,
        line_workspace_callbacks=line_workspace_callbacks,
        line_survey_callbacks=line_survey_callbacks,
    )
    line_navigation_callbacks = build_default_line_navigation_callbacks(
        cfg,
        line_search_callbacks=operational_callbacks.search,
        line_target_callbacks=foundation_callbacks.target,
        line_route_service_callbacks=foundation_callbacks.route_service,
        line_session_callbacks=operational_callbacks.session,
        line_job_callbacks=operational_callbacks.job,
        line_action_callbacks=foundation_callbacks.action,
        line_queue_callbacks=operational_callbacks.queue,
    )
    line_workflow_callbacks = build_default_line_workflow_callbacks(
        cfg,
        line_target_callbacks=foundation_callbacks.target,
        line_file_callbacks=operational_callbacks.file,
        line_queue_callbacks=operational_callbacks.queue,
        line_job_callbacks=operational_callbacks.job,
    )
    line_legacy_callbacks = build_default_line_legacy_callbacks(
        cfg,
        line_input=line_input,
        line_search_callbacks=operational_callbacks.search,
        line_route_service_callbacks=foundation_callbacks.route_service,
        line_target_callbacks=foundation_callbacks.target,
        line_file_callbacks=operational_callbacks.file,
        line_queue_callbacks=operational_callbacks.queue,
        line_action_callbacks=foundation_callbacks.action,
    )

    return LineDispatchCallbacks(
        utility=line_utility_callbacks,
        core=line_core_callbacks,
        navigation=line_navigation_callbacks,
        workflow=line_workflow_callbacks,
        legacy=line_legacy_callbacks,
    )


def build_line_callback_bundles(
    cfg,
    line_input,
    *,
    readline_module=None,
    have_readline=False,
):
    foundation_callbacks = build_line_foundation_callbacks(
        cfg,
        line_input,
        readline_module=readline_module,
        have_readline=have_readline,
    )
    operational_callbacks = build_line_operational_callbacks(
        cfg,
        line_input,
        foundation_callbacks,
    )
    dispatch_callbacks = build_line_dispatch_callbacks(
        cfg,
        line_input,
        foundation_callbacks,
        operational_callbacks,
    )
    return LineCallbackBundles(
        foundation=foundation_callbacks,
        operational=operational_callbacks,
        dispatch=dispatch_callbacks,
    )
