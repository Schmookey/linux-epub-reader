# Linux EPUB Reader

A local-first, text-oriented EPUB reader for Linux with a modern dark interface, a left-hand contents panel and Linux Mint-green accents. The original Linux EPUB Reader project code is licensed under GNU GPL v3.0 only; see LICENSE and LICENSE_STATUS.md. Third-party components retain their own licences.

> Status: early release for desktop testing. This is not a browser-grade EPUB renderer, and native Adobe DRM support is not implemented.

## Features

- Continuous chapter scrolling: all chapters appear in one reading pane, so you can carry on scrolling instead of selecting each chapter separately.
- Chapter progress from 0% to 100%: the green progress bar and percentage refer to the chapter currently at the top of the reading view. The percentage resets when the next chapter becomes active.
- Left-hand nested contents with current-chapter highlighting and estimated page counts.
- The sidebar width is calculated from the widest chapter/page label, with a cap based on available window width so the reading area remains usable. A Mint-green arrow on the sidebar's right edge opens/closes it; no dragging of a divider is required.
- Dark reading surface, soft-white text, Atkinson Hyperlegible defaults, adjustable text size and approximately 1.5× line spacing.
- Full-screen reading (F11; Esc to exit), with an optional floating Mint-green F11 exit hint and a saved 'Don't show this again' preference. The hint can be restored from the View menu.
- Book metadata, search, bookmarks and saved reading positions.
- Local M4B audiobooks in the same application window, with play/pause, stop, seeking, clickable chapter markers on the playback timeline, elapsed/remaining time and separately saved listening positions. Audiobooks open paused; playback never starts automatically. The audiobook mode has no Contents sidebar; EPUB mode retains it.
- A Home dashboard with independent **Last Read**, **Last Listened**, and **Last Played** cards, local artwork, metadata and saved positions. Ebooks, M4B audiobooks and music retain their histories independently.
- A new **Music** mode styled like the EBook and Audiobook sections: open local songs or folders, browse albums and playlists, and use previous/pause/play/stop/next, a seek slider, Mint-green volume control and mute.
- DRM-free local music in MP3, FLAC, Ogg Vorbis, Opus, WAV, M4A/AAC/ALAC, AIFF and other audio containers when supported by the installed mpv/FFmpeg decoder. **M4B is explicitly excluded from Music** and remains exclusive to Audiobooks.
- Music and M4B playback can continue while the application is minimised or while Home/EBook is shown. A local MPRIS2 D-Bus service exposes the active player to media keys and, when the desktop permits, lock-screen controls. See [Music guide](docs/MUSIC.md).
- Detection of Adobe ADEPT and Readium LCP protected files without attempting to remove protection.

## Current limitations

- This is a text-oriented EPUB reader, not a full browser-grade EPUB renderer. Publisher CSS, illustrations, tables, embedded media, fixed-layout publications and some complex layouts are not rendered faithfully.
- Adobe DRM is not implemented inside this application. It detects protected files, displays an explanatory notice and stops. It never launches Adobe Digital Editions, Wine, Thorium Reader, a PDF reader or any other external application for protected or unsupported files.
- ACSM files are download/fulfilment instructions, not book contents. This application does not fulfil them or contact a publisher.
- Readium LCP-protected files are identified and explained in a notice; no external reader is launched.
- Audiobook support is for locally stored, DRM-free M4B files. DRM-protected or unsupported audio is not decrypted or bypassed; it produces a local error notice.
- Music accepts local files only, does not support streaming, and rejects `.m4b`, `.m4p`, `.aa`, `.aax` and network URLs. Playback of less-common audio extensions depends on the codecs bundled in the selected package; file extensions do not guarantee decodability.
- Linux desktop media controls depend on MPRIS/D-Bus availability and desktop settings. Playback and lock-screen controls were verified on Linux Mint Cinnamon during Preview testing; behaviour on other desktops may vary.
- Chapter page counts are estimates unless a publication provides page markers.
- Automated tests are included. Please test on a real Linux Mint desktop before relying on the reader for important books.

