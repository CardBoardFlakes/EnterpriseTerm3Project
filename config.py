"""
Central configuration for the Flow.

A single source of truth for defaults + load/save, used by both the GUI
and the background engine so the two never drift apart.
"""

import copy
import json
import os

# Absolute path next to this module, so the app reads/writes the SAME config
# no matter which directory it's launched from. (A relative "config.json" would
# resolve against the launch directory, silently creating a second config when
# started from the parent folder — the desktop then never seemed to change.)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

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

    # Theme. Higher = more vivid weather colour (lower blends toward neutral).
    "weather_tint_strength": 72,  # percent 0-100

    # Wallpaper — subtle, continuous colour drift so the desktop feels alive.
    "wallpaper_dynamic": True,            # enable the slow colour shift
    "wallpaper_shift_strength": 35,       # percent 0-100 — drift amplitude
    "wallpaper_min_interval_seconds": 45, # never redraw more often than this
    # Re-apply the wallpaper at least this often even when nothing changed, so
    # the visible Space catches up after you leave a fullscreen app (macOS only
    # sets the current Space's desktop). 0 disables the periodic refresh.
    "wallpaper_refresh_seconds": 90,
    "wallpaper_patterns": True,           # weather-specific patterns (rain, sun, stars…)
    "wallpaper_warmth": True,             # warm the palette when it's cold outside

    # Sound.
    "sound_volume": 25,           # percent 0-100 — "subtle" by default
    # Playback style: "loop" plays the ambience continuously; "random" plays a
    # single (randomly chosen) clip now and then, roughly every N minutes.
    "sound_mode": "loop",         # loop | random
    "sound_interval_minutes": 5,  # random mode: average gap between plays
    "music_volume": 60,           # your own music (separate from ambience)
    # Pause the app's ambient sound while other audio is playing (our own music
    # player, or — best effort — another app like Spotify / Apple Music).
    "pause_when_other_audio": False,

    # Location used for live weather (Open-Meteo). Chosen from a list of cities
    # in the GUI, so only a coarse, city-level position is ever used.
    "location": {"lat": -33.8688, "lon": 151.2093, "name": "Sydney"},

    # Manual overrides. "auto" / None means "use live data".
    "manual_weather": "auto",     # auto|clear|cloud|rain|storm|night
    "manual_time":    "auto",     # auto | sunrise|morning|midday|afternoon|sunset|dusk|night
    "manual_theme_color": None,   # null or [r, g, b]

    # Gradual transitions: time-of-day colour changes continuously, and weather
    # changes cross-fade over this many seconds instead of snapping.
    "smooth_transitions": True,
    "theme_transition_seconds": 8,

    # Seasons nudge the palette (fresh green spring, golden summer, amber
    # autumn, cool-blue winter). Hemisphere flips the calendar; "auto" derives
    # it from the location latitude.
    "seasonal_themes": True,
    "hemisphere": "auto",         # auto|north|south

    # Mood profiles overlay the theme + feel. "none" = off.
    "active_profile": "none",     # none|focus|creativity|relax

    # Accessibility. "high_contrast" forces bold, maximum-contrast colours and
    # a high-contrast GUI regardless of the time of day.
    "accessibility_mode": "none", # none|high_contrast

    # Lock the device's Dark/Light appearance. "auto" follows day/night.
    "appearance_mode": "auto",    # auto|dark|light

    # Set the wallpaper on every connected monitor (not just the primary).
    "multi_monitor": True,

    # Start automatically when the user logs in.
    "run_at_login": False,

    # Engine cadence. The loop steps cheaply every tick_interval; live weather
    # is only refetched every weather_refresh (expensive work runs on change).
    "tick_interval_seconds": 30,
    "weather_refresh_seconds": 600,

    # Countdown ("standard") timer — last-used duration in minutes.
    "countdown_minutes": 10,

    # Productivity (Pomodoro) timer durations, in minutes.
    "pomodoro": {
        "work_min": 25,
        "break_min": 5,
        "long_break_min": 15,
        "cycles_before_long": 4,
    },
}

# Allowed values for the override dropdowns — shared with the GUI.
WEATHER_CHOICES = ["auto", "clear", "cloud", "rain", "storm", "night"]
TIME_CHOICES = ["auto", "sunrise", "morning", "midday", "afternoon", "sunset", "dusk", "night"]
FEATURE_KEYS = ["dynamic_theme", "wallpaper", "ambient_sound", "tasks"]
SOUND_MODES = ["loop", "random"]
PROFILE_CHOICES = ["none", "focus", "creativity", "relax"]
ACCESSIBILITY_CHOICES = ["none", "high_contrast"]
HEMISPHERE_CHOICES = ["auto", "north", "south"]
APPEARANCE_CHOICES = ["auto", "dark", "light"]

