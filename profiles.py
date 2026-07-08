"""
Mood profiles — Focus, Creativity, Relax.

A profile is a light overlay on the computed theme and a few settings, so the
whole environment shifts to suit what you're doing. Profiles can be switched
between and turned off ("none"). Everything here is pure so it's testable
without a display.

  * Focus      — calm, cool, low-saturation; quiet; no motion. Fewer distractions.
  * Creativity — vivid, saturated, slightly warm; lively motion.
  * Relax      — warm, dim, gentle; louder ambience.
"""

import colorsys

# name -> knobs
#   saturation : multiply colour saturation
#   warmth     : hue nudge toward warm (+) or cool (-), in 0..1 hue units * 0.1
#   brightness : multiply value
#   volume     : ambient sound volume (percent)
#   motion     : "off" | "smooth"  (maps to the wallpaper animation)
_PROFILES = {
    "focus":      {"label": "Focus",      "saturation": 0.70, "warmth": -0.06,
                   "brightness": 0.96, "volume": 12, "motion": "off"},
    "creativity": {"label": "Creativity", "saturation": 1.30, "warmth": 0.05,
                   "brightness": 1.00, "volume": 30, "motion": "smooth"},
    "relax":      {"label": "Relax",      "saturation": 0.95, "warmth": 0.16,
                   "brightness": 0.82, "volume": 45, "motion": "smooth"},
}

PROFILE_NAMES = ["focus", "creativity", "relax"]


def get(name):
    """The profile knobs for *name*, or None when off/unknown."""
    return _PROFILES.get((name or "none").lower())


def label(name):
    p = get(name)
    return p["label"] if p else "None"


def adjust_color(rgb, name):
    """Apply a profile's saturation / warmth / brightness to an RGB colour."""
    p = get(name)
    if not p:
        return tuple(int(c) for c in rgb)
    r, g, b = (max(0.0, min(1.0, c / 255.0)) for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = max(0.0, min(1.0, s * p["saturation"]))
    v = max(0.0, min(1.0, v * p["brightness"]))
    # Warmth: rotate hue gently toward orange (~0.08) or toward blue (~0.58).
    if p["warmth"]:
        target = 0.08 if p["warmth"] > 0 else 0.58
        amt = min(1.0, abs(p["warmth"]) * 2.0)
        # shortest-path hue blend toward the target
        dh = target - h
        if dh > 0.5:
            dh -= 1.0
        elif dh < -0.5:
            dh += 1.0
        h = (h + dh * amt) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def overlay_config(cfg, name):
    """
    Return *cfg* with the profile's settings applied (sound volume + motion).
    Returns the same dict unchanged when no profile is active. Non-destructive:
    a shallow copy is made only when a profile is active.
    """
    p = get(name)
    if not p:
        return cfg
    out = dict(cfg)
    out["sound_volume"] = p["volume"]
    if p["motion"] == "off":
        out["wallpaper_animated"] = False
    elif p["motion"] == "smooth":
        out["wallpaper_animated"] = True
        if (out.get("wallpaper_backend") or "png").lower() != "web":
            out["wallpaper_backend"] = "png"
    return out
