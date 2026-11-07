"""Home navigation must not restart an active Music playback session."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from music_ui import MusicMixin


class MusicNavigationTests(unittest.TestCase):
    def test_home_resume_keeps_playing_music_session(self):
        view = mock.Mock()
        view.music_path = '/music/already-playing.flac'
        view.music_ready = True
        view.music_loading = False
        MusicMixin._music_resume_last(view)
        view.show_music_mode.assert_called_once_with()
        view._music_open_queue.assert_not_called()
        view.music_worker.submit.assert_not_called()

    def test_home_resume_keeps_loading_session(self):
        view = mock.Mock()
        view.music_path = '/music/loading.flac'
        view.music_ready = False
        view.music_loading = True
        MusicMixin._music_resume_last(view)
        view.show_music_mode.assert_called_once_with()
        view._music_open_queue.assert_not_called()

    def test_music_tab_does_not_reload_or_pause_music(self):
        view = mock.Mock()
        view.audio_worker = None
        view.audio_path = None
        MusicMixin.show_music_mode(view)
        view._set_app_mode.assert_called_once_with('music')
        view.music_worker.submit.assert_not_called()
        view._music_open_queue.assert_not_called()

    def test_home_resume_recovers_previous_track_when_no_session(self):
        with tempfile.TemporaryDirectory() as folder:
            song = Path(folder) / 'offline.flac'
            song.write_bytes(b'fixture')
            view = mock.Mock()
            view.music_path = ''
            view.music_ready = False
            view.music_loading = False
            view.music_state = {'last_path': str(song), 'queue': [str(song)], 'position': 47.5}
            MusicMixin._music_resume_last(view)
            view._music_open_queue.assert_called_once_with([str(song)], 0, 47.5, autoplay=False)
            view.show_music_mode.assert_not_called()

if __name__ == '__main__':
    unittest.main()
