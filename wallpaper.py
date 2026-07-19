"""
Weather-driven desktop wallpaper.

Generates a vertical gradient image (pure standard library — no Pillow)
from the weather/time colour and sets it as the desktop background on
both macOS and Windows.
"""

import os
import sys
import math
import struct
import zlib
import colorsys
import subprocess

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".environment_theme_controller")

# Path of the wallpaper the OS is currently displaying (last successful set).
# Never deleted by cleanup, so the desktop can't be left pointing at a file we
# removed — which would make it revert to the OS default background.
_applied_path = None


# ---------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------

def _clamp(v):
    return max(0, min(255, int(round(v))))


def _lerp(a, b, t):
    return a + (b - a) * t


def _mix(c1, c2, t):
    return tuple(_clamp(_lerp(c1[i], c2[i], t)) for i in range(3))


# ---------------------------------------------------------
# Minimal PNG writer (8-bit RGB)
# ---------------------------------------------------------

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _build_raw_gradient(width, height, top_rgb, bottom_rgb):
    """
    Build the raw PNG scanline buffer for a vertical gradient and return
    ``(raw, stride)``. *stride* is the byte length of one scanline including
    its leading filter byte, so pixel (x, y)'s red channel lives at
    ``y * stride + 1 + x * 3`` — this makes the buffer randomly addressable
    for the pattern overlays below.
    """
    stride = 1 + width * 3
    raw = bytearray(stride * height)
    for y in range(height):
        t = y / max(1, height - 1)
        r, g, b = _mix(top_rgb, bottom_rgb, t)
        base = y * stride
        raw[base] = 0                        # filter type 0 (None)
        row = bytes((r, g, b)) * width
        raw[base + 1:base + stride] = row
    return raw, stride


def _encode_png(raw, width, height):
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, colour type 2 (RGB)
    idat = zlib.compress(bytes(raw), 6)
    return sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


def write_gradient_png(path, width, height, top_rgb, bottom_rgb):
    """Write a vertical gradient PNG from top_rgb (y=0) to bottom_rgb."""
    raw, _ = _build_raw_gradient(width, height, top_rgb, bottom_rgb)
    png = _encode_png(raw, width, height)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return path


# ---------------------------------------------------------
# Weather pattern overlays
#
# Each pattern draws a *sparse* set of elements (streaks, dots, a soft glow)
# straight onto the raw buffer, so cost scales with the number of elements
# drawn — not the pixel count. Element positions are driven by *phase*
# (0..1, one slow cycle) so successive redraws show gentle motion: rain
# trickles down, clouds drift, stars twinkle. All randomness is a
# deterministic LCG seeded per pattern, so a given frame is reproducible
# (and testable) with no reliance on the wall clock.
# ---------------------------------------------------------

# Weather palette is warmed toward this amber when it is cold outside; the
# colder it gets, the stronger the blend, to counteract a bleak cold sky.
WARM_TINT = (255, 140, 60)
COMFORT_TEMP = 18.0     # °C at/above which no warming is applied
COLD_TEMP = -4.0        # °C at/below which warming is at full strength

# Conditions that carry motion worth redrawing on the engine's interval.
ANIMATED_CONDITIONS = ("storm", "rain", "cloud", "night", "clear")


def warmth_factor(temperature):
    """0..1 cosy-warmth strength for *temperature* (°C); 0 when None/warm."""
    if temperature is None:
        return 0.0
    if temperature >= COMFORT_TEMP:
        return 0.0
    if temperature <= COLD_TEMP:
        return 1.0
    return (COMFORT_TEMP - temperature) / (COMFORT_TEMP - COLD_TEMP)


def is_animated(condition):
    """True if *condition* has a moving pattern (worth redrawing over time)."""
    c = (condition or "").lower()
    return any(k in c for k in ANIMATED_CONDITIONS)


def _prng(seed):
    """Tiny deterministic LCG → successive floats in [0, 1)."""
    # Scramble the seed first so *nearby* seeds (e.g. consecutive frames)
    # diverge right from the first draw instead of marching in lockstep.
    state = (int(seed) * 2654435761 + 1013904223) & 0x7FFFFFFF

    def nxt():
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    nxt()  # warm up
    return nxt


