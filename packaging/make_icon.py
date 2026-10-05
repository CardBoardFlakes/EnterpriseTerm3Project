"""
Generate Flow's app icon (a sun in a dusk-to-day sky) as a 512x512 PNG.

Uses the same stdlib-only drawing helpers as the wallpaper, so no image
library is needed to *draw* it. PyInstaller converts the PNG into the
platform's .icns / .ico at build time (that step needs Pillow, which is a
build-only dependency — the app itself never imports it).

  python packaging/make_icon.py [output.png]
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import wallpaper  # noqa: E402

SIZE = 512
DEFAULT_OUT = os.path.join(HERE, "build", "flow.png")


def build_icon(size=SIZE):
    raw, stride = wallpaper._build_raw_gradient(size, size, (70, 140, 230), (255, 170, 110))
    c = size // 2
    wallpaper._soft_glow(raw, stride, size, size, c, c, int(size * 0.48), (255, 230, 160), 0.75)
    wallpaper._soft_glow(raw, stride, size, size, c, c, int(size * 0.22), (255, 250, 225), 1.0)
    wallpaper._soft_glow(raw, stride, size, size, c, c, int(size * 0.12), (255, 255, 245), 1.0)
    return wallpaper._encode_png(raw, size, size)


def main(out=DEFAULT_OUT):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(build_icon())
    print(f"[icon] wrote {out}")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
