# AGENTS.md

Guidance for AI agents working in this repo. Read this before making changes.

## What this is

**Environment Theme Controller** — a cross-platform (macOS + Windows) desktop
app that makes the OS reflect the weather + time of day: accent colour,
Dark/Light, desktop wallpaper, ambient sound, plus a Pomodoro timer, task
scheduler, and a music player. Pure Python; the only hard dependency is the
standard library (`tkinter` for the GUI). `requests` (weather) and `pygame`
(audio) are optional — the app degrades gracefully without them.

## Commands (run from this directory)

```bash
python3 tests.py            # full test suite — MUST stay green
python3 -m ruff check .     # lint — MUST stay clean (config: ruff.toml)
python3 main.py             # GUI
python3 main.py --once      # one apply cycle, then exit
python3 main.py --background # headless engine loop
```

**The gate for any change:** `python3 tests.py` passes (0 failed) **and**
`python3 -m ruff check .` prints "All checks passed!". Add tests for new logic.

## Architecture / data flow

`main.py` → `gui.py` (Tk) or `engine.run_forever`. The **engine** is the brain:

```
weather.get_live_weather (Open-Meteo, cached)      # real measurements
  → weather.apply_overrides (manual weather/time)  # condition/is_night only
  → theme.compute_theme_color (weather + time-of-day phase + season)
  → profiles.adjust_color + accessibility (high_contrast) + easing
  → theme.apply_theme_color   (accent + Dark/Light: osascript/defaults | registry)
  → wallpaper.apply_weather_wallpaper (generate PNG gradient+patterns, set desktop)
     or webwall (Ultra: write weather.json for ScreenPlay/Lively/Plash)
  → sound.play_ambient (pygame) ; music player is separate
  → tasks fire (notify/chime/set_weather/set_theme)
```

`engine.Engine.step()` is the stateful, cheap per-tick path (used by the GUI
thread + `--background`); `engine.tick()` is the one-shot path (`--once`, GUI
live-apply). Both must be kept consistent when you change behaviour.

### Module map

| File | Role |
|---|---|
| `engine.py` | Orchestration; `step` (stateful) + `tick` (one-shot); easing, guards, tasks |
| `config.py` | `DEFAULTS`, load/save, choice lists, `feature_enabled`, motion mapping |
| `weather.py` | Open-Meteo fetch, condition classification, overrides, offline fallback |
| `theme.py` | Colour maths: weather base, time-of-day phases, `sky_light`, seasons, high-contrast, accent/appearance apply |
| `wallpaper.py` | Stdlib PNG generation (gradient + patterns + sun/moon), set desktop |
| `webwall.py` | "Ultra" web wallpaper (HTML/canvas + `weather.json`) |
| `perf.py` | `AdaptiveGovernor` — throttles/pauses the Smooth animation |
| `profiles.py` | Focus/Creativity/Relax mood overlays |
| `sound.py` | Ambient selection + variants + pygame playback + placeholder synth |
| `music.py` | Background music player (pygame `mixer.music`) |
| `audiocheck.py` | Best-effort "is other audio playing" (auto-duck) |
| `pomodoro.py`, `clocks.py` | Timers |
| `tasks.py` | Task/schedule store (`tasks.json`) |
| `activity.py`, `autostart.py` | Idle detection; run-at-login |
| `gui.py` | Tk UI (Dashboard + Settings tabs; separate Focus & Tasks window) |

## Conventions

- **Standard library only** for image generation (no Pillow) and everything
  core. Keep optional deps optional and wrapped in try/except.
- **Work only on change**: the engine re-applies theme/wallpaper/sound only
  when the visible result changes (signatures/guards). Don't add unconditional
  per-tick OS writes.
- **Degrade gracefully**: no network → fallback weather; no pygame → silent; an
  unsupported OS → skip that write and log `[subsystem] …`. Never crash a tick.
- **Adding a setting** usually means: add to `config.py:DEFAULTS` (+ a
  `*_CHOICES` list if enumerated) → read it in `engine.py` → add a widget in
  `gui.py` (var + control + `_collect` + `apply_values_to_config` mapping) →
  add a test. `apply_values_to_config` reads new keys via `values.get(..., default)`
  so the existing GUI-mapping test keeps passing.
- **Files/paths**: user data in `config.json` / `tasks.json` (cwd); generated
  assets in `~/.environment_theme_controller/`; bundled `sounds/` and `music/`
  are resolved **absolute** (next to the module) — keep it that way.
- **Cross-platform** branches live in `theme.py`, `wallpaper.py`, `autostart.py`,
  `audiocheck.py` (guard on `sys.platform`).

## Testing conventions

- `tests.py` is a single headless script using a `check(name, cond)` helper and
  `section(title)`. It **stubs all system-mutating calls** (accent, wallpaper,
  audio, launchctl/registry, network) so running it never touches the machine
  or hits the internet. Follow that pattern for new tests.
- Prefer pure, deterministic logic you can test without a display. Inject `now`
  (datetime) rather than reading the clock so tests are stable.

## Gotchas (real, learned the hard way)

- **The GUI cannot be run in a headless/sandbox environment** — Tk aborts with
  `SystemAppearance not found` on macOS without a window server. Verify GUI
  changes via `py_compile` + `import gui` + logic tests, not by launching it.
- **`config.save_config` / `load_config` default `path` args bind at def time**
  to `"config.json"`. Reassigning `config.CONFIG_FILE` at runtime does NOT
  change them. Pass explicit paths in tests; don't rely on monkeypatching the
  module constant.
- **macOS wallpaper is per-Space**: a set made while a fullscreen app is focused
  doesn't reach the normal desktop. The engine periodically re-applies
  (`wallpaper_refresh_seconds`) to compensate — don't remove that.
- **macOS accent** only shows in apps launched *after* it's set, and snaps to
  ~8 named colours. Judge theme changes by the wallpaper, not the accent.
- **Never delete the displayed wallpaper file.** `wallpaper._cleanup_old`
  protects the just-built file, the last-applied file (`_applied_path`), and a
  few recent ones — otherwise the desktop reverts to the OS default when a set
  fails. Keep that invariant.
- **`engine.notify()` interpolates task titles into osascript/PowerShell** —
  a known injection sink if `tasks.json` is untrusted. Sanitize if you touch it.
- **Gradual transitions**: `engine` eases the displayed colour toward the target
  and sets `self.transitioning`; the loops step fast (~0.5s) while transitioning.
  Sun/moon position is recomputed live per animation frame.

## Don't

- Don't add telemetry/analytics or new outbound network calls (only Open-Meteo).
- Don't require an API key (Open-Meteo is keyless).
- Don't introduce heavy deps (NumPy/Pillow/Qt) — keep it stdlib-first.
- Don't leave `tests.py` red or `ruff` dirty.

## Docs

User-facing docs are in `docs/` (User guide, Wallpaper, Sounds, Tasks & timer,
Configuration, Troubleshooting). Update the relevant one when you change
behaviour, and bump the test count in `README.md`'s Testing section.
