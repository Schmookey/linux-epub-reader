# Pre-release checklist

Before making a public GitHub release or submitting the app to a software catalogue:

- [ ] Choose a project licence, add its complete text as `LICENSE`, and update `LICENSE_STATUS.md`.
- [ ] Set a real maintainer identity/contact in `packaging/debian/control` if a Debian package will be distributed.
- [ ] Test the application on a supported, real Linux Mint desktop.
- [ ] Check opening, scrolling, left-hand contents, full-screen, reading-position restoration and bookmarks with more than one DRM-free EPUB.
- [ ] Verify that any claim about DRM support is limited to the tested external-reader hand-off. No Adobe DRM engine is bundled in this repository.
- [ ] Verify any external DRM application separately with the network disconnected if offline behaviour is a requirement.
- [ ] Check keyboard focus, display scaling, contrast and icon/desktop-entry appearance.
- [ ] Review the source for personal information, test books, licence files, private keys and credentials before publishing.
- [ ] Build the `.deb` from the source and test installation, upgrade, launch and removal on a disposable Linux Mint system.
- [ ] Tag the tested version and attach the corresponding source archive and Debian package to a GitHub Release.
