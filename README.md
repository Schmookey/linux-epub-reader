# Linux EPUB Reader

A local-first, text-oriented EPUB reader for Linux with a modern dark interface, a left-hand contents panel and Linux Mint-green accents. Original project materials are offered under CC BY-NC-SA 4.0; see LICENSE and LICENSE_STATUS.md for scope and limitations.

> Status: early release for desktop testing. This is not a browser-grade EPUB renderer, and native Adobe DRM support is not implemented.

## Features

- Continuous chapter scrolling: all chapters appear in one reading pane, so you can carry on scrolling instead of selecting each chapter separately.
- Chapter progress from 0% to 100%: the green progress bar and percentage refer to the chapter currently at the top of the reading view. The percentage resets when the next chapter becomes active.
- Left-hand nested contents with current-chapter highlighting and estimated page counts.
- The sidebar width is calculated from the widest chapter/page label, with a cap based on available window width so the reading area remains usable. A Mint-green arrow on the sidebar's right edge opens/closes it; no dragging of a divider is required.
- Dark reading surface, soft-white text, Atkinson Hyperlegible defaults, adjustable text size and approximately 1.5× line spacing.
- Full-screen reading (F11; Esc to exit), with an optional floating Mint-green F11 exit hint and a saved 'Don't show this again' preference. The hint can be restored from the View menu.
- Book metadata, search, bookmarks and saved reading positions.
- Detection of Adobe ADEPT and Readium LCP protected files without attempting to remove protection.

## Current limitations

- This is a text-oriented EPUB reader, not a full browser-grade EPUB renderer. Publisher CSS, illustrations, tables, embedded media, fixed-layout publications and some complex layouts are not rendered faithfully.
- Adobe DRM is not implemented inside this application. It detects protected files, displays an explanatory notice and stops. It never launches Adobe Digital Editions, Wine, Thorium Reader, a PDF reader or any other external application for protected or unsupported files.
- ACSM files are download/fulfilment instructions, not book contents. This application does not fulfil them or contact a publisher.
- Readium LCP-protected files are identified and explained in a notice; no external reader is launched.
- Chapter page counts are estimates unless a publication provides page markers.
- Automated tests are included. Please test on a real Linux Mint desktop before relying on the reader for important books.

## Requirements

- Linux desktop with Python 3 and Tkinter (python3, python3-tk).
- Optional: fonts-atkinson-hyperlegible for the preferred typeface. The reader falls back to available fonts if it is absent.

The app uses Python's standard library and Tkinter; no third-party Python package is required.

## Run from source

From the repository root, run:

    python3 src/linux_epub_reader.py

Run tests:

    python3 -m unittest discover -s tests -v

## Build a Debian package

On Debian or Linux Mint with dpkg-deb available, run:

    bash scripts/build-deb.sh

The Debian package uses gzip compression for broader compatibility with older package managers.

The output is dist/linux-epub-reader_0.13.6-2_all.deb. Install it by double-clicking the deb in the desktop installer, or using:

    sudo apt install ./dist/linux-epub-reader_0.13.6-2_all.deb

## Local data and offline behaviour

Reading state is stored in ~/.local/share/linux-epub-reader/. On first launch, the app attempts to copy saved state from the former ~/.local/share/mint-epub-reader/ directory when corresponding new files do not already exist.

The reader source does not implement HTTP clients or fetch book content. It does not open web pages or download software. Protected and unsupported files trigger a local explanatory message only; no external application is launched.

## Contributing

Please read CONTRIBUTING.md and the issue templates under .github/ISSUE_TEMPLATE/. Do not attach commercial books, DRM licence files, credentials, Adobe IDs or private keys to public issues. Small synthetic test EPUBs are preferred.

## Licence

The project owner selected Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) for original project materials, subject to the scope notes in LICENSE. This does not cover third-party components or books opened with the app. Creative Commons advises against using CC licences for software; the NonCommercial condition may also limit acceptance by some software catalogues. This project should not be represented as OSI-approved open source. See the Creative Commons FAQ at https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software.
