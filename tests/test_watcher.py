from pathlib import Path
import tempfile
import time
import unittest

from watchdog.events import FileCreatedEvent

from doc2md.config import AppSettings
from doc2md.watcher import DocumentEventHandler, PendingJobs, watch_documents

ROOT = Path(__file__).resolve().parents[1]


class WatcherTests(unittest.TestCase):
    def test_created_file_event_is_scheduled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "document.txt"
            source.write_text("content", encoding="utf-8")
            pending_jobs = PendingJobs()
            handler = DocumentEventHandler(pending_jobs, debounce_seconds=1.0)

            handler.on_any_event(FileCreatedEvent(str(source)))

            self.assertIn(source.absolute(), pending_jobs.jobs)

    def test_stops_after_idle_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AppSettings(
                input_dir=root / "input",
                output_dir=root / "converted",
                pymarkdown_config=ROOT / ".pymarkdown.json",
                idle_timeout_seconds=0.05,
            )
            started = time.monotonic()

            watch_documents(settings, processor=object())  # type: ignore[arg-type]

            self.assertLess(time.monotonic() - started, 1.0)

    def test_rejects_same_input_and_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = AppSettings(
                input_dir=root,
                output_dir=root,
                pymarkdown_config=ROOT / ".pymarkdown.json",
            )

            with self.assertRaisesRegex(ValueError, "distinto"):
                watch_documents(settings, processor=object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
