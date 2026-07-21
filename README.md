# Flow

A cross-platform (macOS + Windows) desktop app that makes your computer reflect
the weather and time of day outside — accent colour, desktop wallpaper, and
subtle ambient sound — plus a built-in Pomodoro timer and task scheduler.

It is dependency-light (weather + audio are optional; wallpaper images are
generated with the Python standard library, no Pillow) and stays cheap by only
doing work when something actually changes.

---

## Quick start

```bash
cd EnterpriseTerm3Project
pip install -r requirements.txt      # optional deps: requests (weather), pygame (sound)
python main.py                       # launch the GUI
```

Then, in the window: pick your settings and press **▶ Start**. That applies the
theme/wallpaper/sound right away and keeps them updating in the background.
Press **■ Stop** to halt.

> **GUI won't open?** `tkinter` ships with Python but isn't a pip package.
> - macOS (Homebrew): `brew install python-tk` (match your Python version)
> - Debian/Ubuntu: `sudo apt install python3-tk`
> - Windows: included with the python.org installer

See the full walkthrough in **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**.

---

## What it does

| Feature | Summary |
|---|---|
| **Dynamic theme** | OS accent colour follows the weather. Windows: taskbar accent. macOS: Dark/Light by time of day + nearest named accent. |
| **Time-of-day light** | Theme + wallpaper move through the day's light — sunrise, morning, midday, afternoon, sunset, dusk, night — warm and low at the edges, bright and neutral at noon, deep blue at night. |
| **Gradual transitions** | Time-of-day colour changes continuously and weather changes cross-fade over a few seconds — no sudden jumps. |
| **Seasons** | A seasonal wash nudges the palette (fresh-green spring → golden summer → amber autumn → cool-blue winter); hemisphere auto-detected from your latitude. |
| **Mood profiles** | Switchable **Focus / Creativity / Relax** profiles reshape the colours and sound; toggle off with "None". |
| **Multi-monitor** | Sets the wallpaper on every connected display (toggleable). |
| **Accessibility** | A **high-contrast** mode forces bold, maximum-contrast colours and a black/white/yellow window. |
| **Dark/Light lock** | Force the device (and app) to Dark or Light, or let it follow the time of day. |
| **Weather wallpaper** | A sky-gradient background per condition, with weather patterns (rain, sun, clouds, stars) and a cosy warm tint when it's cold. |
| **Ambient sound** | Weather/time soundscapes with your own files + random variants; play looped or occasionally. Windy skies use the cloudy ambience. |
| **Music player** | Play your own downloaded songs (mp3/ogg/wav) in the background, with a playlist, auto-advance and its own volume. |
| **Auto-duck** | Optionally pause the ambient sound while other audio plays (your music player, or best-effort Spotify/Apple Music on macOS / any app on Windows). |
| **Timers** | A Timers tab with three modes: **Pomodoro** (work/break cycles), a plain **countdown Timer**, and a **Stopwatch** with laps. |
| **Tasks & schedules** | Daily or one-off tasks that notify, chime, or switch the weather/theme. |
| **Live weather panel** | Temperature, feels-like, humidity, UV index (with risk band), wind + gusts, rain chance and pressure. |
| **Manual overrides** | Force a weather condition, time of day, or exact accent colour — the live data keeps showing the *real* outside conditions. |
| **Time-of-day UI** | The app window itself follows the day: a light theme by day, dark at night, with a phase-tinted accent — matching the wallpaper/OS. |
| **Location privacy** | Coordinates are rounded to a coarse, city-level area before use — your exact position never leaves the machine. |
| **Run at login** | Optional auto-start (macOS LaunchAgent / Windows Run key). |

---

## Documentation

Detailed, task-focused guides live in **[`docs/`](docs/)**:

