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


class CoverAndWelcomePanelDataTests(unittest.TestCase):
    def test_epub3_cover_image_is_extracted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cover.epub")
            cover = bytes.fromhex(
                "89504e470d0a1a0a0000000d494844520000000100000001"
                "08060000001f15c4890000000b49444154789c636000020000"
                "050001a5f645400000000049454e44ae426082"
            )
            files = {
                "META-INF/container.xml": '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf"/></rootfiles></container>',
                "EPUB/package.opf": '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Cover Test</dc:title><dc:creator>Test Author</dc:creator></metadata><manifest><item id="cover" href="images/front%20cover.png" media-type="image/png" properties="cover-image"/><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="chapter"/></spine></package>',
                "EPUB/images/front cover.png": cover,
                "EPUB/chapter.xhtml": "<html xmlns='http://www.w3.org/1999/xhtml'><body><h1>Chapter One</h1><p>Cover test text.</p></body></html>",
            }
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
                for name, data in files.items():
                    archive.writestr(name, data)
            book = reader.EPUBBook(path)
            self.assertEqual(book.cover_name, "front cover.png")
            self.assertEqual(book.cover_bytes, cover)
            self.assertEqual(book.author, "Test Author")

    def test_saved_book_summary_reports_chapter_and_overall_progress(self):
        class Book:
            chapters = [
                {"title": "First", "words": 100},
                {"title": "Second", "words": 300},
            ]
        path = "/books/sample.epub"
        state = {
            "books": {
                reader.book_state_key(path): {
                    "chapter": 1,
                    "fraction": 0.5,
                }
            }
        }
        summary = reader.saved_book_summary(state, path, Book())
        self.assertEqual(summary["chapter_number"], 2)
        self.assertEqual(summary["chapter_count"], 2)
        self.assertEqual(summary["chapter_title"], "Second")
        self.assertEqual(summary["chapter_percent"], 50)
        self.assertEqual(summary["overall_percent"], 63)


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



class FullscreenHintTests(unittest.TestCase):
    def test_hint_is_shown_on_first_fullscreen_entry(self):
        self.assertTrue(reader.fullscreen_hint_should_show({}, True))
        self.assertTrue(reader.fullscreen_hint_should_show({"hide_fullscreen_hint": False}, True))

    def test_hint_is_not_shown_outside_fullscreen(self):
        self.assertFalse(reader.fullscreen_hint_should_show({}, False))

    def test_hint_stays_hidden_after_saved_opt_out(self):
        saved_state = {"hide_fullscreen_hint": True}
        self.assertFalse(reader.fullscreen_hint_should_show(saved_state, True))

    def test_hint_can_be_restored_by_clearing_saved_opt_out(self):
        saved_state = {"hide_fullscreen_hint": True}
        saved_state["hide_fullscreen_hint"] = False
        self.assertTrue(reader.fullscreen_hint_should_show(saved_state, True))


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


class WelcomePageTests(unittest.TestCase):
    def test_welcome_explains_features_local_storage_and_offline_privacy(self):
        self.assertIn("Welcome to Linux EPUB Reader", reader.WELCOME_TEXT)
        self.assertIn("reading_state.json", reader.WELCOME_TEXT)
        self.assertIn("There are no accounts, cloud services, analytics or reading-history uploads", reader.WELCOME_TEXT)
        self.assertIn("not a blanket legal certification of GDPR compliance", reader.WELCOME_TEXT)


class FullscreenLayoutTests(unittest.TestCase):
    def test_fullscreen_has_zero_sidebar_column_when_contents_was_open(self):
        self.assertEqual(reader.sidebar_column_minimum(True, True, 340), 0)

    def test_fullscreen_has_zero_sidebar_column_when_contents_was_closed(self):
        self.assertEqual(reader.sidebar_column_minimum(False, True, 340), 0)

    def test_normal_window_restores_column_only_when_contents_is_visible(self):
        self.assertEqual(reader.sidebar_column_minimum(True, False, 340), 340)
        self.assertEqual(reader.sidebar_column_minimum(False, False, 340), 0)

    def test_fullscreen_entry_recalculates_sidebar_column_minimum(self):
        source = Path(reader.__file__).read_text(encoding="utf-8")
        start = source.index("    def toggle_fullscreen(self):")
        end = source.index("    def _update_fullscreen_hint(self):", start)
        self.assertIn("self._ensure_toc_left()", source[start:end])

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