def _blend_px(raw, stride, w, h, x, y, color, alpha):
    """Alpha-blend *color* onto pixel (x, y); silently ignores out-of-bounds."""
    if alpha <= 0 or x < 0 or x >= w or y < 0 or y >= h:
        return
    if alpha > 1:
        alpha = 1.0
    off = y * stride + 1 + x * 3
    inv = 1.0 - alpha
    raw[off]     = _clamp(raw[off]     * inv + color[0] * alpha)
    raw[off + 1] = _clamp(raw[off + 1] * inv + color[1] * alpha)
    raw[off + 2] = _clamp(raw[off + 2] * inv + color[2] * alpha)


def _soft_glow(raw, stride, w, h, cx, cy, radius, color, alpha):
    """A radial glow with quadratic (no-sqrt) falloff inside a bounding box."""
    if radius <= 0 or alpha <= 0:
        return
    r2 = radius * radius
    for y in range(max(0, cy - radius), min(h, cy + radius)):
        dy2 = (y - cy) ** 2
        for x in range(max(0, cx - radius), min(w, cx + radius)):
            d2 = (x - cx) ** 2 + dy2
            if d2 >= r2:
                continue
            _blend_px(raw, stride, w, h, x, y, color, alpha * (1 - d2 / r2))


def _soft_ellipse(raw, stride, w, h, cx, cy, rx, ry, color, alpha):
    """A soft-edged filled ellipse (used for cloud puffs)."""
    if rx <= 0 or ry <= 0 or alpha <= 0:
        return
    for y in range(max(0, cy - ry), min(h, cy + ry)):
        ny2 = ((y - cy) / ry) ** 2
        for x in range(max(0, cx - rx), min(w, cx + rx)):
            d = ((x - cx) / rx) ** 2 + ny2
            if d >= 1:
                continue
            _blend_px(raw, stride, w, h, x, y, color, alpha * (1 - d))


