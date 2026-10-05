# Flow

A cross-platform (macOS + Windows) desktop app that makes your computer reflect
the weather and time of day outside — accent colour, desktop wallpaper, and
subtle ambient sound — plus a built-in Pomodoro timer and task scheduler.
It also includes a countdown timer, stopwatch, and local music player.

It is dependency-light (weather + audio are optional; wallpaper images are
generated with the Python standard library, no Pillow) and stays cheap by only
doing work when something actually changes.

---

## Screenshots

| Dashboard (day) | Dashboard (night) |
|---|---|
| ![Flow dashboard during the day: live Sydney weather, mood profiles, feature toggles and manual theme controls](docs/screenshots/dashboard.png) | ![The same dashboard after dark — the window follows the time of day into a dark theme](docs/screenshots/dashboard-night.png) |

| Settings | Timers |
|---|---|
| ![Settings tab: wallpaper look, ambient sound, seasons and transitions, device appearance](docs/screenshots/settings.png) | ![Focus & Tasks window, Timers tab: Pomodoro / countdown / stopwatch](docs/screenshots/timers.png) |

| To-Do & Schedules | Music |
|---|---|
| ![Scheduled reminders list and new-reminder form](docs/screenshots/tasks.png) | ![Local music player with the two built-in sample tracks](docs/screenshots/music.png) |

---

## Getting Flow

There are three ways to run Flow. Most people should use the first.

### 1. Download the app (no Python or command line needed)

