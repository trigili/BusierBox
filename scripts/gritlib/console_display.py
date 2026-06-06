"""Console display helpers shared by grit-console modules."""

import os
import shutil


NORMAL_WIDTH = 80
ULTRA_NARROW_WIDTH = 50
STACKED_TABLE_WIDTH = 70
MIN_TABLE_CELL_WIDTH = 4


def console_width():
    override = (os.environ.get("GRIT_CONSOLE_WIDTH") or "").strip().lower()
    if override in ("phone", "ultra", "ultra-narrow"):
        return 40
    if override in ("compact", "narrow"):
        return 70
    if override:
        try:
            return max(20, int(override))
        except ValueError:
            pass
    env_columns = (os.environ.get("COLUMNS") or "").strip()
    if env_columns:
        try:
            columns = int(env_columns)
        except ValueError:
            columns = 0
        if columns <= STACKED_TABLE_WIDTH:
            return max(20, columns)
    terminal_columns = shutil.get_terminal_size(fallback=(120, 24)).columns
    if terminal_columns <= STACKED_TABLE_WIDTH:
        return max(20, terminal_columns)
    return 10000


def console_display_mode(width=None):
    width = console_width() if width is None else int(width)
    if width <= ULTRA_NARROW_WIDTH:
        return "ultra-narrow"
    if width <= NORMAL_WIDTH:
        return "narrow"
    return "normal"


def print_dry_run_notice(*, machine=False):
    if machine:
        print("dry_run=yes")
    else:
        print("preview only: no changes applied")


def _middle_truncate(text, width):
    text = str(text)
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return "." * width
    left = max(1, (width - 3) // 2)
    right = max(1, width - 3 - left)
    return f"{text[:left]}...{text[-right:]}"


def _fit_widths(widths, max_total):
    widths = list(widths)
    if not widths or sum(widths) <= max_total:
        return widths
    min_widths = [min(width, MIN_TABLE_CELL_WIDTH) for width in widths]
    while sum(widths) > max_total and widths != min_widths:
        idx = max(
            range(len(widths)),
            key=lambda i: (widths[i] - min_widths[i], i),
        )
        if widths[idx] <= min_widths[idx]:
            break
        widths[idx] -= 1
    return widths


def _print_stacked_table(records, cols, cells, detail_fn=None):
    num_w = len(str(len(records)))
    for n, (rec, row) in enumerate(zip(records, cells), 1):
        print(f"  {n:{num_w}}.")
        for cell, (header, _) in zip(row, cols):
            value = str(cell or "-")
            print(f"    {header}: {value}")
        if detail_fn:
            for label, value in (detail_fn(rec) or []):
                if value and value != "-":
                    print(f"    {label}: {value}")


def console_table(title, records, cols, detail_fn=None, footer=None):
    """Render a numbered table to stdout.

    cols      — list of (header, getter) where getter is a dict key or callable(rec)->str
    detail_fn — optional callable(rec) -> list of (label, value) shown indented below each row
    footer    — optional one-line hint printed after the table
    """
    def _get(rec, getter):
        return str(getter(rec) if callable(getter) else (rec.get(getter) or "")) or "-"

    print(title)
    if not records:
        print("  (none)")
        if footer:
            print(f"\n  {footer}")
        return

    cells = [[_get(rec, g) for _, g in cols] for rec in records]
    width = console_width()
    if width <= STACKED_TABLE_WIDTH:
        print("")
        _print_stacked_table(records, cols, cells, detail_fn=detail_fn)
        if footer:
            print(f"\n  {footer}")
        return

    widths = [
        max(len(header), max(len(row[i]) for row in cells))
        for i, (header, _) in enumerate(cols)
    ]
    num_w = len(str(len(records)))
    prefix_w = 2 + num_w + 2
    separators_w = max(0, len(cols) - 1) * 2
    max_cells_w = max(1, width - prefix_w - separators_w)
    widths = _fit_widths(widths, max_cells_w)
    indent = " " * (2 + num_w + 2)

    print("")
    headers = [_middle_truncate(h, widths[i]) for i, (h, _) in enumerate(cols)]
    print("  " + " " * num_w + "  " + "  ".join(f"{h:{widths[i]}}" for i, h in enumerate(headers)))
    print("  " + "─" * num_w + "  " + "  ".join("─" * w for w in widths))
    for n, (rec, row) in enumerate(zip(records, cells), 1):
        fitted = [_middle_truncate(cell, widths[i]) for i, cell in enumerate(row)]
        line = f"  {n:{num_w}}  " + "  ".join(f"{cell:{widths[i]}}" for i, cell in enumerate(fitted))
        print(line.rstrip())
        if detail_fn:
            for label, value in (detail_fn(rec) or []):
                if value and value != "-":
                    print(f"{indent}{label}: {value}")
    if footer:
        print(f"\n  {footer}")