class ResumeLastBookTests(unittest.TestCase):
    def test_explicit_last_book_path_and_title_are_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "book.epub")
            state = {"last_opened_book": path, "last_opened_title": "My Book"}
            self.assertEqual(
                reader.last_opened_book_info(state),
                (os.path.abspath(path), "My Book", False),
            )

    def test_legacy_state_uses_last_inserted_book_as_a_suggestion(self):
        with tempfile.TemporaryDirectory() as directory:
            first = os.path.join(directory, "first.epub")
            second = os.path.join(directory, "second.epub")
            state = {"books": {
                "first": {"path": first, "chapter": 1, "fraction": 0.2},
                "second": {"path": second, "chapter": 3, "fraction": 0.7},
            }}
            self.assertEqual(
                reader.last_opened_book_info(state),
                (os.path.abspath(second), "second.epub", True),
            )

    def test_empty_state_has_no_resume_target(self):
        self.assertEqual(reader.last_opened_book_info({"books": {}}), ("", "", False))

    def test_remember_last_opened_book_stores_only_path_and_title(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "book.epub")
            state = {"books": {}}
            reader.remember_last_opened_book(state, path, "Book Title")
            self.assertEqual(state["last_opened_book"], os.path.abspath(path))
            self.assertEqual(state["last_opened_title"], "Book Title")
            self.assertEqual(set(state), {"books", "last_opened_book", "last_opened_title"})

    def test_moved_book_receives_saved_position_and_bookmarks(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = os.path.join(directory, "old", "book.epub")
            new_path = os.path.join(directory, "new", "book.epub")
            old_key = reader.book_state_key(old_path)
            new_key = reader.book_state_key(new_path)
            state = {"books": {
                old_key: {"path": old_path, "chapter": 4, "fraction": 0.63,
                          "bookmarks": [{"label": "Important", "chapter": 2, "fraction": 0.4}]}
            }}
            self.assertTrue(reader.restore_book_state_for_moved_file(state, old_path, new_path))
            self.assertEqual(state["books"][new_key]["chapter"], 4)
            self.assertEqual(state["books"][new_key]["fraction"], 0.63)
            self.assertEqual(state["books"][new_key]["bookmarks"][0]["label"], "Important")
            self.assertEqual(state["books"][new_key]["path"], os.path.abspath(new_path))
            self.assertIn(old_key, state["books"])

    def test_existing_destination_state_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = os.path.join(directory, "old.epub")
            new_path = os.path.join(directory, "new.epub")
            old_key = reader.book_state_key(old_path)
            new_key = reader.book_state_key(new_path)
            state = {"books": {
                old_key: {"path": old_path, "chapter": 4, "fraction": 0.63, "bookmarks": []},
                new_key: {"path": new_path, "chapter": 1, "fraction": 0.1, "bookmarks": []},
            }}
            self.assertFalse(reader.restore_book_state_for_moved_file(state, old_path, new_path))
            self.assertEqual(state["books"][new_key]["chapter"], 1)

    def test_welcome_message_explains_resume_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "book.epub")
            state = {"last_opened_book": path, "last_opened_title": "My Book"}
            missing_message = reader.welcome_text_for_last_book(state)
            self.assertIn("\n\n", missing_message)
            self.assertIn("Locate last book", missing_message)
            self.assertNotIn("\\n", missing_message)
            with open(path, "wb") as handle:
                handle.write(b"test")
            existing_message = reader.welcome_text_for_last_book(state)
            self.assertIn("Resume last book", existing_message)
            self.assertIn("\n\n", existing_message)
            self.assertNotIn("\\n", existing_message)


class EpubTests(unittest.TestCase):
    def test_application_identity_and_version(self):
        self.assertEqual(reader.APP_NAME, "Linux EPUB Reader")
        self.assertEqual(reader.APP_VERSION, "0.13.9")

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
