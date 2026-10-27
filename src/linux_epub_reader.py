#!/usr/bin/env python3
# SPDX-License-Identifier: CC-BY-NC-SA-4.0
"""Linux EPUB Reader v0.13.0 — offline-first, dark EPUB reader with Linux Mint accents.

Uses only Python's standard library and Tkinter. This is a text-oriented reader,
not a full browser-grade EPUB renderer; complex CSS, illustrations and embedded
media are not rendered. Chapter page counts are estimates unless publisher page
markers are supplied.
"""
import os, re, sys, json, zipfile, posixpath, hashlib, html, io, base64, subprocess, shutil, glob
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox, simpledialog
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

APP_NAME = "Linux EPUB Reader"
APP_VERSION = "0.13.0"
APP_BG = "#17191C"
PANEL_BG = "#22252A"
BORDER = "#353941"
MINT_GREEN = "#87CF3E"
MINT_DARK = "#30451F"
MUTED_TEXT = "#AEB4BD"
STATE_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "linux-epub-reader")
STATE_FILE = os.path.join(STATE_DIR, "reading_state.json")
LEGACY_STATE_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "mint-epub-reader")
DEFAULT_BG = "#000000"
DEFAULT_FG = "#E0E0E0"
FONT_NAME = "Atkinson Hyperlegible"
CONTAINER = "META-INF/container.xml"
FONT_OBFUSCATION_ALGORITHMS = {
    "http://www.idpf.org/2008/embedding",
    "http://ns.adobe.com/pdf/enc#RC",
}
# This application never opens web pages or downloads book content.
# DRM hand-off is optional and only launches already-installed local software.
ADOBE_CONFIG_FILE = os.path.join(STATE_DIR, "adobe_drm.json")


