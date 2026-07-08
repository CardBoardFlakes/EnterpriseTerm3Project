# Environment Theme Controller

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
| **Mood profiles** | Switchable **Focus / Creativity / Relax** profiles reshape the colours, motion and sound; toggle off with "None". |
| **Multi-monitor** | Sets the wallpaper on every connected display (toggleable). |
| **Accessibility** | A **high-contrast** mode forces bold, maximum-contrast colours and a black/white/yellow window. |
| **Weather wallpaper** | A sky-gradient background per condition, with moving patterns (rain, sun, clouds, stars) and a cosy warm tint when it's cold. |
| **Animated wallpaper** | One **Off / Smooth / Ultra** choice — *Smooth* animates with zero setup; *Ultra* uses a free external app for GPU-smooth motion. |
| **Ambient sound** | Weather/time soundscapes with your own files + random variants; play looped or occasionally. |
| **Pomodoro timer** | Work / break / long-break cycles with chime + notification. |
| **Tasks & schedules** | Daily or one-off tasks that notify, chime, or switch the weather/theme. |
| **Live weather panel** | Temperature, feels-like, humidity, UV index (with risk band), wind + gusts, rain chance and pressure. |
| **Manual overrides** | Force a weather condition, time of day, or exact accent colour — the live data keeps showing the *real* outside conditions. |
| **Time-of-day UI** | The app window itself follows the day: a light theme by day, dark at night, with a phase-tinted accent — matching the wallpaper/OS. |
| **Run at login** | Optional auto-start (macOS LaunchAgent / Windows Run key). |

---

## Documentation

Detailed, task-focused guides live in **[`docs/`](docs/)**:

| Guide | What's inside |
|---|---|
| [User guide](docs/USER_GUIDE.md) | First launch, the Dashboard & Appearance tabs, the Focus & Tasks window, Start/Stop, running at login. |
| [Wallpaper guide](docs/WALLPAPER.md) | Motion (Off/Smooth/Ultra), weather patterns, cold warmth, and step-by-step external-app setup (ScreenPlay / Lively / Plash). |
| [Sound guide](docs/SOUNDS.md) | File names, adding your own clips, variants, loop vs. random playback. |
| [Tasks & timer guide](docs/TASKS_AND_TIMER.md) | Pomodoro usage and creating daily / one-off scheduled tasks. |
| [Configuration reference](docs/CONFIGURATION.md) | Every `config.json` key, defaults, and where files are stored. |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | GUI, audio, wallpaper, accent-colour, weather, and animation issues. |

---

## Running modes

```bash
python main.py              # settings GUI (default)
python main.py --once       # apply once, then exit
python main.py --background # headless loop (what "run at login" launches)
python tests.py             # run the test suite
```

---

## Project layout

| File | Responsibility |
|---|---|
| `main.py` | Entry point (GUI / `--once` / `--background`) |
| `gui.py` | Tkinter UI: Dashboard + Appearance tabs, separate Focus & Tasks window |
| `engine.py` | Stateful orchestration: cheap steps, work only on change |
| `config.py` | Defaults, load/save, feature gating, friendly-motion mapping |
| `weather.py` | Live weather (Open-Meteo) + manual override + offline fallback |
| `theme.py` | Compute colour + apply accent (Windows / macOS) |
| `wallpaper.py` | Generate + set the weather wallpaper (patterns, warmth, drift) |
| `webwall.py` | "Ultra" web wallpaper: HTML/canvas page + live `weather.json` feed |
| `perf.py` | Load governor that throttles/pauses the Smooth animation |
| `profiles.py` | Focus / Creativity / Relax mood profiles (colour + settings overlay) |
| `sound.py` | Ambient sound selection, variants, playback, placeholder synth |
| `pomodoro.py` | Productivity timer state machine |
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

A headless suite (**238 checks**) covering config + friendly-motion mapping,
mood profiles, seasons, gradual transitions + easing, high-contrast,
weather override, theme + time-of-day phases, wallpaper PNG / drift / patterns
/ warmth, the
animation load governor and animated-wallpaper wiring, the web backend, sound
selection / variants / modes, tasks, autostart, the Pomodoro timer, the GUI
value mapping, and the engine's change-guards. All system-mutating calls
(accent, wallpaper, audio, launchctl/registry) are stubbed, so running the
tests never changes your machine.
