import sys
import struct
import colorsys
from datetime import datetime


# ---------------------------------------------------------
# BRIGHTNESS MULTIPLIER  (day vs night)
# ---------------------------------------------------------

def brightness_factor(sunrise, sunset):
    if isinstance(sunrise, str):
        sunrise_dt = datetime.fromisoformat(sunrise)
    else:
        sunrise_dt = sunrise
    if isinstance(sunset, str):
        sunset_dt = datetime.fromisoformat(sunset)
    else:
        sunset_dt = sunset

    def total_secs(dt):
        t = dt.time() if hasattr(dt, "time") else dt
        return t.hour * 3600 + t.minute * 60 + t.second

    now_s  = total_secs(datetime.now())
    rise_s = total_secs(sunrise_dt)
    set_s  = total_secs(sunset_dt)
    fade   = 45 * 60
    NIGHT  = 0.15

    if now_s < rise_s - fade:
        return NIGHT
    elif now_s < rise_s + fade:
        t = (now_s - (rise_s - fade)) / (2 * fade)
        return NIGHT + t * (1.0 - NIGHT)
    elif now_s < set_s - fade:
        return 1.0
    elif now_s < set_s + fade:
        t = (now_s - (set_s - fade)) / (2 * fade)
        return 1.0 - t * (1.0 - NIGHT)
    else:
        return NIGHT


# ---------------------------------------------------------
# WEATHER BASE COLORS
# ---------------------------------------------------------

CONDITION_COLORS = {
    "clear": ( 80, 160, 255),   # clear-sky blue
    "cloud": (135, 178, 222),   # bright soft-blue overcast (cheerful, not grey)
    "rain":  ( 40,  80, 180),   # stormy blue
    "storm": ( 80,  20, 160),   # deep purple
    "night": ( 20,  30,  80),   # midnight navy
}
FALLBACK_COLOR = (70, 80, 100)


def weather_base_color(condition):
    cond = condition.lower()
    for key, color in CONDITION_COLORS.items():
        if key in cond:
            return color
    return FALLBACK_COLOR


def scale(color, factor):
    factor = max(0.0, min(1.0, factor))
    return (
        int(color[0] * factor),
        int(color[1] * factor),
        int(color[2] * factor),
    )


# ---------------------------------------------------------
# ACCENT PALETTE GENERATOR  (Windows)
# ---------------------------------------------------------

def generate_accent_palette(r, g, b):
    """
    Generate the 8-shade palette Windows derives from an accent colour.
    Stored as 32 bytes: R,G,B,0x00 per shade, lightest to darkest.
    """
    shades = []
    for t in [0.6, 0.2, 0.0]:              # 3 lighter shades
        shades.append((
            int(r + (255 - r) * t),
            int(g + (255 - g) * t),
            int(b + (255 - b) * t),
        ))
    shades.append((r, g, b))               # base colour
    for t in [0.15, 0.3, 0.5, 0.7]:       # 4 darker shades
        shades.append((
            int(r * (1 - t)),
            int(g * (1 - t)),
            int(b * (1 - t)),
        ))
    return b"".join(struct.pack("4B", sr, sg, sb, 0x00)
                    for sr, sg, sb in shades)


# ---------------------------------------------------------
# WINDOWS ACCENT COLOR SETTER
# ---------------------------------------------------------