| Guide | What's inside |
|---|---|
| [User guide](docs/USER_GUIDE.md) | First launch, the Dashboard & Appearance tabs, the Focus & Tasks window, Start/Stop, running at login. |
| [Wallpaper guide](docs/WALLPAPER.md) | The static weather wallpaper: weather patterns, sun/moon movement, and the cold-weather warm tint. |
| [Sound guide](docs/SOUNDS.md) | File names, adding your own clips, variants, loop vs. random playback. |
| [Tasks & timer guide](docs/TASKS_AND_TIMER.md) | Pomodoro usage and creating daily / one-off scheduled tasks. |
| [Configuration reference](docs/CONFIGURATION.md) | Every `config.json` key, defaults, and where files are stored. |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | GUI, audio, wallpaper, accent-colour, and weather issues. |

---

## Running modes

```bash
python main.py              # settings GUI (default)
python main.py --once       # apply once, then exit
python main.py --background # headless loop (what "run at login" launches)
python tests.py             # run the test suite
```

---

## Location & privacy

The app **does not detect your location** — no GPS, no IP lookup, no OS query,
no "auto-detect". It uses fixed coordinates:

1. A hardcoded default in `config.py` — `{"lat": -33.8688, "lon": 151.2093,
   "name": "Sydney"}`.
2. Overridden only by the `location` block in **`config.json`** if you edit it
   by hand (there's no GUI field for it yet).
3. Those `lat`/`lon` are placed directly in the Open-Meteo request URL
   (`…?latitude=<lat>&longitude=<lon>&…&timezone=auto`). `timezone=auto` just
   returns times in that coordinate's timezone — it does not locate you.

So until you edit `config.json`, it fetches weather for **Sydney**, wherever the
computer actually is. To use your own area, set `location.lat` / `location.lon`
(find them in any maps app) — see the
[Configuration reference](docs/CONFIGURATION.md#location).

**What leaves the machine:** only the configured `lat`/`lon` → Open-Meteo, over
HTTPS, about once every 10 minutes. No API key or account is used. Everything
else (settings, tasks, reminder text, audio) stays local in plaintext
(`config.json`, `tasks.json`, `~/.environment_theme_controller/`). There is no
telemetry or analytics. Coordinates are low-sensitivity **personal** data — for
privacy, use a nearby town's coordinates rather than your exact address.

---

## Project layout

| File | Responsibility |
|---|---|
| `main.py` | Entry point (GUI / `--once` / `--background`) |
| `gui.py` | Tkinter UI: Dashboard + Appearance tabs, separate Focus & Tasks window |
| `engine.py` | Stateful orchestration: cheap steps, work only on change |
| `config.py` | Defaults, load/save, feature gating |
| `weather.py` | Live weather (Open-Meteo) + manual override + offline fallback |
| `theme.py` | Compute colour + apply accent (Windows / macOS) |
| `wallpaper.py` | Generate + set the weather wallpaper (patterns, warmth, drift) |
| `profiles.py` | Focus / Creativity / Relax mood profiles (colour + settings overlay) |
| `sound.py` | Ambient sound selection, variants, playback, placeholder synth |
| `music.py` | Background music player for your own songs |
| `audiocheck.py` | Best-effort detection of audio from other apps (for auto-duck) |
| `pomodoro.py` | Pomodoro timer state machine |
| `clocks.py` | Stopwatch + countdown timer |
| `tasks.py` | Tasks & schedules store |
| `activity.py` | Idle-time detection |
| `autostart.py` | Run-at-login (LaunchAgent / Run key) |

Settings are stored in `config.json`; tasks in `tasks.json`; generated
wallpaper assets in `~/.environment_theme_controller/`.

---

## Testing

```bash
python tests.py
```

### Linting

Code is linted with [Ruff](https://docs.astral.sh/ruff/) (config in `ruff.toml`):

```bash
pip install ruff
python3 -m ruff check .      # 0 issues
```

A headless test suite covering config,
mood profiles, seasons, gradual transitions + easing, high-contrast,
weather override, theme + time-of-day phases, wallpaper PNG / drift / patterns
/ warmth, sound
selection / variants / modes, tasks, autostart, the Pomodoro timer, the GUI
value mapping + display helpers (icons, temperature, UV band, live-data line),
idle detection, other-audio detection, desktop notifications, and the engine's
pure helpers + change-guards. All system-mutating calls
(accent, wallpaper, audio, notifications, launchctl/registry) are stubbed, so
running the tests never changes your machine.
