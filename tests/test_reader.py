"""Regression tests for Linux EPUB Reader's helpers and EPUB parser."""
import os
import sys
import tempfile
from pathlib import Path
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

    def test_short_chapter_progress_still_runs_from_zero_to_one_hundred(self):
        self.assertEqual(reader.chapter_progress_fraction(0, 10, 20), 0.0)
        self.assertEqual(reader.chapter_progress_fraction(5, 10, 20), 0.5)
        self.assertEqual(reader.chapter_progress_fraction(10, 10, 20), 1.0)

    def test_progress_clamps_invalid_positions(self):
        self.assertEqual(reader.chapter_progress_fraction(-10, 100, 20), 0.0)
        self.assertEqual(reader.chapter_progress_fraction(200, 100, 20), 1.0)

    def test_empty_chapter_is_safe(self):
        self.assertEqual(reader.chapter_progress_fraction(0, 0, 20), 0.0)



class SidebarWidthTests(unittest.TestCase):
    def test_width_fits_longest_label_when_space_is_available(self):
        self.assertEqual(reader.sidebar_width_for_labels(
            [80, 330, 240], available_width=1400,
            minimum_width=250, reading_min_width=520, padding=72,
        ), 402)

    def test_width_is_capped_to_keep_reading_area_visible(self):
        self.assertEqual(reader.sidebar_width_for_labels(
            [1000], available_width=1000,
            minimum_width=250, reading_min_width=520, padding=72,
        ), 480)

    def test_width_keeps_a_minimum_for_empty_contents(self):
        self.assertEqual(reader.sidebar_width_for_labels(
            [], available_width=1200,
            minimum_width=250, reading_min_width=520, padding=72,
        ), 250)

    def test_width_never_grows_without_respect_to_available_space(self):
        result = reader.sidebar_width_for_labels(
            [4000], available_width=900,
            minimum_width=250, reading_min_width=520, padding=72,
        )
        self.assertEqual(result, 380)


class DrmNoticeTests(unittest.TestCase):
    def test_adobe_drm_notice_does_not_offer_an_external_reader(self):
        title, message = reader.drm_notice_for("/books/protected.epub", "Adobe DRM-protected EPUB")
        self.assertEqual(title, "DRM-protected book cannot be opened")
        self.assertIn("cannot read this protection format", message)
        self.assertIn("will not try to launch Adobe Digital Editions", message)
        self.assertIn("will not connect to the internet", message)

    def test_acsm_notice_explains_it_will_not_fulfil_or_launch(self):
        title, message = reader.drm_notice_for("/books/book.acsm", "Adobe DRM download file")
        self.assertEqual(title, "ACSM files cannot be read offline")
        self.assertIn("will not fulfil this file", message)
        self.assertIn("launch another application", message)

    def test_pdf_notice_does_not_launch_another_reader(self):
        title, message = reader.drm_notice_for("/books/document.pdf", "PDF document")
        self.assertEqual(title, "PDF files are not supported")
        self.assertIn("will not launch a PDF reader", message)

    def test_unsupported_file_handling_has_no_external_launch_code(self):
        source_path = Path(reader.__file__)
        source = source_path.read_text(encoding="utf-8")
        for forbidden in ("subprocess.Popen", "subprocess.run", "_offer_external_drm_reader",
                          "find_adobe_digital_editions", 'shutil.which("thorium")'):
            self.assertNotIn(forbidden, source)


class EpubTests(unittest.TestCase):
    def test_application_identity_and_version(self):
        self.assertEqual(reader.APP_NAME, "Linux EPUB Reader")
        self.assertEqual(reader.APP_VERSION, "0.13.2")

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
