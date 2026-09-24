from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

def executable_path(name: str) -> Path:
    directory = Path(sys.executable).parent
    expected_directory = "Scripts" if sys.platform == "win32" else "bin"
    if directory.name.lower() != expected_directory.lower():
        directory = directory / expected_directory
    return directory / name


BUNDLED_PYMARKDOWN_CONFIG = Path(__file__).with_name("pymarkdown.json")
PYMARKDOWN_EXECUTABLE = executable_path(
    "pymarkdown.exe" if sys.platform == "win32" else "pymarkdown"
)


@dataclass(frozen=True)
class AppSettings:
    input_dir: Path
    output_dir: Path
    pymarkdown_config: Path
    pymarkdown_executable: Path = PYMARKDOWN_EXECUTABLE
    debounce_seconds: float = 1.0
    retry_seconds: float = 10.0
    max_attempts: int = 5
    max_input_bytes: int = 500 * 1024 * 1024
    idle_timeout_seconds: float = 30.0


def default_settings() -> AppSettings:
    project_root = Path.cwd()
    local_config = project_root / ".pymarkdown.json"
    return AppSettings(
        input_dir=project_root / "input",
        output_dir=project_root / "converted",
        pymarkdown_config=local_config if local_config.exists() else BUNDLED_PYMARKDOWN_CONFIG,
    )
