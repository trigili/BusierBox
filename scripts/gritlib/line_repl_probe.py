"""Line REPL probe callback adapters."""


def build_line_probe_callbacks(
    cfg,
    *,
    choose_operator_host_func,
    input_func,
    interactive_func,
    render_probe_command_func,
    workbench_snapshot_func,
    service_record_func=None,
    service_rows_func=None,
    service_start_command_func,
    service_start_func,
    queue_command_func,
    target_filter_func,
    target_context_func,
    probe_delivery_func,
    append_event_fn,
    route_service_callbacks=None,
    probe_results_func=None,
    probe_config_func=None,
    probe_clear_func=None,
    probe_paste_func=None,
    probe_script_func=None,
):
    if service_record_func is None and route_service_callbacks is not None:
        service_record_func = route_service_callbacks["service_record"]
    if service_rows_func is None and route_service_callbacks is not None:
        service_rows_func = lambda _cfg: route_service_callbacks["service_rows"]()

    return {
        "probe_line_start": build_line_probe_start_callback(
            cfg,
            choose_operator_host_func=choose_operator_host_func,
            input_func=input_func,
            interactive_func=interactive_func,
            render_probe_command_func=render_probe_command_func,
            workbench_snapshot_func=workbench_snapshot_func,
            service_record_func=service_record_func,
            service_rows_func=service_rows_func,
            service_start_command_func=service_start_command_func,
            service_start_func=service_start_func,
            queue_command_func=queue_command_func,
            target_filter_func=target_filter_func,
            target_context_func=target_context_func,
            probe_delivery_func=probe_delivery_func,
            append_event_fn=append_event_fn,
        ),
        "probe_results": probe_results_func,
        "probe_config": probe_config_func,
        "probe_clear": probe_clear_func,
        "probe_serve_input": input_func,
        "probe_delivery": probe_delivery_func,
        "probe_paste": probe_paste_func,
        "probe_script": probe_script_func,
    }


def build_line_probe_start_callback(
    cfg,
    *,
    choose_operator_host_func,
    input_func,
    interactive_func,
    render_probe_command_func,
    workbench_snapshot_func,
    service_record_func,
    service_rows_func,
    service_start_command_func,
    service_start_func,
    queue_command_func,
    target_filter_func,
    target_context_func,
    probe_delivery_func,
    append_event_fn,
):
    def probe_line_start(queue=False, start_service=False):
        choose_operator_host_func(
            cfg,
            input_func=input_func,
            interactive=interactive_func(),
        )

        command = render_probe_command_func(cfg)
        snap = workbench_snapshot_func(cfg)
        actions = snap.get("probe_workflow_actions_by_id") or {}
        start_action = actions.get("probe:start-probe") or {}
        start_headless = (
            start_action.get("run_command")
            or start_action.get("headless_command")
            or service_start_command_func(cfg, "probe")
        )

        svc = service_record_func(service_rows_func(cfg), "probe")
        already_listening = str(svc.get("actual") or "") == "listening"

        started = False
        if start_service and not already_listening:
            service_start_func(cfg, "probe", headless_command=start_headless)
            started = True
        elif start_service and already_listening:
            print("Probe listener already running.")

        port = cfg.get("GRIT_PROBE_PORT", 22207)
        script_name = cfg.get("GRIT_PROBE_NAME", "probe.sh")

        if not already_listening and not started:
            print(f"Probe listener is not running on port {port}.")
            print("  start it with: probe start")
            print("")

        state = "listening" if (already_listening or started) else "not listening"
        print(f"Probe  —  port {port}  |  script {script_name}  |  {state}")

        queued = {}
        target_id = target_filter_func(cfg)
        if queue:
            if not target_id:
                raise ValueError("select an agent before probe queue; use agent NAME or use target ID")
            queued = queue_command_func(cfg, command, metadata={
                "work_kind": "probe",
                "workflow": "probe",
                "request_name": str(script_name),
                "route_kind": "bridge" if cfg.get("bridge_profile") else "direct",
                "bridge_profile": str(cfg.get("bridge_profile") or ""),
            })
            print(f"  queued: {queued['id']}")
            print(f"  target: {queued.get('target_id', '')} ({queued.get('target_label', '') or '-'})")

        if already_listening or started:
            probe_delivery_func(cfg)

        append_event_fn(cfg, "workbench", "workbench_probe_command_shown", details={
            "target_command": command,
            "target_id": target_id,
            "target_label": str(target_context_func(cfg).get("target_label") or ""),
            "queued": bool(queue),
            "command_id": queued.get("id", "") if queued else "",
            "started_service": started,
            "already_listening": already_listening,
            "GRIT_PROBE_NAME": str(script_name),
            "GRIT_PROBE_PORT": port,
        })
        return command

    return probe_line_start
