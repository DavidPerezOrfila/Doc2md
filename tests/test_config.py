from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from doc2md.config import BUNDLED_PYMARKDOWN_CONFIG, default_settings


class DefaultSettingsTests(unittest.TestCase):
    def test_uses_bundled_config_when_local_override_is_absent(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("doc2md.config.Path.cwd", return_value=Path(temp_dir)),
        ):
            settings = default_settings()

        self.assertEqual(settings.pymarkdown_config, BUNDLED_PYMARKDOWN_CONFIG)

    def test_ignores_untrusted_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".pymarkdown.json").write_text("{}", encoding="utf-8")
            with patch("doc2md.config.Path.cwd", return_value=root):
                settings = default_settings()

        self.assertEqual(settings.pymarkdown_config, BUNDLED_PYMARKDOWN_CONFIG)
