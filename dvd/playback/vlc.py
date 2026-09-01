"""Real libVLC-backed playback controller for ISweep Host Playback.

This module gives ISweep direct software control over media playback while
keeping the Decision Engine independent from VLC.  The media itself is never
modified; ISweep only changes the live player state.

`python-vlc` is imported lazily so the website, browser extension, backend,
and normal DVD tests do not require VLC to be installed.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from .models import MediaKind, MediaSource, PlaybackState, PlaybackStatus


class VLCUnavailableError(RuntimeError):
    """Raised when the VLC runtime/bindings are unavailable on this computer."""


def _prepare_windows_vlc_runtime() -> None:
    """Add common 64-bit/32-bit VLC install folders to Windows DLL search."""

    if not sys.platform.startswith("win"):
        return

    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name)
        if root:
            candidates.append(Path(root) / "VideoLAN" / "VLC")

    for candidate in candidates:
        libvlc = candidate / "libvlc.dll"
        if not libvlc.exists():
            continue

        candidate_text = str(candidate)
        os.environ["PATH"] = candidate_text + os.pathsep + os.environ.get("PATH", "")

        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                add_dll_directory(candidate_text)
            except OSError:
                pass
        return


def _load_vlc_module() -> Any:
    """Load python-vlc only when the real player is requested."""

    _prepare_windows_vlc_runtime()

    try:
        return importlib.import_module("vlc")
    except (ImportError, OSError) as exc:
        raise VLCUnavailableError(
            "ISweep Player could not load VLC. Install the VLC desktop runtime "
            "and then install the Python binding with: "
            "pip install -r dvd/requirements-player.txt"
        ) from exc


def dvd_mrl(location: str) -> str:
    """Convert a Windows DVD drive/root into a VLC DVD media location."""

    raw = str(location).strip()
    if raw.lower().startswith("dvd://"):
        return raw

    normalized = raw.replace("\\", "/")

    # Windows drive root: D:\ or D:/ -> dvd:///D:/
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[:2]
        return f"dvd:///{drive}/"

    # libVLC also accepts a mounted DVD folder after dvd://.
    return "dvd://" + normalized


class VLCPlaybackController:
    """PlaybackController implementation backed by libVLC.

    The controller owns one libVLC MediaPlayer.  A UI can optionally attach a
    native video surface with :meth:`set_video_output`.
    """

    def __init__(
        self,
        *,
        vlc_module: Any | None = None,
        instance: Any | None = None,
    ) -> None:
        self._vlc = vlc_module or _load_vlc_module()

        try:
            self._instance = instance or self._vlc.Instance(
                "--no-video-title-show",
                "--quiet",
            )
            self._player = self._instance.media_player_new()
        except Exception as exc:  # libVLC can raise platform-specific errors
            raise VLCUnavailableError(
                "VLC is installed but ISweep could not create a media player."
            ) from exc

        self._source: MediaSource | None = None
        self._muted = False

    @property
    def player(self) -> Any:
        """Expose the native player for UI integration only."""

        return self._player

    def set_video_output(self, native_window_id: int) -> None:
        """Render video into an existing UI widget/window."""

        if native_window_id <= 0:
            return

        if sys.platform.startswith("win"):
            self._player.set_hwnd(native_window_id)
        elif sys.platform == "darwin":
            setter = getattr(self._player, "set_nsobject", None)
            if setter:
                setter(native_window_id)
        else:
            setter = getattr(self._player, "set_xwindow", None)
            if setter:
                setter(native_window_id)

    def load(self, source: MediaSource) -> None:
        """Load a file, stream, or DVD source without changing the media."""

        if source.kind == MediaKind.DVD:
            media_location = dvd_mrl(source.location)
            media = self._instance.media_new(media_location)
        elif source.kind == MediaKind.FILE:
            path = str(Path(source.location).expanduser().resolve())
            media = self._instance.media_new(path)
        else:
            media = self._instance.media_new(source.location)

        self._player.set_media(media)
        self._source = source
        self._muted = False

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        # set_pause is deterministic; player.pause() is a toggle.
        setter = getattr(self._player, "set_pause", None)
        if setter is not None:
            setter(1)
        else:
            self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def mute(self) -> None:
        self._player.audio_set_mute(True)
        self._muted = True

    def unmute(self) -> None:
        self._player.audio_set_mute(False)
        self._muted = False

    def seek_relative(self, seconds: float) -> None:
        current_ms = self._safe_int(self._player.get_time(), default=0)
        length_ms = self._safe_int(self._player.get_length(), default=-1)
        target_ms = max(0, current_ms + int(seconds * 1000))

        if length_ms > 0:
            target_ms = min(target_ms, length_ms)

        self._player.set_time(target_ms)

    def get_state(self) -> PlaybackState:
        current_ms = self._safe_int(self._player.get_time(), default=0)
        length_ms = self._safe_int(self._player.get_length(), default=-1)
        volume_raw = self._safe_int(self._player.audio_get_volume(), default=100)

        status = self._map_status(self._player.get_state())
        duration = length_ms / 1000.0 if length_ms >= 0 else None

        return PlaybackState(
            source=self._source,
            status=status,
            position_seconds=max(0.0, current_ms / 1000.0),
            duration_seconds=duration,
            muted=self._read_muted_state(),
            volume=max(0.0, min(1.0, volume_raw / 100.0)),
        )

    def _read_muted_state(self) -> bool:
        getter = getattr(self._player, "audio_get_mute", None)
        if getter is None:
            return self._muted

        try:
            value = getter()
        except Exception:
            return self._muted

        if value in (0, False):
            return False
        if value in (1, True):
            return True
        return self._muted

    def _map_status(self, native_state: Any) -> PlaybackStatus:
        state = getattr(self._vlc, "State", None)

        if state is not None:
            if native_state == getattr(state, "Playing", object()):
                return PlaybackStatus.PLAYING
            if native_state == getattr(state, "Paused", object()):
                return PlaybackStatus.PAUSED

        # Fallback helps tests and unusual bindings that expose string states.
        name = str(native_state).lower()
        if "playing" in name:
            return PlaybackStatus.PLAYING
        if "paused" in name:
            return PlaybackStatus.PAUSED
        return PlaybackStatus.STOPPED

    @staticmethod
    def _safe_int(value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
