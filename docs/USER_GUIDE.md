# User Guide

A full walkthrough of the Flow. New here? Read this top
to bottom once — it takes five minutes.

- [Installing & first launch](#installing--first-launch)
- [The main window](#the-main-window)
  - [Dashboard tab](#dashboard-tab)
  - [Settings tab](#settings-tab)
- [Automatic apply](#automatic-apply)
- [The Focus & Tasks window](#the-focus--tasks-window)
- [Running automatically at login](#running-automatically-at-login)
- [Running without the GUI](#running-without-the-gui)
- [Where your settings live](#where-your-settings-live)

---

## Installing & first launch

```bash
cd EnterpriseTerm3Project
pip install -r requirements.txt
python main.py
```

`requirements.txt` installs two **optional** packages:

- **requests** — live weather from Open-Meteo. Without it, the app falls back to
  a sensible default (clear sky, fixed sunrise/sunset) and everything still works.
- **pygame** — ambient sound playback. Without it, sound is silently skipped.

`tkinter` (the GUI toolkit) ships with Python but is not a pip package. If the
window doesn't open, see [Troubleshooting](TROUBLESHOOTING.md#the-gui-wont-open).

On first launch the app writes a `config.json` with defaults and, when sound
plays, synthesises placeholder audio into `sounds/`.

---

## The main window

The window has a **header** (title + **Focus & Tasks** button), two tabs
(**Dashboard**, **Settings**), and a status bar at the bottom.

### Dashboard tab

Everything you touch day-to-day is here.

**Live weather card** — an icon, the current condition, the time-of-day phase,
the **temperature**, and a live-data line: **feels-like, humidity, UV index
(with risk band), wind + gusts, rain chance and pressure**. It also shows your
location and data source (`live` / `fallback`). Press **↻ Refresh weather** to
fetch again.

The heading names both values explicitly, for example **Weather: Rain · Time:
Afternoon**. Night and dusk are time-of-day phases, not weather conditions.

> The live readings always reflect the *real* outside weather. Using a manual
> weather/time override only changes the look (theme, wallpaper, sound) — the
> card still shows the true temperature, humidity, UV, etc., marked `(manual)`
> so you know a look is forced.

The whole window also follows the time of day — light by day, dark at night,
with an accent tinted to the current sky — so the app matches your desktop.

**Features** — the master switch plus per-feature toggles:

- *Enable everything* — the master switch. Toggling it takes effect
  **immediately** and checks or unchecks every feature below it. Turning it off
  silences ambient sound and stops all further theme/wallpaper updates (it
  leaves the current wallpaper and accent as they are). Turning it back on
  enables and resumes every feature.
- *Dynamic accent theme* — OS accent colour follows the weather.
- *Weather wallpaper* — desktop background follows the weather.
- *Ambient sound* — weather/time soundscape.

Scheduled reminders have no separate main-window toggle. They run automatically
while the master switch is on and are managed in **Focus & Tasks**.

**Manual theme changer** — override what the app shows:

- *Weather* — `auto` (use live data) or force `clear`, `cloud`, `rain`, or
  `storm`.
- *Time of day* — `auto`, or a specific phase: `sunrise`, `morning`, `midday`,
  `afternoon`, `sunset`, `dusk`, `night`. Each phase tints the theme and
  wallpaper with that time's light — warm and low at sunrise/sunset, bright and
  neutral at midday, deep blue at night — and sets the matching brightness /
  Dark mode. `auto` moves through the phases with the real sun.
- *Accent colour* — `auto`, or an exact `r,g,b`. Use **Pick…** for a colour
  picker (the swatch previews your choice) or **Auto** to clear it.

> (On macOS the *accent* colour snaps to the nearest named system accent,
> so daytime phases may look similar there; the **wallpaper** shows the change
> clearly.)

### Settings tab

Looks and performance — set once and forget.

- **Wallpaper look** — tint strength, subtle colour drift, weather patterns
  (rain/sun/clouds/stars), and the cold-weather warm tint. See the
  [Wallpaper guide](WALLPAPER.md).
- **Sound** — ambient volume, optional pause while other audio plays, and a
  **Sound files…** button that lists the required filenames and opens the
  folder. Ambience loops continuously. See the [Sound guide](SOUNDS.md).
- **Engine** — how often the app steps (`Tick`) and refetches weather, the city
  used for live weather, multi-monitor wallpaper, and **Run automatically at
  login**.

---

## Automatic apply

The engine starts when the window opens. Every main-window setting is saved and
applied automatically as you change it; no Start, Step, Apply, or Save action is
needed.

> **macOS note:** the accent colour only appears in apps launched *after* it's
> set. Dark/Light mode and the wallpaper update immediately.

---

## The Focus & Tasks window

Click **⏱ Focus & Tasks** in the header to open a separate window with three tabs.
It runs independently of the main window — the timer keeps ticking even if you
close it. Full details in the [Tasks & timer guide](TASKS_AND_TIMER.md).

- **Timers** — Pomodoro work/break cycles, a countdown timer, and a stopwatch
  with laps.
- **To-Do & Schedules** — a list of your tasks plus a form to add daily or
  one-off reminders that show a notification or play a chime.
- **Music** — add local songs, choose a track, and use play/pause, stop,
  previous/next, and separate volume controls.

---

## Running automatically at login

Tick **Run automatically at login** (Settings → Engine). This installs a
headless launcher that runs `main.py --background` when you log in:

- **macOS** — a LaunchAgent at `~/Library/LaunchAgents/com.environmenttheme.controller.plist`.
- **Windows** — a value under `HKCU\...\CurrentVersion\Run`.

Untick it to remove the launcher. It runs the engine without a window; open the
GUI any time to change settings (the background loop reloads `config.json` each
cycle, so changes apply without a restart).

---

## Running without the GUI

```bash
python main.py --once        # apply the theme/wallpaper/sound once, then exit
python main.py --background  # run the engine loop forever (Ctrl-C to stop)
```

`--once` is useful for scripting or a quick test; `--background` is what the
run-at-login launcher uses.

---

## Where your settings live

| What | Location |
|---|---|
| Settings | `config.json` (in the project folder) |
| Tasks | `tasks.json` (in the project folder) |
| Generated wallpaper | `~/.environment_theme_controller/` |
| Ambient sound files | `sounds/` (in the project folder) |

To change your **location** for live weather, pick your **City** from the
dropdown in Settings → Engine. For a city that isn't listed, edit `location`
in `config.json` — see the [Configuration reference](CONFIGURATION.md#location).
