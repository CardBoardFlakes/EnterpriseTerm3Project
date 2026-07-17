# Troubleshooting

Quick fixes for the most common issues. Most subsystems fail *soft* — if
weather, sound, or the accent API is unavailable, the rest of the app keeps
working and prints a `[subsystem] …` note to the console.

- [The GUI won't open](#the-gui-wont-open)
- [There's no sound](#theres-no-sound)
- [The wallpaper isn't changing](#the-wallpaper-isnt-changing)
- [The accent colour didn't change (macOS)](#the-accent-colour-didnt-change-macos)
- [Weather is wrong or says "fallback"](#weather-is-wrong-or-says-fallback)
- [Smooth animation looks choppy or keeps pausing](#smooth-animation-looks-choppy-or-keeps-pausing)
- [Ultra wallpaper shows nothing](#ultra-wallpaper-shows-nothing)
- [Run-at-login didn't stick](#run-at-login-didnt-stick)
- [Reset everything](#reset-everything)

---

## The GUI won't open

Symptom: `No module named '_tkinter'` or the window never appears.

`tkinter` ships with Python but isn't a pip package:

- **macOS (Homebrew):** `brew install python-tk` — match your Python version,
  e.g. `brew install python-tk@3.13`.
- **Debian/Ubuntu:** `sudo apt install python3-tk`
- **Windows:** reinstall Python from python.org with the default options
  (Tk is included).

If there's genuinely no display, `python main.py` falls back to a single tick
and exits — use `--background` for the headless loop instead.

When run on macOS try checking the doc for the controller

---

## There's no sound

1. Install pygame: `pip install pygame`.
2. Make sure **Ambient sound** is ticked (Dashboard) and **Ambient volume**
   isn't at 0 (Appearance).
3. Check the console for `[sound] Audio unavailable …`. If mixer init fails,
   another app may hold the audio device, or the environment has no output.
4. Confirm the files are real `.wav` in `sounds/` — see the
   [sound guide](SOUNDS.md).

In **random** mode, sound is *supposed* to be silent most of the time — it plays
a clip only every few minutes.

---

## The wallpaper isn't changing

- Ensure **Weather wallpaper** is ticked and you pressed **▶ Start** (not just
  Save).
- Static redraws are rate-limited (`wallpaper_min_interval_seconds`, default
  45s) and only happen when the colour/brightness actually changes — give it a
  moment, or change the manual weather to force a difference.
- Linux desktops aren't supported for *setting* the wallpaper (the image is
  still generated); use the **Ultra** web backend with an engine instead.
- Check the console for `[wallpaper] Failed to set …`.

### It only changes when I'm *not* in a fullscreen app (macOS)

macOS gives each **Space** its own desktop, and a fullscreen app sits on its own
Space. The system API only sets the *current* Space's wallpaper, so a change made
while you're in a fullscreen app never reaches the normal desktop. The app works
around this by **re-applying the wallpaper periodically** (default every ~90s,
`wallpaper_refresh_seconds` in `config.json`), so the desktop catches up shortly
after you leave the fullscreen app. Lower that value for a faster catch-up, or
`0` to disable it. (Tip: in **System Settings → Desktop & Dock**, turning off
"Displays have separate Spaces" makes wallpaper behave more consistently.)

---

## The accent colour didn't change (macOS)

This is expected: macOS apps read the accent colour **when they launch**.
Already-open apps keep the old colour until relaunched. Dark/Light mode and the
wallpaper update immediately. macOS also snaps the colour to the nearest *named*
system accent (Blue, Purple, Graphite, …), so it won't be an exact RGB match.

---

## Weather is wrong or says "fallback"

- `fallback` means the live fetch failed (no `requests`, no network, or the API
  was unreachable). Install `requests` and check your connection.
- Wrong city? Set your coordinates in `config.json` →
  [`location`](CONFIGURATION.md#location).
- Want to test a specific condition regardless of the sky? Use the **Manual
  theme changer** on the Dashboard (`Weather` = rain/storm/…).

---

## Smooth animation looks choppy or keeps pausing

Smooth mode redraws the whole desktop image repeatedly, which is heavier than a
static image. The **load governor** intentionally lowers the frame rate — or
pauses to a static frame — when the machine is busy, then resumes when it frees
up (you'll see `[engine] Animation paused …`).

- Lower the **Frame rate (Smooth)** slider for less load.
- Raise `wallpaper_load_ceiling` in `config.json` if you want it to tolerate
  more load before backing off.
- For consistently smooth motion on a busy machine, use **Ultra** instead — it
  offloads rendering to a dedicated GPU wallpaper engine.

---

## Ultra wallpaper shows nothing

- Did you point the wallpaper engine at the right file? It's `index.html` in
  `~/.environment_theme_controller/webwallpaper/` — the **Set up the wallpaper
  app…** button opens that folder.
- Is the engine (ScreenPlay / Lively / Plash) actually running with that page
  set as the wallpaper?
- Is the app **Started**? It only refreshes `weather.json` while running; the
  page reads that file every couple of seconds.
- Full steps: [wallpaper guide → Ultra](WALLPAPER.md#setting-up-ultra-external-app).

---

## Run-at-login didn't stick

- **macOS:** check `~/Library/LaunchAgents/com.environmenttheme.controller.plist`
  exists. If `launchctl` reported an error, the plist is still written and will
  load next login.
- **Windows:** check the value `EnvironmentThemeController` under
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- The launcher runs `main.py --background` from the project folder — if you move
  the folder, re-toggle run-at-login so the path updates.

---

## Reset everything

Stop the app, then delete the state files — they're recreated with defaults on
next launch:

```bash
rm config.json tasks.json
rm -rf ~/.environment_theme_controller     # generated wallpaper + web assets
```

(Deleting `sounds/` also removes any custom audio; placeholders regenerate.)