def detect_drm_input(path):
    """Identify recognised DRM/licence inputs without altering their protection."""
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".lcpl":
        return "Readium LCP licence"
    if suffix == ".acsm":
        return "Adobe DRM download file"
    if suffix == ".pdf":
        # The text-oriented reader cannot render PDFs itself. Route to local ADE
        # when available instead of trying to parse the file as an EPUB.
        return "PDF document"
    if suffix != ".epub":
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            names = {name.lower() for name in zf.namelist()}
            if "meta-inf/license.lcpl" in names:
                return "Readium LCP-protected EPUB"
            # Adobe ADEPT EPUBs normally include a rights.xml licence alongside
            # encrypted resources. Recognise it before the generic XML checks.
            if "meta-inf/rights.xml" in names:
                return "Adobe DRM-protected EPUB"
            enc_name = next((name for name in zf.namelist() if name.lower() == "meta-inf/encryption.xml"), None)
            if not enc_name:
                return None
            try:
                raw_xml = zf.read(enc_name)
                root = ET.fromstring(raw_xml)
            except ET.ParseError:
                return "possibly encrypted EPUB"
            xml_text = raw_xml.decode("utf-8", errors="ignore").lower()
            if "adept" in xml_text or "adobe.com/adept" in xml_text:
                return "Adobe DRM-protected EPUB"
            for data in root.iter():
                if lname(data.tag) != "EncryptedData":
                    continue
                method = next((el.get("Algorithm", "") for el in data.iter() if lname(el.tag) == "EncryptionMethod"), "")
                refs = [el.get("URI", "") for el in data.iter() if lname(el.tag) == "CipherReference"]
                if method in FONT_OBFUSCATION_ALGORITHMS:
                    continue
                # Font obfuscation is a standard EPUB feature, not book DRM.
                if any(os.path.splitext(uri.split("#", 1)[0])[1].lower() not in (".otf", ".ttf", ".woff", ".woff2") for uri in refs):
                    return "encrypted or DRM-protected EPUB"
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def migrate_legacy_state():
    """Copy settings from an older installation without overwriting newer data."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except OSError:
        return
    for filename in ("reading_state.json", "adobe_drm.json"):
        old_path = os.path.join(LEGACY_STATE_DIR, filename)
        new_path = os.path.join(STATE_DIR, filename)
        if os.path.exists(new_path) or not os.path.isfile(old_path):
            continue
        try:
            shutil.copy2(old_path, new_path)
        except OSError:
            # Reading remains usable if migration is unavailable; state saving
            # will report no user-facing error until the next explicit save.
            pass


def find_adobe_digital_editions():
    """Find a conventional Wine-prefix install of Adobe Digital Editions."""
    config_path = ADOBE_CONFIG_FILE
    try:
        with open(config_path, "r", encoding="utf-8") as stream:
            configured = json.load(stream).get("executable", "")
        if configured and os.path.isfile(configured):
            return os.path.abspath(configured)
    except (OSError, ValueError, TypeError):
        pass

    home = os.path.expanduser("~")
    prefixes = [
        os.path.join(home, ".wine"),
        os.path.join(home, ".wine32"),
        os.path.join(home, ".wine-adobe"),
        os.path.join(home, ".local", "share", "wineprefixes", "adobe"),
        os.path.join(home, ".PlayOnLinux", "wineprefix", "AdobeDigitalEditions"),
    ]
    versions = (
        "Adobe Digital Editions 3.0",
        "Adobe Digital Editions 4.5",
        "Adobe Digital Editions",
    )
    for prefix in prefixes:
        for program_dir in ("Program Files (x86)", "Program Files"):
            for version in versions:
                candidate = os.path.join(prefix, "drive_c", program_dir, "Adobe", version, "Digital Editions.exe")
                if os.path.isfile(candidate):
                    return os.path.abspath(candidate)
    # PlayOnLinux may use a versioned prefix name.
    patterns = [
        os.path.join(home, ".PlayOnLinux", "wineprefix", "*", "drive_c", "Program Files*", "Adobe", "Adobe Digital Editions*", "Digital Editions.exe"),
    ]
    for pattern in patterns:
        for candidate in glob.glob(pattern):
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
    return None


def adobe_wine_prefix(executable):
    """Infer the Wine prefix from the path containing drive_c."""
    path = os.path.abspath(executable)
    parts = path.split(os.sep)
    for index, part in enumerate(parts):
        if part.lower() == "drive_c":
            prefix = os.sep.join(parts[:index]) or os.sep
            return prefix
    return os.path.expanduser("~/.wine")


def wine_windows_path(path, wine_env):
    """Convert a Linux filename to a Windows path usable by ADE under Wine."""
    winepath = shutil.which("winepath") or shutil.which("winepath-stable")
    if winepath:
        try:
            result = subprocess.run(
                [winepath, "-w", os.path.abspath(path)], env=wine_env,
                check=True, capture_output=True, text=True, timeout=5,
            )
            converted = result.stdout.strip()
            if converted:
                return converted
        except (OSError, subprocess.SubprocessError):
            pass
    # Wine's Z: drive commonly maps to the host root filesystem.
    return "Z:" + os.path.abspath(path).replace("/", "\\")


def lname(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def chapter_progress_fraction(position_units, content_units, visible_units):
    """Normalise a viewport position to 0..1 within one chapter.

    Position and length are measured in display lines. A chapter shorter than
    the viewport is considered fully visible; otherwise the last scrollable
    position maps to 100 percent.
    """
    try:
        content = max(0, int(content_units))
        visible = max(0, int(visible_units))
        position = max(0, int(position_units))
    except (TypeError, ValueError):
        return 0.0
    if content == 0:
        return 0.0
    if content <= visible:
        return 1.0
    scrollable = max(1, content - visible)
    return max(0.0, min(1.0, position / scrollable))


class TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "tr", "pre", "figure", "figcaption", "br", "hr"}
    SKIP = {"script", "style", "head", "svg", "noscript", "audio", "video"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0
        self.ids = {}
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
        if self.skip:
            return
        if attrs.get("id"):
            self.ids[attrs["id"]] = len("".join(self.parts))
        if tag in self.BLOCKS:
            self.parts.append("\n\n" if tag != "br" else "\n")
        if tag == "li":
            self.parts.append("• ")
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs); self.handle_endtag(tag)
    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag in self.BLOCKS:
            self.parts.append("\n\n")
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
    def result(self):
        text = "".join(self.parts).replace("\xa0", " ")
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text, self.ids


def extract_markup(raw):
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return parser.result()


def resolve_member(base_dir, href):
    href = (href or "").split("#", 1)[0]
    return posixpath.normpath(posixpath.join(base_dir, href))


class EPUBBook:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.title = os.path.basename(path)
        self.author = ""
        self.publisher = ""
        self.date = ""
        self.language = ""
        self.identifier = ""
        self.description = ""
        self.subjects = []
        self.cover_name = ""
        self.cover_bytes = None
        self.chapters = []
        self.toc = []
        self.page_list = {}
        self._load()

    def _load(self):
        with zipfile.ZipFile(self.path) as zf:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"Damaged EPUB archive entry: {bad}")
            names = set(zf.namelist())
            if CONTAINER not in names:
                raise ValueError("Missing META-INF/container.xml; this file may not be an EPUB.")
            container = ET.fromstring(zf.read(CONTAINER))
            rootfile = next((e.get("full-path") for e in container.iter() if lname(e.tag) == "rootfile" and e.get("full-path")), None)
            if not rootfile or rootfile not in names:
                raise ValueError("Could not locate the EPUB package document.")
            opf = ET.fromstring(zf.read(rootfile))
            opf_dir = posixpath.dirname(rootfile)
            manifest, spine = {}, []
            spine_el = next((e for e in opf.iter() if lname(e.tag) == "spine"), None)
            ncx_id = spine_el.get("toc") if spine_el is not None else None
            for el in opf.iter():
                kind = lname(el.tag)
                if kind == "item" and el.get("id") and el.get("href"):
                    manifest[el.get("id")] = {"href": el.get("href"), "media": el.get("media-type", "").lower(), "properties": el.get("properties", "")}
                elif kind == "itemref" and el.get("idref"):
                    spine.append(el.get("idref"))
            # Extract standard Dublin Core metadata.
            for el in opf.iter():
                tag = lname(el.tag)
                value = clean_text("".join(el.itertext()))
                if not value: continue
                if tag == "title" and self.title == os.path.basename(self.path): self.title = value
                elif tag == "creator" and not self.author: self.author = value
                elif tag == "publisher" and not self.publisher: self.publisher = value
                elif tag == "date" and not self.date: self.date = value
                elif tag == "language" and not self.language: self.language = value
                elif tag == "identifier" and not self.identifier: self.identifier = value
                elif tag == "description" and not self.description: self.description = value
                elif tag == "subject": self.subjects.append(value)
            cover_id = None
            for el in opf.iter():
                if lname(el.tag) == "item" and "cover-image" in el.get("properties", "").split():
                    cover_id = el.get("id")
                if lname(el.tag) == "meta" and el.get("name", "").lower() == "cover":
                    cover_id = el.get("content")
            if cover_id and cover_id in manifest:
                cover_member = resolve_member(opf_dir, manifest[cover_id]["href"])
                if cover_member in names:
                    self.cover_name = posixpath.basename(cover_member)
                    self.cover_bytes = zf.read(cover_member)
            # Load chapter XHTML in the publication's declared reading order.
            member_to_index = {}
            for item_id in spine:
                item = manifest.get(item_id)
                if not item or item["media"] not in ("application/xhtml+xml", "text/html", "application/xml"):
                    continue
                member = resolve_member(opf_dir, item["href"])
                if member not in names: continue
                raw = zf.read(member)
                body, ids = extract_markup(raw)
                if not body: continue
                idx = len(self.chapters)
                member_to_index[member] = idx
                self.chapters.append({"title": "", "text": body, "member": member, "ids": ids, "words": len(body.split()), "publisher_pages": 0})
            if not self.chapters:
                raise ValueError("No readable XHTML chapters were found. This reader currently supports text-oriented, DRM-free EPUBs.")
            # Parse EPUB 3 nav and/or EPUB 2 NCX, retaining nested entries.
            nav_files = [(i, m) for i, m in manifest.items() if "nav" in m.get("properties", "").split()]
            if ncx_id and ncx_id in manifest:
                nav_files.append((ncx_id, manifest[ncx_id]))
            seen_nav = set()
            for _id, item in nav_files:
                nav_member = resolve_member(opf_dir, item["href"])
                if nav_member in seen_nav or nav_member not in names: continue
                seen_nav.add(nav_member)
                try: nav_root = ET.fromstring(zf.read(nav_member))
                except ET.ParseError: continue
                nav_dir = posixpath.dirname(nav_member)
                # EPUB 3: find the nav element marked type=toc; fallback to any nav.
                toc_nodes = []
                for el in nav_root.iter():
                    if lname(el.tag) == "nav":
                        typ = " ".join(v for k, v in el.attrib.items() if lname(k) == "type")
                        if "toc" in typ.split(): toc_nodes.append(el)
                if toc_nodes:
                    def parse_nav_list(list_el):
                        result = []
                        for li in list_el:
                            if lname(li.tag) != "li": continue
                            link = next((x for x in li.iter() if lname(x.tag) in ("a", "content")), None)
                            label = ""
                            target = ""
                            if link is not None:
                                target = link.get("href") or link.get("src") or ""
                                label = clean_text(" ".join(link.itertext()))
                            if not label:
                                label_el = next((x for x in li.iter() if lname(x.tag) == "text"), None)
                                if label_el is not None: label = clean_text(" ".join(label_el.itertext()))
                            target_member = resolve_member(nav_dir, target)
                            child_list = next((x for x in li if lname(x.tag) in ("ol", "ul", "navPoint")), None)
                            node = {"title": label or "Untitled section", "member": target_member, "fragment": target.split("#", 1)[1] if "#" in target else "", "children": parse_nav_list(child_list) if child_list is not None else []}
                            result.append(node)
                        return result
                    nav_el = toc_nodes[0]
                    list_el = next((x for x in nav_el if lname(x.tag) in ("ol", "ul")), None)
                    if list_el is not None:
                        self.toc = parse_nav_list(list_el)
                else:
                    # NCX hierarchy (navMap/navPoint/navLabel/text/content).
                    nav_map = next((x for x in nav_root.iter() if lname(x.tag) == "navMap"), None)
                    if nav_map is not None:
                        def parse_ncx(parent):
                            result = []
                            for point in parent:
                                if lname(point.tag) != "navPoint": continue
                                label_el = next((x for x in point.iter() if lname(x.tag) == "text"), None)
                                content_el = next((x for x in point if lname(x.tag) == "content"), None)
                                target = content_el.get("src", "") if content_el is not None else ""
                                result.append({"title": clean_text(" ".join(label_el.itertext())) if label_el is not None else "Untitled section", "member": resolve_member(nav_dir, target), "fragment": target.split("#", 1)[1] if "#" in target else "", "children": parse_ncx(point)})
                            return result
                        self.toc = parse_ncx(nav_map)
            # Fill chapter titles from TOC targets first, then headings/title.
            def set_titles(nodes):
                for node in nodes:
                    idx = member_to_index.get(node["member"])
                    if idx is not None and not self.chapters[idx]["title"]:
                        self.chapters[idx]["title"] = node["title"]
                    set_titles(node["children"])
            set_titles(self.toc)
            for i, ch in enumerate(self.chapters):
                if not ch["title"]:
                    first = next((line.strip() for line in ch["text"].splitlines() if line.strip()), "")
                    ch["title"] = first[:100] if first else f"Chapter {i+1}"
            # Publisher-defined page-list entries, if present, are retained as metadata.
            for el in opf.iter():
                if lname(el.tag) == "item" and "page-list" in el.get("properties", "").split():
                    page_member = resolve_member(opf_dir, el.get("href", ""))
                    if page_member in names:
                        try:
                            page_root = ET.fromstring(zf.read(page_member))
                            self.page_list = {clean_text(" ".join(a.itertext())): a.get("href", "") for a in page_root.iter() if lname(a.tag) == "a"}
                        except ET.ParseError: pass

    @property
    def word_count(self):
        return sum(ch["words"] for ch in self.chapters)

    def estimate_pages(self, chapter, font_size=11, column_width=700, line_spacing=1.5):
        # Approximation based on characters per line and lines per screen/page.
        # This is deliberately labelled estimated: no fixed page geometry exists in most EPUBs.
        chars_per_line = max(20, int(column_width / max(5.0, font_size * 0.53)))
        lines_per_page = max(8, int((760 / (font_size * 1.35 * line_spacing))))
        chars = len(chapter["text"])
        return max(1, int((chars / (chars_per_line * lines_per_page)) + 0.999))


class Reader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x780")
        self.minsize(800, 520)
        self.configure(background=APP_BG)
        self.book = None
        self.index = 0
        self.font_size = 11
        self.line_spacing = 1.5
        self.column_width = 700
        self.is_fullscreen = False
        self.fullscreen_column = False
        migrate_legacy_state()
        self.state = self._load_state()
        self.current_key = None
        self.chapter_word_offsets = []
        self.chapter_marks = []
        self.rendered_book_key = None
        self.sidebar_visible = True
        self.sidebar_target_width = 270
        self._toc_items = {}
        self._setting_toc_selection = False
        self._search_results = []
        self._build_ui()
        self.bind("<Control-o>", lambda _e: self.open_dialog())
        self.bind("<Control-f>", lambda _e: self.search_dialog())
        self.bind("<Control-b>", lambda _e: self.add_bookmark())
        self.bind("<Control-plus>", lambda _e: self.change_font(1))
        self.bind("<Control-minus>", lambda _e: self.change_font(-1))
        self.bind("<F11>", lambda _e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda _e: self.exit_fullscreen())
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _load_state(self):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except (OSError, ValueError): return {"books": {}}

    def _save_state(self):
        os.makedirs(STATE_DIR, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.state, f, indent=2)
        os.replace(tmp, STATE_FILE)

    def _book_key(self, path):
        return hashlib.sha256(os.path.abspath(path).encode()).hexdigest()[:24]

    def _book_state(self):
        if not self.current_key: return {}
        return self.state.setdefault("books", {}).setdefault(self.current_key, {"path": self.book.path if self.book else "", "chapter": 0, "fraction": 0.0, "bookmarks": []})

    def _build_ui(self):
        # A restrained, modern dark theme with Linux Mint green accents.
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        self.mint_green = MINT_GREEN
        style.configure("TFrame", background=APP_BG)
        style.configure("Panel.TFrame", background=PANEL_BG)
        style.configure("Toolbar.TFrame", background=PANEL_BG)
        style.configure("TLabel", background=APP_BG, foreground=DEFAULT_FG, font=("Sans", 10))
        style.configure("Panel.TLabel", background=PANEL_BG, foreground=DEFAULT_FG, font=("Sans", 10))
        style.configure("Heading.TLabel", background=PANEL_BG, foreground=DEFAULT_FG, font=("Sans", 11, "bold"))
        style.configure("BookTitle.TLabel", background=PANEL_BG, foreground=DEFAULT_FG, font=("Sans", 10, "bold"))
        style.configure("Muted.TLabel", background=APP_BG, foreground=MUTED_TEXT, font=("Sans", 9))
        style.configure("TButton", background=PANEL_BG, foreground=DEFAULT_FG,
                        bordercolor=BORDER, lightcolor=PANEL_BG, darkcolor=PANEL_BG,
                        padding=(11, 7), relief="flat", font=("Sans", 9))
        style.map("TButton",
                  background=[("pressed", MINT_DARK), ("active", "#30353B")],
                  foreground=[("disabled", MUTED_TEXT), ("active", "#FFFFFF")],
                  bordercolor=[("focus", MINT_GREEN)])
        style.configure("LinuxEPUB.Horizontal.TProgressbar", troughcolor="#30343A",
                        background=self.mint_green, bordercolor="#30343A",
                        lightcolor=self.mint_green, darkcolor=self.mint_green,
                        thickness=7, relief="flat")
        style.map("LinuxEPUB.Horizontal.TProgressbar",
                  background=[("disabled", self.mint_green), ("!disabled", self.mint_green)])
        style.configure("SidebarToggle.TButton", background=MINT_GREEN, foreground="#17191C",
                        bordercolor=MINT_GREEN, lightcolor=MINT_GREEN, darkcolor=MINT_GREEN,
                        padding=(5, 8), relief="flat", font=("Sans", 10, "bold"))
        style.map("SidebarToggle.TButton",
                  background=[("pressed", "#6FAF2E"), ("active", "#9BDC59")],
                  foreground=[("active", "#17191C")])
        style.configure("Treeview", background=PANEL_BG, fieldbackground=PANEL_BG,
                        foreground=DEFAULT_FG, bordercolor=PANEL_BG, lightcolor=PANEL_BG,
                        darkcolor=PANEL_BG, rowheight=29, font=("Sans", 10), padding=(5, 3))
        style.map("Treeview", background=[("selected", MINT_DARK)],
                  foreground=[("selected", "#FFFFFF")])
        style.configure("Treeview.Heading", background=PANEL_BG, foreground=DEFAULT_FG,
                        font=("Sans", 9, "bold"), relief="flat")
        style.configure("Vertical.TScrollbar", background=PANEL_BG, troughcolor=APP_BG,
                        bordercolor=APP_BG, arrowcolor=MUTED_TEXT, relief="flat")
        style.configure("Horizontal.TScrollbar", background=PANEL_BG, troughcolor=APP_BG,
                        bordercolor=APP_BG, arrowcolor=MUTED_TEXT, relief="flat")
        style.configure("TPanedwindow", background=APP_BG, sashwidth=5, sashrelief="flat")

        self.toolbar = ttk.Frame(self, padding=(12, 10), style="Toolbar.TFrame")
        self.toolbar.pack(fill=tk.X)
        ttk.Button(self.toolbar, text="Open book…", command=self.open_dialog).pack(side=tk.LEFT)
        ttk.Button(self.toolbar, text="Book details", command=self.show_details).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="Search book", command=self.search_dialog).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="Bookmarks", command=self.show_bookmarks).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="Add bookmark", command=self.add_bookmark).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="A−", width=3, command=lambda: self.change_font(-1)).pack(side=tk.LEFT, padx=(14, 3))
        ttk.Button(self.toolbar, text="A+", width=3, command=lambda: self.change_font(1)).pack(side=tk.LEFT)
        ttk.Button(self.toolbar, text="Full-screen (F11)", command=self.toggle_fullscreen).pack(side=tk.LEFT, padx=(10, 0))
        self.book_label = ttk.Label(self.toolbar, text="No book open", style="BookTitle.TLabel")
        self.book_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(14, 4))

        self.panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.panes.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 6))
        self.left = ttk.Frame(self.panes, padding=10, style="Panel.TFrame")
        self.right = ttk.Frame(self.panes, padding=12, style="Panel.TFrame")
        # Keep the contents pane on the left; its width is fitted to the labels.
        self.panes.add(self.left, weight=0)
        self.panes.add(self.right, weight=1)
        ttk.Label(self.left, text="CONTENTS", style="Heading.TLabel").pack(anchor="w", pady=(2, 10))
        self.toc_tree = ttk.Treeview(self.left, show="tree", selectmode="browse")
        toc_sb = ttk.Scrollbar(self.left, orient=tk.VERTICAL, command=self.toc_tree.yview)
        self.toc_tree.configure(yscrollcommand=toc_sb.set)
        self.toc_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        toc_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.toc_tree.bind("<<TreeviewSelect>>", self._toc_selected)
        self.toc_tree.bind("<Button-1>", self._focus_contents_tree, add="+")
        # Mouse-wheel and arrow-key scrolling for the contents panel.
        self.toc_tree.bind("<MouseWheel>", lambda event: self._on_mousewheel(event, self.toc_tree))
        self.toc_tree.bind("<Button-4>", lambda event: self._on_linux_wheel(event, self.toc_tree))
        self.toc_tree.bind("<Button-5>", lambda event: self._on_linux_wheel(event, self.toc_tree))
        self.toc_tree.bind("<Up>", lambda event: self._on_scroll_arrow(event, self.toc_tree))
        self.toc_tree.bind("<Down>", lambda event: self._on_scroll_arrow(event, self.toc_tree))

        self.sidebar_toggle = ttk.Button(self.right, text="◀", width=2, style="SidebarToggle.TButton",
                                          command=self.toggle_sidebar)
        # The button sits at the reading pane edge: beside the sidebar when open,
        # and still reachable from the left edge when the sidebar is hidden.
        self.sidebar_toggle.place(relx=0.0, rely=0.5, anchor="w", x=0)
        self.heading = ttk.Label(self.right, text="Welcome", style="Heading.TLabel", font=("Sans", 16, "bold"), wraplength=700)
        self.heading.pack(fill=tk.X, anchor="w", pady=(0, 12))
        self.text_frame = tk.Frame(self.right, bg=DEFAULT_BG, bd=0, highlightthickness=0)
        self.text_frame.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(self.text_frame, wrap=tk.WORD, padx=22, pady=20,
            font=(FONT_NAME, self.font_size), foreground=DEFAULT_FG, background=DEFAULT_BG,
            insertbackground=DEFAULT_FG, selectforeground=DEFAULT_BG, selectbackground=DEFAULT_FG,
            spacing1=0, spacing2=0, spacing3=0, relief=tk.FLAT, borderwidth=0,
            highlightthickness=0, state=tk.DISABLED, undo=False, takefocus=True)
        self._apply_line_spacing()
        self.text.place(relx=0.5, rely=0, anchor="n", width=self.column_width, relheight=1)
        self._last_scroll_target = self.text
        self.text_scroll = ttk.Scrollbar(self.text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=self._on_scroll)
        self.text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_frame.bind("<Configure>", self._size_reading_column)
        self.text.tag_configure("search_hit", background="#5A4A12", foreground="#FFFFFF")
        self.text.tag_configure("chapter_heading", foreground=DEFAULT_FG, font=("Sans", 15, "bold"),
                                spacing1=12, spacing3=10)
        self.text.bind("<KeyRelease>", lambda _e: self._schedule_progress_save())
        self.text.bind("<Button-1>", self._focus_reading_text)
        self.text.bind("<ButtonRelease-1>", lambda _e: self._schedule_progress_save())
        # Make the reading pane scroll with a mouse wheel on X11/Linux, Windows and macOS.
        self.text.bind("<MouseWheel>", lambda event: self._on_mousewheel(event, self.text))
        self.text.bind("<Button-4>", lambda event: self._on_linux_wheel(event, self.text))
        self.text.bind("<Button-5>", lambda event: self._on_linux_wheel(event, self.text))
        # The reader is read-only, so provide explicit Up/Down scrolling while it has focus.
        self.text.bind("<Up>", lambda event: self._on_scroll_arrow(event, self.text))
        self.text.bind("<Down>", lambda event: self._on_scroll_arrow(event, self.text))

        self.bottom = ttk.Frame(self, padding=(12, 7, 12, 10), style="Toolbar.TFrame")
        self.bottom.pack(fill=tk.X)
        self.status = ttk.Label(self.bottom, text="Open an EPUB to begin.", style="Muted.TLabel")
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_percent = ttk.Label(self.bottom, text="0% of chapter", width=13, anchor="e", style="Panel.TLabel")
        self.progress_percent.pack(side=tk.RIGHT, padx=(10, 0))
        self.progress = ttk.Progressbar(self.bottom, style="LinuxEPUB.Horizontal.TProgressbar", orient=tk.HORIZONTAL, mode="determinate", maximum=100, length=240)
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(12, 0))
        self.set_text("Welcome to Linux EPUB Reader\n\nOpen an EPUB to begin. Chapters flow continuously in one reading pane, and the green progress bar reports your position within the current chapter from 0% to 100%. Use the contents panel to jump to a chapter, or the Mint-green arrow on the panel edge to hide or restore it. Press F11 for distraction-free full-screen reading. Chapter page counts are estimates unless the publication supplies page markers.\n\nReading defaults: Atkinson Hyperlegible 11 pt, soft-white text on black, approximately 1.5× line spacing, and a medium-width reading column.")

    def _focus_reading_text(self, _event=None):
        """Allow the read-only reading view to receive Up/Down keyboard scrolling."""
        self._last_scroll_target = self.text
        self.after_idle(self.text.focus_set)

    def _focus_contents_tree(self, _event=None):
        """Make the contents panel the keyboard-scroll target after it is clicked."""
        self._last_scroll_target = self.toc_tree
        self.after_idle(self.toc_tree.focus_set)

    def _keyboard_scroll_target(self, fallback):
        """Prefer the pane under the pointer; fall back to the last pane the user scrolled."""
        try:
            node = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
            while node is not None:
                if node is self.text:
                    return self.text
                if node is self.toc_tree:
                    return self.toc_tree
                parent = node.winfo_parent()
                node = self.nametowidget(parent) if parent else None
        except (tk.TclError, KeyError):
            pass
        if getattr(self, "_last_scroll_target", None) in (self.text, self.toc_tree):
            return self._last_scroll_target
        return fallback

    def _scroll_widget(self, widget, direction, steps=1):
        """Scroll a supported vertical pane and refresh reading progress when needed."""
        self._last_scroll_target = widget
        widget.yview_scroll(int(direction * max(1, steps)), "units")
        if widget is self.text:
            self.after_idle(self._update_progress)
        return "break"

    def _on_mousewheel(self, event, widget):
        """Normalise mouse-wheel delta values used by Windows, macOS and X11 Tk builds."""
        delta = getattr(event, "delta", 0) or 0
        if not delta:
            return "break"
        direction = -1 if delta > 0 else 1
        # Most Windows wheels report multiples of 120; some platforms report smaller deltas.
        steps = max(1, int(abs(delta) / 120))
        return self._scroll_widget(widget, direction, steps)

    def _on_linux_wheel(self, event, widget):
        """Handle X11/Linux wheel events, where up/down arrive as buttons 4 and 5."""
        number = getattr(event, "num", 0)
        if number == 4:
            return self._scroll_widget(widget, -1)
        if number == 5:
            return self._scroll_widget(widget, 1)
        return "break"

    def _on_scroll_arrow(self, event, widget):
        """Scroll the pane under the pointer (or last-used pane) with Up/Down."""
        direction = -1 if getattr(event, "keysym", "") == "Up" else 1
        target = self._keyboard_scroll_target(widget)
        return self._scroll_widget(target, direction)

    def _apply_line_spacing(self):
        """Add approximately half a font line of extra space for 1.5× reading."""
        try:
            font = tkfont.Font(root=self, font=(FONT_NAME, self.font_size))
            line_height = int(font.metrics("linespace"))
            extra = max(1, round(line_height * max(0.0, self.line_spacing - 1.0)))
            # spacing2 applies between wrapped display lines; spacing3 supplies
            # the same extra room after logical lines (paragraphs/headings).
            self.text.configure(spacing1=0, spacing2=extra, spacing3=extra)
        except (tk.TclError, ValueError):
            # Keep readable defaults if the selected font's metrics are unavailable.
            self.text.configure(spacing1=0, spacing2=5, spacing3=5)

    def set_text(self, value):
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", value)
        self.text.configure(state=tk.DISABLED)
        self.text.yview_moveto(0)

    def _on_scroll(self, first, last):
        self.text_scroll.set(first, last)
        self.after_idle(self._update_progress)

    def _schedule_progress_save(self):
        self.after(120, self._update_progress)

    def _raw_scroll_fraction(self):
        """Return the saved position as a 0..1 fraction within the active chapter."""
        return self._chapter_fraction()

    def _text_count(self, first, last, unit="displaylines"):
        """Count Tk Text units between two indices, returning zero on unsupported builds."""
        try:
            result = self.text.count(first, last, unit)
            return int(result[0]) if result else 0
        except (tk.TclError, TypeError, ValueError):
            return 0

    def _visible_chapter_index(self):
        """Find the chapter whose start is closest before the top visible text index."""
        if not self.book or not self.chapter_marks:
            return 0
        try:
            top = self.text.index("@1,1")
            active = 0
            for i, marks in enumerate(self.chapter_marks):
                if self.text.compare(top, ">=", marks["start"]):
                    active = i
                else:
                    break
            return max(0, min(len(self.book.chapters) - 1, active))
        except tk.TclError:
            return self.index

    def _chapter_fraction(self):
        """Calculate scroll position within the active chapter, normalised 0..1."""
        if not self.book or not self.chapter_marks or not (0 <= self.index < len(self.chapter_marks)):
            return 0.0
        marks = self.chapter_marks[self.index]
        try:
            top = self.text.index("@1,1")
            start, end = marks["start"], marks["end"]
            if self.text.compare(top, "<=", start):
                position_lines = 0
            elif self.text.compare(top, ">=", end):
                position_lines = self._text_count(start, end, "displaylines")
            else:
                position_lines = self._text_count(start, top, "displaylines")
            chapter_lines = max(1, self._text_count(start, end, "displaylines"))
            height = max(2, self.text.winfo_height() - 3)
            bottom_visible = self.text.index(f"@1,{height}")
            visible_lines = max(1, self._text_count(top, bottom_visible, "displaylines"))
            return chapter_progress_fraction(position_lines, chapter_lines, visible_lines)
        except (tk.TclError, TypeError, ValueError):
            try:
                first, last = self.text.yview()
                scrollable = 1.0 - (last - first)
                return 1.0 if scrollable <= 0.001 else max(0.0, min(1.0, float(first) / scrollable))
            except Exception:
                return 0.0

    def _goto_chapter_fraction(self, index, fraction):
        """Move the continuous reading pane to a saved 0..1 position in one chapter."""
        if not self.book or not self.chapter_marks or not (0 <= index < len(self.chapter_marks)):
            return
        marks = self.chapter_marks[index]
        fraction = max(0.0, min(1.0, float(fraction)))
        chars = self._text_count(marks["start"], marks["end"], "chars")
        try:
            self.text.yview(f"{marks['start']} + {int(chars * fraction)} chars")
        except tk.TclError:
            self.text.yview(marks["start"])

    def _size_reading_column(self, event):
        # Keep the comfortable ~700 px column in normal mode, but let it use
        # the available width in full-screen mode. Font size and spacing stay put.
        available = max(200, event.width - 18)
        width = available if self.fullscreen_column else min(self.column_width, available)
        self.text.place_configure(width=width)

    def _update_progress(self):
        if not self.book or not self.chapter_marks:
            return
        visible_index = self._visible_chapter_index()
        if visible_index != self.index:
            self.index = visible_index
            self.heading.configure(text=self.book.chapters[self.index]["title"])
            self._highlight_toc_index(self.index)
        fraction = self._chapter_fraction()
        percent = int(max(0.0, min(1.0, fraction)) * 100 + 0.5)
        self.progress["value"] = percent
        self.progress_percent.configure(text=f"{percent}% of chapter")
        st = self._book_state()
        st["chapter"] = self.index
        st["fraction"] = fraction
        st["path"] = self.book.path
        pages = self.book.estimate_pages(self.book.chapters[self.index], self.font_size, self.column_width, self.line_spacing)
        self.status.configure(text=f"Chapter {self.index+1} of {len(self.book.chapters)}  •  {percent}% read  •  {pages} estimated pages in this chapter")
        try:
            self._save_state()
        except OSError:
            pass

    def _ensure_toc_left(self):
        """Restore pane order, keeping the contents panel on the left when visible."""
        try:
            existing = list(self.panes.panes())
            if str(self.left) in existing:
                self.panes.forget(self.left)
            if str(self.right) in existing:
                self.panes.forget(self.right)
            if self.sidebar_visible:
                self.panes.add(self.left, weight=0)
            self.panes.add(self.right, weight=1)
            if self.sidebar_visible and not self.is_fullscreen:
                self.after_idle(lambda: self.panes.sashpos(0, self.sidebar_target_width))
        except tk.TclError:
            pass

    def toggle_sidebar(self):
        """Show or hide the contents pane without dragging the splitter."""
        if self.is_fullscreen:
            return
        self.sidebar_visible = not self.sidebar_visible
        self.sidebar_toggle.configure(text="◀" if self.sidebar_visible else "▶")
        self._ensure_toc_left()
        if self.sidebar_visible:
            self.after_idle(self._fit_sidebar_to_contents)
            self.after_idle(self._refresh_reading_column)

    def _fit_sidebar_to_contents(self):
        """Size the contents pane to its widest chapter/page label, within sensible limits."""
        if not hasattr(self, "toc_tree") or not self.book:
            return
        try:
            font = tkfont.Font(root=self, font=("Sans", 10))
            widest = font.measure("CONTENTS")
            def measure_items(parent=""):
                nonlocal widest
                for item in self.toc_tree.get_children(parent):
                    widest = max(widest, font.measure(self.toc_tree.item(item, "text")) + 24)
                    measure_items(item)
            measure_items()
            target = max(230, min(460, widest + 46))
            self.sidebar_target_width = target
            self.left.configure(width=target)
            self.toc_tree.column("#0", width=max(175, target - 55), minwidth=170, stretch=True)
            if self.sidebar_visible and not self.is_fullscreen:
                self.after_idle(lambda: self.panes.sashpos(0, self.sidebar_target_width))
        except (tk.TclError, ValueError):
            pass

    def _highlight_toc_index(self, index):
        """Highlight the contents entry corresponding to the currently visible chapter."""
        self._setting_toc_selection = True
        try:
            for iid, (idx, _fragment) in self._toc_items.items():
                if idx == index:
                    if self.toc_tree.selection() != (iid,):
                        self.toc_tree.selection_set(iid)
                    self.toc_tree.focus(iid)
                    self.toc_tree.see(iid)
                    return
        finally:
            self._setting_toc_selection = False

    def open_dialog(self):
        path = filedialog.askopenfilename(
            title="Open EPUB, PDF or DRM licence",
            filetypes=[
                ("EPUB books", "*.epub"),
                ("PDF books", "*.pdf"),
                ("Readium LCP licences", "*.lcpl"),
                ("Adobe DRM download files (not readable offline)", "*.acsm"),
                ("All files", "*.*"),
            ],
        )
        if path: self.open_book(path)

    def _launch_adobe_digital_editions(self, executable, path):
        """Hand an existing protected book to locally installed ADE under Wine.

        This does not fulfil ACSM files and does not make network requests from
        Linux EPUB Reader. ADE is a separate application and its own network behaviour
        is outside this application's control.
        """
        wine = shutil.which("wine") or shutil.which("wine-stable") or shutil.which("wine64")
        if not wine:
            messagebox.showinfo(
                "Wine is not available",
                "Linux EPUB Reader cannot launch Adobe Digital Editions because Wine was not found.\n\n"
                "This offline-only version will not open websites, download software, or fulfil ACSM files. "
                "Install and configure your authorised reader separately, then try the existing protected EPUB again."
            )
            return
        prefix = adobe_wine_prefix(executable)
        wine_env = os.environ.copy()
        wine_env["WINEPREFIX"] = prefix
        windows_path = wine_windows_path(path, wine_env)
        try:
            subprocess.Popen(
                [wine, os.path.abspath(executable), windows_path],
                env=wine_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            messagebox.showerror(
                "Could not launch Adobe Digital Editions",
                f"Linux EPUB Reader could not start Adobe Digital Editions.\n\n{exc}\n\n"
                "Your book has not been changed. Check that Wine and Adobe Digital Editions are already installed correctly."
            )

    def _offer_adobe_reader(self, path, drm_type):
        """Offer a local Adobe Digital Editions hand-off without online setup."""
        executable = find_adobe_digital_editions()
        wine = shutil.which("wine") or shutil.which("wine-stable") or shutil.which("wine64")
        if executable and wine:
            self._launch_adobe_digital_editions(executable, path)
            return
        if executable and not wine:
            messagebox.showinfo(
                "Wine is needed",
                "An Adobe Digital Editions executable was found, but Wine is not available on the command path.\n\n"
                "Linux EPUB Reader will not open a website or install anything. The book has not been changed."
            )
            return
        detail = (
            f"This file was identified as {drm_type}. Linux EPUB Reader cannot decrypt Adobe-protected books itself. "
            "It can hand an already-authorised EPUB/PDF to an existing Adobe Digital Editions installation running under Wine.\n\n"
            "This offline-only build will not contact Adobe or a publisher, fulfil an ACSM file, open a web page, "
            "or download software. If Digital Editions is already installed, choose its ‘Digital Editions.exe’ file."
        )
        choice = messagebox.askyesnocancel(
            "Adobe DRM reader not configured",
            detail + "\n\nYes: choose an existing Digital Editions.exe\nNo or Cancel: do nothing",
        )
        if choice is not True:
            return
        selected = filedialog.askopenfilename(
            title="Choose existing Adobe Digital Editions executable",
            initialdir=os.path.expanduser("~/.wine/drive_c/Program Files (x86)/Adobe"),
            filetypes=[("Adobe Digital Editions executable", "Digital Editions.exe"), ("Windows programs", "*.exe"), ("All files", "*.*")],
        )
        if not selected:
            return
        if not wine:
            messagebox.showinfo(
                "Wine is needed",
                "Wine was not found. Linux EPUB Reader cannot launch this Windows application.\n\n"
                "No website was opened and nothing was downloaded."
            )
            return
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(ADOBE_CONFIG_FILE, "w", encoding="utf-8") as stream:
                json.dump({"executable": os.path.abspath(selected)}, stream, indent=2)
        except OSError as exc:
            messagebox.showwarning(
                "Could not save Adobe reader setting",
                f"The path was not saved, but you can still try to open the book.\n\n{exc}"
            )
        self._launch_adobe_digital_editions(selected, path)

    def _offer_external_drm_reader(self, path, drm_type):
        """Route protected content only to local software; never open network links."""
        suffix = os.path.splitext(path)[1].lower()
        if drm_type == "Adobe DRM download file" or suffix == ".acsm":
            messagebox.showinfo(
                "ACSM files cannot be read offline",
                "An .acsm file is a fulfilment instruction, not the ebook itself. It does not contain the complete book text.\n\n"
                "Obtaining the associated EPUB/PDF normally requires an online fulfilment step. To respect your offline-only "
                "requirement, Linux EPUB Reader will not launch fulfilment or contact a publisher. Please open the actual, "
                "already-downloaded EPUB/PDF instead."
            )
            return

        if drm_type == "Adobe DRM-protected EPUB" or suffix == ".pdf":
            self._offer_adobe_reader(path, drm_type if suffix != ".pdf" else "PDF document")
            return

        if drm_type in ("Readium LCP licence", "Readium LCP-protected EPUB"):
            detail = (
                "This publication appears to use Readium LCP protection. Linux EPUB Reader cannot decrypt it itself. "
                "If Thorium Reader is already installed, this app can hand the existing file to it. "
                "This app will not open websites or download software."
            )
            thorium = shutil.which("thorium")
            if thorium:
                try:
                    subprocess.Popen([thorium, os.path.abspath(path)], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
                except OSError as exc:
                    messagebox.showerror("Could not launch Thorium Reader", f"{detail}\n\nError: {exc}")
                return
            messagebox.showinfo(
                "Readium LCP publication",
                detail + "\n\nThorium Reader's local command-line launcher was not found. No website was opened."
            )
            return

        detail = (
            "This EPUB contains encrypted content, but Linux EPUB Reader could not identify the protection system. "
            "It will not decrypt, remove or bypass DRM. If you already have an authorised compatible reader installed, "
            "you can try selecting its local executable. This app will not open websites or download software."
        )
        choice = messagebox.askyesnocancel(
            "Encrypted EPUB",
            detail + "\n\nYes: choose Adobe Digital Editions\nNo or Cancel: do nothing",
        )
        if choice is True:
            self._offer_adobe_reader(path, "an encrypted EPUB of an unconfirmed DRM type")

    def open_book(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        drm_type = detect_drm_input(path)
        if drm_type:
            self._offer_external_drm_reader(path, drm_type)
            return
        try:
            book = EPUBBook(path)
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
            messagebox.showerror("Could not open EPUB", str(exc))
            return
        self.book = book
        self.current_key = self._book_key(path)
        st = self._book_state()
        self.index = max(0, min(len(book.chapters) - 1, int(st.get("chapter", 0))))
        self.rendered_book_key = None
        self.chapter_marks = []
        self.title(f"{book.title} — {APP_NAME}")
        self.book_label.configure(text=book.title)
        self._populate_toc()
        self._render_book_text()
        if not self.is_fullscreen:
            self._ensure_toc_left()
        self.show_chapter(self.index, restore=True)
        self.show_details(first_open=True)

    def _populate_toc(self):
        self.toc_tree.delete(*self.toc_tree.get_children())
        self._toc_items = {}
        if not self.book:
            return
        member_to_index = {ch["member"]: i for i, ch in enumerate(self.book.chapters)}
        if self.book.toc:
            def add_nodes(nodes, parent=""):
                for node in nodes:
                    idx = member_to_index.get(node["member"])
                    label = node["title"]
                    if idx is not None:
                        pages = self.book.estimate_pages(self.book.chapters[idx], self.font_size, self.column_width, self.line_spacing)
                        label = f"{label}  ({pages} pp. est.)"
                    iid = self.toc_tree.insert(parent, tk.END, text=label, open=True)
                    self._toc_items[iid] = (idx, node.get("fragment", ""))
                    add_nodes(node.get("children", []), iid)
            add_nodes(self.book.toc)
        else:
            for i, ch in enumerate(self.book.chapters):
                pages = self.book.estimate_pages(ch, self.font_size, self.column_width, self.line_spacing)
                iid = self.toc_tree.insert("", tk.END, text=f"{ch['title']}  ({pages} pp. est.)")
                self._toc_items[iid] = (i, "")
        self._fit_sidebar_to_contents()

    def _toc_selected(self, _event=None):
        if self._setting_toc_selection:
            return
        selected = self.toc_tree.selection()
        if not selected:
            return
        data = self._toc_items.get(selected[0])
        if data and data[0] is not None and (data[0] != self.index or data[1]):
            self.show_chapter(data[0], fragment=data[1])

    def _render_book_text(self):
        """Render all chapters into one continuous text widget and keep chapter marks."""
        if not self.book:
            return
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.tag_remove("search_hit", "1.0", tk.END)
        self.chapter_marks = []
        for i, chapter in enumerate(self.book.chapters):
            if i:
                self.text.insert("end-1c", "\n\n")
            start = f"chapter_start_{i}"
            body = f"chapter_body_{i}"
            end = f"chapter_end_{i}"
            self.text.mark_set(start, "end-1c")
            self.text.mark_gravity(start, "left")
            title_start = self.text.index("end-1c")
            self.text.insert("end-1c", chapter["title"] + "\n\n")
            title_end = self.text.index("end-1c")
            self.text.tag_add("chapter_heading", title_start, title_end)
            self.text.mark_set(body, "end-1c")
            self.text.mark_gravity(body, "left")
            self.text.insert("end-1c", chapter["text"])
            self.text.mark_set(end, "end-1c")
            self.text.mark_gravity(end, "left")
            self.chapter_marks.append({"start": start, "body": body, "end": end})
        self.text.configure(state=tk.DISABLED)
        self.text.yview_moveto(0.0)
        self.rendered_book_key = self.current_key

    def show_chapter(self, index, restore=False, fragment="", fraction=None):
        """Navigate to a chapter inside the continuously scrolling reading pane."""
        if not self.book or not (0 <= index < len(self.book.chapters)):
            return
        if self.rendered_book_key != self.current_key or len(self.chapter_marks) != len(self.book.chapters):
            self._render_book_text()
        self.index = index
        chapter = self.book.chapters[index]
        self.heading.configure(text=chapter["title"])
        self.text.tag_remove("search_hit", "1.0", tk.END)
        if fraction is not None:
            self._goto_chapter_fraction(index, fraction)
        elif restore:
            saved_fraction = float(self._book_state().get("fraction", 0.0))
            self._goto_chapter_fraction(index, saved_fraction)
        elif fragment and fragment in chapter.get("ids", {}):
            offset = max(0, int(chapter["ids"].get(fragment, 0)))
            marks = self.chapter_marks[index]
            try:
                self.text.yview(f"{marks['body']} + {offset} chars")
            except tk.TclError:
                self.text.yview(marks["start"])
        else:
            self.text.yview(self.chapter_marks[index]["start"])
        self._highlight_toc_index(index)
        self.after_idle(self._update_progress)

    def toggle_fullscreen(self):
        if self.is_fullscreen: self.exit_fullscreen(); return
        self.is_fullscreen = True
        self.fullscreen_column = True
        self.toolbar.pack_forget()
        self.panes.pack_configure(padx=0, pady=0)
        if str(self.left) in list(self.panes.panes()):
            self.panes.forget(self.left)
        self.sidebar_toggle.place_forget()
        self.heading.pack_forget()
        self.right.configure(padding=0)
        self.text.configure(padx=28, pady=24)
        self.text_scroll.pack_forget()
        # Keep the current-chapter progress bar and its numeric percentage at the bottom.
        # Hide status/navigation text so the document remains distraction-free.
        self.status.pack_forget()
        self.progress.pack_forget()
        self.progress_percent.pack_forget()
        self.bottom.configure(padding=(8, 2, 8, 4))
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=0, pady=0)
        self.progress_percent.pack(side=tk.RIGHT, padx=(8, 0))
        self.bottom.pack_configure(fill=tk.X, padx=0, pady=0)
        self.attributes("-fullscreen", True)
        self.after_idle(self._refresh_reading_column)

    def _refresh_reading_column(self):
        try:
            self._size_reading_column(type("Event", (), {"width": self.text_frame.winfo_width()})())
        except tk.TclError:
            pass

    def exit_fullscreen(self):
        if not self.is_fullscreen: return
        self.attributes("-fullscreen", False)
        self.is_fullscreen = False
        self.fullscreen_column = False
        self._ensure_toc_left()
        self.panes.pack_configure(padx=10, pady=(8, 6))
        self.sidebar_toggle.configure(text="◀" if self.sidebar_visible else "▶")
        self.sidebar_toggle.place(relx=0.0, rely=0.5, anchor="w", x=0)
        self.right.configure(padding=6)
        self.heading.pack(fill=tk.X, anchor="w", pady=(0, 8), before=self.text_frame)
        self.text.configure(padx=22, pady=20)
        self.text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.toolbar.pack(fill=tk.X, before=self.panes)
        self.bottom.configure(padding=(10, 2, 10, 8))
        self.progress.pack_forget()
        self.progress_percent.pack_forget()
        self.progress_percent.pack(side=tk.RIGHT, padx=(8, 0))
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(12, 0))
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.bottom.pack_configure(fill=tk.X)
        self.after_idle(self._refresh_reading_column)
        if self.sidebar_visible:
            self.after_idle(self._fit_sidebar_to_contents)

    def change_font(self, delta):
        self.font_size = max(8, min(32, self.font_size + delta))
        self.text.configure(font=(FONT_NAME, self.font_size))
        self._apply_line_spacing()
        self._populate_toc()
        self._update_progress()

def show_details(self, first_open=False):
        if not self.book or first_open:
            return
        b = self.book
        win = tk.Toplevel(self)
        win.title("Book details")
        win.geometry("720x540")
        win.configure(background=APP_BG)
        outer = ttk.Frame(win, padding=16, style="Panel.TFrame")
        outer.pack(fill=tk.BOTH, expand=True)
        cover_frame = ttk.Frame(outer)
        cover_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 16))
        self._cover_photo = None
        if b.cover_bytes:
            try:
                try:
                    from PIL import Image, ImageTk
                    im = Image.open(io.BytesIO(b.cover_bytes))
                    im.thumbnail((210, 320))
                    self._cover_photo = ImageTk.PhotoImage(im)
                except ImportError:
                    # Tk's built-in image decoder handles PNG/GIF on common Linux builds.
                    self._cover_photo = tk.PhotoImage(data=base64.b64encode(b.cover_bytes))
                    if self._cover_photo.width() > 210 or self._cover_photo.height() > 320:
                        factor = max(1, self._cover_photo.width() // 210, self._cover_photo.height() // 320)
                        self._cover_photo = self._cover_photo.subsample(factor, factor)
                ttk.Label(cover_frame, image=self._cover_photo).pack(anchor="n")
            except Exception:
                ttk.Label(cover_frame, text=f"Cover included\n({b.cover_name})", width=24).pack(anchor="n")
        else:
            ttk.Label(cover_frame, text="No cover image\nsupplied", width=24).pack(anchor="n")
        info = ttk.Frame(outer)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lines = [f"Title: {b.title}", f"Author: {b.author or 'Not supplied'}", f"Publisher: {b.publisher or 'Not supplied'}", f"Publication date: {b.date or 'Not supplied'}", f"Language: {b.language or 'Not supplied'}", f"Identifier: {b.identifier or 'Not supplied'}", f"Words (extracted): {b.word_count:,}", f"Chapters in reading order: {len(b.chapters)}", f"Cover file: {b.cover_name or 'Not supplied'}"]
        if b.subjects: lines.append("Subjects: " + "; ".join(b.subjects))
        ttk.Label(info, text="\n".join(lines), justify=tk.LEFT, wraplength=410, style="Panel.TLabel").pack(anchor="nw", fill=tk.X)
        if b.description:
            ttk.Label(info, text="Description", style="Heading.TLabel").pack(anchor="w", pady=(14, 3))
            desc = tk.Text(info, height=8, wrap=tk.WORD, font=(FONT_NAME, 10), bg=DEFAULT_BG, fg=DEFAULT_FG, insertbackground=DEFAULT_FG, relief=tk.FLAT, highlightthickness=0)
            desc.pack(fill=tk.BOTH, expand=True)
            desc.insert("1.0", b.description); desc.configure(state=tk.DISABLED)
        ttk.Button(info, text="Close", command=win.destroy).pack(anchor="e", pady=(10, 0))

    def search_dialog(self):
        if not self.book:
            messagebox.showinfo("Search", "Open an EPUB first."); return
        query = simpledialog.askstring("Search book", "Find text in this book:", parent=self)
        if not query: return
        q = query.casefold()
        results = []
        for i, ch in enumerate(self.book.chapters):
            start = 0
            text = ch["text"]
            folded = text.casefold()
            while True:
                pos = folded.find(q, start)
                if pos < 0: break
                excerpt = text[max(0, pos-55):min(len(text), pos+len(query)+85)].replace("\n", " ")
                results.append((i, pos, excerpt))
                start = pos + max(1, len(q))
                if len(results) >= 200: break
            if len(results) >= 200: break
        if not results:
            messagebox.showinfo("Search", f"No results found for: {query}"); return
        win = tk.Toplevel(self); win.title(f"Search results — {query}"); win.geometry("760x420"); win.configure(background=APP_BG)
        ttk.Label(win, text=f"{len(results)} result(s) for “{query}” (showing up to 200)").pack(anchor="w", padx=10, pady=8)
        frame = ttk.Frame(win); frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        lb = tk.Listbox(frame, width=100, height=18, bg=PANEL_BG, fg=DEFAULT_FG, selectbackground=MINT_DARK, selectforeground="#FFFFFF", relief=tk.FLAT, highlightthickness=0, font=("Sans", 10)); sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=lb.yview); lb.configure(yscrollcommand=sb.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.RIGHT, fill=tk.Y)
        for i, pos, excerpt in results: lb.insert(tk.END, f"{self.book.chapters[i]['title']} — …{excerpt}…")
        def jump(_event=None):
            sel = lb.curselection()
            if not sel: return
            i, pos, _excerpt = results[sel[0]]
            self.show_chapter(i)
            self.text.configure(state=tk.NORMAL)
            body_mark = self.chapter_marks[i]["body"]
            start = f"{body_mark} + {pos} chars"
            end = f"{start} + {len(query)} chars"
            self.text.tag_remove("search_hit", "1.0", tk.END)
            self.text.tag_add("search_hit", start, end)
            self.text.see(start)
            self.text.configure(state=tk.DISABLED)
            self._update_progress()
            win.destroy()
        lb.bind("<Double-Button-1>", jump)
        ttk.Button(win, text="Open selected result", command=jump).pack(anchor="e", padx=10, pady=(0, 10))

    def add_bookmark(self):
        if not self.book:
            messagebox.showinfo("Bookmarks", "Open an EPUB first."); return
        label = simpledialog.askstring("Add bookmark", "Bookmark name (optional):", parent=self)
        if label is None: return
        st = self._book_state()
        self._update_progress()
        fraction = self._chapter_fraction()
        st.setdefault("bookmarks", []).append({"label": label.strip() or f"{self.book.chapters[self.index]['title']} — {int(fraction*100)}%", "chapter": self.index, "fraction": fraction})
        self._save_state()
        self.status.configure(text="Bookmark saved.")

    def show_bookmarks(self):
        if not self.book:
            messagebox.showinfo("Bookmarks", "Open an EPUB first."); return
        marks = self._book_state().setdefault("bookmarks", [])
        win = tk.Toplevel(self); win.title("Bookmarks"); win.geometry("640x320"); win.configure(background=APP_BG)
        lb = tk.Listbox(win, bg=PANEL_BG, fg=DEFAULT_FG, selectbackground=MINT_DARK, selectforeground="#FFFFFF", relief=tk.FLAT, highlightthickness=0, font=("Sans", 10)); lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for mark in marks:
            ch = max(0, min(len(self.book.chapters)-1, int(mark.get("chapter", 0))))
            lb.insert(tk.END, f"{mark.get('label', 'Bookmark')} — {self.book.chapters[ch]['title']}")
        def open_mark(_event=None):
            sel = lb.curselection()
            if not sel: return
            mark = marks[sel[0]]
            chapter_index = max(0, min(len(self.book.chapters)-1, int(mark.get("chapter", 0))))
            self.show_chapter(chapter_index, fraction=max(0.0, min(1.0, float(mark.get("fraction", 0.0)))))
            self._update_progress(); win.destroy()
        def remove_mark():
            sel = lb.curselection()
            if not sel: return
            del marks[sel[0]]; self._save_state(); win.destroy(); self.show_bookmarks()
        lb.bind("<Double-Button-1>", open_mark)
        buttons = ttk.Frame(win); buttons.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Open", command=open_mark).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Delete selected", command=remove_mark).pack(side=tk.LEFT, padx=6)

    def on_close(self):
        if self.book: self._update_progress()
        try: self._save_state()
        except OSError: pass
        self.destroy()


def main():
    app = Reader()
    if len(sys.argv) > 1:
        app.after(150, lambda: app.open_book(sys.argv[1]))
    app.mainloop()

if __name__ == "__main__":
    main()
