"""Optical-disc discovery for ISweep Host Playback.

This module only detects optical drives and standard DVD-Video folder
structure. It does not decrypt, copy, rip, or modify disc content.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiscCandidate:
    drive: str
    has_media: bool
    is_dvd_video: bool


def looks_like_dvd_video(root: str | Path) -> bool:
    """Return True when the source exposes a standard VIDEO_TS directory."""

    try:
        root_path = Path(root)
        return (root_path / "VIDEO_TS").is_dir()
    except OSError:
        return False


def find_windows_optical_drives() -> list[str]:
    """Return Windows drive roots whose type is CD-ROM/DVD/BD optical media."""

    if not sys.platform.startswith("win"):
        return []

    import ctypes

    DRIVE_CDROM = 5
    kernel32 = ctypes.windll.kernel32
    bitmask = kernel32.GetLogicalDrives()

    drives: list[str] = []

    for index in range(26):
        if not bitmask & (1 << index):
            continue

        root = f"{chr(ord('A') + index)}:\\"
        if kernel32.GetDriveTypeW(root) == DRIVE_CDROM:
            drives.append(root)

    return drives


def inspect_optical_drive(drive: str) -> DiscCandidate:
    """Inspect an optical drive without reading or changing the media."""

    has_media = False
    try:
        # Accessing the root is enough to distinguish an empty tray from a
        # mounted disc on normal Windows optical drives.
        has_media = os.path.exists(drive) and any(Path(drive).iterdir())
    except (OSError, PermissionError):
        has_media = False

    return DiscCandidate(
        drive=drive,
        has_media=has_media,
        is_dvd_video=has_media and looks_like_dvd_video(drive),
    )


def find_inserted_dvds() -> list[DiscCandidate]:
    """Return detected optical drives, including whether DVD-Video is present."""

    return [inspect_optical_drive(drive) for drive in find_windows_optical_drives()]
