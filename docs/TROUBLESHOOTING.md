# Troubleshooting

Quick fixes for the most common issues. Most subsystems fail *soft* — if
weather, sound, or the accent API is unavailable, the rest of the app keeps
working and prints a `[subsystem] …` note to the console.

- [The GUI won't open](#the-gui-wont-open)
- [There's no sound](#theres-no-sound)
- [The wallpaper isn't changing](#the-wallpaper-isnt-changing)
- [The accent colour didn't change (macOS)](#the-accent-colour-didnt-change-macos)
- [Weather is wrong or says "fallback"](#weather-is-wrong-or-says-fallback)
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

---

## There's no sound

1. Install pygame: `pip install pygame`.
2. Make sure **Ambient sound** is ticked (Dashboard) and **Ambient volume**
   isn't at 0 (Settings).
3. Check the console for `[sound] Audio unavailable …`. If mixer init fails,
   another app may hold the audio device, or the environment has no output.
4. Confirm the files are real `.wav` in `sounds/` — see the
   [sound guide](SOUNDS.md).

Ambient sound should loop continuously. The engine retries mixer initialisation
after temporary device errors and restarts a dropped loop within a few seconds.

---

## The wallpaper isn't changing

- Ensure **Weather wallpaper** is ticked. Changes save and apply automatically.
- Generated wallpaper redraws are rate-limited (`wallpaper_min_interval_seconds`, default
  45s) and only happen when the colour/brightness actually changes — give it a
  moment, or change the manual weather to force a difference.
- Linux desktops aren't supported for *setting* the wallpaper (the image is
  still generated).
- Check the console for `[wallpaper] Failed to set …`.

Unticking **Weather wallpaper** restores the non-Flow wallpaper that was visible
before Flow most recently took over. Flow archives a stable copy rather than
relying on a temporary OS path. Turning off **Enable everything** also restores
it because that select-all action clears **Weather wallpaper**.

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
- Wrong city? Pick **Settings → Engine → City**. For an unlisted city, set its
  coordinates in `config.json` → [`location`](CONFIGURATION.md#location).
- Want to test a specific condition regardless of the sky? Use the **Manual
  theme changer** on the Dashboard (`Weather` = rain/storm/…).

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

Stop the app, then delete the state files. Defaults are used on next launch;
`config.json` is written again when a setting changes and `tasks.json` when a
reminder changes.

Before deleting the generated-wallpaper folder, untick **Weather wallpaper** so
Flow can restore the original desktop first. That folder also contains Flow's
archived copy used for restoration.

macOS/Linux shell:

```bash
rm config.json tasks.json
rm -rf ~/.environment_theme_controller     # generated wallpaper assets
```

Windows PowerShell (run from the project folder):

```powershell
Remove-Item config.json, tasks.json -ErrorAction SilentlyContinue
Remove-Item "$HOME\.environment_theme_controller" -Recurse -Force -ErrorAction SilentlyContinue
```

(Deleting `sounds/` also removes any custom audio; placeholders regenerate.)
