# Copyright (C) 2026 Linux EPUB Reader project contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Local-only M4B playback control using mpv's Unix-domain JSON IPC.

The backend deliberately has no URL-loading API. It starts mpv with a private
IPC socket, disables user configuration/scripts and requests audio-only output.
DRM is not bypassed: files mpv cannot decode are reported to the caller.
"""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import threading


class AudiobookError(RuntimeError):
    """A local audiobook could not be opened or controlled."""


def normalise_m4b_path(path):
    """Return an absolute local M4B path, rejecting other formats."""
    if not isinstance(path, (str, os.PathLike)):
        raise AudiobookError("Choose an M4B audiobook file.")
    value = os.path.abspath(os.path.expanduser(os.fspath(path)))
    if os.path.splitext(value)[1].lower() != ".m4b":
        raise AudiobookError("Only M4B audiobook files are supported.")
    if not os.path.isfile(value):
        raise AudiobookError("The selected audiobook file could not be found.")
    return value


def format_time(seconds):
    """Format a media time as H:MM:SS or M:SS."""
    try:
        value = max(0, int(float(seconds)))
    except (TypeError, ValueError, OverflowError):
        value = 0
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def chapter_rows(chapters):
    """Return safe display records from mpv's chapter-list property."""
    rows = []
    if not isinstance(chapters, list):
        return rows
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        try:
            start = max(0.0, float(chapter.get("time", 0)))
        except (TypeError, ValueError, OverflowError):
            start = 0.0
        title = str(chapter.get("title") or f"Chapter {index + 1}").strip()
        rows.append({"index": index, "title": title, "time": start})
    return rows


def _iter_mp4_atoms(handle, start, end):
    """Yield (fourcc, payload_start, payload_end) for a bounded MP4 atom range."""
    cursor = max(0, int(start))
    end = max(cursor, int(end))
    while cursor + 8 <= end:
        handle.seek(cursor)
        header = handle.read(8)
        if len(header) != 8:
            return
        size = int.from_bytes(header[:4], "big")
        kind = header[4:8]
        header_size = 8
        if size == 1:
            extended = handle.read(8)
            if len(extended) != 8:
                return
            size = int.from_bytes(extended, "big")
            header_size = 16
        elif size == 0:
            size = end - cursor
        if size < header_size or cursor + size > end:
            return
        payload_start = cursor + header_size
        payload_end = cursor + size
        yield kind, payload_start, payload_end
        cursor += size


