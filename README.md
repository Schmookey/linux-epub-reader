# Linux EPUB Reader

A desktop reader for text-oriented EPUB books, with a modern dark interface and Linux Mint-green accents. It is built with Python 3 and Tkinter and is intended to operate locally without fetching book content or opening web pages. Original project materials are offered under **CC BY-NC-SA 4.0**; see [LICENSE](LICENSE) for scope and terms.

> **Project status:** prepared for public source review; not yet a fully validated release. Please see [current limitations](#current-limitations) before using it for important books.

## Features

- Left-hand table of contents based on the book's navigation where available, including nested entries.
- Dark reading surface with soft-white text, Atkinson Hyperlegible defaults, adjustable text size and line spacing.
- Whole-book progress indicator using Linux Mint green (`#87CF3E`).
- Search, bookmarks, reading-position persistence and book metadata display.
- Full-screen reading mode (`F11`; `Esc` to exit).
- Mouse-wheel and Up/Down keyboard scrolling for the reading pane and contents.
- Detection of Adobe ADEPT and Readium LCP protected files without attempting to remove protection.
- Legacy settings migration from the previous `mint-epub-reader` data directory.

## Current limitations

- **This is a text-oriented EPUB reader, not a complete browser-grade EPUB renderer.** Complex publisher CSS, images, tables, embedded media and some layouts are not rendered faithfully.
- **Adobe DRM is not implemented inside this application.** The app can identify protected files and, where configured, pass an existing Adobe-protected EPUB/PDF to a separately installed Adobe Digital Editions setup under Wine. That external reader has its own dependencies and network behaviour, which this application cannot guarantee or control.
- `.acsm` files are download/fulfilment instructions, not the book itself. This app does not fulfil them or contact a publisher. Open the already-downloaded EPUB/PDF instead.
- Readium LCP support is a local hand-off to an already-installed Thorium Reader when its command is available; it is not native decryption in this app.
- Chapter page counts are estimates unless the publication provides page markers.
- Linux Mint-specific look and feel is tested only at the source/theme level in the available environment. Please test on your own desktop before relying on it.

## Requirements

- Linux desktop with Python 3 and Tkinter (`python3`, `python3-tk`).
- Optional: the `fonts-atkinson-hyperlegible` package for the preferred typeface. The reader falls back to available fonts if it is absent.
- Optional, for external protected-book hand-off only: a separately installed and configured compatible reader. Wine and Adobe Digital Editions are not bundled.

The application uses Python's standard library and Tkinter; there are no third-party Python package dependencies.

## Run from source

From the repository root:

```bash
python3 src/linux_epub_reader.py
```

Open a book with **Open EPUB** or use `Ctrl+O`. For keyboard shortcuts and usage details, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

## Build a Debian package

On Debian or Linux Mint, install the packaging tools (`dpkg-deb` is normally available with `dpkg`), then run:

```bash
./scripts/build-deb.sh
```

The package is written to `dist/linux-epub-reader_0.12.1-1_all.deb`. Install it by opening the `.deb` in the desktop installer, or with:

```bash
sudo apt install ./dist/linux-epub-reader_0.12.1-1_all.deb
```

To remove the package:

```bash
sudo apt remove linux-epub-reader
```

The previous `mint-epub-reader` package, if installed, is a separate package. The new application copies its saved state on first launch without overwriting existing new-format state. The old package can be removed separately after confirming the new app works.

## Local data and offline behaviour

Reading state is stored under:

```text
~/.local/share/linux-epub-reader/
```

On first launch, the app attempts to copy existing `reading_state.json` and `adobe_drm.json` files from `~/.local/share/mint-epub-reader/` if matching new files do not already exist.

The reader source does not implement HTTP clients or fetch book content. It does not open web pages or download software. **Handing a protected book to a separate program means that program's network behaviour is outside this project's control.** For a strict offline requirement, test with networking disabled and do not use external reader software unless you have separately verified its behaviour.

## Contributing and reporting issues

Please read [CONTRIBUTING.md](CONTRIBUTING.md) and the issue templates under `.github/ISSUE_TEMPLATE/`. Do not attach copyrighted books, DRM licences, credentials, Adobe IDs, or private keys to public issues. Minimal synthetic test EPUBs are preferred.

## Licence

The project owner selected **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)** for original project material, subject to the scope notes in [LICENSE](LICENSE). The licence requires attribution, limits licensed use to non-commercial purposes, and requires shared adaptations to use the same or a compatible licence. It does not cover third-party components or the books opened by the reader.

**Software licensing note:** Creative Commons advises against using its licences for software because they were not designed specifically for software and do not include software-specific source-code and patent provisions. This project retains CC BY-NC-SA 4.0 as selected by the project owner; this choice may affect acceptance by software catalogues and compatibility with other projects. See the [Creative Commons FAQ](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software).
