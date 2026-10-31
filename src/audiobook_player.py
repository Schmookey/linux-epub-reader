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
            "--load-scripts=no",
            "--ytdl=no",
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

    def pause(self):
        self.command("set_property", "pause", True)

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
        }

    def close(self):
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
