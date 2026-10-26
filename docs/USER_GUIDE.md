# User guide

## Open a book

Launch Linux EPUB Reader from your desktop menu, or run `python3 src/linux_epub_reader.py` from the repository root. Choose **Open EPUB** (or press `Ctrl+O`) and select an EPUB file.

## Reading and navigation

- The contents panel is on the left; select a heading to navigate.
- Use the mouse wheel or Up/Down arrow keys to scroll the focused pane.
- Press `F11` to enter full-screen mode and `Esc` to leave it.
- The bottom progress indicator represents whole-book progress.
- Search, bookmarks and saved reading position are available from the reader controls.

## Appearance

The default appearance is dark, with soft-white text, Atkinson Hyperlegible when installed, and a Linux Mint-green progress accent. Settings may be adjusted in the application.

## Protected books and ACSM files

The app can detect Adobe ADEPT and Readium LCP protection, but it does not contain an Adobe DRM engine and does not remove DRM. An already-authorised protected book may be handed to a separately installed compatible reader when configured. Network behaviour of external software is outside this app's control.

An `.acsm` file is a fulfilment instruction, not the book itself. This app does not fulfil ACSM files or download books.

## Troubleshooting

Run from a terminal to see diagnostic messages:

```bash
python3 src/linux_epub_reader.py
```

Report reproducible issues using the repository issue templates. Do not upload commercial books, DRM licence files, credentials or private keys.
