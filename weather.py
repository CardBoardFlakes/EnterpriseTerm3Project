import requests
import datetime

LAT = -33.8688   # Sydney — replace with your location
LON = 151.2093


def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        f"latitude={LAT}&longitude={LON}"
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

    # Extract sunrise/sunset for today
    sunrise = datetime.datetime.fromisoformat(daily["sunrise"][0])
    sunset = datetime.datetime.fromisoformat(daily["sunset"][0])

    rain_amount    = current.get("rain", 0) or 0
    precipitation  = current.get("precipitation", 0) or 0
    showers        = current.get("showers", 0) or 0
    cloud_cover    = current.get("cloud_cover", 0) or 0   # 0-100 %
    is_day         = current.get("is_day", 1)

    # Determine condition in priority order
    if rain_amount > 0 or precipitation > 0 or showers > 0:
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
        "temperature": current.get("temperature_2m"),
        "rain":        rain_amount,
        "wind_speed":  current.get("wind_speed_10m"),
        "cloud_cover": cloud_cover,
    }