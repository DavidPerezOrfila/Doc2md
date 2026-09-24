from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile

from doc2md.validation import BLOCKED_SUFFIXES, SUPPORTED_DOCUMENT_SUFFIXES, has_media_signature

MAX_ARCHIVE_ENTRIES = 1_000
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
ZIP_BASED_SUFFIXES = {
    ".docx",
    ".epub",
    ".odp",
    ".ods",
    ".odt",
    ".pptx",
    ".xlsx",
    ".zip",
}


def validate_archive(source: BinaryIO, suffix: str, source_name: str) -> None:
    if suffix.lower() not in ZIP_BASED_SUFFIXES:
        return

    source.seek(0)
    try:
        with ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise ValueError(f"El ZIP contiene demasiadas entradas: {source_name}")
            for entry in entries:
                if entry.is_dir():
                    continue
                entry_name = Path(entry.filename).name
                entry_suffix = Path(entry.filename).suffix.lower()
                if entry_suffix in ZIP_BASED_SUFFIXES:
                    raise ValueError(
                        f"No se permiten archivos comprimidos anidados: {source_name}"
                    )
                if entry_suffix in BLOCKED_SUFFIXES:
                    raise ValueError(
                        f"Los archivos de audio/video están bloqueados: {source_name}"
                    )
                if (
                    entry_name not in {".rels", "mimetype"}
                    and entry_suffix not in SUPPORTED_DOCUMENT_SUFFIXES
                    and entry_suffix != ".rels"
                ):
                    raise ValueError(
                        f"Contiene un tipo no compatible: {entry.filename}"
                    )
                with archive.open(entry) as member:
                    if has_media_signature(member):
                        raise ValueError(
                            f"Los archivos de audio/video están bloqueados: {source_name}"
                        )

            expanded_bytes = sum(entry.file_size for entry in entries)
            compressed_bytes = sum(entry.compress_size for entry in entries)
            if expanded_bytes > MAX_EXPANDED_BYTES:
                raise ValueError(f"El ZIP supera el límite expandido: {source_name}")
            if compressed_bytes and expanded_bytes / compressed_bytes > MAX_COMPRESSION_RATIO:
                raise ValueError(
                    f"El ZIP tiene una ratio de compresión insegura: {source_name}"
                )
    except BadZipFile as error:
        raise ValueError(f"El archivo ZIP está dañado: {source_name}") from error
    finally:
        source.seek(0)
