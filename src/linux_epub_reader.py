#!/usr/bin/env python3
# Copyright (C) 2026 Linux EPUB Reader project contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Linux EPUB Reader v0.13.14 — offline-first, dark EPUB reader with Linux Mint accents.

Uses only Python's standard library and Tkinter. This is a text-oriented reader,
not a full browser-grade EPUB renderer; complex CSS, illustrations and embedded
media are not rendered. Chapter page counts are estimates unless publisher page
markers are supplied.
"""
import os, re, sys, json, zipfile, posixpath, hashlib, html, io, base64, shutil, queue, threading
from urllib.parse import unquote
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox, simpledialog
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

try:
    from audiobook_player import MPVBackend, AudioWorker, AudiobookError, format_time, extract_cover_art
except ImportError:
    MPVBackend = None
    AudioWorker = None
    AudiobookError = RuntimeError
    format_time = lambda value: "0:00"
    extract_cover_art = lambda path: None

APP_NAME = "Linux EPUB Reader"
APP_VERSION = "0.13.14"
APP_BG = "#17191C"
PANEL_BG = "#22252A"
BORDER = "#353941"
MINT_GREEN = "#87CF3E"
MINT_DARK = "#30451F"
MUTED_TEXT = "#AEB4BD"
DEFAULT_STATE_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", "linux-epub-reader")
STATE_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("LINUX_EPUB_READER_STATE_DIR", DEFAULT_STATE_DIR)
))
STATE_FILE = os.path.join(STATE_DIR, "reading_state.json")
DEFAULT_LEGACY_STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "share", "mint-epub-reader"
)
# An alternate preview data directory must never import or modify the stable
# installation's legacy state. The normal installation keeps its migration.
LEGACY_STATE_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get(
        "LINUX_EPUB_READER_LEGACY_STATE_DIR",
        DEFAULT_LEGACY_STATE_DIR if STATE_DIR == DEFAULT_STATE_DIR
        else os.path.join(STATE_DIR, "legacy"),
    )
))

def _unique_state_backup_path(path):
    """Choose a backup name without replacing an earlier recovery copy."""
    base = path + ".corrupt"
    candidate = base
    suffix = 1
    while os.path.exists(candidate):
        candidate = f"{base}.{suffix}"
        suffix += 1
    return candidate


def load_state_file(path):
    """Load saved state, preserving unreadable or structurally invalid files.

    Returns (state, backup_path, writes_blocked, message). A failed backup or
    an ordinary I/O error blocks writes so the original file cannot be lost.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except FileNotFoundError:
        return {"books": {}}, None, False, ""
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        problem = f"The saved-reading file is not valid JSON: {exc}"
    except OSError as exc:
        return {"books": {}}, None, True, f"The saved-reading file could not be read: {exc}"
    else:
        if isinstance(state, dict) and isinstance(state.get("books", {}), dict):
            return state, None, False, ""
        problem = "The saved-reading file has an invalid structure."

    try:
        backup_path = _unique_state_backup_path(path)
        shutil.copy2(path, backup_path)
    except OSError as exc:
        return (
            {"books": {}}, None, True,
            f"{problem}\nA safety copy could not be created: {exc}\n"
            "Saving is disabled to protect the original file.",
        )
    return (
        {"books": {}}, backup_path, False,
        f"{problem}\nA safety copy was created at:\n{backup_path}",
    )


def save_state_file(state, path):
    """Write state atomically, cleaning up the temporary file after failures."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temporary_path = path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise

DEFAULT_BG = "#000000"
DEFAULT_FG = "#E0E0E0"
FONT_NAME = "Atkinson Hyperlegible"
WELCOME_TEXT = """Welcome to Linux EPUB Reader

Linux EPUB Reader is a simple, offline EPUB reader. Open an EPUB file to read it in one continuous reading panel. Use the Contents panel to move between chapters, Search to find text, and Bookmarks to save places you want to return to. Press F11 for full-screen reading and Esc to return.

The app uses Atkinson Hyperlegible in a dark theme, with light text on a black background. You can adjust the text size.

What is saved?
The app saves the book's file location, your current chapter and approximate reading position. When you add a bookmark, it saves its name, chapter and position. Your saved information is updated as you read and when you close the app.

Where is it saved?
Your reading information is kept in a local file on your computer:
~/.local/share/linux-epub-reader/reading_state.json
The file contains reading information, not a copy of the book's text.

Privacy and GDPR
The app is designed to minimise personal data. Reading positions, bookmarks and preferences stay on your computer. There are no accounts, cloud services, analytics or reading-history uploads. The app does not send this information to the developer or other services.

This describes how the application handles data and its privacy-focused design; it is not a blanket legal certification of GDPR compliance."""
CONTAINER = "META-INF/container.xml"
FONT_OBFUSCATION_ALGORITHMS = {
    "http://www.idpf.org/2008/embedding",
    "http://ns.adobe.com/pdf/enc#RC",
}
# This application never opens web pages, fulfils ACSM files, or launches external readers.



def detect_drm_input(path):
    """Identify recognised DRM/licence inputs without altering their protection."""
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".lcpl":
        return "Readium LCP licence"
    if suffix == ".acsm":
        return "Adobe DRM download file"
    if suffix == ".pdf":
        # PDF display is not implemented. The UI explains this and never launches
        # a separate PDF or DRM reader.
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


def drm_notice_for(path, drm_type):
    """Return a local-only notice for an unsupported/protected input.

    Deliberately does not search for, start, or communicate with other software.
    """
    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".acsm" or drm_type == "Adobe DRM download file":
        return (
            "ACSM files cannot be read offline",
            "An .acsm file is a fulfilment instruction, not the ebook itself. It does not contain the complete book text.\n\n"
            "Linux EPUB Reader will not fulfil this file, contact a publisher, open a website, or launch another application. "
            "To respect your offline-only requirement, please open an EPUB or PDF that has already been downloaded; "
            "Adobe DRM-protected files will still not be readable inside this app."
        )
    if suffix == ".pdf" or drm_type == "PDF document":
        return (
            "PDF files are not supported",
            "Linux EPUB Reader currently reads text-oriented EPUB files and cannot display PDFs.\n\n"
            "It will not launch a PDF reader, Adobe Digital Editions, Wine, or any other application. "
            "Your file has not been changed."
        )
    if drm_type == "Readium LCP licence" or suffix == ".lcpl":
        return (
            "Readium LCP book cannot be opened",
            "This file is a Readium LCP licence, not readable book content. Linux EPUB Reader does not fulfil licence files.\n\n"
            "It will not launch Thorium Reader or any other application, open a website, or connect to the internet. "
            "Your file has not been changed."
        )
    if drm_type in ("Readium LCP-protected EPUB", "Adobe DRM-protected EPUB") or "encrypt" in str(drm_type).lower() or "drm" in str(drm_type).lower():
        kind = "Adobe DRM-protected EPUB" if "Adobe" in str(drm_type) else "DRM-protected or encrypted EPUB"
        return (
            "DRM-protected book cannot be opened",
            f"This file appears to be a {kind}. Linux EPUB Reader cannot read this protection format.\n\n"
            "As requested, it will not try to launch Adobe Digital Editions, Wine, Thorium Reader, or any other application. "
            "It will not connect to the internet. Your book has not been changed."
        )
    return (
        "Book cannot be opened",
        "Linux EPUB Reader cannot open this protected or unsupported file.\n\n"
        "It will not launch another application or connect to the internet. Your file has not been changed."
    )


def migrate_legacy_state():
    """Copy settings from an older installation without overwriting newer data."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
    except OSError:
        return
    for filename in ("reading_state.json",):
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


def book_state_key(path):
    """Return the stable per-book key used for locally saved reading state."""
    normalised = os.path.abspath(os.path.expanduser(os.fspath(path)))
    return hashlib.sha256(normalised.encode()).hexdigest()[:24]


def last_opened_book_info(state):
    """Return (path, title, inferred) for the last book, including v0.13.7 state.

    Older state files did not record a global last-opened path. For those files,
    use the last inserted book record as a best-effort starting suggestion. The
    user still chooses whether to resume it.
    """
    if not isinstance(state, dict):
        return "", "", False
    path = state.get("last_opened_book")
    title = state.get("last_opened_title", "")
    inferred = False
    if not path:
        books = state.get("books", {})
        if isinstance(books, dict):
            for record in reversed(list(books.values())):
                if isinstance(record, dict) and record.get("path"):
                    path = record["path"]
                    inferred = True
                    break
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path).strip():
        return "", "", False
    path = os.path.abspath(os.path.expanduser(os.fspath(path)))
    if not title:
        title = os.path.basename(path)
    return path, str(title), inferred


def remember_last_opened_book(state, path, title):
    """Record the last successfully opened book without storing its contents."""
    state["last_opened_book"] = os.path.abspath(os.path.expanduser(os.fspath(path)))
    state["last_opened_title"] = str(title or os.path.basename(path))


def last_opened_item_info(state):
    """Return a validated last-opened EPUB or audiobook record, if present."""
    if not isinstance(state, dict):
        return None
    item = state.get("last_opened_item")
    if not isinstance(item, dict) or item.get("type") not in ("epub", "audiobook"):
        return None
    path = item.get("path")
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path).strip():
        return None
    path = os.path.abspath(os.path.expanduser(os.fspath(path)))
    title = str(item.get("title") or os.path.basename(path))
    return {"type": item["type"], "path": path, "title": title}


def audiobook_records(state):
    """Return the audiobook progress dictionary, repairing only a malformed field."""
    if not isinstance(state, dict):
        return {}
    records = state.get("audiobooks")
    if not isinstance(records, dict):
        records = {}
        state["audiobooks"] = records
    return records


