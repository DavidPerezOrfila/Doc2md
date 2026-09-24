from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from doc2md.config import executable_path
from doc2md.markdown_repair import MarkdownLinter

ROOT = Path(__file__).resolve().parents[1]
PYMARKDOWN = executable_path("pymarkdown.exe" if sys.platform == "win32" else "pymarkdown")
CONFIG = ROOT / ".pymarkdown.json"


class MarkdownLinterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.linter = MarkdownLinter(CONFIG, PYMARKDOWN, max_attempts=5)

    def test_repairs_markdown_until_scan_has_no_warnings(self) -> None:
        repaired = self.linter.lint_and_fix("#  Title\ntext   ")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "document.md"
            path.write_text(repaired, encoding="utf-8")
            result = subprocess.run(
                [
                    str(PYMARKDOWN),
                    "--config",
                    str(CONFIG),
                    "--strict-config",
                    "scan",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# Title", repaired)

    def test_adds_heading_to_plain_text_output(self) -> None:
        repaired = self.linter.lint_and_fix("Integration Document", "integration")

        self.assertTrue(repaired.startswith("# integration\n"))

    def test_configuration_applies_120_character_limit(self) -> None:
        result = subprocess.run(
            [str(PYMARKDOWN), "--config", str(CONFIG), "--strict-config", "plugins", "info", "md013"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("line_length             integer  120", result.stdout)

    def test_uses_configured_120_character_line_limit(self) -> None:
        line = "word " * 24

        repaired = self.linter.lint_and_fix(f"# Title\n\n{line.strip()}", "line")

        self.assertGreater(len(max(repaired.splitlines(), key=len)), 80)
        self.assertLessEqual(len(max(repaired.splitlines(), key=len)), 120)

    def test_repairs_and_degrades_markitdown_structure(self) -> None:
        markdown = """Visit https://example.com
- first
- second
Section
===
# First
# Second?
"""

        repaired = self.linter.lint_and_fix(markdown, "document")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "document.md"
            path.write_text(repaired, encoding="utf-8")
            result = subprocess.run(
                [str(PYMARKDOWN), "--config", str(CONFIG), "--strict-config", "scan", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("## Second", repaired)
        self.assertIn("# Section", repaired)
        self.assertIn("<https://example.com>", repaired)

    def test_preserves_list_continuations_and_nested_hierarchy(self) -> None:
        markdown = """# Lists

- first item
continued text
  - nested item
    1. deep item
- second item
"""

        repaired = self.linter.lint_and_fix(markdown, "lists")

        self.assertIn("- first item\ncontinued text", repaired)
        self.assertIn("  - nested item\n    1. deep item", repaired)

    def test_preserves_hard_breaks_and_code_fences(self) -> None:
        markdown = """# Formatting

first line  
second line

````markdown
~~~text
## Code heading
https://code.example.com
~~~
````
"""

        repaired = self.linter.lint_and_fix(markdown, "formatting")

        self.assertIn("first line  \nsecond line", repaired)
        self.assertIn("~~~text\n## Code heading\nhttps://code.example.com\n~~~", repaired)

    def test_wraps_only_bare_urls_without_changing_links(self) -> None:
        markdown = """# Links

See https://example.com.
[label](https://target.example.com)
[https://label.example.com](https://target.example.com)
[label](https://target.example.com "https://title.example.com")
[outer https://outer.example [inner]](https://target.example.com)
[foo [bar]]: https://reference.example.com
[foo\\]]: https://escaped.example.com
Example: Uri.Parts("http://contoso?a=" & data)[Query][a]
"""

        repaired = self.linter.lint_and_fix(markdown, "links")

        self.assertIn("<https://example.com>.", repaired)
        self.assertIn("[label](https://target.example.com)", repaired)
        self.assertIn(
            "[https://label.example.com](https://target.example.com)",
            repaired,
        )
        self.assertIn(
            '[label](https://target.example.com "https://title.example.com")',
            repaired,
        )
        self.assertIn("[foo [bar]]: <https://reference.example.com>", repaired)
        self.assertIn(r"[foo\]]: <https://escaped.example.com>", repaired)
        self.assertIn(
            "[outer https://outer.example [inner]](https://target.example.com)",
            repaired,
        )
        self.assertIn(
            'Uri.Parts("http://contoso?a=" & data)&#91;Query][a]',
            repaired,
        )

    def test_preserves_front_matter_and_adds_heading_after_it(self) -> None:
        markdown = "---\ntitle: Example\n---\n\n# Existing\n\nBody\n"

        repaired = self.linter.lint_and_fix(markdown, "fallback")

        self.assertTrue(repaired.startswith("---\ntitle: Example\n---\n\n## Existing\n"))

    def test_preserves_balanced_parentheses_and_indented_code(self) -> None:
        markdown = """# Content

https://en.wikipedia.org/wiki/Python_(programming_language).

`` a ` b https://code.example.com ``

    indented code stays
    with its original spacing
"""

        repaired = self.linter.lint_and_fix(markdown, "content")

        self.assertIn(
            "<https://en.wikipedia.org/wiki/Python_(programming_language)>.",
            repaired,
        )
        self.assertIn("`` a ` b https://code.example.com ``", repaired)
        self.assertIn("    indented code stays\n    with its original spacing", repaired)

    def test_autolinks_www_urls_without_breaking_existing_links(self) -> None:
        markdown = """# Links

Visit www.Example.com.
[site](https://target.example.com)
"""

        repaired = self.linter.lint_and_fix(markdown, "links")

        self.assertIn("<https://www.Example.com>.", repaired)
        self.assertIn("[site](https://target.example.com)", repaired)

    def test_separates_valid_tables_from_paragraphs(self) -> None:
        markdown = """# Tables

Before
| A | B |
| --- | --- |
| 1 | 2 |
After
"""

        repaired = self.linter.lint_and_fix(markdown, "tables")

        self.assertIn("Before\n\n| A | B |", repaired)
        self.assertIn("| 1 | 2 |\n\nAfter", repaired)

    def test_degrades_broken_tables_to_clean_text_blocks(self) -> None:
        markdown = """# Tables

| A | B |
| --- | --- |
| too | many | cells |
"""

        repaired = self.linter.lint_and_fix(markdown, "tables")

        self.assertIn("```text", repaired)
        self.assertIn("| too | many | cells |", repaired)

    def test_degrades_unfixable_table_to_clean_text(self) -> None:
        repaired = self.linter.lint_and_fix("| " + " | ".join(["value"] * 40) + " |")

        self.assertIn("```text", repaired)


if __name__ == "__main__":
    unittest.main()
