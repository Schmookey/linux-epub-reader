# Music mode — offline, DRM-free playback

This feature branch adds **Music** as a fourth mode to the existing Home, EBook and Audiobook application. It follows the existing dark background, Linux Mint-green transport styling and embedded-artwork presentation. Music and M4B audiobooks are separate **libraries, playback processes and saved histories**.

## Operation

1. Select **Music** in the top navigation.
2. Use **Open songs…** to select one or several local audio files, or **Open album/folder…** to add the supported files from a folder and subfolders.
3. Double-click a track or a saved playlist in the Music sidebar. The selected recording is **loaded paused** and you can press Play when ready.
4. Use **previous, pause, play, stop and next**, the playback-position slider, volume rocker and mute control. A track's completion advances to the next song in its queue.
5. Use **New playlist…**, **Add to playlist…** and **Delete playlist…** to manage playlists. Deleting a playlist never deletes the audio files.
6. Return to **Home** to see the Last Played card. **Resume music** restores the last track and position, still paused until explicitly played.

Music continues playing if the window is minimised, resized, or switched to Home or EBook. Switching into Audiobook mode pauses Music and vice versa. Closing the application stops playback and saves its position.

### Supported audio file extensions

MP3, FLAC, WAV/WAVE, Ogg Vorbis (`.ogg`, `.oga`), Opus, Speex, M4A/AAC, MP4 audio, AIFF, CAF, ALAC, WMA, APE, WavPack, Musepack, Matroska Audio, TTA, TAK, AC-3, DTS, DSD (`.dsf`, `.dff`), AMR, 3GP, and RealAudio are eligible for loading **only if the locally installed mpv/FFmpeg build can decode their audio streams**. A listed extension is not a guarantee for every codec variant. Files containing no playable audio are rejected, and there is no video display.

**M4B files are explicitly rejected in Music** (including uppercase extensions and symlink targets), with the message that M4B belongs in Audiobooks. M4B is the only supported audiobook format. Protected Apple Music `.m4p` files, Audible `.aa`/`.aax`, and any network URL are also rejected. There is **no DRM engine, circumvention, streaming, network access, or online metadata lookup**.

### Metadata and artwork

Mutagen reads embedded title, artist, album, album artist, disc/track numbers, year and genre where present. Embedded JPEG/PNG/WebP artwork is displayed locally with Pillow. Untagged or malformed metadata falls back to the filename and a local artwork placeholder. Album/track ordering favours embedded disc and track numbers; filenames are the fallback. Importing large folders may temporarily use the main thread while indexing: this should be profiled before a production release.

### Separate on-disk state

Inside `~/.local/share/linux-epub-reader/` (or `~/.local/share/linux-epub-reader-preview/` in Flatpak Preview):

- `reading_state.json`: remains for EPUB and M4B reading/listening history.
- `music_state.json`: last song, queue order, volume, mute and saved position.
- `music_library.sqlite3`: locally indexed song tags and playlists.
- `mpris-art/`: small local copies of embedded JPEG/PNG covers for lock-screen display.

Music never writes to the original music files. It does not affect EPUB bookmarks or audiobook chapter positions.

### MPRIS, media keys and the lock screen

A local D-Bus **MPRIS2** service (`org.mpris.MediaPlayer2.LinuxEpubReader`, with a distinct `LinuxEpubReaderPreview` name in the Preview build) exposes the **currently active** Music or Audiobook playback state to compatible Linux desktops. It supports Play, Pause, Stop, PlayPause, Next, Previous, Seek and SetPosition, plus title, artist, album, elapsed time and embedded cover artwork where supplied. When an audiobook is active, Next/Previous skip 30 seconds.

This service uses `python3-dbus-next` and the machine's **session bus only**, not the internet. The application still works without it, but desktop media controls will not appear. On Linux Mint Cinnamon, screensaver/lock-screen settings determine whether controls and artwork are displayed. Screen-locking does **not** suspend the computer; actual system suspend/hibernate naturally interrupts playback.

## Dependencies and packaging

**Debian:** `python3`, `python3-tk`, `python3-pil`, `python3-mutagen`, `python3-dbus-next`, `mpv`.

**Standalone Flatpak:** pins a pure-Python Mutagen wheel and a pure-Python dbus-next wheel into the existing bundled Python runtime, with SHA-256 checks and no application network permission. The MPRIS bus name is granted explicitly by the Flatpak manifest. Stable and Preview state directories remain isolated.

**From source:** install `mpv` and the corresponding distribution Python packages for Mutagen, Pillow and dbus-next. When optional metadata or D-Bus libraries are absent, the Music UI still opens, but it uses filename fallbacks or omits media-key support respectively.

## Review and test scope

- Confirm M4B and protected/URL sources never enter the Music backend.
- Verify MP3, FLAC, Ogg, Opus, WAV, AIFF and M4A playback using generated **DRM-free** fixtures, then validate additional codecs supported in each package.
- Verify play/pause/stop/seek/previous/next and automatic track advance; no autoplay when the application first opens.
- Verify music queue, playlists, metadata, embedded artwork and last-track state survive a restart.
- Re-run the existing EPUB, M4B, audio-threading and Flatpak-preview isolation tests; Music must not replace their state.
- Verify MPRIS and Cinnamon lock-screen controls on a physical Linux Mint desktop (not just in a headless test runner).
- Confirm neither Flatpak manifest grants `--share=network` and that no media URI is accepted in Music.

## Source research

The public [VLC user documentation](https://vlc-user-documentation.readthedocs.io/en/latest/) was used as a functional reference for local playback, format breadth and transport conventions. VLC itself has **not** been embedded or linked into this implementation; the existing local `mpv` backend is reused in a separate process to protect the M4B player. [mpv JSON IPC](https://mpv.io/manual/stable/) describes the command and property interface; [Mutagen documentation](https://mutagen.readthedocs.io/en/latest/) describes supported embedded tags; and [MPRIS specification](https://specifications.freedesktop.org/mpris-spec/latest/) defines desktop media controls.

## Limitations and release status

This is a feature-branch implementation for testing, **not** a validated stable release. Decoder coverage depends on each package. Albums are grouped from embedded tags, and playlist creation, addition and deletion work locally; playlist track reordering and M3U export are not yet included. Playlist library importing can block the interface for large folders. MPRIS behaviour on an actual locked Cinnamon desktop and real packaged playback require manual verification before merging.
