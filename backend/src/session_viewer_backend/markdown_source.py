import re


FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$")
SETEXT_UNDERLINE_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
CLOSING_HASHES_RE = re.compile(r"[ \t]+#+[ \t]*$")
# A line that starts a list item or quote cannot be the text of a setext heading;
# a following "---" is a thematic break there.
NOT_SETEXT_TEXT_RE = re.compile(r"^ {0,3}(?:[-*+]|\d+[.)])[ \t]|^ {0,3}>")
# Match how Markdown parsers count lines. str.splitlines() also splits on form
# feed, U+2028 and others, which would shift line numbers.
LINE_BREAK_RE = re.compile(r"\r\n|\r|\n")


def split_lines(markdown: str):
    return LINE_BREAK_RE.split(markdown)


def _heading_at(lines: list[str], index: int):
    """Return (depth, text, lines_used) when a heading starts at lines[index]."""
    line = lines[index]
    atx = ATX_RE.match(line)
    if atx:
        text = CLOSING_HASHES_RE.sub("", atx.group(2) or "").strip()
        return (len(atx.group(1)), text, 1) if text else None
    if (
        line.strip()
        and not NOT_SETEXT_TEXT_RE.match(line)
        and index + 1 < len(lines)
    ):
        underline = SETEXT_UNDERLINE_RE.match(lines[index + 1])
        if underline:
            return (1 if underline.group(1)[0] == "=" else 2, line.strip(), 2)
    return None


def heading_chain(lines: list[str], start_line: int):
    """Headings in effect at start_line, outermost first, as ATX heading lines.

    The headings are ancestors of the passage: for "## A", "### B", text the
    chain at the text is ["## A", "### B"]. Headings inside fenced code are
    ignored. A heading that starts on start_line is the annotated text itself, so
    it is excluded, along with the siblings and deeper headings it closes.
    """
    stack: list[tuple[int, str, int]] = []
    fence = None
    index = 0
    last = min(start_line, len(lines))
    while index < last:
        fence_match = FENCE_RE.match(lines[index])
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
            index += 1
            continue
        if fence is not None:
            index += 1
            continue
        heading = _heading_at(lines, index)
        if heading is None:
            index += 1
            continue
        depth, text, used = heading
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, text, index + 1))
        index += used
    if stack and stack[-1][2] == start_line:
        stack.pop()
    return [f"{'#' * depth} {text}" for depth, text, _ in stack]


def source_snapshot(markdown: str, start_line: int, end_line: int):
    """Return (source_text, source_context) for annotated 1-based, inclusive lines."""
    lines = split_lines(markdown)
    return (
        "\n".join(lines[start_line - 1 : end_line]),
        "\n".join(heading_chain(lines, start_line)),
    )
