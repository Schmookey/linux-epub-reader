# Changelog

## 0.13.0-1 — Continuous reading and chapter progress

- Render all chapters in one continuous reading pane.
- Change the bottom progress bar to measure the active chapter from 0% to 100%; reset it when the next chapter becomes active.
- Synchronise the active chapter heading and contents highlight with the chapter at the top of the reading view.
- Automatically size the contents sidebar to chapter labels and estimated page counts, within sensible limits.
- Add a Mint-green arrow button to hide and restore the sidebar.
- Update chapter navigation, search, bookmarks and reading-position restoration for the continuous view.

## 0.12.0-1 — GitHub-ready rebrand

- Rename the visible application, launcher, source module and documentation to Linux EPUB Reader.
- Keep Linux Mint green as the interface accent, not as the product name.
- Copy legacy reading state and Adobe hand-off settings from ~/.local/share/mint-epub-reader/ on first start when the new state file does not exist.
- Add packaging scripts, synthetic tests, GitHub Actions, documentation and issue templates.
- No Adobe DRM engine is bundled; native in-app Adobe DRM reading remains unsupported.
