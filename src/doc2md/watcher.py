from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from doc2md.config import AppSettings
from doc2md.document_processor import DocumentProcessor
from doc2md.markdown_repair import MarkdownLintError
from doc2md.validation import is_ignored

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversionJob:
    deadline: float
    size: int
    modified_at: float
    attempts: int = 0


@dataclass
class PendingJobs:
    jobs: dict[Path, ConversionJob] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)
    last_activity: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        with self.lock:
            self.last_activity = time.monotonic()

    def state(self) -> tuple[dict[Path, ConversionJob], float]:
        with self.lock:
            return dict(self.jobs), self.last_activity


class DocumentEventHandler(FileSystemEventHandler):
    def __init__(self, pending_jobs: PendingJobs, debounce_seconds: float) -> None:
        super().__init__()
        self.pending_jobs = pending_jobs
        self.debounce_seconds = debounce_seconds

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or event.event_type not in {"created", "modified", "moved"}:
            return
        paths = [Path(event.src_path)]
        destination = getattr(event, "dest_path", None)
        if destination:
            paths.append(Path(destination))
        self.schedule(paths, self.debounce_seconds)

    def schedule(self, paths: list[Path], delay: float) -> None:
        for path in paths:
            absolute = path.absolute()
            if absolute.is_file() and not is_ignored(path):
                stats = absolute.stat()
                with self.pending_jobs.lock:
                    self.pending_jobs.last_activity = time.monotonic()
                    self.pending_jobs.jobs[absolute] = ConversionJob(
                        deadline=time.monotonic() + delay,
                        size=stats.st_size,
                        modified_at=stats.st_mtime,
                    )


def watch_documents(settings: AppSettings, processor: DocumentProcessor) -> None:
    input_root = settings.input_dir.resolve()
    output_root = settings.output_dir.resolve()
    if input_root == output_root:
        raise ValueError("El directorio de salida debe ser distinto de input")
    if settings.input_dir.is_symlink() or settings.input_dir.is_junction():
        raise ValueError("El directorio de entrada no puede ser un enlace")

    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    pending_jobs = PendingJobs()
    handler = DocumentEventHandler(pending_jobs, settings.debounce_seconds)
    observer = Observer()
    observer.schedule(handler, str(input_root), recursive=False)
    handler.schedule(
        [path for path in input_root.iterdir() if path.is_file()],
        settings.debounce_seconds,
    )
    observer.start()
    LOGGER.info("Vigilando %s", input_root)

    try:
        while True:
            time.sleep(0.25)
            now = time.monotonic()
            with pending_jobs.lock:
                ready = [
                    (path, pending_jobs.jobs.pop(path))
                    for path, job in list(pending_jobs.jobs.items())
                    if job.deadline <= now
                ]
            for path, job in ready:
                process_job(
                    path,
                    job,
                    pending_jobs,
                    processor,
                    settings,
                )
            if ready:
                pending_jobs.touch()
            queued_jobs, last_activity = pending_jobs.state()
            if (
                not queued_jobs
                and now - last_activity >= settings.idle_timeout_seconds
            ):
                LOGGER.info(
                    "Sin actividad durante %.0f segundos; cerrando",
                    settings.idle_timeout_seconds,
                )
                break
    except KeyboardInterrupt:
        LOGGER.info("Conversión detenida")
    finally:
        observer.stop()
        observer.join()


def process_job(
    path: Path,
    job: ConversionJob,
    pending_jobs: PendingJobs,
    processor: DocumentProcessor,
    settings: AppSettings,
) -> None:
    try:
        source = path
        stats = source.stat()
        if (stats.st_size, stats.st_mtime) != (job.size, job.modified_at):
            reschedule(path, job, pending_jobs, settings.debounce_seconds, settings)
            return

        output_path = processor.process(source)
        LOGGER.info("Convertido: %s -> %s", source.name, output_path.name)
    except (FileNotFoundError, PermissionError, OSError):
        if job.attempts + 1 < settings.max_attempts:
            LOGGER.warning("Archivo ocupado; reintentando: %s", path.name)
            reschedule(path, job, pending_jobs, settings.retry_seconds, settings)
        else:
            LOGGER.error("No se pudo convertir tras varios intentos: %s", path.name)
    except MarkdownLintError as error:
        LOGGER.error(
            "Markdown aislado por warnings en converted/.quarantine: %s\n%s",
            path.name,
            error,
        )
    except Exception:
        LOGGER.exception("No se pudo convertir: %s", path.name)


def reschedule(
    path: Path,
    job: ConversionJob,
    pending_jobs: PendingJobs,
    delay: float,
    settings: AppSettings,
) -> None:
    try:
        stats = path.stat()
    except OSError:
        return
    with pending_jobs.lock:
        pending_jobs.last_activity = time.monotonic()
        pending_jobs.jobs[path] = ConversionJob(
            deadline=time.monotonic() + delay,
            size=stats.st_size,
            modified_at=stats.st_mtime,
            attempts=job.attempts + 1,
        )
