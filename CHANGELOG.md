# Changelog

## 0.13.11-1 — Audiobook player visual and navigation refinement

- Match the audiobook screen more closely to the approved cover-led design, with rounded circular transport controls.
- Add a visible working volume rocker/slider and speaker mute toggle, synchronised with MPV playback state.
- Keep embedded chapter titles in the left Contents panel, replace generic numbered track/file names with Chapter labels, and wrap long titles to fit without horizontal scrolling.
- Highlight the chapter currently playing and retain per-audiobook progress.


## 0.13.10-1 — Resume and full-screen layout fixes

- Restore the reader text frame before packing its chapter heading, preventing Tkinter pack-order errors when resuming a book from the welcome-back panel.
- Keep the illustrated welcome-back panel intact when entering and leaving full-screen without an open book.
- Restore the reader heading, toolbar and normal window controls reliably when leaving full-screen with a book open.
- Add regression tests for welcome-back resume layout and full-screen exit.

## 0.13.9-1 — Illustrated welcome-back panel

- Replace the title-only welcome-back message with a book panel showing the front cover, title, author, publisher, publication date, language, identifier, subjects, chapter count, extracted word count and description when supplied.
- Show the saved chapter, chapter position and estimated overall reading progress, with a prominent Linux Mint-green Resume button.
- Load the last book locally for the welcome preview and reuse the parsed book when resuming; no book contents or reading history leave the computer.
- Improve EPUB 2 and EPUB 3 cover metadata detection and resolve escaped image paths.
- Bundle Pillow in the Flatpak and depend on the distribution's python3-pil package for JPEG cover display; use Tk's native decoder as a fallback for supported formats.


## 0.13.8-1 — Resume last book

- Add a Resume last book action to the toolbar and a welcome-back message showing the last book.
- Save the last successfully opened book's path and title locally; keep each book's chapter, reading position and bookmarks in its existing per-book record.
- Restore the saved chapter and position when resuming, without opening another application or using a network connection.
- If the saved book has moved, let the user locate it again and carry its saved position/bookmarks to the selected path without overwriting existing state.
- Offer a best-effort resume suggestion for existing v0.13.7 reading-state files, which did not record the global last-opened book.
- Add regression tests for resume-state migration, moved files and welcome-back messaging.
- Modernise CI to Ubuntu 26.04 and current GitHub Actions; test Python 3.12.16 and 3.15.2.
- Modernise the standalone Flatpak to CPython 3.15.2, Tcl/Tk 9.1.0 and Freedesktop Platform 26.08, with explicit in-sandbox version checks.


## 0.13.7-1 — Practical welcome and privacy information

- Replace the welcome page with a practical description of reading, contents navigation, search, bookmarks and full-screen controls.
- Explain which reading information is saved, where the local state file is stored, and that the app does not upload reading history.
- Describe the app's privacy-focused design without claiming blanket legal certification of GDPR compliance.
- Reaffirm that the app and future features remain offline-only; no cloud implementation is planned.

## 0.13.3-1 — Optional full-screen exit hint

- Show a floating Mint-green “F11 · Exit full-screen” button near the bottom of the reading panel.
- Add a “Don't show this again” checkbox that saves the preference locally.
- Keep F11 and Esc working regardless of the hint preference.
- Allow the hint to be restored from View → Show full-screen exit hint.
- Add regression tests for initial visibility, saved opt-out and restoring the hint.

## 0.13.2-1 — Fixed sidebar layout and sizing

- Replace the draggable pane splitter with a fixed two-column layout so the reading page occupies its own column and does not slide underneath the contents.
- Measure the longest nested chapter label including estimated page count, and size the sidebar dynamically within the available window width.
- Place the Mint-green hide button on the right edge of the sidebar and show a matching reopen button at the reading area's left edge when the sidebar is hidden.

## 0.13.1 — No external DRM applications

- Replace DRM hand-off behaviour with a local explanatory notice.
- Never launch Adobe Digital Editions, Wine, Thorium Reader, a PDF reader or another external application for protected/unsupported files.
- Keep ACSM handling informational only; no fulfilment, website, download or external-app launch.

## 0.13.0-1 — Continuous reading and chapter progress

- Render all chapters in one continuous reading pane.
- Measure progress within the active chapter from 0% to 100%.
- Synchronise the active chapter heading and contents highlight with the visible chapter.
- Size the left contents sidebar automatically and add a Mint-green show/hide button.
