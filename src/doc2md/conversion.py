from __future__ import annotations

import os
import stat
from pathlib import Path

from markitdown import MarkItDown

from doc2md.archive_validation import validate_archive
from doc2md.validation import has_media_signature


class DocumentConverter:
    def __init__(self, max_input_bytes: int = 500 * 1024 * 1024) -> None:
        self.markitdown = MarkItDown(enable_plugins=False)
        self.max_input_bytes = max_input_bytes

    def convert(self, source: Path) -> str:
        source_before_open = source.stat()
        with source.open("rb") as source_file:
            source_after_open = source.lstat()
            opened_file = os.fstat(source_file.fileno())
            if (
                opened_file.st_size > self.max_input_bytes
                or not self._is_same_regular_file(
                    source,
                    source_before_open,
                    source_after_open,
                    opened_file,
                )
            ):
                raise ValueError(f"El archivo cambió o excede el límite: {source.name}")
            if has_media_signature(source_file):
                raise ValueError(f"Los archivos de audio/video están bloqueados: {source.name}")
            validate_archive(source_file, source.suffix, source.name)
            markdown = self.markitdown.convert_stream(
                source_file,
                file_extension=source.suffix,
            ).markdown
            source_after_conversion = os.fstat(source_file.fileno())
            if (
                source_after_conversion.st_size != opened_file.st_size
                or source_after_conversion.st_mtime != opened_file.st_mtime
            ):
                raise ValueError(f"El archivo cambió durante la conversión: {source.name}")
            return markdown

    @staticmethod
    def _is_same_regular_file(
        source: Path,
        before_open: os.stat_result,
        after_open: os.stat_result,
        opened_file: os.stat_result,
    ) -> bool:
        opened_identity = (opened_file.st_dev, opened_file.st_ino)
        return (
            not source.is_symlink()
            and stat.S_ISREG(opened_file.st_mode)
            and (before_open.st_dev, before_open.st_ino) == opened_identity
            and (after_open.st_dev, after_open.st_ino) == opened_identity
        )
