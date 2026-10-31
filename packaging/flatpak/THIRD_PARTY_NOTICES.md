# Third-party notices for the standalone Flatpak

Linux EPUB Reader's original project code is licensed under GNU GPL version 3 only (GPL-3.0-only); see the repository's `LICENSE` file. This licence does not replace the separate licences of bundled third-party components.

The Flatpak build includes these additional components:

- **Pillow 13.0.0** — bundled Python image decoder for JPEG and other EPUB cover formats; upstream: https://python-pillow.org/

- **CPython 3.15.2** — bundled interpreter and matching Tkinter extension; licence installed at `share/licenses/python/LICENSE`. Upstream: https://www.python.org/
- **Tcl 9.1.0** — source pinned to upstream tag `core-9-1-0`; licence terms are installed at `share/licenses/tcl/LICENSE`. Upstream: https://www.tcl-lang.org/
- **Tk 9.1.0** — source pinned to upstream tag `core-9-1-0`; licence terms are installed at `share/licenses/tk/LICENSE`. Upstream: https://www.tcl-lang.org/
- **Freedesktop Platform 26.08** — Python and base libraries come from the separately installed Flatpak runtime. Notices are provided by that runtime.

The exact Python source archive SHA-256 and Tcl/Tk upstream release commit identifiers are pinned in `io.github.schmookey.LinuxEpubReader.yml`.

- **FFmpeg 9.0.1** — bundled AAC/MP4 demuxing and decoding libraries; configured with network protocols disabled and without GPL components. LGPL-2.1-or-later; the applicable upstream licence is installed at `share/licenses/ffmpeg/COPYING.LGPLv2.1`. Upstream: https://ffmpeg.org/

- **libplacebo 7.360.1** — mpv's required media support library, built without optional shader compiler dependencies. LGPL-2.1-or-later; upstream licence installed at `share/licenses/libplacebo/LICENSE`. Upstream: https://github.com/haasn/libplacebo

- **libass 0.17.5** — subtitle/text rendering dependency of mpv; no subtitle display is enabled by the reader. ISC licence installed at `share/licenses/libass/COPYING`. Upstream: https://github.com/libass/libass

- **mpv 0.41.0** — local audio playback engine; built without GPL features, streaming integrations, scripts or network-enabled FFmpeg. LGPL-2.1-or-later terms installed at `share/licenses/mpv/LICENSE.LGPL`. Upstream: https://mpv.io/
