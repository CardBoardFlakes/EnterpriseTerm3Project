"""
Central configuration for the Environment Theme Controller.

A single source of truth for defaults + load/save, used by both the GUI
and the background engine so the two never drift apart.
"""

import copy
import json
import os

CONFIG_FILE = "config.json"

# Master defaults. Every setting the app understands lives here.
DEFAULTS = {
    # Master switch — when False the engine does nothing at all.
    "enabled": True,

    # Per-feature switches.
    "features": {
        "dynamic_theme": True,    # OS accent colour follows the weather
        "wallpaper":     True,    # desktop background follows the weather
        "ambient_sound": True,    # subtle weather/time ambience
        "tasks":         True,    # run user tasks & schedules
    },

    # Theme.
    "weather_tint_strength": 40,  # percent 0-100 (reserved for blending)

    # Sound.
    "sound_volume": 25,           # percent 0-100 — "subtle" by default

    # Location used for live weather (Open-Meteo).
    "location": {"lat": -33.8688, "lon": 151.2093, "name": "Sydney"},

    # Manual overrides. "auto" / None means "use live data".
    "manual_weather": "auto",     # auto|clear|cloud|rain|storm|night
    "manual_time":    "auto",     # auto|day|night
    "manual_theme_color": None,   # null or [r, g, b]

    # Start automatically when the user logs in.
    "run_at_login": False,

    # How often the background engine re-evaluates everything.
    "poll_interval_seconds": 300,
}

# Allowed values for the override dropdowns — shared with the GUI.
WEATHER_CHOICES = ["auto", "clear", "cloud", "rain", "storm", "night"]
TIME_CHOICES = ["auto", "day", "night"]
FEATURE_KEYS = ["dynamic_theme", "wallpaper", "ambient_sound", "tasks"]


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge *override* into a deep copy of *base*.

    Deep-copying matters: it guarantees the returned config shares no
    mutable state with DEFAULTS, so mutating one loaded config can never
    corrupt the module-level defaults (or any other config).
    """
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def default_config() -> dict:
    """A fresh, fully-populated config dict (independent of DEFAULTS)."""
    return copy.deepcopy(DEFAULTS)


def load_config(path: str = CONFIG_FILE) -> dict:
    """Load config from *path*, filling any missing keys from DEFAULTS."""
    if not os.path.exists(path):
        return default_config()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("config root is not an object")
        return _deep_merge(DEFAULTS, data)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f"[config] Could not load {path}, using defaults: {e}")
        return default_config()


def save_config(cfg: dict, path: str = CONFIG_FILE) -> bool:
    """Persist *cfg* to *path*. Returns True on success."""
    try:
        with open(path, "w") as f:
            json.dump(cfg, f, indent=2)
        return True
    except OSError as e:
        print(f"[config] Could not save {path}: {e}")
        return False


def feature_enabled(cfg: dict, feature: str) -> bool:
    """True only if the master switch AND the named feature are both on."""
    if not cfg.get("enabled", True):
        return False
    return bool(cfg.get("features", {}).get(feature, True))
