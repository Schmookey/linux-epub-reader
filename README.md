# Linux EPUB Reader

A local-first, text-oriented EPUB reader for Linux with a modern dark interface, a left-hand contents panel and Linux Mint-green accents. Original project materials are offered under CC BY-NC-SA 4.0; see LICENSE and LICENSE_STATUS.md for scope and limitations.

> Status: early release for desktop testing. This is not a browser-grade EPUB renderer, and native Adobe DRM support is not implemented.

## Features

- Continuous chapter scrolling: all chapters appear in one reading pane, so you can carry on scrolling instead of selecting each chapter separately.
- Chapter progress from 0% to 100%: the bottom green progress bar and percentage refer to the chapter currently at the top of the reading view. The percentage resets when the next chapter becomes active.
- Left-hand nested table of contents, current-chapter highlighting and estimated page counts.
- Sidebar automatically sizes to chapter labels and estimated page counts, within sensible limits. A Mint-green arrow at the right edge of the sidebar hides or restores it without dragging a splitter.
- Dark reading surface, soft-white text, Atkinson Hyperlegible defaults, adjustable text size and approximately 1.5× line spacing.
- Full-screen reading (F11; Esc to exit), mouse-wheel and Up/Down keyboard scrolling.
- Book metadata, search, bookmarks and saved reading positions.
- Detection of Adobe ADEPT and Readium LCP protected files without attempting to remove protection.

## Current limitations

- This is a text-oriented EPUB reader, not a full browser-grade EPUB renderer. Publisher CSS, illustrations, tables, embedded media, fixed-layout publications and some complex layouts are not rendered faithfully.
- Adobe DRM is not implemented inside this application. The app can detect protected files and, where configured, hand an existing Adobe-protected EPUB/PDF to a separately installed Adobe Digital Editions setup under Wine. That external reader has its own dependencies and network behaviour, which this application cannot guarantee or control.
- ACSM files are download/fulfilment instructions, not book contents. This application does not fulfil them or contact a publisher.
- Readium LCP support is a local hand-off to an already-installed Thorium Reader when its command is available; it is not native decryption in this app.
- Chapter page counts are estimates unless a publication provides page markers.
- Automated and virtual-desktop checks are included, but please test on a real Linux Mint desktop before relying on the reader for important books.

## Requirements

- Linux desktop with Python 3 and Tkinter (python3, python3-tk).
- Optional: fonts-atkinson-hyperlegible for the preferred typeface. The reader falls back to available fonts if it is absent.
- Optional, for external protected-book hand-off only: a separately installed and configured compatible reader. Wine and Adobe Digital Editions are not bundled.

The app uses Python's standard library and Tkinter; no third-party Python package is required.

## Run from source

From the repository root, run:

    python3 src/linux_epub_reader.py

Open a book using Open book or press Ctrl+O. For keyboard shortcuts and usage, see docs/USER_GUIDE.md.

Run tests:

    python3 -m unittest discover -s tests -v

## Build a Debian package

On Debian or Linux Mint with dpkg-deb available, run:

    bash scripts/build-deb.sh

The output is dist/linux-epub-reader_0.13.0-1_all.deb. Install it by double-clicking the deb in the desktop installer, or using:

    sudo apt install ./dist/linux-epub-reader_0.13.0-1_all.deb

## Local data and offline behaviour

Reading state is stored in ~/.local/share/linux-epub-reader/. On first launch, the app attempts to copy saved state from the former ~/.local/share/mint-epub-reader/ directory when corresponding new files do not already exist.

The reader source does not implement HTTP clients or fetch book content. It does not open web pages or download software. Handing a protected book to a separate program means that program's network behaviour is outside this project's control. For a strict offline requirement, test with networking disabled and do not use external reader software unless you have separately verified its behaviour.

## Contributing

Please read CONTRIBUTING.md and the issue templates under .github/ISSUE_TEMPLATE/. Do not attach commercial books, DRM licence files, credentials, Adobe IDs or private keys to public issues. Small synthetic test EPUBs are preferred.

## Licence

The project owner selected Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) for original project materials, subject to the scope notes in LICENSE. This does not cover third-party components or books opened with the app. Creative Commons advises against using CC licences for software; the NonCommercial condition may also limit acceptance by some software catalogues. This project should not be represented as OSI-approved open source. See the Creative Commons FAQ at https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software.
