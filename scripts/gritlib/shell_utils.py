"""Shell command formatting helpers for grit-console."""


def shquote(value):
    text = str(value)
    if all(ch.isalnum() or ch in "._-/:=" for ch in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"
