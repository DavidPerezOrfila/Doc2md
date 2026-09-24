from __future__ import annotations

import logging

from doc2md.config import default_settings
from doc2md.conversion import DocumentConverter
from doc2md.document_processor import DocumentProcessor
from doc2md.markdown_repair import MarkdownLinter
from doc2md.watcher import watch_documents


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    settings = default_settings()
    processor = DocumentProcessor(
        settings,
        DocumentConverter(settings.max_input_bytes),
        MarkdownLinter(
            settings.pymarkdown_config,
            settings.pymarkdown_executable,
            max_attempts=settings.max_attempts,
        ),
    )
    watch_documents(settings, processor)


if __name__ == "__main__":
    main()
