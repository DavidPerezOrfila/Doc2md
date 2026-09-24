from pathlib import Path
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from doc2md.markdown_repair import MarkdownLinter, MarkdownLintError
from doc2md.pymarkdown_runner import (
    MAX_DIAGNOSTIC_CHARACTERS,
    MAX_MARKDOWN_BYTES,
    MarkdownScanResult,
    PyMarkdownRunner,
    _scan_diagnostics,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src" / "doc2md" / "pymarkdown.json"


class StubRunner:
    def __init__(
        self,
        scan_result: MarkdownScanResult,
        fixed_markdown: str = "# Fixed\n",
    ) -> None:
        self.scan_result = scan_result
        self.fixed_markdown = fixed_markdown
        self.fix_calls = 0
        self.scan_calls = 0

    def fix(self, markdown: str) -> str:
        self.fix_calls += 1
        return self.fixed_markdown

    def scan(self, markdown: str) -> MarkdownScanResult:
        self.scan_calls += 1
        return self.scan_result


class PyMarkdownRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = PyMarkdownRunner(CONFIG)

    def test_scans_clean_markdown(self) -> None:
        result = self.runner.scan("# Title\n\nClean output.\n")

        self.assertTrue(result.is_clean)

    def test_rejects_markdown_over_size_limit(self) -> None:
        oversized = "x" * (MAX_MARKDOWN_BYTES + 1)

        with self.assertRaisesRegex(RuntimeError, "16 MiB"):
            self.runner.scan(oversized)

    def test_measures_non_ascii_markdown_in_bytes(self) -> None:
        oversized = "漢" * ((MAX_MARKDOWN_BYTES // 3) + 1)

        with patch("doc2md.pymarkdown_runner.run_bounded") as run_bounded:
            with self.assertRaisesRegex(RuntimeError, "16 MiB"):
                self.runner.scan(oversized)

        run_bounded.assert_not_called()

    def test_enforces_worker_timeout(self) -> None:
        runner = PyMarkdownRunner(CONFIG, timeout_seconds=0)

        with self.assertRaisesRegex(RuntimeError, "excedió 0 segundos"):
            runner.scan("# Title\n")

    def test_bounds_diagnostics(self) -> None:
        failures = [
            SimpleNamespace(
                scan_file="in-memory",
                line_number=index,
                column_number=1,
                rule_id="MD999",
                rule_description="x" * 100,
            )
            for index in range(1000)
        ]
        api = SimpleNamespace(
            scan_string=lambda markdown: SimpleNamespace(
                scan_failures=failures,
                pragma_errors=[],
                critical_errors=[],
            )
        )

        diagnostics = _scan_diagnostics(api, "")

        self.assertLessEqual(len(diagnostics), MAX_DIAGNOSTIC_CHARACTERS + 30)
        self.assertTrue(diagnostics.endswith("Diagnóstico truncado"))

    def test_ignores_local_pymarkdown_plugin_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            marker = root / "marker.txt"
            (plugin_dir / "hostile.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
                encoding="utf-8",
            )
            (root / ".pymarkdown.json").write_text(
                '{"plugins": {"additional_paths": ["plugins"]}}',
                encoding="utf-8",
            )
            original_directory = Path.cwd()
            os.chdir(root)
            try:
                result = self.runner.scan("# Title\n\nClean output.\n")
            finally:
                os.chdir(original_directory)

            self.assertTrue(result.is_clean, result.diagnostics)
            self.assertFalse(marker.exists())

    def test_large_input_does_not_block_spawn_handshake(self) -> None:
        runner = PyMarkdownRunner(CONFIG, timeout_seconds=0)

        with self.assertRaisesRegex(RuntimeError, "excedió 0 segundos"):
            runner.fix("x" * MAX_MARKDOWN_BYTES)

    def test_formats_rule_failure(self) -> None:
        result = self.runner.scan("<span>inline HTML</span>")

        self.assertFalse(result.is_clean)
        self.assertIn("MD033", result.diagnostics)

    def test_reports_invalid_pragma_without_crashing(self) -> None:
        result = self.runner.scan("<!-- pyml disable-next-line -->\n")

        self.assertFalse(result.is_clean)
        self.assertIn("pragma", result.diagnostics)

    def test_fixes_markdown_in_memory(self) -> None:
        fixed = self.runner.fix("#  Title\n\ntext")

        self.assertEqual(fixed, "# Title\n\ntext\n")


class MarkdownLinterRunnerTests(unittest.TestCase):
    def test_uses_injected_runner(self) -> None:
        runner = StubRunner(MarkdownScanResult(""))

        repaired = MarkdownLinter(runner=runner).lint_and_fix("body")

        self.assertEqual(repaired, "# Fixed\n")
        self.assertEqual(runner.fix_calls, 1)
        self.assertEqual(runner.scan_calls, 1)

    def test_reports_injected_scan_diagnostics(self) -> None:
        runner = StubRunner(MarkdownScanResult("MD033 inline HTML"))
        linter = MarkdownLinter(runner=runner, max_attempts=1)

        with self.assertRaisesRegex(MarkdownLintError, "MD033"):
            linter.lint_and_fix("body")

    def test_bounds_markdown_stored_for_quarantine(self) -> None:
        runner = StubRunner(
            MarkdownScanResult("MD033 inline HTML"),
            fixed_markdown="<span>invalid</span>\n" * 100_000,
        )
        linter = MarkdownLinter(runner=runner, max_attempts=1)
        oversized = "body"

        with self.assertRaises(MarkdownLintError) as context:
            linter.lint_and_fix(oversized)

        self.assertLessEqual(len(context.exception.markdown), 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
