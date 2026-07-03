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


def _render_clear(raw, stride, w, h, phase, brightness):
    """A warm sun that drifts slowly across the upper sky."""
    cx = int(w * (0.18 + 0.64 * phase))
    cy = int(h * 0.22)
    _soft_glow(raw, stride, w, h, cx, cy, int(min(w, h) * 0.45),
               (255, 236, 190), 0.5 * brightness)
    _soft_glow(raw, stride, w, h, cx, cy, max(3, int(min(w, h) * 0.07)),
               (255, 250, 225), 0.85 * brightness)


def _render_cloud(raw, stride, w, h, phase, brightness):
    """Warm cream puffs drifting over a veiled-sun glow — cosy, not bleak."""
    _soft_glow(raw, stride, w, h, int(w * 0.7), int(h * 0.2),
               int(min(w, h) * 0.42), (255, 226, 180), 0.30 * brightness)
    rnd = _prng(7)
    for _ in range(4):
        base_x = rnd()
        cx = int(((base_x + phase * 0.15) % 1.1 - 0.05) * w)
        cy = int((0.22 + rnd() * 0.5) * h)
        rx = int((0.12 + rnd() * 0.12) * w)
        ry = max(2, int(rx * 0.55))
        _soft_ellipse(raw, stride, w, h, cx, cy, rx, ry, (247, 242, 236), 0.32)


def _render_night(raw, stride, w, h, phase, brightness):
    """A moon and a twinkling starfield over the deep night gradient."""
    mx, my = int(w * 0.78), int(h * 0.22)
    _soft_glow(raw, stride, w, h, mx, my, int(min(w, h) * 0.28), (215, 222, 255), 0.35)
    _soft_glow(raw, stride, w, h, mx, my, max(3, int(min(w, h) * 0.06)), (240, 242, 255), 0.95)
    rnd = _prng(42)
    for _ in range(max(30, w // 6)):
        x = int(rnd() * w)
        y = int(rnd() * h * 0.85)
        tw = 0.5 + 0.5 * math.sin(2 * math.pi * (phase + rnd()))
        _blend_px(raw, stride, w, h, x, y, (255, 255, 255), (0.35 + 0.55 * rnd()) * tw)


def _render_pattern(condition, raw, stride, w, h, phase, brightness):
    c = (condition or "").lower()
    if "storm" in c:
        _render_storm(raw, stride, w, h, phase, brightness)
    elif "rain" in c:
        _render_rain(raw, stride, w, h, phase, brightness)
    elif "night" in c:
        _render_night(raw, stride, w, h, phase, brightness)
    elif "cloud" in c:
        _render_cloud(raw, stride, w, h, phase, brightness)
    elif "clear" in c:
        _render_clear(raw, stride, w, h, phase, brightness)


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
    grey = (90, 90, 95)
    base = _mix(grey, (r, g, b), max(0.0, min(1.0, tint_strength)))
    return _drift(base, phase, max(0.0, min(1.0, shift_strength)))


def build_weather_image(r, g, b, brightness, tint_strength=0.4,
                        phase=0.0, shift_strength=0.0, condition="clear",
                        temperature=None, patterns=True, warmth=True,
                        width=480, height=300):
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

    # Sky gradient: lighter near the top, darker toward the bottom.
    top = _mix(base, (255, 255, 255), 0.18 * brightness)
    bottom = _mix(base, (0, 0, 0), 0.45)

    # Cold outside → warm the palette so the desktop feels comforting.
    wf = warmth_factor(temperature) if warmth else 0.0
    if wf > 0:
        top = _mix(top, WARM_TINT, 0.22 * wf)
        bottom = _mix(bottom, WARM_TINT, 0.14 * wf)

    raw, stride = _build_raw_gradient(width, height, top, bottom)
    if patterns:
        _render_pattern(condition, raw, stride, width, height, phase, brightness)

    # Phase + condition are in the filename so each frame is a distinct path —
    # macOS/Windows only reload the desktop when the path changes.
    cond = (condition or "na").lower()[:6]
    fname = (f"wallpaper_{cond}_{base[0]:02x}{base[1]:02x}{base[2]:02x}"
             f"_{int(brightness*100):03d}_{int(phase*1000):03d}.png")
    path = os.path.join(CACHE_DIR, fname)
    png = _encode_png(raw, width, height)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    _cleanup_old(keep=path)
    return path


def _cleanup_old(keep=None):
    """Remove previously generated wallpapers so the cache dir stays small."""
    try:
        for f in os.listdir(CACHE_DIR):
            full = os.path.join(CACHE_DIR, f)
            if f.startswith("wallpaper_") and f.endswith(".png") and full != keep:
                try:
                    os.remove(full)
                except OSError:
                    pass
    except OSError:
        pass


# ---------------------------------------------------------
# Set the desktop background
# ---------------------------------------------------------

def set_wallpaper(path: str) -> bool:
    """Set *path* as the desktop background. Returns True on success."""
    if sys.platform == "darwin":
        return _set_wallpaper_macos(path)
    elif sys.platform == "win32":
        return _set_wallpaper_windows(path)
    else:
        print(f"[wallpaper] Not supported on {sys.platform!r} — skipping.")
        return False


def _set_wallpaper_macos(path: str) -> bool:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to set picture of every desktop to "{path}"'],
            check=True, capture_output=True, text=True, timeout=10,
        )
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
                            temperature=None, patterns=True, warmth=True) -> bool:
    """Build the (optionally drifted) weather image and apply it."""
    path = build_weather_image(r, g, b, brightness, tint_strength,
                               phase=phase, shift_strength=shift_strength,
                               condition=condition, temperature=temperature,
                               patterns=patterns, warmth=warmth)
    return set_wallpaper(path)