def set_windows_accent(r, g, b):
    """
    Set the Windows taskbar accent colour by writing directly to the
    registry keys Windows 11 24H2 actually reads, then broadcasting
    ImmersiveColorSet so the change applies immediately without any
    explorer restart.
    """
    import ctypes
    import winreg

    abgr      = (0xFF << 24) | (b << 16) | (g << 8) | r
    mr, mg, mb = int(r * 0.4), int(g * 0.4), int(b * 0.4)
    abgr_menu = (0xFF << 24) | (mb << 16) | (mg << 8) | mr
    palette   = generate_accent_palette(r, g, b)

    try:
        # Primary key — what Win11 24H2 actually reads for taskbar colour
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "AccentColor",     0, winreg.REG_DWORD,  abgr)
        winreg.SetValueEx(key, "AccentColorMenu", 0, winreg.REG_DWORD,  abgr_menu)
        winreg.SetValueEx(key, "AccentPalette",   0, winreg.REG_BINARY, palette)
        winreg.CloseKey(key)

        # Keep DWM in sync (used by title bars and older components)
        key2 = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\DWM",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key2, "AccentColor",     0, winreg.REG_DWORD, abgr)
        winreg.SetValueEx(key2, "AccentColorMenu", 0, winreg.REG_DWORD, abgr_menu)
        winreg.CloseKey(key2)

        # Ensure accent-on-taskbar is enabled
        key3 = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key3, "ColorPrevalence", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key3)

        # Broadcast so Windows applies the change immediately
        HWND_BROADCAST   = 0xFFFF
        WM_SETTINGCHANGE  = 0x001A
        SMTO_ABORTIFHUNG  = 0x0002
        result = ctypes.c_long()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0,
            "ImmersiveColorSet",
            SMTO_ABORTIFHUNG, 5000, ctypes.byref(result)
        )
        print(f"[theme] Accent colour set to ({r},{g},{b})")

    except Exception as e:
        print(f"[theme] Failed to set accent colour: {e}")


# ---------------------------------------------------------
# macOS THEME SETTER
# ---------------------------------------------------------
#
# macOS has no taskbar and no public API for an arbitrary-RGB system
# accent. Two scriptable knobs map cleanly onto this app's intent:
#   1. Dark / Light appearance  -> driven by the day/night brightness.
#   2. System accent colour     -> snapped to the nearest macOS named
#                                   accent derived from the weather colour.
#
# Appearance changes apply live; the accent colour is picked up by apps
# as they next draw (a relaunch shows it everywhere).

# (name, AppleAccentColor int, representative RGB) — names match the
# tokens macOS expects in AppleHighlightColor.
_MACOS_ACCENTS = [
    ("Red",      0,  (255,  82,  89)),
    ("Orange",   1,  (247, 130,  50)),
    ("Yellow",   2,  (252, 184,  40)),
    ("Green",    3,  (102, 186,  73)),
    ("Blue",     4,  (  0, 122, 255)),
    ("Purple",   5,  (148,  81, 165)),
    ("Pink",     6,  (247, 100, 168)),
    ("Graphite", -1, (142, 142, 147)),
]

# Below this day/night brightness, switch to Dark mode.
DARK_MODE_THRESHOLD = 0.5


def _nearest_macos_accent(r, g, b):
    """Pick the macOS named accent whose RGB is closest to (r, g, b)."""
    return min(
        _MACOS_ACCENTS,
        key=lambda a: (r - a[2][0]) ** 2 + (g - a[2][1]) ** 2 + (b - a[2][2]) ** 2,
    )


def set_macos_theme(r, g, b, brightness):
    """Apply appearance + accent colour on macOS via osascript / defaults."""
    import subprocess

    # 1. Dark / Light appearance from the day-night brightness curve.
    dark = brightness < DARK_MODE_THRESHOLD
    try:
        subprocess.run(
            ["osascript", "-e",
             "tell application \"System Events\" to tell appearance preferences "
             f"to set dark mode to {str(dark).lower()}"],
            check=True, capture_output=True, text=True, timeout=5,
        )
        print(f"[theme] macOS appearance -> {'Dark' if dark else 'Light'} "
              f"(brightness={brightness:.2f})")
    except Exception as e:
        print(f"[theme] Failed to set macOS appearance: {e}")

    # 2. Accent colour -> nearest macOS named accent.
    name, idx, (cr, cg, cb) = _nearest_macos_accent(r, g, b)
    try:
        subprocess.run(
            ["defaults", "write", "-g", "AppleAccentColor", "-int", str(idx)],
            check=True, capture_output=True, text=True, timeout=5,
        )
        highlight = f"{cr/255:.6f} {cg/255:.6f} {cb/255:.6f} {name}"
        subprocess.run(
            ["defaults", "write", "-g", "AppleHighlightColor", "-string", highlight],
            check=True, capture_output=True, text=True, timeout=5,
        )
        print(f"[theme] macOS accent -> {name} (nearest to ({r},{g},{b})). "
              "Relaunch apps to see it everywhere.")
    except Exception as e:
        print(f"[theme] Failed to set macOS accent colour: {e}")


