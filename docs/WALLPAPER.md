# Wallpaper Guide

The desktop background is a generated sky gradient coloured by current weather
and time of day, with optional weather patterns and a cold-weather warm tint.
Each frame is a still PNG; the app periodically regenerates it as conditions,
light, celestial position, or subtle drift change.

- [Wallpaper look](#wallpaper-look)
- [Weather patterns](#weather-patterns)
- [Cold-weather warmth](#cold-weather-warmth)

---

## Wallpaper look

On the **Settings** tab, the **Wallpaper look** card controls generated images:

- **Weather tint strength** — how strongly the weather colour shows vs. a
  neutral base.
- **Dynamic (subtle colour shift)** — a slow, barely-perceptible hue/brightness
  drift so the desktop feels alive without being distracting.
- **Colour shift strength** — how far that drift travels.
- **Weather patterns** — the condition-specific overlay (see below); positions
  shift between redraws. Turn it off for a plain gradient.
- **Warm palette when it's cold outside** — see [warmth](#cold-weather-warmth).

Each weather condition has its own base colour and gradient, so clear, cloudy,
rainy, stormy, and night skies all look distinct.

---

## Weather patterns

When **Weather patterns** is on, a light overlay is drawn per condition:

| Condition | Pattern |
|---|---|
| Clear (day) | The sun **rises in the east, arcs overhead, and sets in the west**, tracking the real sun — its drawn position moves gradually across the day as the wallpaper is redrawn; its glow is warm orange near the horizons, white at noon |
| Cloudy | Warm cream cloud puffs over a veiled-sun glow (never a bleak flat grey) |
| Rain | Light streaks trickling downward |
| Storm | Heavier slanted rain + the occasional lightning bolt |
| Clear night | The **moon** rises in the east, arcs overhead, and sets in the west (like the sun), over a twinkling starfield |
| Cloudy night | The moon + a few stars behind **dark, moonlit clouds** — distinct from a clear night |

Patterns are drawn *sparsely* — cost scales with the number of elements, not the
pixel count — so the wallpaper stays cheap to generate. Each wallpaper remains
still after it is set; element positions shift when the next PNG is generated.

---

## Cold-weather warmth

When the outside temperature is low, the whole palette is nudged toward a cosy
amber — stronger the colder it gets — so a cold day doesn't leave you with a
bleak blue-grey desktop. It fades in below ~18 °C and reaches full strength
around −4 °C. Turn it off with **Warm palette when it's cold outside**.
