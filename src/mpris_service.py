# Copyright (C) 2026 Linux EPUB Reader project contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Local MPRIS2 player using the optional pure-Python dbus-next package.

The D-Bus thread never touches Tk widgets or the mpv socket. All incoming
playback controls are queued for the Tk main thread; metadata is snapshot-only.
No network bus or remote-control transport is created.
"""
import asyncio
import hashlib
import os
import queue
import threading
from pathlib import Path


class MPRISBridge:
    def __init__(self, state_dir, preview=False):
        self.commands = queue.Queue()
        self._state_dir = state_dir
        flatpak_id = os.environ.get('FLATPAK_ID', '')
        if flatpak_id in ('io.github.schmookey.LinuxEpubReader',
                          'io.github.schmookey.LinuxEpubReader.Preview'):
            self._name = 'org.mpris.MediaPlayer2.' + flatpak_id
            self._desktop_entry = flatpak_id
        else:
            self._name = ('org.mpris.MediaPlayer2.LinuxEpubReaderPreview' if preview
                          else 'org.mpris.MediaPlayer2.LinuxEpubReader')
            self._desktop_entry = 'linux-epub-reader'
        self._lock = threading.RLock()
        self._snapshot = {'status': 'Stopped', 'metadata': {}, 'position': 0,
                          'volume': 0.8, 'next': False, 'previous': False,
                          'can_seek': False, 'can_play': False}
        self._loop = None
        self._interface = None
        self._bus = None
        self.error = None
        self.available = False
        self._thread = threading.Thread(target=self._run, name='MPRISLocalService', daemon=True)

    def start(self):
        self._thread.start()

    def store_art(self, cover_bytes, identifier):
        """Only copy embedded cover artwork; no online artwork lookup."""
        if not cover_bytes or len(cover_bytes) > 8 * 1024 * 1024:
            return ''
        extension = '.jpg' if cover_bytes.startswith(b'\xff\xd8\xff') else '.png'
        if not (extension == '.jpg' or cover_bytes.startswith(b'\x89PNG')):
            return ''
        directory = os.path.join(self._state_dir, 'mpris-art')
        name = hashlib.sha256(os.fsencode(identifier)).hexdigest() + extension
        try:
            os.makedirs(directory, exist_ok=True)
            file = os.path.join(directory, name)
            if not os.path.isfile(file):
                with open(file, 'wb') as stream:
                    stream.write(cover_bytes)
            return Path(file).as_uri()
        except OSError:
            return ''

    def snapshot(self):
        with self._lock:
            return dict(self._snapshot)

    def update(self, *, media_path='', title='', artist='', album='', cover_uri='',
               status='Paused', duration=0.0, position=0.0, volume=80.0,
               next_track=False, previous_track=False, can_seek=True):
        try:
            from dbus_next import Variant
        except ImportError:
            return
        if media_path:
            digest = hashlib.sha256(os.fsencode(media_path)).hexdigest()
            trackid = '/org/mpris/MediaPlayer2/track/t' + digest
            meta = {'mpris:trackid': Variant('o', trackid),
                    'xesam:title': Variant('s', str(title or Path(media_path).stem)),
                    'xesam:artist': Variant('as', [str(artist or 'Unknown artist')]),
                    'mpris:length': Variant('x', max(0, int(float(duration)*1_000_000)))}
            if album:
                meta['xesam:album'] = Variant('s', str(album))
            if cover_uri:
                meta['mpris:artUrl'] = Variant('s', cover_uri)
        else:
            meta = {}
        with self._lock:
            self._snapshot = {'status': status, 'metadata': meta,
                              'position': max(0, int(float(position)*1_000_000)),
                              'volume': max(0.0, min(1.0, float(volume)/100.0)),
                              'next': bool(next_track), 'previous': bool(previous_track),
                              'can_play': bool(media_path), 'can_seek': bool(can_seek and media_path)}
        if self._loop is not None and self._interface is not None:
            try:
                self._loop.call_soon_threadsafe(self._notify)
            except RuntimeError:
                pass

    def _notify(self):
        if self._interface is None:
            return
        s = self.snapshot()
        self._interface.emit_properties_changed({
            'PlaybackStatus': s['status'], 'Metadata': s['metadata'],
            'Volume': s['volume'], 'CanGoNext': s['next'],
            'CanGoPrevious': s['previous'], 'CanPlay': s['can_play'],
            'CanSeek': s['can_seek'],
        })

    def _run(self):
        try:
            from dbus_next import BusType, PropertyAccess, RequestNameReply
            from dbus_next.aio import MessageBus
            from dbus_next.service import ServiceInterface, method, dbus_property
        except ImportError as exc:
            self.error = 'Install python3-dbus-next for desktop media controls: ' + str(exc)
            return
        bridge = self

        class Root(ServiceInterface):
            def __init__(self):
                super().__init__('org.mpris.MediaPlayer2')

            @method()
            def Raise(self):
                pass

            @method()
            def Quit(self):
                pass

            @dbus_property(access=PropertyAccess.READ)
            def CanQuit(self) -> 'b':
                return False

            @dbus_property(access=PropertyAccess.READ)
            def CanRaise(self) -> 'b':
                return False

            @dbus_property(access=PropertyAccess.READ)
            def HasTrackList(self) -> 'b':
                return False

            @dbus_property(access=PropertyAccess.READ)
            def Identity(self) -> 's':
                return 'Linux EPUB Reader'

            @dbus_property(access=PropertyAccess.READ)
            def DesktopEntry(self) -> 's':
                return bridge._desktop_entry

            @dbus_property(access=PropertyAccess.READ)
            def SupportedUriSchemes(self) -> 'as':
                return []  # file playback is opened in-app, never via a D-Bus URL

            @dbus_property(access=PropertyAccess.READ)
            def SupportedMimeTypes(self) -> 'as':
                return ['audio/mpeg', 'audio/flac', 'audio/ogg', 'audio/opus',
                        'audio/wav', 'audio/mp4', 'audio/aac']

        class Player(ServiceInterface):
            def __init__(self):
                super().__init__('org.mpris.MediaPlayer2.Player')

            def dispatch(self, action, *args):
                bridge.commands.put((action, args))

            @method()
            def Next(self):
                self.dispatch('next')

            @method()
            def Previous(self):
                self.dispatch('previous')

            @method()
            def Pause(self):
                self.dispatch('pause')

            @method()
            def PlayPause(self):
                self.dispatch('playpause')

            @method()
            def Stop(self):
                self.dispatch('stop')

            @method()
            def Play(self):
                self.dispatch('play')

            @method()
            def Seek(self, Offset: 'x'):
                self.dispatch('seek', Offset)

            @method()
            def SetPosition(self, TrackId: 'o', Position: 'x'):
                self.dispatch('position', TrackId, Position)

            @method()
            def OpenUri(self, Uri: 's'):
                # MPRIS OpenUri cannot bypass the app's local-file-only selector.
                pass

            @dbus_property(access=PropertyAccess.READ)
            def PlaybackStatus(self) -> 's':
                return bridge.snapshot()['status']

            @dbus_property(access=PropertyAccess.READ)
            def LoopStatus(self) -> 's':
                return 'None'

            @dbus_property(access=PropertyAccess.READ)
            def Rate(self) -> 'd':
                return 1.0

            @dbus_property(access=PropertyAccess.READ)
            def Shuffle(self) -> 'b':
                return False

            @dbus_property(access=PropertyAccess.READ)
            def Metadata(self) -> 'a{sv}':
                return bridge.snapshot()['metadata']

            @dbus_property(access=PropertyAccess.READ)
            def Volume(self) -> 'd':
                return bridge.snapshot()['volume']

            @dbus_property(access=PropertyAccess.READ)
            def Position(self) -> 'x':
                return bridge.snapshot()['position']

            @dbus_property(access=PropertyAccess.READ)
            def MinimumRate(self) -> 'd':
                return 1.0

            @dbus_property(access=PropertyAccess.READ)
            def MaximumRate(self) -> 'd':
                return 1.0

            @dbus_property(access=PropertyAccess.READ)
            def CanGoNext(self) -> 'b':
                return bridge.snapshot()['next']

            @dbus_property(access=PropertyAccess.READ)
            def CanGoPrevious(self) -> 'b':
                return bridge.snapshot()['previous']

            @dbus_property(access=PropertyAccess.READ)
            def CanPlay(self) -> 'b':
                return bridge.snapshot()['can_play']

            @dbus_property(access=PropertyAccess.READ)
            def CanPause(self) -> 'b':
                return bridge.snapshot()['can_play']

            @dbus_property(access=PropertyAccess.READ)
            def CanSeek(self) -> 'b':
                return bridge.snapshot()['can_seek']

            @dbus_property(access=PropertyAccess.READ)
            def CanControl(self) -> 'b':
                return True

        async def server():
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
            bus.export('/org/mpris/MediaPlayer2', Root())
            iface = Player()
            bus.export('/org/mpris/MediaPlayer2', iface)
            reply = await bus.request_name(self._name)
            if reply not in (RequestNameReply.PRIMARY_OWNER, RequestNameReply.ALREADY_OWNER):
                raise RuntimeError('MPRIS bus name could not be acquired: ' + self._name)
            self._interface, self._bus = iface, bus
            self.available = True
            await bus.wait_for_disconnect()

        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server())
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.available = False
            self._interface = None
            self._loop = None
            loop.close()

    def close(self):
        if self._loop is not None and self._bus is not None:
            try:
                self._loop.call_soon_threadsafe(self._bus.disconnect)
            except RuntimeError:
                pass