# ---------------------------------------------------------
# COMPUTE + APPLY  (used by the engine)
# ---------------------------------------------------------

NIGHT_BRIGHTNESS = 0.15


# ---------------------------------------------------------
# TIME-OF-DAY PHASES
# ---------------------------------------------------------
#
# Beyond a plain day/night split, the theme moves through the day's light:
# warm and low at sunrise, neutral and bright at midday, warm again at sunset,
# cooling into a purple dusk and a deep-blue night. Each phase carries a
# representative brightness plus a "sky light" colour blended into the weather
# colour, so the background reflects the time of day, not just the weather.

TIME_PHASES = ["night", "sunrise", "morning", "midday", "afternoon", "sunset", "dusk"]

# phase -> (brightness, sky-light colour RGB, strength 0..1)
# Strong, saturated tints so the result reads as a real colour (orange dawn/
# dusk, blue noon, purple twilight, navy night) rather than a muddy grey. The
# tint is kept vivid enough that the nearest macOS named accent lands on the
# expected colour (e.g. sunset -> Orange).
_PHASE_LIGHT = {
    "night":     (0.15, ( 15,  20,  70), 0.80),
    "sunrise":   (0.75, (255, 150,  40), 0.80),
    "morning":   (0.90, (255, 235, 180), 0.05),
    "midday":    (1.00, (255, 255, 255), 0.05),
    "afternoon": (0.95, (255, 215, 150), 0.06),
    "sunset":    (0.80, (255, 110,  30), 0.85),
    "dusk":      (0.40, (110,  60, 170), 0.70),
}

# Where the sun sits for a manual phase (0 = sunrise/east, 1 = sunset/west);
# None means no sun (dusk/night).
_PHASE_SUN = {"sunrise": 0.06, "morning": 0.28, "midday": 0.5,
              "afternoon": 0.72, "sunset": 0.94}


def phase_sun_fraction(phase):
    """Sun position 0..1 (east->west) for a phase, or None if the sun is down."""
    return _PHASE_SUN.get(phase)


def day_fraction(sunrise, sunset, now=None):
    """
    How far through daylight *now* is: 0 at sunrise (east), 1 at sunset (west).
    None before sunrise / after sunset (sun below the horizon).
    """
    now_s = _secs_of_day(now or datetime.now())
    rise = _secs_of_day(sunrise)
    set_ = _secs_of_day(sunset)
    if set_ <= rise or now_s <= rise or now_s >= set_:
        return None
    return (now_s - rise) / (set_ - rise)


def night_fraction(sunrise, sunset, now=None):
    """
    How far through the night *now* is: 0 at sunset (moon rises in the east),
    1 at the next sunrise (moon sets in the west). None during daylight.
    """
    now_s = _secs_of_day(now or datetime.now())
    rise = _secs_of_day(sunrise)
    set_ = _secs_of_day(sunset)
    DAY = 24 * 3600
    if rise <= now_s <= set_:            # daytime — no moon
        return None
    night_len = (DAY - set_) + rise
    if night_len <= 0:
        return 0.5
    elapsed = (now_s - set_) if now_s > set_ else (DAY - set_) + now_s
    return max(0.0, min(1.0, elapsed / night_len))


def celestial_fraction(phase, sunrise, sunset, now=None):
    """
    Sky-body position 0..1 (east->west) for the wallpaper: the sun's arc by day
    and the moon's arc by night. Falls back to mid-sky when time is ambiguous.
    """
    frac = phase_sun_fraction(phase) if phase else day_fraction(sunrise, sunset, now)
    if frac is None:
        frac = night_fraction(sunrise, sunset, now)
    return 0.5 if frac is None else frac


def _to_dt(x):
    return datetime.fromisoformat(x) if isinstance(x, str) else x


def _secs_of_day(x):
    dt = _to_dt(x)
    t = dt.time() if hasattr(dt, "time") else dt
    return t.hour * 3600 + t.minute * 60 + t.second


def _mix(c1, c2, t):
    return tuple(max(0, min(255, int(round(c1[i] + (c2[i] - c1[i]) * t))))
                 for i in range(3))


