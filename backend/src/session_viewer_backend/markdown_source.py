import re


FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
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


def scan_context(lines: list[str], start_line: int):
    """Return (headings, fence_language) for the passage starting at start_line.

    headings are the headings in effect there, outermost first, as ATX lines. They
    are ancestors of the passage: for "## A", "### B", text the chain at the text
    is ["## A", "### B"]. Headings inside fenced code are ignored. A heading that
    starts on start_line is the annotated text itself, so it is excluded, along
    with the siblings and deeper headings it closes.

    fence_language is None unless start_line is inside a fenced code block that
    opened on an earlier line; then it is the first word of the fence's info
    string ("" when it has none).
    """
    stack: list[tuple[int, str, int]] = []
    fence = None
    inside = None
    index = 0
    last = min(start_line, len(lines))
    while index < last:
        if index + 1 == start_line:
            inside = fence
        fence_match = FENCE_RE.match(lines[index])
        if fence_match:
            marker = fence_match.group(1)
            info = fence_match.group(2).strip()
            if fence is None:
                fence = (marker[0], len(marker), info.split()[0] if info else "")
            elif marker[0] == fence[0] and len(marker) >= fence[1] and not info:
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
    if start_line > len(lines):
        inside = fence
    if stack and stack[-1][2] == start_line:
        stack.pop()
    return (
        [f"{'#' * depth} {text}" for depth, text, _ in stack],
        None if inside is None else inside[2],
    )


def heading_chain(lines: list[str], start_line: int):
    return scan_context(lines, start_line)[0]


def source_snapshot(markdown: str, start_line: int, end_line: int):
    """Return (source_text, source_context, source_fence) for 1-based, inclusive lines."""
    lines = split_lines(markdown)
    headings, fence_language = scan_context(lines, start_line)
    return (
        "\n".join(lines[start_line - 1 : end_line]),
        "\n".join(headings),
        fence_language,
    )
