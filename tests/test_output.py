from pathlib import Path
import tempfile
import unittest

from doc2md.output import write_atomic


class AtomicOutputTests(unittest.TestCase):
    def test_writes_utf8_bytes_without_newline_translation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "document.md"

            write_atomic(path, "línea\n")

            self.assertEqual(path.read_bytes(), "línea\n".encode("utf-8"))

    def test_rejects_oversized_content_before_replacing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "document.md"
            path.write_text("previous", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "16 MiB"):
                write_atomic(path, "12345", max_bytes=4)

            self.assertEqual(path.read_text(encoding="utf-8"), "previous")


if __name__ == "__main__":
    unittest.main()
