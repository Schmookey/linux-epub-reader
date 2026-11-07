"""Offline music-mode regressions. Run with python3 -m unittest discover -s tests."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from music_player import (MUSIC_EXTENSIONS, MusicError, MusicLibrary, MusicBackend,
                          MusicWorker, load_music_state, normalise_music_path,
                          save_music_state, scan_music_folder, track_info,
                          safe_playlist_name)


class MusicFormatTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='ler-music-test-')
        self.root = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def fixture(self, name):
        path = self.root / name
        path.write_bytes(b'fixture')
        return str(path)

    def test_common_open_formats(self):
        for name in ('track.mp3', 'album.flac', 'song.OGG', 'mix.opus',
                     'song.wav', 'song.aiff', 'song.m4a', 'song.mp4',
                     'track.ape', 'track.wv', 'track.wma', 'track.caf'):
            with self.subTest(name=name):
                self.assertEqual(normalise_music_path(self.fixture(name)),
                                 str(self.root / name))

    def test_m4b_rejected_in_music_including_uppercase(self):
        for name in ('book.m4b', 'BOOK.M4B'):
            with self.subTest(name=name), self.assertRaisesRegex(MusicError, 'Audiobook'):
                normalise_music_path(self.fixture(name))

    def test_no_drmed_or_network_urls(self):
        for source in ('https://example.org/song.flac', 'http://localhost/track.mp3',
                       'file:///tmp/song.mp3', 'ftp://example.net/a.opus'):
            with self.subTest(source=source), self.assertRaises(MusicError):
                normalise_music_path(source)
        for name in ('protected.m4p', 'protected.aax', 'protected.aa'):
            with self.subTest(name=name), self.assertRaises(MusicError):
                normalise_music_path(self.fixture(name))

    def test_invalid_extension_missing_file_and_nonpath(self):
        for path in (str(self.root / 'not-found.flac'), self.fixture('text.txt'), None):
            with self.assertRaises(MusicError):
                normalise_music_path(path)

    def test_folder_scan_no_symlink_follow_or_m4b(self):
        album = self.root / 'Album'
        album.mkdir()
        (album / '1.flac').write_bytes(b'one')
        (album / '2.mp3').write_bytes(b'two')
        (album / 'book.m4b').write_bytes(b'book')
        (self.root / 'outside-link').symlink_to(album, target_is_directory=True)
        results = scan_music_folder(self.root)
        self.assertEqual(set(results), {str(album / '1.flac'), str(album / '2.mp3')})
        self.assertEqual(scan_music_folder(self.root, limit=1).__len__(), 1)

    def test_untagged_track_fallback(self):
        track = track_info(self.fixture('Untitled.flac'))
        self.assertEqual(track['title'], 'Untitled')
        self.assertEqual(track['artist'], '')
        self.assertEqual(track['duration'], 0)


class MusicLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ler-music-db-')
        self.root = Path(self.tmp.name)
        self.song = self.root / 'song.mp3'
        self.song.write_bytes(b'test')

    def tearDown(self):
        self.tmp.cleanup()

    def test_playlist_persistence_and_duplicate_songs(self):
        db = MusicLibrary(str(self.root))
        self.assertEqual(db.import_paths([str(self.song), str(self.song)]), 2)
        self.assertEqual(len(db.tracks()), 1)
        ident = db.new_playlist('My offline mix')
        db.add_to_playlist(ident, str(self.song))
        db.add_to_playlist(ident, str(self.song))
        self.assertEqual(len(db.playlist_paths(ident)), 2)
        db.close()
        db = MusicLibrary(str(self.root))
        self.assertEqual(db.playlists(), [(ident, 'My offline mix')])
        self.assertEqual(len(db.playlist_paths(ident)), 2)
        db.remove_playlist(ident)
        self.assertEqual(db.playlists(), [])
        self.assertTrue(self.song.is_file())  # playlists never delete audio
        db.close()

    def test_reject_duplicate_or_empty_playlist_name(self):
        db = MusicLibrary(str(self.root))
        db.new_playlist('My list')
        with self.assertRaises(Exception):
            db.new_playlist('MY LIST')
        for name in ('', '   ', 'x'*81, 'Bad\nname'):
            with self.assertRaises(MusicError):
                safe_playlist_name(name)
        db.close()

    def test_music_state_separate_and_atomic(self):
        state = {'last_path': str(self.song), 'position': 26.5,
                 'queue': [str(self.song)], 'muted': False}
        save_music_state(self.root, state)
        self.assertEqual(load_music_state(self.root), state)
        self.assertFalse((self.root / 'reading_state.json').exists())
        (self.root / 'music_state.json').write_text('{bad json', encoding='utf-8')
        self.assertEqual(load_music_state(self.root), {})


class FakeMusicBackend:
    def __init__(self):
        self.current_path = None
        self.paused = True
        self.position = 0.0
        self.volume = 80
        self.muted = False
        self.closed = False
    def load(self, path, start_position=None):
        self.current_path = normalise_music_path(path)
        self.paused = True
        self.position = float(start_position or 0)
        return self.status()
    def set_volume(self, v):
        self.volume = float(v)
        return self.volume
    def set_mute(self, v):
        self.muted = bool(v)
        return self.muted
    def play(self):
        self.paused = False
    def pause(self):
        self.paused = True
    def seek(self, v):
        self.position = float(v)
    def status(self, include_details=True):
        return dict(time_pos=self.position, paused=self.paused,
                    duration=60, volume=self.volume, mute=self.muted)
    def idle(self):
        return False
    def close(self):
        self.closed = True


class MusicWorkerTests(unittest.TestCase):
    def test_worker_commands_and_paused_initial_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a.opus'
            path.write_bytes(b'fixture')
            worker = MusicWorker(backend_factory=FakeMusicBackend, poll_interval=0.04)
            try:
                self.assertTrue(worker.submit('open', 3, str(path), 6.0, 42, True))
                loaded = None
                import time
                end = time.monotonic() + 2
                while time.monotonic() < end:
                    event = worker.events.get(timeout=0.5)
                    if event['type'] == 'loaded':
                        loaded = event
                        break
                self.assertEqual(loaded['token'], 3)
                self.assertTrue(loaded['status']['paused'])
                self.assertEqual(loaded['status']['time_pos'], 6.0)
                self.assertTrue(loaded['status']['mute'])
                worker.submit('play', 3)
                worker.submit('seek', 3, 23)
                worker.submit('pause', 3)
                worker.submit('stop', 3)
            finally:
                worker.shutdown()
                worker.join(timeout=2)
                self.assertFalse(worker._thread.is_alive())

    def test_backend_validation_does_not_weaken_audiobooks(self):
        from audiobook_player import normalise_m4b_path
        with tempfile.TemporaryDirectory() as folder:
            music = Path(folder) / 'song.flac'
            book = Path(folder) / 'book.m4b'
            music.write_bytes(b'fixture')
            book.write_bytes(b'fixture')
            with self.assertRaises(Exception):
                normalise_m4b_path(music)
            with self.assertRaises(MusicError):
                normalise_music_path(book)


if __name__ == '__main__':
    unittest.main()
