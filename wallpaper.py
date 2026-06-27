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


def write_gradient_png(path, width, height, top_rgb, bottom_rgb):
    """Write a vertical gradient PNG from top_rgb (y=0) to bottom_rgb."""
    raw = bytearray()
    for y in range(height):
        t = y / max(1, height - 1)
        r, g, b = _mix(top_rgb, bottom_rgb, t)
        row = bytes((r, g, b)) * width
        raw.append(0)          # filter type 0 (None) for this scanline
        raw.extend(row)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, colour type 2 (RGB)
    idat = zlib.compress(bytes(raw), 9)
    png = sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return path


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
                        phase=0.0, shift_strength=0.0, width=480, height=300):
    """
    Render the weather colour as a sky-like vertical gradient and return
    the file path. *tint_strength* (0..1) blends toward neutral grey;
    *phase*/*shift_strength* apply the subtle dynamic colour drift.

    The image is deliberately small — a gradient upscales cleanly and a tiny
    PNG keeps generation near-instant and memory use negligible.
    """
    base = shifted_base(r, g, b, tint_strength, phase, shift_strength)

    # Sky gradient: lighter near the top, darker toward the bottom.
    top = _mix(base, (255, 255, 255), 0.18 * brightness)
    bottom = _mix(base, (0, 0, 0), 0.45)

    fname = f"wallpaper_{base[0]:02x}{base[1]:02x}{base[2]:02x}_{int(brightness*100):03d}.png"
    path = os.path.join(CACHE_DIR, fname)
    write_gradient_png(path, width, height, top, bottom)
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
                            phase=0.0, shift_strength=0.0) -> bool:
    """Build the (optionally drifted) weather image and apply it."""
    path = build_weather_image(r, g, b, brightness, tint_strength,
                               phase=phase, shift_strength=shift_strength)
    return set_wallpaper(path)
