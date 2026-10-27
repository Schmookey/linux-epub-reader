"""Regression tests for Linux EPUB Reader's non-GUI helpers and EPUB parser."""
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import linux_epub_reader as reader


def make_epub(path):
    files = {
        "META-INF/container.xml": '''<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles></container>''',
        "EPUB/package.opf": '''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">urn:test</dc:identifier><dc:title>Continuous Sample</dc:title></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/><item id="c2" href="c2.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>''',
        "EPUB/nav.xhtml": '''<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol><li><a href="c1.xhtml">Chapter One</a></li><li><a href="c2.xhtml">Chapter Two with a longer heading</a></li></ol></nav></body></html>''',
        "EPUB/c1.xhtml": "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1>Chapter One</h1><p>First chapter content.</p></body></html>",
        "EPUB/c2.xhtml": "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1>Chapter Two</h1><p>Second chapter content.</p></body></html>",
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            archive.writestr(name, data)


class ProgressTests(unittest.TestCase):
    def test_progress_starts_at_zero(self):
        self.assertEqual(reader.chapter_progress_fraction(0, 100, 20), 0.0)

    def test_progress_middle(self):
        self.assertAlmostEqual(reader.chapter_progress_fraction(40, 100, 20), 0.5)

    def test_progress_reaches_one_hundred_at_last_scroll_position(self):
        self.assertEqual(reader.chapter_progress_fraction(80, 100, 20), 1.0)

    def test_chapter_shorter_than_viewport_is_fully_visible(self):
        self.assertEqual(reader.chapter_progress_fraction(0, 10, 20), 1.0)

    def test_progress_clamps_invalid_positions(self):
        self.assertEqual(reader.chapter_progress_fraction(-10, 100, 20), 0.0)
        self.assertEqual(reader.chapter_progress_fraction(200, 100, 20), 1.0)

    def test_empty_chapter_is_safe(self):
        self.assertEqual(reader.chapter_progress_fraction(0, 0, 20), 0.0)


class EpubTests(unittest.TestCase):
    def test_application_identity_and_version(self):
        self.assertEqual(reader.APP_NAME, "Linux EPUB Reader")
        self.assertEqual(reader.APP_VERSION, "0.13.0")

    def test_epub_chapters_keep_reading_order_and_navigation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "test.epub")
            make_epub(path)
            book = reader.EPUBBook(path)
        self.assertEqual(len(book.chapters), 2)
        self.assertIn("First chapter content", book.chapters[0]["text"])
        self.assertIn("Second chapter content", book.chapters[1]["text"])
        self.assertEqual(book.toc[0]["title"], "Chapter One")
        self.assertEqual(book.toc[1]["title"], "Chapter Two with a longer heading")

    def test_corrupt_epub_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "bad.epub")
            with open(path, "wb") as handle:
                handle.write(b"not a zip archive")
            with self.assertRaises(zipfile.BadZipFile):
                reader.EPUBBook(path)


if __name__ == "__main__":
    unittest.main()
