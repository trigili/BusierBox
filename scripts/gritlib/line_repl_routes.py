"""Line REPL route and listener callback adapters."""

from gritlib.bridge_routes import (
    add_line_route,
    delete_bridge_profile,
    delete_line_route,
    line_route_record,
    print_bridge_profile,
    print_line_routes,
    select_line_route,
    start_line_route,
    stop_line_route,
)
from gritlib.line_services import (
    print_line_services,
    select_line_service,
    start_line_service,
    stop_line_service,
)


def build_bridge_profile_headless_command_callback(cfg, bridge_command_func):
    def bridge_profile_headless_command(action, name="", extra=None):
        return bridge_command_func(
            cfg,
            action,
            name=name,
            extra=extra,
        )

    return bridge_profile_headless_command


def build_line_route_service_callbacks(
    cfg,
    *,
    service_status_rows_func,
    service_record_func=None,
    bridge_profile_records_func,
    bridge_command_func,
    service_start_command_func,
    service_stop_command_func,
    service_start_func,
    service_stop_func,
    probe_delivery_func,
    sleep_func,
    quote,
):
    bridge_profile_headless_command = build_bridge_profile_headless_command_callback(
        cfg,
        bridge_command_func,
    )

    def route_record(name):
        return line_route_record(bridge_profile_records_func(cfg), name)

    def service_rows():
        return service_status_rows_func(cfg)

    def print_routes(verbose=False):
        return print_line_routes(
            cfg,
            bridge_profile_records_func(cfg),
            verbose=verbose,
            command_builder=bridge_profile_headless_command,
            quote=quote,
        )

    def select_route(selector, records=None):
        return select_line_route(
            cfg,
            selector,
            records if records is not None else bridge_profile_records_func(cfg),
        )

    def add_route(args):
        return add_line_route(
            cfg,
            args,
            headless_command_builder=bridge_profile_headless_command,
        )

    def start_route(route_name):
        return start_line_route(
            cfg,
            route_name,
            bridge_profile_records_func(cfg),
            headless_command_builder=bridge_profile_headless_command,
            start_service=service_start_func,
        )

    def stop_route(route_name):
        return stop_line_route(
            cfg,
            route_name,
            bridge_profile_records_func(cfg),
            headless_command_builder=bridge_profile_headless_command,
            stop_service=service_stop_func,
        )

    def delete_route(route_name):
        return delete_line_route(
            cfg,
            route_name,
            bridge_profile_records_func(cfg),
            headless_command_builder=bridge_profile_headless_command,
        )

    def print_profile(name):
        return print_bridge_profile(cfg, name)

    def delete_profile(name):
        return delete_bridge_profile(cfg, name)

    def select_service(selector):
        return select_line_service(
            cfg,
            selector,
            service_rows(),
            start_command=lambda name: service_start_command_func(cfg, name),
            stop_command=lambda name: service_stop_command_func(cfg, name),
        )

    def print_services(verbose=False):
        return print_line_services(
            cfg,
            service_rows(),
            verbose=verbose,
            start_command=lambda name: service_start_command_func(cfg, name),
            stop_command=lambda name: service_stop_command_func(cfg, name),
            quote=quote,
        )

    def start_service(service):
        return start_line_service(
            cfg,
            service,
            service_rows_func=service_rows,
            route_record_func=route_record,
            route_start_func=start_route,
            service_start_command_func=lambda name: service_start_command_func(cfg, name),
            service_start_func=service_start_func,
            probe_delivery_func=lambda: probe_delivery_func(cfg),
            sleep_func=sleep_func,
        )

    def stop_service(service):
        return stop_line_service(
            cfg,
            service,
            service_rows_func=service_rows,
            route_record_func=route_record,
            route_stop_func=stop_route,
            service_stop_command_func=lambda name: service_stop_command_func(cfg, name),
            service_stop_func=service_stop_func,
        )

    return {
        "bridge_profile_headless_command": bridge_profile_headless_command,
        "line_route_record": route_record,
        "service_rows": service_rows,
        "service_record": service_record_func,
        "print_line_routes": print_routes,
        "select_line_route": select_route,
        "add_line_route": add_route,
        "start_line_route": start_route,
        "stop_line_route": stop_route,
        "delete_line_route": delete_route,
        "print_bridge_profile": print_profile,
        "delete_bridge_profile": delete_profile,
        "select_line_service": select_service,
        "print_line_services": print_services,
        "start_line_service": start_service,
        "stop_line_service": stop_service,
    }