def extract_cover_art(path, max_bytes=20 * 1024 * 1024):
    """Extract an embedded iTunes/MP4 covr image without loading the whole audiobook."""
    containers = {b"moov", b"udta", b"meta", b"ilst"}
    try:
        with open(path, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size
            pending = [(0, size, 0)]
            while pending:
                start, end, depth = pending.pop()
                if depth > 12:
                    continue
                for kind, payload_start, payload_end in _iter_mp4_atoms(handle, start, end):
                    if kind == b"covr":
                        for child_kind, child_start, child_end in _iter_mp4_atoms(handle, payload_start, payload_end):
                            if child_kind != b"data" or child_end - child_start <= 8:
                                continue
                            image_size = child_end - child_start - 8
                            if image_size > max_bytes:
                                continue
                            handle.seek(child_start + 8)
                            image = handle.read(image_size)
                            if image.startswith((bytes.fromhex("89504e470d0a1a0a"), bytes.fromhex("ffd8ff"),
                                                 b"GIF87a", b"GIF89a", b"BM")) or (
                                len(image) >= 12 and image[:4] == b"RIFF" and image[8:12] == b"WEBP"
                            ):
                                return image
                    if kind in containers:
                        # The 'meta' atom starts with a four-byte version/flags field.
                        child_start = payload_start + (4 if kind == b"meta" else 0)
                        if child_start <= payload_end:
                            pending.append((child_start, payload_end, depth + 1))
    except (OSError, ValueError, OverflowError):
        return None
    return None


class MPVBackend:
    """Small synchronous controller for one private mpv audio-only process."""

    def __init__(self, executable=None, startup_timeout=5.0, command_timeout=5.0,
                 audio_output=None):
        self.executable = executable or shutil.which("mpv")
        self.startup_timeout = float(startup_timeout)
        self.command_timeout = float(command_timeout)
        self.audio_output = audio_output
        self.process = None
        self._runtime_dir = None
        self._socket_path = None
        self._request_id = 0
        self._ipc_socket = None
        self._ipc_buffer = bytearray()
        self._ipc_lock = threading.RLock()
        self._stderr_log_path = None
        self._stderr_log = None
        self._mpv_log_path = None
        self.current_path = None

    @property
    def available(self):
        return bool(self.executable)

    def start(self):
        if self.process and self.process.poll() is None:
            return
        if not self.executable:
            raise AudiobookError(
                "The audiobook playback engine (mpv) is not installed."
            )
        self._runtime_dir = tempfile.mkdtemp(prefix="ler-audio-")
        os.chmod(self._runtime_dir, 0o700)
        self._socket_path = os.path.join(self._runtime_dir, "mpv.sock")
        self._stderr_log_path = os.path.join(self._runtime_dir, "mpv-stderr.log")
        self._mpv_log_path = os.path.join(self._runtime_dir, "mpv-debug.log")
        self._stderr_log = open(self._stderr_log_path, "wb")
        command = [
            self.executable,
            "--no-config",
            "--idle=yes",
            "--force-window=no",
            "--no-video",
            "--audio-display=no",
            "--demuxer-lavf-o=protocol_whitelist=file",
            "--terminal=no",
            "--msg-level=all=debug",
            f"--log-file={self._mpv_log_path}",
            "--pause=yes",
            f"--input-ipc-server={self._socket_path}",
        ]
        if self.audio_output:
            command.append(f"--ao={self.audio_output}")
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=self._stderr_log,
                close_fds=True,
            )
            deadline = time.monotonic() + self.startup_timeout
            while time.monotonic() < deadline:
                exit_code = self.process.poll()
                if exit_code is not None:
                    detail = self._read_startup_diagnostics()
                    message = (
                        "The audiobook playback engine stopped unexpectedly "
                        f"(exit code {exit_code})."
                    )
                    if detail:
                        message += "\n" + detail
                    raise AudiobookError(message)
                if os.path.exists(self._socket_path):
                    try:
                        self._connect_ipc()
                        return
                    except OSError:
                        self._disconnect_ipc()
                time.sleep(0.05)
            raise AudiobookError("The audiobook playback engine did not become ready.")
        except Exception:
            self.close()
            raise

    def _read_startup_diagnostics(self):
        """Read a bounded amount of mpv stderr before the private log is removed."""
        if self._stderr_log is not None:
            try:
                self._stderr_log.flush()
            except OSError:
                pass
        if not self._stderr_log_path:
            return ""
        chunks = []
        for path in (self._mpv_log_path, self._stderr_log_path):
            if not path:
                continue
            try:
                with open(path, "rb") as log_file:
                    data = log_file.read()[-5000:]
            except OSError:
                continue
            if data:
                chunks.append(data.decode("utf-8", errors="replace").strip())
        return "\n".join(chunk for chunk in chunks if chunk)

    def diagnostics(self):
        """Return the bounded MPV log tail before close removes its private files."""
        return self._read_startup_diagnostics()

    def _connect_ipc(self):
        """Connect once and retain the private mpv IPC stream for this session."""
        if self._ipc_socket is not None:
            return
        if not self._socket_path:
            raise AudiobookError("The audiobook playback engine is not running.")
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.command_timeout)
        try:
            connection.connect(self._socket_path)
        except OSError:
            connection.close()
            raise
        self._ipc_socket = connection
        self._ipc_buffer = bytearray()

    def _request(self, payload):
        """Serialize access to the shared MPV IPC stream across UI and worker threads."""
        with self._ipc_lock:
            return self._request_locked(payload)

    def _request_locked(self, payload):
        if not self._socket_path:
            raise AudiobookError("The audiobook playback engine is not running.")
        self._request_id += 1
        request_id = self._request_id
        message = dict(payload)
        message["request_id"] = request_id
        encoded = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self._connect_ipc()
            self._ipc_socket.sendall(encoded)
            while True:
                while b"\n" in self._ipc_buffer:
                    line, _, remainder = self._ipc_buffer.partition(b"\n")
                    self._ipc_buffer = bytearray(remainder)
                    try:
                        response = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    # Ignore asynchronous mpv events; wait for this command's reply.
                    if response.get("request_id") != request_id:
                        if "request_id" in response or "error" not in response:
                            continue
                    if response.get("error") != "success":
                        raise AudiobookError(
                            str(response.get("error") or "The playback command failed.")
                        )
                    return response.get("data")
                chunk = self._ipc_socket.recv(65536)
                if not chunk:
                    raise AudiobookError("The playback engine closed its IPC connection.")
                self._ipc_buffer.extend(chunk)
        except (OSError, socket.timeout):
            self._disconnect_ipc()
            raise

    def _disconnect_ipc(self):
        connection, self._ipc_socket = self._ipc_socket, None
        self._ipc_buffer = bytearray()
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass

    def command(self, *arguments):
        return self._request({"command": list(arguments)})

    def load(self, path):
        local_path = normalise_m4b_path(path)
        self.start()
        # Pause the current session before replacing media so opening a second
        # audiobook can never briefly start it playing automatically.
        self.command("set_property", "pause", True)
        self.command("loadfile", local_path, "replace")
        self.command("set_property", "pause", True)
        self.current_path = local_path
        # mpv acknowledges loadfile before FFmpeg has finished probing the
        # container. Wait briefly for duration metadata so the UI can restore
        # a saved position and populate chapter controls reliably.
        deadline = time.monotonic() + self.startup_timeout
        latest = self.status()
        while time.monotonic() < deadline:
            duration = latest.get("duration")
            try:
                if duration is not None and float(duration) > 0:
                    return latest
            except (TypeError, ValueError, OverflowError):
                pass
            if not self.process or self.process.poll() is not None:
                raise AudiobookError("The playback engine stopped while opening the audiobook.")
            time.sleep(0.05)
            latest = self.status()
        raise AudiobookError(
            "The M4B file could not be read or its audio track could not be loaded. "
            "It may be damaged, unsupported or DRM-protected."
        )

    def play_pause(self):
        paused = bool(self._request({"command": ["get_property", "pause"]}))
        self.command("set_property", "pause", not paused)
        # Return whether playback is active after the toggle (True = playing).
        return paused

    def play(self):
        self.command("set_property", "pause", False)

    def pause(self):
        self.command("set_property", "pause", True)

    def set_volume(self, value):
        try:
            volume = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError, OverflowError) as exc:
            raise AudiobookError("Enter a valid volume level.") from exc
        self.command("set_property", "volume", volume)
        return volume

    def set_mute(self, muted):
        self.command("set_property", "mute", bool(muted))
        return bool(muted)

    def set_speed(self, value):
        try:
            speed = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise AudiobookError("Choose a valid playback speed.") from exc
        if not 0.5 <= speed <= 2.0:
            raise AudiobookError("Playback speed must be between 0.5× and 2.0×.")
        self.command("set_property", "speed", speed)
        return speed

    def stop(self):
        if self.process and self.process.poll() is None:
            self.command("stop")
        self.current_path = None

    def seek(self, seconds):
        try:
            position = max(0.0, float(seconds))
        except (TypeError, ValueError, OverflowError) as exc:
            raise AudiobookError("Enter a valid listening position.") from exc
        self.command("seek", position, "absolute", "exact")

    def select_chapter(self, index):
        try:
            chapter_index = int(index)
        except (TypeError, ValueError) as exc:
            raise AudiobookError("Choose a valid chapter.") from exc
        if chapter_index < 0:
            raise AudiobookError("Choose a valid chapter.")
        self.command("set_property", "chapter", chapter_index)

    def status(self):
        def prop(name):
            try:
                return self._request({"command": ["get_property", name]})
            except AudiobookError:
                return None
        return {
            "time_pos": prop("time-pos"),
            "duration": prop("duration"),
            "paused": prop("pause"),
            "chapter": prop("chapter"),
            "chapters": chapter_rows(prop("chapter-list")),
            "metadata": prop("metadata") or {},
            "volume": prop("volume"),
            "mute": prop("mute"),
            "speed": prop("speed"),
        }

    def close(self):
        """Close MPV safely even if the background status monitor is polling."""
        with self._ipc_lock:
            self._close_locked()

    def _close_locked(self):
        self._disconnect_ipc()
        process, self.process = self.process, None
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        self.current_path = None
        stderr_log, self._stderr_log = self._stderr_log, None
        if stderr_log is not None:
            try:
                stderr_log.close()
            except OSError:
                pass
        runtime_dir, self._runtime_dir = self._runtime_dir, None
        self._socket_path = None
        self._stderr_log_path = None
        self._mpv_log_path = None
        if runtime_dir:
            shutil.rmtree(runtime_dir, ignore_errors=True)



