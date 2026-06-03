"""Small configuration value helpers for grit-console."""


def yes(value):
    return str(value).lower() in {"1", "true", "yes", "on"}
