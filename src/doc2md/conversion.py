from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from markitdown import MarkItDown
from markitdown.converters import (
    CsvConverter,
    DocxConverter,
    EpubConverter,
    HtmlConverter,
    ImageConverter,
    OutlookMsgConverter,
    PdfConverter,
    PlainTextConverter,
    PptxConverter,
    XlsConverter,
    XlsxConverter,
    ZipConverter,
)

from doc2md.archive_validation import validate_archive
from doc2md.limits import MAX_INPUT_BYTES, MAX_MARKDOWN_BYTES
from doc2md.process_worker import run_bounded
from doc2md.validation import has_media_signature


CONVERSION_TIMEOUT_SECONDS = 120


def _create_markitdown() -> MarkItDown:
    # Solo convertidores locales: AudioConverter sube audio a Google y los
    # conectores web (YouTube, Bing, Wikipedia) podrían salir de la máquina.
    markitdown = MarkItDown(enable_builtins=False, enable_plugins=False)
    markitdown.register_converter(PlainTextConverter())
    markitdown.register_converter(ZipConverter(markitdown=markitdown))
    markitdown.register_converter(HtmlConverter())
    for converter in (
        DocxConverter(),
        XlsxConverter(),
        XlsConverter(),
        PptxConverter(),
        ImageConverter(),
        PdfConverter(),
        OutlookMsgConverter(),
        EpubConverter(),
        CsvConverter(),
    ):
        markitdown.register_converter(converter)
    return markitdown


class DocumentConverter:
    def __init__(self, max_input_bytes: int = MAX_INPUT_BYTES) -> None:
        self.max_input_bytes = max_input_bytes

    def convert(self, source: Path) -> str:
        source = source.absolute()
        if source.stat().st_size > self.max_input_bytes:
            raise ValueError(f"El archivo cambió o excede el límite: {source.name}")
        return run_bounded(
            _convert_document,
            (source, self.max_input_bytes),
            timeout_seconds=CONVERSION_TIMEOUT_SECONDS,
            max_result_bytes=MAX_MARKDOWN_BYTES,
        )


def _convert_document(result_path: Path, source: Path, max_input_bytes: int) -> None:
    work_dir = result_path.parent
    original_directory = Path.cwd()
    os.chdir(work_dir)
    tempfile.tempdir = str(work_dir)
    try:
        source_before_open = source.stat()
        with source.open("rb") as source_file:
            source_after_open = source.lstat()
            opened_file = os.fstat(source_file.fileno())
            if (
                opened_file.st_size > max_input_bytes
                or not _is_same_regular_file(
                    source,
                    source_before_open,
                    source_after_open,
                    opened_file,
                )
            ):
                raise ValueError(f"El archivo cambió o excede el límite: {source.name}")
            if has_media_signature(source_file):
                raise ValueError(
                    f"Los archivos de audio/video están bloqueados: {source.name}"
                )
            validate_archive(source_file, source.suffix, source.name)
            markdown = (
                _create_markitdown()
                .convert_stream(
                    source_file,
                    file_extension=source.suffix,
                    exiftool_path="",
                )
                .markdown
            )
            source_after_conversion = os.fstat(source_file.fileno())
            if (
                source_after_conversion.st_size != opened_file.st_size
                or source_after_conversion.st_mtime != opened_file.st_mtime
            ):
                raise ValueError(
                    f"El archivo cambió durante la conversión: {source.name}"
                )
            markdown_bytes = markdown.encode("utf-8")
            if len(markdown_bytes) > MAX_MARKDOWN_BYTES:
                raise ValueError("El Markdown convertido supera el límite de 16 MiB")
            result_path.write_bytes(markdown_bytes)
    finally:
        os.chdir(original_directory)


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
