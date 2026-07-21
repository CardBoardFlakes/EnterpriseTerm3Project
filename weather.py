"""
Weather source for the Flow.

Provides live weather from Open-Meteo, but also supports:
  * a manual weather override (pick the condition yourself),
  * a manual day/night override,
  * a graceful offline fallback so the app still themes without a network.
"""

import datetime

# Conditions the rest of the app understands.
CONDITIONS = ["clear", "cloud", "rain", "storm"]

# Default location (overridden by config["location"]).
LAT = -33.8688   # Sydney
LON = 151.2093


def _default_sun_times():
    """Reasonable sunrise/sunset for today when we have no live data."""
    today = datetime.date.today()
    sunrise = datetime.datetime.combine(today, datetime.time(6, 30))
    sunset = datetime.datetime.combine(today, datetime.time(18, 30))
    return sunrise, sunset


def get_weather(lat: float = LAT, lon: float = LON) -> dict:
    """Fetch current weather + today's sun times from Open-Meteo."""
    # Deferred import so a missing 'requests' doesn't break the whole app.
    import requests

    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
        "is_day,rain,precipitation,showers,wind_speed_10m,wind_gusts_10m,"
        "wind_direction_10m,cloud_cover,pressure_msl,uv_index,weathercode"
        "&daily=sunrise,sunset,uv_index_max,precipitation_probability_max"
        "&timezone=auto"
    )

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to reach Open-Meteo: {e}") from e

    if "current" not in data or "daily" not in data:
        raise ValueError(f"Unexpected Open-Meteo response: {data}")

    current = data["current"]
    daily = data["daily"]

    sunrise = datetime.datetime.fromisoformat(daily["sunrise"][0])
    sunset = datetime.datetime.fromisoformat(daily["sunset"][0])

    rain_amount   = current.get("rain", 0) or 0
    precipitation = current.get("precipitation", 0) or 0
    showers       = current.get("showers", 0) or 0
    cloud_cover   = current.get("cloud_cover", 0) or 0
    wind_speed    = current.get("wind_speed_10m", 0) or 0
    is_day        = current.get("is_day", 1)

    # Determine condition in priority order.
    if (rain_amount > 0 or precipitation > 0 or showers > 0) and wind_speed >= 35:
        condition = "storm"
    elif rain_amount > 0 or precipitation > 0 or showers > 0:
        condition = "rain"
    elif cloud_cover >= 60:
        condition = "cloud"
    elif is_day == 1:
        condition = "clear"
    else:
        condition = "night"

    return {
        "condition":     condition,
        "sunrise":       sunrise,
        "sunset":        sunset,
        "is_day":        bool(is_day),
        "temperature":   current.get("temperature_2m"),
        "feels_like":    current.get("apparent_temperature"),
        "humidity":      current.get("relative_humidity_2m"),
        "uv_index":      current.get("uv_index"),
        "uv_index_max":  (daily.get("uv_index_max") or [None])[0],
        "pressure":      current.get("pressure_msl"),
        "rain":          rain_amount,
        "precip_chance": (daily.get("precipitation_probability_max") or [None])[0],
        "wind_speed":    wind_speed,
        "wind_gust":     current.get("wind_gusts_10m"),
        "wind_dir":      current.get("wind_direction_10m"),
        "cloud_cover":   cloud_cover,
    }


# Measurement keys carried straight from live data (never faked by overrides).
MEASUREMENT_KEYS = (
    "temperature", "feels_like", "humidity", "uv_index", "uv_index_max",
    "pressure", "rain", "precip_chance", "wind_speed", "wind_gust",
    "wind_dir", "cloud_cover",
)


def _is_night(sunrise, sunset, now=None) -> bool:
    now = now or datetime.datetime.now()
    return not (sunrise <= now <= sunset)


def location_coords(cfg: dict):
    """The configured city's coordinates (city-level by design)."""
    loc = cfg.get("location", {})
    try:
        return float(loc.get("lat", LAT)), float(loc.get("lon", LON))
    except (TypeError, ValueError):
        return LAT, LON


def get_live_weather(cfg: dict) -> dict:
    """
    The real measured weather for the configured location (temperature,
    humidity, UV, wind, …), tagged ``source`` = "live" or "fallback". This is
    always the true outside data — manual overrides never touch it.

    The location is a city picked in the GUI, so only a coarse, city-level
    position is ever used.
    """
    try:
        lat, lon = location_coords(cfg)
        w = get_weather(lat, lon)
        w["source"] = "live"
        return w
    except Exception as e:
        print(f"[weather] Live fetch failed ({e}); using fallback.")
        sunrise, sunset = _default_sun_times()
        w = {k: None for k in MEASUREMENT_KEYS}
        w.update({
            "condition": "clear",
            "sunrise": sunrise,
            "sunset": sunset,
            "is_day": not _is_night(sunrise, sunset),
            "source": "fallback",
        })
        return w


def apply_overrides(live: dict, cfg: dict, now=None) -> dict:
    """
    Return the weather the app should *act on*: the live data with manual
    weather/time overrides applied to the condition and day/night only. Live
    measurements carry through unchanged, so the dashboard keeps showing real
    UV / humidity / temperature even while a manual look is forced.

    Adds keys: "is_night" (bool) and "condition_source" ("manual"/live source).
    """
    w = dict(live)
    manual_weather = (cfg.get("manual_weather") or "auto").lower()
    manual_time = (cfg.get("manual_time") or "auto").lower()

    # Condition drives theme/wallpaper/sound — overridable; data stays live.
    if manual_weather in CONDITIONS:
        w["condition"] = manual_weather
        w["condition_source"] = "manual"
    else:
        w["condition_source"] = live.get("source", "live")

    # Day/night — "night" forces night; any daytime phase forces day.
    if manual_time == "night":
        w["is_night"] = True
    elif manual_time in ("day", "sunrise", "morning", "midday",
                         "afternoon", "sunset", "dusk"):
        w["is_night"] = False
    else:  # auto
        w["is_night"] = _is_night(w["sunrise"], w["sunset"], now)

    return w


def get_effective_weather(cfg: dict) -> dict:
    """Fetch live weather and apply manual overrides (one-shot convenience)."""
    return apply_overrides(get_live_weather(cfg), cfg)
