# Changelog

## 0.13.1 — No external DRM applications

- Replace DRM hand-off behaviour with a local explanatory notice.
- Never launch Adobe Digital Editions, Wine, Thorium Reader, a PDF reader or another external application for protected/unsupported files.
- Do not look for local DRM reader executables or run subprocesses for file handling.
- Keep ACSM handling informational only; no fulfilment, website, download or external-app launch.
- Add regression tests for notice text and the absence of external-launch code.

## 0.13.0-1 — Continuous reading and chapter progress

- Render all chapters in one continuous reading pane.
- Measure progress within the active chapter from 0% to 100%.
- Synchronise the active chapter heading and contents highlight with the visible chapter.
- Size the left contents sidebar automatically and add a Mint-green show/hide button.