def phase_light(phase):
    """(brightness, tint_rgb, strength) for *phase*; neutral for unknown."""
    return _PHASE_LIGHT.get(phase, (1.0, (255, 255, 255), 0.0))


def apply_phase_tint(rgb, phase):
    """Blend the weather colour toward the phase's sky-light colour."""
    _b, tint, strength = phase_light(phase)
    return _mix(rgb, tint, strength)


def normalize_phase(name):
    """Map a manual choice to a known phase (``day`` -> ``midday``), or None."""
    n = (name or "").lower()
    if n == "day":
        return "midday"
    return n if n in TIME_PHASES else None


def phase_is_night(phase):
    """True for phases treated as night (dark mode + night ambience/wallpaper)."""
    return phase == "night"


def compute_day_phase(sunrise, sunset, now=None):
    """Which time-of-day phase *now* falls in, relative to sunrise/sunset."""
    now_s = _secs_of_day(now or datetime.now())
    rise = _secs_of_day(sunrise)
    set_ = _secs_of_day(sunset)
    noon = (rise + set_) / 2
    H = 3600
    if now_s < rise - 0.5 * H or now_s >= set_ + 1.5 * H:
        return "night"
    if now_s < rise + 0.5 * H:
        return "sunrise"
    if now_s < noon - 1.5 * H:
        return "morning"
    if now_s < noon + 1.5 * H:
        return "midday"
    if now_s < set_ - 0.5 * H:
        return "afternoon"
    if now_s < set_ + 0.5 * H:
        return "sunset"
    return "dusk"


# ---------------------------------------------------------
# SEASONS
# ---------------------------------------------------------
# A gentle seasonal wash over the palette.
SEASON_LIGHT = {
    "spring": ((120, 225, 150), 0.08),   # fresh green
    "summer": ((255, 225, 120), 0.08),   # golden
    "autumn": ((235, 140,  55), 0.12),   # amber
    "winter": ((150, 195, 240), 0.10),   # cool blue
}

_NORTH_SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring",
                 4: "spring", 5: "spring", 6: "summer", 7: "summer",
                 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
_OPPOSITE = {"winter": "summer", "summer": "winter",
             "spring": "autumn", "autumn": "spring"}


def hemisphere_for(lat, setting="auto"):
    s = (setting or "auto").lower()
    if s in ("north", "south"):
        return s
    return "south" if (lat is not None and lat < 0) else "north"


def season_for(date, hemisphere="north"):
    """Meteorological season for *date* in the given hemisphere."""
    s = _NORTH_SEASON[date.month]
    return _OPPOSITE[s] if (hemisphere or "north").lower() == "south" else s


def _apply_season(rgb, season):
    sl = SEASON_LIGHT.get(season)
    return _mix(rgb, sl[0], sl[1]) if sl else rgb


# ---------------------------------------------------------
# CONTINUOUS SKY LIGHT  (gradual time-of-day transitions)
# ---------------------------------------------------------

def sky_light(sunrise, sunset, now=None):
    """
    Interpolate (brightness, tint, strength) smoothly across the day between
    the phase keyframes, so the theme glides between times instead of snapping.
    """
    now_s = _secs_of_day(now or datetime.now())
    rise = _secs_of_day(sunrise)
    set_ = _secs_of_day(sunset)
    if set_ <= rise:
        return phase_light("midday")
    noon = (rise + set_) / 2.0
    H, DAY = 3600.0, 86400.0
    raw = [
        (0.0, "night"), (rise - 0.75 * H, "night"), (rise + 0.25 * H, "sunrise"),
        (rise + 0.25 * H + 0.35 * (noon - rise), "morning"), (noon, "midday"),
        (noon + 0.6 * (set_ - noon), "afternoon"), (set_, "sunset"),
        (set_ + 0.75 * H, "dusk"), (set_ + 1.5 * H, "night"), (DAY, "night"),
    ]
    anchors = []
    for tsec, ph in raw:
        tsec = max(0.0, min(DAY, tsec))
        if anchors and tsec <= anchors[-1][0]:
            continue
        anchors.append((tsec, ph))
    prev, nxt = anchors[0], anchors[-1]
    for i in range(len(anchors) - 1):
        if anchors[i][0] <= now_s <= anchors[i + 1][0]:
            prev, nxt = anchors[i], anchors[i + 1]
            break
    span = nxt[0] - prev[0]
    t = 0.0 if span <= 0 else (now_s - prev[0]) / span
    pb, pt, ps = phase_light(prev[1])
    nb, nt, ns = phase_light(nxt[1])
    return (pb + (nb - pb) * t,
            tuple(pt[i] + (nt[i] - pt[i]) * t for i in range(3)),
            ps + (ns - ps) * t)


