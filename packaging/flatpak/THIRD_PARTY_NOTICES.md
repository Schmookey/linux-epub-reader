# Third-party notices for the standalone Flatpak

Linux EPUB Reader's original project materials are covered by the licence notice in the repository's `LICENSE` file. That licence does not replace the separate licences of bundled third-party components.

The Flatpak build includes these additional components:

- **CPython 3.13.18** — bundled interpreter and matching Tkinter extension; licence installed at `share/licenses/python/LICENSE`. Upstream: https://www.python.org/
- **Tcl 8.6.12** — licence terms are installed at `share/licenses/tcl/LICENSE`. Upstream: https://www.tcl-lang.org/
- **Tk 8.6.12** — licence terms are installed at `share/licenses/tk/LICENSE`. Upstream: https://www.tcl-lang.org/
- **Freedesktop Platform 25.08** — Python and base libraries come from the separately installed Flatpak runtime. Notices are provided by that runtime.

The exact source revisions and archive SHA-256 checksums are pinned in `io.github.schmookey.LinuxEpubReader.yml`.
