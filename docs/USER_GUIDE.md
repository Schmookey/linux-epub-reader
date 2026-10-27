# User guide

## Open a book

Launch Linux EPUB Reader from your desktop menu, or run python3 src/linux_epub_reader.py from the repository root. Choose Open book or press Ctrl+O and select an EPUB file.

## Continuous reading and chapter progress

All chapter text is placed in one continuous reading pane, separated by chapter headings. Scroll down to continue into the next chapter; you do not need to select each chapter in the contents. The bottom green progress bar shows your position within the active chapter, from 0% to 100%. It resets when the next chapter becomes active. The active chapter is highlighted in the contents panel.

## Contents panel layout

The contents panel stays on the left, and the reading page occupies the separate right-hand column. The layout does not use a draggable splitter, so the text page should not slide underneath the contents.

The sidebar measures its longest nested chapter label, including the estimated page-count text, and sizes itself to fit when there is enough window space. It leaves a minimum width for the reading area when the window is narrower than the longest title. Use the Mint-green arrow button on the sidebar's right edge to hide it. When hidden, a matching green arrow appears at the left edge of the reading area to restore it.

## Scrolling and full-screen

Use the mouse wheel or Up/Down arrow keys to scroll the pane under the pointer or the pane you last used. Press F11 to enter full-screen mode and Esc to leave it. Full-screen hides the contents and toolbar while retaining the current-chapter progress bar.

## Appearance, search and bookmarks

The default appearance is dark, with soft-white text, Atkinson Hyperlegible when installed, and a Linux Mint-green progress accent. Use A− and A+ to adjust the size. Search, bookmarks and reading-position persistence are available from the reader controls.

## Protected books and ACSM files

The app detects Adobe ADEPT and Readium LCP protection, but it does not contain an Adobe DRM engine and does not remove DRM. When a protected book is selected, the app shows an explanatory message and stops. It will not launch Adobe Digital Editions, Wine, Thorium Reader, a PDF reader or any other external application. The app will not open a website, contact a publisher or fulfil ACSM files.

An ACSM file is a fulfilment instruction, not the book itself. This app does not fulfil ACSM files, download books or launch another program to handle them.

## Troubleshooting

Run from a terminal to see diagnostic messages:

    python3 src/linux_epub_reader.py

Do not upload commercial books, DRM licence files, credentials or private keys to public issues.

## Full-screen exit hint

When you enter full-screen with F11, a small Mint-green **F11 · Exit full-screen** button appears near the bottom of the reading panel. Click it to leave full-screen. The checkbox beside it, **Don't show this again**, saves your choice locally and hides the hint on later full-screen sessions. You can restore it at any time from the **View → Show full-screen exit hint** menu. The keyboard shortcuts F11 and Esc continue to work even when the hint is hidden.
