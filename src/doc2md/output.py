from __future__ import annotations

import os
import tempfile
from pathlib import Path

from doc2md.limits import MAX_MARKDOWN_BYTES


def write_atomic(
    path: Path,
    content: str | bytes,
    max_bytes: int = MAX_MARKDOWN_BYTES,
) -> None:
    if path.parent.is_symlink() or path.parent.is_junction():
        raise ValueError(f"El directorio padre no puede ser un enlace: {path.parent.name}")
    if path.is_symlink():
        raise ValueError(f"La salida ya es un enlace: {path.name}")

    data = content.encode("utf-8") if isinstance(content, str) else content
    if len(data) > max_bytes:
        raise ValueError(f"El contenido de {path.name} supera el límite de 16 MiB")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(data)
            temporary_file.flush()
            temporary_path = Path(temporary_file.name)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
