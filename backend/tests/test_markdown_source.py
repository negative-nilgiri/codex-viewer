import pytest

from session_viewer_backend.markdown_source import (
    heading_chain,
    scan_context,
    source_snapshot,
    split_lines,
)


def chain(markdown: str, line: int):
    return heading_chain(split_lines(markdown), line)


def fence(markdown: str, line: int):
    return scan_context(split_lines(markdown), line)[1]


def test_chain_is_the_headings_above_the_passage():
    markdown = "## Heading\n### Subheading\nsome-text\n"
    assert chain(markdown, 3) == ["## Heading", "### Subheading"]


def test_chain_has_no_headings_before_the_first_one():
    assert chain("intro\n\n## Later\n", 1) == []


def test_a_new_sibling_or_parent_replaces_deeper_headings():
    markdown = "## A\n### A1\ntext\n## B\ntext2\n# Top\ntext3\n"
    assert chain(markdown, 3) == ["## A", "### A1"]
    assert chain(markdown, 5) == ["## B"]
    assert chain(markdown, 7) == ["# Top"]


def test_skipped_levels_are_kept_as_written():
    assert chain("# A\n#### D\ntext\n", 3) == ["# A", "#### D"]


def test_an_annotated_heading_is_not_repeated_and_closes_its_siblings():
    markdown = "# Title\n## A\n### A1\ntext\n## B\nbody\n"
    assert chain(markdown, 5) == ["# Title"]
    assert chain(markdown, 3) == ["# Title", "## A"]


def test_hashes_inside_fenced_code_are_not_headings():
    markdown = "## Real\n```python\n# comment\n## also code\n```\ntext\n"
    assert chain(markdown, 6) == ["## Real"]
    assert chain(markdown, 4) == ["## Real"]


def test_a_longer_closing_fence_and_tildes_close_a_fence():
    markdown = "## Real\n~~~\n# code\n~~~~\n### After\ntext\n"
    assert chain(markdown, 6) == ["## Real", "### After"]


def test_closing_hashes_and_extra_spaces_are_normalised():
    assert chain("##   Title with   gaps ##  \ntext\n", 2) == ["## Title with   gaps"]


def test_empty_headings_are_ignored():
    assert chain("## Real\n##\ntext\n", 3) == ["## Real"]


def test_setext_headings_are_reported_in_atx_form():
    markdown = "Title\n=====\n\nSub\n---\nbody\n"
    assert chain(markdown, 6) == ["# Title", "## Sub"]


def test_a_thematic_break_after_a_list_item_or_quote_is_not_a_heading():
    assert chain("## A\n- item\n---\ntext\n", 4) == ["## A"]
    assert chain("## A\n> quote\n---\ntext\n", 4) == ["## A"]


def test_windows_and_old_mac_line_endings_count_like_unix_ones():
    assert chain("## A\r\ntext\r\n", 2) == ["## A"]
    assert chain("## A\rtext\r", 2) == ["## A"]


def test_unicode_line_separators_do_not_shift_line_numbers():
    markdown = "## A\n\u2028still line two\n### B\ntext\n"
    assert chain(markdown, 4) == ["## A", "### B"]


def test_a_start_line_past_the_end_uses_every_heading():
    assert chain("## A\ntext\n", 99) == ["## A"]


def test_snapshot_returns_the_source_lines_and_their_headings():
    markdown = "## Heading\n### Subheading\nfirst **bold** line\nsecond line\nthird\n"
    assert source_snapshot(markdown, 3, 4) == (
        "first **bold** line\nsecond line",
        "## Heading\n### Subheading",
        None,
    )


def test_snapshot_context_is_empty_without_headings():
    assert source_snapshot("plain\n", 1, 1) == ("plain", "", None)


@pytest.mark.parametrize(
    "markdown",
    ["$$\nx = \\frac{1}{2}\n$$\n", "```python\nprint(1)\n```\n"],
)
def test_snapshot_keeps_math_and_code_exactly(markdown):
    text, _, _ = source_snapshot(markdown, 1, 3)
    assert text == markdown.rstrip("\n")


CODE = "intro\n```python\nprint(1)\nprint(2)\n```\nafter\n"


def test_fence_language_is_reported_for_lines_inside_a_fenced_block():
    assert fence(CODE, 3) == "python"
    assert fence(CODE, 4) == "python"


def test_fence_is_none_outside_a_block_and_on_its_opening_line():
    assert fence(CODE, 1) is None
    assert fence(CODE, 2) is None
    assert fence(CODE, 6) is None


def test_the_closing_fence_line_is_still_inside_the_block():
    assert fence(CODE, 5) == "python"


def test_a_fence_without_a_language_reports_an_empty_string():
    assert fence("```\ncode\n```\n", 2) == ""


def test_only_the_first_word_of_the_info_string_is_the_language():
    assert fence("```js title=a.js\ncode\n```\n", 2) == "js"


def test_tilde_fences_and_longer_fences_are_tracked():
    assert fence("~~~ruby\ncode\n~~~\ntext\n", 2) == "ruby"
    assert fence("````md\n```\nnested\n```\n````\ntext\n", 3) == "md"
    assert fence("````md\n```\nnested\n```\n````\ntext\n", 6) is None


def test_a_fence_line_with_an_info_string_does_not_close_the_block():
    assert fence("```python\n```js\ncode\n```\ntext\n", 3) == "python"
    assert fence("```python\n```js\ncode\n```\ntext\n", 5) is None


def test_an_unclosed_fence_stays_open_to_the_end():
    assert fence("```sh\nls\n", 2) == "sh"
    assert fence("```sh\nls\n", 99) == "sh"


def test_snapshot_reports_the_fence_for_code_lines():
    assert source_snapshot("## Run\n```sh\nls -la\n```\n", 3, 3) == (
        "ls -la",
        "## Run",
        "sh",
    )