def audiobook_record(state, path):
    """Return one valid per-file progress record without disturbing EPUB state."""
    key = os.path.abspath(os.path.expanduser(os.fspath(path)))
    records = audiobook_records(state)
    record = records.get(key)
    if not isinstance(record, dict):
        record = {}
        records[key] = record
    return record


def restore_book_state_for_moved_file(state, old_path, new_path):
    """Copy saved position/bookmarks to a user-selected replacement path.

    Existing state for the new path is kept intact. The old record is retained
    too, so choosing a different file never destroys the previous reading data.
    """
    old_key = book_state_key(old_path)
    new_key = book_state_key(new_path)
    if old_key == new_key:
        return False
    books = state.setdefault("books", {})
    previous = books.get(old_key)
    if not isinstance(previous, dict) or new_key in books:
        return False
    restored = dict(previous)
    restored["path"] = os.path.abspath(os.path.expanduser(os.fspath(new_path)))
    restored["bookmarks"] = [dict(item) if isinstance(item, dict) else item
                             for item in previous.get("bookmarks", [])]
    books[new_key] = restored
    return True


def saved_book_summary(state, path, book):
    """Summarise the last saved chapter position without changing reading state."""
    books = state.get("books", {}) if isinstance(state, dict) else {}
    record = books.get(book_state_key(path), {}) if isinstance(books, dict) else {}
    if not isinstance(record, dict):
        record = {}
    chapters = getattr(book, "chapters", []) or []
    if not chapters:
        return {
            "chapter_index": 0, "chapter_number": 0, "chapter_count": 0,
            "chapter_title": "Not available", "chapter_percent": 0,
            "overall_percent": 0,
        }
    try:
        index = int(record.get("chapter", 0))
    except (TypeError, ValueError):
        index = 0
    index = max(0, min(len(chapters) - 1, index))
    try:
        fraction = float(record.get("fraction", 0.0))
    except (TypeError, ValueError):
        fraction = 0.0
    fraction = max(0.0, min(1.0, fraction))
    word_counts = [max(0, int(ch.get("words", len(ch.get("text", "").split())))) for ch in chapters]
    total_words = max(1, sum(word_counts))
    words_before = sum(word_counts[:index])
    words_here = word_counts[index]
    overall = int(((words_before + words_here * fraction) / total_words) * 100 + 0.5)
    return {
        "chapter_index": index,
        "chapter_number": index + 1,
        "chapter_count": len(chapters),
        "chapter_title": chapters[index].get("title") or f"Chapter {index + 1}",
        "chapter_percent": int(fraction * 100 + 0.5),
        "overall_percent": max(0, min(100, overall)),
    }


def welcome_text_for_last_book(state):
    """Build the local welcome screen with an optional resume/locate hint."""
    path, title, inferred = last_opened_book_info(state)
    if not path:
        return WELCOME_TEXT
    if os.path.isfile(path):
        message = (
            f"Welcome back!\n\nYour last book was:\n{title}\n\n"
            "Your saved chapter and reading position are ready. Select "
            "“Resume last book” in the toolbar to continue, or choose "
            "“Open book…” to read something else."
        )
    else:
        message = (
            f"Welcome back!\n\nYour last book was:\n{title}\n\n"
            "The book is not currently available at its saved location. "
            "Select “Locate last book…” to find it again. Your saved reading "
            "position and bookmarks will be restored when you select the same book."
        )
    if inferred:
        message += (
            "\n\nThis suggestion was recovered from your earlier reading "
            "history; confirm it is the book you want to resume."
        )
    return message


