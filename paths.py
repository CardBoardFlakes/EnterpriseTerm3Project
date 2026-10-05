"""
Where Flow keeps its files.

Run from source, settings, tasks, sounds and music live next to the modules
(the long-standing behaviour). A packaged app (PyInstaller ``Flow.app`` /
``Flow.exe``) can't write inside its own bundle, so it uses a per-user folder:

  * macOS   -> ~/Library/Application Support/Flow
  * Windows -> %APPDATA%\\Flow
  * other   -> $XDG_DATA_HOME/Flow (or ~/.local/share/Flow)
"""

import os
import sys

APP_NAME = "Flow"


def is_frozen() -> bool:
    """True when running from a packaged (PyInstaller) build."""
    return bool(getattr(sys, "frozen", False))


def user_data_dir(platform: str = sys.platform) -> str:
    home = os.path.expanduser("~")
    if platform == "win32":
        base = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    elif platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, APP_NAME)


def _data_dir() -> str:
    if not is_frozen():
        return os.path.dirname(os.path.abspath(__file__))
    path = user_data_dir()
    os.makedirs(path, exist_ok=True)
    return path


# Absolute base for config.json, tasks.json, sounds/ and music/.
DATA_DIR = _data_dir()
