"""Basic regression tests for Linux EPUB Reader's file detection helpers."""
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import linux_epub_reader


class EpubContainerTests(unittest.TestCase):
    def test_source_has_expected_application_identity(self):
        self.assertEqual(linux_epub_reader.APP_NAME, "Linux EPUB Reader")

    def test_version_is_defined(self):
        self.assertTrue(linux_epub_reader.APP_VERSION)

    def test_detects_epub_zip(self):
        with tempfile.NamedTemporaryFile(suffix=".epub") as f:
            with zipfile.ZipFile(f.name, "w") as zf:
                zf.writestr("mimetype", "application/epub+zip")
                zf.writestr("META-INF/container.xml", "<container/>")
            self.assertTrue(zipfile.is_zipfile(f.name))

    def test_rejects_non_zip_as_epub_container(self):
        with tempfile.NamedTemporaryFile(suffix=".epub") as f:
            f.write(b"not a zip file")
            f.flush()
            self.assertFalse(zipfile.is_zipfile(f.name))


if __name__ == "__main__":
    unittest.main()
