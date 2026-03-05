"""
NervaOS paths - Writable data directory for DBs and runtime data

Uses ~/.local/share/nervaos/data (XDG data dir) so SQLite and other
writes always use a user-writable location. Avoids "readonly database"
errors when ~/.config is restrictive or on read-only mounts.
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger("nerva-paths")


def get_nervaos_data_dir() -> Path:
    """Return ~/.local/share/nervaos/data (user-writable data directory)."""
    base = Path.home() / ".local" / "share" / "nervaos"
    return base / "data"


def ensure_data_dir() -> Path:
    """
    Create data dir with mode 0o700 if missing. Return path.
    Use this before opening SQLite DBs or other data files.
    """
    data_dir = get_nervaos_data_dir()
    try:
        os.makedirs(str(data_dir), mode=0o700, exist_ok=True)
        if not os.access(str(data_dir), os.W_OK):
            logger.warning("Data dir exists but is not writable: %s", data_dir)
    except OSError as e:
        logger.error("Failed to create data dir %s: %s", data_dir, e)
        raise
    return data_dir