def _render_rain(raw, stride, w, h, phase, brightness, heavy=False):
    """Streaks that trickle downward as *phase* advances."""
    drops = max(12, w // (8 if heavy else 12))
    slant = 4 if heavy else 2
    length = 16 if heavy else 11
    head = 0.4 if heavy else 0.28
    col = (205, 222, 255)
    rnd = _prng(1 if not heavy else 2)
    for _ in range(drops):
        x0 = int(rnd() * w)
        spd = 0.6 + rnd() * 0.9
        L = max(4, int(length * (0.6 + rnd() * 0.8)))
        travel = h + L
        y0 = (rnd() * h + phase * travel * spd) % travel - L
        for k in range(L):
            x = x0 + int(slant * k / L)
            y = int(y0) + k
            _blend_px(raw, stride, w, h, x, y, col, head * (k + 1) / L)


def _render_bolt(raw, stride, w, h, phase, flash):
    """A jagged lightning bolt down the upper half, with a faint halo."""
    seg = int(phase * 12)
    rnd = _prng(seg + 200)
    x = int(rnd() * w * 0.6 + w * 0.2)
    y = 0
    limit = int(h * 0.55)
    col = (255, 255, 240)
    while y < limit:
        seglen = int(6 + rnd() * 12)
        dx = int((rnd() - 0.5) * 12)
        for k in range(seglen):
            if y >= h:
                break
            xx = x + int(dx * k / max(1, seglen))
            _blend_px(raw, stride, w, h, xx, y, col, flash * 0.9)
            _blend_px(raw, stride, w, h, xx - 1, y, col, flash * 0.4)
            _blend_px(raw, stride, w, h, xx + 1, y, col, flash * 0.4)
            y += 1
        x += dx


def _flash_intensity(phase):
    """0..1 lightning flash for this frame; mostly 0, an occasional spike."""
    seg = int(phase * 12)
    rnd = _prng(seg + 100)
    if rnd() < 0.22:
        local = phase * 12 - seg
        return max(0.0, 1 - abs(local - 0.15) / 0.2)
    return 0.0


def _render_storm(raw, stride, w, h, phase, brightness):
    flash = _flash_intensity(phase)
    if flash > 0:
        _render_bolt(raw, stride, w, h, phase, flash)
    _render_rain(raw, stride, w, h, phase, brightness, heavy=True)


def _sun_xy(w, h, sun):
    """
    Screen position of the sun for daylight fraction *sun* (0=sunrise/east,
    1=sunset/west): a low arc that peaks at midday. None -> centred, high.
    """
    if sun is None:
        sun = 0.5
    sun = max(0.0, min(1.0, sun))
    elev = math.sin(math.pi * sun)                 # 0 at the horizons, 1 at noon
    cx = int(w * (0.10 + 0.80 * sun))              # east (left) -> west (right)
    cy = int(h * (0.40 - 0.26 * elev))             # low near the edges, high at noon
    return cx, cy, elev


def _render_sun_rays(raw, stride, w, h, cx, cy, radius, color, alpha, phase):
    """A few faint rays fanning out from the sun — cheap line sampling."""
    if alpha <= 0:
        return
    for i in range(10):
        ang = 2 * math.pi * i / 10 + phase * 0.6
        dx, dy = math.cos(ang), math.sin(ang)
        for r in range(int(radius * 0.35), int(radius * 1.05), 2):
            _blend_px(raw, stride, w, h, int(cx + dx * r), int(cy + dy * r),
                      color, alpha * (1 - r / (radius * 1.05)))


def _render_clear(raw, stride, w, h, phase, brightness, sun=None):
    """The sun: rises in the east, arcs overhead, sets in the west, with rays.

    Near the horizons (low sun) the glow warms to orange; at noon it's white.
    """
    cx, cy, elev = _sun_xy(w, h, sun)
    warm = _mix((255, 140, 40), (255, 250, 220), elev)   # orange low -> white high
    R = int(min(w, h) * (0.42 + 0.12 * (1 - elev)))
    _soft_glow(raw, stride, w, h, cx, cy, R, warm, 0.55 * brightness)
    _render_sun_rays(raw, stride, w, h, cx, cy, R * 0.9, warm, 0.10 * brightness, phase)
    _soft_glow(raw, stride, w, h, cx, cy, max(3, int(min(w, h) * 0.07)),
               (255, 250, 225), 0.9 * brightness)


def _render_cloud(raw, stride, w, h, phase, brightness, sun=None):
    """Fluffy sunlit clouds over a bright sky — cheerful, never a flat grey."""
    sx, sy, elev = _sun_xy(w, h, sun)
    # Warm sunlit haze behind the clouds: golden low, bright white at noon.
    veil = _mix((255, 175, 95), (255, 252, 235), elev)
    _soft_glow(raw, stride, w, h, sx, sy, int(min(w, h) * 0.5),
               veil, (0.30 + 0.25 * elev) * brightness)
    rnd = _prng(7)
    for _ in range(6):
        cx = int(((rnd() + phase * 0.1) % 1.1 - 0.05) * w)
        cy = int((0.16 + rnd() * 0.55) * h)
        rx = int((0.10 + rnd() * 0.14) * w)
        ry = max(2, int(rx * (0.48 + rnd() * 0.22)))
        # soft shadowed underside for depth, then a bright white top.
        _soft_ellipse(raw, stride, w, h, cx, int(cy + ry * 0.45),
                      int(rx * 0.85), max(2, int(ry * 0.7)), (205, 214, 232), 0.20)
        _soft_ellipse(raw, stride, w, h, cx, cy, rx, ry, (253, 253, 255), 0.46)


def _render_moon(raw, stride, w, h, sun):
    """The moon: rises in the east, arcs overhead, sets in the west."""
    mx, my, _elev = _sun_xy(w, h, sun)
    _soft_glow(raw, stride, w, h, mx, my, int(min(w, h) * 0.26), (210, 220, 255), 0.35)
    _soft_glow(raw, stride, w, h, mx, my, max(3, int(min(w, h) * 0.055)),
               (240, 244, 255), 0.95)
    return mx, my


def _render_stars(raw, stride, w, h, phase, count):
    """A twinkling starfield (fewer when clouds cover the sky)."""
    rnd = _prng(42)
    for _ in range(count):
        x = int(rnd() * w)
        y = int(rnd() * h * 0.9)
        tw = 0.5 + 0.5 * math.sin(2 * math.pi * (phase + rnd()))
        _blend_px(raw, stride, w, h, x, y, (255, 255, 255), (0.35 + 0.55 * rnd()) * tw)


def _render_night(raw, stride, w, h, phase, brightness, sun=None):
    """A twinkling starfield with the moon arcing across a clear night sky."""
    _render_stars(raw, stride, w, h, phase, max(30, w // 6))
    _render_moon(raw, stride, w, h, sun)


def _render_cloudnight(raw, stride, w, h, phase, brightness, sun=None):
    """A cloudy night: the moon + a few stars behind dark, moonlit clouds."""
    _render_stars(raw, stride, w, h, phase, max(14, w // 14))
    _render_moon(raw, stride, w, h, sun)
    rnd = _prng(9)
    for _ in range(5):
        cx = int(((rnd() + phase * 0.08) % 1.1 - 0.05) * w)
        cy = int((0.18 + rnd() * 0.55) * h)
        rx = int((0.11 + rnd() * 0.13) * w)
        ry = max(2, int(rx * (0.5 + rnd() * 0.2)))
        _soft_ellipse(raw, stride, w, h, cx, int(cy + ry * 0.4),
                      int(rx * 0.85), max(2, int(ry * 0.7)), (30, 38, 60), 0.30)
        _soft_ellipse(raw, stride, w, h, cx, cy, rx, ry, (86, 96, 128), 0.36)
        _soft_ellipse(raw, stride, w, h, cx, int(cy - ry * 0.3),
                      int(rx * 0.7), max(2, int(ry * 0.4)), (168, 178, 210), 0.16)


def _render_pattern(condition, raw, stride, w, h, phase, brightness, sun=None):
    c = (condition or "").lower()
    if "storm" in c:
        _render_storm(raw, stride, w, h, phase, brightness)
    elif "rain" in c:
        _render_rain(raw, stride, w, h, phase, brightness)
    elif "cloudnight" in c:
        _render_cloudnight(raw, stride, w, h, phase, brightness, sun)
    elif "night" in c:
        _render_night(raw, stride, w, h, phase, brightness, sun)
    elif "cloud" in c:
        _render_cloud(raw, stride, w, h, phase, brightness, sun)
    elif "clear" in c:
        _render_clear(raw, stride, w, h, phase, brightness, sun)


# ---------------------------------------------------------
# Build the weather wallpaper image
# ---------------------------------------------------------

def _drift(rgb, phase, strength):
    """
    Nudge a colour along a smooth cycle: a small hue rotation plus a gentle
    brightness breathe. *phase* (0..1) walks the cycle; *strength* (0..1)
    scales the amplitude. Kept small so the shift is noticeable, not jarring.
    """
    if strength <= 0:
        return rgb
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    h = (h + 0.05 * strength * math.sin(2 * math.pi * phase)) % 1.0
    v = max(0.0, min(1.0, v + 0.07 * strength * math.cos(2 * math.pi * phase)))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (_clamp(r * 255), _clamp(g * 255), _clamp(b * 255))


def shifted_base(r, g, b, tint_strength=0.4, phase=0.0, shift_strength=0.0):
    """The final tinted+drifted base colour (engine uses this for change-detection)."""
    # Desaturate toward a grey of the *same brightness* rather than a fixed
    # grey. Lower strength => less saturated, but never lighter or darker — so
    # day stays bright and night stays dark instead of everything going muddy.
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    neutral = (lum, lum, lum)
    base = _mix(neutral, (r, g, b), max(0.0, min(1.0, tint_strength)))
    return _drift(base, phase, max(0.0, min(1.0, shift_strength)))


def build_weather_image(r, g, b, brightness, tint_strength=0.4,
                        phase=0.0, shift_strength=0.0, condition="clear",
                        temperature=None, patterns=True, warmth=True,
                        sun=None, width=480, height=300):
    """
    Render the weather colour as a sky-like vertical gradient, overlay the
    condition's pattern, and return the file path. *tint_strength* (0..1)
    blends toward neutral grey; *phase*/*shift_strength* apply the subtle
    dynamic colour drift and drive the pattern's motion. When *warmth* is on
    and *temperature* is low, the whole palette is nudged toward a cosy amber.

    The image is deliberately small — a gradient upscales cleanly and the
    sparse pattern overlay keeps generation near-instant and memory tiny.
    """
    base = shifted_base(r, g, b, tint_strength, phase, shift_strength)

    # Sky gradient: lighter near the top, gently deeper toward the bottom.
    top = _mix(base, (255, 255, 255), 0.20 * brightness)
    bottom = _mix(base, (0, 0, 0), 0.36)

    # Cold outside → warm the palette so the desktop feels comforting.
    wf = warmth_factor(temperature) if warmth else 0.0
    if wf > 0:
        top = _mix(top, WARM_TINT, 0.22 * wf)
        bottom = _mix(bottom, WARM_TINT, 0.14 * wf)

    raw, stride = _build_raw_gradient(width, height, top, bottom)
    if patterns:
        _render_pattern(condition, raw, stride, width, height, phase, brightness, sun)

    # Phase + sun + condition are in the filename so each frame is a distinct
    # path — macOS/Windows only reload the desktop when the path changes.
    cond = (condition or "na").lower()[:6]
    sun_tag = "xx" if sun is None else f"{int(max(0.0, min(1.0, sun)) * 99):02d}"
    fname = (f"wallpaper_{cond}_{base[0]:02x}{base[1]:02x}{base[2]:02x}"
             f"_{int(brightness*100):03d}_{int(phase*1000):03d}_{sun_tag}.png")
    path = os.path.join(CACHE_DIR, fname)
    png = _encode_png(raw, width, height)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    _cleanup_old(keep=path)
    return path


def _cleanup_old(keep=None, keep_recent=3):
    """
    Remove old generated wallpapers so the cache dir stays small — but never
    the file just built (*keep*), the file the OS is currently showing
    (*_applied_path*), or the few most-recent frames. This avoids deleting the
    image the desktop points at (which would revert it to the default).
    """
    try:
        paths = [os.path.join(CACHE_DIR, f) for f in os.listdir(CACHE_DIR)
                 if f.startswith("wallpaper_") and f.endswith(".png")]
    except OSError:
        return

    def _mtime(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0

    paths.sort(key=_mtime, reverse=True)
    protected = set(paths[:max(0, keep_recent)])
    if keep:
        protected.add(keep)
    if _applied_path:
        protected.add(_applied_path)
    for p in paths:
        if p not in protected:
            try:
                os.remove(p)
            except OSError:
                pass


# ---------------------------------------------------------
# Set the desktop background
# ---------------------------------------------------------

def set_wallpaper(path: str, multi=True) -> bool:
    """Set *path* as the desktop background. Returns True on success.

    *multi*: when True, set it on every connected monitor; otherwise just the
    main one.
    """
    global _applied_path
    changed = (path != _applied_path)
    if sys.platform == "darwin":
        ok = _set_wallpaper_macos(path, multi)
    elif sys.platform == "win32":
        ok = _set_wallpaper_windows(path)
    else:
        print(f"[wallpaper] Not supported on {sys.platform!r} — skipping.")
        return False
    if ok:
        _applied_path = path
        # macOS 14+ (Sonoma/Sequoia): System Events updates the wallpaper
        # record but the visible desktop frequently doesn't repaint until
        # WallpaperAgent is restarted. Nudge it — but only on a genuine change,
        # so periodic same-image re-applies don't cause needless churn.
        if sys.platform == "darwin" and changed:
            _refresh_wallpaper_agent_macos()
    return ok


def _refresh_wallpaper_agent_macos():
    """Restart WallpaperAgent so the desktop actually repaints (Sequoia bug)."""
    try:
        subprocess.run(["killall", "WallpaperAgent"],
                       capture_output=True, text=True, timeout=5)
    except Exception as e:
        print(f"[wallpaper] Could not refresh WallpaperAgent: {e}")


def _set_wallpaper_macos(path: str, multi=True) -> bool:
    # Use a POSIX file reference — more reliable than a bare string path on
    # recent macOS (Sonoma/Sequoia). With *multi*, set every desktop (one per
    # display); otherwise just the main desktop.
    if multi:
        target = ('  repeat with d in desktops\n'
                  '    set picture of d to thePic\n'
                  '  end repeat\n')
    else:
        target = '  set picture of desktop 1 to thePic\n'
    script = (
        'tell application "System Events"\n'
        f'  set thePic to POSIX file "{path}"\n'
        f'{target}'
        'end tell'
    )
    try:
        res = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            # Fall back to the classic one-liner before giving up.
            res = subprocess.run(
                ["osascript", "-e",
                 f'tell application "System Events" to set picture of every desktop to "{path}"'],
                capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            print(f"[wallpaper] osascript error setting wallpaper: "
                  f"{res.stderr.strip() or res.returncode}")
            return False
        print(f"[wallpaper] macOS desktop set to {path}")
        return True
    except Exception as e:
        print(f"[wallpaper] Failed to set macOS wallpaper: {e}")
        return False


def _set_wallpaper_windows(path: str) -> bool:
    try:
        import ctypes
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
        )
        if not ok:
            raise OSError("SystemParametersInfoW returned 0")
        print(f"[wallpaper] Windows desktop set to {path}")
        return True
    except Exception as e:
        print(f"[wallpaper] Failed to set Windows wallpaper: {e}")
        return False


def apply_weather_wallpaper(r, g, b, brightness, tint_strength=0.4,
                            phase=0.0, shift_strength=0.0, condition="clear",
                            temperature=None, patterns=True, warmth=True,
                            sun=None, multi=True) -> bool:
    """Build the (optionally drifted) weather image and apply it."""
    path = build_weather_image(r, g, b, brightness, tint_strength,
                               phase=phase, shift_strength=shift_strength,
                               condition=condition, temperature=temperature,
                               patterns=patterns, warmth=warmth, sun=sun)
    return set_wallpaper(path, multi=multi)
