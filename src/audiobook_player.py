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

    def __init__(self, executable=None, startup_timeout=5.0, command_timeout=2.0,
                 audio_output=None):
        self.executable = executable or shutil.which("mpv")
        self.startup_timeout = float(startup_timeout)
        self.command_timeout = float(command_timeout)
        self.audio_output = audio_output
        self.process = None
        self._runtime_dir = None
        self._socket_path = None
        self._request_id = 0
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
            "--pause=yes",
            f"--input-ipc-server={self._socket_path}",
        ]
        if self.audio_output:
            command.append(f"--ao={self.audio_output}")
        try:
            self.process = subprocess.Popen(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            deadline = time.monotonic() + self.startup_timeout
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise AudiobookError("The audiobook playback engine stopped unexpectedly.")
                if os.path.exists(self._socket_path):
                    try:
                        self._request({"command": ["get_property", "idle-active"]})
                        return
                    except (OSError, AudiobookError, socket.timeout):
                        pass
                time.sleep(0.05)
            raise AudiobookError("The audiobook playback engine did not become ready.")
        except Exception:
            self.close()
            raise

    def _request(self, payload):
        if not self._socket_path:
            raise AudiobookError("The audiobook playback engine is not running.")
        self._request_id += 1
        request_id = self._request_id
        message = dict(payload)
        message["request_id"] = request_id
        encoded = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.command_timeout)
            connection.connect(self._socket_path)
            connection.sendall(encoded)
            received = bytearray()
            while b"\n" not in received:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                received.extend(chunk)
        for line in received.splitlines():
            try:
                response = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if response.get("request_id") == request_id:
                if response.get("error") != "success":
                    raise AudiobookError(
                        str(response.get("error") or "The playback command failed.")
                    )
                return response.get("data")
        raise AudiobookError("The playback engine did not return a valid response.")

    def command(self, *arguments):
        return self._request({"command": list(arguments)})

    def load(self, path):
        local_path = normalise_m4b_path(path)
        self.start()
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
        return not paused

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
        runtime_dir, self._runtime_dir = self._runtime_dir, None
        self._socket_path = None
        if runtime_dir:
            shutil.rmtree(runtime_dir, ignore_errors=True)