def lname(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def audiobook_display_chapter_title(title, index):
    """Replace file/track numbering with a useful chapter label, preserving real titles."""
    value = clean_text(str(title or ""))
    value = re.sub(
        r"^(?:(?:audio\s*)?file|track)\s*0*\d+\s*[-:._–—)]*\s*",
        "", value, flags=re.IGNORECASE,
    )
    value = re.sub(r"^0*\d+\s*[-:._–—)]\s*", "", value)
    if not value or re.fullmatch(
        r"(?:chapter|track|file)?\s*#?\s*0*\d+", value, flags=re.IGNORECASE
    ):
        return f"Chapter {int(index) + 1}"
    return value


def wrap_audio_chapter_title(title, font, max_width):
    """Wrap a chapter name by measured pixels so the Contents pane needs no sideways scrolling."""
    value = clean_text(str(title or ""))
    if not value:
        return ""
    width = max(40, int(max_width))
    lines = []
    current = ""

    def split_long_word(word):
        chunks = []
        chunk = ""
        for character in word:
            candidate = chunk + character
            if chunk and font.measure(candidate) > width:
                chunks.append(chunk)
                chunk = character
            else:
                chunk = candidate
        if chunk:
            chunks.append(chunk)
        return chunks

    for word in value.split():
        if not current:
            if font.measure(word) <= width:
                current = word
            else:
                pieces = split_long_word(word)
                lines.extend(pieces[:-1])
                current = pieces[-1]
            continue
        candidate = current + " " + word
        if font.measure(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            if font.measure(word) <= width:
                current = word
            else:
                pieces = split_long_word(word)
                lines.extend(pieces[:-1])
                current = pieces[-1]
    if current:
        lines.append(current)
    return "\n".join(lines)


def sidebar_width_for_labels(label_widths, available_width, minimum_width=250, reading_min_width=520, padding=72):
    """Calculate a measured sidebar width while leaving room for the reading pane.

    label_widths are measured text widths including nested-tree indentation. The
    width has no fixed maximum; the available window width limits it instead.
    """
    try:
        widths = [max(0, int(width)) for width in label_widths]
        available = max(0, int(available_width))
        minimum = max(1, int(minimum_width))
        keep_reading = max(1, int(reading_min_width))
        extra = max(0, int(padding))
    except (TypeError, ValueError):
        return max(1, int(minimum_width))
    required = max([width for width in widths] + [0]) + extra
    maximum = max(minimum, available - keep_reading)
    return max(minimum, min(required, maximum))


def sidebar_column_minimum(sidebar_visible, is_fullscreen, target_width):
    """Return zero for hidden/full-screen contents so its grid column cannot reserve space."""
    if is_fullscreen or not sidebar_visible:
        return 0
    try:
        return max(0, int(target_width))
    except (TypeError, ValueError):
        return 0

def fullscreen_hint_should_show(state, is_fullscreen):
    """Whether to show the floating F11 hint for the current fullscreen session."""
    return bool(is_fullscreen and not state.get("hide_fullscreen_hint", False))


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
        # Short chapters may fit on one screen, but must still start at 0%.
        # Their progress is based on how far the viewport has crossed the chapter.
        return max(0.0, min(1.0, position / max(1, content)))
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
    """Resolve an EPUB-relative resource path, including escaped filenames."""
    href = unquote((href or "").split("#", 1)[0].split("?", 1)[0])
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
            # EPUB 3 uses the cover-image manifest property; EPUB 2 commonly
            # points to the cover item through a <meta name="cover"> entry.
            cover_ids = []
            for el in opf.iter():
                if lname(el.tag) == "item" and "cover-image" in el.get("properties", "").split():
                    if el.get("id"):
                        cover_ids.insert(0, el.get("id"))
                elif lname(el.tag) == "meta":
                    if el.get("name", "").lower() == "cover" and el.get("content"):
                        cover_ids.append(el.get("content"))
                    elif el.get("property", "").lower() in ("cover", "cover-image") and el.get("content"):
                        cover_ids.append(el.get("content"))
            cover_items = [manifest[item_id] for item_id in cover_ids if item_id in manifest]
            if not cover_items:
                # Be tolerant of older/less complete EPUBs that omit the formal
                # cover declaration but use an obvious cover filename or id.
                cover_items = [
                    item for item_id, item in manifest.items()
                    if item["media"].startswith("image/")
                    and "cover" in (item_id + " " + item["href"]).lower()
                ]
            if not cover_items:
                cover_items = [
                    item for item in manifest.values()
                    if item["media"].startswith("image/")
                ][:1]
            for item in cover_items:
                cover_member = resolve_member(opf_dir, item["href"])
                if cover_member in names:
                    self.cover_name = posixpath.basename(cover_member)
                    self.cover_bytes = zf.read(cover_member)
                    break
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
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("1180x780")
        self.minsize(800, 520)
        self.configure(background=APP_BG)
        self.book = None
        self.audio_worker = AudioWorker() if MPVBackend and AudioWorker else None
        # Retain this availability flag for the existing player UI.
        self.audio_backend = self.audio_worker
        self.audio_path = None
        self.audio_title = ""
        self.audio_tick_id = None
        self.audio_chapters = []
        self.audio_screen = None
        self.audio_is_active = False
        self.audio_seeking = False
        self.audio_volume_dragging = False
        self._audio_toc_entries = []
        self._audio_load_token = 0
        self._audio_load_poll_id = None
        self.audio_loading = False
        self._audio_close_requested = False
        self._last_audio_status = None
        self._pending_audio_chapter_index = None
        self.index = 0
        self.font_size = 11
        self.line_spacing = 1.5
        self.column_width = 700
        self.is_fullscreen = False
        migrate_legacy_state()
        self._state_recovery_backup = None
        self._state_write_blocked = False
        self._state_recovery_message = ""
        self.state = self._load_state()
        self.hide_fullscreen_hint_var = tk.BooleanVar(
            value=bool(self.state.get("hide_fullscreen_hint", False))
        )
        self.show_fullscreen_hint_var = tk.BooleanVar(
            value=not bool(self.state.get("hide_fullscreen_hint", False))
        )
        self.current_key = None
        self.chapter_word_offsets = []
        self.chapter_marks = []
        self.rendered_book_key = None
        self.sidebar_visible = True
        self.sidebar_target_width = 290
        self._toc_items = {}
        self._setting_toc_selection = False
        self._search_results = []
        self.last_book_preview = None
        self.last_book_preview_path = ""
        self.last_book_preview_error = ""
        self._welcome_cover_photo = None
        self._build_ui()
        self._refresh_resume_ui()
        # Audiobooks never start automatically: the welcome panel asks before resuming.
        if self._state_recovery_message:
            messagebox.showwarning(
                "Saved reading data needs attention",
                self._state_recovery_message,
                parent=self,
            )
        self.bind("<Control-o>", lambda _e: self.open_dialog())
        self.bind("<Control-f>", lambda _e: self.search_dialog())
        self.bind("<Control-b>", lambda _e: self.add_bookmark())
        self.bind("<Control-plus>", lambda _e: self.change_font(1))
        self.bind("<Control-minus>", lambda _e: self.change_font(-1))
        self.bind("<F11>", lambda _e: self.toggle_fullscreen())
        self.bind("<Escape>", lambda _e: self.exit_fullscreen())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._audio_load_poll_id = self.after(100, self._poll_audio_load_queue)

    def _load_state(self):
        state, backup_path, writes_blocked, message = load_state_file(STATE_FILE)
        self._state_recovery_backup = backup_path
        self._state_write_blocked = writes_blocked
        self._state_recovery_message = message
        return state

    def _save_state(self):
        if self._state_write_blocked:
            raise OSError(
                "Saving is disabled because the original reading-state file "
                "could not be safely backed up or read."
            )
        save_state_file(self.state, STATE_FILE)

    def _book_key(self, path):
        return book_state_key(path)

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
        style.configure("FullscreenHint.TFrame", background=PANEL_BG, relief="solid", borderwidth=1)
        style.configure("FullscreenHint.TCheckbutton", background=PANEL_BG, foreground=DEFAULT_FG,
                        font=("Sans", 9))
        style.map("FullscreenHint.TCheckbutton",
                  background=[("active", PANEL_BG)], foreground=[("active", DEFAULT_FG)])
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
        self.resume_button = ttk.Button(
            self.toolbar, text="Resume last book", command=self.resume_last_book, state=tk.DISABLED
        )
        self.resume_button.pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="Book details", command=self.show_details).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="Search book", command=self.search_dialog).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="Bookmarks", command=self.show_bookmarks).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="Add bookmark", command=self.add_bookmark).pack(side=tk.LEFT, padx=(7, 0))
        ttk.Button(self.toolbar, text="A−", width=3, command=lambda: self.change_font(-1)).pack(side=tk.LEFT, padx=(14, 3))
        ttk.Button(self.toolbar, text="A+", width=3, command=lambda: self.change_font(1)).pack(side=tk.LEFT)
        ttk.Button(self.toolbar, text="Full-screen (F11)", command=self.toggle_fullscreen).pack(side=tk.LEFT, padx=(10, 0))
        self.book_label = ttk.Label(self.toolbar, text="No book open", style="BookTitle.TLabel")
        self.book_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(14, 4))
        ttk.Button(self.toolbar, text="Audiobook", command=self.open_audiobook_dialog).pack(side=tk.RIGHT, padx=(8, 0))

        # The View menu makes the fullscreen hint preference reversible later.
        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_checkbutton(
            label="Show full-screen exit hint",
            variable=self.show_fullscreen_hint_var,
            command=self._set_fullscreen_hint_from_menu,
        )
        menubar.add_cascade(label="View", menu=view_menu)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About Linux EPUB Reader", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menubar)

        # Use a fixed grid rather than a draggable Panedwindow. This keeps the
        # contents column independent of the reading column and prevents overlap.
        self.panes = ttk.Frame(self)
        self.panes.pack(fill=tk.BOTH, expand=True, padx=10, pady=(8, 6))
        self.panes.grid_rowconfigure(0, weight=1)
        self.panes.grid_columnconfigure(0, weight=0, minsize=self.sidebar_target_width)
        self.panes.grid_columnconfigure(1, weight=1)
        self.left = ttk.Frame(self.panes, padding=10, style="Panel.TFrame", width=self.sidebar_target_width)
        self.left.grid(row=0, column=0, sticky="nsew")
        self.left.grid_propagate(False)
        self.right = ttk.Frame(self.panes, padding=12, style="Panel.TFrame")
        self.right.grid(row=0, column=1, sticky="nsew")
        self.panes.bind("<Configure>", self._panes_configured, add="+")
        ttk.Label(self.left, text="CONTENTS", style="Heading.TLabel").pack(anchor="w", pady=(2, 10))
        self.toc_container = ttk.Frame(self.left, style="Panel.TFrame")
        self.toc_container.pack(fill=tk.BOTH, expand=True)
        self.toc_container.grid_rowconfigure(0, weight=1)
        self.toc_container.grid_columnconfigure(0, weight=1)
        self.toc_tree = ttk.Treeview(self.toc_container, show="tree", selectmode="browse")
        toc_sb = ttk.Scrollbar(self.toc_container, orient=tk.VERTICAL, command=self.toc_tree.yview)
        self.toc_tree.configure(yscrollcommand=toc_sb.set)
        self.toc_tree.grid(row=0, column=0, sticky="nsew")
        toc_sb.grid(row=0, column=1, sticky="ns")
        # This green control is on the sidebar's right edge, not over the page text.
        self.sidebar_toggle = ttk.Button(
            self.toc_container, text="◀", width=2, style="SidebarToggle.TButton",
            command=self.toggle_sidebar,
        )
        self.sidebar_toggle.grid(row=0, column=2, sticky="ns", padx=(6, 0))
        self.toc_tree.bind("<<TreeviewSelect>>", self._toc_selected)
        self.toc_tree.bind("<Button-1>", self._focus_contents_tree, add="+")
        # Mouse-wheel and arrow-key scrolling for the contents panel.
        self.toc_tree.bind("<MouseWheel>", lambda event: self._on_mousewheel(event, self.toc_tree))
        self.toc_tree.bind("<Button-4>", lambda event: self._on_linux_wheel(event, self.toc_tree))
        self.toc_tree.bind("<Button-5>", lambda event: self._on_linux_wheel(event, self.toc_tree))
        self.toc_tree.bind("<Up>", lambda event: self._on_scroll_arrow(event, self.toc_tree))
        self.toc_tree.bind("<Down>", lambda event: self._on_scroll_arrow(event, self.toc_tree))

        self.sidebar_reopen_toggle = ttk.Button(
            self.right, text="▶", width=2, style="SidebarToggle.TButton",
            command=self.toggle_sidebar,
        )
        self.sidebar_reopen_toggle.place_forget()
        self.reader_body = ttk.Frame(self.right, style="Panel.TFrame")
        self.reader_body.pack(fill=tk.BOTH, expand=True)
        self.heading = ttk.Label(self.reader_body, text="Welcome", style="Heading.TLabel", font=("Sans", 16, "bold"), wraplength=700)
        self.heading.pack(fill=tk.X, anchor="w", pady=(0, 12))
        self.text_frame = tk.Frame(self.reader_body, bg=APP_BG, bd=0, highlightthickness=0)
        self.text_frame.pack(fill=tk.BOTH, expand=True)
        self.reading_area = tk.Frame(self.text_frame, bg=APP_BG, bd=0, highlightthickness=0)
        self.reading_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text_surface = tk.Frame(self.reading_area, bg=DEFAULT_BG, bd=0, highlightthickness=0)
        # Let the reading surface follow its parent instead of placing it at a fixed
        # pixel width. This keeps book text fitted to the available panel when the
        # window enters/exits full-screen or is resized.
        self.text_surface.pack(fill=tk.BOTH, expand=True)
        self.text = tk.Text(self.text_surface, wrap=tk.WORD, padx=22, pady=20,
            font=(FONT_NAME, self.font_size), foreground=DEFAULT_FG, background=DEFAULT_BG,
            insertbackground=DEFAULT_FG, selectforeground=DEFAULT_BG, selectbackground=DEFAULT_FG,
            spacing1=0, spacing2=0, spacing3=0, relief=tk.FLAT, borderwidth=0,
            highlightthickness=0, state=tk.DISABLED, undo=False, takefocus=True)
        self.text.pack(fill=tk.BOTH, expand=True)
        self._apply_line_spacing()
        self._last_scroll_target = self.text
        self.text_scroll = ttk.Scrollbar(self.text_frame, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=self._on_scroll)
        self.text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.welcome_view = tk.Frame(self.reader_body, bg=APP_BG, bd=0, highlightthickness=0)
        self.audio_screen = tk.Frame(self.reader_body, bg=APP_BG, bd=0, highlightthickness=0)
        self._build_audiobook_screen()
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

        # A floating, optional F11 reminder sits over the lower edge of the reading pane.
        self.fullscreen_hint = ttk.Frame(self.reader_body, padding=(10, 7), style="FullscreenHint.TFrame")
        ttk.Button(
            self.fullscreen_hint, text="F11 · Exit full-screen",
            style="SidebarToggle.TButton", command=self.exit_fullscreen,
        ).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Checkbutton(
            self.fullscreen_hint, text="Don't show this again",
            style="FullscreenHint.TCheckbutton", variable=self.hide_fullscreen_hint_var,
            command=self._set_fullscreen_hint_from_checkbox,
        ).pack(side=tk.LEFT)
        self.fullscreen_hint.place_forget()

        self.bottom = ttk.Frame(self, padding=(12, 7, 12, 10), style="Toolbar.TFrame")
        self.bottom.pack(fill=tk.X)
        self.status = ttk.Label(self.bottom, text="Open an EPUB to begin.", style="Muted.TLabel")
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.progress_percent = ttk.Label(self.bottom, text="0% of chapter", width=13, anchor="e", style="Panel.TLabel")
        self.progress_percent.pack(side=tk.RIGHT, padx=(10, 0))
        self.progress = ttk.Progressbar(self.bottom, style="LinuxEPUB.Horizontal.TProgressbar", orient=tk.HORIZONTAL, mode="determinate", maximum=100, length=240)
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(12, 0))

    def show_about(self):
        """Show the running application version so installed builds are easy to verify."""
        messagebox.showinfo(
            f"About {APP_NAME}",
            f"{APP_NAME} v{APP_VERSION}\\n\\n"
            "Offline-first EPUB reader with a continuous reading pane, chapter progress, "
            "a collapsible contents panel and Mint-green full-screen controls.\\n\\n"
            "Adobe DRM is not supported. Protected files are never sent to another application "
            "or opened online.",
            parent=self,
        )

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
        """Lay out the reading area beside a fixed-width, left-hand contents panel."""
        try:
            self.panes.grid_rowconfigure(0, weight=1)
            self.panes.grid_columnconfigure(1, weight=1)
            self.panes.grid_columnconfigure(
                0,
                minsize=sidebar_column_minimum(
                    self.sidebar_visible, self.is_fullscreen, self.sidebar_target_width
                ),
                weight=0,
            )
            if self.sidebar_visible and not self.is_fullscreen:
                self.left.grid()
                self.left.configure(width=self.sidebar_target_width)
                self.sidebar_toggle.grid()
                self.sidebar_reopen_toggle.place_forget()
                self.reader_body.pack_configure(padx=0)
            else:
                self.left.grid_remove()
                self.panes.grid_columnconfigure(0, minsize=0, weight=0)
                if self.is_fullscreen:
                    self.sidebar_toggle.grid_remove()
                    self.sidebar_reopen_toggle.place_forget()
                    self.reader_body.pack_configure(padx=0)
                else:
                    self.sidebar_reopen_toggle.place(relx=0.0, rely=0.5, anchor="w", x=0)
                    self.reader_body.pack_configure(padx=(36, 0))
        except tk.TclError:
            pass

    def toggle_sidebar(self):
        """Show or hide the contents panel using the green edge button."""
        if self.is_fullscreen:
            return
        self.sidebar_visible = not self.sidebar_visible
        self._ensure_toc_left()
        if self.sidebar_visible:
            self.after_idle(self._fit_sidebar_to_contents)

    def _panes_configured(self, _event=None):
        """Re-fit the contents pane when the application window changes size."""
        if self.book and self.sidebar_visible and not self.is_fullscreen:
            self.after_idle(self._fit_sidebar_to_contents)

    def _fit_sidebar_to_contents(self):
        """Fit the longest nested contents label while leaving space for reading."""
        if not hasattr(self, "toc_tree") or not self.book:
            return
        try:
            font = tkfont.Font(root=self, font=("Sans", 10))
            widths = [font.measure("CONTENTS")]
            # ttk.Treeview has no public "indent" option; estimate its disclosure indentation.
            indent_width = 18

            def measure_items(parent="", depth=0):
                for item in self.toc_tree.get_children(parent):
                    label = self.toc_tree.item(item, "text")
                    widths.append(font.measure(label) + depth * indent_width)
                    measure_items(item, depth + 1)

            measure_items()
            available = max(260, int(self.panes.winfo_width()))
            target = sidebar_width_for_labels(
                widths, available_width=available,
                minimum_width=250, reading_min_width=460, padding=72,
            )
            self.toc_tree.column("#0", width=max(165, target - 72), minwidth=160, stretch=True)
            if target != self.sidebar_target_width:
                self.sidebar_target_width = target
                self.left.configure(width=target)
                self.panes.grid_columnconfigure(
                    0, minsize=target if self.sidebar_visible and not self.is_fullscreen else 0, weight=0
                )
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

    def _build_audiobook_screen(self):
        """Build the cover-led audiobook player to match the agreed visual design."""
        panel = tk.Frame(self.audio_screen, bg=APP_BG, bd=0)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.audio_cover_photo = None
        self.audio_cover_box = tk.Frame(
            panel, bg="#090A0B", highlightthickness=1, highlightbackground=BORDER,
            width=380, height=380,
        )
        self.audio_cover_box.pack(pady=(8, 12))
        self.audio_cover_box.pack_propagate(False)
        self.audio_cover_label = tk.Label(
            self.audio_cover_box, text="AUDIOBOOK", bg="#090A0B",
            fg=MUTED_TEXT, font=("Sans", 18, "bold"),
        )
        self.audio_cover_label.pack(fill=tk.BOTH, expand=True)
        self.audio_chapter_title = tk.Label(
            panel, text="Choose a chapter", bg=APP_BG, fg=DEFAULT_FG,
            font=(FONT_NAME, 16, "bold"), wraplength=760, justify=tk.CENTER,
        )
        self.audio_chapter_title.pack(fill=tk.X, pady=(0, 16))

        controls = tk.Frame(panel, bg=APP_BG)
        controls.pack(pady=(0, 18))
        self.audio_rewind_button = self._make_round_audio_button(
            controls, "⏪ 30", lambda: self._audio_skip(-30), size=96, font_size=15
        )
        self.audio_pause_button = self._make_round_audio_button(
            controls, "Ⅱ", self._audio_pause, size=96, font_size=27
        )
        self.audio_play_button = self._make_round_audio_button(
            controls, "▶", self._audio_play, size=96, font_size=27
        )
        self.audio_stop_button = self._make_round_audio_button(
            controls, "■", self._audio_stop, size=96, font_size=25
        )
        self.audio_forward_button = self._make_round_audio_button(
            controls, "⏩ 30", lambda: self._audio_skip(30), size=96, font_size=15
        )

        seek_row = tk.Frame(panel, bg=APP_BG)
        seek_row.pack(fill=tk.X, padx=18)
        self.audio_elapsed_label = tk.Label(
            seek_row, text="0:00", bg=APP_BG, fg=MUTED_TEXT, font=("Sans", 10)
        )
        self.audio_elapsed_label.pack(side=tk.LEFT)
        self.audio_position_var = tk.DoubleVar(value=0.0)
        self.audio_seek = ttk.Scale(
            seek_row, from_=0, to=1, orient=tk.HORIZONTAL,
            variable=self.audio_position_var, command=self._audio_seek_preview,
        )
        self.audio_seek.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12)
        self.audio_seek.bind("<ButtonPress-1>", self._audio_seek_start)
        self.audio_seek.bind("<ButtonRelease-1>", self._audio_seek_commit)
        self.audio_remaining_label = tk.Label(
            seek_row, text="-0:00", bg=APP_BG, fg=MUTED_TEXT, font=("Sans", 10)
        )
        self.audio_remaining_label.pack(side=tk.RIGHT)

        bottom = tk.Frame(panel, bg=APP_BG)
        bottom.pack(fill=tk.X, padx=22, pady=(24, 4))
        self.audio_volume_var = tk.DoubleVar(value=80)
        tk.Label(
            bottom, text="◖))", bg=APP_BG, fg=DEFAULT_FG, font=("Sans", 16)
        ).pack(side=tk.LEFT)
        self.audio_volume = tk.Scale(
            bottom, from_=0, to=100, orient=tk.HORIZONTAL,
            variable=self.audio_volume_var, command=self._audio_set_volume,
            showvalue=False, resolution=1, length=220, width=12,
            sliderlength=24, relief=tk.FLAT, bd=0, highlightthickness=0,
            bg=APP_BG, fg=DEFAULT_FG, troughcolor="#30343A",
            activebackground=MINT_GREEN, sliderrelief=tk.FLAT,
            cursor="hand2",
        )
        self.audio_volume.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 8))
        self.audio_volume.bind(
            "<ButtonPress-1>", lambda _event: setattr(self, "audio_volume_dragging", True)
        )
        self.audio_volume.bind(
            "<ButtonRelease-1>", lambda _event: setattr(self, "audio_volume_dragging", False)
        )
        self.audio_mute_button, self.audio_mute_text_id, self.audio_mute_circle = (
            self._make_round_audio_button(
                bottom, "◖×", self._audio_toggle_mute,
                size=48, font_size=13, pack=False,
            )
        )
        self.audio_mute_button.pack(side=tk.LEFT, padx=(4, 16))

        tk.Label(
            bottom, text="Speed", bg=APP_BG, fg=MUTED_TEXT, font=("Sans", 9)
        ).pack(side=tk.RIGHT, padx=(12, 4))
        self.audio_speed_var = tk.StringVar(value="1.0×")
        self.audio_speed = ttk.Combobox(
            bottom, textvariable=self.audio_speed_var, state="readonly",
            values=("0.5×", "0.75×", "1.0×", "1.25×", "1.5×", "1.75×", "2.0×"),
            width=6,
        )
        self.audio_speed.pack(side=tk.RIGHT)
        self.audio_speed.bind("<<ComboboxSelected>>", self._audio_set_speed)
        self.audio_time_label = tk.Label(
            panel, text="Not playing", bg=APP_BG, fg=MUTED_TEXT, font=("Sans", 9)
        )
        self.audio_time_label.pack(anchor="center", pady=(10, 0))
        self._set_audio_mute_icon(False)

    def _make_round_audio_button(self, parent, label, command, size=96,
                                 font_size=24, pack=True):
        """Create a real clickable circular transport/mute control on a Tk canvas."""
        canvas = tk.Canvas(
            parent, width=size, height=size, bg=APP_BG,
            highlightthickness=0, bd=0, cursor="hand2", takefocus=True,
        )
        inset = 3
        circle = canvas.create_oval(
            inset, inset, size - inset, size - inset,
            fill="#292D32", outline="#3B4048", width=1,
        )
        text_id = canvas.create_text(
            size / 2, size / 2, text=label, fill=DEFAULT_FG,
            font=(FONT_NAME, font_size, "bold"), justify=tk.CENTER,
        )
        canvas.bind("<Enter>", lambda _event: canvas.itemconfigure(circle, fill="#363B42"))
        canvas.bind("<Leave>", lambda _event: canvas.itemconfigure(circle, fill="#292D32"))
        canvas.bind("<ButtonPress-1>", lambda _event: canvas.itemconfigure(circle, fill=MINT_DARK))
        canvas.bind(
            "<ButtonRelease-1>",
            lambda _event: (canvas.itemconfigure(circle, fill="#363B42"), command()),
        )
        canvas.bind("<Return>", lambda _event: command())
        canvas.bind("<space>", lambda _event: command())
        if pack:
            canvas.pack(side=tk.LEFT, padx=6)
        return canvas, text_id, circle

    def _set_audio_mute_icon(self, muted):
        """Keep the mute control's speaker symbol aligned with mpv's actual mute state."""
        if not hasattr(self, "audio_mute_button"):
            return
        self.audio_mute_button.itemconfigure(
            self.audio_mute_text_id, text="◖×" if muted else "◖))"
        )

    def open_audiobook_dialog(self):
        path = filedialog.askopenfilename(
            parent=self, title="Open DRM-free M4B audiobook",
            filetypes=[("M4B audiobooks", "*.m4b"), ("All files", "*.*")],
        )
        if path:
            self.open_audiobook(path)

    def open_audiobook(self, path, resume=False, chapter_index=None):
        """Queue an M4B load for the single thread that owns the MPV backend."""
        if self.audio_worker is None:
            messagebox.showerror(
                "Audiobooks unavailable",
                "The audiobook playback engine is not available in this build.",
                parent=self,
            )
            return
        if self.audio_loading:
            messagebox.showinfo(
                "Audiobook opening",
                "An audiobook is already being opened. Please wait for it to finish.",
                parent=self,
            )
            return
        path = os.path.abspath(os.path.expanduser(path))
        if os.path.splitext(path)[1].lower() != ".m4b" or not os.path.isfile(path):
            messagebox.showerror(
                "Cannot open audiobook",
                "Please choose an existing local M4B file.",
                parent=self,
            )
            return

        if self.audio_tick_id:
            try:
                self.after_cancel(self.audio_tick_id)
            except tk.TclError:
                pass
            self.audio_tick_id = None
        if self.audio_path and self._last_audio_status:
            self._save_audio_position(self._last_audio_status)

        record = audiobook_record(self.state, path) if resume else {}
        try:
            restore_position = (
                max(0.0, float(record.get("position", 0.0)))
                if resume and chapter_index is None else 0.0
            )
        except (TypeError, ValueError, OverflowError):
            restore_position = 0.0

        self._audio_load_token += 1
        token = self._audio_load_token
        self.audio_loading = True
        self.audio_time_label.configure(text="Opening audiobook…")
        self.status.configure(text=f"Opening audiobook: {os.path.basename(path)}")
        if not self.audio_worker.submit(
            "open", token, path, restore_position, chapter_index,
            self.audio_volume_var.get(),
            self.audio_speed_var.get().replace("×", ""),
        ):
            self.audio_loading = False
            messagebox.showerror(
                "Audiobook unavailable", "The audio worker is shutting down.", parent=self
            )

    def _poll_audio_load_queue(self):
        """Apply audio-worker events on Tk's thread; MPV is never accessed here."""
        if self._audio_close_requested or self.audio_worker is None:
            return
        try:
            while True:
                event = self.audio_worker.events.get_nowait()
                if event.get("token") != self._audio_load_token:
                    continue
                event_type = event.get("type")
                if event_type == "loaded":
                    self.audio_loading = False
                    self._finish_audiobook_open(
                        event["path"], event.get("status") or {},
                        event.get("cover_bytes"),
                    )
                elif event_type == "status":
                    if self.audio_is_active:
                        self._audio_update_tick(event.get("status") or {})
                elif event_type == "command_started":
                    action = event.get("action", "")
                    labels = {
                        "play": "Starting playback…",
                        "pause": "Pausing audiobook…",
                        "stop": "Stopping audiobook…",
                        "seek": "Moving to requested position…",
                        "skip": "Skipping audiobook…",
                        "mute": "Changing mute setting…",
                        "toggle_mute": "Changing mute setting…",
                    }
                    if labels.get(action):
                        self.status.configure(text=labels[action])
                elif event_type == "command_completed":
                    action = event.get("action", "")
                    labels = {
                        "play": "Audiobook playing",
                        "pause": "Audiobook paused",
                        "stop": "Audiobook stopped at the beginning",
                        "seek": "Playback position updated",
                        "skip": "Playback position updated",
                        "mute": "Mute setting updated",
                        "toggle_mute": "Mute setting updated",
                    }
                    if labels.get(action):
                        self.status.configure(text=labels[action])
                elif event_type == "error":
                    if event.get("action") == "open":
                        self.audio_loading = False
                        self.audio_is_active = False
                        self.audio_path = None
                        self._last_audio_status = None
                        self.audio_chapters = []
                        self.audio_time_label.configure(text="Audiobook could not be opened")
                        self.status.configure(text="Audiobook could not be opened.")
                        error_detail = str(event.get("error", "Unknown playback error"))
                        diagnostic_path = os.path.join(STATE_DIR, "last-audiobook-error.log")
                        try:
                            os.makedirs(STATE_DIR, exist_ok=True)
                            with open(diagnostic_path, "w", encoding="utf-8") as log_file:
                                log_file.write(error_detail + "\\n")
                            diagnostic_note = (
                                f"\\n\\nDiagnostic details saved to:\\n{diagnostic_path}"
                            )
                        except OSError:
                            diagnostic_note = ""
                        messagebox.showerror(
                            "Could not open audiobook",
                            "Linux EPUB Reader could not open this M4B file.\\n\\n"
                            f"{error_detail[:3000]}{diagnostic_note}\\n\\n"
                            "The application should remain responsive. Check that the file "
                            "is readable and is not DRM-protected.",
                            parent=self,
                        )
                    else:
                        prefix = (
                            "Audiobook status failed"
                            if event.get("action") == "status"
                            else "Audiobook control failed"
                        )
                        self.status.configure(
                            text=f"{prefix}: {event.get('error', 'Unknown error')}"
                        )
        except queue.Empty:
            pass
        if not self._audio_close_requested:
            self._audio_load_poll_id = self.after(100, self._poll_audio_load_queue)

    def _finish_audiobook_open(self, path, status, cover_bytes):
        """Update player widgets after the audio owner confirms a successful load."""
        self.audio_path = path
        self.audio_title = os.path.splitext(os.path.basename(path))[0]
        self.audio_is_active = True
        self._last_audio_status = status or {}
        record = audiobook_record(self.state, path)
        self.state["last_opened_item"] = {
            "type": "audiobook", "path": path, "title": self.audio_title
        }
        self.resume_button.configure(
            text="Resume last audiobook", command=self.resume_last_audiobook,
            state=tk.NORMAL,
        )
        try:
            self._save_state()
        except OSError:
            pass
        metadata = (status or {}).get("metadata", {}) or {}
        self.audio_title = str(metadata.get("title") or self.audio_title)
        record["title"] = self.audio_title
        self.title(f"{self.audio_title} — {APP_NAME} v{APP_VERSION}")
        self.book_label.configure(text=self.audio_title)
        self.heading.pack_forget()
        self.text_frame.pack_forget()
        self.welcome_view.pack_forget()
        self.audio_screen.pack(fill=tk.BOTH, expand=True)
        self._refresh_audio_chapters((status or {}).get("chapters", []))
        self._show_audio_cover(cover_bytes)
        self._populate_audio_contents()

        volume = (status or {}).get("volume")
        if volume is not None:
            try:
                self.audio_volume_var.set(max(0.0, min(100.0, float(volume))))
            except (TypeError, ValueError, OverflowError):
                pass
        speed = (status or {}).get("speed")
        if speed is not None:
            try:
                self.audio_speed_var.set(f"{float(speed):g}×")
            except (TypeError, ValueError, OverflowError):
                pass
        self._audio_update_tick(status)

    def _show_audio_cover(self, cover_bytes):
        self.audio_cover_photo = self._create_cover_photo(cover_bytes, (380, 380)) if cover_bytes else None
        self.audio_cover_label.configure(image="", text="")
        if self.audio_cover_photo is not None:
            self.audio_cover_label.configure(image=self.audio_cover_photo)
        else:
            self.audio_cover_label.configure(text="COVER ART\nNOT AVAILABLE", image="")

    def _refresh_audio_chapters(self, chapters):
        """Store human-readable embedded chapter names independently of filenames."""
        self.audio_chapters = chapters or []
        record = audiobook_record(self.state, self.audio_path) if self.audio_path else {}
        record["chapters"] = [
            audiobook_display_chapter_title(ch.get("title"), index)
            for index, ch in enumerate(self.audio_chapters)
        ]
        self._populate_audio_contents()

    def _populate_audio_contents(self):
        """Show an audiobook heading and its chapter titles, never numbered file names."""
        if not hasattr(self, "toc_tree"):
            return
        self.toc_tree.delete(*self.toc_tree.get_children())
        self._toc_items = {}
        self._audio_toc_entries = []
        records = audiobook_records(self.state)
        paths = list(records)
        if self.audio_path and self.audio_path in paths:
            paths.remove(self.audio_path)
            paths.insert(0, self.audio_path)
        else:
            last_item = last_opened_item_info(self.state)
            if last_item and last_item["type"] == "audiobook" and last_item["path"] in paths:
                paths.remove(last_item["path"])
                paths.insert(0, last_item["path"])

        for book_number, path in enumerate(paths):
            record = records.get(path)
            if not isinstance(record, dict):
                continue
            group_title = "🎧  Audiobook" if book_number == 0 else f"🎧  Audiobook {book_number + 1}"
            book_node = self.toc_tree.insert("", tk.END, text=group_title, open=True)
            chapters = record.get("chapters", [])
            if path == self.audio_path and self.audio_chapters:
                chapters = [
                    audiobook_display_chapter_title(ch.get("title"), index)
                    for index, ch in enumerate(self.audio_chapters)
                ]
            if not chapters:
                self.toc_tree.insert(book_node, tk.END, text="No embedded chapters found")
                continue
            for index, chapter in enumerate(chapters):
                title = audiobook_display_chapter_title(chapter, index)
                iid = self.toc_tree.insert(book_node, tk.END, text=title)
                self._toc_items[iid] = ("audio", path, index)
                self._audio_toc_entries.append((iid, title, 1))
        self._fit_audio_sidebar()

    def _fit_audio_sidebar(self):
        """Wrap complete chapter names inside the visible Contents width."""
        try:
            if not self._audio_toc_entries:
                ttk.Style(self).configure("Treeview", rowheight=29)
                return
            left_width = self.left.winfo_width()
            if left_width <= 1:
                left_width = self.sidebar_target_width
            tree_width = max(170, int(left_width) - 28)
            font = tkfont.Font(root=self, font=("Sans", 10))
            text_width = max(105, tree_width - 58)
            max_lines = 1
            for iid, title, depth in self._audio_toc_entries:
                wrapped = wrap_audio_chapter_title(
                    title, font, max(90, text_width - (depth * 12))
                )
                self.toc_tree.item(iid, text=wrapped)
                max_lines = max(max_lines, wrapped.count("\n") + 1)
            line_height = int(font.metrics("linespace"))
            ttk.Style(self).configure(
                "Treeview", rowheight=max(34, line_height * max_lines + 12)
            )
            self.toc_tree.column(
                "#0", width=tree_width, minwidth=tree_width, stretch=True
            )
        except (tk.TclError, ValueError, TypeError):
            pass

    def _highlight_audio_chapter(self, chapter_index):
        """Select and reveal the currently playing embedded chapter."""
        for iid, data in self._toc_items.items():
            if data and data[0] == "audio" and data[2] == chapter_index:
                # Do not call see() on every status update: it yanks the
                # Contents panel back to the playing chapter while the user
                # is manually scrolling. Reveal only when selection changes.
                if self.toc_tree.selection() != (iid,):
                    self._setting_toc_selection = True
                    try:
                        self.toc_tree.selection_set(iid)
                        self.toc_tree.focus(iid)
                        self.toc_tree.see(iid)
                    finally:
                        self._setting_toc_selection = False
                return

    def _audio_chapter_selected(self, _event=None):
        return

    def _audio_select_chapter(self, path, index):
        if path != self.audio_path:
            self.open_audiobook(path, resume=True, chapter_index=index)
            return
        self.audio_worker.submit("chapter", self._audio_load_token, index)

    def _audio_play(self):
        if not self.audio_backend or not self.audio_path:
            self.open_audiobook_dialog()
            return
        self.audio_worker.submit("play", self._audio_load_token)

    def _audio_pause(self):
        if not self.audio_backend or not self.audio_path:
            return
        self.audio_worker.submit("pause", self._audio_load_token)

    def _audio_set_volume(self, value):
        if self.audio_backend and self.audio_path:
            self.audio_worker.submit("volume", self._audio_load_token, value)

    def _audio_toggle_mute(self):
        if not self.audio_backend or not self.audio_path:
            return
        # Toggle on the MPV-owning thread using its latest acknowledged state;
        # do not calculate from a potentially stale Tk-side status snapshot.
        self.audio_worker.submit("toggle_mute", self._audio_load_token)

    def _audio_set_speed(self, _event=None):
        if not self.audio_backend or not self.audio_path:
            return
        self.audio_worker.submit(
            "speed", self._audio_load_token,
            self.audio_speed_var.get().replace("×", ""),
        )

    def _audio_skip(self, seconds):
        if not self.audio_backend or not self.audio_path:
            return
        self.audio_worker.submit("skip", self._audio_load_token, seconds)

    def _audio_seek_preview(self, value):
        if self.audio_seek.instate(["!disabled"]):
            self.audio_time_label.configure(text=f"Seek to {format_time(value)}")

    def _audio_seek_start(self, _event=None):
        self.audio_seeking = True

    def _audio_seek_commit(self, _event=None):
        if self.audio_worker and self.audio_path:
            position = self.audio_position_var.get()
            self.audio_worker.submit("seek", self._audio_load_token, position)
        self.audio_seeking = False

    def _audio_update_tick(self, initial_status=None):
        if not self.audio_is_active or not self.audio_backend:
            return
        try:
            status = initial_status
            if not status:
                return
            self._last_audio_status = status
            position = float(status.get("time_pos") or 0)
            duration = float(status.get("duration") or 0)
            paused = bool(status.get("paused", True))
            chapters = status.get("chapters", [])
            if chapters and chapters != self.audio_chapters:
                self._refresh_audio_chapters(chapters)
            volume = status.get("volume")
            if volume is not None and not self.audio_volume_dragging:
                self.audio_volume_var.set(max(0.0, min(100.0, float(volume))))
            self._set_audio_mute_icon(bool(status.get("mute")))
            if duration > 0 and not self.audio_seeking:
                self.audio_seek.configure(to=duration)
                self.audio_position_var.set(position)
                self.audio_elapsed_label.configure(text=format_time(position))
                self.audio_remaining_label.configure(text=f"-{format_time(max(0, duration-position))}")
                self.audio_time_label.configure(text=f"{format_time(position)} elapsed · {format_time(max(0, duration-position))} remaining")
            chapter_index = status.get("chapter")
            if isinstance(chapter_index, int) and 0 <= chapter_index < len(self.audio_chapters):
                self.audio_chapter_title.configure(
                    text=audiobook_display_chapter_title(
                        self.audio_chapters[chapter_index].get("title"), chapter_index
                    )
                )
                self._highlight_audio_chapter(chapter_index)
            self._save_audio_position(status)
        except (AudiobookError, OSError, TypeError, ValueError):
            pass
        self.audio_tick_id = None

    def _save_audio_position(self, status=None):
        if not self.audio_path or not self.audio_backend:
            return
        try:
            status = status or self._last_audio_status
            if not status:
                return
            position = max(0.0, float(status.get("time_pos") or 0))
            duration = max(0.0, float(status.get("duration") or 0))
            chapter = max(0, int(status.get("chapter") or 0))
            record = audiobook_record(self.state, self.audio_path)
            record.update({"path": self.audio_path, "title": self.audio_title,
                           "position": position, "duration": duration, "chapter": chapter})
            current_item = last_opened_item_info(self.state)
            if self.audio_is_active or (
                current_item and current_item["type"] == "audiobook"
                and current_item["path"] == os.path.abspath(self.audio_path)
            ):
                self.state["last_opened_item"] = {
                    "type": "audiobook", "path": self.audio_path, "title": self.audio_title
                }
            self._save_state()
        except (AudiobookError, OSError, TypeError, ValueError):
            pass

    def _audio_stop(self):
        if self.audio_worker and self.audio_path:
            self.audio_worker.submit("stop", self._audio_load_token)
            record = audiobook_record(self.state, self.audio_path)
            record.update({
                "path": self.audio_path, "title": self.audio_title,
                "position": 0.0, "chapter": 0,
            })
            try:
                self._save_state()
            except OSError:
                pass
        self.audio_position_var.set(0)
        self.audio_time_label.configure(text="Stopped · ready to play from the beginning")

    def show_reader_screen(self):
        if self.audio_is_active:
            self._save_audio_position(self._last_audio_status)
            if self.audio_worker:
                self.audio_worker.submit("pause", self._audio_load_token)
            self.audio_is_active = False
        if self.audio_tick_id:
            try:
                self.after_cancel(self.audio_tick_id)
            except tk.TclError:
                pass
            self.audio_tick_id = None
        self.audio_screen.pack_forget()
        if self.book:
            # Returning to the EPUB screen makes that book the active item
            # again; keep audiobook progress separately without overriding it.
            self.state["last_opened_item"] = {
                "type": "epub", "path": self.book.path, "title": self.book.title
            }
            self.resume_button.configure(
                text="Resume last book", command=self.resume_last_book,
                state=tk.NORMAL,
            )
            self.book_label.configure(text=self.book.title)
            self.title(f"{self.book.title} — {APP_NAME} v{APP_VERSION}")
            try:
                self._save_state()
            except OSError:
                pass
            self._restore_reader_content_layout()
        else:
            self._refresh_resume_ui()

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

    def _show_drm_notice(self, path, drm_type):
        """Explain that a protected/unsupported file cannot be read here; never hand it off."""
        title, message = drm_notice_for(path, drm_type)
        messagebox.showinfo(title, message)

    def _refresh_resume_ui(self):
        """Keep the resume action aligned with the most recently opened item."""
        item = last_opened_item_info(self.state)
        if item and item["type"] == "audiobook":
            path, title = item["path"], item["title"]
            available = os.path.isfile(path)
            self._populate_audio_contents()
            self.resume_button.configure(
                text="Resume last audiobook" if available else "Locate last audiobook…",
                command=self.resume_last_audiobook,
                state=tk.NORMAL,
            )
            if self.book is None:
                self.last_book_preview = None
                self.last_book_preview_path = ""
                self.last_book_preview_error = ""
                self._show_audiobook_welcome_panel(path, title, available)
            return

        if item and item["type"] == "epub":
            path, title, inferred = item["path"], item["title"], False
        else:
            path, title, inferred = last_opened_book_info(self.state)
        available = bool(path and os.path.isfile(path))
        self.resume_button.configure(
            text=("Resume last book" if available else "Locate last book…") if path else "Resume last book",
            command=self.resume_last_book,
            state=tk.NORMAL if path else tk.DISABLED,
        )
        if self.book is None:
            self.last_book_preview = None
            self.last_book_preview_path = path
            self.last_book_preview_error = ""
            if available:
                try:
                    self.last_book_preview = EPUBBook(path)
                except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
                    self.last_book_preview_error = str(exc)
            self._show_welcome_panel(path, title, inferred, self.last_book_preview)

    def _show_audiobook_welcome_panel(self, path, title, available):
        """Show a simple welcome-back card for the most recently used audiobook."""
        self.heading.pack_forget()
        self.text_frame.pack_forget()
        self.audio_screen.pack_forget()
        self.welcome_view.pack(fill=tk.BOTH, expand=True)
        for child in self.welcome_view.winfo_children():
            child.destroy()
        card = tk.Frame(
            self.welcome_view, bg=PANEL_BG, highlightthickness=1,
            highlightbackground=BORDER, bd=0,
        )
        card.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tk.Label(
            card, text="WELCOME BACK", bg=PANEL_BG, fg=MINT_GREEN,
            font=("Sans", 9, "bold"),
        ).pack(anchor="w", padx=24, pady=(24, 6))
        tk.Label(
            card, text=title, bg=PANEL_BG, fg=DEFAULT_FG,
            font=(FONT_NAME, 19, "bold"), anchor="w", justify=tk.LEFT,
            wraplength=760,
        ).pack(fill=tk.X, padx=24)
        message = (
            "Your last audiobook is ready. It will open paused at your saved listening position."
            if available else
            "The audiobook is no longer at its saved location. Locate the same M4B file to restore your listening position."
        )
        tk.Label(
            card, text=message, bg=PANEL_BG, fg=MUTED_TEXT,
            font=(FONT_NAME, 10), anchor="w", justify=tk.LEFT,
            wraplength=760,
        ).pack(fill=tk.X, padx=24, pady=(10, 8))
        tk.Label(
            card, text=path, bg=PANEL_BG, fg=MUTED_TEXT,
            font=("Sans", 8), anchor="w", wraplength=760,
        ).pack(fill=tk.X, padx=24, pady=(0, 18))
        ttk.Button(
            card,
            text="Resume audiobook" if available else "Locate audiobook…",
            command=self.resume_last_audiobook,
        ).pack(anchor="w", padx=24, pady=(0, 24))

    def _create_cover_photo(self, cover_bytes, max_size):
        """Decode a book cover for Tk, preferring Pillow for JPEG and other formats."""
        if not cover_bytes:
            return None
        try:
            from PIL import Image, ImageTk
            with Image.open(io.BytesIO(cover_bytes)) as image:
                image.load()
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                return ImageTk.PhotoImage(image.copy(), master=self)
        except ImportError:
            # Tk's built-in decoder handles formats such as PNG and GIF.
            try:
                photo = tk.PhotoImage(data=base64.b64encode(cover_bytes), master=self)
                width, height = photo.width(), photo.height()
                if width > max_size[0] or height > max_size[1]:
                    factor = max(1, (width + max_size[0] - 1) // max_size[0],
                                 (height + max_size[1] - 1) // max_size[1])
                    photo = photo.subsample(factor, factor)
                return photo
            except tk.TclError:
                return None
        except Exception:
            return None

    def _show_welcome_panel(self, path="", title="", inferred=False, book=None):
        """Show an illustrated, information-rich welcome-back panel in the reading area."""
        self.heading.pack_forget()
        self.text_frame.pack_forget()
        self.welcome_view.pack(fill=tk.BOTH, expand=True)
        for child in self.welcome_view.winfo_children():
            child.destroy()
        self._welcome_cover_photo = None

        card = tk.Frame(
            self.welcome_view, bg=PANEL_BG, highlightthickness=1,
            highlightbackground=BORDER, bd=0,
        )
        card.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        header = tk.Frame(card, bg=PANEL_BG)
        header.pack(fill=tk.X, padx=22, pady=(18, 8))
        has_saved_book = bool(path)
        eyebrow = "WELCOME BACK" if has_saved_book else "WELCOME"
        tk.Label(
            header, text=eyebrow, bg=PANEL_BG, fg=MINT_GREEN,
            font=("Sans", 9, "bold"), anchor="w",
        ).pack(anchor="w")
        if has_saved_book:
            tk.Label(
                header, text="Your last book is ready when you are",
                bg=PANEL_BG, fg=DEFAULT_FG, font=("Sans", 15, "bold"),
                anchor="w",
            ).pack(anchor="w", pady=(3, 0))
        else:
            tk.Label(
                header, text="Welcome to Linux EPUB Reader",
                bg=PANEL_BG, fg=DEFAULT_FG, font=("Sans", 15, "bold"),
                anchor="w",
            ).pack(anchor="w", pady=(3, 0))

        content = tk.Frame(card, bg=PANEL_BG)
        content.pack(fill=tk.BOTH, expand=True, padx=22, pady=(8, 18))
        cover_column = tk.Frame(content, bg=PANEL_BG, width=190)
        cover_column.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 22))
        cover_column.pack_propagate(False)
        cover_box = tk.Frame(
            cover_column, bg=APP_BG, highlightthickness=1,
            highlightbackground=BORDER, width=176, height=260,
        )
        cover_box.pack(anchor="n")
        cover_box.pack_propagate(False)

        info = tk.Frame(content, bg=PANEL_BG)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        if book is not None and book.cover_bytes:
            self._welcome_cover_photo = self._create_cover_photo(book.cover_bytes, (174, 258))
        if self._welcome_cover_photo is not None:
            tk.Label(cover_box, image=self._welcome_cover_photo, bg=APP_BG, bd=0).pack(
                expand=True, padx=2, pady=2
            )
        else:
            cover_label = "Cover artwork\nnot available" if book is not None and book.cover_bytes else "EPUB\nBOOK"
            tk.Label(
                cover_box, text=cover_label, bg=APP_BG, fg=MUTED_TEXT,
                font=("Sans", 15, "bold"), justify=tk.CENTER,
            ).pack(fill=tk.BOTH, expand=True)

        if book is not None:
            tk.Label(
                info, text=book.title, bg=PANEL_BG, fg=DEFAULT_FG,
                font=(FONT_NAME, 19, "bold"), justify=tk.LEFT, anchor="w",
                wraplength=460,
            ).pack(fill=tk.X, anchor="w")
            tk.Label(
                info, text=book.author or "Author not supplied",
                bg=PANEL_BG, fg=MUTED_TEXT, font=(FONT_NAME, 11),
                justify=tk.LEFT, anchor="w",
            ).pack(fill=tk.X, anchor="w", pady=(4, 12))
            metadata = [
                ("Publisher", book.publisher),
                ("Publication date", book.date),
                ("Language", book.language),
                ("Identifier", book.identifier),
                ("Subjects", "; ".join(book.subjects)),
                ("Chapters", str(len(book.chapters))),
                ("Extracted words", f"{book.word_count:,}"),
            ]
            for label, value in metadata:
                if value:
                    tk.Label(
                        info, text=f"{label}: {value}", bg=PANEL_BG,
                        fg=DEFAULT_FG, font=("Sans", 9), anchor="w",
                        justify=tk.LEFT, wraplength=470,
                    ).pack(fill=tk.X, anchor="w", pady=1)
            if book.description:
                tk.Label(
                    info, text="Description", bg=PANEL_BG, fg=DEFAULT_FG,
                    font=("Sans", 9, "bold"), anchor="w",
                ).pack(fill=tk.X, anchor="w", pady=(9, 2))
                description = tk.Text(
                    info, height=4, wrap=tk.WORD, font=(FONT_NAME, 9),
                    bg=APP_BG, fg=DEFAULT_FG, insertbackground=DEFAULT_FG,
                    relief=tk.FLAT, borderwidth=0, highlightthickness=0,
                    padx=8, pady=6,
                )
                description.pack(fill=tk.X, expand=False)
                description.insert("1.0", book.description)
                description.configure(state=tk.DISABLED)
            summary = saved_book_summary(self.state, path, book)
            tk.Label(
                info,
                text=(
                    f"Saved place: Chapter {summary['chapter_number']} of "
                    f"{summary['chapter_count']} — {summary['chapter_title']}\n"
                    f"{summary['chapter_percent']}% through this chapter"
                    f"  •  about {summary['overall_percent']}% of the book"
                ),
                bg=PANEL_BG, fg=MINT_GREEN, font=("Sans", 9, "bold"),
                anchor="w", justify=tk.LEFT, wraplength=470,
            ).pack(fill=tk.X, anchor="w", pady=(10, 2))
        elif path:
            tk.Label(
                info, text=title or os.path.basename(path), bg=PANEL_BG,
                fg=DEFAULT_FG, font=(FONT_NAME, 19, "bold"),
                justify=tk.LEFT, anchor="w", wraplength=460,
            ).pack(fill=tk.X, anchor="w")
            message = (
                "The saved EPUB is no longer available at its previous location. "
                "Choose Locate last book to select it again; your saved chapter, "
                "reading position and bookmarks will be restored."
            )
            if self.last_book_preview_error:
                message += "\n\nThe book details could not be read: " + self.last_book_preview_error
            tk.Label(
                info, text=message, bg=PANEL_BG, fg=MUTED_TEXT,
                font=(FONT_NAME, 10), justify=tk.LEFT, anchor="w",
                wraplength=470,
            ).pack(fill=tk.X, anchor="w", pady=(10, 0))
        else:
            tk.Label(
                info, text=WELCOME_TEXT, bg=PANEL_BG, fg=DEFAULT_FG,
                font=(FONT_NAME, 10), justify=tk.LEFT, anchor="nw",
                wraplength=470,
            ).pack(fill=tk.BOTH, expand=True, anchor="nw")

        actions = tk.Frame(card, bg=PANEL_BG)
        actions.pack(fill=tk.X, padx=22, pady=(0, 18))
        button_text = "Resume" if has_saved_book and os.path.isfile(path) else (
            "Locate last book…" if has_saved_book else "Open a book…"
        )
        primary = tk.Button(
            actions, text=button_text,
            command=self.resume_last_book if has_saved_book else self.open_dialog,
            bg=MINT_GREEN, fg=APP_BG, activebackground="#9BDC59",
            activeforeground=APP_BG, relief=tk.FLAT, borderwidth=0,
            font=("Sans", 11, "bold"), padx=28, pady=10,
            cursor="hand2",
        )
        primary.pack(side=tk.LEFT)
        ttk.Button(
            actions, text="Open another book…", command=self.open_dialog,
        ).pack(side=tk.LEFT, padx=(10, 0))
        if inferred and has_saved_book:
            tk.Label(
                actions, text="Suggested from your earlier reading history",
                bg=PANEL_BG, fg=MUTED_TEXT, font=("Sans", 8),
            ).pack(side=tk.LEFT, padx=(14, 0))
        if has_saved_book:
            self.status.configure(text="Welcome back — your saved reading place is ready.")
            self.progress.configure(value=0)
            self.progress_percent.configure(text="")
        else:
            self.status.configure(text="Open an EPUB to begin.")
            self.progress.configure(value=0)
            self.progress_percent.configure(text="")

    def resume_last_book(self):
        """Resume the last book, or let the user locate it if it has moved."""
        path, title, _inferred = last_opened_book_info(self.state)
        if not path:
            self.open_dialog()
            return
        if os.path.isfile(path):
            cached = self.last_book_preview if self.last_book_preview_path == path else None
            self.open_book(path, loaded_book=cached)
            return
        messagebox.showinfo(
            "Last book not found",
            f"Linux EPUB Reader cannot find “{title}” at its saved location.\n\n"
            "Please select the same DRM-free EPUB file again. Its saved chapter, "
            "reading position and bookmarks will be restored.",
            parent=self,
        )
        initial_dir = os.path.dirname(path)
        if not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")
        selected = filedialog.askopenfilename(
            parent=self,
            title="Locate your last EPUB book",
            initialdir=initial_dir,
            filetypes=[("EPUB books", "*.epub"), ("All files", "*.*")],
        )
        if selected:
            self.open_book(selected, restore_from_path=path)

    def resume_last_audiobook(self):
        """Resume the saved audiobook or locate it again without losing history."""
        item = last_opened_item_info(self.state)
        if not item or item["type"] != "audiobook":
            self.open_audiobook_dialog()
            return
        path = item["path"]
        if os.path.isfile(path):
            self.open_audiobook(path, resume=True)
            return
        messagebox.showinfo(
            "Last audiobook not found",
            f"Linux EPUB Reader cannot find “{item['title']}” at its saved location. "
            "Select the same DRM-free M4B file to restore your listening position.",
            parent=self,
        )
        initial_dir = os.path.dirname(path)
        if not os.path.isdir(initial_dir):
            initial_dir = os.path.expanduser("~")
        selected = filedialog.askopenfilename(
            parent=self, title="Locate your last audiobook",
            initialdir=initial_dir,
            filetypes=[("M4B audiobooks", "*.m4b"), ("All files", "*.*")],
        )
        if selected:
            selected = os.path.abspath(selected)
            records = audiobook_records(self.state)
            previous = records.get(path)
            if isinstance(previous, dict) and selected not in records:
                restored = dict(previous)
                restored["path"] = selected
                records[selected] = restored
            self.open_audiobook(selected, resume=True)

    def _restore_reader_content_layout(self):
        """Restore reader widgets in a safe order, leaving the welcome panel alone."""
        if self.book is None:
            return
        if self.text_frame.winfo_manager() != "pack":
            self.text_frame.pack(fill=tk.BOTH, expand=True)
        if self.heading.winfo_manager() != "pack":
            self.heading.pack(fill=tk.X, anchor="w", pady=(0, 12), before=self.text_frame)

    def open_book(self, path, restore_from_path=None, loaded_book=None):
        path = os.path.abspath(os.path.expanduser(path))
        drm_type = detect_drm_input(path)
        if drm_type:
            self._show_drm_notice(path, drm_type)
            return
        try:
            book = loaded_book if loaded_book is not None and loaded_book.path == path else EPUBBook(path)
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
            messagebox.showerror("Could not open EPUB", str(exc))
            return
        if self.audio_is_active:
            self.show_reader_screen()
        if restore_from_path:
            restore_book_state_for_moved_file(self.state, restore_from_path, path)
        self.book = book
        self.last_book_preview = None
        self.last_book_preview_path = ""
        self.welcome_view.pack_forget()
        self._restore_reader_content_layout()
        self.current_key = self._book_key(path)
        remember_last_opened_book(self.state, path, book.title)
        self.state["last_opened_item"] = {"type": "epub", "path": path, "title": book.title}
        try:
            self._save_state()
        except OSError:
            pass
        self._refresh_resume_ui()
        st = self._book_state()
        self.index = max(0, min(len(book.chapters) - 1, int(st.get("chapter", 0))))
        self.rendered_book_key = None
        self.chapter_marks = []
        self.title(f"{book.title} — {APP_NAME} v{APP_VERSION}")
        self.book_label.configure(text=book.title)
        self._populate_toc()
        self._render_book_text()
        if not self.is_fullscreen:
            self._ensure_toc_left()
        self.show_chapter(self.index, restore=True)
        self.show_details(first_open=True)

    def _populate_toc(self):
        ttk.Style(self).configure("Treeview", rowheight=29)
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
        if data and data[0] == "audio":
            self._audio_select_chapter(data[1], data[2])
            return
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
        # Reset the grid column minimum as well as hiding the contents widget.
        # grid_remove() alone preserves the old column minimum, leaving a blank
        # sidebar-sized strip in full-screen when the contents panel was open.
        self._ensure_toc_left()
        self.toolbar.pack_forget()
        self.panes.pack_configure(padx=0, pady=0)
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
        self.after_idle(self._update_fullscreen_hint)

    def _update_fullscreen_hint(self):
        """Show the floating F11 control only when fullscreen and not opted out."""
        if fullscreen_hint_should_show(self.state, self.is_fullscreen):
            self.fullscreen_hint.place(relx=0.5, rely=1.0, anchor="s", y=-22)
            self.fullscreen_hint.lift()
        else:
            self.fullscreen_hint.place_forget()

    def _set_fullscreen_hint_from_checkbox(self):
        """Persist the checkbox choice and sync the reversible View-menu preference."""
        hide = bool(self.hide_fullscreen_hint_var.get())
        self.show_fullscreen_hint_var.set(not hide)
        self.state["hide_fullscreen_hint"] = hide
        try:
            self._save_state()
        except OSError:
            pass
        self._update_fullscreen_hint()

    def _set_fullscreen_hint_from_menu(self):
        """Allow the user to restore the fullscreen hint from View after hiding it."""
        show = bool(self.show_fullscreen_hint_var.get())
        self.hide_fullscreen_hint_var.set(not show)
        self.state["hide_fullscreen_hint"] = not show
        try:
            self._save_state()
        except OSError:
            pass
        self._update_fullscreen_hint()

    def exit_fullscreen(self):
        if not self.is_fullscreen: return
        self.fullscreen_hint.place_forget()
        self.attributes("-fullscreen", False)
        self.is_fullscreen = False
        self._ensure_toc_left()
        self.panes.pack_configure(padx=10, pady=(8, 6))
        self.right.configure(padding=6)
        self._ensure_toc_left()
        self._restore_reader_content_layout()
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
        cover_photo = self._create_cover_photo(b.cover_bytes, (210, 320))
        if cover_photo is not None:
            win.cover_photo = cover_photo
            ttk.Label(cover_frame, image=cover_photo).pack(anchor="n")
        elif b.cover_bytes:
            ttk.Label(
                cover_frame, text=f"Cover format cannot be displayed\n({b.cover_name})",
                width=24, justify=tk.CENTER,
            ).pack(anchor="n")
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
        self._audio_close_requested = True
        if self.book:
            self._update_progress()
        if self.audio_path and self._last_audio_status:
            self._save_audio_position(self._last_audio_status)
        if self.audio_tick_id:
            try:
                self.after_cancel(self.audio_tick_id)
            except tk.TclError:
                pass
        if self._audio_load_poll_id:
            try:
                self.after_cancel(self._audio_load_poll_id)
            except tk.TclError:
                pass
        if self.audio_worker:
            # The dedicated owner closes MPV itself; never block Tk waiting for IPC.
            self.audio_worker.shutdown()
        try:
            self._save_state()
        except OSError:
            pass
        self.destroy()


def main():
    app = Reader()
    if len(sys.argv) > 1:
        app.after(150, lambda: app.open_book(sys.argv[1]))
    app.mainloop()

if __name__ == "__main__":
    main()
