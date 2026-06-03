"""Console display helpers shared by grit-console modules."""


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
    widths = [
        max(len(header), max(len(row[i]) for row in cells))
        for i, (header, _) in enumerate(cols)
    ]
    num_w = len(str(len(records)))
    indent = " " * (2 + num_w + 2)

    print("")
    print("  " + " " * num_w + "  " + "  ".join(f"{h:{widths[i]}}" for i, (h, _) in enumerate(cols)))
    print("  " + "─" * num_w + "  " + "  ".join("─" * w for w in widths))
    for n, (rec, row) in enumerate(zip(records, cells), 1):
        line = f"  {n:{num_w}}  " + "  ".join(f"{cell:{widths[i]}}" for i, cell in enumerate(row))
        print(line.rstrip())
        if detail_fn:
            for label, value in (detail_fn(rec) or []):
                if value and value != "-":
                    print(f"{indent}{label}: {value}")
    if footer:
        print(f"\n  {footer}")
