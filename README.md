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
- Local M4B audiobooks in the same application window, with play/pause, stop, seeking, chapter selection, elapsed/remaining time and separately saved listening positions. Audiobooks open paused; playback never starts automatically.
- An illustrated welcome-back screen with the last book's front cover, available publication details, saved chapter and progress, and a prominent Mint-green Resume button.
- Detection of Adobe ADEPT and Readium LCP protected files without attempting to remove protection.

## Current limitations

- This is a text-oriented EPUB reader, not a full browser-grade EPUB renderer. Publisher CSS, illustrations, tables, embedded media, fixed-layout publications and some complex layouts are not rendered faithfully.
- Adobe DRM is not implemented inside this application. It detects protected files, displays an explanatory notice and stops. It never launches Adobe Digital Editions, Wine, Thorium Reader, a PDF reader or any other external application for protected or unsupported files.
- ACSM files are download/fulfilment instructions, not book contents. This application does not fulfil them or contact a publisher.
- Readium LCP-protected files are identified and explained in a notice; no external reader is launched.
- Audiobook support is for locally stored, DRM-free M4B files. DRM-protected or unsupported audio is not decrypted or bypassed; it produces a local error notice.
- Chapter page counts are estimates unless a publication provides page markers.
- Automated tests are included. Please test on a real Linux Mint desktop before relying on the reader for important books.

## Requirements

- Linux desktop with Python 3 and Tkinter (python3, python3-tk).
- Optional: fonts-atkinson-hyperlegible for the preferred typeface. The reader falls back to available fonts if it is absent.
- Optional for running from source: mpv for local M4B audiobook playback. The Debian package declares mpv as a dependency.

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

The output is dist/linux-epub-reader_0.13.10-1_all.deb. Install it by double-clicking the deb in the desktop installer, or using:

    sudo apt install ./dist/linux-epub-reader_0.13.10-1_all.deb

## Privacy and project boundary

**Linux EPUB Reader is intended to remain offline-only. No cloud implementation is planned or permitted.**

- No user accounts, cloud storage, remote bookmark or reading-position synchronisation, analytics, telemetry, advertising trackers, or automatic crash reports.
- Reading positions, bookmarks, and preferences stay on the user's computer.
- Future language settings, theme options, and accessibility or screen-reader integrations must work locally and offline. Any proposed component must be reviewed to ensure it does not send reading data or other personal data to a remote service.
- Any proposal that introduces network communication or remote data storage is out of scope unless the project owner explicitly changes this requirement.

## Local data and offline behaviour

Reading state is stored in ~/.local/share/linux-epub-reader/. On first launch, the app attempts to copy saved state from the former ~/.local/share/mint-epub-reader/ directory when corresponding new files do not already exist.

The reader source does not implement HTTP clients or fetch book content. It does not open web pages or download software. Protected and unsupported files trigger a local explanatory message only; no external application is launched.

## Contributing

Please read CONTRIBUTING.md and the issue templates under .github/ISSUE_TEMPLATE/. Do not attach commercial books, DRM licence files, credentials, Adobe IDs or private keys to public issues. Small synthetic test EPUBs are preferred.

## Licence

Linux EPUB Reader's original project code is licensed under the GNU General Public License, version 3 only (GPL-3.0-only). See the full text in LICENSE. This licence applies to the project's original code; third-party libraries, bundled components, fonts, trademarks and books opened with the application remain subject to their own licences and terms. The project does not grant rights to content opened with the reader.
