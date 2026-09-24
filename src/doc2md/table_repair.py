from __future__ import annotations

import re
import textwrap

FENCE_START = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
TABLE_SEPARATOR = re.compile(r"^ {0,3}\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")


def repair_tables(markdown: str, line_length: int) -> str:
    lines = markdown.split("\n")
    output: list[str] = []
    index = 0
    fence_character: str | None = None
    fence_length = 0

    while index < len(lines):
        line = lines[index]
        boundary, next_character, next_length = _update_fence(line, fence_character, fence_length)
        if boundary:
            fence_character = next_character
            fence_length = next_length
            output.append(line)
            index += 1
            continue
        if fence_character is not None or not _is_table_line(line):
            output.append(line)
            index += 1
            continue

        block: list[str] = []
        while index < len(lines) and _is_table_line(lines[index]):
            block.append(lines[index].rstrip())
            index += 1

        if output and output[-1].strip():
            output.append("")
        if _is_consistent_table(block):
            output.extend(block)
        else:
            output.extend(_degrade_table(block, line_length))
        output.append("")

    while output and not output[-1].strip():
        output.pop()
    return "\n".join(output)


def _is_table_line(line: str) -> bool:
    return not line.startswith(("    ", "\t")) and line.lstrip().startswith("|")


def _is_consistent_table(block: list[str]) -> bool:
    if len(block) < 2 or not TABLE_SEPARATOR.match(block[1]):
        return False
    expected = _pipe_count(block[0])
    return expected > 1 and all(_pipe_count(row) == expected for row in block[1:])


def _pipe_count(line: str) -> int:
    count = 0
    escaped = False
    for character in line:
        if character == "|" and not escaped:
            count += 1
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    return count


def _degrade_table(block: list[str], line_length: int) -> list[str]:
    output = ["```text"]
    for line in block:
        output.extend(
            textwrap.wrap(
                line,
                width=line_length,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [""]
        )
    output.append("```")
    return output


def _update_fence(
    line: str,
    active_character: str | None,
    active_length: int,
) -> tuple[bool, str | None, int]:
    match = FENCE_START.match(line)
    if not match:
        return False, active_character, active_length
    marker = match.group(1)
    suffix = match.group(2)
    if active_character is None:
        if marker[0] == "`" and "`" in suffix:
            return False, None, 0
        return True, marker[0], len(marker)
    if (
        marker[0] == active_character
        and len(marker) >= active_length
        and not suffix.strip()
    ):
        return True, None, 0
    return False, active_character, active_length
