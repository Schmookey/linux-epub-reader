# Standalone Flatpak package

This packaging route builds a `.flatpak` application bundle for a GitHub Release. It is **not** a Flathub submission.

## Download and install

Download `linux-epub-reader-VERSION.flatpak` from the project's GitHub Releases page, then run:

```bash
flatpak install --user ./linux-epub-reader-VERSION.flatpak
flatpak run io.github.schmookey.LinuxEpubReader
```

Replace `VERSION` with the version shown on the release page. To remove it:

```bash
flatpak uninstall --user io.github.schmookey.LinuxEpubReader
```

The bundle contains the app, CPython 3.15.2 with Tkinter, Tcl/Tk 9.1.0, and Pillow 13.0.0 for JPEG and other book-cover image formats. It uses the separately installed Freedesktop Platform 26.08 runtime and does **not** bundle that runtime. If the runtime is missing, Flatpak downloads it from Flathub during installation, so the first installation may need internet access. Once installed, the reader itself has no network permission.

## Sandbox and privacy

The manifest does not grant network access. It uses X11 for its Tk window and read-only home access so the existing Tk file chooser can open EPUB files. Reading state stays in `~/.local/share/linux-epub-reader/`; write access is limited to that directory. The home directory is not writable through the broad home permission.

The current Tk file chooser is not portal-based, so opening files outside the home directory may be restricted by the sandbox.

## Build locally

On Linux with Flatpak and flatpak-builder installed:

```bash
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.freedesktop.Platform//26.08 org.freedesktop.Sdk//26.08
flatpak-builder --user --force-clean --install-deps-from=flathub --repo=repo build-dir io.github.schmookey.LinuxEpubReader.yml
mkdir -p dist
flatpak build-bundle repo dist/linux-epub-reader-0.13.8.flatpak io.github.schmookey.LinuxEpubReader --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
```

The GitHub Actions workflows use Ubuntu 26.04 and current major versions of the GitHub Actions (checkout v7, setup-python v7 and upload-artifact v7). Automated tests cover Python 3.12.16 (the current Linux Mint/Ubuntu baseline) and Python 3.15.2. The Flatpak itself is built and smoke-tested with Python 3.15.2, Tcl/Tk 9.1.0 and Freedesktop 26.08. Tcl/Tk source tags are pinned to their upstream release commits; the Python source archive is SHA-256 verified.

The workflow builds the bundle when packaging or application files change, saves a downloadable workflow artifact, and attaches the bundle to newly published releases. To attach a bundle to an existing release, use **Actions → Standalone Flatpak → Run workflow** and supply a source ref and release tag.

## Important notes

- The app ID is `io.github.schmookey.LinuxEpubReader`; it differs from the Debian package name.
- A standalone Flatpak is an app bundle, not a complete operating-system image. The runtime is installed separately.
- The original project licence is CC BY-NC-SA 4.0 as described in `../../LICENSE`. Third-party components retain their own licences; see `THIRD_PARTY_NOTICES.md`.
