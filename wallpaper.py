"""
Weather-driven desktop wallpaper.

Generates a vertical gradient image (pure standard library — no Pillow)
from the weather/time colour and sets it as the desktop background on
both macOS and Windows.
"""

import os
import sys
import struct
import zlib
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

def build_weather_image(r, g, b, brightness, tint_strength=0.4,
                        width=1280, height=800):
    """
    Render the weather colour as a sky-like vertical gradient and return
    the file path. *tint_strength* (0..1) blends the whole image toward a
    neutral grey — lower = subtler, higher = more saturated colour.
    """
    base = (r, g, b)
    grey = (90, 90, 95)
    tint_strength = max(0.0, min(1.0, tint_strength))
    base = _mix(grey, base, tint_strength)

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


def apply_weather_wallpaper(r, g, b, brightness, tint_strength=0.4) -> bool:
    """Build the weather image and apply it. Returns True on success."""
    path = build_weather_image(r, g, b, brightness, tint_strength)
    return set_wallpaper(path)
