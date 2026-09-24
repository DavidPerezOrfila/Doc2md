from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from doc2md.archive_validation import validate_archive
from doc2md.config import AppSettings, executable_path
from doc2md.conversion import DocumentConverter
from doc2md.document_processor import DocumentProcessor
from doc2md.markdown_repair import MarkdownLinter, MarkdownLintError

ROOT = Path(__file__).resolve().parents[1]


def create_settings(root: Path) -> AppSettings:
    return AppSettings(
        input_dir=root / "input",
        output_dir=root / "converted",
        pymarkdown_config=ROOT / ".pymarkdown.json",
        pymarkdown_executable=executable_path(
            "pymarkdown.exe" if sys.platform == "win32" else "pymarkdown"
        ),
    )


def create_processor(settings: AppSettings) -> DocumentProcessor:
    return DocumentProcessor(
        settings,
        DocumentConverter(),
        MarkdownLinter(
            settings.pymarkdown_config,
            settings.pymarkdown_executable,
            max_attempts=2,
        ),
    )


class DocumentProcessorTests(unittest.TestCase):
    def test_processes_clean_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            source = settings.input_dir / "example.txt"
            source.parent.mkdir()
            source.write_text("#  Title\ntext   ", encoding="utf-8")

            result = create_processor(settings).process(source)

            self.assertEqual(result, settings.output_dir / "example.txt.md")
            self.assertIn("# Title", result.read_text(encoding="utf-8"))

    def test_rejects_audio_and_video_external_processing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            source = settings.input_dir / "recording.mp3"
            settings.input_dir.mkdir()
            source.write_bytes(b"not real audio")

            with self.assertRaisesRegex(ValueError, "audio/video"):
                create_processor(settings).process(source)

    def test_rejects_media_content_with_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            source = settings.input_dir / "recording.bin"
            settings.input_dir.mkdir()
            source.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")

            with self.assertRaisesRegex(ValueError, "audio/video"):
                create_processor(settings).process(source)

    def test_rejects_source_outside_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            settings.input_dir.mkdir()
            source = root / "outside.txt"
            source.write_text("private", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "fuera de input"):
                create_processor(settings).process(source)

    def test_rejects_high_ratio_zip_based_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            settings.input_dir.mkdir()

            for suffix in (".zip", ".docx", ".xlsx", ".pptx", ".epub"):
                with self.subTest(suffix=suffix):
                    source = settings.input_dir / f"archive{suffix}"
                    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
                        archive.writestr("large.txt", b"0" * (2 * 1024 * 1024))

                    with self.assertRaisesRegex(ValueError, "compresión"):
                        create_processor(settings).process(source)

    def test_rejects_nested_zip_based_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            source = settings.input_dir / "archive.zip"
            settings.input_dir.mkdir()
            with ZipFile(source, "w", ZIP_DEFLATED) as archive:
                archive.writestr("payload.docx", b"document content")

            with self.assertRaisesRegex(ValueError, "anidados"):
                create_processor(settings).process(source)

    def test_allows_standard_archive_structure_files(self) -> None:
        archive_bytes = BytesIO()
        with ZipFile(archive_bytes, "w") as archive:
            archive.writestr("_rels/.rels", b"relationships")
            archive.writestr("word/_rels/document.xml.rels", b"relationships")
            archive.writestr("mimetype", b"application/epub+zip")
            archive.writestr("content.xml", b"<content/>")

        archive_bytes.seek(0)
        validate_archive(archive_bytes, ".epub", "book.epub")

    def test_rejects_media_member_inside_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            source = settings.input_dir / "archive.zip"
            settings.input_dir.mkdir()
            with ZipFile(source, "w", ZIP_DEFLATED) as archive:
                archive.writestr("recording.txt", b"RIFF\x00\x00\x00\x00WAVEfmt ")

            with self.assertRaisesRegex(ValueError, "audio/video"):
                create_processor(settings).process(source)

    def test_does_not_write_output_when_markdown_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = create_settings(root)
            source = settings.input_dir / "invalid.txt"
            source.parent.mkdir()
            source.write_text("<span>unrepaired html</span>", encoding="utf-8")
            stale_output = settings.output_dir / "invalid.txt.md"
            stale_output.parent.mkdir()
            stale_output.write_text("stale output", encoding="utf-8")

            with self.assertRaisesRegex(MarkdownLintError, "MD033"):
                create_processor(settings).process(source)

            self.assertTrue(stale_output.exists())
            self.assertEqual(stale_output.read_text(encoding="utf-8"), "stale output")
            quarantine = settings.output_dir / ".quarantine"
            self.assertFalse((quarantine / "invalid.txt.md.previous").exists())
            self.assertTrue((quarantine / "invalid.txt.md").exists())
            self.assertTrue((quarantine / "invalid.txt.md.lint-report.txt").exists())


if __name__ == "__main__":
    unittest.main()
