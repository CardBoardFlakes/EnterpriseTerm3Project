"""
Weather source for the Environment Theme Controller.

Provides live weather from Open-Meteo, but also supports:
  * a manual weather override (pick the condition yourself),
  * a manual day/night override,
  * a graceful offline fallback so the app still themes without a network.
"""

import datetime

# Conditions the rest of the app understands.
CONDITIONS = ["clear", "cloud", "rain", "storm", "night"]

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
        "&current=temperature_2m,is_day,rain,precipitation,showers,wind_speed_10m,cloud_cover,weathercode"
        "&daily=sunrise,sunset"
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
        "condition":   condition,
        "sunrise":     sunrise,
        "sunset":      sunset,
        "is_day":      bool(is_day),
        "temperature": current.get("temperature_2m"),
        "rain":        rain_amount,
        "wind_speed":  wind_speed,
        "cloud_cover": cloud_cover,
    }


def _is_night(sunrise, sunset, now=None) -> bool:
    now = now or datetime.datetime.now()
    return not (sunrise <= now <= sunset)


def get_effective_weather(cfg: dict) -> dict:
    """
    Return the weather the app should act on, honouring manual overrides
    and falling back to a sane default when live data is unavailable.

    Adds keys: "is_night" (bool) and "source" ("manual"/"live"/"fallback").
    """
    manual_weather = (cfg.get("manual_weather") or "auto").lower()
    manual_time = (cfg.get("manual_time") or "auto").lower()

    # --- Manual weather override ---------------------------------------
    if manual_weather != "auto":
        sunrise, sunset = _default_sun_times()
        w = {
            "condition": manual_weather,
            "sunrise": sunrise,
            "sunset": sunset,
            "is_day": manual_weather != "night",
            "temperature": None,
            "rain": 1 if manual_weather in ("rain", "storm") else 0,
            "wind_speed": 40 if manual_weather == "storm" else 0,
            "cloud_cover": 80 if manual_weather in ("cloud", "rain", "storm") else 0,
            "source": "manual",
        }
    else:
        # --- Live weather, with offline fallback -----------------------
        loc = cfg.get("location", {})
        try:
            w = get_weather(loc.get("lat", LAT), loc.get("lon", LON))
            w["source"] = "live"
        except Exception as e:
            print(f"[weather] Live fetch failed ({e}); using fallback.")
            sunrise, sunset = _default_sun_times()
            w = {
                "condition": "clear",
                "sunrise": sunrise,
                "sunset": sunset,
                "is_day": not _is_night(sunrise, sunset),
                "temperature": None,
                "rain": 0,
                "wind_speed": 0,
                "cloud_cover": 0,
                "source": "fallback",
            }

    # --- Manual day/night override -------------------------------------
    if manual_time == "night":
        w["is_night"] = True
    elif manual_time == "day":
        w["is_night"] = False
    else:
        w["is_night"] = _is_night(w["sunrise"], w["sunset"])

    return w
