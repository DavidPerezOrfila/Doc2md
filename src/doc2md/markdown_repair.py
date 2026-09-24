from __future__ import annotations

import re
import textwrap

from doc2md.pymarkdown_runner import MarkdownRunner
from doc2md.table_repair import repair_tables

ATX_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$")
FENCE_START = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
LIST_ITEM = re.compile(r"^[ \t]*(?:[-+*]|\d+[.)])(?:[ \t]+|$)")
BARE_URL = re.compile(r"(?<![<(\[])(?:https?://|www\.)[^\s<>]+")
HARD_BREAK = re.compile(r"(?: {2,}|\\)$")
REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:\s+\S+")
INDENTED_CODE = re.compile(r"^(?: {4}|\t)")
MAX_QUARANTINE_MARKDOWN_CHARACTERS = 1024 * 1024

FenceState = tuple[str, int] | None


class MarkdownLintError(RuntimeError):
    def __init__(self, diagnostics: str, markdown: str) -> None:
        super().__init__(diagnostics)
        self.diagnostics = diagnostics
        self.markdown = markdown


class MarkdownLinter:
    def __init__(
        self,
        runner: MarkdownRunner,
        max_attempts: int = 5,
        line_length: int = 120,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts debe ser mayor que cero")
        if line_length < 1:
            raise ValueError("line_length debe ser mayor que cero")
        self.runner = runner
        self.max_attempts = max_attempts
        self.line_length = line_length

    def lint_and_fix(self, markdown: str, document_title: str = "Document") -> str:
        if not markdown.strip():
            return ""
        current = _prepare_markdown(markdown, document_title, self.line_length)
        for attempt in range(1, self.max_attempts + 1):
            try:
                fixed = self.runner.fix(current)
            except RuntimeError as error:
                raise MarkdownLintError(
                    str(error),
                    _bounded_markdown(current),
                ) from error
            current = _prepare_markdown(fixed, document_title, self.line_length)
            try:
                result = self.runner.scan(current)
            except RuntimeError as error:
                raise MarkdownLintError(
                    str(error),
                    _bounded_markdown(current),
                ) from error
            if result.is_clean:
                return current
            if attempt == self.max_attempts:
                raise MarkdownLintError(
                    result.diagnostics,
                    _bounded_markdown(current),
                )
        raise MarkdownLintError(
            "No se pudo analizar el Markdown",
            _bounded_markdown(current),
        )


def _prepare_markdown(markdown: str, document_title: str, line_length: int) -> str:
    front_matter, body = _split_front_matter(_normalize_line_endings(markdown))
    front_matter_has_h1 = bool(re.search(r"(?im)^title\s*:", front_matter))
    body = _convert_setext_headings(body)
    if front_matter_has_h1:
        body = _degrade_repeated_h1(body, keep_first=False)
    else:
        body = _degrade_repeated_h1(body)
    body = _repair_bare_urls(body)
    body = _escape_reversed_links(body)
    body = _clean_heading_punctuation(body)
    body = _ensure_block_separation(body)
    body = repair_tables(body, line_length)
    body = _collapse_blank_lines(body)
    body = _wrap_long_paragraphs(body, line_length)
    if not front_matter_has_h1:
        body = _ensure_document_heading(body, document_title)
    if not front_matter:
        return body
    return front_matter.rstrip() + "\n\n" + body.lstrip().rstrip() + "\n"


def _split_front_matter(markdown: str) -> tuple[str, str]:
    lines = markdown.split("\n")
    if not lines or lines[0].strip() not in {"---", "+++"}:
        return "", markdown
    marker = lines[0].strip()
    for index in range(1, len(lines)):
        if lines[index].strip() == marker:
            return "\n".join(lines[: index + 1]), "\n".join(lines[index + 1 :])
    return "", markdown


def _normalize_line_endings(markdown: str) -> str:
    return markdown.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")


def _convert_setext_headings(markdown: str) -> str:
    lines = markdown.split("\n")
    converted: list[str] = []
    fence: FenceState = None
    index = 0
    while index < len(lines):
        line = lines[index]
        is_boundary, next_fence = _update_fence(line, fence)
        if is_boundary:
            converted.append(line)
            fence = next_fence
            index += 1
            continue
        if (
            fence is None
            and index + 1 < len(lines)
            and line.strip()
            and not ATX_HEADING.match(line)
            and not LIST_ITEM.match(line)
            and not INDENTED_CODE.match(line)
        ):
            underline = lines[index + 1]
            if re.fullmatch(r" {0,3}=+", underline):
                converted.append(f"# {line.strip()}")
                index += 2
                continue
            if re.fullmatch(r" {0,3}-+", underline):
                converted.append(f"## {line.strip()}")
                index += 2
                continue
        converted.append(_trim_plain_line(line) if fence is None else line)
        index += 1
    return "\n".join(converted)


def _degrade_repeated_h1(markdown: str, keep_first: bool = True) -> str:
    lines = markdown.split("\n")
    fence: FenceState = None
    found_h1 = False
    for index, line in enumerate(lines):
        is_boundary, next_fence = _update_fence(line, fence)
        if is_boundary:
            fence = next_fence
            continue
        match = ATX_HEADING.match(line) if fence is None else None
        if not match or match.group(1) != "#":
            continue
        if found_h1 or not keep_first:
            lines[index] = f"## {match.group(2) or ''}".rstrip()
        else:
            found_h1 = True
    return "\n".join(lines)


def _repair_bare_urls(markdown: str) -> str:
    lines = markdown.split("\n")
    fence: FenceState = None
    for index, line in enumerate(lines):
        is_boundary, next_fence = _update_fence(line, fence)
        if is_boundary:
            fence = next_fence
            continue
        if fence is None:
            lines[index] = _replace_urls_outside_markdown(line)
    return "\n".join(lines)


def _replace_urls_outside_markdown(line: str) -> str:
    if line.lstrip().startswith("[") and "]:" in line:
        return _autolink_reference_definition(line)
    result: list[str] = []
    cursor = 0
    while cursor < len(line):
        link = _next_inline_link(line, cursor)
        if link is None:
            result.append(_replace_urls_outside_inline_code(line[cursor:]))
            break
        start, end = link
        result.append(_replace_urls_outside_inline_code(line[cursor:start]))
        result.append(line[start:end])
        cursor = end
    return "".join(result)


def _autolink_reference_definition(line: str) -> str:
    marker = line.find("]:")
    if marker < 0:
        return line
    destination_start = marker + 2
    while destination_start < len(line) and line[destination_start].isspace():
        destination_start += 1
    destination_end = destination_start
    while destination_end < len(line) and not line[destination_end].isspace():
        destination_end += 1
    destination = line[destination_start:destination_end]
    if not destination.startswith(("http://", "https://", "www.")):
        return line
    if destination.startswith("www."):
        destination = f"https://{destination}"
    return line[:destination_start] + f"<{destination}>" + line[destination_end:]


def _next_inline_link(line: str, cursor: int) -> tuple[int, int] | None:
    search_from = cursor
    while search_from < len(line):
        label_start = line.find("[", search_from)
        if label_start < 0:
            return None
        if label_start > 0 and line[label_start - 1] == "\\":
            search_from = label_start + 1
            continue
        label_end = _matching_square_bracket(line, label_start)
        if label_end is None:
            return None
        opening_parenthesis = label_end + 1
        while opening_parenthesis < len(line) and line[opening_parenthesis].isspace():
            opening_parenthesis += 1
        if opening_parenthesis >= len(line) or line[opening_parenthesis] != "(":
            search_from = label_end + 1
            continue
        closing_parenthesis = _matching_parenthesis(line, opening_parenthesis)
        if closing_parenthesis is None:
            return None
        start = label_start - 1 if label_start > 0 and line[label_start - 1] == "!" else label_start
        return start, closing_parenthesis + 1
    return None


def _matching_square_bracket(line: str, opening: int) -> int | None:
    depth = 0
    escaped = False
    for index in range(opening, len(line)):
        character = line[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index
    return None


def _matching_parenthesis(line: str, opening: int) -> int | None:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(line)):
        character = line[index]
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in "'\"":
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _replace_urls_outside_inline_code(line: str) -> str:
    result: list[str] = []
    cursor = 0
    while cursor < len(line):
        opening = re.search(r"`+|<", line[cursor:])
        if not opening:
            result.append(_replace_bare_urls(line[cursor:]))
            break
        opening_start = cursor + opening.start()
        result.append(_replace_bare_urls(line[cursor:opening_start]))
        marker = opening.group(0)
        if marker == "<":
            closing_angle = line.find(">", opening_start + 1)
            if closing_angle == -1:
                result.append(line[opening_start:])
                break
            result.append(line[opening_start : closing_angle + 1])
            cursor = closing_angle + 1
            continue
        run = marker
        closing_pattern = re.compile(rf"(?<!`){re.escape(run)}(?!`)")
        closing = closing_pattern.search(line, opening_start + len(run))
        if not closing:
            result.append(line[opening_start:])
            break
        result.append(line[opening_start : closing.end()])
        cursor = closing.end()
    return "".join(result)


def _replace_bare_urls(text: str) -> str:
    parts = re.split(r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''', text)
    for part_index in range(0, len(parts), 2):
        parts[part_index] = BARE_URL.sub(_autolink_url, parts[part_index])
    return "".join(parts)


def _autolink_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    suffix = ""
    while raw_url:
        last = raw_url[-1]
        if last in ".,;:!?'\"":
            suffix = last + suffix
            raw_url = raw_url[:-1]
            continue
        if last == ")" and raw_url.count("(") < raw_url.count(")"):
            suffix = last + suffix
            raw_url = raw_url[:-1]
            continue
        break
    target = f"https://{raw_url}" if raw_url.lower().startswith("www.") else raw_url
    return f"<{target}>{suffix}" if target else match.group(0)


def _escape_reversed_links(markdown: str) -> str:
    lines = markdown.split("\n")
    fence: FenceState = None
    for index, line in enumerate(lines):
        is_boundary, next_fence = _update_fence(line, fence)
        if not is_boundary and fence is None:
            parts = re.split(
                r'''(`+[^`]*`+|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''',
                line,
            )
            for part_index in range(0, len(parts), 2):
                parts[part_index] = re.sub(r"\)\[", ")&#91;", parts[part_index])
            lines[index] = "".join(parts)
        fence = next_fence
    return "\n".join(lines)


def _clean_heading_punctuation(markdown: str) -> str:
    lines = markdown.split("\n")
    fence: FenceState = None
    for index, line in enumerate(lines):
        is_boundary, next_fence = _update_fence(line, fence)
        if is_boundary:
            fence = next_fence
            continue
        match = ATX_HEADING.match(line) if fence is None else None
        if match:
            content = (match.group(2) or "").rstrip().rstrip(".,;:!?")
            lines[index] = f"{match.group(1)} {content}".rstrip()
    return "\n".join(lines)


def _ensure_block_separation(markdown: str) -> str:
    source = markdown.split("\n")
    output: list[str] = []
    fence: FenceState = None
    in_list = False
    pending_heading_blank = False
    for line in source:
        is_boundary, next_fence = _update_fence(line, fence)
        is_heading = not is_boundary and fence is None and bool(ATX_HEADING.match(line))
        is_list_item = (
            not is_boundary
            and fence is None
            and not INDENTED_CODE.match(line)
            and bool(LIST_ITEM.match(line))
        )

        if pending_heading_blank and line.strip():
            output.append("")
            pending_heading_blank = False
        if is_heading and output and output[-1].strip():
            output.append("")
        if is_list_item and not in_list and output and output[-1].strip():
            output.append("")

        output.append(line if is_boundary or fence is not None else _trim_plain_line(line))
        pending_heading_blank = is_heading
        if is_heading or is_boundary or not line.strip():
            in_list = False
        elif is_list_item or in_list:
            in_list = True
        fence = next_fence
    while output and not output[-1].strip():
        output.pop()
    return "\n".join(output)


def _collapse_blank_lines(markdown: str) -> str:
    lines = markdown.split("\n")
    output: list[str] = []
    fence: FenceState = None
    previous_blank = False
    for line in lines:
        is_boundary, next_fence = _update_fence(line, fence)
        if is_boundary:
            fence = next_fence
        is_blank = not line.strip() and fence is None
        if not (is_blank and previous_blank):
            output.append(line)
        previous_blank = is_blank
        fence = next_fence
    while output and not output[-1].strip():
        output.pop()
    return "\n".join(output)


def _contains_markdown_link(line: str) -> bool:
    return "](" in line or (line.lstrip().startswith("[") and "]:" in line)


def _wrap_long_paragraphs(markdown: str, line_length: int) -> str:
    source = markdown.split("\n")
    output: list[str] = []
    paragraph: list[str] = []
    fence: FenceState = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if not paragraph:
            return
        if any(
            HARD_BREAK.search(line)
            or REFERENCE_DEFINITION.match(line)
            or _contains_markdown_link(line)
            for line in paragraph
        ):
            output.extend(paragraph)
        else:
            text = " ".join(line.strip() for line in paragraph)
            output.extend(
                textwrap.wrap(
                    text,
                    width=line_length,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
        paragraph = []

    for line in source:
        is_boundary, next_fence = _update_fence(line, fence)
        is_special = (
            is_boundary
            or fence is not None
            or not line.strip()
            or INDENTED_CODE.match(line) is not None
            or ATX_HEADING.match(line) is not None
            or LIST_ITEM.match(line) is not None
            or REFERENCE_DEFINITION.match(line) is not None
            or line.lstrip().startswith(("|", ">"))
        )
        if is_special:
            flush_paragraph()
            output.append(line)
        else:
            paragraph.append(line)
        fence = next_fence
    flush_paragraph()
    return "\n".join(output)


def _ensure_document_heading(markdown: str, document_title: str) -> str:
    lines = markdown.splitlines()
    first_content_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_content_index is None:
        return ""
    first = lines[first_content_index]
    first_heading = ATX_HEADING.match(first)
    if first_heading and first_heading.group(1) == "#":
        return markdown.rstrip() + "\n"

    title = re.sub(r"[\\`*_{}\[\]()<>#]", "", document_title).strip()
    title = re.sub(r"[.!?,;:]+$", "", title) or "Document"
    return f"# {title}\n\n{markdown.lstrip()}"


def _update_fence(line: str, active: FenceState) -> tuple[bool, FenceState]:
    match = FENCE_START.match(line)
    if not match:
        return False, active
    marker = match.group(1)
    suffix = match.group(2)
    if active is None:
        if marker[0] == "`" and "`" in suffix:
            return False, None
        return True, (marker[0], len(marker))
    fence_character, minimum_length = active
    if (
        marker[0] == fence_character
        and len(marker) >= minimum_length
        and not suffix.strip()
    ):
        return True, None
    return False, active


def _bounded_markdown(markdown: str) -> str:
    return markdown[:MAX_QUARANTINE_MARKDOWN_CHARACTERS]


def _trim_plain_line(line: str) -> str:
    return line if HARD_BREAK.search(line) or INDENTED_CODE.match(line) else line.rstrip()
