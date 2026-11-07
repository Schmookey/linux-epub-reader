# Copyright (C) 2026 Linux EPUB Reader project contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Offline, DRM-free music library and mpv worker. M4B is exclusively for audiobooks.

Only existing local, regular files are passed to mpv; this module never accepts a
URL, fetches metadata from the internet, or edits the user's music files.
"""

import base64
import json
import os
import queue
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from audiobook_player import MPVBackend, AudiobookError

# Playback still depends on the codecs enabled in the installed mpv/FFmpeg build.
MUSIC_EXTENSIONS = frozenset({
    '.mp3', '.flac', '.wav', '.wave', '.ogg', '.oga', '.opus', '.spx',
    '.m4a', '.mp4', '.aac', '.aif', '.aiff', '.caf', '.alac',
    '.wma', '.ape', '.wv', '.mpc', '.mka', '.tta', '.tak', '.ac3',
    '.dts', '.dsf', '.dff', '.amr', '.3gp', '.3g2', '.ra',
})

class MusicError(ValueError):
    pass


def normalise_music_path(path):
    if not isinstance(path, (str, os.PathLike)):
        raise MusicError('Choose a local audio file.')
    value = os.fspath(path)
    if '://' in value or '\x00' in value:
        raise MusicError('Network URLs and non-file sources are not supported.')
    full = os.path.abspath(os.path.expanduser(value))
    suffix = os.path.splitext(full)[1].lower()
    if suffix == '.m4b' or os.path.splitext(os.path.realpath(full))[1].lower() == '.m4b':
        raise MusicError('M4B files are for the Audiobook section only.')
    if suffix in {'.m4p', '.aa', '.aax'}:
        raise MusicError('DRM-protected or audiobook files are not supported in Music.')
    if suffix not in MUSIC_EXTENSIONS:
        raise MusicError('This audio format is not supported in Music.')
    if not os.path.isfile(full):
        raise MusicError('The selected local audio file could not be found.')
    return full


def scan_music_folder(folder, recursive=True, limit=15000):
    """Deterministic bounded scan: no playlist URLs, sockets, or symlink traversal."""
    root = os.path.abspath(os.path.expanduser(os.fspath(folder)))
    if not os.path.isdir(root):
        raise MusicError('Choose an existing music folder.')
    paths = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not os.path.islink(os.path.join(base, d))) if recursive else []
        for filename in sorted(files, key=str.casefold):
            if len(paths) >= limit:
                return paths
            path = os.path.join(base, filename)
            if os.path.splitext(filename)[1].lower() in MUSIC_EXTENSIONS:
                try:
                    paths.append(normalise_music_path(path))
                except MusicError:
                    pass
    return paths


def _first(value):
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ''
    return str(value) if value is not None else ''


def track_info(path):
    """Extract tags offline with optional Mutagen; untagged files use filenames."""
    path = normalise_music_path(path)
    result = {'path': path, 'title': Path(path).stem, 'artist': '',
              'album': '', 'albumartist': '', 'genre': '', 'date': '',
              'tracknumber': 0, 'discnumber': 0, 'duration': 0.0}
    try:
        from mutagen import File
        media = File(path, easy=True)
        if media is not None:
            tags = media.tags or {}
            for key in ('title', 'artist', 'album', 'albumartist', 'genre', 'date'):
                val = _first(tags.get(key)).strip()
                if val:
                    result[key] = val
            for key in ('tracknumber', 'discnumber'):
                match = re.match(r'\d+', _first(tags.get(key)))
                result[key] = int(match.group()) if match else 0
            if getattr(media, 'info', None):
                result['duration'] = max(0.0, float(getattr(media.info, 'length', 0.0) or 0.0))
    except Exception:  # Mutagen raises format-specific parse errors for malformed audio
        pass
    return result


def track_cover(path, max_bytes=8 * 1024 * 1024):
    """Bound image allocations; decode embedded artwork only from local tags."""
    path = normalise_music_path(path)
    try:
        from mutagen import File
        audio = File(path)
        if audio is None:
            return None
        candidates = []
        if getattr(audio, 'pictures', None):
            candidates.extend(p.data for p in audio.pictures)
        tags = getattr(audio, 'tags', None)
        if tags:
            if hasattr(tags, 'getall'):
                candidates.extend(x.data for x in tags.getall('APIC'))
            if 'covr' in tags:
                candidates.extend(tags['covr'])
            for name in ('metadata_block_picture', 'METADATA_BLOCK_PICTURE'):
                for val in tags.get(name, []):
                    try:
                        from mutagen.flac import Picture
                        candidates.append(Picture(base64.b64decode(val)).data)
                    except (ValueError, TypeError):
                        pass
        for data in candidates:
            data = bytes(data)
            if 0 < len(data) <= max_bytes and (
                data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n')
                or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')
            ):
                return data
    except Exception:  # Mutagen raises format-specific parse errors for malformed audio
        pass
    return None


def safe_playlist_name(name):
    value = str(name or '').strip()
    if not value or len(value) > 80 or any(ord(c) < 32 for c in value):
        raise MusicError('Choose a playlist name between 1 and 80 printable characters.')
    return value


class MusicLibrary:
    """Separate, local SQLite index; playlists store paths, never the audio."""
    def __init__(self, directory):
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, 'music_library.sqlite3')
        self.db = sqlite3.connect(self.path)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tracks (
              path TEXT PRIMARY KEY, title TEXT, artist TEXT, album TEXT,
              albumartist TEXT, genre TEXT, date TEXT, tracknumber INTEGER,
              discnumber INTEGER, duration REAL);
            CREATE TABLE IF NOT EXISTS playlists (
              id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE NOT NULL);
            CREATE TABLE IF NOT EXISTS playlist_tracks (
              id INTEGER PRIMARY KEY, playlist_id INTEGER NOT NULL,
              path TEXT NOT NULL, position INTEGER NOT NULL,
              FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE);
        ''')
        self.db.commit()

    def import_paths(self, paths):
        count = 0
        with self.db:
            for path in paths:
                try:
                    info = track_info(path)
                except MusicError:
                    continue
                columns = ('path', 'title', 'artist', 'album', 'albumartist',
                           'genre', 'date', 'tracknumber', 'discnumber', 'duration')
                self.db.execute(
                    'INSERT OR REPLACE INTO tracks (' + ','.join(columns) +
                    ') VALUES (' + ','.join('?' for _ in columns) + ')',
                    [info[c] for c in columns])
                count += 1
        return count

    def tracks(self):
        return [dict(zip(('path','title','artist','album','albumartist','genre',
                          'date','tracknumber','discnumber','duration'), row))
                for row in self.db.execute('''SELECT path,title,artist,album,albumartist,
                 genre,date,tracknumber,discnumber,duration FROM tracks
                 ORDER BY album COLLATE NOCASE,discnumber,tracknumber,title COLLATE NOCASE''')]

    def playlists(self):
        return list(self.db.execute('SELECT id,name FROM playlists ORDER BY name COLLATE NOCASE'))

    def new_playlist(self, name):
        name = safe_playlist_name(name)
        with self.db:
            cursor = self.db.execute('INSERT INTO playlists(name) VALUES (?)', (name,))
        return cursor.lastrowid

    def add_to_playlist(self, playlist_id, path):
        path = normalise_music_path(path)
        with self.db:
            count = self.db.execute('SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id=?',
                                    (playlist_id,)).fetchone()[0]
            self.db.execute('INSERT INTO playlist_tracks(playlist_id,path,position) VALUES(?,?,?)',
                            (playlist_id, path, count))

    def playlist_paths(self, playlist_id):
        return [row[0] for row in self.db.execute(
            'SELECT path FROM playlist_tracks WHERE playlist_id=? ORDER BY position,id', (playlist_id,))]

    def remove_playlist(self, playlist_id):
        with self.db:
            self.db.execute('DELETE FROM playlists WHERE id=?', (playlist_id,))

    def close(self):
        self.db.close()


def load_music_state(directory):
    try:
        with open(os.path.join(directory, 'music_state.json'), encoding='utf-8') as fh:
            record = json.load(fh)
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def save_music_state(directory, record):
    """Atomic state save; music never overwrites EPUB or M4B reading state."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, 'music_state.json')
    fd, temporary = tempfile.mkstemp(prefix='.music-state-', suffix='.json', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(record, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class MusicBackend(MPVBackend):
    """Independent MPV instance; the audiobook backend still accepts only M4B."""
    def load(self, path, start_position=None):
        path = normalise_music_path(path)
        self.start()
        self.command('set_property', 'pause', True)
        if start_position is not None and float(start_position) > 0:
            self.command('loadfile', path, 'replace', '-1',
                         f'start={max(0.0, float(start_position)):.3f}')
        else:
            self.command('loadfile', path, 'replace')
        self.command('set_property', 'pause', True)
        self.current_path = path
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            status = self.status()
            if status.get('duration') is not None:
                tracks = self._request({'command': ['get_property', 'track-list']})
                if tracks and not any(t.get('type') == 'audio' for t in tracks):
                    raise MusicError('This file contains no playable audio track.')
                return status
            if not self.process or self.process.poll() is not None:
                raise MusicError('The music playback engine stopped unexpectedly.')
            time.sleep(0.05)
        raise MusicError('The audio file could not be decoded. It may be damaged or protected.')

    def idle(self):
        try:
            return bool(self._request({'command': ['get_property', 'idle-active']}))
        except AudiobookError:
            return False


class MusicWorker:
    """Single-threaded MPV owner with asynchronous events for the Tk interface."""
    def __init__(self, backend_factory=MusicBackend, poll_interval=0.35):
        self.events = queue.Queue()
        self._commands = queue.Queue()
        self._factory = backend_factory
        self._poll_interval = poll_interval
        self._backend = None
        self._path = None
        self._token = 0
        self._last = {}
        self._end_emitted = False
        self._playing = False
        self._thread = threading.Thread(target=self._run, name='MusicPlaybackWorker', daemon=True)
        self._thread.start()

    def submit(self, action, token=0, *args):
        if not self._thread.is_alive():
            return False
        self._commands.put((action, token, args))
        return True

    def shutdown(self):
        self._commands.put(('shutdown', 0, ()))

    def join(self, timeout=None):
        self._thread.join(timeout)

    def _emit(self, event_type, token, **kwargs):
        self.events.put(dict(type=event_type, token=token, **kwargs))

    def _execute(self, action, token, args):
        if self._backend is None:
            self._backend = self._factory()
        player = self._backend
        if action == 'open':
            path, position, volume, muted = args
            path = normalise_music_path(path)
            status = player.load(path, position)
            player.set_volume(volume)
            player.set_mute(muted)
            status.update({'volume': volume, 'mute': muted})
            self._path, self._token, self._last = path, token, status
            self._end_emitted = False
            self._playing = False
            self._emit('loaded', token, path=path, status=status)
            return
        if not self._path:
            raise MusicError('Open a music track first.')
        if action == 'play':
            self._playing = True
            player.play()
            self._last['paused'] = False
        elif action == 'pause':
            self._playing = False
            player.pause()
            self._last['paused'] = True
        elif action == 'stop':
            self._playing = False
            player.pause()
            player.seek(0)
            self._last.update(time_pos=0.0, paused=True)
        elif action == 'seek':
            player.seek(max(0.0, float(args[0])))
        elif action == 'volume':
            self._last['volume'] = player.set_volume(args[0])
        elif action == 'mute':
            self._last['mute'] = player.set_mute(args[0])
        elif action == 'toggle_mute':
            value = not bool(self._last.get('mute'))
            self._last['mute'] = player.set_mute(value)
        else:
            raise MusicError('Unknown music command.')
        self._emit('command_completed', token, action=action)

    def _poll(self):
        if not self._path or self._backend is None:
            return
        live = self._backend.status(include_details=False)
        status = dict(self._last)
        status.update(live)
        if status.get('time_pos') is not None:
            self._last = dict(status)
        if not self._end_emitted and self._playing and self._backend.idle():
            self._end_emitted = True
            self._playing = False
            self._last['paused'] = True
            self._emit('ended', self._token, path=self._path)
            return
        self._emit('status', self._token, status=status)

    def _run(self):
        next_poll = time.monotonic() + self._poll_interval
        try:
            while True:
                try:
                    action, token, args = self._commands.get(timeout=max(0, next_poll-time.monotonic()))
                except queue.Empty:
                    try:
                        self._poll()
                    except Exception as exc:
                        self._emit('error', self._token, action='status', error=str(exc))
                    next_poll = time.monotonic() + self._poll_interval
                    continue
                if action == 'shutdown':
                    break
                try:
                    self._execute(action, token, args)
                except Exception as exc:
                    if action == 'open':
                        self._path = None
                    self._emit('error', token, action=action, error=str(exc))
                next_poll = time.monotonic() + self._poll_interval
        finally:
            if self._backend is not None:
                self._backend.close()