Grab the latest build from the
**[Releases page](https://github.com/CardBoardFlakes/EnterpriseTerm3Project/releases/latest)**:

| Your computer | Download | Install |
|---|---|---|
| Mac with Apple silicon (M1 or newer) | `Flow-macOS-arm64.dmg` | Open the DMG and drag **Flow** into **Applications**. |
| Mac with an Intel processor | `Flow-macOS-x86_64.dmg` | Same as above. |
| Windows 10 / 11 | `Flow-Windows-x64.exe` | Save it anywhere (e.g. your Desktop) and double-click it. Nothing to install. |

Then start Flow like any other app — from Launchpad / the Applications folder
on macOS, or by double-clicking `Flow-Windows-x64.exe` on Windows.

> **First launch security prompts.** The builds aren't code-signed, so your OS
> asks you to confirm the first time:
> - **macOS:** if you see *"Flow can't be opened"* or *"Apple could not verify…"*,
>   open **System Settings → Privacy & Security**, scroll down and click
>   **Open Anyway** next to Flow (on older macOS: right-click Flow → **Open**).
>   macOS may also ask to let Flow control *System Events* — allow it so Flow can
>   change your accent colour, Dark/Light mode and wallpaper.
> - **Windows:** if SmartScreen shows *"Windows protected your PC"*, click
>   **More info → Run anyway**.

The downloaded app keeps its settings in `~/Library/Application Support/Flow/`
(macOS) or `%APPDATA%\Flow\` (Windows). **Run at login** (Settings → Engine)
works the same way and launches the app in the background.

### 2. Run from source

```bash
git clone https://github.com/CardBoardFlakes/EnterpriseTerm3Project.git
cd EnterpriseTerm3Project
pip install -r requirements.txt      # optional deps: requests (weather), pygame (sound)
python main.py                       # launch the GUI
```

The engine starts with the window. Every setting is saved and applied
automatically as you change it.

> **GUI won't open?** `tkinter` ships with Python but isn't a pip package.
> - macOS (Homebrew): `brew install python-tk` (match your Python version)
> - Debian/Ubuntu: `sudo apt install python3-tk`
> - Windows: included with the python.org installer

See the full walkthrough in **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)**.

### 3. Build the app yourself

Builds use [PyInstaller](https://pyinstaller.org/) and must be made on the OS
you're targeting (a Mac builds the Mac app, Windows builds the `.exe`):

```bash
pip install -r requirements.txt -r packaging/requirements-build.txt
python packaging/build.py
```

| OS | Output in `dist/` |
|---|---|
| macOS | `Flow.app` and `Flow-macOS-<arch>.dmg` |
| Windows | `Flow.exe` (single file, no console window) and `Flow-Windows-<arch>.exe` |

**Publishing a release:** push a version tag and GitHub Actions
([`.github/workflows/release.yml`](.github/workflows/release.yml)) runs the tests,
builds the Apple-silicon Mac, Intel Mac and Windows apps, and attaches them to a
new GitHub Release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

You can also run the workflow by hand from the **Actions** tab ("Build desktop
apps" → *Run workflow*) to get the builds as downloadable artifacts without
publishing a release.

---

## What it does

| Feature | Summary |
|---|---|
| **System accent follows theme** | OS accent colour follows the weather and time unless you pick a manual colour. Windows changes the taskbar/title accent; macOS uses the nearest named accent and existing apps may need relaunching. |
| **Time-of-day light** | Theme + wallpaper move through the day's light — sunrise, morning, midday, afternoon, sunset, dusk, night — warm and low at the edges, bright and neutral at noon, deep blue at night. |
| **Gradual transitions** | Time-of-day colour changes continuously and weather changes cross-fade over a few seconds — no sudden jumps. |
| **Seasons** | A seasonal wash nudges the palette (fresh-green spring → golden summer → amber autumn → cool-blue winter); hemisphere auto-detected from your latitude. |
| **Mood profiles** | Switchable **Focus / Creativity / Relax** profiles reshape the colours and sound; toggle off with "None". |
| **Multi-monitor** | Sets the wallpaper on every connected display (toggleable). |
| **Accessibility** | A **high-contrast** mode forces bold, maximum-contrast colours and a black/white/yellow window. |
| **Dark/Light lock** | Force the device (and app) to Dark or Light, or let it follow the time of day. |
| **Weather wallpaper** | A sky-gradient background per condition, with weather patterns (rain, sun, clouds, stars) and a cosy warm tint when it's cold. |
| **Independent features** | **Enable everything** selects or clears all features at once. Leave it off and enable accent, wallpaper, ambience, or reminders individually. |
| **Ambient sound** | Relaxing weather/time soundscapes that loop while Flow is open and stop when its last window closes. Add your own files or variants; windy skies use the cloudy ambience. |
| **Music player** | Two original sample tracks appear automatically in an empty library. Add your own songs (mp3/ogg/wav/flac/m4a), with playlist controls and a separate volume. |
| **Audio priority** | Flow music always pauses ambience and ambience resumes when music stops. An optional setting also pauses ambience for other app audio (CoreAudio on macOS, or `pycaw` on Windows); Flow's own processes are excluded. |
| **Timers** | A Timers tab with three modes: **Pomodoro** (work/break cycles), a plain **countdown Timer**, and a **Stopwatch** with laps. |
| **Tasks & schedules** | Daily or one-off reminders that show a notification or play a chime. |
| **Live weather panel** | Temperature, feels-like, humidity, UV index (with risk band), wind + gusts, rain chance and pressure, refreshed automatically. |
| **Manual overrides** | Force a weather condition, time of day, or exact accent colour. Measurements stay live; a forced weather label is marked `manual`. Night is a time-of-day choice, not a weather condition. |
| **Time-of-day UI** | The app window follows the day with a light theme by day and dark theme at night; its palette uses the active theme accent when the mode changes. |
| **Location privacy** | No automatic location detection; only the coordinates for your selected city are sent for weather data. |
| **Run at login** | Optional auto-start (macOS LaunchAgent / Windows Run key). |

---

## Documentation

Detailed, task-focused guides live in **[`docs/`](docs/)**:

| Guide | What's inside |
|---|---|
| [User guide](docs/USER_GUIDE.md) | First launch, the Dashboard & Settings tabs, the Focus & Tasks window, and running at login. |
| [Wallpaper guide](docs/WALLPAPER.md) | Generated PNG wallpapers: weather patterns, sun/moon movement, subtle drift, and cold-weather warmth. |
| [Sound guide](docs/SOUNDS.md) | Built-in ambience, custom clips and variants, audio priority, and local music. |
| [Tasks & timers guide](docs/TASKS_AND_TIMER.md) | Pomodoro, countdown, stopwatch, and daily / one-off reminders. |
| [Configuration reference](docs/CONFIGURATION.md) | Every `config.json` key, defaults, and where files are stored. |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | GUI, audio, wallpaper, accent-colour, and weather issues. |

---

## Running modes

```bash
python main.py              # settings GUI (default)
python main.py --once       # run one engine cycle, then exit
python main.py --background # headless loop (what "run at login" launches)
python tests.py             # run the test suite
```

The downloaded app accepts the same flags, e.g.
`/Applications/Flow.app/Contents/MacOS/Flow --once` or
`Flow-Windows-x64.exe --background`.

GUI and background modes may be open together. They share one active engine,
so opening the settings window does not duplicate or silence ambient playback;
GUI changes wake the owner and still apply automatically. The open window also
repaints locally, so profile, manual theme, Dark/Light, seasonal, and
high-contrast changes remain immediate when the background process owns the
engine.

---

## Location & privacy

The app **does not detect your location** — no GPS, no IP lookup, no OS query,
no "auto-detect". It uses the fixed coordinates for your selected city:

1. A hardcoded default in `config.py` — `{"lat": -33.8688, "lon": 151.2093,
   "name": "Sydney"}`.
2. The **City** dropdown in Settings → Engine replaces that default with a
   city from the built-in list and saves it to `config.json`.
3. For an unlisted city, you can edit the `location` block in `config.json`.
4. Those `lat`/`lon` are placed directly in the Open-Meteo request URL
   (`…?latitude=<lat>&longitude=<lon>&…&timezone=auto`). `timezone=auto` just
   returns times in that coordinate's timezone — it does not locate you.

So until you pick another city, it fetches weather for **Sydney**, wherever the
computer actually is. For custom coordinates, see the
[Configuration reference](docs/CONFIGURATION.md#location).

**What leaves the machine:** only the configured `lat`/`lon` → Open-Meteo, over
HTTPS, about once every 10 minutes. No API key or account is used. Everything
else stays local: settings and reminders are plaintext JSON; audio and generated
wallpapers are ordinary local files. There is no telemetry or analytics.
Coordinates are low-sensitivity **personal** data — for privacy, use a nearby
town's coordinates rather than your exact address.

---

## Project layout

| File | Responsibility |
|---|---|
| `main.py` | Entry point (GUI / `--once` / `--background`) |
| `gui.py` | Tkinter UI: Dashboard + Settings tabs, separate Focus & Tasks window |
| `engine.py` | Stateful orchestration: cheap steps, work only on change |
| `config.py` | Defaults, load/save, feature gating |
| `weather.py` | Live weather (Open-Meteo) + manual override + offline fallback |
| `theme.py` | Compute colour + apply accent (Windows / macOS) |
| `wallpaper.py` | Generate + set the weather wallpaper (patterns, warmth, drift) |
| `profiles.py` | Focus / Creativity / Relax mood profiles (colour + settings overlay) |
| `sound.py` | Ambient sound selection, variants, playback, placeholder synth |
| `music.py` | Background music player; creates starter samples for an empty library |
| `audiocheck.py` | Best-effort detection of audio from other apps (for auto-duck) |
| `pomodoro.py` | Pomodoro timer state machine |
| `clocks.py` | Stopwatch and countdown timer state machines |
| `tasks.py` | Tasks & schedules store |
| `activity.py` | Idle-time detection |
| `autostart.py` | Run-at-login (LaunchAgent / Run key) |
| `processlock.py` | Single-engine and cross-process audio ownership |
| `paths.py` | Where data lives (project folder from source, per-user folder when packaged) |
| `packaging/` | PyInstaller spec, icon generator and `build.py` for the desktop apps |
| `.github/workflows/release.yml` | Builds + publishes the macOS / Windows apps on version tags |

Settings are stored in `config.json`; tasks in `tasks.json` (in the project
folder from source, or the per-user data folder for the downloaded app);
generated wallpaper assets in `~/.environment_theme_controller/`.

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

A 463-check headless test suite covering config,
mood profiles, seasons, gradual transitions + easing, high-contrast,
weather override, theme + time-of-day phases, wallpaper PNG / drift / patterns
/ warmth / reliable original restoration, sound selection / variants /
continuous-loop recovery, starter music generation, tasks,
autostart, packaged-app data paths, all three timer modes, the GUI
value mapping + display helpers (icons, temperature, UV band, live-data line),
idle detection, other-audio detection, desktop notifications, and the engine's
pure helpers + change-guards. All system-mutating calls
(accent, wallpaper, audio, notifications, launchctl/registry) are stubbed, so
running the tests never changes your machine.
