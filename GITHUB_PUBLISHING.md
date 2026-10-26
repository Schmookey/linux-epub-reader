# Publishing this repository on GitHub

This bundle is prepared for a GitHub repository, but it has **not** been uploaded to an account. You must sign in to GitHub yourself, create the repository, and push the source.

## 1. Create the empty repository

1. Sign in at <https://github.com/new>.
2. Set the repository name to `linux-epub-reader`.
3. Choose Public or Private.
4. Do not initialise it with a README, `.gitignore` or licence; this bundle already contains the README and `.gitignore`, and the project owner still needs to select a licence.
5. Create the repository and copy its HTTPS URL. It will look like `https://github.com/YOUR-USERNAME/linux-epub-reader.git`.

## 2. Push from Linux Mint

Extract `linux-epub-reader-github-ready.zip`. In a terminal, change into the extracted `linux-epub-reader` directory, then run:

```bash
git init
git add .
git status --short
git commit -m "Prepare Linux EPUB Reader source"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/linux-epub-reader.git
git push -u origin main
```

Replace the example URL with the URL GitHub gave you. Check `git status --short` before committing; the ignore rules exclude generated `.deb` packages, virtual environments, caches and build output. If Git asks you to set your name and email, use your preferred public Git identity. GitHub may ask you to authenticate in a browser or through its credential manager; never put a password or personal access token into source files.

## 3. Before inviting contributions

Read `RELEASE_CHECKLIST.md` and resolve the missing project licence. Review the public files for accuracy and decide whether the project should be public. The current code does not embed an Adobe DRM engine; it must not be advertised as native in-app Adobe DRM support.

## Repository summary

Suggested GitHub description:

> Local-first, dark-mode text-oriented EPUB reader for Linux, with a left-hand contents panel, bookmarks, search and whole-book progress.

Suggested topics: `epub`, `ebook-reader`, `linux`, `python`, `tkinter`, `linux-mint`, `offline-first`.
