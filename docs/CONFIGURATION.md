# Configuration Reference

All settings live in **`config.json`** in the project folder. The GUI writes it
for you, but you can edit it by hand (close the app first, or press Save/Start
afterward to reload). Missing keys fall back to the defaults below, and an
unreadable file is replaced with defaults rather than crashing.

- [File locations](#file-locations)
- [Top level](#top-level)
- [Features](#features)
- [Wallpaper](#wallpaper)
- [Sound](#sound)
- [Location](#location)
- [Manual overrides](#manual-overrides)
- [Engine cadence](#engine-cadence)
- [Pomodoro](#pomodoro)
- [Example](#example-configjson)

---

## File locations

| What | Path |
|---|---|
| Settings | `config.json` (project folder) |
| Tasks | `tasks.json` (project folder) — see [tasks guide](TASKS_AND_TIMER.md) |
| Ambient sounds | `sounds/` (project folder) |
| Generated PNG wallpaper | `~/.environment_theme_controller/` |
| "Ultra" web wallpaper assets | `~/.environment_theme_controller/webwallpaper/` |

---

## Top level

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `true` | Master switch. When `false`, the engine does nothing. |

## Features

Under `"features"`; each is ANDed with the master switch.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `dynamic_theme` | bool | `true` | OS accent colour follows the weather. |
| `wallpaper` | bool | `true` | Desktop background follows the weather. |
| `ambient_sound` | bool | `true` | Weather/time soundscape. |
| `tasks` | bool | `true` | Run scheduled tasks. |

## Wallpaper

| Key | Type | Default | Meaning |
|---|---|---|---|
| `weather_tint_strength` | int 0–100 | `40` | How strongly the weather colour shows vs. neutral. |
| `wallpaper_dynamic` | bool | `true` | Slow, subtle colour drift. |
| `wallpaper_shift_strength` | int 0–100 | `35` | Amplitude of that drift. |
| `wallpaper_patterns` | bool | `true` | Weather patterns (rain/sun/clouds/stars). |
| `wallpaper_warmth` | bool | `true` | Warm the palette when it's cold outside. |
| `wallpaper_min_interval_seconds` | int | `45` | Minimum gap between static wallpaper redraws. |
| `wallpaper_backend` | `"png"` \| `"web"` | `"png"` | `png` = built-in image; `web` = external-engine ("Ultra") HTML wallpaper. |
| `wallpaper_animated` | bool | `false` | Built-in ("Smooth") continuous animation, for the `png` backend. |
| `wallpaper_animated_fps` | int 1–30 | `6` | Target frame rate for Smooth animation. |
| `wallpaper_load_ceiling` | int 0–100 | `85` | Per-core system-load % above which the animation governor throttles/pauses. |

> The GUI's **Wallpaper motion** chooser maps to these: **Off** = `png` +
> `animated:false`; **Smooth** = `png` + `animated:true`; **Ultra** = `web`.
> See the [wallpaper guide](WALLPAPER.md).

## Sound

| Key | Type | Default | Meaning |
|---|---|---|---|
| `sound_volume` | int 0–100 | `25` | Ambient volume. |
| `sound_mode` | `"loop"` \| `"random"` | `"loop"` | Continuous loop, or occasional one-shot clips. |
| `sound_interval_minutes` | int | `5` | Average gap between plays in `random` mode. |

See the [sound guide](SOUNDS.md) for file names and variants.

## Location

Used for live weather (Open-Meteo). Pick your **City** from the dropdown in
Appearance → Engine — it fills in the coordinates for you, and only that
city-level position is ever used.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `location.lat` | float | `-33.8688` | Latitude (set by the city picker). |
| `location.lon` | float | `151.2093` | Longitude (set by the city picker). |
| `location.name` | string | `"Sydney"` | Label shown on the weather card. |

To use a city that isn't in the list, set these by hand from any maps app.
Example (London):

```json
"location": { "lat": 51.5072, "lon": -0.1276, "name": "London" }
```

## Profiles, seasons, transitions & accessibility

| Key | Type | Default | Meaning |
|---|---|---|---|
| `active_profile` | `none`/`focus`/`creativity`/`relax` | `"none"` | Mood profile overlaying colours, motion and sound. |
| `smooth_transitions` | bool | `true` | Cross-fade colours on time/weather changes instead of snapping. |
| `theme_transition_seconds` | int | `8` | How long a weather cross-fade takes. |
| `seasonal_themes` | bool | `true` | Apply a seasonal wash to the palette. |
| `hemisphere` | `auto`/`north`/`south` | `"auto"` | Season calendar; `auto` uses the location latitude. |
| `accessibility_mode` | `none`/`high_contrast` | `"none"` | `high_contrast` forces bold colours + a high-contrast window. |
| `appearance_mode` | `auto`/`dark`/`light` | `"auto"` | Lock the device Dark/Light appearance; `auto` follows the time of day. |
| `multi_monitor` | bool | `true` | Set the wallpaper on every connected display. |

## Manual overrides

| Key | Type | Default | Meaning |
|---|---|---|---|
| `manual_weather` | `auto`/`clear`/`cloud`/`rain`/`storm`/`night` | `"auto"` | Force a condition, or `auto` for live data. |
| `manual_time` | `auto` / `sunrise` / `morning` / `midday` / `afternoon` / `sunset` / `dusk` / `night` | `"auto"` | Force a time-of-day phase (tints the theme + wallpaper and sets brightness / Dark mode). `auto` follows the real sun. Legacy `day` = `midday`. |
| `manual_theme_color` | `null` or `[r,g,b]` | `null` | Force an exact accent colour; `null` = derive from weather. |
| `run_at_login` | bool | `false` | Reflects the run-at-login launcher state. |

## Engine cadence

| Key | Type | Default | Meaning |
|---|---|---|---|
| `tick_interval_seconds` | int ≥5 | `30` | How often the engine steps. |
| `weather_refresh_seconds` | int ≥30 | `600` | How often live weather is refetched (expensive work only runs on change). |

## Pomodoro

Under `"pomodoro"`, minutes:

| Key | Type | Default |
|---|---|---|
| `work_min` | int | `25` |
| `break_min` | int | `5` |
| `long_break_min` | int | `15` |
| `cycles_before_long` | int | `4` |

---

## Example `config.json`

```json
{
  "enabled": true,
  "features": {
    "dynamic_theme": true,
    "wallpaper": true,
    "ambient_sound": true,
    "tasks": true
  },
  "weather_tint_strength": 40,
  "wallpaper_dynamic": true,
  "wallpaper_shift_strength": 35,
  "wallpaper_patterns": true,
  "wallpaper_warmth": true,
  "wallpaper_backend": "png",
  "wallpaper_animated": true,
  "wallpaper_animated_fps": 8,
  "wallpaper_load_ceiling": 85,
  "sound_volume": 25,
  "sound_mode": "random",
  "sound_interval_minutes": 5,
  "location": { "lat": 51.5072, "lon": -0.1276, "name": "London" },
  "manual_weather": "auto",
  "manual_time": "auto",
  "manual_theme_color": null,
  "run_at_login": false,
  "tick_interval_seconds": 30,
  "weather_refresh_seconds": 600,
  "pomodoro": { "work_min": 25, "break_min": 5, "long_break_min": 15, "cycles_before_long": 4 }
}
```
