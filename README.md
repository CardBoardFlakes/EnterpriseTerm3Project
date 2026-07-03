# Environment Theme Controller

A cross-platform (macOS + Windows) desktop app that makes your computer
reflect the weather and time of day outside.

## Features

- **Dynamic theme** — sets the OS accent colour from the current weather.
  - Windows: taskbar accent via the registry.
  - macOS: Dark/Light appearance by time of day + nearest named accent colour.
- **Weather wallpaper** — generates a sky-gradient desktop background that
  matches the weather and brightness (pure standard library, no Pillow).
- **Weather patterns** — a distinct, gently-moving overlay per condition:
  trickling rain streaks, slanted rain + lightning in storms, a drifting warm
  sun on clear days, warm cream puffs when cloudy, a moon + twinkling stars at
  night. Elements are drawn sparsely (cost scales with element count, not pixel
  count) and animate via the redraw cadence, so CPU stays negligible. Toggle it
  off to fall back to a plain gradient.
- **Cold-weather warmth** — when it's cold outside the whole palette is nudged
  toward a cosy amber (stronger the colder it gets) so the desktop feels warm,
  and the cloudy sky is a soft warm lilac-grey rather than a bleak flat grey.
- **Animated wallpaper (opt-in)** — a toggle that continuously redraws the
  wallpaper for smooth pattern motion (rain trickling, clouds drifting, stars
  twinkling) at a configurable frame rate. It deliberately uses more CPU, so a
  **load governor** watches frame cost + system load: it throttles the frame
  rate as the machine gets busy and fully **pauses** animation (dropping back
  to a static frame) when it's struggling, then resumes automatically once the
  load clears. Off by default. For genuinely smooth GPU animation, drive an
  external engine (ScreenPlay / Lively / Plash) from this app's weather state —
  the in-app path favours safety and low overhead over cinematic smoothness.
- **Dynamic background** — a slow, subtle hue/brightness drift so the desktop
  feels alive without being distracting (toggle + strength slider).
- **Ambient sound** — subtle weather/time soundscapes (rain, wind, birds,
  crickets, thunder). Bundled placeholder loops are synthesised on first run.
- **Productivity timer** — a Pomodoro timer (work / break / long break) with
  configurable durations and a chime + notification on each transition.
- **Tasks & schedules** — daily or one-off tasks that can notify you, play a
  chime, or switch the weather/theme override.
- **Manual overrides** — force a weather condition, time of day, or exact
  theme colour by hand.
- **Enable/disable everything** — a master switch plus per-feature toggles.
- **Run at login** — optional auto-start (macOS LaunchAgent / Windows Run key).
- **Light on resources** — the engine steps cheaply on a short cadence but only
  refetches weather and re-applies theme/wallpaper/sound *when something
  actually changes*; wallpaper redraws are rate-limited.

## Install

```bash
pip install -r requirements.txt
# If the GUI won't open ("No module named '_tkinter'"):
#   macOS:    brew install python-tk@3.13     # match your python version
#   Ubuntu:   sudo apt install python3-tk
```

## Run

```bash
python main.py              # settings GUI (default)
python main.py --once       # apply once, then exit
python main.py --background # headless loop (what "run at login" launches)
python tests.py             # run the test suite
```

In the GUI: change settings, then press **Apply Now** (one cycle) or **Start**
(continuous engine). **Save** only persists to disk. On macOS the accent colour
only changes in apps launched *after* it is set; Dark/Light and the wallpaper
update immediately.

## Layout

| File           | Responsibility                                          |
|----------------|---------------------------------------------------------|
| `main.py`      | Entry point (GUI / `--once` / `--background`)           |
| `gui.py`       | Tkinter settings window (General / Override / Tasks / Timer) |
| `engine.py`    | Stateful orchestration: cheap steps, work only on change |
| `config.py`    | Defaults, load/save, feature gating                     |
| `weather.py`   | Live weather + manual override + offline fallback       |
| `theme.py`     | Compute colour + apply accent (Windows / macOS)         |
| `wallpaper.py` | Generate + set the (drifting) weather wallpaper         |
| `perf.py`      | Load governor that throttles/pauses animated wallpaper  |
| `sound.py`     | Ambient sound selection, playback, placeholder synth    |
| `pomodoro.py`  | Productivity timer state machine                        |
| `tasks.py`     | Tasks & schedules store                                 |
| `activity.py`  | Idle-time detection                                     |
| `autostart.py` | Run-at-login (LaunchAgent / Run key)                    |

Settings are stored in `config.json`; tasks in `tasks.json`.

## Testing

```bash
python tests.py
```

A headless suite (114 checks) covering config, weather override, theme,
wallpaper PNG + dynamic drift + weather patterns/warmth, the animation load
governor + animated-wallpaper wiring, sound, tasks, autostart, the Pomodoro
timer, and the engine's change-guards (all system mutations are stubbed).
