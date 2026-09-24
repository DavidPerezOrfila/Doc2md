from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

BLOCKED_SUFFIXES = {
    ".aac",
    ".avi",
    ".flac",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".ogg",
    ".wav",
    ".webm",
    ".wma",
}
SUPPORTED_DOCUMENT_SUFFIXES = {
    ".bmp",
    ".csv",
    ".docx",
    ".epub",
    ".gif",
    ".htm",
    ".html",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".markdown",
    ".msg",
    ".pdf",
    ".png",
    ".pptx",
    ".rtf",
    ".tif",
    ".tiff",
    ".txt",
    ".webp",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}


def has_media_signature(stream: BinaryIO) -> bool:
    position = stream.tell()
    header = stream.read(16)
    stream.seek(position)
    return (
        header.startswith(
            (
                b"OggS",
                b"fLaC",
                b"ID3",
                b"\x1a\x45\xdf\xa3",
                b"\x00\x00\x01\xba",
                b"\x00\x00\x01\xb3",
                b"\x30\x26\xb2\x75",
            )
        )
        or (header.startswith(b"RIFF") and header[8:12] in {b"WAVE", b"AVI "})
        or (
            not header.startswith(b"\xff\xfe")
            and len(header) >= 2
            and header[0] == 0xFF
            and (header[1] & 0xE0) == 0xE0
        )
        or header[4:8] == b"ftyp"
        or (header.startswith(b"FORM") and header[8:12] in {b"AIFF", b"AIFC"})
    )


def is_ignored(path: Path) -> bool:
    return path.name.startswith((".", "~$"))


def validate_source(
    source: Path,
    input_root: Path,
    max_input_bytes: int,
) -> Path:
    if source.is_symlink() or source.is_junction():
        raise ValueError(f"No se permiten enlaces: {source.name}")

    resolved = source.resolve(strict=True)
    suffix = resolved.suffix.lower()
    if suffix in BLOCKED_SUFFIXES:
        raise ValueError(f"Los archivos de audio/video están bloqueados: {source.name}")
    if suffix not in SUPPORTED_DOCUMENT_SUFFIXES:
        with resolved.open("rb") as source_file:
            if has_media_signature(source_file):
                raise ValueError(f"Los archivos de audio/video están bloqueados: {source.name}")
        raise ValueError(f"Extensión de documento no compatible: {source.name}")
    if not resolved.is_file():
        raise ValueError(f"No es un archivo local válido: {source}")
    if not resolved.is_relative_to(input_root.resolve()):
        raise ValueError(f"El archivo está fuera de input: {source}")
    if resolved.stat().st_size > max_input_bytes:
        raise ValueError(f"El archivo supera el límite permitido: {source.name}")
    return resolved


def validate_output_directory(output_dir: Path) -> Path:
    if output_dir.is_symlink() or output_dir.is_junction():
        raise ValueError("El directorio de salida no puede ser un enlace")
    resolved = output_dir.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved
