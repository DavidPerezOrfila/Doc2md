from __future__ import annotations

from pathlib import Path

from doc2md.config import AppSettings
from doc2md.conversion import DocumentConverter
from doc2md.markdown_repair import MarkdownLinter, MarkdownLintError
from doc2md.output import write_atomic
from doc2md.quarantine import preserve_previous_output, write_quarantine
from doc2md.validation import validate_output_directory, validate_source


class DocumentProcessor:
    def __init__(
        self,
        settings: AppSettings,
        converter: DocumentConverter,
        linter: MarkdownLinter,
    ) -> None:
        self.settings = settings
        self.converter = converter
        self.linter = linter

    def process(self, source: Path) -> Path:
        source = validate_source(
            source,
            self.settings.input_dir,
            self.settings.max_input_bytes,
        )
        output_dir = validate_output_directory(self.settings.output_dir)
        output_path = output_dir / f"{source.name}.md"
        previous_output = preserve_previous_output(output_path, output_dir, source.name)

        try:
            markdown = self.converter.convert(source)
            try:
                clean_markdown = self.linter.lint_and_fix(markdown, source.stem)
            except MarkdownLintError as error:
                write_quarantine(
                    output_dir,
                    source.name,
                    error.markdown,
                    error.diagnostics,
                )
                raise
            write_atomic(output_path, clean_markdown)
        except BaseException:
            if previous_output is not None and not output_path.exists():
                previous_output.replace(output_path)
            raise
        else:
            if previous_output is not None:
                previous_output.unlink(missing_ok=True)
            return output_path
