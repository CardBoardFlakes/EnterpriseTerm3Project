# PyInstaller spec for Flow. Prefer `python packaging/build.py`, which makes
# the icon, runs this spec, and packages the result for distribution.
#
#   macOS   -> dist/Flow.app            (windowed app bundle)
#   Windows -> dist/Flow.exe            (single-file, no console window)
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821 (PyInstaller global)
ICON_PNG = os.path.join(SPECPATH, "build", "flow.png")  # noqa: F821
ICON = ICON_PNG if os.path.exists(ICON_PNG) else None
VERSION = os.environ.get("FLOW_VERSION", "0.0.0").lstrip("v")

a = Analysis(  # noqa: F821
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    # main.py imports the GUI lazily; list it so it is always bundled.
    hiddenimports=["gui"],
    excludes=["tests", "perf", "numpy", "PIL"],
)
pyz = PYZ(a.pure)  # noqa: F821

if sys.platform == "darwin":
    exe = EXE(  # noqa: F821
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="Flow",
        console=False,
        icon=ICON,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="Flow")  # noqa: F821
    app = BUNDLE(  # noqa: F821
        coll,
        name="Flow.app",
        icon=ICON,
        bundle_identifier="com.environmenttheme.flow",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Flow",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            # Accent colour, Dark/Light and wallpaper are set via osascript.
            "NSAppleEventsUsageDescription":
                "Flow sets your accent colour, appearance and desktop "
                "wallpaper to match the weather.",
        },
    )
else:
    exe = EXE(  # noqa: F821
        pyz, a.scripts, a.binaries, a.datas, [],
        name="Flow",
        console=False,
        icon=ICON,
        upx=False,
    )
