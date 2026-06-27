import sys
import struct
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
    "cloud": (100, 110, 130),   # overcast grey-blue
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


def compute_theme_color(condition, sunrise, sunset, is_night_override=None):
    """
    Return ((r, g, b), brightness) for the given weather + time of day.

    *is_night_override*: pass True/False to force night/day brightness
    (used by the manual time-of-day override); None = compute from the
    sun times.
    """
    base = weather_base_color(condition)
    if is_night_override is True:
        bright = NIGHT_BRIGHTNESS
    elif is_night_override is False:
        bright = 1.0
    else:
        bright = brightness_factor(sunrise, sunset)
    return scale(base, bright), bright


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
