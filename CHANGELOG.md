# Changelog

## 0.13.2-1 — Fixed sidebar layout and sizing

- Replace the draggable pane splitter with a fixed two-column layout so the reading page occupies its own column and does not slide underneath the contents.
- Measure the longest nested chapter label including estimated page count, and size the sidebar dynamically within the available window width.
- Place the Mint-green hide button on the right edge of the sidebar and show a matching reopen button at the reading area's left edge when the sidebar is hidden.
- Add regression tests for sidebar-width calculation.
- Update installer version and instructions.

## 0.13.1 — No external DRM applications

- Replace DRM hand-off behaviour with a local explanatory notice.
- Never launch Adobe Digital Editions, Wine, Thorium Reader, a PDF reader or another external application for protected/unsupported files.
- Keep ACSM handling informational only; no fulfilment, website, download or external-app launch.

## 0.13.0-1 — Continuous reading and chapter progress

- Render all chapters in one continuous reading pane.
- Measure progress within the active chapter from 0% to 100%.
- Synchronise the active chapter heading and contents highlight with the visible chapter.
- Size the left contents sidebar automatically and add a Mint-green show/hide button.
