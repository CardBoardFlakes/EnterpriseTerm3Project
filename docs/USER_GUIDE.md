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
- **pygame** — ambient sound and music playback. Without it, audio is silently
  skipped.

`tkinter` (the GUI toolkit) ships with Python but is not a pip package. If the
window doesn't open, see [Troubleshooting](TROUBLESHOOTING.md#the-gui-wont-open).

On first launch the app uses built-in defaults. It writes `config.json` when a
setting first changes, synthesises missing base ambience into `sounds/` when
needed, and puts two original sample tracks into an empty `music/` library.

---

## The main window

The window has a **header** (title + **Focus & Tasks** button), two tabs
(**Dashboard**, **Settings**), and a status bar at the bottom.

### Dashboard tab

Everything you touch day-to-day is here.

**Live weather card** — an icon, the current condition, the time-of-day phase,
the **temperature**, and a live-data line: **feels-like, humidity, UV index
(with risk band), wind + gusts, rain chance and pressure**. It also shows your
location and data source (`live` / `fallback`). The card fetches at launch,
after a city change, and automatically at the **Weather refresh** interval in
Settings → Engine.

The heading uses a compact condition-and-phase format, for example **Rain ·
afternoon**. Night and dusk are time-of-day phases, not weather conditions.

> Temperature, humidity, UV, wind, rain chance, and pressure remain the live
> outside readings. A manual weather override changes the condition shown and
> the resulting theme, wallpaper, and sound; `manual` marks that condition.
> A manual time override changes the visual time phase while measurements stay
> live.

The whole window also follows the time of day — light by day and dark at night.
Its palette takes the active theme accent when that display mode changes.

**Mood profile** — choose Off, Focus, Creativity, or Relax. Profiles adjust the
computed colour and ambient level without overwriting your volume setting:
Focus is cooler and quieter, Creativity more vivid, and Relax warmer and
gentler.

**Features** — a select-all control plus independent feature toggles:

- *Enable everything* — checks or unchecks every feature below it immediately.
  Turning it off also restores the original wallpaper because it clears
  **Weather wallpaper**. Child controls remain available: leave select-all off
  and enable only the features you want.
- *System accent follows theme* — OS accent follows weather and time unless an
  exact colour is picked below. It changes the Windows taskbar/title colour or
  the nearest named macOS accent; existing macOS apps may need relaunching.
- *Weather wallpaper* — desktop background follows the weather.
- *Ambient sound* — weather/time soundscape.
- *Task reminders* — runs scheduled notification/chime tasks.

Reminder contents are managed in **Focus & Tasks**; their independent feature
switch is on the Dashboard.

**Manual theme changer** — override what the app shows:

Weather and time selections update the Dashboard heading immediately while
reusing the latest live measurements; they do not wait for the next weather
fetch or for the run-at-login engine to return status.

- *Weather* — `auto` (use live data) or force `clear`, `cloud`, `rain`, or
  `storm`.
- *Time of day* — `auto`, or a specific phase: `sunrise`, `morning`, `midday`,
  `afternoon`, `sunset`, `dusk`, `night`. Each phase tints the theme and
  wallpaper with that time's light — warm and low at sunrise/sunset, bright and
  neutral at midday, deep blue at night — and sets the matching brightness /
  Dark mode. `auto` moves through the phases with the real sun.
- *Accent colour* — `auto`, or an exact `r,g,b`. Use **Pick…** for a colour
  picker (the swatch previews your choice) or **Auto** to clear it.

> (On macOS the *accent* colour snaps to the nearest named system accent, so
> nearby computed colours can select the same named accent. Existing apps may
> need relaunching; the swatch shows the computed colour immediately.)

### Settings tab

Longer-lived appearance and engine controls. The tab scrolls only when its
cards do not fit; the scrollbar hides when everything is visible.

- **Wallpaper look** — tint strength, subtle colour drift, celestial/weather
  patterns (sun/moon/stars/rain/clouds), and the cold-weather warm tint. A clear
  daytime wallpaper only shows its sun while this pattern switch is on. See the
  [Wallpaper guide](WALLPAPER.md).
- **Sound** — ambient volume, optional pause for detectable external audio, and
  a **Sound files…** button that lists required filenames and opens the folder.
  Flow's own music always pauses ambience, and stopping or pausing it resumes
  ambience even while the music window remains open. Flow's own audio devices
  are not mistaken for external audio. See the [Sound guide](SOUNDS.md).
- **Seasons & transitions** — gradual colour transitions, seasonal palette,
  and automatic or fixed hemisphere.
- **Device appearance** — follow time of day or lock the device and Flow window
  to Dark or Light.
- **Accessibility** — normal or high-contrast colours. High contrast uses a
  black, white, and yellow palette throughout both tabs.
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
- **Music** — start with either of the two generated sample tracks, add local
  songs, and use play/pause, stop, previous/next, and separate volume controls.

---

## Running automatically at login

Tick **Run automatically at login** (Settings → Engine). This installs a
headless launcher that runs `main.py --background` when you log in:

- **macOS** — a LaunchAgent at `~/Library/LaunchAgents/com.environmenttheme.controller.plist`.
- **Windows** — a value under `HKCU\...\CurrentVersion\Run`.

Untick it to remove the launcher. It runs the engine without a window; open the
GUI any time to change settings (the background loop reloads `config.json` each
cycle, so changes apply without a restart). Theme, wallpaper, weather, and task
reminders stay active headlessly. Ambient sound plays only while at least one
Flow window is open and stops when the last window closes.

---

## Running without the GUI

```bash
python main.py --once        # run one engine cycle, then exit
python main.py --background  # run the engine loop forever (Ctrl-C to stop)
```

`--once` is useful for scripting or a quick theme/wallpaper test; its process
ends after that cycle. `--background` is what the run-at-login launcher uses.
Headless background mode does not play ambient sound until the GUI opens.
Opening the GUI at the same time does not start a competing engine. The two
processes share one engine owner, and GUI changes wake it immediately.

---

## Where your settings live

| What | Location |
|---|---|
| Settings | `config.json` (in the project folder) |
| Tasks | `tasks.json` (in the project folder) |
| Generated wallpaper | `~/.environment_theme_controller/` |
| Ambient sound files | `sounds/` (in the project folder) |
| Music and starter samples | `music/` (in the project folder) |

To change your **location** for live weather, pick your **City** from the
dropdown in Settings → Engine. For a city that isn't listed, edit `location`
in `config.json` — see the [Configuration reference](CONFIGURATION.md#location).
