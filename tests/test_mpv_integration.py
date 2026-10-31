"""Optional real mpv integration test using a generated local AAC/M4B fixture."""
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from audiobook_player import MPVBackend


@unittest.skipUnless(shutil.which("mpv") and shutil.which("ffmpeg"),
                     "mpv and ffmpeg are needed for the real playback integration test")
class MPVIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="ler-m4b-test-")
        cls.media_path = str(Path(cls.directory.name) / "integration-test.m4b")
        cls.metadata_path = str(Path(cls.directory.name) / "chapters.ffmeta")
        Path(cls.metadata_path).write_text(
            ";FFMETADATA1\\n"
            "[CHAPTER]\\nTIMEBASE=1/1\\nSTART=0\\nEND=3\\ntitle=Opening\\n"
            "[CHAPTER]\\nTIMEBASE=1/1\\nSTART=3\\nEND=6\\ntitle=Second chapter\\n",
            encoding="utf-8",
        )
        subprocess.run([
            shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-f", "ffmetadata", "-i", cls.metadata_path,
            "-map_metadata", "1", "-map_chapters", "1",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
            cls.media_path,
        ], check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.backend = MPVBackend(audio_output="null", startup_timeout=8)

    def tearDown(self):
        self.backend.close()

    def test_real_m4b_loads_paused_and_supports_seek_play_pause(self):
        result = self.backend.load(self.media_path)
        self.assertGreater(float(result.get("duration") or 0), 5.0)
        self.assertTrue(result.get("paused"))
        self.assertEqual([chapter["title"] for chapter in result["chapters"]],
                         ["Opening", "Second chapter"])
        self.backend.select_chapter(1)
        self.assertEqual(self.backend.status().get("chapter"), 1)
        self.backend.seek(2.0)
        self.assertTrue(self.backend.play_pause())
        time.sleep(0.25)
        self.assertFalse(self.backend.status().get("paused"))
        self.backend.pause()
        self.assertTrue(self.backend.status().get("paused"))
        self.assertGreaterEqual(float(self.backend.status().get("time_pos") or 0), 1.5)
        # Replacing a currently loaded item must not briefly autoplay it.
        replacement = self.backend.load(self.media_path)
        self.assertTrue(replacement.get("paused"))


if __name__ == "__main__":
    unittest.main()
