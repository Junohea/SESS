"""
platform_defaults.py — detect default emulator base paths on Linux (SteamDeck / SteamOS).

Only `detect_linux_defaults()` is part of the public API.
Returns (ryujinx_base, citron_base) as Path objects, or None for any path not found on disk.
Always returns (None, None) on non-Linux systems.
"""

import platform
from pathlib import Path
from typing import Optional, Tuple


def detect_linux_defaults() -> Tuple[Optional[Path], Optional[Path]]:
    """Return (ryujinx_base, citron_base) for well-known Linux Flatpak / native locations.

    Checks candidate paths in priority order and returns the first that exists on disk.
    Returns None for either value if no matching path is found.
    Does nothing (returns (None, None)) when not running on Linux.
    """
    if platform.system() != "Linux":
        return None, None

    home = Path.home()

    ryujinx_base = _first_existing([
        home / ".var/app/org.ryujinx.Ryujinx/config/Ryujinx",   # Flatpak
        home / ".config/Ryujinx",                                  # native / AppImage
    ])

    citron_base = _first_existing([
        home / ".var/app/io.github.citron_emu.Citron/data/citron",  # Citron Flatpak
        home / ".local/share/citron",                                # Citron native
        home / ".var/app/org.yuzu_emu.yuzu/data/yuzu",              # Yuzu Flatpak (fallback)
        home / ".local/share/yuzu",                                  # Yuzu native (fallback)
    ])

    return ryujinx_base, citron_base


def _first_existing(paths: list) -> Optional[Path]:
    for p in paths:
        if p.exists() and p.is_dir():
            return p
    return None
