"""Shared probe workflow guidance for line-console renderers."""


LOCAL_PROBE_STEP_LINES = (
    ("open probe menu", "use listener probe"),
    ("discover target", "start"),
    ("review probe data", "results"),
    ("update active profile", "config"),
)


GLOBAL_PROBE_STEP_LINES = (
    ("open probe menu", "use listener probe"),
    ("discover target", "listener probe start"),
    ("review probe data", "listener probe results"),
    ("update active profile", "listener probe config"),
)


def probe_step_lines(*, local_commands=False):
    return LOCAL_PROBE_STEP_LINES if local_commands else GLOBAL_PROBE_STEP_LINES


def probe_menu_step_text(indent="  ", *, local_commands=False):
    return "\n".join(
        f"{indent}{label}: {command}"
        for label, command in probe_step_lines(local_commands=local_commands)
    )


def print_probe_menu_steps(indent="  ", *, local_commands=False):
    for label, command in probe_step_lines(local_commands=local_commands):
        print(f"{indent}{label}: {command}")


def print_open_probe_menu_steps(indent="  "):
    print_probe_menu_steps(indent)


def open_probe_menu_step_text(indent="  "):
    return probe_menu_step_text(indent)
