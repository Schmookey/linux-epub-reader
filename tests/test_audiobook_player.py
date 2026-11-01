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

    def test_extract_cover_art_reads_embedded_jpeg_from_mp4_covr_atom(self):
        def atom(kind, payload):
            return (len(payload) + 8).to_bytes(4, "big") + kind + payload

        jpeg = bytes.fromhex("ffd8ff") + b"mock-jpeg-data"
        data = atom(b"data", (13).to_bytes(4, "big") + bytes(4) + jpeg)
        covr = atom(b"covr", data)
        ilst = atom(b"ilst", covr)
        meta = atom(b"meta", bytes(4) + ilst)
        udta = atom(b"udta", meta)
        moov = atom(b"moov", udta)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cover.m4b")
            Path(path).write_bytes(moov)
            self.assertEqual(audio.extract_cover_art(path), jpeg)

    def test_extract_cover_art_returns_none_for_missing_or_invalid_art(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "empty.m4b")
            Path(path).write_bytes(b"not an mp4")
            self.assertIsNone(audio.extract_cover_art(path))


class IPCProtocolTests(unittest.TestCase):
    def test_persistent_connection_ignores_events_and_matches_command_replies(self):
        import json
        import socket
        import threading

        with tempfile.TemporaryDirectory() as directory:
            socket_path = os.path.join(directory, "mpv.sock")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(socket_path)
            server.listen(1)
            received = []

            def serve():
                connection, _ = server.accept()
                with connection:
                    stream = connection.makefile("rb")
                    for _ in range(2):
                        request = json.loads(stream.readline().decode("utf-8"))
                        received.append(request)
                        connection.sendall(
                            (json.dumps({"event": "property-change", "name": "pause"}) + "\n").encode()
                        )
                        connection.sendall(
                            (json.dumps({
                                "request_id": request["request_id"],
                                "error": "success",
                                "data": request["request_id"],
                            }) + "\n").encode()
                        )
                server.close()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            backend = audio.MPVBackend(command_timeout=2)
            backend._socket_path = socket_path
            try:
                self.assertEqual(backend.command("get_property", "pause"), 1)
                self.assertEqual(backend.command("get_property", "duration"), 2)
            finally:
                backend._disconnect_ipc()
                thread.join(timeout=2)
            self.assertEqual(len(received), 2)
            self.assertEqual(received[0]["command"], ["get_property", "pause"])
            self.assertEqual(received[1]["command"], ["get_property", "duration"])


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

    def test_volume_mute_and_speed_controls_use_mpv_properties(self):
        backend, calls = self.make_backend()
        backend.set_volume(65)
        backend.set_mute(True)
        backend.set_speed(1.25)
        self.assertEqual(calls[-3]["command"], ["set_property", "volume", 65.0])
        self.assertEqual(calls[-2]["command"], ["set_property", "mute", True])
        self.assertEqual(calls[-1]["command"], ["set_property", "speed", 1.25])


class AudioWorkerTests(unittest.TestCase):
    def test_all_backend_calls_are_owned_by_one_worker_thread(self):
        import queue
        import threading
        import time

        calls = []
        call_threads = []
        backend_thread = []

        class FakeBackend:
            def __init__(self):
                backend_thread.append(threading.get_ident())

            def _record(self, name, *args):
                calls.append((name, args))
                call_threads.append(threading.get_ident())

            def load(self, path):
                self._record("load", path)
                return {"duration": 10.0, "paused": True}

            def status(self, include_details=True):
                self._record("status", include_details)
                return {
                    "duration": 10.0, "time_pos": 0.0, "paused": True,
                    "chapter": 0, "chapters": [], "volume": 70.0,
                    "mute": False, "speed": 1.0, "metadata": {},
                }

            def play(self): self._record("play")
            def pause(self): self._record("pause")
            def set_volume(self, value): self._record("volume", value)
            def set_mute(self, value): self._record("mute", value)
            def set_speed(self, value): self._record("speed", value)
            def seek(self, value): self._record("seek", value)
            def select_chapter(self, value): self._record("chapter", value)
            def close(self): self._record("close")

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "worker-test.m4b")
            Path(path).write_bytes(b"test")
            worker = audio.AudioWorker(
                backend_factory=FakeBackend, poll_interval=30
            )
            try:
                worker.submit("open", 4, path, 0.0, None)
                loaded = worker.events.get(timeout=3)
                self.assertEqual(loaded["type"], "loaded")
                self.assertEqual(loaded["token"], 4)

                for action, args in [
                    ("play", ()), ("pause", ()), ("volume", (55,)),
                    ("mute", (True,)), ("speed", (1.25,)),
                    ("seek", (8,)), ("chapter", (1,)), ("stop", ()),
                ]:
                    worker.submit(action, 4, *args)

                observed = set()
                deadline = time.monotonic() + 3
                while len(observed) < 8 and time.monotonic() < deadline:
                    event = worker.events.get(timeout=max(0.05, deadline-time.monotonic()))
                    if event["type"] == "status":
                        # Each completed command publishes a status snapshot.
                        observed.add(len(observed))
                self.assertEqual(len(observed), 8)
            finally:
                worker.shutdown()
                worker.join(timeout=3)
            self.assertFalse(worker.is_alive)
            self.assertTrue(call_threads)
            self.assertEqual(set(call_threads), {backend_thread[0]})
            self.assertEqual(
                [name for name, _args in calls if name != "status"],
                ["load", "volume", "speed", "play", "pause", "volume",
                 "mute", "speed", "seek", "chapter", "seek", "pause", "close"],
            )

    def test_open_error_is_reported_without_stopping_worker(self):
        import threading

        class BrokenBackend:
            def load(self, _path):
                raise audio.AudiobookError("test load failure")
            def diagnostics(self):
                return "mock MPV decoder diagnostic"
            def close(self):
                pass

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "broken.m4b")
            Path(path).write_bytes(b"test")
            worker = audio.AudioWorker(
                backend_factory=BrokenBackend, poll_interval=30
            )
            try:
                worker.submit("open", 9, path, 0.0, None)
                event = worker.events.get(timeout=3)
                self.assertEqual(event["type"], "error")
                self.assertEqual(event["action"], "open")
                self.assertIn("test load failure", event["error"])
                self.assertIn("mock MPV decoder diagnostic", event["error"])
                self.assertTrue(worker.is_alive)
            finally:
                worker.shutdown()
                worker.join(timeout=3)
            self.assertFalse(worker.is_alive)


if __name__ == "__main__":
    unittest.main()
