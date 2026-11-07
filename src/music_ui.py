# Copyright (C) 2026 Linux EPUB Reader project contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Tkinter Music mode for Linux EPUB Reader. Separate from M4B Audiobooks."""
import os
import queue
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox

from audiobook_player import format_time
from mpris_service import MPRISBridge
from music_player import (MusicLibrary, MusicWorker, MusicError, MUSIC_EXTENSIONS,
                          normalise_music_path, scan_music_folder, track_info,
                          track_cover, load_music_state, save_music_state)

APP_BG = '#17191C'
PANEL_BG = '#22252A'
MINT_GREEN = '#87CF3E'
MUTED_TEXT = '#AEB4BD'
FG = '#F0F1F3'
BORDER = '#353941'


class MusicMixin:
    """Methods added to Reader without changing its EPUB and M4B data models."""

    def _music_init(self, state_dir):
        self.music_directory = state_dir
        self.music_library = None
        self.music_worker = MusicWorker()
        self.music_state = load_music_state(state_dir)
        self.music_queue = []
        self.music_index = -1
        self.music_path = ''
        self.music_metadata = {}
        self.music_last_status = {}
        self.music_token = 0
        self.music_loading = False
        self.music_seeking = False
        self.music_volume_dragging = False
        self.music_close_requested = False
        self.music_poll_id = None
        self.music_cover_photo = None
        self._music_home_photo = None
        self._music_play_after_open = False
        self._music_last_save = 0.0
        self._music_tree_items = {}
        self._music_import_token = 0
        self._mpris_active_kind = 'music'
        self._mpris = MPRISBridge(state_dir, preview='preview' in os.path.basename(state_dir).lower())
        self._mpris.start()
        self.music_art_uri = ''
        self.audio_cover_uri = ''
        try:
            self.music_library = MusicLibrary(state_dir)
        except (OSError, ValueError) as exc:
            self.music_library_error = str(exc)

    def _music_build_ui(self):
        self.music_mode_button = ttk.Button(self.modebar, text='Music', command=self.show_music_mode)
        self.music_mode_button.pack(side=tk.LEFT, padx=7)
        self.music_toolbar = ttk.Frame(self.toolbar, style='Toolbar.TFrame')
        for label, callback in (
            ('Open songs…', self._music_open_dialog),
            ('Open album/folder…', self._music_folder_dialog),
            ('New playlist…', self._music_new_playlist),
            ('Add to playlist…', self._music_add_to_playlist),
            ('Delete playlist…', self._music_delete_playlist),
            ('Resume last song', self._music_resume_last),
        ):
            ttk.Button(self.music_toolbar, text=label, command=callback).pack(side=tk.LEFT, padx=(0, 6))

        self.music_screen = tk.Frame(self.reader_body, bg=APP_BG)
        self.music_screen.grid_columnconfigure(0, weight=0, minsize=265)
        self.music_screen.grid_columnconfigure(1, weight=1)
        self.music_screen.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(self.music_screen, bg=PANEL_BG, width=280,
                           highlightbackground=BORDER, highlightthickness=1)
        sidebar.grid(row=0, column=0, sticky='nsew', padx=(0, 9))
        sidebar.grid_propagate(False)
        tk.Label(sidebar, text='MUSIC LIBRARY', bg=PANEL_BG, fg=MINT_GREEN,
                 font=('Sans', 10, 'bold')).pack(anchor='w', padx=12, pady=(12, 6))
        tk.Label(sidebar, text='Albums · Tracks · Playlists', bg=PANEL_BG,
                 fg=MUTED_TEXT, font=('Sans', 9)).pack(anchor='w', padx=12, pady=(0, 8))
        self.music_tree = ttk.Treeview(sidebar, show='tree', selectmode='browse')
        scroll = ttk.Scrollbar(sidebar, orient=tk.VERTICAL, command=self.music_tree.yview)
        self.music_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.music_tree.pack(fill=tk.BOTH, expand=True, padx=(8, 0), pady=(0, 8))
        self.music_tree.bind('<Double-Button-1>', self._music_tree_open)
        self.music_tree.bind('<Return>', self._music_tree_open)
        self.music_tree.bind('<space>', self._music_tree_open)

        panel = tk.Frame(self.music_screen, bg=APP_BG)
        panel.grid(row=0, column=1, sticky='nsew')
        tk.Label(panel, text='NOW PLAYING', bg=APP_BG, fg=MINT_GREEN,
                 font=('Sans', 9, 'bold')).pack(pady=(6, 6))
        cover_frame = tk.Frame(panel, bg='#090A0B', width=270, height=270,
                               highlightbackground=BORDER, highlightthickness=1)
        cover_frame.pack(pady=(0, 10))
        cover_frame.pack_propagate(False)
        self.music_cover_label = tk.Label(cover_frame, text='MUSIC\nNO COVER ART',
                                          bg='#090A0B', fg=MUTED_TEXT,
                                          font=('Sans', 16, 'bold'))
        self.music_cover_label.pack(fill=tk.BOTH, expand=True)
        self.music_title_label = tk.Label(panel, text='Choose a song, album or playlist',
             bg=APP_BG, fg=FG, font=('Sans', 16, 'bold'), wraplength=650)
        self.music_title_label.pack(fill=tk.X, pady=(0, 4))
        self.music_artist_label = tk.Label(panel, text='DRM-free · Offline',
             bg=APP_BG, fg=MUTED_TEXT, font=('Sans', 10), wraplength=650)
        self.music_artist_label.pack(fill=tk.X, pady=(0, 13))

        transport = tk.Frame(panel, bg=APP_BG)
        transport.pack(pady=(0, 11))
        for symbol, fn in (('⏮', self._music_previous), ('Ⅱ', self._music_pause),
                           ('▶', self._music_play), ('■', self._music_stop),
                           ('⏭', self._music_next)):
            self._make_round_audio_button(transport, symbol, fn, size=70, font_size=24)

        seekline = tk.Frame(panel, bg=APP_BG)
        seekline.pack(fill=tk.X, padx=18)
        self.music_elapsed = tk.Label(seekline, text='0:00', fg=MUTED_TEXT, bg=APP_BG)
        self.music_elapsed.pack(side=tk.LEFT)
        self.music_position_var = tk.DoubleVar(value=0)
        self.music_seek = tk.Scale(seekline, from_=0, to=1, variable=self.music_position_var,
            orient=tk.HORIZONTAL, showvalue=False, resolution=0.1, width=12, sliderlength=28,
            relief=tk.FLAT, bd=0, highlightthickness=0, bg=MINT_GREEN, fg=FG,
            troughcolor='#30343A', activebackground=MINT_GREEN, sliderrelief=tk.FLAT,
            cursor='hand2')
        self.music_seek.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)
        self.music_seek.bind('<ButtonPress-1>', lambda e: setattr(self, 'music_seeking', True))
        self.music_seek.bind('<ButtonRelease-1>', self._music_seek_commit)
        self.music_remaining = tk.Label(seekline, text='-0:00', fg=MUTED_TEXT, bg=APP_BG)
        self.music_remaining.pack(side=tk.RIGHT)

        bottom = tk.Frame(panel, bg=APP_BG)
        bottom.pack(fill=tk.X, padx=24, pady=(17, 4))
        tk.Label(bottom, text='Volume', bg=APP_BG, fg=MUTED_TEXT,
                 font=('Sans', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 9))
        self.music_volume_var = tk.DoubleVar(value=max(0.0, min(100.0,
                                                float(self.music_state.get('volume', 80) or 80))))
        volume = tk.Scale(bottom, from_=0, to=100, variable=self.music_volume_var,
            command=self._music_volume, orient=tk.HORIZONTAL, showvalue=False,
            resolution=1, width=14, sliderlength=30, length=180,
            relief=tk.FLAT, bd=0, highlightthickness=0, bg=MINT_GREEN, fg=FG,
            troughcolor='#30343A', activebackground=MINT_GREEN, sliderrelief=tk.FLAT,
            cursor='hand2')
        volume.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 7))
        volume.bind('<ButtonPress-1>', lambda e: setattr(self, 'music_volume_dragging', True))
        volume.bind('<ButtonRelease-1>', lambda e: setattr(self, 'music_volume_dragging', False))
        self.music_mute_button, self.music_mute_text, _ = self._make_round_audio_button(
            bottom, '🔊', self._music_toggle_mute, size=47, font_size=17, pack=False)
        self.music_mute_button.pack(side=tk.LEFT, padx=4)
        self.music_queue_label = tk.Label(panel, text='Queue is empty', bg=APP_BG,
                                          fg=MUTED_TEXT, font=('Sans', 9))
        self.music_queue_label.pack(pady=(12, 0))
        self._music_refresh_tree()
        self.music_poll_id = self.after(120, self._music_events)
        self.music_mpris_poll_id = self.after(180, self._music_mpris_actions)

    def _music_refresh_tree(self):
        if not hasattr(self, 'music_tree'):
            return
        self.music_tree.delete(*self.music_tree.get_children())
        self._music_tree_items.clear()
        if self.music_library is None:
            self.music_tree.insert('', tk.END, text='Library unavailable')
            return
        tracks = self.music_library.tracks()
        all_paths = [x['path'] for x in tracks if os.path.isfile(x['path'])]
        available_paths = set(all_paths)
        all_node = self.music_tree.insert('', tk.END, text=f'All tracks ({len(all_paths)})', open=True)
        for track in tracks[:1000]:
            if track['path'] in available_paths:
                iid = self.music_tree.insert(all_node, tk.END,
                     text=f"{track['artist'] + ' — ' if track['artist'] else ''}{track['title']}")
                self._music_tree_items[iid] = (track['path'], all_paths)
        albums_node = self.music_tree.insert('', tk.END, text='Albums', open=True)
        albums = {}
        for item in tracks:
            if item['path'] in available_paths:
                albums.setdefault(item['album'] or 'Unknown album', []).append(item)
        for title, items in sorted(albums.items(), key=lambda x: x[0].casefold()):
            root = self.music_tree.insert(albums_node, tk.END, text=title)
            album_paths = [x['path'] for x in items]
            for item in items[:500]:
                iid = self.music_tree.insert(root, tk.END,
                       text=f"{item['tracknumber']:02d} {item['title']}")
                self._music_tree_items[iid] = (item['path'], album_paths)
        playlists_node = self.music_tree.insert('', tk.END, text='Playlists', open=True)
        for ident, name in self.music_library.playlists():
            root = self.music_tree.insert(playlists_node, tk.END, text=name)
            self._music_tree_items[root] = ('playlist', ident)
            paths = [p for p in self.music_library.playlist_paths(ident) if os.path.isfile(p)]
            for path in paths[:500]:
                iid = self.music_tree.insert(root, tk.END, text=os.path.splitext(os.path.basename(path))[0])
                self._music_tree_items[iid] = (path, paths)

    def _music_tree_open(self, _event=None):
        selected = self.music_tree.selection()
        if not selected:
            return
        item = self._music_tree_items.get(selected[0])
        if not item:
            return
        if item[0] == 'playlist':
            paths = [p for p in self.music_library.playlist_paths(item[1]) if os.path.isfile(p)]
            self._music_open_queue(paths)
        else:
            path, paths = item
            self._music_open_queue(paths, paths.index(path))

    def _music_open_dialog(self):
        filters = ' '.join('*'+ext for ext in sorted(MUSIC_EXTENSIONS))
        paths = filedialog.askopenfilenames(parent=self, title='Open local DRM-free music',
              filetypes=[('Music files', filters), ('All files', '*.*')])
        if paths:
            self._music_open_queue(paths)

    def _music_folder_dialog(self):
        folder = filedialog.askdirectory(parent=self, title='Import a local album or music folder')
        if folder:
            try:
                paths = scan_music_folder(folder)
            except MusicError as exc:
                messagebox.showerror('Cannot import music', str(exc), parent=self)
                return
            if not paths:
                messagebox.showinfo('No supported music', 'No supported DRM-free audio files found.', parent=self)
                return
            self._music_open_queue(paths)

    def _music_open_queue(self, paths, selected=0, position=0.0, autoplay=False):
        valid = []
        errors = []
        for path in paths:
            try:
                valid.append(normalise_music_path(path))
            except MusicError as exc:
                errors.append(str(exc))
        if not valid:
            messagebox.showerror('Cannot open music', errors[0] if errors else 'No music files.', parent=self)
            return
        if errors:
            messagebox.showwarning('Some files were skipped',
                f'{len(errors)} unsupported file(s) were excluded. M4B belongs in Audiobooks.', parent=self)
        if self.music_library is not None:
            try:
                self.music_library.import_paths(valid)
            except (OSError, ValueError) as exc:
                self.status.configure(text=f'Music library could not be updated: {exc}')
        self.music_queue = valid
        original_selected = paths[selected] if 0 <= selected < len(paths) else valid[0]
        self.music_index = valid.index(original_selected) if original_selected in valid else 0
        self._music_refresh_tree()
        self._music_open_index(self.music_index, position, autoplay)

    def _music_open_index(self, index, position=0.0, autoplay=False):
        if not 0 <= index < len(self.music_queue):
            return
        path = self.music_queue[index]
        try:
            path = normalise_music_path(path)
        except MusicError as exc:
            messagebox.showerror('Cannot open music', str(exc), parent=self)
            return
        if self.audio_worker and self.audio_path:
            self.audio_worker.submit('pause', self._audio_load_token)
        self.music_index = index
        self.music_path = path
        self._mpris_active_kind = 'music'
        self.music_metadata = track_info(path)
        self.music_token += 1
        self.music_loading = True
        self._music_play_after_open = autoplay
        self.music_last_status = {'time_pos': position, 'paused': True}
        self.music_title_label.configure(text=self.music_metadata.get('title') or os.path.basename(path))
        self.music_artist_label.configure(text=' · '.join(x for x in (
            self.music_metadata.get('artist'), self.music_metadata.get('album'),
            self.music_metadata.get('date')) if x) or 'Unknown artist')
        cover = track_cover(path)
        self.music_art_uri = self._mpris.store_art(cover, path)
        self.music_cover_photo = self._create_cover_photo(cover, (260, 260)) if cover else None
        self.music_cover_label.configure(image=self.music_cover_photo or '',
            text='' if self.music_cover_photo else 'MUSIC\nNO COVER ART')
        self.music_queue_label.configure(text=f'Track {index+1} of {len(self.music_queue)} · {os.path.basename(path)}')
        self._music_save(force=True)
        self.music_worker.submit('open', self.music_token, path, position,
             self.music_volume_var.get(), bool(self.music_state.get('muted', False)))
        self.show_music_mode()

    def show_music_mode(self):
        if self.audio_worker and self.audio_path:
            self.audio_worker.submit('pause', self._audio_load_token)
        self._mpris_active_kind = 'music'
        self._set_app_mode('music')
        self.heading.pack_forget()
        self.text_frame.pack_forget()
        self.welcome_view.pack_forget()
        self.audio_screen.pack_forget()
        self.music_screen.pack(fill=tk.BOTH, expand=True)
        self.status.configure(text='Music · local playback only')

    def _music_resume_last(self):
        path = self.music_state.get('last_path')
        if not path:
            self.show_music_mode()
            return
        try:
            path = normalise_music_path(path)
        except MusicError:
            messagebox.showwarning('Song not found',
                'The last played song has moved. Choose the song again from Music.', parent=self)
            self.show_music_mode()
            return
        entries = self.music_state.get('queue', [])
        valid = []
        for item in entries if isinstance(entries, list) else []:
            try:
                valid.append(normalise_music_path(item))
            except MusicError:
                pass
        if path not in valid:
            valid = [path]
        try:
            position = max(0.0, float(self.music_state.get('position', 0) or 0))
        except (TypeError, ValueError):
            position = 0.0
        self._music_open_queue(valid, valid.index(path), position, autoplay=False)

    def _music_play(self):
        if self.music_path:
            if self.audio_worker and self.audio_path:
                self.audio_worker.submit('pause', self._audio_load_token)
            self._mpris_active_kind = 'music'
            self.music_worker.submit('play', self.music_token)
            self.music_last_status['paused'] = False
        else:
            self._music_resume_last()

    def _music_pause(self):
        if self.music_path:
            self.music_worker.submit('pause', self.music_token)
            self.music_last_status['paused'] = True
            self._music_save(force=True)

    def _music_stop(self):
        if self.music_path:
            self.music_worker.submit('stop', self.music_token)
            self.music_last_status.update(time_pos=0.0, paused=True)
            self._music_save(force=True)

    def _music_next(self):
        if self.music_queue and self.music_index+1 < len(self.music_queue):
            autoplay = not bool(self.music_last_status.get('paused', True))
            self._music_open_index(self.music_index+1, 0.0, autoplay)
        elif self.music_path:
            self._music_stop()

    def _music_previous(self):
        if not self.music_queue:
            return
        pos = float(self.music_last_status.get('time_pos') or 0)
        if pos >= 3.0 or self.music_index == 0:
            self.music_worker.submit('seek', self.music_token, 0.0)
        elif self.music_index > 0:
            self._music_open_index(self.music_index-1, 0.0,
                autoplay=not bool(self.music_last_status.get('paused', True)))

    def _music_volume(self, value):
        if self.music_path and not self.music_loading:
            self.music_worker.submit('volume', self.music_token, value)
        self.music_state['volume'] = float(value)

    def _music_toggle_mute(self):
        if not self.music_path:
            self.music_state['muted'] = not bool(self.music_state.get('muted', False))
            self._music_set_mute_icon(self.music_state['muted'])
        else:
            self.music_worker.submit('toggle_mute', self.music_token)

    def _music_set_mute_icon(self, muted):
        self.music_mute_button.itemconfigure(self.music_mute_text,
            text='🔇' if muted else '🔊')

    def _music_seek_commit(self, _event=None):
        if self.music_path:
            self.music_worker.submit('seek', self.music_token, self.music_position_var.get())
        self.music_seeking = False

    def _music_events(self):
        if self.music_close_requested:
            return
        try:
            while True:
                event = self.music_worker.events.get_nowait()
                if event['token'] != self.music_token:
                    continue
                kind = event['type']
                if kind == 'loaded':
                    self.music_loading = False
                    self.music_last_status = event['status']
                    if self._music_play_after_open:
                        self._mpris_active_kind = 'music'
                        self.music_worker.submit('play', self.music_token)
                    self._music_play_after_open = False
                elif kind == 'status':
                    self.music_last_status = event['status']
                    self.music_state['muted'] = bool(event['status'].get('mute', False))
                    self._music_set_mute_icon(self.music_state['muted'])
                    if not self.music_seeking:
                        try:
                            duration = max(0.0, float(event['status'].get('duration') or 0))
                            position = max(0.0, float(event['status'].get('time_pos') or 0))
                        except (ValueError, TypeError):
                            duration = position = 0.0
                        self.music_seek.configure(to=max(1, duration))
                        self.music_position_var.set(position)
                        self.music_elapsed.configure(text=format_time(position))
                        self.music_remaining.configure(text='-'+format_time(max(0, duration-position)))
                    if event['status'].get('volume') is not None and not self.music_volume_dragging:
                        self.music_volume_var.set(float(event['status']['volume']))
                    self._music_save()
                    self._music_publish_mpris('music', event['status'])
                elif kind == 'ended':
                    if self.music_index+1 < len(self.music_queue):
                        self._music_open_index(self.music_index+1, 0.0, autoplay=True)
                    else:
                        self.music_last_status.update(time_pos=0.0, paused=True)
                        self._music_save(force=True)
                elif kind == 'error':
                    self.music_loading = False
                    self.status.configure(text='Music: '+event.get('error', 'Playback error'))
                    if event.get('action') == 'open':
                        messagebox.showerror('Music playback failed',
                          'This local audio file could not be played. It may be damaged, '
                          'unsupported by your installed decoder, or DRM-protected.\n\n'
                          + event.get('error', ''), parent=self)
                elif kind == 'command_completed':
                    if event.get('action') == 'toggle_mute':
                        self.music_state['muted'] = not bool(self.music_state.get('muted', False))
                        self._music_set_mute_icon(self.music_state['muted'])
        except queue.Empty:
            pass
        self.music_poll_id = self.after(120, self._music_events)

    def _music_save(self, force=False):
        import time
        now = time.monotonic()
        if not force and now-self._music_last_save < 4.0:
            return
        self._music_last_save = now
        if self.music_path:
            self.music_state.update(last_path=self.music_path,
                queue=self.music_queue[:15000], index=self.music_index,
                position=max(0.0, float(self.music_last_status.get('time_pos') or 0)),
                volume=float(self.music_volume_var.get()))
        try:
            save_music_state(self.music_directory, self.music_state)
        except (OSError, TypeError, ValueError) as exc:
            self.status.configure(text=f'Warning: Music position could not be saved: {exc}')

    def _music_new_playlist(self):
        if self.music_library is None:
            return
        name = simpledialog.askstring('New playlist', 'Playlist name:', parent=self)
        if not name:
            return
        try:
            self.music_library.new_playlist(name)
            self._music_refresh_tree()
        except (ValueError, OSError, Exception) as exc:
            messagebox.showerror('Playlist not created', str(exc), parent=self)

    def _music_selected_playlist(self):
        if self.music_library is None:
            return None
        rows = self.music_library.playlists()
        if not rows:
            messagebox.showinfo('No playlists', 'Create a playlist first.', parent=self)
            return None
        prompt = '\n'.join(f'{i+1}. {name}' for i, (_, name) in enumerate(rows))
        choice = simpledialog.askinteger('Choose playlist', prompt+'\n\nEnter its number:',
             minvalue=1, maxvalue=len(rows), parent=self)
        return rows[choice-1][0] if choice else None

    def _music_add_to_playlist(self):
        if not self.music_path or self.music_library is None:
            messagebox.showinfo('Choose a song', 'Open a music track first.', parent=self)
            return
        ident = self._music_selected_playlist()
        if ident is not None:
            try:
                self.music_library.add_to_playlist(ident, self.music_path)
                self._music_refresh_tree()
            except (MusicError, OSError) as exc:
                messagebox.showerror('Playlist error', str(exc), parent=self)

    def _music_delete_playlist(self):
        ident = self._music_selected_playlist()
        if ident is not None and messagebox.askyesno('Delete playlist',
                'Delete the selected playlist? Your music files will not be deleted.', parent=self):
            self.music_library.remove_playlist(ident)
            self._music_refresh_tree()

    def _build_music_home_card(self, parent, column=2):
        record = self.music_state or {}
        path = record.get('last_path') or ''
        card = tk.Frame(parent, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=0, column=column, sticky='nsew', padx=5, pady=4)
        tk.Label(card, text='LAST PLAYED', bg=PANEL_BG, fg=MINT_GREEN,
                 font=('Sans', 9, 'bold'), anchor='w').pack(fill=tk.X, padx=14, pady=(14, 9))
        body = tk.Frame(card, bg=PANEL_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12)
        art = tk.Frame(body, bg=APP_BG, width=100, height=145)
        art.pack(side=tk.LEFT, anchor='n', padx=(0, 12))
        art.pack_propagate(False)
        info = tk.Frame(body, bg=PANEL_BG)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        available = bool(path and os.path.isfile(path))
        data = track_info(path) if available else {}
        artwork = track_cover(path) if available else None
        self._music_home_photo = self._create_cover_photo(artwork, (98, 140)) if artwork else None
        tk.Label(art, image=self._music_home_photo or '',
                 text='' if self._music_home_photo else 'MUSIC', bg=APP_BG,
                 fg=MUTED_TEXT).pack(fill=tk.BOTH, expand=True)
        tk.Label(info, text=data.get('title') or ('Locate last song' if path else 'No music played yet'),
            bg=PANEL_BG, fg=FG, font=('Sans', 12, 'bold'),
            wraplength=175, justify=tk.LEFT).pack(anchor='w')
        tk.Label(info, text=' · '.join(x for x in (data.get('artist'), data.get('album')) if x)
                 if data else 'Open a song, album or playlist.', bg=PANEL_BG, fg=MUTED_TEXT,
                 wraplength=175, justify=tk.LEFT).pack(anchor='w', pady=(6, 4))
        if available:
            tk.Label(info, text='Saved at '+format_time(record.get('position', 0)),
                     bg=PANEL_BG, fg=MINT_GREEN).pack(anchor='w')
        buttons = tk.Frame(card, bg=PANEL_BG)
        buttons.pack(fill=tk.X, padx=12, pady=(12, 14))
        if available:
            tk.Button(buttons, text='Resume music', command=self._music_resume_last,
                 bg=MINT_GREEN, fg=APP_BG, relief=tk.FLAT, font=('Sans', 9, 'bold'),
                 padx=10, pady=6).pack(side=tk.LEFT)
        tk.Button(buttons, text='Open Music…', command=self.show_music_mode,
                 bg='#30343A', fg=FG, relief=tk.FLAT, padx=10, pady=6).pack(side=tk.LEFT, padx=6)


    def _music_publish_mpris(self, kind, status):
        if kind != self._mpris_active_kind:
            return
        if kind == 'music':
            path = self.music_path
            meta = self.music_metadata
            art = self.music_art_uri
            next_track = self.music_index + 1 < len(self.music_queue)
            previous_track = self.music_index > 0
        else:
            path = self.audio_path or ''
            meta = self.audio_metadata
            art = self.audio_cover_uri
            next_track = previous_track = bool(path)
        if not path:
            return
        self._mpris.update(media_path=path,
            title=meta.get('title') or os.path.basename(path),
            artist=meta.get('artist') or meta.get('album_artist') or '',
            album=meta.get('album') or '', cover_uri=art,
            status='Paused' if status.get('paused', True) else 'Playing',
            duration=float(status.get('duration') or 0),
            position=float(status.get('time_pos') or 0),
            volume=float(status.get('volume') or 80),
            next_track=next_track, previous_track=previous_track,
            can_seek=bool(status.get('duration')))

    def _music_mpris_actions(self):
        if self.music_close_requested:
            return
        try:
            while True:
                action, args = self._mpris.commands.get_nowait()
                kind = self._mpris_active_kind
                if kind == 'music' and self.music_path:
                    if action == 'play': self._music_play()
                    elif action == 'pause': self._music_pause()
                    elif action == 'playpause':
                        (self._music_play if self.music_last_status.get('paused', True)
                         else self._music_pause)()
                    elif action == 'stop': self._music_stop()
                    elif action == 'next': self._music_next()
                    elif action == 'previous': self._music_previous()
                    elif action == 'seek':
                        seconds = float(args[0]) / 1_000_000
                        pos = max(0.0, float(self.music_last_status.get('time_pos') or 0) + seconds)
                        self.music_worker.submit('seek', self.music_token, pos)
                    elif action == 'position':
                        meta = self._mpris.snapshot().get('metadata', {})
                        current = meta.get('mpris:trackid')
                        if current is not None and args[0] == current.value:
                            self.music_worker.submit('seek', self.music_token,
                                                     max(0.0, args[1] / 1_000_000))
                elif kind == 'audiobook' and self.audio_path and self.audio_worker:
                    if action == 'play': self._audio_play()
                    elif action == 'pause': self._audio_pause()
                    elif action == 'playpause':
                        (self._audio_play if (self._last_audio_status or {}).get('paused', True)
                         else self._audio_pause)()
                    elif action == 'stop': self._audio_stop()
                    elif action == 'next': self._audio_skip(30)
                    elif action == 'previous': self._audio_skip(-30)
                    elif action == 'seek': self._audio_skip(args[0] / 1_000_000)
                    elif action == 'position':
                        meta = self._mpris.snapshot().get('metadata', {})
                        current = meta.get('mpris:trackid')
                        if current is not None and args[0] == current.value:
                            self.audio_worker.submit('seek', self._audio_load_token,
                                                     max(0.0, args[1] / 1_000_000))
        except queue.Empty:
            pass
        self.music_mpris_poll_id = self.after(180, self._music_mpris_actions)

    def _music_close(self):
        self.music_close_requested = True
        self._mpris.close()
        if getattr(self, 'music_mpris_poll_id', None):
            try:
                self.after_cancel(self.music_mpris_poll_id)
            except tk.TclError:
                pass
        if self.music_poll_id:
            try:
                self.after_cancel(self.music_poll_id)
            except tk.TclError:
                pass
        self._music_save(force=True)
        self.music_worker.shutdown()
        if self.music_library is not None:
            self.music_library.close()