class AudioWorker:
    """Own one MPV backend on one thread and serialise every audio operation.

    The Tk interface communicates through submit() and events only. The worker
    creates MPV, opens media, executes controls and polls status; no other
    thread is allowed to touch the backend or its IPC socket.
    """

    def __init__(self, backend_factory=None, poll_interval=1.0):
        import queue

        self._backend_factory = backend_factory or MPVBackend
        self._poll_interval = max(0.1, float(poll_interval))
        self._commands = queue.Queue()
        self.events = queue.Queue()
        self._shutdown_requested = threading.Event()
        self._backend = None
        self._active_path = None
        self._active_token = 0
        self._thread = threading.Thread(
            target=self._run, name="M4B audio owner", daemon=True
        )
        self._thread.start()

    def submit(self, action, token=0, *args):
        """Queue one operation for the sole MPV-owning thread."""
        if self._shutdown_requested.is_set():
            return False
        self._commands.put((str(action), int(token), args))
        return True

    def shutdown(self):
        """Ask the owner thread to close MPV after its current operation."""
        if not self._shutdown_requested.is_set():
            self._shutdown_requested.set()
            self._commands.put(("shutdown", 0, ()))

    def join(self, timeout=None):
        """Wait for worker shutdown; intended for tests, never the Tk event loop."""
        self._thread.join(timeout)

    @property
    def is_alive(self):
        return self._thread.is_alive()

    def _emit(self, event_type, token, **values):
        event = {"type": event_type, "token": token}
        event.update(values)
        self.events.put(event)

    def _open(self, token, path, restore_position=0.0, chapter_index=None):
        if self._backend is None:
            self._backend = self._backend_factory()
        try:
            status = self._backend.load(path)
            if chapter_index is not None:
                self._backend.select_chapter(chapter_index)
            elif restore_position and float(restore_position) > 0:
                self._backend.seek(float(restore_position))
            # Take the initial snapshot after restoring the requested position.
            status = self._backend.status()
            cover_bytes = extract_cover_art(path)
        except Exception as exc:
            self._active_path = None
            diagnostic = ""
            try:
                diagnostic = self._backend.diagnostics()
            except Exception:
                pass
            try:
                self._backend.close()
            except Exception:
                pass
            self._backend = None
            detail = f"{type(exc).__name__}: {exc}"
            if diagnostic:
                detail += "\\n\\nMPV diagnostics:\\n" + diagnostic
            raise AudiobookError(detail) from exc
        self._active_path = path
        self._active_token = token
        self._emit(
            "loaded", token, path=path, status=status, cover_bytes=cover_bytes
        )

    def _execute(self, action, token, args):
        if action == "open":
            path, restore_position, chapter_index = args
            self._open(token, path, restore_position, chapter_index)
            return
        if self._backend is None or not self._active_path:
            raise AudiobookError("Open an audiobook before using the playback controls.")

        if action == "play":
            self._backend.play()
        elif action == "pause":
            self._backend.pause()
        elif action == "volume":
            self._backend.set_volume(args[0])
        elif action == "mute":
            self._backend.set_mute(args[0])
        elif action == "speed":
            self._backend.set_speed(args[0])
        elif action == "seek":
            self._backend.seek(args[0])
        elif action == "chapter":
            self._backend.select_chapter(args[0])
        elif action == "stop":
            # Stop means return to the beginning while keeping the book loaded.
            self._backend.seek(0)
            self._backend.pause()
        else:
            raise AudiobookError("Unknown audiobook operation.")
        self._publish_status()

    def _publish_status(self):
        if self._backend is None or not self._active_path:
            return
        try:
            status = self._backend.status()
        except Exception as exc:
            self._emit(
                "error", self._active_token, action="status",
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        self._emit("status", self._active_token, status=status)

    def _run(self):
        """Run the command queue and periodic status reads on the same thread."""
        import queue

        next_poll = None
        try:
            while True:
                timeout = None
                if self._active_path:
                    if next_poll is None:
                        next_poll = time.monotonic() + self._poll_interval
                    timeout = max(0.0, next_poll - time.monotonic())
                try:
                    action, token, args = self._commands.get(timeout=timeout)
                except queue.Empty:
                    self._publish_status()
                    next_poll = time.monotonic() + self._poll_interval
                    continue

                if action == "shutdown":
                    break
                try:
                    self._execute(action, token, args)
                except Exception as exc:
                    if action == "open":
                        self._active_path = None
                    self._emit(
                        "error", token, action=action,
                        error=f"{type(exc).__name__}: {exc}",
                    )

                if self._active_path:
                    if next_poll is None:
                        next_poll = time.monotonic() + self._poll_interval
                    elif time.monotonic() >= next_poll:
                        self._publish_status()
                        next_poll = time.monotonic() + self._poll_interval
        finally:
            if self._backend is not None:
                try:
                    self._backend.close()
                except Exception:
                    pass
                self._backend = None
            self._active_path = None