## Requirements

- Linux desktop with Python 3 and Tkinter (python3, python3-tk).
- Optional: fonts-atkinson-hyperlegible for the preferred typeface. The reader falls back to available fonts if it is absent.
- For running from source: `mpv` for local audio playback, `mutagen` for embedded music tags and cover artwork, and `dbus-next` for MPRIS media controls. The Debian package declares `mpv`, `python3-mutagen` and `python3-dbus-next` as dependencies.

The app uses Python and Tkinter. Pillow (python3-pil on Debian/Ubuntu) is used for JPEG and other cover-image formats; Tk's built-in decoder remains a fallback for supported image types.

## Run from source

From the repository root, run:

    python3 src/linux_epub_reader.py

Run tests:

    python3 -m unittest discover -s tests -v

## Build a Debian package

On Debian or Linux Mint with dpkg-deb available, run:

    bash scripts/build-deb.sh

The Debian package uses gzip compression for broader compatibility with older package managers.

The output is `dist/linux-epub-reader_0.13.15-1_all.deb`. Install it by double-clicking the package in the desktop installer, or using:

    sudo apt install ./dist/linux-epub-reader_0.13.15-1_all.deb

## Privacy and project boundary

**Linux EPUB Reader is intended to remain offline-only. No cloud implementation is planned or permitted.**

- No user accounts, cloud storage, remote bookmark or reading-position synchronisation, analytics, telemetry, advertising trackers, or automatic crash reports.
- Reading positions, bookmarks, and preferences stay on the user's computer.
- Future language settings, theme options, and accessibility or screen-reader integrations must work locally and offline. Any proposed component must be reviewed to ensure it does not send reading data or other personal data to a remote service.
- Any proposal that introduces network communication or remote data storage is out of scope unless the project owner explicitly changes this requirement.

## Local data and offline behaviour

Stable reading state is stored in `~/.local/share/linux-epub-reader/`. The separate Flatpak Preview uses `~/.local/share/linux-epub-reader-preview/`, resolved from the actual home directory at application launch; it does not import or overwrite stable history. On first stable launch, the app attempts to copy saved state from the former `~/.local/share/mint-epub-reader/` directory when corresponding new files do not already exist. If a state save fails (for example because of disk space or permissions), the reader displays a warning instead of silently assuming the progress was saved.

The reader source does not implement HTTP clients or fetch book content. It does not open web pages or download software. Protected and unsupported files trigger a local explanatory message only; no external application is launched.

## Offline music storage

Music uses separate local `music_library.sqlite3` and `music_state.json` files alongside the existing EPUB/M4B `reading_state.json` in the configured data directory. No music files are modified and no network services are contacted. Refer to [docs/MUSIC.md](docs/MUSIC.md) for music formats, playlists, MPRIS behaviour and testing notes.

The Debian build can read local mounted volumes using the user's ordinary Linux permissions. The Stable and Preview Flatpaks expose `/media`, `/run/media` and `/mnt` **read-only** so the Tk file chooser can open EPUB, M4B and Music files on mounted removable drives; the application cannot change those media files. The app still has no network permission. Consult [Flatpak packaging notes](packaging/flatpak/README.md) for mount paths and troubleshooting.

## Contributing

Please read CONTRIBUTING.md and the issue templates under .github/ISSUE_TEMPLATE/. Do not attach commercial books, DRM licence files, credentials, Adobe IDs or private keys to public issues. Small synthetic test EPUBs are preferred.

## Licence

Linux EPUB Reader's original project code is licensed under the GNU General Public License, version 3 only (GPL-3.0-only). See the full text in LICENSE. This licence applies to the project's original code; third-party libraries, bundled components, fonts, trademarks and books opened with the application remain subject to their own licences and terms. The project does not grant rights to content opened with the reader.
