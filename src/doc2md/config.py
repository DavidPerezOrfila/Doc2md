from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from doc2md.limits import MAX_INPUT_BYTES


BUNDLED_PYMARKDOWN_CONFIG = Path(__file__).with_name("pymarkdown.json")


@dataclass(frozen=True)
class AppSettings:
    input_dir: Path
    output_dir: Path
    pymarkdown_config: Path
    debounce_seconds: float = 1.0
    retry_seconds: float = 10.0
    max_attempts: int = 5
    max_input_bytes: int = MAX_INPUT_BYTES
    idle_timeout_seconds: float = 30.0


def default_settings() -> AppSettings:
    project_root = Path.cwd()
    return AppSettings(
        input_dir=project_root / "input",
        output_dir=project_root / "converted",
        pymarkdown_config=BUNDLED_PYMARKDOWN_CONFIG,
    )
