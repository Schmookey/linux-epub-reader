# Release checklist

- [x] Application identity and paths use Linux EPUB Reader.
- [x] Chapter text flows continuously in reading order.
- [x] Progress bar reports 0–100% within the active chapter and reaches 100% at its final scroll position.
- [x] Contents sidebar width is measured from chapter/page labels and capped for very long titles.
- [x] Mint-green sidebar toggle hides/restores the left panel without dragging.
- [x] Unit tests cover chapter-progress normalisation and synthetic EPUB parsing.
- [x] Virtual desktop test opens a three-chapter book, checks continuous reading, progress reaching 100%, and sidebar hide/show.
- [x] Debian package built and inspected locally.
- [ ] Test installation and upgrades on a real Linux Mint desktop.
- [ ] Test with a broad selection of non-DRM EPUB files.
- [ ] Verify saved positions/bookmarks on the user's machine after upgrade.
- [ ] Adobe DRM remains unimplemented in-app until a licensed compatible engine is available.
- [ ] Review the selected CC BY-NC-SA 4.0 licence for software-distribution suitability.
