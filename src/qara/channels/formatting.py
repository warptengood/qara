"""Channel-agnostic text formatting utilities.

Produces plain-text output suitable for any monospace context.
Each channel wraps the result as needed (e.g. <pre> for Telegram).
"""


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Build a box-drawing table from headers and rows.

    Returns a plain-text string using Unicode box-drawing characters.
    All columns are auto-sized to fit the widest value.
    """
    cols = len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], len(row[i]) if i < len(row) else 0)

    def pad(values: list[str]) -> str:
        cells = []
        for i in range(cols):
            v = values[i] if i < len(values) else ""
            cells.append(f" {v.ljust(widths[i])} ")
        return "│" + "│".join(cells) + "│"

    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    sep = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

    lines = [top, pad(headers), sep]
    for row in rows:
        lines.append(pad(row))
    lines.append(bot)
    return "\n".join(lines)