# ---------------------------------------------------------
# ACCESSIBILITY
# ---------------------------------------------------------

def high_contrast(rgb):
    """Push a colour to a bold, maximally-saturated version (keeps the hue)."""
    r, g, b = (c / 255.0 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if s < 0.15:                       # near-grey -> strong yellow / black
        return (255, 255, 0) if v > 0.5 else (10, 10, 10)
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def compute_theme_color(condition, sunrise, sunset, is_night_override=None,
                        phase=None, now=None, season=None):
    """
    Return ((r, g, b), brightness) for the given weather + time of day.

    The colour is the weather base tinted by the time-of-day *phase*.

    *phase*: force a specific phase (``"sunrise"``, ``"midday"``, …) and use its
    representative brightness + light. None = derive the phase from the sun
    times (for the tint) and take brightness from the smooth day/night curve.
    *is_night_override*: when *phase* is None, force night/day brightness
    (manual day/night); None = automatic.
    *season*: optional season name for a gentle palette wash.

    When *phase* is None the tint/brightness come from the *continuous*
    ``sky_light`` curve, so the theme glides smoothly between times of day.
    """
    base = weather_base_color(condition)

    if phase is not None:                       # manual phase -> discrete light
        bright, tint, strength = phase_light(phase)
    elif is_night_override is True:
        bright, tint, strength = phase_light("night")
    elif is_night_override is False:
        bright, tint, strength = phase_light("midday")
    else:                                       # auto -> smooth, continuous
        bright, tint, strength = sky_light(sunrise, sunset, now)

    col = _mix(base, tint, strength)
    col = _apply_season(col, season)
    # Keep the hue vivid; darken only gently (heavy scaling greys the accent).
    final = _mix(col, (0, 0, 0), (1.0 - bright) * 0.45)
    return final, bright


def theme_signature(r, g, b, brightness):
    """
    A hashable summary of what the user would actually *see* for this colour,
    so the engine can skip re-applying when nothing visible changed. On macOS
    the accent snaps to a named colour, so only the name + appearance matter.
    """
    appearance = "dark" if brightness < DARK_MODE_THRESHOLD else "light"
    if sys.platform == "darwin":
        return (appearance, _nearest_macos_accent(r, g, b)[1])
    return (appearance, r, g, b)


def apply_theme_color(r, g, b, brightness):
    """
    Apply an already-computed RGB colour using whatever mechanism the
    current OS supports:
      * Windows -> taskbar accent colour via the registry
      * macOS   -> Dark/Light appearance + nearest named accent colour
    Returns a short human-readable description of what was applied.
    """
    if sys.platform == "win32":
        set_windows_accent(r, g, b)
        return f"Windows accent ({r},{g},{b})"
    elif sys.platform == "darwin":
        set_macos_theme(r, g, b, brightness)
        name, _idx, _rgb = _nearest_macos_accent(r, g, b)
        appearance = "Dark" if brightness < DARK_MODE_THRESHOLD else "Light"
        return f"macOS {appearance} + {name} accent"
    else:
        print(f"[theme] Dynamic theme not supported on {sys.platform!r} — skipping.")
        return "unsupported platform"


# ---------------------------------------------------------
# MAIN ENTRY POINT  (kept for backward compatibility)
# ---------------------------------------------------------

def apply_dynamic_theme(condition, sunrise, sunset, tint_strength=0.3):
    """Compute the theme colour from weather + time of day, then apply it."""
    (r, g, b), bright = compute_theme_color(condition, sunrise, sunset)
    print(
        f"[theme] condition={condition!r}  brightness={bright:.2f}  "
        f"-> final=({r},{g},{b})"
    )
    return apply_theme_color(r, g, b, bright)
