from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pymarkdown.api import PyMarkdownApi, PyMarkdownScanFailure

from doc2md.limits import MAX_DIAGNOSTIC_CHARACTERS, MAX_MARKDOWN_BYTES
from doc2md.process_worker import run_bounded


PYMARKDOWN_RESULT_BYTES = MAX_MARKDOWN_BYTES + 128
WORKER_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class MarkdownScanResult:
    diagnostics: str

    @property
    def is_clean(self) -> bool:
        return not self.diagnostics


class MarkdownRunner(Protocol):
    def fix(self, markdown: str) -> str: ...

    def scan(self, markdown: str) -> MarkdownScanResult: ...


class PyMarkdownRunner:
    def __init__(
        self,
        config_path: Path,
        timeout_seconds: int = WORKER_TIMEOUT_SECONDS,
    ) -> None:
        self.config_path = config_path.resolve(strict=True)
        self.timeout_seconds = timeout_seconds

    def fix(self, markdown: str) -> str:
        kind, value = self._run("fix", markdown)
        if kind != "fixed":
            raise RuntimeError(value)
        return value

    def scan(self, markdown: str) -> MarkdownScanResult:
        kind, value = self._run("scan", markdown)
        if kind != "scanned":
            raise RuntimeError(value)
        return MarkdownScanResult(value)

    def _run(self, action: str, markdown: str) -> tuple[str, str]:
        if action not in {"fix", "scan"}:
            raise ValueError(f"Acción de PyMarkdown no válida: {action}")
        markdown_bytes = markdown.encode("utf-8")
        if len(markdown_bytes) > MAX_MARKDOWN_BYTES:
            raise RuntimeError("El Markdown supera el límite de 16 MiB")
        with tempfile.TemporaryDirectory(prefix="doc2md-pymarkdown-input-") as input_dir:
            input_path = Path(input_dir) / "input.md"
            input_path.write_bytes(markdown_bytes)
            payload = run_bounded(
                _pymarkdown_worker,
                (str(self.config_path), action, input_path),
                timeout_seconds=self.timeout_seconds,
                max_result_bytes=PYMARKDOWN_RESULT_BYTES,
            )
        kind, separator, value = payload.partition("\n")
        if not separator:
            raise RuntimeError("PyMarkdown devolvió un resultado inválido")
        return kind, value


def _pymarkdown_worker(
    result_path: Path,
    config_path: str,
    action: str,
    input_path: Path,
) -> None:
    original_directory = Path.cwd()
    work_dir = result_path.parent
    os.chdir(work_dir)
    tempfile.tempdir = str(work_dir)
    try:
        markdown_bytes = input_path.read_bytes()
        if len(markdown_bytes) > MAX_MARKDOWN_BYTES:
            raise RuntimeError("El Markdown de entrada supera el límite de 16 MiB")
        markdown = markdown_bytes.decode("utf-8")
        api = (
            PyMarkdownApi()
            .configuration_file_path(config_path)
            .enable_strict_configuration()
        )
        if action == "fix":
            fixed = api.fix_string(markdown).fixed_file
            fixed_bytes = fixed.encode("utf-8")
            if len(fixed_bytes) > MAX_MARKDOWN_BYTES:
                raise RuntimeError("El Markdown reparado supera el límite de 16 MiB")
            result_path.write_bytes(f"fixed\n{fixed}".encode("utf-8"))
            return
        result_path.write_bytes(
            f"scanned\n{_scan_diagnostics(api, markdown)}".encode("utf-8")
        )
    finally:
        os.chdir(original_directory)


def _scan_diagnostics(api: PyMarkdownApi, markdown: str) -> str:
    result = api.scan_string(markdown)
    diagnostics: list[str] = []
    remaining_characters = MAX_DIAGNOSTIC_CHARACTERS
    for failure in result.scan_failures:
        if remaining_characters <= 0:
            break
        diagnostic = _format_scan_failure(failure)[:remaining_characters]
        diagnostics.append(diagnostic)
        remaining_characters -= len(diagnostic) + 1
    for error in result.pragma_errors:
        if remaining_characters <= 0:
            break
        diagnostic = (
            f"pragma {error.file_path}:{error.line_number}: {error.pragma_error}"
        )[:remaining_characters]
        diagnostics.append(diagnostic)
        remaining_characters -= len(diagnostic) + 1
    for critical_error in result.critical_errors:
        if remaining_characters <= 0:
            break
        diagnostic = critical_error[:remaining_characters]
        diagnostics.append(diagnostic)
        remaining_characters -= len(diagnostic) + 1
    if remaining_characters <= 0:
        diagnostics.append("Diagnóstico truncado")
    return "\n".join(diagnostics)


def _format_scan_failure(failure: PyMarkdownScanFailure) -> str:
    return (
        f"{failure.scan_file}:{failure.line_number}:{failure.column_number}: "
        f"{failure.rule_id} {failure.rule_description}"
    )