# Major cities the user can pick from instead of editing lat/lon by hand.
# Keyed by display label -> {lat, lon, name}. `name` is the short label shown
# on the weather card. Ordered roughly by region for a tidy dropdown.
CITIES = {
    # Oceania
    "Sydney, Australia":      {"lat": -33.8688, "lon": 151.2093, "name": "Sydney"},
    "Melbourne, Australia":   {"lat": -37.8136, "lon": 144.9631, "name": "Melbourne"},
    "Brisbane, Australia":    {"lat": -27.4698, "lon": 153.0251, "name": "Brisbane"},
    "Perth, Australia":       {"lat": -31.9523, "lon": 115.8613, "name": "Perth"},
    "Auckland, New Zealand":  {"lat": -36.8485, "lon": 174.7633, "name": "Auckland"},
    # Asia
    "Tokyo, Japan":           {"lat": 35.6762,  "lon": 139.6503, "name": "Tokyo"},
    "Singapore":              {"lat": 1.3521,   "lon": 103.8198, "name": "Singapore"},
    "Hong Kong":              {"lat": 22.3193,  "lon": 114.1694, "name": "Hong Kong"},
    "Shanghai, China":        {"lat": 31.2304,  "lon": 121.4737, "name": "Shanghai"},
    "Beijing, China":         {"lat": 39.9042,  "lon": 116.4074, "name": "Beijing"},
    "Seoul, South Korea":     {"lat": 37.5665,  "lon": 126.9780, "name": "Seoul"},
    "Mumbai, India":          {"lat": 19.0760,  "lon": 72.8777,  "name": "Mumbai"},
    "Delhi, India":           {"lat": 28.6139,  "lon": 77.2090,  "name": "Delhi"},
    "Bangkok, Thailand":      {"lat": 13.7563,  "lon": 100.5018, "name": "Bangkok"},
    "Dubai, UAE":             {"lat": 25.2048,  "lon": 55.2708,  "name": "Dubai"},
    # Europe
    "London, UK":             {"lat": 51.5074,  "lon": -0.1278,  "name": "London"},
    "Paris, France":          {"lat": 48.8566,  "lon": 2.3522,   "name": "Paris"},
    "Berlin, Germany":        {"lat": 52.5200,  "lon": 13.4050,  "name": "Berlin"},
    "Madrid, Spain":          {"lat": 40.4168,  "lon": -3.7038,  "name": "Madrid"},
    "Rome, Italy":            {"lat": 41.9028,  "lon": 12.4964,  "name": "Rome"},
    "Amsterdam, Netherlands": {"lat": 52.3676,  "lon": 4.9041,   "name": "Amsterdam"},
    "Moscow, Russia":         {"lat": 55.7558,  "lon": 37.6173,  "name": "Moscow"},
    "Istanbul, Turkey":       {"lat": 41.0082,  "lon": 28.9784,  "name": "Istanbul"},
    # Africa
    "Cairo, Egypt":           {"lat": 30.0444,  "lon": 31.2357,  "name": "Cairo"},
    "Lagos, Nigeria":         {"lat": 6.5244,   "lon": 3.3792,   "name": "Lagos"},
    "Johannesburg, S. Africa":{"lat": -26.2041, "lon": 28.0473,  "name": "Johannesburg"},
    "Nairobi, Kenya":         {"lat": -1.2921,  "lon": 36.8219,  "name": "Nairobi"},
    # North America
    "New York, USA":          {"lat": 40.7128,  "lon": -74.0060, "name": "New York"},
    "Los Angeles, USA":       {"lat": 34.0522,  "lon": -118.2437,"name": "Los Angeles"},
    "Chicago, USA":           {"lat": 41.8781,  "lon": -87.6298, "name": "Chicago"},
    "Toronto, Canada":        {"lat": 43.6532,  "lon": -79.3832, "name": "Toronto"},
    "Vancouver, Canada":      {"lat": 49.2827,  "lon": -123.1207,"name": "Vancouver"},
    "Mexico City, Mexico":    {"lat": 19.4326,  "lon": -99.1332, "name": "Mexico City"},
    # South America
    "São Paulo, Brazil":      {"lat": -23.5505, "lon": -46.6333, "name": "São Paulo"},
    "Rio de Janeiro, Brazil": {"lat": -22.9068, "lon": -43.1729, "name": "Rio de Janeiro"},
    "Buenos Aires, Argentina":{"lat": -34.6037, "lon": -58.3816, "name": "Buenos Aires"},
    "Lima, Peru":             {"lat": -12.0464, "lon": -77.0428, "name": "Lima"},
    "Santiago, Chile":        {"lat": -33.4489, "lon": -70.6693, "name": "Santiago"},
}


def city_choices():
    """Dropdown values: every listed city."""
    return list(CITIES.keys())


def city_label_for(cfg: dict) -> str:
    """The dropdown label matching cfg's location, else the first city.

    Matches on the stored name first, then on (lat, lon) so a config that only
    carries coordinates still resolves to the right city."""
    loc = cfg.get("location", {}) or {}
    name = (loc.get("name") or "").strip()
    for label, c in CITIES.items():
        if name and c["name"].lower() == name.lower():
            return label
    try:
        lat, lon = float(loc.get("lat")), float(loc.get("lon"))
        for label, c in CITIES.items():
            if abs(c["lat"] - lat) < 0.01 and abs(c["lon"] - lon) < 0.01:
                return label
    except (TypeError, ValueError):
        pass
    return next(iter(CITIES))


def location_for_city(label: str):
    """The location dict for a city label, or None if the label is unknown."""
    c = CITIES.get(label)
    return dict(c) if c else None


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


# Settings that used to exist but have since been removed. They're stripped
# from any loaded config so old files get cleaned up on the next save.
RETIRED_KEYS = ("location_precision", "wallpaper_backend", "wallpaper_animated",
                "wallpaper_animated_fps", "wallpaper_load_ceiling")


def load_config(path: str = CONFIG_FILE) -> dict:
    """Load config from *path*, filling any missing keys from DEFAULTS."""
    if not os.path.exists(path):
        return default_config()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("config root is not an object")
        for k in RETIRED_KEYS:
            data.pop(k, None)
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
