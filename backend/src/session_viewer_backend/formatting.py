import re
import textwrap


def normalized_title(markdown: str, width=100):
    value = " ".join(markdown.split())
    value = re.sub(r"^#+\s*", "", value)
    return textwrap.shorten(value, width=width, placeholder="…") or "Untitled session"
