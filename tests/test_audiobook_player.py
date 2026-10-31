"""Tests for the isolated M4B audiobook backend."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import audiobook_player as audio


class AudiobookHelpersTests(unittest.TestCase):
    def test_only_existing_m4b_files_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "Book.M4B")
            Path(path).write_bytes(b"not decoded by this validation test")
            self.assertEqual(audio.normalise_m4b_path(path), path)
            with self.assertRaises(audio.AudiobookError):
                audio.normalise_m4b_path(os.path.join(directory, "book.mp3"))
            with self.assertRaises(audio.AudiobookError):
                audio.normalise_m4b_path(os.path.join(directory, "missing.m4b"))

    def test_non_path_input_is_rejected(self):
        with self.assertRaises(audio.AudiobookError):
            audio.normalise_m4b_path(None)

    def test_time_formatting_handles_hours_and_invalid_values(self):
        self.assertEqual(audio.format_time(0), "0:00")
        self.assertEqual(audio.format_time(65), "1:05")
        self.assertEqual(audio.format_time(3661), "1:01:01")
        self.assertEqual(audio.format_time(-5), "0:00")
        self.assertEqual(audio.format_time("unknown"), "0:00")

    def test_chapter_rows_keep_order_and_supply_missing_titles(self):
        result = audio.chapter_rows([
            {"time": 0, "title": "Opening"},
            {"time": "125.5"},
            {"time": -4, "title": "  Later  "},
            "invalid",
        ])
        self.assertEqual(result, [
            {"index": 0, "title": "Opening", "time": 0.0},
            {"index": 1, "title": "Chapter 2", "time": 125.5},
            {"index": 2, "title": "Later", "time": 0.0},
        ])

    def test_chapter_rows_reject_non_list_input(self):
        self.assertEqual(audio.chapter_rows(None), [])


class BackendCommandTests(unittest.TestCase):
    def make_backend(self):
        backend = audio.MPVBackend(executable="/usr/bin/mpv")
        calls = []
        backend._request = lambda payload: calls.append(payload) or (
            {"request_id": payload.get("request_id"), "error": "success"}
        )
        backend.command = lambda *args: calls.append({"command": list(args)})
        return backend, calls

    def test_seek_is_absolute_and_clamped(self):
        backend, calls = self.make_backend()
        backend.seek(-10)
        self.assertEqual(calls[-1]["command"], ["seek", 0.0, "absolute", "exact"])

    def test_seek_rejects_invalid_value(self):
        backend, _calls = self.make_backend()
        with self.assertRaises(audio.AudiobookError):
            backend.seek("not a time")

    def test_chapter_selection_rejects_negative_index(self):
        backend, _calls = self.make_backend()
        with self.assertRaises(audio.AudiobookError):
            backend.select_chapter(-1)

    def test_chapter_selection_uses_mpv_chapter_property(self):
        backend, calls = self.make_backend()
        backend.select_chapter(3)
        self.assertEqual(calls[-1]["command"], ["set_property", "chapter", 3])


if __name__ == "__main__":
    unittest.main()
