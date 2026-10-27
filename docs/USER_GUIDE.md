# User guide

## Open a book

Launch Linux EPUB Reader from your desktop menu, or run python3 src/linux_epub_reader.py from the repository root. Choose Open book or press Ctrl+O and select an EPUB file.

## Continuous reading and chapter progress

All chapter text is placed in one continuous reading pane, separated by chapter headings. Scroll down to continue into the next chapter; you do not need to select each chapter in the contents. The bottom green progress bar shows your position within the active chapter, from 0% to 100%. It resets when the next chapter becomes active. The active chapter is highlighted in the contents panel.

## Contents panel

The nested contents panel stays on the left. Its width is calculated from chapter names and estimated page counts, within a maximum width so an exceptionally long title does not take over the window. Use the Mint-green arrow button on the right edge of the panel to hide it; use the arrow at the same edge of the reading area to restore it. You do not need to drag the divider.

## Scrolling and full-screen

Use the mouse wheel or Up/Down arrow keys to scroll the pane under the pointer or the pane you last used. Press F11 to enter full-screen mode and Esc to leave it. Full-screen hides the contents and toolbar while retaining the current-chapter progress bar.

## Appearance, search and bookmarks

The default appearance is dark, with soft-white text, Atkinson Hyperlegible when installed, and a Linux Mint-green progress accent. Use A− and A+ to adjust the size. Search, bookmarks and reading-position persistence are available from the reader controls.

## Protected books and ACSM files

The app detects Adobe ADEPT and Readium LCP protection, but it does not contain an Adobe DRM engine and does not remove DRM. An already-authorised protected book may be handed to a separately installed compatible reader when configured. Network behaviour of external software is outside this app's control.

An ACSM file is a fulfilment instruction, not the book itself. This app does not fulfil ACSM files or download books.

## Troubleshooting

Run from a terminal to see diagnostic messages:

    python3 src/linux_epub_reader.py

Do not upload commercial books, DRM licence files, credentials or private keys to public issues.
