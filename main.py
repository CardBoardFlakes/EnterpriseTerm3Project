import json
import os
from weather import get_weather
from theme import apply_dynamic_theme
from sound import play_sound, stop_sound
from activity import get_idle_time

CONFIG_FILE = "config.json"

IDLE_THRESHOLD_SECONDS = 5  # seconds of inactivity before sounds play


def load_config():
    defaults = {
        "enable_dynamic_theme": True,
        "enable_weather_sound": True,
        "weather_tint_strength": 40
    }
    if not os.path.exists(CONFIG_FILE):
        return defaults
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        defaults.update(data)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[main] Could not load config, using defaults: {e}")
    return defaults


def main():
    cfg = load_config()

    # --- Fetch weather ---
    try:
        w = get_weather()
    except Exception as e:
        print(f"[main] Weather fetch failed: {e}")
        return

    # --- Apply dynamic theme ---
    if cfg.get("enable_dynamic_theme", True):
        try:
            apply_dynamic_theme(
                condition=w["condition"],
                sunrise=w["sunrise"],
                sunset=w["sunset"],
                tint_strength=cfg.get("weather_tint_strength", 40) / 100.0
            )
        except Exception as e:
            print(f"[main] Theme apply failed: {e}")

    # --- Handle ambient sound ---
    if not cfg.get("enable_weather_sound", True):
        stop_sound()
        return

    # FIX: Play sounds when the user is IDLE (away from keyboard).
    #      Stop sounds when the user is actively using the machine.
    try:
        idle = get_idle_time()
    except Exception as e:
        print(f"[main] Could not get idle time: {e}")
        idle = 0

    if idle < IDLE_THRESHOLD_SECONDS:
        # User is active — stop ambient sounds
        stop_sound()
        return

    # User is idle — play weather-appropriate ambient sound
    condition = w["condition"]

    if "rain" in condition:
        play_sound("sounds/rain-soft.mp3")
    elif "clear" in condition:
        play_sound("sounds/birds.mp3")
    else:
        # night, cloudy, unknown
        play_sound("sounds/wind.mp3")


if __name__ == "__main__":
    main()