from __future__ import annotations

import os
from pathlib import Path

from doc2md.output import write_atomic


def preserve_previous_output(output_path: Path, output_dir: Path, source_name: str) -> Path | None:
    if not output_path.exists():
        return None
    if output_path.is_symlink() or output_path.is_junction():
        raise ValueError(f"La salida ya es un enlace: {output_path.name}")

    quarantine_dir = output_dir / ".quarantine"
    if quarantine_dir.is_symlink() or quarantine_dir.is_junction():
        raise ValueError("El directorio de cuarentena no puede ser un enlace")
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(quarantine_dir, 0o700)
    previous_path = quarantine_dir / f"{source_name}.md.previous"
    if previous_path.is_symlink() or previous_path.is_junction():
        raise ValueError("La copia anterior no puede ser un enlace")
    os.replace(output_path, previous_path)
    return previous_path


def write_quarantine(
    output_dir: Path,
    source_name: str,
    markdown: str,
    diagnostics: str,
) -> tuple[Path, Path]:
    quarantine_dir = output_dir / ".quarantine"
    if quarantine_dir.is_symlink() or quarantine_dir.is_junction():
        raise ValueError("El directorio de cuarentena no puede ser un enlace")
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(quarantine_dir, 0o700)

    markdown_path = quarantine_dir / f"{source_name}.md"
    report_path = quarantine_dir / f"{source_name}.md.lint-report.txt"
    write_atomic(markdown_path, markdown)
    write_atomic(report_path, diagnostics.rstrip() + "\n")
    return markdown_path, report_path
