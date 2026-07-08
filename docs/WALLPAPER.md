# Wallpaper Guide

The desktop background is a sky gradient coloured by the current weather and
time of day, with optional moving patterns and a cold-weather warm tint.

- [Wallpaper look](#wallpaper-look)
- [Weather patterns](#weather-patterns)
- [Cold-weather warmth](#cold-weather-warmth)
- [Wallpaper motion: Off / Smooth / Ultra](#wallpaper-motion-off--smooth--ultra)
- [Setting up Ultra (external app)](#setting-up-ultra-external-app)
- [Performance & the load governor](#performance--the-load-governor)

---

## Wallpaper look

On the **Appearance** tab, the **Wallpaper look** card controls the static look:

- **Weather tint strength** — how strongly the weather colour shows vs. a
  neutral base.
- **Dynamic (subtle colour shift)** — a slow, barely-perceptible hue/brightness
  drift so the desktop feels alive without being distracting.
- **Colour shift strength** — how far that drift travels.
- **Weather patterns** — the moving overlay (see below); turn off for a plain
  gradient.
- **Warm palette when it's cold outside** — see [warmth](#cold-weather-warmth).

Each weather condition has its own base colour and gradient, so clear, cloudy,
rainy, stormy, and night skies all look distinct.

---

## Weather patterns

When **Weather patterns** is on, a light overlay is drawn per condition:

| Condition | Pattern |
|---|---|
| Clear (day) | The sun **rises in the east, arcs overhead, and sets in the west** with the real time of day; its glow is warm orange near the horizons, white at noon |
| Cloudy | Warm cream cloud puffs over a veiled-sun glow (never a bleak flat grey) |
| Rain | Light streaks trickling downward |
| Storm | Heavier slanted rain + the occasional lightning bolt |
| Clear night | The **moon** rises in the east, arcs overhead, and sets in the west (like the sun), over a twinkling starfield |
| Cloudy night | The moon + a few stars behind **dark, moonlit clouds** — distinct from a clear night |

Patterns are drawn *sparsely* — cost scales with the number of elements, not the
pixel count — so even the static wallpaper stays cheap. The elements shift a
little on each redraw, giving gentle motion without the Smooth/Ultra modes.

---

## Cold-weather warmth

When the outside temperature is low, the whole palette is nudged toward a cosy
amber — stronger the colder it gets — so a cold day doesn't leave you with a
bleak blue-grey desktop. It fades in below ~18 °C and reaches full strength
around −4 °C. Turn it off with **Warm palette when it's cold outside**.

---

## Wallpaper motion: Off / Smooth / Ultra

The **Wallpaper motion** card offers one simple choice:

| Choice | What it does | Setup | Cost |
|---|---|---|---|
| **Off** | A still image that still updates as the weather changes. | None | Negligible |
| **Smooth** | Built-in animation — rain trickling, clouds drifting, stars twinkling — redrawn continuously at your chosen **frame rate**. | **None** | Moderate (auto-managed) |
| **Ultra** | Smoothest, GPU-rendered motion via a free external wallpaper app. | One-time (below) | Near-zero for this app |

**Most people want Smooth** — it needs no extra software. Pick **Ultra** only if
you want buttery, high-frame-rate motion and don't mind installing one free app.

The **Frame rate (Smooth)** slider sets the target frames per second for Smooth
mode. Higher = smoother but more CPU. The load governor (below) will quietly
reduce or pause it if your machine gets busy.

---

## Setting up Ultra (external app)

Ultra hands rendering to a dedicated wallpaper engine. This app keeps a small
HTML/canvas wallpaper and a live `weather.json` file up to date; the engine
draws it. Steps:

1. Select **Ultra**, then click **Set up the wallpaper app…**. This creates the
   files and opens the folder containing **`index.html`** (in
   `~/.environment_theme_controller/webwallpaper/`).
2. Install a free wallpaper engine and point it at that `index.html`:

   **ScreenPlay** (macOS + Windows + Linux) — <https://screen-play.app>
   - Create Wallpaper → **Web** → choose the folder / `index.html`.

   **Lively Wallpaper** (Windows) — Microsoft Store
   - Click **+** → browse → select `index.html`.

   **Plash** (macOS) — Mac App Store
   - Menu-bar icon → set the website to the `file://…/index.html` URL shown in
     the app.

3. Back here, press **▶ Start**. The page picks up live weather within a couple
   of seconds and animates it.

You only do this once. Afterwards the app just refreshes `weather.json` when the
weather changes — its own CPU/GPU cost stays near zero because the external
engine does the drawing (and those apps pause themselves during fullscreen apps
and on battery).

---

## Performance & the load governor

Smooth mode deliberately uses more CPU than a static image, so it is watched by
a **load governor**:

- It measures how long each frame takes to draw *and* the system load.
- As the machine gets busy it **throttles** the frame rate down.
- If things stay heavy it **pauses** animation entirely, dropping to a single
  static frame, and prints a note.
- Once the load clears it **resumes automatically**.

So you can leave Smooth on without worrying about it bogging down a busy laptop.
Ultra offloads all of this to the external engine, so the governor doesn't apply.
