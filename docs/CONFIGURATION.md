# Configuration Reference

All settings live in **`config.json`** in the project folder. The GUI writes it
for you, but you can edit it by hand. Main-window controls save automatically;
the background engine reloads the file each cycle. Missing keys fall back to
the defaults below. An unreadable file uses defaults in memory and logs an
error; the file is not overwritten until settings are next saved.

- [File locations](#file-locations)
- [Top level](#top-level)
- [Features](#features)
- [Wallpaper](#wallpaper)
- [Sound](#sound)
- [Location](#location)
- [Manual overrides](#manual-overrides)
- [Engine cadence](#engine-cadence)
- [Timers](#timers)
- [Pomodoro](#pomodoro)
- [Example](#example-configjson)

---

## File locations

| What | Path |
|---|---|
| Settings | `config.json` (project folder) |
| Tasks | `tasks.json` (project folder) — see [tasks guide](TASKS_AND_TIMER.md) |
| Ambient sounds | `sounds/` (project folder) |
| Music and generated starter samples | `music/` (project folder) |
| Generated PNG wallpaper | `~/.environment_theme_controller/` |

---

## Top level

| Key | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `true` | Saved state of the GUI's **Enable everything** select-all control. It does not gate individually selected features. Turning it off in the GUI clears every feature switch. |

## Features

Under `"features"`; each switch operates independently of `enabled`.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `dynamic_theme` | bool | `true` | OS accent colour follows the computed weather/time theme unless `manual_theme_color` is set. |
| `wallpaper` | bool | `true` | Desktop background follows the weather. Turning this feature off restores Flow's archived copy of the original wallpaper when available. |
| `ambient_sound` | bool | `true` | Weather/time soundscape. |
| `tasks` | bool | `true` | Run scheduled tasks. |

## Wallpaper

| Key | Type | Default | Meaning |
|---|---|---|---|
| `weather_tint_strength` | int 0–100 | `72` | How strongly the weather colour shows vs. neutral. |
| `wallpaper_dynamic` | bool | `true` | Slow, subtle colour drift. |
| `wallpaper_shift_strength` | int 0–100 | `35` | Amplitude of that drift. |
| `wallpaper_patterns` | bool | `true` | Sun, moon, stars, clouds, rain, and storm overlays. A clear afternoon has no visible sun when this is `false`. |
| `wallpaper_warmth` | bool | `true` | Warm the palette when it's cold outside. |
| `wallpaper_min_interval_seconds` | int ≥5 | `45` | Minimum gap between generated wallpaper redraws. |
| `wallpaper_refresh_seconds` | int ≥0 | `90` | Periodically reapply an unchanged wallpaper so macOS Spaces catch up; `0` disables this. |

## Sound

| Key | Type | Default | Meaning |
|---|---|---|---|
| `sound_volume` | int 0–100 | `25` | Ambient volume. |
| `music_volume` | int 0–100 | `60` | Volume for the separate local music player. |
| `pause_when_other_audio` | bool | `false` | Stop ambience for other app audio. Uses CoreAudio process output on macOS and `pycaw` sessions on Windows, excluding Flow's own registered processes. Flow's music always takes priority and ambience resumes when it stops. |

See the [sound guide](SOUNDS.md) for file names and variants.

## Location

Used for live weather (Open-Meteo). Pick your **City** from the dropdown in
Settings → Engine — it fills in the coordinates for you, and only that
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
| `active_profile` | `none`/`focus`/`creativity`/`relax` | `"none"` | Mood profile overlaying colours and sound. |
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
| `manual_weather` | `auto`/`clear`/`cloud`/`rain`/`storm` | `"auto"` | Force a weather condition, or `auto` for live data. |
| `manual_time` | `auto` / `sunrise` / `morning` / `midday` / `afternoon` / `sunset` / `dusk` / `night` | `"auto"` | Force a time-of-day phase (tints the theme + wallpaper and sets brightness / Dark mode). `auto` follows the real sun. Legacy `day` = `midday`. |
| `manual_theme_color` | `null` or `[r,g,b]` | `null` | Force an exact accent colour; `null` = derive from weather. |
| `run_at_login` | bool | `false` | Reflects the run-at-login launcher state. |

## Engine cadence

| Key | Type | Default | Meaning |
|---|---|---|---|
| `tick_interval_seconds` | int 5–3600 | `30` | How often the engine steps. |
| `weather_refresh_seconds` | int 30–7200 | `600` | How often the engine and Dashboard card automatically refetch live weather. |

## Timers

| Key | Type | Default | Meaning |
|---|---|---|---|
| `countdown_minutes` | int 1–600 | `10` | Last duration set in the plain countdown timer. |

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
  "weather_tint_strength": 72,
  "wallpaper_dynamic": true,
  "wallpaper_shift_strength": 35,
  "wallpaper_patterns": true,
  "wallpaper_warmth": true,
  "wallpaper_min_interval_seconds": 45,
  "wallpaper_refresh_seconds": 90,
  "sound_volume": 25,
  "music_volume": 60,
  "pause_when_other_audio": false,
  "location": { "lat": 51.5072, "lon": -0.1276, "name": "London" },
  "manual_weather": "auto",
  "manual_time": "auto",
  "manual_theme_color": null,
  "smooth_transitions": true,
  "theme_transition_seconds": 8,
  "seasonal_themes": true,
  "hemisphere": "auto",
  "active_profile": "none",
  "accessibility_mode": "none",
  "appearance_mode": "auto",
  "multi_monitor": true,
  "run_at_login": false,
  "tick_interval_seconds": 30,
  "weather_refresh_seconds": 600,
  "countdown_minutes": 10,
  "pomodoro": { "work_min": 25, "break_min": 5, "long_break_min": 15, "cycles_before_long": 4 }
}
```
