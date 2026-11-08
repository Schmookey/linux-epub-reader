"""Home dashboard music metadata tests: offline tags, accurate fallbacks and Tk display."""
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import music_ui
from music_player import track_info


class HomeMetadataTests(unittest.TestCase):
    def test_rich_song_and_album_metadata(self):
        values = music_ui.music_home_details({
            'title': 'The song', 'artist': 'The singer', 'album': 'The record',
            'albumartist': 'The group', 'genre': 'Folk', 'date': '2024',
            'tracknumber': 7, 'discnumber': 2, 'duration': 223,
            'description': 'Artist notes supplied in the recording.'
        }, 47)
        self.assertEqual(values['artist'], 'The singer')
        self.assertEqual(values['album'], 'Album: The record')
        self.assertIn('Album artist: The group', values['extra'])
        self.assertIn('Genre: Folk', values['extra'])
        self.assertIn('Released: 2024', values['extra'])
        self.assertIn('Track 7 · Disc 2', values['extra'])
        self.assertIn('Duration: 3:43', values['extra'])
        self.assertEqual(values['description'], 'Artist notes supplied in the recording.')
        self.assertEqual(values['position'], 'Saved position: 0:47 of 3:43')

    def test_untagged_song_is_not_assigned_invented_metadata(self):
        values = music_ui.music_home_details({}, 'invalid')
        self.assertEqual(values['artist'], 'Artist not supplied')
        self.assertEqual(values['album'], 'Album: Album not supplied')
        self.assertFalse(values['extra'])
        self.assertIn('No description', values['description'])
        self.assertEqual(values['position'], 'Saved position: 0:00')

    def test_mutagen_easy_description_and_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'song.mp3'
            path.write_bytes(b'fixture')
            media = types.SimpleNamespace(tags={
                'title': ['A Song'], 'artist': ['An Artist'],
                'album': ['A Record'], 'genre': ['Rock'],
                'date': ['2025'], 'tracknumber': ['3/12'],
                'description': ['Short description.'],
            }, info=types.SimpleNamespace(length=200.5))
            module = types.ModuleType('mutagen')
            module.File = mock.Mock(return_value=media)
            with mock.patch.dict(sys.modules, {'mutagen': module}):
                result = track_info(str(path))
            self.assertEqual(result['title'], 'A Song')
            self.assertEqual(result['album'], 'A Record')
            self.assertEqual(result['tracknumber'], 3)
            self.assertEqual(result['description'], 'Short description.')
            self.assertEqual(result['duration'], 200.5)
            module.File.assert_called_once_with(str(path), easy=True)

    def test_id3_raw_comment_fallback_never_reads_lyrics(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'music.mp3'
            path.write_bytes(b'fixture')
            easy = types.SimpleNamespace(tags={'title': ['Music']}, info=None)
            class RawTags(dict):
                def getall(self, name):
                    return [types.SimpleNamespace(text=['Only the comments.'])] if name == 'COMM' else []
            raw = types.SimpleNamespace(tags=RawTags({'USLT': 'Do not put lyrics in the home card.'}))
            module = types.ModuleType('mutagen')
            module.File = mock.Mock(side_effect=lambda path, easy=False: easy_file if easy else raw)
            easy_file = easy
            with mock.patch.dict(sys.modules, {'mutagen': module}):
                result = track_info(str(path))
            self.assertEqual(result['description'], 'Only the comments.')
            self.assertNotIn('lyrics', result['description'])

    def test_music_home_card_shows_metadata_in_description_panel(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest('No X11 display in this test environment')
            return
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'song.flac'
                path.write_bytes(b'fixture')
                owner = types.SimpleNamespace(music_state={'last_path': str(path), 'position': 50},
                    _music_home_photo=None, _music_resume_last=lambda: None,
                    show_music_mode=lambda: None, _create_cover_photo=lambda *a: None)
                mock_data = {
                    'title': 'Named Song', 'artist': 'Real Artist', 'album': 'Real Album',
                    'genre': 'Jazz', 'date': '2020', 'duration': 180,
                    'description': 'Description found in the file.'
                }
                holder = tk.Frame(root)
                holder.pack()
                with mock.patch.object(music_ui, 'track_info', return_value=mock_data), \
                     mock.patch.object(music_ui, 'track_cover', return_value=None):
                    music_ui.MusicMixin._build_music_home_card(owner, holder)
                def walk(node):
                    for child in node.winfo_children():
                        yield child
                        yield from walk(child)
                widgets=list(walk(holder))
                texts=[item.cget('text') for item in widgets if isinstance(item, (tk.Label, tk.Button))]
                self.assertIn('Named Song', texts)
                self.assertIn('Real Artist', texts)
                self.assertIn('Album: Real Album', texts)
                self.assertIn('Genre: Jazz', texts)
                self.assertIn('Released: 2020', texts)
                self.assertIn('Saved position: 0:50 of 3:00', texts)
                panels=[item for item in widgets if isinstance(item, tk.Text)]
                self.assertEqual(len(panels), 1)
                self.assertEqual(panels[0].get('1.0', 'end-1c'), 'Description found in the file.')
                self.assertEqual(panels[0].cget('state'), tk.DISABLED)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
